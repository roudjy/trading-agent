"""Tests for research universe resolution."""

from __future__ import annotations

import pytest

from research.universe import (
    BUILTIN_UNIVERSES,
    DEFAULT_SOURCE,
    ResearchAsset,
    UniverseSnapshot,
    build_research_universe,
    resolve_universe,
)

AS_OF = "2026-04-13T10:00:00+00:00"


# ---------------------------------------------------------------------------
# resolve_universe — builtin resolver
# ---------------------------------------------------------------------------


class TestBuiltinResolver:
    def test_default_resolves_crypto_major(self):
        assets, snapshot = resolve_universe(None, AS_OF)
        assert snapshot.source == DEFAULT_SOURCE
        assert snapshot.resolver == "builtin"
        assert snapshot.resolved_count == len(BUILTIN_UNIVERSES[DEFAULT_SOURCE])

    def test_named_universe_resolves(self):
        config = {"universe": {"source": "nasdaq_100_sample"}}
        assets, snapshot = resolve_universe(config, AS_OF)
        assert snapshot.source == "nasdaq_100_sample"
        assert snapshot.resolved_count == len(BUILTIN_UNIVERSES["nasdaq_100_sample"])
        assert all(isinstance(a, ResearchAsset) for a in assets)

    def test_unknown_source_raises(self):
        config = {"universe": {"source": "nonexistent"}}
        with pytest.raises(ValueError, match="Unknown universe source"):
            resolve_universe(config, AS_OF)

    def test_missing_source_raises(self):
        config = {"universe": {}}
        with pytest.raises(ValueError, match="source is required"):
            resolve_universe(config, AS_OF)

    def test_exclude_removes_symbols(self):
        config = {"universe": {"source": "crypto_major", "exclude": ["BTC-USD"]}}
        assets, snapshot = resolve_universe(config, AS_OF)
        symbols = [a.symbol for a in assets]
        assert "BTC-USD" not in symbols
        assert "BTC-USD" in snapshot.excluded_symbols
        assert snapshot.resolved_count == len(BUILTIN_UNIVERSES["crypto_major"]) - 1

    def test_include_adds_symbols(self):
        config = {
            "universe": {
                "source": "crypto_major",
                "include": [{"symbol": "MATIC-USD", "asset_type": "crypto", "asset_class": "crypto"}],
            }
        }
        assets, snapshot = resolve_universe(config, AS_OF)
        symbols = [a.symbol for a in assets]
        assert "MATIC-USD" in symbols

    def test_include_dedup_first_wins(self):
        config = {
            "universe": {
                "source": "crypto_major",
                "include": [{"symbol": "BTC-USD", "asset_type": "custom", "asset_class": "crypto"}],
            }
        }
        assets, snapshot = resolve_universe(config, AS_OF)
        btc = [a for a in assets if a.symbol == "BTC-USD"]
        assert len(btc) == 1
        assert btc[0].asset_type == "crypto"  # builtin wins (first occurrence)

    def test_exclude_all_raises(self):
        all_symbols = [a.symbol for a in BUILTIN_UNIVERSES["crypto_major"]]
        config = {"universe": {"source": "crypto_major", "exclude": all_symbols}}
        with pytest.raises(ValueError, match="zero assets"):
            resolve_universe(config, AS_OF)


# ---------------------------------------------------------------------------
# resolve_universe — static resolver
# ---------------------------------------------------------------------------


class TestStaticResolver:
    def test_static_resolves_inline_symbols(self):
        config = {
            "universe": {
                "source": "static",
                "symbols": [
                    {"symbol": "AAPL", "asset_type": "equity", "asset_class": "equity"},
                    {"symbol": "MSFT", "asset_type": "equity", "asset_class": "equity"},
                ],
            }
        }
        assets, snapshot = resolve_universe(config, AS_OF)
        assert snapshot.source == "static"
        assert snapshot.resolver == "static"
        assert snapshot.resolved_count == 2
        assert [a.symbol for a in assets] == ["AAPL", "MSFT"]

    def test_static_empty_symbols_raises(self):
        config = {"universe": {"source": "static", "symbols": []}}
        with pytest.raises(ValueError, match="zero assets"):
            resolve_universe(config, AS_OF)


