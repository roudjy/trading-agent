from __future__ import annotations

import argparse
import hashlib
import json
import os
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Final, Mapping

import pandas as pd

from agent.backtesting.engine import AssetContext, BacktestEngine, build_evaluation_folds
from agent.backtesting.regime import build_regime_frame
from agent.backtesting.strategies import trend_pullback_v1_strategie
from research import qre_bounded_current_basket_generation_runner as runner
from research import qre_bounded_generation_artifact_acceptance_verifier as verifier
from research import qre_bounded_validation_approval_gate as approval_gate
from research import qre_evidence_complete_basket_closure as closure
from research.presets import get_preset, resolve_preset_bundle

SCHEMA_VERSION: Final[str] = "1.0"
REPORT_KIND: Final[str] = "qre_approved_bounded_evidence_materialization"
DEFAULT_APPROVAL_PATH: Final[Path] = Path(
    "research/operator_approvals/qre_bounded_validation_approval_first_batch.v1.json"
)
DEFAULT_OUTPUT_DIR: Final[Path] = Path(
    "logs/qre_bounded_current_basket_generation_runner/approved_bounded_validation_execution"
)
REQUEST_PATH: Final[Path] = Path(
    "logs/qre_bounded_current_basket_generation_runner/approved_bounded_validation_request.v1.json"
)
SOURCE_ARTIFACT_DIR: Final[Path] = Path(
    "logs/qre_controlled_validation_adapter_results/source_artifacts"
)
PROTECTED_PUBLIC_OUTPUTS: Final[tuple[Path, ...]] = (
    Path("research/research_latest.json"),
    Path("research/strategy_matrix.csv"),
)
ALLOWED_OUTPUT_PATHS: Final[tuple[str, ...]] = (
    "logs/qre_bounded_current_basket_generation_runner/",
    "logs/qre_controlled_validation_adapter_results/",
    "logs/qre_bounded_generation_artifact_acceptance_verifier/",
    "logs/qre_evidence_complete_basket_closure/",
)
TIMEFRAME_TO_INTERVAL: Final[dict[str, str]] = {
    "daily_v1": "1d",
    "1d": "1d",
    "1h": "1h",
    "4h": "4h",
}


class ApprovedBoundedEvidenceError(RuntimeError):
    pass


def _resolve_single_preset_strategy(preset_id: str) -> tuple[str, Any]:
    """Resolve one executable strategy from the canonical preset catalog."""
    try:
        preset = get_preset(preset_id)
    except KeyError as exc:
        raise ApprovedBoundedEvidenceError(
            f"unsupported preset for campaign validation: {preset_id}"
        ) from exc

    strategies = resolve_preset_bundle(preset)
    if len(strategies) != 1:
        raise ApprovedBoundedEvidenceError(
            "campaign validation requires exactly one executable preset strategy"
        )

    strategy = strategies[0]
    strategy_name = str(strategy.get("name") or "").strip()
    factory = strategy.get("factory")
    if not strategy_name or not callable(factory):
        raise ApprovedBoundedEvidenceError(
            "campaign validation preset strategy is not executable"
        )
    return strategy_name, factory


@dataclass(frozen=True)
class LocalEvaluation:
    symbol: str
    candidate_id: str
    generation_run_id: str
    oos_window_start: str
    oos_window_end: str
    oos_metric_fields: dict[str, Any]
    reason_record_refs: list[str]
    cost_slippage_assumption_refs: list[str]


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(payload, dict):
        raise ApprovedBoundedEvidenceError(f"expected JSON object: {path.as_posix()}")
    return payload


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def _utcnow() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _fingerprint(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"exists": False, "sha256": None}
    return {
        "exists": True,
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
    }


def _protected_fingerprints(repo_root: Path) -> dict[str, dict[str, Any]]:
    return {
        path.as_posix(): _fingerprint(repo_root / path)
        for path in PROTECTED_PUBLIC_OUTPUTS
    }


def _assert_protected_outputs_unchanged(repo_root: Path, before: Mapping[str, Any]) -> None:
    after = _protected_fingerprints(repo_root)
    if dict(before) != after:
        raise ApprovedBoundedEvidenceError("protected public outputs changed")


