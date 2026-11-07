#!/usr/bin/env python3
"""Register and collect the fixed-filter, Standard-credit confirmation."""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import platform
import random
import shutil
import signal
import subprocess
from threading import Event
import time


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
DEBUGGING = HERE.parent / "debugging"
spec = importlib.util.spec_from_file_location("frozen_sprint_runner", DEBUGGING / "run_sprint.py")
old = importlib.util.module_from_spec(spec)
spec.loader.exec_module(old)
VARIANTS = ("raw", "mini", "rtk")
TASK_IDS = {"C-R1", "C-R2", "C-R3", "C-J1", "C-J2", "C-J3"}
MINIMUM_FREE_BYTES = 4 * 1024 ** 3


def schedule(tasks, seed=20261107):
    randomizer = random.Random(seed)
    trials, blocks = [], []
    for repetition in (1, 2, 3):
        order = sorted(task["id"] for task in tasks)
        randomizer.shuffle(order)
        blocks.append(order)
        # Use a fixed task index for rotation, independent of each shuffled order.
        for task_id in order:
            position = sorted(TASK_IDS).index(task_id)
            offset = (position + repetition - 1) % 3
            variants = VARIANTS[offset:] + VARIANTS[:offset]
            for variant in variants:
                trials.append({"id": f"trial-{len(trials)+1:03d}", "task_id": task_id, "repetition": repetition, "variant": variant})
    return trials, blocks


def codex_argv(plan, workspace, config, state):
    args = old.codex_argv(plan, {}, workspace, config, state)
    for index, value in enumerate(args[:-1]):
        if value == "-c" and args[index + 1].startswith("mcp_servers.sprint.args="):
            args[index + 1] = "mcp_servers.sprint.args=" + json.dumps([str(HERE / "mcp_server.py"), "--config", str(config)])
    additions = ["--disable", "fast_mode", "--disable", "ultrafast_mode"]
    settings = {"service_tier": "default"}
    for key, value in settings.items():
        additions.extend(["-c", key + "=" + json.dumps(value)])
    args[-1:-1] = additions
    return args


def standard_speed_proof(args, model, effort):
    values, disabled = {}, set()
    for index, value in enumerate(args[:-1]):
        if value == "--enable" and args[index + 1] in {"fast_mode", "ultrafast_mode"}:
            return False
        if value == "--disable":
            disabled.add(args[index + 1])
        if value in {"-c", "--config"} and "=" in args[index + 1]:
            key, raw = args[index + 1].split("=", 1)
            try:
                values[key] = json.loads(raw)
            except json.JSONDecodeError:
                values[key] = raw
    return ("--ignore-user-config" in args and values.get("model") == model
            and values.get("model_reasoning_effort") == effort and values.get("service_tier") == "default"
            and values.get("features.fast_mode", False) is False
            and values.get("features.ultrafast_mode", False) is False
            and {"fast_mode", "ultrafast_mode"} <= disabled)


def disk_guard(root, stage, minimum=MINIMUM_FREE_BYTES):
    free = shutil.disk_usage(root).free
    if free < minimum:
        receipts = root / "aborts"
        receipts.mkdir(mode=0o700, exist_ok=True)
        old.write_json(receipts / (stage + ".json"), {"utc": old.now(), "stage": stage, "free_bytes": free, "minimum_free_bytes": minimum, "reason": "insufficient_free_space_before_new_work", "existing_evidence_preserved": True})
        raise RuntimeError("free disk space is below the registered minimum; existing evidence retained")


def source_path(task):
    group = "rust" if task["id"].startswith("C-R") else "js"
    return ROOT / ".tools/confirmation-prep" / group / task["id"] / "base"


def implementation_files():
    paths = [path for path in HERE.rglob("*") if path.is_file() and "__pycache__" not in path.parts]
    paths.extend(DEBUGGING / name for name in ("run_sprint.py", "mcp_server.py", "terminal.py", "evaluate.py"))
    paths.extend((ROOT / "evaluation/tests").glob("test_confirmation*.py"))
    return {path.relative_to(ROOT).as_posix(): old.sha(path) for path in sorted(set(paths))}


