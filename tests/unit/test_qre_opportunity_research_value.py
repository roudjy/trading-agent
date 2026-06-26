from __future__ import annotations

import ast
import json
from pathlib import Path

from packages.qre_research import opportunity_value
from research import qre_opportunity_research_value as opportunity_report


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _write_upstreams(tmp_path: Path) -> None:
    _write_json(
        tmp_path / "logs" / "qre_behavior_thesis_registry" / "latest.json",
        {
            "rows": [
                {
                    "thesis_id": "qbt_ready",
                    "source_hypothesis_id": "trend_pullback_v1",
                    "behavior_family": "pullback_continuation",
                    "strategy_family": "trend_pullback",
                    "status": "research_ready",
                    "signal_density_expectation": "moderate",
                    "null_controls": ["qre_null_control_falsification_suite"],
                    "source_requirements": [
                        "screening_evidence",
                        "oos_evidence",
                        "lineage_evidence",
                    ],
                    "duplicate_signature": "dup-ready",
                    "provenance_refs": [
                        "research/strategy_hypothesis_catalog.py#trend_pullback_v1"
                    ],
                },
                {
                    "thesis_id": "qbt_blocked",
                    "source_hypothesis_id": "regime_diagnostics_v1",
                    "behavior_family": "index_regime_filter",
                    "strategy_family": "regime_diagnostics",
                    "status": "blocked",
                    "signal_density_expectation": "blocked",
                    "null_controls": [
                        "blocked:null_controls:behavior_not_research_ready"
                    ],
                    "source_requirements": [
                        "blocked:source_requirements_not_satisfied_for_execution"
                    ],
                    "duplicate_signature": "dup-blocked",
                    "provenance_refs": [
                        "research/strategy_hypothesis_catalog.py#regime_diagnostics_v1"
                    ],
                },
            ]
        },
    )
    _write_json(
        tmp_path / "logs" / "qre_behavior_thesis_evidence" / "latest.json",
        {
            "rows": [
                {
                    "thesis_id": "qbt_ready",
                    "supporting_evidence_count": 3,
                    "contradicting_evidence_count": 0,
                    "unresolved_evidence_count": 0,
                    "provenance_refs": [
                        "logs/qre_behavior_thesis_evidence/latest.json#rows[0]"
                    ],
                },
                {
                    "thesis_id": "qbt_blocked",
                    "supporting_evidence_count": 1,
                    "contradicting_evidence_count": 1,
                    "unresolved_evidence_count": 3,
                    "provenance_refs": [
                        "logs/qre_behavior_thesis_evidence/latest.json#rows[1]"
                    ],
                },
            ]
        },
    )
    _write_json(
        tmp_path / "logs" / "qre_prior_failure_retrieval" / "latest.json",
        {
            "rows": [
                {
                    "thesis_id": "qbt_ready",
                    "summary_status": "missing_context",
                    "provenance_refs": [
                        "logs/qre_prior_failure_retrieval/latest.json#rows[0]"
                    ],
                },
                {
                    "thesis_id": "qbt_blocked",
                    "summary_status": "prior_failure_dead_zone_visible",
                    "provenance_refs": [
                        "logs/qre_prior_failure_retrieval/latest.json#rows[1]"
                    ],
                },
            ]
        },
    )
    _write_json(
        tmp_path / "logs" / "qre_evidence_breadth_framework" / "latest.json",
        {
            "coverage_matrix": [
                {
                    "dimension": "behavior",
                    "scope_key": "pullback_continuation",
                    "inventory_count": 2,
                    "regime_count": 1,
                    "independent_window_count": 1,
                    "accepted_oos_count": 1,
                    "accepted_lineage_count": 1,
                    "blocker_reasons": [],
                },
                {
                    "dimension": "behavior",
                    "scope_key": "index_regime_filter",
                    "inventory_count": 1,
                    "regime_count": 0,
                    "independent_window_count": 0,
                    "accepted_oos_count": 0,
                    "accepted_lineage_count": 0,
                    "blocker_reasons": [
                        "source_quality_rows_missing",
                        "cache_coverage_missing",
                    ],
                },
            ]
        },
    )
    _write_json(
        tmp_path / "logs" / "qre_source_identity_authority_normalization" / "latest.json",
        {
            "rows": [
                {
                    "behavior_id": "pullback_continuation",
                    "scope_key": "seed::pullback_continuation_daily_v1::SPY",
                    "source_quality_ready": True,
                    "authority_status": "normalized_context_ready",
                }
            ]
        },
    )
    _write_json(
        tmp_path / "logs" / "qre_research_cycle_router" / "latest.json",
        {
            "eligible_directions": [
                {
                    "target_hypothesis": {"behavior_id": "pullback_continuation"},
                    "routing_context_only": {
                        "score_components": {
                            "information_gain_proxy_score": 0.8,
                            "compute_cost_penalty": 0.2,
                        }
                    },
                }
            ]
        },
    )
    _write_json(
        tmp_path / "logs" / "hypothesis_discovery_minimal" / "latest.json",
        {
            "items": [
                {
                    "hypothesis_id": "trend_pullback_v1",
                    "score": {
                        "opportunity_probability_score": 0.77,
                    },
                }
            ]
        },
    )
    _write_json(
        tmp_path / "research" / "campaigns" / "evidence" / "information_gain_latest.v1.json",
        {
            "hypothesis_id": "trend_pullback_v1",
            "information_gain": {"score": 0.9},
        },
    )


