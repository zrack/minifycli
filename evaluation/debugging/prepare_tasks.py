#!/usr/bin/env python3
"""Post-registration reproduction helper; not used to collect the original sprint.

Fetch pinned public sources and development dependencies into a new private
preparation tree. No model calls, agent sessions, or comparative trials occur.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import tarfile
import time

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
TASKS = HERE / "tasks"
PUBLIC_REPOSITORY = re.compile(r"https://github\.com/[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+(?:\.git)?$")
COMMIT = re.compile(r"[0-9a-f]{40}$")


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def write_json(path: Path, value: dict) -> None:
    with path.open("x", encoding="utf-8") as handle:
        json.dump(value, handle, indent=2, sort_keys=True)
        handle.write("\n")


def environment(destination: Path, cargo_home: Path, rustup_home: Path) -> dict[str, str]:
    env = {key: value for key, value in os.environ.items() if key in {"PATH", "HOME"}}
    env["PATH"] = str(cargo_home / "bin") + os.pathsep + env.get("PATH", os.defpath)
    settings = destination / "settings"
    settings.mkdir(mode=0o700)
    userconfig, globalconfig = settings / "npm-userconfig", settings / "npm-globalconfig"
    userconfig.touch(mode=0o600)
    globalconfig.touch(mode=0o600)
    temp = destination / "tmp"
    temp.mkdir(mode=0o700)
    env.update({"CARGO_HOME": str(cargo_home), "RUSTUP_HOME": str(rustup_home),
                "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": "/dev/null", "GIT_TERMINAL_PROMPT": "0",
                "GIT_ASKPASS": "/usr/bin/false", "GIT_CONFIG_COUNT": "2",
                "GIT_CONFIG_KEY_0": "credential.helper", "GIT_CONFIG_VALUE_0": "",
                "GIT_CONFIG_KEY_1": "core.askPass", "GIT_CONFIG_VALUE_1": "",
                "npm_config_userconfig": str(userconfig), "npm_config_globalconfig": str(globalconfig),
                "npm_config_cache": str(destination / "npm-cache"), "npm_config_audit": "false",
                "npm_config_fund": "false", "npm_config_update_notifier": "false",
                "NO_COLOR": "1", "FORCE_COLOR": "0", "CI": "1", "RUST_BACKTRACE": "1",
                "TMPDIR": str(temp), "TMP": str(temp)})
    return env


def run(argv: list[str], cwd: Path, env: dict[str, str], logs: Path, label: str,
        receipt: dict, *, timeout: int = 180, stdout_path: Path | None = None,
        expected: int = 0) -> dict:
    logs.mkdir(mode=0o700, parents=True, exist_ok=True)
    stdout_path = stdout_path or logs / (label + ".stdout")
    stderr_path = logs / (label + ".stderr")
    started = time.monotonic()
    timed_out = False
    with stdout_path.open("xb") as stdout, stderr_path.open("xb") as stderr:
        process = subprocess.Popen(argv, cwd=cwd, env=env, stdin=subprocess.DEVNULL,
                                   stdout=stdout, stderr=stderr, start_new_session=True)
        try:
            returncode = process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            timed_out = True
            os.killpg(process.pid, signal.SIGKILL)
            returncode = process.wait(timeout=5)
    entry = {"label": label, "argv": argv, "exit_code": returncode, "timed_out": timed_out,
             "expected_exit_code": expected, "wall_seconds": time.monotonic() - started,
             "stdout": {"sha256": digest(stdout_path), "bytes": stdout_path.stat().st_size},
             "stderr": {"sha256": digest(stderr_path), "bytes": stderr_path.stat().st_size}}
    receipt["commands"].append(entry)
    if timed_out or returncode != expected:
        raise RuntimeError(f"Preparation step {label} returned {returncode}, expected {expected}; inspect private logs")
    return entry


def extract_archive(archive: Path, destination: Path) -> None:
    destination.mkdir(mode=0o700, parents=True, exist_ok=False)
    with tarfile.open(archive, "r:") as handle:
        for member in handle.getmembers():
            parts = Path(member.name).parts
            if Path(member.name).is_absolute() or ".." in parts or ".git" in parts:
                raise ValueError("source archive contains an unsafe path")
            if not (member.isfile() or member.isdir()):
                raise ValueError("selected source archive has an unexpected link or special file")
        handle.extractall(destination, filter="data")


def copy_dependencies(source: Path, destination: Path) -> None:
    source = source.resolve(strict=True)
    for directory, dirs, files in os.walk(source, followlinks=False):
        for name in dirs + files:
            path = Path(directory) / name
            if path.is_symlink() and (Path(os.readlink(path)).is_absolute() or not path.resolve().is_relative_to(source)):
                raise ValueError("dependency symlink escapes its installed tree")
    shutil.copytree(source, destination / "node_modules", symlinks=True)
    shutil.rmtree(destination / "node_modules/.cache", ignore_errors=True)


def load_tasks() -> list[dict]:
    return [json.loads((TASKS / group / (identifier + ".json")).read_text())
            for group, ids in [("rust", ["R1", "R2", "R3"]), ("js", ["J1", "J2", "J3"])]
            for identifier in ids]


def qualification_statuses() -> dict[tuple[str, str, str], int]:
    javascript = json.loads((TASKS / "js/qualification.json").read_text())
    rust = json.loads((TASKS / "rust/preflight.json").read_text())
    values = {(r["id"], r["version"], r["check"]): r["exit_code"] for r in javascript["checks"]}
    values.update({(r["task"], r["variant"], r["group"]): r["exit_code"] for r in rust["results"]})
    return values


def prepare(destination: Path, cargo_home: Path, rustup_home: Path, *, qualify: bool,
            skip_rust_fetch: bool = False) -> dict:
    destination = destination.resolve()
    destination.mkdir(mode=0o700, parents=True, exist_ok=False)
    receipt = {"schema": 1, "purpose": "Post-registration reproduction setup; not used in original collection",
               "started_utc": datetime.now(timezone.utc).isoformat(), "commands": [], "tasks": [],
               "qualified": False, "finished": False}
    try:
        env = environment(destination, cargo_home.resolve(), rustup_home.resolve())
        logs = destination / "logs"
        receipt["tool_versions"] = {}
        for program in ["git", "node", "npm", "rustc", "cargo"]:
            label = "version-" + program
            run([program, "--version"], destination, env, logs, label, receipt)
            receipt["tool_versions"][program] = (logs / (label + ".stdout")).read_text().strip()
        repositories = {}
        for task in load_tasks():
            identifier, url = task["id"], task["repository"]["url"]
            if not PUBLIC_REPOSITORY.fullmatch(url):
                raise ValueError("only registered public GitHub HTTPS repositories are permitted")
            repository = destination / "repositories" / hashlib.sha256(url.encode()).hexdigest()[:12]
            if url not in repositories:
                repository.mkdir(mode=0o700, parents=True)
                run(["git", "init", "-q"], repository, env, logs, "git-init-" + repository.name, receipt)
                repositories[url] = repository
            for variant, key in [("base", "base_commit"), ("oracle", "oracle_commit")]:
                commit = task[key]
                if not COMMIT.fullmatch(commit):
                    raise ValueError("source must be pinned by full lowercase Git commit")
                label = identifier + "-" + variant
                run(["git", "-c", "core.hooksPath=/dev/null", "fetch", "--no-tags", "--depth=1", url, commit],
                    repository, env, logs, label + "-fetch", receipt)
                archive = destination / (label + ".tar")
                run(["git", "archive", "--format=tar", commit], repository, env, logs, label + "-archive", receipt,
                    stdout_path=archive)
                source = destination / ("rust/preflight" if identifier.startswith("R") else "js") / identifier / variant
                extract_archive(archive, source)
                if "baseline_lockfile" in task["assets"]:
                    shutil.copyfile(ROOT / task["assets"]["baseline_lockfile"], source / "Cargo.lock")
                receipt["tasks"].append({"id": identifier, "variant": variant, "repository": url, "commit": commit,
                                           "archive_sha256": digest(archive),
                                           "baseline_lockfile_sha256": digest(source / "Cargo.lock") if "baseline_lockfile" in task["assets"] else None,
                                           "manifest_sha256": digest(TASKS / ("rust" if identifier.startswith("R") else "js") / (identifier + ".json"))})
        dependencies = destination / "js/deps"
        dependencies.mkdir(mode=0o700)
        shutil.copyfile(TASKS / "js/dependencies.json", dependencies / "package.json")
        shutil.copyfile(TASKS / "js/dependencies-lock.json", dependencies / "package-lock.json")
        receipt["javascript_dependency_lock_sha256"] = digest(dependencies / "package-lock.json")
        run(["npm", "ci", "--ignore-scripts", "--no-audit", "--no-fund"], dependencies, env, logs, "npm-ci", receipt)
        for identifier in ["J1", "J2", "J3"]:
            for variant in ["base", "oracle"]:
                copy_dependencies(dependencies / "node_modules", destination / "js" / identifier / variant)
        if not skip_rust_fetch:
            for identifier in ["R1", "R2", "R3"]:
                source = destination / "rust/preflight" / identifier / "base"
                run(["cargo", "fetch", "--locked", "--manifest-path", str(source / "Cargo.toml")],
                    source, env, logs, identifier + "-cargo-fetch", receipt)
        if qualify:
            statuses = qualification_statuses()
            offline = {**env, "CARGO_NET_OFFLINE": "true", "npm_config_offline": "true"}
            for task in load_tasks():
                identifier = task["id"]
                for variant in ["base", "oracle"]:
                    source = destination / ("rust/preflight" if identifier.startswith("R") else "js") / identifier / variant
                    label = identifier + "-" + variant
                    check_env = {**offline, "CARGO_TARGET_DIR": str(destination / "targets" / label / "baseline")}
                    run(task["baseline_command"], source, check_env, logs, label + "-baseline", receipt,
                        timeout=120, expected=statuses[identifier, variant, "baseline"])
                    hidden = [str(source) if arg == "WORKSPACE" else str(ROOT / arg) if arg.startswith("evaluation/") else arg
                              for arg in task["hidden_command"]]
                    if identifier.startswith("R"):
                        hidden.extend(["--target-dir", str(destination / "targets" / label / "hidden")])
                    run(hidden, source, check_env, logs, label + "-hidden", receipt,
                        timeout=120, expected=statuses[identifier, variant, "hidden"])
            receipt["qualified"] = True
        receipt["finished"] = True
        return receipt
    except Exception as error:
        receipt["failure"] = {"type": type(error).__name__, "message": str(error)}
        raise
    finally:
        receipt["ended_utc"] = datetime.now(timezone.utc).isoformat()
        write_json(destination / "preparation.json", receipt)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--destination", type=Path, default=ROOT / ".tools/debug-sprint-prep",
                        help="New exclusive preparation root; defaults to the runner's expected layout")
    parser.add_argument("--cargo-home", type=Path, default=ROOT / ".tools/cargo")
    parser.add_argument("--rustup-home", type=Path, default=ROOT / ".tools/rustup")
    parser.add_argument("--skip-rust-fetch", action="store_true", help="Require public locked Rust dependencies to be cached already")
    parser.add_argument("--qualify", action="store_true", help="Verify original baseline and hidden exit statuses; no agent calls")
    args = parser.parse_args()
    os.umask(0o077)
    try:
        result = prepare(args.destination, args.cargo_home, args.rustup_home,
                         qualify=args.qualify, skip_rust_fetch=args.skip_rust_fetch)
    except Exception as error:
        print(json.dumps({"ok": False, "error": type(error).__name__, "details": "Inspect the new preparation directory if it was created"}))
        return 1
    print(json.dumps({"ok": result["finished"], "qualified": result["qualified"], "source_snapshots": len(result["tasks"])}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
