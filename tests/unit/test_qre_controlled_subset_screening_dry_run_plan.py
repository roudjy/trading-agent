import json
from pathlib import Path

import pytest

from research.qre_controlled_subset_screening_dry_run_plan import (
    ScreeningDryRunPlanError,
    build_screening_dry_run_plan,
    render_operator_summary,
    write_outputs,
)


def _envelope(symbol: str = "AAPL") -> dict:
    return {
        "local_runner_envelope_id": f"local-harness::runner-dryrun::qre-dryrun::{symbol}::trend_continuation_daily_v1::1d",
        "runner_dry_run_intent_id": f"runner-dryrun::qre-dryrun::{symbol}::trend_continuation_daily_v1::1d",
        "candidate_plan_id": f"qre-dryrun::{symbol}::trend_continuation_daily_v1::1d",
        "instrument_symbol": symbol,
        "asset_class": "equity",
        "region": "US",
        "behavior_preset_id": "trend_continuation_daily_v1",
        "timeframe": "1d",
        "primary_data_provider_symbol": symbol,
        "envelope_status": "local_harness_envelope_materialized_not_executed",
        "execution_performed": False,
        "subprocess_called": False,
        "network_called": False,
        "run_research_called": False,
        "campaign_launcher_called": False,
        "screening_called": False,
        "validation_called": False,
        "candidate_registry_mutated": False,
        "campaign_artifacts_mutated": False,
        "queue_mutated": False,
        "strategy_registered": False,
        "preset_mutated": False,
        "research_latest_mutated": False,
        "strategy_matrix_mutated": False,
        "paper_activation_allowed": False,
        "shadow_activation_allowed": False,
        "live_activation_allowed": False,
        "broker_execution_allowed": False,
        "risk_authority_allowed": False,
    }


def _packet(envelopes: list[dict]) -> dict:
    return {
        "schema_version": "1.0",
        "report_kind": "qre_controlled_subset_local_runner_harness",
        "summary": {
            "local_runner_harness_ready": True,
            "envelope_count": len(envelopes),
            "blocker_count": 0,
            "execution_performed": False,
            "subprocess_called": False,
            "network_called": False,
            "run_research_called": False,
            "campaign_launcher_called": False,
            "screening_called": False,
            "validation_called": False,
            "safe_to_execute_research": False,
        },
        "local_runner_envelopes": envelopes,
    }


def _write_packet(tmp_path: Path, payload: dict, *, bom: bool = False) -> Path:
    path = tmp_path / "local_harness.json"
    path.write_text(json.dumps(payload), encoding="utf-8-sig" if bom else "utf-8")
    return path


def test_screening_dry_run_plan_ready_for_clean_envelopes(tmp_path: Path) -> None:
    path = _write_packet(tmp_path, _packet([_envelope("AAPL"), _envelope("MSFT")]))

    packet = build_screening_dry_run_plan(path)

    assert packet["report_kind"] == "qre_controlled_subset_screening_dry_run_plan"
    assert packet["summary"]["screening_dry_run_plan_ready"] is True
    assert packet["summary"]["envelope_count"] == 2
    assert packet["summary"]["screening_plan_count"] == 2
    assert packet["summary"]["blocker_count"] == 0
    assert packet["summary"]["screening_executed"] is False
    assert packet["summary"]["validation_executed"] is False
    assert packet["summary"]["subprocess_called"] is False
    assert packet["summary"]["run_research_called"] is False
    assert packet["authority_boundaries"]["not_screening_execution"] is True
    assert packet["authority_boundaries"]["does_not_call_run_research"] is True


def test_screening_plan_record_fields(tmp_path: Path) -> None:
    path = _write_packet(tmp_path, _packet([_envelope("ADYEN")]))

    packet = build_screening_dry_run_plan(path)
    record = packet["screening_dry_run_plan_records"][0]

    assert record["screening_dry_run_plan_id"] == (
        "screening-dryrun-plan::local-harness::runner-dryrun::qre-dryrun::ADYEN::trend_continuation_daily_v1::1d"
    )
    assert record["instrument_symbol"] == "ADYEN"
    assert record["plan_status"] == "screening_dry_run_planned_not_executed"
    assert record["screening_mode"] == "local_dry_run_no_subprocess_no_network_no_mutation"
    assert record["screening_executed"] is False
    assert record["validation_executed"] is False
    assert record["candidate_registry_mutated"] is False


