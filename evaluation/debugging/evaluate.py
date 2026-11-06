"""Evaluate a frozen debugging repair without executing in the solver workspace.

Copies and logs are private evaluation artifacts. Returned JSON contains hashes,
counts and outcomes, not source, patches, absolute paths or test output.
"""
from __future__ import annotations

import difflib
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import time

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
EXCLUDED = {".git", "node_modules", "target", ".targetbaseline", ".targethidden", "__pycache__"}
ENVIRONMENT_KEYS = {"PATH", "HOME", "CARGO_HOME", "RUSTUP_HOME"}
TEST_MODULE = re.compile(rb"(?m)^#\[cfg\(test\)\]\r?\nmod (?:test|tests)\s*\{")
COMMAND_TIMEOUT_SECONDS = 120


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _files(root: Path) -> dict[str, bytes]:
    result = {}
    for directory, dirs, names in os.walk(root, followlinks=False):
        for name in dirs:
            path = Path(directory) / name
            if name not in EXCLUDED and path.is_symlink():
                raise ValueError(f"source snapshot contains a directory symlink: {path.relative_to(root)}")
        dirs[:] = sorted(d for d in dirs if d not in EXCLUDED)
        for name in sorted(names):
            path = Path(directory) / name
            if path.is_symlink():
                # Sources with symlinks must not acquire external files implicitly.
                raise ValueError(f"source snapshot contains a symlink: {path.relative_to(root)}")
            if path.is_file():
                result[path.relative_to(root).as_posix()] = path.read_bytes()
    return result


def _tree_hash(files: dict[str, bytes]) -> str:
    entries = [{"path": name, "sha256": sha256(data), "bytes": len(data)} for name, data in sorted(files.items())]
    return sha256(json.dumps(entries, sort_keys=True, separators=(",", ":")).encode())


def _copy_source(source: Path, destination: Path) -> None:
    # Inputs are inspected before copying. Installed test dependencies are handled
    # separately so no shared writable cache survives into an evaluation copy.
    shutil.copytree(source, destination, ignore=shutil.ignore_patterns(*EXCLUDED), symlinks=False)


def _install_dependencies(base: Path, destination: Path) -> None:
    dependencies = base / "node_modules"
    if dependencies.is_dir():
        source = dependencies.resolve()
        for directory, dirs, files in os.walk(source, followlinks=False):
            for name in dirs + files:
                path = Path(directory) / name
                if path.is_symlink() and (Path(os.readlink(path)).is_absolute() or not path.resolve().is_relative_to(source)):
                    raise ValueError("dependency symlink escapes its private dependency tree")
        # npm .bin launchers depend on their relative symlinks for __dirname.
        # Preserve those internal links while copying all dependency files.
        shutil.copytree(source, destination / "node_modules", symlinks=True)


def _production_path(name: str, rust: bool) -> bool:
    path = Path(name)
    return (len(path.parts) > 1 and path.parts[0] == "src" and path.suffix == ".rs") if rust else (
        name in {"index.js", "posix.js"} or len(path.parts) > 1 and path.parts[0] == "lib" and path.suffix == ".js")


def _split_rust(data: bytes, name: str, *, required: bool = False) -> tuple[bytes, bytes]:
    markers = list(TEST_MODULE.finditer(data))
    if len(markers) > 1 or required and len(markers) != 1:
        raise ValueError(f"missing or ambiguous original Rust test module: {name}")
    if not markers:
        return data, b""
    offset = markers[0].start()
    # Selected upstream snapshots put this test module at EOF. Its entire
    # suffix is restored, without parsing Rust braces or rewriting production.
    return data[:offset], data[offset:]


def _production(files: dict[str, bytes], rust: bool) -> dict[str, bytes]:
    return {name: _split_rust(data, name)[0] if rust else data
            for name, data in files.items() if _production_path(name, rust)}


def _overlay_production(base_files: dict[str, bytes], candidate_files: dict[str, bytes], destination: Path, rust: bool) -> list[str]:
    errors = []
    names = sorted({name for name in base_files | candidate_files if _production_path(name, rust)})
    for name in names:
        path = destination / name
        original = base_files.get(name)
        candidate = candidate_files.get(name)
        if candidate is None:
            if rust and original is not None and TEST_MODULE.search(original):
                errors.append(f"production file containing original tests was deleted: {name}")
                continue
            path.unlink(missing_ok=True)
            continue
        try:
            data = candidate
            if rust:
                _, suffix = _split_rust(original or b"", name)
                prefix, _ = _split_rust(candidate, name, required=bool(suffix))
                # A new test module must not replace production after a test
                # boundary absent from the original source.
                data = prefix + suffix
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        except ValueError as error:
            errors.append(str(error))
    return errors


