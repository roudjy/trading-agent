"""Deterministic fail-closed factor field coverage projection."""

from __future__ import annotations

from collections import Counter
from typing import Final

from research.equity_factors.factor_catalog import build_equity_factor_calculation_contracts
from research.external_intelligence.fundamental_provider_registry import (
    build_fundamental_provider_registry,
)
from research.external_intelligence.source_manifest_registry import build_source_manifest_registry


SCHEMA_VERSION: Final[str] = "1.0"
FIELD_COVERAGE_VOCABULARY: Final[tuple[str, ...]] = ("COVERED", "MISSING", "PARTIAL", "UNKNOWN")
PROVIDER_APPROVAL_VOCABULARY: Final[tuple[str, ...]] = (
    "APPROVED_READ_ONLY",
    "QUALITY_GATED_ONLY",
    "CANDIDATE_ONLY",
    "MANUAL_RESEARCH_ONLY",
    "STAGING_ONLY",
    "BLOCKED",
)
FRESHNESS_STATUS_VOCABULARY: Final[tuple[str, ...]] = ("DECLARED", "UNKNOWN", "NOT_APPLICABLE")
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


def _provider_approval_status(
    *,
    source_status: str,
    manifest_status: str,
    license_allows_quality_gate: bool,
    license_allows_active_read_only: bool,
) -> str:
    if (
        source_status == "active_read_only"
        and manifest_status == "VALID"
        and license_allows_active_read_only
    ):
        return "APPROVED_READ_ONLY"
    if (
        source_status == "quality_gated"
        and manifest_status == "VALID"
        and license_allows_quality_gate
    ):
        return "QUALITY_GATED_ONLY"
    if source_status == "manual_research_only":
        return "MANUAL_RESEARCH_ONLY"
    if source_status == "staging":
        return "STAGING_ONLY"
    if source_status == "candidate":
        return "CANDIDATE_ONLY"
    return "BLOCKED"


def _freshness_status(expected_freshness: str) -> str:
    normalized = expected_freshness.strip().lower()
    if normalized in {"metadata_only", "not_applicable", "unsupported"}:
        return "NOT_APPLICABLE"
    if not normalized or "unknown" in normalized or "depends_on" in normalized:
        return "UNKNOWN"
    return "DECLARED"


def _fundamental_claim_index() -> tuple[
    dict[str, list[str]],
    dict[str, list[str]],
    dict[str, dict[str, object]],
]:
    snapshot = build_source_manifest_registry()
    providers = build_fundamental_provider_registry()
    provider_rows = {
        str(row["provider_id"]): row for row in providers["rows"]
    }
    claimed_by_family: dict[str, list[str]] = {}
    active_by_family: dict[str, list[str]] = {}
    provider_claim_rows: dict[str, dict[str, object]] = {}
    for row in snapshot["rows"]:
        source_id = str(row["source_id"])
        provider_id = str(row["provider_id"])
        claims = [str(item) for item in row["factor_field_coverage_claims"]]
        policy = snapshot["policy_by_source"][source_id]
        approval_status = _provider_approval_status(
            source_status=str(row["source_status"]),
            manifest_status=str(row["manifest_status"]),
            license_allows_quality_gate=bool(policy["allowed_for_quality_gate"]),
            license_allows_active_read_only=bool(policy["allowed_for_active_read_only"]),
        )
        freshness = _freshness_status(str(row["expected_freshness"]))
        provider_claim_rows[provider_id] = {
            "provider_id": provider_id,
            "provider_name": str(provider_rows[provider_id]["provider_name"]),
            "provider_source_status": str(provider_rows[provider_id]["source_status"]),
            "manifest_source_id": source_id,
            "manifest_source_status": str(row["source_status"]),
            "manifest_status": str(row["manifest_status"]),
            "approval_status": approval_status,
            "expected_freshness": str(row["expected_freshness"]),
            "freshness_status": freshness,
            "allowed_use": list(row["allowed_use"]),
            "forbidden_use": list(row["forbidden_use"]),
            "required_quality_gates": list(row["required_quality_gates"]),
            "manifest_block_reasons": list(row["manifest_block_reasons"]),
            "provider_alpha_authority": False,
            "provider_factor_authority": False,
            "provider_coverage_claims": claims,
        }
        active = approval_status in {"APPROVED_READ_ONLY", "QUALITY_GATED_ONLY"} and freshness == "DECLARED"
        for claim in claims:
            claimed_by_family.setdefault(claim, []).append(provider_id)
            if active:
                active_by_family.setdefault(claim, []).append(provider_id)
    for mapping in (claimed_by_family, active_by_family):
        for claim_family, provider_ids in mapping.items():
            mapping[claim_family] = sorted(set(provider_ids))
    return claimed_by_family, active_by_family, provider_claim_rows