# ---------------------------------------------------------------------------
# resolve_universe — legacy backward compatibility
# ---------------------------------------------------------------------------


class TestLegacyCompat:
    def test_legacy_assets_config_works(self):
        config = {
            "assets": [
                {"symbol": "BTC-USD", "asset_type": "crypto"},
                {"symbol": "ETH-USD", "asset_type": "crypto"},
            ]
        }
        assets, snapshot = resolve_universe(config, AS_OF)
        assert snapshot.source == "legacy_assets_config"
        assert snapshot.resolver == "static"
        assert snapshot.resolved_count == 2

    def test_universe_takes_precedence_over_legacy(self):
        config = {
            "universe": {"source": "crypto_major"},
            "assets": [{"symbol": "AAPL", "asset_type": "equity"}],
        }
        assets, snapshot = resolve_universe(config, AS_OF)
        assert snapshot.source == "crypto_major"  # universe wins


# ---------------------------------------------------------------------------
# Determinism
# ---------------------------------------------------------------------------


class TestDeterminism:
    def test_same_config_same_result(self):
        config = {"universe": {"source": "nasdaq_100_sample", "exclude": ["TSLA"]}}
        a1, s1 = resolve_universe(config, AS_OF)
        a2, s2 = resolve_universe(config, AS_OF)
        assert [a.symbol for a in a1] == [a.symbol for a in a2]
        assert s1.resolved_count == s2.resolved_count
        assert s1.excluded_symbols == s2.excluded_symbols

    def test_ordering_is_stable(self):
        config = {"universe": {"source": "sp500_top20"}}
        a1, _ = resolve_universe(config, AS_OF)
        a2, _ = resolve_universe(config, AS_OF)
        assert [a.symbol for a in a1] == [a.symbol for a in a2]


# ---------------------------------------------------------------------------
# Snapshot
# ---------------------------------------------------------------------------


class TestSnapshot:
    def test_snapshot_fields_complete(self):
        config = {"universe": {"source": "crypto_major"}}
        _, snapshot = resolve_universe(config, AS_OF)
        assert isinstance(snapshot, UniverseSnapshot)
        assert snapshot.as_of_utc == AS_OF
        assert snapshot.source == "crypto_major"
        assert snapshot.resolver == "builtin"
        assert isinstance(snapshot.resolved_assets, list)
        assert all("symbol" in a for a in snapshot.resolved_assets)
        assert all("asset_type" in a for a in snapshot.resolved_assets)
        assert all("asset_class" in a for a in snapshot.resolved_assets)
        assert snapshot.resolved_count == len(snapshot.resolved_assets)

    def test_snapshot_to_dict_has_version(self):
        config = {"universe": {"source": "crypto_major"}}
        _, snapshot = resolve_universe(config, AS_OF)
        d = snapshot.to_dict()
        assert d["version"] == "v1"
        assert d["source"] == "crypto_major"
        assert d["resolved_count"] == snapshot.resolved_count


# ---------------------------------------------------------------------------
# build_research_universe returns 5-tuple
# ---------------------------------------------------------------------------


class TestBuildResearchUniverse:
    def test_returns_5_tuple(self):
        result = build_research_universe(None)
        assert len(result) == 5
        assets, intervals, date_range_fn, as_of_utc, snapshot = result
        assert isinstance(snapshot, UniverseSnapshot)
        assert len(assets) > 0

    def test_intervals_from_config(self):
        config = {"intervals": ["1d"], "universe": {"source": "crypto_major"}}
        _, intervals, _, _, _ = build_research_universe(config)
        assert intervals == ["1d"]
