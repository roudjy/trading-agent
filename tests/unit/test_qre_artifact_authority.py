from __future__ import annotations

from research import qre_artifact_authority as authority


def test_artifact_authority_registry_is_deterministic() -> None:
    first = authority.build_artifact_authority_snapshot()
    second = authority.build_artifact_authority_snapshot()

    assert first == second
    assert first["report_kind"] == authority.REPORT_KIND
    assert first["summary"]["authority_kind_count"] == len(authority.AUTHORITY_KINDS)


def test_only_accepted_evidence_can_clear_current_evidence_blockers() -> None:
    rows = {row["authority_kind"]: row for row in authority.build_artifact_authority_snapshot()["rows"]}

    assert rows["accepted_evidence"]["can_clear_campaign_lineage_missing"] is True
    assert rows["accepted_evidence"]["can_clear_no_oos_evidence"] is True
    assert rows["accepted_evidence"]["can_clear_evidence_complete"] is True

    for kind in (
        "source_artifact",
        "generated_report",
        "context_only",
        "approval_manifest",
        "generation_manifest",
        "reason_record",
        "legacy_trace",
        "test_fixture",
        "smoke_temp",
        "stdout_only",
        "rejected_artifact",
    ):
        assert rows[kind]["can_clear_campaign_lineage_missing"] is False
        assert rows[kind]["can_clear_no_oos_evidence"] is False
        assert rows[kind]["can_clear_evidence_complete"] is False


def test_context_and_stdout_artifacts_remain_context_only() -> None:
    rows = {row["authority_kind"]: row for row in authority.build_artifact_authority_snapshot()["rows"]}

    assert rows["generated_report"]["can_support_context"] is True
    assert rows["generated_report"]["can_prove_current_evidence"] is False
    assert rows["stdout_only"]["can_support_context"] is False
    assert rows["stdout_only"]["can_prove_current_evidence"] is False
    assert rows["test_fixture"]["can_support_context"] is True
    assert rows["test_fixture"]["can_prove_current_evidence"] is False


def test_accepted_evidence_validation_requires_structured_refs() -> None:
    rejected = authority.classify_artifact_authority(
        {
            "authority_kind": "accepted_evidence",
            "record_kind": "accepted_evidence",
            "source_artifact_ref": "logs/source.json",
            "generation_manifest_ref": "",
            "approval_ref": "approval-001",
            "reason_record_refs": {"record_ids": ["rr-1"]},
        }
    )
    valid = authority.classify_artifact_authority(
        {
            "authority_kind": "accepted_evidence",
            "record_kind": "accepted_evidence",
            "source_artifact_ref": "logs/source.json",
            "generation_manifest_ref": "logs/generation.json",
            "approval_manifest_ref": "logs/approval.json",
            "reason_record_refs": {"record_ids": ["rr-1"]},
        }
    )

    assert rejected["validation_status"] == "rejected"
    assert "missing_generation_manifest_ref" in rejected["rejection_reasons"]
    assert valid["validation_status"] == "valid"
    assert valid["capabilities"]["can_clear_campaign_lineage_missing"] is True

