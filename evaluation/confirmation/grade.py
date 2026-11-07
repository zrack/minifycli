#!/usr/bin/env python3
"""Grade every frozen confirmation attempt, without further model calls."""
from concurrent.futures import ThreadPoolExecutor, as_completed
import argparse
import json
import os
from pathlib import Path
from threading import Event

from evaluate import evaluate_task
import run


def grade(root):
    root = root.resolve(strict=True)
    plan = json.loads((root / "plan.json").read_text())
    run.verify_frozen(root, plan)
    completion = json.loads((root / "sessions-complete.json").read_text())
    if completion["completed"] != 54 or completion["plan_sha256"] != run.old.sha(root / "plan.json"):
        raise ValueError("all planned sessions must finish before grading")
    for trial in plan["trials"]:
        directory = root / "trials" / trial["id"]
        result = json.loads((directory / "result.json").read_text())
        if run.old.tree_manifest(directory / "workspace") != result["workspace_files"]:
            raise ValueError("frozen source changed: " + trial["id"])
        if (directory / "evaluation").exists():
            raise ValueError("existing grading is retained; no automatic replacement")
    run.disk_guard(root, "grading-start", plan["minimum_free_bytes"])
    for key in ("PATH", "CARGO_HOME", "RUSTUP_HOME"):
        os.environ[key] = plan["tool_environment"][key]
    run.old.write_json(root / "grading-started.json", {"started_utc": run.old.now(), "plan_sha256": run.old.sha(root / "plan.json"), "driver_sha256": run.old.sha(__file__), "workers": plan["workers"]})
    tasks = {task["id"]: task for task in plan["tasks"]}
    abort = Event()
    def one(trial):
        if abort.is_set():
            return None
        try:
            run.disk_guard(root, "grade-" + trial["id"], plan["minimum_free_bytes"])
            directory = root / "trials" / trial["id"]
            result = evaluate_task(tasks[trial["task_id"]], root / "sources" / trial["task_id"], directory / "workspace", directory / "evaluation")
            print(json.dumps({"graded": trial["id"], "task": trial["task_id"], "repetition": trial["repetition"], "variant": trial["variant"], "correct_repair": result["correct_repair"], "infrastructure_errors": len(result["infrastructure_errors"]), "restore_errors": len(result["restore_errors"]), "frozen_workspace_unchanged": result["frozen_workspace_unchanged"]}), flush=True)
            if any(error.get("type") in {"DiskSpaceError", "TargetCleanupFailure"} for error in result["infrastructure_errors"]):
                raise RuntimeError("storage grading failure; stop scheduling new checks")
            return result
        except BaseException:
            abort.set()
            raise
    with ThreadPoolExecutor(max_workers=plan["workers"]) as executor:
        futures = [executor.submit(one, trial) for trial in plan["trials"]]
        try:
            results = [future.result() for future in as_completed(futures)]
        except BaseException:
            abort.set()
            for future in futures:
                future.cancel()
            raise
    run.old.write_json(root / "grading-complete.json", {"finished_utc": run.old.now(), "plan_sha256": run.old.sha(root / "plan.json"), "planned": 54, "graded": len(results)})


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-root", type=Path, required=True)
    args = parser.parse_args()
    os.umask(0o077)
    grade(args.run_root)
