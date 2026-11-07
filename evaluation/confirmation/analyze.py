#!/usr/bin/env python3
"""Public-safe, all-attempt priced-usage confirmation from saved local evidence.

No model calls, command executions, account reads, or currency conversion occur.
Cost totals use the frozen Decimal calculator. The task-cluster bootstrap is a
small convenience-sample stability check, not a population confidence claim.
"""
from __future__ import annotations

import argparse
from collections import Counter
from decimal import Decimal, localcontext
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import random
import re
import sys

HERE = Path(__file__).resolve().parent
_spec = importlib.util.spec_from_file_location("confirmation_cost_calculator", HERE / "costs.py")
costs = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(costs)
VARIANTS = ("raw", "mini", "rtk")
TASK_IDS = tuple("C-" + group + str(number) for group in ("R", "J") for number in (1, 2, 3))
BOOTSTRAP_RESAMPLES, BOOTSTRAP_SEED = 20_000, 20261107
TOOLS = {"terminal", "read_file", "write_file", "replace_text", "list_files", "recover_output"}
USAGE_FIELDS = ("input_tokens", "cached_input_tokens", "uncached_input_tokens", "output_tokens", "reasoning_output_tokens")
BOUNDARY = "Observed CLI usage priced at published Standard credit rates; not an invoice, subscription cost, attributed account deduction or USD charge."


class AnalysisError(ValueError):
    """Saved evidence is malformed, inconsistent, or outside registration."""


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _number(value: Decimal | None) -> str | None:
    if value is None:
        return None
    text = format(value, "f")
    return text.rstrip("0").rstrip(".") if "." in text else text


def _unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise AnalysisError("duplicate JSON object key")
        result[key] = value
    return result


def _read(path: Path, root: Path):
    if path.is_symlink() or not path.resolve().is_relative_to(root):
        raise AnalysisError("saved evidence escapes the run root")
    try:
        return json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_unique,
                          parse_constant=lambda _: (_ for _ in ()).throw(AnalysisError("nonfinite JSON value")))
    except (OSError, UnicodeError, json.JSONDecodeError) as error:
        raise AnalysisError("unreadable or malformed saved JSON") from error


def _integer(value):
    return type(value) is int and value >= 0


def _finite(value):
    return type(value) in (int, float) and math.isfinite(value) and value >= 0


def _validate_plan(plan: dict) -> dict[str, dict]:
    if not isinstance(plan, dict) or plan.get("schema") != 1 or type(plan.get("repetitions")) is not int or plan["repetitions"] != 3:
        raise AnalysisError("expected schema 1 and exactly three repetitions")
    if type(plan.get("seed")) is not int or plan["seed"] != BOOTSTRAP_SEED:
        raise AnalysisError("confirmation seed differs from registration protocol")
    tasks, trials = plan.get("tasks"), plan.get("trials")
    if not isinstance(tasks, list) or len(tasks) != 6 or any(not isinstance(task, dict) for task in tasks) or {task.get("id") for task in tasks} != set(TASK_IDS):
        raise AnalysisError("expected exactly the six confirmation task IDs")
    if not isinstance(trials, list) or len(trials) != 54:
        raise AnalysisError("expected exactly 54 planned attempts")
    card = costs.validate_rate_card(plan.get("cost_model"))
    if (plan.get("model") != "gpt-6.1-sol" or plan.get("reasoning_effort") != "ultra"
            or card["model"] != plan["model"] or card["service_tier"] != "standard"
            or card["per_million_tokens"] != {"uncached_input": "50", "cached_input": "2.5", "output": "250"}):
        raise AnalysisError("model, speed or rate card differs from the confirmation protocol")
    by_id, combinations = {}, set()
    for trial in trials:
        if not isinstance(trial, dict) or not isinstance(trial.get("id"), str) or re.fullmatch(r"trial-[0-9]{3}", trial["id"]) is None:
            raise AnalysisError("invalid trial identity")
        if trial["id"] in by_id:
            raise AnalysisError("duplicate registered trial ID")
        if (trial.get("task_id") not in TASK_IDS or trial.get("variant") not in VARIANTS
                or type(trial.get("repetition")) is not int or trial["repetition"] not in {1, 2, 3}):
            raise AnalysisError("invalid registered task/repetition/treatment")
        combination = (trial["task_id"], trial["repetition"], trial["variant"])
        if combination in combinations:
            raise AnalysisError("duplicate registered task/repetition/treatment")
        combinations.add(combination)
        by_id[trial["id"]] = trial
    return by_id