def _patch(before: dict[str, bytes], after: dict[str, bytes]) -> bytes:
    chunks = []
    for name in sorted(before | after):
        old, new = before.get(name, b""), after.get(name, b"")
        if old == new:
            continue
        try:
            chunks.extend(difflib.unified_diff(old.decode("utf-8").splitlines(keepends=True),
                                               new.decode("utf-8").splitlines(keepends=True),
                                               fromfile="a/" + name, tofile="b/" + name))
        except UnicodeDecodeError:
            chunks.append(f"Binary change {name}: {sha256(old)} -> {sha256(new)}\n")
    return "".join(chunks).encode()


def _environment(directory: Path, target: Path) -> dict[str, str]:
    env = {key: value for key, value in os.environ.items() if key in ENVIRONMENT_KEYS}
    env.setdefault("PATH", os.defpath)
    temp = directory / "tmp"
    temp.mkdir(mode=0o700, exist_ok=True)
    npm_userconfig, npm_globalconfig = directory / "npm-userconfig", directory / "npm-globalconfig"
    npm_userconfig.touch(mode=0o600, exist_ok=False)
    npm_globalconfig.touch(mode=0o600, exist_ok=False)
    env.update({"CI": "1", "NO_COLOR": "1", "FORCE_COLOR": "0", "LANG": "C", "LC_ALL": "C",
                "TMPDIR": str(temp), "TMP": str(temp), "CARGO_NET_OFFLINE": "true", "CARGO_TARGET_DIR": str(target),
                "RUST_BACKTRACE": "1", "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": "/dev/null",
                "GIT_TERMINAL_PROMPT": "0", "npm_config_offline": "true", "npm_config_audit": "false",
                "npm_config_fund": "false", "npm_config_update_notifier": "false",
                "npm_config_userconfig": str(npm_userconfig), "npm_config_globalconfig": str(npm_globalconfig),
                "npm_config_cache": str(directory / "npm-cache")})
    return env


def _kill(process: subprocess.Popen, sig: int) -> None:
    try:
        os.killpg(process.pid, sig)
    except ProcessLookupError:
        pass


def _run(argv: list[str], cwd: Path, directory: Path, target: Path) -> dict:
    directory.mkdir(mode=0o700)
    start = time.monotonic()
    timed_out = False
    spawn_error = None
    returncode = None
    with (directory / "stdout").open("xb") as stdout, (directory / "stderr").open("xb") as stderr:
        try:
            process = subprocess.Popen(argv, cwd=cwd, env=_environment(directory, target), stdin=subprocess.DEVNULL,
                                       stdout=stdout, stderr=stderr, start_new_session=True)
            try:
                returncode = process.wait(timeout=COMMAND_TIMEOUT_SECONDS)
            except subprocess.TimeoutExpired:
                timed_out = True
                _kill(process, signal.SIGTERM)
                try:
                    process.wait(timeout=0.5)
                except subprocess.TimeoutExpired:
                    pass
                _kill(process, signal.SIGKILL)
                returncode = process.wait(timeout=5)
            finally:
                # Tests may have launched children which outlive their leader.
                _kill(process, signal.SIGKILL)
        except OSError as error:
            spawn_error = {"errno": error.errno, "type": type(error).__name__}
    streams = {}
    for name in ("stdout", "stderr"):
        path = directory / name
        path.chmod(0o600)
        data = path.read_bytes()
        streams[name] = {"bytes": len(data), "sha256": sha256(data)}
    return {"exit_code": returncode, "timed_out": timed_out, "spawn_error": spawn_error,
            "passed": returncode == 0 and not timed_out and spawn_error is None,
            "wall_seconds": time.monotonic() - start, "streams": streams}


