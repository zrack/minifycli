"""Grade frozen confirmation repairs in disposable, private source copies.

Only manifest-allowlisted production files are overlaid on the pristine base.
Original tests, manifests and configuration stay pristine. Rust test items are
restored by balanced lexical spans, including nonterminal inline modules;
unknown/ambiguous changed test structures fail closed rather than using a suffix.
The frozen first-sprint helper module supplies filesystem/dependency/environment
operations only; include its hash among the new plan's implementation inputs.
"""
from __future__ import annotations

import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import signal
import subprocess
import time


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
HELPER_PATH = REPOSITORY_ROOT / "evaluation/debugging/evaluate.py"
_spec = importlib.util.spec_from_file_location("confirmation_frozen_helpers", HELPER_PATH)
_helpers = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_helpers)
_files, _tree_hash, _patch = _helpers._files, _helpers._tree_hash, _helpers._patch
_copy_source, _install_dependencies = _helpers._copy_source, _helpers._install_dependencies
sha256 = _helpers.sha256
COMMAND_TIMEOUT_SECONDS = 180
MINIMUM_FREE_BYTES = 4 * 1024 * 1024 * 1024
RAW_STRING = re.compile(r'(?:br|cr|r)(#*)"')
CHAR_LITERAL = re.compile(r"'(?:\\(?:u\{[0-9a-fA-F_]+\}|x[0-9a-fA-F]{2}|.)|[^'\\\r\n])'")
PROTECTED = ("test/**", "tests/**", "fixtures/**", "**/test/**", "**/tests/**", "**/fixtures/**",
             "**/tests.rs", "**/test.rs", "Cargo.toml", "Cargo.lock", "package.json", "package-lock.json",
             "pnpm-lock.yaml", "yarn.lock", "tsconfig*.json", ".cargo/**", "build.rs")


class RestoreError(ValueError):
    """A candidate's test structure cannot be restored unambiguously."""


class DiskSpaceError(ValueError):
    """Required working space is unavailable; no command should be started."""


def _check_disk(directory: Path, minimum: int, stage: str) -> None:
    if type(minimum) is not int or minimum < MINIMUM_FREE_BYTES:
        raise ValueError("minimum_free_bytes must be an integer of at least 4 GiB")
    free = shutil.disk_usage(directory).free
    receipt = {"stage": stage, "minimum_free_bytes": minimum, "observed_free_bytes": free,
               "sufficient": free >= minimum}
    # Filesystem capacity is private operational evidence, not a public result.
    path = directory / "disk-space.jsonl"
    with path.open("a", encoding="utf-8") as handle:
        path.chmod(0o600)
        handle.write(json.dumps(receipt, sort_keys=True) + "\n")
    if free < minimum:
        raise DiskSpaceError("Insufficient free disk space at " + stage + "; no command or cleanup started")


def _glob(pattern: str) -> re.Pattern:
    if not isinstance(pattern, str) or not pattern or pattern.startswith("/") or ".." in Path(pattern).parts or "\0" in pattern:
        raise ValueError("unsafe manifest glob")
    expression, index = "", 0
    while index < len(pattern):
        if pattern[index:index + 3] == "**/":
            expression += "(?:.*/)?"
            index += 3
        elif pattern[index:index + 2] == "**":
            expression += ".*"
            index += 2
        elif pattern[index] == "*":
            expression += "[^/]*"
            index += 1
        elif pattern[index] == "?":
            expression += "[^/]"
            index += 1
        else:
            expression += re.escape(pattern[index])
            index += 1
    return re.compile("^" + expression + "$")


