from __future__ import annotations

import json
from pathlib import Path

from packages.qre_diagnostics.research_diagnostics_loop import (
    build_diagnostics_loop_digest,
    read_diagnostics_loop_status,
    write_diagnostics_loop_outputs,
)


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, sort_keys=True, indent=2), encoding="utf-8")


def _write_diagnostic_readiness_evidence(tmp_path: Path) -> None:
    _write_json(
        tmp_path / "logs" / "intelligent_routing_diagnostic_signals" / "latest.json",
        {
            "schema_version": "1.0",
            "generated_at_utc": "2026-05-23T00:00:00Z",
            "report_kind": "intelligent_routing_diagnostic_signals",
            "signals": [
                {"family": "quorum"},
                {"family": "null_model"},
            ],
        },
    )
    _write_json(
        tmp_path / "logs" / "quorum_state" / "latest.json",
        {
            "schema_version": "1.0",
            "generated_at_utc": "2026-05-23T00:00:00Z",
            "summary": {"quorum_ready": True},
        },
    )
    _write_json(
        tmp_path / "logs" / "null_model_evidence" / "latest.json",
        {
            "schema_version": "1.0",
            "generated_at_utc": "2026-05-23T00:00:00Z",
            "summary": {"null_model_ready": True},
        },
    )


def test_diagnostics_loop_links_failure_evidence_to_next_diagnostic(tmp_path: Path) -> None:
    _write_json(
        tmp_path / "research" / "screening_failure_attribution_latest.v1.json",
        {
            "schema_version": "1.0",
            "generated_at_utc": "2026-05-23T00:00:00Z",
            "summary": {
                "observation_count": 2,
                "primary_classification": "data_coverage_gap",
            },
            "classifications": [
                {
                    "classification": "data_coverage_gap",
                    "status": "observed",
                    "count": 2,
                    "raw_reasons": {"coverage_gap": 2},
                    "sources": ["screening_evidence.summary.dominant_failure_reasons"],
                    "action_hint": {
                        "action": "repair_data_coverage_before_research_action",
                        "reason": "Observed artifacts show incomplete market data coverage.",
                        "read_only": True,
                        "mutates_routing": False,
                        "mutates_strategy": False,
                    },
                }
            ],
        },
    )
    _write_json(
        tmp_path / "logs" / "failure_action_mapping_minimal" / "latest.json",
        {
            "schema_version": 1,
            "generated_at_utc": "2026-05-23T00:00:00Z",
            "counts": {"total": 1},
            "items": [
                {
                    "subject_id": "screening:data_coverage_gap",
                    "failure_code": "technical_failure",
                    "severity": "medium",
                    "recommended_action": "review_data_pipeline",
                    "reason_record": {
                        "reason_codes": ["taxonomy_match", "bounded_action"],
                        "reason_text": "Review data pipeline before research action.",
                    },
                }
            ],
        },
    )
    _write_json(
        tmp_path / "logs" / "qre_data_cache_manifest" / "latest.json",
        {"schema_version": "1.0", "summary": {"research_ready": True}},
    )
    _write_json(
        tmp_path / "logs" / "qre_data_source_quality_readiness" / "latest.json",
        {"schema_version": "1.0", "summary": {"research_ready": True}},
    )
    _write_json(
        tmp_path / "logs" / "qre_research_memory" / "latest.json",
        {
            "schema_version": "1.0",
            "summary": {"research_memory_ready": True},
            "entries": [
                {
                    "artifact_id": "research/screening_failure_attribution_latest.v1.json",
                    "record_kind": "screening_failure_attribution",
                    "ontology_tags": ["failure", "data_coverage_gap"],
                    "content_hash": "sha256:abc",
                    "text_preview": "data_coverage_gap",
                }
            ],
        },
    )
    _write_diagnostic_readiness_evidence(tmp_path)

    digest = build_diagnostics_loop_digest(
        repo_root=tmp_path,
        generated_at_utc="2026-05-23T00:00:00Z",
    )

    assert digest["report_kind"] == "qre_research_diagnostics_loop"
    assert digest["summary"]["status"] == "ready"
    assert digest["summary"]["fail_closed"] is False
    assert digest["summary"]["diagnostic_readiness_ready"] is True
    assert digest["summary"]["report_readiness_blockers"] == []
    assert digest["summary"]["primary_failure_classification"] == "data_coverage_gap"
    assert digest["summary"]["recommended_operator_step"] == "inspect_next_diagnostic"
    assert digest["diagnostic_chain"][0]["failure_code"] == "technical_failure"
    assert digest["diagnostic_chain"][0]["next_diagnostic"] == "inspect_data_pipeline_readiness"
    assert digest["diagnostic_chain"][0]["safety"]["mutates_campaign_queue"] is False
    assert digest["diagnostic_chain"][0]["research_memory_context"]["match_count"] == 1
    assert digest["safety_invariants"]["mutates_routing"] is False
    assert digest["safety_invariants"]["activates_addendum1_runtime"] is False
    assert digest["safety_invariants"]["diagnostics_authorize_synthesis"] is False
    assert digest["safety_invariants"]["diagnostics_control_routing"] is False
    assert digest["safety_invariants"]["diagnostics_control_sampling"] is False