def test_helper_score_is_deterministic_and_bounded() -> None:
    scores = {name: 0.5 for name in opportunity_value.COMPONENT_NAMES}
    assert opportunity_value.weighted_opportunity_score(scores) == opportunity_value.weighted_opportunity_score(
        dict(reversed(list(scores.items())))
    )
    assert opportunity_value.priority_band(0.9) == "high"
    assert opportunity_value.priority_band(0.5) == "medium"
    assert opportunity_value.priority_band(0.1) == "low"
    assert opportunity_value.priority_band(0.9, blocked=True) == "blocked"


def test_build_is_deterministic_and_preserves_provenance(tmp_path: Path) -> None:
    _write_upstreams(tmp_path)
    left = opportunity_report.build_opportunity_research_value(repo_root=tmp_path)
    right = opportunity_report.build_opportunity_research_value(repo_root=tmp_path)

    assert left == right
    assert left["report_kind"] == "qre_opportunity_research_value"
    assert left["summary"]["thesis_count"] == 2
    ready = next(row for row in left["rows"] if row["thesis_id"] == "qbt_ready")
    assert ready["priority_band"] in {"medium", "high"}
    assert ready["recommended_next_action"] == "advance_to_routing_comparison"
    assert ready["legacy_discovery_opportunity_score"] == 0.77
    assert ready["provenance_refs"]


def test_required_fields_and_closed_vocabularies_are_present(tmp_path: Path) -> None:
    _write_upstreams(tmp_path)
    report = opportunity_report.build_opportunity_research_value(repo_root=tmp_path)
    row = report["rows"][0]

    for field in opportunity_report.ROW_REQUIRED_FIELDS:
        assert field in row
        assert row[field] or row[field] == 0.0
    assert set(row["component_scores"].keys()) == set(opportunity_value.COMPONENT_NAMES)
    assert set(row["component_statuses"].keys()) == set(opportunity_value.COMPONENT_NAMES)
    assert row["authority"]["evidence_authority"] == "context_only"


