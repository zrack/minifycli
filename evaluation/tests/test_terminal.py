"""Protocol, subprocess and pinned native recovery checks; no agent calls."""
import base64
import importlib.util
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch


PROJECT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location("debugging_terminal", PROJECT / "evaluation/debugging/terminal.py")
terminal = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(terminal)


class TerminalFixture:
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.workspace = self.root / "workspace"
        self.workspace.mkdir()
        self.bin = self.root / "bin"
        self.bin.mkdir()
        self.session_count = 0
        self.env = {"PATH": str(self.bin) + os.pathsep + os.environ.get("PATH", os.defpath),
                    "HOME": os.environ.get("HOME", str(self.root)), "OPENAI_API_KEY": "must-not-reach-child",
                    "GITHUB_TOKEN": "also-secret", "NODE_OPTIONS": "--require=untrusted",
                    "RTK_RECALL": "0", "LEDGER_DASHBOARD_DIR": "/private/oracle"}
        self.helper("node", "import os, sys\nos.write(1, b'out\\r\\nlast')\nos.write(2, b'err\\xff')\nsys.exit(17)\n")
        (self.workspace / "task.mjs").write_text("// Stub receives this literal argument.\n")

    def tearDown(self):
        self.temporary.cleanup()

    def helper(self, name, body):
        path = self.bin / name
        path.write_text("#!" + sys.executable + "\n" + body)
        path.chmod(0o700)
        return path

    def session(self, mode="raw", **options):
        self.session_count += 1
        return terminal.TerminalSession(self.workspace, self.root / f"artifacts-{self.session_count}",
                                        mode, env=self.env, **options)


