import json
from pathlib import Path

import pytest

from research.qre_controlled_subset_screening_dry_run_executor import (
    ScreeningDryRunExecutorError,
    build_screening_dry_run_executor_packet,
    render_operator_summary,
    write_outputs,
)


def _plan(symbol: str = "AAPL") -> dict:
    return {
        "screening_dry_run_plan_id": f"screening-dryrun-plan::local-harness::runner-dryrun::qre-dryrun::{symbol}::trend_continuation_daily_v1::1d",
        "local_runner_envelope_id": f"local-harness::runner-dryrun::qre-dryrun::{symbol}::trend_continuation_daily_v1::1d",
        "runner_dry_run_intent_id": f"runner-dryrun::qre-dryrun::{symbol}::trend_continuation_daily_v1::1d",
        "candidate_plan_id": f"qre-dryrun::{symbol}::trend_continuation_daily_v1::1d",
        "instrument_symbol": symbol,
        "asset_class": "equity",
        "region": "US",
        "behavior_preset_id": "trend_continuation_daily_v1",
        "timeframe": "1d",
        "primary_data_provider_symbol": symbol,
        "plan_status": "screening_dry_run_planned_not_executed",
        "screening_mode": "local_dry_run_no_subprocess_no_network_no_mutation",
        "screening_executed": False,
        "validation_executed": False,
        "execution_performed": False,
        "subprocess_called": False,
        "network_called": False,
        "run_research_called": False,
        "campaign_launcher_called": False,
        "candidate_registry_mutated": False,
        "campaign_artifacts_mutated": False,
        "queue_mutated": False,
        "strategy_registered": False,
        "preset_mutated": False,
        "research_latest_mutated": False,
        "strategy_matrix_mutated": False,
        "candidate_promotion_allowed": False,
        "paper_activation_allowed": False,
        "shadow_activation_allowed": False,
        "live_activation_allowed": False,
        "broker_execution_allowed": False,
        "risk_authority_allowed": False,
    }


def _packet(records: list[dict]) -> dict:
    return {
        "schema_version": "1.0",
        "report_kind": "qre_controlled_subset_screening_dry_run_plan",
        "summary": {
            "screening_dry_run_plan_ready": True,
            "screening_plan_count": len(records),
            "blocker_count": 0,
            "screening_executed": False,
            "validation_executed": False,
            "execution_performed": False,
            "subprocess_called": False,
            "network_called": False,
            "run_research_called": False,
            "campaign_launcher_called": False,
            "safe_to_execute_research": False,
        },
        "screening_dry_run_plan_records": records,
    }


def _write_packet(tmp_path: Path, payload: dict, *, bom: bool = False) -> Path:
    path = tmp_path / "screening_plan.json"
    path.write_text(json.dumps(payload), encoding="utf-8-sig" if bom else "utf-8")
    return path


def test_executor_ready_for_clean_plan_records(tmp_path: Path) -> None:
    path = _write_packet(tmp_path, _packet([_plan("AAPL"), _plan("MSFT")]))

    packet = build_screening_dry_run_executor_packet(path)

    assert packet["report_kind"] == "qre_controlled_subset_screening_dry_run_executor"
    assert packet["summary"]["screening_dry_run_executor_ready"] is True
    assert packet["summary"]["input_screening_plan_count"] == 2
    assert packet["summary"]["screening_result_count"] == 2
    assert packet["summary"]["blocker_count"] == 0
    assert packet["summary"]["screening_executed"] is True
    assert packet["summary"]["validation_executed"] is False
    assert packet["summary"]["subprocess_called"] is False
    assert packet["summary"]["network_called"] is False
    assert packet["summary"]["run_research_called"] is False
    assert packet["authority_boundaries"]["metadata_only_screening"] is True
    assert packet["authority_boundaries"]["does_not_call_run_research"] is True


def test_result_record_fields(tmp_path: Path) -> None:
    path = _write_packet(tmp_path, _packet([_plan("ADYEN")]))

    packet = build_screening_dry_run_executor_packet(path)
    record = packet["screening_dry_run_result_records"][0]

    assert record["screening_dry_run_result_id"] == (
        "screening-dryrun-result::screening-dryrun-plan::local-harness::runner-dryrun::qre-dryrun::ADYEN::trend_continuation_daily_v1::1d"
    )
    assert record["instrument_symbol"] == "ADYEN"
    assert record["result_status"] == "screening_dry_run_result_materialized"
    assert record["screening_mode"] == "deterministic_local_metadata_check_only"
    assert record["screening_executed"] is True
    assert record["screening_result"] == "metadata_only_pass"
    assert record["validation_executed"] is False
    assert record["not_trade_signal"] is True


