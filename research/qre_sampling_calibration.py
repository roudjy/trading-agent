"""Deterministic QRE sampling calibration scaffold.

This module scores research sampling context using existing evidence metadata.
It is read-only and cannot mutate candidates, campaigns, strategies, presets,
or execution state.
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


@dataclass(frozen=True)
class SamplingCalibration:
    subject_id: str
    sampling_score: int
    sampling_decision: str
    preferred_axes: tuple[str, ...]
    penalty_axes: tuple[str, ...]
    explanation: str


def _text(value: Any) -> str:
    return str(value or "").strip().lower()


def _contains_any(text: str, markers: tuple[str, ...]) -> bool:
    return any(marker in text for marker in markers)


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
    title = _text(record.get("title"))
    text_preview = _text(record.get("text_preview"))
    artifact_id = _text(record.get("artifact_id"))
    metadata_text = " ".join([title, text_preview, artifact_id, str(record.get("metadata") or "").lower()])

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

    if score >= 60:
        decision = "prefer_sampling"
    elif score >= 20:
        decision = "allow_sampling"
    elif score > -50:
        decision = "deprioritize_sampling"
    else:
        decision = "exclude_sampling"

    return SamplingCalibration(
        subject_id=subject_id,
        sampling_score=score,
        sampling_decision=decision,
        preferred_axes=tuple(sorted(set(preferred_axes))),
        penalty_axes=tuple(sorted(set(penalty_axes))),
        explanation="Deterministic sampling calibration context only; no campaign mutation authority.",
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
        "authority": {
            "sampling_calibration_is_context_only": True,
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