class TerminalTests(TerminalFixture, unittest.TestCase):
    def test_exact_separate_streams_nonzero_status_and_private_capture(self):
        session = self.session()
        result = session.dispatch({"action": "run", "argv": ["node", "task.mjs"]})
        self.assertTrue(result["ok"])
        self.assertEqual(result["returncode"], 17)
        self.assertTrue(result["capture_complete"])
        self.assertEqual(result["stdout"]["text"], "out\r\nlast")
        self.assertEqual(base64.b64decode(result["stderr"]["base64"]), b"err\xff")
        self.assertEqual(result["stderr"]["encoding"], "base64")
        self.assertGreaterEqual(result["wall_seconds"], result["time_to_first_output_seconds"])
        self.assertEqual((session.artifact_root / result["artifact_id"] / "stdout").read_bytes(), b"out\r\nlast")
        self.assertEqual((session.artifact_root.stat().st_mode & 0o777), 0o700)
        self.assertEqual(((session.artifact_root / result["artifact_id"] / "stdout").stat().st_mode & 0o777), 0o600)

    def test_environment_is_allowlisted_and_recovery_enabled_without_home_override(self):
        session = self.session()
        for name in ("OPENAI_API_KEY", "GITHUB_TOKEN", "NODE_OPTIONS", "LEDGER_DASHBOARD_DIR"):
            self.assertNotIn(name, session.env)
        self.assertEqual(session.env["HOME"], self.env["HOME"])
        for name in ("RTK_RECALL", "RTK_TEE", "RTK_TELEMETRY_DISABLED"):
            self.assertEqual(session.env[name], "1")
        for name in ("RTK_DB_PATH", "RTK_RECALL_DB", "RTK_TEE_DIR"):
            self.assertTrue(Path(session.env[name]).is_relative_to(session.artifact_root))
        self.assertEqual(session.env["npm_config_offline"], "true")
        self.assertEqual(session.env["CARGO_NET_OFFLINE"], "true")
        self.helper("node", "import os,sys,json\nprint(json.dumps(dict(os.environ)))\n")
        result = session.dispatch({"action": "run", "argv": ["node", "task.mjs"]})
        actual = json.loads(result["stdout"]["text"])
        self.assertNotIn("OPENAI_API_KEY", actual)
        self.assertEqual(actual["RTK_RECALL"], "1")

    def test_recovery_is_counted_and_windows_preserve_bytes(self):
        session = self.session()
        result = session.dispatch({"action": "run", "argv": ["node", "task.mjs"]})
        recovered = session.dispatch({"action": "recover", "artifact_id": result["artifact_id"],
                                      "source": "original", "from_line": 2, "lines": 1})
        self.assertEqual(recovered["content"]["text"], "last")
        self.assertEqual(recovered["total_lines"], 2)
        self.assertEqual(recovered["recovery_requests"], 1)
        bad = session.dispatch({"action": "recover", "artifact_id": "../private/oracle"})
        self.assertFalse(bad["ok"])
        self.assertEqual(bad["recovery_requests"], 2)
        events = [json.loads(line) for line in (session.artifact_root / "events.jsonl").read_text().splitlines()]
        self.assertEqual(len(events), 3)
        self.assertEqual(events[-1]["recovery_requests"], 2)

    def test_lf_windows_preserve_cr_vertical_tabs_and_final_newline(self):
        raw = b"a\rb\x0bc\r\nd\n"
        selected, metadata = terminal.window(raw, 1, 1)
        self.assertEqual(selected, b"a\rb\x0bc\r\n")
        self.assertEqual(metadata["total_lines"], 2)
        self.assertEqual(terminal.window(b"", 1)[1]["total_lines"], 0)
        self.assertEqual(terminal.window(raw, 3)[0], b"")

    def test_read_path_and_cwd_are_confined_including_symlinks(self):
        outside = self.root / "oracle"
        outside.write_text("not visible")
        (self.workspace / "escape").symlink_to(outside)
        session = self.session()
        for name in ("../oracle", str(outside), "escape"):
            self.assertFalse(session.dispatch({"action": "read", "path": name})["ok"])
        result = session.dispatch({"action": "run", "argv": ["node", "task.mjs"], "cwd": ".."})
        self.assertFalse(result["ok"])
        (self.workspace / "normal.txt").write_bytes(b"a\r\nb\n")
        result = session.dispatch({"action": "read", "path": "normal.txt", "from_line": 2, "lines": 1})
        self.assertEqual(result["content"]["text"], "b\n")
        self.assertTrue(result["selection_explicit"])

    def test_network_shell_and_external_path_commands_are_rejected_before_launch(self):
        session = self.session()
        bad = [["sh", "-c", "anything"], ["curl", "https://example.com"], ["git", "fetch"],
               ["git", "diff", "--no-index", "/private/oracle", "."], ["git", "show", "--output=../oracle"],
               ["npm", "install"], ["npm", "test", "--prefix", "../oracle"], ["cargo", "install", "x"],
               ["cargo", "test", "--config", "anything"], ["cargo", "test", "--manifest-path=../Cargo.toml"],
               ["node", "../oracle"], ["node", "--eval", "anything"], ["node", "--test-reporter=/outside/module"],
               ["rg", "pattern", "../oracle"], ["rg", "--pre", "anything", "pattern"],
               ["rg", "--follow", "pattern", "."], ["rg", "-nL", "pattern", "."],
               ["rg", "--ignore-file=/private/oracle", "pattern", "."],
               ["rg", "-f", "../oracle", "."], ["find", ".", "-exec", "anything", ";"],
               ["ls", "../oracle"], [str(self.bin / "node"), "task.mjs"]]
        for argv in bad:
            with self.subTest(argv=argv):
                result = session.dispatch({"action": "run", "argv": argv})
                self.assertFalse(result["ok"])
        self.assertEqual(list(session.artifact_root.glob("action-*")), [])

    def test_supported_argv_is_literal_and_pattern_is_not_misread_as_path(self):
        for argv in (["git", "diff", "--no-ext-diff", "--no-color", "HEAD~1", "HEAD", "--", "src"],
                     ["rg", "-n", "/a/b", "src"], ["rg", "--files", "src"],
                     ["node", "--test", "--test-name-pattern", "a/b", "task.mjs"],
                     ["npm", "test", "--", "--runInBand"], ["cargo", "test", "--offline", "--", "--nocapture"]):
            self.assertEqual(terminal.validate_command(argv, self.workspace, self.workspace), argv)

    def test_timeout_and_output_limit_are_explicit_incomplete_captures(self):
        self.helper("node", "import os,time\nos.write(1,b'before\\n')\ntime.sleep(5)\n")
        session = self.session()
        started = time.monotonic()
        result = session.dispatch({"action": "run", "argv": ["node", "task.mjs"], "timeout_seconds": 1.0})
        self.assertLess(time.monotonic() - started, 3)
        self.assertTrue(result["timed_out"])
        self.assertFalse(result["capture_complete"])
        self.assertEqual(result["stdout"]["text"], "before\n")
        self.helper("node", "import os,time\nos.write(1,b'x'*4096)\ntime.sleep(5)\n")
        limited = self.session(max_output_bytes=100)
        result = limited.dispatch({"action": "run", "argv": ["node", "task.mjs"]})
        self.assertTrue(result["output_limit"])
        self.assertFalse(result["capture_complete"])
        self.assertEqual(result["stdout"]["bytes"], 4096)  # Cap crossing is retained.

    def test_descendant_holding_eof_is_terminated_as_a_group(self):
        self.helper("node", "import subprocess,sys\nsubprocess.Popen([sys.executable,'-c','import time; time.sleep(8)'])\n")
        result = self.session().dispatch({"action": "run", "argv": ["node", "task.mjs"], "timeout_seconds": 0.1})
        self.assertTrue(result["timed_out"])
        self.assertFalse(result["capture_complete"])
        self.assertLess(result["wall_seconds"], 3)

    def test_signal_status_and_spawn_failure_are_not_success(self):
        self.helper("node", "import os,signal\nos.kill(os.getpid(),signal.SIGTERM)\n")
        result = self.session().dispatch({"action": "run", "argv": ["node", "task.mjs"]})
        self.assertEqual(result["returncode"], -signal.SIGTERM)
        # Declared program but absent from the explicitly supplied PATH.
        self.env["PATH"] = str(self.root / "absent")
        result = self.session().dispatch({"action": "run", "argv": ["node", "task.mjs"]})
        self.assertIsNone(result["returncode"])
        self.assertIsNotNone(result["spawn_error"])
        self.assertFalse(result["capture_complete"])

    def test_request_limits_and_unknown_fields_fail_before_execution(self):
        session = self.session()
        requests = [{"action": "run", "argv": "node task.mjs"},
                    {"action": "run", "argv": ["node", "task.mjs"], "env": {"SECRET": "x"}},
                    {"action": "run", "argv": ["node", "task.mjs"], "timeout_seconds": 91},
                    {"action": "run", "argv": ["node", "task.mjs"], "timeout_seconds": float("nan")},
                    {"action": "recover", "artifact_id": []},
                    {"action": "read", "path": "task.mjs", "lines": False}]
        for request in requests:
            self.assertFalse(session.dispatch(request)["ok"])

    def test_artifacts_must_be_fresh_separate_private_directories(self):
        session = self.session()
        with self.assertRaises(terminal.TerminalError):
            terminal.TerminalSession(self.workspace, session.artifact_root, "raw", env=self.env)
        with self.assertRaises(terminal.TerminalError):
            terminal.TerminalSession(self.workspace, self.workspace / "artifacts", "raw", env=self.env)
        link = self.root / "linked-artifacts"
        link.symlink_to(session.artifact_root)
        with self.assertRaises(terminal.TerminalError):
            terminal.TerminalSession(self.workspace, link, "raw", env=self.env)

    def test_existing_macos_rtk_config_is_only_checked_not_read(self):
        # Binary can be any existing file here; no process is launched.
        with patch.object(terminal.platform, "system", return_value="Darwin"), patch.object(terminal.os.path, "lexists", return_value=True), patch.object(Path, "read_text", side_effect=AssertionError("must not read host config")):
            with self.assertRaisesRegex(terminal.TerminalError, "host RTK config"):
                self.session("rtk", rtk=self.bin / "node")

    def test_native_routes_and_generic_fallback_do_not_invent_filters(self):
        rtk = Path("/pinned/rtk")
        for argv in (["cargo", "test"], ["npm", "test"], ["git", "status", "--short"], ["rg", "-n", "p", "."]):
            self.assertEqual(terminal.rtk_route(argv, rtk), ([str(rtk), *argv], "native"))
        argv = ["node", "task.mjs"]
        self.assertEqual(terminal.rtk_route(argv, rtk), ([str(rtk), "run", "--", *argv], "passthrough"))


