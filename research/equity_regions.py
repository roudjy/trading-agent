"""Deterministic equity-universe region and grouping definitions."""

from __future__ import annotations

from typing import Final


UNIVERSE_DEFINITIONS: Final[tuple[dict[str, object], ...]] = (
    {"universe_id": "nl_equities", "region": "Netherlands", "kind": "country"},
    {"universe_id": "belgium_equities", "region": "Belgium", "kind": "country"},
    {"universe_id": "germany_equities", "region": "Germany", "kind": "country"},
    {"universe_id": "france_equities", "region": "France", "kind": "country"},
    {"universe_id": "switzerland_equities", "region": "Switzerland", "kind": "country"},
    {"universe_id": "nordics_equities", "region": "Nordics", "kind": "macro_region"},
    {"universe_id": "uk_equities", "region": "United Kingdom", "kind": "country"},
    {"universe_id": "europe_large_mid", "region": "Europe", "kind": "size_group"},
    {"universe_id": "europe_small_mid", "region": "Europe", "kind": "size_group"},
    {"universe_id": "us_large_mid", "region": "United States", "kind": "size_group"},
    {"universe_id": "us_quality_liquid", "region": "United States", "kind": "quality_group"},
    {"universe_id": "canada_liquid_equities", "region": "Canada", "kind": "country"},
    {"universe_id": "japan_large_mid", "region": "Japan", "kind": "country"},
    {"universe_id": "hong_kong_liquid_equities", "region": "Hong Kong", "kind": "country"},
    {"universe_id": "singapore_liquid_equities", "region": "Singapore", "kind": "country"},
    {"universe_id": "australia_liquid_equities", "region": "Australia", "kind": "country"},
    {"universe_id": "asia_developed_liquid", "region": "Asia Developed", "kind": "macro_region"},
    {"universe_id": "global_developed_liquid", "region": "Global Developed", "kind": "macro_region"},
    {"universe_id": "global_ex_crypto_research_universe", "region": "Global", "kind": "macro_region"},
)

NORDIC_COUNTRIES: Final[frozenset[str]] = frozenset(
    {"Denmark", "Sweden", "Norway", "Finland"}
)
EUROPE_COUNTRIES: Final[frozenset[str]] = frozenset(
    {
        "Netherlands",
        "Belgium",
        "Germany",
        "France",
        "Switzerland",
        "United Kingdom",
        "Italy",
        "Spain",
        "Denmark",
        "Sweden",
        "Norway",
        "Finland",
    }
)
ASIA_DEVELOPED_COUNTRIES: Final[frozenset[str]] = frozenset(
    {"Japan", "Hong Kong", "Singapore", "Australia"}
)
QUALITY_SECTORS: Final[frozenset[str]] = frozenset(
    {"Technology", "Health Care", "Financials", "Consumer Staples", "Industrials"}
)

