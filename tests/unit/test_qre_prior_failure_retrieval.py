from __future__ import annotations

import ast
import json
from pathlib import Path

from research import qre_prior_failure_retrieval as prior_failure


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _write_upstreams(tmp_path: Path) -> None:
    _write_json(
        tmp_path / "logs" / "qre_hypothesis_disposition_memory" / "latest.json",
        {
            "schema_version": "1.0",
            "report_kind": "qre_hypothesis_disposition_memory",
            "record": {
                "memory_record_id": "qhm_001",
                "hypothesis_id": "trend_pullback_v1",
                "behavior_id": "pullback_continuation",
                "failure_classes": [
                    "non_positive_oos_trade_count",
                    "all_windows_non_positive_trade_count",
                ],
            },
        },
    )
    _write_json(
        tmp_path / "logs" / "qre_research_memory_retrieval" / "latest.json",
        {
            "schema_version": "1.0",
            "report_kind": "qre_research_memory_retrieval",
            "queries": [
                {
                    "query_id": "exact_scope_already_tested",
                    "answer": True,
                    "scope_signature": {
                        "hypothesis_id": "trend_pullback_v1",
                    },
                },
                {
                    "query_id": "materially_similar_scope_rejected",
                    "answer": True,
                    "failure_classes": [
                        "non_positive_oos_trade_count",
                        "all_windows_non_positive_trade_count",
                    ],
                },
                {
                    "query_id": "recurring_evidence_or_source_failures",
                    "rows": [{"failure_or_blocker": "oos_evidence_missing", "count": 3}],
                },
                {
                    "query_id": "novel_remaining_research_directions",
                    "rows": [{"direction_id": "behavior_rotation::index_regime_filter"}],
                },
            ],
        },
    )
    _write_json(
        tmp_path / "logs" / "qre_evidence_breadth_framework" / "latest.json",
        {
            "coverage_matrix": [
                {
                    "dimension": "behavior",
                    "scope_key": "trend_pullback",
                    "accepted_oos_count": 0,
                    "blocker_reasons": ["no_oos_evidence", "campaign_lineage_missing"],
                }
            ]
        },
    )
    _write_json(
        tmp_path / "logs" / "qre_research_cycle_router" / "latest.json",
        {
            "recommended_research_action": "propose_materially_new_behavior_family",
            "eligible_directions": [
                {
                    "direction_id": "behavior_rotation::index_regime_filter",
                    "route_status": "eligible_context_only",
                }
            ],
        },
    )
    _write_json(
        tmp_path / "logs" / "qre_experiment_dedup_novelty_enforcement" / "latest.json",
        {
            "duplicate_rows": [
                {
                    "duplicate_class": "exact_failed_scope",
                    "evidence_refs": [
                        "logs/qre_research_cycle_router/latest.json",
                        "logs/qre_hypothesis_disposition_memory/latest.json",
                    ],
                }
            ]
        },
    )


def test_build_is_deterministic_and_surfaces_prior_failure_context(tmp_path: Path) -> None:
    _write_upstreams(tmp_path)

    left = prior_failure.build_prior_failure_retrieval(repo_root=tmp_path)
    right = prior_failure.build_prior_failure_retrieval(repo_root=tmp_path)

    assert left == right
    assert left["report_kind"] == "qre_prior_failure_retrieval"
    assert left["summary"]["thesis_count"] == len(left["rows"])
    row = next(item for item in left["rows"] if item["source_hypothesis_id"] == "trend_pullback_v1")
    assert row["prior_failure_count"] > 0
    assert row["dead_zone_count"] > 0
    assert row["prior_action_count"] > 0
    assert row["retrieval_match_count"] >= 0


def test_required_fields_and_provenance_are_present(tmp_path: Path) -> None:
    _write_upstreams(tmp_path)
    report = prior_failure.build_prior_failure_retrieval(repo_root=tmp_path)
    row = report["rows"][0]

    for field in prior_failure.ROW_REQUIRED_FIELDS:
        assert field in row
        value = row[field]
        assert value is not None
        if isinstance(value, str):
            assert value
        elif isinstance(value, list):
            assert value
    for item in row["retrieval_items"]:
        for field in prior_failure.ITEM_REQUIRED_FIELDS:
            assert field in item
            assert item[field]
        assert item["authority"]["evidence_authority"] == "context_only"