def _provider_field_rows(
    *,
    field_name: str,
    requirement_claims: list[str],
    claimed_by_family: dict[str, list[str]],
    provider_claim_rows: dict[str, dict[str, object]],
) -> list[dict[str, object]]:
    provider_ids = sorted(
        {
            provider_id
            for claim_family in requirement_claims
            for provider_id in claimed_by_family.get(claim_family, [])
        }
    )
    rows: list[dict[str, object]] = []
    for provider_id in provider_ids:
        provider_row = dict(provider_claim_rows[provider_id])
        blocking_reasons: list[str] = []
        if provider_row["approval_status"] != "APPROVED_READ_ONLY":
            blocking_reasons.append("provider_not_approved_for_read_only_factor_use")
        if provider_row["freshness_status"] == "UNKNOWN":
            blocking_reasons.append("provider_freshness_unknown")
        if provider_row["manifest_status"] != "VALID":
            blocking_reasons.append("provider_manifest_not_valid")
        rows.append(
            {
                **provider_row,
                "field_name": field_name,
                "required_claim_families": requirement_claims,
                "satisfies_field_for_research": not blocking_reasons,
                "blocking_reasons": blocking_reasons,
                "operator_explanation": (
                    f"{provider_row['provider_id']} can support {field_name} only after read-only approval, "
                    "manifest validity, and declared freshness exist."
                    if blocking_reasons
                    else f"{provider_row['provider_id']} is approved to satisfy {field_name}."
                ),
            }
        )
    return rows


def _field_row(
    field_name: str,
    *,
    claimed_by_family: dict[str, list[str]],
    active_by_family: dict[str, list[str]],
    provider_claim_rows: dict[str, dict[str, object]],
) -> dict[str, object]:
    requirement_claims = list(FIELD_REQUIREMENT_CLAIMS.get(field_name, ("unknown_field_mapping",)))
    candidate_sources = sorted(
        {
            provider_id
            for claim_family in requirement_claims
            for provider_id in claimed_by_family.get(claim_family, [])
        }
    )
    active_sources = sorted(
        {
            provider_id
            for claim_family in requirement_claims
            for provider_id in active_by_family.get(claim_family, [])
        }
    )
    provider_rows = _provider_field_rows(
        field_name=field_name,
        requirement_claims=requirement_claims,
        claimed_by_family=claimed_by_family,
        provider_claim_rows=provider_claim_rows,
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
        "candidate_provider_ids": candidate_sources,
        "approved_provider_ids": active_sources,
        "provider_field_matrix": provider_rows,
        "freshness_status": (
            "DECLARED"
            if any(str(row["freshness_status"]) == "DECLARED" for row in provider_rows)
            else "UNKNOWN"
            if provider_rows
            else "NOT_APPLICABLE"
        ),
    }


def build_factor_field_coverage() -> dict[str, object]:
    contracts = build_equity_factor_calculation_contracts()["rows"]
    (
        claimed_by_family,
        active_by_family,
        provider_claim_rows,
    ) = _fundamental_claim_index()
    rows: list[dict[str, object]] = []
    for row in contracts:
        required_fields = [str(field) for field in row["required_fields"]]
        field_coverage = [
            _field_row(
                field_name,
                claimed_by_family=claimed_by_family,
                active_by_family=active_by_family,
                provider_claim_rows=provider_claim_rows,
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
                "provider_coverage_count": sum(
                    len(list(item["provider_field_matrix"])) for item in field_coverage
                ),
            }
        )
    rows.sort(key=lambda item: str(item["factor_id"]))
    provider_rows = sorted(provider_claim_rows.values(), key=lambda item: str(item["provider_id"]))
    return {
        "schema_version": SCHEMA_VERSION,
        "report_kind": "factor_field_coverage",
        "summary": {
            "factor_count": len(rows),
            "provider_count": len(provider_rows),
            "approved_provider_count": sum(
                str(row["approval_status"]) == "APPROVED_READ_ONLY" for row in provider_rows
            ),
            "quality_gated_only_provider_count": sum(
                str(row["approval_status"]) == "QUALITY_GATED_ONLY" for row in provider_rows
            ),
            "covered_count": sum(row["field_coverage_status"] == "COVERED" for row in rows),
            "missing_count": sum(row["field_coverage_status"] == "MISSING" for row in rows),
            "partial_count": sum(row["field_coverage_status"] == "PARTIAL" for row in rows),
            "unknown_count": sum(row["field_coverage_status"] == "UNKNOWN" for row in rows),
            "operator_summary": (
                "Field coverage is fail-closed. Candidate manifest claims can make coverage more specific, "
                "but no provider becomes factor authority and no field is treated as covered until an approved "
                "read-only provider has valid manifests and declared freshness."
            ),
        },
        "field_coverage_status_vocabulary": list(FIELD_COVERAGE_VOCABULARY),
        "provider_approval_status_vocabulary": list(PROVIDER_APPROVAL_VOCABULARY),
        "freshness_status_vocabulary": list(FRESHNESS_STATUS_VOCABULARY),
        "provider_rows": provider_rows,
        "rows": rows,
        "safety_invariants": {
            "research_only": True,
            "not_trade_signal": True,
            "mutates_registry": False,
            "mutates_frozen_contracts": False,
            "provider_alpha_authority_forbidden": True,
            "paper_shadow_live_forbidden": True,
            "broker_risk_execution_forbidden": True,
        },
    }