def register(root, seed):
    if shutil.disk_usage(ROOT).free < MINIMUM_FREE_BYTES:
        raise RuntimeError("insufficient free space before registration")
    root.mkdir(mode=0o700, parents=True, exist_ok=False)
    tasks = [json.loads(path.read_text()) for group in ("rust", "js") for path in sorted((HERE / "tasks" / group).glob("C-[RJ][123].json"))]
    if len(tasks) != 6 or {task["id"] for task in tasks} != TASK_IDS:
        raise ValueError("exactly six newly qualified confirmation tasks are required")
    prior = json.loads((ROOT / ".tools/debug-sprint-runs/debug-v0.2-20261106/plan.json").read_text())
    for name in ("mini", "rtk"):
        if old.sha(prior[name]) != prior[name + "_sha256"]:
            raise ValueError("fixed prior comparator binary changed: " + name)
    if prior["model"] != "gpt-6.1-sol" or prior["reasoning_effort"] != "ultra":
        raise ValueError("unexpected prior model configuration")
    source_files, dependency_hashes = {}, {}
    for task in tasks:
        destination = root / "sources" / task["id"]
        old.copy_snapshot(source_path(task), destination)
        lock = task.get("assets", {}).get("baseline_lockfile")
        if lock:
            shutil.copyfile(ROOT / lock, destination / "Cargo.lock")
        source_files[task["id"]] = old.tree_manifest(destination)
        dependency_hashes[task["id"]] = old.dependency_tree_hash(destination)
    trials, blocks = schedule(tasks, seed)
    card_path = HERE / "rates/codex-standard-2026-11-06.json"
    card = json.loads(card_path.read_text())
    from costs import validate_rate_card
    validate_rate_card(card)
    cli = shutil.which("codex")
    plan = {"schema": 1, "study": "fixed-filter-cost-confirmation", "registered_utc": old.now(),
            "seed": seed, "repetitions": 3, "workers": 3, "tasks": tasks, "trials": trials,
            "repetition_blocks": blocks, "model": prior["model"], "reasoning_effort": prior["reasoning_effort"],
            "service_tier": "standard", "cli_service_tier": "default", "fast_mode": False, "ultrafast_mode": False,
            "cost_model": card, "rate_card_file_sha256": old.sha(card_path), "actual_billed": False,
            "codex": cli, "codex_sha256": old.sha(cli), "python": shutil.which("python3"),
            "codex_version": subprocess.run([cli, "--version"], capture_output=True, text=True, check=True).stdout.strip(),
            "mini": prior["mini"], "rtk": prior["rtk"], "mini_sha256": prior["mini_sha256"], "rtk_sha256": prior["rtk_sha256"],
            "prior_plan_sha256": old.sha(ROOT / ".tools/debug-sprint-runs/debug-v0.2-20261106/plan.json"),
            "source_files": source_files, "dependency_tree_sha256": dependency_hashes,
            "implementation_sha256": implementation_files(), "protocol_sha256": old.sha(HERE / "protocol.md"),
            "tool_environment": old.tool_environment(), "host_platform": platform.platform(), "machine": platform.machine(),
            "tool_versions": {name: subprocess.run([name, "--version"], env=old.tool_environment(), capture_output=True, text=True, check=True).stdout.strip() for name in ("cargo", "rustc", "node", "npm")},
            "max_actions": 90, "soft_deadline_seconds": 720, "session_timeout_seconds": 900, "command_timeout_seconds": 90,
            "minimum_free_bytes": MINIMUM_FREE_BYTES,
            "bootstrap_resamples": 20000, "bootstrap_seed": 20261107,
            "cost_gate": {"maximum_total_ratio": "0.9", "maximum_cost_per_success_ratio": "0.9", "bootstrap_upper_below": "1", "minimum_task_wins": 4, "both_languages_below_one": True, "all_leave_one_task_out_below_one": True, "correctness_no_lower_than": ["raw", "rtk"]},
            "recovery_enabled": True, "cleanup_disposable_build_products": True,
            "usage_primary": "published Standard credits: ((input-cached)*50 + cached*2.5 + output*250)/1e6; all attempts including unsuccessful repairs"}
    old.write_json(root / "plan.json", plan)
    old.write_json(root / "registration.json", {"registered_utc": old.now(), "plan_sha256": old.sha(root / "plan.json"), "comparative_sessions_started": False})
    return plan


