from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from typing import Any, Final, Literal


SamplingPlanStatus = Literal[
    "sampling_plan_ready_context_only",
    "blocked_missing_hypothesis",
    "blocked_missing_preset",
    "blocked_missing_timeframe",
    "blocked_insufficient_range",
    "blocked_invalid_window",
    "blocked_overlapping_windows",
    "blocked_missing_null_control",
    "blocked_outcome_based_selection",
    "blocked_not_preregistered",
]

SCHEMA_VERSION: Final[str] = "1.0"
REPORT_KIND: Final[str] = "qre_sampling_plan"
NON_AUTHORITATIVE: Final[bool] = True
CAN_AUTHORIZE_EXECUTION: Final[bool] = False
CAN_CLEAR_EVIDENCE_BLOCKERS: Final[bool] = False
CAN_PROMOTE_CANDIDATE: Final[bool] = False
EVIDENCE_AUTHORITY: Final[str] = "context_only"
DEFAULT_SELECTION_POLICY: Final[str] = "deterministic_preregistered_windows_only"
DEFAULT_FORBIDDEN_ADAPTATIONS: Final[tuple[str, ...]] = (
    "profitability_based_window_selection",
    "return_based_window_selection",
    "sharpe_based_window_selection",
    "parameter_tuning_against_oos_window",
    "post_hoc_window_redefinition",
    "in_sample_to_oos_relabeling",
)
OUTCOME_KEYWORDS: Final[tuple[str, ...]] = (
    "profit",
    "pnl",
    "return",
    "sharpe",
    "drawdown",
    "win_rate",
    "outcome",
)


def _text(value: Any) -> str:
    return str(value or "").strip()


def _unique_in_order(values: Sequence[Any]) -> list[str]:
    return list(dict.fromkeys(_text(value) for value in values if _text(value)))


def _normalize_date_text(value: Any) -> str:
    text = _text(value)
    if not text:
        return ""
    return text[:10]


def _date_key(value: Any) -> tuple[int, int, int]:
    text = _normalize_date_text(value)
    if not text:
        return (0, 0, 0)
    year, month, day = text.split("-")
    return (int(year), int(month), int(day))


def _contains_outcome_language(value: Any) -> bool:
    if isinstance(value, Mapping):
        return any(
            _contains_outcome_language(key) or _contains_outcome_language(item)
            for key, item in value.items()
        )
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes)):
        return any(_contains_outcome_language(item) for item in value)
    lowered = _text(value).lower()
    return any(keyword in lowered for keyword in OUTCOME_KEYWORDS)


def _canonical_window(window: Mapping[str, Any], *, index: int) -> dict[str, Any]:
    return {
        "window_id": _text(window.get("window_id")) or f"window_{index:02d}",
        "bounded_input_window": {
            "start": _normalize_date_text((window.get("bounded_input_window") or {}).get("start")),
            "end": _normalize_date_text((window.get("bounded_input_window") or {}).get("end")),
        },
        "oos_window": {
            "start": _normalize_date_text((window.get("oos_window") or {}).get("start")),
            "end": _normalize_date_text((window.get("oos_window") or {}).get("end")),
        },
        "role": _text(window.get("role")) or "oos",
        "regime_label": _text(window.get("regime_label")) or "unclassified",
        "locked": bool(window.get("locked", False)),
        "justification": _text(window.get("justification")),
    }


