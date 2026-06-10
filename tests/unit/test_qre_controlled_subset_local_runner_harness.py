import json
from pathlib import Path

import pytest

from research.qre_controlled_subset_local_runner_harness import (
    LocalRunnerHarnessError,
    build_local_runner_harness_packet,
    render_operator_summary,
    write_outputs,
)


def _intent(symbol: str = "AAPL") -> dict:
    return {
        "runner_dry_run_intent_id": f"runner-dryrun::qre-dryrun::{symbol}::trend_continuation_daily_v1::1d",
        "candidate_plan_id": f"qre-dryrun::{symbol}::trend_continuation_daily_v1::1d",
        "instrument_symbol": symbol,
        "asset_class": "equity",
        "region": "US",
        "behavior_preset_id": "trend_continuation_daily_v1",
        "timeframe": "1d",
        "primary_data_provider_symbol": symbol,
        "intent_status": "runner_dry_run_intent_materialized_not_executed",
        "expected_runner_mode": "dry_run_no_subprocess_no_mutation",
        "run_research_called": False,
        "campaign_launcher_called": False,
        "screening_called": False,
        "validation_called": False,
        "network_allowed": False,
        "external_data_allowed": False,
        "screening_allowed": False,
        "validation_allowed": False,
        "execution_allowed": False,
        "campaign_launch_allowed": False,
        "candidate_promotion_allowed": False,
        "paper_activation_allowed": False,
        "shadow_activation_allowed": False,
        "live_activation_allowed": False,
    }


def _packet(intents: list[dict]) -> dict:
    return {
        "schema_version": "1.0",
        "report_kind": "qre_controlled_subset_runner_dry_run",
        "summary": {
            "runner_dry_run_packet_ready": True,
            "runner_dry_run_intent_count": len(intents),
            "blocker_count": 0,
            "safe_to_execute_research": False,
            "screening_allowed": False,
            "validation_allowed": False,
            "run_research_called": False,
            "campaign_launcher_called": False,
        },
        "runner_dry_run_intents": intents,
    }


def _write_packet(tmp_path: Path, payload: dict, *, bom: bool = False) -> Path:
    path = tmp_path / "runner_dry_run.json"
    path.write_text(json.dumps(payload), encoding="utf-8-sig" if bom else "utf-8")
    return path


def test_local_runner_harness_ready_for_clean_intents(tmp_path: Path) -> None:
    path = _write_packet(tmp_path, _packet([_intent("AAPL"), _intent("MSFT")]))

    packet = build_local_runner_harness_packet(path)

    assert packet["report_kind"] == "qre_controlled_subset_local_runner_harness"
    assert packet["summary"]["local_runner_harness_ready"] is True
    assert packet["summary"]["intent_count"] == 2
    assert packet["summary"]["envelope_count"] == 2
    assert packet["summary"]["blocker_count"] == 0
    assert packet["summary"]["execution_performed"] is False
    assert packet["summary"]["subprocess_called"] is False
    assert packet["summary"]["run_research_called"] is False
    assert packet["summary"]["campaign_launcher_called"] is False
    assert packet["authority_boundaries"]["does_not_call_subprocess"] is True
    assert packet["authority_boundaries"]["does_not_call_run_research"] is True
    assert packet["authority_boundaries"]["does_not_mutate_research_latest"] is True


def test_local_runner_envelope_fields(tmp_path: Path) -> None:
    path = _write_packet(tmp_path, _packet([_intent("ADYEN")]))

    packet = build_local_runner_harness_packet(path)
    envelope = packet["local_runner_envelopes"][0]

    assert envelope["local_runner_envelope_id"] == (
        "local-harness::runner-dryrun::qre-dryrun::ADYEN::trend_continuation_daily_v1::1d"
    )
    assert envelope["instrument_symbol"] == "ADYEN"
    assert envelope["envelope_status"] == "local_harness_envelope_materialized_not_executed"
    assert envelope["execution_performed"] is False
    assert envelope["subprocess_called"] is False
    assert envelope["network_called"] is False
    assert envelope["screening_called"] is False
    assert envelope["validation_called"] is False
    assert envelope["candidate_registry_mutated"] is False


