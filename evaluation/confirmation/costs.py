"""Exact, rate-card credit calculations from observed CLI usage.

This does not read accounts, make API calls, or establish an attributed bill.
Freeze the explicit rate card and requested model/service tier in the plan.
The caller must establish complete usage and the applicable model/tier; missing
or partial telemetry produces unknown cost, never an invented zero charge.

Plan shape (rates are credits per million tokens, not dollars):
  cost_model = {schema: 1, unit: 'credits', model: 'gpt-6.1-sol',
    service_tier: 'standard', per_million_tokens: {
      uncached_input: '50', cached_input: '2.5', output: '250'},
    source_url: 'https://learn.chatgpt.com/docs/pricing#token-rates',
    fetched_at: '<timezone-aware ISO timestamp>', source_sha256: '<optional>'}

price_usage(..., complete=True, model=..., service_tier=...) prices one complete
session aggregate exactly once. summarize_attempts prices every planned attempt
and uses all-attempt cost / successful repairs, retaining unsuccessful attempts.
Do not sum cumulative per-request counters as well as a final session aggregate.
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal, localcontext
import hashlib
import json
import re
from urllib.parse import urlparse


RATE_KEYS = ("uncached_input", "cached_input", "output")
OFFICIAL_HOSTS = frozenset({"learn.chatgpt.com", "developers.openai.com", "platform.openai.com"})


class CostError(ValueError):
    """A rate card or attempt identity is invalid or ambiguous."""


def _rate(value) -> Decimal:
    if type(value) not in (str, int) or re.fullmatch(r"(?:0|[1-9][0-9]*)(?:\.[0-9]+)?", str(value)) is None:
        raise CostError("rates must be explicit finite nonnegative decimal strings or integers")
    return Decimal(str(value))


def _number(value: Decimal) -> str:
    text = format(value, "f")
    return text.rstrip("0").rstrip(".") if "." in text else text


def _precision(*values) -> int:
    return max(60, sum(len(str(value)) for value in values) + 20)


def validate_rate_card(card: dict) -> dict:
    if not isinstance(card, dict) or card.get("schema") != 1 or card.get("unit") != "credits":
        raise CostError("an explicit schema-1 credits rate card is required; no USD default exists")
    model = card.get("model")
    if not isinstance(model, str) or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,79}", model) is None:
        raise CostError("rate card requires an explicit model identifier")
    if not isinstance(card.get("service_tier"), str) or card["service_tier"] not in {"standard", "fast", "ultrafast"}:
        raise CostError("rate card requires an explicit standard/fast/ultrafast service tier")
    rates = card.get("per_million_tokens")
    if not isinstance(rates, dict) or set(rates) != set(RATE_KEYS):
        raise CostError("rate card requires exactly uncached_input, cached_input and output rates")
    normalized_rates = {key: _number(_rate(rates[key])) for key in RATE_KEYS}
    url = card.get("source_url")
    if not isinstance(url, str):
        raise CostError("rate card requires an official source URL")
    try:
        parsed = urlparse(url)
        valid_url = (parsed.scheme == "https" and parsed.hostname in OFFICIAL_HOSTS and parsed.username is None
                     and parsed.password is None and not parsed.query and parsed.port is None)
    except ValueError as error:
        raise CostError("rate provenance URL is malformed") from error
    if not valid_url:
        raise CostError("rate provenance must be an official HTTPS URL without credentials or query parameters")
    timestamp = card.get("fetched_at")
    try:
        parsed_time = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    except (AttributeError, TypeError, ValueError) as error:
        raise CostError("rate card requires a timezone-aware fetched_at timestamp") from error
    if parsed_time.tzinfo is None or parsed_time.utcoffset() is None:
        raise CostError("rate card fetched_at must include a timezone")
    result = {"schema": 1, "unit": "credits", "model": model,
              "service_tier": card["service_tier"], "per_million_tokens": normalized_rates,
              "source_url": url, "fetched_at": timestamp,
              "cache_write_charge": "none", "reasoning_charge": "included-in-output"}
    if "source_sha256" in card:
        if not isinstance(card["source_sha256"], str) or re.fullmatch(r"[0-9a-f]{64}", card["source_sha256"]) is None:
            raise CostError("source_sha256 must be a lowercase SHA-256 hex digest")
        result["source_sha256"] = card["source_sha256"]
    return result


def _usage(value) -> tuple[dict | None, str | None]:
    if not isinstance(value, dict):
        return None, "missing_usage"
    for key in ("input_tokens", "cached_input_tokens", "output_tokens"):
        if type(value.get(key)) is not int or value[key] < 0:
            return None, "missing_or_invalid_" + key
    if value["cached_input_tokens"] > value["input_tokens"]:
        return None, "cached_input_exceeds_total_input"
    reasoning = value.get("reasoning_output_tokens", value.get("reasoning_tokens"))
    if reasoning is not None and (type(reasoning) is not int or not 0 <= reasoning <= value["output_tokens"]):
        return None, "invalid_reasoning_subset"
    if "reasoning_output_tokens" in value and "reasoning_tokens" in value and value["reasoning_output_tokens"] != value["reasoning_tokens"]:
        return None, "conflicting_reasoning_subsets"
    writes = value.get("cache_write_input_tokens")
    if writes is not None and (type(writes) is not int or writes < 0):
        return None, "invalid_cache_write_tokens"
    return {"input_tokens": value["input_tokens"], "cached_input_tokens": value["cached_input_tokens"],
            "uncached_input_tokens": value["input_tokens"] - value["cached_input_tokens"],
            "output_tokens": value["output_tokens"], "reasoning_output_tokens": reasoning,
            "cache_write_input_tokens": writes}, None


def price_usage(usage: dict | None, card: dict, *, complete: bool,
                model: str | None = None, service_tier: str | None = None) -> dict:
    """Calculate published-rate credits; amount=None means unknown, not free.

    ``complete`` refers to entire session billing-relevant token coverage, not
    whether a patch was correct. Failed repairs still incur their full cost.
    ``model`` and ``service_tier`` must be independently established by the
    collector; this function does not infer them from aggregate token counts.
    No API long-context, cache-write or regional rules are silently borrowed.
    Those require a separately registered API cost method, not this credit card.
    """
    normalized = validate_rate_card(card)
    normalized_usage, error = _usage(usage)
    reasons = []
    if type(complete) is not bool or not complete:
        reasons.append("incomplete_usage_telemetry")
    if model != normalized["model"]:
        reasons.append("missing_or_mismatched_model")
    if service_tier != normalized["service_tier"]:
        reasons.append("missing_or_mismatched_service_tier")
    if error:
        reasons.append(error)
    result = {"measure": "published-rate-credit-calculation", "unit": "credits", "actual_billed": False,
              "known": not reasons, "amount": None, "components": None, "unknown_reasons": reasons,
              "usage": normalized_usage, "rate_card": normalized}
    if reasons:
        return result
    rates = {key: Decimal(value) for key, value in normalized["per_million_tokens"].items()}
    with localcontext() as context:
        context.prec = _precision(*normalized_usage.values(), *rates.values())
        components = {"uncached_input": Decimal(normalized_usage["uncached_input_tokens"]) * rates["uncached_input"] / 1_000_000,
                      "cached_input": Decimal(normalized_usage["cached_input_tokens"]) * rates["cached_input"] / 1_000_000,
                      "output": Decimal(normalized_usage["output_tokens"]) * rates["output"] / 1_000_000}
        result["components"] = {key: _number(value) for key, value in components.items()}
        result["amount"] = _number(sum(components.values(), Decimal(0)))
    return result


def summarize_attempts(attempts: list[dict], card: dict, *, planned_ids: list[str]) -> dict:
    """Retain every planned attempt, including failed repairs and unknown costs.

    Attempts: {id, usage, usage_complete, model, service_tier, correct_repair,
               timed_out?:bool, protocol_deviations?:list}. Timeout forces
    unknown cost because the collector has no complete final usage record.
    Missing correctness makes cost-per-success unknown. Identity mismatches or
    duplicate attempts raise; missing planned attempts remain explicit rows.
    """
    normalized = validate_rate_card(card)
    if not isinstance(planned_ids, list) or not planned_ids or any(not isinstance(value, str) or not value for value in planned_ids) or len(set(planned_ids)) != len(planned_ids):
        raise CostError("planned_ids must be a nonempty unique list of strings")
    if not isinstance(attempts, list):
        raise CostError("attempts must be a list")
    by_id = {}
    for attempt in attempts:
        if not isinstance(attempt, dict) or not isinstance(attempt.get("id"), str) or attempt["id"] not in planned_ids:
            raise CostError("unregistered attempt identity")
        if attempt["id"] in by_id:
            raise CostError("duplicate attempt identity")
        by_id[attempt["id"]] = attempt
    rows, missing, correctness_unknown = [], [], []
    for identifier in planned_ids:
        attempt = by_id.get(identifier)
        if attempt is None:
            missing.append(identifier)
            correctness_unknown.append(identifier)
            rows.append({"id": identifier, "observed": False, "correct_repair": None,
                         "known": False, "amount": None, "unknown_reasons": ["missing_attempt"]})
            continue
        priced = price_usage(attempt.get("usage"), card,
                             complete=attempt.get("usage_complete") is True and attempt.get("timed_out", False) is False,
                             model=attempt.get("model"), service_tier=attempt.get("service_tier"))
        correct = attempt.get("correct_repair")
        if type(correct) is not bool:
            correct = None
            correctness_unknown.append(identifier)
        deviations = attempt.get("protocol_deviations", [])
        if not isinstance(deviations, list):
            raise CostError("protocol_deviations must be a list when supplied")
        if deviations:
            correct = False
            # The protocol audit has established failure even if repair grading
            # is unavailable; do not leave it in the unknown denominator count.
            if identifier in correctness_unknown:
                correctness_unknown.remove(identifier)
        rows.append({"id": identifier, "observed": True, "correct_repair": correct,
                     "protocol_deviations_count": len(deviations), **{key: priced[key] for key in
                        ("known", "amount", "components", "unknown_reasons", "usage")}})
    known = [row for row in rows if row["known"]]
    successes = sum(row["correct_repair"] is True for row in rows)
    with localcontext() as context:
        context.prec = _precision(*(row["amount"] for row in known))
        observed_sum = sum((Decimal(row["amount"]) for row in known), Decimal(0))
        complete = len(known) == len(planned_ids)
        total = observed_sum if complete else None
        # Division can repeat: retain 50 significant digits rather than silently
        # rounding a dollar-like display. Primary totals above are exact decimals.
        context.prec = max(context.prec, 50)
        per_success = total / successes if total is not None and successes and not correctness_unknown else None
        per_attempt = total / len(planned_ids) if total is not None else None
    rate_hash = hashlib.sha256(json.dumps(normalized, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    return {"schema": 1, "measure": "published-rate-credit-calculation", "unit": "credits", "actual_billed": False,
            "rate_card": normalized, "rate_card_sha256": rate_hash, "planned_attempts": len(planned_ids),
            "observed_attempts": len(by_id), "known_cost_attempts": len(known), "all_planned_costs_known": complete,
            "missing_attempt_ids": missing, "unknown_cost_attempt_ids": [row["id"] for row in rows if not row["known"]],
            "unknown_correctness_attempt_ids": correctness_unknown, "successful_repairs": successes,
            "total_credits": _number(total) if total is not None else None,
            "known_attempt_credits_sum": _number(observed_sum) if known else None,
            "credits_per_planned_attempt": _number(per_attempt) if per_attempt is not None else None,
            "credits_per_successful_repair": _number(per_success) if per_success is not None else None,
            "attempts": rows,
            "definitions": {"total_credits": "sum of every planned attempt; unavailable if any attempt cost is unknown",
                "credits_per_successful_repair": "ALL planned attempt credits / correct repairs, not successful-attempt-only cost",
                "known_attempt_credits_sum": "observed known-cost subtotal; not a substitute for complete planned cost",
                "billing": "published rate applied to observed CLI tokens; no attributed credit deduction or USD receipt",
                "arithmetic": "exact Decimal component/totals; ratios retain at least 50 significant digits"}}