def _policy(task: dict) -> tuple[list, list, int, list[str]]:
    if not isinstance(task.get("id"), str) or re.fullmatch(r"C-[RJ][123]", task["id"]) is None:
        raise ValueError("unknown confirmation task ID")
    config = task.get("evaluation")
    if not isinstance(config, dict) or not isinstance(config.get("production_globs"), list) or not config["production_globs"]:
        raise ValueError("task requires evaluation.production_globs")
    protected = config.get("protected_test_globs")
    if not isinstance(protected, list):
        raise ValueError("task requires evaluation.protected_test_globs")
    production = [_glob(pattern) for pattern in config["production_globs"]]
    protected = [_glob(pattern) for pattern in (*PROTECTED, *protected)]
    timeout = config.get("timeout_seconds", COMMAND_TIMEOUT_SECONDS)
    if type(timeout) is not int or not 30 <= timeout <= 600:
        raise ValueError("evaluation timeout must be an integer in 30..600 seconds")
    unset = task.get("setup", {}).get("environment_unset", [])
    if not isinstance(unset, list) or any(name not in {"NO_COLOR", "FORCE_COLOR"} for name in unset):
        raise ValueError("only declared color environment unsets are permitted")
    minimum = config.get("minimum_free_bytes", MINIMUM_FREE_BYTES)
    if type(minimum) is not int or minimum < MINIMUM_FREE_BYTES:
        raise ValueError("minimum_free_bytes must be an integer of at least 4 GiB")
    return production, protected, timeout, unset, minimum


def _production_path(name: str, policy: tuple) -> bool:
    production, protected, *_ = policy
    return any(pattern.fullmatch(name) for pattern in production) and not any(pattern.fullmatch(name) for pattern in protected)


def _rust_mask(source: str) -> str:
    """Blank comments/literals without moving delimiters; not a Rust compiler."""
    result = list(source)
    index = 0
    def blank(start, end):
        for position in range(start, end):
            if source[position] not in "\r\n":
                result[position] = " "
    while index < len(source):
        if source.startswith("//", index):
            end = source.find("\n", index)
            end = len(source) if end < 0 else end
            blank(index, end)
            index = end
        elif source.startswith("/*", index):
            start, depth = index, 1
            index += 2
            while index < len(source) and depth:
                if source.startswith("/*", index):
                    depth += 1
                    index += 2
                elif source.startswith("*/", index):
                    depth -= 1
                    index += 2
                else:
                    index += 1
            if depth:
                raise RestoreError("unterminated Rust comment")
            blank(start, index)
        else:
            raw = RAW_STRING.match(source, index) if index == 0 or not (source[index - 1].isalnum() or source[index - 1] == "_") else None
            if raw:
                end = source.find('"' + raw.group(1), raw.end())
                if end < 0:
                    raise RestoreError("unterminated Rust raw string")
                end += 1 + len(raw.group(1))
                blank(index, end)
                index = end
            elif source[index] == '"':
                start = index
                index += 1
                while index < len(source):
                    if source[index] == "\\":
                        index += 2
                    elif source[index] == '"':
                        index += 1
                        break
                    else:
                        index += 1
                else:
                    raise RestoreError("unterminated Rust string")
                blank(start, index)
            elif source[index] == "'":
                char = CHAR_LITERAL.match(source, index)
                if char:
                    blank(index, char.end())
                    index = char.end()
                else:
                    index += 1  # A lifetime, not a character literal.
            else:
                index += 1
    return "".join(result)


def _balanced(mask: str, start: int) -> int:
    opening = mask[start]
    pairs = {"[": "]", "(": ")", "{": "}"}
    stack = [pairs[opening]]
    for index in range(start + 1, len(mask)):
        char = mask[index]
        if char in pairs:
            stack.append(pairs[char])
        elif char in "])}":
            if not stack or char != stack.pop():
                raise RestoreError("unbalanced Rust item")
            if not stack:
                return index + 1
    raise RestoreError("unclosed Rust item")


def _inner_test_attributes(data: bytes) -> list[str]:
    source = data.decode("utf-8", errors="strict")
    mask, result, cursor = _rust_mask(source), [], 0
    while True:
        found = re.search(r"#\s*!\s*\[", mask[cursor:])
        if found is None:
            break
        start, bracket = cursor + found.start(), cursor + found.end() - 1
        end = _balanced(mask, bracket)
        if re.search(r"\btest\b", mask[bracket + 1:end - 1]):
            result.append(source[start:end])
        cursor = end
    return result