def _argv_proof(argv, plan: dict) -> bool:
    """Independently establish requested alias/effort/Standard speed from argv."""
    if (not isinstance(argv, list) or not argv or any(not isinstance(arg, str) for arg in argv)
            or "--ignore-user-config" not in argv):
        return False
    settings, disabled, enabled = {}, set(), set()
    index = 1
    try:
        while index < len(argv):
            arg = argv[index]
            if arg in {"-c", "--config"}:
                index += 1
                key, value = argv[index].split("=", 1)
                if key in settings:
                    return False
                settings[key] = json.loads(value)
            elif arg in {"--disable", "--enable"}:
                index += 1
                (disabled if arg == "--disable" else enabled).add(argv[index])
            elif arg.startswith("--disable="):
                disabled.add(arg.split("=", 1)[1])
            elif arg.startswith("--enable="):
                enabled.add(arg.split("=", 1)[1])
            elif arg in {"--model", "-m"}:
                index += 1
                if argv[index] != plan["model"]:
                    return False
            elif arg.startswith(("--model=", "--service-tier", "--config=", "-cservice_tier", "-cmodel", "-cfeatures")) or arg in {"--fast", "--ultrafast"}:
                return False
            index += 1
    except (IndexError, ValueError, TypeError, json.JSONDecodeError):
        return False
    speed = {"fast_mode", "ultrafast_mode"}
    if not speed <= disabled or speed & enabled:
        return False
    if any(settings.get("features." + key, False) is not False for key in speed):
        return False
    features = settings.get("features", {})
    if not isinstance(features, dict) or any(features.get(key, False) is not False for key in speed):
        return False
    return (settings.get("model") == plan["model"] and settings.get("model_reasoning_effort") == plan["reasoning_effort"]
            and settings.get("service_tier") == "default")


def _test_command(argv, baseline) -> bool:
    if not isinstance(argv, list) or not argv:
        return False
    return (argv == baseline or argv[0] == "cargo" and len(argv) > 1 and argv[1] == "test"
            or argv[0] == "npm" and len(argv) > 1 and (argv[1] in {"test", "t"}
                or argv[1] in {"run", "run-script"} and len(argv) > 2 and (argv[2].startswith("test") or argv[2] == "unit"))
            or argv[0] == "node" and "--test" in argv)


def _tools(path: Path, root: Path, expected_calls, baseline) -> tuple[dict, list[str]]:
    metrics = {key: 0 for key in ("actions", "terminal_commands", "test_commands", "repeated_test_commands", "recovery_calls",
               "native_filtered_commands", "passthrough_commands", "mini_wrapped_commands", "terminal_timeouts",
               "incomplete_terminal_captures", "tool_errors", "visible_response_bytes")}
    if not path.exists():
        return {**metrics, "available": False}, ([] if expected_calls == 0 else ["missing_tool_log"])
    if path.is_symlink() or not path.resolve().is_relative_to(root):
        raise AnalysisError("tool log escapes the run root")
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeError) as error:
        raise AnalysisError("unreadable tool log") from error
    tests = Counter()
    for line in lines:
        if not line.strip():
            continue
        try:
            item = json.loads(line, object_pairs_hook=_unique,
                              parse_constant=lambda _: (_ for _ in ()).throw(AnalysisError("nonfinite tool JSON")))
        except json.JSONDecodeError as error:
            raise AnalysisError("malformed tool log") from error
        if (not isinstance(item, dict) or type(item.get("index")) is not int or item["index"] != metrics["actions"] + 1
                or item.get("tool") not in TOOLS or any(not isinstance(item.get(key), dict) for key in ("arguments", "response", "visible"))):
            raise AnalysisError("duplicate, nonsequential or malformed tool call")
        metrics["actions"] += 1
        tool, args, response, visible = (item[key] for key in ("tool", "arguments", "response", "visible"))
        metrics["visible_response_bytes"] += len(json.dumps(visible, ensure_ascii=False).encode())
        metrics["tool_errors"] += int("error" in visible or response.get("ok") is False)
        metrics["recovery_calls"] += int(tool == "recover_output")
        if tool == "terminal":
            metrics["terminal_commands"] += 1
            metrics["native_filtered_commands"] += int(response.get("route") == "native")
            metrics["passthrough_commands"] += int(response.get("route") == "passthrough")
            metrics["mini_wrapped_commands"] += int(response.get("route") == "mini-record")
            metrics["terminal_timeouts"] += int(response.get("timed_out") is True)
            metrics["incomplete_terminal_captures"] += int(response.get("capture_complete") is False)
            if _test_command(args.get("argv"), baseline):
                metrics["test_commands"] += 1
                tests[json.dumps({"argv": args["argv"], "cwd": args.get("cwd", ".")}, sort_keys=True)] += 1
    metrics["repeated_test_commands"] = sum(value - 1 for value in tests.values())
    return {**metrics, "available": True}, ([] if expected_calls == metrics["actions"] else ["tool_call_count_mismatch"])


