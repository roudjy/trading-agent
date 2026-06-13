import json
from pathlib import Path

import pytest

from research.qre_controlled_closed_loop_dry_run import (
    CONTROLLED_ASSET_SET,
    ControlledClosedLoopError,
    build_closed_loop_packet,
    run_closed_loop,
    write_outputs,
)


def _record(symbol: str) -> dict:
    region = {
        "ADYEN": "NL/EU",
        "ASML": "NL/EU",
        "AAPL": "US",
        "MSFT": "US",
        "SONY": "Asia/proxies",
        "TM": "Asia/proxies",
        "SPY": "ETFs/context",
        "EWJ": "ETFs/context",
    }[symbol]
    asset_class = "etf" if symbol in {"SPY", "EWJ"} else "equity"
    return {
        "instrument_symbol": symbol,
        "asset_class": asset_class,
        "region": region,
        "behavior_preset_id": "trend_continuation_daily_v1",
        "timeframe": "1d",
        "primary_data_provider_symbol": symbol,
        "screening_result": "metadata_only_pass",
        "screening_executed": True,
        "validation_executed": False,
        "execution_performed": False,
        "subprocess_called": False,
        "network_called": False,
        "external_data_called": False,
        "run_research_called": False,
        "campaign_launcher_called": False,
        "candidate_promotion_allowed": False,
        "paper_activation_allowed": False,
        "shadow_activation_allowed": False,
        "live_activation_allowed": False,
        "broker_execution_allowed": False,
        "risk_authority_allowed": False,
        "candidate_registry_mutated": False,
        "campaign_artifacts_mutated": False,
        "queue_mutated": False,
        "strategy_registered": False,
        "preset_mutated": False,
        "research_latest_mutated": False,
        "strategy_matrix_mutated": False,
        "not_trade_signal": True,
    }


def _executor_packet() -> dict:
    records = [_record(symbol) for symbol in sorted(CONTROLLED_ASSET_SET)]
    return {
        "schema_version": "1.0",
        "report_kind": "qre_controlled_subset_screening_dry_run_executor",
        "summary": {
            "screening_dry_run_executor_ready": True,
            "screening_result_count": 8,
            "blocker_count": 0,
            "screening_result_counts": {"metadata_only_pass": 8},
            "validation_executed": False,
            "execution_performed": False,
            "subprocess_called": False,
            "network_called": False,
            "external_data_called": False,
            "run_research_called": False,
            "campaign_launcher_called": False,
            "safe_to_execute_research": False,
            "candidate_promotion_allowed": False,
            "paper_shadow_live_allowed": False,
        },
        "screening_dry_run_result_records": records,
    }


def _write_input(tmp_path: Path, payload: dict | None = None) -> Path:
    path = tmp_path / "executor_latest.json"
    path.write_text(json.dumps(payload or _executor_packet()), encoding="utf-8")
    return path


def test_builds_two_loop_closed_loop_packet(tmp_path: Path) -> None:
    input_path = _write_input(tmp_path)

    packet = build_closed_loop_packet(input_path, max_loops=2)

    assert packet["report_kind"] == "qre_controlled_closed_loop_dry_run"
    assert packet["summary"]["closed_loop_packet_ready"] is True
    assert packet["summary"]["loop_count"] == 2
    assert packet["summary"]["full_loop_materialized"] is True
    assert packet["summary"]["learning_feedback_count"] == 2
    assert packet["summary"]["next_loop_seed_count"] == 2
    assert packet["summary"]["run_research_called"] is False
    assert packet["summary"]["campaign_launcher_called"] is False
    assert packet["summary"]["validation_executed"] is False
    assert packet["summary"]["true_metric_execution_available"] is False


def test_loop_two_uses_loop_one_learning_feedback(tmp_path: Path) -> None:
    input_path = _write_input(tmp_path)

    packet = build_closed_loop_packet(input_path, max_loops=2)
    loop_1 = packet["runs"][0]
    loop_2 = packet["runs"][1]

    loop_2_market_intake = loop_2["phases"][0]
    loop_2_hypothesis = loop_2["phases"][1]

    assert loop_1["learning_feedback"]["learning_result"] == "all_assets_metadata_passed"
    assert loop_2_market_intake["intake_source"] == "previous_loop_learning_feedback"
    assert loop_2_market_intake["previous_feedback_summary"] == loop_1["learning_feedback"]["learning_statement"]
    assert loop_2_hypothesis["hypothesis_family"] == "bounded_metric_evidence_readiness"
    assert loop_2_hypothesis["hypothesis_adjustment"] == "advanced_from_metadata_screening_to_metric_evidence"


