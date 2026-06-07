"""Deterministic fail-closed factor field coverage projection."""

from __future__ import annotations

from collections import Counter
from typing import Final

from research.equity_factors.factor_catalog import build_equity_factor_calculation_contracts
from research.external_intelligence.source_manifest_registry import build_source_manifest_registry


SCHEMA_VERSION: Final[str] = "1.0"
FIELD_COVERAGE_VOCABULARY: Final[tuple[str, ...]] = ("COVERED", "MISSING", "PARTIAL", "UNKNOWN")
FIELD_REQUIREMENT_CLAIMS: Final[dict[str, tuple[str, ...]]] = {
    "aqi": ("multi_period_fundamentals",),
    "asset_quality_index": ("multi_period_fundamentals",),
    "asset_turnover": ("multi_period_fundamentals",),
    "average_daily_value_traded_90d": ("price_history", "volume_history"),
    "average_total_assets": ("multi_period_fundamentals",),
    "book_value_equity": ("balance_sheet_statement",),
    "days_sales_receivables": ("multi_period_fundamentals",),
    "depi": ("multi_period_fundamentals",),
    "depreciation_index": ("multi_period_fundamentals",),
    "dividends_paid_ttm": ("dividend_history", "cash_flow_statement"),
    "dsri": ("multi_period_fundamentals",),
    "ebit_ttm": ("income_statement",),
    "ebitda_ttm": ("income_statement",),
    "enterprise_value": ("enterprise_value",),
    "free_cash_flow_ttm": ("cash_flow_statement",),
    "gmi": ("multi_period_fundamentals",),
    "gross_margin": ("multi_period_fundamentals",),
    "gross_margin_index": ("multi_period_fundamentals",),
    "gross_profit_ttm": ("income_statement",),
    "income_statement": ("income_statement",),
    "invested_capital": ("balance_sheet_statement",),
    "leverage_index": ("multi_period_fundamentals",),
    "leverage_ratio": ("multi_period_fundamentals",),
    "lvgi": ("multi_period_fundamentals",),
    "market_cap": ("market_cap_context",),
    "net_buybacks_ttm": ("capital_returns",),
    "net_debt": ("balance_sheet_statement",),
    "net_debt_change_ttm": ("capital_returns", "cash_flow_statement"),
    "net_income_ttm": ("income_statement",),
    "nopat_ttm": ("income_statement",),
    "operating_cash_flow": ("cash_flow_statement",),
    "operating_cash_flow_ttm": ("cash_flow_statement",),
    "price_history_12m": ("price_history",),
    "price_history_6m": ("price_history",),
    "retained_earnings": ("balance_sheet_statement",),
    "revenue_ttm": ("income_statement",),
    "roa": ("multi_period_fundamentals",),
    "sales_growth_index": ("multi_period_fundamentals",),
    "sgai": ("multi_period_fundamentals",),
    "sgi": ("multi_period_fundamentals",),
    "tata": ("multi_period_fundamentals",),
    "total_accruals_to_assets": ("multi_period_fundamentals",),
    "total_assets": ("balance_sheet_statement",),
    "total_debt": ("balance_sheet_statement",),
    "total_liabilities": ("balance_sheet_statement",),
    "volatility_12m": ("volatility_context",),
    "working_capital": ("balance_sheet_statement",),
}


def _fundamental_claim_index() -> tuple[dict[str, list[str]], dict[str, list[str]]]:
    snapshot = build_source_manifest_registry()
    claimed_by_family: dict[str, list[str]] = {}
    active_by_family: dict[str, list[str]] = {}
    for row in snapshot["rows"]:
        source_id = str(row["source_id"])
        claims = [str(item) for item in row["factor_field_coverage_claims"]]
        policy = snapshot["policy_by_source"][source_id]
        active = bool(policy["allowed_for_quality_gate"]) or str(row["source_status"]) in {
            "quality_gated",
            "active_read_only",
        }
        for claim in claims:
            claimed_by_family.setdefault(claim, []).append(source_id)
            if active:
                active_by_family.setdefault(claim, []).append(source_id)
    for mapping in (claimed_by_family, active_by_family):
        for claim_family, source_ids in mapping.items():
            mapping[claim_family] = sorted(set(source_ids))
    return claimed_by_family, active_by_family


