"""Read-only bridge from equity-factor recipes to hypothesis seed records."""

from __future__ import annotations

from collections import Counter, defaultdict
from hashlib import sha256
from typing import Final

from research.data_readiness.fundamental_readiness import build_fundamental_readiness
from research.equity_factors.factor_catalog import build_equity_factor_catalog
from research.equity_factor_manifest import CATALOG_NAME as FACTOR_CATALOG_NAME
from research.equity_factor_manifest import CONTRACTS_NAME as FACTOR_CONTRACTS_NAME
from research.equity_factors.recipe_catalog import build_equity_factor_recipe_catalog
from research.equity_factors.recipe_manifest import RECIPES_NAME as RECIPE_NAME
from research.equity_universe_catalog import build_equity_universe_catalog
from research.equity_universe_manifest import CATALOG_NAME as UNIVERSE_CATALOG_NAME
from research.equity_universe_manifest import IDENTITY_NAME as IDENTITY_ARTIFACT_NAME
from research.equity_universe_quality import build_equity_universe_quality


SCHEMA_VERSION: Final[str] = "1.0"
REPORT_KIND: Final[str] = "equity_factor_hypothesis_seeds"
ALLOWED_USE: Final[tuple[str, ...]] = ("research_prior",)
FORBIDDEN_USE: Final[tuple[str, ...]] = (
    "strategy_signal",
    "trade_signal",
    "buy_list",
    "sell_list",
    "candidate_promotion",
    "paper",
    "shadow",
    "live",
    "capital_allocation",
    "broker_execution",
)
FEASIBILITY_VOCABULARY: Final[tuple[str, ...]] = ("FEASIBLE", "BLOCKED")
DATA_READINESS_ARTIFACT_PATH: Final[str] = (
    "artifacts/data_readiness/fundamental_readiness_latest.v1.json"
)
UNIVERSE_CATALOG_ARTIFACT_PATH: Final[str] = f"artifacts/universe/{UNIVERSE_CATALOG_NAME}"
UNIVERSE_QUALITY_ARTIFACT_PATH: Final[str] = "artifacts/universe/equity_universe_quality_latest.v1.json"
IDENTITY_ARTIFACT_PATH: Final[str] = f"artifacts/identity/{IDENTITY_ARTIFACT_NAME}"
FACTOR_CATALOG_ARTIFACT_PATH: Final[str] = f"artifacts/equity_factors/{FACTOR_CATALOG_NAME}"
CALCULATION_CONTRACT_ARTIFACT_PATH: Final[str] = (
    f"artifacts/equity_factors/{FACTOR_CONTRACTS_NAME}"
)
RECIPE_ARTIFACT_PATH: Final[str] = f"artifacts/equity_factors/{RECIPE_NAME}"
BLOCKED_SCORE_CAP: Final[float] = 0.49


def _behavior_family(recipe_id: str) -> str:
    recipe_id = recipe_id.lower()
    if "shareholder_yield" in recipe_id:
        return "shareholder_yield_quality_persistence"
    if "deep_value" in recipe_id or "financial_health" in recipe_id:
        return "financial_health_reversal"
    if "low_accrual" in recipe_id:
        return "low_accrual_quality_screening"
    if "magic_formula" in recipe_id:
        return "quality_value_efficiency"
    if "piotroski" in recipe_id:
        return "financial_health_value_recovery"
    if "defensive" in recipe_id:
        return "defensive_quality_drawdown_resilience"
    if "quality" in recipe_id and "momentum" in recipe_id:
        return "quality_value_momentum_persistence"
    if "quality" in recipe_id and "value" in recipe_id:
        return "quality_value_screening"
    return "equity_factor_screening"


def _hypothesis_statement(recipe: dict[str, object], behavior_family: str) -> str:
    universes = ", ".join(str(item) for item in recipe["target_universe_ids"])
    factors = ", ".join(str(item) for item in recipe["required_factor_ids"])
    return (
        f"Research-only hypothesis seed from {recipe['recipe_id']} testing "
        f"{behavior_family} across {universes} using factors: {factors}. "
        "This is not a trade signal or strategy candidate."
    )