def _test_spans(data: bytes, *, preserved_inner: list[str] | None = None) -> tuple[str, list[dict]]:
    try:
        source = data.decode("utf-8", errors="strict")
    except UnicodeError as error:
        raise RestoreError("Rust production source is not UTF-8") from error
    mask = _rust_mask(source)
    attributes, cursor = [], 0
    while True:
        found = re.search(r"#\s*!?\s*\[", mask[cursor:])
        if found is None:
            break
        start = cursor + found.start()
        bracket = cursor + found.end() - 1
        end = _balanced(mask, bracket)
        attributes.append((start, end, re.sub(r"\s+", "", mask[bracket + 1:end - 1])))
        cursor = end
    groups = []
    for attribute in attributes:
        if groups and not mask[groups[-1][-1][1]:attribute[0]].strip():
            groups[-1].append(attribute)
        else:
            groups.append([attribute])
    spans, keys = [], set()
    for group in groups:
        start, attrs_end = group[0][0], group[-1][1]
        if spans and start < spans[-1]["end"]:
            continue
        mentions_test = [attribute[2] for attribute in group if re.search(r"\btest\b", attribute[2])]
        if not mentions_test:
            continue
        protected = False
        for attr in mentions_test:
            inner = next((source[attribute[0]:attribute[1]] for attribute in group if attribute[2] == attr), "")
            if attr.startswith("cfg_attr(") and re.match(r"#\s*!", inner) and inner in (preserved_inner or []):
                continue  # Verified byte-identical crate-level test configuration.
            if attr == "test" or attr == "cfg(test)" or attr.startswith("cfg(all(") and not re.search(r"\b(?:any|not)\(", attr):
                protected = True
            else:
                raise RestoreError("unrecognized Rust test attribute structure")
        if not protected:
            continue
        if "!" in mask[start:mask.find("[", start)]:
            raise RestoreError("unsupported Rust inner test attribute")
        # Find the item's first body/terminator, skipping signature arrays and
        # parentheses. Braces inside literals/comments have already been blanked.
        position = attrs_end
        while position < len(mask):
            if mask[position] in "([":
                position = _balanced(mask, position)
            elif mask[position] in "{;":
                break
            else:
                position += 1
        if position == len(mask):
            raise RestoreError("test attribute has no complete Rust item")
        header = mask[attrs_end:position].strip()
        named = re.search(r"\b(mod|fn|const|static|struct|enum|type|macro_rules)\s*!?\s*([A-Za-z_][A-Za-z_0-9]*)", header)
        if named:
            key = named.group(1) + ":" + named.group(2)
        elif re.match(r"(?:pub(?:\([^)]*\))?\s+)?(?:use|impl|extern)\b", header):
            key = re.sub(r"\s+", " ", header)
        else:
            raise RestoreError("unrecognized Rust protected item")
        if key in keys:
            raise RestoreError("ambiguous repeated Rust test item identity")
        keys.add(key)
        end = position + 1 if mask[position] == ";" else _balanced(mask, position)
        spans.append({"start": start, "end": end, "key": key, "text": source[start:end]})
    return source, spans


def _without_tests(source: str, spans: list[dict]) -> bytes:
    for span in reversed(spans):
        source = source[:span["start"]] + source[span["end"]:]
    return source.encode()


def _restore_rust(original: bytes, candidate: bytes) -> tuple[bytes, bool, bool]:
    inner = _inner_test_attributes(original)
    if inner != _inner_test_attributes(candidate):
        raise RestoreError("candidate changed original crate-level test configuration")
    before, original_spans = _test_spans(original, preserved_inner=inner)
    after, candidate_spans = _test_spans(candidate, preserved_inner=inner)
    originals = {span["key"]: span for span in original_spans}
    candidates = {span["key"]: span for span in candidate_spans}
    if set(originals) - set(candidates):
        raise RestoreError("candidate removed or renamed an original protected Rust test item")
    restored = after
    for span in reversed(candidate_spans):
        replacement = originals.get(span["key"], {}).get("text", "")
        restored = restored[:span["start"]] + replacement + restored[span["end"]:]
    production_changed = _without_tests(before, original_spans).strip() != _without_tests(after, candidate_spans).strip()
    tests_changed = [span["text"] for span in original_spans] != [span["text"] for span in candidate_spans]
    return restored.encode(), production_changed, tests_changed


def _overlay(base: dict, candidate: dict, destination: Path, policy: tuple) -> tuple[list[str], bool, bool]:
    errors, production_changed, tests_changed = [], False, False
    for name in sorted(base | candidate):
        before, after = base.get(name), candidate.get(name)
        if before == after:
            continue
        if not _production_path(name, policy):
            if any(pattern.fullmatch(name) for pattern in policy[1]):
                tests_changed = True
            continue
        target = destination / name
        try:
            if after is None:
                if name.endswith(".rs") and _test_spans(before)[1]:
                    raise RestoreError("production file containing protected tests was deleted")
                target.unlink(missing_ok=True)
                production_changed = True
            else:
                if name.endswith(".rs"):
                    data, changed, changed_tests = _restore_rust(before or b"", after)
                    production_changed |= changed
                    tests_changed |= changed_tests
                else:
                    data = after
                    production_changed = True
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(data)
        except RestoreError as error:
            errors.append(name + ": " + str(error))
    return errors, production_changed, tests_changed