def _hidden_command(task: dict, pristine: Path, directory: Path, rust: bool) -> list[str]:
    argv = []
    for argument in task["hidden_command"]:
        if argument == "WORKSPACE":
            argv.append(str(pristine))
        elif argument.startswith("evaluation/"):
            path = (REPOSITORY_ROOT / argument).resolve(strict=True)
            if not path.is_relative_to(REPOSITORY_ROOT / "evaluation/debugging/tasks"):
                raise ValueError("hidden asset escapes registered evaluation assets")
            argv.append(str(path))
        else:
            argv.append(argument)
    if "WORKSPACE" not in task["hidden_command"]:
        raise ValueError("hidden command must reference the candidate WORKSPACE")
    if rust:
        argv.extend(["--target-dir", str(directory / ".targethidden")])
    return argv


def evaluate_task(task: dict, base: Path, workspace: Path, output_dir: Path) -> dict:
    """Run pristine and candidate checks; preserve all attempts and frozen input."""
    base, workspace, output_dir = Path(base).resolve(), Path(workspace).resolve(), Path(output_dir).resolve()
    if base == workspace or base in workspace.parents or workspace in base.parents:
        raise ValueError("base and candidate must be separate source roots")
    if base == output_dir or workspace == output_dir or base in output_dir.parents or workspace in output_dir.parents:
        raise ValueError("evaluation output must be outside both input trees")
    output_dir.mkdir(mode=0o700, parents=False, exist_ok=False)
    rust = str(task["id"]).startswith("R")
    result = {"schema": 1, "task_id": task["id"], "correct_repair": False, "production_changed": False,
              "added_test_coverage": False, "restore_errors": [], "checks": {}, "infrastructure_errors": []}
    base_files = _files(base)
    candidate_files = _files(workspace)
    result["input_tree_hashes"] = {"base": _tree_hash(base_files), "candidate": _tree_hash(candidate_files)}
    try:
        before = _production(base_files, rust)
        after = _production(candidate_files, rust)
        result["production_changed"] = before != after
        test_paths = set(task.get("upstream_test_paths", []))
        result["added_test_coverage"] = any(
            candidate_files.get(name) != base_files.get(name)
            and (not rust or not _production_path(name, rust) or
                 _split_rust(candidate_files.get(name, b""), name)[1] != _split_rust(base_files.get(name, b""), name)[1])
            for name in candidate_files | base_files
            if name.startswith(("test/", "tests/")) or name in test_paths or rust and _production_path(name, rust))
        patch = _patch(base_files, candidate_files)
        (output_dir / "candidate.patch").write_bytes(patch)
        (output_dir / "candidate.patch").chmod(0o600)
        result["patch"] = {"bytes": len(patch), "sha256": sha256(patch), "changed_paths": sorted(
            name for name in base_files | candidate_files if base_files.get(name) != candidate_files.get(name))}
        pristine = output_dir / "pristine"
        candidate = output_dir / "candidate"
        _copy_source(base, pristine)
        _copy_source(workspace, candidate)
        _install_dependencies(base, pristine)
        _install_dependencies(base, candidate)
        result["restore_errors"] = _overlay_production(base_files, candidate_files, pristine, rust)
        result["checks"]["candidate_baseline"] = _run(task["baseline_command"], candidate, output_dir / "candidate-baseline", candidate / ".targetbaseline")
        if not result["restore_errors"]:
            result["checks"]["pristine_baseline"] = _run(task["baseline_command"], pristine, output_dir / "pristine-baseline", pristine / ".targetbaseline")
            hidden = _hidden_command(task, pristine, output_dir, rust)
            result["checks"]["hidden"] = _run(hidden, pristine, output_dir / "hidden", output_dir / ".targethidden")
        result["correct_repair"] = result["production_changed"] and not result["restore_errors"] and all(
            result["checks"].get(check, {}).get("passed", False) for check in ("candidate_baseline", "pristine_baseline", "hidden"))
    except (OSError, ValueError, KeyError, subprocess.SubprocessError) as error:
        result["infrastructure_errors"].append({"type": type(error).__name__, "message": str(error).replace(str(output_dir), "EVALUATION").replace(str(base), "BASE").replace(str(workspace), "WORKSPACE")})
        result["correct_repair"] = False
    finally:
        result["frozen_workspace_unchanged"] = _tree_hash(_files(workspace)) == result["input_tree_hashes"]["candidate"]
        if not result["frozen_workspace_unchanged"]:
            result["correct_repair"] = False
            result["infrastructure_errors"].append({"type": "InputMutation", "message": "Frozen solver source changed during evaluation"})
        (output_dir / "evaluation.json").write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
        (output_dir / "evaluation.json").chmod(0o600)
    return result
