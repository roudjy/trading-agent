from __future__ import annotations

import copy
import hashlib
import json
from collections import Counter
from datetime import datetime
from typing import Any

from research.asset_typing import normalize_asset_type
from research.registry import count_param_combinations, expand_param_grid

FIT_ALLOWED = "allowed"
FIT_DISCOURAGED = "discouraged"
FIT_BLOCKED = "blocked"

SCREENING_PROMOTED = "promoted_to_validation"
SCREENING_REJECTED = "rejected_in_screening"

SUPPORTED_INITIAL_LANE = "supported"
BLOCKED_INITIAL_LANE = "blocked"
POSITION_OUTRIGHT = "outright"
POSITION_SPREAD = "spread"

DEFAULT_FIT_PRIOR_MATRIX: dict[str, dict[str, tuple[str, str]]] = {
    "futures": {
        "trend_following": (FIT_ALLOWED, "empirical_fit_high"),
        "breakout": (FIT_ALLOWED, "empirical_fit_high"),
        "time_series_momentum": (FIT_ALLOWED, "empirical_fit_high"),
    },
    "index_like": {
        "trend_following": (FIT_ALLOWED, "empirical_fit_high"),
        "breakout": (FIT_ALLOWED, "empirical_fit_high"),
        "time_series_momentum": (FIT_ALLOWED, "empirical_fit_high"),
    },
    "crypto": {
        "trend_following": (FIT_ALLOWED, "empirical_fit_mixed"),
        "breakout": (FIT_ALLOWED, "empirical_fit_mixed"),
        "time_series_momentum": (FIT_ALLOWED, "empirical_fit_mixed"),
        "mean_reversion": (FIT_DISCOURAGED, "insufficient_market_structure_fit"),
    },
    "equity": {
        "mean_reversion": (FIT_DISCOURAGED, "microstructure_sensitive"),
        "stat_arb": (FIT_BLOCKED, "requires_spread_not_outright"),
    },
    "unknown": {},
}


def _canonical_json(payload: Any) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)


def _hash_payload(payload: Any) -> str:
    return hashlib.sha256(_canonical_json(payload).encode("utf-8")).hexdigest()


def _asset_metadata(asset: Any) -> tuple[str, str, str]:
    raw_asset_type = str(getattr(asset, "asset_type", "") or "")
    raw_asset_class = str(getattr(asset, "asset_class", "") or "")
    return (
        str(getattr(asset, "symbol", asset)),
        normalize_asset_type(asset_type=raw_asset_type, asset_class=raw_asset_class),
        raw_asset_class,
    )


def _strategy_family(strategy: dict[str, Any]) -> str:
    return str(strategy.get("strategy_family") or strategy.get("family") or "unknown")


def _candidate_sort_key(candidate: dict[str, Any]) -> tuple[str, str, str, str]:
    return (
        str(candidate["strategy_name"]),
        str(candidate["asset"]),
        str(candidate["interval"]),
        str(candidate["candidate_id"]),
    )


def plan_candidates(
    *,
    strategies: list[dict[str, Any]],
    assets: list[Any],
    intervals: list[str],
) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    for strategy in sorted(strategies, key=lambda item: str(item["name"])):
        strategy_name = str(strategy["name"])
        strategy_family = _strategy_family(strategy)
        param_grid = copy.deepcopy(strategy.get("params") or {})
        param_grid_hash = _hash_payload(param_grid)
        combination_count = count_param_combinations(strategy)
        position_structure = str(strategy.get("position_structure") or POSITION_OUTRIGHT)
        initial_lane_support = str(strategy.get("initial_lane_support") or SUPPORTED_INITIAL_LANE)

        for interval in sorted(str(interval) for interval in intervals):
            for asset in sorted(assets, key=lambda entry: _asset_metadata(entry)[0]):
                symbol, asset_type, asset_class = _asset_metadata(asset)
                candidate = {
                    "candidate_id": _hash_payload(
                        {
                            "strategy_name": strategy_name,
                            "strategy_family": strategy_family,
                            "asset": symbol,
                            "asset_type": asset_type,
                            "asset_class": asset_class,
                            "interval": interval,
                            "param_grid_hash": param_grid_hash,
                            "position_structure": position_structure,
                            "initial_lane_support": initial_lane_support,
                        }
                    ),
                    "current_status": "planned",
                    "strategy_name": strategy_name,
                    "family": str(strategy["family"]),
                    "strategy_family": strategy_family,
                    "asset": symbol,
                    "asset_type": asset_type,
                    "asset_class": asset_class,
                    "interval": interval,
                    "parameter_space_identity": {
                        "param_grid_hash": param_grid_hash,
                        "combination_count": int(combination_count),
                    },
                    "strategy_requirements": {
                        "position_structure": position_structure,
                        "initial_lane_support": initial_lane_support,
                    },
                    "fit_prior": {
                        "status": "pending",
                        "reason": None,
                    },
                    "dedupe": {
                        "duplicate_removed": False,
                        "raw_occurrences": 1,
                    },
                    "eligibility": {
                        "status": "pending",
                        "reason": None,
                    },
                    "screening": {
                        "status": "pending",
                        "reason": None,
                        "sampled_combination_count": 0,
                    },
                    "validation": {
                        "status": "pending",
                        "result_success": None,
                    },
                }
                candidates.append(candidate)
    return sorted(candidates, key=_candidate_sort_key)


