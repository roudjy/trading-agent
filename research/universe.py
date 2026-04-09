"""
Research universe:
centrale bron voor assets, intervallen en datumrange-beleid.
"""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any


@dataclass(frozen=True)
class ResearchAsset:
    symbol: str
    asset_type: str


ASSETS = [
    ResearchAsset(symbol="BTC-USD", asset_type="crypto"),
    ResearchAsset(symbol="ETH-USD", asset_type="crypto"),
]

INTERVALS = ["1h", "4h"]


def get_date_range(interval):
    now = datetime.now(UTC)

    if interval in ["1h", "4h"]:
        start = now - timedelta(days=700)
    else:
        start = now - timedelta(days=1500)

    return start.strftime("%Y-%m-%d"), now.strftime("%Y-%m-%d")


def resolve_as_of_utc(research_config: dict[str, Any] | None = None) -> datetime:
    research_config = research_config or {}
    as_of_utc = research_config.get("as_of_utc")
    if as_of_utc:
        return datetime.fromisoformat(as_of_utc.replace("Z", "+00:00")).astimezone(UTC)
    return datetime.now(UTC)


def build_research_universe(research_config: dict[str, Any] | None = None):
    research_config = research_config or {}
    as_of_utc = resolve_as_of_utc(research_config)

    asset_configs = research_config.get("assets")
    if asset_configs:
        assets = [
            ResearchAsset(
                symbol=asset["symbol"],
                asset_type=asset.get("asset_type", "unknown"),
            )
            for asset in asset_configs
        ]
    else:
        assets = ASSETS

    intervals = research_config.get("intervals", INTERVALS)
    interval_lookbacks = research_config.get("interval_lookbacks", {})
    default_lookback_days = research_config.get("default_lookback_days", 1500)

    def date_range_for_interval(interval):
        lookback_days = interval_lookbacks.get(
            interval,
            700 if interval in ["1h", "4h"] else default_lookback_days,
        )
        start = as_of_utc - timedelta(days=lookback_days)
        return start.strftime("%Y-%m-%d"), as_of_utc.strftime("%Y-%m-%d")

    return assets, intervals, date_range_for_interval, as_of_utc
