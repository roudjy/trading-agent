"""Deterministic QRE routing calibration scaffold.

This module recommends read-only routing targets from existing source, data,
readiness, and diagnostic evidence. It does not mutate queues, candidates,
campaigns, strategies, presets, or execution state.
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


SOURCE_EVIDENCE_MARKERS: tuple[str, ...] = (
    "source_quality",
    "source_manifest",
    "identity_confidence",
    "source_identity",
    "provider_symbol",
    "companyfacts",
    "openfigi",
)

DATA_EVIDENCE_MARKERS: tuple[str, ...] = (
    "cache_ready",
    "cache_manifest",
    "coverage",
    "row_count",
    "file_count",
    "duckdb",
    "parquet",
    "polars",
)

READINESS_EVIDENCE_MARKERS: tuple[str, ...] = (
    "readiness_state",
    "routing_readiness",
    "sampling_readiness",
    "follow_up",
    "primary_reason_code",
    "supporting_reason_codes",
    "ready",
    "blocked",
    "fail_closed",
)

DIAGNOSTIC_EVIDENCE_MARKERS: tuple[str, ...] = (
    "transition_state",
    "state_transition",
    "decision_quality",
    "risk_state",
    "density_state",
    "tail_entropy",
    "diagnostic",
    "null_challenge",
)


@dataclass(frozen=True)
class RoutingCalibration:
    subject_id: str
    routing_targets: tuple[str, ...]
    routing_priority: int
    routing_decision: str
    evidence_support_state: str
    evidence_categories: tuple[str, ...]
    evidence_ref_count: int
    explanation: str


def _text(value: Any) -> str:
    return str(value or "").strip().lower()


def _stringify(value: Any) -> str:
    if isinstance(value, Mapping):
        return " ".join(_stringify(item) for item in value.values())
    if isinstance(value, (list, tuple, set, frozenset)):
        return " ".join(_stringify(item) for item in value)
    return _text(value)


def _contains_any(text: str, markers: tuple[str, ...]) -> bool:
    return any(marker in text for marker in markers)


def _mapping_truthy(mapping: Mapping[str, Any] | None, keys: tuple[str, ...]) -> bool:
    if not isinstance(mapping, Mapping):
        return False
    return any(bool(mapping.get(key)) for key in keys)


def _evidence_categories(record: Mapping[str, Any]) -> tuple[str, ...]:
    categories: set[str] = set()
    evidence_presence = record.get("evidence_presence")
    if isinstance(evidence_presence, Mapping):
        if _mapping_truthy(
            evidence_presence,
            (
                "source_quality_ready",
                "source_identity_ready",
                "manifest_ready",
                "source_identity_status",
                "provider_symbol_status",
                "identity_confidence",
            ),
        ):
            categories.add("source")
        if _mapping_truthy(
            evidence_presence,
            (
                "cache_ready",
                "coverage_present",
                "data_ready",
                "cache_coverage_ready",
                "parquet_snapshot_ready",
                "duckdb_catalog_ready",
            ),
        ):
            categories.add("data")
        if _mapping_truthy(
            evidence_presence,
            (
                "routing_ready",
                "sampling_ready",
                "readiness_ready",
                "readiness_state_ready",
                "follow_up_ready",
            ),
        ):
            categories.add("readiness")
        if _mapping_truthy(
            evidence_presence,
            (
                "diagnostic_ready",
                "state_transition_ready",
                "tail_entropy_ready",
                "transition_state",
                "risk_state",
                "density_state",
            ),
        ):
            categories.add("diagnostic")

    combined_text = " ".join(
        [
            _stringify(record.get("title")),
            _stringify(record.get("text_preview")),
            _stringify(record.get("metadata")),
            _stringify(record.get("artifact_id")),
            _stringify(record.get("source")),
            _stringify(record.get("readiness_state")),
            _stringify(record.get("blocker_class")),
            _stringify(record.get("routing_readiness_state")),
            _stringify(record.get("sampling_readiness_state")),
            _stringify(record.get("transition_state")),
            _stringify(record.get("risk_state")),
            _stringify(record.get("density_state")),
            _stringify(record.get("quality_status")),
            _stringify(record.get("manifest_status")),
            _stringify(record.get("identity_confidence")),
        ]
    )

    if _contains_any(combined_text, SOURCE_EVIDENCE_MARKERS):
        categories.add("source")
    if _contains_any(combined_text, DATA_EVIDENCE_MARKERS):
        categories.add("data")
    if _contains_any(combined_text, READINESS_EVIDENCE_MARKERS):
        categories.add("readiness")
    if _contains_any(combined_text, DIAGNOSTIC_EVIDENCE_MARKERS):
        categories.add("diagnostic")

    return tuple(sorted(categories))


def _evidence_ref_count(record: Mapping[str, Any]) -> int:
    evidence_refs = record.get("evidence_refs")
    if isinstance(evidence_refs, list):
        return sum(1 for ref in evidence_refs if str(ref or "").strip())
    if evidence_refs:
        return 1
    return 0


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
    metadata_text = " ".join(
        [title, text_preview, artifact_id, _stringify(record.get("metadata")), _stringify(record.get("evidence_presence"))]
    )

    evidence_categories = _evidence_categories(record)
    evidence_ref_count = _evidence_ref_count(record)

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
            evidence_support_state="archive_only",
            evidence_categories=("archive",),
            evidence_ref_count=evidence_ref_count,
            explanation="Excluded/legacy context is routed to archive only, not active research calibration.",
        )

    targets.add("sampling_calibration")
    priority += 10

    if "source" in evidence_categories:
        targets.add("source_quality")
        priority += 20

    if "data" in evidence_categories:
        targets.add("data_readiness")
        priority += 20

    if "readiness" in evidence_categories:
        targets.add("sampling_calibration")
        priority += 10

    if "diagnostic" in evidence_categories:
        targets.add("state_transition_diagnostics")
        targets.add("tail_entropy_hardening")
        priority += 20

    if readiness_state in {"blocked", "not_ready", "fail_closed"} or _contains_any(
        blocker_class, ("missing", "blocked", "unknown")
    ):
        targets.add("data_readiness")
        targets.add("failure_retrieval")
        priority += 30

    if _contains_any(metadata_text, ("source_manifest", "provider", "companyfacts", "openfigi", "source_quality")):
        targets.add("source_quality")
        priority += 15

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

    priority += len(evidence_categories) * 8
    priority += min(evidence_ref_count, 3) * 2

    if not targets:
        targets.add("operator_review")

    if len(evidence_categories) >= 3:
        evidence_support_state = "evidence_backed"
    elif evidence_categories:
        evidence_support_state = "partial_evidence"
    else:
        evidence_support_state = "heuristic_only"

    if priority >= 70:
        decision = "route_high_priority"
    elif priority >= 35:
        decision = "route_standard"
    else:
        decision = "route_low_priority"

    return RoutingCalibration(
        subject_id=subject_id,
        routing_targets=tuple(sorted(targets)),
        routing_priority=priority,
        routing_decision=decision,
        evidence_support_state=evidence_support_state,
        evidence_categories=evidence_categories,
        evidence_ref_count=evidence_ref_count,
        explanation=(
            "Deterministic routing calibration context only; no queue or campaign "
            f"mutation authority. Evidence categories: {', '.join(evidence_categories) or 'none'}."
        ),
    )


def calibrate_routing_rows(rows: list[Mapping[str, Any]]) -> list[RoutingCalibration]:
    return [calibrate_routing_context(row) for row in rows if isinstance(row, Mapping)]


def routing_calibration_manifest() -> dict[str, object]:
    return {
        "schema_version": SCHEMA_VERSION,
        "routing_targets": list(ROUTING_TARGETS),
        "evidence_categories": ["source", "data", "readiness", "diagnostic"],
        "authority": {
            "routing_calibration_is_context_only": True,
            "evidence_backed_context_only": True,
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
