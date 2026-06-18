"""Read-only QRE preset feasibility mapping.

This module connects canonical behavior families and hypothesis objects
to structurally feasible preset and timeframe combinations. It is
context-only: it does not synthesize strategies, authorize execution,
clear evidence blockers, or promote candidates.
"""

from __future__ import annotations

import fnmatch
import hashlib
import json
from dataclasses import dataclass
from typing import Any, Final, Iterable, Literal, Mapping

from research.qre_behavior_catalog import BehaviorFamily, get_behavior_family
from research.qre_hypothesis_model import validate_hypothesis


FeasibilityStatus = Literal[
    "feasible",
    "provisional",
    "blocked_unknown_behavior",
    "blocked_missing_hypothesis_fields",
    "blocked_missing_data_capability",
    "blocked_forbidden_interpretation",
    "blocked_no_compatible_preset",
    "blocked_no_compatible_timeframe",
    "blocked_not_evidence_authoritative",
]

FEASIBILITY_SCHEMA_VERSION: Final[str] = "1.0"
NON_AUTHORITATIVE_FLAG: Final[bool] = True
EVIDENCE_AUTHORITY: Final[str] = "context_only"
CAN_AUTHORIZE_EXECUTION: Final[bool] = False
CAN_CLEAR_EVIDENCE_BLOCKERS: Final[bool] = False
CAN_PROMOTE_CANDIDATE: Final[bool] = False
VALID_FEASIBILITY_STATUSES: Final[frozenset[str]] = frozenset(
    {
        "feasible",
        "provisional",
        "blocked_unknown_behavior",
        "blocked_missing_hypothesis_fields",
        "blocked_missing_data_capability",
        "blocked_forbidden_interpretation",
        "blocked_no_compatible_preset",
        "blocked_no_compatible_timeframe",
        "blocked_not_evidence_authoritative",
    }
)
RESEARCH_READY_REQUIRED_FIELDS: Final[tuple[str, ...]] = (
    "hypothesis_id",
    "behavior_id",
    "title",
    "description",
)
HYPOTHESIS_EVIDENCE_FIELDS: Final[tuple[str, ...]] = (
    "required_data_capabilities",
    "required_evidence_types",
)


@dataclass(frozen=True)
class PresetFeasibilitySpec:
    preset_id: str
    timeframe: str
    mapping_reason: str
    required_data_capabilities: tuple[str, ...]
    required_evidence_types: tuple[str, ...]

    def to_payload(self) -> dict[str, Any]:
        return {
            "preset_id": self.preset_id,
            "timeframe": self.timeframe,
            "mapping_reason": self.mapping_reason,
            "required_data_capabilities": list(self.required_data_capabilities),
            "required_evidence_types": list(self.required_evidence_types),
        }


