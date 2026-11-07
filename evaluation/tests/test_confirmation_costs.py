import copy
from decimal import Decimal
import unittest

from evaluation.confirmation.costs import CostError, price_usage, summarize_attempts, validate_rate_card


CARD = {"schema": 1, "unit": "credits", "model": "gpt-6.1-sol", "service_tier": "standard",
        "per_million_tokens": {"uncached_input": "50", "cached_input": "2.5", "output": "250"},
        "source_url": "https://learn.chatgpt.com/docs/pricing#token-rates", "fetched_at": "2026-11-06T22:00:00Z"}


def priced(usage, **kwargs):
    return price_usage(usage, CARD, complete=True, model=CARD["model"], service_tier="standard", **kwargs)


def attempt(identifier, correct=True, **kwargs):
    return {"id": identifier, "usage": {"input_tokens": 1000000, "cached_input_tokens": 0, "output_tokens": 0},
            "usage_complete": True, "model": CARD["model"], "service_tier": "standard", "correct_repair": correct, **kwargs}


class CostTests(unittest.TestCase):
    def test_cached_input_is_subset_and_reasoning_is_not_added_again(self):
        usage = {"input_tokens": 1000000, "cached_input_tokens": 800000, "output_tokens": 100000,
                 "reasoning_output_tokens": 90000, "cache_write_input_tokens": 200000}
        result = priced(usage)
        self.assertEqual(result["components"], {"uncached_input": "10", "cached_input": "2", "output": "25"})
        self.assertEqual(result["amount"], "37")
        self.assertFalse(result["actual_billed"])
        self.assertEqual(result["rate_card"]["cache_write_charge"], "none")

    def test_prior_usage_exact_credit_projection_is_reproducible(self):
        values = [({"input_tokens": 3179375, "cached_input_tokens": 2759424, "output_tokens": 52116}, "40.92511"),
                  ({"input_tokens": 2803737, "cached_input_tokens": 2373760, "output_tokens": 48799}, "39.633"),
                  ({"input_tokens": 3660716, "cached_input_tokens": 3273216, "output_tokens": 52035}, "40.56679")]
        for usage, expected in values:
            self.assertEqual(priced(usage)["amount"], expected)

    def test_zero_known_usage_differs_from_missing_or_partial_usage(self):
        zero = {"input_tokens": 0, "cached_input_tokens": 0, "output_tokens": 0}
        self.assertEqual(priced(zero)["amount"], "0")
        partial = price_usage(zero, CARD, complete=False, model=CARD["model"], service_tier="standard")
        self.assertFalse(partial["known"])
        self.assertIsNone(partial["amount"])
        self.assertIsNone(priced(None)["amount"])

    def test_unknown_cached_tokens_are_not_assumed_free(self):
        result = priced({"input_tokens": 100, "output_tokens": 2})
        self.assertIsNone(result["amount"])
        self.assertIn("missing_or_invalid_cached_input_tokens", result["unknown_reasons"])

    def test_tier_model_and_completeness_must_be_established(self):
        usage = {"input_tokens": 100, "cached_input_tokens": 20, "output_tokens": 2}
        for model, tier in ((None, "standard"), (CARD["model"], None), ("other-model", "standard"), (CARD["model"], "fast")):
            self.assertIsNone(price_usage(usage, CARD, complete=True, model=model, service_tier=tier)["amount"])
        self.assertIsNone(price_usage(usage, CARD, complete=1, model=CARD["model"], service_tier="standard")["amount"])

    def test_invalid_counts_and_conflicting_reasoning_are_unknown(self):
        base = {"input_tokens": 100, "cached_input_tokens": 20, "output_tokens": 5}
        for changes in ({"input_tokens": -1}, {"cached_input_tokens": 101}, {"output_tokens": True},
                        {"reasoning_output_tokens": 6}, {"reasoning_output_tokens": 2, "reasoning_tokens": 3},
                        {"cache_write_input_tokens": -1}):
            self.assertIsNone(priced({**base, **changes})["amount"])

    def test_decimal_precision_preserves_counts_beyond_float_range(self):
        count = 10 ** 40 + 1
        result = priced({"input_tokens": count, "cached_input_tokens": 0, "output_tokens": 0})
        self.assertEqual(result["amount"], "500000000000000000000000000000000000.00005")

    def test_all_attempts_including_failed_repairs_enter_success_cost(self):
        result = summarize_attempts([attempt("one"), attempt("two", False), attempt("three")], CARD,
                                    planned_ids=["one", "two", "three"])
        self.assertEqual(result["total_credits"], "150")
        self.assertEqual(result["successful_repairs"], 2)
        self.assertEqual(result["credits_per_successful_repair"], "75")
        self.assertEqual(result["credits_per_planned_attempt"], "50")

    def test_missing_and_timeout_attempts_keep_total_and_success_cost_unknown(self):
        result = summarize_attempts([attempt("one"), attempt("two", timed_out=True)], CARD,
                                    planned_ids=["one", "two", "missing"])
        self.assertIsNone(result["total_credits"])
        self.assertIsNone(result["credits_per_successful_repair"])
        self.assertEqual(result["known_attempt_credits_sum"], "50")
        self.assertEqual(result["unknown_cost_attempt_ids"], ["two", "missing"])
        self.assertEqual(result["missing_attempt_ids"], ["missing"])

    def test_no_success_or_ungraded_correctness_does_not_divide_by_zero(self):
        result = summarize_attempts([attempt("one", False)], CARD, planned_ids=["one"])
        self.assertEqual(result["total_credits"], "50")
        self.assertIsNone(result["credits_per_successful_repair"])
        result = summarize_attempts([attempt("one", correct_repair=None)], CARD, planned_ids=["one"])
        self.assertEqual(result["unknown_correctness_attempt_ids"], ["one"])
        self.assertIsNone(result["credits_per_successful_repair"])

    def test_protocol_deviations_prevent_success_but_cost_is_retained(self):
        result = summarize_attempts([attempt("one", protocol_deviations=["bypass"])], CARD, planned_ids=["one"])
        self.assertEqual(result["successful_repairs"], 0)
        self.assertEqual(result["total_credits"], "50")

    def test_duplicate_unknown_or_unregistered_attempts_fail_closed(self):
        for attempts, ids in (([attempt("one"), attempt("one")], ["one"]), ([attempt("other")], ["one"]),
                              ([], ["one", "one"]), ([], [])):
            with self.assertRaises(CostError):
                summarize_attempts(attempts, CARD, planned_ids=ids)

    def test_rate_card_is_explicit_and_freezes_source_provenance(self):
        normalized = validate_rate_card(CARD)
        self.assertEqual(normalized["source_url"], CARD["source_url"])
        self.assertEqual(normalized["fetched_at"], CARD["fetched_at"])
        for changes in ({"unit": "USD"}, {"service_tier": "auto"}, {"fetched_at": "2026-11-06T22:00:00"},
                        {"service_tier": []}, {"source_url": "https://learn.chatgpt.com:not-a-port/pricing"},
                        {"source_url": "https://example.com/pricing"}, {"source_url": "https://user:secret@learn.chatgpt.com/pricing"},
                        {"source_sha256": "wrong"}):
            with self.assertRaises(CostError):
                validate_rate_card({**CARD, **changes})
        for rate in (2.5, "NaN", "Infinity", "-1", "1e-3", True):
            value = copy.deepcopy(CARD)
            value["per_million_tokens"]["cached_input"] = rate
            with self.assertRaises(CostError):
                validate_rate_card(value)

    def test_sum_of_exact_attempt_costs_matches_price_of_summed_usage(self):
        one = attempt("one", usage={"input_tokens": 12345, "cached_input_tokens": 3456, "output_tokens": 789})
        two = attempt("two", usage={"input_tokens": 112233, "cached_input_tokens": 123, "output_tokens": 444})
        result = summarize_attempts([one, two], CARD, planned_ids=["one", "two"])
        combined = {key: one["usage"][key] + two["usage"][key] for key in one["usage"]}
        self.assertEqual(Decimal(result["total_credits"]), Decimal(priced(combined)["amount"]))


if __name__ == "__main__":
    unittest.main()