def _normalize_approval_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
    scope = payload.get("scope") if isinstance(payload.get("scope"), Mapping) else {}
    return {
        "approval_id": str(payload.get("approval_id") or ""),
        "approved_by": str(payload.get("approved_by") or ""),
        "approved_at_utc": str(payload.get("approved_at_utc") or ""),
        "expires_at_utc": str(payload.get("expiry_utc") or payload.get("expires_at_utc") or ""),
        "symbols": list(scope.get("symbols") or payload.get("symbols") or []),
        "preset_id": str(scope.get("preset_id") or payload.get("preset_id") or ""),
        "timeframe": str(scope.get("timeframe") or payload.get("timeframe") or ""),
        "allowed_command_class": str(payload.get("allowed_command_class") or ""),
        "allowed_output_paths": list(payload.get("allowed_output_paths") or []),
        "forbidden_capabilities": list(payload.get("forbidden_capabilities") or []),
        "dry_run_allowed": bool(payload.get("dry_run_allowed", False)),
        "real_run_allowed": bool(payload.get("real_run_allowed", False)),
        "external_fetch_allowed": bool(payload.get("external_fetch_allowed", False)),
        "evidence_acceptance_allowed": bool(payload.get("evidence_acceptance_allowed", False)),
        "bounded_input_window": dict(scope.get("bounded_input_window") or {}),
        "oos_window": dict(scope.get("oos_window") or {}),
        "source_data_ref": str(scope.get("source_data_ref") or ""),
    }