def _grade(directory: Path, root: Path, task_id: str) -> tuple[dict, list[str]]:
    paths = [p for p in (directory / "evaluation/evaluation.json", directory / "evaluation.json") if p.exists()]
    if len(paths) > 1:
        raise AnalysisError("duplicate evaluations")
    if not paths:
        return {"observed": False, "correct_repair": None, "baseline_regression": None, "hidden_failure": None}, ["missing_grade"]
    value = _read(paths[0], root)
    if not isinstance(value, dict) or value.get("task_id") != task_id or type(value.get("correct_repair")) is not bool:
        raise AnalysisError("evaluation identity or correctness is malformed")
    reasons = []
    for key, reason in (("restore_errors", "test_restoration_failure"), ("infrastructure_errors", "evaluation_infrastructure_failure")):
        if not isinstance(value.get(key), list):
            reasons.append("missing_evaluation_audit")
        elif value[key]:
            reasons.append(reason)
    if value.get("frozen_workspace_unchanged") is not True:
        reasons.append("frozen_workspace_integrity_unverified")
    checks = value.get("checks")
    if not isinstance(checks, dict) or any(not isinstance(check, dict) for check in checks.values()):
        raise AnalysisError("malformed grading checks")
    for name in ("candidate_baseline", "pristine_baseline", "hidden"):
        check = checks.get(name)
        if check is None:
            reasons.append("missing_grading_check")
        elif type(check.get("passed")) is not bool:
            raise AnalysisError("grading check lacks a boolean outcome")
        elif type(check.get("timed_out")) is not bool or "spawn_error" not in check or (type(check.get("exit_code")) is not int and check.get("spawn_error") is None):
            reasons.append("missing_grading_check_audit")
        elif check.get("spawn_error") is not None:
            reasons.append("grading_spawn_failure")
        elif check["passed"] != (check["exit_code"] == 0 and check["timed_out"] is False):
            raise AnalysisError("grading check status conflicts with its exit code or timeout")
    if value["correct_repair"] and any(checks.get(name, {}).get("passed") is not True for name in ("candidate_baseline", "pristine_baseline", "hidden")):
        raise AnalysisError("correct repair conflicts with grading checks")
    patch = value.get("patch")
    return {"observed": True, "correct_repair": value["correct_repair"] if not reasons else None,
            "baseline_regression": checks.get("pristine_baseline", {}).get("passed") is False,
            "hidden_failure": checks.get("hidden", {}).get("passed") is False,
            "grading_timeout_checks": sum(checks.get(name, {}).get("timed_out") is True
                                          for name in ("candidate_baseline", "pristine_baseline", "hidden")),
            "test_changes_detected": (value.get("test_changes_detected", value.get("added_test_coverage"))
                                     if type(value.get("test_changes_detected", value.get("added_test_coverage"))) is bool else None),
            "patch_bytes": patch.get("bytes") if isinstance(patch, dict) and _integer(patch.get("bytes")) else None}, sorted(set(reasons))


