from __future__ import annotations

import json
from pathlib import Path

from reporting import qre_action_usefulness_tracking as report


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def test_collect_snapshot_builds_baseline_when_no_prior_history(tmp_path: Path) -> None:
    _write_json(
        tmp_path / "logs" / "qre_actionable_failure_taxonomy" / "latest.json",
        {
            "taxonomy_rows": [
                {
                    "taxonomy_id": "basket:ready_for_readonly_research",
                    "source_surface": "qre_failure_action_from_basket",
                    "failure_class": "ready_for_readonly_research",
                    "supported": True,
                    "evidence_status": "supported",
                    "recommended_action": "eligible_for_readonly_routing",
                    "operator_explanation": "Ready for read-only routing.",
                    "evidence_refs": ["logs/qre_actionable_failure_taxonomy/latest.json"],
                }
            ]
        },
    )
    _write_json(
        tmp_path / "logs" / "qre_basket_next_action_queue" / "latest.json",
        {
            "rows": [
                {
                    "candidate_id": "seed::trend::AAPL",
                    "blocker_code": "campaign_lineage_missing",
                    "exact_next_action": "materialize_campaign_lineage",
                    "operator_explanation": "Recover campaign lineage.",
                    "evidence_refs": ["logs/qre_basket_next_action_queue/latest.json#AAPL"],
                }
            ]
        },
    )
    _write_json(
        tmp_path / "logs" / "qre_routing_sampling_readiness" / "latest.json",
        {"summary": {"routing_ready_count": 2, "sampling_ready_count": 1}},
    )
    _write_json(
        tmp_path / "logs" / "qre_source_usefulness_ledger" / "latest.json",
        {"summary": {"false_positive_proxy_rows": 0}},
    )

    snapshot = report.collect_snapshot(
        repo_root=tmp_path,
        frozen_utc="2026-06-26T03:00:00Z",
    )
    rows = {row["recommended_action"]: row for row in snapshot["action_rows"]}

    routing = rows["eligible_for_readonly_routing"]
    assert routing["current_subject_count"] == 1
    assert routing["execution_evidence_state"] == "baseline_no_prior_snapshot"
    assert routing["useful_outcome_state"] == "downstream_readiness_visible"

    lineage = rows["materialize_campaign_lineage"]
    assert lineage["current_subject_count"] == 1
    assert lineage["execution_evidence_state"] == "baseline_no_prior_snapshot"
    assert lineage["blocker_resolution_state"] == "insufficient_evidence"

    assert snapshot["summary"]["prior_snapshot_available"] is False
    assert snapshot["summary"]["action_count"] == 2


def test_collect_snapshot_compares_against_prior_history(tmp_path: Path) -> None:
    _write_json(
        tmp_path / "logs" / "qre_actionable_failure_taxonomy" / "latest.json",
        {"taxonomy_rows": []},
    )
    _write_json(
        tmp_path / "logs" / "qre_basket_next_action_queue" / "latest.json",
        {
            "rows": [
                {
                    "candidate_id": "seed::trend::AAPL",
                    "blocker_code": "campaign_lineage_missing",
                    "exact_next_action": "materialize_campaign_lineage",
                    "operator_explanation": "Recover campaign lineage.",
                    "evidence_refs": [],
                },
                {
                    "candidate_id": "seed::trend::NVDA",
                    "blocker_code": "campaign_lineage_missing",
                    "exact_next_action": "materialize_campaign_lineage",
                    "operator_explanation": "Recover campaign lineage.",
                    "evidence_refs": [],
                },
            ]
        },
    )
    _write_json(
        tmp_path / "logs" / "qre_routing_sampling_readiness" / "latest.json",
        {"summary": {"routing_ready_count": 0, "sampling_ready_count": 0}},
    )
    _write_json(
        tmp_path / "logs" / "qre_source_usefulness_ledger" / "latest.json",
        {"summary": {"false_positive_proxy_rows": 1}},
    )
    history_path = tmp_path / "logs" / "qre_action_usefulness_tracking" / "history.jsonl"
    history_path.parent.mkdir(parents=True, exist_ok=True)
    history_path.write_text(
        json.dumps(
            {
                "action_rows": [
                    {
                        "recommended_action": "materialize_campaign_lineage",
                        "current_subject_keys": [
                            "queue::seed::trend::AAPL::campaign_lineage_missing",
                            "queue::seed::trend::MSFT::campaign_lineage_missing",
                        ],
                    }
                ]
            }
        )
        + "\n",
        encoding="utf-8",
    )

    snapshot = report.collect_snapshot(
        repo_root=tmp_path,
        frozen_utc="2026-06-26T03:05:00Z",
    )
    row = next(
        row
        for row in snapshot["action_rows"]
        if row["recommended_action"] == "materialize_campaign_lineage"
    )

    assert row["prior_subject_count"] == 2
    assert row["repeated_subject_count"] == 1
    assert row["resolved_subject_count"] == 1
    assert row["new_subject_count"] == 1
    assert row["execution_evidence_state"] == "mixed_effect_visible_and_unresolved"
    assert row["blocker_resolution_state"] == "partially_resolved"
    assert row["repeated_failure_state"] == "same_failure_still_present"
    assert row["compute_saving_state"] == "possible_compute_saving_not_proven"
    assert row["false_positive_state"] == "global_false_positive_proxy_present"


def test_write_outputs_writes_json_history_and_doc(tmp_path: Path) -> None:
    _write_json(tmp_path / "logs" / "qre_actionable_failure_taxonomy" / "latest.json", {"taxonomy_rows": []})
    _write_json(tmp_path / "logs" / "qre_basket_next_action_queue" / "latest.json", {"rows": []})
    _write_json(tmp_path / "logs" / "qre_routing_sampling_readiness" / "latest.json", {"summary": {}})
    _write_json(tmp_path / "logs" / "qre_source_usefulness_ledger" / "latest.json", {"summary": {}})

    snapshot = report.collect_snapshot(
        repo_root=tmp_path,
        frozen_utc="2026-06-26T03:10:00Z",
    )
    output_dir = tmp_path / "logs" / "qre_action_usefulness_tracking"
    doc_path = tmp_path / "docs" / "governance" / "qre_action_usefulness_tracking.md"
    paths = report.write_outputs(
        snapshot,
        output_dir=output_dir,
        doc_path=doc_path,
        repo_root=tmp_path,
    )

    assert paths["latest"] == "logs/qre_action_usefulness_tracking/latest.json"
    assert paths["history"] == "logs/qre_action_usefulness_tracking/history.jsonl"
    assert paths["doc"] == "docs/governance/qre_action_usefulness_tracking.md"
    assert doc_path.read_text(encoding="utf-8").startswith("# QRE Action Usefulness Tracking")
    history_lines = (output_dir / "history.jsonl").read_text(encoding="utf-8").splitlines()
    assert len(history_lines) == 1