def verify_frozen(root, plan):
    receipt = json.loads((root / "registration.json").read_text())
    if old.sha(root / "plan.json") != receipt["plan_sha256"]:
        raise ValueError("registered plan bytes changed")
    for relative, expected in plan["implementation_sha256"].items():
        if old.sha(ROOT / relative) != expected:
            raise ValueError("registered implementation changed: " + relative)
    for name in ("mini", "rtk", "codex"):
        if old.sha(plan[name]) != plan[name + "_sha256"]:
            raise ValueError("registered executable changed: " + name)
    for task_id, expected in plan["source_files"].items():
        source = root / "sources" / task_id
        if old.tree_manifest(source) != expected or old.dependency_tree_hash(source) != plan["dependency_tree_sha256"][task_id]:
            raise ValueError("registered source/dependencies changed: " + task_id)


def cleanup_target(workspace):
    target = workspace / "target"
    if target.exists():
        if target.is_symlink() or not target.resolve().is_relative_to(workspace.resolve()):
            raise ValueError("refusing unsafe disposable target cleanup")
        shutil.rmtree(target)
        return {"removed": True, "scope": "workspace/target", "source_and_captures_preserved": True}
    return {"removed": False, "scope": "workspace/target", "source_and_captures_preserved": True}


def run_trial(root, plan, trial, abort=None):
    if abort is not None and abort.is_set():
        raise RuntimeError("collection already aborted; no new session")
    disk_guard(root, trial["id"], plan["minimum_free_bytes"])
    for name in ("mini", "rtk", "codex"):
        if old.sha(plan[name]) != plan[name + "_sha256"]:
            raise ValueError("frozen executable changed during collection")
    directory = root / "trials" / trial["id"]
    directory.mkdir(mode=0o700, parents=True, exist_ok=False)
    workspace = directory / "workspace"
    task = next(task for task in plan["tasks"] if task["id"] == trial["task_id"])
    old.copy_snapshot(root / "sources" / task["id"], workspace)
    if old.tree_manifest(workspace) != plan["source_files"][task["id"]] or old.dependency_tree_hash(workspace) != plan["dependency_tree_sha256"][task["id"]]:
        raise ValueError("workspace copy differs from registration")
    old.initialize_git(workspace)
    prompt = (HERE / "solver_prompt.txt").read_text().format(task_prompt=task["prompt"], baseline_command=json.dumps(task["baseline_command"]))
    (directory / "prompt.txt").write_text(prompt)
    config = {"workspace": str(workspace), "artifact_root": str(directory / "artifacts"), "mode": trial["variant"],
              "mini": plan["mini"], "rtk": plan["rtk"], "max_actions": plan["max_actions"], "env": plan["tool_environment"],
              "environment_unset": task.get("setup", {}).get("environment_unset", []), "soft_deadline_epoch": time.time() + plan["soft_deadline_seconds"]}
    old.write_json(directory / "config.json", config)
    args = codex_argv(plan, workspace, directory / "config.json", root / "codex-state")
    old.write_json(directory / "argv.json", args)
    if not standard_speed_proof(args, plan["model"], plan["reasoning_effort"]):
        raise ValueError("Standard speed configuration proof failed")
    start_utc, started = old.now(), time.monotonic()
    timed_out = False
    with (directory / "events.jsonl").open("xb") as out, (directory / "stderr.txt").open("xb") as err:
        if abort is not None and abort.is_set():
            old.write_json(directory / "aborted-before-session.json", {"utc": old.now(), "reason": "shared_collection_abort", "model_session_started": False})
            raise RuntimeError("collection aborted before model session start")
        process = subprocess.Popen(args, stdin=subprocess.PIPE, stdout=out, stderr=err, start_new_session=True)
        try:
            process.communicate(prompt.encode(), timeout=plan["session_timeout_seconds"])
        except subprocess.TimeoutExpired:
            timed_out = True
            os.killpg(process.pid, signal.SIGTERM)
            try:
                process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait(timeout=5)
    summary = old.event_summary(directory / "events.jsonl")
    result = {**trial, "plan_sha256": old.sha(root / "plan.json"), "started_utc": start_utc, "finished_utc": old.now(),
              "wall_seconds": time.monotonic() - started, "process_exit_code": process.returncode, "timed_out": timed_out,
              "model": plan["model"], "reasoning_effort": plan["reasoning_effort"], "service_tier": "standard", "standard_speed_verified": True,
              "prompt_sha256": old.sha(directory / "prompt.txt"), "events_sha256": old.sha(directory / "events.jsonl"),
              "workspace_files": old.tree_manifest(workspace), **summary}
    result["usage_complete"] = (not timed_out and process.returncode == 0 and summary["turn_completed_count"] == 1 and summary["malformed_event_lines"] == 0 and summary["usage"] is not None and not summary["session_errors"])
    old.git(workspace, "add", "--intent-to-add", "--all")
    (directory / "candidate.patch").write_bytes(old.git(workspace, "diff", "--binary", "HEAD").stdout)
    result["candidate_patch_sha256"] = old.sha(directory / "candidate.patch")
    result["candidate_patch_bytes"] = (directory / "candidate.patch").stat().st_size
    old.write_json(directory / "result.json", result)
    cleanup = cleanup_target(workspace)
    old.write_json(directory / "build-cleanup.json", cleanup)
    if old.tree_manifest(workspace) != result["workspace_files"]:
        raise ValueError("source changed during disposable cleanup")
    print(json.dumps({"finished": trial["id"], "task": task["id"], "repetition": trial["repetition"], "variant": trial["variant"], "wall_seconds": round(result["wall_seconds"], 1), "usage_complete": result["usage_complete"], "timed_out": timed_out, "protocol_deviations": result["protocol_deviations"]}), flush=True)
    return result


