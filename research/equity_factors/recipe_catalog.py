"""Deterministic research-only screener recipe catalog."""

from __future__ import annotations

from typing import Final

from research.equity_factors.factor_catalog import build_equity_factor_catalog
from research.equity_regions import UNIVERSE_DEFINITIONS


SCHEMA_VERSION: Final[str] = "1.0"
REPORT_KIND: Final[str] = "equity_factor_recipes"
OUTPUT_TYPE: Final[str] = "hypothesis_seed_candidates"
FORBIDDEN_OUTPUTS: Final[tuple[str, ...]] = (
    "buy_list",
    "sell_list",
    "trade_signal",
    "strategy_registration",
    "executable_strategy",
    "candidate_promotion",
    "paper_candidate",
    "shadow_candidate",
    "live_candidate",
    "capital_allocation",
    "broker_execution",
)
BLOCK_REASON_VOCABULARY: Final[tuple[str, ...]] = (
    "FEASIBLE",
    "BLOCKED_MISSING_UNIVERSE",
    "BLOCKED_MISSING_FACTOR",
    "BLOCKED_UNIVERSE_QUALITY_FAIL",
    "BLOCKED_IDENTITY_AMBIGUITY",
    "BLOCKED_DATA_READINESS_MISSING",
    "BLOCKED_FACTOR_FIELD_COVERAGE_MISSING",
    "BLOCKED_UNKNOWN",
)

