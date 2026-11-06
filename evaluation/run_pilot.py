#!/usr/bin/env python3
"""Local, frozen-repository output evaluation. Raw captures are private by default."""
from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import random
import re
import selectors
import shutil
import signal
import statistics
import subprocess
import sys
import time
from datetime import datetime, timezone

ENCODINGS = ("o200k_base", "cl100k_base")
SCHEMA = 1
PROJECT = Path(__file__).resolve().parents[1]
MAX_OUTPUT = 64 * 1024 * 1024


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def write_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")


def safe_child(root: Path, name: str) -> Path:
    """Reject traversal and symlink escapes before using a plan-supplied path."""
    if not name or Path(name).is_absolute():
        raise ValueError("expected a nonempty relative path")
    candidate = (root / name).resolve()
    if candidate == root.resolve() or root.resolve() not in candidate.parents:
        raise ValueError("path escapes its declared root")
    return candidate


def private_directory(path: Path) -> None:
    path.mkdir(mode=0o700, parents=True, exist_ok=False)
    path.chmod(0o700)


def reduction(raw: int | None, output: int | None) -> float | None:
    if raw is None or output is None or raw == 0:
        return None
    return 100.0 * (raw - output) / raw


class Tokenizer:
    def __init__(self, cache: Path):
        import tiktoken
        from unittest.mock import patch
        os.environ["TIKTOKEN_CACHE_DIR"] = str(cache)
        # Encoding downloads must be cached explicitly before the pilot. Do not
        # silently perform network work while measuring commands.
        if not cache.is_dir() or len(list(cache.iterdir())) < 2:
            raise ValueError("warm both tokenizer encoding caches before running the pilot")
        with patch("requests.get", side_effect=RuntimeError("tokenizer cache missing; network disabled during pilot")):
            self.encoders = {name: tiktoken.get_encoding(name) for name in ENCODINGS}

    def describe(self, data: bytes) -> dict:
        try:
            text = data.decode("utf-8", errors="strict")
        except UnicodeDecodeError:
            return {"bytes": len(data), "sha256": sha256(data), "utf8": False,
                    "tokens": {name: None for name in ENCODINGS}}
        return {"bytes": len(data), "sha256": sha256(data), "utf8": True,
                "tokens": {name: len(encoding.encode(text, disallowed_special=()))
                           for name, encoding in self.encoders.items()}}


def contracts(data: bytes, definitions: list[dict]) -> list[dict]:
    try:
        text = data.decode("utf-8", errors="strict")
    except UnicodeDecodeError:
        text = None
    return [{"id": item["id"], "passed": text is not None and
             any(re.search(pattern, text, re.MULTILINE) is not None
                 for pattern in item.get("any", []))} for item in definitions]


def stdout_contracts(original: bytes, output: bytes, definitions: list[dict]) -> list[dict]:
    baseline = contracts(original, definitions)
    observed = contracts(output, definitions)
    return [{"id": before["id"], "eligible": before["passed"],
             "passed": after["passed"] if before["passed"] else None}
            for before, after in zip(baseline, observed)]


def plan_repositories(plan: dict) -> list[dict]:
    return plan.get("repositories", plan.get("repos", []))


def terminate_group(process: subprocess.Popen, number: int) -> None:
    try:
        os.killpg(process.pid, number)
    except ProcessLookupError:
        pass


