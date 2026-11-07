import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch


ENTRY = Path(__file__).resolve().parents[1] / "confirmation/mcp_server.py"
spec = importlib.util.spec_from_file_location("confirmation_mcp_test", ENTRY)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class FakeTerminal:
    def __init__(self, *args, **kwargs):
        self.env = {"NO_COLOR": "1", "PATH": "/safe", "CARGO_NET_OFFLINE": "true"}


class ConfirmationMCPTests(unittest.TestCase):
    def test_deadline_rejects_new_write_and_records_error(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            workspace = root / "workspace"
            workspace.mkdir()
            config = {"workspace": str(workspace), "artifact_root": str(root / "artifacts"), "mode": "raw", "mini": "mini", "rtk": "rtk", "soft_deadline_epoch": 10}
            with patch.object(module, "TerminalSession", FakeTerminal), patch.object(module.time, "time", return_value=11):
                instance = module.ConfirmationServer(config)
                response = instance.handle({"id": 1, "method": "tools/call", "params": {"name": "write_file", "arguments": {"path": "changed", "content": "wrong"}}})
            self.assertTrue(response["result"]["isError"])
            self.assertFalse((workspace / "changed").exists())
            entry = json.loads((root / "artifacts/tools.jsonl").read_text())
            self.assertEqual(entry["index"], 1)
            self.assertIn("error", entry["visible"])

    def test_declared_color_unset_is_audited_without_exposing_values(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            workspace = root / "workspace"
            workspace.mkdir()
            config = {"workspace": str(workspace), "artifact_root": str(root / "artifacts"), "mode": "rtk", "mini": "mini", "rtk": "rtk", "soft_deadline_epoch": 999, "environment_unset": ["NO_COLOR"]}
            with patch.object(module, "TerminalSession", FakeTerminal):
                instance = module.ConfirmationServer(config)
            self.assertNotIn("NO_COLOR", instance.session.env)
            self.assertEqual(instance.session.env["CARGO_NET_OFFLINE"], "true")
            receipt = json.loads((root / "artifacts/command-environment.json").read_text())
            self.assertFalse(receipt["values_recorded"])
            self.assertNotIn("NO_COLOR", receipt["effective_keys"])


if __name__ == "__main__":
    unittest.main()