def _deterministic_hash(row: dict[str, object]) -> str:
    payload = "|".join(
        [
            str(row["hypothesis_seed_id"]),
            str(row["source_recipe_id"]),
            ",".join(str(item) for item in row["target_universe_ids"]),
            ",".join(str(item) for item in row["factor_ids"]),
            str(row["behavior_family"]),
            str(row["feasibility_status"]),
        ]
    )
    return sha256(payload.encode("utf-8")).hexdigest()


def _score_components(
    *,
    recipe_known: bool,
    universes_known: bool,
    factors_known: bool,
    universe_quality_fail: bool,
    identity_ambiguity: bool,
    data_ready: bool,
) -> dict[str, float]:
    components = {
        "universe_readiness_component": 0.22 if universes_known and not universe_quality_fail else 0.0,
        "identity_readiness_component": 0.18 if not identity_ambiguity else 0.0,
        "factor_catalog_component": 0.20 if factors_known else 0.0,
        "recipe_structure_component": 0.15 if recipe_known else 0.0,
        "data_readiness_component": 0.15 if data_ready else 0.0,
        "expected_information_gain_placeholder": 0.10 if recipe_known and factors_known else 0.0,
        "blocked_penalty": 0.0 if data_ready and not identity_ambiguity and not universe_quality_fail else -0.30,
    }
    return components


def _expected_research_value_score(
    components: dict[str, float],
    *,
    feasibility_status: str,
) -> float:
    total = sum(components.values())
    bounded = max(0.0, min(1.0, total))
    if feasibility_status == "BLOCKED":
        bounded = min(bounded, BLOCKED_SCORE_CAP)
    return round(bounded, 3)


