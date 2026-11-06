import importlib.util
import json
from pathlib import Path
import tempfile
import unittest


HERE = Path(__file__).resolve().parents[1]


def module(name):
    spec = importlib.util.spec_from_file_location(name, HERE / (name + ".py"))
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


server = module("mcp_server")
runner = module("run_sprint")


class HarnessTests(unittest.TestCase):
    def test_solver_view_retains_text_without_arm_bookkeeping(self):
        raw = {"ok": True, "schema_version": 1, "mode": "rtk", "launched_argv": ["/private/tool"], "returncode": 17, "artifact_id": "action-1", "argv": ["cargo", "test"], "stdout": {"encoding": "utf-8", "text": " exact\n", "sha256": "private"}, "rtk_recall_hashes": ["1234567890abcdef"]}
        visible = server.Server.visible(raw)
        self.assertEqual(visible["stdout"], " exact\n")
        self.assertEqual(visible["exit_code"], 17)
        self.assertEqual(visible["recall_hashes"], ["1234567890abcdef"])
        self.assertNotIn("mode", visible)
        self.assertNotIn("launched_argv", visible)

    def test_recovery_schema_matches_dispatch(self):
        schema = next(tool for tool in server.TOOLS if tool["name"] == "recover_output")["inputSchema"]["properties"]
        self.assertEqual(schema["stream"]["enum"], ["stdout", "stderr"])
        self.assertEqual(schema["source"]["enum"], ["displayed", "original"])
        self.assertIn("grep", schema)
        self.assertIn("list", schema)

    def test_file_boundary_rejects_parent_git_and_symlink_escape(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "workspace"
            root.mkdir()
            (root / "escape").symlink_to(root.parent, target_is_directory=True)
            for name in ("../gold", ".git/config", "escape/gold"):
                with self.assertRaises(ValueError):
                    server.bounded_path(root, name)

    def test_replace_requires_unique_match_and_action_budget(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary) / "workspace"
            root.mkdir()
            (root / "a").write_text("one one")
            instance = server.Server({"workspace": str(root), "artifact_root": str(Path(temporary) / "artifacts"), "max_actions": 2})
            with self.assertRaises(ValueError):
                instance.call("replace_text", {"path": "a", "old": "one", "new": "two"})
            instance.call("replace_text", {"path": "a", "old": "one one", "new": "two"})
            self.assertEqual((root / "a").read_text(), "two")
            self.assertIn("error", instance.call("write_file", {"path": "a", "content": "wrong"}))
            self.assertEqual((root / "a").read_text(), "two")

    def test_final_usage_is_not_summed_or_reasoning_added(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "events"
            path.write_text('\n'.join(json.dumps(item) for item in [
                {"type": "item.completed", "item": {"type": "agent_message", "usage": {"input_tokens": 999}}},
                {"type": "turn.completed", "usage": {"input_tokens": 100, "cached_input_tokens": 70, "output_tokens": 20, "reasoning_output_tokens": 15}},
            ]) + '\n{"type":')
            summary = runner.event_summary(path)
            self.assertEqual(summary["usage"]["input_tokens"], 100)
            self.assertEqual(summary["malformed_event_lines"], 1)

    def test_native_bypass_visible_even_with_completed_turn(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "events"
            path.write_text(json.dumps({"type": "item.completed", "item": {"type": "command_execution"}}))
            self.assertIn("native tool bypass: command_execution", runner.event_summary(path)["protocol_deviations"])

    def test_dependency_links_remain_local_and_executable(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source = root / "source"
            (source / "node_modules/.bin").mkdir(parents=True)
            (source / "node_modules/tool").mkdir()
            (source / "node_modules/tool/cli.js").write_text("original")
            (source / "node_modules/.bin/tool").symlink_to("../tool/cli.js")
            destination = root / "copy"
            runner.copy_snapshot(source, destination)
            link = destination / "node_modules/.bin/tool"
            self.assertTrue(link.is_symlink())
            self.assertTrue(link.resolve().is_relative_to(destination.resolve()))
            self.assertEqual(runner.dependency_tree_hash(source), runner.dependency_tree_hash(destination))


if __name__ == "__main__":
    unittest.main()
