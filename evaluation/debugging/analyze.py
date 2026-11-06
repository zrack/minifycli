#!/usr/bin/env python3
"""Summarize saved debugging trials without running commands or calling models.

The returned dictionary is a public-safe metrics projection: no raw output,
source, patches, prompts, credentials, environment values or private paths.
CLI aggregate usage is counted once from each result.json, never from events.
"""
from __future__ import annotations

import argparse
from collections import Counter
import hashlib
import json
import math
from pathlib import Path
import re
import sys


VARIANTS = ("raw", "mini", "rtk")
TASK_IDS = frozenset({"R1", "R2", "R3", "J1", "J2", "J3"})
TOOLS = frozenset({"terminal", "read_file", "write_file", "replace_text", "list_files", "recover_output"})
USAGE_FIELDS = ("input_tokens", "cached_input_tokens", "output_tokens", "reasoning_tokens",
                "total_tokens", "uncached_input_plus_output_tokens")


class AnalysisError(ValueError):
    """Saved inputs violate registration or contain ambiguous identities."""


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise AnalysisError("duplicate JSON object key")
        result[key] = value
    return result


def _read(path: Path, root: Path):
    if path.is_symlink() or not path.resolve().is_relative_to(root):
        raise AnalysisError("saved input escapes the run root")
    try:
        return json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_unique_object,
                          parse_constant=lambda _: (_ for _ in ()).throw(AnalysisError("nonfinite JSON value")))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise AnalysisError("unreadable or malformed saved JSON: " + path.relative_to(root).as_posix()) from error


def _nonnegative_int(value) -> bool:
    return type(value) is int and value >= 0


def _finite_number(value) -> bool:
    return type(value) in (int, float) and math.isfinite(value) and value >= 0


def _usage(value) -> dict | None:
    if not isinstance(value, dict) or any(not _nonnegative_int(value.get(key)) for key in ("input_tokens", "output_tokens")):
        return None
    inputs, outputs = value["input_tokens"], value["output_tokens"]
    cached = value.get("cached_input_tokens")
    reasoning = value.get("reasoning_output_tokens", value.get("reasoning_tokens"))
    if cached is not None and (not _nonnegative_int(cached) or cached > inputs):
        return None
    if reasoning is not None and (not _nonnegative_int(reasoning) or reasoning > outputs):
        return None
    return {"input_tokens": inputs, "cached_input_tokens": cached, "output_tokens": outputs,
            "reasoning_tokens": reasoning, "total_tokens": inputs + outputs,
            "uncached_input_plus_output_tokens": None if cached is None else inputs - cached + outputs}


def _sum_usage(rows: list[dict]) -> dict:
    usages = [row["usage"] for row in rows if row["usage"] is not None]
    return {"observations": len(usages), **{
        key: (sum(value[key] for value in usages) if usages and all(value[key] is not None for value in usages) else None)
        for key in USAGE_FIELDS}}


def _test_command(argv) -> bool:
    if not isinstance(argv, list) or not argv or not all(isinstance(a, str) for a in argv):
        return False
    return (argv[0] == "cargo" and len(argv) > 1 and argv[1] in {"test", "nextest"}
            or argv[0] == "npm" and len(argv) > 1 and (argv[1] in {"test", "t"}
                or argv[1] in {"run", "run-script"} and len(argv) > 2 and argv[2].startswith("test"))
            or argv[0] == "node" and any(arg == "--test" or arg.startswith("--test=") for arg in argv[1:]))


