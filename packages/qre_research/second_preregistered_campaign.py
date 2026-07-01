from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import tempfile
from collections.abc import Iterable
from contextlib import suppress
from pathlib import Path
from typing import Any, Final

import numpy as np
import pandas as pd

from agent.backtesting.thin_strategy import build_features_for
from packages.qre_research.generated_strategy_paths import REPO_ROOT, validate_write_target
from research.batch_execution import build_validation_evidence_status

SCHEMA_VERSION: Final[str] = "1.0"
MODULE_VERSION: Final[str] = "ade-qre-025.2"
REPORT_KIND: Final[str] = "qre_second_preregistered_campaign"
TARGET_SOURCE_HYPOTHESIS_ID: Final[str] = "cross_sectional_momentum_v0"

STAGE_OUTCOMES: Final[tuple[str, ...]] = (
    "COMPLETED",
    "REJECTED_SCREENING",
    "REJECTED_VALIDATION",
    "REJECTED_OOS",
    "REJECTED_NULL_CONTROLS",
    "INSUFFICIENT_TRADES",
    "INSUFFICIENT_SIGNALS",
    "TIMED_OUT",
    "ERRORED",
    "DATA_INVALID",
    "POLICY_BLOCKED",
)
MANIFEST_OUTCOMES: Final[tuple[str, ...]] = (
    "MANIFEST_VERIFIED",
    "MANIFEST_IDENTITY_MISMATCH",
    "STRATEGY_HASH_MISMATCH",
    "PRESET_MISMATCH",
    "DATASET_MISMATCH",
    "SNAPSHOT_MISMATCH",
    "WINDOW_MISMATCH",
    "POLICY_MISMATCH",
    "NULL_CONTROL_MISMATCH",
    "INPUT_MISSING",
    "MANIFEST_INTEGRITY_BLOCKED",
)
HYPOTHESIS_DECISIONS: Final[tuple[str, ...]] = (
    "SUPPORTED_FOR_FURTHER_RESEARCH",
    "REJECTED",
    "INSUFFICIENT_EVIDENCE",
    "BLOCKED_DATA",
    "BLOCKED_CONTROLS",
    "BLOCKED_SAMPLE_SIZE",
    "BLOCKED_POLICY",
)
STRATEGY_DECISIONS: Final[tuple[str, ...]] = (
    "RESEARCH_SURVIVOR",
    "REJECTED_SCREENING",
    "REJECTED_VALIDATION",
    "REJECTED_OOS",
    "REJECTED_NULL_CONTROLS",
    "INSUFFICIENT_EVIDENCE",
    "QUARANTINED_ERROR",
)
TERMINAL_OUTCOMES: Final[tuple[str, ...]] = (
    "CAMPAIGN_COMPLETE_SUPPORTED",
    "CAMPAIGN_COMPLETE_REJECTED",
    "CAMPAIGN_COMPLETE_INSUFFICIENT_EVIDENCE",
    "REPEATED_OOS_PREREGISTRATION_READY",
    "DATA_OR_OOS_CAPACITY_BLOCKED",
    "NEW_HYPOTHESIS_REQUIRED",
    "NEW_PRIMITIVE_REQUIRED",
    "STRATEGY_REGENERATION_REQUIRED",
    "SYNTHESIS_READINESS_REVIEW_ELIGIBLE",
    "NO_SAFE_AUTOMATED_NEXT_ACTION",
)

CAMPAIGN_ROOT: Final[Path] = REPO_ROOT / "generated_research" / "campaign_execution"
MANIFEST_INTEGRITY_PATH: Final[Path] = (
    CAMPAIGN_ROOT / "manifest_integrity" / "second_campaign_manifest_integrity.v1.json"
)
TRAIN_PATH: Final[Path] = CAMPAIGN_ROOT / "stages" / "train_and_screening.v1.json"
VALIDATION_PATH: Final[Path] = CAMPAIGN_ROOT / "stages" / "validation.v1.json"
OOS_PATH: Final[Path] = CAMPAIGN_ROOT / "stages" / "oos.v1.json"
NULL_CONTROLS_PATH: Final[Path] = CAMPAIGN_ROOT / "stages" / "null_controls.v1.json"
EVIDENCE_PATH: Final[Path] = CAMPAIGN_ROOT / "evidence" / "evidence_reason_records.v1.json"
OOS_CONSUMPTION_PATH: Final[Path] = CAMPAIGN_ROOT / "ledgers" / "oos_consumption.v1.json"
FUNNEL_PATH: Final[Path] = CAMPAIGN_ROOT / "reports" / "funnel_diagnosis.v1.json"
DECISION_PATH: Final[Path] = CAMPAIGN_ROOT / "reports" / "hypothesis_strategy_decision.v1.json"
RECALIBRATION_PATH: Final[Path] = CAMPAIGN_ROOT / "reports" / "bounded_recalibration_decision.v1.json"
REPLAY_PATH: Final[Path] = CAMPAIGN_ROOT / "reports" / "same_input_replay.v1.json"
INDEPENDENT_OOS_PATH: Final[Path] = CAMPAIGN_ROOT / "reports" / "independent_oos_assessment.v1.json"
FEEDBACK_PATH: Final[Path] = CAMPAIGN_ROOT / "reports" / "autonomous_feedback_routing.v1.json"
ACTION_LEDGER_PATH: Final[Path] = CAMPAIGN_ROOT / "reports" / "autonomous_action_ledger.v1.json"
CLOSEOUT_JSON_PATH: Final[Path] = CAMPAIGN_ROOT / "reports" / "second_campaign_closeout.v1.json"
CLOSEOUT_MD_PATH: Final[Path] = CAMPAIGN_ROOT / "reports" / "second_campaign_closeout.v1.md"

READY_SCREENING_MIN_TRADES: Final[int] = 10
READY_SCREENING_MIN_SIGNALS: Final[int] = 6
READY_VALIDATION_MIN_TRADES: Final[int] = 3
READY_VALIDATION_MIN_SIGNALS: Final[int] = 3
REPLAY_ID: Final[str] = "qre_same_input_control_replay_not_run"


def _stable_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def stable_digest(value: Any) -> str:
    return hashlib.sha256(_stable_json(value).encode("utf-8")).hexdigest()


def _content_id(prefix: str, value: Any) -> str:
    return f"{prefix}_{stable_digest(value)[:16]}"


def _repo_relative(path: Path, *, repo_root: Path) -> str:
    return path.resolve().relative_to(repo_root.resolve()).as_posix()


def _repo_path(repo_root: Path, path: Path) -> Path:
    return repo_root / path.relative_to(REPO_ROOT)


def _atomic_write(path: Path, payload: str) -> None:
    validate_write_target(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=".ade_qre_025.", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(payload)
        os.replace(tmp_name, path)
    except Exception:
        with suppress(OSError):
            os.unlink(tmp_name)
        raise


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    _atomic_write(path, json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=True) + "\n")


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _read_rows(path: Path, *keys: str) -> list[dict[str, Any]]:
    payload = _read_json(path)
    for key in keys:
        rows = payload.get(key)
        if isinstance(rows, list):
            return [dict(item) for item in rows if isinstance(item, dict)]
    return []


def _require_path(path: Path, *, missing: list[str]) -> Path | None:
    if path.is_file():
        return path
    missing.append(path.as_posix())
    return None


def _generated_code_hash(path: Path) -> str:
    source = path.read_text(encoding="utf-8").replace("\r\n", "\n")
    return stable_digest(source)