def test_phase_order_is_full_closed_loop(tmp_path: Path) -> None:
    input_path = _write_input(tmp_path)

    packet = build_closed_loop_packet(input_path, max_loops=1)
    run = packet["runs"][0]

    assert run["phase_order"] == [
        "market_intake",
        "hypothesis_generation",
        "strategy_formulation",
        "preset_selection",
        "campaign_planning",
        "controlled_result",
        "analysis",
        "learning_feedback",
        "next_loop_seed",
        "engine_readiness_probe",
    ]


def test_exact_asset_allowlist_required(tmp_path: Path) -> None:
    payload = _executor_packet()
    payload["screening_dry_run_result_records"] = payload["screening_dry_run_result_records"][:-1]
    input_path = _write_input(tmp_path, payload)

    with pytest.raises(ControlledClosedLoopError, match="controlled_asset_set_mismatch"):
        build_closed_loop_packet(input_path, max_loops=1)


def test_crypto_symbol_hard_fails(tmp_path: Path) -> None:
    payload = _executor_packet()
    payload["screening_dry_run_result_records"][0]["instrument_symbol"] = "BTC-USD"
    payload["screening_dry_run_result_records"][0]["asset_class"] = "crypto_legacy"
    input_path = _write_input(tmp_path, payload)

    with pytest.raises(ControlledClosedLoopError, match="forbidden_asset_class"):
        build_closed_loop_packet(input_path, max_loops=1)


def test_any_safety_flag_true_hard_fails(tmp_path: Path) -> None:
    payload = _executor_packet()
    payload["screening_dry_run_result_records"][0]["run_research_called"] = True
    input_path = _write_input(tmp_path, payload)

    with pytest.raises(ControlledClosedLoopError, match="run_research_called_not_false"):
        build_closed_loop_packet(input_path, max_loops=1)


def test_outputs_latest_runs_ledger_and_summary(tmp_path: Path) -> None:
    input_path = _write_input(tmp_path)
    packet = build_closed_loop_packet(input_path, max_loops=2)

    outputs = write_outputs(packet, output_dir=tmp_path / "out")

    latest_path = Path(outputs["latest"])
    summary_path = Path(outputs["operator_summary"])
    ledger_path = Path(outputs["ledger"])

    assert latest_path.exists()
    assert summary_path.exists()
    assert ledger_path.exists()
    assert len(ledger_path.read_text(encoding="utf-8").strip().splitlines()) == 2

    latest = json.loads(latest_path.read_text(encoding="utf-8"))
    assert latest["summary"]["loop_count"] == 2
    assert "Controlled closed-loop research dry-run completed" in summary_path.read_text(encoding="utf-8")


def test_run_closed_loop_write_mode_keeps_protected_outputs_unchanged(tmp_path: Path) -> None:
    input_path = _write_input(tmp_path)

    packet = run_closed_loop(
        input_path=input_path,
        output_dir=tmp_path / "out",
        max_loops=2,
        sleep_seconds=0,
        write=True,
    )

    assert packet["summary"]["closed_loop_packet_ready"] is True
    assert "_artifact_paths" in packet


def test_content_blocker_becomes_learning_not_process_failure(tmp_path: Path) -> None:
    payload = _executor_packet()
    payload["screening_dry_run_result_records"][0]["screening_result"] = "metadata_only_pass"
    input_path = _write_input(tmp_path, payload)

    packet = build_closed_loop_packet(input_path, max_loops=1)

    assert packet["runs"][0]["summary"]["content_blocker_count"] == 1
    assert packet["runs"][0]["content_blockers"] == ["true_metric_execution_not_yet_safe"]
    assert packet["runs"][0]["summary"]["safety_blocker_count"] == 0


def test_invalid_max_loops_rejected(tmp_path: Path) -> None:
    input_path = _write_input(tmp_path)

    with pytest.raises(ControlledClosedLoopError, match="at least 1"):
        build_closed_loop_packet(input_path, max_loops=0)

    with pytest.raises(ControlledClosedLoopError, match="capped"):
        build_closed_loop_packet(input_path, max_loops=26)


def test_source_does_not_import_dangerous_runtime_modules() -> None:
    source = Path("research/qre_controlled_closed_loop_dry_run.py").read_text(encoding="utf-8")

    assert "import subprocess" not in source
    assert "from subprocess" not in source
    assert "import requests" not in source
    assert "import yfinance" not in source
    assert "urllib.request" not in source
    assert "http.client" not in source