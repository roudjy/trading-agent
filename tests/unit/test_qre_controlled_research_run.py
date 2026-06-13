from __future__ import annotations

import json
from pathlib import Path

import pytest

from research.qre_controlled_research_run import (
    CONTROLLED_ASSETS,
    ControlledResearchRunError,
    build_controlled_research_packet,
    run_controlled_research,
    write_outputs,
)


def _record(symbol: str) -> dict:
    region = {
        "AAPL": "US",
        "ADYEN": "NL/EU",
        "ASML": "NL/EU",
        "EWJ": "ETFs/context",
        "MSFT": "US",
        "SONY": "Asia/proxies",
        "SPY": "ETFs/context",
        "TM": "Asia/proxies",
    }[symbol]
    asset_class = "etf" if symbol in {"EWJ", "SPY"} else "equity"
    return {
        "instrument_symbol": symbol,
        "asset_class": asset_class,
        "region": region,
        "behavior_preset_id": "trend_continuation_daily_v1",
        "timeframe": "1d",
        "primary_data_provider_symbol": symbol,
        "screening_result": "metadata_only_pass",
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
    }


def _packet() -> dict:
    return {
        "schema_version": "1.0",
        "report_kind": "qre_controlled_subset_screening_dry_run_executor",
        "summary": {
            "screening_dry_run_executor_ready": True,
            "screening_result_count": 8,
            "blocker_count": 0,
            "validation_executed": False,
            "execution_performed": False,
            "subprocess_called": False,
            "network_called": False,
            "external_data_called": False,
            "run_research_called": False,
            "campaign_launcher_called": False,
        },
        "screening_dry_run_result_records": [_record(symbol) for symbol in CONTROLLED_ASSETS],
    }


def _write_input(tmp_path: Path, payload: dict | None = None) -> Path:
    path = tmp_path / "executor.json"
    path.write_text(json.dumps(payload or _packet()), encoding="utf-8")
    return path


def test_one_command_materializes_two_controlled_loops(tmp_path: Path) -> None:
    input_path = _write_input(tmp_path)

    packet = run_controlled_research(
        input_path=input_path,
        output_dir=tmp_path / "out",
        loops=2,
        write=True,
    )

    assert packet["report_kind"] == "qre_controlled_research_run"
    assert packet["summary"]["controlled_research_run_ready"] is True
    assert packet["summary"]["loop_count"] == 2
    assert packet["summary"]["full_loop_materialized"] is True
    assert packet["summary"]["hypothesis_count"] == 2
    assert packet["summary"]["preset_selection_count"] == 2
    assert packet["summary"]["controlled_campaign_intent_count"] == 2
    assert packet["summary"]["metric_evidence_count"] == 2
    assert packet["summary"]["analysis_count"] == 2
    assert packet["summary"]["learning_feedback_count"] == 2
    assert packet["summary"]["next_action_count"] == 2
    assert packet["summary"]["run_research_called"] is False
    assert packet["summary"]["campaign_launcher_called"] is False
    assert packet["summary"]["validation_executed"] is False
    assert packet["summary"]["execution_performed"] is False


def test_loop_two_consumes_loop_one_learning(tmp_path: Path) -> None:
    packet = build_controlled_research_packet(input_path=_write_input(tmp_path), loops=2)
    loop_1, loop_2 = packet["runs"]

    assert loop_2["learning_feedback"]["consumes_previous_learning_feedback_id"] == (
        loop_1["learning_feedback"]["learning_feedback_id"]
    )
    assert "Loop 1 showed clean controlled metadata" in loop_2["hypothesis"]["statement"]
    assert loop_2["next_hypothesis_or_action"]["recommended_action"] == "add_cache_only_metric_path"


def test_metric_evidence_present_and_actionable_for_every_loop(tmp_path: Path) -> None:
    packet = build_controlled_research_packet(input_path=_write_input(tmp_path), loops=2)

    for run in packet["runs"]:
        evidence = run["metric_evidence"]
        assert evidence["metric_mode"] == "bounded_metric_evidence"
        assert evidence["true_metrics_available"] is False
        assert evidence["bounded_metric_evidence_available"] is True
        assert len(evidence["per_asset"]) == 8
        assert evidence["per_asset"][0]["blocker"] == "safe_metric_runner_missing_or_cache_unavailable"
        assert evidence["per_asset"][0]["next_action"] == "add_cache_only_metric_path"
        assert "no safe cache-only exact-universe metric path" in evidence["evidence_statement"]

    assert packet["summary"]["true_metric_count"] == 0
    assert packet["summary"]["bounded_metric_evidence_count"] == 2


