from __future__ import annotations

import json
from pathlib import Path

import pytest

from research import qre_pre_shadow_paper_research_readiness as readiness


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


def test_build_pre_shadow_paper_research_readiness_stays_conservative(
    tmp_path: Path,
) -> None:
    _seed_complete_aapl_repo(tmp_path)

    report = readiness.build_pre_shadow_paper_research_readiness(
        repo_root=tmp_path,
        max_candidates=2,
    )

    summary = report["summary"]
    assert summary["readiness_state"] == "APPROACHING_READY_FOR_READINESS_PLANNING"
    assert summary["real_basket_diagnosis_exists"] is True
    assert summary["routing_evidence_backed"] is True
    assert summary["sampling_evidence_backed"] is True
    assert summary["reason_records_traceable"] is True
    assert summary["synthesis_still_blocked"] is True


def test_build_pre_shadow_paper_research_readiness_requires_reason_records(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _seed_complete_aapl_repo(tmp_path)

    def _empty_reason_records(*, repo_root: Path = Path("."), max_candidates: int = 15) -> dict:
        return {"records": [], "meta": {"record_count": 0}}

    monkeypatch.setattr(
        readiness.reason_records,
        "build_reason_records_snapshot",
        _empty_reason_records,
    )

    report = readiness.build_pre_shadow_paper_research_readiness(
        repo_root=tmp_path,
        max_candidates=2,
    )

    assert report["summary"]["readiness_state"] == "NOT_READY_MISSING_REASON_RECORDS"


def test_build_pre_shadow_paper_research_readiness_detects_scaffold_state(
    tmp_path: Path,
) -> None:
    report = readiness.build_pre_shadow_paper_research_readiness(
        repo_root=tmp_path,
        max_candidates=0,
    )

    assert report["summary"]["readiness_state"] == "NOT_READY_RESEARCH_LOOP_SCAFFOLD"
    assert report["safety_invariants"]["implements_paper_readiness"] is False


def test_render_operator_summary_and_write_outputs(tmp_path: Path) -> None:
    _seed_complete_aapl_repo(tmp_path)

    report = readiness.build_pre_shadow_paper_research_readiness(
        repo_root=tmp_path,
        max_candidates=2,
    )
    markdown = readiness.render_operator_summary(report)
    paths = readiness.write_outputs(report, repo_root=tmp_path)

    assert "# QRE Pre-Shadow/Paper Research Readiness" in markdown
    assert paths["latest"] == "logs/qre_pre_shadow_paper_research_readiness/latest.json"
    assert (
        paths["operator_summary"]
        == "logs/qre_pre_shadow_paper_research_readiness/operator_summary.md"
    )
