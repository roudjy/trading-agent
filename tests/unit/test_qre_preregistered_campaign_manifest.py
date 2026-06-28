from __future__ import annotations

import json
from pathlib import Path

import pytest

from reporting import qre_preregistered_campaign_manifest as manifest


FROZEN = "2026-06-28T10:30:00Z"


def _row(**overrides) -> dict[str, object]:
    base: dict[str, object] = {
        "cell_id": "qcp_ready_001",
        "thesis_id": "qbt_ready",
        "source_hypothesis_id": "trend_pullback_v1",
        "title": "Pullback Continuation",
        "behavior_family": "pullback_continuation",
        "mechanism": "Bounded pullback resumes the prior trend.",
        "preset_name": "trend_pullback_crypto_1h",
        "proposed_universe": ["BTC-EUR", "ETH-EUR"],
        "proposed_assets_or_basket": ["BTC-EUR", "ETH-EUR"],
        "proposed_timeframe": "1h",
        "proposed_regime_coverage": "trend",
        "source_readiness": {"status": "ready"},
        "data_readiness": {"status": "ready"},
        "identity_readiness": {"status": "ready"},
        "available_train_window": {
            "status": "range_visible_unassigned",
            "min_timestamp_utc": "2024-01-01T00:00:00Z",
            "max_timestamp_utc": "2025-01-01T00:00:00Z",
        },
        "available_validation_window": {
            "status": "range_visible_unassigned",
            "min_timestamp_utc": "2025-01-02T00:00:00Z",
            "max_timestamp_utc": "2025-06-01T00:00:00Z",
        },
        "available_oos_window": {
            "status": "range_visible_unassigned",
            "min_timestamp_utc": "2025-06-02T00:00:00Z",
            "max_timestamp_utc": "2025-09-01T00:00:00Z",
        },
        "null_control_feasibility": {"status": "defined", "defined_controls": ["shuffle_returns"]},
        "cost_and_slippage_readiness": {
            "status": "ready",
            "cost_mode": "realistic",
            "slippage_visible": True,
        },
        "minimum_sample": {"status": "visible", "value": 30},
        "expected_trade_count": {"status": "visible", "value": 42},
        "compute_estimate": {"status": "template_estimate_visible", "estimated_runtime_seconds_default": 1800},
        "timeout_risk": {"status": "bounded_by_visible_runtime_and_lease"},
        "next_action": "advance_to_broad_campaign_execution",
        "operator_decision": "SUPPORTED_FOR_REVIEW",
        "inclusion_status": "READY_FOR_PREREGISTRATION",
        "blocker_reasons": [],
        "provenance_refs": ["logs/qre_campaign_portfolio_plan/latest.json#rows[0]"],
    }
    base.update(overrides)
    return base


def _write_portfolio(path: Path, rows: list[dict[str, object]]) -> Path:
    payload = {
        "schema_version": "1.0",
        "report_kind": "qre_campaign_portfolio_plan",
        "portfolio_identity": "qcp_portfolio_fixture",
        "rows": rows,
        "summary": {
            "cell_count": len(rows),
            "ready_cell_count": sum(1 for row in rows if row.get("inclusion_status") == "READY_FOR_PREREGISTRATION"),
        },
    }
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path


def test_no_executable_cells_fail_closed(tmp_path: Path) -> None:
    source = _write_portfolio(
        tmp_path / "portfolio.json",
        [
            _row(
                cell_id="qcp_blocked",
                inclusion_status="BLOCKED",
                next_action="establish_campaign_lineage_for_thesis",
                available_oos_window={"status": "not_materialized"},
                null_control_feasibility={"status": "not_materialized"},
            )
        ],
    )

    snapshot = manifest.collect_snapshot(portfolio_path=source, generated_at_utc=FROZEN)

    assert snapshot["manifest_identity"].startswith("qcm_")
    assert snapshot["replay_identity"].startswith("qcr_")
    assert snapshot["executable_cells"] == []
    assert snapshot["summary"]["final_recommendation"] == "no_executable_cells_available_for_preregistration"
    assert snapshot["summary"]["execution_readiness"] == "blocked_no_executable_cells"
    assert snapshot["blocked_appendix"][0]["inclusion_status"] == "BLOCKED"


def test_ready_cell_materializes_when_all_required_fields_are_visible(tmp_path: Path) -> None:
    source = _write_portfolio(tmp_path / "portfolio.json", [_row()])

    snapshot = manifest.collect_snapshot(portfolio_path=source, generated_at_utc=FROZEN)

    assert snapshot["summary"]["executable_cell_count"] == 1
    cell = snapshot["executable_cells"][0]
    assert cell["preset_name"] == "trend_pullback_crypto_1h"
    assert cell["cell_manifest_identity"].startswith("qcmc_")
    assert snapshot["summary"]["final_recommendation"] == "preregistered_campaign_manifest_ready"


def test_ready_status_without_oos_or_null_controls_fails_closed(tmp_path: Path) -> None:
    source = _write_portfolio(
        tmp_path / "portfolio.json",
        [
            _row(
                available_oos_window={"status": "not_materialized"},
                null_control_feasibility={"status": "not_materialized"},
                blocker_reasons=["zero_accepted_oos", "null_controls_incomplete"],
            )
        ],
    )

    snapshot = manifest.collect_snapshot(portfolio_path=source, generated_at_utc=FROZEN)

    assert snapshot["summary"]["executable_cell_count"] == 0
    appendix = snapshot["blocked_appendix"][0]
    assert appendix["inclusion_status"] == "BLOCKED"
    assert "zero_accepted_oos" in appendix["blocker_reasons"]
    assert "oos_window_unavailable" in appendix["blocker_reasons"]
    assert "null_controls_incomplete" in appendix["blocker_reasons"]


def test_deterministic_identity_and_replay_identity(tmp_path: Path) -> None:
    source = _write_portfolio(tmp_path / "portfolio.json", [_row()])

    first = manifest.collect_snapshot(portfolio_path=source, generated_at_utc=FROZEN)
    second = manifest.collect_snapshot(portfolio_path=source, generated_at_utc=FROZEN)

    assert first == second


def test_atomic_write_refuses_outside_allowlist(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        manifest._atomic_write(tmp_path / "manifest.json", "{}")


def test_source_has_no_runtime_launch_or_network_calls() -> None:
    src = Path(manifest.__file__).read_text(encoding="utf-8")
    forbidden = (
        "import subprocess",
        "from subprocess",
        "subprocess.",
        "import socket",
        "from socket",
        "import requests",
        "import httpx",
        "import aiohttp",
        "import urllib",
        "from urllib",
        "os.system",
        "os.popen",
        "shell=True",
        "git ",
        "gh ",
        "codex ",
    )
    for token in forbidden:
        assert token not in src, token