PRESET_FEASIBILITY_SPECS: Final[dict[str, tuple[PresetFeasibilitySpec, ...]]] = {
    "trend_continuation": (
        PresetFeasibilitySpec(
            preset_id="trend_continuation_daily_v1",
            timeframe="1d",
            mapping_reason="pattern_aligned_trend_continuation",
            required_data_capabilities=("time_series_ohlcv", "regime_context", "cost_model"),
            required_evidence_types=("screening_evidence", "oos_evidence", "lineage_evidence"),
        ),
        PresetFeasibilitySpec(
            preset_id="trend_pullback_continuation_daily_v1",
            timeframe="1d",
            mapping_reason="pattern_aligned_pullback_continuation",
            required_data_capabilities=("time_series_ohlcv", "regime_context", "cost_model"),
            required_evidence_types=("screening_evidence", "oos_evidence", "lineage_evidence"),
        ),
    ),
    "pullback_continuation": (
        PresetFeasibilitySpec(
            preset_id="trend_pullback_continuation_daily_v1",
            timeframe="1d",
            mapping_reason="pattern_aligned_pullback_continuation",
            required_data_capabilities=("time_series_ohlcv", "trend_context", "cost_model"),
            required_evidence_types=("screening_evidence", "oos_evidence", "lineage_evidence"),
        ),
    ),
    "volatility_compression_breakout": (
        PresetFeasibilitySpec(
            preset_id="vol_compression_breakout_daily_v1",
            timeframe="1d",
            mapping_reason="pattern_aligned_volatility_compression_breakout",
            required_data_capabilities=("time_series_ohlcv", "volatility_measurements", "cost_model"),
            required_evidence_types=("screening_evidence", "oos_evidence", "lineage_evidence"),
        ),
        PresetFeasibilitySpec(
            preset_id="vol_compression_breakout_4h_v1",
            timeframe="4h",
            mapping_reason="pattern_aligned_volatility_compression_breakout",
            required_data_capabilities=("time_series_ohlcv", "volatility_measurements", "cost_model"),
            required_evidence_types=("screening_evidence", "oos_evidence", "lineage_evidence"),
        ),
    ),
    "relative_strength": (
        PresetFeasibilitySpec(
            preset_id="relative_strength_vs_region_daily_v1",
            timeframe="1d",
            mapping_reason="pattern_aligned_relative_strength_region",
            required_data_capabilities=("cross_sectional_prices", "benchmark_series", "cost_model"),
            required_evidence_types=("screening_evidence", "oos_evidence", "lineage_evidence"),
        ),
        PresetFeasibilitySpec(
            preset_id="relative_strength_vs_sector_daily_v1",
            timeframe="1d",
            mapping_reason="pattern_aligned_relative_strength_sector",
            required_data_capabilities=("cross_sectional_prices", "benchmark_series", "cost_model"),
            required_evidence_types=("screening_evidence", "oos_evidence", "lineage_evidence"),
        ),
    ),
    "post_shock_stabilization": (
        PresetFeasibilitySpec(
            preset_id="post_shock_stabilization_daily_v1",
            timeframe="1d",
            mapping_reason="pattern_aligned_post_shock_stabilization",
            required_data_capabilities=("event_context", "time_series_ohlcv", "cost_model"),
            required_evidence_types=("screening_evidence", "oos_evidence", "lineage_evidence"),
        ),
    ),
    "index_regime_filter": (
        PresetFeasibilitySpec(
            preset_id="index_regime_filter_daily_v1",
            timeframe="1d",
            mapping_reason="pattern_aligned_index_regime_filter",
            required_data_capabilities=("index_series", "breadth_context", "cost_model"),
            required_evidence_types=("screening_evidence", "oos_evidence", "lineage_evidence"),
        ),
    ),
}


def _unique_in_order(values: Iterable[str]) -> tuple[str, ...]:
    return tuple(dict.fromkeys(str(value) for value in values if str(value).strip()))


def _canonicalize_result(result: Mapping[str, Any]) -> dict[str, Any]:
    payload = {
        "schema_version": result.get("schema_version", FEASIBILITY_SCHEMA_VERSION),
        "behavior_id": result.get("behavior_id"),
        "hypothesis_id": result.get("hypothesis_id"),
        "feasible_mappings": list(result.get("feasible_mappings", [])),
        "blocked_mappings": list(result.get("blocked_mappings", [])),
        "required_data_capabilities": list(result.get("required_data_capabilities", [])),
        "required_evidence_types": list(result.get("required_evidence_types", [])),
        "compatible_preset_patterns": list(result.get("compatible_preset_patterns", [])),
        "compatible_timeframes": list(result.get("compatible_timeframes", [])),
        "non_authoritative": bool(result.get("non_authoritative", NON_AUTHORITATIVE_FLAG)),
        "evidence_authority": result.get("evidence_authority", EVIDENCE_AUTHORITY),
        "can_authorize_execution": bool(
            result.get("can_authorize_execution", CAN_AUTHORIZE_EXECUTION)
        ),
        "can_clear_evidence_blockers": bool(
            result.get("can_clear_evidence_blockers", CAN_CLEAR_EVIDENCE_BLOCKERS)
        ),
        "can_promote_candidate": bool(result.get("can_promote_candidate", CAN_PROMOTE_CANDIDATE)),
        "blocker_reasons": list(result.get("blocker_reasons", [])),
    }
    return payload


