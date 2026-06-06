"""Deterministic research-only equity universe catalog."""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from typing import Any, Final

from packages.qre_research.equity_regions import (
    ASIA_DEVELOPED_COUNTRIES,
    EUROPE_COUNTRIES,
    NORDIC_COUNTRIES,
    QUALITY_SECTORS,
    UNIVERSE_DEFINITIONS,
)
from packages.qre_research.equity_universe_seed_data import SEED_ROWS


SCHEMA_VERSION: Final[str] = "1.0"
REPORT_KIND: Final[str] = "equity_universe_catalog"


@dataclass(frozen=True)
class EquityInstrument:
    canonical_id: str
    symbol: str
    provider_symbol: str
    candidate_provider_symbols: tuple[str, ...]
    display_name: str
    asset_class: str
    country: str
    macro_region: str
    exchange: str
    currency: str
    sector: str
    industry: str
    size_bucket: str
    liquidity_tier: str
    identity_confidence: str
    ambiguous_mapping_warning: str
    universe_ids: tuple[str, ...]
    research_only: bool = True

    def to_payload(self) -> dict[str, object]:
        return {
            "canonical_id": self.canonical_id,
            "symbol": self.symbol,
            "provider_symbol": self.provider_symbol,
            "candidate_provider_symbols": list(self.candidate_provider_symbols),
            "display_name": self.display_name,
            "asset_class": self.asset_class,
            "country": self.country,
            "macro_region": self.macro_region,
            "exchange": self.exchange,
            "currency": self.currency,
            "sector": self.sector,
            "industry": self.industry,
            "size_bucket": self.size_bucket,
            "liquidity_tier": self.liquidity_tier,
            "identity_confidence": self.identity_confidence,
            "ambiguous_mapping_warning": self.ambiguous_mapping_warning,
            "universe_ids": list(self.universe_ids),
            "research_only": self.research_only,
            "not_trade_signal": True,
            "paper_activation_allowed": False,
            "shadow_activation_allowed": False,
            "live_activation_allowed": False,
        }


def _macro_region(country: str) -> str:
    if country in EUROPE_COUNTRIES:
        return "Europe"
    if country == "United States":
        return "North America"
    if country == "Canada":
        return "North America"
    if country in ASIA_DEVELOPED_COUNTRIES:
        return "Asia Developed"
    return "Global"


def _universe_ids(row: dict[str, object]) -> tuple[str, ...]:
    country = str(row["country"])
    size_bucket = str(row["size_bucket"])
    sector = str(row["sector"])
    liquidity = str(row["liquidity_tier"])
    ids = {"global_ex_crypto_research_universe"}
    by_country = {
        "Netherlands": "nl_equities",
        "Belgium": "belgium_equities",
        "Germany": "germany_equities",
        "France": "france_equities",
        "Switzerland": "switzerland_equities",
        "United Kingdom": "uk_equities",
        "Canada": "canada_liquid_equities",
        "Japan": "japan_large_mid",
        "Hong Kong": "hong_kong_liquid_equities",
        "Singapore": "singapore_liquid_equities",
        "Australia": "australia_liquid_equities",
    }
    if country in by_country:
        ids.add(by_country[country])
    if country in NORDIC_COUNTRIES:
        ids.add("nordics_equities")
    if country in EUROPE_COUNTRIES:
        ids.add("europe_large_mid" if size_bucket == "large" else "europe_small_mid")
    if country == "United States":
        ids.add("us_large_mid")
        if liquidity == "high" and sector in QUALITY_SECTORS:
            ids.add("us_quality_liquid")
    if country in ASIA_DEVELOPED_COUNTRIES:
        ids.add("asia_developed_liquid")
    if liquidity in {"high", "medium"} and country in EUROPE_COUNTRIES | ASIA_DEVELOPED_COUNTRIES | {"United States", "Canada"}:
        ids.add("global_developed_liquid")
    return tuple(sorted(ids))


