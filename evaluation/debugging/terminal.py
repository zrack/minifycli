"""Terminal boundary for local debugging trials; no agent or API dependency.

TerminalSession.dispatch accepts JSON dictionaries with run/read/recover actions.
Only literal argv is executed. The caller must provision an isolated workspace;
this module checks paths and removes inherited credentials/configuration, but is
not an operating-system sandbox for repository code executed by tests.

Every returned stream is the exact captured bytes, represented as UTF-8 text or
base64 (never replacement decoding). Native RTK output stays native: its recall
store is enabled, and unsupported command forms use official ``rtk run``. RTK
artifact recovery returns wrapper output, not imaginary original child streams.
"""
from __future__ import annotations

import base64
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import re
import selectors
import signal
import subprocess
import time


SCHEMA_VERSION = 1
ALLOWED_PROGRAMS = frozenset({"cargo", "npm", "node", "git", "rg", "ls", "find", "cat", "head", "tail", "wc", "pwd"})
BASE_ENV_KEYS = frozenset({"PATH", "HOME", "CARGO_HOME", "RUSTUP_HOME", "SystemRoot", "SYSTEMROOT"})
GIT_COMMANDS = frozenset({"status", "diff", "log", "show", "rev-parse", "ls-files", "grep"})
CARGO_COMMANDS = frozenset({"test", "check", "build", "clippy", "fmt"})
RTK_GIT_FILTERS = frozenset({"status", "diff", "log", "show"})
RTK_CARGO_FILTERS = frozenset({"test", "check", "build", "clippy"})
RECALL_HASH = re.compile(r"\brtk recall ([0-9a-f]{16})\b")


class TerminalError(ValueError):
    """Invalid or unsupported terminal request; no process was launched."""


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def stream_value(data: bytes) -> dict:
    value = {"bytes": len(data), "sha256": digest(data)}
    try:
        value.update(encoding="utf-8", text=data.decode("utf-8", errors="strict"))
    except UnicodeDecodeError:
        value.update(encoding="base64", base64=base64.b64encode(data).decode("ascii"))
    return value


def inside(root: Path, name: str, *, directory: bool = False) -> Path:
    if not isinstance(name, str) or not name or "\0" in name or Path(name).is_absolute():
        raise TerminalError("paths must be nonempty workspace-relative strings")
    path = (root / name).resolve()
    if not path.is_relative_to(root):
        raise TerminalError("path escapes the workspace")
    if directory and not path.is_dir():
        raise TerminalError("working directory does not exist")
    return path


def positive_int(value: object, name: str) -> int:
    if type(value) is not int or value < 1:
        raise TerminalError(f"{name} must be a positive integer")
    return value


def window(data: bytes, from_line: int = 1, lines: int | None = None) -> tuple[bytes, dict]:
    """Explicit source-line window, retaining CR/LF and final unterminated bytes."""
    positive_int(from_line, "from_line")
    if lines is not None:
        positive_int(lines, "lines")
    # LF is the terminal line delimiter. bytes.splitlines would also split on CR.
    split = data.split(b"\n")
    parts = [part + b"\n" for part in split[:-1]] + ([split[-1]] if split[-1] else [])
    start = from_line - 1
    end = None if lines is None else start + lines
    selected = b"".join(parts[start:end])
    return selected, {"from_line": from_line, "requested_lines": lines,
                      "total_lines": len(parts), "selection_explicit": from_line != 1 or lines is not None,
                      "source_bytes": len(data), "source_sha256": digest(data)}


def _path_argument(cwd: Path, workspace: Path, arg: str) -> None:
    if "\0" in arg or "\n" in arg or "\r" in arg:
        raise TerminalError("control characters are not allowed in path arguments")
    # Git pathspec magic can disable ordinary path interpretation; no need for it
    # in these debugging tasks. Commit:path itself is handled separately below.
    if arg.startswith(":(") or arg.startswith("~"):
        raise TerminalError("special or home-relative paths are unsupported")
    candidate = Path(arg)
    resolved = candidate.resolve() if candidate.is_absolute() else (cwd / candidate).resolve()
    if not resolved.is_relative_to(workspace):
        raise TerminalError("command path escapes the workspace")