def deduplicate_candidates(candidates: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, int]]:
    unique_by_id: dict[str, dict[str, Any]] = {}
    for candidate in sorted(candidates, key=_candidate_sort_key):
        candidate_id = str(candidate["candidate_id"])
        if candidate_id not in unique_by_id:
            unique_by_id[candidate_id] = copy.deepcopy(candidate)
            continue
        unique_by_id[candidate_id]["dedupe"]["raw_occurrences"] += 1

    unique_candidates = []
    for candidate_id in sorted(unique_by_id):
        candidate = unique_by_id[candidate_id]
        candidate["dedupe"]["duplicate_removed"] = candidate["dedupe"]["raw_occurrences"] > 1
        candidate["current_status"] = "deduplicated"
        unique_candidates.append(candidate)

    raw_count = len(candidates)
    deduplicated_count = len(unique_candidates)
    return unique_candidates, {
        "raw_candidate_count": int(raw_count),
        "deduplicated_candidate_count": int(deduplicated_count),
        "duplicates_removed": int(raw_count - deduplicated_count),
    }


def _normalized_asset_type(candidate: dict[str, Any]) -> str:
    return normalize_asset_type(
        asset_type=candidate.get("asset_type"),
        asset_class=candidate.get("asset_class"),
    )


def assess_fit_prior(candidate: dict[str, Any]) -> tuple[str, str]:
    requirements = candidate.get("strategy_requirements") or {}
    if requirements.get("position_structure") == POSITION_SPREAD:
        return FIT_BLOCKED, "requires_spread_not_outright"
    if requirements.get("initial_lane_support") == BLOCKED_INITIAL_LANE:
        return FIT_BLOCKED, "unsupported_for_initial_lane"

    asset_type = _normalized_asset_type(candidate)
    strategy_family = str(candidate.get("strategy_family") or "unknown")
    mapping = DEFAULT_FIT_PRIOR_MATRIX.get(asset_type, {})
    if strategy_family in mapping:
        return mapping[strategy_family]
    if asset_type == "unknown":
        return FIT_DISCOURAGED, "unsupported_for_initial_lane"
    return FIT_ALLOWED, "empirical_fit_mixed"


