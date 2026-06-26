from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from reporting import qre_actionable_failure_taxonomy as report


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")


def test_collect_snapshot_combines_screening_basket_and_explicit_minimal_gap(
    tmp_path: Path,
    monkeypatch,
) -> None:
    _write_json(
        tmp_path / "research" / "screening_failure_attribution_latest.v1.json",
        {
            "classifications": [
                {
                    "classification": "insufficient_trades",
                    "count": 3,
                    "status": "observed",
                    "action_hint": {
                        "action": "increase_timeframe_or_extend_sample_window",
                        "reason": "Observed candidates do not carry enough trades.",
                    },
                },
                {
                    "classification": "unknown_screening_failure",
                    "count": 1,
                    "status": "observed",
                    "action_hint": {
                        "action": "hold_no_action_until_evidence_improves",
                        "reason": "Existing evidence is insufficient for a deterministic failure class.",
                    },
                },
            ]
        },
    )
    _write_json(
        tmp_path / "logs" / "failure_action_mapping_minimal" / "latest.json",
        {
            "counts": {"total": 0},
            "items": [],
        },
    )

    basket_report = {
        "rows": [
            {
                "blocker_code": "source_identity_blocked",
                "recommended_action": "require_identity_resolution",
                "actionability": {
                    "status": "actionable",
                    "operator_explanation": "Resolve symbol identity before research action.",
                },
                "reason_record_refs": {
                    "reason_codes": ["source_identity_blocked"],
                    "record_ids": ["qrr_1"],
                    "evidence_refs": ["logs/qre_reason_records/latest.jsonl"],
                },
            },
            {
                "blocker_code": "source_identity_blocked",
                "recommended_action": "require_identity_resolution",
                "actionability": {
                    "status": "actionable",
                    "operator_explanation": "Resolve symbol identity before research action.",
                },
                "reason_record_refs": {
                    "reason_codes": ["source_identity_blocked"],
                    "record_ids": ["qrr_2"],
                    "evidence_refs": ["logs/qre_reason_records/latest.jsonl"],
                },
            },
            {
                "blocker_code": "supporting_artifacts_missing",
                "recommended_action": "keep_blocked",
                "actionability": {
                    "status": "non_actionable",
                    "operator_explanation": "Supporting artifacts are missing, so the basket stays blocked.",
                },
                "reason_record_refs": {
                    "reason_codes": ["fail_closed"],
                    "record_ids": ["qrr_3"],
                    "evidence_refs": ["logs/qre_reason_records/latest.jsonl"],
                },
            },
        ]
    }

    monkeypatch.setattr(
        report,
        "_research_module",
        lambda name: SimpleNamespace(build_failure_action_from_basket=lambda **_: basket_report),
    )

    snapshot = report.collect_snapshot(
        repo_root=tmp_path,
        frozen_utc="2026-06-26T02:00:00Z",
    )
    rows = {row["taxonomy_id"]: row for row in snapshot["taxonomy_rows"]}

    screening = rows["screening:insufficient_trades"]
    assert screening["supported"] is True
    assert screening["recommended_action"] == "increase_timeframe_or_extend_sample_window"
    assert screening["exact_one_next_action"] is True

    basket = rows["basket:source_identity_blocked"]
    assert basket["observed_count"] == 2
    assert basket["supported"] is True
    assert basket["recommended_action"] == "require_identity_resolution"

    fail_closed = rows["basket:supporting_artifacts_missing"]
    assert fail_closed["supported"] is False
    assert fail_closed["recommended_action"] == "keep_blocked"

    minimal = rows["minimal:no_failure_inputs"]
    assert minimal["supported"] is False
    assert minimal["evidence_status"] == "insufficient_evidence"
    assert minimal["recommended_action"] == "collect_more_evidence"

    assert snapshot["summary"]["supported_failure_class_count"] == 2
    assert snapshot["summary"]["all_supported_classes_have_exactly_one_next_action"] is True


def test_collect_snapshot_fails_closed_when_same_basket_blocker_maps_to_multiple_actions(
    tmp_path: Path,
    monkeypatch,
) -> None:
    _write_json(tmp_path / "research" / "screening_failure_attribution_latest.v1.json", {})
    _write_json(tmp_path / "logs" / "failure_action_mapping_minimal" / "latest.json", {"items": []})

    basket_report = {
        "rows": [
            {
                "blocker_code": "campaign_lineage_missing",
                "recommended_action": "repair_scope_matching",
                "actionability": {
                    "status": "actionable",
                    "operator_explanation": "Repair lineage.",
                },
                "reason_record_refs": {"reason_codes": ["campaign_lineage_missing"]},
            },
            {
                "blocker_code": "campaign_lineage_missing",
                "recommended_action": "route_to_manual_review",
                "actionability": {
                    "status": "actionable",
                    "operator_explanation": "Manual review required.",
                },
                "reason_record_refs": {"reason_codes": ["campaign_lineage_missing"]},
            },
        ]
    }

    monkeypatch.setattr(
        report,
        "_research_module",
        lambda name: SimpleNamespace(build_failure_action_from_basket=lambda **_: basket_report),
    )

    snapshot = report.collect_snapshot(repo_root=tmp_path, frozen_utc="2026-06-26T02:00:00Z")
    row = next(row for row in snapshot["taxonomy_rows"] if row["taxonomy_id"] == "basket:campaign_lineage_missing")

    assert row["supported"] is False
    assert row["exact_one_next_action"] is False
    assert row["recommended_action"] == "keep_blocked"
    assert row["evidence_status"] == "inconsistent_mapping_fail_closed"
    assert "inconsistent_mapping_fail_closed" in row["reason_codes"]


def test_write_outputs_writes_json_and_doc(tmp_path: Path, monkeypatch) -> None:
    _write_json(tmp_path / "research" / "screening_failure_attribution_latest.v1.json", {})
    _write_json(tmp_path / "logs" / "failure_action_mapping_minimal" / "latest.json", {"items": []})
    monkeypatch.setattr(
        report,
        "_research_module",
        lambda name: SimpleNamespace(build_failure_action_from_basket=lambda **_: {"rows": []}),
    )

    snapshot = report.collect_snapshot(repo_root=tmp_path, frozen_utc="2026-06-26T02:00:00Z")
    output_dir = tmp_path / "logs" / "qre_actionable_failure_taxonomy"
    doc_path = tmp_path / "docs" / "governance" / "qre_actionable_failure_taxonomy.md"
    paths = report.write_outputs(snapshot, output_dir=output_dir, doc_path=doc_path, repo_root=tmp_path)

    assert paths["latest"] == "logs/qre_actionable_failure_taxonomy/latest.json"
    assert paths["doc"] == "docs/governance/qre_actionable_failure_taxonomy.md"
    assert doc_path.read_text(encoding="utf-8").startswith("# QRE Actionable Failure Taxonomy")
