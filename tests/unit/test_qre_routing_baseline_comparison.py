from __future__ import annotations

import ast
import json
from pathlib import Path

from research import qre_routing_baseline_comparison as comparison


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _seed(tmp_path: Path) -> None:
    _write_json(
        tmp_path / "logs" / "qre_opportunity_research_value" / "latest.json",
        {
            "rows": [
                {
                    "behavior_family": "index_regime_filter",
                    "opportunity_score": 0.8,
                    "priority_band": "high",
                    "recommended_next_action": "advance_to_routing_comparison",
                },
                {
                    "behavior_family": "post_shock_stabilization",
                    "opportunity_score": 0.2,
                    "priority_band": "low",
                    "recommended_next_action": "resolve_data_readiness",
                },
                {
                    "behavior_family": "relative_strength",
                    "opportunity_score": 0.6,
                    "priority_band": "medium",
                    "recommended_next_action": "increase_evidence_density",
                },
            ]
        },
    )
    _write_json(
        tmp_path / "logs" / "qre_research_cycle_router" / "latest.json",
        {
            "eligible_directions": [
                {
                    "direction_id": "behavior_rotation::post_shock_stabilization",
                    "route_status": "eligible_context_only",
                    "target_hypothesis": {"behavior_id": "post_shock_stabilization"},
                    "routing_context_only": {
                        "routing_score": 0.40,
                        "blocked_reasons": [],
                        "score_components": {
                            "information_gain_proxy_score": 0.4,
                            "evidence_gap_reduction_score": 0.5,
                            "source_cache_readiness_score": 0.6,
                            "behavior_diversity_score": 1.0,
                            "feasibility_score": 1.0,
                            "prior_failure_penalty": 0.1,
                            "compute_cost_penalty": 0.2,
                        },
                    },
                },
                {
                    "direction_id": "behavior_rotation::index_regime_filter",
                    "route_status": "eligible_context_only",
                    "target_hypothesis": {"behavior_id": "index_regime_filter"},
                    "routing_context_only": {
                        "routing_score": 0.61,
                        "blocked_reasons": [],
                        "score_components": {
                            "information_gain_proxy_score": 0.9,
                            "evidence_gap_reduction_score": 0.6,
                            "source_cache_readiness_score": 1.0,
                            "behavior_diversity_score": 1.0,
                            "feasibility_score": 1.0,
                            "prior_failure_penalty": 0.1,
                            "compute_cost_penalty": 0.2,
                        },
                    },
                },
                {
                    "direction_id": "behavior_rotation::relative_strength",
                    "route_status": "eligible_context_only",
                    "target_hypothesis": {"behavior_id": "relative_strength"},
                    "routing_context_only": {
                        "routing_score": 0.51,
                        "blocked_reasons": ["context_only"],
                        "score_components": {
                            "information_gain_proxy_score": 0.8,
                            "evidence_gap_reduction_score": 0.4,
                            "source_cache_readiness_score": 0.8,
                            "behavior_diversity_score": 1.0,
                            "feasibility_score": 1.0,
                            "prior_failure_penalty": 0.2,
                            "compute_cost_penalty": 0.3,
                        },
                    },
                },
            ]
        },
    )


def test_build_is_deterministic_and_current_routing_beats_fifo(tmp_path: Path) -> None:
    _seed(tmp_path)
    left = comparison.build_routing_baseline_comparison(repo_root=tmp_path)
    right = comparison.build_routing_baseline_comparison(repo_root=tmp_path)

    assert left == right
    assert left["report_kind"] == "qre_routing_baseline_comparison"
    assert left["summary"]["best_baseline_id"] == "current_routing_score"
    assert left["summary"]["current_minus_fifo"] > 0
    assert left["source_status"]["research_cycle_router"]["status"] == "ready"
    assert left["source_status"]["opportunity_research_value"]["status"] == "ready"