def execute(argv: list[str], cwd: Path, env: dict[str, str], directory: Path,
            timeout: float = 60.0, stdin: bytes | None = None) -> dict:
    """Drain both streams concurrently; timeout covers EOF, including descendants."""
    private_directory(directory)
    started = time.perf_counter()
    first = None
    timed_out = False
    output_limit = False
    killed_at = None
    sizes = {"stdout": 0, "stderr": 0}
    with (directory / "stdout").open("wb") as out, (directory / "stderr").open("wb") as err:
        process = subprocess.Popen(argv, cwd=cwd, env=env, stdin=subprocess.PIPE if stdin is not None else subprocess.DEVNULL,
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE, start_new_session=True)
        if stdin is not None:
            # Pipe adapters accept <=10MiB. A separate writer avoids deadlock if
            # a filter emits output before it consumes the complete input.
            import threading
            def feed():
                try:
                    process.stdin.write(stdin)
                    process.stdin.close()
                except (BrokenPipeError, OSError):
                    pass
            threading.Thread(target=feed, daemon=True).start()
        selector = selectors.DefaultSelector()
        selector.register(process.stdout, selectors.EVENT_READ, ("stdout", out))
        selector.register(process.stderr, selectors.EVENT_READ, ("stderr", err))
        try:
            while selector.get_map() or process.poll() is None:
                now = time.perf_counter()
                if killed_at is None and now - started >= timeout:
                    timed_out = True
                    killed_at = now
                    terminate_group(process, signal.SIGTERM)
                if killed_at is not None and now - killed_at >= 1.0:
                    terminate_group(process, signal.SIGKILL)
                    if process.poll() is None:
                        process.kill()
                    # An escaped descendant can retain a pipe. Capture is then
                    # incomplete, and must not become a performance success.
                    if now - killed_at >= 1.5:
                        break
                for key, _ in selector.select(timeout=0.02):
                    name, handle = key.data
                    chunk = os.read(key.fileobj.fileno(), 65536)
                    if not chunk:
                        selector.unregister(key.fileobj)
                        key.fileobj.close()
                        continue
                    if first is None:
                        first = time.perf_counter() - started
                    sizes[name] += len(chunk)
                    if sizes[name] <= MAX_OUTPUT:
                        handle.write(chunk)
                    else:
                        output_limit = True
                        if killed_at is None:
                            killed_at = time.perf_counter()
                            terminate_group(process, signal.SIGTERM)
            if process.poll() is None:
                terminate_group(process, signal.SIGKILL)
                process.kill()
            returncode = process.wait(timeout=5)
        finally:
            selector.close()
            for pipe in (process.stdout, process.stderr):
                if pipe and not pipe.closed:
                    pipe.close()
            if process.poll() is None:
                terminate_group(process, signal.SIGKILL)
                process.kill()
                process.wait(timeout=5)
    return {"returncode": returncode, "timed_out": timed_out, "output_limit": output_limit,
            "wall_seconds": time.perf_counter() - started,
            "time_to_first_output_seconds": first,
            "capture_complete": not (timed_out or output_limit)}


def describe_run(result: dict, directory: Path, run_root: Path, tokenizer: Tokenizer,
                 expected: int, definitions: list[dict]) -> dict:
    stdout, stderr = (directory / "stdout").read_bytes(), (directory / "stderr").read_bytes()
    return {**result, "stdout": tokenizer.describe(stdout), "stderr": tokenizer.describe(stderr),
            "exit_matches_expected": result["capture_complete"] and result["returncode"] == expected,
            "contracts": contracts(stdout + b"\n" + stderr, definitions),
            "private_capture": directory.relative_to(run_root).as_posix()}


def git(arguments: list[str], env: dict[str, str], cwd: Path | None = None) -> str:
    process = subprocess.Popen(["git", "-c", "core.hooksPath=/dev/null", *arguments], cwd=cwd,
                               env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, start_new_session=True)
    try:
        stdout, _ = process.communicate(timeout=180)
    except subprocess.TimeoutExpired:
        terminate_group(process, signal.SIGTERM)
        try:
            process.communicate(timeout=1)
        except subprocess.TimeoutExpired:
            terminate_group(process, signal.SIGKILL)
            process.kill()
            process.communicate(timeout=5)
        raise ValueError("Git preparation exceeded 180 seconds; no workload command was started")
    if process.returncode:
        raise ValueError("Git preparation failed; inspect the local repository state")
    return stdout.decode("utf-8").strip()


def validate_plan(plan: dict) -> None:
    repos = {item["id"] for item in plan_repositories(plan)}
    if len(repos) != 2 or len(plan_repositories(plan)) != 2:
        raise ValueError("the pilot requires exactly two distinct repositories")
    identifiers = set()
    for case in plan["cases"]:
        if case["id"] in identifiers or case["repo"] not in repos:
            raise ValueError("duplicate case ID or unknown repository")
        identifiers.add(case["id"])
        if not case.get("argv") or not all(isinstance(arg, str) for arg in case["argv"]):
            raise ValueError("case argv must be a nonempty string list")
        if case.get("scenario", "baseline") not in {"baseline", "controlled_failure"}:
            raise ValueError("unknown scenario")
        if case.get("group", "ordinary") not in {"ordinary", "controlled"}:
            raise ValueError("unknown aggregation group")
        if not isinstance(case["expected_exit"], int):
            raise ValueError("expected_exit must be an integer")
        for definition in case.get("contracts", []):
            for pattern in definition.get("any", []):
                re.compile(pattern)