def test_diagnostics_loop_missing_sources_fail_closed(tmp_path: Path) -> None:
    digest = build_diagnostics_loop_digest(
        repo_root=tmp_path,
        generated_at_utc="2026-05-23T00:00:00Z",
    )

    assert digest["summary"]["status"] == "not_ready"
    assert digest["summary"]["fail_closed"] is True
    assert digest["summary"]["recommended_operator_step"] == "stop_collect_upstream_sidecars"
    assert digest["summary"]["missing_source_count"] == 5
    assert digest["diagnostic_chain"] == []
    assert "missing_failure_diagnostic_chain" in digest["summary"]["blocking_reasons"]
    assert digest["summary"]["diagnostic_readiness_ready"] is False
    assert digest["summary"]["readiness_blocker_category_counts"] == {
        "diagnostic": 2,
        "null_model": 1,
        "quorum": 1,
    }
    assert digest["summary"]["readiness_blocker_reason_counts"] == {
        "diagnostic_failure_chain_missing": 1,
        "diagnostic_signal_evidence_missing": 1,
        "null_model_evidence_missing": 1,
        "quorum_evidence_missing": 1,
    }
    assert all(
        blocker["fail_closed"] is True
        for blocker in digest["summary"]["report_readiness_blockers"]
    )


def test_diagnostics_loop_fails_closed_without_quorum_and_null_model_evidence(
    tmp_path: Path,
) -> None:
    _write_json(
        tmp_path / "research" / "screening_failure_attribution_latest.v1.json",
        {
            "schema_version": "1.0",
            "summary": {"observation_count": 1},
            "classifications": [
                {
                    "classification": "policy_gap",
                    "count": 1,
                    "sources": ["screening"],
                    "action_hint": {"action": "inspect_policy_trace_evidence"},
                }
            ],
        },
    )
    _write_json(
        tmp_path / "logs" / "failure_action_mapping_minimal" / "latest.json",
        {
            "counts": {"total": 1},
            "items": [
                {
                    "subject_id": "screening:policy_gap",
                    "recommended_action": "inspect_policy_trace_evidence",
                }
            ],
        },
    )
    _write_json(
        tmp_path / "logs" / "qre_data_cache_manifest" / "latest.json",
        {"summary": {"research_ready": True}},
    )
    _write_json(
        tmp_path / "logs" / "qre_data_source_quality_readiness" / "latest.json",
        {"summary": {"research_ready": True}},
    )
    _write_json(
        tmp_path / "logs" / "qre_research_memory" / "latest.json",
        {"summary": {"research_memory_ready": True}},
    )
    _write_json(
        tmp_path / "logs" / "intelligent_routing_diagnostic_signals" / "latest.json",
        {"signals": [{"family": "quorum"}, {"family": "null_model"}]},
    )

    digest = build_diagnostics_loop_digest(
        repo_root=tmp_path,
        generated_at_utc="2026-05-23T00:00:00Z",
    )

    assert digest["summary"]["status"] == "not_ready"
    assert digest["summary"]["fail_closed"] is True
    assert digest["summary"]["diagnostic_readiness_ready"] is False
    assert digest["summary"]["recommended_operator_step"] == (
        "stop_collect_diagnostic_readiness_evidence"
    )
    assert digest["summary"]["readiness_blocker_category_counts"] == {
        "null_model": 1,
        "quorum": 1,
    }
    assert digest["summary"]["readiness_blocker_reason_counts"] == {
        "null_model_evidence_missing": 1,
        "quorum_evidence_missing": 1,
    }
    assert "diagnostic/quorum/null-model readiness blockers" in digest["summary"][
        "operator_summary"
    ]
    assert digest["diagnostic_readiness_evidence"]["quorum_evidence"]["fails_closed"] is True
    assert (
        digest["diagnostic_readiness_evidence"]["null_model_evidence"]["fails_closed"]
        is True
    )


