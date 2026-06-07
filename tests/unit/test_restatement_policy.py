from __future__ import annotations

from research.data_readiness.restatement_policy import build_restatement_policy


def test_restatement_policy_is_deterministic_and_fail_closed() -> None:
    left = build_restatement_policy()
    right = build_restatement_policy()
    assert left == right
    assert left["summary"]["required_count"] >= 1


def test_restatement_policy_keeps_sec_blocked_and_metadata_only_not_required() -> None:
    rows = {row["source_id"]: row for row in build_restatement_policy()["rows"]}
    sec = rows["sec_companyfacts_manifest"]
    euronext = rows["euronext_issuer_metadata_manifest"]
    assert sec["requirement_status"] == "REQUIRED"
    assert "MISSING_RESTATEMENT_POLICY" in sec["block_reasons"]
    assert "RESTATEMENT_POLICY_UNKNOWN" in sec["block_reasons"]
    assert euronext["policy_status"] == "NOT_REQUIRED"
