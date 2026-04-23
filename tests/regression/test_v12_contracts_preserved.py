"""Regression — v3.13 must not mutate v3.12 semantics silently.

Guards that keep v3.12 fields shape-stable and value-stable when the
v3.13 regime intelligence sidecar is absent:

- ``derive_taxonomy`` without ``regime_intelligence`` produces the
  same codes/derivations as the v3.12 signature path (legacy
  flag-source behaviour).
- ``derive_taxonomy`` with the sidecar absent and the legacy
  regime_suspicion_flag True emits
  ``derivation_method="flag_source"`` (not classifier_output).
- The v3.13 additive parameter defaults to ``None``.
"""

from __future__ import annotations

import inspect

from research.rejection_taxonomy import derive_taxonomy


def test_derive_taxonomy_signature_keeps_v3_12_positional_args() -> None:
    sig = inspect.signature(derive_taxonomy)
    names = list(sig.parameters.keys())
    # first three positional args are unchanged from v3.12 semantics
    assert names[0] == "v1_entry"
    assert names[1] == "regime_diag"
    assert names[2] == "cost_sens"


def test_derive_taxonomy_v3_12_signature_call_still_works() -> None:
    entry = {
        "strategy_name": "sma_crossover",
        "asset": "NVDA",
        "interval": "4h",
        "reasoning": {
            "failed": ["insufficient_trades", "drawdown_above_limit"],
            "escalated": ["psr_below_threshold"],
        },
    }
    cost_sens = {"sma_crossover|NVDA|4h": {"flag": True}}
    regime_legacy = {
        "candidates": [
            {
                "strategy_name": "sma_crossover",
                "asset": "NVDA",
                "interval": "4h",
                "flag": True,
            }
        ]
    }
    codes, derivations = derive_taxonomy(
        entry, regime_diag=regime_legacy, cost_sens=cost_sens
    )
    # all three derived codes must appear, legacy flag source path intact
    assert "cost_sensitive" in codes
    assert "regime_concentrated" in codes
    assert "insufficient_trades" in codes
    regime_deriv = next(d for d in derivations if d.taxonomy_code == "regime_concentrated")
    assert regime_deriv.derivation_method == "flag_source"


def test_regime_intelligence_param_defaults_to_none() -> None:
    sig = inspect.signature(derive_taxonomy)
    regime_intelligence_param = sig.parameters["regime_intelligence"]
    assert regime_intelligence_param.default is None


def test_regime_concentrated_threshold_param_is_explicit_constant() -> None:
    sig = inspect.signature(derive_taxonomy)
    threshold_param = sig.parameters["regime_concentrated_threshold"]
    # explicit named constant, not None
    assert isinstance(threshold_param.default, (int, float))
    assert 0.0 < float(threshold_param.default) <= 1.0