def _trial(root: Path, trial: dict, plan: dict, plan_hash: str, task: dict) -> dict:
    directory = root / "trials" / trial["id"]
    row = {key: trial[key] for key in ("id", "task_id", "repetition", "variant")}
    row.update(language="rust" if trial["task_id"].startswith("C-R") else "javascript", observed=False,
               operational_complete=False, exclusions=[], usage=None, usage_complete=False, model=None, service_tier=None,
               standard_speed_verified=False, timed_out=None, correct_repair=None, wall_seconds=None, protocol_deviations=[],
               session_errors_count=None, tools=None, argv_sha256=None,
               priced_cost={"known": False, "amount": None, "components": None, "unknown_reasons": ["missing_result"]})
    grade, grade_reasons = _grade(directory, root, trial["task_id"])
    row["grade"] = grade
    row["exclusions"].extend(grade_reasons)
    path = directory / "result.json"
    if not path.exists():
        row["exclusions"].append("missing_result")
        return row
    value = _read(path, root)
    if (not isinstance(value, dict) or type(value.get("repetition")) is not int
            or any(value.get(key) != trial[key] for key in ("id", "task_id", "repetition", "variant"))):
        raise AnalysisError("trial result identity differs from registration")
    if value.get("plan_sha256") != plan_hash:
        raise AnalysisError("trial result plan hash differs from registration")
    row["observed"] = True
    row["usage"] = value.get("usage")
    row["usage_complete"] = value.get("usage_complete") is True
    if not row["usage_complete"]:
        row["exclusions"].append("incomplete_usage_telemetry")
    row["timed_out"] = value.get("timed_out") if type(value.get("timed_out")) is bool else None
    if row["timed_out"] is None:
        row["exclusions"].append("missing_timeout_status")
    elif row["timed_out"]:
        row["exclusions"].append("session_timeout")
    if type(value.get("process_exit_code")) is not int or value["process_exit_code"] != 0:
        row["exclusions"].append("session_process_failure")
    if type(value.get("turn_completed_count")) is not int or value["turn_completed_count"] != 1:
        row["exclusions"].append("incomplete_or_multiple_cli_turns")
    deviations = value.get("protocol_deviations")
    if not isinstance(deviations, list):
        row["exclusions"].append("missing_protocol_audit")
    else:
        row["protocol_deviations"] = ["recorded_deviation"] * len(deviations)
        if deviations:
            row["exclusions"].append("protocol_deviation")
    errors = value.get("session_errors")
    if not isinstance(errors, list):
        row["exclusions"].append("missing_session_error_audit")
    else:
        row["session_errors_count"] = len(errors)
        if errors:
            row["exclusions"].append("session_infrastructure_error")
    if _finite(value.get("wall_seconds")):
        row["wall_seconds"] = value["wall_seconds"]
    else:
        row["exclusions"].append("invalid_wall_time")
    argv_path = directory / "argv.json"
    if not argv_path.exists():
        row["exclusions"].append("missing_argv_proof")
    else:
        argv = _read(argv_path, root)
        row["argv_sha256"] = sha(argv_path.read_bytes())
        if _argv_proof(argv, plan) and value.get("standard_speed_verified") is True and value.get("model") == plan["model"] and value.get("service_tier") == "standard":
            row.update(model=plan["model"], service_tier="standard", standard_speed_verified=True)
        else:
            row["exclusions"].append("unverified_model_or_standard_speed")
    calls = value.get("mcp_calls")
    if not _integer(calls):
        row["exclusions"].append("missing_tool_call_count")
    row["tools"], tool_reasons = _tools(directory / "artifacts/tools.jsonl", root, calls, task.get("baseline_command"))
    row["exclusions"].extend(tool_reasons)
    # Cost validity is separate from correctness. A wrong repair still has a
    # complete measurable cost; grading failure does not erase inference usage.
    row["usage_complete"] = (row["usage_complete"] and row["timed_out"] is False
                             and type(value.get("process_exit_code")) is int and value["process_exit_code"] == 0
                             and type(value.get("turn_completed_count")) is int and value["turn_completed_count"] == 1
                             and isinstance(errors, list) and not errors)
    priced = costs.price_usage(row["usage"], plan["cost_model"], complete=row["usage_complete"],
                               model=row["model"], service_tier=row["service_tier"])
    row["usage"] = priced["usage"]
    row["priced_cost"] = {key: priced[key] for key in ("known", "amount", "components", "unknown_reasons")}
    if not priced["known"]:
        row["exclusions"].append("unknown_priced_cost")
    if grade["correct_repair"] is not None:
        row["correct_repair"] = (grade["correct_repair"] and not row["protocol_deviations"] and row["timed_out"] is False
                                 and value.get("process_exit_code") == 0 and isinstance(deviations, list))
    if row["protocol_deviations"]:
        row["correct_repair"] = False
    row["exclusions"] = sorted(set(row["exclusions"]))
    row["operational_complete"] = not row["exclusions"]
    return row


