from __future__ import annotations

import json
from pathlib import Path

import pytest

from reporting import qre_broad_campaign_execution as execution


FROZEN = "2026-06-28T11:30:00Z"


def _manifest(
    *,
    executable_cells: list[dict[str, object]] | None = None,
    blocked_appendix: list[dict[str, object]] | None = None,
) -> dict[str, object]:
    return {
        "schema_version": "1.0",
        "report_kind": "qre_preregistered_campaign_manifest",
        "manifest_identity": "qcm_fixture",
        "replay_identity": "qcr_fixture",
        "executable_cells": executable_cells or [],
        "blocked_appendix": blocked_appendix or [],
    }


def _appendix_row(**overrides) -> dict[str, object]:
    base: dict[str, object] = {
        "cell_id": "qcp_blocked_001",
        "thesis_id": "qbt_blocked",
        "source_hypothesis_id": "trend_pullback_v1",
        "preset_name": "trend_pullback_crypto_1h",
        "title": "Pullback Continuation: trend_pullback_v1",
        "inclusion_status": "BLOCKED",
        "operator_decision": "BLOCKED",
        "next_action": "reject_hypothesis",
        "blocker_reasons": ["accepted_oos_count_zero", "null_controls_incomplete"],
        "available_oos_window": {"status": "not_materialized"},
        "null_control_feasibility": {"status": "not_materialized"},
        "cost_and_slippage_readiness": {"status": "cost_mode_visible_slippage_not_materialized"},
        "provenance_refs": ["logs/qre_campaign_portfolio_plan/latest.json#rows[0]"],
    }
    base.update(overrides)
    return base


def _executable_row(**overrides) -> dict[str, object]:
    base: dict[str, object] = {
        "cell_id": "qcp_exec_001",
        "cell_manifest_identity": "qcmc_exec_001",
        "thesis_id": "qbt_exec",
        "source_hypothesis_id": "trend_pullback_v1",
        "preset_name": "trend_pullback_equities_4h",
        "title": "Pullback Continuation: trend_pullback_v1",
        "operator_decision": "SUPPORTED_FOR_REVIEW",
        "next_action": "advance_to_broad_campaign_execution",
        "proposed_universe": ["AAPL", "MSFT"],
        "proposed_assets_or_basket": ["AAPL", "MSFT"],
        "proposed_timeframe": "4h",
        "proposed_regime_coverage": "trend",
        "available_train_window": {"status": "range_visible_unassigned"},
        "available_validation_window": {"status": "range_visible_unassigned"},
        "available_oos_window": {"status": "range_visible_unassigned"},
        "null_control_feasibility": {"status": "defined"},
        "cost_and_slippage_readiness": {"status": "ready"},
        "compute_estimate": {"estimated_runtime_seconds_default": 1200},
        "timeout_risk": {"status": "bounded_by_visible_runtime_and_lease"},
        "provenance_refs": ["logs/qre_preregistered_campaign_manifest/latest.json#executable_cells[0]"],
    }
    base.update(overrides)
    return base


def _run_artifact(**overrides) -> dict[str, object]:
    base: dict[str, object] = {
        "report_kind": "qre_preregistered_multiwindow_evidence_run",
        "hash": "run_hash",
        "accepted_lineage_count": 12,
        "accepted_oos_count": 0,
        "positive_oos_trade_count_total": 0,
        "campaign_outcome": "all_windows_non_positive_trade_count",
        "proposal_id": "cpsp_fixture",
        "campaign_scope": {
            "hypothesis_id": "trend_pullback_v1",
            "preset_name": "trend_pullback_equities_4h",
            "campaign_id": "campaign_fixture",
        },
        "null_control_results": {
            "status": "controls_incomplete",
            "missing_control_ids": ["null_preregistered_holdout"],
            "recommended_next_action": "materialize_missing_preregistered_controls",
        },
    }
    base.update(overrides)
    return base


def _closure_artifact(**overrides) -> dict[str, object]:
    base: dict[str, object] = {
        "report_kind": "qre_multiwindow_evidence_closure",
        "hash": "closure_hash",
        "accepted_lineage_count": 12,
        "evidence_complete_count": 0,
        "closure_status": "all_windows_no_oos_trades",
        "hypothesis_disposition": "fail_closed_rejected",
        "proposal_id": "cpsp_fixture",
        "blockers_remaining": ["no_oos_evidence"],
        "campaign_scope": {
            "hypothesis_id": "trend_pullback_v1",
            "preset_name": "trend_pullback_equities_4h",
            "campaign_id": "campaign_fixture",
        },
    }
    base.update(overrides)
    return base


