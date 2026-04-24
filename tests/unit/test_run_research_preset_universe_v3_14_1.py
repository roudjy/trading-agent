"""v3.14.1 targeted regression tests: preset.universe is load-bearing.

Pins:

1. ``build_research_universe_from_preset`` resolves to the preset
   universe (equities for ``trend_equities_4h_baseline``), not the
   config-driven default (``crypto_major``).
2. Intervals default to ``[preset.timeframe]``.
3. Empty preset.universe raises a clear ValueError.
4. Snapshot reflects preset provenance (``source`` prefixed
   ``preset:``, ``resolver`` is ``"preset"``, ``requested_config``
   carries ``preset_name`` / ``preset_universe`` /
   ``preset_timeframe``).
5. Non-preset runs still use the config-driven
   :func:`build_research_universe`.
"""

from __future__ import annotations

import pytest

from research.presets import PRESETS
from research.universe import (
    BUILTIN_UNIVERSES,
    DEFAULT_SOURCE,
    build_research_universe,
    build_research_universe_from_preset,
)


def _preset(name: str):
    for p in PRESETS:
        if p.name == name:
            return p
    pytest.fail(f"preset {name!r} missing from research.presets.PRESETS")


# ---------------------------------------------------------------------------
# Preset-driven: trend_equities_4h_baseline → equities, not crypto_major
# ---------------------------------------------------------------------------


def test_trend_equities_4h_baseline_resolves_to_equity_universe():
    preset = _preset("trend_equities_4h_baseline")
    assets, intervals, _date_range, _as_of, snapshot = (
        build_research_universe_from_preset(preset, {})
    )
    symbols = [a.symbol for a in assets]

    # Must match the preset's declared universe exactly
    assert symbols == list(preset.universe)

    # Must NOT accidentally be any built-in like crypto_major
    for builtin_name, builtin_assets in BUILTIN_UNIVERSES.items():
        builtin_symbols = [a.symbol for a in builtin_assets]
        assert symbols != builtin_symbols, (
            f"preset-driven universe must not collapse to built-in "
            f"{builtin_name!r}"
        )

    # Every symbol should be typed as equity
    assert all(a.asset_type == "equity" for a in assets), (
        f"preset universe was not typed as equity: "
        f"{[(a.symbol, a.asset_type) for a in assets]}"
    )

    # Snapshot provenance reflects preset source
    assert snapshot.resolver == "preset"
    assert snapshot.source == "preset:trend_equities_4h_baseline"
    assert snapshot.requested_config["preset_name"] == "trend_equities_4h_baseline"
    assert list(snapshot.requested_config["preset_universe"]) == list(preset.universe)


def test_preset_intervals_default_to_preset_timeframe():
    preset = _preset("trend_equities_4h_baseline")
    _assets, intervals, _dr, _asof, _snap = build_research_universe_from_preset(
        preset, {}
    )
    assert intervals == ["4h"]


def test_crypto_preset_resolves_to_crypto_asset_type():
    preset = _preset("crypto_diagnostic_1h")
    assets, intervals, *_ = build_research_universe_from_preset(preset, {})
    symbols = [a.symbol for a in assets]
    assert symbols == list(preset.universe)
    # BTC-EUR / ETH-EUR suffix-based inference
    assert all(a.asset_type == "crypto" for a in assets), (
        f"crypto preset universe was not typed as crypto: "
        f"{[(a.symbol, a.asset_type) for a in assets]}"
    )
    assert intervals == ["1h"]


def test_empty_preset_universe_raises_clear_value_error():
    class _EmptyPreset:
        name = "empty_preset_test"
        universe: tuple[str, ...] = ()
        timeframe = "1d"

    with pytest.raises(ValueError) as exc_info:
        build_research_universe_from_preset(_EmptyPreset(), {})
    msg = str(exc_info.value)
    assert "empty" in msg.lower()
    assert "empty_preset_test" in msg


def test_none_preset_is_rejected_loudly():
    with pytest.raises(ValueError):
        build_research_universe_from_preset(None, {})


def test_preset_driven_universe_ignores_config_research_universe_source():
    """Pin the precedence rule: config ``research.universe`` is ignored
    when a preset is active. Otherwise a daily scheduler misconfig
    could silently override the preset universe.
    """
    preset = _preset("trend_equities_4h_baseline")
    research_config = {
        "universe": {"source": "crypto_major"},
        "default_lookback_days": 500,
    }
    assets, intervals, _dr, _asof, snapshot = (
        build_research_universe_from_preset(preset, research_config)
    )
    symbols = [a.symbol for a in assets]
    assert symbols == list(preset.universe), (
        "config research.universe leaked into a preset-driven run"
    )
    assert DEFAULT_SOURCE == "crypto_major"  # guard: default still the same
    # snapshot must not claim crypto_major
    assert "crypto_major" not in snapshot.source


def test_preset_driven_universe_respects_lookback_config():
    """interval_lookbacks / default_lookback_days still come from
    research_config — only the asset universe + intervals switch.
    """
    preset = _preset("trend_equities_4h_baseline")
    research_config = {"default_lookback_days": 1234}
    _assets, _intervals, date_range, as_of_utc, _snap = (
        build_research_universe_from_preset(preset, research_config)
    )
    # 4h uses 700d hard-coded fallback path, not default_lookback_days;
    # verify 1d interval hits default_lookback_days=1234 instead.
    start, end = date_range("1d")
    from datetime import datetime
    start_dt = datetime.fromisoformat(start)
    end_dt = datetime.fromisoformat(end)
    delta_days = (end_dt - start_dt).days
    assert delta_days == 1234, (
        f"default_lookback_days from research_config was ignored: "
        f"got delta={delta_days}"
    )


# ---------------------------------------------------------------------------
# Non-preset runs still use build_research_universe (config-driven)
# ---------------------------------------------------------------------------


def test_non_preset_run_still_uses_config_research_universe():
    """Sanity: a run without a preset goes through
    ``build_research_universe(research_config)`` which honours the
    config-driven source. v3.14.1 must not accidentally force all
    runs through the preset path.
    """
    research_config = {"universe": {"source": "crypto_major"}}
    assets, intervals, _dr, _asof, snapshot = build_research_universe(
        research_config
    )
    symbols = [a.symbol for a in assets]
    crypto_major_symbols = [a.symbol for a in BUILTIN_UNIVERSES["crypto_major"]]
    assert symbols == crypto_major_symbols
    assert snapshot.source == "crypto_major"
    assert snapshot.resolver != "preset"


def test_config_research_universe_still_defaults_to_crypto_major_when_missing():
    """Pin the legacy default behaviour so the fix doesn't accidentally
    change non-preset runs.
    """
    assets, _intervals, _dr, _asof, snapshot = build_research_universe({})
    symbols = [a.symbol for a in assets]
    crypto_major_symbols = [a.symbol for a in BUILTIN_UNIVERSES["crypto_major"]]
    assert symbols == crypto_major_symbols
    assert snapshot.source == "crypto_major"


# ---------------------------------------------------------------------------
# Source-level pin: run_research.py actually calls the preset helper
# ---------------------------------------------------------------------------


def test_run_research_uses_preset_helper_when_preset_obj_is_present():
    """Static guard: the runner must call
    ``build_research_universe_from_preset(preset_obj, research_config)``
    when a preset is active. Prevents a silent regression that
    re-routes preset runs through the config-driven resolver.
    """
    with open("research/run_research.py", encoding="utf-8") as fh:
        text = fh.read()
    assert "build_research_universe_from_preset(preset_obj, research_config)" in text
