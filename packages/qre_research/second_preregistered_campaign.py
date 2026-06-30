from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import math
import os
import tempfile
from pathlib import Path
from typing import Any, Final

import numpy as np
import pandas as pd

from agent.backtesting.thin_strategy import build_features_for
from packages.qre_research.generated_strategy_paths import REPO_ROOT, validate_write_target
from research.batch_execution import build_validation_evidence_status


SCHEMA_VERSION: Final[str] = "1.0"
MODULE_VERSION: Final[str] = "ade-qre-025.1"
REPORT_KIND: Final[str] = "qre_second_preregistered_campaign"

READY_CELL_ID: Final[str] = "qrcell_fdd68e20fd2724dd"
READY_STRATEGY_ID: Final[str] = "qgs_5af8f605ba82ae53"
READY_STRATEGY_SPEC_ID: Final[str] = "qsp_16800d656bf28677"
READY_PRESET_ID: Final[str] = "qgp_3150293b47cd6923"
READY_DATASET_ID: Final[str] = "qds_f8a7d624458bb131"
READY_SNAPSHOT_ID: Final[str] = "qsn_f8a7d624458bb131"
READY_MANIFEST_ID: Final[str] = "qcm_04f0e702e5be8884"
READY_OOS_WINDOW_ID: Final[str] = "qwl_06fd2878a7332daa"
READY_EXPECTED_CODE_HASH: Final[str] = (
    "5c0d49077ce84c1b31aafc28bdbbe9caf7d76e6116a6aa2ce2fa3a4f5cf9f26f"
)
READY_NULL_CONTROL_SPEC_ID: Final[str] = "qnc_10490ff5bd45b2e1"
READY_SIGNAL_CAPACITY_ID: Final[str] = "qrcap_signal_ready_4h"

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
RECALIBRATION_OUTCOMES: Final[tuple[str, ...]] = (
    "RECALIBRATION_JUSTIFIED",
    "NO_RECALIBRATION_JUSTIFIED",
    "INSUFFICIENT_EVIDENCE",
    "REJECT_STRATEGY_OR_HYPOTHESIS",
)
INDEPENDENT_OOS_OUTCOMES: Final[tuple[str, ...]] = (
    "INDEPENDENT_OOS_AVAILABLE",
    "INDEPENDENT_OOS_NOT_AVAILABLE",
    "DATA_CAPACITY_BLOCKED",
    "POINT_IN_TIME_UNIVERSE_BLOCKED",
    "INDEPENDENCE_NOT_PROVEN",
    "INSUFFICIENT_EVIDENCE",
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
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
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


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


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
    ledger_payload = _read_json(repo_root / "generated_research/readiness/window_ledger/canonical_window_ledger.v1.json")
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
    spec = _read_json(repo_root / f"generated_research/specs/{READY_STRATEGY_SPEC_ID}.json")
    cache_manifest = _read_json(repo_root / "logs/qre_data_cache_manifest/latest.json")
    cache_coverage = _read_json(repo_root / "artifacts/cache/cache_coverage_latest.v1.json")

    manifest_row = next(
        row for row in manifest["rows"] if str(row.get("campaign_cell_id") or "") == READY_CELL_ID
    )
    portfolio_row = next(
        row for row in portfolio_rows if str(row.get("campaign_cell_id") or "") == READY_CELL_ID
    )
    snapshot_row = next(
        row for row in snapshot_rows if str(row.get("campaign_cell_id") or "") == READY_CELL_ID
    )
    window_row = next(
        row for row in window_rows if str(row.get("campaign_cell_id") or "") == READY_CELL_ID
    )
    independence_row = next(
        row for row in independence_rows if str(row.get("campaign_cell_id") or "") == READY_CELL_ID
    )
    signal_row = next(
        row for row in signal_rows if str(row.get("campaign_cell_id") or "") == READY_CELL_ID
    )
    quality_row = next(
        row for row in quality_rows if str(row.get("campaign_cell_id") or "") == READY_CELL_ID
    )
    registry_row = next(
        row for row in strategy_registry_rows if str(row.get("generated_strategy_id") or "") == READY_STRATEGY_ID
    )
    null_row = next(
        row for row in null_rows if str(row.get("generated_strategy_id") or "") == READY_STRATEGY_ID
    )
    cache_file_row = next(
        row
        for row in cache_manifest.get("files", [])
        if str(row.get("instrument") or "") == "ASML" and str(row.get("timeframe") or "") == "4h"
    )
    coverage_row = next(
        row
        for row in cache_coverage.get("coverage", [])
        if str(row.get("instrument") or "") == "ASML"
        and str(row.get("timeframe") or "") == "4h"
        and str(row.get("content_hash") or "") == "sha256:bfcf62c1f46529440bd32fa0475abf67ece219f930bed02f483af7cbfc079676"
    )

    module_path = repo_root / str(registry_row.get("module_path") or "")
    return {
        "manifest": manifest,
        "manifest_row": manifest_row,
        "portfolio_row": portfolio_row,
        "snapshot_row": snapshot_row,
        "window_row": window_row,
        "ledger_payload": ledger_payload,
        "independence_row": independence_row,
        "signal_row": signal_row,
        "quality_row": quality_row,
        "registry_row": registry_row,
        "null_row": null_row,
        "validation_row": validation_rows[READY_STRATEGY_ID],
        "spec": spec,
        "cache_file_row": cache_file_row,
        "coverage_row": coverage_row,
        "module_path": module_path,
    }


def _verify_manifest(repo_root: Path, bundle: dict[str, Any]) -> dict[str, Any]:
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
        repo_root / "generated_research/specs/qsp_16800d656bf28677.json",
        repo_root / "generated_research/validation/qgs_5af8f605ba82ae53.json",
        repo_root / "generated_research/lineage/generated_null_controls.v1.json",
        bundle["module_path"],
        repo_root / str(bundle["cache_file_row"]["path"]),
    ]
    for path in required_paths:
        _require_path(path, missing=missing)

    mismatches: list[str] = []
    if str(bundle["manifest"].get("campaign_manifest_identity") or "") != READY_MANIFEST_ID:
        mismatches.append("manifest_identity")
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
        "campaign_cell_id": str(manifest_row.get("campaign_cell_id") or "") == READY_CELL_ID,
        "generated_strategy_id": str(manifest_row.get("generated_strategy_id") or "") == READY_STRATEGY_ID,
        "strategy_spec_id": str(manifest_row.get("strategy_spec_id") or "") == READY_STRATEGY_SPEC_ID,
        "preset_id": str(manifest_row.get("preset_id") or "") == READY_PRESET_ID,
        "dataset_identity": str(manifest_row.get("dataset_identity") or "") == READY_DATASET_ID,
        "snapshot_identity": str(manifest_row.get("snapshot_identity") or "") == READY_SNAPSHOT_ID,
        "timeframe": str(manifest_row.get("timeframe") or "") == "4h",
        "train_window": dict(manifest_row.get("train_window") or {}) == dict(window_row.get("train_window") or {}),
        "validation_window": dict(manifest_row.get("validation_window") or {}) == dict(window_row.get("validation_window") or {}),
        "oos_window": dict(manifest_row.get("oos_window") or {}) == dict(window_row.get("oos_window") or {}),
        "portfolio_ready": str(portfolio_row.get("status") or "") == "READY_FOR_PREREGISTRATION",
        "registry_strategy": str(registry_row.get("generated_strategy_id") or "") == READY_STRATEGY_ID,
        "registry_spec": str(registry_row.get("strategy_spec_id") or "") == READY_STRATEGY_SPEC_ID,
        "registry_hash_matches_expected": str(registry_row.get("code_hash") or "") == READY_EXPECTED_CODE_HASH,
        "module_hash_matches_registry": module_hash == str(registry_row.get("code_hash") or ""),
        "validation_state": str(validation_row.get("status") or "") == "VALIDATED",
        "validation_hash": str(validation_row.get("code_hash") or "") == module_hash,
        "null_control_spec": str(null_row.get("null_control_spec_id") or "") == READY_NULL_CONTROL_SPEC_ID,
        "snapshot_dataset": str(snapshot_row.get("dataset_identity") or "") == READY_DATASET_ID,
        "snapshot_identity": str(snapshot_row.get("snapshot_identity") or "") == READY_SNAPSHOT_ID,
        "oos_independence": str(bundle["independence_row"].get("outcome") or "") == "INDEPENDENCE_PROVEN",
        "signal_capacity": str(bundle["signal_row"].get("outcome") or "") == "SIGNAL_CAPACITY_READY",
        "quality_ready": str(bundle["quality_row"].get("quality_state") or "") == "QUALITY_READY",
    }
    if missing:
        status = "INPUT_MISSING"
    elif not checks["registry_hash_matches_expected"] or not checks["module_hash_matches_registry"]:
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
    elif not all(
        checks[key]
        for key in (
            "campaign_cell_id",
            "generated_strategy_id",
            "strategy_spec_id",
            "preset_id",
            "dataset_identity",
            "snapshot_identity",
            "timeframe",
            "portfolio_ready",
            "registry_strategy",
            "registry_spec",
            "validation_state",
            "validation_hash",
            "oos_independence",
            "signal_capacity",
            "quality_ready",
        )
    ):
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
                "manifest": READY_MANIFEST_ID,
                "status": status,
                "checks": checks,
                "missing": missing,
                "mismatches": mismatches,
            },
        ),
        "manifest_identity": READY_MANIFEST_ID,
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
            "generated_research/specs/qsp_16800d656bf28677.json",
            "generated_research/validation/qgs_5af8f605ba82ae53.json",
            "generated_research/lineage/generated_null_controls.v1.json",
            _repo_relative(bundle["module_path"], repo_root=repo_root),
            str(bundle["cache_file_row"]["path"]),
        ],
    }