def test_invalid_vocabularies_are_rejected() -> None:
    result = prior_failure.validate_prior_failure_row(
        {
            "thesis_id": "qbt_invalid",
            "source_hypothesis_id": "src",
            "behavior_family": "trend_continuation",
            "thesis_status": "draft",
            "summary_status": "invented",
            "retrieval_query": "src trend",
            "prior_failure_count": 1,
            "dead_zone_count": 0,
            "prior_action_count": 0,
            "retrieval_match_count": 0,
            "provenance_refs": ["fixture#1"],
            "schema_version": prior_failure.SCHEMA_VERSION,
            "retrieval_items": [
                {
                    "retrieval_id": "id",
                    "thesis_id": "qbt_invalid",
                    "retrieval_kind": "wrong",
                    "status": "wrong",
                    "retrieval_ref": "fixture#1",
                    "summary": "fixture",
                    "linked_by": "fixture",
                    "provenance_refs": ["fixture#1"],
                    "authority": {
                        "can_generate_executable_strategy": False,
                        "can_register_strategy": False,
                        "can_promote_candidate": False,
                        "can_launch_campaign": False,
                        "can_activate_paper_shadow_live": False,
                        "evidence_authority": "context_only",
                    },
                }
            ],
        }
    )

    assert result["valid"] is False
    assert "invalid_summary_status" in result["rejection_reasons"]
    assert "invalid_retrieval_kind" in result["rejection_reasons"]
    assert "invalid_item_status" in result["rejection_reasons"]


def test_missing_explicit_states_fail_closed() -> None:
    result = prior_failure.validate_prior_failure_row(
        {
            "thesis_id": "qbt_missing",
            "source_hypothesis_id": "src",
            "behavior_family": "trend_continuation",
            "thesis_status": "draft",
            "summary_status": "prior_failure_visible",
            "retrieval_query": "src trend",
            "prior_failure_count": 1,
            "dead_zone_count": 0,
            "prior_action_count": 0,
            "retrieval_match_count": 0,
            "provenance_refs": ["fixture#1"],
            "schema_version": prior_failure.SCHEMA_VERSION,
            "retrieval_items": [
                {
                    "retrieval_id": "id",
                    "thesis_id": "qbt_missing",
                    "retrieval_kind": "prior_failure",
                    "status": "present",
                    "retrieval_ref": "fixture#1",
                    "summary": "fixture",
                    "linked_by": "fixture",
                    "provenance_refs": ["fixture#1"],
                    "authority": {
                        "can_generate_executable_strategy": False,
                        "can_register_strategy": False,
                        "can_promote_candidate": False,
                        "can_launch_campaign": False,
                        "can_activate_paper_shadow_live": False,
                        "evidence_authority": "context_only",
                    },
                }
            ],
        }
    )

    assert result["valid"] is False
    assert "missing_explicit_dead_zone_state" in result["rejection_reasons"]
    assert "missing_explicit_prior_action_state" in result["rejection_reasons"]


def test_write_outputs_and_status_round_trip(tmp_path: Path) -> None:
    _write_upstreams(tmp_path)
    report = prior_failure.build_prior_failure_retrieval(repo_root=tmp_path)

    paths = prior_failure.write_outputs(report, repo_root=tmp_path)

    assert paths == {
        "latest": "logs/qre_prior_failure_retrieval/latest.json",
        "doc": "docs/governance/qre_prior_failure_retrieval.md",
    }
    assert "QRE Prior-Failure Retrieval" in (
        tmp_path / paths["doc"]
    ).read_text(encoding="utf-8")
    assert prior_failure.read_prior_failure_retrieval_status(repo_root=tmp_path) == {
        "status": "ready",
        "path": "logs/qre_prior_failure_retrieval/latest.json",
        "fails_closed": False,
        "schema_version": "1.0",
    }


def test_surface_has_no_execution_or_registration_authority(tmp_path: Path) -> None:
    _write_upstreams(tmp_path)
    report = prior_failure.build_prior_failure_retrieval(repo_root=tmp_path)

    for row in report["rows"]:
        for item in row["retrieval_items"]:
            assert item["authority"] == {
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
    source = Path(prior_failure.__file__).read_text(encoding="utf-8")
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
