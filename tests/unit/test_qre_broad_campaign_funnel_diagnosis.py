from __future__ import annotations

import json
from pathlib import Path

import pytest

from reporting import qre_broad_campaign_funnel_diagnosis as diagnosis


FROZEN = "2026-06-28T12:30:00Z"


def _write_json(path: Path, payload: dict[str, object]) -> Path:
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path


def _execution_payload() -> dict[str, object]:
    return {
        "report_kind": "qre_broad_campaign_execution",
        "campaign_execution_identity": "qcy_fixture",
        "rows": [
            {
                "cell_id": "cell-1",
                "title": "Pullback Continuation",
                "source_hypothesis_id": "trend_pullback_v1",
                "preset_name": "trend_pullback_crypto_1h",
                "execution_status": "blocked",
                "status_reasons": ["campaign_identity", "source_identity", "data_snapshot_identity"],
                "stage_outcomes": {
                    "oos": {"status": "not_materialized"},
                    "null_controls": {"status": "not_materialized"},
                },
            },
            {
                "cell_id": "cell-2",
                "title": "Pullback Continuation",
                "source_hypothesis_id": "trend_pullback_v1",
                "preset_name": "trend_pullback_equities_4h",
                "execution_status": "rejected",
                "status_reasons": ["accepted_oos_count_zero", "null_controls_incomplete", "dead_zone_retrieval_visible"],
                "stage_outcomes": {
                    "oos": {"status": "all_windows_no_oos_trades"},
                    "null_controls": {"status": "controls_incomplete"},
                },
            },
            {
                "cell_id": "cell-3",
                "title": "Trend Continuation",
                "source_hypothesis_id": "atr_adaptive_trend_v0",
                "preset_name": "",
                "execution_status": "insufficient_evidence",
                "status_reasons": ["no_executable_preset_mapping", "campaign_scope_not_materialized"],
                "stage_outcomes": {
                    "oos": {"status": "not_materialized"},
                    "null_controls": {"status": "not_materialized"},
                },
            },
        ],
        "summary": {"executable_cell_count": 0},
    }


def _portfolio_payload() -> dict[str, object]:
    return {
        "report_kind": "qre_campaign_portfolio_plan",
        "portfolio_identity": "qcpp_fixture",
        "summary": {"ready_cell_count": 0},
        "rows": [
            {
                "cell_id": "cell-1",
                "behavior_family": "pullback_continuation",
                "mechanism": "bounded pullback",
                "proposed_timeframe": "1h",
                "proposed_regime_coverage": "trend",
                "expected_signal_density": {"value": "moderate"},
            },
            {
                "cell_id": "cell-2",
                "behavior_family": "pullback_continuation",
                "mechanism": "bounded pullback",
                "proposed_timeframe": "4h",
                "proposed_regime_coverage": "trend",
                "expected_signal_density": {"value": "moderate"},
            },
            {
                "cell_id": "cell-3",
                "behavior_family": "trend_continuation",
                "mechanism": "atr trend",
                "proposed_timeframe": "1d",
                "proposed_regime_coverage": "pending",
                "expected_signal_density": {"value": "low"},
            },
        ],
    }


def test_collect_snapshot_surfaces_primary_bottleneck_and_recommendations(tmp_path: Path) -> None:
    execution_path = _write_json(tmp_path / "execution.json", _execution_payload())
    portfolio_path = _write_json(tmp_path / "portfolio.json", _portfolio_payload())

    snapshot = diagnosis.collect_snapshot(
        execution_path=execution_path,
        portfolio_path=portfolio_path,
        generated_at_utc=FROZEN,
    )

    assert snapshot["summary"]["primary_bottleneck"] == "evidence_completeness"
    criteria = {row["criterion_id"]: row for row in snapshot["criterion_rows"]}
    assert criteria["evidence_completeness"]["recommendation"] == "keep"
    assert criteria["oos_acceptance"]["recommendation"] == "keep"
    assert criteria["null_controls"]["recommendation"] == "keep"
    assert snapshot["summary"]["all_criteria_have_exactly_one_recommendation"] is True


def test_funnel_counts_and_stratifications_are_deterministic(tmp_path: Path) -> None:
    execution_path = _write_json(tmp_path / "execution.json", _execution_payload())
    portfolio_path = _write_json(tmp_path / "portfolio.json", _portfolio_payload())

    first = diagnosis.collect_snapshot(
        execution_path=execution_path,
        portfolio_path=portfolio_path,
        generated_at_utc=FROZEN,
    )
    second = diagnosis.collect_snapshot(
        execution_path=execution_path,
        portfolio_path=portfolio_path,
        generated_at_utc=FROZEN,
    )

    assert first == second
    assert first["funnel_counts"]["raw_scope_count"] == 3
    assert first["funnel_counts"]["eligibility_ready_count"] == 0
    assert first["stratifications"]["by_behavior_family"][0]["label"] == "pullback_continuation"


def test_atomic_write_refuses_outside_allowlist(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        diagnosis._atomic_write(tmp_path / "latest.json", "{}")


def test_source_has_no_runtime_launch_or_network_calls() -> None:
    src = Path(diagnosis.__file__).read_text(encoding="utf-8")
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