def compute_feasibility_hash(payload: Mapping[str, Any]) -> str:
    canonical = _canonicalize_result(payload)
    blob = json.dumps(canonical, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode(
        "utf-8"
    )
    return hashlib.sha256(blob).hexdigest()


def _build_blocked_mapping(
    *,
    behavior_id: str,
    hypothesis_id: str | None,
    status: FeasibilityStatus,
    mapping_reason: str,
    blocker_reasons: Iterable[str],
    required_data_capabilities: Iterable[str] = (),
    required_evidence_types: Iterable[str] = (),
    compatible_preset_patterns: Iterable[str] = (),
    compatible_timeframes: Iterable[str] = (),
) -> dict[str, Any]:
    return {
        "behavior_id": behavior_id,
        "hypothesis_id": hypothesis_id,
        "feasible_mappings": [],
        "blocked_mappings": [
            {
                "preset_id": None,
                "timeframe": None,
                "feasibility_status": status,
                "mapping_reason": mapping_reason,
                "required_data_capabilities": list(_unique_in_order(required_data_capabilities)),
                "required_evidence_types": list(_unique_in_order(required_evidence_types)),
                "compatible_preset_patterns": list(_unique_in_order(compatible_preset_patterns)),
                "compatible_timeframes": list(_unique_in_order(compatible_timeframes)),
                "blocker_reasons": list(_unique_in_order(blocker_reasons)),
                "non_authoritative": NON_AUTHORITATIVE_FLAG,
                "evidence_authority": EVIDENCE_AUTHORITY,
                "can_authorize_execution": CAN_AUTHORIZE_EXECUTION,
                "can_clear_evidence_blockers": CAN_CLEAR_EVIDENCE_BLOCKERS,
                "can_promote_candidate": CAN_PROMOTE_CANDIDATE,
            }
        ],
        "required_data_capabilities": list(_unique_in_order(required_data_capabilities)),
        "required_evidence_types": list(_unique_in_order(required_evidence_types)),
        "compatible_preset_patterns": list(_unique_in_order(compatible_preset_patterns)),
        "compatible_timeframes": list(_unique_in_order(compatible_timeframes)),
        "non_authoritative": NON_AUTHORITATIVE_FLAG,
        "evidence_authority": EVIDENCE_AUTHORITY,
        "can_authorize_execution": CAN_AUTHORIZE_EXECUTION,
        "can_clear_evidence_blockers": CAN_CLEAR_EVIDENCE_BLOCKERS,
        "can_promote_candidate": CAN_PROMOTE_CANDIDATE,
        "blocker_reasons": list(_unique_in_order(blocker_reasons)),
        "schema_version": FEASIBILITY_SCHEMA_VERSION,
    }


def _base_result(behavior: BehaviorFamily, hypothesis_id: str | None) -> dict[str, Any]:
    return {
        "behavior_id": behavior.behavior_id,
        "hypothesis_id": hypothesis_id,
        "feasible_mappings": [],
        "blocked_mappings": [],
        "required_data_capabilities": list(_unique_in_order(behavior.required_data_capabilities)),
        "required_evidence_types": list(_unique_in_order(behavior.evidence_requirements)),
        "compatible_preset_patterns": list(_unique_in_order(behavior.compatible_preset_patterns)),
        "compatible_timeframes": list(_unique_in_order(behavior.typical_timeframes)),
        "non_authoritative": NON_AUTHORITATIVE_FLAG,
        "evidence_authority": EVIDENCE_AUTHORITY,
        "can_authorize_execution": CAN_AUTHORIZE_EXECUTION,
        "can_clear_evidence_blockers": CAN_CLEAR_EVIDENCE_BLOCKERS,
        "can_promote_candidate": CAN_PROMOTE_CANDIDATE,
        "blocker_reasons": [],
        "schema_version": FEASIBILITY_SCHEMA_VERSION,
    }


def _mapping_status_for_behavior(behavior: BehaviorFamily) -> FeasibilityStatus:
    if behavior.status == "active":
        return "feasible"
    return "provisional"


def _mapping_reason_for_behavior(behavior: BehaviorFamily) -> str:
    if behavior.status == "active":
        return "structural_behavior_to_preset_alignment"
    return f"structural_behavior_to_preset_alignment_{behavior.status}"


def _matches_compatible_pattern(behavior: BehaviorFamily, preset_id: str) -> bool:
    return any(
        fnmatch.fnmatch(preset_id, pattern) for pattern in behavior.compatible_preset_patterns
    )


def _build_mapping_entry(
    behavior: BehaviorFamily,
    spec: PresetFeasibilitySpec,
    hypothesis_id: str | None,
    hypothesis_payload: Mapping[str, Any] | None,
) -> dict[str, Any]:
    blocker_reasons: list[str] = []
    status: FeasibilityStatus = _mapping_status_for_behavior(behavior)
    mapping_reason = _mapping_reason_for_behavior(behavior)

    if not _matches_compatible_pattern(behavior, spec.preset_id):
        status = "blocked_no_compatible_preset"
        mapping_reason = "preset_not_compatible_with_behavior_patterns"
        blocker_reasons.append("preset_pattern_mismatch")
    elif spec.timeframe not in behavior.typical_timeframes:
        status = "blocked_no_compatible_timeframe"
        mapping_reason = "timeframe_not_compatible_with_behavior"
        blocker_reasons.append("timeframe_mismatch")
    elif behavior.status == "blocked":
        status = "blocked_forbidden_interpretation"
        mapping_reason = "behavior_status_blocked"
        blocker_reasons.append("behavior_status_blocked")

    if hypothesis_payload is not None:
        hypothesis_timeframe = str(hypothesis_payload.get("timeframe") or "").strip()
        if hypothesis_timeframe and hypothesis_timeframe != spec.timeframe:
            status = "blocked_no_compatible_timeframe"
            mapping_reason = "hypothesis_timeframe_not_compatible"
            blocker_reasons.append("hypothesis_timeframe_mismatch")

        hypothesis_capabilities = _unique_in_order(hypothesis_payload.get("required_data_capabilities") or ())
        if hypothesis_capabilities:
            missing_caps = [
                capability
                for capability in spec.required_data_capabilities
                if capability not in hypothesis_capabilities
            ]
            if missing_caps:
                status = "blocked_missing_data_capability"
                mapping_reason = "hypothesis_missing_required_data_capability"
                blocker_reasons.extend(f"missing_data_capability:{capability}" for capability in missing_caps)

        if str(hypothesis_payload.get("status") or "").strip() == "evidence_complete":
            status = "blocked_not_evidence_authoritative"
            mapping_reason = "preset_feasibility_is_not_accepted_evidence"
            blocker_reasons.append("not_evidence_authoritative")

    return {
        "preset_id": spec.preset_id,
        "timeframe": spec.timeframe,
        "feasibility_status": status,
        "mapping_reason": mapping_reason,
        "required_data_capabilities": list(spec.required_data_capabilities),
        "required_evidence_types": list(spec.required_evidence_types),
        "compatible_preset_patterns": list(behavior.compatible_preset_patterns),
        "compatible_timeframes": list(behavior.typical_timeframes),
        "blocker_reasons": list(_unique_in_order(blocker_reasons)),
        "non_authoritative": NON_AUTHORITATIVE_FLAG,
        "evidence_authority": EVIDENCE_AUTHORITY,
        "can_authorize_execution": CAN_AUTHORIZE_EXECUTION,
        "can_clear_evidence_blockers": CAN_CLEAR_EVIDENCE_BLOCKERS,
        "can_promote_candidate": CAN_PROMOTE_CANDIDATE,
    }


def _finalize_result(result: dict[str, Any]) -> dict[str, Any]:
    result["required_data_capabilities"] = list(_unique_in_order(result["required_data_capabilities"]))
    result["required_evidence_types"] = list(_unique_in_order(result["required_evidence_types"]))
    result["compatible_preset_patterns"] = list(_unique_in_order(result["compatible_preset_patterns"]))
    result["compatible_timeframes"] = list(_unique_in_order(result["compatible_timeframes"]))
    result["blocker_reasons"] = list(_unique_in_order(result["blocker_reasons"]))
    result["hash"] = compute_feasibility_hash(result)
    return result


def list_feasible_presets_for_behavior(behavior_id: str) -> dict[str, Any]:
    try:
        behavior = get_behavior_family(behavior_id)
    except KeyError:
        blocked = _build_blocked_mapping(
            behavior_id=behavior_id,
            hypothesis_id=None,
            status="blocked_unknown_behavior",
            mapping_reason="unknown_behavior_id",
            blocker_reasons=("unknown_behavior_id",),
        )
        return _finalize_result(blocked)

    result = _base_result(behavior, None)
    specs = PRESET_FEASIBILITY_SPECS.get(behavior.behavior_id, ())
    if not specs:
        blocked = _build_blocked_mapping(
            behavior_id=behavior.behavior_id,
            hypothesis_id=None,
            status="blocked_no_compatible_preset",
            mapping_reason="no_configured_preset_mapping",
            blocker_reasons=("no_compatible_preset_mapping",),
            required_data_capabilities=behavior.required_data_capabilities,
            required_evidence_types=behavior.evidence_requirements,
            compatible_preset_patterns=behavior.compatible_preset_patterns,
            compatible_timeframes=behavior.typical_timeframes,
        )
        return _finalize_result(blocked)

    for spec in specs:
        entry = _build_mapping_entry(behavior, spec, None, None)
        if entry["feasibility_status"] in {"feasible", "provisional"}:
            result["feasible_mappings"].append(entry)
        else:
            result["blocked_mappings"].append(entry)
            result["blocker_reasons"].extend(entry["blocker_reasons"])

    return _finalize_result(result)


def evaluate_preset_feasibility_for_hypothesis(hypothesis: Mapping[str, Any]) -> dict[str, Any]:
    payload = dict(hypothesis)
    behavior_id = str(payload.get("behavior_id") or "").strip()
    hypothesis_id = str(payload.get("hypothesis_id") or "").strip() or None
    hypothesis_status = str(payload.get("status") or "").strip()

    if not behavior_id:
        blocked = _build_blocked_mapping(
            behavior_id="",
            hypothesis_id=hypothesis_id,
            status="blocked_missing_hypothesis_fields",
            mapping_reason="missing_behavior_id",
            blocker_reasons=("missing_behavior_id",),
        )
        return _finalize_result(blocked)

    try:
        behavior = get_behavior_family(behavior_id)
    except KeyError:
        blocked = _build_blocked_mapping(
            behavior_id=behavior_id,
            hypothesis_id=hypothesis_id,
            status="blocked_unknown_behavior",
            mapping_reason="unknown_behavior_id",
            blocker_reasons=("unknown_behavior_id",),
        )
        return _finalize_result(blocked)

    validation = validate_hypothesis(payload)
    missing_fields = [
        field_name
        for field_name in RESEARCH_READY_REQUIRED_FIELDS
        if not str(payload.get(field_name) or "").strip()
    ]
    if hypothesis_status == "research_ready" and not tuple(payload.get("falsification_criteria") or ()):
        missing_fields.append("falsification_criteria")
    if missing_fields:
        blocked = _build_blocked_mapping(
            behavior_id=behavior_id,
            hypothesis_id=hypothesis_id,
            status="blocked_missing_hypothesis_fields",
            mapping_reason="missing_research_ready_hypothesis_fields",
            blocker_reasons=tuple(
                f"missing_hypothesis_field:{field_name}" for field_name in missing_fields
            ),
            required_data_capabilities=behavior.required_data_capabilities,
            required_evidence_types=behavior.evidence_requirements,
            compatible_preset_patterns=behavior.compatible_preset_patterns,
            compatible_timeframes=behavior.typical_timeframes,
        )
        return _finalize_result(blocked)

    if not validation.valid:
        blocked = _build_blocked_mapping(
            behavior_id=behavior_id,
            hypothesis_id=hypothesis_id,
            status="blocked_missing_hypothesis_fields",
            mapping_reason="hypothesis_validation_failed",
            blocker_reasons=validation.rejection_reasons,
            required_data_capabilities=behavior.required_data_capabilities,
            required_evidence_types=behavior.evidence_requirements,
            compatible_preset_patterns=behavior.compatible_preset_patterns,
            compatible_timeframes=behavior.typical_timeframes,
        )
        return _finalize_result(blocked)

    result = _base_result(behavior, hypothesis_id)
    hypothesis_data_capabilities = _unique_in_order(payload.get("required_data_capabilities") or ())
    if not hypothesis_data_capabilities:
        payload["required_data_capabilities"] = list(behavior.required_data_capabilities)
    hypothesis_evidence_types = _unique_in_order(payload.get("required_evidence_types") or ())
    if not hypothesis_evidence_types:
        payload["required_evidence_types"] = list(behavior.evidence_requirements)

    specs = PRESET_FEASIBILITY_SPECS.get(behavior.behavior_id, ())
    if not specs:
        blocked = _build_blocked_mapping(
            behavior_id=behavior.behavior_id,
            hypothesis_id=hypothesis_id,
            status="blocked_no_compatible_preset",
            mapping_reason="no_configured_preset_mapping",
            blocker_reasons=("no_compatible_preset_mapping",),
            required_data_capabilities=behavior.required_data_capabilities,
            required_evidence_types=behavior.evidence_requirements,
            compatible_preset_patterns=behavior.compatible_preset_patterns,
            compatible_timeframes=behavior.typical_timeframes,
        )
        return _finalize_result(blocked)

    for spec in specs:
        entry = _build_mapping_entry(behavior, spec, hypothesis_id, payload)
        result["required_data_capabilities"].extend(entry["required_data_capabilities"])
        result["required_evidence_types"].extend(entry["required_evidence_types"])
        if entry["feasibility_status"] in {"feasible", "provisional"}:
            result["feasible_mappings"].append(entry)
        else:
            result["blocked_mappings"].append(entry)
            result["blocker_reasons"].extend(entry["blocker_reasons"])

    return _finalize_result(result)


def validate_feasibility_result(result: Mapping[str, Any]) -> dict[str, Any]:
    rejection_reasons: list[str] = []
    canonical = _canonicalize_result(result)

    for field_name in (
        "behavior_id",
        "feasible_mappings",
        "blocked_mappings",
        "required_data_capabilities",
        "required_evidence_types",
        "compatible_preset_patterns",
        "compatible_timeframes",
        "non_authoritative",
        "evidence_authority",
        "can_authorize_execution",
        "can_clear_evidence_blockers",
        "can_promote_candidate",
    ):
        if field_name not in canonical:
            rejection_reasons.append(f"missing_field:{field_name}")

    if canonical["non_authoritative"] is not True:
        rejection_reasons.append("non_authoritative_must_be_true")

    if canonical["evidence_authority"] != EVIDENCE_AUTHORITY:
        rejection_reasons.append("invalid_evidence_authority")

    if canonical["can_authorize_execution"] is not False:
        rejection_reasons.append("can_authorize_execution_must_be_false")

    if canonical["can_clear_evidence_blockers"] is not False:
        rejection_reasons.append("can_clear_evidence_blockers_must_be_false")

    if canonical["can_promote_candidate"] is not False:
        rejection_reasons.append("can_promote_candidate_must_be_false")

    for collection_name in ("feasible_mappings", "blocked_mappings"):
        for entry in canonical[collection_name]:
            status = entry.get("feasibility_status")
            if status is None:
                rejection_reasons.append(f"missing_feasibility_status:{collection_name}")
                continue
            if status not in VALID_FEASIBILITY_STATUSES:
                rejection_reasons.append(f"invalid_feasibility_status:{status}")

    computed_hash = compute_feasibility_hash(result)
    if str(result.get("hash") or "") and str(result.get("hash")) != computed_hash:
        rejection_reasons.append("hash_mismatch")

    return {
        "valid": not rejection_reasons,
        "rejection_reasons": list(_unique_in_order(rejection_reasons)),
        "hash": computed_hash,
        "schema_version": FEASIBILITY_SCHEMA_VERSION,
    }