def validate_command(argv: object, cwd: Path, workspace: Path) -> list[str]:
    cwd, workspace = cwd.resolve(), workspace.resolve()
    if not isinstance(argv, list) or not argv or any(not isinstance(a, str) or "\0" in a for a in argv):
        raise TerminalError("argv must be a nonempty list of strings without NUL")
    if len(argv) > 256 or sum(len(a) for a in argv) > 65536:
        raise TerminalError("argv exceeds the declared request limit")
    program, *args = argv
    if program not in ALLOWED_PROGRAMS:
        raise TerminalError("program is outside the declared local tool allowlist")
    if program == "pwd":
        if args:
            raise TerminalError("pwd accepts no arguments here")
    elif program == "git":
        if not args or args[0] not in GIT_COMMANDS:
            raise TerminalError("only local, read-only Git subcommands are permitted")
        forbidden = ("--git-dir", "--work-tree", "--exec-path", "--output", "--ext-diff", "--no-index", "--textconv", "--open-files-in-pager")
        for arg in args[1:]:
            if arg == "-c" or arg == "-C" or arg.startswith(forbidden):
                raise TerminalError("Git path/configuration or external-command overrides are unsupported")
            if arg.startswith("/") or ".." in Path(arg).parts:
                _path_argument(cwd, workspace, arg)
        if "--" in args:
            for arg in args[args.index("--") + 1:]:
                _path_argument(cwd, workspace, arg)
    elif program == "cargo":
        if not args or args[0] not in CARGO_COMMANDS:
            raise TerminalError("only offline Cargo test/check/build/clippy/fmt are permitted")
        for i, arg in enumerate(args):
            if arg in {"--config", "--target-dir", "--artifact-dir", "--out-dir", "--lockfile-path"} or any(arg.startswith(flag + "=") for flag in ("--config", "--target-dir", "--artifact-dir", "--out-dir", "--lockfile-path")):
                raise TerminalError("Cargo configuration/output overrides are unsupported")
            if arg == "--manifest-path":
                if i + 1 >= len(args):
                    raise TerminalError("missing Cargo manifest path")
                _path_argument(cwd, workspace, args[i + 1])
            elif arg.startswith("--manifest-path="):
                _path_argument(cwd, workspace, arg.split("=", 1)[1])
    elif program == "npm":
        if not args or args[0] not in {"test", "t", "run", "run-script"}:
            raise TerminalError("npm is limited to existing local test/run scripts")
        if args[0] in {"run", "run-script"} and (len(args) < 2 or args[1].startswith("-")):
            raise TerminalError("npm run requires an explicit local script name")
        for arg in args[1:]:
            if arg.startswith(("--prefix", "--userconfig", "--globalconfig", "--cache", "--registry", "--workspace", "--script-shell")) or arg in {"-g", "--global", "-w"}:
                raise TerminalError("npm location, network and shell overrides are unsupported")
    elif program == "node":
        options = {"--test", "--test-only", "--test-force-exit", "--check", "-c", "--experimental-test-coverage", "--no-warnings"}
        with_value = {"--test-name-pattern", "--test-skip-pattern", "--test-reporter", "--test-concurrency", "--test-timeout"}
        i = 0
        while i < len(args):
            arg = args[i]
            if arg in with_value:
                if i + 1 >= len(args):
                    raise TerminalError("missing Node option value")
                if arg == "--test-reporter" and args[i + 1] not in {"spec", "dot", "tap", "junit", "lcov"}:
                    raise TerminalError("custom Node test-reporter modules are unsupported")
                i += 2
                continue
            if arg.startswith("-"):
                if arg not in options and not any(arg.startswith(key + "=") for key in with_value):
                    raise TerminalError("Node eval, preload and undeclared options are unsupported")
                if arg.startswith("--test-reporter=") and arg.split("=", 1)[1] not in {"spec", "dot", "tap", "junit", "lcov"}:
                    raise TerminalError("custom Node test-reporter modules are unsupported")
            else:
                _path_argument(cwd, workspace, arg)
            i += 1
    elif program == "rg":
        # Ban command execution/config/path escapes, while leaving regex syntax
        # untouched. The first positional operand is the pattern unless -e/-f
        # supplies it, or --files switches to file enumeration.
        if any(a in {"--pre", "--follow", "-L", "--ignore-file"} or a.startswith(("--pre=", "--hostname-bin", "--ignore-file=")) or (a.startswith("-") and not a.startswith("--") and "L" in a[1:]) for a in args):
            raise TerminalError("ripgrep preprocessors, symlink following and external ignore files are unsupported")
        value_flags = {"-e", "--regexp", "-f", "--file", "-g", "--glob", "--iglob", "-t", "--type", "-T", "--type-not", "-A", "-B", "-C", "--after-context", "--before-context", "--context", "-m", "--max-count", "--max-columns", "--max-depth", "--threads", "--sort", "--sortr"}
        has_pattern = "--files" in args or any(a in {"-e", "--regexp", "-f", "--file"} or a.startswith(("--regexp=", "--file=")) for a in args)
        i = 0
        while i < len(args):
            arg = args[i]
            if arg in value_flags:
                if i + 1 >= len(args):
                    raise TerminalError("missing ripgrep option value")
                if arg in {"-f", "--file"}:
                    _path_argument(cwd, workspace, args[i + 1])
                i += 2
                continue
            if arg.startswith("--file="):
                _path_argument(cwd, workspace, arg.split("=", 1)[1])
            elif not arg.startswith("-"):
                if not has_pattern:
                    has_pattern = True
                else:
                    _path_argument(cwd, workspace, arg)
            i += 1
    elif program == "find":
        # No -exec/-delete/-fprint and no symlink-follow mode.
        value_flags = {"-name", "-iname", "-path", "-ipath", "-type", "-maxdepth", "-mindepth"}
        i = 0
        while i < len(args):
            arg = args[i]
            if arg in value_flags:
                if i + 1 >= len(args):
                    raise TerminalError("missing find predicate value")
                i += 2
                continue
            if arg.startswith("-") and arg not in {"-print", "-print0", "-and", "-or", "-not"}:
                raise TerminalError("find permits enumeration predicates only")
            if not arg.startswith("-") and arg not in {"!", "(", ")"}:
                _path_argument(cwd, workspace, arg)
            i += 1
    else:
        skip = False
        for arg in args:
            if skip:
                positive_int(int(arg) if arg.isdigit() else None, "line count")
                skip = False
            elif program in {"head", "tail"} and arg == "-n":
                skip = True
            elif arg.startswith("-"):
                if arg.startswith("--") and arg not in {"--", "--help", "--version"}:
                    raise TerminalError("undeclared diagnostic option")
            else:
                _path_argument(cwd, workspace, arg)
        if skip:
            raise TerminalError("missing line count")
    return list(argv)


