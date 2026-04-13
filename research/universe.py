"""
Research universe:
config-driven universe resolution with reproducible snapshots.

Supports:
- built-in named index/market universes (static constituent snapshots)
- static custom symbol lists from config
- legacy research.assets backward compatibility
- exclude/include modifiers
- universe snapshot for lineage/audit
"""

from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol


@dataclass(frozen=True)
class ResearchAsset:
    """A single research target."""

    symbol: str
    asset_type: str
    asset_class: str = ""


@dataclass(frozen=True)
class UniverseSnapshot:
    """Immutable record of a resolved universe for lineage."""

    source: str
    resolver: str
    as_of_utc: str
    requested_config: dict
    resolved_assets: list[dict]
    excluded_symbols: list[str]
    resolved_count: int

    def to_dict(self) -> dict[str, Any]:
        """Serialize for JSON sidecar."""
        return {
            "version": "v1",
            "generated_at_utc": self.as_of_utc,
            "source": self.source,
            "resolver": self.resolver,
            "requested_config": self.requested_config,
            "resolved_assets": self.resolved_assets,
            "excluded_symbols": self.excluded_symbols,
            "resolved_count": self.resolved_count,
        }


# ---------------------------------------------------------------------------
# Built-in index/market universe snapshots
# ---------------------------------------------------------------------------
# Names must reflect actual scope. Use _sample suffix for partial sets.

BUILTIN_UNIVERSES: dict[str, list[ResearchAsset]] = {
    "crypto_major": [
        ResearchAsset("BTC-USD", "crypto", "crypto"),
        ResearchAsset("ETH-USD", "crypto", "crypto"),
        ResearchAsset("SOL-USD", "crypto", "crypto"),
        ResearchAsset("BNB-USD", "crypto", "crypto"),
        ResearchAsset("ADA-USD", "crypto", "crypto"),
        ResearchAsset("DOT-USD", "crypto", "crypto"),
        ResearchAsset("LINK-USD", "crypto", "crypto"),
    ],
    "aex_sample": [
        ResearchAsset("ASML.AS", "equity", "equity"),
        ResearchAsset("SHELL.AS", "equity", "equity"),
        ResearchAsset("UNA.AS", "equity", "equity"),
        ResearchAsset("INGA.AS", "equity", "equity"),
        ResearchAsset("PHIA.AS", "equity", "equity"),
        ResearchAsset("ABN.AS", "equity", "equity"),
        ResearchAsset("WKL.AS", "equity", "equity"),
    ],
    "nasdaq_100_sample": [
        ResearchAsset("AAPL", "equity", "equity"),
        ResearchAsset("MSFT", "equity", "equity"),
        ResearchAsset("NVDA", "equity", "equity"),
        ResearchAsset("GOOGL", "equity", "equity"),
        ResearchAsset("AMZN", "equity", "equity"),
        ResearchAsset("META", "equity", "equity"),
        ResearchAsset("TSLA", "equity", "equity"),
        ResearchAsset("AMD", "equity", "equity"),
        ResearchAsset("AVGO", "equity", "equity"),
        ResearchAsset("TSM", "equity", "equity"),
    ],
    "sp500_top20": [
        ResearchAsset("AAPL", "equity", "equity"),
        ResearchAsset("MSFT", "equity", "equity"),
        ResearchAsset("NVDA", "equity", "equity"),
        ResearchAsset("GOOGL", "equity", "equity"),
        ResearchAsset("AMZN", "equity", "equity"),
        ResearchAsset("META", "equity", "equity"),
        ResearchAsset("BRK-B", "equity", "equity"),
        ResearchAsset("LLY", "equity", "equity"),
        ResearchAsset("JPM", "equity", "equity"),
        ResearchAsset("V", "equity", "equity"),
        ResearchAsset("UNH", "equity", "equity"),
        ResearchAsset("XOM", "equity", "equity"),
        ResearchAsset("MA", "equity", "equity"),
        ResearchAsset("JNJ", "equity", "equity"),
        ResearchAsset("PG", "equity", "equity"),
        ResearchAsset("COST", "equity", "equity"),
        ResearchAsset("HD", "equity", "equity"),
        ResearchAsset("ABBV", "equity", "equity"),
        ResearchAsset("WMT", "equity", "equity"),
        ResearchAsset("NFLX", "equity", "equity"),
    ],
}

