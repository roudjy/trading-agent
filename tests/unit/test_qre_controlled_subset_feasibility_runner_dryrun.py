import json
from pathlib import Path

import pytest

from research.qre_controlled_subset_candidate_feasibility import (
    CandidateFeasibilityError,
    build_feasibility_report,
    render_operator_summary as render_feasibility_summary,
    write_outputs as write_feasibility_outputs,
)
from research.qre_controlled_subset_runner_dry_run import (
    RunnerDryRunError,
    build_runner_dry_run_packet,
    render_operator_summary as render_runner_summary,
    write_outputs as write_runner_outputs,
)


def _candidate_record(symbol: str = "AAPL") -> dict:
    return {
        "candidate_plan_id": f"qre-dryrun::{symbol}::trend_continuation_daily_v1::1d",
        "subset_sequence_number": 1,
        "source_sequence_number": 125,
        "instrument_symbol": symbol,
        "asset_class": "equity",
        "region": "US",
        "behavior_preset_id": "trend_continuation_daily_v1",
        "timeframe": "1d",
        "classification": "executable",
        "mapping_status": "ready",
        "source_identity_status": "provider_symbol_verified",
        "primary_data_provider_symbol": symbol,
        "provider_symbol_status": "verified",
        "plan_status": "planned_not_executed",
        "screening_allowed": False,
        "validation_allowed": False,
        "execution_allowed": False,
        "campaign_launch_allowed": False,
        "candidate_promotion_allowed": False,
        "paper_activation_allowed": False,
        "shadow_activation_allowed": False,
        "live_activation_allowed": False,
    }


def _candidate_plan(records: list[dict]) -> dict:
    return {
        "schema_version": "1.0",
        "report_kind": "qre_controlled_subset_candidate_plan",
        "summary": {
            "candidate_plan_ready": True,
            "candidate_plan_count": len(records),
            "validation_blocker_count": 0,
            "safe_to_execute_research": False,
            "screening_allowed": False,
            "validation_allowed": False,
        },
        "candidate_plan_records": records,
    }


def _write_json(tmp_path: Path, payload: dict, *, name: str = "latest.json") -> Path:
    path = tmp_path / name
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_feasibility_report_ready_for_clean_candidate_plan(tmp_path: Path) -> None:
    path = _write_json(tmp_path, _candidate_plan([_candidate_record("AAPL"), _candidate_record("MSFT")]))

    report = build_feasibility_report(path)

    assert report["report_kind"] == "qre_controlled_subset_candidate_feasibility"
    assert report["summary"]["feasibility_report_ready"] is True
    assert report["summary"]["candidate_count"] == 2
    assert report["summary"]["hard_blocker_count"] == 0
    assert report["summary"]["runner_design_ready"] is True
    assert report["summary"]["safe_to_execute_research"] is False
    assert report["authority_boundaries"]["not_screening_execution"] is True
    assert report["authority_boundaries"]["does_not_mutate_research_latest"] is True


def test_feasibility_blocks_not_ready_candidate_plan(tmp_path: Path) -> None:
    payload = _candidate_plan([_candidate_record("AAPL")])
    payload["summary"]["candidate_plan_ready"] = False
    path = _write_json(tmp_path, payload)

    report = build_feasibility_report(path)

    assert report["summary"]["feasibility_report_ready"] is False
    assert "input_candidate_plan_not_ready" in report["hard_blockers"]


def test_feasibility_blocks_crypto_candidate(tmp_path: Path) -> None:
    record = {**_candidate_record("BTC-USD"), "asset_class": "crypto_legacy"}
    path = _write_json(tmp_path, _candidate_plan([record]))

    report = build_feasibility_report(path)

    assert report["summary"]["feasibility_report_ready"] is False
    assert any("forbidden_asset_class:crypto_legacy" in item for item in report["hard_blockers"])
    assert any("crypto_symbol_marker_detected" in item for item in report["hard_blockers"])


def test_feasibility_blocks_duplicate_candidate_ids(tmp_path: Path) -> None:
    records = [_candidate_record("AAPL"), _candidate_record("AAPL")]
    path = _write_json(tmp_path, _candidate_plan(records))

    report = build_feasibility_report(path)

    assert report["summary"]["duplicate_candidate_plan_id_count"] == 1
    assert report["summary"]["feasibility_report_ready"] is False
    assert any("duplicate_candidate_plan_id" in item for item in report["hard_blockers"])


