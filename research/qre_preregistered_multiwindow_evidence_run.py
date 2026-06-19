from __future__ import annotations

import argparse
import hashlib
import json
import os
from collections import Counter
from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Final

from research import qre_approved_bounded_evidence_materialization as approved
from research import qre_bounded_generation_artifact_acceptance_verifier as verifier
from research import qre_controlled_validation_adapter as adapter
from research import qre_controlled_validation_adapter_result_materialization as materializer
from research import qre_failure_to_action_mapper as failure_mapper
from research import qre_preregistered_multiwindow_validation as campaign_builder
from research import qre_sampling_plan as sampling


SCHEMA_VERSION: Final[str] = "1.0"
REPORT_KIND: Final[str] = "qre_preregistered_multiwindow_evidence_run"
DEFAULT_APPROVAL_PATH: Final[Path] = Path(
    "research/operator_approvals/qre_preregistered_multiwindow_validation_approval.v1.json"
)
DEFAULT_OUTPUT_DIR: Final[Path] = Path("logs/qre_preregistered_multiwindow_evidence_run")
LATEST_NAME: Final[str] = "latest.json"
SUMMARY_NAME: Final[str] = "operator_summary.md"
WRITE_PREFIX: Final[str] = "logs/qre_preregistered_multiwindow_evidence_run/"
ALLOWED_OUTPUT_PATHS: Final[tuple[str, ...]] = (
    "logs/qre_bounded_current_basket_generation_runner/",
    "logs/qre_controlled_validation_adapter_results/",
    "logs/qre_bounded_generation_artifact_acceptance_verifier/",
    "logs/qre_evidence_complete_basket_closure/",
)
TIMEFRAME_TO_INTERVAL: Final[dict[str, str]] = {"daily_v1": "1d"}


def _text(value: Any) -> str:
    return str(value or "").strip()


def _unique_in_order(values: Sequence[Any]) -> list[str]:
    return list(dict.fromkeys(_text(value) for value in values if _text(value)))


def _read_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(payload, dict):
        raise ValueError(f"expected JSON object: {path.as_posix()}")
    return payload


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(tmp, path)


def _utcnow() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _candidate_scope(repo_root: Path, *, symbols: Sequence[str], preset_id: str) -> tuple[str, list[str]]:
    payload = _read_json(repo_root / "logs/qre_basket_next_action_queue/latest.json")
    rows = payload.get("rows") if isinstance(payload.get("rows"), list) else []
    candidate_ids: list[str] = []
    hypothesis_id = ""
    wanted = {symbol.upper() for symbol in symbols}
    for row in rows:
        if not isinstance(row, Mapping):
            continue
        if _text(row.get("symbol")).upper() not in wanted:
            continue
        if _text(row.get("preset_id")) != preset_id:
            continue
        candidate_id = _text(row.get("candidate_id"))
        if candidate_id:
            candidate_ids.append(candidate_id)
        if not hypothesis_id:
            hypothesis_id = _text(row.get("hypothesis_id"))
    if not candidate_ids or not hypothesis_id:
        raise ValueError("missing_queue_candidate_scope")
    return hypothesis_id, sorted(set(candidate_ids))


def _load_common_trading_dates(repo_root: Path, *, symbols: Sequence[str], timeframe: str) -> list[str]:
    interval = TIMEFRAME_TO_INTERVAL[timeframe]
    date_sets: list[set[str]] = []
    for symbol in symbols:
        frame = approved._load_stitched_local_cache_frame(repo_root=repo_root, symbol=symbol, interval=interval)
        date_sets.append({index.strftime("%Y-%m-%d") for index in frame.index})
    common = sorted(set.intersection(*date_sets)) if date_sets else []
    if not common:
        raise ValueError("missing_common_local_trading_dates")
    return common


