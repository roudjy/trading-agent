from __future__ import annotations

from research import qre_reason_record_contract as contract


def test_reason_record_contract_is_deterministic() -> None:
    first = contract.build_reason_record_contract_snapshot()
    second = contract.build_reason_record_contract_snapshot()

    assert first == second
    assert first["report_kind"] == contract.REPORT_KIND
    assert first["summary"]["required_field_count"] >= 7


def test_reason_record_contract_requires_blocker_and_evidence_refs() -> None:
    snapshot = contract.build_reason_record_contract_snapshot()
    validation = snapshot["contract"]["accepted_record_validation"]

    assert validation["validation_status"] == "valid"
    assert snapshot["contract"]["reason_record_required_for_blockers"] is True
    assert snapshot["contract"]["accepted_evidence_required_to_clear_blockers"] is True
    assert snapshot["contract"]["negative_evidence_preservation_required"] is True


def test_reason_record_contract_rejects_missing_structured_refs() -> None:
    rejected = contract.validate_reason_record_contract(
        {
            "record_id": "rr-1",
            "record_kind": "reason_record",
            "subject_id": "basket-1",
            "reason_codes": ["campaign_lineage_missing"],
            "reason_text": "lineage missing",
            "evidence_refs": ["logs/a.json"],
            "inputs_digest": "digest",
            "accepted_evidence": True,
            "basket_request_ref": "logs/request.json",
            "verifier_ref": "logs/verifier.json",
            "closure_ref": "logs/closure.json",
            "negative_evidence_preservation": "preserved",
            "source_artifact_ref": "logs/source.json",
            "generation_manifest_ref": "",
            "approval_manifest_ref": "logs/approval.json",
        }
    )

    assert rejected["validation_status"] == "rejected"
    assert "missing_generation_manifest_ref" in rejected["rejection_reasons"]


def test_reason_record_contract_requires_consumer_refs_and_negative_preservation() -> None:
    rejected = contract.validate_reason_record_contract(
        {
            "record_id": "rr-2",
            "record_kind": "reason_record",
            "subject_id": "basket-2",
            "reason_codes": ["no_oos_evidence"],
            "reason_text": "oos missing",
            "evidence_refs": ["logs/a.json"],
            "inputs_digest": "digest",
            "accepted_evidence": False,
            "basket_request_ref": "",
            "verifier_ref": "",
            "closure_ref": "",
            "negative_evidence_preservation": "lost",
        }
    )

    assert rejected["validation_status"] == "rejected"
    assert "missing_consumer_refs" in rejected["rejection_reasons"]
    assert "negative_evidence_not_preserved" in rejected["rejection_reasons"]
