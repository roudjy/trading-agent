from __future__ import annotations

import argparse
import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any, Final

from packages.qre_research.generated_strategy_paths import (
    REPO_ROOT,
    repo_relative,
    validate_write_target,
)


SCHEMA_VERSION: Final[str] = "1.0"
MODULE_VERSION: Final[str] = "ade-qre-022.1"
REPORT_KIND: Final[str] = "qre_automated_campaign_readiness"

FIELD_STATE: Final[tuple[str, ...]] = (
    "RESOLVED",
    "RESOLVED_WITH_LIMITATIONS",
    "MISSING",
    "AMBIGUOUS",
    "CONFLICTING",
    "STALE",
    "NON_AUTHORITATIVE",
    "NOT_APPLICABLE",
    "BLOCKED",
)
IDENTITY_OUTCOME: Final[tuple[str, ...]] = (
    "RESOLVED_UNIQUE_AUTHORITATIVE",
    "RESOLVED_CANONICAL_ALIAS",
    "RESOLVED_WITH_LIMITATIONS",
    "AMBIGUOUS_MULTIPLE_AUTHORITATIVE",
    "CONFLICTING_AUTHORITIES",
    "MISSING_NO_CANDIDATE",
    "BLOCKED_NON_AUTHORITATIVE_ONLY",
    "REJECTED_INVALID_IDENTITY",
)
READINESS_STATE: Final[tuple[str, ...]] = (
    "READINESS_DIAGNOSIS_REQUIRED",
    "READINESS_GAPS_IDENTIFIED",
    "IDENTITY_CANDIDATES_FOUND",
    "IDENTITY_RESOLVED",
    "IDENTITY_AMBIGUOUS",
    "IDENTITY_CONFLICTING",
    "IDENTITY_MISSING",
    "DATA_BINDING_READY",
    "DATA_BINDING_BLOCKED",
    "WINDOW_CAPACITY_READY",
    "WINDOW_CAPACITY_BLOCKED",
    "PRESET_READY",
    "PRESET_BLOCKED",
    "NULL_CONTROLS_SPECIFIED",
    "NULL_CONTROLS_EXECUTION_READY",
    "NULL_CONTROLS_BLOCKED",
    "CAMPAIGN_METADATA_READY",
    "CAMPAIGN_LINEAGE_COMPLETE",
    "READY_FOR_PREREGISTRATION",
    "PREREGISTRATION_BLOCKED",
    "QUARANTINED",
    "SUPERSEDED",
)
DATA_BINDING_OUTCOME: Final[tuple[str, ...]] = (
    "DATA_BINDING_READY",
    "DATA_BINDING_READY_WITH_LIMITATIONS",
    "DATA_SOURCE_AMBIGUOUS",
    "DATASET_MISSING",
    "SNAPSHOT_MISSING",
    "SCHEMA_INCOMPATIBLE",
    "COVERAGE_INSUFFICIENT",
    "QUALITY_BLOCKED",
    "FRESHNESS_BLOCKED",
)
WINDOW_OUTCOME: Final[tuple[str, ...]] = (
    "WINDOW_CAPACITY_READY",
    "WINDOW_CAPACITY_READY_WITH_LIMITATIONS",
    "TRAIN_CAPACITY_BLOCKED",
    "VALIDATION_CAPACITY_BLOCKED",
    "OOS_CAPACITY_BLOCKED",
    "INDEPENDENCE_NOT_PROVEN",
    "SIGNAL_DENSITY_INSUFFICIENT",
    "REGIME_COVERAGE_INSUFFICIENT",
    "DATA_COVERAGE_INSUFFICIENT",
)
PRESET_OUTCOME: Final[tuple[str, ...]] = (
    "PRESET_READY",
    "PRESET_READY_WITH_LIMITATIONS",
    "PRESET_BLOCKED_IDENTITY",
    "PRESET_BLOCKED_DATA",
    "PRESET_BLOCKED_PARAMETERS",
    "PRESET_BLOCKED_POLICY",
)
NULL_CONTROL_OUTCOME: Final[tuple[str, ...]] = (
    "NULL_CONTROL_EXECUTION_READY",
    "NULL_CONTROL_READY_WITH_LIMITATIONS",
    "SPECIFICATION_ONLY",
    "IMPLEMENTATION_MISSING",
    "DATA_BLOCKED",
    "WINDOW_BLOCKED",
    "COMPUTE_BLOCKED",
    "NOT_APPLICABLE_WITH_REASON",
)
LINEAGE_OUTCOME: Final[tuple[str, ...]] = (
    "CAMPAIGN_LINEAGE_COMPLETE",
    "CAMPAIGN_LINEAGE_COMPLETE_WITH_LIMITATIONS",
    "CAMPAIGN_LINEAGE_MISSING",
    "CAMPAIGN_LINEAGE_CONFLICTING",
    "CAMPAIGN_LINEAGE_STALE",
)
PORTFOLIO_STATUS: Final[tuple[str, ...]] = (
    "READY_FOR_PREREGISTRATION",
    "READY_WITH_LIMITATIONS",
    "BLOCKED_IDENTITY",
    "BLOCKED_DATA",
    "BLOCKED_WINDOWS",
    "BLOCKED_NULL_CONTROLS",
    "BLOCKED_LINEAGE",
    "BLOCKED_SIGNAL_DENSITY",
    "BLOCKED_POLICY",
    "INSUFFICIENT_EVIDENCE",
    "EXCLUDED_REJECTED",
    "EXCLUDED_DUPLICATE",
)
CLOSEOUT_OUTCOME: Final[tuple[str, ...]] = (
    "READY_FOR_SECOND_CAMPAIGN",
    "READINESS_PARTIALLY_REMEDIATED",
    "IDENTITY_RESOLUTION_BLOCKED",
    "DATA_CAPACITY_BLOCKED",
    "OOS_CAPACITY_BLOCKED",
    "NULL_CONTROL_READINESS_BLOCKED",
    "NO_CAMPAIGN_READY_STRATEGIES",
)

GENERATED_RESEARCH_ROOT: Final[Path] = REPO_ROOT / "generated_research" / "readiness"
READINESS_GAPS_PATH: Final[Path] = GENERATED_RESEARCH_ROOT / "gaps" / "strategy_readiness_gaps.v1.json"
IDENTITY_CANDIDATES_PATH: Final[Path] = GENERATED_RESEARCH_ROOT / "identity_candidates" / "strategy_identity_candidates.v1.json"
IDENTITY_DECISIONS_PATH: Final[Path] = GENERATED_RESEARCH_ROOT / "identity_decisions" / "strategy_identity_decisions.v1.json"
DATA_BINDINGS_PATH: Final[Path] = GENERATED_RESEARCH_ROOT / "data_bindings" / "strategy_data_bindings.v1.json"
WINDOW_CAPACITY_PATH: Final[Path] = GENERATED_RESEARCH_ROOT / "window_capacity" / "strategy_window_capacity.v1.json"
PRESET_READINESS_PATH: Final[Path] = GENERATED_RESEARCH_ROOT / "presets" / "strategy_preset_readiness.v1.json"
NULL_CONTROL_READINESS_PATH: Final[Path] = GENERATED_RESEARCH_ROOT / "null_controls" / "strategy_null_control_readiness.v1.json"
CAMPAIGN_METADATA_PATH: Final[Path] = GENERATED_RESEARCH_ROOT / "campaigns" / "generated_campaign_metadata.v1.json"
CAMPAIGN_LINEAGE_PATH: Final[Path] = GENERATED_RESEARCH_ROOT / "campaigns" / "generated_campaign_lineage_resolution.v1.json"
PORTFOLIO_PATH: Final[Path] = GENERATED_RESEARCH_ROOT / "campaigns" / "generated_portfolio_readiness.v1.json"
PREREG_MANIFEST_PATH: Final[Path] = GENERATED_RESEARCH_ROOT / "campaigns" / "generated_second_campaign_manifest.v1.json"
CLOSEOUT_JSON_PATH: Final[Path] = GENERATED_RESEARCH_ROOT / "reports" / "automated_campaign_readiness_closeout.v1.json"
CLOSEOUT_MD_PATH: Final[Path] = GENERATED_RESEARCH_ROOT / "reports" / "automated_campaign_readiness_closeout.v1.md"