def build_equity_factor_hypothesis_seeds() -> dict[str, object]:
    recipe_catalog = build_equity_factor_recipe_catalog()
    factor_catalog = build_equity_factor_catalog()
    universe_catalog = build_equity_universe_catalog()
    universe_quality = build_equity_universe_quality()
    fundamental_readiness = build_fundamental_readiness()

    factor_ids = {str(row["factor_id"]) for row in factor_catalog.get("rows", [])}
    readiness_by_factor = {
        str(row["factor_id"]): row for row in fundamental_readiness.get("factor_rows", [])
    }
    factor_ids.update(readiness_by_factor.keys())
    readiness_by_recipe = {
        str(row["recipe_id"]): row for row in fundamental_readiness.get("recipe_rows", [])
    }

    universe_members: dict[str, list[str]] = defaultdict(list)
    for instrument in universe_catalog.get("instruments", []):
        canonical_id = str(instrument["canonical_id"])
        for universe_id in instrument["universe_ids"]:
            universe_members[str(universe_id)].append(canonical_id)

    quality_by_canonical = {
        str(row["canonical_id"]): row for row in universe_quality.get("rows", [])
    }

    rows: list[dict[str, object]] = []
    for recipe in recipe_catalog.get("rows", []):
        recipe_id = str(recipe["recipe_id"])
        target_universe_ids = [str(item) for item in recipe["target_universe_ids"]]
        required_factor_ids = [str(item) for item in recipe["required_factor_ids"]]
        optional_factor_ids = [str(item) for item in recipe["optional_factor_ids"]]
        missing_universes = sorted(
            universe_id for universe_id in target_universe_ids if universe_id not in universe_members
        )
        missing_factors = sorted(
            factor_id
            for factor_id in required_factor_ids + optional_factor_ids
            if factor_id not in factor_ids
        )

        target_quality_rows = [
            quality_by_canonical[canonical_id]
            for universe_id in target_universe_ids
            for canonical_id in universe_members.get(universe_id, [])
            if canonical_id in quality_by_canonical
        ]
        universe_quality_fail = any(
            str(row["universe_readiness_status"]) == "FAIL" for row in target_quality_rows
        )
        identity_ambiguity = any(
            bool(row["ambiguous_mapping_warning"]) or not bool(row["eligible_for_hypothesis_seed"])
            for row in target_quality_rows
        )

        readiness_row = readiness_by_recipe.get(recipe_id, {})
        data_ready = str(readiness_row.get("readiness_status", "UNKNOWN")) == "READY"
        blocked_reason_codes: list[str] = []
        if missing_universes:
            blocked_reason_codes.append("BLOCKED_MISSING_UNIVERSE")
        if missing_factors:
            blocked_reason_codes.append("BLOCKED_MISSING_FACTOR")
        if universe_quality_fail:
            blocked_reason_codes.append("BLOCKED_UNIVERSE_QUALITY_FAIL")
        if identity_ambiguity:
            blocked_reason_codes.append("BLOCKED_IDENTITY_AMBIGUITY")
        if not data_ready:
            blocked_reason_codes.append("BLOCKED_DATA_READINESS_MISSING")
            for reason in readiness_row.get("readiness_block_reasons", []):
                text = str(reason)
                if text and text not in blocked_reason_codes:
                    blocked_reason_codes.append(text)
        if not blocked_reason_codes and str(recipe.get("feasibility_status")) != "FEASIBLE":
            for reason in recipe.get("blocked_reason_codes", []):
                text = str(reason)
                if text and text not in blocked_reason_codes:
                    blocked_reason_codes.append(text)
        feasibility_status = "FEASIBLE" if not blocked_reason_codes else "BLOCKED"

        behavior_family = _behavior_family(recipe_id)
        components = _score_components(
            recipe_known=True,
            universes_known=not missing_universes,
            factors_known=not missing_factors,
            universe_quality_fail=universe_quality_fail,
            identity_ambiguity=identity_ambiguity,
            data_ready=data_ready,
        )
        required_next_action = (
            "add_source_manifest"
            if {
                "MISSING_SOURCE_MANIFEST",
                "LICENSE_REVIEW_REQUIRED",
                "SOURCE_LICENSE_UNKNOWN",
                "SOURCE_QUALITY_UNKNOWN",
            }
            & set(blocked_reason_codes)
            else "resolve_identity_ambiguity"
            if "BLOCKED_IDENTITY_AMBIGUITY" in blocked_reason_codes
            else "fix_recipe_references"
            if {"BLOCKED_MISSING_UNIVERSE", "BLOCKED_MISSING_FACTOR"} & set(blocked_reason_codes)
            else "operator_review"
            if blocked_reason_codes
            else "eligible_for_readonly_hypothesis_intake"
        )
        row = {
            "hypothesis_seed_id": f"equity_factor_seed::{recipe_id}",
            "source_recipe_id": recipe_id,
            "target_universe_ids": target_universe_ids,
            "factor_ids": required_factor_ids,
            "behavior_family": behavior_family,
            "hypothesis_statement": _hypothesis_statement(recipe, behavior_family),
            "expected_research_value_score": _expected_research_value_score(
                components,
                feasibility_status=feasibility_status,
            ),
            "score_components": components,
            "score_interpretation": (
                "expected_research_value_only_not_alpha_confidence"
            ),
            "feasibility_status": feasibility_status,
            "blocked_reason_codes": blocked_reason_codes,
            "required_next_action": required_next_action,
            "allowed_use": list(ALLOWED_USE),
            "forbidden_use": list(FORBIDDEN_USE),
            "created_from_artifacts": [
                UNIVERSE_CATALOG_ARTIFACT_PATH,
                UNIVERSE_QUALITY_ARTIFACT_PATH,
                IDENTITY_ARTIFACT_PATH,
                FACTOR_CATALOG_ARTIFACT_PATH,
                CALCULATION_CONTRACT_ARTIFACT_PATH,
                RECIPE_ARTIFACT_PATH,
                DATA_READINESS_ARTIFACT_PATH,
            ],
        }
        row["deterministic_hash"] = _deterministic_hash(row)
        rows.append(row)

    rows.sort(key=lambda row: str(row["hypothesis_seed_id"]))
    blocked_reason_counts = Counter(
        reason for row in rows for reason in row["blocked_reason_codes"]
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "report_kind": REPORT_KIND,
        "feasibility_status_vocabulary": list(FEASIBILITY_VOCABULARY),
        "summary": {
            "hypothesis_seed_count": len(rows),
            "feasible_seed_count": sum(row["feasibility_status"] == "FEASIBLE" for row in rows),
            "blocked_seed_count": sum(row["feasibility_status"] == "BLOCKED" for row in rows),
            "top_blocked_reasons": dict(sorted(blocked_reason_counts.items())),
            "operator_summary": (
                "Equity-factor hypothesis seeds are read-only research priors. "
                "Blocked seeds remain visible for operator review and do not promote to candidates or strategies."
            ),
        },
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