def build_sampling_plan_for_multiwindow_approval(
    *,
    approval_manifest: Mapping[str, Any],
    repo_root: Path = Path("."),
) -> dict[str, Any]:
    scope = approval_manifest.get("scope") if isinstance(approval_manifest.get("scope"), Mapping) else {}
    symbols = list(scope.get("symbols") or [])
    preset_id = _text(scope.get("preset_id"))
    timeframe = _text(scope.get("timeframe"))
    hypothesis_id, _ = _candidate_scope(repo_root, symbols=symbols, preset_id=preset_id)
    common_dates = _load_common_trading_dates(repo_root, symbols=symbols, timeframe=timeframe)
    window_definitions = list(scope.get("window_definitions") or [])
    if not window_definitions:
        window_definitions = sampling.derive_preregistered_windows(
            trading_dates=common_dates,
            window_count=2,
            minimum_window_length=20,
            minimum_warmup_period=10,
            regime_labels=["trend", "high_volatility"],
        )
    else:
        window_definitions = [
            {
                **dict(window),
                "role": _text((window or {}).get("role")) or "oos",
                "locked": True if window.get("locked") is None else bool(window.get("locked")),
            }
            for window in window_definitions
            if isinstance(window, Mapping)
        ]
    return sampling.build_preregistered_sampling_plan(
        hypothesis_ref=hypothesis_id,
        behavior_id="trend_pullback",
        preset_id=preset_id,
        timeframe=timeframe,
        bounded_source_data_availability={
            "source_data_ref": _text(scope.get("source_data_ref")),
            "local_only": True,
        },
        proposed_total_validation_range=dict(scope.get("bounded_validation_range") or {}),
        minimum_window_length=20,
        minimum_warmup_period=10,
        required_oos_evidence_types=["structured_lineage", "structured_oos"],
        null_control_definitions=[
            {
                "control_id": "null_daily_holdout",
                "required_for_evidence_complete": True,
                "required_for_fail_closed_rejection": False,
            }
        ],
        known_previous_failed_windows=[
            {
                "scope_ref": "qre_bounded_validation_next_oos_source_001",
                "failure_class": "non_positive_oos_trade_count",
            }
        ],
        regime_buckets=[
            {"regime_label": "trend", "selection_basis": "preregistered_window_label"},
            {"regime_label": "high_volatility", "selection_basis": "preregistered_window_label"},
        ],
        window_definitions=window_definitions,
        preregistration_timestamp=_text(approval_manifest.get("approved_at_utc")),
        minimum_trade_requirement=1,
    )


def build_campaign_for_multiwindow_approval(
    *,
    approval_manifest: Mapping[str, Any],
    sampling_plan_payload: Mapping[str, Any],
) -> dict[str, Any]:
    scope = approval_manifest.get("scope") if isinstance(approval_manifest.get("scope"), Mapping) else {}
    return campaign_builder.build_preregistered_multiwindow_validation(
        sampling_plan_payload=sampling_plan_payload,
        approval_manifest=approval_manifest,
        local_source_ref=_text(scope.get("source_data_ref")),
        minimum_required_windows=2,
        minimum_total_oos_trades=1,
        per_window_minimum_oos_trades=1,
        null_control_requirements=[
            {"control_id": "null_daily_holdout", "required_for_evidence_complete": True}
        ],
    )


def _window_approval(
    *,
    approval_manifest: Mapping[str, Any],
    symbol: str,
    window_spec: Mapping[str, Any],
) -> dict[str, Any]:
    scope = approval_manifest.get("scope") if isinstance(approval_manifest.get("scope"), Mapping) else {}
    approval_id = f"{_text(approval_manifest.get('approval_id'))}__{_text(window_spec.get('window_id'))}__{symbol}"
    return {
        "approval_id": approval_id,
        "approved_by": _text(approval_manifest.get("approved_by")),
        "approved_at_utc": _text(approval_manifest.get("approved_at_utc")),
        "expiry_utc": _text(approval_manifest.get("expiry_utc") or approval_manifest.get("expires_at_utc")),
        "scope": {
            "symbols": [symbol],
            "preset_id": _text(scope.get("preset_id")),
            "timeframe": _text(scope.get("timeframe")),
            "source_data_ref": _text(scope.get("source_data_ref")),
            "bounded_input_window": dict(window_spec.get("bounded_input_window") or {}),
            "oos_window": dict(window_spec.get("oos_window") or {}),
        },
        "allowed_command_class": _text(approval_manifest.get("allowed_command_class")),
        "allowed_output_paths": list(approval_manifest.get("allowed_output_paths") or []),
        "forbidden_capabilities": list(approval_manifest.get("forbidden_capabilities") or []),
        "dry_run_allowed": bool(approval_manifest.get("dry_run_allowed", False)),
        "real_run_allowed": bool(approval_manifest.get("real_run_allowed", False)),
        "evidence_acceptance_allowed": bool(approval_manifest.get("evidence_acceptance_allowed", False)),
        "external_fetch_allowed": bool(approval_manifest.get("external_fetch_allowed", False)),
    }