DEFAULT_SOURCE = "crypto_major"
DEFAULT_INTERVALS = ["1h", "4h"]


# ---------------------------------------------------------------------------
# Resolver protocol and implementations
# ---------------------------------------------------------------------------


class UniverseResolver(Protocol):
    """Extension point for universe resolution."""

    def resolve(
        self, config: dict[str, Any], as_of_utc: str
    ) -> tuple[list[ResearchAsset], UniverseSnapshot]: ...


class BuiltinResolver:
    """Resolves named index/market universes from BUILTIN_UNIVERSES."""

    def resolve(
        self, config: dict[str, Any], as_of_utc: str
    ) -> tuple[list[ResearchAsset], UniverseSnapshot]:
        source = config["source"]
        if source not in BUILTIN_UNIVERSES:
            raise ValueError(
                f"Unknown built-in universe: {source!r}. "
                f"Available: {sorted(BUILTIN_UNIVERSES.keys())}"
            )
        base_assets = list(BUILTIN_UNIVERSES[source])
        assets, excluded = _apply_modifiers(base_assets, config)
        snapshot = _build_snapshot(
            source=source,
            resolver="builtin",
            as_of_utc=as_of_utc,
            config=config,
            assets=assets,
            excluded=excluded,
        )
        return assets, snapshot


class StaticResolver:
    """Resolves inline symbol lists from config."""

    def resolve(
        self, config: dict[str, Any], as_of_utc: str
    ) -> tuple[list[ResearchAsset], UniverseSnapshot]:
        symbols_config = config.get("symbols", [])
        base_assets = [
            ResearchAsset(
                symbol=entry["symbol"],
                asset_type=entry.get("asset_type", "unknown"),
                asset_class=entry.get("asset_class", ""),
            )
            for entry in symbols_config
        ]
        assets, excluded = _apply_modifiers(base_assets, config)
        snapshot = _build_snapshot(
            source="static",
            resolver="static",
            as_of_utc=as_of_utc,
            config=config,
            assets=assets,
            excluded=excluded,
        )
        return assets, snapshot


# ---------------------------------------------------------------------------
# Resolution helpers
# ---------------------------------------------------------------------------


def _apply_modifiers(
    base_assets: list[ResearchAsset], config: dict[str, Any]
) -> tuple[list[ResearchAsset], list[str]]:
    """Apply include/exclude modifiers. Returns (assets, excluded_symbols)."""
    exclude_set = set(config.get("exclude", []))

    # Add includes
    for entry in config.get("include", []):
        asset = ResearchAsset(
            symbol=entry["symbol"],
            asset_type=entry.get("asset_type", "unknown"),
            asset_class=entry.get("asset_class", ""),
        )
        base_assets.append(asset)

    # Dedup by symbol (first occurrence wins), then exclude
    seen: set[str] = set()
    assets: list[ResearchAsset] = []
    excluded: list[str] = []
    for asset in base_assets:
        if asset.symbol in seen:
            continue
        seen.add(asset.symbol)
        if asset.symbol in exclude_set:
            excluded.append(asset.symbol)
            continue
        assets.append(asset)

    # Record excludes that were requested but not found
    for symbol in sorted(exclude_set - set(excluded)):
        excluded.append(symbol)

    return assets, excluded


def _build_snapshot(
    source: str,
    resolver: str,
    as_of_utc: str,
    config: dict[str, Any],
    assets: list[ResearchAsset],
    excluded: list[str],
) -> UniverseSnapshot:
    return UniverseSnapshot(
        source=source,
        resolver=resolver,
        as_of_utc=as_of_utc,
        requested_config=dict(config),
        resolved_assets=[
            {"symbol": a.symbol, "asset_type": a.asset_type, "asset_class": a.asset_class}
            for a in assets
        ],
        excluded_symbols=excluded,
        resolved_count=len(assets),
    )


