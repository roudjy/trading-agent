"""Sidecar assembly for candidate promotion registry.

Joins walk-forward, statistical defensibility, and research_latest
artifacts to classify each strategy run and build the candidate
registry payload. No IO — pure data transformation.
"""

import json
from typing import Any

from research.promotion import (
    build_strategy_id,
    classify_candidate,
    normalize_promotion_config,
)


class ArtifactJoinError(Exception):
    """Raised when required artifacts are missing or cannot be joined."""


def build_candidate_registry_payload(
    research_latest: dict[str, Any],
    walk_forward: dict[str, Any],
    statistical_defensibility: dict[str, Any] | None,
    promotion_config: dict[str, Any] | None,
    git_revision: str,
    screening_pass_kinds: dict[str, str | None] | None = None,
) -> dict[str, Any]:
    """Build the candidate_registry_latest.v1.json payload.

    Raises ArtifactJoinError if a required artifact is malformed
    or the join between artifacts fails.

    v3.15.7: ``screening_pass_kinds`` is an optional ``{strategy_id
    -> pass_kind}`` index that the caller (typically
    ``run_research``) builds from screening runtime records. The
    index is forwarded to ``classify_candidate`` so exploratory
    passes are downgraded to ``needs_investigation``. The
    ``pass_kind`` value itself is NEVER added to a registry row —
    the v1 schema is bytewise unchanged. Default ``None`` keeps
    every existing call site byte-identical to pre-v3.15.7.
    """
    pass_kinds_index = screening_pass_kinds or {}
    config = normalize_promotion_config(promotion_config)
    results = research_latest.get("results")
    if not isinstance(results, list):
        raise ArtifactJoinError("research_latest.results is missing or not a list")

    wf_strategies = walk_forward.get("strategies")
    if not isinstance(wf_strategies, list):
        raise ArtifactJoinError("walk_forward.strategies is missing or not a list")

    defensibility_index = _build_defensibility_index(statistical_defensibility)
    wf_index = _build_walk_forward_index(wf_strategies)

    candidates: list[dict[str, Any]] = []
    for result in results:
        if not result.get("success", False):
            continue

        strategy_name = result["strategy_name"]
        asset = result["asset"]
        interval = result["interval"]
        selected_params = json.loads(result.get("params_json", "{}"))
        strategy_id = build_strategy_id(strategy_name, asset, interval, selected_params)

        wf_entry = wf_index.get((strategy_name, asset, interval))
        if wf_entry is None:
            raise ArtifactJoinError(
                f"walk-forward entry missing for {strategy_name}|{asset}|{interval}"
            )

        oos_summary = wf_entry.get("oos_summary", {})
        leakage_ok = wf_entry.get("leakage_checks_ok", False)
        defensibility = defensibility_index.get((strategy_name, asset, interval))

        status, reasoning = classify_candidate(
            oos_summary=oos_summary,
            leakage_checks_ok=leakage_ok,
            defensibility=defensibility,
            config=config,
            pass_kind=pass_kinds_index.get(strategy_id),
        )

        # v3.15.7: pass_kind is INTENTIONALLY NOT added to the
        # candidate row. The v1 registry schema is frozen — only
        # status + reasoning carry the v3.15.7 effect downstream.
        candidates.append({
            "strategy_id": strategy_id,
            "strategy_name": strategy_name,
            "asset": asset,
            "interval": interval,
            "selected_params": selected_params,
            "status": status,
            "reasoning": reasoning,
        })

    candidates.sort(key=lambda c: c["strategy_id"])

    as_of_utc = research_latest.get("generated_at_utc", "")
    return {
        "version": "v1",
        "generated_at_utc": as_of_utc,
        "git_revision": git_revision,
        "promotion_config": config,
        "candidates": candidates,
        "summary": _build_summary(candidates),
    }


def _build_summary(candidates: list[dict[str, Any]]) -> dict[str, int]:
    """Count candidates by status."""
    counts: dict[str, int] = {"rejected": 0, "needs_investigation": 0, "candidate": 0}
    for entry in candidates:
        status = entry["status"]
        counts[status] = counts.get(status, 0) + 1
    counts["total"] = len(candidates)
    return counts


def _build_walk_forward_index(
    strategies: list[dict[str, Any]],
) -> dict[tuple[str, str, str], dict[str, Any]]:
    """Index walk-forward entries by (strategy_name, asset, interval)."""
    index: dict[tuple[str, str, str], dict[str, Any]] = {}
    for entry in strategies:
        key = (entry["strategy_name"], entry["asset"], entry["interval"])
        index[key] = entry
    return index


def _build_defensibility_index(
    payload: dict[str, Any] | None,
) -> dict[tuple[str, str, str], dict[str, Any]]:
    """Index defensibility members by (strategy_name, asset, interval).

    Returns empty dict if payload is None (defensibility is optional
    for classification — classify_candidate handles None defensibility).
    """
    if payload is None:
        return {}

    index: dict[tuple[str, str, str], dict[str, Any]] = {}
    for family_entry in payload.get("families", []):
        interval = family_entry["interval"]
        for member in family_entry.get("members", []):
            key = (member["strategy_name"], member["asset"], interval)
            index[key] = member
    return index