def _build_request_payload(
    approval: Mapping[str, Any],
    *,
    created_at_utc: str,
) -> dict[str, Any]:
    raw = json.dumps(
        {
            "approval_id": approval.get("approval_id"),
            "symbols": list(approval.get("symbols") or []),
            "preset_id": approval.get("preset_id"),
            "timeframe": approval.get("timeframe"),
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    request_hash = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:16]
    return {
        "request_id": f"approved-bounded-validation-{request_hash}",
        "symbols": list(approval.get("symbols") or []),
        "preset_id": str(approval.get("preset_id") or ""),
        "timeframe": str(approval.get("timeframe") or ""),
        "approval_ref": str(approval.get("approval_id") or ""),
        "required_artifact_types": [
            "generation_manifest",
            "structured_lineage_artifact",
            "structured_oos_artifact",
        ],
        "allowed_output_paths": list(ALLOWED_OUTPUT_PATHS),
        "forbidden_capabilities": [],
        "created_at_utc": created_at_utc,
        "source": "operator_approval_manifest",
    }


def _candidate_ids_from_queue(
    *,
    repo_root: Path,
    symbols: list[str],
    preset_id: str,
    timeframe: str,
) -> dict[str, str]:
    payload = _read_json(repo_root / "logs/qre_basket_next_action_queue/latest.json")
    rows = payload.get("rows")
    if not isinstance(rows, list):
        raise ApprovedBoundedEvidenceError("next action queue rows missing")
    out: dict[str, str] = {}
    wanted = {symbol.upper() for symbol in symbols}
    for row in rows:
        if not isinstance(row, Mapping):
            continue
        symbol = str(row.get("symbol") or "").upper()
        if symbol not in wanted:
            continue
        if str(row.get("preset_id") or "") != preset_id:
            continue
        candidate_id = str(row.get("candidate_id") or "")
        if candidate_id:
            out[symbol] = candidate_id
    missing = sorted(wanted.difference(out))
    if missing:
        raise ApprovedBoundedEvidenceError(
            "missing candidate ids in current basket queue: " + ", ".join(missing)
        )
    return out


def _load_stitched_local_cache_frame(
    *,
    repo_root: Path,
    symbol: str,
    interval: str,
) -> pd.DataFrame:
    cache_root = repo_root / "data/cache/market"
    frames: list[pd.DataFrame] = []
    for path in cache_root.glob(f"yfinance__{symbol}__{interval}__*.parquet"):
        try:
            frame = pd.read_parquet(path, columns=["timestamp_utc", "open", "high", "low", "close", "volume"])
        except Exception:
            continue
        frames.append(frame)
    if not frames:
        raise ApprovedBoundedEvidenceError(f"no local cache bars for {symbol}/{interval}")
    merged = pd.concat(frames, ignore_index=True)
    merged["timestamp_utc"] = pd.to_datetime(merged["timestamp_utc"], utc=True)
    merged = merged.drop_duplicates(subset=["timestamp_utc"], keep="last").sort_values("timestamp_utc")
    merged = merged.set_index(merged["timestamp_utc"].dt.tz_convert("UTC").dt.tz_localize(None))
    merged = merged.drop(columns=["timestamp_utc"])
    return merged.astype(float)


def _bounded_window_label(approval: Mapping[str, Any]) -> str:
    bounded_window = approval.get("bounded_input_window")
    if isinstance(bounded_window, Mapping):
        label = str(bounded_window.get("selection_rule") or "").strip()
        if label:
            return label
    return "single_symbol_full_local_cache_extent"


def _normalize_window_bounds(window: Mapping[str, Any], *, field_name: str) -> tuple[str, str]:
    start = str(window.get("start") or "").strip()
    end = str(window.get("end") or "").strip()
    if not start or not end:
        raise ApprovedBoundedEvidenceError(f"missing {field_name} bounds")
    return start, end


def _is_date_only_bound(value: str) -> bool:
    try:
        datetime.strptime(value, "%Y-%m-%d")
    except ValueError:
        return False
    return True


def _restrict_frame_to_approval_window(
    *,
    frame: pd.DataFrame,
    approval: Mapping[str, Any],
) -> pd.DataFrame:
    bounded_window = approval.get("bounded_input_window")
    if not isinstance(bounded_window, Mapping) or not bounded_window:
        return frame.copy()

    start_text, end_text = _normalize_window_bounds(
        bounded_window,
        field_name="bounded_input_window",
    )
    start = pd.Timestamp(start_text)
    end = pd.Timestamp(end_text)

    if _is_date_only_bound(end_text):
        end_exclusive = end + pd.Timedelta(days=1)
        mask = (
            (frame.index >= start)
            & (frame.index < end_exclusive)
        )
    else:
        mask = (
            (frame.index >= start)
            & (frame.index <= end)
        )

    restricted = frame.loc[mask].copy()

    if restricted.empty:
        raise ApprovedBoundedEvidenceError(
            "approved bounded_input_window produced empty local frame"
        )

    return restricted


def _expected_oos_window(
    *,
    frame: pd.DataFrame,
    engine: BacktestEngine,
) -> tuple[pd.Timestamp, pd.Timestamp]:
    folds = build_evaluation_folds(len(frame), engine.evaluation_config)
    (_, _), (test_start, test_end) = folds[0]
    return pd.Timestamp(frame.index[test_start]), pd.Timestamp(frame.index[test_end])


def _validate_expected_oos_window(
    *,
    approval: Mapping[str, Any],
    expected_start: pd.Timestamp,
    expected_end: pd.Timestamp,
) -> None:
    configured = approval.get("oos_window")
    if not isinstance(configured, Mapping) or not configured:
        return
    start_text, end_text = _normalize_window_bounds(configured, field_name="oos_window")
    if expected_start.strftime("%Y-%m-%d") != start_text or expected_end.strftime("%Y-%m-%d") != end_text:
        raise ApprovedBoundedEvidenceError(
            "approved oos_window does not match deterministic single-split validation window"
        )


def _common_local_window(frames: Mapping[str, pd.DataFrame]) -> tuple[pd.Timestamp, pd.Timestamp]:
    starts = [frame.index.min() for frame in frames.values() if not frame.empty]
    ends = [frame.index.max() for frame in frames.values() if not frame.empty]
    if not starts or not ends:
        raise ApprovedBoundedEvidenceError("local cache frames missing timestamps")
    start = max(starts)
    end = min(ends)
    if start >= end:
        raise ApprovedBoundedEvidenceError("no overlapping local cache window")
    return pd.Timestamp(start), pd.Timestamp(end)


def _evaluate_symbol_with_local_cache(
    *,
    symbol: str,
    candidate_id: str,
    generation_run_id: str,
    frame: pd.DataFrame,
    source_ref: str,
    approval: Mapping[str, Any],
    preset_id: str | None = None,
    interval: str = "1d",
) -> LocalEvaluation:
    if preset_id:
        _strategy_name, strategy_factory = _resolve_single_preset_strategy(
            preset_id
        )
        strategy = strategy_factory()
    else:
        strategy = trend_pullback_v1_strategie()
    engine = BacktestEngine(
        start_datum=frame.index.min().strftime("%Y-%m-%d"),
        eind_datum=frame.index.max().strftime("%Y-%m-%d"),
        evaluation_config={"mode": "single_split", "train_ratio": 0.7},
    )
    engine.interval = interval
    expected_start, expected_end = _expected_oos_window(frame=frame, engine=engine)
    _validate_expected_oos_window(
        approval=approval,
        expected_start=expected_start,
        expected_end=expected_end,
    )
    folds = build_evaluation_folds(len(frame), engine.evaluation_config)
    context = AssetContext(
        asset=symbol,
        frame=frame.copy(),
        regime_frame=build_regime_frame(frame.copy(), engine.regime_config),
        folds=folds,
        reference_frame=None,
    )
    metrics = engine._evaluate_windows(strategy, [context], use_train=False)
    daily_returns = list(engine._last_window_samples.get("daily_returns", []))
    trade_events = list(engine._last_window_streams.get("oos_trade_events", []))
    execution_events = list(engine._last_window_streams.get("oos_execution_events", []))
    oos_bar_count = int(sum(1 for entry in engine._last_window_streams.get("oos_bar_returns", []) if entry.get("asset") == symbol))
    reason_record_refs = [
        f"{source_ref}#reason:lineage:{symbol}",
        f"{source_ref}#reason:oos:{symbol}",
    ]
    cost_ref = f"{source_ref}#cost:baseline:{symbol}"
    metric_fields = {
        "oos_trade_count": int(metrics.get("totaal_trades") or 0),
        "oos_return_pct": round(float(sum(daily_returns)) * 100.0, 4) if daily_returns else 0.0,
        "max_drawdown_pct": round(float(metrics.get("max_drawdown") or 0.0) * 100.0, 4),
        "deflated_sharpe": float(metrics.get("deflated_sharpe") or 0.0),
        "profit_factor": float(metrics.get("profit_factor") or 0.0),
        "expectancy": float(metrics.get("expectancy") or 0.0),
        "daily_bar_count": oos_bar_count,
        "trade_event_count": int(len(trade_events)),
        "execution_event_count": int(len(execution_events)),
    }
    return LocalEvaluation(
        symbol=symbol,
        candidate_id=candidate_id,
        generation_run_id=generation_run_id,
        oos_window_start=expected_start.tz_localize(UTC).isoformat().replace("+00:00", "Z"),
        oos_window_end=expected_end.tz_localize(UTC).isoformat().replace("+00:00", "Z"),
        oos_metric_fields=metric_fields,
        reason_record_refs=reason_record_refs,
        cost_slippage_assumption_refs=[cost_ref],
    )


def _source_artifact_name(approval_id: str) -> str:
    safe = approval_id.replace("/", "-").replace("\\", "-")
    return f"{safe}.v1.json"


def build_approved_bounded_evidence_materialization(
    *,
    approval_payload: Mapping[str, Any],
    repo_root: Path = Path("."),
    generated_at_utc: str | None = None,
    persist_intermediate_outputs: bool = True,
    approval_manifest_ref: str | None = None,
) -> dict[str, Any]:
    before = _protected_fingerprints(repo_root)
    generated_at = generated_at_utc or _utcnow()
    approval = _normalize_approval_payload(approval_payload)
    request = _build_request_payload(approval, created_at_utc=generated_at)
    gate = approval_gate.build_bounded_validation_approval_gate(
        approval,
        request,
        evaluated_at_utc=generated_at,
        requested_external_fetch=False,
        require_real_run=True,
        require_evidence_acceptance=True,
    )
    if gate["approval_gate_status"] != "approval_valid_for_bounded_validation":
        raise ApprovedBoundedEvidenceError(
            "approval gate blocked: " + ", ".join(gate.get("rejection_reasons") or [])
        )

    interval = TIMEFRAME_TO_INTERVAL.get(str(request["timeframe"]))
    if not interval:
        raise ApprovedBoundedEvidenceError(f"unsupported timeframe: {request['timeframe']}")

    candidate_ids = _candidate_ids_from_queue(
        repo_root=repo_root,
        symbols=list(request["symbols"]),
        preset_id=str(request["preset_id"]),
        timeframe=str(request["timeframe"]),
    )
    stitched_frames = {
        symbol: _load_stitched_local_cache_frame(repo_root=repo_root, symbol=symbol, interval=interval)
        for symbol in request["symbols"]
    }
    common_start, common_end = _common_local_window(stitched_frames)
    bounded_frames = {
        symbol: frame.loc[(frame.index >= common_start) & (frame.index <= common_end)].copy()
        for symbol, frame in stitched_frames.items()
    }
    bounded_frames = {
        symbol: _restrict_frame_to_approval_window(frame=frame, approval=approval)
        for symbol, frame in bounded_frames.items()
    }
    if any(frame.empty for frame in bounded_frames.values()):
        raise ApprovedBoundedEvidenceError("empty bounded frame after overlap restriction")

    generation_seed = json.dumps(
        {
            "approval_id": approval["approval_id"],
            "symbols": list(request["symbols"]),
            "preset_id": request["preset_id"],
            "timeframe": request["timeframe"],
            "common_start": common_start.isoformat(),
            "common_end": common_end.isoformat(),
        },
        sort_keys=True,
        separators=(",", ":"),
    )
    generation_run_id = "approved-bounded-validation-" + hashlib.sha256(generation_seed.encode("utf-8")).hexdigest()[:16]
    source_path = repo_root / SOURCE_ARTIFACT_DIR / _source_artifact_name(str(approval["approval_id"]))
    source_ref = source_path.relative_to(repo_root).as_posix()

    evaluations = [
        _evaluate_symbol_with_local_cache(
            symbol=symbol,
            candidate_id=candidate_ids[str(symbol).upper()],
            generation_run_id=generation_run_id,
            frame=bounded_frames[symbol],
            source_ref=source_ref,
            approval=approval,
        )
        for symbol in request["symbols"]
    ]
    source_payload = {
        "schema_version": SCHEMA_VERSION,
        "report_kind": "qre_bounded_local_cache_controlled_validation_source",
        "generated_at_utc": generated_at,
        "approval_id": approval["approval_id"],
        "approval_manifest_ref": approval_manifest_ref or DEFAULT_APPROVAL_PATH.as_posix(),
        "source_type": "structured_controlled_validation",
        "source_authority": "structured_source",
        "source_ref": source_ref,
        "source_metadata_kind": "approved_local_cache_strategy_validation",
        "no_external_fetch": True,
        "run_research_called": False,
        "campaign_launcher_called": False,
        "frozen_contracts_unchanged": True,
        "protected_paths_unchanged": True,
        "generation_run_id": generation_run_id,
        "timeframe_interval": interval,
        "bounded_input_window": {
            "start": bounded_frames[request["symbols"][0]].index.min().strftime("%Y-%m-%d"),
            "end": bounded_frames[request["symbols"][0]].index.max().strftime("%Y-%m-%d"),
            "label": _bounded_window_label(approval),
        },
        "lineage_records": [
            {
                "symbol": evaluation.symbol,
                "candidate_id": evaluation.candidate_id,
                "generation_run_id": evaluation.generation_run_id,
                "validation_status": "accepted",
                "reason_record_refs": evaluation.reason_record_refs,
            }
            for evaluation in evaluations
        ],
        "oos_records": [
            {
                "symbol": evaluation.symbol,
                "candidate_id": evaluation.candidate_id,
                "oos_window": {
                    "start": evaluation.oos_window_start,
                    "end": evaluation.oos_window_end,
                    "label": "approved_local_cache_overlap_window",
                },
                "oos_metric_fields": dict(evaluation.oos_metric_fields),
                "cost_slippage_assumption_refs": list(evaluation.cost_slippage_assumption_refs),
                "validation_status": "accepted",
                "reason_record_refs": evaluation.reason_record_refs,
            }
            for evaluation in evaluations
        ],
        "cost_slippage_assumptions": [
            {
                "ref": evaluation.cost_slippage_assumption_refs[0],
                "fee_per_side_fraction": 0.0035,
                "slippage_bps": 0.0,
                "source": "agent.backtesting.engine default cost model",
            }
            for evaluation in evaluations
        ],
        "reason_records": [
            {
                "ref": f"{source_ref}#reason:lineage:{evaluation.symbol}",
                "subject": evaluation.candidate_id,
                "reason_code": "approved_local_cache_generation_run",
            }
            for evaluation in evaluations
        ]
        + [
            {
                "ref": f"{source_ref}#reason:oos:{evaluation.symbol}",
                "subject": evaluation.candidate_id,
                "reason_code": "approved_local_cache_oos_metrics_materialized",
            }
            for evaluation in evaluations
        ],
    }
    source_payload["hash"] = hashlib.sha256(
        json.dumps(source_payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    ).hexdigest()

    runner_report = runner.build_bounded_current_basket_generation_runner(
        request,
        repo_root=repo_root,
        controlled_validation_source=source_payload,
    )
    if persist_intermediate_outputs:
        _write_json(repo_root / REQUEST_PATH, request)
        _write_json(source_path, source_payload)
        runner.write_outputs(runner_report, repo_root=repo_root)
    verifier_report = verifier.build_bounded_generation_artifact_acceptance_verifier(repo_root=repo_root)
    closure_report = closure.build_evidence_complete_basket_closure(repo_root=repo_root)
    _assert_protected_outputs_unchanged(repo_root, before)
    return {
        "schema_version": SCHEMA_VERSION,
        "report_kind": REPORT_KIND,
        "generated_at_utc": generated_at,
        "approval_gate": gate,
        "request": request,
        "source_ref": source_ref,
        "source_payload": source_payload,
        "runner_report": runner_report,
        "verifier_report": verifier_report,
        "closure_report": closure_report,
        "external_fetch_required": False,
        "hash": hashlib.sha256(
            json.dumps(
                {
                    "approval_id": approval["approval_id"],
                    "request_id": request["request_id"],
                    "source_ref": source_ref,
                    "runner_status": runner_report.get("runner_status"),
                    "accepted_lineage_count": verifier_report.get("summary", {}).get("accepted_lineage_candidate_count", 0),
                    "accepted_oos_count": verifier_report.get("summary", {}).get("accepted_oos_candidate_count", 0),
                    "evidence_complete_count": closure_report.get("summary", {}).get("evidence_complete_count", 0),
                },
                sort_keys=True,
                separators=(",", ":"),
                ensure_ascii=True,
            ).encode("utf-8")
        ).hexdigest(),
    }


def write_outputs(
    report: Mapping[str, Any],
    *,
    repo_root: Path = Path("."),
    output_dir: Path = DEFAULT_OUTPUT_DIR,
) -> dict[str, str]:
    _write_json(repo_root / REQUEST_PATH, report["request"])
    _write_json(repo_root / Path(str(report["source_ref"])), report["source_payload"])
    runner_paths = runner.write_outputs(report["runner_report"], repo_root=repo_root)
    verifier_paths = verifier.write_outputs(report["verifier_report"], repo_root=repo_root)
    closure_paths = closure.write_outputs(report["closure_report"], repo_root=repo_root)
    base = repo_root / output_dir
    base.mkdir(parents=True, exist_ok=True)
    latest_path = base / "latest.json"
    summary_path = base / "operator_summary.md"
    _write_json(latest_path, report)
    summary_lines = [
        "# Approved Bounded Evidence Materialization",
        "",
        f"- approval_gate_status: {report['approval_gate']['approval_gate_status']}",
        f"- request_id: {report['request']['request_id']}",
        f"- source_ref: {report['source_ref']}",
        f"- runner_status: {report['runner_report']['runner_status']}",
        f"- verifier accepted_lineage: {report['verifier_report']['summary']['accepted_lineage_candidate_count']}",
        f"- verifier accepted_oos: {report['verifier_report']['summary']['accepted_oos_candidate_count']}",
        f"- closure evidence_complete_count: {report['closure_report']['summary']['evidence_complete_count']}",
        "",
    ]
    summary_path.write_text("\n".join(summary_lines), encoding="utf-8")
    return {
        "request": REQUEST_PATH.as_posix(),
        "source": str(report["source_ref"]),
        "runner_latest": runner_paths.get("latest", ""),
        "verifier_latest": verifier_paths.get("latest", ""),
        "closure_latest": closure_paths.get("latest", ""),
        "latest": latest_path.relative_to(repo_root).as_posix(),
        "operator_summary": summary_path.relative_to(repo_root).as_posix(),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m research.qre_approved_bounded_evidence_materialization",
        description="Run the approved bounded local-cache evidence materialization path.",
    )
    parser.add_argument("--approval-file", default=DEFAULT_APPROVAL_PATH.as_posix())
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args(argv)

    approval_payload = _read_json(Path(args.approval_file))
    try:
        report = build_approved_bounded_evidence_materialization(
            approval_payload=approval_payload,
            approval_manifest_ref=Path(args.approval_file).as_posix(),
        )
    except ApprovedBoundedEvidenceError as exc:
        print(
            json.dumps(
                {
                    "report_kind": REPORT_KIND,
                    "result": "OPERATOR_APPROVAL_REQUIRED_FOR_EXTERNAL_FETCH"
                    if "no local cache" in str(exc) or "overlapping local cache window" in str(exc)
                    else "FAILED",
                    "error": str(exc),
                },
                indent=2,
                sort_keys=True,
            )
        )
        return 2
    if args.write:
        report["_artifact_paths"] = write_outputs(report)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