def _source_payload_for_window(
    *,
    approval_payload: Mapping[str, Any],
    repo_root: Path,
) -> tuple[dict[str, Any], dict[str, Any]]:
    normalized = approved._normalize_approval_payload(approval_payload)
    request = approved._build_request_payload(
        normalized,
        created_at_utc=_utcnow(),
    )
    symbol = list(normalized["symbols"])[0]
    timeframe = _text(normalized["timeframe"])
    interval = TIMEFRAME_TO_INTERVAL[timeframe]
    candidate_ids = approved._candidate_ids_from_queue(
        repo_root=repo_root,
        symbols=[symbol],
        preset_id=_text(normalized["preset_id"]),
        timeframe=timeframe,
    )
    frame = approved._load_stitched_local_cache_frame(repo_root=repo_root, symbol=symbol, interval=interval)
    bounded_frame = approved._restrict_frame_to_approval_window(frame=frame, approval=normalized)
    source_ref = (
        "logs/qre_controlled_validation_adapter_results/source_artifacts/"
        f"{approval_payload['approval_id']}.v1.json"
    )
    evaluation = approved._evaluate_symbol_with_local_cache(
        symbol=symbol,
        candidate_id=candidate_ids[symbol.upper()],
        generation_run_id=f"{approval_payload['approval_id']}::generation",
        frame=bounded_frame,
        source_ref=source_ref,
        approval=normalized,
    )
    source_payload = {
        "schema_version": approved.SCHEMA_VERSION,
        "report_kind": "qre_bounded_local_cache_controlled_validation_source",
        "generated_at_utc": _utcnow(),
        "approval_id": approval_payload["approval_id"],
        "approval_manifest_ref": DEFAULT_APPROVAL_PATH.as_posix(),
        "source_type": "structured_controlled_validation",
        "source_authority": "structured_source",
        "source_ref": source_ref,
        "source_metadata_kind": "approved_local_cache_strategy_validation",
        "no_external_fetch": True,
        "lineage_records": [
            {
                "symbol": evaluation.symbol,
                "candidate_id": evaluation.candidate_id,
                "generation_run_id": evaluation.generation_run_id,
                "validation_status": "accepted",
                "reason_record_refs": evaluation.reason_record_refs,
            }
        ],
        "oos_records": [
            {
                "symbol": evaluation.symbol,
                "candidate_id": evaluation.candidate_id,
                "oos_window": {
                    "start": evaluation.oos_window_start,
                    "end": evaluation.oos_window_end,
                    "label": _text((approval_payload.get("scope") or {}).get("oos_window", {}).get("selection_rule"))
                    or "preregistered_oos_window",
                },
                "oos_metric_fields": dict(evaluation.oos_metric_fields),
                "cost_slippage_assumption_refs": list(evaluation.cost_slippage_assumption_refs),
                "validation_status": "accepted",
                "reason_record_refs": evaluation.reason_record_refs,
            }
        ],
        "cost_slippage_assumptions": [
            {
                "ref": evaluation.cost_slippage_assumption_refs[0],
                "fee_per_side_fraction": 0.0035,
                "slippage_bps": 0.0,
                "source": "agent.backtesting.engine default cost model",
            }
        ],
        "reason_records": [
            {
                "ref": evaluation.reason_record_refs[0],
                "subject": evaluation.candidate_id,
                "reason_code": "approved_local_cache_generation_run",
            },
            {
                "ref": evaluation.reason_record_refs[1],
                "subject": evaluation.candidate_id,
                "reason_code": "approved_local_cache_oos_metrics_materialized",
            },
        ],
    }
    source_payload["hash"] = hashlib.sha256(
        json.dumps(source_payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    ).hexdigest()
    return request, source_payload


def _classify_window_symbol(
    *,
    approval_manifest: Mapping[str, Any],
    window_spec: Mapping[str, Any],
    symbol: str,
    repo_root: Path,
) -> dict[str, Any]:
    approval_payload = _window_approval(
        approval_manifest=approval_manifest,
        symbol=symbol,
        window_spec=window_spec,
    )
    request, source_payload = _source_payload_for_window(
        approval_payload=approval_payload,
        repo_root=repo_root,
    )
    adapter_result = adapter.build_controlled_validation_adapter_result(
        request,
        controlled_validation_source=source_payload,
    )
    materialized = materializer.build_controlled_validation_adapter_result_materialization(adapter_result)
    row = verifier._classify_materialized_record(
        materialized,
        relative_path=f"logs/qre_controlled_validation_adapter_results/{approval_payload['approval_id']}.json",
        allowlisted_paths=list(ALLOWED_OUTPUT_PATHS),
    )
    oos_metrics = {}
    if source_payload["oos_records"]:
        oos_metrics = dict(source_payload["oos_records"][0].get("oos_metric_fields") or {})
    positive_trades = int(oos_metrics.get("oos_trade_count") or 0) if row["accepted_for_oos_evidence"] else 0
    return {
        "window_id": _text(window_spec.get("window_id")),
        "symbol": symbol,
        "request_id": request["request_id"],
        "approval_id": approval_payload["approval_id"],
        "source_ref": source_payload["source_ref"],
        "classification": row["classification"],
        "accepted_lineage_count": int(row.get("accepted_lineage_count") or 0),
        "accepted_oos_count": int(row.get("accepted_oos_count") or 0),
        "positive_oos_trade_count": positive_trades,
        "oos_trade_count": int(oos_metrics.get("oos_trade_count") or 0),
        "rejection_reasons": list(dict.fromkeys([
            *list(row.get("rejection_reasons") or []),
            *list(row.get("oos_rejection_reasons") or []),
        ])),
        "lineage_records": list(row.get("accepted_lineage_records") or []),
        "oos_records": list(row.get("accepted_oos_records") or []),
        "adapter_result": adapter_result,
        "materialized_result": materialized,
    }


def compute_campaign_run_hash(report: Mapping[str, Any]) -> str:
    canonical = {
        "schema_version": report.get("schema_version", SCHEMA_VERSION),
        "report_kind": report.get("report_kind", REPORT_KIND),
        "campaign_id": report.get("campaign_id", ""),
        "sampling_plan_id": report.get("sampling_plan_id", ""),
        "campaign_plan_hash": report.get("campaign_plan_hash", ""),
        "accepted_lineage_count": int(report.get("accepted_lineage_count", 0) or 0),
        "accepted_oos_count": int(report.get("accepted_oos_count", 0) or 0),
        "positive_oos_trade_count_total": int(report.get("positive_oos_trade_count_total", 0) or 0),
        "failed_window_count": int(report.get("failed_window_count", 0) or 0),
        "accepted_window_count": int(report.get("accepted_window_count", 0) or 0),
        "rejection_reasons": list(report.get("rejection_reasons", [])),
        "campaign_outcome": report.get("campaign_outcome", ""),
    }
    blob = json.dumps(canonical, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def build_preregistered_multiwindow_evidence_run(
    *,
    approval_manifest: Mapping[str, Any],
    repo_root: Path = Path("."),
) -> dict[str, Any]:
    sampling_plan_payload = build_sampling_plan_for_multiwindow_approval(
        approval_manifest=approval_manifest,
        repo_root=repo_root,
    )
    campaign_plan = build_campaign_for_multiwindow_approval(
        approval_manifest=approval_manifest,
        sampling_plan_payload=sampling_plan_payload,
    )
    if sampling_plan_payload["hash"] != campaign_plan["sampling_plan_hash"]:
        raise ValueError("sampling_plan_hash_mismatch")
    if campaign_plan["hash"] != campaign_builder.compute_campaign_hash(campaign_plan):
        raise ValueError("campaign_plan_hash_mismatch")
    if campaign_plan["status"] != "campaign_ready_preregistered_context":
        return {
            "schema_version": SCHEMA_VERSION,
            "report_kind": REPORT_KIND,
            "campaign_id": campaign_plan["campaign_id"],
            "sampling_plan_id": sampling_plan_payload["sampling_plan_id"],
            "campaign_plan_hash": campaign_plan["hash"],
            "window_results": [],
            "regime_results": [],
            "accepted_lineage_count": 0,
            "accepted_oos_count": 0,
            "positive_oos_trade_count_total": 0,
            "failed_window_count": 0,
            "accepted_window_count": 0,
            "rejection_reasons": list(campaign_plan.get("blocked_reasons") or []),
            "null_control_results": {"status": "not_run_due_to_blocked_campaign"},
            "campaign_outcome": "blocked_approval",
            "can_clear_blockers": False,
            "can_promote_candidate": False,
            "can_activate_deployment": False,
            "hash": "",
        }

    window_results: list[dict[str, Any]] = []
    remaining = len(campaign_plan["window_run_specs"])
    for window_spec in campaign_plan["window_run_specs"]:
        symbol_results = [
            _classify_window_symbol(
                approval_manifest=approval_manifest,
                window_spec=window_spec,
                symbol=symbol,
                repo_root=repo_root,
            )
            for symbol in window_spec["symbols"]
        ]
        remaining -= 1
        accepted_oos_count = sum(item["accepted_oos_count"] for item in symbol_results)
        positive_trades = sum(max(0, item["positive_oos_trade_count"]) for item in symbol_results)
        rejection_reasons = _unique_in_order(
            [reason for item in symbol_results for reason in item["rejection_reasons"]]
        )
        window_failure = "window_accepted" if accepted_oos_count > 0 else "non_positive_oos_trade_count"
        next_action = (
            failure_mapper.map_failure_to_action(
                failure_class="non_positive_oos_trade_count",
                remaining_preregistered_window_count=remaining,
            )
            if window_failure != "window_accepted"
            else None
        )
        window_results.append(
            {
                "window_id": _text(window_spec.get("window_id")),
                "regime_label": _text(window_spec.get("regime_label")) or "unclassified",
                "bounded_input_window": dict(window_spec.get("bounded_input_window") or {}),
                "oos_window": dict(window_spec.get("oos_window") or {}),
                "symbol_results": symbol_results,
                "accepted_lineage_count": sum(item["accepted_lineage_count"] for item in symbol_results),
                "accepted_oos_count": accepted_oos_count,
                "positive_oos_trade_count_total": positive_trades,
                "rejection_reasons": rejection_reasons,
                "window_outcome": "accepted_oos_evidence" if accepted_oos_count > 0 else "non_positive_oos_trade_count",
                "recommended_next_action": dict(next_action or {}),
            }
        )

    regime_summary: dict[str, dict[str, Any]] = {}
    for window in window_results:
        regime = _text(window.get("regime_label")) or "unclassified"
        bucket = regime_summary.setdefault(
            regime,
            {
                "regime_label": regime,
                "window_count": 0,
                "accepted_window_count": 0,
                "positive_oos_trade_count_total": 0,
                "rejection_reasons": [],
            },
        )
        bucket["window_count"] += 1
        if int(window["accepted_oos_count"]) > 0:
            bucket["accepted_window_count"] += 1
        bucket["positive_oos_trade_count_total"] += int(window["positive_oos_trade_count_total"])
        bucket["rejection_reasons"] = _unique_in_order(
            [*bucket["rejection_reasons"], *list(window["rejection_reasons"] or [])]
        )

    accepted_lineage_count = sum(int(window["accepted_lineage_count"]) for window in window_results)
    accepted_oos_count = sum(int(window["accepted_oos_count"]) for window in window_results)
    positive_oos_trade_count_total = sum(int(window["positive_oos_trade_count_total"]) for window in window_results)
    accepted_window_count = sum(1 for window in window_results if int(window["accepted_oos_count"]) > 0)
    failed_window_count = len(window_results) - accepted_window_count
    rejection_reasons = _unique_in_order(
        [reason for window in window_results for reason in window.get("rejection_reasons", [])]
    )
    if accepted_oos_count > 0 and accepted_window_count >= int(campaign_plan["minimum_required_windows"]) and positive_oos_trade_count_total >= int(campaign_plan["minimum_total_oos_trades"]):
        campaign_outcome = "accepted_multiwindow_oos_evidence"
    elif accepted_oos_count > 0 and positive_oos_trade_count_total < int(campaign_plan["minimum_total_oos_trades"]):
        campaign_outcome = "insufficient_total_oos_trades"
    elif accepted_oos_count > 0:
        campaign_outcome = "partial_oos_evidence"
    elif (
        failed_window_count == len(window_results)
        and all(
            int(item.get("oos_trade_count") or 0) <= 0
            for window in window_results
            for item in window.get("symbol_results", [])
        )
    ):
        campaign_outcome = "all_windows_non_positive_trade_count"
    else:
        campaign_outcome = "hypothesis_not_supported"
    report = {
        "schema_version": SCHEMA_VERSION,
        "report_kind": REPORT_KIND,
        "campaign_id": campaign_plan["campaign_id"],
        "sampling_plan_id": sampling_plan_payload["sampling_plan_id"],
        "sampling_plan_hash": sampling_plan_payload["hash"],
        "campaign_plan_hash": campaign_plan["hash"],
        "window_results": window_results,
        "regime_results": list(regime_summary.values()),
        "accepted_lineage_count": accepted_lineage_count,
        "accepted_oos_count": accepted_oos_count,
        "positive_oos_trade_count_total": positive_oos_trade_count_total,
        "failed_window_count": failed_window_count,
        "accepted_window_count": accepted_window_count,
        "rejection_reasons": rejection_reasons,
        "null_control_results": {
            "status": "not_run_due_to_no_accepted_oos" if accepted_oos_count == 0 else "pending_manual_null_control_review"
        },
        "campaign_outcome": campaign_outcome,
        "can_clear_blockers": False,
        "can_promote_candidate": False,
        "can_activate_deployment": False,
    }
    report["hash"] = compute_campaign_run_hash(report)
    return report


def _validate_write_target(path: Path) -> None:
    if WRITE_PREFIX not in path.as_posix():
        raise ValueError(f"{REPORT_KIND}: refusing write outside allowlist: {path!r}")


def write_outputs(report: Mapping[str, Any], *, repo_root: Path = Path(".")) -> dict[str, str]:
    base = repo_root / DEFAULT_OUTPUT_DIR
    base.mkdir(parents=True, exist_ok=True)
    latest = base / LATEST_NAME
    summary_path = base / SUMMARY_NAME
    for target in (latest, summary_path):
        _validate_write_target(target)
    _write_json(latest, report)
    summary = [
        "# QRE Preregistered Multi-Window Evidence Run",
        "",
        f"- campaign_id: {report.get('campaign_id', '')}",
        f"- accepted_lineage_count: {report.get('accepted_lineage_count', 0)}",
        f"- accepted_oos_count: {report.get('accepted_oos_count', 0)}",
        f"- positive_oos_trade_count_total: {report.get('positive_oos_trade_count_total', 0)}",
        f"- campaign_outcome: {report.get('campaign_outcome', '')}",
        "",
    ]
    summary_path.write_text("\n".join(summary), encoding="utf-8")
    return {
        "latest": latest.relative_to(repo_root).as_posix(),
        "operator_summary": summary_path.relative_to(repo_root).as_posix(),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m research.qre_preregistered_multiwindow_evidence_run",
        description="Execute the preregistered multi-window local-only evidence campaign.",
    )
    parser.add_argument("--approval-file", default=DEFAULT_APPROVAL_PATH.as_posix())
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args(argv)
    report = build_preregistered_multiwindow_evidence_run(
        approval_manifest=_read_json(Path(args.approval_file)),
    )
    if args.write:
        report["_artifact_paths"] = write_outputs(report)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
