from __future__ import annotations

from pathlib import Path
from typing import Any

import pandas as pd

from packages.qre_data import cache_manifest as cm
from packages.qre_data import source_quality_readiness as sqr

from .contracts import CoverageDecision, DataRequirement, ExperimentContract, content_id


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


def build_data_requirement(contract: ExperimentContract) -> DataRequirement:
    return DataRequirement(
        requirement_id=content_id("qdr", {"experiment_id": contract.experiment_id, "timeframe": contract.timeframe}),
        universe_selector=contract.universe_spec,
        resolved_instrument_ids=tuple(),
        timeframe=contract.timeframe,
        required_fields=contract.required_data_fields,
        required_history_start="unknown",
        required_history_end="unknown",
        minimum_rows=1,
        minimum_assets=1,
        point_in_time_requirement="point_in_time_rows_only",
        corporate_action_requirement="not_applicable_or_canonical",
        session_calendar_requirement="canonical_session_calendar_if_available",
        quality_policy="quality_ready_only",
        identity_policy="identity_resolved_only",
        preferred_sources=("data/cache",),
        content_identity=content_id("qdrp", {"timeframe": contract.timeframe, "universe": contract.universe_spec}),
    )


def resolve_data_plan(repo_root: Path, requirement: DataRequirement) -> CoverageDecision:
    manifest = _load_manifest(repo_root)
    quality = _load_quality(repo_root, manifest)
    source_rows = [dict(row) for row in quality.get("rows", []) if isinstance(row, dict)]
    selected_rows = _choose_rows(manifest, requirement.timeframe)
    if not selected_rows:
        selected_rows = sorted(
            [
                dict(row)
                for row in manifest.get("files", [])
                if isinstance(row, dict)
                and str(row.get("status") or "") == "ready"
                and str(row.get("path") or "") != ""
            ],
            key=lambda row: (
                str(row.get("instrument") or ""),
                str(row.get("timeframe") or ""),
                str(row.get("path") or ""),
            ),
        )
    if not selected_rows:
        return CoverageDecision(
            decision="EXTERNAL_DATA_BOUNDARY",
            reason_codes=("no_ready_cache_rows",),
            selected_data={},
            approved_fetch=True,
            content_identity=content_id("qdc", {"decision": "EXTERNAL_DATA_BOUNDARY"}),
        )
    row = selected_rows[0]
    file_path = repo_root / str(row.get("path") or "")
    if not file_path.is_file():
        return CoverageDecision(
            decision="FETCH_REQUIRED",
            reason_codes=("selected_cache_missing",),
            selected_data={"selected_row": row},
            approved_fetch=True,
            content_identity=content_id("qdc", {"decision": "FETCH_REQUIRED", "path": str(row.get("path") or "")}),
        )
    frame = pd.read_parquet(file_path)
    if "timestamp_utc" in frame.columns:
        frame = frame.copy()
        frame["timestamp_utc"] = pd.to_datetime(frame["timestamp_utc"], utc=True)
        frame = frame.sort_values("timestamp_utc")
        frame = frame.set_index("timestamp_utc")
    decision = "CACHE_READY"
    selected = {
        "selected_row": row,
        "data_path": file_path.as_posix(),
        "row_count": int(len(frame)),
        "frame": frame,
        "quality_summary": quality.get("summary", {}),
        "source_quality_rows": len(source_rows),
    }
    return CoverageDecision(
        decision=decision,
        reason_codes=("ready_cache_row_selected",),
        selected_data=selected,
        approved_fetch=False,
        content_identity=content_id("qdc", {"decision": decision, "path": file_path.as_posix(), "rows": len(frame)}),
    )
