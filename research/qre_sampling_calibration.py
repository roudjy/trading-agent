"""Deterministic QRE sampling calibration scaffold.

This module scores research sampling context using source, data, readiness,
null-model, and regime evidence metadata. It is read-only and cannot mutate
candidates, campaigns, strategies, presets, or execution state.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping


SCHEMA_VERSION = "1.0"


SAMPLING_DECISIONS: tuple[str, ...] = (
    "prefer_sampling",
    "allow_sampling",
    "deprioritize_sampling",
    "exclude_sampling",
)


PREFERRED_REGIONS: tuple[str, ...] = (
    "netherlands",
    "europe",
    "united_states",
    "asia",
)


PREFERRED_ASSET_CLASSES: tuple[str, ...] = (
    "equity",
    "fundamental_equity",
    "index",
)


EXCLUDED_ASSET_CLASSES: tuple[str, ...] = (
    "crypto_legacy",
)


PREFERRED_RESEARCH_SCOPES: tuple[str, ...] = (
    "target_equity_research",
    "target_source_data_research",
    "target_factor_research",
)


EXCLUDED_RESEARCH_SCOPES: tuple[str, ...] = (
    "excluded_from_current_research_scope",
    "legacy_non_target_reference",
)


SOURCE_EVIDENCE_MARKERS: tuple[str, ...] = (
    "source_quality",
    "source_manifest",
    "identity_confidence",
    "provider_symbol",
    "openfigi",
    "companyfacts",
)


DATA_EVIDENCE_MARKERS: tuple[str, ...] = (
    "cache_ready",
    "cache_manifest",
    "coverage",
    "row_count",
    "file_count",
    "parquet",
    "duckdb",
    "polars",
)


READINESS_EVIDENCE_MARKERS: tuple[str, ...] = (
    "readiness_state",
    "routing_readiness",
    "sampling_readiness",
    "follow_up",
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
)


NULL_EVIDENCE_MARKERS: tuple[str, ...] = (
    "null_model",
    "baseline_type",
    "baseline_metric",
    "random_walk",
    "shuffled_surrogate",
    "martingale_like",
    "candidate_above_baseline",
    "candidate_below_baseline",
    "candidate_equal_to_baseline",
)


REGIME_EVIDENCE_MARKERS: tuple[str, ...] = (
    "regime_duration",
    "dwell_state",
    "sequence_state",
    "longest_run",
    "sequence_diagnostic",
    "transition_reason",
)


@dataclass(frozen=True)
class SamplingCalibration:
    subject_id: str
    sampling_score: int
    sampling_decision: str
    preferred_axes: tuple[str, ...]
    penalty_axes: tuple[str, ...]
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
            ),
        ):
            categories.add("data")
        if _mapping_truthy(
            evidence_presence,
            (
                "sampling_ready",
                "routing_ready",
                "readiness_ready",
            ),
        ):
            categories.add("readiness")
        if _mapping_truthy(
            evidence_presence,
            (
                "diagnostic_ready",
                "tail_entropy_ready",
                "state_transition_ready",
            ),
        ):
            categories.add("diagnostic")
        if _mapping_truthy(
            evidence_presence,
            (
                "null_model_ready",
                "baseline_ready",
                "comparison_ready",
            ),
        ):
            categories.add("null")
        if _mapping_truthy(
            evidence_presence,
            (
                "regime_ready",
                "sequence_ready",
                "dwell_ready",
            ),
        ):
            categories.add("regime")

    combined_text = " ".join(
        [
            _stringify(record.get("title")),
            _stringify(record.get("text_preview")),
            _stringify(record.get("metadata")),
            _stringify(record.get("artifact_id")),
            _stringify(record.get("source")),
            _stringify(record.get("readiness_state")),
            _stringify(record.get("blocker_class")),
            _stringify(record.get("comparison_state")),
            _stringify(record.get("baseline_type")),
            _stringify(record.get("risk_state")),
            _stringify(record.get("density_state")),
            _stringify(record.get("transition_state")),
            _stringify(record.get("sequence_state")),
            _stringify(record.get("dwell_state")),
            _stringify(record.get("regime_duration_steps")),
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
    if _contains_any(combined_text, NULL_EVIDENCE_MARKERS):
        categories.add("null")
    if _contains_any(combined_text, REGIME_EVIDENCE_MARKERS):
        categories.add("regime")

    return tuple(sorted(categories))


def _evidence_ref_count(record: Mapping[str, Any]) -> int:
    evidence_refs = record.get("evidence_refs")
    if isinstance(evidence_refs, list):
        return sum(1 for ref in evidence_refs if str(ref or "").strip())
    if evidence_refs:
        return 1
    return 0


def _region_axis(metadata_text: str) -> str | None:
    if _contains_any(metadata_text, ("netherlands", "nederland", "aex", "amsterdam", "euronext amsterdam")):
        return "region:netherlands"
    if _contains_any(metadata_text, ("europe", "europa", "euronext", "stoxx", "dax", "cac", "ftse")):
        return "region:europe"
    if _contains_any(metadata_text, ("united_states", "usa", "us equity", "nyse", "nasdaq", "s&p", "sp500")):
        return "region:united_states"
    if _contains_any(metadata_text, ("asia", "japan", "hong kong", "singapore", "nikkei", "topix")):
        return "region:asia"
    return None


def calibrate_sampling_context(record: Mapping[str, Any]) -> SamplingCalibration:
    """Calibrate sampling priority for one evidence/candidate context row.

    This is advisory context only. It does not schedule or mutate campaigns.
    """

    subject_id = str(record.get("subject_id") or record.get("candidate_id") or "unknown")
    ontology = record.get("ontology_classification")
    ontology = ontology if isinstance(ontology, Mapping) else {}

    asset_class = _text(record.get("asset_class") or ontology.get("asset_class"))
    research_scope = _text(record.get("research_scope") or ontology.get("research_scope"))
    readiness_state = _text(record.get("readiness_state") or ontology.get("readiness_state"))
    comparison_state = _text(record.get("comparison_state") or ontology.get("comparison_state"))
    title = _text(record.get("title"))
    text_preview = _text(record.get("text_preview"))
    artifact_id = _text(record.get("artifact_id"))
    metadata_text = " ".join(
        [title, text_preview, artifact_id, _stringify(record.get("metadata")), _stringify(record.get("evidence_presence"))]
    )

    evidence_categories = _evidence_categories(record)
    evidence_ref_count = _evidence_ref_count(record)

    score = 0
    preferred_axes: list[str] = []
    penalty_axes: list[str] = []

    if asset_class in EXCLUDED_ASSET_CLASSES:
        penalty_axes.append(f"asset_class:{asset_class}")
        return SamplingCalibration(
            subject_id=subject_id,
            sampling_score=-100,
            sampling_decision="exclude_sampling",
            preferred_axes=tuple(preferred_axes),
            penalty_axes=tuple(penalty_axes),
            evidence_support_state="archive_only",
            evidence_categories=("archive",),
            evidence_ref_count=evidence_ref_count,
            explanation="Crypto legacy/non-target asset class is excluded from current sampling scope.",
        )

    if research_scope in EXCLUDED_RESEARCH_SCOPES:
        penalty_axes.append(f"research_scope:{research_scope}")
        return SamplingCalibration(
            subject_id=subject_id,
            sampling_score=-100,
            sampling_decision="exclude_sampling",
            preferred_axes=tuple(preferred_axes),
            penalty_axes=tuple(penalty_axes),
            evidence_support_state="archive_only",
            evidence_categories=("archive",),
            evidence_ref_count=evidence_ref_count,
            explanation="Research scope is excluded from current sampling scope.",
        )

    if asset_class in PREFERRED_ASSET_CLASSES:
        score += 30
        preferred_axes.append(f"asset_class:{asset_class}")

    if research_scope in PREFERRED_RESEARCH_SCOPES:
        score += 30
        preferred_axes.append(f"research_scope:{research_scope}")

    if _contains_any(metadata_text, ("fundamental", "factor", "companyfacts", "source_manifest", "openfigi", "field_coverage")):
        score += 20
        preferred_axes.append("evidence:fundamental_source_or_factor")

    region = _region_axis(metadata_text)
    if region is not None:
        score += 15
        preferred_axes.append(region)

    if "source" in evidence_categories:
        score += 15
        preferred_axes.append("evidence:source_ready")

    if "data" in evidence_categories:
        score += 15
        preferred_axes.append("evidence:data_ready")

    if "readiness" in evidence_categories:
        score += 10
        preferred_axes.append("evidence:readiness_ready")

    if "diagnostic" in evidence_categories:
        score += 10
        preferred_axes.append("evidence:diagnostic_ready")

    if "null" in evidence_categories:
        score += 15
        preferred_axes.append("evidence:null_model_ready")

    if "regime" in evidence_categories:
        score += 10
        preferred_axes.append("evidence:regime_ready")

    if comparison_state == "candidate_above_baseline":
        score += 10
        preferred_axes.append("comparison_state:above_baseline")
    elif comparison_state == "candidate_equal_to_baseline":
        score += 5
        preferred_axes.append("comparison_state:equal_to_baseline")
    elif comparison_state == "candidate_below_baseline":
        score -= 15
        penalty_axes.append("comparison_state:below_baseline")

    if readiness_state in {"blocked", "fail_closed", "not_ready"}:
        score -= 40
        penalty_axes.append(f"readiness_state:{readiness_state}")
    elif readiness_state in {"partial", "unknown"}:
        score -= 10
        penalty_axes.append(f"readiness_state:{readiness_state}")
    elif readiness_state == "ready":
        score += 10
        preferred_axes.append("readiness_state:ready")

    if _contains_any(metadata_text, ("crypto", "btc-usd", "eth-usd", "sol-usd")):
        score -= 80
        penalty_axes.append("content:crypto_marker")

    if len(evidence_categories) >= 3:
        evidence_support_state = "evidence_backed"
    elif evidence_categories:
        evidence_support_state = "partial_evidence"
    else:
        evidence_support_state = "heuristic_only"

    if score >= 60:
        decision = "prefer_sampling"
    elif score >= 20:
        decision = "allow_sampling"
    elif score > -50:
        decision = "deprioritize_sampling"
    else:
        decision = "exclude_sampling"

    if readiness_state in {"blocked", "fail_closed", "not_ready"} and decision == "prefer_sampling":
        decision = "allow_sampling" if score >= 20 else "deprioritize_sampling"

    return SamplingCalibration(
        subject_id=subject_id,
        sampling_score=score,
        sampling_decision=decision,
        preferred_axes=tuple(sorted(set(preferred_axes))),
        penalty_axes=tuple(sorted(set(penalty_axes))),
        evidence_support_state=evidence_support_state,
        evidence_categories=evidence_categories,
        evidence_ref_count=evidence_ref_count,
        explanation=(
            "Deterministic sampling calibration context only; no campaign mutation "
            f"authority. Evidence categories: {', '.join(evidence_categories) or 'none'}."
        ),
    )


def calibrate_sampling_rows(rows: list[Mapping[str, Any]]) -> list[SamplingCalibration]:
    return [calibrate_sampling_context(row) for row in rows if isinstance(row, Mapping)]


def sampling_calibration_manifest() -> dict[str, object]:
    return {
        "schema_version": SCHEMA_VERSION,
        "sampling_decisions": list(SAMPLING_DECISIONS),
        "preferred_regions": list(PREFERRED_REGIONS),
        "preferred_asset_classes": list(PREFERRED_ASSET_CLASSES),
        "excluded_asset_classes": list(EXCLUDED_ASSET_CLASSES),
        "preferred_research_scopes": list(PREFERRED_RESEARCH_SCOPES),
        "excluded_research_scopes": list(EXCLUDED_RESEARCH_SCOPES),
        "evidence_categories": [
            "source",
            "data",
            "readiness",
            "diagnostic",
            "null",
            "regime",
        ],
        "authority": {
            "sampling_calibration_is_context_only": True,
            "evidence_backed_context_only": True,
            "not_alpha_authority": True,
            "not_candidate_promotion": True,
            "not_campaign_mutation": True,
            "not_strategy_registration": True,
            "not_paper_shadow_live": True,
            "not_broker_execution": True,
            "does_not_fetch_data": True,
            "does_not_mutate_candidates": True,
            "does_not_mutate_campaigns": True,
            "does_not_mutate_strategies": True,
            "does_not_mutate_frozen_contracts": True,
        },
    }