RECIPE_ROWS: Final[tuple[dict[str, object], ...]] = (
    {
        "recipe_id": "asia_developed_quality_value_v0",
        "display_name": "Asia Developed Quality Value v0",
        "description": "Research-intake recipe for quality and valuation behaviors in Asia developed liquid equities.",
        "target_universe_ids": ["asia_developed_liquid"],
        "required_factor_ids": ["roic", "gross_profitability", "book_to_market", "earnings_yield"],
        "optional_factor_ids": ["six_month_momentum", "average_daily_value_traded"],
        "liquidity_gate": "high_or_medium",
        "size_gate": "large_mid",
        "identity_readiness_required": "OK",
        "universe_readiness_allowed": ["OK", "WARN"],
        "data_readiness_required": "fundamental_manifest_required",
        "ranking_components": ["quality_rank", "valuation_rank", "liquidity_guardrail"],
        "exclusion_rules": ["identity_ambiguity", "universe_quality_fail", "missing_required_factor_field"],
        "operator_explanation": "Research-only recipe for testing whether quality-plus-value behaviors deserve hypothesis intake in Asia developed universes.",
    },
    {
        "recipe_id": "defensive_quality_momentum_v0",
        "display_name": "Defensive Quality Momentum v0",
        "description": "Quality and defensive-stability intake recipe with momentum confirmation.",
        "target_universe_ids": ["global_developed_liquid"],
        "required_factor_ids": ["return_on_assets", "gross_profitability", "twelve_month_momentum"],
        "optional_factor_ids": ["dividend_yield", "average_daily_value_traded"],
        "liquidity_gate": "high",
        "size_gate": "large_mid",
        "identity_readiness_required": "OK",
        "universe_readiness_allowed": ["OK", "WARN"],
        "data_readiness_required": "fundamental_manifest_required",
        "ranking_components": ["quality_rank", "momentum_rank", "defensive_overlay"],
        "exclusion_rules": ["identity_ambiguity", "universe_quality_fail", "data_readiness_missing"],
        "operator_explanation": "Research-only recipe for defensive compounder behavior; not a buy list.",
    },
    {
        "recipe_id": "eu_quality_value_momentum_v0",
        "display_name": "Europe Quality Value Momentum v0",
        "description": "Broad Europe large/mid research recipe combining quality, value, and momentum components.",
        "target_universe_ids": ["europe_large_mid"],
        "required_factor_ids": ["roic", "earnings_yield", "twelve_month_momentum"],
        "optional_factor_ids": ["gross_profitability", "adjusted_slope"],
        "liquidity_gate": "high_or_medium",
        "size_gate": "large_mid",
        "identity_readiness_required": "OK",
        "universe_readiness_allowed": ["OK", "WARN"],
        "data_readiness_required": "fundamental_manifest_required",
        "ranking_components": ["quality_rank", "valuation_rank", "momentum_rank"],
        "exclusion_rules": ["identity_ambiguity", "source_manifest_missing", "currency_normalization_missing"],
        "operator_explanation": "Research-only intake recipe for Europe quality/value/momentum interactions.",
    },
    {
        "recipe_id": "europe_deep_value_financial_health_v0",
        "display_name": "Europe Deep Value Financial Health v0",
        "description": "Deep-value research intake with a financial-health guardrail for Europe.",
        "target_universe_ids": ["europe_large_mid", "europe_small_mid"],
        "required_factor_ids": ["book_to_market", "price_to_sales", "piotroski_f_score", "altman_z_score"],
        "optional_factor_ids": ["debt_to_equity", "net_debt_to_ebitda"],
        "liquidity_gate": "medium_or_high",
        "size_gate": "large_small_mid",
        "identity_readiness_required": "OK",
        "universe_readiness_allowed": ["OK", "WARN"],
        "data_readiness_required": "fundamental_manifest_required",
        "ranking_components": ["deep_value_rank", "financial_health_rank"],
        "exclusion_rules": ["identity_ambiguity", "universe_quality_fail", "restatement_policy_missing"],
        "operator_explanation": "Research-only deep-value intake recipe that blocks on weak accounting readiness.",
    },
    {
        "recipe_id": "europe_small_mid_quality_value_v0",
        "display_name": "Europe Small Mid Quality Value v0",
        "description": "Europe small/mid quality-plus-value intake recipe for later hypothesis screening.",
        "target_universe_ids": ["europe_small_mid"],
        "required_factor_ids": ["gross_profitability", "book_to_market", "accruals_ratio"],
        "optional_factor_ids": ["return_on_assets", "average_daily_value_traded"],
        "liquidity_gate": "medium_or_high",
        "size_gate": "small_mid",
        "identity_readiness_required": "OK",
        "universe_readiness_allowed": ["OK", "WARN"],
        "data_readiness_required": "fundamental_manifest_required",
        "ranking_components": ["quality_rank", "value_rank", "accounting_cleanliness_rank"],
        "exclusion_rules": ["identity_ambiguity", "field_coverage_missing"],
        "operator_explanation": "Research-only small/midcap intake recipe; no trade output is allowed.",
    },
    {
        "recipe_id": "global_developed_quality_momentum_v0",
        "display_name": "Global Developed Quality Momentum v0",
        "description": "Global developed quality and momentum intake recipe.",
        "target_universe_ids": ["global_developed_liquid"],
        "required_factor_ids": ["roic", "gross_profitability", "twelve_month_momentum"],
        "optional_factor_ids": ["adjusted_slope", "average_daily_value_traded"],
        "liquidity_gate": "high",
        "size_gate": "large_mid",
        "identity_readiness_required": "OK",
        "universe_readiness_allowed": ["OK", "WARN"],
        "data_readiness_required": "fundamental_manifest_required",
        "ranking_components": ["quality_rank", "momentum_rank"],
        "exclusion_rules": ["identity_ambiguity", "data_readiness_missing"],
        "operator_explanation": "Research-only global developed quality/momentum intake definition.",
    },
    {
        "recipe_id": "global_developed_value_quality_v0",
        "display_name": "Global Developed Value Quality v0",
        "description": "Global developed value-plus-quality intake recipe.",
        "target_universe_ids": ["global_developed_liquid"],
        "required_factor_ids": ["book_to_market", "earnings_yield", "return_on_assets"],
        "optional_factor_ids": ["fcf_yield", "gross_profitability"],
        "liquidity_gate": "high_or_medium",
        "size_gate": "large_mid",
        "identity_readiness_required": "OK",
        "universe_readiness_allowed": ["OK", "WARN"],
        "data_readiness_required": "fundamental_manifest_required",
        "ranking_components": ["value_rank", "quality_rank"],
        "exclusion_rules": ["identity_ambiguity", "point_in_time_policy_missing"],
        "operator_explanation": "Research-only value/quality intake recipe for global developed equities.",
    },
    {
        "recipe_id": "low_accrual_quality_v0",
        "display_name": "Low Accrual Quality v0",
        "description": "Accounting-quality intake recipe using low accruals and profitability signals.",
        "target_universe_ids": ["global_developed_liquid"],
        "required_factor_ids": ["accruals_ratio", "gross_profitability", "return_on_assets"],
        "optional_factor_ids": ["piotroski_f_score"],
        "liquidity_gate": "high_or_medium",
        "size_gate": "large_mid",
        "identity_readiness_required": "OK",
        "universe_readiness_allowed": ["OK", "WARN"],
        "data_readiness_required": "fundamental_manifest_required",
        "ranking_components": ["accounting_cleanliness_rank", "quality_rank"],
        "exclusion_rules": ["identity_ambiguity", "restatement_policy_missing"],
        "operator_explanation": "Research-only low-accrual quality intake recipe; blocked until accounting field coverage is known.",
    },
    {
        "recipe_id": "magic_formula_style_v0",
        "display_name": "Magic Formula Style v0",
        "description": "Research-only recipe inspired by EBIT yield plus return on capital ranking.",
        "target_universe_ids": ["global_developed_liquid"],
        "required_factor_ids": ["enterprise_value_to_ebit", "roic"],
        "optional_factor_ids": ["average_daily_value_traded"],
        "liquidity_gate": "high_or_medium",
        "size_gate": "large_mid",
        "identity_readiness_required": "OK",
        "universe_readiness_allowed": ["OK", "WARN"],
        "data_readiness_required": "fundamental_manifest_required",
        "ranking_components": ["value_rank", "quality_rank"],
        "exclusion_rules": ["identity_ambiguity", "enterprise_value_field_missing"],
        "operator_explanation": "Research-only intake recipe capturing magic-formula style behavior without creating tradable output.",
    },
    {
        "recipe_id": "nl_quality_large_liquid_v0",
        "display_name": "NL Quality Large Liquid v0",
        "description": "Netherlands quality and liquidity intake recipe for large liquid names.",
        "target_universe_ids": ["nl_equities"],
        "required_factor_ids": ["roic", "gross_profitability", "average_daily_value_traded"],
        "optional_factor_ids": ["return_on_assets", "dividend_yield"],
        "liquidity_gate": "high",
        "size_gate": "large",
        "identity_readiness_required": "OK",
        "universe_readiness_allowed": ["OK", "WARN"],
        "data_readiness_required": "fundamental_manifest_required",
        "ranking_components": ["quality_rank", "liquidity_rank"],
        "exclusion_rules": ["identity_ambiguity", "universe_quality_fail"],
        "operator_explanation": "Research-only Dutch large/liquid intake recipe. Universe membership is not a signal.",
    },
    {
        "recipe_id": "nordics_quality_compounders_v0",
        "display_name": "Nordics Quality Compounders v0",
        "description": "Nordics quality-compounder intake recipe.",
        "target_universe_ids": ["nordics_equities"],
        "required_factor_ids": ["roic", "gross_profitability", "twelve_month_momentum"],
        "optional_factor_ids": ["dividend_yield", "accruals_ratio"],
        "liquidity_gate": "high_or_medium",
        "size_gate": "large_mid",
        "identity_readiness_required": "OK",
        "universe_readiness_allowed": ["OK", "WARN"],
        "data_readiness_required": "fundamental_manifest_required",
        "ranking_components": ["quality_rank", "momentum_rank", "compounder_stability_rank"],
        "exclusion_rules": ["identity_ambiguity", "report_lag_policy_missing"],
        "operator_explanation": "Research-only Nordics quality-compounder intake definition.",
    },
    {
        "recipe_id": "piotroski_value_style_v0",
        "display_name": "Piotroski Value Style v0",
        "description": "Research-only value style recipe requiring Piotroski support.",
        "target_universe_ids": ["global_developed_liquid"],
        "required_factor_ids": ["book_to_market", "piotroski_f_score"],
        "optional_factor_ids": ["altman_z_score", "debt_to_equity"],
        "liquidity_gate": "high_or_medium",
        "size_gate": "large_mid",
        "identity_readiness_required": "OK",
        "universe_readiness_allowed": ["OK", "WARN"],
        "data_readiness_required": "fundamental_manifest_required",
        "ranking_components": ["value_rank", "financial_health_rank"],
        "exclusion_rules": ["identity_ambiguity", "multi_period_fundamentals_missing"],
        "operator_explanation": "Research-only Piotroski-style intake recipe.",
    },
    {
        "recipe_id": "switzerland_defensive_quality_v0",
        "display_name": "Switzerland Defensive Quality v0",
        "description": "Defensive quality intake recipe over Swiss equities.",
        "target_universe_ids": ["switzerland_equities"],
        "required_factor_ids": ["return_on_assets", "gross_profitability", "dividend_yield"],
        "optional_factor_ids": ["six_month_momentum"],
        "liquidity_gate": "high_or_medium",
        "size_gate": "large_mid",
        "identity_readiness_required": "OK",
        "universe_readiness_allowed": ["OK", "WARN"],
        "data_readiness_required": "fundamental_manifest_required",
        "ranking_components": ["defensive_quality_rank", "income_support_rank"],
        "exclusion_rules": ["identity_ambiguity", "currency_normalization_missing"],
        "operator_explanation": "Research-only Swiss defensive-quality intake definition.",
    },
    {
        "recipe_id": "us_quality_momentum_large_mid_v0",
        "display_name": "US Quality Momentum Large Mid v0",
        "description": "US quality and momentum intake recipe for liquid large/mid equities.",
        "target_universe_ids": ["us_large_mid", "us_quality_liquid"],
        "required_factor_ids": ["roic", "gross_profitability", "twelve_month_momentum"],
        "optional_factor_ids": ["adjusted_slope", "average_daily_value_traded"],
        "liquidity_gate": "high",
        "size_gate": "large_mid",
        "identity_readiness_required": "OK",
        "universe_readiness_allowed": ["OK", "WARN"],
        "data_readiness_required": "fundamental_manifest_required",
        "ranking_components": ["quality_rank", "momentum_rank", "liquidity_guardrail"],
        "exclusion_rules": ["identity_ambiguity", "field_coverage_missing"],
        "operator_explanation": "Research-only US quality/momentum intake definition.",
    },
    {
        "recipe_id": "us_shareholder_yield_quality_v0",
        "display_name": "US Shareholder Yield Quality v0",
        "description": "US shareholder-yield plus quality intake recipe.",
        "target_universe_ids": ["us_large_mid", "us_quality_liquid"],
        "required_factor_ids": ["shareholder_yield", "return_on_assets", "gross_profitability"],
        "optional_factor_ids": ["buyback_yield", "dividend_yield"],
        "liquidity_gate": "high",
        "size_gate": "large_mid",
        "identity_readiness_required": "OK",
        "universe_readiness_allowed": ["OK", "WARN"],
        "data_readiness_required": "fundamental_manifest_required",
        "ranking_components": ["shareholder_return_rank", "quality_rank"],
        "exclusion_rules": ["identity_ambiguity", "capital_returns_data_missing"],
        "operator_explanation": "Research-only shareholder-yield intake recipe for US large/mid equities.",
    },
)


