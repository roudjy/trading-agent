import json
from pathlib import Path

import pytest

from research.qre_controlled_discovery_subset_adapter import (
    SubsetAdapterError,
    build_subset_adapter_packet,
    render_operator_summary,
    write_outputs,
)


def _safe_row(symbol: str = "AAPL") -> dict:
    return {
        "sequence_number": 1,
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
    }


def _write_subset(tmp_path: Path, rows: list[dict]) -> Path:
    path = tmp_path / "safe_executable_subset.json"
    path.write_text(json.dumps(rows), encoding="utf-8")
    return path


def test_build_subset_adapter_packet_is_operator_review_only(tmp_path: Path) -> None:
    path = _write_subset(tmp_path, [_safe_row("AAPL"), _safe_row("MSFT")])

    packet = build_subset_adapter_packet(path)

    assert packet["report_kind"] == "qre_controlled_discovery_subset_adapter"
    assert packet["summary"]["subset_adapter_ready"] is True
    assert packet["summary"]["subset_row_count"] == 2
    assert packet["summary"]["safe_to_execute_research"] is False
    assert packet["authority_boundaries"]["not_campaign_launch"] is True
    assert packet["authority_boundaries"]["not_paper_shadow_live"] is True
    assert packet["authority_boundaries"]["does_not_mutate_research_latest"] is True
    assert packet["authority_boundaries"]["does_not_mutate_strategy_matrix"] is True
    assert packet["safety_invariants"]["read_only"] is True
    assert packet["safety_invariants"]["broker_risk_execution_forbidden"] is True


def test_build_subset_adapter_packet_counts_regions_and_presets(tmp_path: Path) -> None:
    rows = [
        {**_safe_row("ADYEN"), "region": "NL/EU"},
        {**_safe_row("AAPL"), "region": "US"},
        {**_safe_row("SPY"), "asset_class": "etf", "region": "ETFs/context"},
    ]
    path = _write_subset(tmp_path, rows)

    packet = build_subset_adapter_packet(path)

    assert packet["summary"]["region_counts"] == {
        "ETFs/context": 1,
        "NL/EU": 1,
        "US": 1,
    }
    assert packet["summary"]["asset_class_counts"] == {"equity": 2, "etf": 1}
    assert packet["summary"]["preset_counts"] == {"trend_continuation_daily_v1": 3}


def test_build_subset_adapter_packet_blocks_crypto(tmp_path: Path) -> None:
    path = _write_subset(tmp_path, [{**_safe_row("BTC-USD"), "asset_class": "crypto_legacy"}])

    packet = build_subset_adapter_packet(path)

    assert packet["summary"]["subset_adapter_ready"] is False
    assert packet["summary"]["validation_blocker_count"] >= 1
    assert any("forbidden_asset_class:crypto_legacy" in item for item in packet["validation_blockers"])


def test_build_subset_adapter_packet_blocks_non_executable_rows(tmp_path: Path) -> None:
    path = _write_subset(tmp_path, [{**_safe_row("AAPL"), "classification": "seed_only"}])

    packet = build_subset_adapter_packet(path)

    assert packet["summary"]["subset_adapter_ready"] is False
    assert any("classification_not_executable" in item for item in packet["validation_blockers"])


def test_build_subset_adapter_packet_requires_provider_verified_identity(tmp_path: Path) -> None:
    path = _write_subset(
        tmp_path,
        [{**_safe_row("ASMI"), "source_identity_status": "candidate_alias_only"}],
    )

    packet = build_subset_adapter_packet(path)

    assert packet["summary"]["subset_adapter_ready"] is False
    assert any("source_identity_not_provider_verified" in item for item in packet["validation_blockers"])


def test_render_operator_summary_contains_authority_boundary(tmp_path: Path) -> None:
    path = _write_subset(tmp_path, [_safe_row("AAPL")])
    packet = build_subset_adapter_packet(path)

    summary = render_operator_summary(packet)

    assert "subset_adapter_ready: True" in summary
    assert "safe_to_execute_research: False" in summary
    assert "operator-review context only" in summary
    assert "does not launch research" in summary


def test_write_outputs_writes_latest_and_operator_summary(tmp_path: Path) -> None:
    path = _write_subset(tmp_path, [_safe_row("AAPL")])
    packet = build_subset_adapter_packet(path)

    outputs = write_outputs(packet, tmp_path / "out")

    latest = Path(outputs["latest"])
    summary = Path(outputs["operator_summary"])
    assert latest.exists()
    assert summary.exists()
    assert json.loads(latest.read_text(encoding="utf-8"))["summary"]["subset_row_count"] == 1
    assert "QRE Controlled Discovery Subset Adapter" in summary.read_text(encoding="utf-8")


def test_missing_input_raises() -> None:
    with pytest.raises(SubsetAdapterError):
        build_subset_adapter_packet(Path("does/not/exist.json"))
def test_build_subset_adapter_packet_accepts_utf8_bom_input(tmp_path: Path) -> None:
    path = tmp_path / "safe_executable_subset_bom.json"
    payload = json.dumps([_safe_row("AAPL")])
    path.write_text(payload, encoding="utf-8-sig")

    packet = build_subset_adapter_packet(path)

    assert packet["summary"]["subset_adapter_ready"] is True
    assert packet["summary"]["subset_row_count"] == 1
    assert packet["rows"][0]["instrument_symbol"] == "AAPL"