def prepare_workspaces(plan: dict, repositories_root: Path, run_root: Path,
                       env: dict[str, str], plan_directory: Path) -> tuple[dict, list]:
    workspaces, provenance = {}, []
    for repo in plan_repositories(plan):
        source = safe_child(repositories_root, repo["source_name"])
        commit = repo["commit"]
        if re.fullmatch(r"[0-9a-f]{40}", commit) is None:
            raise ValueError("repository commit must be a full lowercase SHA")
        resolved = git(["rev-parse", f"{commit}^{{commit}}"], env, source)
        if resolved != commit:
            raise ValueError("repository commit must be a complete pinned commit SHA")
        dirty = bool(git(["status", "--porcelain"], env, source))
        for scenario in ("baseline", "controlled_failure"):
            destination = safe_child(run_root / "workspaces", f"{repo['id']}/{scenario}")
            destination.parent.mkdir(parents=True, exist_ok=True)
            git(["init", "--quiet", str(destination)], env)
            git(["config", "core.hooksPath", "/dev/null"], env, destination)
            # A depth-two pack transfer is independent (no hardlinks or
            # alternates) and retains HEAD~1 for the registered historical diffs.
            git(["fetch", "--no-tags", "--no-recurse-submodules", "--depth=2", str(source), commit], env, destination)
            git(["checkout", "--detach", commit], env, destination)
            if git(["rev-parse", "HEAD"], env, destination) != commit:
                raise ValueError("snapshot HEAD does not match the registered commit")
            if (destination / ".git/objects/info/alternates").exists():
                raise ValueError("snapshot unexpectedly depends on an external object store")
            workspaces[(repo["id"], scenario)] = destination
        patch_key = repo.get("language", repo["id"])
        patch = plan.get("controlled_patch", {}).get(patch_key)
        if patch:
            controlled = workspaces[(repo["id"], "controlled_failure")]
            target = safe_child(controlled, patch["file"])
            fixture = safe_child(PROJECT, patch["fixture"])
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(fixture.read_bytes())
            if patch.get("append_test_script"):
                package = controlled / "package.json"
                value = json.loads(package.read_text())
                append = patch["append_test_script"]
                if isinstance(append, bool):
                    append = patch["file"]
                value["scripts"]["test"] += " " + append
                package.write_text(json.dumps(value, indent=2) + "\n")
        provenance.append({"id": repo["id"], "name": repo["name"], "commit": commit,
                           "snapshot_method": "independent-init-fetch", "history_fetch_depth": 2,
                           "self_pilot": repo.get("self_pilot", False), "source_dirty": dirty,
                           "baseline_clean": not bool(git(["status", "--porcelain"], env, workspaces[(repo["id"], "baseline")])),
                           "controlled_patch_sha256": sha256(target.read_bytes()) if patch else None})
    return workspaces, provenance


def case_environment(base: dict[str, str], workspace: Path, run_root: Path) -> dict[str, str]:
    env = dict(base)
    env.pop("LEDGER_DASHBOARD_DIR", None)
    env.pop("FORCE_COLOR", None)
    env.update({"CI": "1", "NO_COLOR": "1", "TERM": "dumb", "LC_ALL": "C", "LANG": "C",
                "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": "/dev/null",
                "npm_config_cache": str(run_root / "npm-cache"), "npm_config_audit": "false",
                "npm_config_fund": "false", "npm_config_update_notifier": "false",
                "npm_config_offline": "true", "CARGO_NET_OFFLINE": "true", "RUST_BACKTRACE": "1",
                "CARGO_TARGET_DIR": str(workspace / "target"),
                "RTK_TELEMETRY_DISABLED": "1", "RTK_SUPPRESS_HOOK_WARNING": "1", "RTK_NO_TOML": "1",
                "RTK_RECALL": "0", "RTK_TEE": "0", "RTK_DB_PATH": str(run_root / "rtk-data/tracking.db"),
                "RTK_RECALL_DB": str(run_root / "rtk-data/recall.db"), "RTK_TEE_DIR": str(run_root / "rtk-data/tee"),
                "CLAUDE_CONFIG_DIR": str(run_root / "rtk-claude"),
                "XDG_CONFIG_HOME": str(run_root / "rtk-config"), "XDG_DATA_HOME": str(run_root / "rtk-data"),
                "XDG_STATE_HOME": str(run_root / "rtk-state"), "XDG_CACHE_HOME": str(run_root / "rtk-cache")})
    return env


def sum_tokens(run: dict, encoding: str) -> int | None:
    values = [run[name]["tokens"][encoding] for name in ("stdout", "stderr")]
    return None if any(value is None for value in values) else sum(values)