def test_diagnostics_loop_blocks_diagnostic_taxonomy_without_quorum_or_null_model(
    tmp_path: Path,
) -> None:
    _write_json(
        tmp_path / "logs" / "intelligent_routing_diagnostic_signals" / "latest.json",
        {"signals": [{"family": "entropy"}]},
    )
    _write_json(
        tmp_path / "logs" / "quorum_state" / "latest.json",
        {"summary": {"quorum_ready": True}},
    )
    _write_json(
        tmp_path / "logs" / "null_model_evidence" / "latest.json",
        {"summary": {"null_model_ready": True}},
    )

    digest = build_diagnostics_loop_digest(
        repo_root=tmp_path,
        generated_at_utc="2026-05-23T00:00:00Z",
    )

    assert digest["summary"]["readiness_blocker_reason_counts"][
        "diagnostic_signal_evidence_not_ready"
    ] == 1
    assert digest["diagnostic_readiness_evidence"]["diagnostic_signal_evidence"][
        "status"
    ] == "not_ready"
    assert digest["reference_taxonomy"]["runtime_activation"] is False
    assert "quorum" in digest["reference_taxonomy"]["terms"]
    assert "null_model" in digest["reference_taxonomy"]["terms"]


def test_diagnostics_loop_surfaces_data_source_identity_blockers(
    tmp_path: Path,
) -> None:
    _write_json(
        tmp_path / "logs" / "qre_data_source_quality_readiness" / "latest.json",
        {
            "schema_version": "1.0",
            "generated_at_utc": "2026-05-23T00:00:00Z",
            "summary": {
                "research_ready": False,
                "operator_summary": (
                    "Source quality is not research-ready; inspect "
                    "data/source/identity readiness blockers."
                ),
                "readiness_blocker_category_counts": {
                    "data": 2,
                    "identity": 1,
                    "source": 1,
                },
                "readiness_blocker_reason_counts": {
                    "data_row_count_not_positive": 1,
                    "data_timestamp_range_missing": 1,
                    "identity_source_unknown": 1,
                    "source_content_hash_missing": 1,
                },
                "report_readiness_blockers": [
                    {
                        "category": "source",
                        "reason": "source_manifest_research_not_ready",
                        "fail_closed": True,
                    }
                ],
            },
        },
    )

    digest = build_diagnostics_loop_digest(
        repo_root=tmp_path,
        generated_at_utc="2026-05-23T00:00:00Z",
    )

    source_quality = digest["sources"]["source_quality"]
    assert source_quality["status"] == "not_ready"
    assert source_quality["fails_closed"] is True
    assert source_quality["readiness_blocker_category_counts"] == {
        "data": 2,
        "identity": 1,
        "source": 1,
    }
    assert source_quality["readiness_blocker_reason_counts"][
        "identity_source_unknown"
    ] == 1
    assert source_quality["report_readiness_blockers"][0]["fail_closed"] is True
    assert "data/source/identity readiness blockers" in source_quality[
        "operator_summary"
    ]


def test_diagnostics_loop_invalid_source_count_is_separate_from_missing(
    tmp_path: Path,
) -> None:
    path = tmp_path / "research" / "screening_failure_attribution_latest.v1.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("{not json", encoding="utf-8")

    digest = build_diagnostics_loop_digest(
        repo_root=tmp_path,
        generated_at_utc="2026-05-23T00:00:00Z",
    )

    assert digest["summary"]["status"] == "not_ready"
    assert digest["summary"]["available_source_count"] == 0
    assert digest["summary"]["missing_source_count"] == 4
    assert digest["summary"]["invalid_source_count"] == 1
    assert digest["summary"]["invalid_sources"] == ["screening_failure_attribution"]


def test_diagnostics_loop_status_reader_fails_closed_when_missing(tmp_path: Path) -> None:
    status = read_diagnostics_loop_status(repo_root=tmp_path)

    assert status == {
        "status": "missing_research_diagnostics_loop",
        "diagnostics_loop_ready": False,
        "path": "logs/qre_research_diagnostics_loop/latest.json",
        "fails_closed": True,
    }


def test_diagnostics_loop_writer_is_bounded_and_status_reads_ready(tmp_path: Path) -> None:
    digest = {
        "schema_version": "1.0",
        "report_kind": "qre_research_diagnostics_loop",
        "generated_at_utc": "2026-05-23T00:00:00Z",
        "summary": {"status": "ready"},
    }

    paths = write_diagnostics_loop_outputs(digest, repo_root=tmp_path)
    status = read_diagnostics_loop_status(repo_root=tmp_path)

    assert paths["latest"] == "logs/qre_research_diagnostics_loop/latest.json"
    assert paths["history"] == "logs/qre_research_diagnostics_loop/history.jsonl"
    assert status["status"] == "ready"
    assert status["diagnostics_loop_ready"] is True