def _resolve_legacy_assets(
    asset_configs: list[dict], as_of_utc: str
) -> tuple[list[ResearchAsset], UniverseSnapshot]:
    """Convert legacy research.assets format to resolved universe."""
    assets = [
        ResearchAsset(
            symbol=entry["symbol"],
            asset_type=entry.get("asset_type", "unknown"),
            asset_class=entry.get("asset_class", ""),
        )
        for entry in asset_configs
    ]
    snapshot = _build_snapshot(
        source="legacy_assets_config",
        resolver="static",
        as_of_utc=as_of_utc,
        config={"assets": asset_configs},
        assets=assets,
        excluded=[],
    )
    return assets, snapshot


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

_BUILTIN_RESOLVER = BuiltinResolver()
_STATIC_RESOLVER = StaticResolver()


def resolve_universe(
    research_config: dict[str, Any] | None, as_of_utc: str
) -> tuple[list[ResearchAsset], UniverseSnapshot]:
    """Resolve universe from config. Pure function, no IO."""
    research_config = research_config or {}
    universe_config = research_config.get("universe")

    # New universe config format
    if universe_config is not None:
        source = universe_config.get("source", "")
        if source == "static":
            assets, snapshot = _STATIC_RESOLVER.resolve(universe_config, as_of_utc)
        elif source in BUILTIN_UNIVERSES:
            assets, snapshot = _BUILTIN_RESOLVER.resolve(universe_config, as_of_utc)
        elif source:
            raise ValueError(
                f"Unknown universe source: {source!r}. "
                f"Available built-in: {sorted(BUILTIN_UNIVERSES.keys())}. "
                f"Or use source: 'static' with a symbols list."
            )
        else:
            raise ValueError("research.universe.source is required")
        if not assets:
            raise ValueError(f"Universe {source!r} resolved to zero assets after modifiers")
        return assets, snapshot

    # Legacy research.assets format
    legacy_assets = research_config.get("assets")
    if legacy_assets:
        assets, snapshot = _resolve_legacy_assets(legacy_assets, as_of_utc)
        if not assets:
            raise ValueError("Legacy research.assets resolved to zero assets")
        return assets, snapshot

    # Default: crypto_major
    default_config = {"source": DEFAULT_SOURCE}
    return _BUILTIN_RESOLVER.resolve(default_config, as_of_utc)


def resolve_as_of_utc(research_config: dict[str, Any] | None = None) -> datetime:
    """Resolve the as-of timestamp for a research run."""
    research_config = research_config or {}
    as_of_utc = research_config.get("as_of_utc")
    if as_of_utc:
        return datetime.fromisoformat(as_of_utc.replace("Z", "+00:00")).astimezone(UTC)
    return datetime.now(UTC)


def build_research_universe(research_config: dict[str, Any] | None = None):
    """Build the full research universe tuple consumed by run_research.

    Returns (assets, intervals, date_range_fn, as_of_utc, snapshot).
    """
    research_config = research_config or {}
    as_of_utc = resolve_as_of_utc(research_config)
    assets, snapshot = resolve_universe(research_config, as_of_utc.isoformat())

    intervals = research_config.get("intervals", DEFAULT_INTERVALS)
    interval_lookbacks = research_config.get("interval_lookbacks", {})
    default_lookback_days = research_config.get("default_lookback_days", 1500)

    def date_range_for_interval(interval):
        lookback_days = interval_lookbacks.get(
            interval,
            700 if interval in ["1h", "4h"] else default_lookback_days,
        )
        start = as_of_utc - timedelta(days=lookback_days)
        return start.strftime("%Y-%m-%d"), as_of_utc.strftime("%Y-%m-%d")

    return assets, intervals, date_range_for_interval, as_of_utc, snapshot