def test_invalid_or_incomplete_row_is_rejected() -> None:
    result = opportunity_report.validate_opportunity_row(
        {
            "thesis_id": "bad",
            "source_hypothesis_id": "src",
            "behavior_family": "trend_continuation",
            "thesis_status": "research_ready",
            "opportunity_score": 2.0,
            "priority_band": "invented",
            "recommended_next_action": "wrong",
            "component_scores": {"wrong": 2.0},
            "component_statuses": {"wrong": "wrong"},
            "provenance_refs": [],
            "schema_version": "1.0",
            "authority": {
                "can_generate_executable_strategy": True,
                "can_register_strategy": True,
                "can_launch_campaign": True,
            },
        }
    )

    assert result["valid"] is False
    assert "invalid_priority_band" in result["rejection_reasons"]
    assert "invalid_recommended_next_action" in result["rejection_reasons"]
    assert "invalid_component_scores" in result["rejection_reasons"]
    assert "invalid_component_statuses" in result["rejection_reasons"]
    assert "invalid_strategy_generation_authority" in result["rejection_reasons"]


def test_duplicate_signatures_fail_closed(tmp_path: Path) -> None:
    _write_upstreams(tmp_path)
    registry_payload = json.loads(
        (tmp_path / "logs" / "qre_behavior_thesis_registry" / "latest.json").read_text(encoding="utf-8")
    )
    registry_payload["rows"][1]["duplicate_signature"] = registry_payload["rows"][0]["duplicate_signature"]
    (tmp_path / "logs" / "qre_behavior_thesis_registry" / "latest.json").write_text(
        json.dumps(registry_payload, indent=2),
        encoding="utf-8",
    )

    report = opportunity_report.build_opportunity_research_value(repo_root=tmp_path)

    assert report["summary"]["duplicate_signature_count"] == 1
    blocked = next(row for row in report["rows"] if row["thesis_id"] == "qbt_blocked")
    assert blocked["priority_band"] == "blocked"


def test_missing_information_gain_and_discovery_digest_fail_closed(tmp_path: Path) -> None:
    _write_upstreams(tmp_path)
    (tmp_path / "logs" / "hypothesis_discovery_minimal" / "latest.json").unlink()
    (tmp_path / "research" / "campaigns" / "evidence" / "information_gain_latest.v1.json").unlink()

    report = opportunity_report.build_opportunity_research_value(repo_root=tmp_path)

    ready = next(row for row in report["rows"] if row["thesis_id"] == "qbt_ready")
    assert ready["component_statuses"]["information_gain"] in {"missing", "derived_proxy"}
    assert ready["legacy_discovery_semantics"] == "missing"


def test_write_outputs_and_status_round_trip(tmp_path: Path) -> None:
    _write_upstreams(tmp_path)
    report = opportunity_report.build_opportunity_research_value(repo_root=tmp_path)

    paths = opportunity_report.write_outputs(report, repo_root=tmp_path)

    assert paths == {
        "latest": "logs/qre_opportunity_research_value/latest.json",
        "doc": "docs/governance/qre_opportunity_research_value.md",
    }
    assert "QRE Opportunity Research Value" in (
        tmp_path / paths["doc"]
    ).read_text(encoding="utf-8")
    assert opportunity_report.read_opportunity_research_value_status(repo_root=tmp_path) == {
        "status": "ready",
        "path": "logs/qre_opportunity_research_value/latest.json",
        "fails_closed": False,
        "schema_version": "1.0",
    }


def test_surface_has_no_execution_registration_or_campaign_authority(tmp_path: Path) -> None:
    _write_upstreams(tmp_path)
    report = opportunity_report.build_opportunity_research_value(repo_root=tmp_path)

    for row in report["rows"]:
        assert row["authority"] == {
            "can_generate_executable_strategy": False,
            "can_register_strategy": False,
            "can_promote_candidate": False,
            "can_launch_campaign": False,
            "can_activate_paper_shadow_live": False,
            "evidence_authority": "context_only",
        }
    assert report["safety_invariants"]["can_generate_executable_strategy"] is False
    assert report["safety_invariants"]["can_register_strategy"] is False
    assert report["safety_invariants"]["can_launch_campaign"] is False


def test_source_is_read_only_and_preserves_frozen_contracts() -> None:
    source = Path(opportunity_report.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])

    assert imported.isdisjoint({"requests", "socket", "httpx", "urllib", "subprocess"})
    assert "research/research_latest.json" not in source
    assert "research/strategy_matrix.csv" not in source
