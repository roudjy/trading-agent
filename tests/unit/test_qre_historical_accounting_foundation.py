from __future__ import annotations

from research import qre_historical_accounting_foundation as foundation


def test_historical_accounting_foundation_is_deterministic_and_fail_closed() -> None:
    left = foundation.build_historical_accounting_foundation()
    right = foundation.build_historical_accounting_foundation()

    assert left == right
    assert left["summary"]["required_source_count"] >= 1
    assert left["summary"]["required_blocked_count"] >= 1
    assert left["summary"]["no_lookahead_ready_count"] == 0


def test_historical_accounting_foundation_blocks_sec_and_skips_identity_only_sources() -> None:
    rows = {row["source_id"]: row for row in foundation.build_historical_accounting_foundation()["rows"]}
    sec = rows["sec_companyfacts_manifest"]
    openfigi = rows["openfigi_symbology_manifest"]

    assert sec["requires_historical_accounting"] is True
    assert sec["snapshot_contract_status"] == "BLOCKED"
    assert "report_lag_policy_supported" in sec["blocking_reasons"]
    assert "restatement_policy_supported" in sec["blocking_reasons"]
    assert "historical_lineage_reproducible" in sec["blocking_reasons"]
    assert openfigi["snapshot_contract_status"] == "NOT_REQUIRED"


def test_safety_invariants_keep_historical_accounting_report_only() -> None:
    report = foundation.build_historical_accounting_foundation()

    assert report["safety_invariants"] == {
        "read_only": True,
        "fetches_external_data": False,
        "mutates_runtime_state": False,
        "mutates_research_outputs": False,
        "mutates_frozen_contracts": False,
        "paper_shadow_live_forbidden": True,
        "broker_risk_execution_forbidden": True,
        "lookahead_contamination_forbidden": True,
        "point_in_time_foundation_only": True,
    }