def rtk_route(argv: list[str], rtk: Path) -> tuple[list[str], str]:
    """Only syntax verified in the pinned 1.1.0 CLI gets a native filter."""
    native = argv[0] in {"rg", "ls", "npm"} or (argv[0] == "git" and len(argv) > 1 and argv[1] in RTK_GIT_FILTERS) or (argv[0] == "cargo" and len(argv) > 1 and argv[1] in RTK_CARGO_FILTERS)
    return ([str(rtk), *argv], "native") if native else ([str(rtk), "run", "--", *argv], "passthrough")


def _kill_group(process: subprocess.Popen, sig: int) -> None:
    try:
        os.killpg(process.pid, sig)
    except ProcessLookupError:
        pass


def capture(argv: list[str], cwd: Path, env: dict[str, str], directory: Path,
            timeout: float, max_output_bytes: int) -> dict:
    """Spool both pipes concurrently; timeouts include descendants holding EOF."""
    started = time.perf_counter()
    first = None
    termination = None
    timed_out = output_limit = False
    sizes = {"stdout": 0, "stderr": 0}
    selector = selectors.DefaultSelector()
    process = None
    complete = False
    try:
        with (directory / "stdout").open("xb") as out, (directory / "stderr").open("xb") as err:
            out_path, err_path = directory / "stdout", directory / "stderr"
            out_path.chmod(0o600)
            err_path.chmod(0o600)
            try:
                process = subprocess.Popen(argv, cwd=cwd, env=env, stdin=subprocess.DEVNULL,
                                           stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                           start_new_session=True)
            except OSError as error:
                return {"returncode": None, "spawn_error": {"errno": error.errno, "message": str(error)},
                        "wall_seconds": time.perf_counter() - started,
                        "time_to_first_output_seconds": None, "capture_complete": False,
                        "timed_out": False, "output_limit": False}
            selector.register(process.stdout, selectors.EVENT_READ, ("stdout", out))
            selector.register(process.stderr, selectors.EVENT_READ, ("stderr", err))
            while selector.get_map() or process.poll() is None:
                now = time.perf_counter()
                if termination is None and now - started >= timeout:
                    timed_out = True
                    termination = now
                    _kill_group(process, signal.SIGTERM)
                if termination is not None and now - termination >= 0.5:
                    _kill_group(process, signal.SIGKILL)
                    if process.poll() is None:
                        process.kill()
                    if now - termination >= 1.0:
                        break  # Escaped descendants cannot stall the tool forever.
                for key, _ in selector.select(0.02):
                    name, handle = key.data
                    chunk = os.read(key.fileobj.fileno(), 65536)
                    if not chunk:
                        selector.unregister(key.fileobj)
                        key.fileobj.close()
                        continue
                    if first is None:
                        first = time.perf_counter() - started
                    handle.write(chunk)  # Never silently drop the cap-crossing chunk.
                    sizes[name] += len(chunk)
                    if sum(sizes.values()) > max_output_bytes and termination is None:
                        output_limit = True
                        termination = time.perf_counter()
                        _kill_group(process, signal.SIGTERM)
            complete = not selector.get_map() and not (timed_out or output_limit)
            if process.poll() is None:
                _kill_group(process, signal.SIGKILL)
                process.kill()
            status = process.wait(timeout=5)
    finally:
        selector.close()
        if process is not None:
            if process.poll() is None:
                _kill_group(process, signal.SIGKILL)
                process.kill()
                process.wait(timeout=5)
            for pipe in (process.stdout, process.stderr):
                if pipe is not None and not pipe.closed:
                    pipe.close()
    return {"returncode": status, "spawn_error": None,
            "wall_seconds": time.perf_counter() - started, "time_to_first_output_seconds": first,
            "capture_complete": complete, "timed_out": timed_out, "output_limit": output_limit}