def _aggregate(rows: list[dict], card: dict) -> dict:
    if not rows:
        return {"planned_attempts": 0, "observed_attempts": 0, "successful_repairs": 0, "unknown_correctness": 0,
                "all_planned_costs_known": True, "total_credits": "0", "credits_per_successful_repair": None,
                "total_components": {key: "0" for key in costs.RATE_KEYS}, "usage": None, "operationally_complete_attempts": 0}
    attempts = [{key: row[key] for key in ("id", "usage", "usage_complete", "model", "service_tier", "correct_repair", "timed_out", "protocol_deviations")}
                for row in rows if row["observed"]]
    summary = costs.summarize_attempts(attempts, card, planned_ids=[row["id"] for row in rows])
    result = {key: value for key, value in summary.items() if key not in {"attempts", "rate_card", "definitions"}}
    result["unknown_correctness"] = len(summary["unknown_correctness_attempt_ids"])
    result["operationally_complete_attempts"] = sum(row["operational_complete"] for row in rows)
    result["incorrect_repairs"] = sum(row["correct_repair"] is False for row in rows)
    result["grading_timeout_attempts"] = sum(row["grade"].get("grading_timeout_checks", 0) > 0 for row in rows)
    result["exclusion_counts"] = dict(Counter(reason for row in rows for reason in row["exclusions"]))
    known = [row for row in summary["attempts"] if row["known"]]
    with localcontext() as context:
        context.prec = max(60, sum(len(row["amount"]) for row in known) + 20)
        result["known_component_subtotals"] = {key: _number(sum((Decimal(row["components"][key]) for row in known), Decimal(0))) if known else None for key in costs.RATE_KEYS}
    result["total_components"] = result["known_component_subtotals"] if summary["all_planned_costs_known"] else None
    observed_usage = [row["usage"] for row in rows if row["usage"] is not None]
    result["usage"] = {"observations": len(observed_usage), **{key: sum(row[key] for row in observed_usage)
        if observed_usage and all(row.get(key) is not None for row in observed_usage) else None for key in USAGE_FIELDS}}
    result["wall_seconds_sum"] = sum(row["wall_seconds"] for row in rows if row["wall_seconds"] is not None)
    tools = [row["tools"] for row in rows if row["tools"] is not None]
    result["tools"] = {"observations": len(tools), **{key: sum(item[key] for item in tools) for key in tools[0] if key != "available"}} if tools else None
    return result


def _ratio(numerator, denominator) -> str | None:
    if numerator is None or denominator is None or Decimal(denominator) == 0:
        return None
    with localcontext() as context:
        context.prec = 60
        return _number(Decimal(numerator) / Decimal(denominator))


def _comparison(groups: dict) -> dict:
    result = {}
    for comparator in ("raw", "rtk"):
        mini, other = groups["mini"], groups[comparator]
        per_success = None
        if (mini["total_credits"] is not None and other["total_credits"] is not None
                and mini["successful_repairs"] and other["successful_repairs"]
                and mini["credits_per_successful_repair"] is not None and other["credits_per_successful_repair"] is not None):
            # Compare exact totals and counts directly; do not divide two
            # already rounded repeating per-success decimal strings.
            with localcontext() as context:
                context.prec = max(60, len(mini["total_credits"]) + len(other["total_credits"]) + 30)
                per_success = _ratio(Decimal(mini["total_credits"]) * other["successful_repairs"],
                                     Decimal(other["total_credits"]) * mini["successful_repairs"])
        result["mini_vs_" + comparator] = {
            "total_cost_ratio": _ratio(mini["total_credits"], other["total_credits"]),
            "cost_per_success_ratio": per_success,
            "mini_successes": mini["successful_repairs"], "comparator_successes": other["successful_repairs"]}
    return result