def test_exact_universe_is_enforced(tmp_path: Path) -> None:
    payload = _packet()
    payload["screening_dry_run_result_records"] = payload["screening_dry_run_result_records"][:-1]
    input_path = _write_input(tmp_path, payload)

    with pytest.raises(ControlledResearchRunError, match="controlled_universe_mismatch"):
        build_controlled_research_packet(input_path=input_path, loops=2)


def test_duplicate_universe_rows_are_rejected(tmp_path: Path) -> None:
    payload = _packet()
    payload["screening_dry_run_result_records"][-1] = _record("AAPL")
    input_path = _write_input(tmp_path, payload)

    with pytest.raises(ControlledResearchRunError, match="duplicate_controlled_universe_rows"):
        build_controlled_research_packet(input_path=input_path, loops=2)


def test_crypto_is_rejected(tmp_path: Path) -> None:
    payload = _packet()
    payload["screening_dry_run_result_records"][0]["instrument_symbol"] = "BTC-USD"
    payload["screening_dry_run_result_records"][0]["asset_class"] = "crypto_legacy"
    input_path = _write_input(tmp_path, payload)

    with pytest.raises(ControlledResearchRunError, match="forbidden_asset_class"):
        build_controlled_research_packet(input_path=input_path, loops=2)


def test_region_asset_preset_and_timeframe_drift_are_rejected(tmp_path: Path) -> None:
    payload = _packet()
    payload["screening_dry_run_result_records"][0]["timeframe"] = "4h"
    input_path = _write_input(tmp_path, payload)

    with pytest.raises(ControlledResearchRunError, match="timeframe_drift"):
        build_controlled_research_packet(input_path=input_path, loops=2)


def test_protected_files_remain_unchanged_in_write_mode(tmp_path: Path) -> None:
    packet = run_controlled_research(
        input_path=_write_input(tmp_path),
        output_dir=tmp_path / "out",
        loops=2,
        write=True,
    )

    assert packet["summary"]["research_latest_mutated"] is False
    assert packet["summary"]["strategy_matrix_mutated"] is False


def test_write_outputs_use_required_artifact_names(tmp_path: Path) -> None:
    packet = build_controlled_research_packet(input_path=_write_input(tmp_path), loops=2)
    outputs = write_outputs(packet, output_dir=tmp_path / "out")

    assert Path(outputs["latest"]).name == "latest.json"
    assert Path(outputs["operator_summary"]).name == "operator_summary.md"
    assert Path(outputs["ledger"]).name == "ledger.jsonl"
    assert len(outputs["runs"]) == 2
    assert Path(outputs["runs"][0]).name.endswith("__loop__1.json")
    assert Path(outputs["runs"][1]).name.endswith("__loop__2.json")
    assert len(Path(outputs["ledger"]).read_text(encoding="utf-8").strip().splitlines()) == 2


def test_operator_summary_contains_required_flow(tmp_path: Path) -> None:
    packet = build_controlled_research_packet(input_path=_write_input(tmp_path), loops=2)
    outputs = write_outputs(packet, output_dir=tmp_path / "out")
    summary = Path(outputs["operator_summary"]).read_text(encoding="utf-8")

    assert "# QRE Controlled Research Run" in summary
    assert "hypothesis -> preset -> controlled campaign intent -> metric evidence -> analysis -> learning -> next hypothesis/action" in summary
    assert "## Loop 1" in summary
    assert "## Loop 2" in summary
    assert "- metric evidence mode: bounded_metric_evidence" in summary
    assert "- No paper/shadow/live." in summary
    assert "- No broker/risk authority." in summary
    assert "- No protected artifact mutation." in summary


def test_unsafe_loop_counts_are_rejected(tmp_path: Path) -> None:
    input_path = _write_input(tmp_path)

    with pytest.raises(ControlledResearchRunError, match="exactly 2"):
        build_controlled_research_packet(input_path=input_path, loops=1)
    with pytest.raises(ControlledResearchRunError, match="exactly 2"):
        build_controlled_research_packet(input_path=input_path, loops=3)


def test_source_has_no_runtime_imports_or_calls() -> None:
    source = Path("research/qre_controlled_research_run.py").read_text(encoding="utf-8")

    assert "import subprocess" not in source
    assert "from subprocess" not in source
    assert "import requests" not in source
    assert "import yfinance" not in source
    assert "campaign_launcher.main" not in source
    assert "run_research(" not in source
