from __future__ import annotations

import ast
import json
from pathlib import Path

from packages.qre_research import retrieval_coverage

FROZEN = "2026-05-25T00:00:00Z"


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, sort_keys=True, indent=2), encoding="utf-8")


def _seed_linked_trusted_loop_artifacts(tmp_path: Path) -> list[Path]:
    reason_density = tmp_path / "logs" / "reason_record_evidence_density" / "latest.json"
    failure_actions = tmp_path / "logs" / "failure_action_mapping_minimal" / "latest.json"
    diagnostics = tmp_path / "logs" / "qre_research_diagnostics_loop" / "latest.json"
    materialization = tmp_path / "logs" / "trusted_loop_materialization" / "latest.json"

    _write_json(
        reason_density,
        {
            "report_kind": "reason_record_evidence_density",
            "records_top": [
                {
                    "record_id": "rr_1",
                    "subject_id": "campaign-a",
                    "reason_codes": ["info_gain_low"],
                    "reason_text": "routing reason kept for trusted loop review",
                    "evidence_refs": ["logs/intelligent_routing_minimal/latest.json"],
                }
            ],
        },
    )
    _write_json(
        failure_actions,
        {
            "report_kind": "failure_action_mapping_minimal",
            "items": [
                {
                    "subject_id": "screening-a",
                    "classification": "insufficient_trades",
                    "raw_reasons": {"insufficient_trades": 1},
                    "action_hint": {"action": "increase_timeframe"},
                    "reason_record": {
                        "reason_codes": ["operator_directive"],
                        "evidence_refs": [
                            "research/screening_failure_attribution_latest.v1.json"
                        ],
                    },
                }
            ],
            "total_failures": 1,
        },
    )
    _write_json(
        diagnostics,
        {
            "report_kind": "qre_research_diagnostics_loop",
            "summary": {
                "recommended_operator_step": "inspect_failure_action_mapping",
                "blocking_reasons": [],
            },
        },
    )
    _write_json(
        materialization,
        {
            "report_kind": "trusted_loop_materialization_digest",
            "block_reasons": [
                "routing_ready_evidence_missing_or_not_ready",
                "no_complete_research_quality_kpi_values",
            ],
            "synthesis_blocker_explanation_density": {
                "values": {
                    "routing_ready_evidence_missing_or_not_ready": {
                        "source_ref": "logs/intelligent_routing_minimal/latest.json",
                        "missing_evidence": ["prioritize_count_positive"],
                        "operator_explanation": "Routing remains fail_closed.",
                    }
                }
            },
        },
    )

    return [
        Path("logs/reason_record_evidence_density/latest.json"),
        Path("logs/failure_action_mapping_minimal/latest.json"),
        Path("logs/qre_research_diagnostics_loop/latest.json"),
        Path("logs/trusted_loop_materialization/latest.json"),
    ]


def test_retrieval_coverage_is_deterministic_and_linked(tmp_path: Path) -> None:
    artifact_paths = _seed_linked_trusted_loop_artifacts(tmp_path)

    left = retrieval_coverage.build_retrieval_coverage(
        artifact_paths=artifact_paths,
        repo_root=tmp_path,
        generated_at_utc=FROZEN,
    )
    right = retrieval_coverage.build_retrieval_coverage(
        artifact_paths=artifact_paths,
        repo_root=tmp_path,
        generated_at_utc=FROZEN,
    )

    assert left == right
    assert left["summary"]["status"] == "ready"
    assert left["summary"]["coverage_score"] == 1.0
    assert left["operator_summary"]["cannot_retrieve"] == []
    assert left["authority_boundary"] == {
        "retrieval_is_context_not_authority": True,
        "can_inform_later_calibration_review": True,
        "can_route_or_sample": False,
        "can_mutate_campaigns": False,
        "can_approve_or_synthesize_strategies": False,
    }
    assert all(row["status"] == "covered" for row in left["coverage"])
    assert all(row["linked_match_count"] >= 1 for row in left["coverage"])
    assert all(
        row["retrieval_role"] == "context_only_not_authority"
        for row in left["coverage"]
    )


def test_missing_retrieval_links_are_explicit(tmp_path: Path) -> None:
    doc = tmp_path / "docs" / "memory.md"
    doc.parent.mkdir(parents=True, exist_ok=True)
    doc.write_text(
        "reason failure blocker action trusted loop context without durable links",
        encoding="utf-8",
    )

    snapshot = retrieval_coverage.build_retrieval_coverage(
        artifact_paths=[Path("docs/memory.md")],
        repo_root=tmp_path,
        generated_at_utc=FROZEN,
    )

    assert snapshot["summary"]["status"] == "not_ready"
    assert snapshot["summary"]["covered_surface_count"] == 0
    assert snapshot["operator_summary"]["can_retrieve"] == []
    for row in snapshot["coverage"]:
        assert row["status"] == "missing_link"
        assert row["retrieved_match_count"] == 1
        assert row["linked_match_count"] == 0
        assert row["missing_retrieval_links"][0].startswith("no_required_link_signals:")


def test_missing_artifacts_fail_closed_with_no_matches(tmp_path: Path) -> None:
    snapshot = retrieval_coverage.build_retrieval_coverage(
        artifact_paths=[Path("logs/missing/latest.json")],
        repo_root=tmp_path,
        generated_at_utc=FROZEN,
    )

    assert snapshot["summary"]["status"] == "not_ready"
    assert snapshot["summary"]["missing_artifacts"] == ["logs/missing/latest.json"]
    assert {row["status"] for row in snapshot["coverage"]} == {"missing_retrieval"}
    assert all(row["missing_retrieval_links"] == ["no_retrieval_matches"] for row in snapshot["coverage"])
    assert snapshot["safety_invariants"]["uses_network"] is False
    assert snapshot["safety_invariants"]["uses_vector_database"] is False
    assert snapshot["safety_invariants"]["uses_hidden_ml"] is False
    assert snapshot["safety_invariants"]["enables_strategy_synthesis"] is False


def test_retrieval_coverage_source_avoids_network_and_subprocess_imports() -> None:
    source = Path(retrieval_coverage.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])

    assert imported.isdisjoint({"requests", "socket", "httpx", "urllib", "subprocess"})
    assert "requests." not in source
    assert "qdrant" not in source.lower()
    assert "chromadb" not in source.lower()


def test_write_outputs_refuses_outside_allowlist(tmp_path: Path) -> None:
    bad = tmp_path / "elsewhere" / "latest.json"
    bad.parent.mkdir(parents=True, exist_ok=True)
    try:
        retrieval_coverage._validate_write_target(bad)
    except ValueError as exc:
        assert "outside allowlist" in str(exc)
    else:
        raise AssertionError("expected outside-allowlist refusal")
