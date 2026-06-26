from __future__ import annotations

import ast
import json
from pathlib import Path

from research import qre_behavior_thesis_evidence as evidence
from research import qre_behavior_thesis_registry as registry


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
                "failure_classes": ["all_windows_non_positive_trade_count"],
            },
        },
    )
    _write_json(
        tmp_path / "logs" / "hypothesis_discovery_minimal" / "latest.json",
        {
            "schema_version": 1,
            "report_kind": "hypothesis_discovery_minimal_digest",
            "items": [
                {
                    "hypothesis_id": "trend_pullback_v1",
                    "strategy_mapping_ref": "strategy_hypothesis_catalog:trend_pullback_v1",
                }
            ],
            "seeds": [
                {
                    "seed_id": "hds_001",
                    "strategy_mapping_ref": "strategy_hypothesis_catalog:trend_pullback_v1",
                }
            ],
        },
    )
    _write_json(
        tmp_path / "logs" / "qre_hypothesis_validation_results" / "latest.json",
        {
            "schema_version": 1,
            "report_kind": "qre_hypothesis_validation_results",
            "validation_results": [
                {
                    "result_id": "qre-result-001",
                    "hypothesis_id": "trend_pullback_v1",
                }
            ],
        },
    )
    _write_json(
        tmp_path / "logs" / "qre_hypothesis_evidence_updates" / "latest.json",
        {
            "schema_version": 1,
            "report_kind": "qre_hypothesis_evidence_update",
            "evidence_updates": [
                {
                    "evidence_update_id": "qre-update-001",
                    "hypothesis_id": "trend_pullback_v1",
                }
            ],
        },
    )


def test_build_is_deterministic_and_surfaces_all_evidence_states(tmp_path: Path) -> None:
    _write_upstreams(tmp_path)

    left = evidence.build_behavior_thesis_evidence(repo_root=tmp_path)
    right = evidence.build_behavior_thesis_evidence(repo_root=tmp_path)

    assert left == right
    assert left["report_kind"] == "qre_behavior_thesis_evidence"
    assert left["summary"]["thesis_count"] == len(left["rows"])
    row = next(item for item in left["rows"] if item["source_hypothesis_id"] == "trend_pullback_v1")
    assert row["supporting_evidence_count"] > 0
    assert row["contradicting_evidence_count"] > 0
    assert row["unresolved_evidence_count"] > 0


def test_required_fields_and_provenance_are_present(tmp_path: Path) -> None:
    _write_upstreams(tmp_path)
    report = evidence.build_behavior_thesis_evidence(repo_root=tmp_path)
    row = report["rows"][0]

    for field in evidence.ROW_REQUIRED_FIELDS:
        assert field in row
        assert row[field]
    for item in row["evidence_items"]:
        for field in evidence.ITEM_REQUIRED_FIELDS:
            assert field in item
            assert item[field]
        assert item["authority"]["evidence_authority"] == "context_only"


def test_invalid_vocabularies_are_rejected() -> None:
    result = evidence.validate_thesis_evidence_row(
        {
            "thesis_id": "qbt_invalid",
            "source_hypothesis_id": "src",
            "behavior_family": "trend_continuation",
            "thesis_status": "draft",
            "summary_status": "invented",
            "supporting_evidence_count": 1,
            "contradicting_evidence_count": 1,
            "unresolved_evidence_count": 1,
            "provenance_refs": ["fixture#1"],
            "schema_version": evidence.SCHEMA_VERSION,
            "evidence_items": [
                {
                    "evidence_id": "id",
                    "thesis_id": "qbt_invalid",
                    "stance": "wrong",
                    "evidence_kind": "wrong",
                    "evidence_ref": "fixture#1",
                    "status": "wrong",
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
    assert "invalid_stance" in result["rejection_reasons"]
    assert "invalid_evidence_kind" in result["rejection_reasons"]
    assert "invalid_item_status" in result["rejection_reasons"]


def test_duplicate_handling_dedupes_and_records_duplicates(tmp_path: Path) -> None:
    _write_upstreams(tmp_path)
    registry_report = registry.build_behavior_thesis_registry(repo_root=tmp_path)
    row = dict(registry_report["rows"][0])
    row["supporting_evidence"] = list(row["supporting_evidence"]) + [row["supporting_evidence"][0]]
    registry_report["rows"][0] = row

    report = evidence.build_behavior_thesis_evidence(
        repo_root=tmp_path,
        registry_report=registry_report,
    )

    assert report["summary"]["duplicate_item_count"] >= 1


def test_missing_or_incomplete_visibility_fails_closed() -> None:
    result = evidence.validate_thesis_evidence_row(
        {
            "thesis_id": "qbt_missing",
            "source_hypothesis_id": "src",
            "behavior_family": "trend_continuation",
            "thesis_status": "draft",
            "summary_status": "support_visible",
            "supporting_evidence_count": 1,
            "contradicting_evidence_count": 0,
            "unresolved_evidence_count": 0,
            "provenance_refs": ["fixture#1"],
            "schema_version": evidence.SCHEMA_VERSION,
            "evidence_items": [
                {
                    "evidence_id": "id",
                    "thesis_id": "qbt_missing",
                    "stance": "supporting",
                    "evidence_kind": "strategy_hypothesis_catalog",
                    "evidence_ref": "fixture#1",
                    "status": "present",
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
    assert "missing_contradicting_evidence_visibility" in result["rejection_reasons"]
    assert "missing_unresolved_evidence_visibility" in result["rejection_reasons"]


def test_write_outputs_and_status_round_trip(tmp_path: Path) -> None:
    _write_upstreams(tmp_path)
    report = evidence.build_behavior_thesis_evidence(repo_root=tmp_path)

    paths = evidence.write_outputs(report, repo_root=tmp_path)

    assert paths == {
        "latest": "logs/qre_behavior_thesis_evidence/latest.json",
        "doc": "docs/governance/qre_behavior_thesis_evidence.md",
    }
    assert "QRE Behavior Thesis Evidence" in (
        tmp_path / paths["doc"]
    ).read_text(encoding="utf-8")
    assert evidence.read_behavior_thesis_evidence_status(repo_root=tmp_path) == {
        "status": "ready",
        "path": "logs/qre_behavior_thesis_evidence/latest.json",
        "fails_closed": False,
        "schema_version": "1.0",
    }


def test_surface_has_no_execution_or_registration_authority(tmp_path: Path) -> None:
    _write_upstreams(tmp_path)
    report = evidence.build_behavior_thesis_evidence(repo_root=tmp_path)

    for row in report["rows"]:
        for item in row["evidence_items"]:
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
    source = Path(evidence.__file__).read_text(encoding="utf-8")
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
