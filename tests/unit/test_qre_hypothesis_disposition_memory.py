from __future__ import annotations

import ast
import json
from pathlib import Path

from research import qre_hypothesis_disposition_memory as disposition_memory


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
                    {
                        "lineage_records": [
                            {
                                "verifier_ref": "logs/qre_preregistered_multiwindow_evidence_run/latest.json#lineage:aapl",
                            }
                        ],
                        "oos_records": [],
                    },
                    {
                        "lineage_records": [
                            {
                                "verifier_ref": "logs/qre_preregistered_multiwindow_evidence_run/latest.json#lineage:nvda",
                            }
                        ],
                        "oos_records": [],
                    },
                ],
            },
            {
                "regime_label": "high_volatility",
                "symbol_results": [
                    {
                        "lineage_records": [
                            {
                                "verifier_ref": "logs/qre_preregistered_multiwindow_evidence_run/latest.json#lineage:aapl_2",
                            }
                        ],
                        "oos_records": [],
                    },
                    {
                        "lineage_records": [
                            {
                                "verifier_ref": "logs/qre_preregistered_multiwindow_evidence_run/latest.json#lineage:nvda_2",
                            }
                        ],
                        "oos_records": [],
                    },
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
        "closure_status": "all_windows_no_oos_trades",
        "campaign_ref": "qmwv_817024aec3967516",
        "sampling_plan_ref": "qsp_f343a1e05e1abfc2",
        "accepted_lineage_count": 4,
        "accepted_oos_count": 0,
        "evidence_complete_count": 0,
        "hypothesis_disposition": "fail_closed_rejected",
        "blockers_cleared": ["campaign_lineage_missing"],
        "blockers_remaining": ["no_oos_evidence"],
        "recommended_next_action": "reject_hypothesis",
        "reason_records": [
            {
                "record_id": "rr_multiwindow_lineage_present",
                "record_family": "multiwindow_evidence_closure",
                "reason_codes": ["accepted_lineage_present"],
                "evidence_refs": ["qmwv_817024aec3967516"],
                "message": "Verifier-acceptable structured lineage exists for the preregistered campaign scope.",
            },
            {
                "record_id": "rr_multiwindow_all_zero",
                "record_family": "multiwindow_evidence_closure",
                "reason_codes": ["all_windows_non_positive_trade_count"],
                "evidence_refs": ["qmwv_817024aec3967516"],
                "message": "Every preregistered window completed with non-positive OOS trade count.",
            },
        ],
    }
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def test_build_hypothesis_disposition_memory_persists_exact_scope_and_fail_closed_rejection(
    tmp_path: Path,
) -> None:
    campaign_path = tmp_path / "logs" / "qre_preregistered_multiwindow_evidence_run" / "latest.json"
    closure_path = tmp_path / "logs" / "qre_multiwindow_evidence_closure" / "latest.json"
    _write_campaign_report(campaign_path)
    _write_closure_report(closure_path)

    left = disposition_memory.build_hypothesis_disposition_memory(
        repo_root=tmp_path,
        generated_at_utc="2026-06-19T14:45:00Z",
    )
    right = disposition_memory.build_hypothesis_disposition_memory(
        repo_root=tmp_path,
        generated_at_utc="2026-06-19T14:45:00Z",
    )

    assert left == right
    assert left["status"] == "ready"
    assert left["summary"]["hypothesis_disposition_memory_ready"] is True
    assert left["summary"]["entry_count"] == 1
    assert left["record"]["hypothesis_id"] == "trend_pullback_behavior_v1"
    assert left["record"]["behavior_id"] == "pullback_continuation"
    assert left["record"]["hypothesis_disposition"] == "not_supported"
    assert left["record"]["accepted_lineage_refs"] == [
        "logs/qre_preregistered_multiwindow_evidence_run/latest.json#lineage:aapl",
        "logs/qre_preregistered_multiwindow_evidence_run/latest.json#lineage:nvda",
        "logs/qre_preregistered_multiwindow_evidence_run/latest.json#lineage:aapl_2",
        "logs/qre_preregistered_multiwindow_evidence_run/latest.json#lineage:nvda_2",
    ]
    assert left["record"]["accepted_oos_refs"] == []
    assert left["record"]["window_refs"]
    assert left["record"]["regime_refs"] == ["trend", "high_volatility"]
    assert "non_positive_oos_trade_count" in left["record"]["failure_classes"]
    assert "all_windows_non_positive_trade_count" in left["record"]["failure_classes"]
    assert left["record"]["authority"] == {
        "non_authoritative": True,
        "evidence_authority": "context_only",
        "can_authorize_execution": False,
        "can_clear_evidence_blockers": False,
        "can_promote_candidate": False,
    }
    assert left["safety_invariants"] == {
        "read_only": True,
        "uses_network": False,
        "uses_subprocess": False,
        "paper_shadow_live_forbidden": True,
        "broker_risk_execution_forbidden": True,
        "can_authorize_execution": False,
        "can_clear_evidence_blockers": False,
        "can_promote_candidate": False,
    }
    assert left["record"]["memory_record_id"].startswith("qhm_")
    assert left["record"]["hash"].startswith("sha256:")


def test_same_failed_scope_is_suppressed_but_materially_new_scope_is_eligible(
    tmp_path: Path,
) -> None:
    campaign_path = tmp_path / "logs" / "qre_preregistered_multiwindow_evidence_run" / "latest.json"
    closure_path = tmp_path / "logs" / "qre_multiwindow_evidence_closure" / "latest.json"
    _write_campaign_report(campaign_path)
    _write_closure_report(closure_path)

    memory = disposition_memory.build_hypothesis_disposition_memory(
        repo_root=tmp_path,
        generated_at_utc="2026-06-19T14:45:00Z",
    )

    same_scope = dict(memory["record"]["disposition_scope"])
    same_result = disposition_memory.evaluate_revisit_eligibility(memory, proposed_scope=same_scope)
    new_result = disposition_memory.evaluate_revisit_eligibility(
        memory,
        proposed_scope={
            **same_scope,
            "universe_or_basket_scope": "Europe liquid equities preregistered basket",
            "operator_approved_new_research_rationale": "new universe and regime rationale",
        },
    )

    assert same_result == {
        "eligible": False,
        "reason": "same_failed_scope_suppressed",
        "can_reuse_scope": False,
        "can_revisit": False,
    }
    assert new_result["eligible"] is True
    assert new_result["reason"] == "materially_new_research_scope"


def test_write_outputs_and_status_round_trip(tmp_path: Path) -> None:
    campaign_path = tmp_path / "logs" / "qre_preregistered_multiwindow_evidence_run" / "latest.json"
    closure_path = tmp_path / "logs" / "qre_multiwindow_evidence_closure" / "latest.json"
    _write_campaign_report(campaign_path)
    _write_closure_report(closure_path)

    report = disposition_memory.build_hypothesis_disposition_memory(
        repo_root=tmp_path,
        generated_at_utc="2026-06-19T14:45:00Z",
    )
    paths = disposition_memory.write_outputs(report, repo_root=tmp_path)

    assert paths == {
        "latest": "logs/qre_hypothesis_disposition_memory/latest.json",
        "operator_summary": "logs/qre_hypothesis_disposition_memory/operator_summary.md",
    }
    assert disposition_memory.read_hypothesis_disposition_memory_status(
        output_dir=Path("logs/qre_hypothesis_disposition_memory"),
        repo_root=tmp_path,
    ) == {
        "status": "ready",
        "hypothesis_disposition_memory_ready": True,
        "path": "logs/qre_hypothesis_disposition_memory/latest.json",
        "fails_closed": False,
        "schema_version": "1.0",
    }


def test_hypothesis_disposition_memory_source_is_read_only() -> None:
    source = Path(disposition_memory.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module.split(".")[0])

    assert imported.isdisjoint({"requests", "socket", "httpx", "urllib", "subprocess"})
    assert "requests." not in source