def pipe_succeeded(row: dict) -> bool:
    return row.get("filter_returncode", 0) == 0 and row.get("filter_complete", True)


def public_rtk_provenance(value: dict | None) -> dict | None:
    if value is None:
        return None
    fields = ("repository", "tag", "source_commit", "edition", "license", "target", "archive_url",
              "archive_sha256", "binary_sha256", "version_stdout", "global_macos_config_existed_before",
              "global_macos_rtk_directory_exists_after_probes", "named_pipe_filters", "pipe_raw_cap_bytes",
              "pipe_accepts_original_exit_status", "native_probe_exit_codes")
    public = {key: value[key] for key in fields if key in value}
    if value.get("edition") == "rtk-oss":
        public["engine_included"] = False
    return public


def summarize(results: dict) -> dict:
    """Use ratios of summed tokens. Keep unsupported, invalid and empty distinct."""
    summary = {"same_capture": {}, "native": {}, "same_capture_common": {}, "native_common": {}}
    for group in ("ordinary", "controlled"):
        cases = [case for case in results["cases"] if case["group"] == group]
        shared = {}
        for variant in ("mini", "rtk_pipe"):
            selected = [case["same_capture"] for case in cases if case["same_capture"].get(variant) is not None]
            entry = {"supported_cases": len(selected), "total_cases": len(cases), "encodings": {}}
            for encoding in ENCODINGS:
                pairs = [(row["raw"]["stdout"]["tokens"][encoding], row[variant]["stdout"]["tokens"][encoding])
                         for row in selected if variant != "rtk_pipe" or pipe_succeeded(row[variant])]
                valid = [(raw, output) for raw, output in pairs if raw is not None and output is not None]
                raw_total, output_total = sum(x[0] for x in valid), sum(x[1] for x in valid)
                entry["encodings"][encoding] = {"valid_cases": len(valid), "excluded_cases": len(selected) - len(valid), "raw_tokens": raw_total,
                    "output_tokens": output_total, "reduction_percent": reduction(raw_total, output_total)}
            shared[variant] = entry
        summary["same_capture"][group] = shared
        native = {}
        for variant in ("raw", "mini", "rtk"):
            rows = [trial for case in cases for trial in case["native"].get(variant, [])]
            entry = {"trials": len(rows), "status_mismatches": sum(not row["exit_matches_expected"] for row in rows),
                     "contract_failures": sum(not item["passed"] for row in rows for item in row["contracts"]),
                     "contract_checks": sum(len(row["contracts"]) for row in rows),
                     "timeouts": sum(row["timed_out"] for row in rows),
                     "median_wall_seconds": statistics.median(row["wall_seconds"] for row in rows if row["capture_complete"]) if any(row["capture_complete"] for row in rows) else None,
                     "encodings": {}}
            for encoding in ENCODINGS:
                totals = [sum_tokens(row, encoding) if row["capture_complete"] else None for row in rows]
                entry["encodings"][encoding] = {"valid_trials": sum(value is not None for value in totals),
                    "excluded_trials": sum(value is None for value in totals),
                    "tokens": sum(value for value in totals if value is not None)}
            native[variant] = entry
        # Compare only matching case/trial support, never a restricted RTK subset
        # against the entire baseline workload.
        for variant in ("mini", "rtk"):
            for encoding in ENCODINGS:
                candidates = [(raw, output) for case in cases for raw, output in zip(case["native"].get("raw", []), case["native"].get(variant, []))]
                pairs = [(sum_tokens(raw, encoding), sum_tokens(output, encoding)) for raw, output in candidates
                         if raw["capture_complete"] and output["capture_complete"]]
                valid = [(a, b) for a, b in pairs if a is not None and b is not None]
                a, b = sum(p[0] for p in valid), sum(p[1] for p in valid)
                native[variant]["encodings"][encoding].update({"paired_trials": len(valid), "excluded_pairs": len(candidates) - len(valid), "paired_raw_tokens": a,
                    "paired_output_tokens": b, "reduction_percent": reduction(a, b)})
        summary["native"][group] = native
        shared_common_cases = [case for case in cases if case["same_capture"].get("mini") is not None and case["same_capture"].get("rtk_pipe") is not None]
        common = {"case_ids": [case["id"] for case in shared_common_cases], "variants": {}}
        for variant in ("mini", "rtk_pipe"):
            entry = {"encodings": {}, "eligible_contract_checks": 0, "contract_failures": 0}
            for case in shared_common_cases:
                for item in case["same_capture"][variant].get("contracts_stdout", []):
                    entry["eligible_contract_checks"] += bool(item["eligible"])
                    entry["contract_failures"] += item["eligible"] and item["passed"] is False
            for encoding in ENCODINGS:
                pairs = [(case["same_capture"]["raw"]["stdout"]["tokens"][encoding],
                          case["same_capture"][variant]["stdout"]["tokens"][encoding]) for case in shared_common_cases
                         if pipe_succeeded(case["same_capture"]["rtk_pipe"]) and
                         all(case["same_capture"][name]["stdout"]["tokens"][encoding] is not None for name in ("raw", "mini", "rtk_pipe"))]
                valid = [(a, b) for a, b in pairs if a is not None and b is not None]
                a, b = sum(p[0] for p in valid), sum(p[1] for p in valid)
                entry["encodings"][encoding] = {"valid_cases": len(valid), "excluded_cases": len(shared_common_cases) - len(valid), "raw_tokens": a,
                    "output_tokens": b, "reduction_percent": reduction(a, b)}
            common["variants"][variant] = entry
        summary["same_capture_common"][group] = common
        native_common_cases = [case for case in cases if case["native"].get("rtk") and case["native"].get("mini")]
        native_common_triples = [triple for case in native_common_cases for triple in zip(case["native"]["raw"], case["native"]["mini"], case["native"]["rtk"])]
        common_native = {"case_ids": [case["id"] for case in native_common_cases], "variants": {}}
        for variant in ("raw", "mini", "rtk"):
            rows = [row for case in native_common_cases for row in case["native"][variant]]
            variant_index = {"raw": 0, "mini": 1, "rtk": 2}[variant]
            timing_rows = [triple[variant_index] for triple in native_common_triples if all(row["capture_complete"] for row in triple)]
            entry = {"trials": len(rows), "status_mismatches": sum(not row["exit_matches_expected"] for row in rows),
                     "contract_checks": sum(len(row["contracts"]) for row in rows),
                     "contract_failures": sum(not item["passed"] for row in rows for item in row["contracts"]),
                     "timing_trials": len(timing_rows),
                     "median_wall_seconds": statistics.median(row["wall_seconds"] for row in timing_rows) if timing_rows else None,
                     "encodings": {}}
            for encoding in ENCODINGS:
                candidates = [triple for case in native_common_cases for triple in zip(case["native"]["raw"], case["native"]["mini"], case["native"]["rtk"])]
                index = {"raw": 0, "mini": 1, "rtk": 2}[variant]
                pairs = [(sum_tokens(triple[0], encoding), sum_tokens(triple[index], encoding)) for triple in candidates
                         if all(row["capture_complete"] and sum_tokens(row, encoding) is not None for row in triple)]
                valid = [(a, b) for a, b in pairs if a is not None and b is not None]
                a, b = sum(p[0] for p in valid), sum(p[1] for p in valid)
                entry["encodings"][encoding] = {"paired_trials": len(valid), "excluded_pairs": len(candidates) - len(valid), "raw_tokens": a,
                    "output_tokens": b, "reduction_percent": reduction(a, b)}
            common_native["variants"][variant] = entry
        summary["native_common"][group] = common_native
    return summary


