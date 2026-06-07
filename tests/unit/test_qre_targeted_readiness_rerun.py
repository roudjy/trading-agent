from __future__ import annotations

import json
from pathlib import Path

from research import qre_targeted_readiness_rerun as rerun


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def test_targeted_rerun_reports_delta_and_focus_rows(monkeypatch, tmp_path: Path) -> None:
    _write_json(
        tmp_path / "logs" / "qre_pre_shadow_paper_research_readiness" / "latest.json",
        {
            "summary": {
                "readiness_state": "APPROACHING_READY_FOR_READINESS_PLANNING",
                "final_recommendation": "APPROACHING_READY_FOR_READINESS_PLANNING",
                "source_readiness_linked": True,
                "candidate_blockers_explainable": False,
                "oos_blockers_explainable": True,
                "routing_evidence_backed": True,
                "sampling_evidence_backed": True,
                "trusted_loop_maturity_state": "working_capability",
            }
        },
    )

    monkeypatch.setattr(
        rerun.pre_shadow_readiness,
        "build_pre_shadow_paper_research_readiness",
        lambda **_: {
            "summary": {
                "readiness_state": "NOT_READY_NO_ROUTING_SAMPLING_EVIDENCE",
                "final_recommendation": "NOT_READY_NO_ROUTING_SAMPLING_EVIDENCE",
                "source_readiness_linked": False,
                "candidate_blockers_explainable": False,
                "oos_blockers_explainable": True,
                "routing_evidence_backed": False,
                "sampling_evidence_backed": False,
                "trusted_loop_maturity_state": "working_capability",
            },
            "supporting_reports": {
                "coverage": {"screening_evidence_rows_total": 0},
                "source_cache_materialization": {
                    "missing_sidecars": ["cache_manifest"],
                    "present_not_ready_sidecars": [],
                },
            },
        },
    )
    monkeypatch.setattr(
        rerun.local_grid_refresh,
        "build_local_grid_artifact_refresh",
        lambda **_: {"summary": {"missing_local_grid_artifacts": True}},
    )

    report = rerun.build_targeted_readiness_rerun(repo_root=tmp_path, max_candidates=3)

    assert report["summary"]["persisted_report_present"] is True
    assert report["summary"]["targeted_local_refresh_executed"] is True
    assert report["summary"]["changed_metric_count"] >= 1
    assert report["summary"]["current_readiness_state"] == "NOT_READY_NO_ROUTING_SAMPLING_EVIDENCE"
    assert {row["focus_area"] for row in report["focus_rows"]} >= {
        "controlled_grid_artifacts",
        "candidate_blocker_explainability",
        "source_cache_linkage",
        "screening_and_oos_evidence",
    }


def test_targeted_rerun_writes_outputs(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(
        rerun.pre_shadow_readiness,
        "build_pre_shadow_paper_research_readiness",
        lambda **_: {"summary": {}, "supporting_reports": {"coverage": {}, "source_cache_materialization": {}}},
    )
    monkeypatch.setattr(
        rerun.local_grid_refresh,
        "build_local_grid_artifact_refresh",
        lambda **_: {"summary": {"missing_local_grid_artifacts": False}},
    )

    report = rerun.build_targeted_readiness_rerun(repo_root=tmp_path)
    paths = rerun.write_outputs(report, repo_root=tmp_path)

    markdown = (tmp_path / paths["operator_summary"]).read_text(encoding="utf-8")
    assert paths["latest"] == "logs/qre_targeted_readiness_rerun/latest.json"
    assert "# QRE Targeted Readiness Rerun" in markdown
