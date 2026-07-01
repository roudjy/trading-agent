from __future__ import annotations

from pathlib import Path

from packages.qre_research import empirical_research_flywheel as flywheel


def test_empirical_research_flywheel_composes_canonical_chain(
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
            ],
            "summary": {
                "candidate_count": 2,
                "admitted_count": 1,
                "exact_duplicate_suppressed_count": 0,
                "near_duplicate_suppressed_count": 1,
            },
        },
    )
    monkeypatch.setattr(
        flywheel.qhl,
        "run_trusted_hypothesis_loop",
        lambda repo_root, write_outputs: {
            "summary": {
                "next_action": "launch_data_oos_capacity_expansion",
            }
        },
    )
    monkeypatch.setattr(
        flywheel.qhl,
        "build_feasibility_snapshot",
        lambda repo_root: {"summary": {"feasibility_ready_count": 1}},
    )
    monkeypatch.setattr(
        flywheel.qhl,
        "build_routing_snapshot",
        lambda repo_root: {"summary": {"routing_ready_count": 1}},
    )
    monkeypatch.setattr(
        flywheel.qhl,
        "build_sampling_snapshot",
        lambda repo_root: {"summary": {"sampling_ready_count": 0}},
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

    assert payload["summary"]["candidate_count"] == 2
    assert payload["summary"]["research_cycles_executed"] == 3
    assert payload["summary"]["campaigns_executed"] == 1
    assert payload["summary"]["synthesis_readiness"] == "INELIGIBLE_EVIDENCE"
    assert payload["summary"]["next_action"] == "launch_data_oos_capacity_expansion"
    assert (tmp_path / flywheel.FLYWHEEL_REPORT_PATH).is_file()