def _groups(rows, card):
    return {variant: _aggregate([row for row in rows if row["variant"] == variant], card) for variant in VARIANTS}


def _percentile(values: list[Decimal], fraction: str) -> Decimal:
    position = Decimal(fraction) * (len(values) - 1)
    lower = int(position)
    upper = min(lower + 1, len(values) - 1)
    return values[lower] + (values[upper] - values[lower]) * (position - lower)


def cluster_bootstrap(task_costs: dict[str, tuple[str, str]], *, resamples: int = BOOTSTRAP_RESAMPLES, seed: int = BOOTSTRAP_SEED) -> dict:
    """Resample task clusters; each pair already sums all three repetitions."""
    if set(task_costs) != set(TASK_IDS) or resamples != BOOTSTRAP_RESAMPLES or seed != BOOTSTRAP_SEED:
        raise AnalysisError("bootstrap must use the six registered clusters, 20000 resamples and fixed seed")
    pairs = [(Decimal(task_costs[key][0]), Decimal(task_costs[key][1])) for key in sorted(task_costs)]
    rng, ratios = random.Random(seed), []
    with localcontext() as context:
        context.prec = 60
        for _ in range(resamples):
            picked = [pairs[rng.randrange(len(pairs))] for _ in pairs]
            denominator = sum((pair[1] for pair in picked), Decimal(0))
            if denominator == 0:
                return {"available": False, "reason": "zero_resampled_comparator_cost"}
            ratios.append(sum((pair[0] for pair in picked), Decimal(0)) / denominator)
        ratios.sort()
        return {"available": True, "clusters": 6, "repetitions_per_cluster": 3, "resamples": resamples, "seed": seed,
                "lower_2_5_percentile": _number(_percentile(ratios, "0.025")),
                "upper_97_5_percentile": _number(_percentile(ratios, "0.975")),
                "method": "paired task-cluster ratio of summed costs; linear percentile interpolation",
                "interpretation": "Stability check for six convenience-sampled tasks, not population proof"}