def render_summary(results: dict) -> str:
    summary = summarize(results)
    lines = ["# Pilot metrics summary", "", "Generated from retained metrics; raw output stays local.", "",
             "## Same-capture stdout-only filter comparison", "",
             "Original stderr is excluded for every variant in this track. Unsupported RTK adapters are null.", "",
             "| Group | Variant | Valid/common cases | o200k raw tokens | o200k output tokens | Reduction |", "| --- | --- | ---: | ---: | ---: | ---: |"]
    for group, common in summary["same_capture_common"].items():
        for name, value in common["variants"].items():
            metric = value["encodings"]["o200k_base"]
            percent = metric["reduction_percent"]
            lines.append(f"| {group} | {name} | {metric['valid_cases']}/{len(common['case_ids'])} | {metric['raw_tokens']} | {metric['output_tokens']} | {'NA' if percent is None else f'{percent:.2f}%'} |")
    lines += ["", "## Native paired execution", "", "Tokens sum separate stdout/stderr encodings. Timings are observational product-path timings, including auxiliary commands.", "",
              "| Group | Variant | Valid/common trials | o200k reduction | Status mismatches | Contract failures/checks | Median wall seconds |", "| --- | --- | ---: | ---: | ---: | ---: | ---: |"]
    for group, common in summary["native_common"].items():
        for name, value in common["variants"].items():
            percent = value["encodings"]["o200k_base"].get("reduction_percent")
            wall = value["median_wall_seconds"]
            valid = value['encodings']['o200k_base']['paired_trials']
            lines.append(f"| {group} | {name} | {valid}/{value['trials']} | {'NA' if percent is None else f'{percent:.2f}%'} | {value['status_mismatches']} | {value['contract_failures']}/{value['contract_checks']} | {'NA' if wall is None else f'{wall:.4f}'} |")
    lines += ["", "Memory, live-agent task completion, retries, API charges and total agent context are not measured. This convenience summary does not replace per-case review.", ""]
    return "\n".join(lines)


