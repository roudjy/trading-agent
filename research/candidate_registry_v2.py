"""Candidate registry v2 — first-class candidate object for v3.12.

The v1 registry (``candidate_registry_latest.v1.json``) remains
frozen byte-for-byte; v2 is emitted alongside as an additive
adjacent artifact.

Each v2 entry carries:
- lineage metadata (run_id, git_revision, config_hash, seed,
  versions)
- processing_state (v3.11-style: planned / fit_prior / eligible /
  screening / validation)
- lifecycle_status (v3.12: active subset only — rejected /
  exploratory / candidate)
- legacy_verdict + mapping_reason (audit for the v1 -> v2 mapping)
- observed_reason_codes + taxonomy_rejection_codes +
  taxonomy_derivations (from rejection_taxonomy)
- scores (from candidate_scoring — provisional, non-authoritative)
- paper_readiness_flags = None (not assessed in v3.12)
- paper_readiness_assessment_status = "reserved_for_future_phase"
- deployment_eligibility = "reserved_for_future_phase"
- source_artifact_references pointing at every upstream sidecar

The payload top-level carries status_model_version, schema_version,
run_id, git_revision, generated_at_utc, summary (by_lifecycle and
by_processing_state), and sorted entries.
"""

from __future__ import annotations

import json
from typing import Any

from research.candidate_lifecycle import (
    STATUS_MODEL_VERSION,
    map_legacy_verdict,
)
from research.candidate_scoring import compute_candidate_score, score_to_payload
from research.rejection_taxonomy import (
    collect_observed_reason_codes,
    derive_taxonomy,
)


REGISTRY_V2_SCHEMA_VERSION = "2.0"
EXECUTION_ENGINE_USED = "research_only"


# Standard pointers to upstream artifacts. Produced as strings (POSIX
# paths) so consumers on every platform can resolve them identically.
_SOURCE_ARTIFACT_REFERENCES = {
    "run_candidates": "research/run_candidates_latest.v1.json",
    "candidate_registry_v1": "research/candidate_registry_latest.v1.json",
    "statistical_defensibility": "research/statistical_defensibility_latest.v1.json",
    "regime_diagnostics": "research/regime_diagnostics_latest.v1.json",
    "cost_sensitivity": "research/cost_sensitivity_latest.v1.json",
    "run_meta": "research/run_meta_latest.v1.json",
}


def _experiment_family(strategy_family: str, asset_type: str) -> str:
    return f"{strategy_family or 'unknown'}|{asset_type or 'unknown'}"


def _asset_type(asset: str) -> str:
    """Rough asset-type classification used only for experiment_family.

    Pairs (AAA/BBB) and crypto USD-denominated symbols are grouped as
    crypto. Equity tickers (non-dash, non-slash) are equities. This
    keeps experiment_family stable without introducing a new registry
    dependency.
    """
    if "/" in asset or "-USD" in asset or "-EUR" in asset:
        return "crypto"
    return "equities"


def _lookup_run_candidate(
    run_candidates: dict[str, Any] | None,
    candidate_id: str,
) -> dict[str, Any] | None:
    if run_candidates is None:
        return None
    for entry in run_candidates.get("candidates") or []:
        if entry.get("candidate_id") == candidate_id:
            return entry
    return None


def _lookup_defensibility(
    defensibility: dict[str, Any] | None,
    strategy_name: str,
    asset: str,
    interval: str,
) -> dict[str, Any] | None:
    if defensibility is None:
        return None
    for family_entry in defensibility.get("families") or []:
        fam_interval = family_entry.get("interval")
        if fam_interval != interval:
            continue
        for member in family_entry.get("members") or []:
            if member.get("strategy_name") == strategy_name and member.get("asset") == asset:
                return member
    return None


def _build_lineage_metadata(
    run_meta: dict[str, Any] | None,
    run_id: str,
    git_revision: str,
) -> dict[str, Any]:
    meta = run_meta or {}
    return {
        "run_id": run_id,
        "git_revision": git_revision,
        "config_hash": meta.get("config_hash"),
        "data_snapshot_id": meta.get("data_snapshot_id"),
        "random_seed": meta.get("random_seed"),
        "adapter_versions": meta.get("adapter_versions") or {},
        "feature_versions": meta.get("feature_versions") or {},
        "evaluation_version": meta.get("evaluation_version"),
        "execution_engine_used": EXECUTION_ENGINE_USED,
    }


