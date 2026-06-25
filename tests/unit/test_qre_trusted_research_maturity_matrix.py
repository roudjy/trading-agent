from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from reporting import qre_trusted_research_maturity_matrix as matrix


def _stub_plan() -> dict:
    return {
        "report_kind": "qre_audit_gap_closure_plan",
        "current_maturity": {"SCAFFOLD": 11, "WORKING_CAPABILITY": 9},
        "summary": {"audit_item_count": 20, "gap_closure_pr_count": 19},
    }


def _stub_coverage() -> dict:
    return {
        "summary": {
            "basket_inventory_count": 15,
            "evidence_completeness_status_counts": {
                "complete": 2,
                "partial": 4,
                "thin": 8,
                "missing": 1,
            },
            "missing_evidence_taxonomy_counts": {
                "campaign_lineage_missing": 15,
                "source_quality_rows_missing": 10,
            },
        }
    }


def _stub_reasons() -> dict:
    return {
        "meta": {
            "record_count": 45,
            "records_by_surface": {
                "basket_diagnosis": 15,
                "routing_readiness": 15,
                "sampling_readiness": 15,
            },
            "skipped_missing_refs_count": 0,
        }
    }


def _stub_reason_audit() -> dict:
    return {
        "summary": {
            "producer_count": 6,
            "expected_subject_count": 4240,
            "subjects_with_evidence_refs": 4195,
            "reason_record_coverage_pct": 98.94,
            "reason_records_manifest_total": 0,
        }
    }


def _stub_routing() -> dict:
    return {
        "summary": {
            "basket_inventory_count": 15,
            "routing_readiness_state_counts": {
                "ready": 2,
                "blocked": 1,
                "deferred": 12,
                "fail_closed": 0,
            },
            "routing_ready_count": 2,
        }
    }


def _stub_sampling() -> dict:
    return {
        "summary": {
            "basket_inventory_count": 15,
            "sampling_readiness_state_counts": {
                "ready": 2,
                "blocked": 1,
                "deferred": 12,
                "fail_closed": 0,
            },
        }
    }


def _stub_actions() -> dict:
    return {
        "summary": {
            "actionable_count": 15,
            "non_actionable_count": 0,
            "action_counts": {
                "collect_more_evidence": 3,
                "eligible_for_readonly_routing": 2,
                "expand_basket_coverage": 9,
                "require_identity_resolution": 1,
            },
            "blocker_counts": {
                "oos_evidence_missing": 3,
                "ready_for_readonly_research": 2,
            },
        }
    }


def _stub_explanations() -> dict:
    return {
        "summary": {
            "candidate_count": 15,
            "safe_next_action_counts": {
                "collect_more_evidence": 3,
                "eligible_for_readonly_routing": 2,
            },
            "paper_blocked_count": 0,
            "synthesis_blocked_count": 0,
        }
    }


def _stub_memory() -> dict:
    return {
        "summary": {
            "indexed_entry_count": 75,
            "indexed_basket_count": 15,
            "indexed_reason_record_count": 45,
            "ontology_readiness_state_counts": {"ready": 6, "unknown": 28},
        }
    }


def _stub_kpis() -> dict:
    return {
        "summary": {
            "basket_inventory_count": 15,
            "routing_ready_count": 2,
            "sampling_ready_count": 2,
            "reason_record_count": 45,
            "reason_record_coverage_pct": 98.94,
            "source_ready_basket_pct": 33.33,
            "evidence_complete_basket_pct": 13.33,
        }
    }