def test_local_runner_harness_counts_regions_assets_presets_timeframes(tmp_path: Path) -> None:
    intents = [
        {**_intent("ADYEN"), "region": "NL/EU"},
        {**_intent("AAPL"), "region": "US"},
        {**_intent("SPY"), "asset_class": "etf", "region": "ETFs/context"},
    ]
    path = _write_packet(tmp_path, _packet(intents))

    packet = build_local_runner_harness_packet(path)

    assert packet["summary"]["region_counts"] == {"ETFs/context": 1, "NL/EU": 1, "US": 1}
    assert packet["summary"]["asset_class_counts"] == {"equity": 2, "etf": 1}
    assert packet["summary"]["preset_counts"] == {"trend_continuation_daily_v1": 3}
    assert packet["summary"]["timeframe_counts"] == {"1d": 3}


def test_local_runner_harness_blocks_not_ready_input(tmp_path: Path) -> None:
    payload = _packet([_intent("AAPL")])
    payload["summary"]["runner_dry_run_packet_ready"] = False
    path = _write_packet(tmp_path, payload)

    packet = build_local_runner_harness_packet(path)

    assert packet["summary"]["local_runner_harness_ready"] is False
    assert "input_runner_dry_run_packet_not_ready" in packet["blockers"]


def test_local_runner_harness_blocks_crypto_intent(tmp_path: Path) -> None:
    path = _write_packet(
        tmp_path,
        _packet([{**_intent("BTC-USD"), "asset_class": "crypto_legacy"}]),
    )

    packet = build_local_runner_harness_packet(path)

    assert packet["summary"]["local_runner_harness_ready"] is False
    assert any("forbidden_asset_class:crypto_legacy" in item for item in packet["blockers"])
    assert any("crypto_symbol_marker_detected" in item for item in packet["blockers"])


def test_local_runner_harness_blocks_any_true_execution_flag(tmp_path: Path) -> None:
    path = _write_packet(tmp_path, _packet([{**_intent("AAPL"), "run_research_called": True}]))

    packet = build_local_runner_harness_packet(path)

    assert packet["summary"]["local_runner_harness_ready"] is False
    assert any("run_research_called_true" in item for item in packet["blockers"])


def test_local_runner_harness_blocks_duplicate_intents(tmp_path: Path) -> None:
    intents = [_intent("AAPL"), _intent("AAPL")]
    path = _write_packet(tmp_path, _packet(intents))

    packet = build_local_runner_harness_packet(path)

    assert packet["summary"]["local_runner_harness_ready"] is False
    assert packet["summary"]["duplicate_runner_dry_run_intent_id_count"] == 1
    assert any("duplicate_runner_dry_run_intent_id" in item for item in packet["blockers"])


def test_local_runner_harness_accepts_bom_input(tmp_path: Path) -> None:
    path = _write_packet(tmp_path, _packet([_intent("AAPL")]), bom=True)

    packet = build_local_runner_harness_packet(path)

    assert packet["summary"]["local_runner_harness_ready"] is True
    assert packet["local_runner_envelopes"][0]["instrument_symbol"] == "AAPL"


def test_operator_summary_and_outputs(tmp_path: Path) -> None:
    path = _write_packet(tmp_path, _packet([_intent("AAPL")]))
    packet = build_local_runner_harness_packet(path)

    summary = render_operator_summary(packet)
    outputs = write_outputs(packet, tmp_path / "out")

    assert "local_runner_harness_ready: True" in summary
    assert "does not call subprocess" in summary
    assert Path(outputs["latest"]).exists()
    assert Path(outputs["operator_summary"]).exists()
    assert json.loads(Path(outputs["latest"]).read_text(encoding="utf-8"))["summary"]["envelope_count"] == 1


def test_missing_input_raises() -> None:
    with pytest.raises(LocalRunnerHarnessError):
        build_local_runner_harness_packet(Path("does/not/exist.json"))