def list_equity_instruments() -> list[EquityInstrument]:
    instruments: list[EquityInstrument] = []
    for row in SEED_ROWS:
        provider_symbol = str(row.get("provider_symbol") or "")
        symbol = str(row["symbol"])
        exchange = str(row["exchange"])
        country = str(row["country"])
        instruments.append(
            EquityInstrument(
                canonical_id=f"{exchange}:{symbol}",
                symbol=symbol,
                provider_symbol=provider_symbol,
                candidate_provider_symbols=tuple(row.get("candidate_provider_symbols") or ()),
                display_name=str(row["name"]),
                asset_class="equity",
                country=country,
                macro_region=_macro_region(country),
                exchange=exchange,
                currency=str(row["currency"]),
                sector=str(row["sector"]),
                industry=str(row["industry"]),
                size_bucket=str(row["size_bucket"]),
                liquidity_tier=str(row["liquidity_tier"]),
                identity_confidence=str(row["identity_confidence"]),
                ambiguous_mapping_warning=str(row.get("ambiguous_mapping_warning") or ""),
                universe_ids=_universe_ids(row),
            )
        )
    instruments.sort(key=lambda item: (item.country, item.exchange, item.symbol))
    return instruments


def build_equity_universe_catalog() -> dict[str, object]:
    instruments = list_equity_instruments()
    return {
        "schema_version": SCHEMA_VERSION,
        "report_kind": REPORT_KIND,
        "summary": {
            "instrument_count": len(instruments),
            "country_count": len({item.country for item in instruments}),
            "exchange_count": len({item.exchange for item in instruments}),
            "currency_count": len({item.currency for item in instruments}),
            "universe_count": len(UNIVERSE_DEFINITIONS),
            "operator_summary": (
                "Deterministic static equity-universe metadata for QRE research intake only. "
                "Universe membership is research context, not a trade signal."
            ),
        },
        "universes": list(UNIVERSE_DEFINITIONS),
        "instruments": [item.to_payload() for item in instruments],
        "safety_invariants": {
            "research_only": True,
            "not_trade_signal": True,
            "mutates_registry": False,
            "mutates_frozen_contracts": False,
            "paper_shadow_live_forbidden": True,
            "broker_risk_execution_forbidden": True,
        },
    }


def build_equity_universe_summary() -> dict[str, object]:
    instruments = list_equity_instruments()
    universe_counts: dict[str, int] = Counter(
        universe_id for item in instruments for universe_id in item.universe_ids
    )
    country_counts: dict[str, int] = Counter(item.country for item in instruments)
    exchange_counts: dict[str, int] = Counter(item.exchange for item in instruments)
    currency_counts: dict[str, int] = Counter(item.currency for item in instruments)
    universe_countries: dict[str, set[str]] = defaultdict(set)
    universe_currencies: dict[str, set[str]] = defaultdict(set)
    for item in instruments:
        for universe_id in item.universe_ids:
            universe_countries[universe_id].add(item.country)
            universe_currencies[universe_id].add(item.currency)
    return {
        "schema_version": SCHEMA_VERSION,
        "report_kind": "equity_universe_summary",
        "summary": {
            "total_instruments": len(instruments),
            "total_countries": len(country_counts),
            "total_exchanges": len(exchange_counts),
            "total_currencies": len(currency_counts),
        },
        "universe_counts": dict(sorted(universe_counts.items())),
        "country_counts": dict(sorted(country_counts.items())),
        "exchange_counts": dict(sorted(exchange_counts.items())),
        "currency_counts": dict(sorted(currency_counts.items())),
        "largest_universes": [
            {
                "universe_id": universe_id,
                "instrument_count": universe_counts[universe_id],
                "countries": sorted(universe_countries[universe_id]),
                "primary_currencies": sorted(universe_currencies[universe_id]),
            }
            for universe_id in sorted(universe_counts, key=lambda item: (-universe_counts[item], item))[:10]
        ],
    }