def _repo_path(repo_root: Path, path: Path) -> Path:
    return repo_root / path.relative_to(REPO_ROOT)


def _stable_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def stable_digest(value: Any) -> str:
    return hashlib.sha256(_stable_json(value).encode("utf-8")).hexdigest()


def _atomic_write(path: Path, payload: str) -> None:
    validate_write_target(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=".ade_qre_022.", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(payload)
        os.replace(tmp_name, path)
    except Exception:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise


def _read_json(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _read_rows(path: Path) -> list[dict[str, Any]]:
    payload = _read_json(path)
    rows = payload.get("rows") if isinstance(payload, dict) else None
    if not isinstance(rows, list):
        return []
    return [dict(row) for row in rows if isinstance(row, dict)]


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    _atomic_write(path, json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=True) + "\n")


def _find_unique(rows: list[dict[str, Any]], predicate: Any) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
    matches = [row for row in rows if predicate(row)]
    return matches, matches[0] if len(matches) == 1 else None


def _field_record(
    *,
    field_name: str,
    state: str,
    authoritative_value: Any,
    candidate_refs: list[str],
    missing_reason: str,
    conflict_reason: str,
    source_authority: str,
    next_action: str,
    provenance: list[str],
) -> dict[str, Any]:
    return {
        "field_name": field_name,
        "state": state,
        "authoritative_value": authoritative_value,
        "candidate_refs": list(candidate_refs),
        "missing_reason": missing_reason,
        "conflict_reason": conflict_reason,
        "source_authority": source_authority,
        "next_action": next_action,
        "provenance": list(provenance),
    }


def _identity_candidate(
    *,
    generated_strategy_id: str,
    identity_class: str,
    requested_identity: str,
    candidate_id: str,
    candidate_authority: str,
    alias_evidence: list[str],
    conflict_evidence: list[str],
    provenance: list[str],
) -> dict[str, Any]:
    return {
        "generated_strategy_id": generated_strategy_id,
        "identity_class": identity_class,
        "requested_identity": requested_identity,
        "candidate_id": candidate_id,
        "candidate_authority": candidate_authority,
        "alias_evidence": list(alias_evidence),
        "conflict_evidence": list(conflict_evidence),
        "provenance": list(provenance),
    }


def _identity_decision(
    *,
    generated_strategy_id: str,
    identity_class: str,
    requested_identity: str,
    candidate_ids: list[str],
    candidate_authority: str,
    selected_identity: str,
    outcome: str,
    selection_reason: str,
    rejection_reasons: list[str],
    provenance: list[str],
) -> dict[str, Any]:
    decision_key = {
        "generated_strategy_id": generated_strategy_id,
        "identity_class": identity_class,
        "requested_identity": requested_identity,
        "selected_identity": selected_identity,
        "outcome": outcome,
    }
    return {
        "decision_id": f"qrd_{stable_digest(decision_key)[:16]}",
        "generated_strategy_id": generated_strategy_id,
        "identity_class": identity_class,
        "requested_identity": requested_identity,
        "candidate_ids": list(candidate_ids),
        "candidate_authority": candidate_authority,
        "selected_identity": selected_identity,
        "selection_reason": selection_reason,
        "rejection_reasons": list(rejection_reasons),
        "confidence_or_authority_state": candidate_authority,
        "resolution_outcome": outcome,
        "provenance": list(provenance),
    }


def _cache_dataset_id(row: dict[str, Any]) -> str:
    key = {
        "source": str(row.get("source") or ""),
        "instrument": str(row.get("instrument") or ""),
        "timeframe": str(row.get("timeframe") or ""),
    }
    return f"qds_{stable_digest(key)[:16]}"


def _cache_snapshot_id(row: dict[str, Any]) -> str:
    key = {
        "source": str(row.get("source") or ""),
        "instrument": str(row.get("instrument") or ""),
        "timeframe": str(row.get("timeframe") or ""),
        "content_hash": str(row.get("content_hash") or ""),
    }
    return f"qsn_{stable_digest(key)[:16]}"


def _single_instrument_universe_id(canonical_instrument_id: str) -> str:
    return f"quv_{stable_digest({'kind': 'single_instrument_universe', 'instrument': canonical_instrument_id})[:16]}"


def _load_inputs(repo_root: Path) -> dict[str, Any]:
    strategy_registry_rows = _read_rows(repo_root / "generated_research/registry/generated_strategy_registry.v1.json")
    preset_rows = _read_rows(repo_root / "generated_research/presets/generated_research_presets.v1.json")
    null_rows = _read_rows(repo_root / "generated_research/lineage/generated_null_controls.v1.json")
    lineage_rows = _read_rows(repo_root / "generated_research/lineage/generated_campaign_lineage.v1.json")
    generated_thesis_rows = _read_rows(repo_root / "generated_research/hypotheses/registry/generated_thesis_registry.v1.json")
    resolved_thesis_rows = _read_rows(repo_root / "generated_research/hypotheses/registry/resolved_thesis_catalog.v1.json")
    identity_hint_rows = _read_rows(repo_root / "logs/qre_identity_ambiguity_resolution/latest.json")
    instrument_rows = _read_rows(repo_root / "artifacts/identity/instrument_identity_latest.v1.json")
    universe_rows = _read_rows(repo_root / "artifacts/universe/equity_universe_catalog_latest.v1.json")
    cache_rows = _read_rows(repo_root / "logs/qre_data_cache_manifest/latest.json")
    source_normalization_rows = _read_rows(repo_root / "logs/qre_source_identity_authority_normalization/latest.json")
    spec_dir = repo_root / "generated_research/specs"
    specs: dict[str, dict[str, Any]] = {}
    if spec_dir.is_dir():
        for path in sorted(spec_dir.glob("qsp_*.json")):
            payload = _read_json(path)
            if payload:
                specs[str(payload.get("strategy_spec_id") or path.stem)] = payload
    return {
        "strategy_registry_by_id": {
            str(row.get("generated_strategy_id") or ""): row
            for row in strategy_registry_rows
            if str(row.get("generated_strategy_id") or "")
        },
        "preset_by_strategy_id": {
            str(row.get("generated_strategy_id") or ""): row
            for row in preset_rows
            if str(row.get("generated_strategy_id") or "")
        },
        "null_by_strategy_id": {
            str(row.get("generated_strategy_id") or ""): row
            for row in null_rows
            if str(row.get("generated_strategy_id") or "")
        },
        "lineage_by_strategy_id": {
            str(row.get("generated_strategy_id") or ""): row
            for row in lineage_rows
            if str(row.get("generated_strategy_id") or "")
        },
        "generated_thesis_by_id": {
            str(row.get("thesis_id") or ""): row
            for row in generated_thesis_rows
            if str(row.get("thesis_id") or "")
        },
        "resolved_thesis_by_hypothesis": {
            str(row.get("source_hypothesis_id") or ""): row
            for row in resolved_thesis_rows
            if str(row.get("source_hypothesis_id") or "")
        },
        "identity_hint_by_hypothesis": {
            str(row.get("source_hypothesis_id") or ""): row
            for row in identity_hint_rows
            if str(row.get("source_hypothesis_id") or "")
        },
        "instrument_rows": instrument_rows,
        "universe_rows": universe_rows,
        "cache_rows": cache_rows,
        "source_normalization_rows": source_normalization_rows,
        "specs": specs,
    }


def _resolve_instrument(
    *,
    generated_strategy_id: str,
    source_hypothesis_id: str,
    identity_hint: dict[str, Any],
    instrument_rows: list[dict[str, Any]],
) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
    candidates: list[dict[str, Any]] = []
    decisions: list[dict[str, Any]] = []
    requested = str(identity_hint.get("instrument_identity") or "")
    provenance = [
        "logs/qre_identity_ambiguity_resolution/latest.json",
        "artifacts/identity/instrument_identity_latest.v1.json",
    ]
    if not requested:
        decision = _identity_decision(
            generated_strategy_id=generated_strategy_id,
            identity_class="instrument",
            requested_identity=requested,
            candidate_ids=[],
            candidate_authority="missing",
            selected_identity="",
            outcome="MISSING_NO_CANDIDATE",
            selection_reason="no instrument identity surfaced by authoritative readiness inputs",
            rejection_reasons=["missing_instrument_identity"],
            provenance=provenance,
        )
        decisions.append(decision)
        return (
            {
                "state": "MISSING",
                "selected_identity": "",
                "instrument_row": None,
                "reason": "missing_instrument_identity",
            },
            candidates,
            decisions,
        )
    matches = [
        row
        for row in instrument_rows
        if requested in {
            str(row.get("symbol") or ""),
            str(row.get("provider_symbol") or ""),
            str(row.get("canonical_id") or ""),
        }
    ]
    for row in matches:
        candidates.append(
            _identity_candidate(
                generated_strategy_id=generated_strategy_id,
                identity_class="instrument",
                requested_identity=requested,
                candidate_id=str(row.get("canonical_id") or ""),
                candidate_authority="authoritative_registry",
                alias_evidence=[f"instrument_identity::{requested}"],
                conflict_evidence=[],
                provenance=provenance,
            )
        )
    if len(matches) == 1:
        row = matches[0]
        decision = _identity_decision(
            generated_strategy_id=generated_strategy_id,
            identity_class="instrument",
            requested_identity=requested,
            candidate_ids=[str(row.get("canonical_id") or "")],
            candidate_authority="authoritative_registry",
            selected_identity=str(row.get("canonical_id") or ""),
            outcome="RESOLVED_UNIQUE_AUTHORITATIVE",
            selection_reason="single canonical instrument row matched the authoritative hint",
            rejection_reasons=[],
            provenance=provenance,
        )
        decisions.append(decision)
        return (
            {
                "state": "RESOLVED",
                "selected_identity": str(row.get("canonical_id") or ""),
                "instrument_row": row,
                "reason": "single_canonical_match",
            },
            candidates,
            decisions,
        )
    outcome = "AMBIGUOUS_MULTIPLE_AUTHORITATIVE" if matches else "MISSING_NO_CANDIDATE"
    state = "AMBIGUOUS" if matches else "MISSING"
    decision = _identity_decision(
        generated_strategy_id=generated_strategy_id,
        identity_class="instrument",
        requested_identity=requested,
        candidate_ids=[str(row.get("canonical_id") or "") for row in matches],
        candidate_authority="authoritative_registry" if matches else "missing",
        selected_identity="",
        outcome=outcome,
        selection_reason="multiple authoritative matches" if matches else "no canonical instrument matched the authoritative hint",
        rejection_reasons=["instrument_identity_ambiguous" if matches else "instrument_identity_missing"],
        provenance=provenance,
    )
    decisions.append(decision)
    return (
        {
            "state": state,
            "selected_identity": "",
            "instrument_row": None,
            "reason": "instrument_identity_ambiguous" if matches else "instrument_identity_missing",
        },
        candidates,
        decisions,
    )


def _resolve_universe(
    *,
    generated_strategy_id: str,
    spec: dict[str, Any],
    preset_row: dict[str, Any] | None,
    instrument_resolution: dict[str, Any],
) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
    candidates: list[dict[str, Any]] = []
    decisions: list[dict[str, Any]] = []
    universe_constraints = [str(value) for value in spec.get("universe_constraints", []) if str(value)]
    preset_universe = [str(value) for value in (preset_row or {}).get("universe", []) if str(value)]
    requested = preset_universe[0] if len(preset_universe) == 1 else "|".join(universe_constraints)
    provenance = [
        "generated_research/specs",
        "generated_research/presets/generated_research_presets.v1.json",
        "artifacts/universe/equity_universe_catalog_latest.v1.json",
    ]
    if "single_resolved_instrument_only" in universe_constraints and instrument_resolution.get("state") == "RESOLVED":
        canonical_instrument_id = str(instrument_resolution["selected_identity"])
        selected_identity = _single_instrument_universe_id(canonical_instrument_id)
        candidates.append(
            _identity_candidate(
                generated_strategy_id=generated_strategy_id,
                identity_class="universe",
                requested_identity=requested,
                candidate_id=selected_identity,
                candidate_authority="derived_from_authoritative_instrument",
                alias_evidence=[canonical_instrument_id],
                conflict_evidence=[],
                provenance=provenance,
            )
        )
        decisions.append(
            _identity_decision(
                generated_strategy_id=generated_strategy_id,
                identity_class="universe",
                requested_identity=requested,
                candidate_ids=[selected_identity],
                candidate_authority="derived_from_authoritative_instrument",
                selected_identity=selected_identity,
                outcome="RESOLVED_WITH_LIMITATIONS",
                selection_reason="single-instrument strategy can bind a deterministic one-member research universe from the resolved instrument",
                rejection_reasons=[],
                provenance=provenance,
            )
        )
        return (
            {
                "state": "RESOLVED_WITH_LIMITATIONS",
                "selected_identity": selected_identity,
                "reason": "single_instrument_universe_bound_from_instrument",
            },
            candidates,
            decisions,
        )
    if "breadth_resolved_multi_asset_basket" in universe_constraints or "breadth_resolved_multi_asset_basket" in preset_universe:
        requested = "breadth_resolved_multi_asset_basket"
        candidates.append(
            _identity_candidate(
                generated_strategy_id=generated_strategy_id,
                identity_class="universe",
                requested_identity=requested,
                candidate_id=requested,
                candidate_authority="non_authoritative_generated_alias",
                alias_evidence=["generated specification or preset alias only"],
                conflict_evidence=[],
                provenance=provenance,
            )
        )
        decisions.append(
            _identity_decision(
                generated_strategy_id=generated_strategy_id,
                identity_class="universe",
                requested_identity=requested,
                candidate_ids=[requested],
                candidate_authority="non_authoritative_generated_alias",
                selected_identity="",
                outcome="BLOCKED_NON_AUTHORITATIVE_ONLY",
                selection_reason="generated basket alias has no single authoritative universe member set or canonical universe binding",
                rejection_reasons=["non_authoritative_universe_alias_only"],
                provenance=provenance,
            )
        )
        return (
            {
                "state": "BLOCKED",
                "selected_identity": "",
                "reason": "non_authoritative_universe_alias_only",
            },
            candidates,
            decisions,
        )
    decisions.append(
        _identity_decision(
            generated_strategy_id=generated_strategy_id,
            identity_class="universe",
            requested_identity=requested,
            candidate_ids=[],
            candidate_authority="missing",
            selected_identity="",
            outcome="MISSING_NO_CANDIDATE",
            selection_reason="no authoritative universe binding surfaced for the strategy",
            rejection_reasons=["universe_identity_missing"],
            provenance=provenance,
        )
    )
    return (
        {
            "state": "MISSING",
            "selected_identity": "",
            "reason": "universe_identity_missing",
        },
        candidates,
        decisions,
    )


def _resolve_timeframe(spec: dict[str, Any], preset_row: dict[str, Any] | None) -> dict[str, Any]:
    if preset_row and str(preset_row.get("timeframe") or ""):
        return {
            "state": "RESOLVED",
            "selected_timeframe": str(preset_row.get("timeframe") or ""),
            "reason": "preset_timeframe",
        }
    timeframes = [str(value) for value in spec.get("timeframe", []) if str(value)]
    if len(timeframes) == 1:
        return {
            "state": "RESOLVED",
            "selected_timeframe": timeframes[0],
            "reason": "single_spec_timeframe",
        }
    if len(timeframes) > 1:
        return {
            "state": "AMBIGUOUS",
            "selected_timeframe": "",
            "reason": "multiple_spec_timeframes",
            "candidates": timeframes,
        }
    return {
        "state": "MISSING",
        "selected_timeframe": "",
        "reason": "timeframe_missing",
    }


def _resolve_data_binding(
    *,
    instrument_resolution: dict[str, Any],
    timeframe_resolution: dict[str, Any],
    cache_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    if instrument_resolution.get("state") not in {"RESOLVED", "RESOLVED_WITH_LIMITATIONS"}:
        return {
            "outcome": "DATASET_MISSING",
            "state": "BLOCKED",
            "reason": "instrument_identity_not_resolved",
            "coverage_row": None,
        }
    if timeframe_resolution.get("state") != "RESOLVED":
        return {
            "outcome": "DATASET_MISSING",
            "state": "BLOCKED",
            "reason": "timeframe_not_resolved",
            "coverage_row": None,
        }
    instrument_row = instrument_resolution.get("instrument_row") or {}
    if not instrument_row:
        return {
            "outcome": "DATASET_MISSING",
            "state": "BLOCKED",
            "reason": "instrument_row_missing",
            "coverage_row": None,
        }
    symbol_candidates = {
        str(instrument_row.get("symbol") or ""),
        str(instrument_row.get("provider_symbol") or ""),
    }
    timeframe = str(timeframe_resolution.get("selected_timeframe") or "")
    matches = [
        row
        for row in cache_rows
        if str(row.get("timeframe") or "") == timeframe and str(row.get("instrument") or "") in symbol_candidates
    ]
    if not matches:
        return {
            "outcome": "COVERAGE_INSUFFICIENT",
            "state": "BLOCKED",
            "reason": "no_cache_row_for_resolved_instrument_and_timeframe",
            "coverage_row": None,
        }
    sources = sorted({str(row.get("source") or "") for row in matches if str(row.get("source") or "")})
    if len(sources) > 1:
        return {
            "outcome": "DATA_SOURCE_AMBIGUOUS",
            "state": "AMBIGUOUS",
            "reason": "multiple_cache_sources_for_same_binding",
            "coverage_row": None,
            "source_candidates": sources,
        }
    row = sorted(
        matches,
        key=lambda item: (
            str(item.get("source") or ""),
            str(item.get("instrument") or ""),
            str(item.get("timeframe") or ""),
            str(item.get("content_hash") or ""),
        ),
    )[0]
    return {
        "outcome": "DATA_BINDING_READY_WITH_LIMITATIONS",
        "state": "RESOLVED_WITH_LIMITATIONS",
        "reason": "single_cache_binding_available_but_source_quality_not_promoted_to_point_in_time_authority",
        "coverage_row": row,
        "source_identity": str(row.get("source") or ""),
        "dataset_identity": _cache_dataset_id(row),
        "snapshot_identity": _cache_snapshot_id(row),
    }


def _assess_window_capacity(
    *,
    data_binding: dict[str, Any],
    timeframe_resolution: dict[str, Any],
    spec: dict[str, Any],
) -> dict[str, Any]:
    coverage_row = data_binding.get("coverage_row")
    if not coverage_row:
        return {
            "outcome": "DATA_COVERAGE_INSUFFICIENT",
            "state": "BLOCKED",
            "reason": data_binding.get("reason", "data_binding_missing"),
        }
    if timeframe_resolution.get("state") != "RESOLVED":
        return {
            "outcome": "TRAIN_CAPACITY_BLOCKED",
            "state": "BLOCKED",
            "reason": "timeframe_not_resolved",
        }
    return {
        "outcome": "OOS_CAPACITY_BLOCKED",
        "state": "BLOCKED",
        "reason": "campaign_window_boundaries_not_materialized_from_authoritative_policy",
        "earliest_usable_timestamp_utc": str(coverage_row.get("min_timestamp_utc") or ""),
        "latest_usable_timestamp_utc": str(coverage_row.get("max_timestamp_utc") or ""),
        "warmup_requirement_bars": max(
            [int(value) for value in dict(spec.get("warmup_requirements") or {}).values() if isinstance(value, int)]
            or [0]
        ),
        "consumed_oos_windows": [],
    }


def _assess_preset_readiness(
    *,
    generated_strategy_id: str,
    preset_row: dict[str, Any] | None,
    timeframe_resolution: dict[str, Any],
    instrument_resolution: dict[str, Any],
    data_binding: dict[str, Any],
) -> dict[str, Any]:
    if preset_row:
        outcome = "PRESET_READY_WITH_LIMITATIONS"
        if str((preset_row.get("slippage_assumptions") or {}).get("status") or "") == "materialized":
            outcome = "PRESET_READY"
        return {
            "generated_strategy_id": generated_strategy_id,
            "outcome": outcome,
            "reason": "generated_preset_present",
            "preset_id": str(preset_row.get("preset_id") or ""),
            "preset_name": str(preset_row.get("preset_name") or ""),
            "timeframe": str(preset_row.get("timeframe") or ""),
            "universe": list(preset_row.get("universe") or []),
        }
    if timeframe_resolution.get("state") != "RESOLVED":
        return {
            "generated_strategy_id": generated_strategy_id,
            "outcome": "PRESET_BLOCKED_PARAMETERS",
            "reason": "timeframe_ambiguity_prevents_preset_materialization",
        }
    if instrument_resolution.get("state") not in {"RESOLVED", "RESOLVED_WITH_LIMITATIONS"}:
        return {
            "generated_strategy_id": generated_strategy_id,
            "outcome": "PRESET_BLOCKED_IDENTITY",
            "reason": "instrument_or_universe_not_resolved",
        }
    if data_binding.get("state") not in {"RESOLVED", "RESOLVED_WITH_LIMITATIONS"}:
        return {
            "generated_strategy_id": generated_strategy_id,
            "outcome": "PRESET_BLOCKED_DATA",
            "reason": "data_binding_not_ready",
        }
    return {
        "generated_strategy_id": generated_strategy_id,
        "outcome": "PRESET_BLOCKED_POLICY",
        "reason": "generated_preset_writer_not_triggered_without_authoritative_campaign_path",
    }


def _assess_null_controls(
    *,
    generated_strategy_id: str,
    source_hypothesis_id: str,
    null_row: dict[str, Any] | None,
    data_binding: dict[str, Any],
    window_capacity: dict[str, Any],
) -> list[dict[str, Any]]:
    if not null_row:
        return [
            {
                "generated_strategy_id": generated_strategy_id,
                "source_hypothesis_id": source_hypothesis_id,
                "control_identity": "",
                "control_class": "",
                "outcome": "IMPLEMENTATION_MISSING",
                "blocker": "null_control_spec_missing",
                "required_inputs": [],
                "provenance": ["generated_research/lineage/generated_null_controls.v1.json"],
            }
        ]
    rows: list[dict[str, Any]] = []
    for control in [str(value) for value in null_row.get("required_controls", []) if str(value)]:
        if data_binding.get("state") not in {"RESOLVED", "RESOLVED_WITH_LIMITATIONS"}:
            outcome = "DATA_BLOCKED"
            blocker = data_binding.get("reason", "data_binding_not_ready")
        elif str(window_capacity.get("outcome") or "").endswith("BLOCKED"):
            outcome = "WINDOW_BLOCKED"
            blocker = str(window_capacity.get("reason") or "window_capacity_not_ready")
        elif bool(null_row.get("execution_readiness")):
            outcome = "NULL_CONTROL_EXECUTION_READY"
            blocker = ""
        elif bool(null_row.get("implementation_readiness")):
            outcome = "SPECIFICATION_ONLY"
            blocker = "execution_path_not_materialized"
        else:
            outcome = "IMPLEMENTATION_MISSING"
            blocker = "implementation_readiness_false"
        rows.append(
            {
                "generated_strategy_id": generated_strategy_id,
                "source_hypothesis_id": source_hypothesis_id,
                "control_identity": f"qnr_{stable_digest({'strategy': generated_strategy_id, 'control': control})[:16]}",
                "control_class": control,
                "required_inputs": ["resolved_dataset", "resolved_windows", "resolved_strategy_registration"],
                "deterministic_seed": str(null_row.get("deterministic_seed") or ""),
                "outcome": outcome,
                "blocker": blocker,
                "provenance": [
                    "generated_research/lineage/generated_null_controls.v1.json",
                    "generated_research/registry/generated_strategy_registry.v1.json",
                ],
            }
        )
    return rows


def _campaign_metadata_row(
    *,
    registry_row: dict[str, Any],
    spec: dict[str, Any],
    preset_status: dict[str, Any],
    universe_resolution: dict[str, Any],
    instrument_resolution: dict[str, Any],
    data_binding: dict[str, Any],
    timeframe_resolution: dict[str, Any],
    window_capacity: dict[str, Any],
    null_control_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    blockers: list[str] = []
    if universe_resolution.get("state") not in {"RESOLVED", "RESOLVED_WITH_LIMITATIONS"}:
        blockers.append("universe_not_resolved")
    if instrument_resolution.get("state") not in {"RESOLVED", "RESOLVED_WITH_LIMITATIONS"} and "single_resolved_instrument_only" in spec.get("universe_constraints", []):
        blockers.append("instrument_not_resolved")
    if data_binding.get("state") not in {"RESOLVED", "RESOLVED_WITH_LIMITATIONS"}:
        blockers.append("data_binding_not_ready")
    if timeframe_resolution.get("state") != "RESOLVED":
        blockers.append("timeframe_not_resolved")
    if not str(preset_status.get("preset_id") or ""):
        blockers.append("preset_not_ready")
    if str(window_capacity.get("outcome") or "").endswith("BLOCKED"):
        blockers.append("window_capacity_not_ready")
    null_blockers = [row["blocker"] for row in null_control_rows if row.get("outcome") != "NULL_CONTROL_EXECUTION_READY"]
    if null_blockers:
        blockers.append("null_controls_not_execution_ready")
    metadata_state = "CAMPAIGN_METADATA_READY" if not blockers else "PREREGISTRATION_BLOCKED"
    return {
        "campaign_candidate_id": f"qcmr_{stable_digest({'strategy': registry_row['generated_strategy_id'], 'kind': 'campaign_candidate'})[:16]}",
        "metadata_state": metadata_state,
        "generated_strategy_id": str(registry_row.get("generated_strategy_id") or ""),
        "generated_registration_id": str(registry_row.get("generated_registration_id") or ""),
        "strategy_spec_id": str(registry_row.get("strategy_spec_id") or ""),
        "thesis_id": str(registry_row.get("thesis_id") or ""),
        "source_hypothesis_id": str(registry_row.get("source_hypothesis_id") or ""),
        "preset_id": str(preset_status.get("preset_id") or ""),
        "universe_identity": str(universe_resolution.get("selected_identity") or ""),
        "instrument_identity": str(instrument_resolution.get("selected_identity") or ""),
        "source_identity": str(data_binding.get("source_identity") or ""),
        "dataset_identity": str(data_binding.get("dataset_identity") or ""),
        "snapshot_identity": str(data_binding.get("snapshot_identity") or ""),
        "timeframe": str(timeframe_resolution.get("selected_timeframe") or ""),
        "train_window": "",
        "validation_window": "",
        "oos_window": "",
        "costs": dict(spec.get("cost_assumptions") or {}),
        "slippage": dict(spec.get("slippage_assumptions") or {}),
        "null_controls": [str(row.get("control_class") or "") for row in null_control_rows],
        "blockers": blockers,
        "provenance": [
            "generated_research/registry/generated_strategy_registry.v1.json",
            "generated_research/specs",
            "generated_research/presets/generated_research_presets.v1.json",
            "generated_research/lineage/generated_null_controls.v1.json",
            "logs/qre_data_cache_manifest/latest.json",
        ],
    }


def _lineage_row(
    *,
    registry_row: dict[str, Any],
    metadata_row: dict[str, Any],
    source_hypothesis_id: str,
) -> dict[str, Any]:
    blockers = list(metadata_row.get("blockers") or [])
    state = "CAMPAIGN_LINEAGE_COMPLETE" if not blockers else "CAMPAIGN_LINEAGE_COMPLETE_WITH_LIMITATIONS"
    return {
        "generated_strategy_id": str(registry_row.get("generated_strategy_id") or ""),
        "source_hypothesis_id": source_hypothesis_id,
        "lineage_state": state,
        "campaign_candidate_id": str(metadata_row.get("campaign_candidate_id") or ""),
        "blockers": blockers,
        "lineage_identity": f"qcl_{stable_digest({'strategy': registry_row['generated_strategy_id'], 'kind': 'campaign_lineage_resolution'})[:16]}",
        "provenance": [
            "generated_research/hypotheses/registry/generated_thesis_registry.v1.json",
            "generated_research/primitives/registry/generated_primitive_registry.v1.json",
            "generated_research/registry/generated_strategy_registry.v1.json",
            "generated_research/presets/generated_research_presets.v1.json",
            "generated_research/lineage/generated_null_controls.v1.json",
        ],
    }


def _portfolio_row(
    *,
    registry_row: dict[str, Any],
    preset_status: dict[str, Any],
    data_binding: dict[str, Any],
    window_capacity: dict[str, Any],
    null_control_rows: list[dict[str, Any]],
    lineage_row: dict[str, Any],
    universe_resolution: dict[str, Any],
) -> dict[str, Any]:
    if universe_resolution.get("state") not in {"RESOLVED", "RESOLVED_WITH_LIMITATIONS"}:
        status = "BLOCKED_IDENTITY"
        blockers = [str(universe_resolution.get("reason") or "identity_not_resolved")]
    elif str(data_binding.get("reason") or "") == "timeframe_not_resolved":
        status = "BLOCKED_WINDOWS"
        blockers = ["timeframe_not_resolved"]
    elif data_binding.get("state") not in {"RESOLVED", "RESOLVED_WITH_LIMITATIONS"}:
        status = "BLOCKED_DATA"
        blockers = [str(data_binding.get("reason") or "data_binding_not_ready")]
    elif str(window_capacity.get("outcome") or "").endswith("BLOCKED"):
        status = "BLOCKED_WINDOWS"
        blockers = [str(window_capacity.get("reason") or "window_capacity_not_ready")]
    elif any(row.get("outcome") != "NULL_CONTROL_EXECUTION_READY" for row in null_control_rows):
        status = "BLOCKED_NULL_CONTROLS"
        blockers = sorted({str(row.get("blocker") or row.get("outcome") or "") for row in null_control_rows})
    elif str(lineage_row.get("lineage_state") or "") not in {"CAMPAIGN_LINEAGE_COMPLETE", "CAMPAIGN_LINEAGE_COMPLETE_WITH_LIMITATIONS"}:
        status = "BLOCKED_LINEAGE"
        blockers = [str(lineage_row.get("lineage_state") or "lineage_not_ready")]
    elif preset_status.get("outcome") != "PRESET_READY":
        status = "READY_WITH_LIMITATIONS"
        blockers = [str(preset_status.get("reason") or "preset_limited")]
    else:
        status = "READY_FOR_PREREGISTRATION"
        blockers = []
    return {
        "portfolio_cell_id": f"qrp_{stable_digest({'strategy': registry_row['generated_strategy_id'], 'kind': 'portfolio_readiness'})[:16]}",
        "generated_strategy_id": str(registry_row.get("generated_strategy_id") or ""),
        "source_hypothesis_id": str(registry_row.get("source_hypothesis_id") or ""),
        "strategy_spec_id": str(registry_row.get("strategy_spec_id") or ""),
        "status": status,
        "blockers": blockers,
        "next_action": (
            "create_second_campaign_preregistration_manifest"
            if status == "READY_FOR_PREREGISTRATION"
            else "preserve_fail_closed_readiness_blockers"
        ),
    }


def _markdown_closeout(payload: dict[str, Any]) -> str:
    lines = [
        "# Automated Campaign Readiness Closeout",
        "",
        f"- outcome: `{payload['overall_outcome']}`",
        f"- campaign-ready cells: `{payload['summary']['campaign_ready_cells']}`",
        f"- strategies processed: `{payload['summary']['strategies_processed']}`",
        f"- exact next action: `{payload['exact_next_action']}`",
        "",
        "## Strategy Outcomes",
    ]
    for row in payload.get("strategy_summaries", []):
        lines.append(
            f"- `{row['generated_strategy_id']}`: `{row['portfolio_status']}` -> `{row['primary_blocker']}`"
        )
    lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def run_readiness_remediation(
    *,
    repo_root: Path | None = None,
    generated_strategy_ids: list[str] | None = None,
) -> dict[str, Any]:
    repo_root = (repo_root or REPO_ROOT).resolve()
    inputs = _load_inputs(repo_root)
    available_ids = sorted(inputs["strategy_registry_by_id"].keys())
    target_ids = sorted(generated_strategy_ids or available_ids)

    gap_rows: list[dict[str, Any]] = []
    candidate_rows: list[dict[str, Any]] = []
    decision_rows: list[dict[str, Any]] = []
    data_binding_rows: list[dict[str, Any]] = []
    window_rows: list[dict[str, Any]] = []
    preset_rows: list[dict[str, Any]] = []
    null_rows: list[dict[str, Any]] = []
    metadata_rows: list[dict[str, Any]] = []
    lineage_rows: list[dict[str, Any]] = []
    portfolio_rows: list[dict[str, Any]] = []
    strategy_summaries: list[dict[str, Any]] = []

    for generated_strategy_id in target_ids:
        registry_row = dict(inputs["strategy_registry_by_id"].get(generated_strategy_id) or {})
        if not registry_row:
            continue
        source_hypothesis_id = str(registry_row.get("source_hypothesis_id") or "")
        spec = dict(inputs["specs"].get(str(registry_row.get("strategy_spec_id") or "")) or {})
        preset_row = dict(inputs["preset_by_strategy_id"].get(generated_strategy_id) or {})
        null_row = dict(inputs["null_by_strategy_id"].get(generated_strategy_id) or {})
        identity_hint = dict(inputs["identity_hint_by_hypothesis"].get(source_hypothesis_id) or {})

        instrument_resolution, instrument_candidates, instrument_decisions = _resolve_instrument(
            generated_strategy_id=generated_strategy_id,
            source_hypothesis_id=source_hypothesis_id,
            identity_hint=identity_hint,
            instrument_rows=inputs["instrument_rows"],
        )
        universe_resolution, universe_candidates, universe_decisions = _resolve_universe(
            generated_strategy_id=generated_strategy_id,
            spec=spec,
            preset_row=preset_row or None,
            instrument_resolution=instrument_resolution,
        )
        timeframe_resolution = _resolve_timeframe(spec, preset_row or None)
        data_binding = _resolve_data_binding(
            instrument_resolution=instrument_resolution,
            timeframe_resolution=timeframe_resolution,
            cache_rows=inputs["cache_rows"],
        )
        window_capacity = _assess_window_capacity(
            data_binding=data_binding,
            timeframe_resolution=timeframe_resolution,
            spec=spec,
        )
        preset_status = _assess_preset_readiness(
            generated_strategy_id=generated_strategy_id,
            preset_row=preset_row or None,
            timeframe_resolution=timeframe_resolution,
            instrument_resolution=instrument_resolution,
            data_binding=data_binding,
        )
        null_control_rows = _assess_null_controls(
            generated_strategy_id=generated_strategy_id,
            source_hypothesis_id=source_hypothesis_id,
            null_row=null_row or None,
            data_binding=data_binding,
            window_capacity=window_capacity,
        )
        metadata_row = _campaign_metadata_row(
            registry_row=registry_row,
            spec=spec,
            preset_status=preset_status,
            universe_resolution=universe_resolution,
            instrument_resolution=instrument_resolution,
            data_binding=data_binding,
            timeframe_resolution=timeframe_resolution,
            window_capacity=window_capacity,
            null_control_rows=null_control_rows,
        )
        lineage_row = _lineage_row(
            registry_row=registry_row,
            metadata_row=metadata_row,
            source_hypothesis_id=source_hypothesis_id,
        )
        portfolio_row = _portfolio_row(
            registry_row=registry_row,
            preset_status=preset_status,
            data_binding=data_binding,
            window_capacity=window_capacity,
            null_control_rows=null_control_rows,
            lineage_row=lineage_row,
            universe_resolution=universe_resolution,
        )

        candidate_rows.extend(instrument_candidates)
        candidate_rows.extend(universe_candidates)
        decision_rows.extend(instrument_decisions)
        decision_rows.extend(universe_decisions)

        source_field = _field_record(
            field_name="source",
            state=(
                "RESOLVED_WITH_LIMITATIONS"
                if data_binding.get("state") == "RESOLVED_WITH_LIMITATIONS"
                else "BLOCKED"
            ),
            authoritative_value=str(data_binding.get("source_identity") or ""),
            candidate_refs=[],
            missing_reason=str(data_binding.get("reason") or ""),
            conflict_reason="",
            source_authority="logs/qre_data_cache_manifest/latest.json",
            next_action="bind_source_from_authoritative_cache_row" if data_binding.get("source_identity") else "resolve_universe_and_timeframe_before_source_binding",
            provenance=["logs/qre_data_cache_manifest/latest.json"],
        )
        dataset_field = _field_record(
            field_name="dataset",
            state=(
                "RESOLVED_WITH_LIMITATIONS"
                if data_binding.get("dataset_identity")
                else "BLOCKED"
            ),
            authoritative_value=str(data_binding.get("dataset_identity") or ""),
            candidate_refs=[],
            missing_reason=str(data_binding.get("reason") or ""),
            conflict_reason="",
            source_authority="logs/qre_data_cache_manifest/latest.json",
            next_action="preserve_cache_bound_dataset_identity" if data_binding.get("dataset_identity") else "resolve_binding_before_dataset_identity",
            provenance=["logs/qre_data_cache_manifest/latest.json"],
        )
        snapshot_field = _field_record(
            field_name="snapshot",
            state=(
                "RESOLVED_WITH_LIMITATIONS"
                if data_binding.get("snapshot_identity")
                else "BLOCKED"
            ),
            authoritative_value=str(data_binding.get("snapshot_identity") or ""),
            candidate_refs=[],
            missing_reason=str(data_binding.get("reason") or ""),
            conflict_reason="",
            source_authority="logs/qre_data_cache_manifest/latest.json",
            next_action="preserve_content_addressed_snapshot_identity" if data_binding.get("snapshot_identity") else "resolve_binding_before_snapshot_identity",
            provenance=["logs/qre_data_cache_manifest/latest.json"],
        )
        timeframe_field = _field_record(
            field_name="timeframe",
            state="RESOLVED" if timeframe_resolution.get("state") == "RESOLVED" else ("AMBIGUOUS" if timeframe_resolution.get("state") == "AMBIGUOUS" else "MISSING"),
            authoritative_value=str(timeframe_resolution.get("selected_timeframe") or ""),
            candidate_refs=list(timeframe_resolution.get("candidates") or []),
            missing_reason=str(timeframe_resolution.get("reason") or ""),
            conflict_reason="multiple timeframes available" if timeframe_resolution.get("state") == "AMBIGUOUS" else "",
            source_authority="generated_research/specs or generated preset",
            next_action="use_preset_timeframe" if timeframe_resolution.get("state") == "RESOLVED" else "preserve_fail_closed_timeframe_ambiguity",
            provenance=["generated_research/specs", "generated_research/presets/generated_research_presets.v1.json"],
        )
        gap_rows.append(
            {
                "generated_strategy_id": generated_strategy_id,
                "source_hypothesis_id": source_hypothesis_id,
                "generated_registration_id": str(registry_row.get("generated_registration_id") or ""),
                "readiness_state": "READINESS_GAPS_IDENTIFIED",
                "aggregate_blocker": (
                    "identity_not_resolved"
                    if portfolio_row["status"] == "BLOCKED_IDENTITY"
                    else (
                        "generated_preset_missing"
                        if portfolio_row["status"] == "BLOCKED_WINDOWS"
                        else portfolio_row["status"].lower()
                    )
                ),
                "resolved_fields": [
                    field["field_name"]
                    for field in (
                        source_field,
                        dataset_field,
                        snapshot_field,
                        timeframe_field,
                    )
                    if field["state"] in {"RESOLVED", "RESOLVED_WITH_LIMITATIONS"}
                ],
                "unresolved_fields": [
                    field["field_name"]
                    for field in (
                        source_field,
                        dataset_field,
                        snapshot_field,
                        timeframe_field,
                    )
                    if field["state"] not in {"RESOLVED", "RESOLVED_WITH_LIMITATIONS"}
                ]
                + (
                    ["instrument"] if instrument_resolution.get("state") not in {"RESOLVED", "RESOLVED_WITH_LIMITATIONS"} else []
                )
                + (
                    ["universe"] if universe_resolution.get("state") not in {"RESOLVED", "RESOLVED_WITH_LIMITATIONS"} else []
                ),
                "fields": [
                    _field_record(
                        field_name="instrument",
                        state=str(instrument_resolution.get("state") or "BLOCKED"),
                        authoritative_value=str(instrument_resolution.get("selected_identity") or ""),
                        candidate_refs=[row["candidate_id"] for row in instrument_candidates],
                        missing_reason=str(instrument_resolution.get("reason") or ""),
                        conflict_reason="",
                        source_authority="artifacts/identity/instrument_identity_latest.v1.json",
                        next_action="preserve_resolved_instrument" if instrument_resolution.get("selected_identity") else "resolve_instrument_identity",
                        provenance=["artifacts/identity/instrument_identity_latest.v1.json", "logs/qre_identity_ambiguity_resolution/latest.json"],
                    ),
                    _field_record(
                        field_name="universe",
                        state="RESOLVED_WITH_LIMITATIONS" if universe_resolution.get("state") == "RESOLVED_WITH_LIMITATIONS" else "BLOCKED",
                        authoritative_value=str(universe_resolution.get("selected_identity") or ""),
                        candidate_refs=[row["candidate_id"] for row in universe_candidates],
                        missing_reason=str(universe_resolution.get("reason") or ""),
                        conflict_reason="",
                        source_authority="artifacts/universe/equity_universe_catalog_latest.v1.json",
                        next_action="preserve_bound_single_instrument_universe" if universe_resolution.get("selected_identity") else "resolve_authoritative_universe_membership",
                        provenance=["artifacts/universe/equity_universe_catalog_latest.v1.json", "generated_research/presets/generated_research_presets.v1.json"],
                    ),
                    timeframe_field,
                    source_field,
                    dataset_field,
                    snapshot_field,
                    _field_record(
                        field_name="preset",
                        state="RESOLVED_WITH_LIMITATIONS" if preset_status.get("outcome") in {"PRESET_READY", "PRESET_READY_WITH_LIMITATIONS"} else "BLOCKED",
                        authoritative_value=str(preset_status.get("preset_id") or ""),
                        candidate_refs=[str(preset_row.get("preset_id") or "")] if preset_row else [],
                        missing_reason=str(preset_status.get("reason") or ""),
                        conflict_reason="",
                        source_authority="generated_research/presets/generated_research_presets.v1.json",
                        next_action="preserve_generated_preset" if preset_status.get("preset_id") else "resolve_timeframe_before_preset",
                        provenance=["generated_research/presets/generated_research_presets.v1.json"],
                    ),
                ],
                "provenance": sorted(
                    {
                        *source_field["provenance"],
                        *dataset_field["provenance"],
                        *snapshot_field["provenance"],
                        *timeframe_field["provenance"],
                        "generated_research/registry/generated_strategy_registry.v1.json",
                        "generated_research/specs",
                    }
                ),
            }
        )

        binding_row = {
            "generated_strategy_id": generated_strategy_id,
            "source_hypothesis_id": source_hypothesis_id,
            "outcome": str(data_binding.get("outcome") or ""),
            "state": str(data_binding.get("state") or ""),
            "reason": str(data_binding.get("reason") or ""),
            "source_identity": str(data_binding.get("source_identity") or ""),
            "dataset_identity": str(data_binding.get("dataset_identity") or ""),
            "snapshot_identity": str(data_binding.get("snapshot_identity") or ""),
            "coverage_row": dict(data_binding.get("coverage_row") or {}),
            "provenance": ["logs/qre_data_cache_manifest/latest.json"],
        }
        data_binding_rows.append(binding_row)

        window_rows.append(
            {
                "generated_strategy_id": generated_strategy_id,
                "source_hypothesis_id": source_hypothesis_id,
                **window_capacity,
                "provenance": ["logs/qre_data_cache_manifest/latest.json", "generated_research/specs"],
            }
        )
        preset_rows.append(dict(preset_status))
        null_rows.extend(null_control_rows)
        metadata_rows.append(metadata_row)
        lineage_rows.append(lineage_row)
        portfolio_rows.append(portfolio_row)
        strategy_summaries.append(
            {
                "generated_strategy_id": generated_strategy_id,
                "source_hypothesis_id": source_hypothesis_id,
                "portfolio_status": portfolio_row["status"],
                "primary_blocker": (portfolio_row["blockers"][0] if portfolio_row["blockers"] else ""),
            }
        )

    for path, report_kind, rows, identity_key in (
        (READINESS_GAPS_PATH, "qre_strategy_readiness_gaps", gap_rows, "readiness_gap_identity"),
        (IDENTITY_CANDIDATES_PATH, "qre_strategy_identity_candidates", candidate_rows, "identity_candidate_identity"),
        (IDENTITY_DECISIONS_PATH, "qre_strategy_identity_decisions", decision_rows, "identity_decision_identity"),
        (DATA_BINDINGS_PATH, "qre_strategy_data_bindings", data_binding_rows, "data_binding_identity"),
        (WINDOW_CAPACITY_PATH, "qre_strategy_window_capacity", window_rows, "window_capacity_identity"),
        (PRESET_READINESS_PATH, "qre_strategy_preset_readiness", preset_rows, "preset_readiness_identity"),
        (NULL_CONTROL_READINESS_PATH, "qre_strategy_null_control_readiness", null_rows, "null_control_readiness_identity"),
        (CAMPAIGN_METADATA_PATH, "qre_generated_campaign_metadata", metadata_rows, "campaign_metadata_identity"),
        (CAMPAIGN_LINEAGE_PATH, "qre_generated_campaign_lineage_resolution", lineage_rows, "campaign_lineage_resolution_identity"),
        (PORTFOLIO_PATH, "qre_generated_portfolio_readiness", portfolio_rows, "portfolio_readiness_identity"),
    ):
        _write_json(
            _repo_path(repo_root, path),
            {
                identity_key: f"qrr_{stable_digest(rows)[:16]}",
                "schema_version": SCHEMA_VERSION,
                "module_version": MODULE_VERSION,
                "report_kind": report_kind,
                "rows": rows,
            },
        )

    campaign_ready_cells = len([row for row in portfolio_rows if row.get("status") == "READY_FOR_PREREGISTRATION"])
    if campaign_ready_cells:
        manifest_rows = [
            row for row in metadata_rows if str(row.get("metadata_state") or "") == "CAMPAIGN_METADATA_READY"
        ]
        _write_json(
            _repo_path(repo_root, PREREG_MANIFEST_PATH),
            {
                "campaign_manifest_identity": f"qcm_{stable_digest(manifest_rows)[:16]}",
                "schema_version": SCHEMA_VERSION,
                "module_version": MODULE_VERSION,
                "report_kind": "qre_generated_second_campaign_manifest",
                "rows": manifest_rows,
            },
        )

    overall_outcome = "NO_CAMPAIGN_READY_STRATEGIES"
    if campaign_ready_cells:
        overall_outcome = "READY_FOR_SECOND_CAMPAIGN"
    elif any(row.get("status") == "BLOCKED_IDENTITY" for row in portfolio_rows):
        overall_outcome = "IDENTITY_RESOLUTION_BLOCKED"
    elif any(row.get("status") == "BLOCKED_WINDOWS" for row in portfolio_rows):
        overall_outcome = "OOS_CAPACITY_BLOCKED"
    elif any(row.get("status") == "BLOCKED_NULL_CONTROLS" for row in portfolio_rows):
        overall_outcome = "NULL_CONTROL_READINESS_BLOCKED"
    elif portfolio_rows:
        overall_outcome = "READINESS_PARTIALLY_REMEDIATED"
    closeout = {
        "closeout_identity": f"qrca_{stable_digest(strategy_summaries)[:16]}",
        "schema_version": SCHEMA_VERSION,
        "module_version": MODULE_VERSION,
        "report_kind": REPORT_KIND,
        "overall_outcome": overall_outcome,
        "summary": {
            "strategies_processed": len(strategy_summaries),
            "campaign_ready_cells": campaign_ready_cells,
            "identity_blocked_cells": len([row for row in portfolio_rows if row.get("status") == "BLOCKED_IDENTITY"]),
            "window_blocked_cells": len([row for row in portfolio_rows if row.get("status") == "BLOCKED_WINDOWS"]),
            "null_control_blocked_cells": len([row for row in portfolio_rows if row.get("status") == "BLOCKED_NULL_CONTROLS"]),
        },
        "strategy_summaries": sorted(strategy_summaries, key=lambda row: (row["generated_strategy_id"], row["source_hypothesis_id"])),
        "remaining_blockers": sorted(
            {
                blocker
                for row in portfolio_rows
                for blocker in row.get("blockers", [])
                if blocker
            }
        ),
        "exact_next_action": (
            "create_second_campaign_preregistration_manifest"
            if campaign_ready_cells
            else "preserve_fail_closed_readiness_and_route_identity_window_or_null_blockers_to_their_governed_remediation_programs"
        ),
    }
    _write_json(_repo_path(repo_root, CLOSEOUT_JSON_PATH), closeout)
    _atomic_write(_repo_path(repo_root, CLOSEOUT_MD_PATH), _markdown_closeout(closeout))
    return closeout


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="ADE-QRE-022 automated campaign readiness remediation")
    parser.add_argument("--strategy", action="append", default=[], help="Generated strategy id to process")
    args = parser.parse_args(argv)
    run_readiness_remediation(repo_root=REPO_ROOT, generated_strategy_ids=list(args.strategy) or None)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
