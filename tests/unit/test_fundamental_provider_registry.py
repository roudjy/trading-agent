from __future__ import annotations

import pytest

from research.external_intelligence import fundamental_provider_registry as registry


def test_provider_registry_is_deterministic_and_conservative() -> None:
    left = registry.build_fundamental_provider_registry()
    right = registry.build_fundamental_provider_registry()
    assert left == right
    assert left["summary"]["total_providers"] >= 10
    assert left["summary"]["active_read_only_count"] == 0
    assert left["summary"]["quality_gated_count"] == 0
    assert left["safety_invariants"]["no_data_fetch"] is True


def test_provider_registry_contains_required_candidates() -> None:
    payload = registry.build_fundamental_provider_registry()
    provider_ids = {row["provider_id"] for row in payload["rows"]}
    assert "openfigi_symbology" in provider_ids
    assert "sec_companyfacts" in provider_ids
    assert "yahoo_finance_yfinance" in provider_ids
    assert "openbb_connector" in provider_ids


def test_unknown_license_cannot_be_active_read_only() -> None:
    bad_row = {
        **registry.PROVIDER_ROWS[0],
        "provider_id": "bad_provider",
        "source_status": "active_read_only",
        "license_terms_status": "unknown",
    }
    with pytest.raises(ValueError, match="cannot be active_read_only"):
        registry.validate_provider_rows([bad_row])


def test_forbidden_use_is_complete_for_all_rows() -> None:
    payload = registry.build_fundamental_provider_registry()
    for row in payload["rows"]:
        assert row["forbidden_use"] == list(registry.FORBIDDEN_USE)