def _tool_metrics(path: Path, root: Path, expected_calls) -> tuple[dict, list[str]]:
    counters = {name: 0 for name in ("actions", "terminal_commands", "recovery_calls", "test_commands",
                "repeated_identical_test_commands", "native_filtered_commands", "passthrough_commands",
                "mini_wrapped_commands", "terminal_timeouts", "incomplete_terminal_captures", "tool_errors",
                "visible_response_bytes")}
    counters.update(reference_tokens=None)
    if not path.exists():
        return {**counters, "log_available": False}, ([] if expected_calls == 0 else ["missing_tool_log"])
    if path.is_symlink() or not path.resolve().is_relative_to(root):
        raise AnalysisError("tool log escapes run root")
    seen, tests = set(), Counter()
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeError) as error:
        raise AnalysisError("unreadable saved tool log") from error
    for line in lines:
        if not line.strip():
            continue
        try:
            item = json.loads(line, object_pairs_hook=_unique_object)
        except json.JSONDecodeError as error:
            raise AnalysisError("malformed saved tool log") from error
        if not isinstance(item, dict) or type(item.get("index")) is not int or item["index"] != len(seen) + 1 or item["index"] in seen:
            raise AnalysisError("duplicate or nonsequential tool call index")
        if item.get("tool") not in TOOLS or not isinstance(item.get("arguments"), dict) or not isinstance(item.get("response"), dict) or not isinstance(item.get("visible"), dict):
            raise AnalysisError("malformed saved tool call")
        seen.add(item["index"])
        tool, args, response, visible = item["tool"], item["arguments"], item["response"], item["visible"]
        counters["actions"] += 1
        counters["visible_response_bytes"] += len(json.dumps(visible, ensure_ascii=False).encode("utf-8"))
        counters["tool_errors"] += int("error" in visible or response.get("ok") is False)
        if tool == "recover_output":
            counters["recovery_calls"] += 1
        if tool == "terminal":
            counters["terminal_commands"] += 1
            counters["native_filtered_commands"] += int(response.get("route") == "native")
            counters["passthrough_commands"] += int(response.get("route") == "passthrough")
            counters["mini_wrapped_commands"] += int(response.get("route") == "mini-record")
            counters["terminal_timeouts"] += int(response.get("timed_out") is True)
            counters["incomplete_terminal_captures"] += int(response.get("capture_complete") is False)
            if _test_command(args.get("argv")):
                counters["test_commands"] += 1
                tests[json.dumps({"argv": args["argv"], "cwd": args.get("cwd", ".")}, sort_keys=True)] += 1
    counters["repeated_identical_test_commands"] = sum(number - 1 for number in tests.values())
    return {**counters, "log_available": True}, ([] if expected_calls == len(seen) else ["tool_call_count_mismatch"])


def _validate_plan(plan: dict) -> dict[str, dict]:
    if not isinstance(plan, dict) or plan.get("schema") != 1 or plan.get("repetitions") != 2:
        raise AnalysisError("expected registered schema 1 with exactly two repetitions")
    tasks = plan.get("tasks")
    if not isinstance(tasks, list) or len(tasks) != 6 or any(not isinstance(task, dict) for task in tasks) or {task.get("id") for task in tasks} != TASK_IDS:
        raise AnalysisError("registration must contain exactly the six declared task IDs")
    trials = plan.get("trials")
    if not isinstance(trials, list) or len(trials) != 36:
        raise AnalysisError("registration must contain exactly 36 trials")
    by_id, combinations = {}, set()
    for trial in trials:
        if not isinstance(trial, dict) or not isinstance(trial.get("id"), str) or re.fullmatch(r"trial-[0-9]{3}", trial["id"]) is None:
            raise AnalysisError("invalid registered trial ID")
        if trial["id"] in by_id:
            raise AnalysisError("duplicate registered trial ID")
        if trial.get("task_id") not in TASK_IDS or trial.get("variant") not in VARIANTS or type(trial.get("repetition")) is not int or trial["repetition"] not in {1, 2}:
            raise AnalysisError("invalid registered task/repetition/variant")
        combination = (trial["task_id"], trial["repetition"], trial["variant"])
        if combination in combinations:
            raise AnalysisError("duplicate registered task/repetition/variant")
        combinations.add(combination)
        by_id[trial["id"]] = trial
    return by_id


