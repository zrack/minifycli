"""Decision gates and usage arithmetic on synthetic saved receipts only."""
import hashlib
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest


SPEC = importlib.util.spec_from_file_location("debug_analysis", Path(__file__).resolve().parents[1] / "debugging/analyze.py")
analysis = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(analysis)


class AnalysisTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        trials = []
        for task in sorted(analysis.TASK_IDS):
            for rep in (1, 2):
                for variant in analysis.VARIANTS:
                    trials.append({"id": f"trial-{len(trials)+1:03d}", "task_id": task, "repetition": rep, "variant": variant})
        self.plan = {"schema": 1, "repetitions": 2, "model": "gpt-test", "reasoning_effort": "medium",
                     "tasks": [{"id": task} for task in sorted(analysis.TASK_IDS)], "trials": trials}
        self.write(self.root / "plan.json", self.plan)
        self.register()
        for trial in trials:
            directory = self.root / "trials" / trial["id"]
            result = {**trial, "usage": {"input_tokens": 100, "cached_input_tokens": 40, "output_tokens": 20, "reasoning_tokens": 10},
                      "timed_out": False, "process_exit_code": 0, "turn_completed_count": 1, "protocol_deviations": [],
                      "session_errors": [], "wall_seconds": 1.0, "mcp_calls": 0, "candidate_patch_bytes": 99}
            evaluation = {"task_id": trial["task_id"], "correct_repair": True, "infrastructure_errors": [],
                          "frozen_workspace_unchanged": True, "checks": {"pristine_baseline": {"passed": True}, "hidden": {"passed": True}}}
            self.write(directory / "result.json", result)
            self.write(directory / "evaluation.json", evaluation)

    def tearDown(self):
        self.temp.cleanup()

    def write(self, path, value):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value))

    def register(self):
        self.write(self.root / "registration.json", {"plan_sha256": hashlib.sha256((self.root / "plan.json").read_bytes()).hexdigest()})

    def change(self, trial, kind, **changes):
        path = self.root / "trials" / trial["id"] / (kind + ".json")
        value = json.loads(path.read_text())
        value.update(changes)
        self.write(path, value)

    def tokens(self, mini=60, rtk=100, raw=100):
        for trial in self.plan["trials"]:
            amount = {"mini": mini, "rtk": rtk, "raw": raw}[trial["variant"]]
            self.change(trial, "result", usage={"input_tokens": amount, "cached_input_tokens": 0, "output_tokens": 0})

    def outcomes(self, variant, tasks, correct):
        for trial in self.plan["trials"]:
            if trial["variant"] == variant and trial["task_id"] in tasks:
                self.change(trial, "evaluation", correct_repair=correct)

    def test_usage_once_cached_separate_reasoning_not_double_counted_and_tie_stops(self):
        result = analysis.summarize(self.root)
        self.assertEqual(result["decision"], "stop_compressor_expansion")
        self.assertTrue(result["all_planned_observations_valid"])
        usage = result["primary_paired_usage"]["mini"]
        self.assertEqual(usage["total_tokens"], 12 * 120)
        self.assertEqual(usage["cached_input_tokens"], 12 * 40)
        self.assertEqual(usage["reasoning_tokens"], 12 * 10)
        self.assertEqual(usage["uncached_input_plus_output_tokens"], 12 * 80)
        self.assertEqual(result["valid_paired_triples"], 12)

    def test_resource_gate_uses_sums_all_trials_and_both_language_groups(self):
        self.tokens(mini=80)
        result = analysis.summarize(self.root)
        self.assertEqual(result["resource_gate"]["status"], "met")
        self.assertEqual(result["decision"], "continue_bounded_compressor_experiment")
        # An aggregate win concentrated only in JavaScript fails the language gate.
        for trial in self.plan["trials"]:
            if trial["variant"] == "mini":
                value = 100 if trial["task_id"].startswith("R") else 10
                self.change(trial, "result", usage={"input_tokens": value, "output_tokens": 0})
        result = analysis.summarize(self.root)
        self.assertLess(result["resource_gate"]["mini_to_rtk_total_token_ratio"], 0.8)
        self.assertEqual(result["resource_gate"]["status"], "not_met")
        self.assertEqual(result["decision"], "stop_compressor_expansion")

    def test_lower_correctness_blocks_resource_gate(self):
        self.tokens()
        self.outcomes("mini", {"J1"}, False)
        result = analysis.summarize(self.root)
        self.assertFalse(result["resource_gate"]["correctness_count_noninferior_to_raw_and_rtk"])
        self.assertEqual(result["decision"], "stop_compressor_expansion")

    def test_task_count_advantage_requires_reviewed_output_attribution(self):
        self.outcomes("rtk", {"R1", "J1"}, False)
        result = analysis.summarize(self.root)
        self.assertEqual(result["decision"], "requires_attribution")
        receipt = {"schema": 1, "plan_sha256": result["plan_sha256"], "reviewed": True,
                   "reviewed_by": "human-review", "tasks": [{"task_id": task, "output_related": True,
                        "evidence_sha256": ["a" * 64]} for task in ("J1", "R1")]}
        self.write(self.root / "attribution.json", receipt)
        self.assertEqual(analysis.summarize(self.root)["decision"], "continue_bounded_compressor_experiment")

    def test_consistent_reverse_task_blocks_task_gate(self):
        self.outcomes("rtk", {"R1", "J1"}, False)
        self.outcomes("mini", {"R2"}, False)
        result = analysis.summarize(self.root)
        self.assertEqual(result["task_gate"]["consistent_reverse_tasks"], ["R2"])
        self.assertEqual(result["decision"], "stop_compressor_expansion")

    def test_missing_trial_prevents_gate_and_excludes_entire_paired_triple(self):
        self.tokens()
        trial = self.plan["trials"][0]
        (self.root / "trials" / trial["id"] / "result.json").unlink()
        result = analysis.summarize(self.root)
        self.assertEqual(result["decision"], "inconclusive")
        self.assertEqual(result["valid_paired_triples"], 11)
        for variant in analysis.VARIANTS:
            self.assertEqual(result["primary_paired_usage"][variant]["observations"], 11)
        self.assertIn("missing_result", result["trials"][0]["exclusions"])

    def test_timeout_protocol_infra_and_invalid_usage_are_visible(self):
        self.tokens()
        for index, change in enumerate(({"timed_out": True}, {"protocol_deviations": ["native bypass /Users/private"]},
                                        {"usage": {"input_tokens": 10, "cached_input_tokens": 20, "output_tokens": 1}})):
            self.change(self.plan["trials"][index], "result", **change)
        self.change(self.plan["trials"][3], "evaluation", infrastructure_errors=[{"message": "private details"}])
        result = analysis.summarize(self.root)
        self.assertEqual(result["decision"], "inconclusive")
        self.assertFalse(result["trials"][1]["correct_repair"])
        serialized = json.dumps(result)
        self.assertNotIn("/Users/private", serialized)
        self.assertNotIn("private details", serialized)

    def test_plan_hash_mismatch_duplicate_json_id_and_result_identity_fail_closed(self):
        (self.root / "plan.json").write_text((self.root / "plan.json").read_text() + "\n")
        with self.assertRaises(analysis.AnalysisError):
            analysis.summarize(self.root)
        self.register()
        self.change(self.plan["trials"][0], "result", variant="mini")
        with self.assertRaises(analysis.AnalysisError):
            analysis.summarize(self.root)
        path = self.root / "trials" / self.plan["trials"][0]["id"] / "result.json"
        path.write_text('{"id":"one","id":"two"}')
        with self.assertRaises(analysis.AnalysisError):
            analysis.summarize(self.root)

    def test_unregistered_result_and_duplicate_evaluations_fail_closed(self):
        self.write(self.root / "trials/trial-999/result.json", {})
        with self.assertRaises(analysis.AnalysisError):
            analysis.summarize(self.root)
        (self.root / "trials/trial-999/result.json").unlink()
        self.write(self.root / "trials" / self.plan["trials"][0]["id"] / "evaluation/evaluation.json", {})
        with self.assertRaises(analysis.AnalysisError):
            analysis.summarize(self.root)

    def test_tool_metrics_count_visible_actions_recovery_repeated_tests_and_routes(self):
        trial = self.plan["trials"][0]
        self.change(trial, "result", mcp_calls=4)
        entries = []
        for index, tool in enumerate(("terminal", "terminal", "recover_output", "terminal"), 1):
            entries.append({"index": index, "tool": tool, "arguments": {"argv": ["npm", "test"]},
                            "response": {"route": "native" if index < 3 else "passthrough", "capture_complete": True},
                            "visible": {"stdout": "diagnostic /private/hidden text"}})
        path = self.root / "trials" / trial["id"] / "artifacts/tools.jsonl"
        path.parent.mkdir()
        path.write_text("\n".join(json.dumps(entry) for entry in entries))
        result = analysis.summarize(self.root)
        metrics = result["trials"][0]["tools"]
        self.assertEqual(metrics["actions"], 4)
        self.assertEqual(metrics["terminal_commands"], 3)
        self.assertEqual(metrics["recovery_calls"], 1)
        self.assertEqual(metrics["test_commands"], 3)
        self.assertEqual(metrics["repeated_identical_test_commands"], 2)
        self.assertEqual(metrics["native_filtered_commands"], 2)
        self.assertEqual(metrics["passthrough_commands"], 1)
        self.assertNotIn("diagnostic /private/hidden text", json.dumps(result))

    def test_missing_cached_usage_stays_unknown_and_zero_denominator_is_unavailable(self):
        self.tokens(mini=0, raw=0, rtk=0)
        result = analysis.summarize(self.root)
        self.assertIsNone(result["resource_gate"]["mini_to_rtk_total_token_ratio"])
        trial = self.plan["trials"][0]
        self.change(trial, "result", usage={"input_tokens": 10, "output_tokens": 3})
        result = analysis.summarize(self.root)
        self.assertIsNone(result["trials"][0]["usage"]["cached_input_tokens"])
        self.assertIsNone(result["trials"][0]["usage"]["uncached_input_plus_output_tokens"])


if __name__ == "__main__":
    unittest.main()
