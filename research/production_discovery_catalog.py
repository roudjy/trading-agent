"""Read-only production discovery seed for QRE candidate discovery.

This module is catalog/scaffold only. It does not register executable
strategies, launch campaigns, or grant paper/shadow/live authority.
"""

from __future__ import annotations

from dataclasses import dataclass
from itertools import cycle
from typing import Final


SCHEMA_VERSION: Final[int] = 1
MODULE_VERSION: Final[str] = "v1-production-discovery-seed-2026-06-05"
REGION_ORDER: Final[tuple[str, ...]] = (
    "NL/EU",
    "US",
    "Asia/proxies",
    "ETFs/context",
)


@dataclass(frozen=True)
class DiscoveryAsset:
    symbol: str
    canonical_instrument_id: str
    display_name: str
    region: str
    country: str
    exchange: str
    asset_class: str
    currency: str
    sector: str
    industry: str
    liquidity_tier: str
    data_source: str
    source_quality_status: str
    enabled_for_discovery: bool
    enabled_for_validation: bool
    not_alpha_claim: bool
    paper_activation_allowed: bool
    shadow_activation_allowed: bool
    live_activation_allowed: bool
    notes: str

    def to_payload(self) -> dict[str, object]:
        return {
            "symbol": self.symbol,
            "canonical_instrument_id": self.canonical_instrument_id,
            "display_name": self.display_name,
            "region": self.region,
            "country": self.country,
            "exchange": self.exchange,
            "asset_class": self.asset_class,
            "currency": self.currency,
            "sector": self.sector,
            "industry": self.industry,
            "liquidity_tier": self.liquidity_tier,
            "data_source": self.data_source,
            "source_quality_status": self.source_quality_status,
            "enabled_for_discovery": self.enabled_for_discovery,
            "enabled_for_validation": self.enabled_for_validation,
            "not_alpha_claim": self.not_alpha_claim,
            "paper_activation_allowed": self.paper_activation_allowed,
            "shadow_activation_allowed": self.shadow_activation_allowed,
            "live_activation_allowed": self.live_activation_allowed,
            "notes": self.notes,
        }


@dataclass(frozen=True)
class DiscoveryPreset:
    preset_id: str
    hypothesis_id: str
    behavior_family: str
    description: str
    allowed_asset_classes: tuple[str, ...]
    allowed_regions: tuple[str, ...]
    allowed_timeframes: tuple[str, ...]
    required_data_quality: str
    min_history_bars: int
    expected_failure_modes: tuple[str, ...]
    selection_reason: str
    enabled_for_discovery: bool
    enabled_for_validation: bool
    not_alpha_claim: bool
    paper_activation_allowed: bool
    shadow_activation_allowed: bool
    live_activation_allowed: bool

    def to_payload(self) -> dict[str, object]:
        return {
            "preset_id": self.preset_id,
            "hypothesis_id": self.hypothesis_id,
            "behavior_family": self.behavior_family,
            "description": self.description,
            "allowed_asset_classes": list(self.allowed_asset_classes),
            "allowed_regions": list(self.allowed_regions),
            "allowed_timeframes": list(self.allowed_timeframes),
            "required_data_quality": self.required_data_quality,
            "min_history_bars": self.min_history_bars,
            "expected_failure_modes": list(self.expected_failure_modes),
            "selection_reason": self.selection_reason,
            "enabled_for_discovery": self.enabled_for_discovery,
            "enabled_for_validation": self.enabled_for_validation,
            "not_alpha_claim": self.not_alpha_claim,
            "paper_activation_allowed": self.paper_activation_allowed,
            "shadow_activation_allowed": self.shadow_activation_allowed,
            "live_activation_allowed": self.live_activation_allowed,
        }


