import json
from pathlib import Path

import pytest

from research.qre_controlled_subset_candidate_plan import (
    CandidatePlanError,
    build_candidate_plan,
    render_operator_summary,
    write_outputs,
)


def _adapter_row(symbol: str = "AAPL") -> dict:
    return {
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
        "execution_allowed": False,
        "campaign_launch_allowed": False,
        "paper_activation_allowed": False,
        "shadow_activation_allowed": False,
        "live_activation_allowed": False,
    }


def _packet(rows: list[dict]) -> dict:
    return {
        "schema_version": "1.0",
        "report_kind": "qre_controlled_discovery_subset_adapter",
        "summary": {
            "subset_adapter_ready": True,
            "subset_row_count": len(rows),
            "validation_blocker_count": 0,
            "safe_to_execute_research": False,
        },
        "rows": rows,
    }


def _write_packet(tmp_path: Path, payload: dict, *, bom: bool = False) -> Path:
    path = tmp_path / "latest.json"
    path.write_text(json.dumps(payload), encoding="utf-8-sig" if bom else "utf-8")
    return path


def test_build_candidate_plan_is_dry_run_only(tmp_path: Path) -> None:
    path = _write_packet(tmp_path, _packet([_adapter_row("AAPL"), _adapter_row("MSFT")]))

    plan = build_candidate_plan(path)

    assert plan["report_kind"] == "qre_controlled_subset_candidate_plan"
    assert plan["summary"]["candidate_plan_ready"] is True
    assert plan["summary"]["candidate_plan_count"] == 2
    assert plan["summary"]["safe_to_execute_research"] is False
    assert plan["summary"]["screening_allowed"] is False
    assert plan["summary"]["validation_allowed"] is False
    assert plan["authority_boundaries"]["not_screening_execution"] is True
    assert plan["authority_boundaries"]["not_validation_execution"] is True
    assert plan["authority_boundaries"]["does_not_mutate_research_latest"] is True
    assert plan["authority_boundaries"]["does_not_mutate_strategy_matrix"] is True


def test_candidate_plan_records_preserve_subset_identity(tmp_path: Path) -> None:
    row = {
        **_adapter_row("ADYEN"),
        "subset_sequence_number": 7,
        "source_sequence_number": 5,
        "region": "NL/EU",
        "primary_data_provider_symbol": "ADYEN.AS",
    }
    path = _write_packet(tmp_path, _packet([row]))

    plan = build_candidate_plan(path)
    record = plan["candidate_plan_records"][0]

    assert record["candidate_plan_id"] == "qre-dryrun::ADYEN::trend_continuation_daily_v1::1d"
    assert record["subset_sequence_number"] == 7
    assert record["source_sequence_number"] == 5
    assert record["instrument_symbol"] == "ADYEN"
    assert record["primary_data_provider_symbol"] == "ADYEN.AS"
    assert record["region"] == "NL/EU"
    assert record["plan_status"] == "planned_not_executed"
    assert record["screening_allowed"] is False
    assert record["validation_allowed"] is False


def test_candidate_plan_counts_regions_assets_presets_timeframes(tmp_path: Path) -> None:
    rows = [
        {**_adapter_row("ADYEN"), "region": "NL/EU"},
        {**_adapter_row("AAPL"), "region": "US"},
        {**_adapter_row("SPY"), "asset_class": "etf", "region": "ETFs/context"},
    ]
    path = _write_packet(tmp_path, _packet(rows))

    plan = build_candidate_plan(path)

    assert plan["summary"]["region_counts"] == {"ETFs/context": 1, "NL/EU": 1, "US": 1}
    assert plan["summary"]["asset_class_counts"] == {"equity": 2, "etf": 1}
    assert plan["summary"]["preset_counts"] == {"trend_continuation_daily_v1": 3}
    assert plan["summary"]["timeframe_counts"] == {"1d": 3}


def test_candidate_plan_blocks_not_ready_adapter_packet(tmp_path: Path) -> None:
    payload = _packet([_adapter_row("AAPL")])
    payload["summary"]["subset_adapter_ready"] = False
    path = _write_packet(tmp_path, payload)

    plan = build_candidate_plan(path)

    assert plan["summary"]["candidate_plan_ready"] is False
    assert "input_subset_adapter_not_ready_for_operator_review" in plan["validation_blockers"]


def test_candidate_plan_blocks_crypto(tmp_path: Path) -> None:
    path = _write_packet(
        tmp_path,
        _packet([{**_adapter_row("BTC-USD"), "asset_class": "crypto_legacy"}]),
    )

    plan = build_candidate_plan(path)

    assert plan["summary"]["candidate_plan_ready"] is False
    assert any("forbidden_asset_class:crypto_legacy" in item for item in plan["validation_blockers"])
    assert any("crypto_symbol_marker_detected" in item for item in plan["validation_blockers"])


def test_candidate_plan_blocks_duplicate_candidate_ids(tmp_path: Path) -> None:
    rows = [_adapter_row("AAPL"), _adapter_row("AAPL")]
    path = _write_packet(tmp_path, _packet(rows))

    plan = build_candidate_plan(path)

    assert plan["summary"]["candidate_plan_ready"] is False
    assert plan["summary"]["duplicate_candidate_plan_id_count"] == 1
    assert any("duplicate_candidate_plan_id:qre-dryrun::AAPL::trend_continuation_daily_v1::1d" in item for item in plan["validation_blockers"])


def test_candidate_plan_accepts_bom_input(tmp_path: Path) -> None:
    path = _write_packet(tmp_path, _packet([_adapter_row("AAPL")]), bom=True)

    plan = build_candidate_plan(path)

    assert plan["summary"]["candidate_plan_ready"] is True
    assert plan["candidate_plan_records"][0]["instrument_symbol"] == "AAPL"


def test_render_operator_summary_contains_dry_run_boundary(tmp_path: Path) -> None:
    path = _write_packet(tmp_path, _packet([_adapter_row("AAPL")]))
    plan = build_candidate_plan(path)

    summary = render_operator_summary(plan)

    assert "candidate_plan_ready: True" in summary
    assert "safe_to_execute_research: False" in summary
    assert "dry-run operator-review context only" in summary
    assert "does not run screening" in summary


def test_write_outputs_writes_latest_and_operator_summary(tmp_path: Path) -> None:
    path = _write_packet(tmp_path, _packet([_adapter_row("AAPL")]))
    plan = build_candidate_plan(path)

    outputs = write_outputs(plan, tmp_path / "out")

    latest = Path(outputs["latest"])
    summary = Path(outputs["operator_summary"])
    assert latest.exists()
    assert summary.exists()
    assert json.loads(latest.read_text(encoding="utf-8"))["summary"]["candidate_plan_count"] == 1
    assert "QRE Controlled Subset Candidate Plan" in summary.read_text(encoding="utf-8")


def test_missing_input_raises() -> None:
    with pytest.raises(CandidatePlanError):
        build_candidate_plan(Path("does/not/exist.json"))