def export(results: dict, destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=False)
    write_json(destination / "metrics.json", results)
    write_json(destination / "summary.json", summarize(results))
    (destination / "summary.md").write_text(render_summary(results))


def binary_metadata(path: Path, env: dict[str, str]) -> dict:
    result = subprocess.run([str(path), "--version"], env=env, capture_output=True, timeout=20)
    # A wrapper is hashed as a launcher and its underlying pinned RTK artifact
    # receives its own independent provenance below.
    return {"name": path.name, "sha256": sha256(path.read_bytes()),
            "version": result.stdout.decode("utf-8", errors="strict").strip(), "version_status": result.returncode}


def run(args: argparse.Namespace) -> dict:
    plan_path = args.plan.resolve()
    plan_bytes = plan_path.read_bytes()
    plan = json.loads(plan_bytes)
    validate_plan(plan)
    run_root = args.run_root.resolve()
    private_directory(run_root)
    (run_root / "registered-plan.json").write_bytes(plan_bytes)
    harness_hash = sha256(Path(__file__).read_bytes())
    write_json(run_root / "registration.json", {"plan_sha256": sha256(plan_bytes), "harness_sha256": harness_hash,
                                               "registered_before_collection_utc": datetime.now(timezone.utc).isoformat()})
    (run_root / "workspaces").mkdir()
    for name in ("rtk-data", "rtk-claude", "rtk-config", "rtk-state", "rtk-cache", "npm-cache"):
        (run_root / name).mkdir(mode=0o700)
    env = os.environ.copy()
    if platform.system() == "Darwin" and (Path.home() / "Library/Application Support/rtk/config.toml").exists():
        raise ValueError("existing macOS RTK config would influence this pilot; no config was read or changed")
    for variable, path in (("CARGO_HOME", PROJECT / ".tools/cargo"), ("RUSTUP_HOME", PROJECT / ".tools/rustup")):
        if variable not in env and path.is_dir():
            env[variable] = str(path)
    cargo_bin = Path(env.get("CARGO_HOME", "/nonexistent")) / "bin"
    if cargo_bin.is_dir():
        env["PATH"] = str(cargo_bin) + os.pathsep + env["PATH"]
    env.update({"GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": "/dev/null"})
    mini, rtk = args.mini.resolve(), args.rtk.resolve()
    workspaces, repos = prepare_workspaces(plan, args.repositories_root.resolve(), run_root, env, plan_path.parent)
    if args.preflight_only:
        preflight = {"schema_version": SCHEMA, "kind": "raw-only-preflight", "plan_sha256": sha256(plan_bytes), "harness_sha256": harness_hash,
                     "repositories": repos, "cases": [], "passed": True}
        for case in plan["cases"]:
            print(f"Preflight {case['id']}", flush=True)
            workspace = workspaces[(case["repo"], case.get("scenario", "baseline"))]
            directory = safe_child(run_root / "preflight", case["id"])
            directory.parent.mkdir(parents=True, exist_ok=True)
            value = execute(case["argv"], workspace, case_environment(env, workspace, run_root), directory, args.timeout)
            stdout, stderr = (directory / "stdout").read_bytes(), (directory / "stderr").read_bytes()
            checks = contracts(stdout + b"\n" + stderr, case.get("contracts", []))
            passed = value["capture_complete"] and value["returncode"] == case["expected_exit"] and all(item["passed"] for item in checks)
            preflight["passed"] = preflight["passed"] and passed
            preflight["cases"].append({"id": case["id"], "argv": case["argv"], "expected_exit": case["expected_exit"],
                **value, "contracts": checks, "passed": passed,
                "stdout_sha256": sha256(stdout), "stderr_sha256": sha256(stderr),
                "private_capture": directory.relative_to(run_root).as_posix()})
            write_json(run_root / "preflight.json", preflight)
        return preflight
    tokenizer = Tokenizer(args.tokenizer_cache.resolve())
    versions = {}
    for tool in ("git", "rustc", "cargo", "node", "npm"):
        try:
            value = subprocess.run([tool, "--version"], env=env, capture_output=True, timeout=20)
            versions[tool] = {"version": value.stdout.decode("utf-8").strip(), "status": value.returncode}
        except (OSError, subprocess.TimeoutExpired):
            versions[tool] = {"version": None, "status": None}
    rtk_provenance = json.loads(args.rtk_provenance.read_text()) if args.rtk_provenance.is_file() else None
    if rtk_provenance is None or sha256(rtk.read_bytes()) != rtk_provenance.get("binary_sha256"):
        raise ValueError("RTK binary does not match the pinned official artifact provenance")
    install_report = json.loads(args.tokenizer_install_report.read_text()) if args.tokenizer_install_report.is_file() else None
    wheels = [{"name": item["metadata"]["name"], "version": item["metadata"]["version"],
               "hashes": item.get("download_info", {}).get("archive_info", {}).get("hashes", {})}
              for item in (install_report or {}).get("install", [])]
    probe_env = case_environment(env, next(iter(workspaces.values())), run_root)
    results = {"schema_version": SCHEMA, "started_utc": datetime.now(timezone.utc).isoformat(),
               "plan_sha256": sha256(plan_bytes), "harness_sha256": harness_hash, "repositories": repos,
               "platform": {"system": platform.system(), "release": platform.release(), "machine": platform.machine(), "python": platform.python_version()},
               "binaries": {"mini": binary_metadata(mini, probe_env), "rtk_launcher": binary_metadata(rtk, probe_env)},
               "rtk_provenance": public_rtk_provenance(rtk_provenance), "tools": versions,
               "tokenizer": {"name": "tiktoken", "version": importlib.metadata.version("tiktoken"), "encodings": list(ENCODINGS), "wheels": wheels,
                             "cache_sha256": {path.name: sha256(path.read_bytes()) for path in sorted(args.tokenizer_cache.iterdir()) if path.is_file()}},
               "seed": args.seed, "repetitions": args.repetitions, "warmups_per_variant_case": 1,
               "limitations": ["stdout-only same-capture filter track", "native paired runs are separate executions", "no memory measurement", "no live-agent task/cost/retry measurement"],
               "cases": []}
    rng = random.Random(args.seed)
    for case in plan["cases"]:
        print(f"Running {case['id']}", flush=True)
        scenario = case.get("scenario", "baseline")
        workspace = workspaces[(case["repo"], scenario)]
        case_env = case_environment(env, workspace, run_root)
        directory = safe_child(run_root / "captures", case["id"])
        directory.mkdir(parents=True)
        definitions = case.get("contracts", [])
        expected = case["expected_exit"]
        record_dir = directory / "record"
        live_dir = directory / "record-live"
        live = execute([str(mini), "--record", str(record_dir), *case["argv"]], workspace, case_env, live_dir, args.timeout)
        metadata = json.loads((record_dir / "metadata.json").read_text())
        if not metadata.get("complete") or metadata.get("cancelled") or metadata.get("stdout_spilled") or metadata.get("stderr_spilled"):
            raise ValueError(f"record is incomplete or nonreplayable: {case['id']}")
        raw_out = (record_dir / "stdout.raw").read_bytes()
        raw_err = (record_dir / "stderr.raw").read_bytes()
        filtered_out = (record_dir / "stdout.filtered").read_bytes()
        filtered_err = (record_dir / "stderr.filtered").read_bytes()
        replay_dir = directory / "replay"
        replay = execute([str(mini), "--replay", str(record_dir)], workspace, case_env, replay_dir, args.timeout)
        replay_ok = replay["returncode"] == metadata["exit_code"] and (replay_dir / "stdout").read_bytes() == filtered_out and (replay_dir / "stderr").read_bytes() == filtered_err
        raw = {"stdout": tokenizer.describe(raw_out), "stderr": tokenizer.describe(raw_err), "returncode": metadata["exit_code"]}
        shared = {"raw": raw, "mini": {"stdout": tokenizer.describe(filtered_out), "stderr": tokenizer.describe(filtered_err),
                  "contracts_stdout": stdout_contracts(raw_out, filtered_out, definitions)}, "rtk_pipe": None,
                  "record_status_matches_expected": metadata["exit_code"] == expected and live["returncode"] == expected,
                  "replay_exact": replay_ok, "private_record": record_dir.relative_to(run_root).as_posix(),
                  "stderr_included_in_token_comparison": False}
        if case.get("rtk_pipe"):
            pipe_dir = directory / "rtk-pipe"
            pipe = execute([str(rtk), "pipe", "--filter", case["rtk_pipe"]], workspace, case_env, pipe_dir, args.timeout, raw_out)
            shared["rtk_pipe"] = {"stdout": tokenizer.describe((pipe_dir / "stdout").read_bytes()),
                                  "stderr": tokenizer.describe((pipe_dir / "stderr").read_bytes()),
                                  "filter_returncode": pipe["returncode"], "filter_complete": pipe["capture_complete"],
                                  "contracts_stdout": stdout_contracts(raw_out, (pipe_dir / "stdout").read_bytes(), definitions)}
        native_argv = {"raw": case["argv"], "mini": [str(mini), *case["argv"]]}
        if case.get("rtk_native") is not None:
            native_argv["rtk"] = [str(rtk), *case["rtk_native"]]
        native = {name: [] for name in native_argv}
        warmups = {}
        for name, argv in native_argv.items():
            warm_dir = directory / f"warmup-{name}"
            result = execute(argv, workspace, case_env, warm_dir, args.timeout)
            warmups[name] = describe_run(result, warm_dir, run_root, tokenizer, expected, definitions)
        orders = []
        names = list(native_argv)
        rng.shuffle(names)
        for repetition in range(args.repetitions):
            order = names[repetition % len(names):] + names[:repetition % len(names)]
            orders.append(order)
            for name in order:
                trial_dir = directory / f"trial-{repetition + 1}-{name}"
                value = execute(native_argv[name], workspace, case_env, trial_dir, args.timeout)
                native[name].append(describe_run(value, trial_dir, run_root, tokenizer, expected, definitions))
        results["cases"].append({"id": case["id"], "repo": case["repo"], "scenario": scenario,
                                 "group": case.get("group", "ordinary"), "argv": case["argv"],
                                 "rtk_native_argv": case.get("rtk_native"), "rtk_pipe_filter": case.get("rtk_pipe"),
                                 "expected_exit": expected, "same_capture": shared, "native": native,
                                 "warmups": warmups, "trial_variant_orders": orders})
        write_json(run_root / "results.pending.json", results)
    results["finished_utc"] = datetime.now(timezone.utc).isoformat()
    results["summary"] = summarize(results)
    write_json(run_root / "results.json", results)
    (run_root / "summary.md").write_text(render_summary(results))
    return results


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", type=Path, default=PROJECT / "evaluation/plans/pilot-v0.2.json")
    parser.add_argument("--repositories-root", type=Path)
    parser.add_argument("--mini", type=Path, default=PROJECT / "target/release/mini")
    parser.add_argument("--rtk", type=Path, default=PROJECT / ".tools/rtk-1.1.0/bin/rtk")
    parser.add_argument("--rtk-provenance", type=Path, default=PROJECT / ".tools/rtk-1.1.0/provenance.json")
    parser.add_argument("--tokenizer-cache", type=Path, default=PROJECT / ".tools/tokenizer-cache")
    parser.add_argument("--tokenizer-install-report", type=Path, default=PROJECT / ".tools/rtk-1.1.0/tokenizer-install-report.json")
    parser.add_argument("--run-root", type=Path)
    parser.add_argument("--report", type=Path, help="regenerate a sanitized summary from an existing metrics JSON")
    parser.add_argument("--preflight-only", action="store_true", help="run registered raw commands only; save private readiness/status/contract checks")
    parser.add_argument("--export", type=Path, help="explicitly export metadata/metrics only, never raw captures")
    parser.add_argument("--repetitions", type=int, default=3)
    parser.add_argument("--seed", type=int, default=20261106)
    parser.add_argument("--timeout", type=float, default=60.0)
    args = parser.parse_args(argv)
    if args.repetitions < 1 or args.timeout <= 0:
        parser.error("repetitions and timeout must be positive")
    if args.preflight_only and (args.report or args.export):
        parser.error("raw-only preflight cannot be combined with report/export")
    try:
        if args.report:
            results = json.loads(args.report.read_text())
            if results.get("schema_version") != SCHEMA:
                raise ValueError("unsupported report schema")
        else:
            if args.repositories_root is None or args.run_root is None:
                parser.error("--repositories-root and --run-root are required for a pilot")
            results = run(args)
        if args.preflight_only:
            print(json.dumps({"preflight_passed": results["passed"], "cases": len(results["cases"])}, indent=2))
            return 0 if results["passed"] else 1
        if args.export:
            export(results, args.export)
        print(render_summary(results))
        return 0
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
        print(f"evaluation: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