class PinnedBinaryTests(TerminalFixture, unittest.TestCase):
    MINI = PROJECT / "target/release/mini"
    RTK = PROJECT / ".tools/rtk-1.1.0/bin/rtk"

    @unittest.skipUnless(MINI.is_file(), "local release Mini not built")
    def test_mini_record_recovery_is_original_child_bytes(self):
        self.helper("cargo", "import os,sys\nos.write(1,b'running 1 test\\ntest hidden_case ... ok\\ntest result: ok. 1 passed; 0 failed\\n')\nos.write(2,b'child stderr\\n')\nsys.exit(17)\n")
        session = self.session("mini", mini=self.MINI)
        result = session.dispatch({"action": "run", "argv": ["cargo", "test"]})
        self.assertEqual(result["returncode"], 17)
        self.assertTrue(result["mini_record_complete"])
        recovered = session.dispatch({"action": "recover", "artifact_id": result["artifact_id"], "source": "original"})
        self.assertIn("test hidden_case ... ok", recovered["content"]["text"])
        err = session.dispatch({"action": "recover", "artifact_id": result["artifact_id"], "source": "original", "stream": "stderr"})
        self.assertEqual(err["content"]["text"], "child stderr\n")

    @unittest.skipUnless(RTK.is_file(), "pinned RTK absent")
    def test_real_rtk_generic_passthrough_preserves_literal_argv_and_status(self):
        self.helper("node", "import sys,json\nprint(json.dumps(sys.argv[1:]))\nsys.exit(17)\n")
        session = self.session("rtk", rtk=self.RTK)
        result = session.dispatch({"action": "run", "argv": ["node", "task.mjs"]})
        self.assertEqual(result["returncode"], 17)
        self.assertEqual(result["route"], "passthrough")
        self.assertEqual(json.loads(result["stdout"]["text"]), ["task.mjs"])
        denied = session.dispatch({"action": "recover", "artifact_id": result["artifact_id"], "source": "original"})
        self.assertFalse(denied["ok"])
        displayed = session.dispatch({"action": "recover", "artifact_id": result["artifact_id"]})
        self.assertEqual(displayed["content"], result["stdout"])

    @unittest.skipUnless(RTK.is_file(), "pinned RTK absent")
    def test_real_rtk_native_recall_enabled_and_countable(self):
        # A synthetic Cargo child verifies integration, not benchmark compression.
        raw = "running 41 tests\n" + ("test fixture ... ok\n" * 40) + "test broken ... FAILED\nfailures:\n    broken\ntest result: FAILED. 40 passed; 1 failed\n"
        self.helper("cargo", "import os,sys\nos.write(1," + repr(raw.encode()) + ")\nsys.exit(17)\n")
        session = self.session("rtk", rtk=self.RTK)
        result = session.dispatch({"action": "run", "argv": ["cargo", "test"]})
        self.assertEqual(result["returncode"], 17)
        self.assertEqual(result["route"], "native")
        self.assertTrue(result["rtk_recall_hashes"], result["stdout"])
        self.assertTrue((session.artifact_root / "rtk-data/recall.db").is_file())
        recovered = session.dispatch({"action": "recover", "recall_hash": result["rtk_recall_hashes"][0], "full": True})
        self.assertTrue(recovered["ok"])
        self.assertEqual(recovered["returncode"], 0)
        self.assertEqual(recovered["stdout"]["text"], raw)
        self.assertEqual(recovered["recovery_requests"], 1)
        self.assertFalse(session.dispatch({"action": "recover", "recall_hash": "0000000000000000"})["ok"])

    @unittest.skipUnless(RTK.is_file(), "pinned RTK absent")
    def test_real_rtk_npm_keeps_its_actual_recovery_limitations(self):
        raw = "> fixture@1.0.0 test\n" * 40 + "FAIL fixture diagnostic\n"
        self.helper("npm", "import os,sys\nos.write(1," + repr(raw.encode()) + ")\nsys.exit(17)\n")
        session = self.session("rtk", rtk=self.RTK)
        result = session.dispatch({"action": "run", "argv": ["npm", "test"]})
        self.assertEqual(result["returncode"], 17)
        self.assertEqual(result["route"], "native")
        self.assertEqual(result["rtk_recall_hashes"], [])
        self.assertFalse((session.artifact_root / "rtk-data/recall.db").exists())

    @unittest.skipUnless(RTK.is_file(), "pinned RTK absent")
    def test_real_rtk_declared_cargo_npm_rg_ls_routes_accept_argv(self):
        self.helper("cargo", "import sys\nsys.exit(17)\n")
        self.helper("npm", "import sys\nsys.exit(17)\n")
        self.helper("rg", "import sys\nprint('task.mjs:1:fixture')\nsys.exit(1)\n")
        session = self.session("rtk", rtk=self.RTK)
        for argv, code, route in [(["cargo", c, "--offline"], 17, "native") for c in ("test", "check", "build", "clippy")] + [
                (["cargo", "fmt", "--", "--check"], 17, "passthrough"),
                (["npm", "test", "--", "--runInBand"], 17, "native"),
                (["npm", "run", "missing"], 17, "native"),
                (["rg", "-n", "fixture", "task.mjs"], 1, "native"),
                (["ls", "-la"], 0, "native")]:
            with self.subTest(argv=argv):
                result = session.dispatch({"action": "run", "argv": argv})
                self.assertTrue(result["ok"], result)
                self.assertEqual(result["returncode"], code, result)
                self.assertEqual(result["route"], route)

    @unittest.skipUnless(RTK.is_file(), "pinned RTK absent")
    def test_real_rtk_git_routes_on_normal_disposable_repository(self):
        env = {**os.environ, "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": "/dev/null"}
        def git(*args):
            subprocess.run(["git", "-c", "core.hooksPath=/dev/null", *args], cwd=self.workspace,
                           env=env, check=True, capture_output=True)
        git("init", "-q")
        git("config", "user.name", "Adapter Fixture")
        git("config", "user.email", "fixture@example.invalid")
        git("add", "task.mjs")
        git("commit", "-qm", "first fixture")
        (self.workspace / "task.mjs").write_text("// changed fixture\n")
        git("add", "task.mjs")
        git("commit", "-qm", "second fixture")
        session = self.session("rtk", rtk=self.RTK)
        for argv, route in [(["git", "status", "--short"], "native"),
                            (["git", "diff", "--no-ext-diff", "--no-color", "HEAD~1", "HEAD", "--", "task.mjs"], "native"),
                            (["git", "log", "-1"], "native"), (["git", "show", "HEAD:task.mjs"], "native"),
                            (["git", "rev-parse", "HEAD"], "passthrough"),
                            (["git", "ls-files"], "passthrough"), (["git", "grep", "fixture"], "passthrough")]:
            with self.subTest(argv=argv):
                result = session.dispatch({"action": "run", "argv": argv})
                self.assertTrue(result["ok"], result)
                self.assertEqual(result["returncode"], 0, result)
                self.assertEqual(result["route"], route)


if __name__ == "__main__":
    unittest.main()
