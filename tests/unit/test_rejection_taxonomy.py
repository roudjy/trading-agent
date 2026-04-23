"""Tests for research.rejection_taxonomy (v3.12)."""

from __future__ import annotations

from dataclasses import fields

from research.rejection_taxonomy import (
    DEFERRED_TAXONOMY_CODES,
    OBSERVED_TO_TAXONOMY,
    TAXONOMY_CODES,
    TaxonomyDerivation,
    all_known_codes,
    collect_observed_reason_codes,
    derive_taxonomy,
)


EIGHT_EXPECTED_CODES = {
    "insufficient_trades",
    "no_oos_samples",
    "oos_collapse",
    "cost_sensitive",
    "unstable_parameter_neighborhood",
    "regime_concentrated",
    "single_asset_dependency",
    "low_statistical_defensibility",
}


def test_taxonomy_has_exactly_the_eight_spec_codes() -> None:
    assert TAXONOMY_CODES == EIGHT_EXPECTED_CODES


def test_deferred_codes_are_subset_of_taxonomy() -> None:
    assert DEFERRED_TAXONOMY_CODES.issubset(TAXONOMY_CODES)


def test_observed_to_taxonomy_values_are_valid_codes() -> None:
    for observed_code, taxonomy_code in OBSERVED_TO_TAXONOMY.items():
        assert isinstance(observed_code, str)
        assert taxonomy_code in TAXONOMY_CODES


def test_taxonomy_derivation_dataclass_has_no_timestamp_field() -> None:
    field_names = {f.name for f in fields(TaxonomyDerivation)}
    assert field_names == {
        "taxonomy_code",
        "observed_sources",
        "derivation_method",
        "caveats",
    }
    assert "derived_at_utc" not in field_names
    assert "at_utc" not in field_names


def test_collect_observed_reason_codes_reads_failed_and_escalated() -> None:
    v1_entry = {
        "reasoning": {
            "passed": ["drawdown_below_limit"],
            "failed": ["insufficient_trades", "oos_sharpe_below_threshold"],
            "escalated": ["psr_below_threshold"],
        },
    }
    codes = collect_observed_reason_codes(v1_entry)
    assert set(codes) == {
        "insufficient_trades",
        "oos_sharpe_below_threshold",
        "psr_below_threshold",
    }
    # passed codes must NOT leak into observed rejection codes
    assert "drawdown_below_limit" not in codes


def test_collect_observed_reason_codes_tolerates_missing_reasoning() -> None:
    assert collect_observed_reason_codes({}) == ()
    assert collect_observed_reason_codes({"reasoning": None}) == ()


def test_derive_taxonomy_direct_mapping_insufficient_trades() -> None:
    entry = {
        "strategy_name": "sma_crossover",
        "asset": "NVDA",
        "interval": "4h",
        "reasoning": {"failed": ["insufficient_trades"], "escalated": []},
    }
    codes, derivations = derive_taxonomy(entry, regime_diag=None, cost_sens=None)
    assert codes == ("insufficient_trades",)
    (d,) = derivations
    assert d.taxonomy_code == "insufficient_trades"
    assert d.derivation_method == "direct_mapping"
    assert "insufficient_trades" in d.observed_sources


def test_derive_taxonomy_merges_multiple_defensibility_signals_into_one_code() -> None:
    entry = {
        "strategy_name": "s",
        "asset": "A",
        "interval": "4h",
        "reasoning": {
            "failed": ["oos_sharpe_below_threshold"],
            "escalated": ["psr_below_threshold", "dsr_canonical_below_threshold"],
        },
    }
    codes, derivations = derive_taxonomy(entry, regime_diag=None, cost_sens=None)
    assert codes == ("low_statistical_defensibility",)
    (d,) = derivations
    assert set(d.observed_sources) == {
        "oos_sharpe_below_threshold",
        "psr_below_threshold",
        "dsr_canonical_below_threshold",
    }
    # more than one source -> no single_observed_signal caveat
    assert "single_observed_signal" not in d.caveats