class TerminalSession:
    """One task/variant, one fresh private artifact directory and recall store.

    run: {action, argv, cwd='.', timeout_seconds=60}
    read: {action, path, from_line=1, lines=null}
    recover: {action, artifact_id, stream='stdout', source='displayed'|'original',
              from_line=1, lines=null}
    RTK recover: {action, recall_hash, full=false, from_line?, lines?, grep?},
                 or {action:'recover', list:true}.

    No shell strings, per-request environment overrides, implicit pagination or
    implicit reruns. A server may paginate explicitly and count delivery costs.
    Calls must be serialized by that server.
    """

    def __init__(self, workspace: Path, artifact_root: Path, mode: str,
                 mini: Path | None = None, rtk: Path | None = None,
                 env: dict[str, str] | None = None, *, max_output_bytes: int = 64 * 1024 * 1024,
                 max_timeout_seconds: float = 90.0):
        self.workspace = Path(workspace).resolve(strict=True)
        if not self.workspace.is_dir() or mode not in {"raw", "mini", "rtk"}:
            raise TerminalError("expected an existing workspace directory and raw/mini/rtk mode")
        supplied_root = Path(artifact_root)
        if supplied_root.is_symlink():
            raise TerminalError("artifact root cannot be a symlink")
        self.artifact_root = supplied_root.resolve()
        if self.artifact_root.is_relative_to(self.workspace) or self.workspace.is_relative_to(self.artifact_root):
            raise TerminalError("workspace and private artifacts must be separate directories")
        self.mode = mode
        self.mini = Path(mini).resolve(strict=True) if mini is not None else None
        self.rtk = Path(rtk).resolve(strict=True) if rtk is not None else None
        if (mode == "mini" and self.mini is None) or (mode == "rtk" and self.rtk is None):
            raise TerminalError("selected mode requires its pinned binary path")
        self.max_output_bytes = positive_int(max_output_bytes, "max_output_bytes")
        self.max_timeout_seconds = float(max_timeout_seconds)
        if not math.isfinite(self.max_timeout_seconds) or self.max_timeout_seconds <= 0:
            raise TerminalError("max_timeout_seconds must be finite and positive")
        self._check_rtk_config()
        self.artifact_root.mkdir(mode=0o700, parents=True, exist_ok=True)
        if any(self.artifact_root.iterdir()):
            raise TerminalError("artifact root must be fresh and empty")
        self.artifact_root.chmod(0o700)
        self.env = self._environment(os.environ if env is None else env)
        self.count = self.recovery_requests = 0
        self.artifacts: dict[str, dict] = {}
        self.recall_hashes: set[str] = set()
        self._write_json(self.artifact_root / "session.json", {
            "schema_version": SCHEMA_VERSION, "mode": mode,
            "max_output_bytes": self.max_output_bytes, "max_timeout_seconds": self.max_timeout_seconds,
            "mini_sha256": digest(self.mini.read_bytes()) if self.mini else None,
            "rtk_sha256": digest(self.rtk.read_bytes()) if self.rtk else None,
            "rtk_recovery": "default-sqlite-enabled" if mode == "rtk" else None,
            "environment_keys": sorted(self.env), "is_os_sandbox": False})

    def _check_rtk_config(self) -> None:
        # RTK 1.1.0 has no configuration-path flag. On macOS XDG is ignored.
        # Examine existence only; never read the user's configuration contents.
        if self.mode != "rtk":
            return
        if platform.system() == "Darwin":
            path = Path.home() / "Library/Application Support/rtk/config.toml"
        elif platform.system() == "Windows":
            raise TerminalError("RTK configuration isolation is not implemented on Windows")
        else:
            return  # Linux uses the task-local XDG_CONFIG_HOME below.
        if os.path.lexists(path):
            raise TerminalError("existing host RTK config prevents isolated default configuration")

    def _environment(self, source: dict[str, str]) -> dict[str, str]:
        env = {k: str(v) for k, v in source.items() if k in BASE_ENV_KEYS}
        env.setdefault("PATH", os.defpath)
        # HOME is preserved, never redirected. Credentials/options are excluded.
        data = self.artifact_root / "rtk-data"
        for name in ("rtk-data", "rtk-config", "rtk-cache", "rtk-state", "claude", "npm-cache", "tmp"):
            (self.artifact_root / name).mkdir(mode=0o700)
        for name in ("npm-user.conf", "npm-global.conf"):
            (self.artifact_root / name).write_text("", encoding="utf-8")
            (self.artifact_root / name).chmod(0o600)
        env.update({"CI": "1", "NO_COLOR": "1", "TERM": "dumb", "LANG": "C", "LC_ALL": "C",
                    "TMPDIR": str(self.artifact_root / "tmp"), "TMP": str(self.artifact_root / "tmp"),
                    "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": "/dev/null", "GIT_TERMINAL_PROMPT": "0",
                    "GIT_PAGER": "cat", "PAGER": "cat", "RIPGREP_CONFIG_PATH": "/dev/null",
                    "npm_config_cache": str(self.artifact_root / "npm-cache"), "npm_config_offline": "true",
                    "npm_config_audit": "false", "npm_config_fund": "false", "npm_config_update_notifier": "false",
                    "npm_config_userconfig": str(self.artifact_root / "npm-user.conf"), "npm_config_globalconfig": str(self.artifact_root / "npm-global.conf"),
                    "CARGO_NET_OFFLINE": "true", "CARGO_TARGET_DIR": str(self.workspace / "target"), "RUST_BACKTRACE": "1",
                    "RTK_TELEMETRY_DISABLED": "1", "RTK_SUPPRESS_HOOK_WARNING": "1", "RTK_NO_TOML": "1",
                    "RTK_RECALL": "1", "RTK_TEE": "1", "RTK_DB_PATH": str(data / "tracking.db"),
                    "RTK_RECALL_DB": str(data / "recall.db"), "RTK_TEE_DIR": str(data / "tee"),
                    "CLAUDE_CONFIG_DIR": str(self.artifact_root / "claude"),
                    "XDG_CONFIG_HOME": str(self.artifact_root / "rtk-config"), "XDG_DATA_HOME": str(data),
                    "XDG_CACHE_HOME": str(self.artifact_root / "rtk-cache"), "XDG_STATE_HOME": str(self.artifact_root / "rtk-state")})
        return env

    @staticmethod
    def _write_json(path: Path, value: dict) -> None:
        with path.open("x", encoding="utf-8") as handle:
            path.chmod(0o600)
            json.dump(value, handle, ensure_ascii=True, indent=2, sort_keys=True)
            handle.write("\n")

    def dispatch(self, request: dict) -> dict:
        self.count += 1
        action_id = f"action-{self.count:06d}"
        started = time.perf_counter()
        try:
            if not isinstance(request, dict):
                raise TerminalError("request must be a JSON object")
            action = request.get("action")
            if action == "run":
                result = self._run(request, action_id)
            elif action == "read":
                result = self._read(request)
            elif action == "recover":
                self.recovery_requests += 1
                result = self._recover(request, action_id)
            else:
                raise TerminalError("action must be run, read or recover")
            response = {"ok": True, **result}
        except (TerminalError, FileNotFoundError, IsADirectoryError, PermissionError) as error:
            response = {"ok": False, "error": {"type": type(error).__name__, "message": str(error)}}
        response.update(schema_version=SCHEMA_VERSION, action_id=action_id, mode=self.mode,
                        recovery_requests=self.recovery_requests,
                        action_wall_seconds=time.perf_counter() - started)
        # Audit hashes and metadata only; complete stream bytes live in artifacts.
        receipt = {"action_id": action_id, "request": request,
                   "response_sha256": digest(json.dumps(response, sort_keys=True, ensure_ascii=True).encode()),
                   "ok": response["ok"], "recovery_requests": self.recovery_requests}
        with (self.artifact_root / "events.jsonl").open("a", encoding="utf-8") as handle:
            (self.artifact_root / "events.jsonl").chmod(0o600)
            handle.write(json.dumps(receipt, sort_keys=True, ensure_ascii=True) + "\n")
        return response

    def _keys(self, request: dict, allowed: set[str]) -> None:
        if set(request) - allowed:
            raise TerminalError("request contains undeclared fields")

    def _run(self, request: dict, action_id: str) -> dict:
        self._keys(request, {"action", "argv", "cwd", "timeout_seconds"})
        self._check_rtk_config()
        cwd = inside(self.workspace, request.get("cwd", "."), directory=True)
        argv = validate_command(request.get("argv"), cwd, self.workspace)
        timeout = request.get("timeout_seconds", min(60.0, self.max_timeout_seconds))
        if type(timeout) not in (int, float) or not math.isfinite(timeout) or not 0 < timeout <= self.max_timeout_seconds:
            raise TerminalError("timeout_seconds exceeds the declared finite positive limit")
        directory = self.artifact_root / action_id
        directory.mkdir(mode=0o700)
        route = "raw"
        if self.mode == "mini":
            launched = [str(self.mini), "--record", str(directory / "record"), "--", *argv]
            route = "mini-record"
        elif self.mode == "rtk":
            launched, route = rtk_route(argv, self.rtk)
        else:
            launched = argv
        status = capture(launched, cwd, self.env, directory, float(timeout), self.max_output_bytes)
        streams = {name: (directory / name).read_bytes() for name in ("stdout", "stderr")}
        observed_hashes = sorted({h for data in streams.values() for h in RECALL_HASH.findall(data.decode("utf-8", "ignore"))}) if self.mode == "rtk" else []
        self.recall_hashes.update(observed_hashes)
        original_scope = "original-child-streams" if self.mode in {"raw", "mini"} else "wrapper-output-only"
        record_complete = None
        if self.mode == "mini":
            metadata = directory / "record/metadata.json"
            if metadata.is_file():
                record_complete = json.loads(metadata.read_text()).get("complete") is True
        self.artifacts[action_id] = {"directory": directory, "original_scope": original_scope,
                                     "record_complete": record_complete, "capture_complete": status["capture_complete"]}
        result = {**status, "artifact_id": action_id, "argv": argv, "launched_argv": launched,
                  "cwd": cwd.relative_to(self.workspace).as_posix(), "route": route,
                  "stdout": stream_value(streams["stdout"]), "stderr": stream_value(streams["stderr"]),
                  "original_output_scope": original_scope, "mini_record_complete": record_complete,
                  "rtk_recall_hashes": observed_hashes,
                  "recovery_instructions": "recover with artifact_id and stream; source=original selects raw/Mini child bytes. RTK artifact recovery is wrapper output; use recall_hash for RTK's own stored content."}
        self._write_json(directory / "metadata.json", {k: v for k, v in result.items() if k not in {"stdout", "stderr"}})
        return result

    def _read(self, request: dict) -> dict:
        self._keys(request, {"action", "path", "from_line", "lines"})
        path = inside(self.workspace, request.get("path"))
        if not path.is_file():
            raise TerminalError("read expects an existing regular file")
        data, selection = window(path.read_bytes(), request.get("from_line", 1), request.get("lines"))
        return {"path": path.relative_to(self.workspace).as_posix(), "content": stream_value(data), **selection}

    def _recover(self, request: dict, action_id: str) -> dict:
        if "recall_hash" in request or request.get("list") is True:
            return self._rtk_recall(request, action_id)
        self._keys(request, {"action", "artifact_id", "stream", "source", "from_line", "lines"})
        identifier = request.get("artifact_id")
        if not isinstance(identifier, str) or identifier not in self.artifacts:
            raise TerminalError("artifact_id must name a run from this session")
        artifact = self.artifacts[identifier]
        stream = request.get("stream", "stdout")
        source = request.get("source", "displayed")
        if not isinstance(stream, str) or not isinstance(source, str) or stream not in {"stdout", "stderr"} or source not in {"displayed", "original"}:
            raise TerminalError("unknown stream or recovery source")
        if source == "original" and self.mode == "rtk":
            raise TerminalError("RTK child originals are not captured; use native recall_hash or displayed wrapper artifact")
        path = artifact["directory"] / stream
        if source == "original" and self.mode == "mini":
            path = artifact["directory"] / "record" / (stream + ".raw")
        data, selection = window(path.read_bytes(), request.get("from_line", 1), request.get("lines"))
        return {"artifact_id": identifier, "stream": stream, "source": source,
                "output_scope": artifact["original_scope"] if source == "original" else "displayed-wrapper-stream",
                "capture_complete": artifact["capture_complete"],
                "mini_record_complete": artifact["record_complete"],
                "content": stream_value(data), **selection}

    def _rtk_recall(self, request: dict, action_id: str) -> dict:
        self._keys(request, {"action", "recall_hash", "list", "full", "from_line", "lines", "grep"})
        self._check_rtk_config()
        if self.mode != "rtk":
            raise TerminalError("native recall is available only in RTK mode")
        if request.get("list") is True:
            if set(request) != {"action", "list"}:
                raise TerminalError("recall listing cannot be combined with selection")
            argv = [str(self.rtk), "recall", "--list"]
        else:
            value = request.get("recall_hash")
            if not isinstance(value, str) or value not in self.recall_hashes:
                raise TerminalError("recall_hash must be a complete hash observed in this session's output")
            if type(request.get("full", False)) is not bool:
                raise TerminalError("full must be a boolean")
            if sum((request.get("full", False), "from_line" in request, "lines" in request)) > 1:
                raise TerminalError("RTK full/from_line/lines selections are mutually exclusive")
            argv = [str(self.rtk), "recall", value]
            if request.get("full", False):
                argv.append("--full")
            for field, flag in (("from_line", "--from"), ("lines", "--lines")):
                if field in request:
                    argv.extend([flag, str(positive_int(request[field], field))])
            if "grep" in request:
                if not isinstance(request["grep"], str) or "\0" in request["grep"]:
                    raise TerminalError("grep must be a string without NUL")
                argv.extend(["--grep", request["grep"]])
        directory = self.artifact_root / action_id
        directory.mkdir(mode=0o700)
        status = capture(argv, self.workspace, self.env, directory, min(60.0, self.max_timeout_seconds), self.max_output_bytes)
        if request.get("list") is True:
            listing = (directory / "stdout").read_bytes().decode("utf-8", "ignore")
            self.recall_hashes.update(re.findall(r"(?m)^([0-9a-f]{16})\s", listing))
        result = {**status, "output_scope": "rtk-native-recalled-content", "launched_argv": argv,
                  "stdout": stream_value((directory / "stdout").read_bytes()),
                  "stderr": stream_value((directory / "stderr").read_bytes()),
                  "semantics": "RTK may store combined/formatted/capped text. Default recall returns hidden lines; full requests all stored content. Native warnings and exit status are preserved."}
        self._write_json(directory / "metadata.json", {k: v for k, v in result.items() if k not in {"stdout", "stderr"}})
        return result