def _known_universe_ids() -> set[str]:
    return {str(row["universe_id"]) for row in UNIVERSE_DEFINITIONS}


def _known_factor_ids() -> set[str]:
    snapshot = build_equity_factor_catalog()
    return {str(row["factor_id"]) for row in snapshot["rows"]}


def _evaluate_recipe(raw_row: dict[str, object]) -> dict[str, object]:
    universe_ids = [str(item) for item in raw_row["target_universe_ids"]]
    required_factor_ids = [str(item) for item in raw_row["required_factor_ids"]]
    optional_factor_ids = [str(item) for item in raw_row["optional_factor_ids"]]
    missing_universes = sorted(set(universe_ids) - _known_universe_ids())
    missing_factors = sorted(set(required_factor_ids + optional_factor_ids) - _known_factor_ids())
    blocked_reason_codes: list[str]
    feasibility_status: str
    if missing_universes:
        feasibility_status = "BLOCKED_MISSING_UNIVERSE"
        blocked_reason_codes = ["BLOCKED_MISSING_UNIVERSE"]
    elif missing_factors:
        feasibility_status = "BLOCKED_MISSING_FACTOR"
        blocked_reason_codes = ["BLOCKED_MISSING_FACTOR"]
    else:
        feasibility_status = "BLOCKED_DATA_READINESS_MISSING"
        blocked_reason_codes = ["BLOCKED_DATA_READINESS_MISSING"]
    return {
        **raw_row,
        "target_universe_ids": universe_ids,
        "required_factor_ids": required_factor_ids,
        "optional_factor_ids": optional_factor_ids,
        "output_type": OUTPUT_TYPE,
        "forbidden_outputs": list(FORBIDDEN_OUTPUTS),
        "feasibility_status": feasibility_status,
        "blocked_reason_codes": blocked_reason_codes,
        "research_only": True,
        "not_trade_signal": True,
        "paper_activation_allowed": False,
        "shadow_activation_allowed": False,
        "live_activation_allowed": False,
    }


