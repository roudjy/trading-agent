from __future__ import annotations

import ast
import json
from pathlib import Path

from reporting import qre_suppression_efficacy as efficacy


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _seed(tmp_path: Path) -> None:
    _write_json(
        tmp_path / "logs" / "qre_research_cycle_router" / "latest.json",
        {
            "suppressed_scopes": [
                {"scope_kind": "exact_failed_scope", "suppression_reason": "same_failed_scope_suppressed"},
                {
                    "scope_kind": "materially_equivalent_retry",
                    "suppression_reason": "insufficient_scope_novelty",
                },
            ],
            "eligible_directions": [
                {"direction_id": "behavior_rotation::relative_strength"},
                {"direction_id": "behavior_rotation::trend_continuation"},
                {"direction_id": "null_control_investigation"},
            ],
        },
    )
    _write_json(
        tmp_path / "logs" / "qre_experiment_dedup_novelty_enforcement" / "latest.json",
        {
            "duplicate_rows": [
                {
                    "duplicate_class": "duplicate_low_value_run_pressure",
                    "status": "context_only_duplicate_pressure",
                },
                {"duplicate_class": "exact_failed_scope", "status": "suppressed"},
                {"duplicate_class": "materially_equivalent_retry", "status": "suppressed"},
            ]
        },
    )
    _write_json(
        tmp_path / "logs" / "qre_prior_failure_retrieval" / "latest.json",
        {
            "rows": [
                {"thesis_id": "t1", "dead_zone_count": 1},
                {"thesis_id": "t2", "dead_zone_count": 0},
            ]
        },
    )
    _write_json(
        tmp_path / "logs" / "qre_routing_baseline_comparison" / "latest.json",
        {"baselines": [{"baseline_id": "current_routing_score", "decision_usefulness_score": 1.25}]},
    )
    _write_json(
        tmp_path / "logs" / "qre_sampling_baseline_comparison" / "latest.json",
        {"baselines": [{"baseline_id": "current_sampling_score", "decision_usefulness_score": 1.75}]},
    )
    _write_json(
        tmp_path / "research" / "run_candidates_latest.v1.json",
        {"summary": {"duplicates_removed": 0}},
    )
    _write_json(
        tmp_path / "research" / "run_manifest_latest.v1.json",
        {"status": "failed", "deduplicated_candidate_count": 2},
    )
    _write_json(
        tmp_path / "research" / "campaign_registry_latest.v1.json",
        {"campaigns": {"camp-1": {"campaign_id": "camp-1", "state": "completed"}}},
    )
    _write_json(
        tmp_path / "logs" / "qre_campaign_throughput_bottleneck_intelligence" / "latest.json",
        {
            "bottlenecks": [
                {"bottleneck_code": "duplicate_low_value_run_pressure"},
            ],
            "summary": {"duplicate_low_value_run_count": 1},
        },
    )


def test_build_is_deterministic_and_fails_closed_on_missing_baseline(tmp_path: Path) -> None:
    _seed(tmp_path)

    left = efficacy.build_suppression_efficacy(repo_root=tmp_path)
    right = efficacy.build_suppression_efficacy(repo_root=tmp_path)

    assert left == right
    assert left["report_kind"] == "qre_suppression_efficacy"
    assert left["mechanics_vs_evidence"]["mechanics_exist"] is True
    assert left["mechanics_vs_evidence"]["evidence_populated"] is True
    assert left["mechanics_vs_evidence"]["efficacy_measured"] is False
    assert left["summary"]["final_recommendation"] == "suppression_efficacy_insufficient_baseline"


def test_metrics_capture_observed_prevention_counts(tmp_path: Path) -> None:
    _seed(tmp_path)
    report = efficacy.build_suppression_efficacy(repo_root=tmp_path)

    assert efficacy._find_metric(report["metrics"], "eligible_comparison_population")["value"] == 5
    assert efficacy._find_metric(report["metrics"], "repeated_rejected_scopes_prevented")["value"] == 2
    assert efficacy._find_metric(report["metrics"], "dead_zone_selections_avoided")["value"] == 1
    assert efficacy._find_metric(report["metrics"], "evaluations_avoided")["value"] == 2
    assert efficacy._find_metric(report["metrics"], "useful_outcome_rate_with_suppression")["status"] == "insufficient_evidence"
    assert report["unresolved_cases"][0]["case_id"] == "duplicate_low_value_run_pressure"


def test_missing_upstream_surface_fails_closed_without_inventing_values(tmp_path: Path) -> None:
    _seed(tmp_path)
    (tmp_path / "logs" / "qre_prior_failure_retrieval" / "latest.json").unlink()

    report = efficacy.build_suppression_efficacy(repo_root=tmp_path)

    assert report["source_status"]["prior_failure_retrieval"]["status"] == "missing"
    assert efficacy._find_metric(report["metrics"], "dead_zone_selections_avoided")["status"] == "missing"
    assert efficacy._find_metric(report["metrics"], "dead_zone_selections_avoided")["value"] is None


def test_metric_validation_rejects_missing_provenance() -> None:
    validation = efficacy.validate_metric(
        {
            "metric_id": "m",
            "status": "observed",
            "value": 1,
            "provenance_refs": [],
        }
    )

    assert validation["valid"] is False
    assert "missing_provenance_refs" in validation["rejection_reasons"]


def test_write_outputs_and_status_round_trip(tmp_path: Path) -> None:
    _seed(tmp_path)
    report = efficacy.build_suppression_efficacy(repo_root=tmp_path)

    paths = efficacy.write_outputs(report, repo_root=tmp_path)

    assert paths == {
        "latest": "logs/qre_suppression_efficacy/latest.json",
        "doc": "docs/governance/qre_suppression_efficacy.md",
    }
    assert "QRE Suppression Efficacy" in (tmp_path / paths["doc"]).read_text(encoding="utf-8")
    assert efficacy.read_status(repo_root=tmp_path) == {
        "status": "ready",
        "path": "logs/qre_suppression_efficacy/latest.json",
        "fails_closed": False,
        "schema_version": "1.0",
    }


def test_source_is_read_only_and_preserves_frozen_contracts() -> None:
    source = Path(efficacy.__file__).read_text(encoding="utf-8")
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
    assert "\"can_launch_campaign\": False" in source