def _run(argv: list[str], cwd: Path, directory: Path, target: Path, *, timeout: int = COMMAND_TIMEOUT_SECONDS,
         environment_unset: list[str] | None = None, minimum_free_bytes: int = MINIMUM_FREE_BYTES) -> dict:
    directory.mkdir(mode=0o700)
    _check_disk(directory, minimum_free_bytes, "before-check")
    # This helper may delete only a target newly created under its evaluator
    # output tree. Never delete a preexisting/shared target or any source/logs.
    boundary = directory.parent.resolve()
    target = target.resolve()
    owned = target.is_relative_to(boundary) and target.name in {".targetbaseline", ".targethidden"} and not target.exists()
    if not owned:
        raise ValueError("compiler target must be a new evaluator-owned disposable path")
    start, returncode, timed_out, spawn_error = time.monotonic(), None, False, None
    cleanup = {"owned": True, "created": False, "removed": False, "error_type": None}
    with (directory / "stdout").open("xb") as stdout, (directory / "stderr").open("xb") as stderr:
        try:
            env = _helpers._environment(directory, target)
            for name in environment_unset or []:
                if name not in {"NO_COLOR", "FORCE_COLOR"}:
                    raise ValueError("unsupported task environment unset")
                env.pop(name, None)
            process = subprocess.Popen(argv, cwd=cwd, env=env, stdin=subprocess.DEVNULL,
                                       stdout=stdout, stderr=stderr, start_new_session=True)
            try:
                returncode = process.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                timed_out = True
                _helpers._kill(process, signal.SIGTERM)
                try:
                    process.wait(timeout=0.5)
                except subprocess.TimeoutExpired:
                    pass
                _helpers._kill(process, signal.SIGKILL)
                returncode = process.wait(timeout=5)
            finally:
                _helpers._kill(process, signal.SIGKILL)
        except OSError as error:
            spawn_error = {"errno": error.errno, "type": type(error).__name__}
    streams = {}
    for name in ("stdout", "stderr"):
        path = directory / name
        path.chmod(0o600)
        data = path.read_bytes()
        streams[name] = {"bytes": len(data), "sha256": sha256(data)}
    cleanup["created"] = target.exists()
    if cleanup["created"]:
        try:
            if target.is_symlink():
                target.unlink()
            elif target.is_dir():
                shutil.rmtree(target)
            else:
                target.unlink()
            cleanup["removed"] = True
        except OSError as error:
            cleanup["error_type"] = type(error).__name__
    return {"exit_code": returncode, "timed_out": timed_out, "spawn_error": spawn_error,
            "passed": returncode == 0 and not timed_out and spawn_error is None,
            "wall_seconds": time.monotonic() - start, "streams": streams, "target_cleanup": cleanup}


def _hidden_command(task: dict, pristine: Path, directory: Path) -> list[str]:
    arguments = task.get("hidden_command")
    if not isinstance(arguments, list) or not arguments or any(not isinstance(arg, str) or "\0" in arg for arg in arguments):
        raise ValueError("hidden command must be an explicit argument list")
    if "WORKSPACE" not in arguments:
        raise ValueError("hidden command must use WORKSPACE")
    result = []
    for argument in arguments:
        if argument == "WORKSPACE":
            result.append(str(pristine))
        elif argument == "TARGET_DIR":
            result.append(str(directory / ".targethidden"))
        elif argument.startswith("evaluation/"):
            path = (REPOSITORY_ROOT / argument).resolve(strict=True)
            if not path.is_relative_to(REPOSITORY_ROOT / "evaluation/confirmation/tasks"):
                raise ValueError("hidden asset escapes confirmation task assets")
            result.append(str(path))
        else:
            result.append(argument)
    # Existing Rust task runners accept this flag; a manifest can instead place
    # TARGET_DIR explicitly when a different runner syntax is required.
    if task["id"].startswith("C-R") and "TARGET_DIR" not in arguments:
        result.extend(["--target-dir", str(directory / ".targethidden")])
    return result