def test_counts_regions_assets_presets_timeframes(tmp_path: Path) -> None:
    envelopes = [
        {**_envelope("ADYEN"), "region": "NL/EU"},
        {**_envelope("AAPL"), "region": "US"},
        {**_envelope("SPY"), "asset_class": "etf", "region": "ETFs/context"},
    ]
    path = _write_packet(tmp_path, _packet(envelopes))

    packet = build_screening_dry_run_plan(path)

    assert packet["summary"]["region_counts"] == {"ETFs/context": 1, "NL/EU": 1, "US": 1}
    assert packet["summary"]["asset_class_counts"] == {"equity": 2, "etf": 1}
    assert packet["summary"]["preset_counts"] == {"trend_continuation_daily_v1": 3}
    assert packet["summary"]["timeframe_counts"] == {"1d": 3}


def test_blocks_not_ready_input(tmp_path: Path) -> None:
    payload = _packet([_envelope("AAPL")])
    payload["summary"]["local_runner_harness_ready"] = False
    path = _write_packet(tmp_path, payload)

    packet = build_screening_dry_run_plan(path)

    assert packet["summary"]["screening_dry_run_plan_ready"] is False
    assert "input_local_runner_harness_packet_not_ready" in packet["blockers"]


def test_blocks_crypto_envelope(tmp_path: Path) -> None:
    path = _write_packet(
        tmp_path,
        _packet([{**_envelope("BTC-USD"), "asset_class": "crypto_legacy"}]),
    )

    packet = build_screening_dry_run_plan(path)

    assert packet["summary"]["screening_dry_run_plan_ready"] is False
    assert any("forbidden_asset_class:crypto_legacy" in item for item in packet["blockers"])
    assert any("crypto_symbol_marker_detected" in item for item in packet["blockers"])


def test_blocks_any_true_execution_flag(tmp_path: Path) -> None:
    path = _write_packet(tmp_path, _packet([{**_envelope("AAPL"), "screening_called": True}]))

    packet = build_screening_dry_run_plan(path)

    assert packet["summary"]["screening_dry_run_plan_ready"] is False
    assert any("screening_called_true" in item for item in packet["blockers"])


def test_blocks_duplicate_envelopes(tmp_path: Path) -> None:
    path = _write_packet(tmp_path, _packet([_envelope("AAPL"), _envelope("AAPL")]))

    packet = build_screening_dry_run_plan(path)

    assert packet["summary"]["screening_dry_run_plan_ready"] is False
    assert packet["summary"]["duplicate_local_runner_envelope_id_count"] == 1
    assert any("duplicate_local_runner_envelope_id" in item for item in packet["blockers"])


def test_accepts_bom_input(tmp_path: Path) -> None:
    path = _write_packet(tmp_path, _packet([_envelope("AAPL")]), bom=True)

    packet = build_screening_dry_run_plan(path)

    assert packet["summary"]["screening_dry_run_plan_ready"] is True
    assert packet["screening_dry_run_plan_records"][0]["instrument_symbol"] == "AAPL"


def test_operator_summary_and_outputs(tmp_path: Path) -> None:
    path = _write_packet(tmp_path, _packet([_envelope("AAPL")]))
    packet = build_screening_dry_run_plan(path)

    summary = render_operator_summary(packet)
    outputs = write_outputs(packet, tmp_path / "out")

    assert "screening_dry_run_plan_ready: True" in summary
    assert "does not execute screening" in summary
    assert Path(outputs["latest"]).exists()
    assert Path(outputs["operator_summary"]).exists()
    assert json.loads(Path(outputs["latest"]).read_text(encoding="utf-8"))["summary"]["screening_plan_count"] == 1


def test_missing_input_raises() -> None:
    with pytest.raises(ScreeningDryRunPlanError):
        build_screening_dry_run_plan(Path("does/not/exist.json"))