def _validate_windows(window_definitions: Sequence[Mapping[str, Any]]) -> tuple[str | None, list[str], list[dict[str, Any]]]:
    normalized = [_canonical_window(window, index=index + 1) for index, window in enumerate(window_definitions)]
    seen_ids: set[str] = set()
    errors: list[str] = []
    spans: list[tuple[tuple[int, int, int], tuple[int, int, int], str]] = []
    for window in normalized:
        window_id = window["window_id"]
        if window_id in seen_ids:
            errors.append(f"duplicate_window_id:{window_id}")
        seen_ids.add(window_id)
        bounded_start = window["bounded_input_window"]["start"]
        bounded_end = window["bounded_input_window"]["end"]
        oos_start = window["oos_window"]["start"]
        oos_end = window["oos_window"]["end"]
        if not bounded_start or not bounded_end or not oos_start or not oos_end:
            errors.append(f"invalid_window_bounds:{window_id}")
            continue
        if _date_key(bounded_start) >= _date_key(bounded_end):
            errors.append(f"invalid_bounded_window:{window_id}")
        if _date_key(oos_start) >= _date_key(oos_end):
            errors.append(f"invalid_oos_window:{window_id}")
        if _date_key(oos_start) < _date_key(bounded_start) or _date_key(oos_end) > _date_key(bounded_end):
            errors.append(f"oos_window_outside_bounded_window:{window_id}")
        if window["role"] != "oos":
            errors.append(f"invalid_window_role:{window_id}")
        if window["locked"] is not True:
            errors.append(f"window_not_locked:{window_id}")
        spans.append((_date_key(oos_start), _date_key(oos_end), window_id))
    ordered_spans = sorted(spans, key=lambda item: (item[0], item[1], item[2]))
    for left, right in zip(ordered_spans, ordered_spans[1:]):
        if right[0] <= left[1]:
            errors.append(f"overlapping_oos_windows:{left[2]}:{right[2]}")
    if any(error.startswith("overlapping_oos_windows:") for error in errors):
        return "blocked_overlapping_windows", errors, normalized
    if errors:
        return "blocked_invalid_window", errors, normalized
    return None, [], normalized


def derive_preregistered_windows(
    *,
    trading_dates: Sequence[Any],
    window_count: int,
    minimum_window_length: int,
    minimum_warmup_period: int,
    regime_labels: Sequence[str] | None = None,
) -> list[dict[str, Any]]:
    ordered_dates = sorted({_normalize_date_text(value) for value in trading_dates if _normalize_date_text(value)})
    if window_count <= 0:
        raise ValueError("window_count_must_be_positive")
    if minimum_window_length <= 0:
        raise ValueError("minimum_window_length_must_be_positive")
    if minimum_warmup_period < 0:
        raise ValueError("minimum_warmup_period_must_be_non_negative")
    if len(ordered_dates) < minimum_window_length * window_count:
        raise ValueError("insufficient_range_for_preregistered_windows")
    base_length = len(ordered_dates) // window_count
    remainder = len(ordered_dates) % window_count
    cursor = 0
    windows: list[dict[str, Any]] = []
    labels = list(regime_labels or [])
    for index in range(window_count):
        current_length = base_length + (1 if index < remainder else 0)
        slice_dates = ordered_dates[cursor : cursor + current_length]
        cursor += current_length
        if len(slice_dates) < minimum_window_length:
            raise ValueError("insufficient_window_length")
        split_index = max(minimum_warmup_period, int(len(slice_dates) * 0.7))
        if split_index >= len(slice_dates):
            raise ValueError("invalid_oos_split")
        regime_label = _text(labels[index]) if index < len(labels) else "unclassified"
        windows.append(
            {
                "window_id": f"window_{index + 1:02d}",
                "bounded_input_window": {
                    "start": slice_dates[0],
                    "end": slice_dates[-1],
                },
                "oos_window": {
                    "start": slice_dates[split_index],
                    "end": slice_dates[-1],
                },
                "role": "oos",
                "regime_label": regime_label or "unclassified",
                "locked": True,
                "justification": "deterministic_non_overlapping_partition",
            }
        )
    return windows