def _trial(root: Path, trial: dict, plan_hash: str) -> dict:
    directory = root / "trials" / trial["id"]
    result_path = directory / "result.json"
    evaluations = [path for path in (directory / "evaluation.json", directory / "evaluation/evaluation.json") if path.exists()]
    if len(evaluations) > 1:
        raise AnalysisError("duplicate evaluation for " + trial["id"])
    row = {key: trial[key] for key in ("id", "task_id", "repetition", "variant")}
    row.update(language="rust" if trial["task_id"].startswith("R") else "javascript", result_observed=False,
               evaluation_observed=bool(evaluations), correct_repair=None, evaluation_correct_repair=None,
               valid=False, exclusions=[], usage=None, wall_seconds=None, patch_bytes=None,
               protocol_deviations_count=None, session_errors_count=None, tools=None,
               baseline_regression=None, hidden_failure=None, timed_out=None)
    if not result_path.exists():
        row["exclusions"].append("missing_result")
        if not evaluations:
            row["exclusions"].append("missing_evaluation")
        return row
    result = _read(result_path, root)
    if not isinstance(result, dict) or any(result.get(key) != trial[key] for key in ("id", "task_id", "repetition", "variant")):
        raise AnalysisError("result identity differs from registration: " + trial["id"])
    if "plan_sha256" in result and result["plan_sha256"] != plan_hash:
        raise AnalysisError("result plan hash differs from registration")
    row["result_observed"] = True
    row["usage"] = _usage(result.get("usage"))
    if row["usage"] is None:
        row["exclusions"].append("missing_or_invalid_usage")
    if type(result.get("timed_out")) is not bool:
        row["exclusions"].append("missing_timeout_status")
    row["timed_out"] = result.get("timed_out") is True
    if row["timed_out"]:
        row["exclusions"].append("session_timeout")
    if type(result.get("process_exit_code")) is not int or result["process_exit_code"] != 0:
        row["exclusions"].append("session_process_failure")
    if type(result.get("turn_completed_count")) is not int or result["turn_completed_count"] != 1:
        row["exclusions"].append("incomplete_or_multiple_cli_turns")
    deviations = result.get("protocol_deviations")
    if not isinstance(deviations, list):
        row["exclusions"].append("missing_protocol_audit")
    else:
        row["protocol_deviations_count"] = len(deviations)
        if deviations:
            row["exclusions"].append("protocol_deviations")
    errors = result.get("session_errors")
    if not isinstance(errors, list):
        row["exclusions"].append("missing_session_error_audit")
    else:
        row["session_errors_count"] = len(errors)
        if errors:
            row["exclusions"].append("session_errors")
    if _finite_number(result.get("wall_seconds")):
        row["wall_seconds"] = result["wall_seconds"]
    else:
        row["exclusions"].append("invalid_wall_time")
    calls = result.get("mcp_calls")
    if not _nonnegative_int(calls):
        row["exclusions"].append("missing_tool_call_count")
    row["tools"], tool_exclusions = _tool_metrics(directory / "artifacts/tools.jsonl", root, calls)
    row["exclusions"].extend(tool_exclusions)
    if evaluations:
        evaluation = _read(evaluations[0], root)
        if not isinstance(evaluation, dict) or evaluation.get("task_id") != trial["task_id"] or type(evaluation.get("correct_repair")) is not bool:
            raise AnalysisError("evaluation identity or correctness type is invalid: " + trial["id"])
        row["evaluation_correct_repair"] = evaluation["correct_repair"]
        row["correct_repair"] = evaluation["correct_repair"] and row["protocol_deviations_count"] == 0
        if evaluation.get("infrastructure_errors"):
            row["exclusions"].append("evaluation_infrastructure_failure")
        if evaluation.get("frozen_workspace_unchanged") is False:
            row["exclusions"].append("frozen_workspace_mutated")
        checks = evaluation.get("checks", {})
        if not isinstance(checks, dict) or any(not isinstance(check, dict) for check in checks.values()):
            raise AnalysisError("malformed evaluation checks")
        if any(check.get("timed_out") is True for check in checks.values()):
            row["exclusions"].append("evaluation_timeout")
        if any(check.get("spawn_error") is not None for check in checks.values()):
            row["exclusions"].append("evaluation_spawn_failure")
        baseline = checks.get("pristine_baseline")
        hidden = checks.get("hidden")
        row["baseline_regression"] = None if baseline is None else baseline.get("passed") is False
        row["hidden_failure"] = None if hidden is None else hidden.get("passed") is False
        patch_bytes = evaluation.get("patch", {}).get("bytes") if isinstance(evaluation.get("patch"), dict) else result.get("candidate_patch_bytes")
        row["patch_bytes"] = patch_bytes if _nonnegative_int(patch_bytes) else None
    else:
        row["exclusions"].append("missing_evaluation")
    row["exclusions"] = sorted(set(row["exclusions"]))
    row["valid"] = not row["exclusions"]
    return row


