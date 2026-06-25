from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from reporting import qre_evidence_density_inventory as inventory


def _coverage() -> dict:
    return {
        "summary": {
            "evidence_completeness_status_counts": {
                "complete": 2,
                "partial": 4,
                "thin": 6,
                "missing": 3,
            },
            "missing_evidence_taxonomy_counts": {
                "source_identity_blocked": 5,
                "campaign_lineage_missing": 15,
            },
        },
        "rows": [
            {
                "provider_symbol_status": "verified",
                "evidence_presence": {
                    "source_quality_ready": True,
                    "cache_ready": True,
                    "screening_evidence_present": True,
                    "oos_evidence_known": True,
                    "campaign_lineage_present": False,
                    "candidate_lineage_present": True,
                },
            },
            {
                "provider_symbol_status": "candidate_alias_requires_verification",
                "evidence_presence": {
                    "source_quality_ready": False,
                    "cache_ready": False,
                    "screening_evidence_present": True,
                    "oos_evidence_known": False,
                    "campaign_lineage_present": False,
                    "candidate_lineage_present": False,
                },
            },
            {
                "provider_symbol_status": "verified",
                "evidence_presence": {
                    "source_quality_ready": True,
                    "cache_ready": False,
                    "screening_evidence_present": False,
                    "oos_evidence_known": False,
                    "campaign_lineage_present": False,
                    "candidate_lineage_present": True,
                },
            },
        ],
    }


def _reason_records() -> dict:
    return {
        "meta": {
            "record_count": 45,
            "skipped_missing_refs_count": 0,
        }
    }


def _reason_audit() -> dict:
    return {
        "summary": {
            "subjects_with_evidence_refs": 9,
            "expected_subject_count": 12,
            "reason_record_coverage_pct": 75.0,
        }
    }


def _routing() -> dict:
    return {
        "summary": {
            "routing_ready_count": 2,
            "routing_blocked_count": 1,
            "routing_deferred_count": 12,
        }
    }


def _sampling() -> dict:
    return {
        "summary": {
            "sampling_ready_count": 2,
            "sampling_blocked_count": 1,
            "sampling_deferred_count": 12,
        }
    }


def _failure() -> dict:
    return {
        "summary": {
            "actionable_count": 4,
            "non_actionable_count": 11,
            "basket_inventory_count": 15,
        }
    }


def _explanations() -> dict:
    return {
        "summary": {
            "candidate_count": 15,
            "paper_blocked_count": 12,
            "synthesis_blocked_count": 15,
        }
    }


def _memory() -> dict:
    return {
        "summary": {
            "indexed_entry_count": 20,
            "indexed_basket_count": 5,
            "indexed_failure_action_count": 5,
            "indexed_reason_record_count": 10,
        }
    }


def _kpis() -> dict:
    return {
        "summary": {
            "basket_inventory_count": 15,
            "reason_record_coverage_pct": 98.94,
            "source_ready_basket_pct": 33.33,
            "evidence_complete_basket_pct": 13.33,
            "trusted_loop_maturity_state": "working_capability",
        }
    }


def test_build_evidence_density_inventory(monkeypatch) -> None:
    modules = {
        "research.qre_real_basket_evidence_coverage": SimpleNamespace(
            build_real_basket_evidence_coverage=lambda **_: _coverage()
        ),
        "research.qre_reason_records_v1": SimpleNamespace(
            build_reason_records_snapshot=lambda **_: _reason_records()
        ),
        "research.qre_reason_record_audit": SimpleNamespace(
            build_reason_record_audit=lambda **_: _reason_audit()
        ),
        "research.qre_routing_readiness_from_basket": SimpleNamespace(
            build_routing_readiness_from_basket=lambda **_: _routing()
        ),
        "research.qre_sampling_readiness_from_basket": SimpleNamespace(
            build_sampling_readiness_from_basket=lambda **_: _sampling()
        ),
        "research.qre_failure_action_from_basket": SimpleNamespace(
            build_failure_action_from_basket=lambda **_: _failure()
        ),
        "research.qre_candidate_explanation_rows": SimpleNamespace(
            build_candidate_explanation_rows=lambda **_: _explanations()
        ),
        "research.qre_research_memory_coverage": SimpleNamespace(
            build_research_memory_coverage=lambda **_: _memory()
        ),
        "research.qre_trusted_loop_operator_kpis": SimpleNamespace(
            build_trusted_loop_operator_kpis=lambda **_: _kpis()
        ),
    }
    monkeypatch.setattr(inventory, "_research_module", modules.__getitem__)

    report = inventory.build_evidence_density_inventory(max_candidates=15)

    assert report["report_kind"] == "qre_evidence_density_inventory"
    assert report["summary"]["evidence_class_count"] == 14
    assert set(report["population_states"]) == set(inventory.POPULATION_STATES)
    by_id = {row["evidence_class_id"]: row for row in report["evidence_classes"]}
    assert by_id["source_identity"]["population_state"] == "blocked"
    assert by_id["campaign_lineage"]["population_state"] == "blocked"
    assert by_id["reason_records"]["population_state"] == "partial"
    assert by_id["routing_readiness"]["population_state"] == "partial"
    assert by_id["trusted_loop_kpis"]["population_state"] == "complete"
    assert report["summary"]["population_state_counts"]["blocked"] >= 1


def test_write_outputs(tmp_path: Path) -> None:
    report = {
        "schema_version": "1.0",
        "report_kind": "qre_evidence_density_inventory",
        "generated_at_utc": "2026-06-25T00:00:00Z",
        "population_states": list(inventory.POPULATION_STATES),
        "evidence_classes": [
            {
                "evidence_class_id": "source_identity",
                "title": "Source identity verification",
                "producers": ["a"],
                "consumers": ["b"],
                "population_state": "blocked",
                "fail_closed": True,
                "blocker_codes": ["source_identity_blocked"],
                "artifact_paths": ["logs/x.json"],
                "metrics": {"verified_basket_count": 1},
                "why": "x",
            }
        ],
        "summary": {
            "evidence_class_count": 1,
            "population_state_counts": {"blocked": 1},
            "top_blocker_codes": [{"blocker_code": "source_identity_blocked", "count": 1}],
            "final_recommendation": "evidence_density_inventory_ready",
        },
    }

    paths = inventory.write_outputs(
        report,
        output_dir=tmp_path / "logs" / "qre_evidence_density_inventory",
        doc_path=tmp_path / "docs" / "governance" / "qre_evidence_density_inventory.md",
    )

    parsed = json.loads(Path(paths["latest"]).read_text(encoding="utf-8"))
    assert parsed["report_kind"] == "qre_evidence_density_inventory"
    assert "QRE Evidence Density Inventory" in Path(paths["doc"]).read_text(encoding="utf-8")