def evaluate_task(task: dict, base: Path, workspace: Path, output_dir: Path) -> dict:
    base, workspace, output_dir = Path(base).resolve(), Path(workspace).resolve(), Path(output_dir).resolve()
    if base == workspace or base in workspace.parents or workspace in base.parents:
        raise ValueError("base and candidate must be separate source roots")
    if any(output_dir == source or source in output_dir.parents or output_dir in source.parents for source in (base, workspace)):
        raise ValueError("evaluation output must be separate from both source roots")
    output_dir.mkdir(mode=0o700, parents=False, exist_ok=False)
    result = {"schema": 1, "task_id": task.get("id"), "correct_repair": False, "production_changed": False,
              "added_test_coverage": False, "restore_errors": [], "checks": {}, "infrastructure_errors": [],
              "input_tree_hashes": {}, "frozen_workspace_unchanged": False, "base_unchanged": False}
    try:
        policy = _policy(task)
        before, after = _files(base), _files(workspace)
        result["input_tree_hashes"] = {"base": _tree_hash(before), "candidate": _tree_hash(after)}
        _check_disk(output_dir, policy[4], "before-source-copies")
        patch = _patch(before, after)
        (output_dir / "candidate.patch").write_bytes(patch)
        (output_dir / "candidate.patch").chmod(0o600)
        result["patch"] = {"bytes": len(patch), "sha256": sha256(patch), "changed_paths": sorted(name for name in before | after if before.get(name) != after.get(name))}
        pristine, candidate = output_dir / "pristine", output_dir / "candidate"
        _copy_source(base, pristine)
        _copy_source(workspace, candidate)
        _install_dependencies(base, pristine)
        _install_dependencies(base, candidate)
        errors, changed, tests_changed = _overlay(before, after, pristine, policy)
        result.update(restore_errors=errors, production_changed=changed, added_test_coverage=tests_changed)
        command = task.get("baseline_command")
        if not isinstance(command, list) or not command or any(not isinstance(arg, str) or "\0" in arg for arg in command):
            raise ValueError("baseline command must be an explicit argument list")
        kwargs = {"timeout": policy[2], "environment_unset": policy[3], "minimum_free_bytes": policy[4]}
        result["checks"]["candidate_baseline"] = _run(command, candidate, output_dir / "candidate-baseline", candidate / ".targetbaseline", **kwargs)
        if not errors:
            result["checks"]["pristine_baseline"] = _run(command, pristine, output_dir / "pristine-baseline", pristine / ".targetbaseline", **kwargs)
            result["checks"]["hidden"] = _run(_hidden_command(task, pristine, output_dir), pristine,
                                                output_dir / "hidden", output_dir / ".targethidden", **kwargs)
        for check in result["checks"].values():
            if check["target_cleanup"]["error_type"]:
                result["infrastructure_errors"].append({"type": "TargetCleanupFailure", "message": "Disposable compiler target cleanup failed"})
        result["correct_repair"] = changed and not errors and not result["infrastructure_errors"] and all(result["checks"].get(name, {}).get("passed", False) for name in ("candidate_baseline", "pristine_baseline", "hidden"))
    except (OSError, ValueError, KeyError, subprocess.SubprocessError) as error:
        result["infrastructure_errors"].append({"type": type(error).__name__, "message": str(error).replace(str(output_dir), "EVALUATION").replace(str(base), "BASE").replace(str(workspace), "WORKSPACE").replace(str(REPOSITORY_ROOT), "PROJECT")})
        result["correct_repair"] = False
    finally:
        for key, source, field in (("candidate", workspace, "frozen_workspace_unchanged"), ("base", base, "base_unchanged")):
            expected = result["input_tree_hashes"].get(key)
            if expected is not None:
                try:
                    result[field] = _tree_hash(_files(source)) == expected
                except (OSError, ValueError):
                    result[field] = False
                if not result[field]:
                    result["correct_repair"] = False
                    result["infrastructure_errors"].append({"type": "InputMutation", "message": "Frozen " + key + " source changed during evaluation"})
        path = output_dir / "evaluation.json"
        path.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
        path.chmod(0o600)
    return result
