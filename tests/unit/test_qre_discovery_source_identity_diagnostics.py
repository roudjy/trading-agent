from __future__ import annotations

from research import qre_discovery_source_identity_diagnostics as diagnostics


def test_source_identity_diagnostics_expose_verified_and_ambiguous_symbols() -> None:
    report = diagnostics.build_source_identity_diagnostics(max_candidates=15)

    rows = {row["instrument_symbol"]: row for row in report["rows"]}
    assert rows["ADYEN"]["selected_provider_symbol"] == "ADYEN.AS"
    assert rows["ADYEN"]["provider_symbol_status"] == "verified"
    assert rows["ADYEN"]["identity_confidence"] == "high"
    assert rows["ADYEN"]["affected_grid_rows"] == 8
    assert rows["ADYEN"]["affected_baskets"] == 1
    assert rows["ASMI"]["provider_symbol_status"] == "candidate_alias_requires_verification"
    assert rows["ASMI"]["ambiguity_warning"] == "multiple_candidate_aliases"
    assert rows["ASMI"]["next_action"] == "require_alias_verification"


def test_render_operator_summary_includes_required_identity_columns() -> None:
    report = diagnostics.build_source_identity_diagnostics(max_candidates=15)

    markdown = diagnostics.render_operator_summary(report)

    assert "# QRE Discovery Source Identity Diagnostics" in markdown
    assert "## 3. Source identity diagnostics" in markdown
    assert "Selected provider symbol" in markdown
    assert "Affected grid rows" in markdown
    assert "ADYEN" in markdown