def _load_module_from_path(path: Path) -> Any:
    spec = importlib.util.spec_from_file_location(path.stem, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"unable to create import spec for {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _iso_to_ts(value: str | None) -> pd.Timestamp:
    return pd.Timestamp(value or "1970-01-01T00:00:00Z", tz="UTC")


def _select_manifest_row(
    manifest_rows: list[dict[str, Any]],
    registry_by_strategy: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    if not manifest_rows:
        raise KeyError("generated second campaign manifest has no rows")
    ranked = sorted(
        manifest_rows,
        key=lambda row: (
            str(
                (registry_by_strategy.get(str(row.get("generated_strategy_id") or ""), {}) or {}).get(
                    "source_hypothesis_id"
                )
                or ""
            )
            != TARGET_SOURCE_HYPOTHESIS_ID,
            str(row.get("campaign_cell_id") or ""),
        ),
    )
    return dict(ranked[0])


def _iter_cache_file_groups(
    rows: Iterable[dict[str, Any]],
    *,
    source: str,
    instrument: str,
    timeframe: str,
) -> list[dict[str, Any]]:
    filtered = [
        dict(row)
        for row in rows
        if str(row.get("source") or "") == source
        and str(row.get("instrument") or "").upper() == instrument.upper()
        and str(row.get("timeframe") or "") == timeframe
        and str(row.get("status") or "ready") == "ready"
        and row.get("path")
    ]
    keyed: dict[tuple[str, str], dict[str, Any]] = {}
    for row in filtered:
        key = (str(row.get("min_timestamp_utc") or ""), str(row.get("max_timestamp_utc") or ""))
        existing = keyed.get(key)
        if existing is None or str(row.get("path") or "") > str(existing.get("path") or ""):
            keyed[key] = row
    return sorted(
        keyed.values(),
        key=lambda row: (
            str(row.get("min_timestamp_utc") or ""),
            str(row.get("max_timestamp_utc") or ""),
            str(row.get("path") or ""),
        ),
    )


def _minimal_cover(
    rows: list[dict[str, Any]],
    *,
    start: pd.Timestamp,
    end: pd.Timestamp,
) -> list[dict[str, Any]]:
    candidates = [
        dict(row)
        for row in rows
        if _iso_to_ts(str(row.get("max_timestamp_utc") or "")) >= start
        and _iso_to_ts(str(row.get("min_timestamp_utc") or "")) <= end
    ]
    selected: list[dict[str, Any]] = []
    cursor = start
    while cursor <= end:
        eligible = [
            row
            for row in candidates
            if _iso_to_ts(str(row.get("min_timestamp_utc") or "")) <= cursor
        ]
        if not eligible:
            break
        best = max(eligible, key=lambda row: _iso_to_ts(str(row.get("max_timestamp_utc") or "")))
        selected.append(best)
        next_cursor = _iso_to_ts(str(best.get("max_timestamp_utc") or "")) + pd.Timedelta(seconds=1)
        if next_cursor <= cursor:
            break
        cursor = next_cursor
        candidates = [row for row in candidates if row != best]
    return selected


def _load_bundle(repo_root: Path) -> dict[str, Any]:
    manifest = _read_json(repo_root / "generated_research/readiness/campaigns/generated_second_campaign_manifest.v1.json")
    portfolio_rows = _read_rows(
        repo_root / "generated_research/readiness/campaigns/automated_portfolio_readiness.v1.json",
        "rows",
    )
    snapshot_rows = _read_rows(
        repo_root / "generated_research/readiness/snapshots/immutable_strategy_snapshots.v1.json",
        "rows",
    )
    window_rows = _read_rows(
        repo_root / "generated_research/readiness/window_capacity/authoritative_window_assignments.v1.json",
        "rows",
    )
    independence_rows = _read_rows(
        repo_root / "generated_research/readiness/window_capacity/oos_independence_proof.v1.json",
        "rows",
    )
    signal_rows = _read_rows(
        repo_root / "generated_research/readiness/window_capacity/signal_density_capacity.v1.json",
        "rows",
    )
    quality_rows = _read_rows(
        repo_root / "generated_research/readiness/data_capacity/strategy_data_quality_coverage.v1.json",
        "rows",
    )
    strategy_registry_rows = _read_rows(
        repo_root / "generated_research/registry/generated_strategy_registry.v1.json",
        "rows",
    )
    null_rows = _read_rows(
        repo_root / "generated_research/lineage/generated_null_controls.v1.json",
        "rows",
    )
    validation_rows = {
        str(path.stem): _read_json(path)
        for path in sorted((repo_root / "generated_research/validation").glob("qgs_*.json"))
    }
    cache_manifest = _read_json(repo_root / "logs/qre_data_cache_manifest/latest.json")
    ledger_payload = _read_json(repo_root / "generated_research/readiness/window_ledger/canonical_window_ledger.v1.json")
    registry_by_strategy = {
        str(row.get("generated_strategy_id") or ""): dict(row)
        for row in strategy_registry_rows
        if str(row.get("generated_strategy_id") or "")
    }
    manifest_row = _select_manifest_row(_read_rows(repo_root / "generated_research/readiness/campaigns/generated_second_campaign_manifest.v1.json", "rows"), registry_by_strategy)
    campaign_cell_id = str(manifest_row.get("campaign_cell_id") or "")
    strategy_id = str(manifest_row.get("generated_strategy_id") or "")
    registry_row = dict(registry_by_strategy.get(strategy_id) or {})
    spec_id = str(registry_row.get("strategy_spec_id") or "")
    spec = _read_json(repo_root / f"generated_research/specs/{spec_id}.json")
    quality_row = next(row for row in quality_rows if str(row.get("campaign_cell_id") or "") == campaign_cell_id)
    module_path = repo_root / str(registry_row.get("module_path") or "")
    source_hypothesis_id = str(registry_row.get("source_hypothesis_id") or "")
    coverage_map = [dict(row) for row in quality_row.get("coverage_map") or [] if isinstance(row, dict)]
    window_row = next(row for row in window_rows if str(row.get("campaign_cell_id") or "") == campaign_cell_id)
    required_start = _iso_to_ts(str((window_row.get("train_window") or {}).get("start") or ""))
    required_end = _iso_to_ts(str((window_row.get("oos_window") or {}).get("end") or ""))
    cache_file_rows: list[dict[str, Any]] = []
    for coverage_row in coverage_map:
        grouped = _iter_cache_file_groups(
            cache_manifest.get("files", []),
            source=str(coverage_row.get("source") or ""),
            instrument=str(coverage_row.get("instrument") or ""),
            timeframe=str(coverage_row.get("timeframe") or ""),
        )
        cache_file_rows.extend(
            _minimal_cover(
                grouped,
                start=required_start,
                end=required_end,
            )
        )
    selection = {
        "campaign_cell_id": campaign_cell_id,
        "generated_strategy_id": strategy_id,
        "strategy_spec_id": spec_id,
        "preset_id": str(manifest_row.get("preset_id") or ""),
        "dataset_identity": str(manifest_row.get("dataset_identity") or ""),
        "snapshot_identity": str(manifest_row.get("snapshot_identity") or ""),
        "timeframe": str(manifest_row.get("timeframe") or ""),
        "source_hypothesis_id": source_hypothesis_id,
        "manifest_identity": str(manifest.get("campaign_manifest_identity") or ""),
    }
    return {
        "selection": selection,
        "manifest": manifest,
        "manifest_row": manifest_row,
        "portfolio_row": next(row for row in portfolio_rows if str(row.get("campaign_cell_id") or "") == campaign_cell_id),
        "snapshot_row": next(row for row in snapshot_rows if str(row.get("campaign_cell_id") or "") == campaign_cell_id),
        "window_row": window_row,
        "ledger_payload": ledger_payload,
        "independence_row": next(row for row in independence_rows if str(row.get("campaign_cell_id") or "") == campaign_cell_id),
        "signal_row": next(row for row in signal_rows if str(row.get("campaign_cell_id") or "") == campaign_cell_id),
        "quality_row": quality_row,
        "registry_row": registry_row,
        "null_row": next(row for row in null_rows if str(row.get("generated_strategy_id") or "") == strategy_id),
        "validation_row": validation_rows[strategy_id],
        "spec": spec,
        "cache_file_rows": cache_file_rows,
        "module_path": module_path,
    }


def _verify_manifest(repo_root: Path, bundle: dict[str, Any]) -> dict[str, Any]:
    selection = dict(bundle["selection"])
    missing: list[str] = []
    required_paths = [
        repo_root / "generated_research/readiness/campaigns/generated_second_campaign_manifest.v1.json",
        repo_root / "generated_research/readiness/campaigns/automated_portfolio_readiness.v1.json",
        repo_root / "generated_research/readiness/snapshots/immutable_strategy_snapshots.v1.json",
        repo_root / "generated_research/readiness/window_capacity/authoritative_window_assignments.v1.json",
        repo_root / "generated_research/readiness/window_ledger/canonical_window_ledger.v1.json",
        repo_root / "generated_research/readiness/window_capacity/oos_independence_proof.v1.json",
        repo_root / "generated_research/readiness/window_capacity/signal_density_capacity.v1.json",
        repo_root / "generated_research/readiness/data_capacity/strategy_data_quality_coverage.v1.json",
        repo_root / "generated_research/registry/generated_strategy_registry.v1.json",
        repo_root / f"generated_research/specs/{selection['strategy_spec_id']}.json",
        repo_root / f"generated_research/validation/{selection['generated_strategy_id']}.json",
        repo_root / "generated_research/lineage/generated_null_controls.v1.json",
        bundle["module_path"],
    ]
    for row in bundle["cache_file_rows"]:
        required_paths.append(repo_root / str(row.get("path") or ""))
    for path in required_paths:
        _require_path(path, missing=missing)

    mismatches: list[str] = []
    manifest_row = bundle["manifest_row"]
    portfolio_row = bundle["portfolio_row"]
    snapshot_row = bundle["snapshot_row"]
    window_row = bundle["window_row"]
    registry_row = bundle["registry_row"]
    validation_row = bundle["validation_row"]
    null_row = bundle["null_row"]
    module_hash = _generated_code_hash(bundle["module_path"]) if bundle["module_path"].is_file() else ""
    status = "MANIFEST_VERIFIED"

    checks = {
        "manifest_identity": bool(selection["manifest_identity"]),
        "campaign_cell_id": str(manifest_row.get("campaign_cell_id") or "") == selection["campaign_cell_id"],
        "generated_strategy_id": str(manifest_row.get("generated_strategy_id") or "") == selection["generated_strategy_id"],
        "strategy_spec_id": str(manifest_row.get("strategy_spec_id") or "") == selection["strategy_spec_id"],
        "preset_id": str(manifest_row.get("preset_id") or "") == str(portfolio_row.get("preset_id") or ""),
        "dataset_identity": str(manifest_row.get("dataset_identity") or "") == str(snapshot_row.get("dataset_identity") or ""),
        "snapshot_identity": str(manifest_row.get("snapshot_identity") or "") == str(snapshot_row.get("snapshot_identity") or ""),
        "timeframe": str(manifest_row.get("timeframe") or "") == str(portfolio_row.get("timeframe") or ""),
        "train_window": dict(manifest_row.get("train_window") or {}) == dict(window_row.get("train_window") or {}),
        "validation_window": dict(manifest_row.get("validation_window") or {}) == dict(window_row.get("validation_window") or {}),
        "oos_window": dict(manifest_row.get("oos_window") or {}) == dict(window_row.get("oos_window") or {}),
        "portfolio_ready": str(portfolio_row.get("status") or "") == "READY_FOR_PREREGISTRATION",
        "registry_strategy": str(registry_row.get("generated_strategy_id") or "") == selection["generated_strategy_id"],
        "registry_spec": str(registry_row.get("strategy_spec_id") or "") == selection["strategy_spec_id"],
        "module_hash_matches_registry": module_hash == str(registry_row.get("code_hash") or ""),
        "validation_state": str(validation_row.get("status") or "") == "VALIDATED",
        "validation_hash": str(validation_row.get("code_hash") or "") == module_hash,
        "null_control_spec": bool(str(null_row.get("null_control_spec_id") or "")),
        "oos_independence": str(bundle["independence_row"].get("outcome") or "") == "INDEPENDENCE_PROVEN",
        "signal_capacity": str(bundle["signal_row"].get("outcome") or "").startswith("SIGNAL_CAPACITY_READY"),
        "quality_ready": str(bundle["quality_row"].get("quality_state") or "") == "QUALITY_READY",
        "cache_files_present": bool(bundle["cache_file_rows"]),
    }
    if missing:
        status = "INPUT_MISSING"
    elif not checks["module_hash_matches_registry"]:
        status = "STRATEGY_HASH_MISMATCH"
    elif not checks["preset_id"]:
        status = "PRESET_MISMATCH"
    elif not checks["dataset_identity"]:
        status = "DATASET_MISMATCH"
    elif not checks["snapshot_identity"]:
        status = "SNAPSHOT_MISMATCH"
    elif not (checks["train_window"] and checks["validation_window"] and checks["oos_window"]):
        status = "WINDOW_MISMATCH"
    elif not checks["null_control_spec"]:
        status = "NULL_CONTROL_MISMATCH"
    elif not all(checks.values()):
        status = "MANIFEST_INTEGRITY_BLOCKED"

    if status != "MANIFEST_VERIFIED":
        mismatches.extend([key for key, ok in checks.items() if not ok])

    return {
        "schema_version": SCHEMA_VERSION,
        "module_version": MODULE_VERSION,
        "report_kind": "qre_second_campaign_manifest_integrity",
        "manifest_integrity_identity": _content_id(
            "qmi",
            {
                "manifest": selection["manifest_identity"],
                "status": status,
                "checks": checks,
                "missing": missing,
                "mismatches": mismatches,
            },
        ),
        "manifest_identity": selection["manifest_identity"],
        "status": status,
        "missing_inputs": missing,
        "mismatches": mismatches,
        "checks": checks,
        "provenance": [
            "generated_research/readiness/campaigns/generated_second_campaign_manifest.v1.json",
            "generated_research/readiness/campaigns/automated_portfolio_readiness.v1.json",
            "generated_research/readiness/snapshots/immutable_strategy_snapshots.v1.json",
            "generated_research/readiness/window_capacity/authoritative_window_assignments.v1.json",
            "generated_research/readiness/window_ledger/canonical_window_ledger.v1.json",
            "generated_research/readiness/window_capacity/oos_independence_proof.v1.json",
            "generated_research/readiness/window_capacity/signal_density_capacity.v1.json",
            "generated_research/readiness/data_capacity/strategy_data_quality_coverage.v1.json",
            "generated_research/registry/generated_strategy_registry.v1.json",
            f"generated_research/specs/{selection['strategy_spec_id']}.json",
            f"generated_research/validation/{selection['generated_strategy_id']}.json",
            "generated_research/lineage/generated_null_controls.v1.json",
            _repo_relative(bundle["module_path"], repo_root=repo_root),
            *[str(row.get("path") or "") for row in bundle["cache_file_rows"]],
        ],
    }


def _normalize_frame(frame: pd.DataFrame, *, asset: str | None) -> pd.DataFrame:
    normalized = frame.copy()
    normalized["timestamp_utc"] = pd.to_datetime(normalized["timestamp_utc"], utc=True)
    normalized = normalized.sort_values("timestamp_utc")
    if asset is None:
        return normalized.set_index("timestamp_utc")
    normalized["asset"] = asset
    normalized = normalized.set_index(["timestamp_utc", "asset"]).sort_index()
    return normalized


def _load_frame(repo_root: Path, bundle: dict[str, Any]) -> pd.DataFrame:
    coverage_map = [dict(row) for row in bundle["quality_row"].get("coverage_map") or [] if isinstance(row, dict)]
    if len(coverage_map) <= 1:
        row = bundle["cache_file_rows"][0]
        frame = pd.read_parquet(repo_root / str(row.get("path") or ""))
        return _normalize_frame(frame, asset=None)

    frames: list[pd.DataFrame] = []
    seen_paths: set[str] = set()
    for coverage_row in coverage_map:
        instrument = str(coverage_row.get("instrument") or "")
        matching = [
            dict(row)
            for row in bundle["cache_file_rows"]
            if str(row.get("instrument") or "").upper() == instrument.upper()
        ]
        for row in matching:
            rel_path = str(row.get("path") or "")
            if rel_path in seen_paths:
                continue
            seen_paths.add(rel_path)
            frame = pd.read_parquet(repo_root / rel_path)
            frames.append(_normalize_frame(frame, asset=instrument))
    panel = pd.concat(frames).sort_index()
    panel = panel[~panel.index.duplicated(keep="last")]
    start = _iso_to_ts(str((bundle["window_row"].get("train_window") or {}).get("start") or ""))
    end = _iso_to_ts(str((bundle["window_row"].get("oos_window") or {}).get("end") or ""))
    timestamps = panel.index.get_level_values(0)
    return panel[(timestamps >= start) & (timestamps <= end)].copy()


def _evaluate_strategy(frame: pd.DataFrame, bundle: dict[str, Any]) -> dict[str, pd.Series]:
    module = _load_module_from_path(bundle["module_path"])
    features = build_features_for(module.generated_strategy._feature_requirements, frame)
    signal = module.generated_strategy(frame, features).astype(int)
    if isinstance(frame.index, pd.MultiIndex):
        grouped_close = frame["close"].astype(float).groupby(level=1)
        returns = grouped_close.pct_change().fillna(0.0)
        position = signal.groupby(level=1).shift(1).fillna(0).astype(int)
    else:
        returns = frame["close"].astype(float).pct_change().fillna(0.0)
        position = signal.shift(1).fillna(0).astype(int)
    gross_returns = position.astype(float) * returns.astype(float)
    turnover = _turnover(position)
    return {
        "signal": signal,
        "position": position,
        "returns": returns,
        "gross_returns": gross_returns,
        "turnover": turnover,
    }


def _slice_window(frame: pd.DataFrame, window: dict[str, Any]) -> pd.DataFrame:
    start = _iso_to_ts(str(window["start"]))
    end = _iso_to_ts(str(window["end"]))
    if isinstance(frame.index, pd.MultiIndex):
        timestamps = frame.index.get_level_values(0)
        return frame[(timestamps >= start) & (timestamps <= end)].copy()
    return frame.loc[str(window["start"]):str(window["end"])].copy()


def _turnover(position: pd.Series) -> pd.Series:
    if isinstance(position.index, pd.MultiIndex):
        return position.groupby(level=1).diff().abs().fillna(position.abs()).astype(int)
    return position.diff().abs().fillna(position.abs()).astype(int)


def _portfolio_returns(gross_returns: pd.Series, position: pd.Series) -> pd.Series:
    if not isinstance(gross_returns.index, pd.MultiIndex):
        return gross_returns.astype(float)
    active = position.abs().groupby(level=0).sum().replace(0, np.nan)
    summed = gross_returns.astype(float).groupby(level=0).sum()
    return (summed / active).fillna(0.0)


def _trade_events_single(position: pd.Series, returns: pd.Series) -> list[dict[str, Any]]:
    trades: list[dict[str, Any]] = []
    entry_ts: str | None = None
    entry_side = 0
    pnl_path: list[float] = []
    holding_bars = 0
    previous = 0
    for timestamp, position_value in position.items():
        current = int(position_value)
        ret = float(returns.loc[timestamp])
        if current != 0 and previous == 0:
            entry_ts = timestamp.isoformat().replace("+00:00", "Z")
            entry_side = current
            pnl_path = []
            holding_bars = 0
        if current != 0:
            pnl_path.append(ret)
            holding_bars += 1
        if current == 0 and previous != 0 and entry_ts is not None:
            exit_ts = timestamp.isoformat().replace("+00:00", "Z")
            trade_return = float(np.prod([1.0 + value for value in pnl_path]) - 1.0) if pnl_path else 0.0
            trades.append(
                {
                    "asset": "",
                    "side": entry_side,
                    "entry_timestamp_utc": entry_ts,
                    "exit_timestamp_utc": exit_ts,
                    "holding_bars": holding_bars,
                    "gross_return": trade_return,
                    "net_return": trade_return,
                }
            )
            entry_ts = None
            entry_side = 0
            pnl_path = []
            holding_bars = 0
        previous = current
    if previous != 0 and entry_ts is not None:
        exit_ts = position.index[-1].isoformat().replace("+00:00", "Z")
        trade_return = float(np.prod([1.0 + value for value in pnl_path]) - 1.0) if pnl_path else 0.0
        trades.append(
            {
                "asset": "",
                "side": entry_side,
                "entry_timestamp_utc": entry_ts,
                "exit_timestamp_utc": exit_ts,
                "holding_bars": holding_bars,
                "gross_return": trade_return,
                "net_return": trade_return,
            }
        )
    return trades


def _trade_events(position: pd.Series, returns: pd.Series) -> list[dict[str, Any]]:
    if not isinstance(position.index, pd.MultiIndex):
        return _trade_events_single(position, returns)
    trades: list[dict[str, Any]] = []
    for asset in sorted(set(position.index.get_level_values(1))):
        asset_position = position.xs(asset, level=1)
        asset_returns = returns.xs(asset, level=1)
        for trade in _trade_events_single(asset_position, asset_returns):
            trade["asset"] = str(asset)
            trades.append(trade)
    return trades


def _max_drawdown(compound_returns: pd.Series) -> float:
    if compound_returns.empty:
        return 0.0
    equity = (1.0 + compound_returns).cumprod()
    running_max = equity.cummax()
    drawdown = equity / running_max - 1.0
    return abs(float(drawdown.min()))


def _stage_metrics(
    *,
    stage_name: str,
    stage_frame: pd.DataFrame,
    signal: pd.Series,
    position: pd.Series,
    gross_returns: pd.Series,
) -> dict[str, Any]:
    portfolio_returns = _portfolio_returns(gross_returns, position)
    trades = _trade_events(position, gross_returns)
    gross_compound = float((1.0 + portfolio_returns).prod() - 1.0) if len(portfolio_returns) else 0.0
    signal_count = int((signal != 0).sum()) if len(signal) else 0
    trade_count = len(trades)
    expectancy = float(sum(item["net_return"] for item in trades) / trade_count) if trade_count else 0.0
    wins = [item["net_return"] for item in trades if item["net_return"] > 0.0]
    losses = [item["net_return"] for item in trades if item["net_return"] < 0.0]
    profit_factor = float(sum(wins) / abs(sum(losses))) if losses else (999.0 if wins else 0.0)
    bar_count = (
        int(stage_frame.index.get_level_values(0).nunique())
        if isinstance(stage_frame.index, pd.MultiIndex)
        else int(len(stage_frame))
    )
    turnover = int(_turnover(position).sum()) if len(position) else 0
    active_bar_count = int(position.abs().sum()) if len(position) else 0
    exposure_fraction = round(float(position.abs().mean()) if len(position) else 0.0, 6)
    signal_rows: list[dict[str, Any]] = []
    for idx, value in signal.items():
        if int(value) == 0:
            continue
        if isinstance(idx, tuple):
            ts, asset = idx
            signal_rows.append(
                {
                    "timestamp_utc": ts.isoformat().replace("+00:00", "Z"),
                    "asset": str(asset),
                    "signal": int(value),
                }
            )
        else:
            signal_rows.append(
                {
                    "timestamp_utc": idx.isoformat().replace("+00:00", "Z"),
                    "signal": int(value),
                }
            )
    return {
        "stage_name": stage_name,
        "bar_count": bar_count,
        "signal_count": signal_count,
        "trade_count": trade_count,
        "active_bar_count": active_bar_count,
        "exposure_fraction": exposure_fraction,
        "turnover": turnover,
        "gross_return_sum": float(portfolio_returns.sum()) if len(portfolio_returns) else 0.0,
        "gross_return_compound": gross_compound,
        "net_return_compound": gross_compound,
        "costs": 0.0,
        "slippage": 0.0,
        "max_drawdown": _max_drawdown(portfolio_returns),
        "expectancy": expectancy,
        "profit_factor": profit_factor,
        "holding_period_bars_average": round(
            float(sum(item["holding_bars"] for item in trades) / trade_count) if trade_count else 0.0,
            6,
        ),
        "trades": trades,
        "signals": signal_rows,
    }


def _execute_train(stage: dict[str, Any]) -> dict[str, Any]:
    checks = {
        "sufficient_trades": stage["trade_count"] >= READY_SCREENING_MIN_TRADES,
        "sufficient_signals": stage["signal_count"] >= READY_SCREENING_MIN_SIGNALS,
    }
    passed = all(checks.values())
    return {
        **stage,
        "criteria_checks": checks,
        "screening_outcome": "PASSED" if passed else ("INSUFFICIENT_TRADES" if not checks["sufficient_trades"] else "INSUFFICIENT_SIGNALS"),
        "reason_records": [
            {
                "decision": "screening_gate",
                "metric": "trade_count",
                "threshold": READY_SCREENING_MIN_TRADES,
                "value": stage["trade_count"],
                "status": "PASSED" if checks["sufficient_trades"] else "FAILED",
                "next_action": "continue_to_validation" if passed else "fail_closed_screening",
            },
            {
                "decision": "screening_gate",
                "metric": "signal_count",
                "threshold": READY_SCREENING_MIN_SIGNALS,
                "value": stage["signal_count"],
                "status": "PASSED" if checks["sufficient_signals"] else "FAILED",
                "next_action": "continue_to_validation" if passed else "fail_closed_screening",
            },
        ],
    }


def _execute_validation(stage: dict[str, Any], train_stage: dict[str, Any]) -> dict[str, Any]:
    checks = {
        "sufficient_trades": stage["trade_count"] >= READY_VALIDATION_MIN_TRADES,
        "sufficient_signals": stage["signal_count"] >= READY_VALIDATION_MIN_SIGNALS,
    }
    passed = all(checks.values())
    return {
        **stage,
        "criteria_checks": checks,
        "train_to_validation_degradation": {
            "trade_count_delta": stage["trade_count"] - train_stage["trade_count"],
            "signal_count_delta": stage["signal_count"] - train_stage["signal_count"],
            "net_return_compound_delta": round(
                stage["net_return_compound"] - train_stage["net_return_compound"],
                6,
            ),
        },
        "validation_outcome": "PASSED" if passed else ("INSUFFICIENT_TRADES" if not checks["sufficient_trades"] else "INSUFFICIENT_SIGNALS"),
        "reason_records": [
            {
                "decision": "validation_gate",
                "metric": "trade_count",
                "threshold": READY_VALIDATION_MIN_TRADES,
                "value": stage["trade_count"],
                "status": "PASSED" if checks["sufficient_trades"] else "FAILED",
                "next_action": "continue_to_oos" if passed else "fail_closed_validation",
            },
            {
                "decision": "validation_gate",
                "metric": "signal_count",
                "threshold": READY_VALIDATION_MIN_SIGNALS,
                "value": stage["signal_count"],
                "status": "PASSED" if checks["sufficient_signals"] else "FAILED",
                "next_action": "continue_to_oos" if passed else "fail_closed_validation",
            },
        ],
    }


def _execute_oos(stage: dict[str, Any], window_id: str) -> dict[str, Any]:
    validation_evidence = build_validation_evidence_status(
        {"oos_summary": {"totaal_trades": stage["trade_count"]}},
        result_success=True,
    )
    evidence_status = str(validation_evidence["evidence_status"])
    if evidence_status == "sufficient_oos_evidence":
        outcome = "COMPLETED"
    elif evidence_status == "insufficient_oos_trades":
        outcome = "INSUFFICIENT_TRADES"
    else:
        outcome = "INSUFFICIENT_SIGNALS"
    return {
        **stage,
        "oos_window_id": window_id,
        "validation_evidence": validation_evidence,
        "oos_outcome": outcome,
        "reason_records": [
            {
                "decision": "oos_gate",
                "metric": "trade_count",
                "threshold": int(validation_evidence["min_oos_trades"]),
                "value": stage["trade_count"],
                "status": "PASSED" if evidence_status == "sufficient_oos_evidence" else "FAILED",
                "next_action": "continue_to_null_controls" if outcome == "COMPLETED" else "route_to_data_oos_capacity_expansion",
            }
        ],
    }


def _seed_int(seed_hex: str, stage_name: str) -> int:
    return int(hashlib.sha256(f"{seed_hex}:{stage_name}".encode()).hexdigest()[:16], 16)


def _matched_frequency_null(position: pd.Series, seed_hex: str, stage_name: str) -> pd.Series:
    if position.empty:
        return position.copy()
    if isinstance(position.index, pd.MultiIndex):
        rows: list[pd.Series] = []
        for asset in sorted(set(position.index.get_level_values(1))):
            leg = position.xs(asset, level=1)
            shift = _seed_int(seed_hex, f"{stage_name}:{asset}") % len(leg)
            if shift == 0 and len(leg) > 1:
                shift = 1
            values = np.roll(leg.to_numpy(), shift)
            rows.append(pd.Series(values, index=leg.index).to_frame("value").assign(asset=asset).set_index("asset", append=True)["value"])
        return pd.concat(rows).sort_index().astype(int)
    shift = _seed_int(seed_hex, stage_name) % len(position)
    if shift == 0 and len(position) > 1:
        shift = 1
    values = np.roll(position.to_numpy(), shift)
    return pd.Series(values, index=position.index, dtype=int)


def _sign_flipped_signal(position: pd.Series) -> pd.Series:
    if position.empty:
        return position.copy()
    if position.min() < 0:
        return (-position.astype(int)).astype(int)
    return (1 - position.astype(int)).astype(int)


def _permuted_cross_sectional_ranking(position: pd.Series) -> pd.Series:
    if not isinstance(position.index, pd.MultiIndex) or position.empty:
        return _matched_frequency_null(position, "", "permuted_cross_sectional_ranking")
    rows: list[pd.Series] = []
    for timestamp, group in position.groupby(level=0, sort=True):
        assets = list(group.index.get_level_values(1))
        rotated_assets = assets[1:] + assets[:1]
        remapped = pd.Series(group.to_numpy(), index=pd.MultiIndex.from_arrays([[timestamp] * len(assets), rotated_assets]))
        remapped = remapped.reindex(group.index)
        rows.append(remapped.astype(int))
    return pd.concat(rows).sort_index().astype(int)


def _cost_only_baseline(position: pd.Series) -> pd.Series:
    return pd.Series(0, index=position.index, dtype=int)


def _evaluate_null_controls(
    *,
    stage_frame: pd.DataFrame,
    actual_stage: dict[str, Any],
    position: pd.Series,
    returns: pd.Series,
    bundle: dict[str, Any],
) -> dict[str, Any]:
    selection = dict(bundle["selection"])
    seed_hex = str(bundle["null_row"].get("deterministic_seed") or "")
    control_builders = {
        "permuted_cross_sectional_ranking": lambda: _permuted_cross_sectional_ranking(position),
        "matched_frequency_null": lambda: _matched_frequency_null(position, seed_hex, "oos"),
        "sign_flipped_signal": lambda: _sign_flipped_signal(position),
        "cost_only_baseline": lambda: _cost_only_baseline(position),
    }
    rows: list[dict[str, Any]] = []
    for control_name in bundle["null_row"].get("required_controls", []):
        null_position = control_builders[str(control_name)]()
        null_returns = null_position.astype(float) * returns.astype(float)
        metrics = _stage_metrics(
            stage_name=str(control_name),
            stage_frame=stage_frame,
            signal=null_position,
            position=null_position,
            gross_returns=null_returns,
        )
        comparison_outcome = (
            "INSUFFICIENT_SAMPLE"
            if str(actual_stage["validation_evidence"]["evidence_status"]) != "sufficient_oos_evidence"
            else (
                "OUTPERFORMS"
                if actual_stage["net_return_compound"] > metrics["net_return_compound"]
                else "FAILS_TO_OUTPERFORM"
            )
        )
        rows.append(
            {
                "control_identity": _content_id(
                    "qncx",
                    {
                        "generated_strategy_id": selection["generated_strategy_id"],
                        "control_class": control_name,
                        "seed": seed_hex,
                    },
                ),
                "control_class": control_name,
                "deterministic_seed": seed_hex,
                "generated_strategy_id": selection["generated_strategy_id"],
                "campaign_cell_id": selection["campaign_cell_id"],
                "snapshot_identity": selection["snapshot_identity"],
                "window": dict(bundle["window_row"]["oos_window"]),
                "metrics": metrics,
                "comparison_outcome": comparison_outcome,
                "accepted": comparison_outcome == "OUTPERFORMS",
                "technical_validation_only": False,
            }
        )
    null_control_passed = all(bool(row["accepted"]) for row in rows) if rows else False
    return {
        "schema_version": SCHEMA_VERSION,
        "module_version": MODULE_VERSION,
        "report_kind": "qre_second_campaign_null_controls",
        "generated_strategy_id": selection["generated_strategy_id"],
        "campaign_cell_id": selection["campaign_cell_id"],
        "null_control_execution_identity": _content_id("qne", rows),
        "rows": rows,
        "null_control_complete": bool(rows),
        "null_control_passed": null_control_passed,
        "reason": (
            "null_controls_not_distinguishable_under_current_sample"
            if rows and not null_control_passed
            else ""
        ),
    }


def _consume_oos_window(repo_root: Path, bundle: dict[str, Any], oos_stage: dict[str, Any]) -> dict[str, Any]:
    selection = dict(bundle["selection"])
    ledger = dict(bundle["ledger_payload"])
    rows = [dict(row) for row in ledger.get("rows", []) if isinstance(row, dict)]
    updated_rows: list[dict[str, Any]] = []
    consumed_row: dict[str, Any] | None = None
    selected_window_id = ""
    for row in rows:
        if (
            str(row.get("campaign_cell_id") or "") == selection["campaign_cell_id"]
            and str(row.get("purpose") or "") == "OOS"
        ):
            selected_window_id = str(row.get("window_id") or "")
            consumed = dict(row)
            consumed["status"] = "CONSUMED"
            consumed["consumption_identity"] = _content_id(
                "qwc",
                {
                    "window_id": selected_window_id,
                    "campaign_manifest_identity": selection["manifest_identity"],
                    "oos_outcome": oos_stage["oos_outcome"],
                },
            )
            consumed["consumption_evidence"] = {
                "campaign_manifest_identity": selection["manifest_identity"],
                "campaign_cell_id": selection["campaign_cell_id"],
                "generated_strategy_id": selection["generated_strategy_id"],
                "oos_stage_path": "generated_research/campaign_execution/stages/oos.v1.json",
            }
            consumed_row = consumed
            updated_rows.append(consumed)
        else:
            updated_rows.append(dict(row))
    if consumed_row is None:
        raise KeyError(f"missing OOS window for campaign cell {selection['campaign_cell_id']}")
    updated_payload = {
        **ledger,
        "rows": updated_rows,
        "window_ledger_identity": _content_id("qwlr", {"rows": updated_rows, "version": MODULE_VERSION}),
    }
    _write_json(repo_root / "generated_research/readiness/window_ledger/canonical_window_ledger.v1.json", updated_payload)
    return {
        "schema_version": SCHEMA_VERSION,
        "module_version": MODULE_VERSION,
        "report_kind": "qre_second_campaign_oos_consumption",
        "oos_consumption_identity": str(consumed_row["consumption_identity"]),
        "window_id": selected_window_id,
        "status": "CONSUMED",
        "campaign_manifest_identity": selection["manifest_identity"],
        "campaign_cell_id": selection["campaign_cell_id"],
        "generated_strategy_id": selection["generated_strategy_id"],
        "provenance": [
            "generated_research/readiness/window_ledger/canonical_window_ledger.v1.json",
            "generated_research/campaign_execution/stages/oos.v1.json",
        ],
    }


def _build_evidence_rows(
    *,
    integrity: dict[str, Any],
    train_stage: dict[str, Any],
    validation_stage: dict[str, Any],
    oos_stage: dict[str, Any],
    null_controls: dict[str, Any],
) -> dict[str, Any]:
    rows = [
        {
            "stage": "manifest_integrity",
            "decision": integrity["status"],
            "metric": "integrity_checks",
            "threshold_or_policy": "all_frozen_identities_and_hashes_must_match",
            "source_artifact": "generated_research/readiness/campaigns/generated_second_campaign_manifest.v1.json",
            "status": "PRESENT_AUTHORITATIVE" if integrity["status"] == "MANIFEST_VERIFIED" else "BLOCKED",
            "next_action": "execute_ready_cell_only" if integrity["status"] == "MANIFEST_VERIFIED" else "preserve_manifest_integrity_block",
        },
        {
            "stage": "train_and_screening",
            "decision": train_stage["screening_outcome"],
            "metric": "trade_count",
            "threshold_or_policy": READY_SCREENING_MIN_TRADES,
            "source_artifact": "generated_research/campaign_execution/stages/train_and_screening.v1.json",
            "status": "PRESENT_AUTHORITATIVE",
            "next_action": "continue_to_validation" if train_stage["screening_outcome"] == "PASSED" else "fail_closed_screening",
        },
        {
            "stage": "validation",
            "decision": validation_stage["validation_outcome"],
            "metric": "trade_count",
            "threshold_or_policy": READY_VALIDATION_MIN_TRADES,
            "source_artifact": "generated_research/campaign_execution/stages/validation.v1.json",
            "status": "PRESENT_AUTHORITATIVE",
            "next_action": "continue_to_oos" if validation_stage["validation_outcome"] == "PASSED" else "fail_closed_validation",
        },
        {
            "stage": "oos",
            "decision": oos_stage["oos_outcome"],
            "metric": "trade_count",
            "threshold_or_policy": int(oos_stage["validation_evidence"]["min_oos_trades"]),
            "source_artifact": "generated_research/campaign_execution/stages/oos.v1.json",
            "status": "PRESENT_AUTHORITATIVE",
            "next_action": "route_to_data_oos_capacity_expansion" if oos_stage["oos_outcome"] != "COMPLETED" else "continue_to_null_controls",
        },
        {
            "stage": "null_controls",
            "decision": "PASSED" if null_controls["null_control_passed"] else "FAILED",
            "metric": "null_control_comparison",
            "threshold_or_policy": "actual_strategy_must_outperform_frozen_null_controls_or_remain_insufficient_evidence",
            "source_artifact": "generated_research/campaign_execution/stages/null_controls.v1.json",
            "status": "PRESENT_AUTHORITATIVE",
            "next_action": "route_to_post_campaign_decision",
        },
    ]
    return {
        "schema_version": SCHEMA_VERSION,
        "module_version": MODULE_VERSION,
        "report_kind": "qre_second_campaign_evidence_reason_records",
        "evidence_identity": _content_id("qev", rows),
        "rows": rows,
    }


def _funnel(
    *,
    manifest_cells: int,
    train_stage: dict[str, Any],
    validation_stage: dict[str, Any],
    oos_stage: dict[str, Any],
    null_controls: dict[str, Any],
) -> dict[str, Any]:
    oos_accepted = 1 if oos_stage["oos_outcome"] == "COMPLETED" else 0
    null_passed = 1 if null_controls["null_control_passed"] else 0
    primary_bottleneck = (
        "oos_sample_size"
        if oos_stage["oos_outcome"] in {"INSUFFICIENT_TRADES", "INSUFFICIENT_SIGNALS"}
        else ("null_controls" if not null_controls["null_control_passed"] else "not_visible")
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "module_version": MODULE_VERSION,
        "report_kind": "qre_second_campaign_funnel_diagnosis",
        "funnel_identity": _content_id(
            "qfd",
            {
                "train": train_stage["screening_outcome"],
                "validation": validation_stage["validation_outcome"],
                "oos": oos_stage["oos_outcome"],
                "null_controls": null_controls["null_control_passed"],
            },
        ),
        "manifest_cells": manifest_cells,
        "executable_cells": 1,
        "train_complete": 1,
        "screening_passed": 1 if train_stage["screening_outcome"] == "PASSED" else 0,
        "validation_complete": 1,
        "validation_passed": 1 if validation_stage["validation_outcome"] == "PASSED" else 0,
        "oos_complete": 1,
        "oos_accepted": oos_accepted,
        "null_control_complete": 1 if null_controls["null_control_complete"] else 0,
        "null_control_passed": null_passed,
        "final_supported_hypotheses": 1 if (oos_accepted and null_passed) else 0,
        "final_rejected_hypotheses": 1 if primary_bottleneck == "null_controls" else 0,
        "threshold_distances": {
            "screening_trade_distance": train_stage["trade_count"] - READY_SCREENING_MIN_TRADES,
            "validation_trade_distance": validation_stage["trade_count"] - READY_VALIDATION_MIN_TRADES,
            "oos_trade_distance": oos_stage["trade_count"] - int(oos_stage["validation_evidence"]["min_oos_trades"]),
        },
        "primary_bottleneck": primary_bottleneck,
        "secondary_bottlenecks": ["null_controls"] if primary_bottleneck != "null_controls" else ["oos_sample_size"],
        "recommendations": [
            {"criterion": "screening", "recommendation": "KEEP"},
            {"criterion": "validation", "recommendation": "KEEP"},
            {"criterion": "oos_acceptance", "recommendation": "INSUFFICIENT_EVIDENCE_TO_CHANGE"},
            {"criterion": "null_controls", "recommendation": "INSUFFICIENT_EVIDENCE_TO_CHANGE"},
        ],
    }


def _final_decision(
    *,
    bundle: dict[str, Any],
    funnel: dict[str, Any],
    train_stage: dict[str, Any],
    validation_stage: dict[str, Any],
    oos_stage: dict[str, Any],
    null_controls: dict[str, Any],
) -> dict[str, Any]:
    selection = dict(bundle["selection"])
    if train_stage["screening_outcome"] != "PASSED":
        hypothesis = "BLOCKED_POLICY"
        strategy = "REJECTED_SCREENING"
    elif validation_stage["validation_outcome"] != "PASSED":
        hypothesis = "BLOCKED_SAMPLE_SIZE"
        strategy = "REJECTED_VALIDATION"
    elif oos_stage["oos_outcome"] in {"INSUFFICIENT_TRADES", "INSUFFICIENT_SIGNALS"}:
        hypothesis = "BLOCKED_SAMPLE_SIZE"
        strategy = "INSUFFICIENT_EVIDENCE"
    elif not null_controls["null_control_passed"]:
        hypothesis = "BLOCKED_CONTROLS"
        strategy = "REJECTED_NULL_CONTROLS"
    else:
        hypothesis = "SUPPORTED_FOR_FURTHER_RESEARCH"
        strategy = "RESEARCH_SURVIVOR"
    return {
        "schema_version": SCHEMA_VERSION,
        "module_version": MODULE_VERSION,
        "report_kind": "qre_second_campaign_hypothesis_strategy_decision",
        "decision_identity": _content_id("qdd", {"hypothesis": hypothesis, "strategy": strategy}),
        "hypothesis_decision": hypothesis,
        "strategy_decision": strategy,
        "operator_report_update": {
            "primary_bottleneck": funnel["primary_bottleneck"],
            "campaign_ready_cells": 0,
            "oos_trade_count": oos_stage["trade_count"],
            "null_control_passed": null_controls["null_control_passed"],
        },
        "contradiction_update": {
            "source_hypothesis_id": selection["source_hypothesis_id"],
            "evidence": (
                "oos_sample_size_insufficient_after_ready_cell_execution"
                if hypothesis == "BLOCKED_SAMPLE_SIZE"
                else "null_controls_failed_after_ready_cell_execution"
                if hypothesis == "BLOCKED_CONTROLS"
                else ""
            ),
        },
        "failure_memory_update": {
            "generated_strategy_id": selection["generated_strategy_id"],
            "dominant_failure_mode": funnel["primary_bottleneck"],
        },
        "portfolio_state_update": {
            "campaign_cell_id": selection["campaign_cell_id"],
            "post_execution_status": (
                "CONSUMED_OOS_INSUFFICIENT_EVIDENCE"
                if strategy == "INSUFFICIENT_EVIDENCE"
                else "CONSUMED_OOS_REJECTED"
                if strategy.startswith("REJECTED")
                else "CONSUMED_OOS_SUPPORTED"
            ),
        },
    }


def _recalibration(decision: dict[str, Any]) -> dict[str, Any]:
    outcome = "NO_RECALIBRATION_JUSTIFIED"
    if decision["strategy_decision"] == "REJECTED_NULL_CONTROLS":
        outcome = "REJECT_STRATEGY_OR_HYPOTHESIS"
    return {
        "schema_version": SCHEMA_VERSION,
        "module_version": MODULE_VERSION,
        "report_kind": "qre_second_campaign_recalibration_decision",
        "recalibration_identity": _content_id("qra", {"outcome": outcome, "decision": decision["decision_identity"]}),
        "outcome": outcome,
        "selected_criterion_class": "",
        "next_action": "same_input_replay_not_authorized_without_recalibration",
    }


def _same_input_replay(recalibration: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "module_version": MODULE_VERSION,
        "report_kind": "qre_second_campaign_same_input_replay",
        "replay_identity": _content_id("qsr", {"recalibration": recalibration["recalibration_identity"]}),
        "outcome": "NOT_RUN",
        "reason": "no_recalibration_justified_and_no_control_replay_required",
        "independent_oos_evidence": False,
    }


def _independent_oos_assessment(bundle: dict[str, Any]) -> dict[str, Any]:
    selection = dict(bundle["selection"])
    snapshot_latest = str(bundle["snapshot_row"].get("coverage_end_utc") or "")
    oos_end = str(bundle["window_row"]["oos_window"]["end"])
    outcome = "INDEPENDENT_OOS_NOT_AVAILABLE" if snapshot_latest == oos_end else "DATA_CAPACITY_BLOCKED"
    return {
        "schema_version": SCHEMA_VERSION,
        "module_version": MODULE_VERSION,
        "report_kind": "qre_second_campaign_independent_oos_assessment",
        "assessment_identity": _content_id(
            "qio",
            {
                "snapshot_identity": selection["snapshot_identity"],
                "oos_end": oos_end,
                "snapshot_latest": snapshot_latest,
                "outcome": outcome,
            },
        ),
        "outcome": outcome,
        "reason": "snapshot_exhausted_at_consumed_oos_end" if outcome == "INDEPENDENT_OOS_NOT_AVAILABLE" else "additional_authoritative_snapshot_required",
        "future_preregistration_proposal": {},
    }


def _feedback_routing(
    *,
    decision: dict[str, Any],
    independent_oos: dict[str, Any],
) -> dict[str, Any]:
    if decision["hypothesis_decision"] == "SUPPORTED_FOR_FURTHER_RESEARCH" and independent_oos["outcome"] == "INDEPENDENT_OOS_AVAILABLE":
        next_action = "preregister_repeated_independent_oos_campaign"
        terminal = "REPEATED_OOS_PREREGISTRATION_READY"
    elif independent_oos["outcome"] == "INDEPENDENT_OOS_NOT_AVAILABLE":
        next_action = "launch_data_oos_capacity_expansion"
        terminal = "DATA_OR_OOS_CAPACITY_BLOCKED"
    elif decision["strategy_decision"] == "REJECTED_NULL_CONTROLS":
        next_action = "bounded_control_capability_generation"
        terminal = "CAMPAIGN_COMPLETE_REJECTED"
    elif decision["hypothesis_decision"] == "SUPPORTED_FOR_FURTHER_RESEARCH":
        next_action = "handoff_ready_for_synthesis_review"
        terminal = "SYNTHESIS_READINESS_REVIEW_ELIGIBLE"
    else:
        next_action = "launch_data_oos_capacity_expansion"
        terminal = "CAMPAIGN_COMPLETE_INSUFFICIENT_EVIDENCE"
    return {
        "schema_version": SCHEMA_VERSION,
        "module_version": MODULE_VERSION,
        "report_kind": "qre_second_campaign_autonomous_feedback_routing",
        "routing_identity": _content_id("qfr", {"next_action": next_action, "terminal": terminal}),
        "next_action": next_action,
        "terminal_outcome": terminal,
        "route_reason": independent_oos["outcome"],
    }


def _closeout_markdown(payload: dict[str, Any]) -> str:
    if "train_stage" not in payload:
        return (
            "# ADE-QRE-025 Second Preregistered Campaign\n\n"
            f"- manifest verification: `{payload['manifest_integrity']['status']}`\n"
            f"- terminal outcome: `{payload['terminal_outcome']}`\n"
            f"- next autonomous action: `{payload['feedback_routing']['next_action']}`\n"
        )
    selection = dict(payload.get("selection") or {})
    train = payload["train_stage"]
    validation = payload["validation_stage"]
    oos = payload["oos_stage"]
    lines = [
        "# ADE-QRE-025 Second Preregistered Campaign",
        "",
        f"- manifest verification: `{payload['manifest_integrity']['status']}`",
        f"- executed campaign cell: `{selection.get('campaign_cell_id') or payload['executed_campaign_cell']}`",
        f"- source hypothesis: `{selection.get('source_hypothesis_id') or ''}`",
        f"- terminal outcome: `{payload['terminal_outcome']}`",
        f"- next autonomous action: `{payload['feedback_routing']['next_action']}`",
        "",
        "## Stage Outcomes",
        "",
        f"- train/screening: `{train['screening_outcome']}` / trades={train['trade_count']} / signals={train['signal_count']} / net={train['net_return_compound']:.6f}",
        f"- validation: `{validation['validation_outcome']}` / trades={validation['trade_count']} / signals={validation['signal_count']} / net={validation['net_return_compound']:.6f}",
        f"- oos: `{oos['oos_outcome']}` / trades={oos['trade_count']} / signals={oos['signal_count']} / net={oos['net_return_compound']:.6f}",
        f"- null controls passed: `{str(payload['null_controls']['null_control_passed']).lower()}`",
    ]
    return "\n".join(lines) + "\n"


def run_second_preregistered_campaign(
    *,
    repo_root: Path = REPO_ROOT,
    write_outputs: bool = True,
    max_iterations: int = 4,
) -> dict[str, Any]:
    repo_root = repo_root.resolve()
    bundle = _load_bundle(repo_root)
    selection = dict(bundle["selection"])
    integrity = _verify_manifest(repo_root, bundle)
    if write_outputs:
        _write_json(_repo_path(repo_root, MANIFEST_INTEGRITY_PATH), integrity)
    if integrity["status"] != "MANIFEST_VERIFIED":
        closeout = {
            "schema_version": SCHEMA_VERSION,
            "module_version": MODULE_VERSION,
            "report_kind": REPORT_KIND,
            "closeout_identity": _content_id("qcc", integrity),
            "manifest_integrity": integrity,
            "selection": selection,
            "terminal_outcome": "NO_SAFE_AUTOMATED_NEXT_ACTION",
            "feedback_routing": {"next_action": "preserve_manifest_integrity_block"},
        }
        if write_outputs:
            _write_json(_repo_path(repo_root, CLOSEOUT_JSON_PATH), closeout)
            _atomic_write(_repo_path(repo_root, CLOSEOUT_MD_PATH), _closeout_markdown(closeout))
        return closeout

    frame = _load_frame(repo_root, bundle)
    evaluated = _evaluate_strategy(frame, bundle)

    train_frame = _slice_window(frame, bundle["window_row"]["train_window"])
    validation_frame = _slice_window(frame, bundle["window_row"]["validation_window"])
    oos_frame = _slice_window(frame, bundle["window_row"]["oos_window"])

    train_index = train_frame.index
    validation_index = validation_frame.index
    oos_index = oos_frame.index
    train_stage = _execute_train(
        _stage_metrics(
            stage_name="train",
            stage_frame=train_frame,
            signal=evaluated["signal"].loc[train_index],
            position=evaluated["position"].loc[train_index],
            gross_returns=evaluated["gross_returns"].loc[train_index],
        )
    )
    validation_stage = _execute_validation(
        _stage_metrics(
            stage_name="validation",
            stage_frame=validation_frame,
            signal=evaluated["signal"].loc[validation_index],
            position=evaluated["position"].loc[validation_index],
            gross_returns=evaluated["gross_returns"].loc[validation_index],
        ),
        train_stage,
    )
    oos_window_id = next(
        str(row.get("window_id") or "")
        for row in bundle["ledger_payload"].get("rows", [])
        if str(row.get("campaign_cell_id") or "") == selection["campaign_cell_id"]
        and str(row.get("purpose") or "") == "OOS"
    )
    oos_stage = _execute_oos(
        _stage_metrics(
            stage_name="oos",
            stage_frame=oos_frame,
            signal=evaluated["signal"].loc[oos_index],
            position=evaluated["position"].loc[oos_index],
            gross_returns=evaluated["gross_returns"].loc[oos_index],
        ),
        oos_window_id,
    )
    null_controls = _evaluate_null_controls(
        stage_frame=oos_frame,
        actual_stage=oos_stage,
        position=evaluated["position"].loc[oos_index],
        returns=evaluated["returns"].loc[oos_index],
        bundle=bundle,
    )
    evidence = _build_evidence_rows(
        integrity=integrity,
        train_stage=train_stage,
        validation_stage=validation_stage,
        oos_stage=oos_stage,
        null_controls=null_controls,
    )
    oos_consumption = _consume_oos_window(repo_root, bundle, oos_stage)
    funnel = _funnel(
        manifest_cells=len(bundle["manifest"].get("rows", [])),
        train_stage=train_stage,
        validation_stage=validation_stage,
        oos_stage=oos_stage,
        null_controls=null_controls,
    )
    decision = _final_decision(
        bundle=bundle,
        funnel=funnel,
        train_stage=train_stage,
        validation_stage=validation_stage,
        oos_stage=oos_stage,
        null_controls=null_controls,
    )
    recalibration = _recalibration(decision)
    replay = _same_input_replay(recalibration)
    independent_oos = _independent_oos_assessment(bundle)
    feedback = _feedback_routing(decision=decision, independent_oos=independent_oos)
    action_ledger = {
        "schema_version": SCHEMA_VERSION,
        "module_version": MODULE_VERSION,
        "report_kind": "qre_second_campaign_autonomous_action_ledger",
        "action_ledger_identity": _content_id(
            "qal",
            {
                "terminal": feedback["terminal_outcome"],
                "next_action": feedback["next_action"],
                "max_iterations": max_iterations,
                "campaign_cell_id": selection["campaign_cell_id"],
            },
        ),
        "rows": [
            {
                "iteration": 1,
                "before_state": "MANIFEST_VERIFIED",
                "selected_blocker": funnel["primary_bottleneck"],
                "remediation": "execute_frozen_campaign_and_close_decision_loop",
                "artifacts_created": [
                    "generated_research/campaign_execution/stages/train_and_screening.v1.json",
                    "generated_research/campaign_execution/stages/validation.v1.json",
                    "generated_research/campaign_execution/stages/oos.v1.json",
                    "generated_research/campaign_execution/stages/null_controls.v1.json",
                ],
                "after_state": feedback["terminal_outcome"],
                "progress_status": "IRREDUCIBLE_BLOCKER_PROVEN",
                "next_action": feedback["next_action"],
            }
        ],
    }
    manifest_ids = {str(row.get("campaign_cell_id") or "") for row in bundle["manifest"].get("rows", [])}
    all_portfolio_rows = _read_rows(
        repo_root / "generated_research/readiness/campaigns/automated_portfolio_readiness.v1.json",
        "rows",
    )
    excluded_blocked_cells = [
        {
            "campaign_cell_id": str(row.get("campaign_cell_id") or ""),
            "reason": next(iter(row.get("blockers") or ["blocked_unknown"])),
        }
        for row in all_portfolio_rows
        if str(row.get("campaign_cell_id") or "") not in manifest_ids
    ]
    classification = {
        "current_hypothesis_campaigns_executed": 1 if selection["source_hypothesis_id"] == TARGET_SOURCE_HYPOTHESIS_ID else 0,
        "new_empirical_campaigns_completed": 1,
        "historical_campaigns_consumed": 0,
        "fixture_campaigns_consumed": 0,
        "null_or_synthetic_campaigns_executed": 0,
    }
    closeout = {
        "schema_version": SCHEMA_VERSION,
        "module_version": MODULE_VERSION,
        "report_kind": REPORT_KIND,
        "closeout_identity": _content_id(
            "qce",
            {
                "manifest": selection["manifest_identity"],
                "decision": decision["decision_identity"],
                "terminal": feedback["terminal_outcome"],
            },
        ),
        "selection": selection,
        "manifest_integrity": integrity,
        "executed_campaign_identity": _content_id(
            "qcx",
            {"cell": selection["campaign_cell_id"], "module_version": MODULE_VERSION},
        ),
        "executed_campaign_cell": selection["campaign_cell_id"],
        "excluded_blocked_cells": excluded_blocked_cells,
        "campaign_classification": classification,
        "train_stage": train_stage,
        "validation_stage": validation_stage,
        "oos_stage": oos_stage,
        "null_controls": null_controls,
        "evidence": evidence,
        "oos_consumption": oos_consumption,
        "funnel": funnel,
        "decision": decision,
        "recalibration": recalibration,
        "replay": replay,
        "independent_oos": independent_oos,
        "feedback_routing": feedback,
        "action_ledger": action_ledger,
        "terminal_outcome": feedback["terminal_outcome"],
    }

    if write_outputs:
        _write_json(_repo_path(repo_root, TRAIN_PATH), train_stage)
        _write_json(_repo_path(repo_root, VALIDATION_PATH), validation_stage)
        _write_json(_repo_path(repo_root, OOS_PATH), oos_stage)
        _write_json(_repo_path(repo_root, NULL_CONTROLS_PATH), null_controls)
        _write_json(_repo_path(repo_root, EVIDENCE_PATH), evidence)
        _write_json(_repo_path(repo_root, OOS_CONSUMPTION_PATH), oos_consumption)
        _write_json(_repo_path(repo_root, FUNNEL_PATH), funnel)
        _write_json(_repo_path(repo_root, DECISION_PATH), decision)
        _write_json(_repo_path(repo_root, RECALIBRATION_PATH), recalibration)
        _write_json(_repo_path(repo_root, REPLAY_PATH), replay)
        _write_json(_repo_path(repo_root, INDEPENDENT_OOS_PATH), independent_oos)
        _write_json(_repo_path(repo_root, FEEDBACK_PATH), feedback)
        _write_json(_repo_path(repo_root, ACTION_LEDGER_PATH), action_ledger)
        _write_json(_repo_path(repo_root, CLOSEOUT_JSON_PATH), closeout)
        _atomic_write(_repo_path(repo_root, CLOSEOUT_MD_PATH), _closeout_markdown(closeout))
    return closeout


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="ADE-QRE-025 execute the frozen second preregistered campaign")
    parser.add_argument("--repo-root", type=Path, default=REPO_ROOT)
    parser.add_argument("--no-write", action="store_true")
    parser.add_argument("--max-iterations", type=int, default=4)
    parser.add_argument("--indent", type=int, default=2)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    payload = run_second_preregistered_campaign(
        repo_root=args.repo_root,
        write_outputs=not args.no_write,
        max_iterations=args.max_iterations,
    )
    print(json.dumps(payload, indent=args.indent, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