def compute_sampling_plan_hash(plan: Mapping[str, Any]) -> str:
    canonical = {
        "schema_version": plan.get("schema_version", SCHEMA_VERSION),
        "report_kind": plan.get("report_kind", REPORT_KIND),
        "sampling_plan_id": plan.get("sampling_plan_id", ""),
        "hypothesis_ref": plan.get("hypothesis_ref", ""),
        "behavior_id": plan.get("behavior_id", ""),
        "preset_id": plan.get("preset_id", ""),
        "timeframe": plan.get("timeframe", ""),
        "window_definitions": list(plan.get("window_definitions", [])),
        "regime_buckets": list(plan.get("regime_buckets", [])),
        "null_control_definitions": list(plan.get("null_control_definitions", [])),
        "minimum_trade_requirement": int(plan.get("minimum_trade_requirement", 0) or 0),
        "minimum_window_length": int(plan.get("minimum_window_length", 0) or 0),
        "known_previous_failed_windows": list(plan.get("known_previous_failed_windows", [])),
        "preregistration_timestamp": plan.get("preregistration_timestamp", ""),
        "selection_policy": plan.get("selection_policy", ""),
        "forbidden_adaptations": list(plan.get("forbidden_adaptations", [])),
        "authority": dict(plan.get("authority", {})),
        "status": plan.get("status", ""),
    }
    blob = json.dumps(canonical, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def build_preregistered_sampling_plan(
    *,
    hypothesis_ref: str | None = None,
    hypothesis: Mapping[str, Any] | None = None,
    behavior_id: str,
    preset_id: str | None,
    timeframe: str | None,
    bounded_source_data_availability: Mapping[str, Any] | None = None,
    proposed_total_validation_range: Mapping[str, Any] | None = None,
    minimum_window_length: int,
    minimum_warmup_period: int,
    required_oos_evidence_types: Sequence[str],
    null_control_definitions: Sequence[Mapping[str, Any]] | None,
    known_previous_failed_windows: Sequence[Mapping[str, Any]] | None = None,
    regime_buckets: Sequence[Mapping[str, Any]] | None = None,
    window_definitions: Sequence[Mapping[str, Any]] | None = None,
    trading_dates: Sequence[Any] | None = None,
    window_count: int | None = None,
    preregistration_timestamp: str | None = None,
    minimum_trade_requirement: int = 1,
    selection_policy: str = DEFAULT_SELECTION_POLICY,
    forbidden_adaptations: Sequence[str] = DEFAULT_FORBIDDEN_ADAPTATIONS,
) -> dict[str, Any]:
    hypothesis_id = _text((hypothesis or {}).get("hypothesis_id")) or _text(hypothesis_ref)
    timestamp = _text(preregistration_timestamp) or datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    if not hypothesis_id:
        status: SamplingPlanStatus = "blocked_missing_hypothesis"
        blocked_reasons = ["missing_hypothesis"]
        normalized_windows: list[dict[str, Any]] = []
    elif not _text(preset_id):
        status = "blocked_missing_preset"
        blocked_reasons = ["missing_preset_id"]
        normalized_windows = []
    elif not _text(timeframe):
        status = "blocked_missing_timeframe"
        blocked_reasons = ["missing_timeframe"]
        normalized_windows = []
    elif not null_control_definitions:
        status = "blocked_missing_null_control"
        blocked_reasons = ["missing_null_control_definition"]
        normalized_windows = []
    elif not timestamp:
        status = "blocked_not_preregistered"
        blocked_reasons = ["missing_preregistration_timestamp"]
        normalized_windows = []
    elif _contains_outcome_language(selection_policy):
        status = "blocked_outcome_based_selection"
        blocked_reasons = ["outcome_based_selection_detected"]
        normalized_windows = []
    else:
        candidate_windows = list(window_definitions or [])
        if not candidate_windows:
            if not trading_dates or not window_count:
                status = "blocked_insufficient_range"
                blocked_reasons = ["insufficient_range_for_preregistered_windows"]
                normalized_windows = []
            else:
                try:
                    candidate_windows = derive_preregistered_windows(
                        trading_dates=trading_dates,
                        window_count=window_count,
                        minimum_window_length=minimum_window_length,
                        minimum_warmup_period=minimum_warmup_period,
                        regime_labels=[
                            _text(bucket.get("regime_label")) if isinstance(bucket, Mapping) else _text(bucket)
                            for bucket in (regime_buckets or [])
                        ],
                    )
                except ValueError as exc:
                    status = "blocked_insufficient_range"
                    blocked_reasons = [str(exc)]
                    normalized_windows = []
                else:
                    status = "sampling_plan_ready_context_only"
                    blocked_reasons = []
                    _, blocked_reasons, normalized_windows = _validate_windows(candidate_windows)
                    if blocked_reasons:
                        status = "blocked_overlapping_windows" if any(
                            reason.startswith("overlapping_oos_windows:") for reason in blocked_reasons
                        ) else "blocked_invalid_window"
        else:
            derived_status, blocked_reasons, normalized_windows = _validate_windows(candidate_windows)
            status = derived_status or "sampling_plan_ready_context_only"
    authority = {
        "non_authoritative": NON_AUTHORITATIVE,
        "can_authorize_execution": CAN_AUTHORIZE_EXECUTION,
        "can_clear_evidence_blockers": CAN_CLEAR_EVIDENCE_BLOCKERS,
        "can_promote_candidate": CAN_PROMOTE_CANDIDATE,
        "evidence_authority": EVIDENCE_AUTHORITY,
    }
    plan_seed = {
        "hypothesis_ref": hypothesis_id,
        "behavior_id": _text(behavior_id),
        "preset_id": _text(preset_id),
        "timeframe": _text(timeframe),
        "window_definitions": normalized_windows,
        "timestamp": timestamp,
    }
    sampling_plan_id = "qsp_" + hashlib.sha256(
        json.dumps(plan_seed, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    ).hexdigest()[:16]
    plan = {
        "schema_version": SCHEMA_VERSION,
        "report_kind": REPORT_KIND,
        "sampling_plan_id": sampling_plan_id,
        "hypothesis_ref": hypothesis_id,
        "behavior_id": _text(behavior_id),
        "preset_id": _text(preset_id),
        "timeframe": _text(timeframe),
        "bounded_source_data_availability": dict(bounded_source_data_availability or {}),
        "proposed_total_validation_range": dict(proposed_total_validation_range or {}),
        "required_oos_evidence_types": _unique_in_order(required_oos_evidence_types),
        "window_definitions": normalized_windows,
        "regime_buckets": [
            {
                "regime_label": _text(bucket.get("regime_label")) if isinstance(bucket, Mapping) else _text(bucket),
                "selection_basis": _text((bucket or {}).get("selection_basis")) if isinstance(bucket, Mapping) else "",
            }
            for bucket in (regime_buckets or [])
        ],
        "null_control_definitions": [dict(item) for item in (null_control_definitions or [])],
        "minimum_trade_requirement": int(minimum_trade_requirement),
        "minimum_window_length": int(minimum_window_length),
        "minimum_warmup_period": int(minimum_warmup_period),
        "known_previous_failed_windows": [dict(item) for item in (known_previous_failed_windows or [])],
        "preregistration_timestamp": timestamp,
        "selection_policy": selection_policy,
        "forbidden_adaptations": _unique_in_order(forbidden_adaptations),
        "authority": authority,
        "status": status,
        "blocked_reasons": blocked_reasons,
    }
    plan["hash"] = compute_sampling_plan_hash(plan)
    return plan


def validate_sampling_plan(plan: Mapping[str, Any]) -> dict[str, Any]:
    rejection_reasons: list[str] = []
    if plan.get("authority", {}).get("non_authoritative") is not True:
        rejection_reasons.append("non_authoritative_must_be_true")
    if plan.get("authority", {}).get("can_authorize_execution") is not False:
        rejection_reasons.append("can_authorize_execution_must_be_false")
    if plan.get("authority", {}).get("can_clear_evidence_blockers") is not False:
        rejection_reasons.append("can_clear_evidence_blockers_must_be_false")
    if plan.get("authority", {}).get("can_promote_candidate") is not False:
        rejection_reasons.append("can_promote_candidate_must_be_false")
    if plan.get("authority", {}).get("evidence_authority") != EVIDENCE_AUTHORITY:
        rejection_reasons.append("invalid_evidence_authority")
    if _contains_outcome_language(plan.get("selection_policy")):
        rejection_reasons.append("selection_policy_contains_outcome_language")
    recomputed_hash = compute_sampling_plan_hash(plan)
    if _text(plan.get("hash")) and _text(plan.get("hash")) != recomputed_hash:
        rejection_reasons.append("hash_mismatch")
    return {
        "valid": not rejection_reasons,
        "rejection_reasons": rejection_reasons,
        "hash": recomputed_hash,
        "schema_version": SCHEMA_VERSION,
    }
