import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch


HERE = Path(__file__).resolve().parents[1] / "confirmation"
spec = importlib.util.spec_from_file_location("confirmation_runner_test", HERE / "run.py")
runner = importlib.util.module_from_spec(spec)
spec.loader.exec_module(runner)


class ConfirmationRunnerTests(unittest.TestCase):
    def test_infrastructure_abort_latches_before_queued_groups_launch(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            trials = [{"id": "trial-001", "task_id": "C-R1", "repetition": 1, "variant": "raw"},
                      {"id": "trial-002", "task_id": "C-R2", "repetition": 1, "variant": "raw"}]
            with patch.object(runner, "verify_frozen"), patch.object(runner, "disk_guard"), patch.object(runner, "run_trial", side_effect=RuntimeError("storage unavailable")) as started:
                with self.assertRaises(RuntimeError):
                    runner.execute(root, {"workers": 1, "trials": trials, "minimum_free_bytes": 1})
            self.assertEqual(started.call_count, 1)
            self.assertFalse((root / "sessions-complete.json").exists())

    def test_actual_builder_has_unique_config_keys(self):
        args = runner.codex_argv({"codex": "codex", "python": "python3", "model": "gpt-6.1-sol", "reasoning_effort": "ultra"}, Path("workspace"), Path("config.json"), Path("state"))
        settings = [args[i+1] for i, value in enumerate(args[:-1]) if value == "-c"]
        keys = [value.split("=", 1)[0] for value in settings]
        self.assertEqual(len(keys), len(set(keys)))
        self.assertTrue(runner.standard_speed_proof(args, "gpt-6.1-sol", "ultra"))
        mcp = next(value.split("=", 1)[1] for value in settings if value.startswith("mcp_servers.sprint.args="))
        self.assertEqual(Path(json.loads(mcp)[0]), HERE / "mcp_server.py")
        check_spec = importlib.util.spec_from_file_location("confirmation_analysis_builder_test", HERE / "analyze.py")
        checker = importlib.util.module_from_spec(check_spec)
        check_spec.loader.exec_module(checker)
        self.assertTrue(checker._argv_proof(args, {"model": "gpt-6.1-sol", "reasoning_effort": "ultra"}))

    def test_balanced_three_repetitions_per_task(self):
        trials, blocks = runner.schedule([{"id": task} for task in runner.TASK_IDS])
        self.assertEqual(len(trials), 54)
        self.assertEqual(len({(t["task_id"], t["repetition"], t["variant"]) for t in trials}), 54)
        for task in runner.TASK_IDS:
            positions = {variant: [] for variant in runner.VARIANTS}
            for repetition in (1, 2, 3):
                triple = [t for t in trials if t["task_id"] == task and t["repetition"] == repetition]
                for index, trial in enumerate(triple):
                    positions[trial["variant"]].append(index)
            self.assertTrue(all(sorted(p) == [0, 1, 2] for p in positions.values()))
        self.assertEqual([len(block) for block in blocks], [6, 6, 6])

    def test_standard_proof_rejects_ambiguous_speed_configuration(self):
        base = ["codex", "exec", "--ignore-user-config", "--disable", "fast_mode", "--disable", "ultrafast_mode",
                "-c", 'model="gpt-6.1-sol"', "-c", 'model_reasoning_effort="ultra"', "-c", 'service_tier="default"', "-"]
        self.assertTrue(runner.standard_speed_proof(base, "gpt-6.1-sol", "ultra"))
        for extra in (["--enable", "fast_mode"], ["-c", 'service_tier="fast"'], ["-c", "features.ultrafast_mode=true"], ["-c", 'model="other"']):
            self.assertFalse(runner.standard_speed_proof(base[:-1] + extra + ["-"], "gpt-6.1-sol", "ultra"))
        self.assertFalse(runner.standard_speed_proof([a for a in base if a != "--ignore-user-config"], "gpt-6.1-sol", "ultra"))

    def test_cleanup_preserves_source_and_refuses_external_symlink(self):
        with tempfile.TemporaryDirectory() as temporary:
            workspace = Path(temporary) / "workspace"
            (workspace / "target").mkdir(parents=True)
            (workspace / "target/output").write_text("compiled")
            (workspace / "source.rs").write_text("source")
            self.assertTrue(runner.cleanup_target(workspace)["removed"])
            self.assertEqual((workspace / "source.rs").read_text(), "source")
            outside = Path(temporary) / "outside"
            outside.mkdir()
            (outside / "evidence").write_text("retain")
            (workspace / "target").symlink_to(outside, target_is_directory=True)
            with self.assertRaises(ValueError):
                runner.cleanup_target(workspace)
            self.assertTrue((outside / "evidence").exists())

    def test_low_disk_stops_before_work_with_receipt(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "capture").write_text("retain")
            with patch.object(runner.shutil, "disk_usage", return_value=type("Usage", (), {"free": 10})()):
                with self.assertRaises(RuntimeError):
                    runner.disk_guard(root, "trial-001", 100)
            receipt = json.loads((root / "aborts/trial-001.json").read_text())
            self.assertEqual(receipt["free_bytes"], 10)
            self.assertEqual((root / "capture").read_text(), "retain")


if __name__ == "__main__":
    unittest.main()