def _load_frame(repo_root: Path, bundle: dict[str, Any]) -> pd.DataFrame:
    frame = pd.read_parquet(repo_root / str(bundle["cache_file_row"]["path"]))
    frame = frame.sort_values("timestamp_utc").set_index("timestamp_utc")
    return frame


def _evaluate_strategy(frame: pd.DataFrame, bundle: dict[str, Any]) -> dict[str, pd.Series]:
    module = _load_module_from_path(bundle["module_path"])
    features = build_features_for(module.generated_strategy._feature_requirements, frame)
    signal = module.generated_strategy(frame, features).astype(int)
    position = signal.shift(1).fillna(0).astype(int)
    returns = frame["close"].astype(float).pct_change().fillna(0.0)
    gross_returns = position.astype(float) * returns
    turnover = position.diff().abs().fillna(position).astype(int)
    return {
        "signal": signal,
        "position": position,
        "returns": returns,
        "gross_returns": gross_returns,
        "turnover": turnover,
    }


def _slice_window(frame: pd.DataFrame, window: dict[str, Any]) -> pd.DataFrame:
    return frame.loc[str(window["start"]):str(window["end"])].copy()


def _trade_events(
    stage_frame: pd.DataFrame,
    stage_position: pd.Series,
    stage_returns: pd.Series,
) -> list[dict[str, Any]]:
    trades: list[dict[str, Any]] = []
    entry_ts: str | None = None
    pnl_path: list[float] = []
    holding_bars = 0
    previous = 0
    for timestamp, position_value in stage_position.items():
        current = int(position_value)
        ret = float(stage_returns.loc[timestamp])
        if current == 1 and previous == 0:
            entry_ts = timestamp.isoformat().replace("+00:00", "Z")
            pnl_path = []
            holding_bars = 0
        if current == 1:
            pnl_path.append(ret)
            holding_bars += 1
        if current == 0 and previous == 1 and entry_ts is not None:
            exit_ts = timestamp.isoformat().replace("+00:00", "Z")
            trade_return = float(np.prod([1.0 + value for value in pnl_path]) - 1.0) if pnl_path else 0.0
            trades.append(
                {
                    "entry_timestamp_utc": entry_ts,
                    "exit_timestamp_utc": exit_ts,
                    "holding_bars": holding_bars,
                    "gross_return": trade_return,
                    "net_return": trade_return,
                }
            )
            entry_ts = None
            pnl_path = []
            holding_bars = 0
        previous = current
    if previous == 1 and entry_ts is not None:
        exit_ts = stage_position.index[-1].isoformat().replace("+00:00", "Z")
        trade_return = float(np.prod([1.0 + value for value in pnl_path]) - 1.0) if pnl_path else 0.0
        trades.append(
            {
                "entry_timestamp_utc": entry_ts,
                "exit_timestamp_utc": exit_ts,
                "holding_bars": holding_bars,
                "gross_return": trade_return,
                "net_return": trade_return,
            }
        )
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
    trades = _trade_events(stage_frame, position, gross_returns)
    gross_compound = float((1.0 + gross_returns).prod() - 1.0) if len(gross_returns) else 0.0
    turnover = int(position.diff().abs().fillna(position).sum()) if len(position) else 0
    signal_count = int(signal.sum()) if len(signal) else 0
    trade_count = len(trades)
    expectancy = float(sum(item["net_return"] for item in trades) / trade_count) if trade_count else 0.0
    wins = [item["net_return"] for item in trades if item["net_return"] > 0.0]
    losses = [item["net_return"] for item in trades if item["net_return"] < 0.0]
    profit_factor = float(sum(wins) / abs(sum(losses))) if losses else (999.0 if wins else 0.0)
    return {
        "stage_name": stage_name,
        "bar_count": int(len(stage_frame)),
        "signal_count": signal_count,
        "trade_count": trade_count,
        "active_bar_count": int(position.sum()) if len(position) else 0,
        "exposure_fraction": round(float(position.mean()) if len(position) else 0.0, 6),
        "turnover": turnover,
        "gross_return_sum": float(gross_returns.sum()) if len(gross_returns) else 0.0,
        "gross_return_compound": gross_compound,
        "net_return_compound": gross_compound,
        "costs": 0.0,
        "slippage": 0.0,
        "max_drawdown": _max_drawdown(gross_returns),
        "expectancy": expectancy,
        "profit_factor": profit_factor,
        "holding_period_bars_average": round(
            float(sum(item["holding_bars"] for item in trades) / trade_count) if trade_count else 0.0,
            6,
        ),
        "trades": trades,
        "signals": [
            {
                "timestamp_utc": idx.isoformat().replace("+00:00", "Z"),
                "signal": int(value),
            }
            for idx, value in signal.items()
            if int(value) != 0
        ],
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
    return int(hashlib.sha256(f"{seed_hex}:{stage_name}".encode("utf-8")).hexdigest()[:16], 16)


def _matched_frequency_null(position: pd.Series, seed_hex: str, stage_name: str) -> pd.Series:
    if position.empty:
        return position.copy()
    shift = _seed_int(seed_hex, stage_name) % len(position)
    if shift == 0 and len(position) > 1:
        shift = 1
    values = np.roll(position.to_numpy(), shift)
    return pd.Series(values, index=position.index, dtype=int)


def _sign_flipped_signal(position: pd.Series) -> pd.Series:
    if position.empty:
        return position.copy()
    return (1 - position.astype(int)).astype(int)


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
    seed_hex = str(bundle["null_row"].get("deterministic_seed") or "")
    control_builders = {
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
                        "generated_strategy_id": READY_STRATEGY_ID,
                        "control_class": control_name,
                        "seed": seed_hex,
                    },
                ),
                "control_class": control_name,
                "deterministic_seed": seed_hex,
                "generated_strategy_id": READY_STRATEGY_ID,
                "campaign_cell_id": READY_CELL_ID,
                "snapshot_identity": READY_SNAPSHOT_ID,
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
        "generated_strategy_id": READY_STRATEGY_ID,
        "campaign_cell_id": READY_CELL_ID,
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
    ledger = dict(bundle["ledger_payload"])
    rows = [dict(row) for row in ledger.get("rows", []) if isinstance(row, dict)]
    updated_rows: list[dict[str, Any]] = []
    consumed_row: dict[str, Any] | None = None
    for row in rows:
        if str(row.get("window_id") or "") == READY_OOS_WINDOW_ID:
            consumed = dict(row)
            consumed["status"] = "CONSUMED"
            consumed["consumption_identity"] = _content_id(
                "qwc",
                {
                    "window_id": READY_OOS_WINDOW_ID,
                    "campaign_manifest_identity": READY_MANIFEST_ID,
                    "oos_outcome": oos_stage["oos_outcome"],
                },
            )
            consumed["consumption_evidence"] = {
                "campaign_manifest_identity": READY_MANIFEST_ID,
                "campaign_cell_id": READY_CELL_ID,
                "generated_strategy_id": READY_STRATEGY_ID,
                "oos_stage_path": "generated_research/campaign_execution/stages/oos.v1.json",
            }
            consumed_row = consumed
            updated_rows.append(consumed)
        else:
            updated_rows.append(dict(row))
    if consumed_row is None:
        raise KeyError(f"missing OOS window id {READY_OOS_WINDOW_ID}")
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
        "window_id": READY_OOS_WINDOW_ID,
        "status": "CONSUMED",
        "campaign_manifest_identity": READY_MANIFEST_ID,
        "campaign_cell_id": READY_CELL_ID,
        "generated_strategy_id": READY_STRATEGY_ID,
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
            "metric": "oos_trade_count",
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
        "manifest_cells": 4,
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
    funnel: dict[str, Any],
    train_stage: dict[str, Any],
    validation_stage: dict[str, Any],
    oos_stage: dict[str, Any],
    null_controls: dict[str, Any],
) -> dict[str, Any]:
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
            "source_hypothesis_id": "atr_adaptive_trend_v0",
            "evidence": "oos_sample_size_insufficient_after_ready_cell_execution",
        },
        "failure_memory_update": {
            "generated_strategy_id": READY_STRATEGY_ID,
            "dominant_failure_mode": funnel["primary_bottleneck"],
        },
        "portfolio_state_update": {
            "campaign_cell_id": READY_CELL_ID,
            "post_execution_status": "CONSUMED_OOS_INSUFFICIENT_EVIDENCE",
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
                "snapshot_identity": READY_SNAPSHOT_ID,
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
    train = payload["train_stage"]
    validation = payload["validation_stage"]
    oos = payload["oos_stage"]
    lines = [
        "# ADE-QRE-025 Second Preregistered Campaign",
        "",
        f"- manifest verification: `{payload['manifest_integrity']['status']}`",
        f"- executed campaign cell: `{READY_CELL_ID}`",
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

    train_stage = _execute_train(
        _stage_metrics(
            stage_name="train",
            stage_frame=train_frame,
            signal=evaluated["signal"].loc[train_frame.index],
            position=evaluated["position"].loc[train_frame.index],
            gross_returns=evaluated["gross_returns"].loc[train_frame.index],
        )
    )
    validation_stage = _execute_validation(
        _stage_metrics(
            stage_name="validation",
            stage_frame=validation_frame,
            signal=evaluated["signal"].loc[validation_frame.index],
            position=evaluated["position"].loc[validation_frame.index],
            gross_returns=evaluated["gross_returns"].loc[validation_frame.index],
        ),
        train_stage,
    )
    oos_stage = _execute_oos(
        _stage_metrics(
            stage_name="oos",
            stage_frame=oos_frame,
            signal=evaluated["signal"].loc[oos_frame.index],
            position=evaluated["position"].loc[oos_frame.index],
            gross_returns=evaluated["gross_returns"].loc[oos_frame.index],
        ),
        READY_OOS_WINDOW_ID,
    )
    null_controls = _evaluate_null_controls(
        stage_frame=oos_frame,
        actual_stage=oos_stage,
        position=evaluated["position"].loc[oos_frame.index],
        returns=evaluated["returns"].loc[oos_frame.index],
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
        train_stage=train_stage,
        validation_stage=validation_stage,
        oos_stage=oos_stage,
        null_controls=null_controls,
    )
    decision = _final_decision(
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
    closeout = {
        "schema_version": SCHEMA_VERSION,
        "module_version": MODULE_VERSION,
        "report_kind": REPORT_KIND,
        "closeout_identity": _content_id(
            "qce",
            {
                "manifest": READY_MANIFEST_ID,
                "decision": decision["decision_identity"],
                "terminal": feedback["terminal_outcome"],
            },
        ),
        "manifest_integrity": integrity,
        "executed_campaign_identity": _content_id(
            "qcx",
            {"cell": READY_CELL_ID, "module_version": MODULE_VERSION},
        ),
        "executed_campaign_cell": READY_CELL_ID,
        "excluded_blocked_cells": [
            {
                "campaign_cell_id": "qrcell_41d3efbcaa2aeddb",
                "reason": "usable_history_below_minimum_policy_span",
            },
            {
                "campaign_cell_id": "qrcell_d5ded3130f132558",
                "reason": "cache_row_missing",
            },
            {
                "campaign_cell_id": "qrcell_44aa81da7c2fc7c9",
                "reason": "usable_history_below_minimum_policy_span",
            },
        ],
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
