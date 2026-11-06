import sys
from pathlib import Path
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from comprehension import score


class ComprehensionTests(unittest.TestCase):
    def setUp(self):
        self.manifest = {"labels": {"A": "raw", "B": "mini", "C": "rtk"},
                         "plan_sha256": "plan", "results_sha256": "results",
                         "protocol_sha256": "protocol",
                         "batch_sha256": dict.fromkeys("ABC", "hash"),
                         "questions": [{"id": "Q1", "case_id": "R8", "required_answers": ["failing_test", "ASSERTION_MARKER"]}]}

    def responses(self):
        return {label: {"external_sources_used": False, "answers": [{"id": "Q1", "answer": "The failing_test reported assertion_marker."}]}
                for label in "ABC"}

    def test_requires_every_registered_fact_with_case_insensitive_identifiers(self):
        responses = self.responses()
        responses["C"]["answers"][0]["answer"] = "unknown"
        report = score(self.manifest, responses)
        self.assertEqual(report["variants"]["raw"]["correct"], 1)
        self.assertEqual(report["variants"]["rtk"]["correct"], 0)

    def test_rejects_missing_duplicate_and_unblinded_tool_responses(self):
        for mode in ("missing", "duplicate", "tools"):
            responses = self.responses()
            if mode == "missing":
                del responses["B"]
            elif mode == "duplicate":
                responses["B"]["answers"] *= 2
            else:
                responses["B"]["external_sources_used"] = True
            with self.assertRaises(ValueError):
                score(self.manifest, responses)

    def test_public_score_contains_no_answer_text(self):
        report = score(self.manifest, self.responses())
        self.assertNotIn("answer", report["variants"]["raw"]["checks"][0])


if __name__ == "__main__":
    unittest.main()
