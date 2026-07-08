"""Deterministic canonical-memory influence for next hypothesis batches."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from typing import Any, Final

PROVIDER_TERMS: Final[tuple[str, ...]] = ("tiingo", "yfinance", "alpaca", "binance", "kraken", "coinbase")
SAFETY: Final[dict[str, bool]] = {
    "research_only": True,
    "memory_context_only": True,
    "creates_candidates": False,
    "creates_strategies": False,
    "creates_presets": False,
    "creates_campaigns": False,
    "runs_screening": False,
    "strategy_synthesis_authority": False,
    "stochastic_selector": False,
    "trading_authority": False,
    "validation_authority": False,
    "paper_authority": False,
    "shadow_authority": False,
    "live_authority": False,
}


class MemoryAwareGenerationError(ValueError):
    """Raised when memory-aware ordering cannot be safely computed."""


def _stable(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _stable(value[key]) for key in sorted(value)}
    if isinstance(value, list | tuple):
        return [_stable(item) for item in value]
    return value


def _digest(value: Any) -> str:
    payload = json.dumps(_stable(value), sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def _assert_no_provider_leakage(payload: Any, path: tuple[str, ...] = ()) -> None:
    if "provenance" in path:
        return
    if isinstance(payload, Mapping):
        for key, value in payload.items():
            if any(term in str(key).lower() for term in PROVIDER_TERMS):
                raise MemoryAwareGenerationError("provider_leakage:" + ".".join((*path, str(key))))
            _assert_no_provider_leakage(value, (*path, str(key)))
        return
    if isinstance(payload, list | tuple):
        for index, value in enumerate(payload):
            _assert_no_provider_leakage(value, (*path, str(index)))
        return
    if any(term in str(payload).lower() for term in PROVIDER_TERMS):
        raise MemoryAwareGenerationError("provider_leakage:" + ".".join(path))


def _family(payload: Mapping[str, Any]) -> str:
    value = payload.get("feature_family") or payload.get("mechanism_family") or payload.get("candidate_family")
    if not value and isinstance(payload.get("mechanism"), Mapping):
        value = payload["mechanism"].get("feature_family")
    text = str(value or "").strip()
    if not text:
        raise MemoryAwareGenerationError("missing_hypothesis_family")
    return text


def _memory_rules(memory: Mapping[str, Any] | None) -> dict[str, dict[str, Any]]:
    if not memory:
        return {}
    _assert_no_provider_leakage(memory)
    rules: dict[str, dict[str, Any]] = {}
    for record in memory.get("feedback_records", []) if isinstance(memory.get("feedback_records"), list) else []:
        if not isinstance(record, Mapping):
            continue
        family = str(record.get("hypothesis_family") or record.get("candidate_family") or "").strip()
        if not family:
            continue
        decision = str(record.get("feedback_decision") or "")
        if decision in {"reject_for_now", "block_until_repaired"}:
            rules[family] = {"action": "suppress", "reason": decision}
        elif decision in {"modify_or_deprioritize", "needs_more_evidence"}:
            rules.setdefault(family, {"action": "deprioritize", "reason": decision})
        elif decision == "retain_for_more_research":
            rules.setdefault(family, {"action": "boost", "reason": decision})
    for lesson in memory.get("lessons", []) if isinstance(memory.get("lessons"), list) else []:
        if not isinstance(lesson, Mapping):
            continue
        for family in lesson.get("do_not_repeat_families", []) if isinstance(lesson.get("do_not_repeat_families"), list) else []:
            rules[str(family)] = {"action": "suppress", "reason": "negative_lesson_memory"}
        for family in lesson.get("dead_zone_families", []) if isinstance(lesson.get("dead_zone_families"), list) else []:
            rules.setdefault(str(family), {"action": "deprioritize", "reason": "dead_zone_memory"})
        for family in lesson.get("near_pass_families", []) if isinstance(lesson.get("near_pass_families"), list) else []:
            rules.setdefault(str(family), {"action": "boost", "reason": "near_pass_feedback"})
    return rules


def prioritize_hypothesis_batch(
    hypotheses: Sequence[Mapping[str, Any]],
    memory: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Apply canonical memory to a hypothesis batch deterministically."""

    if not hypotheses:
        raise MemoryAwareGenerationError("missing_hypotheses")
    for hypothesis in hypotheses:
        _assert_no_provider_leakage(hypothesis)
    rules = _memory_rules(memory)
    rows: list[dict[str, Any]] = []
    for index, hypothesis in enumerate(hypotheses):
        family = _family(hypothesis)
        rule = rules.get(family, {"action": "baseline", "reason": "no_memory_match"})
        base_priority = float(hypothesis.get("base_priority", 1.0))
        adjustment = {"boost": 0.25, "deprioritize": -0.35, "suppress": -1.0, "baseline": 0.0}[rule["action"]]
        final_priority = base_priority + adjustment
        suppressed = rule["action"] == "suppress"
        rows.append(
            {
                "hypothesis_id": str(hypothesis.get("hypothesis_id") or f"hypothesis_{index}"),
                "hypothesis_family": family,
                "base_priority": base_priority,
                "memory_action": rule["action"],
                "memory_reason": rule["reason"],
                "final_priority": final_priority,
                "suppressed": suppressed,
                "explanation": f"memory_action={rule['action']}; reason={rule['reason']}",
                "source_index": index,
            }
        )
    ordered = sorted(rows, key=lambda row: (row["suppressed"], -float(row["final_priority"]), row["hypothesis_id"]))
    payload = {
        "canonical_name": "HypothesisBatchMemoryView",
        "schema_version": 1,
        "batch_view_id": "hbatch_" + _digest({"hypotheses": rows, "memory": memory or {}}),
        "hypotheses": ordered,
        "suppressed_count": sum(1 for row in ordered if row["suppressed"]),
        "memory_applied_count": sum(1 for row in ordered if row["memory_action"] != "baseline"),
        "warnings": _contradiction_warnings(memory),
        "safety": dict(SAFETY),
    }
    _assert_no_provider_leakage(payload)
    return payload


def _contradiction_warnings(memory: Mapping[str, Any] | None) -> list[str]:
    if not memory:
        return []
    warnings = []
    for item in memory.get("contradictions", []) if isinstance(memory.get("contradictions"), list) else []:
        warnings.append("contradictory_memory:" + str(item))
    return sorted(warnings)


__all__ = ["MemoryAwareGenerationError", "SAFETY", "prioritize_hypothesis_batch"]