def test_feasibility_summary_and_outputs(tmp_path: Path) -> None:
    path = _write_json(tmp_path, _candidate_plan([_candidate_record("AAPL")]))
    report = build_feasibility_report(path)

    summary = render_feasibility_summary(report)
    outputs = write_feasibility_outputs(report, tmp_path / "feasibility")

    assert "feasibility_report_ready: True" in summary
    assert "runner_design_ready: True" in summary
    assert Path(outputs["latest"]).exists()
    assert Path(outputs["operator_summary"]).exists()


def test_runner_dry_run_packet_ready_from_feasibility(tmp_path: Path) -> None:
    plan_path = _write_json(tmp_path, _candidate_plan([_candidate_record("AAPL"), _candidate_record("MSFT")]))
    feasibility = build_feasibility_report(plan_path)
    feasibility_path = _write_json(tmp_path, feasibility, name="feasibility.json")

    packet = build_runner_dry_run_packet(feasibility_path)

    assert packet["report_kind"] == "qre_controlled_subset_runner_dry_run"
    assert packet["summary"]["runner_dry_run_packet_ready"] is True
    assert packet["summary"]["runner_dry_run_intent_count"] == 2
    assert packet["summary"]["safe_to_execute_research"] is False
    assert packet["summary"]["run_research_called"] is False
    assert packet["summary"]["campaign_launcher_called"] is False
    assert packet["authority_boundaries"]["does_not_call_run_research"] is True
    assert packet["authority_boundaries"]["not_validation_execution"] is True


def test_runner_dry_run_intent_fields(tmp_path: Path) -> None:
    plan_path = _write_json(tmp_path, _candidate_plan([_candidate_record("ADYEN")]))
    feasibility = build_feasibility_report(plan_path)
    feasibility_path = _write_json(tmp_path, feasibility, name="feasibility.json")

    packet = build_runner_dry_run_packet(feasibility_path)
    intent = packet["runner_dry_run_intents"][0]

    assert intent["runner_dry_run_intent_id"] == "runner-dryrun::qre-dryrun::ADYEN::trend_continuation_daily_v1::1d"
    assert intent["instrument_symbol"] == "ADYEN"
    assert intent["intent_status"] == "runner_dry_run_intent_materialized_not_executed"
    assert intent["expected_runner_mode"] == "dry_run_no_subprocess_no_mutation"
    assert intent["run_research_called"] is False
    assert intent["screening_called"] is False
    assert intent["validation_called"] is False


def test_runner_dry_run_blocks_not_ready_feasibility(tmp_path: Path) -> None:
    plan_path = _write_json(tmp_path, _candidate_plan([_candidate_record("AAPL")]))
    feasibility = build_feasibility_report(plan_path)
    feasibility["summary"]["feasibility_report_ready"] = False
    feasibility_path = _write_json(tmp_path, feasibility, name="feasibility.json")

    packet = build_runner_dry_run_packet(feasibility_path)

    assert packet["summary"]["runner_dry_run_packet_ready"] is False
    assert "input_feasibility_report_not_ready" in packet["blockers"]


def test_runner_summary_and_outputs(tmp_path: Path) -> None:
    plan_path = _write_json(tmp_path, _candidate_plan([_candidate_record("AAPL")]))
    feasibility = build_feasibility_report(plan_path)
    feasibility_path = _write_json(tmp_path, feasibility, name="feasibility.json")
    packet = build_runner_dry_run_packet(feasibility_path)

    summary = render_runner_summary(packet)
    outputs = write_runner_outputs(packet, tmp_path / "runner")

    assert "runner_dry_run_packet_ready: True" in summary
    assert "does not call run_research" in summary
    assert Path(outputs["latest"]).exists()
    assert Path(outputs["operator_summary"]).exists()


def test_missing_inputs_raise() -> None:
    with pytest.raises(CandidateFeasibilityError):
        build_feasibility_report(Path("does/not/exist.json"))
    with pytest.raises(RunnerDryRunError):
        build_runner_dry_run_packet(Path("does/not/exist.json"))