def apply_fit_prior(candidates: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    updated: list[dict[str, Any]] = []
    blocked_reasons: Counter[str] = Counter()
    counts = {
        "fit_allowed_count": 0,
        "fit_discouraged_count": 0,
        "fit_blocked_count": 0,
    }
    for candidate in sorted(candidates, key=_candidate_sort_key):
        item = copy.deepcopy(candidate)
        status, reason = assess_fit_prior(item)
        item["fit_prior"] = {"status": status, "reason": reason}
        if status == FIT_BLOCKED:
            item["current_status"] = "fit_blocked"
            counts["fit_blocked_count"] += 1
            blocked_reasons[reason] += 1
        elif status == FIT_DISCOURAGED:
            item["current_status"] = "fit_discouraged"
            counts["fit_discouraged_count"] += 1
        else:
            counts["fit_allowed_count"] += 1
        updated.append(item)

    return updated, {
        **counts,
        "fit_blocked_reasons": dict(sorted(blocked_reasons.items())),
    }


def index_readiness(pair_diagnostics: list[dict[str, Any]]) -> dict[tuple[str, str], dict[str, Any]]:
    return {
        (str(item["asset"]), str(item["interval"])): item
        for item in pair_diagnostics
    }


def apply_eligibility(
    *,
    candidates: list[dict[str, Any]],
    readiness_by_pair: dict[tuple[str, str], dict[str, Any]],
    universe_symbols: set[str],
    integrity_checks: list[Any] | None = None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Mark candidates as eligible / rejected; optionally collect IntegrityCheck evidence.

    Single-gate design per v3.5 plan: strategy-applicability and
    feature-completeness checks land alongside the existing universe /
    readiness checks so there is still exactly one eligibility pass.
    When `integrity_checks` is provided, this function appends typed
    IntegrityCheck records for every candidate decision. The existing
    rejection_reasons string taxonomy is preserved so downstream
    empty_run_diagnostics remains lossless.
    """
    from research.integrity import (
        FEATURE_INCOMPLETE,
        STRATEGY_NOT_APPLICABLE,
    )
    from research.integrity_reporting import make_eligibility_integrity_check

    updated: list[dict[str, Any]] = []
    rejection_reasons: Counter[str] = Counter()
    eligible_count = 0
    rejected_count = 0

    for candidate in sorted(candidates, key=_candidate_sort_key):
        item = copy.deepcopy(candidate)
        if item["fit_prior"]["status"] == FIT_BLOCKED:
            if integrity_checks is not None:
                integrity_checks.append(
                    make_eligibility_integrity_check(
                        strategy_name=str(item.get("strategy_name") or "unknown"),
                        asset=str(item.get("asset") or "unknown"),
                        interval=str(item.get("interval") or "unknown"),
                        passed=False,
                        reason_code=STRATEGY_NOT_APPLICABLE,
                        extras={
                            "eligibility_reason": "fit_prior_blocked",
                            "fit_prior_reason": item["fit_prior"].get("reason"),
                        },
                    )
                )
            updated.append(item)
            continue

        reason: str | None = None
        integrity_reason: str | None = None
        if not item.get("strategy_name") or not item.get("asset") or not item.get("interval"):
            reason = "invalid_candidate_shape"
            integrity_reason = FEATURE_INCOMPLETE
        elif item["asset"] not in universe_symbols:
            reason = "universe_membership_mismatch"
            integrity_reason = STRATEGY_NOT_APPLICABLE
        elif item.get("initial_lane_support") == BLOCKED_INITIAL_LANE:
            reason = "strategy_not_applicable"
            integrity_reason = STRATEGY_NOT_APPLICABLE
        else:
            readiness = readiness_by_pair.get((str(item["asset"]), str(item["interval"])))
            if readiness is None:
                reason = "invalid_asset_interval"
                integrity_reason = FEATURE_INCOMPLETE
            elif readiness.get("status") != "evaluable":
                reason = str(readiness.get("drop_reason") or "invalid_asset_interval")
                integrity_reason = FEATURE_INCOMPLETE

        if reason is None:
            item["eligibility"] = {"status": "eligible", "reason": None}
            eligible_count += 1
        else:
            item["eligibility"] = {"status": "rejected", "reason": reason}
            item["current_status"] = "eligibility_rejected"
            rejected_count += 1
            rejection_reasons[reason] += 1

        if integrity_checks is not None:
            integrity_checks.append(
                make_eligibility_integrity_check(
                    strategy_name=str(item.get("strategy_name") or "unknown"),
                    asset=str(item.get("asset") or "unknown"),
                    interval=str(item.get("interval") or "unknown"),
                    passed=reason is None,
                    reason_code=integrity_reason,
                    extras={"eligibility_reason": reason},
                )
            )
        updated.append(item)

    return updated, {
        "eligible_candidate_count": int(eligible_count),
        "eligibility_rejected_count": int(rejected_count),
        "eligibility_rejection_reasons": dict(sorted(rejection_reasons.items())),
    }


def screening_param_samples(param_grid: dict[str, Any], max_samples: int = 3) -> list[dict[str, Any]]:
    combinations = expand_param_grid(param_grid)
    if not combinations:
        return [{}]
    if len(combinations) <= max_samples:
        return combinations

    selected_indices = {0, len(combinations) // 2, len(combinations) - 1}
    sampled = [combinations[index] for index in sorted(selected_indices)]
    return sampled[:max_samples]


def normalize_screening_decision(sample_results: list[dict[str, Any]]) -> dict[str, Any]:
    if any(result.get("status") == SCREENING_PROMOTED for result in sample_results):
        return {
            "status": SCREENING_PROMOTED,
            "reason": None,
            "sampled_combination_count": len(sample_results),
        }

    reason_counts = Counter(str(result.get("reason") or "screening_error") for result in sample_results)
    reason = sorted(
        reason_counts.items(),
        key=lambda item: (-item[1], item[0]),
    )[0][0]
    return {
        "status": SCREENING_REJECTED,
        "reason": reason,
        "sampled_combination_count": len(sample_results),
    }


def screening_candidates(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        candidate
        for candidate in sorted(candidates, key=_candidate_sort_key)
        if candidate.get("eligibility", {}).get("status") == "eligible"
    ]


def validation_candidates(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        candidate
        for candidate in sorted(candidates, key=_candidate_sort_key)
        if candidate.get("screening", {}).get("status") == SCREENING_PROMOTED
    ]


def summarize_candidates(candidates: list[dict[str, Any]]) -> dict[str, int]:
    raw_count = sum(int(candidate["dedupe"]["raw_occurrences"]) for candidate in candidates)
    deduplicated_count = len(candidates)
    fit_statuses = Counter(str(candidate["fit_prior"]["status"]) for candidate in candidates)
    eligibility_statuses = Counter(str(candidate["eligibility"]["status"]) for candidate in candidates)
    screening_statuses = Counter(str(candidate["screening"]["status"]) for candidate in candidates)
    validated_count = sum(
        1
        for candidate in candidates
        if candidate.get("validation", {}).get("status") == "validated"
    )
    return {
        "raw_candidate_count": int(raw_count),
        "fit_allowed_count": int(fit_statuses.get(FIT_ALLOWED, 0)),
        "fit_discouraged_count": int(fit_statuses.get(FIT_DISCOURAGED, 0)),
        "fit_blocked_count": int(fit_statuses.get(FIT_BLOCKED, 0)),
        "deduplicated_candidate_count": int(deduplicated_count),
        "duplicates_removed": int(raw_count - deduplicated_count),
        "eligible_candidate_count": int(eligibility_statuses.get("eligible", 0)),
        "eligibility_rejected_count": int(eligibility_statuses.get("rejected", 0)),
        "screening_rejected_count": int(screening_statuses.get(SCREENING_REJECTED, 0)),
        "validation_candidate_count": int(screening_statuses.get(SCREENING_PROMOTED, 0)),
        "validated_count": int(validated_count),
    }


def build_candidate_artifact_payload(
    *,
    run_id: str,
    as_of_utc: datetime,
    candidates: list[dict[str, Any]],
) -> dict[str, Any]:
    ordered_candidates = sorted((copy.deepcopy(candidate) for candidate in candidates), key=_candidate_sort_key)
    return {
        "version": "v1",
        "run_id": run_id,
        "generated_at_utc": as_of_utc.isoformat(),
        "summary": summarize_candidates(ordered_candidates),
        "candidates": ordered_candidates,
    }


def build_filter_summary_payload(
    *,
    run_id: str,
    as_of_utc: datetime,
    candidates: list[dict[str, Any]],
) -> dict[str, Any]:
    fit_blocked_reasons = Counter(
        str(candidate["fit_prior"]["reason"])
        for candidate in candidates
        if candidate.get("fit_prior", {}).get("status") == FIT_BLOCKED
        and candidate.get("fit_prior", {}).get("reason")
    )
    eligibility_rejection_reasons = Counter(
        str(candidate["eligibility"]["reason"])
        for candidate in candidates
        if candidate.get("eligibility", {}).get("status") == "rejected"
        and candidate.get("eligibility", {}).get("reason")
    )
    screening_rejection_reasons = Counter(
        str(candidate["screening"]["reason"])
        for candidate in candidates
        if candidate.get("screening", {}).get("status") == SCREENING_REJECTED
        and candidate.get("screening", {}).get("reason")
    )
    screening_decisions = Counter(
        str(candidate["screening"]["status"])
        for candidate in candidates
        if candidate.get("screening", {}).get("status") in {SCREENING_PROMOTED, SCREENING_REJECTED}
    )
    return {
        "version": "v1",
        "run_id": run_id,
        "generated_at_utc": as_of_utc.isoformat(),
        "summary": summarize_candidates(candidates),
        "fit_blocked_reasons": dict(sorted(fit_blocked_reasons.items())),
        "eligibility_rejection_reasons": dict(sorted(eligibility_rejection_reasons.items())),
        "screening_decisions": {
            SCREENING_PROMOTED: int(screening_decisions.get(SCREENING_PROMOTED, 0)),
            SCREENING_REJECTED: int(screening_decisions.get(SCREENING_REJECTED, 0)),
        },
        "screening_rejection_reasons": dict(sorted(screening_rejection_reasons.items())),
    }
