#!/usr/bin/env python3
"""Register and execute prospective raw/Mini/RTK debugging comparisons.

Uses saved Codex CLI authentication, never reads or copies credentials.
All comparative work is local and private until explicitly exported/reviewed.
"""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import platform
import random
import shutil
import signal
import subprocess
import time
import tomllib


HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
VARIANTS = ["raw", "mini", "rtk"]
FEATURES_OFF = ["shell_tool", "unified_exec", "apps", "plugins", "memories", "multi_agent", "browser_use", "computer_use", "in_app_browser", "image_generation", "goals"]


def tool_environment():
    return {"PATH": str(ROOT / ".tools/cargo/bin") + os.pathsep + os.environ.get("PATH", os.defpath),
            "HOME": str(Path.home()), "CARGO_HOME": str(ROOT / ".tools/cargo"),
            "RUSTUP_HOME": str(ROOT / ".tools/rustup")}


def now():
    return datetime.now(timezone.utc).isoformat()


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write_json(path, value):
    with Path(path).open("x", encoding="utf-8") as output:
        json.dump(value, output, ensure_ascii=False, indent=2, sort_keys=True)
        output.write("\n")


def ignored(directory, names):
    return [name for name in names if name in {".git", "target", "__pycache__", ".eslintcache"}]


def copy_snapshot(source, destination):
    def source_ignore(directory, names):
        return ignored(directory, names) + (["node_modules"] if Path(directory) == source else [])
    shutil.copytree(source, destination, ignore=source_ignore, symlinks=True)
    dependencies = source / "node_modules"
    if dependencies.exists():
        physical = dependencies.resolve()
        for path in physical.rglob("*"):
            if path.is_symlink() and not path.resolve().is_relative_to(physical):
                raise ValueError("dependency symlink escapes its installed tree")
        shutil.copytree(physical, destination / "node_modules", symlinks=True)
    # Cached lint state must not decide whether a copied source is checked.
    shutil.rmtree(destination / "node_modules/.cache", ignore_errors=True)


def tree_manifest(directory):
    result = {}
    for path in sorted(directory.rglob("*")):
        relative = path.relative_to(directory)
        if any(part in {".git", "target", "node_modules", "__pycache__"} for part in relative.parts):
            continue
        if path.is_file():
            result[relative.as_posix()] = sha(path)
    return result


def dependency_tree_hash(directory):
    root = directory / "node_modules"
    entries = {path.relative_to(root).as_posix(): ("symlink:" + os.readlink(path) if path.is_symlink() else sha(path)) for path in sorted(root.rglob("*")) if (path.is_file() or path.is_symlink()) and ".cache" not in path.relative_to(root).parts} if root.exists() else {}
    return hashlib.sha256(json.dumps(entries, sort_keys=True).encode()).hexdigest()


def git(workspace, *args, check=True):
    env = {**os.environ, "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": "/dev/null", "GIT_TERMINAL_PROMPT": "0"}
    return subprocess.run(["git", "-c", "core.hooksPath=/dev/null", "-c", "commit.gpgsign=false", *args], cwd=workspace, env=env, capture_output=True, check=check)


def initialize_git(workspace):
    git(workspace, "init", "-q")
    git(workspace, "add", "--all")
    git(workspace, "-c", "user.name=Debugging evaluation", "-c", "user.email=evaluation@example.invalid", "commit", "-qm", "Frozen task baseline")