def _field_row(field_name: str, *, claimed_by_family: dict[str, list[str]], active_by_family: dict[str, list[str]]) -> dict[str, object]:
    requirement_claims = list(FIELD_REQUIREMENT_CLAIMS.get(field_name, ("unknown_field_mapping",)))
    candidate_sources = sorted(
        {
            source_id
            for claim_family in requirement_claims
            for source_id in claimed_by_family.get(claim_family, [])
        }
    )
    active_sources = sorted(
        {
            source_id
            for claim_family in requirement_claims
            for source_id in active_by_family.get(claim_family, [])
        }
    )
    if active_sources:
        coverage_status = "COVERED"
        coverage_reason = "active_or_quality_gated_source_claim_present"
    elif candidate_sources:
        coverage_status = "UNKNOWN"
        coverage_reason = "candidate_source_claim_present_but_not_quality_gated"
    else:
        coverage_status = "MISSING"
        coverage_reason = "no_manifest_claim_for_required_field"
    return {
        "field_name": field_name,
        "coverage_status": coverage_status,
        "coverage_reason": coverage_reason,
        "required_claim_families": requirement_claims,
        "candidate_source_ids": candidate_sources,
        "active_source_ids": active_sources,
    }


def build_factor_field_coverage() -> dict[str, object]:
    contracts = build_equity_factor_calculation_contracts()["rows"]
    claimed_by_family, active_by_family = _fundamental_claim_index()
    rows: list[dict[str, object]] = []
    for row in contracts:
        required_fields = [str(field) for field in row["required_fields"]]
        field_coverage = [
            _field_row(
                field_name,
                claimed_by_family=claimed_by_family,
                active_by_family=active_by_family,
            )
            for field_name in required_fields
        ]
        coverage_counter = Counter(str(item["coverage_status"]) for item in field_coverage)
        if coverage_counter.get("COVERED", 0) == len(field_coverage):
            field_coverage_status = "COVERED"
        elif coverage_counter.get("UNKNOWN", 0) == len(field_coverage):
            field_coverage_status = "UNKNOWN"
        elif coverage_counter.get("MISSING", 0) == len(field_coverage):
            field_coverage_status = "MISSING"
        else:
            field_coverage_status = "PARTIAL"
        coverage_block_reasons: list[str] = []
        if field_coverage_status in {"UNKNOWN", "PARTIAL"}:
            coverage_block_reasons.append("FACTOR_FIELD_COVERAGE_UNKNOWN")
        if field_coverage_status in {"MISSING", "PARTIAL"}:
            coverage_block_reasons.append("MISSING_REQUIRED_FIELD")
        rows.append(
            {
                "factor_id": row["factor_id"],
                "required_fields": required_fields,
                "field_coverage": field_coverage,
                "field_coverage_status": field_coverage_status,
                "coverage_block_reasons": coverage_block_reasons,
                "source_manifest_required": True,
                "point_in_time_required": bool(row["point_in_time_required"]),
                "report_lag_required": bool(row["point_in_time_required"]),
                "currency_normalization_required": "currency_consistent"
                in row["quality_gate_requirements"],
            }
        )
    rows.sort(key=lambda item: str(item["factor_id"]))
    return {
        "schema_version": SCHEMA_VERSION,
        "report_kind": "factor_field_coverage",
        "summary": {
            "factor_count": len(rows),
            "covered_count": sum(row["field_coverage_status"] == "COVERED" for row in rows),
            "missing_count": sum(row["field_coverage_status"] == "MISSING" for row in rows),
            "partial_count": sum(row["field_coverage_status"] == "PARTIAL" for row in rows),
            "unknown_count": sum(row["field_coverage_status"] == "UNKNOWN" for row in rows),
            "operator_summary": (
                "Field coverage is fail-closed. Candidate manifest claims can make coverage more specific, "
                "but no field is treated as covered until a quality-gated or active read-only source exists."
            ),
        },
        "field_coverage_status_vocabulary": list(FIELD_COVERAGE_VOCABULARY),
        "rows": rows,
        "safety_invariants": {
            "research_only": True,
            "not_trade_signal": True,
            "mutates_registry": False,
            "mutates_frozen_contracts": False,
            "paper_shadow_live_forbidden": True,
            "broker_risk_execution_forbidden": True,
        },
    }