def _asset(
    symbol: str,
    *,
    display_name: str,
    region: str,
    country: str,
    exchange: str,
    currency: str,
    sector: str,
    industry: str,
    notes: str,
    asset_class: str = "equity",
    liquidity_tier: str = "high",
    data_source: str = "existing_data_boundary",
    source_quality_status: str = "reviewed_seed_only",
) -> DiscoveryAsset:
    return DiscoveryAsset(
        symbol=symbol,
        canonical_instrument_id=f"{exchange}:{symbol}",
        display_name=display_name,
        region=region,
        country=country,
        exchange=exchange,
        asset_class=asset_class,
        currency=currency,
        sector=sector,
        industry=industry,
        liquidity_tier=liquidity_tier,
        data_source=data_source,
        source_quality_status=source_quality_status,
        enabled_for_discovery=True,
        enabled_for_validation=True,
        not_alpha_claim=True,
        paper_activation_allowed=False,
        shadow_activation_allowed=False,
        live_activation_allowed=False,
        notes=notes,
    )


_ASSETS: Final[tuple[DiscoveryAsset, ...]] = (
    _asset("ASML", display_name="ASML Holding", region="NL/EU", country="Netherlands", exchange="NASDAQ", currency="USD", sector="Technology", industry="Semiconductor Equipment", notes="Dutch large-cap semiconductor equipment anchor."),
    _asset("ASMI", display_name="ASM International", region="NL/EU", country="Netherlands", exchange="EURONEXT", currency="EUR", sector="Technology", industry="Semiconductor Equipment", notes="Dutch semiconductor equipment exposure."),
    _asset("BESI", display_name="BE Semiconductor", region="NL/EU", country="Netherlands", exchange="EURONEXT", currency="EUR", sector="Technology", industry="Semiconductor Equipment", notes="Dutch semiconductor packaging exposure."),
    _asset("ADYEN", display_name="Adyen", region="NL/EU", country="Netherlands", exchange="EURONEXT", currency="EUR", sector="Financial Technology", industry="Payments", notes="Dutch fintech large-cap seed."),
    _asset("ING", display_name="ING Group", region="NL/EU", country="Netherlands", exchange="NYSE", currency="USD", sector="Financials", industry="Banking", notes="Banking regime anchor for Europe."),
    _asset("SHELL", display_name="Shell", region="NL/EU", country="United Kingdom", exchange="NYSE", currency="USD", sector="Energy", industry="Integrated Oil & Gas", notes="Europe energy supermajor proxy."),
    _asset("PRX", display_name="Prosus", region="NL/EU", country="Netherlands", exchange="EURONEXT", currency="EUR", sector="Communication Services", industry="Internet Holdings", notes="Dutch internet holding exposure."),
    _asset("SAP", display_name="SAP", region="NL/EU", country="Germany", exchange="NYSE", currency="USD", sector="Technology", industry="Enterprise Software", notes="Europe software leadership seed."),
    _asset("SIE", display_name="Siemens", region="NL/EU", country="Germany", exchange="XETRA", currency="EUR", sector="Industrials", industry="Industrial Conglomerates", notes="Europe industrial trend seed."),
    _asset("LVMH", display_name="LVMH", region="NL/EU", country="France", exchange="EURONEXT", currency="EUR", sector="Consumer Discretionary", industry="Luxury Goods", notes="Europe consumer leadership seed."),
    _asset("NOVO-B", display_name="Novo Nordisk", region="NL/EU", country="Denmark", exchange="NYSE", currency="USD", sector="Health Care", industry="Pharmaceuticals", notes="Europe health-care leadership seed."),
    _asset("AIR", display_name="Airbus", region="NL/EU", country="France", exchange="EURONEXT", currency="EUR", sector="Industrials", industry="Aerospace & Defense", notes="Europe aerospace cycle seed."),
    _asset("TTE", display_name="TotalEnergies", region="NL/EU", country="France", exchange="NYSE", currency="USD", sector="Energy", industry="Integrated Oil & Gas", notes="Europe energy trend seed."),
    _asset("IFX", display_name="Infineon", region="NL/EU", country="Germany", exchange="XETRA", currency="EUR", sector="Technology", industry="Semiconductors", notes="Europe semiconductor cycle seed."),
    _asset("NESN", display_name="Nestle", region="NL/EU", country="Switzerland", exchange="SIX", currency="CHF", sector="Consumer Staples", industry="Packaged Foods", notes="Defensive Europe large-cap seed."),
    _asset("AAPL", display_name="Apple", region="US", country="United States", exchange="NASDAQ", currency="USD", sector="Technology", industry="Consumer Electronics", notes="US mega-cap leadership anchor."),
    _asset("MSFT", display_name="Microsoft", region="US", country="United States", exchange="NASDAQ", currency="USD", sector="Technology", industry="Software", notes="US mega-cap software anchor."),
    _asset("NVDA", display_name="NVIDIA", region="US", country="United States", exchange="NASDAQ", currency="USD", sector="Technology", industry="Semiconductors", notes="US semiconductor momentum seed."),
    _asset("AMD", display_name="AMD", region="US", country="United States", exchange="NASDAQ", currency="USD", sector="Technology", industry="Semiconductors", notes="US semiconductor challenger seed."),
    _asset("GOOGL", display_name="Alphabet", region="US", country="United States", exchange="NASDAQ", currency="USD", sector="Communication Services", industry="Internet Services", notes="US internet leadership seed."),
    _asset("META", display_name="Meta Platforms", region="US", country="United States", exchange="NASDAQ", currency="USD", sector="Communication Services", industry="Internet Services", notes="US platform momentum seed."),
    _asset("AMZN", display_name="Amazon", region="US", country="United States", exchange="NASDAQ", currency="USD", sector="Consumer Discretionary", industry="E-Commerce", notes="US consumer platform leadership seed."),
    _asset("TSLA", display_name="Tesla", region="US", country="United States", exchange="NASDAQ", currency="USD", sector="Consumer Discretionary", industry="Automobiles", notes="US high-beta EV seed."),
    _asset("AVGO", display_name="Broadcom", region="US", country="United States", exchange="NASDAQ", currency="USD", sector="Technology", industry="Semiconductors", notes="US infrastructure semiconductor seed."),
    _asset("JPM", display_name="JPMorgan Chase", region="US", country="United States", exchange="NYSE", currency="USD", sector="Financials", industry="Banking", notes="US financial regime anchor."),
    _asset("XOM", display_name="Exxon Mobil", region="US", country="United States", exchange="NYSE", currency="USD", sector="Energy", industry="Integrated Oil & Gas", notes="US energy large-cap seed."),
    _asset("COST", display_name="Costco", region="US", country="United States", exchange="NASDAQ", currency="USD", sector="Consumer Staples", industry="Retail", notes="US defensive consumer leader."),
    _asset("TSM", display_name="Taiwan Semiconductor", region="Asia/proxies", country="Taiwan", exchange="NYSE", currency="USD", sector="Technology", industry="Semiconductors", notes="Asia semiconductor foundry anchor."),
    _asset("TM", display_name="Toyota Motor", region="Asia/proxies", country="Japan", exchange="NYSE", currency="USD", sector="Consumer Discretionary", industry="Automobiles", notes="Japan industrial/export proxy."),
    _asset("SONY", display_name="Sony Group", region="Asia/proxies", country="Japan", exchange="NYSE", currency="USD", sector="Consumer Discretionary", industry="Consumer Electronics", notes="Japan electronics/media proxy."),
    _asset("BABA", display_name="Alibaba", region="Asia/proxies", country="China", exchange="NYSE", currency="USD", sector="Consumer Discretionary", industry="E-Commerce", notes="China internet proxy."),
    _asset("TCEHY", display_name="Tencent", region="Asia/proxies", country="China", exchange="OTC", currency="USD", sector="Communication Services", industry="Internet Services", notes="China platform proxy via ADR/OTC."),
    _asset("INFY", display_name="Infosys", region="Asia/proxies", country="India", exchange="NYSE", currency="USD", sector="Technology", industry="IT Services", notes="India IT services proxy."),
    _asset("SPY", display_name="SPDR S&P 500 ETF", region="ETFs/context", country="United States", exchange="NYSEARCA", currency="USD", sector="Multi-sector", industry="Broad Market ETF", notes="US benchmark context ETF.", asset_class="etf"),
    _asset("QQQ", display_name="Invesco QQQ Trust", region="ETFs/context", country="United States", exchange="NASDAQ", currency="USD", sector="Technology", industry="Nasdaq 100 ETF", notes="US growth benchmark ETF.", asset_class="etf"),
    _asset("SMH", display_name="VanEck Semiconductor ETF", region="ETFs/context", country="United States", exchange="NASDAQ", currency="USD", sector="Technology", industry="Semiconductor ETF", notes="Semiconductor context ETF.", asset_class="etf"),
    _asset("VGK", display_name="Vanguard FTSE Europe ETF", region="ETFs/context", country="Europe", exchange="NYSEARCA", currency="USD", sector="Multi-sector", industry="Europe Equity ETF", notes="Europe benchmark context ETF.", asset_class="etf"),
    _asset("EWJ", display_name="iShares MSCI Japan ETF", region="ETFs/context", country="Japan", exchange="NYSEARCA", currency="USD", sector="Multi-sector", industry="Japan Equity ETF", notes="Japan benchmark context ETF.", asset_class="etf"),
    _asset("EWT", display_name="iShares MSCI Taiwan ETF", region="ETFs/context", country="Taiwan", exchange="NYSEARCA", currency="USD", sector="Multi-sector", industry="Taiwan Equity ETF", notes="Taiwan benchmark context ETF.", asset_class="etf"),
    _asset("EWY", display_name="iShares MSCI South Korea ETF", region="ETFs/context", country="South Korea", exchange="NYSEARCA", currency="USD", sector="Multi-sector", industry="Korea Equity ETF", notes="Korea benchmark context ETF.", asset_class="etf"),
    _asset("INDA", display_name="iShares MSCI India ETF", region="ETFs/context", country="India", exchange="NYSEARCA", currency="USD", sector="Multi-sector", industry="India Equity ETF", notes="India benchmark context ETF.", asset_class="etf"),
)


