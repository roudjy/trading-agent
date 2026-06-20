from __future__ import annotations

import json
from pathlib import Path

from research import qre_reason_record_normalization as normalization


def test_build_reason_record_normalization_surfaces_contract_gaps(monkeypatch) -> None:
    monkeypatch.setattr(
        normalization.reason_records_v1,
        "build_reason_records_snapshot",
        lambda **_: {
            "records": [
                {
                    "record_id": "rr1",
                    "record_kind": "qre_reason_record",
                    "record_family": "routing_readiness",
                    "subject_id": "cand-1",
                    "reason_codes": ["routing_ready"],
                    "reason_text": "Routing is ready.",
                    "evidence_refs": ["logs/qre_reason_records/latest.jsonl#line[0]"],
                    "inputs_digest": "sha256:rr1",
                }
            ]
        },
    )
    monkeypatch.setattr(
        normalization.candidate_quality,
        "build_candidate_quality_framework",
        lambda **_: {
            "rows": [
                {
                    "reason_record": {
                        "record_id": "rr2",
                        "record_kind": "qre_candidate_quality",
                        "subject_id": "cand-1",
                        "reason_codes": ["blocked_missing_accepted_oos"],
                        "reason_text": "Accepted OOS is missing.",
                        "evidence_refs": ["logs/qre_candidate_identity_lifecycle/latest.json"],
                        "inputs_digest": "sha256:rr2",
                        "accepted_evidence": False,
                        "basket_request_ref": "logs/qre_evidence_breadth_framework/latest.json",
                        "verifier_ref": "logs/qre_multiwindow_evidence_closure/latest.json",
                        "closure_ref": "logs/qre_multiwindow_evidence_closure/latest.json",
                    }
                }
            ]
        },
    )
    monkeypatch.setattr(
        normalization.shadow_readiness,
        "build_shadow_readiness_gates",
        lambda **_: {
            "reason_records": [
                {
                    "record_id": "rr3",
                    "record_kind": "qre_shadow_readiness_deferral",
                    "subject_id": "qre_shadow_readiness",
                    "reason_codes": ["accepted_oos_missing"],
                    "reason_text": "Shadow readiness remains deferred.",
                    "evidence_refs": ["logs/qre_shadow_readiness_gates/latest.json"],
                }
            ]
        },
    )
    monkeypatch.setattr(
        normalization.basket_closure,
        "build_evidence_complete_basket_closure",
        lambda **_: {
            "rows": [
                {
                    "clearance_reason_records": [
                        {
                            "record_family": "accepted_structured_evidence_clearance",
                            "subject_id": "cand-1",
                            "reason_codes": ["campaign_lineage_missing_cleared_by_accepted_structured_evidence"],
                            "evidence_refs": ["logs/qre_structured_lineage_artifacts/latest.json"],
                        }
                    ]
                }
            ]
        },
    )

    report = normalization.build_reason_record_normalization()

    assert report["summary"]["reason_record_normalization_ready"] is True
    assert report["summary"]["normalized_record_count"] == 4
    assert report["summary"]["valid_record_count"] == 1
    assert report["summary"]["invalid_record_count"] == 3
    assert report["summary"]["final_recommendation"] == "reason_record_normalization_has_contract_gaps"
    rows = {row["producer_id"]: row for row in report["producer_rows"]}
    assert rows["qre_reason_records_v1"]["invalid_record_count"] == 1
    assert rows["qre_candidate_quality_framework"]["valid_record_count"] == 1
    assert rows["qre_shadow_readiness_gates"]["invalid_record_count"] == 1
    assert rows["qre_evidence_complete_basket_closure"]["invalid_record_count"] == 1


def test_write_outputs_materializes_normalization_report(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(
        normalization,
        "build_reason_record_normalization",
        lambda **_: {
            "summary": {
                "reason_record_normalization_ready": True,
                "normalized_record_count": 1,
                "valid_record_count": 1,
                "invalid_record_count": 0,
                "exact_next_action": "preserve_normalized_reason_record_visibility",
            },
            "producer_rows": [
                {
                    "producer_id": "qre_reason_records_v1",
                    "record_count": 1,
                    "valid_record_count": 1,
                    "invalid_record_count": 0,
                    "status": "normalized_ready",
                }
            ],
        },
    )

    report = normalization.build_reason_record_normalization(repo_root=tmp_path)
    paths = normalization.write_outputs(report, repo_root=tmp_path)

    assert paths["latest"] == "logs/qre_reason_record_normalization/latest.json"
    assert paths["operator_summary"] == "logs/qre_reason_record_normalization/operator_summary.md"
    payload = json.loads((tmp_path / paths["latest"]).read_text(encoding="utf-8"))
    assert payload["summary"]["reason_record_normalization_ready"] is True
    assert "# QRE Reason Record Normalization" in (
        tmp_path / paths["operator_summary"]
    ).read_text(encoding="utf-8")
