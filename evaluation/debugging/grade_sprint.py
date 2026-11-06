#!/usr/bin/env python3
"""Grade all frozen sessions after collection, without additional model calls.

The evaluator and analysis rules were registered before agent collection. This
driver only applies those fixed rules to all planned trials, in fresh copies.
"""
from concurrent.futures import ThreadPoolExecutor, as_completed
import argparse
import json
import os
from pathlib import Path

from evaluate import evaluate_task
from run_sprint import now, sha, tree_manifest, verify_frozen, write_json


def grade(run_root: Path, workers=3):
    root = run_root.resolve(strict=True)
    plan = json.loads((root / "plan.json").read_text())
    verify_frozen(root, plan)
    completion = json.loads((root / "sessions-complete.json").read_text())
    if completion["completed"] != len(plan["trials"]) or completion["plan_sha256"] != sha(root / "plan.json"):
        raise ValueError("all registered sessions must finish before grading")
    for trial in plan["trials"]:
        directory = root / "trials" / trial["id"]
        result = json.loads((directory / "result.json").read_text())
        if tree_manifest(directory / "workspace") != result["workspace_files"]:
            raise ValueError("frozen solver workspace changed: " + trial["id"])
        if (directory / "evaluation").exists() or (directory / "evaluation.json").exists():
            raise ValueError("existing grading must be retained; no automatic replacement")
    # Preserve the actual user HOME. Only select the registered compiler paths.
    for key in ("PATH", "CARGO_HOME", "RUSTUP_HOME"):
        os.environ[key] = plan["tool_environment"][key]
    write_json(root / "grading-started.json", {"started_utc": now(), "plan_sha256": sha(root / "plan.json"), "driver_sha256": sha(__file__), "workers": workers})
    tasks = {task["id"]: task for task in plan["tasks"]}

    def one(trial):
        directory = root / "trials" / trial["id"]
        result = evaluate_task(tasks[trial["task_id"]], root / "sources" / trial["task_id"], directory / "workspace", directory / "evaluation")
        print(json.dumps({"graded": trial["id"], "task": trial["task_id"], "variant": trial["variant"], "correct_repair": result["correct_repair"], "infrastructure_errors": len(result["infrastructure_errors"]), "restore_errors": len(result["restore_errors"]), "frozen_workspace_unchanged": result["frozen_workspace_unchanged"]}), flush=True)
        return result

    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = [executor.submit(one, trial) for trial in plan["trials"]]
        results = [future.result() for future in as_completed(futures)]
    write_json(root / "grading-complete.json", {"finished_utc": now(), "plan_sha256": sha(root / "plan.json"), "planned": len(plan["trials"]), "graded": len(results)})


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-root", type=Path, required=True)
    parser.add_argument("--workers", type=int, choices=[1, 2, 3], default=3)
    args = parser.parse_args()
    os.umask(0o077)
    grade(args.run_root, args.workers)