_PRESETS: Final[tuple[DiscoveryPreset, ...]] = (
    DiscoveryPreset(
        preset_id="trend_continuation_daily_v1",
        hypothesis_id="trend_continuation_behavior_v1",
        behavior_family="trend_continuation",
        description="Persistent trend continuation after shallow pullbacks in liquid equities.",
        allowed_asset_classes=("equity", "etf"),
        allowed_regions=("NL/EU", "US", "Asia/proxies", "ETFs/context"),
        allowed_timeframes=("1d",),
        required_data_quality="reviewed_seed_only",
        min_history_bars=750,
        expected_failure_modes=("insufficient_trades", "late_trend_entry", "trend_break_reversal"),
        selection_reason="Baseline trend research across liquid regions.",
        enabled_for_discovery=True,
        enabled_for_validation=True,
        not_alpha_claim=True,
        paper_activation_allowed=False,
        shadow_activation_allowed=False,
        live_activation_allowed=False,
    ),
    DiscoveryPreset(
        preset_id="trend_pullback_continuation_daily_v1",
        hypothesis_id="trend_pullback_behavior_v1",
        behavior_family="trend_pullback",
        description="Trend continuation after a volatility-normalized pullback.",
        allowed_asset_classes=("equity",),
        allowed_regions=("NL/EU", "US", "Asia/proxies"),
        allowed_timeframes=("1d",),
        required_data_quality="reviewed_seed_only",
        min_history_bars=750,
        expected_failure_modes=("insufficient_trades", "no_oos_trades", "weak_follow_through"),
        selection_reason="Extends current trend-pullback research to broader regions without execution authority.",
        enabled_for_discovery=True,
        enabled_for_validation=True,
        not_alpha_claim=True,
        paper_activation_allowed=False,
        shadow_activation_allowed=False,
        live_activation_allowed=False,
    ),
    DiscoveryPreset(
        preset_id="vol_compression_breakout_daily_v1",
        hypothesis_id="vol_compression_expansion_behavior_v1",
        behavior_family="volatility_compression_breakout",
        description="Daily compression to expansion behavior in liquid leadership names.",
        allowed_asset_classes=("equity", "etf"),
        allowed_regions=("NL/EU", "US", "Asia/proxies", "ETFs/context"),
        allowed_timeframes=("1d",),
        required_data_quality="reviewed_seed_only",
        min_history_bars=750,
        expected_failure_modes=("false_breakout", "insufficient_trades", "post_breakout_mean_reversion"),
        selection_reason="Provides a non-trend-only discovery family for autonomous research.",
        enabled_for_discovery=True,
        enabled_for_validation=True,
        not_alpha_claim=True,
        paper_activation_allowed=False,
        shadow_activation_allowed=False,
        live_activation_allowed=False,
    ),
    DiscoveryPreset(
        preset_id="vol_compression_breakout_4h_v1",
        hypothesis_id="vol_compression_expansion_behavior_v1",
        behavior_family="volatility_compression_breakout",
        description="4h compression to expansion behavior for liquid leadership and context ETFs.",
        allowed_asset_classes=("equity", "etf"),
        allowed_regions=("US", "ETFs/context"),
        allowed_timeframes=("4h",),
        required_data_quality="reviewed_seed_only",
        min_history_bars=1200,
        expected_failure_modes=("insufficient_trades", "microstructure_noise", "failed_breakout"),
        selection_reason="Higher-frequency breakout companion for bounded controlled validation routing.",
        enabled_for_discovery=True,
        enabled_for_validation=True,
        not_alpha_claim=True,
        paper_activation_allowed=False,
        shadow_activation_allowed=False,
        live_activation_allowed=False,
    ),
    DiscoveryPreset(
        preset_id="relative_strength_vs_sector_daily_v1",
        hypothesis_id="relative_strength_sector_behavior_v1",
        behavior_family="relative_strength_sector",
        description="Leadership persistence versus sector peers in liquid equities.",
        allowed_asset_classes=("equity",),
        allowed_regions=("NL/EU", "US"),
        allowed_timeframes=("1d",),
        required_data_quality="reviewed_seed_only",
        min_history_bars=750,
        expected_failure_modes=("leader_rotation", "no_oos_trades", "sector_mean_reversion"),
        selection_reason="Tests whether sector leadership can seed differentiated candidates.",
        enabled_for_discovery=True,
        enabled_for_validation=True,
        not_alpha_claim=True,
        paper_activation_allowed=False,
        shadow_activation_allowed=False,
        live_activation_allowed=False,
    ),
    DiscoveryPreset(
        preset_id="relative_strength_vs_region_daily_v1",
        hypothesis_id="relative_strength_region_behavior_v1",
        behavior_family="relative_strength_region",
        description="Persistent relative strength versus regional benchmarks and peers.",
        allowed_asset_classes=("equity", "etf"),
        allowed_regions=("NL/EU", "US", "Asia/proxies", "ETFs/context"),
        allowed_timeframes=("1d",),
        required_data_quality="reviewed_seed_only",
        min_history_bars=750,
        expected_failure_modes=("benchmark_reversal", "insufficient_trades", "relative_strength_decay"),
        selection_reason="Adds cross-region leadership behavior without executable authority.",
        enabled_for_discovery=True,
        enabled_for_validation=True,
        not_alpha_claim=True,
        paper_activation_allowed=False,
        shadow_activation_allowed=False,
        live_activation_allowed=False,
    ),
    DiscoveryPreset(
        preset_id="post_shock_stabilization_daily_v1",
        hypothesis_id="post_shock_stabilization_behavior_v1",
        behavior_family="post_shock_stabilization",
        description="Recovery and stabilization behavior after sharp dislocations.",
        allowed_asset_classes=("equity", "etf"),
        allowed_regions=("NL/EU", "US", "Asia/proxies", "ETFs/context"),
        allowed_timeframes=("1d",),
        required_data_quality="reviewed_seed_only",
        min_history_bars=900,
        expected_failure_modes=("aftershock_instability", "no_oos_trades", "insufficient_trades"),
        selection_reason="Supports research into post-dislocation recovery regimes.",
        enabled_for_discovery=True,
        enabled_for_validation=True,
        not_alpha_claim=True,
        paper_activation_allowed=False,
        shadow_activation_allowed=False,
        live_activation_allowed=False,
    ),
    DiscoveryPreset(
        preset_id="index_regime_filter_daily_v1",
        hypothesis_id="index_regime_filter_behavior_v1",
        behavior_family="regime_context_filter",
        description="Index and sector context filter for regime-aware candidate selection.",
        allowed_asset_classes=("equity", "etf"),
        allowed_regions=("NL/EU", "US", "Asia/proxies", "ETFs/context"),
        allowed_timeframes=("1d",),
        required_data_quality="reviewed_seed_only",
        min_history_bars=900,
        expected_failure_modes=("weak_signal_specificity", "regime_flip", "benchmark_noise"),
        selection_reason="Provides read-only regime context alongside directional behaviors.",
        enabled_for_discovery=True,
        enabled_for_validation=True,
        not_alpha_claim=True,
        paper_activation_allowed=False,
        shadow_activation_allowed=False,
        live_activation_allowed=False,
    ),
)