def _aggregate(rows: list[dict]) -> dict:
    tool_rows = [row["tools"] for row in rows if row["tools"] is not None]
    return {"planned_sessions": len(rows), "result_observations": sum(row["result_observed"] for row in rows),
            "evaluation_observations": sum(row["evaluation_observed"] for row in rows),
            "valid_sessions": sum(row["valid"] for row in rows),
            "correct_repairs": sum(row["correct_repair"] is True for row in rows),
            "incorrect_repairs": sum(row["correct_repair"] is False for row in rows),
            "unknown_correctness": sum(row["correct_repair"] is None for row in rows),
            "observed_usage": _sum_usage(rows),
            "observed_wall_seconds": sum(row["wall_seconds"] for row in rows if row["wall_seconds"] is not None),
            "observed_patch_bytes": sum(row["patch_bytes"] for row in rows if row["patch_bytes"] is not None),
            "exclusion_counts": dict(sorted(Counter(reason for row in rows for reason in row["exclusions"]).items())),
            "tools": {key: sum(tool[key] for tool in tool_rows) for key in tool_rows[0] if type(tool_rows[0][key]) is int} if tool_rows else None}


def _ratio(numerator, denominator):
    return numerator / denominator if numerator is not None and denominator is not None and denominator > 0 else None


def _attributed(root: Path, plan_hash: str, wins: list[str]) -> list[str]:
    path = root / "attribution.json"
    if not path.exists():
        return []
    value = _read(path, root)
    if not isinstance(value, dict) or value.get("schema") != 1 or value.get("plan_sha256") != plan_hash:
        raise AnalysisError("attribution receipt does not match registration")
    if value.get("reviewed") is not True or not isinstance(value.get("reviewed_by"), str) or not value["reviewed_by"].strip():
        return []
    tasks = value.get("tasks", [])
    if not isinstance(tasks, list):
        raise AnalysisError("invalid attribution task list")
    seen, attributed = set(), []
    for task in tasks:
        if not isinstance(task, dict) or task.get("task_id") not in TASK_IDS or task["task_id"] in seen:
            raise AnalysisError("unknown or duplicate attribution task")
        seen.add(task["task_id"])
        evidence = task.get("evidence_sha256")
        if task["task_id"] in wins and task.get("output_related") is True and isinstance(evidence, list) and evidence and all(isinstance(item, str) and re.fullmatch(r"[0-9a-f]{64}", item) for item in evidence):
            attributed.append(task["task_id"])
    return sorted(attributed)


