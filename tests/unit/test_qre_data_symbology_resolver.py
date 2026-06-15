from __future__ import annotations

from packages.qre_data import symbology_resolver


def test_symbology_resolver_verifies_single_provider_symbol() -> None:
    row = symbology_resolver.resolve_symbology_row(
        {
            "symbol": "ADYEN",
            "canonical_instrument_id": "EURONEXT:ADYEN",
            "primary_data_provider_symbol": "ADYEN.AS",
            "provider_symbol_aliases": ["ADYEN.AS"],
            "provider_symbol_status": "verified",
            "source_identity_status": "provider_symbol_verified",
        }
    )

    assert row["resolution_status"] == "VERIFIED"
    assert row["ambiguity_blocked"] is False
    assert row["blocking_reasons"] == []


def test_symbology_resolver_blocks_candidate_alias_ambiguity() -> None:
    row = symbology_resolver.resolve_symbology_row(
        {
            "symbol": "ASMI",
            "canonical_instrument_id": "EURONEXT:ASMI",
            "primary_data_provider_symbol": None,
            "provider_symbol_aliases": ["ASM.AS", "ASMI.AS"],
            "provider_symbol_status": "candidate_alias_requires_verification",
            "source_identity_status": "candidate_alias_only",
        }
    )

    assert row["resolution_status"] == "MISSING_BLOCKED"
    assert row["ambiguity_blocked"] is True
    assert row["blocking_reasons"] == [
        "missing_primary_provider_symbol",
        "candidate_alias_requires_verification",
        "multiple_candidate_aliases",
    ]
