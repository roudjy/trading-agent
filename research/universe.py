"""
Research universe:
centrale bron voor assets, intervallen en datumrange-beleid.
"""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta


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