def build_equity_factor_recipe_catalog() -> dict[str, object]:
    rows = [_evaluate_recipe(dict(row)) for row in RECIPE_ROWS]
    rows.sort(key=lambda row: str(row["recipe_id"]))
    blocked_counts: dict[str, int] = {}
    for reason in BLOCK_REASON_VOCABULARY:
        blocked_counts[reason] = sum(reason in row["blocked_reason_codes"] for row in rows)
    return {
        "schema_version": SCHEMA_VERSION,
        "report_kind": REPORT_KIND,
        "summary": {
            "recipe_count": len(rows),
            "feasible_recipe_count": sum(row["feasibility_status"] == "FEASIBLE" for row in rows),
            "blocked_recipe_count": sum(row["feasibility_status"] != "FEASIBLE" for row in rows),
            "blocked_reason_counts": blocked_counts,
            "operator_summary": (
                "Screener recipes are deterministic research-intake definitions only. "
                "They can emit blocked visibility for hypothesis intake, but never trade, promote, or execute."
            ),
        },
        "rows": rows,
        "policy_vocabulary": {
            "output_type": [OUTPUT_TYPE],
            "forbidden_outputs": list(FORBIDDEN_OUTPUTS),
            "blocked_reason_codes": list(BLOCK_REASON_VOCABULARY),
        },
        "safety_invariants": {
            "research_only": True,
            "not_trade_signal": True,
            "mutates_registry": False,
            "mutates_frozen_contracts": False,
            "paper_shadow_live_forbidden": True,
            "broker_risk_execution_forbidden": True,
        },
    }
