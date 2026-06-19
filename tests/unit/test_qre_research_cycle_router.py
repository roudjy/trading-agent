from __future__ import annotations

import ast
import json
from pathlib import Path

from research import qre_hypothesis_disposition_memory as disposition_memory
from research import qre_research_cycle_router as router


def _write_campaign_report(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": "1.0",
        "report_kind": "qre_preregistered_multiwindow_evidence_run",
        "generated_at_utc": "2026-06-19T14:15:30Z",
        "sampling_plan_id": "qsp_f343a1e05e1abfc2",
        "campaign_id": "qmwv_817024aec3967516",
        "campaign_outcome": "all_windows_non_positive_trade_count",
        "accepted_lineage_count": 4,
        "accepted_oos_count": 0,
        "rejection_reasons": ["non_positive_oos_trade_count", "accepted_oos_count_mismatch"],
        "window_results": [
            {
                "regime_label": "trend",
                "symbol_results": [
                    {"lineage_records": [{"verifier_ref": "logs/qre_preregistered_multiwindow_evidence_run/latest.json#lineage:one"}], "oos_records": []},
                    {"lineage_records": [{"verifier_ref": "logs/qre_preregistered_multiwindow_evidence_run/latest.json#lineage:two"}], "oos_records": []},
                ],
            },
            {
                "regime_label": "high_volatility",
                "symbol_results": [
                    {"lineage_records": [{"verifier_ref": "logs/qre_preregistered_multiwindow_evidence_run/latest.json#lineage:three"}], "oos_records": []},
                    {"lineage_records": [{"verifier_ref": "logs/qre_preregistered_multiwindow_evidence_run/latest.json#lineage:four"}], "oos_records": []},
                ],
            },
        ],
    }
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _write_closure_report(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": "1.0",
        "report_kind": "qre_multiwindow_evidence_closure",
        "generated_at_utc": "2026-06-19T14:15:45Z",
        "closure_status": "all_windows_no_oos_trades",
        "campaign_ref": "qmwv_817024aec3967516",
        "sampling_plan_ref": "qsp_f343a1e05e1abfc2",
        "accepted_lineage_count": 4,
        "accepted_oos_count": 0,
        "evidence_complete_count": 0,
        "hypothesis_disposition": "fail_closed_rejected",
        "blockers_remaining": ["no_oos_evidence"],
        "recommended_next_action": "reject_hypothesis",
        "reason_records": [
            {
                "record_id": "rr_lineage_present",
                "record_family": "multiwindow_evidence_closure",
                "reason_codes": ["accepted_lineage_present"],
                "evidence_refs": ["qmwv_817024aec3967516"],
                "message": "Structured lineage exists for the rejected scope.",
            },
            {
                "record_id": "rr_no_oos",
                "record_family": "multiwindow_evidence_closure",
                "reason_codes": ["all_windows_non_positive_trade_count"],
                "evidence_refs": ["qmwv_817024aec3967516"],
                "message": "Every preregistered window ended without acceptable OOS support.",
            },
        ],
    }
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _write_research_memory(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": "1.0",
        "report_kind": "qre_research_memory_v1",
        "summary": {"status": "ready", "research_memory_ready": True},
        "entries": [
            {
                "artifact_id": "logs/qre_hypothesis_disposition_memory/latest.json",
                "artifact_path": "logs/qre_hypothesis_disposition_memory/latest.json",
                "record_kind": "artifact",
                "title": "Rejected pullback hypothesis",
                "ontology_tags": ["hypothesis", "failure"],
                "keywords": ["trend_pullback_behavior_v1", "non_positive_oos_trade_count", "rejected"],
                "text_preview": "trend_pullback_behavior_v1 rejected because non_positive_oos_trade_count with no_oos_evidence",
            }
        ],
    }
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def _write_disposition_memory(tmp_path: Path) -> None:
    campaign_path = tmp_path / "logs" / "qre_preregistered_multiwindow_evidence_run" / "latest.json"
    closure_path = tmp_path / "logs" / "qre_multiwindow_evidence_closure" / "latest.json"
    _write_campaign_report(campaign_path)
    _write_closure_report(closure_path)
    report = disposition_memory.build_hypothesis_disposition_memory(
        repo_root=tmp_path,
        generated_at_utc="2026-06-19T15:00:00Z",
    )
    disposition_memory.write_outputs(report, repo_root=tmp_path)


def test_router_suppresses_exact_retry_and_surfaces_novel_directions(tmp_path: Path) -> None:
    _write_disposition_memory(tmp_path)
    _write_research_memory(tmp_path / "logs" / "qre_research_memory" / "latest.json")

    left = router.build_research_cycle_router(
        repo_root=tmp_path,
        generated_at_utc="2026-06-19T16:00:00Z",
    )
    right = router.build_research_cycle_router(
        repo_root=tmp_path,
        generated_at_utc="2026-06-19T16:00:00Z",
    )

    assert left == right
    assert left["status"] == "ready"
    assert left["summary"]["router_ready"] is True
    assert left["source_disposition_ref"].startswith("logs/qre_hypothesis_disposition_memory/latest.json#record::qhm_")
    assert left["suppressed_scopes"][0]["suppression_reason"] == "same_failed_scope_suppressed"
    assert left["eligible_directions"]
    assert any(
        row["direction_type"] == "different_behavior_family"
        for row in left["eligible_directions"]
    )
    assert any(
        row["direction_id"] == "hypothesis_retirement"
        for row in left["eligible_directions"]
    )
    assert any(
        row["direction_id"] == "timeframe_shift"
        for row in left["ineligible_directions"]
    )
    assert left["operator_review_required"] is True
    assert left["authority_flags"]["safe_to_execute"] is False
    assert left["recommended_research_action"] in {
        "propose_materially_new_behavior_family",
        "plan_evidence_breadth_expansion",
        "retire_rejected_exact_scope",
    }
    assert left["deterministic_hash"].startswith("sha256:")


def test_router_write_outputs_and_status_round_trip(tmp_path: Path) -> None:
    _write_disposition_memory(tmp_path)
    _write_research_memory(tmp_path / "logs" / "qre_research_memory" / "latest.json")

    report = router.build_research_cycle_router(
        repo_root=tmp_path,
        generated_at_utc="2026-06-19T16:00:00Z",
    )
    paths = router.write_outputs(report, repo_root=tmp_path)

    assert paths == {
        "latest": "logs/qre_research_cycle_router/latest.json",
        "operator_summary": "logs/qre_research_cycle_router/operator_summary.md",
    }
    assert router.read_research_cycle_router_status(
        output_dir=Path("logs/qre_research_cycle_router"),
        repo_root=tmp_path,
    ) == {
        "status": "ready",
        "router_ready": True,
        "path": "logs/qre_research_cycle_router/latest.json",
        "fails_closed": False,
        "schema_version": "1.0",
    }


def test_router_fails_closed_without_disposition_memory(tmp_path: Path) -> None:
    report = router.build_research_cycle_router(
        repo_root=tmp_path,
        generated_at_utc="2026-06-19T16:00:00Z",
    )

    assert report["status"] == "blocked_missing_disposition_memory"
    assert report["summary"]["router_ready"] is False
    assert report["summary"]["recommended_research_action"] == "route_to_operator_review"


def test_router_source_is_read_only() -> None:
    source = Path(router.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])

    assert imported.isdisjoint({"requests", "socket", "httpx", "urllib", "subprocess"})
    assert "requests." not in source
