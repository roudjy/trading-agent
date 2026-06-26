from __future__ import annotations

import ast
import json
from pathlib import Path

from research import qre_behavior_thesis_registry as registry
from research.strategy_hypothesis_catalog import StrategyHypothesis


def _disposition_memory() -> dict[str, object]:
    return {
        "schema_version": "1.0",
        "report_kind": "qre_hypothesis_disposition_memory",
        "record": {
            "memory_record_id": "qhm_test_001",
            "hypothesis_id": "trend_pullback_v1",
            "behavior_id": "pullback_continuation",
            "failure_classes": [
                "non_positive_oos_trade_count",
                "all_windows_non_positive_trade_count",
            ],
        },
    }


def _write_disposition_memory(tmp_path: Path) -> None:
    path = tmp_path / "logs" / "qre_hypothesis_disposition_memory" / "latest.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(_disposition_memory(), indent=2), encoding="utf-8")


def _duplicate_catalog_row() -> StrategyHypothesis:
    base = registry.STRATEGY_HYPOTHESIS_CATALOG[0]
    return StrategyHypothesis(
        hypothesis_id="trend_pullback_duplicate_v1",
        strategy_family=base.strategy_family,
        status=base.status,
        description=base.description,
        feature_dependencies=base.feature_dependencies,
        parameter_schema=base.parameter_schema,
        default_parameter_grid=base.default_parameter_grid,
        eligible_campaign_types=base.eligible_campaign_types,
        expected_failure_modes=base.expected_failure_modes,
        baseline_reference=base.baseline_reference,
        cost_class=base.cost_class,
        policy_metadata=dict(base.policy_metadata),
    )


def test_registry_is_deterministic_and_stable(tmp_path: Path) -> None:
    _write_disposition_memory(tmp_path)

    left = registry.build_behavior_thesis_registry(repo_root=tmp_path)
    right = registry.build_behavior_thesis_registry(repo_root=tmp_path)

    assert left == right
    assert left["report_kind"] == "qre_behavior_thesis_registry"
    assert left["summary"]["research_ready"] is True
    assert left["summary"]["thesis_count"] == len(left["rows"])
    assert [row["thesis_id"] for row in left["rows"]] == sorted(
        row["thesis_id"] for row in left["rows"]
    )


def test_required_fields_and_provenance_are_present(tmp_path: Path) -> None:
    _write_disposition_memory(tmp_path)

    report = registry.build_behavior_thesis_registry(repo_root=tmp_path)
    row = report["rows"][0]

    for field in registry.REQUIRED_FIELDS:
        assert field in row
        assert row[field]
    assert row["schema_version"] == registry.SCHEMA_VERSION
    assert row["supporting_evidence"]
    assert row["provenance_refs"]
    assert row["authority"]["evidence_authority"] == "context_only"


def test_disposition_memory_surfaces_contradictions_and_prior_failures(tmp_path: Path) -> None:
    _write_disposition_memory(tmp_path)

    report = registry.build_behavior_thesis_registry(repo_root=tmp_path)
    row = next(
        item for item in report["rows"] if item["source_hypothesis_id"] == "trend_pullback_v1"
    )

    assert row["contradicting_evidence"] == [
        "logs/qre_hypothesis_disposition_memory/latest.json#record::qhm_test_001"
    ]
    assert row["prior_similar_failures"] == [
        "non_positive_oos_trade_count",
        "all_windows_non_positive_trade_count",
    ]


def test_incomplete_thesis_fails_closed() -> None:
    result = registry.validate_behavior_thesis(
        {
            "thesis_id": "qbt_missing",
            "title": "",
            "behavior_family": "",
            "mechanism": "",
            "expected_behavior": "",
            "universe": "",
            "timeframe": "",
            "regime_context": "",
            "falsification_plan": [],
            "minimum_sample": "",
            "signal_density_expectation": "unknown",
            "screening_plan": [],
            "validation_plan": [],
            "oos_plan": [],
            "null_controls": [],
            "data_requirements": [],
            "source_requirements": [],
            "supporting_evidence": [],
            "contradicting_evidence": [],
            "prior_similar_failures": [],
            "status": "draft",
            "created_at_equivalent": "",
            "schema_version": registry.SCHEMA_VERSION,
            "duplicate_signature": "dup",
            "authority": {
                "can_generate_executable_strategy": False,
                "can_register_strategy": False,
                "can_launch_campaign": False,
            },
        }
    )

    assert result["valid"] is False
    assert "missing_required_fields" in result["rejection_reasons"]


def test_invalid_vocabulary_is_rejected(tmp_path: Path) -> None:
    _write_disposition_memory(tmp_path)
    report = registry.build_behavior_thesis_registry(repo_root=tmp_path)
    row = dict(report["rows"][0])
    row["status"] = "invented_status"
    row["signal_density_expectation"] = "impossible"

    result = registry.validate_behavior_thesis(row)

    assert result["valid"] is False
    assert "invalid_status" in result["rejection_reasons"]
    assert "invalid_signal_density_expectation" in result["rejection_reasons"]


def test_duplicate_handling_rejects_duplicate_signature(tmp_path: Path) -> None:
    _write_disposition_memory(tmp_path)
    catalog = tuple(registry.STRATEGY_HYPOTHESIS_CATALOG) + (_duplicate_catalog_row(),)

    report = registry.build_behavior_thesis_registry(repo_root=tmp_path, catalog=catalog)

    assert report["summary"]["research_ready"] is False
    assert report["summary"]["duplicate_signature_count"] == 1
    assert any(
        "duplicate_thesis_signature" in row["rejection_reasons"]
        for row in report["validations"]
    )


def test_write_outputs_and_status_round_trip(tmp_path: Path) -> None:
    _write_disposition_memory(tmp_path)
    report = registry.build_behavior_thesis_registry(repo_root=tmp_path)

    paths = registry.write_outputs(report, repo_root=tmp_path)

    assert paths == {
        "latest": "logs/qre_behavior_thesis_registry/latest.json",
        "doc": "docs/governance/qre_behavior_thesis_registry.md",
    }
    assert "QRE Behavior Thesis Registry" in (
        tmp_path / paths["doc"]
    ).read_text(encoding="utf-8")
    assert registry.read_behavior_thesis_registry_status(repo_root=tmp_path) == {
        "status": "ready",
        "research_ready": True,
        "path": "logs/qre_behavior_thesis_registry/latest.json",
        "fails_closed": False,
        "schema_version": "1.0",
    }


def test_registry_has_no_execution_or_registration_authority(tmp_path: Path) -> None:
    _write_disposition_memory(tmp_path)
    report = registry.build_behavior_thesis_registry(repo_root=tmp_path)

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


def test_registry_source_is_read_only_and_preserves_frozen_contracts() -> None:
    source = Path(registry.__file__).read_text(encoding="utf-8")
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