def summarize(run_root: Path) -> dict:
    root = Path(run_root).resolve(strict=True)
    plan_path = root / "plan.json"
    plan = _read(plan_path, root)
    plan_hash = sha(plan_path.read_bytes())
    registration = _read(root / "registration.json", root)
    if not isinstance(registration, dict) or registration.get("plan_sha256") != plan_hash:
        raise AnalysisError("plan bytes differ from the registered SHA-256")
    trials = _validate_plan(plan)
    for path in (root / "trials").glob("*/result.json"):
        if path.parent.name not in trials:
            raise AnalysisError("unregistered result ID")
    rows = [_trial(root, trial, plan_hash) for trial in plan["trials"]]
    indexed = {(row["task_id"], row["repetition"], row["variant"]): row for row in rows}
    triples = [(task, repetition) for task in sorted(TASK_IDS) for repetition in (1, 2)]
    paired = [(task, repetition) for task, repetition in triples if all(indexed[(task, repetition, variant)]["valid"] for variant in VARIANTS)]
    success = [(task, repetition) for task, repetition in paired if all(indexed[(task, repetition, variant)]["correct_repair"] for variant in VARIANTS)]
    def corpus(keys):
        return {variant: _sum_usage([indexed[(task, repetition, variant)] for task, repetition in keys]) for variant in VARIANTS}
    paired_usage = corpus(paired)
    language_usage = {language: corpus([key for key in paired if key[0].startswith(prefix)]) for language, prefix in (("rust", "R"), ("javascript", "J"))}
    complete = len(paired) == len(triples)
    by_variant = {variant: _aggregate([row for row in rows if row["variant"] == variant]) for variant in VARIANTS}
    ratio = _ratio(paired_usage["mini"]["total_tokens"], paired_usage["rtk"]["total_tokens"])
    language_ratios = {language: _ratio(values["mini"]["total_tokens"], values["rtk"]["total_tokens"]) for language, values in language_usage.items()}
    correctness_noninferior = all(by_variant["mini"]["correct_repairs"] >= by_variant[variant]["correct_repairs"] for variant in ("raw", "rtk"))
    mini_tokens, rtk_tokens = paired_usage["mini"]["total_tokens"], paired_usage["rtk"]["total_tokens"]
    resource_numbers_met = (ratio is not None and mini_tokens * 5 <= rtk_tokens * 4
                            and correctness_noninferior and all(value is not None and value < 1 for value in language_ratios.values()))
    wins, reverse = [], []
    for task in sorted(TASK_IDS):
        mini = [indexed[(task, repetition, "mini")]["correct_repair"] for repetition in (1, 2)]
        rtk = [indexed[(task, repetition, "rtk")]["correct_repair"] for repetition in (1, 2)]
        if all(value is True for value in mini) and all(value is False for value in rtk):
            wins.append(task)
        if all(value is True for value in rtk) and all(value is False for value in mini):
            reverse.append(task)
    task_numbers_met = len(wins) >= 2 and not reverse
    attributed = _attributed(root, plan_hash, wins)
    if not complete:
        decision = "inconclusive"
    elif resource_numbers_met:
        decision = "continue_bounded_compressor_experiment"
    elif task_numbers_met:
        decision = "continue_bounded_compressor_experiment" if len(attributed) >= 2 else "requires_attribution"
    else:
        decision = "stop_compressor_expansion"
    # Only inert identifiers from configuration are exported; never executable
    # paths, user identities, prompts, errors or attribution free text.
    identifier = lambda value: value if isinstance(value, str) and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,79}", value) else None
    return {"schema": 1, "plan_sha256": plan_hash, "model": identifier(plan.get("model")),
            "reasoning_effort": identifier(plan.get("reasoning_effort")), "planned_sessions": 36,
            "observed_results": sum(row["result_observed"] for row in rows),
            "observed_evaluations": sum(row["evaluation_observed"] for row in rows),
            "all_planned_observations_valid": complete, "valid_paired_triples": len(paired),
            "excluded_paired_triples": len(triples) - len(paired), "by_variant": by_variant,
            "by_language": {language: {variant: _aggregate([row for row in rows if row["language"] == language and row["variant"] == variant]) for variant in VARIANTS} for language in language_usage},
            "primary_paired_usage": paired_usage, "paired_usage_by_language": language_usage,
            "successful_repair_common_subset": {"paired_triples": len(success), "usage": corpus(success)},
            "resource_gate": {"status": ("met" if resource_numbers_met else "not_met") if complete else "inconclusive",
                "mini_to_rtk_total_token_ratio": ratio, "mini_to_rtk_ratio_by_language": language_ratios,
                "correctness_count_noninferior_to_raw_and_rtk": correctness_noninferior,
                "requires_all_36_valid": True},
            "task_gate": {"status": ("met" if len(attributed) >= 2 else "requires_attribution") if complete and task_numbers_met else ("not_met" if complete else "inconclusive"),
                "consistent_mini_win_tasks": wins, "consistent_reverse_tasks": reverse,
                "reviewed_output_attribution_tasks": attributed},
            "decision": decision, "trials": rows,
            "definitions": {"primary_tokens": "CLI aggregate input_tokens + output_tokens, once per session; cached input included and reasoning is not added again",
                "uncached_proxy": "input_tokens - cached_input_tokens + output_tokens, unavailable if cached input was not reported; not a monetary cost",
                "paired_corpus": "complete valid raw/Mini/RTK task-repetition triples, without selecting successful repairs",
                "test_command": "cargo test/nextest, npm test/t or run script beginning test, node --test",
                "repeated_test": "extra occurrences of identical literal test argv and cwd within a trial",
                "reference_tokens": "not measured by this stdlib analyzer; visible_response_bytes counts serialized solver-visible tool responses",
                "attribution": "manually reviewed evidence receipt is required; outcome differences alone do not establish an output-related cause",
                "limits": "six historical tasks, dependent repositories, two repetitions; no significance, general superiority, market demand or causal claim"}}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, help="Create a new public-safe JSON summary; never overwrite")
    args = parser.parse_args()
    try:
        result = summarize(args.run_root)
        if args.output:
            with args.output.open("x", encoding="utf-8") as handle:
                json.dump(result, handle, ensure_ascii=True, sort_keys=True, indent=2)
                handle.write("\n")
        else:
            print(json.dumps(result, ensure_ascii=True, sort_keys=True, indent=2))
    except (AnalysisError, OSError) as error:
        # No OS exception message: those can contain private absolute paths.
        print(json.dumps({"ok": False, "error": str(error) if isinstance(error, AnalysisError) else type(error).__name__}), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
