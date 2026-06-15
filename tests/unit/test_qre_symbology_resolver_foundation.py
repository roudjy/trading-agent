from __future__ import annotations

from research import qre_symbology_resolver_foundation as foundation


def test_symbology_resolver_foundation_is_deterministic_and_blocks_ambiguity() -> None:
    left = foundation.build_symbology_resolver_foundation()
    right = foundation.build_symbology_resolver_foundation()

    assert left == right
    assert left["summary"]["instrument_count"] >= 1
    assert left["summary"]["ambiguity_blocked_count"] >= 1


def test_symbology_resolver_foundation_keeps_candidate_aliases_blocked() -> None:
    rows = {row["instrument_symbol"]: row for row in foundation.build_symbology_resolver_foundation()["rows"]}

    assert rows["ADYEN"]["resolution_status"] == "VERIFIED"
    assert rows["ASMI"]["ambiguity_blocked"] is True
    assert "candidate_alias_requires_verification" in rows["ASMI"]["blocking_reasons"]
    assert "multiple_candidate_aliases" in rows["ASMI"]["blocking_reasons"]
    assert rows["NOVO-B"]["ambiguity_blocked"] is True


def test_symbology_resolver_safety_invariants_keep_identity_non_authoritative() -> None:
    report = foundation.build_symbology_resolver_foundation()

    assert report["safety_invariants"] == {
        "read_only": True,
        "identity_is_infrastructure_only": True,
        "not_alpha_authority": True,
        "candidate_promotion_forbidden": True,
        "paper_shadow_live_forbidden": True,
        "broker_risk_execution_forbidden": True,
    }
