from __future__ import annotations

import json
from pathlib import Path

from research import qre_trusted_loop_operator_kpis as kpis


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _seed_complete_aapl_repo(tmp_path: Path) -> None:
    _write_json(
        tmp_path / "logs" / "qre_data_cache_manifest" / "latest.json",
        {"coverage": [{"instrument": "AAPL", "timeframe": "1d", "ready": True}]},
    )
    _write_json(
        tmp_path / "logs" / "qre_data_source_quality_readiness" / "latest.json",
        {"rows": [{"instrument": "AAPL", "timeframe": "1d", "quality_status": "ready"}]},
    )
    _write_json(
        tmp_path / "research" / "screening_evidence_latest.v1.json",
        {
            "candidates": [
                {
                    "asset": "AAPL",
                    "hypothesis_id": "trend_pullback_behavior_v1",
                    "stage_result": "screening_pass",
                    "validation_evidence": {
                        "status": "sufficient_oos_evidence",
                        "oos_trade_count": 12,
                    },
                }
            ]
        },
    )
    _write_json(
        tmp_path / "research" / "campaign_registry_latest.v1.json",
        {
            "campaigns": {
                "cmp-1": {
                    "preset_name": "trend_pullback_continuation_daily_v1",
                    "hypothesis_id": "trend_pullback_behavior_v1",
                    "state": "completed",
                }
            }
        },
    )
    _write_json(
        tmp_path / "research" / "candidate_registry_latest.v1.json",
        {"candidates": [{"asset": "AAPL", "status": "candidate"}]},
    )
    _write_json(
        tmp_path / "research" / "paper_readiness_latest.v1.json",
        {
            "entries": [
                {
                    "candidate_id": "candidate_0001",
                    "asset": "AAPL",
                    "readiness_status": "blocked",
                    "blocking_reasons": ["missing_execution_events"],
                }
            ]
        },
    )
    _write_json(
        tmp_path / "research" / "synthesis_gate_latest.v1.json",
        {
            "synthesis_gate_state": "blocked_insufficient_attribution",
            "allowed": False,
        },
    )
    _write_json(
        tmp_path / "logs" / "reason_records" / "manifest.v1.json",
        {
            "total_records": 0,
        },
    )


def test_build_trusted_loop_operator_kpis_stays_conservative_when_synthesis_blocked(
    tmp_path: Path,
) -> None:
    _seed_complete_aapl_repo(tmp_path)

    report = kpis.build_trusted_loop_operator_kpis(
        repo_root=tmp_path,
        max_candidates=2,
    )

    summary = report["summary"]
    assert summary["basket_inventory_count"] == 2
    assert summary["routing_ready_count"] >= 1
    assert summary["sampling_ready_count"] >= 1
    assert summary["reason_record_count"] >= 3
    assert summary["failure_actionable_count"] >= 1
    assert summary["trusted_loop_maturity_state"] == "working_capability"


def test_build_trusted_loop_operator_kpis_fail_closed_without_baskets(tmp_path: Path) -> None:
    report = kpis.build_trusted_loop_operator_kpis(
        repo_root=tmp_path,
        max_candidates=1,
    )

    assert report["summary"]["trusted_loop_maturity_state"] in {"scaffold", "working_capability"}
    assert report["safety_invariants"]["paper_shadow_live_forbidden"] is True


def test_render_operator_summary_and_write_outputs(tmp_path: Path) -> None:
    _seed_complete_aapl_repo(tmp_path)

    report = kpis.build_trusted_loop_operator_kpis(
        repo_root=tmp_path,
        max_candidates=2,
    )
    markdown = kpis.render_operator_summary(report)
    paths = kpis.write_outputs(report, repo_root=tmp_path)

    assert "# QRE Trusted-Loop Operator KPIs" in markdown
    assert paths["latest"] == "logs/qre_trusted_loop_operator_kpis/latest.json"
    assert paths["operator_summary"] == "logs/qre_trusted_loop_operator_kpis/operator_summary.md"