def test_derive_taxonomy_single_defensibility_signal_flags_caveat() -> None:
    entry = {
        "strategy_name": "s",
        "asset": "A",
        "interval": "4h",
        "reasoning": {"failed": [], "escalated": ["psr_below_threshold"]},
    }
    _, derivations = derive_taxonomy(entry, regime_diag=None, cost_sens=None)
    (d,) = derivations
    assert d.caveats == ("single_observed_signal",)


def test_derive_taxonomy_does_not_emit_deferred_codes() -> None:
    # Nothing in observed codes should be able to produce
    # unstable_parameter_neighborhood or single_asset_dependency.
    entry = {
        "strategy_name": "s",
        "asset": "A",
        "interval": "4h",
        "reasoning": {
            "failed": ["insufficient_trades", "drawdown_above_limit"],
            "escalated": ["psr_below_threshold"],
        },
    }
    codes, _ = derive_taxonomy(entry, regime_diag=None, cost_sens=None)
    assert "unstable_parameter_neighborhood" not in codes
    assert "single_asset_dependency" not in codes


def test_derive_taxonomy_emits_cost_sensitive_from_flag() -> None:
    entry = {
        "strategy_name": "s",
        "asset": "A",
        "interval": "4h",
        "reasoning": {"failed": [], "escalated": []},
    }
    cost_sens = {"s|A|4h": {"flag": True}}
    codes, derivations = derive_taxonomy(entry, regime_diag=None, cost_sens=cost_sens)
    assert codes == ("cost_sensitive",)
    (d,) = derivations
    assert d.derivation_method == "flag_source"


def test_derive_taxonomy_emits_regime_concentrated_from_flag() -> None:
    entry = {
        "strategy_name": "s",
        "asset": "A",
        "interval": "4h",
        "reasoning": {"failed": [], "escalated": []},
    }
    regime = {"candidates": [{"strategy_name": "s", "asset": "A", "interval": "4h", "flag": True}]}
    codes, _ = derive_taxonomy(entry, regime_diag=regime, cost_sens=None)
    assert "regime_concentrated" in codes


def test_derive_taxonomy_results_are_sorted_for_determinism() -> None:
    entry = {
        "strategy_name": "s",
        "asset": "A",
        "interval": "4h",
        "reasoning": {
            "failed": ["insufficient_trades", "drawdown_above_limit"],
            "escalated": ["psr_below_threshold"],
        },
    }
    cost_sens = {"s|A|4h": {"flag": True}}
    codes, derivations = derive_taxonomy(entry, regime_diag=None, cost_sens=cost_sens)
    assert list(codes) == sorted(codes)
    derivation_codes = [d.taxonomy_code for d in derivations]
    assert derivation_codes == sorted(derivation_codes)


def test_all_known_codes_is_sorted() -> None:
    assert list(all_known_codes()) == sorted(TAXONOMY_CODES)


def test_to_payload_is_json_safe_dict() -> None:
    d = TaxonomyDerivation(
        taxonomy_code="insufficient_trades",
        observed_sources=("insufficient_trades",),
        derivation_method="direct_mapping",
        caveats=(),
    )
    payload = d.to_payload()
    assert payload["observed_sources"] == ["insufficient_trades"]
    assert payload["caveats"] == []
    assert payload["taxonomy_code"] == "insufficient_trades"
    assert "derived_at_utc" not in payload


def test_derive_taxonomy_is_deterministic_across_calls() -> None:
    entry = {
        "strategy_name": "s",
        "asset": "A",
        "interval": "4h",
        "reasoning": {"failed": ["insufficient_trades"], "escalated": []},
    }
    out_a = derive_taxonomy(entry, regime_diag=None, cost_sens=None)
    out_b = derive_taxonomy(entry, regime_diag=None, cost_sens=None)
    assert out_a == out_b