def test_counts_regions_assets_presets_timeframes_and_results(tmp_path: Path) -> None:
    records = [
        {**_plan("ADYEN"), "region": "NL/EU"},
        {**_plan("AAPL"), "region": "US"},
        {**_plan("SPY"), "asset_class": "etf", "region": "ETFs/context"},
    ]
    path = _write_packet(tmp_path, _packet(records))

    packet = build_screening_dry_run_executor_packet(path)

    assert packet["summary"]["region_counts"] == {"ETFs/context": 1, "NL/EU": 1, "US": 1}
    assert packet["summary"]["asset_class_counts"] == {"equity": 2, "etf": 1}
    assert packet["summary"]["preset_counts"] == {"trend_continuation_daily_v1": 3}
    assert packet["summary"]["timeframe_counts"] == {"1d": 3}
    assert packet["summary"]["screening_result_counts"] == {"metadata_only_pass": 3}


def test_blocks_not_ready_input(tmp_path: Path) -> None:
    payload = _packet([_plan("AAPL")])
    payload["summary"]["screening_dry_run_plan_ready"] = False
    path = _write_packet(tmp_path, payload)

    packet = build_screening_dry_run_executor_packet(path)

    assert packet["summary"]["screening_dry_run_executor_ready"] is False
    assert "input_screening_dry_run_plan_not_ready" in packet["blockers"]


def test_blocks_crypto_plan(tmp_path: Path) -> None:
    path = _write_packet(
        tmp_path,
        _packet([{**_plan("BTC-USD"), "asset_class": "crypto_legacy"}]),
    )

    packet = build_screening_dry_run_executor_packet(path)

    assert packet["summary"]["screening_dry_run_executor_ready"] is False
    assert any("forbidden_asset_class:crypto_legacy" in item for item in packet["blockers"])
    assert any("crypto_symbol_marker_detected" in item for item in packet["blockers"])


def test_blocks_any_true_execution_or_mutation_flag(tmp_path: Path) -> None:
    path = _write_packet(tmp_path, _packet([{**_plan("AAPL"), "network_called": True}]))

    packet = build_screening_dry_run_executor_packet(path)

    assert packet["summary"]["screening_dry_run_executor_ready"] is False
    assert any("network_called_true" in item for item in packet["blockers"])


def test_blocks_duplicate_plans(tmp_path: Path) -> None:
    path = _write_packet(tmp_path, _packet([_plan("AAPL"), _plan("AAPL")]))

    packet = build_screening_dry_run_executor_packet(path)

    assert packet["summary"]["screening_dry_run_executor_ready"] is False
    assert packet["summary"]["duplicate_screening_dry_run_plan_id_count"] == 1
    assert any("duplicate_screening_dry_run_plan_id" in item for item in packet["blockers"])


def test_accepts_bom_input(tmp_path: Path) -> None:
    path = _write_packet(tmp_path, _packet([_plan("AAPL")]), bom=True)

    packet = build_screening_dry_run_executor_packet(path)

    assert packet["summary"]["screening_dry_run_executor_ready"] is True
    assert packet["screening_dry_run_result_records"][0]["instrument_symbol"] == "AAPL"


def test_operator_summary_and_outputs(tmp_path: Path) -> None:
    path = _write_packet(tmp_path, _packet([_plan("AAPL")]))
    packet = build_screening_dry_run_executor_packet(path)

    summary = render_operator_summary(packet)
    outputs = write_outputs(packet, tmp_path / "out")

    assert "screening_dry_run_executor_ready: True" in summary
    assert "deterministic metadata-only screening dry-runs" in summary
    assert Path(outputs["latest"]).exists()
    assert Path(outputs["operator_summary"]).exists()
    assert json.loads(Path(outputs["latest"]).read_text(encoding="utf-8"))["summary"]["screening_result_count"] == 1


def test_missing_input_raises() -> None:
    with pytest.raises(ScreeningDryRunExecutorError):
        build_screening_dry_run_executor_packet(Path("does/not/exist.json"))