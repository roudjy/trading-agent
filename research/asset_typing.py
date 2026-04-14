from __future__ import annotations

from typing import Any

NORMALIZED_ASSET_TYPE_ALIASES: dict[str, str] = {
    "crypto": "crypto",
    "cryptocurrency": "crypto",
    "equity": "equity",
    "stock": "equity",
    "stocks": "equity",
    "future": "futures",
    "futures": "futures",
    "index": "index_like",
    "index_like": "index_like",
    "etf": "index_like",
}


def normalize_asset_type(*, asset_type: Any = None, asset_class: Any = None) -> str:
    explicit_type = str(asset_type or "").strip().lower()
    explicit_class = str(asset_class or "").strip().lower()
    if explicit_type in NORMALIZED_ASSET_TYPE_ALIASES:
        return NORMALIZED_ASSET_TYPE_ALIASES[explicit_type]
    if explicit_class in NORMALIZED_ASSET_TYPE_ALIASES:
        return NORMALIZED_ASSET_TYPE_ALIASES[explicit_class]
    return "unknown"
