from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

from packages.qre_data import cache_manifest as cm
from packages.qre_data import source_quality_readiness as sqr

from .contracts import (
    CoverageDecision,
    DataRequirement,
    EXECUTION_TIER_COMPILER_ONLY,
    EXECUTION_TIER_EMPIRICAL_SCREENING,
    EXECUTION_TIER_EXECUTOR_SMOKE,
    EXECUTION_TIER_LOCKED_OOS_VALIDATION,
    EXECUTION_TIERS,
    ExperimentContract,
    content_id,
)

TIER_ORDER = {
    EXECUTION_TIER_COMPILER_ONLY: 0,
    EXECUTION_TIER_EXECUTOR_SMOKE: 1,
    EXECUTION_TIER_EMPIRICAL_SCREENING: 2,
    EXECUTION_TIER_LOCKED_OOS_VALIDATION: 3,
}


def _read_json(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        import json

        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception:
        return None
    return payload if isinstance(payload, dict) else None


def _load_manifest(repo_root: Path) -> dict[str, Any]:
    latest = _read_json(repo_root / "logs/qre_data_cache_manifest/latest.json")
    if isinstance(latest, dict) and latest and (latest.get("coverage") or latest.get("files")):
        return latest
    return cm.build_cache_manifest(repo_root=repo_root)


def _load_quality(repo_root: Path, manifest: dict[str, Any]) -> dict[str, Any]:
    latest = _read_json(repo_root / "logs/qre_data_source_quality_readiness/latest.json")
    return latest if isinstance(latest, dict) and latest else sqr.build_source_quality_report(manifest)


def _choose_rows(manifest: dict[str, Any], timeframe: str) -> list[dict[str, Any]]:
    rows = [dict(row) for row in manifest.get("files", []) if isinstance(row, dict)]
    if not rows:
        rows = [dict(row) for row in manifest.get("coverage", []) if isinstance(row, dict)]
    ready = [
        row
        for row in rows
        if str(row.get("timeframe") or "") == timeframe
        and str(row.get("status") or "ready") == "ready"
        and str(row.get("path") or "") != ""
    ]
    return sorted(
        ready,
        key=lambda row: (
            str(row.get("source") or ""),
            str(row.get("instrument") or ""),
            str(row.get("path") or ""),
        ),
    )


def _parse_ts(value: Any) -> datetime | None:
    if not value:
        return None
    text = str(value).replace("Z", "+00:00")
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def _span_days(start: Any, end: Any) -> int:
    start_ts = _parse_ts(start)
    end_ts = _parse_ts(end)
    if start_ts is None or end_ts is None:
        return 0
    return max((end_ts - start_ts).days, 0)


def _string_status(value: Any, *, default: str) -> str:
    text = str(value or "").strip().lower()
    if not text:
        return default
    if text in {"ready", "resolved", "pass", "true", "research_ready"}:
        return "ready"
    if text in {"blocked", "fail", "false", "quarantined"}:
        return "blocked"
    if text in {"ambiguous", "unknown", "manual", "manual_research_only"}:
        return "ambiguous"
    return text


def _infer_source_quality_status(quality_payload: dict[str, Any], row: dict[str, Any]) -> str:
    summary = quality_payload.get("summary") if isinstance(quality_payload, dict) else {}
    rows = quality_payload.get("rows") if isinstance(quality_payload, dict) else []
    source = str(row.get("source") or "")
    instrument = str(row.get("instrument") or "")
    timeframe = str(row.get("timeframe") or "")
    for quality_row in rows if isinstance(rows, list) else []:
        if not isinstance(quality_row, dict):
            continue
        if (
            str(quality_row.get("source") or "") == source
            and str(quality_row.get("instrument") or "") == instrument
            and str(quality_row.get("timeframe") or "") == timeframe
        ):
            return _string_status(
                quality_row.get("effective_research_quality_status")
                or quality_row.get("source_quality_status")
                or quality_row.get("status"),
                default="unknown",
            )
    return _string_status(
        (summary or {}).get("status")
        or (summary or {}).get("effective_research_quality_status")
        or ("ready" if (summary or {}).get("research_ready") is True else "blocked"),
        default="unknown",
    )


def _infer_identity_status(row: dict[str, Any], quality_payload: dict[str, Any]) -> str:
    candidate = row.get("identity_status") or row.get("identity_readiness")
    if candidate:
        return _string_status(candidate, default="unknown")
    summary = quality_payload.get("summary") if isinstance(quality_payload, dict) else {}
    return _string_status((summary or {}).get("identity_status"), default="ready")


def _infer_validation_rows(row_count: int) -> int:
    return max(row_count // 5, 0)


def _infer_locked_oos_rows(row_count: int) -> int:
    return max(row_count // 10, 0)


def _infer_expected_activity(row_count: int, timeframe: str) -> int:
    if timeframe.endswith("d"):
        return row_count // 20
    if timeframe.endswith("h"):
        return row_count // 40
    return max(row_count // 50, 0)


def _admissible_tier(
    *,
    row_count: int,
    span_days: int,
    source_quality: str,
    identity_status: str,
    has_path: bool,
    required: DataRequirement,
) -> tuple[str, list[str]]:
    reasons: list[str] = []
    if not has_path:
        return EXECUTION_TIER_COMPILER_ONLY, ["selected_cache_missing"]
    if source_quality != "ready":
        reasons.append("source_quality_not_research_ready")
    if identity_status != "ready":
        reasons.append("identity_not_resolved")
    validation_rows = _infer_validation_rows(row_count)
    locked_oos_rows = _infer_locked_oos_rows(row_count)
    expected_activity = _infer_expected_activity(row_count, required.timeframe)
    if row_count < required.minimum_rows:
        reasons.append("minimum_rows_not_met")
    if span_days < 30:
        reasons.append("history_span_too_short_for_empirical")
    if expected_activity < required.minimum_expected_trades:
        reasons.append("expected_activity_too_low")
    if reasons:
        return EXECUTION_TIER_EXECUTOR_SMOKE, reasons
    if validation_rows < required.minimum_validation_rows:
        return EXECUTION_TIER_EXECUTOR_SMOKE, ["validation_rows_insufficient"]
    if locked_oos_rows < required.minimum_locked_oos_rows or expected_activity < required.minimum_locked_oos_activity:
        return EXECUTION_TIER_EMPIRICAL_SCREENING, ["locked_oos_not_available"]
    return EXECUTION_TIER_LOCKED_OOS_VALIDATION, []


def build_data_requirement(contract: ExperimentContract) -> DataRequirement:
    requested_tier = contract.requested_execution_tier
    minimum_rows = 5 if requested_tier == EXECUTION_TIER_EXECUTOR_SMOKE else 60
    minimum_validation_rows = 0 if requested_tier == EXECUTION_TIER_EXECUTOR_SMOKE else 20
    minimum_locked_oos_rows = 0 if requested_tier != EXECUTION_TIER_LOCKED_OOS_VALIDATION else 20
    minimum_expected_trades = 1 if requested_tier == EXECUTION_TIER_EXECUTOR_SMOKE else 3
    minimum_locked_oos_activity = 0 if requested_tier != EXECUTION_TIER_LOCKED_OOS_VALIDATION else 2
    return DataRequirement(
        requirement_id=content_id(
            "qdr",
            {"experiment_id": contract.experiment_id, "timeframe": contract.timeframe, "tier": requested_tier},
        ),
        universe_selector=contract.universe_spec,
        resolved_instrument_ids=tuple(),
        timeframe=contract.timeframe,
        required_fields=contract.required_data_fields,
        required_history_start="unknown",
        required_history_end="unknown",
        minimum_rows=minimum_rows,
        minimum_assets=1,
        requested_execution_tier=requested_tier,
        minimum_history_span="30d" if requested_tier != EXECUTION_TIER_EXECUTOR_SMOKE else "5d",
        minimum_expected_signals=minimum_expected_trades,
        minimum_expected_trades=minimum_expected_trades,
        minimum_validation_rows=minimum_validation_rows,
        minimum_locked_oos_rows=minimum_locked_oos_rows,
        minimum_locked_oos_activity=minimum_locked_oos_activity,
        required_source_quality="research_ready",
        required_identity_status="resolved",
        required_cost_model=contract.transaction_cost_model,
        required_slippage_model=contract.slippage_model,
        point_in_time_requirement="point_in_time_rows_only",
        corporate_action_requirement="not_applicable_or_canonical",
        session_calendar_requirement="canonical_session_calendar_if_available",
        quality_policy="quality_ready_only",
        identity_policy="identity_resolved_only",
        preferred_sources=("data/cache",),
        content_identity=content_id(
            "qdrp",
            {"timeframe": contract.timeframe, "universe": contract.universe_spec, "tier": requested_tier},
        ),
    )


def _inventory_rows(repo_root: Path, requirement: DataRequirement) -> tuple[dict[str, Any], ...]:
    manifest = _load_manifest(repo_root)
    quality = _load_quality(repo_root, manifest)
    rows = _choose_rows(manifest, requirement.timeframe)
    inventory: list[dict[str, Any]] = []
    for row in rows:
        file_path = repo_root / str(row.get("path") or "")
        row_count = int(row.get("row_count") or 0)
        span_days = _span_days(row.get("min_timestamp_utc"), row.get("max_timestamp_utc"))
        source_quality = _infer_source_quality_status(quality, row)
        identity_status = _infer_identity_status(row, quality)
        highest_tier, downgrade = _admissible_tier(
            row_count=row_count,
            span_days=span_days,
            source_quality=source_quality,
            identity_status=identity_status,
            has_path=file_path.is_file(),
            required=requirement,
        )
        inventory.append(
            {
                "dataset_identity": content_id(
                    "qds",
                    {
                        "path": str(row.get("path") or ""),
                        "content_hash": str(row.get("content_hash") or ""),
                    },
                ),
                "asset_count": 1,
                "row_count": row_count,
                "history_span_days": span_days,
                "timeframe": str(row.get("timeframe") or ""),
                "source_quality_status": source_quality,
                "source_identity_status": identity_status,
                "validation_rows": _infer_validation_rows(row_count),
                "locked_oos_rows": _infer_locked_oos_rows(row_count),
                "estimated_activity": _infer_expected_activity(row_count, requirement.timeframe),
                "highest_admissible_tier": highest_tier,
                "tier_downgrade_reasons": tuple(downgrade),
                "row_integrity_status": "ready" if row_count > 0 else "blocked",
                "cache_integrity_status": "ready" if file_path.is_file() else "blocked",
                "campaign_scoped_quality_status": "ready" if row_count > 0 else "blocked",
                "effective_research_quality_status": source_quality if source_quality == "ready" and identity_status == "ready" else "blocked",
                "dataset_path": str(row.get("path") or ""),
                "instrument": str(row.get("instrument") or ""),
                "source": str(row.get("source") or ""),
                "__selected_row": row,
            }
        )
    return tuple(inventory)


def resolve_data_plan(repo_root: Path, requirement: DataRequirement) -> CoverageDecision:
    inventory = _inventory_rows(repo_root, requirement)
    if not inventory:
        return CoverageDecision(
            decision="EXTERNAL_DATA_BOUNDARY",
            coverage_decision="EXTERNAL_DATA_BOUNDARY",
            requested_execution_tier=requirement.requested_execution_tier,
            admissible_execution_tier=EXECUTION_TIER_COMPILER_ONLY,
            tier_downgrade_reasons=("no_ready_cache_rows",),
            reason_codes=("no_ready_cache_rows",),
            selected_data={},
            approved_fetch=True,
            dataset_inventory=tuple(),
            content_identity=content_id("qdc", {"decision": "EXTERNAL_DATA_BOUNDARY"}),
        )

    selected = sorted(
        inventory,
        key=lambda row: (
            -TIER_ORDER.get(str(row.get("highest_admissible_tier") or ""), -1),
            0 if str(row.get("source_quality_status") or "") == "ready" else 1,
            0 if str(row.get("source_identity_status") or "") == "ready" else 1,
            -int(row.get("history_span_days") or 0),
            -int(row.get("estimated_activity") or 0),
            -int(row.get("locked_oos_rows") or 0),
            len(tuple(row.get("tier_downgrade_reasons") or ())),
            int(row.get("row_count") or 0),
            str((row.get("selected_row") or {}).get("path") or ""),
        ),
    )[0]
    row = dict(selected.get("__selected_row") or {})
    file_path = repo_root / str(row.get("path") or "")
    frame = None
    if file_path.is_file():
        frame = pd.read_parquet(file_path)
        if "timestamp_utc" in frame.columns:
            frame = frame.copy()
            frame["timestamp_utc"] = pd.to_datetime(frame["timestamp_utc"], utc=True)
            frame = frame.sort_values("timestamp_utc")
            frame = frame.set_index("timestamp_utc")
    admissible_tier = str(selected.get("highest_admissible_tier") or EXECUTION_TIER_COMPILER_ONLY)
    downgrade = tuple(str(item) for item in tuple(selected.get("tier_downgrade_reasons") or ()))
    decision = "CACHE_READY" if admissible_tier != EXECUTION_TIER_COMPILER_ONLY and file_path.is_file() else "FETCH_REQUIRED"
    reason_codes = ("ready_cache_row_selected",) if decision == "CACHE_READY" else ("selected_cache_missing",)
    selected_data = {
        "selected_row": row,
        "data_path": file_path.as_posix(),
        "row_count": int(selected.get("row_count") or 0),
        "history_span_days": int(selected.get("history_span_days") or 0),
        "frame": frame,
        "row_integrity_status": str(selected.get("row_integrity_status") or ""),
        "cache_integrity_status": str(selected.get("cache_integrity_status") or ""),
        "source_quality_status": str(selected.get("source_quality_status") or ""),
        "source_identity_status": str(selected.get("source_identity_status") or ""),
        "campaign_scoped_quality_status": str(selected.get("campaign_scoped_quality_status") or ""),
        "effective_research_quality_status": str(selected.get("effective_research_quality_status") or ""),
        "validation_rows": int(selected.get("validation_rows") or 0),
        "locked_oos_rows": int(selected.get("locked_oos_rows") or 0),
        "estimated_activity": int(selected.get("estimated_activity") or 0),
    }
    return CoverageDecision(
        decision=decision,
        coverage_decision=decision,
        requested_execution_tier=requirement.requested_execution_tier,
        admissible_execution_tier=admissible_tier,
        tier_downgrade_reasons=downgrade,
        reason_codes=reason_codes,
        selected_data=selected_data,
        approved_fetch=not file_path.is_file(),
        dataset_inventory=inventory,
        content_identity=content_id(
            "qdc",
            {
                "decision": decision,
                "path": file_path.as_posix(),
                "admissible_execution_tier": admissible_tier,
                "requested_execution_tier": requirement.requested_execution_tier,
            },
        ),
    )