def codex_argv(plan, trial, workspace, config, state):
    args = [plan["codex"], "exec", "--ignore-user-config", "--ephemeral", "--json", "--sandbox", "workspace-write", "--cd", str(workspace), "--color", "never"]
    for feature in FEATURES_OFF:
        args.extend(["--disable", feature])
    settings = {
        "model": plan["model"], "model_reasoning_effort": plan["reasoning_effort"],
        "approval_policy": "never", "web_search": "disabled", "project_doc_max_bytes": 0,
        "sqlite_home": str(state), "log_dir": str(state), "tool_output_token_limit": 100000,
        "mcp_servers.sprint.command": plan["python"],
        "mcp_servers.sprint.args": [str(HERE / "mcp_server.py"), "--config", str(config)],
        "mcp_servers.sprint.required": True, "mcp_servers.sprint.default_tools_approval_mode": "approve",
        "mcp_servers.sprint.tool_timeout_sec": 100,
        "mcp_servers.sprint.tools.terminal.output_token_limit": 100000,
        "mcp_servers.sprint.tools.read_file.output_token_limit": 100000,
        "mcp_servers.sprint.tools.recover_output.output_token_limit": 100000,
    }
    for key, value in settings.items():
        args.extend(["-c", key + "=" + json.dumps(value)])
    args.append("-")
    return args


def register(run_root, seed, repetitions, workers=3):
    run_root.mkdir(mode=0o700, parents=True, exist_ok=False)
    tasks = []
    for group in ("rust", "js"):
        tasks.extend(json.loads(path.read_text()) for path in sorted((HERE / "tasks" / group).glob("[RJ][123].json")))
    if {task["id"] for task in tasks} != {"R1", "R2", "R3", "J1", "J2", "J3"}:
        raise ValueError("exactly the six qualified tasks are required")
    source_receipts, dependency_receipts = {}, {}
    for task in tasks:
        task_id = task["id"]
        if task_id.startswith("R"):
            source = ROOT / ".tools/debug-sprint-prep/rust/preflight" / task_id / "base"
        else:
            source = ROOT / ".tools/debug-sprint-prep/js" / task_id / "base"
        destination = run_root / "sources" / task_id
        copy_snapshot(source, destination)
        if "baseline_lockfile" in task["assets"]:
            shutil.copyfile(ROOT / task["assets"]["baseline_lockfile"], destination / "Cargo.lock")
        source_receipts[task_id] = tree_manifest(destination)
        dependency_receipts[task_id] = dependency_tree_hash(destination)
    config_path = Path.home() / ".codex/config.toml"
    user_config = tomllib.loads(config_path.read_text()) if config_path.exists() else {}
    model = user_config.get("model")
    effort = user_config.get("model_reasoning_effort")
    if not model or not effort:
        raise ValueError("freeze an explicit existing CLI model and reasoning effort")
    mini = ROOT / "target/release/mini"
    rtk = ROOT / ".tools/rtk-1.1.0/bin/rtk"
    task_order = [task["id"] for task in tasks]
    random.Random(seed).shuffle(task_order)
    trials = []
    for position, task_id in enumerate(task_order):
        for repetition in range(1, repetitions + 1):
            offset = (position + repetition - 1) % 3
            for variant in VARIANTS[offset:] + VARIANTS[:offset]:
                trials.append({"id": f"trial-{len(trials)+1:03d}", "task_id": task_id, "repetition": repetition, "variant": variant})
    implementation = {str(path.relative_to(ROOT)): sha(path) for path in sorted(HERE.rglob("*")) if path.is_file() and "__pycache__" not in path.parts}
    plan = {"schema": 1, "registered_utc": now(), "seed": seed, "repetitions": repetitions,
            "model": model, "reasoning_effort": effort, "model_source": "existing user CLI configuration; same values in every session",
            "codex": shutil.which("codex"), "python": shutil.which("python3"),
            "codex_version": subprocess.run(["codex", "--version"], capture_output=True, text=True, check=True).stdout.strip(),
            "mini": str(mini), "rtk": str(rtk), "mini_sha256": sha(mini), "rtk_sha256": sha(rtk),
            "protocol_sha256": sha(HERE / "protocol.md"), "implementation_sha256": implementation,
            "tasks": tasks, "source_files": source_receipts, "dependency_tree_sha256": dependency_receipts, "task_order": task_order, "trials": trials,
            "max_actions": 60, "session_timeout_seconds": 600, "command_timeout_seconds": 90, "workers": workers,
            "features_disabled": FEATURES_OFF, "recovery_enabled": True,
            "tool_environment": tool_environment(),
            "host_platform": platform.platform(), "machine": platform.machine(),
            "tool_versions": {command: subprocess.run([command, "--version"], env=tool_environment(), capture_output=True, text=True, check=True).stdout.strip() for command in ("cargo", "rustc", "node", "npm")},
            "usage_primary": "CLI aggregate input_tokens + output_tokens; cached input included; reasoning subset not double counted"}
    write_json(run_root / "plan.json", plan)
    write_json(run_root / "registration.json", {"registered_utc": now(), "plan_sha256": sha(run_root / "plan.json"), "comparative_sessions_started": False})
    return plan