def _write_json(path: Path, payload: dict[str, object]) -> Path:
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path


def test_fail_closed_when_manifest_has_no_executable_cells(tmp_path: Path) -> None:
    source = _write_json(
        tmp_path / "manifest.json",
        _manifest(
            blocked_appendix=[
                _appendix_row(),
                _appendix_row(
                    cell_id="qcp_insufficient",
                    inclusion_status="INSUFFICIENT_EVIDENCE",
                    operator_decision="INSUFFICIENT_EVIDENCE",
                    blocker_reasons=["signal_density_unproven"],
                ),
                _appendix_row(
                    cell_id="qcp_dead_zone",
                    inclusion_status="EXCLUDED_DEAD_ZONE",
                    operator_decision="BLOCKED",
                    next_action="preserve_suppressed_scope_boundary",
                    blocker_reasons=["dead_zone_visible"],
                ),
            ]
        ),
    )

    snapshot = execution.collect_snapshot(manifest_path=source, generated_at_utc=FROZEN)

    assert snapshot["summary"]["final_recommendation"] == "broad_campaign_execution_fail_closed_no_executable_cells"
    assert snapshot["summary"]["status_counts"]["blocked"] == 1
    assert snapshot["summary"]["status_counts"]["insufficient_evidence"] == 1
    assert snapshot["summary"]["status_counts"]["not_executed"] == 1
    assert snapshot["summary"]["status_counts"]["completed"] == 0


def test_rejected_appendix_row_preserves_historical_evidence_links(tmp_path: Path) -> None:
    manifest_path = _write_json(
        tmp_path / "manifest.json",
        _manifest(
                blocked_appendix=[
                    _appendix_row(
                        inclusion_status="BLOCKED",
                        operator_decision="REJECTED",
                        preset_name="trend_pullback_equities_4h",
                    )
                ]
            ),
        )
    run_path = _write_json(tmp_path / "run.json", _run_artifact())
    closure_path = _write_json(tmp_path / "closure.json", _closure_artifact())

    snapshot = execution.collect_snapshot(
        manifest_path=manifest_path,
        run_artifact_path=run_path,
        closure_artifact_path=closure_path,
        generated_at_utc=FROZEN,
    )

    row = snapshot["rows"][0]
    assert row["execution_status"] == "rejected"
    assert row["historical_campaign_evidence"]["visible"] is True
    assert row["stage_outcomes"]["oos"]["status"] == "all_windows_no_oos_trades"
    assert row["stage_outcomes"]["null_controls"]["status"] == "controls_incomplete"


def test_executable_cell_without_materialized_execution_artifact_stays_not_executed(tmp_path: Path) -> None:
    manifest_path = _write_json(
        tmp_path / "manifest.json",
        _manifest(executable_cells=[_executable_row()]),
    )

    snapshot = execution.collect_snapshot(
        manifest_path=manifest_path,
        run_artifact_path=tmp_path / "missing-run.json",
        closure_artifact_path=tmp_path / "missing-closure.json",
        generated_at_utc=FROZEN,
    )

    assert snapshot["summary"]["final_recommendation"] == "broad_campaign_execution_incomplete_missing_execution_artifacts"
    row = snapshot["rows"][0]
    assert row["execution_status"] == "not_executed"
    assert "execution_artifact_missing_for_executable_cell" in row["status_reasons"]


def test_deterministic_identity_and_ordering(tmp_path: Path) -> None:
    manifest_path = _write_json(
        tmp_path / "manifest.json",
        _manifest(
            executable_cells=[_executable_row()],
            blocked_appendix=[_appendix_row(cell_id="b"), _appendix_row(cell_id="a")],
        ),
    )

    first = execution.collect_snapshot(manifest_path=manifest_path, generated_at_utc=FROZEN)
    second = execution.collect_snapshot(manifest_path=manifest_path, generated_at_utc=FROZEN)

    assert first == second
    assert [row["cell_id"] for row in first["rows"]] == ["a", "b", "qcp_exec_001"]


def test_atomic_write_refuses_outside_allowlist(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        execution._atomic_write(tmp_path / "latest.json", "{}")


def test_source_has_no_runtime_launch_or_network_calls() -> None:
    src = Path(execution.__file__).read_text(encoding="utf-8")
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
