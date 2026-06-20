from __future__ import annotations

from pathlib import Path

from research import qre_incomplete_artifact_remediation_planning as planning


def test_build_incomplete_artifact_remediation_planning_prioritizes_existing_gaps(monkeypatch) -> None:
    monkeypatch.setattr(
        planning.artifact_continuity,
        "build_read_only_artifact_continuity",
        lambda **_: {
            "summary": {"artifact_continuity_ready": False},
            "targets": [
                {
                    "artifact_path": "logs/a/latest.json",
                    "projected_status": "blocked",
                    "materialization_state": "blocked_missing_prerequisites",
                    "reason_codes": ["missing_inputs"],
                    "exact_next_action": "restore_inputs",
                    "source_artifact_refs": ["research/a.json"],
                }
            ],
        },
    )
    monkeypatch.setattr(
        planning.contradiction_staleness,
        "build_contradiction_staleness_intelligence",
        lambda **_: {
            "summary": {"exact_next_action": "reconcile_stale_or_superseded_artifacts"},
            "stale_or_superseded": [
                {
                    "detail": "stale_manifest",
                    "artifact_path": "research/run_manifest_latest.v1.json",
                    "artifact_ref": "logs/qre_contradiction_staleness_intelligence/latest.json",
                }
            ],
        },
    )
    monkeypatch.setattr(
        planning.throughput_bottlenecks,
        "build_campaign_throughput_bottleneck_intelligence",
        lambda **_: {
            "summary": {"campaign_throughput_bottleneck_intelligence_ready": True},
            "bottlenecks": [
                {
                    "bottleneck_code": "queue_registry_divergence",
                    "severity": "critical",
                    "operator_explanation": "queue diverged",
                    "exact_next_action": "reconcile_campaign_queue_from_registry",
                    "evidence_refs": ["research/campaign_queue_latest.v1.json"],
                }
            ],
        },
    )
    monkeypatch.setattr(
        planning.sequential_retrieval,
        "build_research_state_sequential_retrieval",
        lambda **_: {
            "summary": {"exact_next_action": "restore_current_run_artifacts"},
            "blockers": [
                {
                    "blocker_code": "missing_research_state",
                    "severity": "high",
                    "reason": "research_state missing",
                    "evidence_ref": "research/research_state_latest.v1.json",
                }
            ],
        },
    )
    monkeypatch.setattr(
        planning.operational_controls,
        "build_trusted_loop_operational_controls",
        lambda **_: {
            "summary": {
                "trusted_loop_operational_controls_ready": False,
                "status": "failed_resumable",
                "exact_next_safe_action": "resume_from_existing_run_history",
            },
            "current_run": {"status_reason": "research_run_failed:screening"},
        },
    )

    report = planning.build_incomplete_artifact_remediation_planning(repo_root=Path("."))

    assert report["summary"]["remediation_planning_ready"] is True
    assert report["summary"]["remediation_count"] == 5
    assert report["summary"]["critical_count"] == 1
    assert report["summary"]["high_count"] == 3
    assert report["summary"]["exact_next_action"] == "reconcile_campaign_queue_from_registry"
    assert report["remediation_rows"][0]["priority"] == "critical"


def test_write_outputs_stays_in_allowlist(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(
        planning,
        "build_incomplete_artifact_remediation_planning",
        lambda **_: {
            "schema_version": "1.0",
            "report_kind": planning.REPORT_KIND,
            "summary": {"remediation_planning_ready": True, "remediation_count": 0, "exact_next_action": "preserve_current_read_only_artifact_visibility"},
            "remediation_rows": [],
            "source_summaries": {},
            "authority_boundary": {"read_only": True},
            "safety_invariants": {"uses_local_artifacts_only": True},
            "deterministic_hash": "sha256:test",
        },
    )

    paths = planning.write_outputs({}, repo_root=tmp_path)

    assert paths["latest"] == "logs/qre_incomplete_artifact_remediation_planning/latest.json"
    assert paths["operator_summary"] == "logs/qre_incomplete_artifact_remediation_planning/operator_summary.md"
    assert (tmp_path / paths["latest"]).exists()
    assert (tmp_path / paths["operator_summary"]).exists()