def verify_frozen(run_root, plan):
    registration = json.loads((run_root / "registration.json").read_text())
    if sha(run_root / "plan.json") != registration["plan_sha256"]:
        raise ValueError("registered plan bytes changed")
    for name, expected in plan["implementation_sha256"].items():
        if sha(ROOT / name) != expected:
            raise ValueError("registered implementation changed: " + name)
    for name in ("mini", "rtk"):
        if sha(plan[name]) != plan[name + "_sha256"]:
            raise ValueError("registered binary changed: " + name)
    for task_id, expected in plan["source_files"].items():
        source = run_root / "sources" / task_id
        if tree_manifest(source) != expected or dependency_tree_hash(source) != plan["dependency_tree_sha256"][task_id]:
            raise ValueError("registered source/dependencies changed: " + task_id)


def event_summary(path):
    events, malformed = [], 0
    for line in path.read_text(errors="replace").splitlines():
        if not line.strip():
            continue
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError:
            malformed += 1
    completed = [event for event in events if event.get("type") == "turn.completed"]
    usage = completed[0].get("usage") if len(completed) == 1 else None
    tools = [event["item"] for event in events if event.get("type") == "item.completed" and event.get("item", {}).get("type") == "mcp_tool_call"]
    violations = []
    for event in events:
        item = event.get("item", {})
        kind = item.get("type")
        if event.get("type") == "item.completed" and kind in {"command_execution", "file_change", "web_search"}:
            violations.append("native tool bypass: " + kind)
        if kind == "mcp_tool_call" and item.get("server") != "sprint":
            violations.append("outside MCP server")
    errors = [event for event in events if event.get("type") in {"error", "turn.failed"}]
    return {"usage": usage, "turn_completed_count": len(completed), "malformed_event_lines": malformed, "mcp_calls": len(tools),
            "mcp_failures": sum(tool.get("status") == "failed" for tool in tools),
            "protocol_deviations": sorted(set(violations)), "session_errors": errors,
            "thread_id": next((event.get("thread_id") for event in events if event.get("type") == "thread.started"), None)}


