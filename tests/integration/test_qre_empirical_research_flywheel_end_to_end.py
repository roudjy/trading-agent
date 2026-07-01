from __future__ import annotations

import json
from pathlib import Path

from packages.qre_research import empirical_research_flywheel as flywheel


def test_empirical_research_flywheel_end_to_end_materializes_report(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        flywheel.a20,
        "compile_candidate_theses",
        lambda repo_root: {
            "rows": [
                {"behavior_family": "relative_strength"},
                {"behavior_family": "trend"},
                {"behavior_family": "volatility_compression_breakout"},
                {"behavior_family": "mean_reversion"},
            ],
            "summary": {
                "candidate_count": 4,
                "admitted_count": 1,
                "exact_duplicate_suppressed_count": 0,
                "near_duplicate_suppressed_count": 2,
            },
        },
    )
    monkeypatch.setattr(
        flywheel.qhl,
        "run_trusted_hypothesis_loop",
        lambda repo_root, write_outputs: {
            "next_action": "launch_data_oos_capacity_expansion",
            "empirical_research_evidence_materialized": True,
        },
    )
    monkeypatch.setattr(
        flywheel.qhl,
        "build_feasibility_snapshot",
        lambda repo_root: {
            "rows": [{"source_hypothesis_id": "cross_sectional_momentum_v0"}],
            "summary": {"feasibility_ready_count": 1},
        },
    )
    monkeypatch.setattr(
        flywheel.qhl,
        "build_routing_snapshot",
        lambda repo_root: {
            "rows": [{"source_hypothesis_id": "cross_sectional_momentum_v0"}],
            "summary": {"routing_ready_count": 1},
        },
    )
    monkeypatch.setattr(
        flywheel.qhl,
        "build_sampling_snapshot",
        lambda repo_root: {
            "rows": [{"source_hypothesis_id": "cross_sectional_momentum_v0"}],
            "summary": {"sampling_ready_count": 0},
        },
    )
    monkeypatch.setattr(
        flywheel.ao,
        "run_orchestration",
        lambda **kwargs: {
            "cycles_completed": 3,
            "campaigns_executed": 1,
            "next_autonomous_action": "launch_data_oos_capacity_expansion",
            "latest_status_identity": "qstatus_fixture",
        },
    )
    monkeypatch.setattr(
        flywheel.eep,
        "run_empirical_evidence_pack",
        lambda **kwargs: {
            "evidence_pack_id": "qep_fixture",
            "disposition": "NEEDS_MORE_EVIDENCE",
            "recommended_next_action": "launch_data_oos_capacity_expansion",
        },
    )
    monkeypatch.setattr(
        flywheel.bss,
        "materialize_synthesis_readiness",
        lambda **kwargs: {
            "readiness_status": "INELIGIBLE_EVIDENCE",
            "recommended_next_actions": ["launch_data_oos_capacity_expansion"],
        },
    )
    monkeypatch.setattr(
        flywheel.bss,
        "run_bounded_strategy_synthesis",
        lambda **kwargs: {
            "status": "BLOCKED_BY_READINESS",
            "recommended_next_actions": ["launch_data_oos_capacity_expansion"],
        },
    )
    monkeypatch.setattr(flywheel, "validate_write_target", lambda path: None)

    payload = flywheel.run_empirical_research_flywheel(
        repo_root=tmp_path,
        max_cycles=3,
        write_outputs=True,
        report_date="2026-07-01",
    )

    report_path = tmp_path / flywheel.FLYWHEEL_REPORT_PATH
    assert report_path.is_file()
    written = json.loads(report_path.read_text(encoding="utf-8"))
    assert written["summary"]["research_cycles_executed"] == 3
    assert written["summary"]["campaigns_executed"] == 1
    assert written["summary"]["synthesis_readiness"] == "INELIGIBLE_EVIDENCE"
    assert payload["summary"]["next_action"] == "launch_data_oos_capacity_expansion"