def summarize(run_root: Path) -> dict:
    root = Path(run_root).resolve()
    plan_path = root / "plan.json"
    plan = _read(plan_path, root)
    by_id = _validate_plan(plan)
    plan_hash = sha(plan_path.read_bytes())
    registration = _read(root / "registration.json", root)
    if not isinstance(registration, dict) or registration.get("plan_sha256") != plan_hash:
        raise AnalysisError("registration receipt does not match plan bytes")
    for directory in (root / "trials").iterdir() if (root / "trials").exists() else []:
        if directory.is_dir() and directory.name not in by_id and (directory / "result.json").exists():
            raise AnalysisError("unregistered trial result")
    tasks = {task["id"]: task for task in plan["tasks"]}
    rows = [_trial(root, trial, plan, plan_hash, tasks[trial["task_id"]]) for trial in plan["trials"]]
    card = plan["cost_model"]
    aggregate = _groups(rows, card)
    comparison = _comparison(aggregate)
    language = {}
    for name in ("rust", "javascript"):
        groups = _groups([row for row in rows if row["language"] == name], card)
        language[name] = {"variants": groups, "comparisons": _comparison(groups)}
    task_results = {}
    for task_id in TASK_IDS:
        groups = _groups([row for row in rows if row["task_id"] == task_id], card)
        task_results[task_id] = {"variants": groups, "comparisons": _comparison(groups)}
    repetitions = {}
    for number in (1, 2, 3):
        groups = _groups([row for row in rows if row["repetition"] == number], card)
        repetitions[str(number)] = {"variants": groups, "comparisons": _comparison(groups)}
    leave_one_out = {}
    for omitted in TASK_IDS:
        groups = _groups([row for row in rows if row["task_id"] != omitted], card)
        leave_one_out[omitted] = _comparison(groups)["mini_vs_rtk"]
    complete = len(rows) == 54 and all(row["operational_complete"] for row in rows)
    ratio = comparison["mini_vs_rtk"]["total_cost_ratio"]
    per_success = comparison["mini_vs_rtk"]["cost_per_success_ratio"]
    correctness = all(aggregate["mini"]["successful_repairs"] >= aggregate[other]["successful_repairs"] for other in ("raw", "rtk"))
    task_pairs = {task_id: (task_results[task_id]["variants"]["mini"]["total_credits"], task_results[task_id]["variants"]["rtk"]["total_credits"]) for task_id in TASK_IDS}
    bootstrap = cluster_bootstrap(task_pairs) if complete else {"available": False, "reason": "incomplete_operational_coverage"}
    below_one = lambda value: value is not None and Decimal(value) < 1
    interval_below_one = bootstrap.get("available") is True and below_one(bootstrap.get("upper_97_5_percentile"))
    evidence = complete and correctness and interval_below_one
    tests = {
        "all_54_attempts_usable": complete, "correctness_no_lower_than_raw_and_rtk": correctness,
        "bootstrap_upper_below_one": interval_below_one,
        "total_cost_at_least_10_percent_lower": ratio is not None and Decimal(ratio) <= Decimal("0.9"),
        "cost_per_success_at_least_10_percent_lower": per_success is not None and Decimal(per_success) <= Decimal("0.9"),
        "both_language_groups_lower": all(below_one(language[name]["comparisons"]["mini_vs_rtk"]["total_cost_ratio"]) for name in language),
        "at_least_four_task_totals_lower": sum(below_one(task_results[key]["comparisons"]["mini_vs_rtk"]["total_cost_ratio"]) for key in TASK_IDS) >= 4,
        "all_leave_one_task_out_ratios_lower": all(below_one(value["total_cost_ratio"]) for value in leave_one_out.values())}
    investment = evidence and all(tests.values())
    if not complete:
        classification = "inconclusive_operational_coverage"
    elif not correctness:
        classification = "no_acceptable_cost_advantage_with_lower_correctness"
    elif evidence:
        classification = "confirmed_lower_published_rate_usage_cost"
    elif below_one(ratio):
        classification = "observed_lower_cost_not_confirmed"
    else:
        classification = "equal_or_higher_observed_cost"
    successful = _groups([row for row in rows if row["correct_repair"] is True], card)
    return {"schema": 1, "measure": "fixed-filter-published-rate-cost-confirmation", "actual_billed": False,
            "cost_boundary": BOUNDARY, "plan_sha256": plan_hash, "rate_card": costs.validate_rate_card(card),
            "coverage": {"planned": 54, "observed_results": sum(row["observed"] for row in rows),
                         "observed_grades": sum(row["grade"]["observed"] for row in rows),
                         "operationally_complete": sum(row["operational_complete"] for row in rows), "complete_confirmation": complete},
            "all_attempts": {"variants": aggregate, "comparisons": comparison}, "by_language": language,
            "by_task": task_results, "by_repetition": repetitions,
            "successful_attempts_only_secondary": {"variants": successful, "comparisons": _comparison(successful),
                "warning": "Unpaired successful-only subsets; excludes failure costs and does not replace the all-attempt primary denominator"},
            "leave_one_task_out": leave_one_out, "mini_vs_rtk_task_cluster_bootstrap": bootstrap,
            "decision": {"classification": classification, "repeatable_cost_evidence": evidence,
                         "continue_compressor_expansion": investment, "criteria": tests,
                         "recommendation": "continue_bounded_compressor_expansion" if investment else "maintain_release_and_stop_broad_expansion",
                         "cost_boundary": BOUNDARY},
            "trials": [{key: value for key, value in row.items() if key not in {"model", "service_tier", "usage_complete", "protocol_deviations"}}
                       | {"protocol_deviations_count": len(row["protocol_deviations"])} for row in rows]}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, help="Create an exclusive public-safe summary; never overwrite")
    options = parser.parse_args()
    try:
        result = summarize(options.run_root)
        if options.output:
            with options.output.open("x", encoding="utf-8") as handle:
                json.dump(result, handle, indent=2, sort_keys=True)
                handle.write("\n")
        else:
            print(json.dumps(result, indent=2, sort_keys=True))
    except (AnalysisError, costs.CostError, OSError) as error:
        print(json.dumps({"ok": False, "error": str(error) if isinstance(error, AnalysisError) else type(error).__name__}), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
