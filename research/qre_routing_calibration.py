"""Deterministic QRE routing calibration scaffold.

This module recommends read-only evidence routing targets from existing context.
It does not mutate queues, candidates, campaigns, strategies, presets, or
execution state.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping


SCHEMA_VERSION = "1.0"


ROUTING_TARGETS: tuple[str, ...] = (
    "sampling_calibration",
    "data_readiness",
    "source_quality",
    "identity_resolution",
    "factor_coverage",
    "null_model_baseline",
    "state_transition_diagnostics",
    "tail_entropy_hardening",
    "failure_retrieval",
    "operator_review",
    "excluded_scope_archive",
)


@dataclass(frozen=True)
class RoutingCalibration:
    subject_id: str
    routing_targets: tuple[str, ...]
    routing_priority: int
    routing_decision: str
    explanation: str


def _text(value: Any) -> str:
    return str(value or "").strip().lower()


def _contains_any(text: str, markers: tuple[str, ...]) -> bool:
    return any(marker in text for marker in markers)


def calibrate_routing_context(record: Mapping[str, Any]) -> RoutingCalibration:
    """Recommend deterministic read-only routing targets for one context row."""

    subject_id = str(record.get("subject_id") or record.get("candidate_id") or "unknown")
    ontology = record.get("ontology_classification")
    ontology = ontology if isinstance(ontology, Mapping) else {}

    asset_class = _text(record.get("asset_class") or ontology.get("asset_class"))
    research_scope = _text(record.get("research_scope") or ontology.get("research_scope"))
    readiness_state = _text(record.get("readiness_state") or ontology.get("readiness_state"))
    blocker_class = _text(record.get("blocker_class") or record.get("blocker_code"))
    record_kind = _text(record.get("record_kind"))
    title = _text(record.get("title"))
    text_preview = _text(record.get("text_preview"))
    artifact_id = _text(record.get("artifact_id"))
    metadata_text = " ".join([title, text_preview, artifact_id, str(record.get("metadata") or "").lower()])

    targets: set[str] = set()
    priority = 0

    if asset_class == "crypto_legacy" or research_scope in {
        "excluded_from_current_research_scope",
        "legacy_non_target_reference",
    }:
        return RoutingCalibration(
            subject_id=subject_id,
            routing_targets=("excluded_scope_archive",),
            routing_priority=0,
            routing_decision="route_to_archive_only",
            explanation="Excluded/legacy context is routed to archive only, not active research calibration.",
        )

    targets.add("sampling_calibration")
    priority += 10

    if readiness_state in {"blocked", "not_ready", "fail_closed"} or _contains_any(
        blocker_class, ("missing", "blocked", "unknown")
    ):
        targets.add("data_readiness")
        targets.add("failure_retrieval")
        priority += 30

    if _contains_any(metadata_text, ("source_manifest", "provider", "companyfacts", "openfigi", "source_quality")):
        targets.add("source_quality")
        priority += 20

    if _contains_any(metadata_text, ("identity", "symbol", "figi", "isin", "ticker", "ambiguous")):
        targets.add("identity_resolution")
        priority += 20

    if _contains_any(metadata_text, ("factor", "field_coverage", "fundamental", "metric")):
        targets.add("factor_coverage")
        priority += 20

    if _contains_any(metadata_text, ("null_model", "baseline", "above_baseline", "below_baseline")):
        targets.add("null_model_baseline")
        priority += 15

    if _contains_any(metadata_text, ("transition", "state", "screened", "validation_candidate", "blocked")):
        targets.add("state_transition_diagnostics")
        priority += 15

    if _contains_any(metadata_text, ("tail", "entropy", "drawdown", "concentration", "risk_state")):
        targets.add("tail_entropy_hardening")
        priority += 15

    if record_kind in {"failure_action", "reason_record"}:
        targets.add("failure_retrieval")
        priority += 20

    if not targets:
        targets.add("operator_review")

    if priority >= 60:
        decision = "route_high_priority"
    elif priority >= 25:
        decision = "route_standard"
    else:
        decision = "route_low_priority"

    return RoutingCalibration(
        subject_id=subject_id,
        routing_targets=tuple(sorted(targets)),
        routing_priority=priority,
        routing_decision=decision,
        explanation="Deterministic routing calibration context only; no queue or campaign mutation authority.",
    )


def calibrate_routing_rows(rows: list[Mapping[str, Any]]) -> list[RoutingCalibration]:
    return [calibrate_routing_context(row) for row in rows if isinstance(row, Mapping)]


def routing_calibration_manifest() -> dict[str, object]:
    return {
        "schema_version": SCHEMA_VERSION,
        "routing_targets": list(ROUTING_TARGETS),
        "authority": {
            "routing_calibration_is_context_only": True,
            "not_queue_mutation": True,
            "not_candidate_promotion": True,
            "not_campaign_mutation": True,
            "not_strategy_registration": True,
            "not_paper_shadow_live": True,
            "not_broker_execution": True,
            "does_not_fetch_data": True,
            "does_not_mutate_queues": True,
            "does_not_mutate_candidates": True,
            "does_not_mutate_campaigns": True,
            "does_not_mutate_strategies": True,
            "does_not_mutate_presets": True,
            "does_not_mutate_frozen_contracts": True,
        },
    }