def list_assets() -> list[DiscoveryAsset]:
    return list(_ASSETS)


def list_presets() -> list[DiscoveryPreset]:
    return list(_PRESETS)


def _asset_matches_preset(asset: DiscoveryAsset, preset: DiscoveryPreset) -> bool:
    return (
        asset.enabled_for_discovery
        and asset.asset_class in preset.allowed_asset_classes
        and asset.region in preset.allowed_regions
        and asset.source_quality_status == preset.required_data_quality
    )


def build_bounded_candidate_basket(*, max_candidates: int = 15) -> list[dict[str, object]]:
    if max_candidates <= 0:
        return []

    presets = list_presets()
    candidate_lists = [
        [asset for asset in list_assets() if _asset_matches_preset(asset, preset)]
        for preset in presets
    ]
    if not any(candidate_lists):
        return []

    counters = [0] * len(presets)
    basket: list[dict[str, object]] = []
    seen: set[tuple[str, str]] = set()
    region_offsets = {region: 0 for region in REGION_ORDER}

    for preset_index in cycle(range(len(presets))):
        preset = presets[preset_index]
        matches = candidate_lists[preset_index]
        if not matches:
            continue
        selected: DiscoveryAsset | None = None
        preferred_regions = REGION_ORDER[preset_index % len(REGION_ORDER) :] + REGION_ORDER[
            : preset_index % len(REGION_ORDER)
        ]
        for region in preferred_regions:
            region_matches = [asset for asset in matches if asset.region == region]
            if not region_matches:
                continue
            start_index = region_offsets[region]
            for offset in range(len(region_matches)):
                asset = region_matches[(start_index + offset) % len(region_matches)]
                key = (preset.preset_id, asset.symbol)
                if key not in seen:
                    selected = asset
                    region_offsets[region] = start_index + offset + 1
                    counters[preset_index] += 1
                    seen.add(key)
                    break
            if selected is not None:
                break
        if selected is None:
            start_index = counters[preset_index]
            for offset in range(len(matches)):
                asset = matches[(start_index + offset) % len(matches)]
                key = (preset.preset_id, asset.symbol)
                if key not in seen:
                    selected = asset
                    counters[preset_index] = start_index + offset + 1
                    seen.add(key)
                    break
        if selected is None:
            if len(seen) == sum(len(items) for items in candidate_lists):
                break
            continue
        basket.append(
            {
                "candidate_id": f"seed::{preset.preset_id}::{selected.symbol}",
                "symbol": selected.symbol,
                "region": selected.region,
                "asset_class": selected.asset_class,
                "preset_id": preset.preset_id,
                "hypothesis_id": preset.hypothesis_id,
                "behavior_family": preset.behavior_family,
                "timeframes": list(preset.allowed_timeframes),
                "enabled_for_discovery": True,
                "enabled_for_validation": True,
                "not_alpha_claim": True,
                "paper_activation_allowed": False,
                "shadow_activation_allowed": False,
                "live_activation_allowed": False,
            }
        )
        if len(basket) >= max_candidates:
            break

    return basket


def production_discovery_catalog_payload(*, max_candidates: int = 15) -> dict[str, object]:
    return {
        "schema_version": SCHEMA_VERSION,
        "module_version": MODULE_VERSION,
        "assets": [asset.to_payload() for asset in list_assets()],
        "presets": [preset.to_payload() for preset in list_presets()],
        "bounded_candidate_basket": build_bounded_candidate_basket(
            max_candidates=max_candidates
        ),
        "read_only": True,
        "not_alpha_claim": True,
        "paper_activation_allowed": False,
        "shadow_activation_allowed": False,
        "live_activation_allowed": False,
    }