def test_build_maturity_matrix_composes_repo_backed_rows(monkeypatch) -> None:
    modules = {
        "research.qre_audit_gap_closure_plan": SimpleNamespace(
            build_audit_gap_closure_plan=_stub_plan
        ),
        "research.qre_real_basket_evidence_coverage": SimpleNamespace(
            build_real_basket_evidence_coverage=lambda **_: _stub_coverage()
        ),
        "research.qre_reason_records_v1": SimpleNamespace(
            build_reason_records_snapshot=lambda **_: _stub_reasons()
        ),
        "research.qre_reason_record_audit": SimpleNamespace(
            build_reason_record_audit=lambda **_: _stub_reason_audit()
        ),
        "research.qre_routing_readiness_from_basket": SimpleNamespace(
            build_routing_readiness_from_basket=lambda **_: _stub_routing()
        ),
        "research.qre_sampling_readiness_from_basket": SimpleNamespace(
            build_sampling_readiness_from_basket=lambda **_: _stub_sampling()
        ),
        "research.qre_failure_action_from_basket": SimpleNamespace(
            build_failure_action_from_basket=lambda **_: _stub_actions()
        ),
        "research.qre_candidate_explanation_rows": SimpleNamespace(
            build_candidate_explanation_rows=lambda **_: _stub_explanations()
        ),
        "research.qre_research_memory_coverage": SimpleNamespace(
            build_research_memory_coverage=lambda **_: _stub_memory()
        ),
        "research.qre_trusted_loop_operator_kpis": SimpleNamespace(
            build_trusted_loop_operator_kpis=lambda **_: _stub_kpis()
        ),
    }
    monkeypatch.setattr(matrix, "_research_module", modules.__getitem__)

    report = matrix.build_maturity_matrix(repo_root=Path("."), max_candidates=15)

    assert report["report_kind"] == "qre_trusted_research_maturity_matrix"
    assert report["summary"]["surface_count"] == 14
    assert report["summary"]["current_level_counts"]["scaffold"] == 3
    assert report["summary"]["current_level_counts"]["populated_working_capability"] == 2
    assert report["summary"]["current_level_counts"]["integrated_capability"] == 2
    assert report["summary"]["current_level_counts"]["repeatable_evidence_capability"] == 2
    assert report["summary"]["current_level_counts"]["decision_useful_capability"] == 5
    assert report["summary"]["operator_trusted_surface_count"] == 0
    assert report["summary"]["evidence_authoritative_surface_count"] == 0
    assert report["summary"]["highest_level_present"] == "decision_useful_capability"
    by_id = {row["surface_id"]: row for row in report["surfaces"]}
    assert by_id["behavior_thesis_registry"]["current_level"] == "scaffold"
    assert by_id["routing_readiness"]["current_level"] == "decision_useful_capability"
    assert by_id["reason_records_v1"]["current_level"] == "repeatable_evidence_capability"


def test_render_markdown_surfaces_counts_and_safety() -> None:
    report = {
        "summary": {
            "operator_summary": "Baseline remains mixed.",
            "overall_baseline": "mixed_decision_useful_pockets_not_operator_trusted",
            "highest_level_present": "decision_useful_capability",
            "operator_trusted_surface_count": 0,
            "evidence_authoritative_surface_count": 0,
            "planning_gap_scaffold_count": 11,
            "planning_gap_working_count": 9,
            "current_level_counts": {level: 0 for level in matrix.LEVELS},
            "top_blockers": [{"blocker_code": "campaign_lineage_missing", "count": 15}],
        },
        "surfaces": [
            {
                "surface_id": "routing_readiness",
                "surface_name": "Routing readiness",
                "current_level": "decision_useful_capability",
                "workstream": "F. Routing and Sampling Calibration",
                "primary_phase": "Phase 0 - Baseline Reconciliation",
                "supporting_metrics": {"ready_count": 2},
                "why_not_higher": "Most baskets remain deferred.",
                "evidence_refs": ["research/qre_routing_readiness_from_basket.py"],
            }
        ],
    }

    markdown = matrix.render_markdown(report)

    assert "# QRE Trusted Research Maturity Matrix" in markdown
    assert "campaign_lineage_missing" in markdown
    assert "decision_useful_capability" in markdown
    assert "Evidence-authoritative status is never inferred from file existence alone." in markdown


def test_write_outputs_writes_allowlisted_json_and_doc(tmp_path: Path) -> None:
    report = {
        "schema_version": "1.0",
        "report_kind": "qre_trusted_research_maturity_matrix",
        "summary": {
            "operator_summary": "ok",
            "overall_baseline": "mixed",
            "highest_level_present": "scaffold",
            "operator_trusted_surface_count": 0,
            "evidence_authoritative_surface_count": 0,
            "planning_gap_scaffold_count": 0,
            "planning_gap_working_count": 0,
            "current_level_counts": {level: 0 for level in matrix.LEVELS},
            "top_blockers": [],
        },
        "surfaces": [],
    }

    paths = matrix.write_outputs(report, repo_root=tmp_path)

    assert paths["latest"] == "logs/qre_trusted_research_maturity_matrix/latest.json"
    assert paths["doc"] == "docs/governance/qre_trusted_research_maturity_matrix.md"
    latest = tmp_path / paths["latest"]
    doc = tmp_path / paths["doc"]
    assert latest.is_file()
    assert doc.is_file()
    parsed = json.loads(latest.read_text(encoding="utf-8"))
    assert parsed["report_kind"] == "qre_trusted_research_maturity_matrix"