def execute(root, plan):
    verify_frozen(root, plan)
    disk_guard(root, "collection-start", plan["minimum_free_bytes"])
    (root / "codex-state").mkdir(mode=0o700, exist_ok=True)
    pending = [trial for trial in plan["trials"] if not (root / "trials" / trial["id"] / "result.json").exists()]
    if any((root / "trials" / trial["id"]).exists() for trial in pending):
        raise ValueError("unfinished trial retained; no automatic replacement")
    groups = {}
    for trial in pending:
        groups.setdefault((trial["task_id"], trial["repetition"]), []).append(trial)
    abort = Event()
    def triple(trials):
        results = []
        try:
            for trial in trials:
                if abort.is_set():
                    break
                results.append(run_trial(root, plan, trial, abort))
            return results
        except BaseException:
            abort.set()
            raise
    with ThreadPoolExecutor(max_workers=plan["workers"]) as executor:
        futures = [executor.submit(triple, trials) for trials in groups.values()]
        try:
            for future in as_completed(futures):
                future.result()
        except BaseException:
            abort.set()
            for future in futures:
                future.cancel()
            raise
    old.write_json(root / "sessions-complete.json", {"finished_utc": old.now(), "plan_sha256": old.sha(root / "plan.json"), "planned": 54, "completed": len(list((root / "trials").glob("*/result.json")))})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-root", type=Path, required=True)
    parser.add_argument("--register", action="store_true")
    parser.add_argument("--run", action="store_true")
    parser.add_argument("--seed", type=int, default=20261107)
    args = parser.parse_args()
    os.umask(0o077)
    root = args.run_root.resolve()
    if args.register:
        plan = register(root, args.seed)
        print(json.dumps({"registered": len(plan["trials"]), "plan_sha256": old.sha(root / "plan.json")}), flush=True)
    elif args.run:
        plan = json.loads((root / "plan.json").read_text())
    else:
        parser.error("choose --register and/or --run")
    if args.run:
        execute(root, plan)


if __name__ == "__main__":
    main()