def build_registry_v2_entry(
    v1_entry: dict[str, Any],
    research_row: dict[str, Any] | None,
    run_candidate_entry: dict[str, Any] | None,
    preset_origin: str | None,
    asset_universe: list[str],
    defensibility: dict[str, Any] | None,
    regime: dict[str, Any] | None,
    cost_sens: dict[str, Any] | None,
    breadth_context: dict[str, Any] | None,
    lineage_metadata: dict[str, Any],
) -> dict[str, Any]:
    """Assemble one v2 entry from joined upstream data."""
    strategy_name = v1_entry["strategy_name"]
    asset = v1_entry["asset"]
    interval = v1_entry["interval"]
    legacy_verdict = v1_entry["status"]

    lifecycle_status, mapping_reason = map_legacy_verdict(legacy_verdict)

    observed = list(collect_observed_reason_codes(v1_entry))
    taxonomy_codes, taxonomy_derivations = derive_taxonomy(
        v1_entry, regime_diag=regime, cost_sens=cost_sens
    )

    # Scoring needs a "metrics-flat" view of the candidate. We pull
    # from the research_latest row when available; otherwise from the
    # v1 entry which does not carry metrics (fallback = empty dict).
    scoring_input: dict[str, Any] = {}
    if research_row is not None:
        scoring_input.update(research_row)
    # make sure identifiers are present for flag-sourced scoring
    scoring_input.setdefault("strategy_name", strategy_name)
    scoring_input.setdefault("asset", asset)
    scoring_input.setdefault("interval", interval)

    score = compute_candidate_score(
        v1_entry={**scoring_input, **{"reasoning": v1_entry.get("reasoning") or {}}},
        defensibility=_lookup_defensibility(defensibility, strategy_name, asset, interval),
        breadth_context=breadth_context,
    )

    selected_params = v1_entry.get("selected_params") or {}

    processing_state = (
        (run_candidate_entry or {}).get("current_status") or "validation"
    )

    strategy_family = (run_candidate_entry or {}).get("strategy_family") or v1_entry.get(
        "strategy_family"
    )
    asset_type = (run_candidate_entry or {}).get("asset_type") or _asset_type(asset)

    return {
        "candidate_id": v1_entry.get("strategy_id")
        or build_candidate_id(strategy_name, asset, interval, selected_params),
        "experiment_family": _experiment_family(strategy_family or "", asset_type or ""),
        "preset_origin": preset_origin,
        "strategy_name": strategy_name,
        "parameter_set": selected_params,
        "asset": asset,
        "interval": interval,
        "asset_universe": list(asset_universe or []),
        "processing_state": processing_state,
        "lifecycle_status": lifecycle_status.value,
        "legacy_verdict": legacy_verdict,
        "mapping_reason": mapping_reason,
        "observed_reason_codes": observed,
        "taxonomy_rejection_codes": list(taxonomy_codes),
        "taxonomy_derivations": [d.to_payload() for d in taxonomy_derivations],
        "scores": score_to_payload(score),
        "paper_readiness_flags": None,
        "paper_readiness_assessment_status": "reserved_for_future_phase",
        "deployment_eligibility": "reserved_for_future_phase",
        "lineage_metadata": lineage_metadata,
        "source_artifact_references": dict(_SOURCE_ARTIFACT_REFERENCES),
    }


def build_candidate_id(
    strategy_name: str,
    asset: str,
    interval: str,
    selected_params: dict[str, Any],
) -> str:
    """Fallback candidate_id when the v1 entry does not provide one.

    Matches ``research.promotion.build_strategy_id`` format so v2
    entries align with v1 entries by identifier.
    """
    params_json = json.dumps(selected_params, sort_keys=True)
    return f"{strategy_name}|{asset}|{interval}|{params_json}"


def _summarize(entries: list[dict[str, Any]]) -> dict[str, Any]:
    by_lifecycle: dict[str, int] = {}
    by_processing: dict[str, int] = {}
    for entry in entries:
        lc = entry.get("lifecycle_status", "unknown")
        ps = entry.get("processing_state", "unknown")
        by_lifecycle[lc] = by_lifecycle.get(lc, 0) + 1
        by_processing[ps] = by_processing.get(ps, 0) + 1
    return {
        "total": len(entries),
        "by_lifecycle_status": by_lifecycle,
        "by_processing_state": by_processing,
    }


def build_registry_v2_payload(
    *,
    candidate_registry_v1: dict[str, Any],
    research_latest: dict[str, Any],
    run_candidates: dict[str, Any] | None,
    run_meta: dict[str, Any] | None,
    defensibility: dict[str, Any] | None,
    regime: dict[str, Any] | None,
    cost_sens: dict[str, Any] | None,
    breadth_context: dict[str, Any] | None,
    run_id: str,
    git_revision: str,
    generated_at_utc: str,
) -> dict[str, Any]:
    """Assemble the full registry_v2 payload."""
    research_rows_index: dict[str, dict[str, Any]] = {}
    for row in research_latest.get("results") or []:
        strategy_name = row.get("strategy_name")
        asset = row.get("asset")
        interval = row.get("interval")
        try:
            params = json.loads(row.get("params_json") or "{}")
        except (TypeError, json.JSONDecodeError):
            params = {}
        key = build_candidate_id(str(strategy_name), str(asset), str(interval), params)
        research_rows_index[key] = row

    v1_candidates = candidate_registry_v1.get("candidates") or []

    lineage_metadata = _build_lineage_metadata(
        run_meta=run_meta, run_id=run_id, git_revision=git_revision
    )

    preset_origin = (run_meta or {}).get("preset_name")
    asset_universe = list((run_meta or {}).get("preset_universe") or [])

    entries: list[dict[str, Any]] = []
    for v1_entry in v1_candidates:
        candidate_id = v1_entry.get("strategy_id") or build_candidate_id(
            v1_entry.get("strategy_name", ""),
            v1_entry.get("asset", ""),
            v1_entry.get("interval", ""),
            v1_entry.get("selected_params") or {},
        )
        research_row = research_rows_index.get(candidate_id)
        run_candidate_entry = _lookup_run_candidate(run_candidates, candidate_id)
        entries.append(
            build_registry_v2_entry(
                v1_entry={**v1_entry, "strategy_id": candidate_id},
                research_row=research_row,
                run_candidate_entry=run_candidate_entry,
                preset_origin=preset_origin,
                asset_universe=asset_universe,
                defensibility=defensibility,
                regime=regime,
                cost_sens=cost_sens,
                breadth_context=breadth_context,
                lineage_metadata=lineage_metadata,
            )
        )

    entries.sort(key=lambda e: e["candidate_id"])

    return {
        "schema_version": REGISTRY_V2_SCHEMA_VERSION,
        "status_model_version": STATUS_MODEL_VERSION,
        "generated_at_utc": generated_at_utc,
        "run_id": run_id,
        "git_revision": git_revision,
        "summary": _summarize(entries),
        "entries": entries,
    }
