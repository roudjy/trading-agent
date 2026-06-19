from __future__ import annotations

import json
from pathlib import Path

from research.qre_multibasket_portfolio_intelligence import (
    build_multibasket_portfolio_intelligence,
    build_portfolio_intelligence_report,
    write_outputs,
)


def _quality_rows(*rows: dict[str, object]) -> dict[str, object]:
    return {"rows": list(rows)}


def _breadth_rows(*rows: dict[str, object]) -> dict[str, object]:
    return {"coverage_matrix": list(rows)}


def test_portfolio_intelligence_blocks_when_no_candidates() -> None:
    report = build_multibasket_portfolio_intelligence(
        quality_report={"rows": []},
        breadth_report={"coverage_matrix": []},
    )

    assert report["summary"]["status"] == "blocked_no_candidates"
    assert report["summary"]["candidate_count"] == 0


def test_portfolio_intelligence_blocks_without_accepted_oos_but_keeps_context() -> None:
    report = build_multibasket_portfolio_intelligence(
        quality_report=_quality_rows(
            {
                "candidate_id": "q1",
                "quality_status": "blocked_evidence_incomplete",
                "lifecycle_status": "evidence_incomplete",
                "scope_key": "basket-1",
                "accepted_lineage_count": 1,
                "accepted_oos_count": 0,
                "blocker_codes": ["accepted_evidence_incomplete"],
                "quality_dimensions": {
                    "source_quality": {"passed": True},
                },
            },
            {
                "candidate_id": "q2",
                "quality_status": "blocked_evidence_incomplete",
                "lifecycle_status": "evidence_incomplete",
                "scope_key": "basket-2",
                "accepted_lineage_count": 1,
                "accepted_oos_count": 0,
                "blocker_codes": ["accepted_evidence_incomplete"],
                "quality_dimensions": {
                    "source_quality": {"passed": True},
                },
            },
        ),
        breadth_report=_breadth_rows(
            {
                "dimension": "basket",
                "scope_key": "basket-1",
                "hypothesis_id": "h1",
                "behavior_id": "trend",
                "region": "EU",
                "sector": "semiconductors",
                "symbol": "ASML",
                "timeframe": "1d",
                "scope_label": "eu-trend-1",
            },
            {
                "dimension": "basket",
                "scope_key": "basket-2",
                "hypothesis_id": "h2",
                "behavior_id": "trend",
                "region": "US",
                "sector": "software",
                "symbol": "MSFT",
                "timeframe": "1d",
                "scope_label": "us-trend-1",
            },
        ),
    )

    assert report["summary"]["status"] == "blocked_no_accepted_oos"
    assert report["summary"]["context_status"] == "portfolio_research_context_ready"
    assert len(report["pairwise_overlap"]) == 1
    assert report["concentration"]["behavior"]["trend"] == 2


def test_portfolio_intelligence_reuses_portfolio_diagnostics_when_comparable_returns_exist() -> None:
    report = build_multibasket_portfolio_intelligence(
        quality_report=_quality_rows(
            {
                "candidate_id": "qa",
                "quality_status": "eligible_for_operator_quality_review",
                "lifecycle_status": "evidence_complete",
                "scope_key": "basket-a",
                "accepted_lineage_count": 2,
                "accepted_oos_count": 2,
                "blocker_codes": [],
                "quality_dimensions": {
                    "source_quality": {"passed": True},
                },
            },
            {
                "candidate_id": "qb",
                "quality_status": "eligible_for_operator_quality_review",
                "lifecycle_status": "evidence_complete",
                "scope_key": "basket-b",
                "accepted_lineage_count": 2,
                "accepted_oos_count": 2,
                "blocker_codes": [],
                "quality_dimensions": {
                    "source_quality": {"passed": True},
                },
            },
        ),
        breadth_report=_breadth_rows(
            {
                "dimension": "basket",
                "scope_key": "basket-a",
                "hypothesis_id": "ha",
                "behavior_id": "trend",
                "region": "EU",
                "sector": "semiconductors",
                "symbol": "ASML",
                "timeframe": "1d",
                "scope_label": "a",
            },
            {
                "dimension": "basket",
                "scope_key": "basket-b",
                "hypothesis_id": "hb",
                "behavior_id": "relative_strength",
                "region": "US",
                "sector": "software",
                "symbol": "MSFT",
                "timeframe": "1d",
                "scope_label": "b",
            },
        ),
        candidate_returns={
            "qa": [0.01, -0.005, 0.012, 0.004, 0.003, 0.002],
            "qb": [0.009, -0.004, 0.011, 0.005, 0.002, 0.003],
        },
    )

    assert report["correlation"]["status"] == "portfolio_research_context_ready"
    assert report["correlation"]["diagnostics"]["equal_weight_portfolio"]["candidate_count"] == 2


def test_portfolio_intelligence_flags_scope_mismatch() -> None:
    report = build_multibasket_portfolio_intelligence(
        quality_report=_quality_rows(
            {
                "candidate_id": "q1",
                "quality_status": "blocked_evidence_incomplete",
                "lifecycle_status": "evidence_incomplete",
                "scope_key": "missing-scope",
                "accepted_lineage_count": 1,
                "accepted_oos_count": 0,
                "blocker_codes": [],
                "quality_dimensions": {
                    "source_quality": {"passed": True},
                },
            }
        ),
        breadth_report=_breadth_rows(),
    )

    assert report["summary"]["status"] == "blocked_scope_mismatch"
    assert "scope_missing_from_breadth:missing-scope" in report["missing_evidence"]


def test_build_portfolio_intelligence_report_materializes_from_repo_paths(tmp_path: Path) -> None:
    logs = tmp_path / "logs"
    (logs / "qre_candidate_quality_framework").mkdir(parents=True)
    (logs / "qre_evidence_breadth_framework").mkdir(parents=True)

    (logs / "qre_candidate_quality_framework" / "latest.json").write_text(
        json.dumps(
            _quality_rows(
                {
                    "candidate_id": "q1",
                    "quality_status": "blocked_evidence_incomplete",
                    "lifecycle_status": "evidence_incomplete",
                    "scope_key": "basket-1",
                    "accepted_lineage_count": 1,
                    "accepted_oos_count": 0,
                    "blocker_codes": [],
                    "quality_dimensions": {
                        "source_quality": {"passed": True},
                    },
                }
            )
        ),
        encoding="utf-8",
    )
    (logs / "qre_evidence_breadth_framework" / "latest.json").write_text(
        json.dumps(
            _breadth_rows(
                {
                    "dimension": "basket",
                    "scope_key": "basket-1",
                    "hypothesis_id": "h1",
                    "behavior_id": "trend",
                    "region": "EU",
                    "sector": "semiconductors",
                    "symbol": "ASML",
                    "timeframe": "1d",
                    "scope_label": "basket-1",
                }
            )
        ),
        encoding="utf-8",
    )

    report = build_portfolio_intelligence_report(repo_root=tmp_path)

    assert report["summary"]["candidate_count"] == 1
    assert report["summary"]["status"] == "blocked_no_accepted_oos"


def test_write_outputs_uses_allowlisted_location(tmp_path: Path) -> None:
    report = {
        "schema_version": "1.0",
        "report_kind": "qre_multibasket_portfolio_intelligence",
        "summary": {"status": "blocked_no_candidates"},
    }

    paths = write_outputs(report, repo_root=tmp_path)

    assert (tmp_path / paths["latest"]).is_file()