def test_baseline_vocab_and_rankings_are_closed(tmp_path: Path) -> None:
    _seed(tmp_path)
    report = comparison.build_routing_baseline_comparison(repo_root=tmp_path)

    assert [row["baseline_id"] for row in report["baselines"]] == sorted(
        [row["baseline_id"] for row in report["baselines"]],
        key=lambda baseline_id: -next(
            row["decision_usefulness_score"]
            for row in report["baselines"]
            if row["baseline_id"] == baseline_id
        ),
    )
    for row in report["baselines"]:
        assert row["baseline_id"] in comparison.BASELINE_IDS
        assert row["comparison_scope"] == "context_only_not_execution_authority"
        assert comparison.validate_baseline(row) == {"valid": True, "rejection_reasons": []}
    for row in report["directions"]:
        assert comparison.validate_direction(row) == {"valid": True, "rejection_reasons": []}


def test_missing_opportunity_surface_fails_closed(tmp_path: Path) -> None:
    _seed(tmp_path)
    (tmp_path / "logs" / "qre_opportunity_research_value" / "latest.json").unlink()

    report = comparison.build_routing_baseline_comparison(repo_root=tmp_path)

    assert all(direction["opportunity_score"] == 0.0 for direction in report["directions"])
    assert report["source_status"]["opportunity_research_value"]["status"] == "missing"


def test_direction_rows_keep_provenance_and_closed_vocab(tmp_path: Path) -> None:
    _seed(tmp_path)
    report = comparison.build_routing_baseline_comparison(repo_root=tmp_path)

    direction = report["directions"][0]
    assert direction["opportunity_priority_band"] in comparison.PRIORITY_BAND_VALUES
    assert direction["opportunity_next_action"] in comparison.NEXT_ACTION_VALUES
    assert direction["provenance_refs"]
    assert direction["provenance_refs"][0].startswith("logs/qre_research_cycle_router/latest.json#eligible_directions[")


def test_invalid_row_validation_fails_closed() -> None:
    validation = comparison.validate_direction(
        {
            "direction_id": "bad",
            "behavior_id": "b",
            "route_status": "eligible_context_only",
            "artifact_index": 0,
            "blocked_reason_count": 0,
            "routing_score": 1.2,
            "opportunity_score": 0.2,
            "opportunity_priority_band": "invented",
            "opportunity_next_action": "invented",
            "decision_usefulness_proxy": -0.1,
            "information_gain_proxy_score": 0.3,
            "provenance_refs": [],
        }
    )

    assert validation["valid"] is False
    assert "invalid_priority_band" in validation["rejection_reasons"]
    assert "invalid_next_action" in validation["rejection_reasons"]
    assert "missing_provenance_refs" in validation["rejection_reasons"]
    assert "out_of_range_routing_score" in validation["rejection_reasons"]
    assert "out_of_range_decision_usefulness_proxy" in validation["rejection_reasons"]


def test_write_outputs_and_status_round_trip(tmp_path: Path) -> None:
    _seed(tmp_path)
    report = comparison.build_routing_baseline_comparison(repo_root=tmp_path)

    paths = comparison.write_outputs(report, repo_root=tmp_path)

    assert paths == {
        "latest": "logs/qre_routing_baseline_comparison/latest.json",
        "doc": "docs/governance/qre_routing_baseline_comparison.md",
    }
    assert "QRE Routing Baseline Comparison" in (
        tmp_path / paths["doc"]
    ).read_text(encoding="utf-8")
    assert comparison.read_status(repo_root=tmp_path) == {
        "status": "ready",
        "path": "logs/qre_routing_baseline_comparison/latest.json",
        "fails_closed": False,
        "schema_version": "1.0",
    }


def test_source_is_read_only_and_preserves_frozen_contracts() -> None:
    source = Path(comparison.__file__).read_text(encoding="utf-8")
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
    assert "can_launch_campaign\": False" in source or "\"can_launch_campaign\": False" in source