def run_trial(run_root, plan, trial):
    directory = run_root / "trials" / trial["id"]
    directory.mkdir(mode=0o700, parents=True, exist_ok=False)
    workspace = directory / "workspace"
    copy_snapshot(run_root / "sources" / trial["task_id"], workspace)
    if tree_manifest(workspace) != plan["source_files"][trial["task_id"]] or dependency_tree_hash(workspace) != plan["dependency_tree_sha256"][trial["task_id"]]:
        raise ValueError("trial copy differs from registered source/dependencies")
    initialize_git(workspace)
    task = next(task for task in plan["tasks"] if task["id"] == trial["task_id"])
    prompt = (HERE / "solver_prompt.txt").read_text().format(task_prompt=task["prompt"], baseline_command=json.dumps(task["baseline_command"]))
    (directory / "prompt.txt").write_text(prompt)
    config = {"workspace": str(workspace), "artifact_root": str(directory / "artifacts"),
              "mode": trial["variant"], "mini": plan["mini"], "rtk": plan["rtk"], "max_actions": plan["max_actions"], "env": plan["tool_environment"]}
    write_json(directory / "config.json", config)
    args = codex_argv(plan, trial, workspace, directory / "config.json", run_root / "codex-state")
    write_json(directory / "argv.json", args)
    started_utc, started = now(), time.monotonic()
    timed_out = False
    with (directory / "events.jsonl").open("xb") as output, (directory / "stderr.txt").open("xb") as errors:
        process = subprocess.Popen(args, stdin=subprocess.PIPE, stdout=output, stderr=errors, start_new_session=True)
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
    result = {**trial, "started_utc": started_utc, "finished_utc": now(), "wall_seconds": time.monotonic() - started,
              "process_exit_code": process.returncode, "timed_out": timed_out,
              "prompt_sha256": sha(directory / "prompt.txt"), "events_sha256": sha(directory / "events.jsonl"),
              "workspace_files": tree_manifest(workspace), **event_summary(directory / "events.jsonl")}
    # Preserve untracked regression/reproduction files in the patch without committing.
    git(workspace, "add", "--intent-to-add", "--all")
    patch = git(workspace, "diff", "--binary", "HEAD").stdout
    (directory / "candidate.patch").write_bytes(patch)
    result["candidate_patch_sha256"] = sha(directory / "candidate.patch")
    result["candidate_patch_bytes"] = len(patch)
    write_json(directory / "result.json", result)
    print(json.dumps({"finished": trial["id"], "task": trial["task_id"], "repetition": trial["repetition"], "variant": trial["variant"], "wall_seconds": round(result["wall_seconds"], 1), "has_usage": result["usage"] is not None, "process_exit": process.returncode, "protocol_deviations": result["protocol_deviations"]}), flush=True)
    return result


def execute(run_root, plan, workers):
    verify_frozen(run_root, plan)
    if workers != plan["workers"]:
        raise ValueError("worker count differs from registered concurrency")
    (run_root / "codex-state").mkdir(mode=0o700, exist_ok=True)
    pending = [trial for trial in plan["trials"] if not (run_root / "trials" / trial["id"] / "result.json").exists()]
    if any((run_root / "trials" / trial["id"]).exists() for trial in pending):
        raise ValueError("unfinished trials must be retained and reviewed; no silent retry")
    # Each worker receives a whole task/repetition triple. Treatments stay in the
    # registered order within a triple; independent triples may run concurrently.
    grouped = {}
    for trial in pending:
        grouped.setdefault((trial["task_id"], trial["repetition"]), []).append(trial)
    triples = list(grouped.values())
    def run_triple(triple):
        return [run_trial(run_root, plan, trial) for trial in triple]
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = [executor.submit(run_triple, triple) for triple in triples]
        for future in as_completed(futures):
            future.result()
    write_json(run_root / "sessions-complete.json", {"finished_utc": now(), "planned": len(plan["trials"]), "completed": len(list((run_root / "trials").glob("*/result.json"))), "plan_sha256": sha(run_root / "plan.json")})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-root", type=Path, required=True)
    parser.add_argument("--register", action="store_true")
    parser.add_argument("--run", action="store_true")
    parser.add_argument("--seed", type=int, default=20261106)
    parser.add_argument("--repetitions", type=int, default=2)
    parser.add_argument("--workers", type=int, choices=[1, 2, 3], default=3)
    args = parser.parse_args()
    os.umask(0o077)
    run_root = args.run_root.resolve()
    if args.register:
        plan = register(run_root, args.seed, args.repetitions, args.workers)
        print(json.dumps({"registered": len(plan["trials"]), "plan_sha256": sha(run_root / "plan.json")}), flush=True)
    elif args.run:
        plan = json.loads((run_root / "plan.json").read_text())
    else:
        parser.error("choose --register, --run, or both")
    if args.run:
        execute(run_root, plan, args.workers)


if __name__ == "__main__":
    main()
