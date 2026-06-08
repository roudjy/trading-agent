from __future__ import annotations

from pathlib import Path

from research import qre_evidence_complete_basket_closure as closure


def test_closure_marks_complete_basket_without_blockers(monkeypatch) -> None:
    monkeypatch.setattr(
        closure.evidence_coverage,
        "build_real_basket_evidence_coverage",
        lambda **_: {
            "rows": [
                {
                    "candidate_id": "c1",
                    "symbol": "AAPL",
                    "preset_id": "trend_pullback_continuation_daily_v1",
                    "diagnosis_class": "diagnosable",
                    "evidence_completeness_score_pct": 100,
                    "evidence_completeness_status": "complete",
                    "missing_evidence_taxonomy": [],
                    "follow_up": "eligible_for_readonly_routing",
                    "evidence_presence": {
                        "source_identity_ready": True,
                        "source_quality_ready": True,
                        "cache_ready": True,
                        "screening_evidence_present": True,
                        "oos_evidence_known": True,
                        "campaign_lineage_present": True,
                        "candidate_lineage_present": True,
                    },
                }
            ]
        },
    )

    report = closure.build_evidence_complete_basket_closure()
    row = report["rows"][0]
    assert row["closure_status"] == "evidence_complete"
    assert row["exact_blockers"] == []
    assert report["summary"]["evidence_complete_count"] == 1


def test_closure_requires_exact_blockers_without_unknowns(monkeypatch) -> None:
    monkeypatch.setattr(
        closure.evidence_coverage,
        "build_real_basket_evidence_coverage",
        lambda **_: {
            "rows": [
                {
                    "candidate_id": "c2",
                    "symbol": "ASML",
                    "preset_id": "trend_continuation_daily_v1",
                    "diagnosis_class": "diagnosable",
                    "evidence_completeness_score_pct": 57,
                    "evidence_completeness_status": "partial",
                    "missing_evidence_taxonomy": [
                        "screening_evidence_missing",
                        "oos_evidence_missing",
                        "campaign_lineage_missing",
                    ],
                    "follow_up": "collect_more_evidence",
                    "evidence_presence": {
                        "source_identity_ready": True,
                        "source_quality_ready": True,
                        "cache_ready": True,
                        "screening_evidence_present": False,
                        "oos_evidence_known": False,
                        "campaign_lineage_present": False,
                        "candidate_lineage_present": True,
                    },
                }
            ]
        },
    )

    report = closure.build_evidence_complete_basket_closure()
    row = report["rows"][0]
    assert row["closure_status"] == "blocked_not_evidence_complete"
    assert row["exact_next_action"] == "restore_or_run_grid_artifacts"
    assert row["unknown_blocker_count"] == 0
    assert report["summary"]["all_non_complete_baskets_have_exact_blockers"] is True
    assert report["summary"]["all_non_complete_baskets_have_no_unknown_blockers"] is True
    assert report["summary"]["final_recommendation"] == "no_basket_evidence_complete_exact_blockers_enumerated"


def test_closure_writes_outputs(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(
        closure.evidence_coverage,
        "build_real_basket_evidence_coverage",
        lambda **_: {"rows": []},
    )
    report = closure.build_evidence_complete_basket_closure(repo_root=tmp_path)
    paths = closure.write_outputs(report, repo_root=tmp_path)
    markdown = (tmp_path / paths["operator_summary"]).read_text(encoding="utf-8")
    assert paths["latest"] == "logs/qre_evidence_complete_basket_closure/latest.json"
    assert "# QRE Evidence Complete Basket Closure" in markdown
