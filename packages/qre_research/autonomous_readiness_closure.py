from __future__ import annotations

import argparse
import hashlib
import json
import os
import tempfile
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Final

from packages.qre_research import automated_campaign_readiness as acr
from packages.qre_research.generated_strategy_paths import REPO_ROOT, validate_write_target


SCHEMA_VERSION: Final[str] = "1.0"
MODULE_VERSION: Final[str] = "ade-qre-023.1"
REPORT_KIND: Final[str] = "qre_autonomous_readiness_closure"
WINDOW_POLICY_VERSION: Final[str] = "ade-qre-023.window-policy.1"
UNIVERSE_RESOLVER_VERSION: Final[str] = "ade-qre-023.universe-resolver.1"
TIMEFRAME_RESOLVER_VERSION: Final[str] = "ade-qre-023.timeframe-resolver.1"
PRESET_COMPLETION_VERSION: Final[str] = "ade-qre-023.preset-completion.1"
DATA_BINDING_VERSION: Final[str] = "ade-qre-023.data-binding.1"
NULL_CONTROL_READINESS_VERSION: Final[str] = "ade-qre-023.null-control-readiness.1"

BLOCKER_CLASS: Final[tuple[str, ...]] = (
    "UNIVERSE_IDENTITY_MISSING",
    "UNIVERSE_MEMBERSHIP_HISTORY_MISSING",
    "INSTRUMENT_IDENTITY_MISSING",
    "SOURCE_IDENTITY_MISSING",
    "DATASET_IDENTITY_MISSING",
    "SNAPSHOT_IDENTITY_MISSING",
    "TIMEFRAME_AMBIGUOUS",
    "PRESET_INCOMPLETE",
    "FEATURE_PRIMITIVE_MISSING",
    "DATA_SCHEMA_INCOMPATIBLE",
    "DATA_COVERAGE_INSUFFICIENT",
    "SIGNAL_DENSITY_INSUFFICIENT",
    "TRAIN_WINDOW_MISSING",
    "VALIDATION_WINDOW_MISSING",
    "OOS_WINDOW_MISSING",
    "OOS_INDEPENDENCE_NOT_PROVEN",
    "CONSUMED_OOS_REUSE_RISK",
    "NULL_CONTROL_IMPLEMENTATION_MISSING",
    "NULL_CONTROL_DATA_BLOCKED",
    "COST_MODEL_MISSING",
    "SLIPPAGE_MODEL_MISSING",
    "REGIME_IDENTITY_MISSING",
    "CAMPAIGN_METADATA_INCOMPLETE",
    "CAMPAIGN_LINEAGE_INCOMPLETE",
    "REPRODUCIBILITY_INCOMPLETE",
    "EVIDENCE_AUTHORITY_AMBIGUOUS",
    "COMPUTE_BUDGET_MISSING",
    "TIMEOUT_POLICY_MISSING",
    "STRATEGY_SPEC_INCOMPLETE",
    "STRATEGY_VALIDATION_FAILED",
    "SCIENTIFIC_TESTABILITY_FAILED",
    "DUPLICATE_OR_REJECTED_LINEAGE",
    "NO_SAFE_AUTOMATED_REMEDIATION",
)
REMEDIATION_DECISION: Final[tuple[str, ...]] = (
    "AUTO_REMEDIATE",
    "GENERATE_BOUNDED_CAPABILITY",
    "REPLAY_EXISTING_PIPELINE",
    "ROUTE_TO_EXISTING_PROGRAM",
    "FAIL_CLOSED",
    "EXTERNAL_INPUT_REQUIRED",
    "SCIENTIFIC_REJECTION",
)
TERMINAL_OUTCOME: Final[tuple[str, ...]] = (
    "READY_FOR_PREREGISTRATION",
    "READY_FOR_SECOND_CAMPAIGN",
    "EXTERNALLY_BLOCKED",
    "SCIENTIFICALLY_BLOCKED",
    "NO_VALID_REMEDIATION_PATH",
    "SAFETY_POLICY_BLOCKED",
    "DATA_CAPACITY_BLOCKED",
    "INDEPENDENT_OOS_CAPACITY_BLOCKED",
)
OVERALL_OUTCOME: Final[tuple[str, ...]] = (
    "READY_FOR_SECOND_CAMPAIGN",
    "PARTIAL_READINESS_CLOSURE",
    "INDEPENDENT_OOS_CAPACITY_BLOCKED",
    "DATA_CAPACITY_BLOCKED",
    "SCIENTIFICALLY_BLOCKED",
    "NO_SAFE_REMEDIATION_PATH",
    "LOOP_STALLED_WITH_EVIDENCE",
    "NO_CAMPAIGN_READY_STRATEGIES",
)
READINESS_STATE: Final[tuple[str, ...]] = (
    "READINESS_DIAGNOSIS_REQUIRED",
    "READINESS_GAPS_IDENTIFIED",
    "CAPABILITY_REMEDIATED",
    "READY_FOR_PREREGISTRATION",
    "PREREGISTRATION_BLOCKED",
    "TERMINAL",
)

BLOCKER_PRIORITY: Final[dict[str, int]] = {
    "UNIVERSE_IDENTITY_MISSING": 10,
    "UNIVERSE_MEMBERSHIP_HISTORY_MISSING": 20,
    "INSTRUMENT_IDENTITY_MISSING": 30,
    "SOURCE_IDENTITY_MISSING": 40,
    "DATASET_IDENTITY_MISSING": 50,
    "SNAPSHOT_IDENTITY_MISSING": 60,
    "TIMEFRAME_AMBIGUOUS": 70,
    "PRESET_INCOMPLETE": 80,
    "DATA_SCHEMA_INCOMPATIBLE": 90,
    "DATA_COVERAGE_INSUFFICIENT": 100,
    "TRAIN_WINDOW_MISSING": 110,
    "VALIDATION_WINDOW_MISSING": 120,
    "OOS_WINDOW_MISSING": 130,
    "OOS_INDEPENDENCE_NOT_PROVEN": 140,
    "CONSUMED_OOS_REUSE_RISK": 150,
    "NULL_CONTROL_IMPLEMENTATION_MISSING": 160,
    "NULL_CONTROL_DATA_BLOCKED": 170,
    "COST_MODEL_MISSING": 180,
    "SLIPPAGE_MODEL_MISSING": 190,
    "REGIME_IDENTITY_MISSING": 200,
    "CAMPAIGN_METADATA_INCOMPLETE": 210,
    "CAMPAIGN_LINEAGE_INCOMPLETE": 220,
    "REPRODUCIBILITY_INCOMPLETE": 230,
    "EVIDENCE_AUTHORITY_AMBIGUOUS": 240,
    "COMPUTE_BUDGET_MISSING": 250,
    "TIMEOUT_POLICY_MISSING": 260,
    "FEATURE_PRIMITIVE_MISSING": 270,
    "STRATEGY_SPEC_INCOMPLETE": 280,
    "STRATEGY_VALIDATION_FAILED": 290,
    "SCIENTIFIC_TESTABILITY_FAILED": 300,
    "DUPLICATE_OR_REJECTED_LINEAGE": 310,
    "SIGNAL_DENSITY_INSUFFICIENT": 320,
    "NO_SAFE_AUTOMATED_REMEDIATION": 330,
}

GENERATED_READINESS_ROOT: Final[Path] = REPO_ROOT / "generated_research" / "readiness"
BLOCKERS_PATH: Final[Path] = GENERATED_READINESS_ROOT / "reports" / "autonomous_readiness_blockers.v1.json"
ITERATION_LEDGER_PATH: Final[Path] = GENERATED_READINESS_ROOT / "reports" / "autonomous_readiness_iteration_ledger.v1.json"
UNIVERSE_AUTHORITY_PATH: Final[Path] = GENERATED_READINESS_ROOT / "identity_decisions" / "autonomous_universe_authority.v1.json"
TIMEFRAME_RESOLUTION_PATH: Final[Path] = GENERATED_READINESS_ROOT / "reports" / "autonomous_timeframe_resolution.v1.json"
PRESET_COMPLETION_PATH: Final[Path] = GENERATED_READINESS_ROOT / "presets" / "autonomous_completed_presets.v1.json"
DATA_BINDING_PATH: Final[Path] = GENERATED_READINESS_ROOT / "data_bindings" / "autonomous_strategy_data_bindings.v1.json"
WINDOW_CAPACITY_PATH: Final[Path] = GENERATED_READINESS_ROOT / "window_capacity" / "autonomous_window_capacity.v1.json"
NULL_CONTROL_PATH: Final[Path] = GENERATED_READINESS_ROOT / "null_controls" / "autonomous_null_control_readiness.v1.json"
CAMPAIGN_METADATA_PATH: Final[Path] = GENERATED_READINESS_ROOT / "campaigns" / "autonomous_campaign_metadata.v1.json"
CAMPAIGN_LINEAGE_PATH: Final[Path] = GENERATED_READINESS_ROOT / "campaigns" / "autonomous_campaign_lineage.v1.json"
PORTFOLIO_PATH: Final[Path] = GENERATED_READINESS_ROOT / "campaigns" / "autonomous_portfolio_readiness.v1.json"
MANIFEST_PATH: Final[Path] = GENERATED_READINESS_ROOT / "campaigns" / "autonomous_second_campaign_manifest.v1.json"
CLOSEOUT_JSON_PATH: Final[Path] = GENERATED_READINESS_ROOT / "reports" / "autonomous_readiness_closeout.v1.json"
CLOSEOUT_MD_PATH: Final[Path] = GENERATED_READINESS_ROOT / "reports" / "autonomous_readiness_closeout.v1.md"


def _stable_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def stable_digest(value: Any) -> str:
    return hashlib.sha256(_stable_json(value).encode("utf-8")).hexdigest()


def _content_id(prefix: str, value: Any) -> str:
    return f"{prefix}_{stable_digest(value)[:16]}"


def _atomic_write(path: Path, payload: str) -> None:
    validate_write_target(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=".ade_qre_023.", suffix=".tmp", dir=str(path.parent))
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


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    _atomic_write(path, json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=True) + "\n")


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


def _iso_to_dt(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)


def _dt_to_iso(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _load_strategy_specs(repo_root: Path) -> dict[str, dict[str, Any]]:
    specs: dict[str, dict[str, Any]] = {}
    specs_dir = repo_root / "generated_research" / "specs"
    for path in sorted(specs_dir.glob("qsp_*.json")):
        payload = _read_json(path)
        if not payload:
            continue
        strategy_spec_id = str(payload.get("strategy_spec_id") or "")
        if strategy_spec_id:
            specs[strategy_spec_id] = payload
    return specs


def _load_registry(repo_root: Path) -> list[dict[str, Any]]:
    return _read_rows(repo_root / "generated_research" / "registry" / "generated_strategy_registry.v1.json")


def _load_readiness_gap_rows(repo_root: Path) -> dict[str, dict[str, Any]]:
    rows = _read_rows(repo_root / "generated_research" / "readiness" / "gaps" / "strategy_readiness_gaps.v1.json")
    return {str(row.get("generated_strategy_id") or ""): row for row in rows}


def _load_instrument_rows(repo_root: Path) -> list[dict[str, Any]]:
    payload = _read_json(repo_root / "artifacts" / "identity" / "instrument_identity_latest.v1.json") or {}
    rows = payload.get("rows")
    if not isinstance(rows, list):
        return []
    return [dict(row) for row in rows if isinstance(row, dict)]


def _load_universe_catalog(repo_root: Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    payload = _read_json(repo_root / "artifacts" / "universe" / "equity_universe_catalog_latest.v1.json") or {}
    instrument_rows = payload.get("instruments")
    universe_rows = payload.get("universes")
    return (
        [dict(row) for row in instrument_rows if isinstance(row, dict)] if isinstance(instrument_rows, list) else [],
        [dict(row) for row in universe_rows if isinstance(row, dict)] if isinstance(universe_rows, list) else [],
    )


def _load_coverage_rows(repo_root: Path) -> list[dict[str, Any]]:
    payload = _read_json(repo_root / "logs" / "qre_data_cache_manifest" / "latest.json") or {}
    rows = payload.get("coverage")
    if not isinstance(rows, list):
        return []
    return [dict(row) for row in rows if isinstance(row, dict)]


def _load_null_control_rows(repo_root: Path) -> dict[str, dict[str, Any]]:
    rows = _read_rows(repo_root / "generated_research" / "lineage" / "generated_null_controls.v1.json")
    return {str(row.get("generated_strategy_id") or ""): row for row in rows}


def _load_baseline_inputs(repo_root: Path) -> dict[str, Any]:
    acr.run_readiness_remediation(repo_root=repo_root)
    registry_rows = _load_registry(repo_root)
    specs_by_id = _load_strategy_specs(repo_root)
    gaps_by_strategy = _load_readiness_gap_rows(repo_root)
    instrument_rows = _load_instrument_rows(repo_root)
    universe_instruments, universe_rows = _load_universe_catalog(repo_root)
    coverage_rows = _load_coverage_rows(repo_root)
    null_rows = _load_null_control_rows(repo_root)
    return {
        "registry_rows": registry_rows,
        "registry_by_strategy": {
            str(row.get("generated_strategy_id") or ""): row for row in registry_rows if str(row.get("generated_strategy_id") or "")
        },
        "specs_by_id": specs_by_id,
        "gaps_by_strategy": gaps_by_strategy,
        "instrument_rows": instrument_rows,
        "universe_instruments": universe_instruments,
        "universe_rows": universe_rows,
        "coverage_rows": coverage_rows,
        "null_rows": null_rows,
    }


def _build_base_cell(
    *,
    registry_row: dict[str, Any],
    spec: dict[str, Any],
    timeframe: str,
    split_required: bool,
) -> dict[str, Any]:
    generated_strategy_id = str(registry_row.get("generated_strategy_id") or "")
    cell_identity = {
        "generated_strategy_id": generated_strategy_id,
        "timeframe": timeframe,
        "split_required": split_required,
    }
    return {
        "campaign_cell_id": _content_id("qrcell", cell_identity),
        "generated_strategy_id": generated_strategy_id,
        "generated_registration_id": str(registry_row.get("generated_registration_id") or ""),
        "source_hypothesis_id": str(registry_row.get("source_hypothesis_id") or ""),
        "strategy_spec_id": str(registry_row.get("strategy_spec_id") or ""),
        "thesis_id": str(registry_row.get("thesis_id") or ""),
        "requested_timeframe": timeframe,
        "resolved_timeframe": timeframe if timeframe else "",
        "timeframe_resolution_state": "TIMEFRAME_RESOLVED_UNIQUE" if not split_required else "TIMEFRAME_SPLIT_INTO_DISTINCT_CELLS",
        "split_required": split_required,
        "state": "READINESS_DIAGNOSIS_REQUIRED",
        "terminal_outcome": "",
        "terminal_reason": "",
        "universe_identity": "",
        "universe_state": "MISSING",
        "membership_snapshot_id": "",
        "instrument_identities": [],
        "source_identity": "",
        "dataset_identity": "",
        "snapshot_identity": "",
        "data_binding_state": "BLOCKED",
        "preset_id": "",
        "preset_state": "PRESET_BLOCKED",
        "train_window": {},
        "validation_window": {},
        "oos_window": {},
        "window_state": "WINDOW_CAPACITY_BLOCKED",
        "null_control_state": "NULL_CONTROLS_BLOCKED",
        "null_controls": [],
        "campaign_metadata_id": "",
        "campaign_metadata_state": "PREREGISTRATION_BLOCKED",
        "lineage_identity": "",
        "lineage_state": "CAMPAIGN_LINEAGE_MISSING",
        "portfolio_status": "INSUFFICIENT_EVIDENCE",
        "blockers": [],
        "provenance": sorted(set(list(spec.get("provenance") or []) + list(registry_row.get("provenance") or []))),
    }


def _candidate_timeframes(spec: dict[str, Any]) -> list[str]:
    raw = spec.get("timeframe") or []
    if isinstance(raw, list):
        return [str(value) for value in raw if str(value)]
    if isinstance(raw, str) and raw:
        return [part for part in raw.split("|") if part]
    return []


def _initial_cells(registry_row: dict[str, Any], spec: dict[str, Any]) -> list[dict[str, Any]]:
    timeframes = _candidate_timeframes(spec)
    if not timeframes:
        return [_build_base_cell(registry_row=registry_row, spec=spec, timeframe="", split_required=False)]
    if len(timeframes) == 1:
        return [_build_base_cell(registry_row=registry_row, spec=spec, timeframe=timeframes[0], split_required=False)]
    return [
        _build_base_cell(registry_row=registry_row, spec=spec, timeframe=timeframe, split_required=True)
        for timeframe in timeframes
    ]


def _coverage_matches(
    *,
    coverage_rows: list[dict[str, Any]],
    symbols: set[str],
    timeframe: str,
) -> list[dict[str, Any]]:
    return [
        row
        for row in coverage_rows
        if row.get("ready") is True
        and str(row.get("timeframe") or "") == timeframe
        and str(row.get("instrument") or "") in symbols
    ]


def _candidate_universes_for_cross_sectional(
    *,
    timeframe: str,
    minimum_universe_size: int,
    universe_instruments: list[dict[str, Any]],
    universe_rows: list[dict[str, Any]],
    coverage_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    universe_meta = {str(row.get("universe_id") or ""): row for row in universe_rows}
    by_universe: dict[str, list[dict[str, Any]]] = {}
    for row in universe_instruments:
        if str(row.get("identity_confidence") or "") != "high":
            continue
        for universe_id in row.get("universe_ids", []):
            if not isinstance(universe_id, str) or not universe_id:
                continue
            by_universe.setdefault(universe_id, []).append(row)
    candidates: list[dict[str, Any]] = []
    for universe_id, instrument_rows in sorted(by_universe.items()):
        matched_members: list[dict[str, Any]] = []
        excluded_members: list[dict[str, Any]] = []
        total_members = len(instrument_rows)
        for instrument_row in sorted(instrument_rows, key=lambda item: str(item.get("canonical_id") or "")):
            symbols = {
                str(instrument_row.get("symbol") or ""),
                str(instrument_row.get("provider_symbol") or ""),
            }
            coverage = _coverage_matches(coverage_rows=coverage_rows, symbols=symbols, timeframe=timeframe)
            if coverage:
                matched_members.append(
                    {
                        "canonical_instrument_id": str(instrument_row.get("canonical_id") or ""),
                        "symbol": str(instrument_row.get("symbol") or ""),
                        "provider_symbol": str(instrument_row.get("provider_symbol") or ""),
                        "coverage_hash": str(sorted(coverage, key=lambda row: str(row.get("content_hash") or ""))[0].get("content_hash") or ""),
                        "min_timestamp_utc": min(str(row.get("min_timestamp_utc") or "") for row in coverage),
                        "max_timestamp_utc": max(str(row.get("max_timestamp_utc") or "") for row in coverage),
                    }
                )
            else:
                excluded_members.append(
                    {
                        "canonical_instrument_id": str(instrument_row.get("canonical_id") or ""),
                        "reason": f"missing_{timeframe}_coverage",
                    }
                )
        if len(matched_members) < minimum_universe_size:
            continue
        meta = universe_meta.get(universe_id, {})
        region = str(meta.get("region") or "")
        specificity_score = 1 if region == "Global" else 0
        candidates.append(
            {
                "universe_id": universe_id,
                "kind": str(meta.get("kind") or ""),
                "region": region,
                "total_members": total_members,
                "matched_members": matched_members,
                "matched_member_count": len(matched_members),
                "excluded_members": excluded_members,
                "specificity_score": specificity_score,
            }
        )
    return sorted(
        candidates,
        key=lambda row: (
            row["total_members"],
            row["specificity_score"],
            -row["matched_member_count"],
            row["universe_id"],
        ),
    )


def _resolve_cross_sectional_universe(
    *,
    cell: dict[str, Any],
    spec: dict[str, Any],
    universe_instruments: list[dict[str, Any]],
    universe_rows: list[dict[str, Any]],
    coverage_rows: list[dict[str, Any]],
) -> tuple[dict[str, Any], dict[str, Any]]:
    minimum_universe_size = int(dict(spec.get("parameters") or {}).get("minimum_universe_size") or 0)
    candidates = _candidate_universes_for_cross_sectional(
        timeframe=str(cell.get("resolved_timeframe") or ""),
        minimum_universe_size=minimum_universe_size,
        universe_instruments=universe_instruments,
        universe_rows=universe_rows,
        coverage_rows=coverage_rows,
    )
    requested_alias = "breadth_resolved_multi_asset_basket"
    if not candidates:
        return (
            {
                "state": "BLOCKED",
                "reason": "no_authoritative_universe_with_minimum_breadth_and_local_coverage",
                "requested_alias": requested_alias,
                "candidates": [],
            },
            {},
        )
    selected = candidates[0]
    effective_from = max(_iso_to_dt(member["min_timestamp_utc"]) for member in selected["matched_members"])
    effective_to = min(_iso_to_dt(member["max_timestamp_utc"]) for member in selected["matched_members"])
    snapshot_core = {
        "universe_id": selected["universe_id"],
        "timeframe": str(cell.get("resolved_timeframe") or ""),
        "effective_from": _dt_to_iso(effective_from),
        "effective_to": _dt_to_iso(effective_to),
        "member_ids": [member["canonical_instrument_id"] for member in selected["matched_members"]],
        "coverage_hashes": [member["coverage_hash"] for member in selected["matched_members"]],
        "resolver_version": UNIVERSE_RESOLVER_VERSION,
    }
    snapshot_id = _content_id("qum", snapshot_core)
    row = {
        "requested_alias": requested_alias,
        "resolution_outcome": "RESOLVED_UNIQUE_AUTHORITATIVE",
        "selected_universe_id": selected["universe_id"],
        "universe_kind": selected["kind"],
        "universe_region": selected["region"],
        "membership_snapshot_id": snapshot_id,
        "effective_from_utc": _dt_to_iso(effective_from),
        "effective_to_utc": _dt_to_iso(effective_to),
        "matched_member_count": selected["matched_member_count"],
        "minimum_universe_size": minimum_universe_size,
        "included_members": [
            {
                "canonical_instrument_id": member["canonical_instrument_id"],
                "symbol": member["symbol"],
                "provider_symbol": member["provider_symbol"],
                "inclusion_reason": "high_confidence_identity_and_matching_local_timeframe_coverage",
                "coverage_hash": member["coverage_hash"],
            }
            for member in selected["matched_members"]
        ],
        "excluded_members": list(selected["excluded_members"]),
        "selection_reason": (
            "smallest authoritative universe with sufficient local breadth and non-global tie-break precedence"
        ),
        "provenance": [
            "artifacts/universe/equity_universe_catalog_latest.v1.json",
            "artifacts/identity/instrument_identity_latest.v1.json",
            "logs/qre_data_cache_manifest/latest.json",
        ],
    }
    return (
        {
            "state": "RESOLVED",
            "reason": "authoritative_universe_membership_snapshot_materialized",
            "universe_id": selected["universe_id"],
            "membership_snapshot_id": snapshot_id,
            "instrument_identities": [member["canonical_instrument_id"] for member in selected["matched_members"]],
            "effective_from_utc": _dt_to_iso(effective_from),
            "effective_to_utc": _dt_to_iso(effective_to),
            "included_members": list(row["included_members"]),
            "excluded_members": list(row["excluded_members"]),
        },
        row,
    )


def _resolve_single_instrument_identity(
    *,
    instrument_rows: list[dict[str, Any]],
    symbol_hint: str,
) -> dict[str, Any]:
    matches = [
        row
        for row in instrument_rows
        if str(row.get("identity_status") or "") == "OK"
        and (
            str(row.get("symbol") or "") == symbol_hint
            or str(row.get("provider_symbol") or "") == symbol_hint
            or str(row.get("canonical_id") or "").endswith(f":{symbol_hint}")
        )
    ]
    if len(matches) != 1:
        return {
            "state": "BLOCKED",
            "reason": "single_instrument_identity_not_unique",
            "instrument_identities": [],
        }
    row = matches[0]
    return {
        "state": "RESOLVED",
        "reason": "unique_high_confidence_single_instrument_identity",
        "instrument_identities": [str(row.get("canonical_id") or "")],
        "selected_instrument_row": row,
    }


def _build_cross_sectional_data_binding(
    *,
    cell: dict[str, Any],
    coverage_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    included = list(cell.get("included_members") or [])
    timeframe = str(cell.get("resolved_timeframe") or "")
    member_rows: list[dict[str, Any]] = []
    for member in included:
        symbols = {str(member.get("symbol") or ""), str(member.get("provider_symbol") or "")}
        matches = _coverage_matches(coverage_rows=coverage_rows, symbols=symbols, timeframe=timeframe)
        if not matches:
            return {
                "state": "BLOCKED",
                "reason": "missing_member_coverage_after_universe_resolution",
            }
        member_rows.append(sorted(matches, key=lambda row: str(row.get("content_hash") or ""))[0])
    sources = {str(row.get("source") or "") for row in member_rows}
    if len(sources) != 1:
        return {
            "state": "BLOCKED",
            "reason": "multiple_sources_for_cross_sectional_binding",
        }
    common_start = max(_iso_to_dt(str(row.get("min_timestamp_utc") or "")) for row in member_rows)
    common_end = min(_iso_to_dt(str(row.get("max_timestamp_utc") or "")) for row in member_rows)
    binding_core = {
        "strategy": str(cell.get("generated_strategy_id") or ""),
        "timeframe": timeframe,
        "member_hashes": [str(row.get("content_hash") or "") for row in member_rows],
        "common_start": _dt_to_iso(common_start),
        "common_end": _dt_to_iso(common_end),
        "source": sorted(sources)[0],
        "version": DATA_BINDING_VERSION,
    }
    return {
        "state": "RESOLVED",
        "reason": "single_source_cross_sectional_panel_binding_available",
        "source_identity": sorted(sources)[0],
        "dataset_identity": _content_id("qds", binding_core),
        "snapshot_identity": _content_id("qsn", binding_core),
        "common_start_utc": _dt_to_iso(common_start),
        "common_end_utc": _dt_to_iso(common_end),
        "member_count": len(member_rows),
        "member_content_hashes": [str(row.get("content_hash") or "") for row in member_rows],
    }


def _build_single_instrument_data_binding(
    *,
    cell: dict[str, Any],
    coverage_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    instrument_row = dict(cell.get("selected_instrument_row") or {})
    symbols = {str(instrument_row.get("symbol") or ""), str(instrument_row.get("provider_symbol") or "")}
    timeframe = str(cell.get("resolved_timeframe") or "")
    matches = _coverage_matches(coverage_rows=coverage_rows, symbols=symbols, timeframe=timeframe)
    if not matches:
        return {
            "state": "BLOCKED",
            "reason": "no_cache_row_for_resolved_instrument_and_timeframe",
        }
    row = sorted(matches, key=lambda item: str(item.get("content_hash") or ""))[0]
    binding_core = {
        "strategy": str(cell.get("generated_strategy_id") or ""),
        "timeframe": timeframe,
        "source": str(row.get("source") or ""),
        "instrument": str(row.get("instrument") or ""),
        "content_hash": str(row.get("content_hash") or ""),
        "version": DATA_BINDING_VERSION,
    }
    return {
        "state": "RESOLVED_WITH_LIMITATIONS",
        "reason": "single_cache_binding_available",
        "source_identity": str(row.get("source") or ""),
        "dataset_identity": _content_id("qds", binding_core),
        "snapshot_identity": _content_id("qsn", binding_core),
        "common_start_utc": str(row.get("min_timestamp_utc") or ""),
        "common_end_utc": str(row.get("max_timestamp_utc") or ""),
        "coverage_hash": str(row.get("content_hash") or ""),
    }


def _window_capacity_from_binding(
    *,
    cell: dict[str, Any],
    spec: dict[str, Any],
) -> dict[str, Any]:
    if str(cell.get("data_binding_state") or "") not in {"RESOLVED", "RESOLVED_WITH_LIMITATIONS"}:
        return {
            "state": "BLOCKED",
            "terminal_outcome": "DATA_CAPACITY_BLOCKED",
            "reason": "data_binding_not_ready",
        }
    start_raw = str(cell.get("common_start_utc") or "")
    end_raw = str(cell.get("common_end_utc") or "")
    if not start_raw or not end_raw:
        return {
            "state": "BLOCKED",
            "terminal_outcome": "DATA_CAPACITY_BLOCKED",
            "reason": "binding_missing_common_coverage_range",
        }
    start = _iso_to_dt(start_raw)
    end = _iso_to_dt(end_raw)
    warmup_bars = max(
        [int(value) for value in dict(spec.get("warmup_requirements") or {}).values() if isinstance(value, int)] or [0]
    )
    total_days = (end - start).days
    # A23 intentionally refuses to assign train/validation/OOS windows without an
    # explicit authoritative segmentation policy. It still materializes exact local
    # coverage capacity so the blocker becomes more specific.
    return {
        "state": "BLOCKED",
        "terminal_outcome": "INDEPENDENT_OOS_CAPACITY_BLOCKED",
        "reason": "authoritative_window_assignment_policy_not_materialized",
        "earliest_usable_timestamp_utc": start_raw,
        "latest_usable_timestamp_utc": end_raw,
        "warmup_requirement_bars": warmup_bars,
        "coverage_span_days": total_days,
        "window_policy_version": WINDOW_POLICY_VERSION,
        "consumed_oos_windows": [],
    }


def _materialize_preset(
    *,
    cell: dict[str, Any],
    spec: dict[str, Any],
) -> dict[str, Any]:
    if str(cell.get("data_binding_state") or "") not in {"RESOLVED", "RESOLVED_WITH_LIMITATIONS"}:
        return {
            "preset_state": "PRESET_BLOCKED_DATA",
            "reason": "data_binding_not_ready",
        }
    if str(cell.get("universe_state") or "") not in {"RESOLVED", "RESOLVED_WITH_LIMITATIONS"}:
        return {
            "preset_state": "PRESET_BLOCKED_IDENTITY",
            "reason": "universe_not_resolved",
        }
    preset_core = {
        "strategy": str(cell.get("generated_strategy_id") or ""),
        "timeframe": str(cell.get("resolved_timeframe") or ""),
        "universe": str(cell.get("universe_identity") or ""),
        "dataset": str(cell.get("dataset_identity") or ""),
        "snapshot": str(cell.get("snapshot_identity") or ""),
        "parameters": dict(spec.get("parameters") or {}),
        "version": PRESET_COMPLETION_VERSION,
    }
    return {
        "preset_state": "PRESET_READY_WITH_LIMITATIONS",
        "preset_id": _content_id("qgp", preset_core),
        "reason": "bounded_preset_materialized_from_resolved_identity_and_binding",
        "parameter_values": dict(spec.get("parameters") or {}),
    }


def _null_control_readiness(
    *,
    cell: dict[str, Any],
    null_row: dict[str, Any] | None,
) -> dict[str, Any]:
    if not null_row:
        return {
            "state": "NULL_CONTROLS_BLOCKED",
            "reason": "null_control_spec_missing",
            "outcomes": [],
        }
    outcomes: list[dict[str, Any]] = []
    data_ready = str(cell.get("data_binding_state") or "") in {"RESOLVED", "RESOLVED_WITH_LIMITATIONS"}
    windows_ready = str(cell.get("window_state") or "") == "WINDOW_CAPACITY_READY"
    implementation_ready = bool(null_row.get("implementation_readiness"))
    for control_class in [str(value) for value in null_row.get("required_controls", []) if str(value)]:
        if not implementation_ready:
            outcome = "IMPLEMENTATION_MISSING"
            blocker = "null_control_implementation_missing"
        elif not data_ready:
            outcome = "DATA_BLOCKED"
            blocker = "data_binding_not_ready"
        elif not windows_ready:
            outcome = "WINDOW_BLOCKED"
            blocker = "authoritative_window_assignment_policy_not_materialized"
        else:
            outcome = "NULL_CONTROL_EXECUTION_READY"
            blocker = ""
        outcomes.append(
            {
                "control_identity": _content_id(
                    "qnr",
                    {
                        "strategy": str(cell.get("generated_strategy_id") or ""),
                        "timeframe": str(cell.get("resolved_timeframe") or ""),
                        "control": control_class,
                        "seed": str(null_row.get("deterministic_seed") or ""),
                    },
                ),
                "control_class": control_class,
                "deterministic_seed": str(null_row.get("deterministic_seed") or ""),
                "outcome": outcome,
                "blocker": blocker,
                "required_inputs": [
                    "resolved_dataset",
                    "resolved_windows",
                    "resolved_strategy_registration",
                ],
            }
        )
    state = "NULL_CONTROLS_EXECUTION_READY" if all(row["outcome"] == "NULL_CONTROL_EXECUTION_READY" for row in outcomes) else "NULL_CONTROLS_BLOCKED"
    return {
        "state": state,
        "reason": "" if state == "NULL_CONTROLS_EXECUTION_READY" else "null_controls_not_execution_ready",
        "outcomes": outcomes,
    }


def _campaign_metadata(
    *,
    cell: dict[str, Any],
    spec: dict[str, Any],
) -> dict[str, Any]:
    blockers = list(cell.get("blockers") or [])
    metadata_core = {
        "strategy": str(cell.get("generated_strategy_id") or ""),
        "timeframe": str(cell.get("resolved_timeframe") or ""),
        "preset": str(cell.get("preset_id") or ""),
        "universe": str(cell.get("universe_identity") or ""),
        "dataset": str(cell.get("dataset_identity") or ""),
        "snapshot": str(cell.get("snapshot_identity") or ""),
        "version": MODULE_VERSION,
    }
    return {
        "campaign_metadata_id": _content_id("qcmd", metadata_core),
        "campaign_metadata_state": "CAMPAIGN_METADATA_READY" if not blockers else "PREREGISTRATION_BLOCKED",
        "costs": dict(spec.get("cost_assumptions") or {}),
        "slippage": dict(spec.get("slippage_assumptions") or {}),
        "null_controls": [row["control_class"] for row in list(cell.get("null_control_outcomes") or [])],
    }


def _lineage(cell: dict[str, Any]) -> dict[str, Any]:
    lineage_core = {
        "generated_strategy_id": str(cell.get("generated_strategy_id") or ""),
        "timeframe": str(cell.get("resolved_timeframe") or ""),
        "preset_id": str(cell.get("preset_id") or ""),
        "universe_identity": str(cell.get("universe_identity") or ""),
        "dataset_identity": str(cell.get("dataset_identity") or ""),
    }
    blockers = list(cell.get("blockers") or [])
    return {
        "lineage_identity": _content_id("qcl", lineage_core),
        "lineage_state": "CAMPAIGN_LINEAGE_COMPLETE" if not blockers else "CAMPAIGN_LINEAGE_COMPLETE_WITH_LIMITATIONS",
    }


def _current_blockers(cell: dict[str, Any], spec: dict[str, Any]) -> list[dict[str, Any]]:
    blockers: list[dict[str, Any]] = []
    if str(cell.get("source_hypothesis_id") or "") == "cross_sectional_momentum_v0":
        if str(cell.get("universe_state") or "") not in {"RESOLVED", "RESOLVED_WITH_LIMITATIONS"}:
            blockers.append(
                {
                    "blocker_class": "UNIVERSE_IDENTITY_MISSING",
                    "reason": str(cell.get("universe_reason") or "non_authoritative_universe_alias_only"),
                    "expected_output": "canonical_universe_and_point_in_time_membership_snapshot",
                }
            )
            return blockers
    else:
        if str(cell.get("timeframe_resolution_state") or "") == "TIMEFRAME_AMBIGUOUS":
            blockers.append(
                {
                    "blocker_class": "TIMEFRAME_AMBIGUOUS",
                    "reason": "multiple_spec_timeframes",
                    "expected_output": "timeframe_selection_or_distinct_campaign_cells",
                }
            )
            return blockers
    if str(cell.get("data_binding_state") or "") not in {"RESOLVED", "RESOLVED_WITH_LIMITATIONS"}:
        reason = str(cell.get("data_binding_reason") or "")
        blocker_class = {
            "no_cache_row_for_resolved_instrument_and_timeframe": "DATA_COVERAGE_INSUFFICIENT",
            "missing_member_coverage_after_universe_resolution": "DATA_COVERAGE_INSUFFICIENT",
            "multiple_sources_for_cross_sectional_binding": "EVIDENCE_AUTHORITY_AMBIGUOUS",
            "data_binding_not_ready": "DATASET_IDENTITY_MISSING",
        }.get(reason, "DATASET_IDENTITY_MISSING")
        blockers.append(
            {
                "blocker_class": blocker_class,
                "reason": reason or "data_binding_not_ready",
                "expected_output": "authoritative_source_dataset_snapshot_binding",
            }
        )
        return blockers
    if str(cell.get("preset_state") or "") not in {"PRESET_READY", "PRESET_READY_WITH_LIMITATIONS"}:
        blockers.append(
            {
                "blocker_class": "PRESET_INCOMPLETE",
                "reason": str(cell.get("preset_reason") or "preset_not_materialized"),
                "expected_output": "bounded_preset_with_resolved_identity_and_binding",
            }
        )
    if str(cell.get("window_state") or "") != "WINDOW_CAPACITY_READY":
        window_reason = str(cell.get("window_reason") or "")
        blocker_class = "OOS_INDEPENDENCE_NOT_PROVEN" if "policy_not_materialized" in window_reason else "OOS_WINDOW_MISSING"
        blockers.append(
            {
                "blocker_class": blocker_class,
                "reason": window_reason or "window_capacity_not_ready",
                "expected_output": "explicit_train_validation_oos_capacity",
            }
        )
        return blockers
    if str(cell.get("null_control_state") or "") != "NULL_CONTROLS_EXECUTION_READY":
        blockers.append(
            {
                "blocker_class": "NULL_CONTROL_DATA_BLOCKED",
                "reason": str(cell.get("null_control_reason") or "null_controls_not_execution_ready"),
                "expected_output": "null_control_execution_readiness",
            }
        )
    return sorted(
        blockers,
        key=lambda row: (
            BLOCKER_PRIORITY.get(str(row["blocker_class"]), 9999),
            str(row["reason"]),
        ),
    )


def _remediation_decision(blocker_class: str) -> str:
    mapping = {
        "UNIVERSE_IDENTITY_MISSING": "AUTO_REMEDIATE",
        "TIMEFRAME_AMBIGUOUS": "AUTO_REMEDIATE",
        "DATASET_IDENTITY_MISSING": "AUTO_REMEDIATE",
        "DATA_COVERAGE_INSUFFICIENT": "FAIL_CLOSED",
        "EVIDENCE_AUTHORITY_AMBIGUOUS": "FAIL_CLOSED",
        "PRESET_INCOMPLETE": "AUTO_REMEDIATE",
        "OOS_WINDOW_MISSING": "FAIL_CLOSED",
        "OOS_INDEPENDENCE_NOT_PROVEN": "FAIL_CLOSED",
        "NULL_CONTROL_DATA_BLOCKED": "REPLAY_EXISTING_PIPELINE",
    }
    decision = mapping.get(blocker_class, "FAIL_CLOSED")
    if decision not in REMEDIATION_DECISION:
        raise ValueError(f"unknown remediation decision: {decision}")
    return decision


def _apply_strategy_specific_identity_resolution(
    *,
    cell: dict[str, Any],
    spec: dict[str, Any],
    inputs: dict[str, Any],
) -> dict[str, Any]:
    source_hypothesis_id = str(cell.get("source_hypothesis_id") or "")
    if source_hypothesis_id == "cross_sectional_momentum_v0":
        resolved, universe_row = _resolve_cross_sectional_universe(
            cell=cell,
            spec=spec,
            universe_instruments=inputs["universe_instruments"],
            universe_rows=inputs["universe_rows"],
            coverage_rows=inputs["coverage_rows"],
        )
        cell["universe_state"] = str(resolved.get("state") or "BLOCKED")
        cell["universe_reason"] = str(resolved.get("reason") or "")
        cell["universe_identity"] = str(resolved.get("universe_id") or "")
        cell["membership_snapshot_id"] = str(resolved.get("membership_snapshot_id") or "")
        cell["instrument_identities"] = list(resolved.get("instrument_identities") or [])
        cell["included_members"] = list(resolved.get("included_members") or [])
        cell["excluded_members"] = list(resolved.get("excluded_members") or [])
        cell["common_start_utc"] = str(resolved.get("effective_from_utc") or "")
        cell["common_end_utc"] = str(resolved.get("effective_to_utc") or "")
        return universe_row
    symbol_hint = "ASML"
    resolved = _resolve_single_instrument_identity(
        instrument_rows=inputs["instrument_rows"],
        symbol_hint=symbol_hint,
    )
    cell["universe_state"] = "RESOLVED_WITH_LIMITATIONS"
    cell["universe_reason"] = "single_instrument_universe_bound_from_instrument"
    cell["universe_identity"] = acr._single_instrument_universe_id(str(resolved.get("instrument_identities", [""])[0] if resolved.get("instrument_identities") else ""))
    cell["membership_snapshot_id"] = _content_id(
        "qum",
        {
            "generated_strategy_id": str(cell.get("generated_strategy_id") or ""),
            "instrument": list(resolved.get("instrument_identities") or []),
            "timeframe": str(cell.get("resolved_timeframe") or ""),
        },
    )
    cell["instrument_identities"] = list(resolved.get("instrument_identities") or [])
    cell["selected_instrument_row"] = dict(resolved.get("selected_instrument_row") or {})
    return {
        "requested_alias": "single_resolved_instrument_only",
        "resolution_outcome": "RESOLVED_WITH_LIMITATIONS",
        "selected_universe_id": str(cell.get("universe_identity") or ""),
        "membership_snapshot_id": str(cell.get("membership_snapshot_id") or ""),
        "included_members": [
            {
                "canonical_instrument_id": instrument_id,
                "inclusion_reason": "unique_high_confidence_single_instrument_identity",
            }
            for instrument_id in cell["instrument_identities"]
        ],
        "excluded_members": [],
        "selection_reason": "single-instrument strategy bound to deterministic one-member universe",
        "provenance": [
            "artifacts/identity/instrument_identity_latest.v1.json",
            "artifacts/universe/equity_universe_catalog_latest.v1.json",
        ],
    }


def _apply_data_binding(*, cell: dict[str, Any], spec: dict[str, Any], inputs: dict[str, Any]) -> None:
    if str(cell.get("source_hypothesis_id") or "") == "cross_sectional_momentum_v0":
        binding = _build_cross_sectional_data_binding(cell=cell, coverage_rows=inputs["coverage_rows"])
    else:
        binding = _build_single_instrument_data_binding(cell=cell, coverage_rows=inputs["coverage_rows"])
    cell["data_binding_state"] = str(binding.get("state") or "BLOCKED")
    cell["data_binding_reason"] = str(binding.get("reason") or "")
    cell["source_identity"] = str(binding.get("source_identity") or "")
    cell["dataset_identity"] = str(binding.get("dataset_identity") or "")
    cell["snapshot_identity"] = str(binding.get("snapshot_identity") or "")
    if binding.get("common_start_utc"):
        cell["common_start_utc"] = str(binding.get("common_start_utc") or "")
    if binding.get("common_end_utc"):
        cell["common_end_utc"] = str(binding.get("common_end_utc") or "")


def _apply_window_capacity(*, cell: dict[str, Any], spec: dict[str, Any]) -> None:
    capacity = _window_capacity_from_binding(cell=cell, spec=spec)
    cell["window_state"] = "WINDOW_CAPACITY_READY" if capacity.get("state") == "READY" else "WINDOW_CAPACITY_BLOCKED"
    cell["window_reason"] = str(capacity.get("reason") or "")
    cell["window_terminal_outcome"] = str(capacity.get("terminal_outcome") or "")
    cell["window_capacity"] = capacity


def _apply_preset_completion(*, cell: dict[str, Any], spec: dict[str, Any]) -> None:
    preset = _materialize_preset(cell=cell, spec=spec)
    cell["preset_state"] = str(preset.get("preset_state") or "PRESET_BLOCKED")
    cell["preset_reason"] = str(preset.get("reason") or "")
    cell["preset_id"] = str(preset.get("preset_id") or "")
    cell["parameter_values"] = dict(preset.get("parameter_values") or {})


def _apply_null_controls(*, cell: dict[str, Any], null_row: dict[str, Any] | None) -> None:
    readiness = _null_control_readiness(cell=cell, null_row=null_row)
    cell["null_control_state"] = str(readiness.get("state") or "NULL_CONTROLS_BLOCKED")
    cell["null_control_reason"] = str(readiness.get("reason") or "")
    cell["null_control_outcomes"] = list(readiness.get("outcomes") or [])
    cell["null_controls"] = [row["control_class"] for row in cell["null_control_outcomes"]]


def _apply_campaign_views(*, cell: dict[str, Any], spec: dict[str, Any]) -> None:
    blockers = _current_blockers(cell, spec)
    cell["blockers"] = blockers
    metadata = _campaign_metadata(cell=cell, spec=spec)
    cell["campaign_metadata_id"] = str(metadata.get("campaign_metadata_id") or "")
    cell["campaign_metadata_state"] = str(metadata.get("campaign_metadata_state") or "")
    cell["costs"] = dict(metadata.get("costs") or {})
    cell["slippage"] = dict(metadata.get("slippage") or {})
    lineage = _lineage(cell)
    cell["lineage_identity"] = str(lineage.get("lineage_identity") or "")
    cell["lineage_state"] = str(lineage.get("lineage_state") or "")
    if not blockers:
        cell["portfolio_status"] = "READY_FOR_PREREGISTRATION"
        cell["state"] = "READY_FOR_PREREGISTRATION"
        cell["terminal_outcome"] = "READY_FOR_PREREGISTRATION"
        cell["terminal_reason"] = ""
    else:
        primary = blockers[0]["blocker_class"]
        if primary in {"UNIVERSE_IDENTITY_MISSING", "INSTRUMENT_IDENTITY_MISSING"}:
            cell["portfolio_status"] = "BLOCKED_IDENTITY"
        elif primary in {"DATASET_IDENTITY_MISSING", "DATA_COVERAGE_INSUFFICIENT", "SOURCE_IDENTITY_MISSING", "SNAPSHOT_IDENTITY_MISSING"}:
            cell["portfolio_status"] = "BLOCKED_DATA"
        elif primary in {"TIMEFRAME_AMBIGUOUS", "TRAIN_WINDOW_MISSING", "VALIDATION_WINDOW_MISSING", "OOS_WINDOW_MISSING", "OOS_INDEPENDENCE_NOT_PROVEN"}:
            cell["portfolio_status"] = "BLOCKED_WINDOWS"
        elif primary in {"NULL_CONTROL_IMPLEMENTATION_MISSING", "NULL_CONTROL_DATA_BLOCKED"}:
            cell["portfolio_status"] = "BLOCKED_NULL_CONTROLS"
        else:
            cell["portfolio_status"] = "INSUFFICIENT_EVIDENCE"
        cell["state"] = "PREREGISTRATION_BLOCKED"


def _serialize_blocker(
    *,
    cell: dict[str, Any],
    blocker: dict[str, Any],
) -> dict[str, Any]:
    blocker_class = str(blocker["blocker_class"])
    blocker_core = {
        "generated_strategy_id": str(cell.get("generated_strategy_id") or ""),
        "campaign_cell_id": str(cell.get("campaign_cell_id") or ""),
        "blocker_class": blocker_class,
        "reason": str(blocker.get("reason") or ""),
    }
    return {
        "blocker_id": _content_id("qrb", blocker_core),
        "blocker_class": blocker_class,
        "affected_strategy": str(cell.get("generated_strategy_id") or ""),
        "affected_thesis": str(cell.get("thesis_id") or ""),
        "affected_campaign_cell": str(cell.get("campaign_cell_id") or ""),
        "upstream_dependencies": [],
        "downstream_consequences": [str(cell.get("portfolio_status") or "")],
        "evidence_references": list(cell.get("provenance") or []),
        "authority_state": "authoritative_local" if blocker_class not in {"OOS_INDEPENDENCE_NOT_PROVEN"} else "insufficient_authoritative_policy",
        "remediability": blocker_class not in {"OOS_INDEPENDENCE_NOT_PROVEN", "DATA_COVERAGE_INSUFFICIENT"},
        "remediation_class": _remediation_decision(blocker_class),
        "expected_output": str(blocker.get("expected_output") or ""),
        "validation_requirements": [
            "deterministic_identity",
            "no_protected_research_writes",
            "no_trading_authority",
        ],
        "next_action": str(blocker.get("reason") or ""),
        "deterministic_identity": _content_id("qrbx", blocker_core),
        "reason": str(blocker.get("reason") or ""),
        "priority": BLOCKER_PRIORITY.get(blocker_class, 9999),
    }


def _select_blocker(cells: list[dict[str, Any]]) -> tuple[dict[str, Any], dict[str, Any]] | tuple[None, None]:
    ranked: list[tuple[dict[str, Any], dict[str, Any]]] = []
    for cell in cells:
        for blocker in list(cell.get("blockers") or []):
            ranked.append((cell, blocker))
    if not ranked:
        return None, None
    ranked.sort(
        key=lambda pair: (
            BLOCKER_PRIORITY.get(str(pair[1]["blocker_class"]), 9999),
            str(pair[0].get("campaign_cell_id") or ""),
            str(pair[1].get("reason") or ""),
        )
    )
    return ranked[0]


def _mark_terminal(cell: dict[str, Any], outcome: str, reason: str) -> None:
    if outcome not in TERMINAL_OUTCOME:
        raise ValueError(f"invalid terminal outcome: {outcome}")
    cell["terminal_outcome"] = outcome
    cell["terminal_reason"] = reason
    cell["state"] = "TERMINAL"


def _execute_remediation(
    *,
    cell: dict[str, Any],
    blocker: dict[str, Any],
    spec: dict[str, Any],
    inputs: dict[str, Any],
) -> dict[str, Any]:
    blocker_class = str(blocker["blocker_class"])
    decision = _remediation_decision(blocker_class)
    artifacts: list[str] = []
    progress = False
    if decision == "AUTO_REMEDIATE" and blocker_class == "UNIVERSE_IDENTITY_MISSING":
        row = _apply_strategy_specific_identity_resolution(cell=cell, spec=spec, inputs=inputs)
        artifacts.append("generated_research/readiness/identity_decisions/autonomous_universe_authority.v1.json")
        progress = str(cell.get("universe_state") or "") in {"RESOLVED", "RESOLVED_WITH_LIMITATIONS"}
        return {"decision": decision, "progress": progress, "artifacts": artifacts, "row": row}
    if decision == "AUTO_REMEDIATE" and blocker_class == "TIMEFRAME_AMBIGUOUS":
        # Timeframe ambiguity is resolved structurally by cell splitting before the loop starts.
        progress = True
        return {"decision": decision, "progress": progress, "artifacts": artifacts, "row": {}}
    if decision == "AUTO_REMEDIATE" and blocker_class in {"DATASET_IDENTITY_MISSING", "SOURCE_IDENTITY_MISSING", "SNAPSHOT_IDENTITY_MISSING"}:
        _apply_data_binding(cell=cell, spec=spec, inputs=inputs)
        artifacts.append("generated_research/readiness/data_bindings/autonomous_strategy_data_bindings.v1.json")
        progress = str(cell.get("data_binding_state") or "") in {"RESOLVED", "RESOLVED_WITH_LIMITATIONS"}
        return {"decision": decision, "progress": progress, "artifacts": artifacts, "row": {}}
    if decision == "AUTO_REMEDIATE" and blocker_class == "PRESET_INCOMPLETE":
        _apply_preset_completion(cell=cell, spec=spec)
        artifacts.append("generated_research/readiness/presets/autonomous_completed_presets.v1.json")
        progress = str(cell.get("preset_state") or "") in {"PRESET_READY", "PRESET_READY_WITH_LIMITATIONS"}
        return {"decision": decision, "progress": progress, "artifacts": artifacts, "row": {}}
    if decision == "REPLAY_EXISTING_PIPELINE" and blocker_class == "NULL_CONTROL_DATA_BLOCKED":
        _apply_null_controls(cell=cell, null_row=inputs["null_rows"].get(str(cell.get("generated_strategy_id") or "")))
        artifacts.append("generated_research/readiness/null_controls/autonomous_null_control_readiness.v1.json")
        progress = str(cell.get("null_control_state") or "") == "NULL_CONTROLS_EXECUTION_READY"
        return {"decision": decision, "progress": progress, "artifacts": artifacts, "row": {}}
    if decision == "FAIL_CLOSED" and blocker_class == "DATA_COVERAGE_INSUFFICIENT":
        _mark_terminal(cell, "DATA_CAPACITY_BLOCKED", str(blocker.get("reason") or "data_coverage_insufficient"))
        return {"decision": decision, "progress": True, "artifacts": artifacts, "row": {}}
    if decision == "FAIL_CLOSED" and blocker_class in {"OOS_WINDOW_MISSING", "OOS_INDEPENDENCE_NOT_PROVEN"}:
        _mark_terminal(cell, "INDEPENDENT_OOS_CAPACITY_BLOCKED", str(blocker.get("reason") or "oos_capacity_blocked"))
        return {"decision": decision, "progress": True, "artifacts": artifacts, "row": {}}
    if decision == "FAIL_CLOSED":
        _mark_terminal(cell, "NO_VALID_REMEDIATION_PATH", str(blocker.get("reason") or "no_safe_remediation_path"))
        return {"decision": decision, "progress": True, "artifacts": artifacts, "row": {}}
    return {"decision": decision, "progress": False, "artifacts": artifacts, "row": {}}


def _refresh_cell_state(*, cell: dict[str, Any], spec: dict[str, Any], inputs: dict[str, Any]) -> None:
    if str(cell.get("terminal_outcome") or ""):
        return
    if str(cell.get("source_hypothesis_id") or "") != "cross_sectional_momentum_v0":
        if not cell.get("selected_instrument_row"):
            _apply_strategy_specific_identity_resolution(cell=cell, spec=spec, inputs=inputs)
    _apply_data_binding(cell=cell, spec=spec, inputs=inputs)
    _apply_preset_completion(cell=cell, spec=spec)
    _apply_window_capacity(cell=cell, spec=spec)
    _apply_null_controls(cell=cell, null_row=inputs["null_rows"].get(str(cell.get("generated_strategy_id") or "")))
    _apply_campaign_views(cell=cell, spec=spec)


def _cell_sort_key(cell: dict[str, Any]) -> tuple[str, str]:
    return (str(cell.get("generated_strategy_id") or ""), str(cell.get("campaign_cell_id") or ""))


def _iteration_row(
    *,
    iteration_index: int,
    before_summary: dict[str, Any],
    selected_cell: dict[str, Any] | None,
    selected_blocker: dict[str, Any] | None,
    remediation: dict[str, Any] | None,
    after_summary: dict[str, Any],
    progress_status: str,
) -> dict[str, Any]:
    core = {
        "iteration_index": iteration_index,
        "selected_cell": str((selected_cell or {}).get("campaign_cell_id") or ""),
        "selected_blocker": str((selected_blocker or {}).get("blocker_class") or ""),
        "progress_status": progress_status,
        "before": before_summary,
        "after": after_summary,
    }
    return {
        "iteration_id": _content_id("qri", core),
        "iteration_index": iteration_index,
        "before_state": before_summary,
        "selected_blocker": _serialize_blocker(cell=selected_cell, blocker=selected_blocker) if selected_cell and selected_blocker else None,
        "remediation": remediation or {},
        "artifacts_created": list((remediation or {}).get("artifacts") or []),
        "tests": [],
        "after_state": after_summary,
        "blocker_delta": {
            "before": before_summary.get("blocker_counts", {}),
            "after": after_summary.get("blocker_counts", {}),
        },
        "progress_status": progress_status,
        "next_action": after_summary.get("next_action", ""),
    }


def _summary_from_cells(cells: list[dict[str, Any]]) -> dict[str, Any]:
    blocker_counts: Counter[str] = Counter()
    ready = 0
    terminal = Counter()
    for cell in cells:
        for blocker in list(cell.get("blockers") or []):
            blocker_counts[str(blocker["blocker_class"])] += 1
        if str(cell.get("portfolio_status") or "") == "READY_FOR_PREREGISTRATION":
            ready += 1
        if str(cell.get("terminal_outcome") or ""):
            terminal[str(cell.get("terminal_outcome") or "")] += 1
    next_action = "create_second_campaign_preregistration_manifest" if ready else "continue_fail_closed_readiness_remediation"
    return {
        "ready_cells": ready,
        "terminal_outcomes": dict(sorted(terminal.items())),
        "blocker_counts": dict(sorted(blocker_counts.items())),
        "next_action": next_action,
    }


def _write_reports(
    *,
    repo_root: Path,
    blockers: list[dict[str, Any]],
    universe_rows: list[dict[str, Any]],
    timeframe_rows: list[dict[str, Any]],
    preset_rows: list[dict[str, Any]],
    data_rows: list[dict[str, Any]],
    window_rows: list[dict[str, Any]],
    null_rows: list[dict[str, Any]],
    campaign_metadata_rows: list[dict[str, Any]],
    lineage_rows: list[dict[str, Any]],
    portfolio_rows: list[dict[str, Any]],
    iteration_rows: list[dict[str, Any]],
    closeout: dict[str, Any],
) -> None:
    def _repo_output_path(path: Path) -> Path:
        if path.is_absolute() and REPO_ROOT in path.parents:
            return repo_root / path.relative_to(REPO_ROOT)
        return path

    payloads = [
        (
            BLOCKERS_PATH,
            "qre_autonomous_readiness_blockers",
            blockers,
            "blocker_report_identity",
        ),
        (
            UNIVERSE_AUTHORITY_PATH,
            "qre_autonomous_universe_authority",
            universe_rows,
            "universe_authority_identity",
        ),
        (
            TIMEFRAME_RESOLUTION_PATH,
            "qre_autonomous_timeframe_resolution",
            timeframe_rows,
            "timeframe_resolution_identity",
        ),
        (
            PRESET_COMPLETION_PATH,
            "qre_autonomous_completed_presets",
            preset_rows,
            "preset_completion_identity",
        ),
        (
            DATA_BINDING_PATH,
            "qre_autonomous_strategy_data_bindings",
            data_rows,
            "data_binding_identity",
        ),
        (
            WINDOW_CAPACITY_PATH,
            "qre_autonomous_window_capacity",
            window_rows,
            "window_capacity_identity",
        ),
        (
            NULL_CONTROL_PATH,
            "qre_autonomous_null_control_readiness",
            null_rows,
            "null_control_readiness_identity",
        ),
        (
            CAMPAIGN_METADATA_PATH,
            "qre_autonomous_campaign_metadata",
            campaign_metadata_rows,
            "campaign_metadata_identity",
        ),
        (
            CAMPAIGN_LINEAGE_PATH,
            "qre_autonomous_campaign_lineage",
            lineage_rows,
            "campaign_lineage_identity",
        ),
        (
            PORTFOLIO_PATH,
            "qre_autonomous_portfolio_readiness",
            portfolio_rows,
            "portfolio_identity",
        ),
        (
            ITERATION_LEDGER_PATH,
            "qre_autonomous_iteration_ledger",
            iteration_rows,
            "iteration_ledger_identity",
        ),
    ]
    for path, report_kind, rows, identity_field in payloads:
        payload = {
            "schema_version": SCHEMA_VERSION,
            "module_version": MODULE_VERSION,
            "report_kind": report_kind,
            identity_field: _content_id(identity_field[:3], rows),
            "rows": rows,
        }
        _write_json(_repo_output_path(path), payload)
    _write_json(_repo_output_path(CLOSEOUT_JSON_PATH), closeout)
    _atomic_write(_repo_output_path(CLOSEOUT_MD_PATH), _markdown_closeout(closeout))
    manifest = closeout.get("manifest")
    manifest_path = _repo_output_path(MANIFEST_PATH)
    if isinstance(manifest, dict) and manifest:
        _write_json(manifest_path, manifest)
    elif manifest_path.exists():
        manifest_path.unlink()


def _markdown_closeout(payload: dict[str, Any]) -> str:
    lines = [
        "# Autonomous Readiness Closure",
        "",
        f"- outcome: `{payload['overall_outcome']}`",
        f"- ready cells: `{payload['summary']['ready_for_preregistration_count']}`",
        f"- strategies processed: `{payload['summary']['strategies_processed']}`",
        f"- iterations: `{payload['summary']['iteration_count']}`",
        f"- exact next action: `{payload['exact_next_action']}`",
        "",
        "## Strategy Outcomes",
    ]
    for row in payload.get("strategy_outcomes", []):
        lines.append(
            f"- `{row['generated_strategy_id']}`: `{row['terminal_outcome']}` -> `{row['terminal_reason']}`"
        )
    lines.append("")
    return "\n".join(lines)


def _choose_overall_outcome(cells: list[dict[str, Any]]) -> str:
    ready_count = len([cell for cell in cells if str(cell.get("portfolio_status") or "") == "READY_FOR_PREREGISTRATION"])
    if ready_count:
        return "READY_FOR_SECOND_CAMPAIGN"
    terminals = Counter(str(cell.get("terminal_outcome") or "") for cell in cells if str(cell.get("terminal_outcome") or ""))
    if terminals.get("INDEPENDENT_OOS_CAPACITY_BLOCKED"):
        return "INDEPENDENT_OOS_CAPACITY_BLOCKED"
    if terminals.get("DATA_CAPACITY_BLOCKED"):
        return "DATA_CAPACITY_BLOCKED"
    if terminals.get("SCIENTIFICALLY_BLOCKED"):
        return "SCIENTIFICALLY_BLOCKED"
    if terminals.get("NO_VALID_REMEDIATION_PATH"):
        return "NO_SAFE_REMEDIATION_PATH"
    if terminals:
        return "PARTIAL_READINESS_CLOSURE"
    return "NO_CAMPAIGN_READY_STRATEGIES"


def run_autonomous_closure(
    *,
    repo_root: Path | None = None,
    strategy_ids: list[str] | None = None,
    max_iterations: int = 8,
) -> dict[str, Any]:
    root = repo_root or REPO_ROOT
    inputs = _load_baseline_inputs(root)
    target_ids = strategy_ids or ["qgs_e565b01bd0a162d0", "qgs_5af8f605ba82ae53"]
    cells: list[dict[str, Any]] = []
    universe_rows: list[dict[str, Any]] = []
    timeframe_rows: list[dict[str, Any]] = []
    preset_rows: list[dict[str, Any]] = []
    data_rows: list[dict[str, Any]] = []
    window_rows: list[dict[str, Any]] = []
    null_rows: list[dict[str, Any]] = []
    campaign_metadata_rows: list[dict[str, Any]] = []
    lineage_rows: list[dict[str, Any]] = []
    portfolio_rows: list[dict[str, Any]] = []
    all_blockers: list[dict[str, Any]] = []
    iteration_rows: list[dict[str, Any]] = []

    for strategy_id in target_ids:
        registry_row = inputs["registry_by_strategy"][strategy_id]
        spec = inputs["specs_by_id"][str(registry_row.get("strategy_spec_id") or "")]
        strategy_cells = _initial_cells(registry_row, spec)
        for cell in strategy_cells:
            timeframe_rows.append(
                {
                    "generated_strategy_id": strategy_id,
                    "campaign_cell_id": str(cell.get("campaign_cell_id") or ""),
                    "requested_timeframe": str(cell.get("requested_timeframe") or ""),
                    "resolution_outcome": str(cell.get("timeframe_resolution_state") or ""),
                    "selection_reason": (
                        "multiple independently valid spec timeframes split into distinct campaign cells"
                        if bool(cell.get("split_required"))
                        else "single authoritative timeframe in strategy specification"
                    ),
                    "provenance": [
                        "generated_research/specs",
                        "generated_research/readiness/gaps/strategy_readiness_gaps.v1.json",
                        "logs/qre_data_cache_manifest/latest.json",
                    ],
                }
            )
            if strategy_id == "qgs_e565b01bd0a162d0":
                universe_row = _apply_strategy_specific_identity_resolution(cell=cell, spec=spec, inputs=inputs)
                if universe_row:
                    universe_rows.append(
                        {
                            "generated_strategy_id": strategy_id,
                            "campaign_cell_id": str(cell.get("campaign_cell_id") or ""),
                            **universe_row,
                        }
                    )
            _refresh_cell_state(cell=cell, spec=spec, inputs=inputs)
            cells.append(cell)

    seen_fingerprints: set[str] = set()
    no_progress_streak = 0
    for iteration_index in range(1, max_iterations + 1):
        for cell in cells:
            if str(cell.get("terminal_outcome") or ""):
                continue
            spec = inputs["specs_by_id"][str(cell.get("strategy_spec_id") or "")]
            _refresh_cell_state(cell=cell, spec=spec, inputs=inputs)
        before = _summary_from_cells(cells)
        selected_cell, selected_blocker = _select_blocker([cell for cell in cells if not str(cell.get("terminal_outcome") or "")])
        if selected_cell is None or selected_blocker is None:
            iteration_rows.append(
                _iteration_row(
                    iteration_index=iteration_index,
                    before_summary=before,
                    selected_cell=None,
                    selected_blocker=None,
                    remediation=None,
                    after_summary=before,
                    progress_status="terminal_no_blockers",
                )
            )
            break
        fingerprint = _stable_json(
            {
                "cell": str(selected_cell.get("campaign_cell_id") or ""),
                "blocker_class": str(selected_blocker.get("blocker_class") or ""),
                "reason": str(selected_blocker.get("reason") or ""),
            }
        )
        if fingerprint in seen_fingerprints and no_progress_streak >= 1:
            _mark_terminal(
                selected_cell,
                "NO_VALID_REMEDIATION_PATH",
                "cycle_detected_same_upstream_blocker_recurred_without_progress",
            )
            after = _summary_from_cells(cells)
            iteration_rows.append(
                _iteration_row(
                    iteration_index=iteration_index,
                    before_summary=before,
                    selected_cell=selected_cell,
                    selected_blocker=selected_blocker,
                    remediation={"decision": "FAIL_CLOSED", "reason": "cycle_detected"},
                    after_summary=after,
                    progress_status="cycle_detected",
                )
            )
            break
        seen_fingerprints.add(fingerprint)
        spec = inputs["specs_by_id"][str(selected_cell.get("strategy_spec_id") or "")]
        remediation = _execute_remediation(
            cell=selected_cell,
            blocker=selected_blocker,
            spec=spec,
            inputs=inputs,
        )
        _refresh_cell_state(cell=selected_cell, spec=spec, inputs=inputs)
        after = _summary_from_cells(cells)
        progress_status = "progress" if remediation["progress"] and after != before else "no_progress"
        no_progress_streak = 0 if progress_status == "progress" else no_progress_streak + 1
        iteration_rows.append(
            _iteration_row(
                iteration_index=iteration_index,
                before_summary=before,
                selected_cell=selected_cell,
                selected_blocker=selected_blocker,
                remediation=remediation,
                after_summary=after,
                progress_status=progress_status,
            )
        )
        if all(str(cell.get("terminal_outcome") or "") or str(cell.get("portfolio_status") or "") == "READY_FOR_PREREGISTRATION" for cell in cells):
            break

    for cell in sorted(cells, key=_cell_sort_key):
        spec = inputs["specs_by_id"][str(cell.get("strategy_spec_id") or "")]
        _refresh_cell_state(cell=cell, spec=spec, inputs=inputs)
        all_blockers.extend(_serialize_blocker(cell=cell, blocker=blocker) for blocker in list(cell.get("blockers") or []))
        if cell.get("universe_identity") or cell.get("membership_snapshot_id"):
            universe_rows.append(
                {
                    "generated_strategy_id": str(cell.get("generated_strategy_id") or ""),
                    "campaign_cell_id": str(cell.get("campaign_cell_id") or ""),
                    "requested_alias": "breadth_resolved_multi_asset_basket" if str(cell.get("source_hypothesis_id") or "") == "cross_sectional_momentum_v0" else "single_resolved_instrument_only",
                    "resolution_outcome": "RESOLVED_UNIQUE_AUTHORITATIVE" if str(cell.get("source_hypothesis_id") or "") == "cross_sectional_momentum_v0" else "RESOLVED_WITH_LIMITATIONS",
                    "selected_universe_id": str(cell.get("universe_identity") or ""),
                    "membership_snapshot_id": str(cell.get("membership_snapshot_id") or ""),
                    "included_members": [
                        {"canonical_instrument_id": value}
                        if isinstance(value, str)
                        else value
                        for value in (cell.get("included_members") or cell.get("instrument_identities") or [])
                    ],
                    "excluded_members": list(cell.get("excluded_members") or []),
                    "selection_reason": str(cell.get("universe_reason") or ""),
                    "provenance": list(cell.get("provenance") or []),
                }
            )
        preset_rows.append(
            {
                "generated_strategy_id": str(cell.get("generated_strategy_id") or ""),
                "campaign_cell_id": str(cell.get("campaign_cell_id") or ""),
                "timeframe": str(cell.get("resolved_timeframe") or ""),
                "outcome": str(cell.get("preset_state") or ""),
                "preset_id": str(cell.get("preset_id") or ""),
                "reason": str(cell.get("preset_reason") or ""),
                "dataset_identity": str(cell.get("dataset_identity") or ""),
                "snapshot_identity": str(cell.get("snapshot_identity") or ""),
                "universe_identity": str(cell.get("universe_identity") or ""),
                "parameter_values": dict(cell.get("parameter_values") or {}),
                "provenance": list(cell.get("provenance") or []),
            }
        )
        data_rows.append(
            {
                "generated_strategy_id": str(cell.get("generated_strategy_id") or ""),
                "campaign_cell_id": str(cell.get("campaign_cell_id") or ""),
                "timeframe": str(cell.get("resolved_timeframe") or ""),
                "outcome": "DATA_BINDING_READY" if str(cell.get("data_binding_state") or "") in {"RESOLVED", "RESOLVED_WITH_LIMITATIONS"} else "DATASET_MISSING",
                "state": str(cell.get("data_binding_state") or ""),
                "reason": str(cell.get("data_binding_reason") or ""),
                "source_identity": str(cell.get("source_identity") or ""),
                "dataset_identity": str(cell.get("dataset_identity") or ""),
                "snapshot_identity": str(cell.get("snapshot_identity") or ""),
                "provenance": list(cell.get("provenance") or []),
            }
        )
        window = dict(cell.get("window_capacity") or {})
        window_rows.append(
            {
                "generated_strategy_id": str(cell.get("generated_strategy_id") or ""),
                "campaign_cell_id": str(cell.get("campaign_cell_id") or ""),
                "timeframe": str(cell.get("resolved_timeframe") or ""),
                "outcome": str(window.get("terminal_outcome") or "WINDOW_CAPACITY_READY"),
                "state": str(cell.get("window_state") or ""),
                "reason": str(cell.get("window_reason") or ""),
                "earliest_usable_timestamp_utc": str(window.get("earliest_usable_timestamp_utc") or ""),
                "latest_usable_timestamp_utc": str(window.get("latest_usable_timestamp_utc") or ""),
                "warmup_requirement_bars": int(window.get("warmup_requirement_bars") or 0),
                "provenance": list(cell.get("provenance") or []),
            }
        )
        null_rows.extend(
            {
                "generated_strategy_id": str(cell.get("generated_strategy_id") or ""),
                "campaign_cell_id": str(cell.get("campaign_cell_id") or ""),
                "timeframe": str(cell.get("resolved_timeframe") or ""),
                **row,
                "provenance": list(cell.get("provenance") or []),
            }
            for row in list(cell.get("null_control_outcomes") or [])
        )
        campaign_metadata_rows.append(
            {
                "generated_strategy_id": str(cell.get("generated_strategy_id") or ""),
                "campaign_cell_id": str(cell.get("campaign_cell_id") or ""),
                "campaign_metadata_id": str(cell.get("campaign_metadata_id") or ""),
                "campaign_metadata_state": str(cell.get("campaign_metadata_state") or ""),
                "timeframe": str(cell.get("resolved_timeframe") or ""),
                "universe_identity": str(cell.get("universe_identity") or ""),
                "dataset_identity": str(cell.get("dataset_identity") or ""),
                "snapshot_identity": str(cell.get("snapshot_identity") or ""),
                "preset_id": str(cell.get("preset_id") or ""),
                "null_controls": list(cell.get("null_controls") or []),
                "blockers": [row["reason"] for row in list(cell.get("blockers") or [])],
                "provenance": list(cell.get("provenance") or []),
            }
        )
        lineage_rows.append(
            {
                "generated_strategy_id": str(cell.get("generated_strategy_id") or ""),
                "campaign_cell_id": str(cell.get("campaign_cell_id") or ""),
                "lineage_identity": str(cell.get("lineage_identity") or ""),
                "lineage_state": str(cell.get("lineage_state") or ""),
                "blockers": [row["reason"] for row in list(cell.get("blockers") or [])],
                "provenance": list(cell.get("provenance") or []),
            }
        )
        portfolio_rows.append(
            {
                "generated_strategy_id": str(cell.get("generated_strategy_id") or ""),
                "campaign_cell_id": str(cell.get("campaign_cell_id") or ""),
                "status": str(cell.get("portfolio_status") or ""),
                "blockers": [str(row["reason"]) for row in list(cell.get("blockers") or [])],
                "timeframe": str(cell.get("resolved_timeframe") or ""),
                "universe_identity": str(cell.get("universe_identity") or ""),
                "preset_id": str(cell.get("preset_id") or ""),
                "next_action": (
                    "create_second_campaign_preregistration_manifest"
                    if str(cell.get("portfolio_status") or "") == "READY_FOR_PREREGISTRATION"
                    else "preserve_fail_closed_autonomous_readiness_blockers"
                ),
            }
        )
        if not str(cell.get("terminal_outcome") or "") and str(cell.get("portfolio_status") or "") != "READY_FOR_PREREGISTRATION":
            primary = list(cell.get("blockers") or [])
            if primary:
                first = primary[0]
                outcome = "NO_VALID_REMEDIATION_PATH"
                if first["blocker_class"] in {"OOS_WINDOW_MISSING", "OOS_INDEPENDENCE_NOT_PROVEN"}:
                    outcome = "INDEPENDENT_OOS_CAPACITY_BLOCKED"
                elif first["blocker_class"] in {"DATA_COVERAGE_INSUFFICIENT", "DATASET_IDENTITY_MISSING"}:
                    outcome = "DATA_CAPACITY_BLOCKED"
                _mark_terminal(cell, outcome, str(first.get("reason") or "remaining_fail_closed_blocker"))

    ready_cells = [row for row in portfolio_rows if row["status"] == "READY_FOR_PREREGISTRATION"]
    manifest: dict[str, Any] | None = None
    if ready_cells:
        manifest_core = {
            "ready_cells": [
                {
                    "campaign_cell_id": row["campaign_cell_id"],
                    "generated_strategy_id": row["generated_strategy_id"],
                    "timeframe": row["timeframe"],
                    "universe_identity": row["universe_identity"],
                    "preset_id": row["preset_id"],
                }
                for row in ready_cells
            ],
            "version": MODULE_VERSION,
        }
        manifest = {
            "schema_version": SCHEMA_VERSION,
            "module_version": MODULE_VERSION,
            "report_kind": "qre_autonomous_second_campaign_manifest",
            "manifest_identity": _content_id("qcm", manifest_core),
            "replay_identity": _content_id("qcr", manifest_core),
            "rows": ready_cells,
        }
    summary = _summary_from_cells(cells)
    closeout = {
        "schema_version": SCHEMA_VERSION,
        "module_version": MODULE_VERSION,
        "report_kind": REPORT_KIND,
        "closeout_identity": _content_id(
            "qrca",
            {
                "cells": [
                    {
                        "campaign_cell_id": cell["campaign_cell_id"],
                        "generated_strategy_id": cell["generated_strategy_id"],
                        "portfolio_status": cell["portfolio_status"],
                        "terminal_outcome": cell["terminal_outcome"],
                        "terminal_reason": cell["terminal_reason"],
                    }
                    for cell in sorted(cells, key=_cell_sort_key)
                ],
                "iterations": [row["iteration_id"] for row in iteration_rows],
            },
        ),
        "overall_outcome": _choose_overall_outcome(cells),
        "summary": {
            "strategies_processed": len(target_ids),
            "campaign_cells": len(cells),
            "ready_for_preregistration_count": len(ready_cells),
            "iteration_count": len(iteration_rows),
            "terminal_outcomes": summary["terminal_outcomes"],
        },
        "strategy_outcomes": [
            {
                "generated_strategy_id": str(cell.get("generated_strategy_id") or ""),
                "campaign_cell_id": str(cell.get("campaign_cell_id") or ""),
                "timeframe": str(cell.get("resolved_timeframe") or ""),
                "portfolio_status": str(cell.get("portfolio_status") or ""),
                "terminal_outcome": str(cell.get("terminal_outcome") or ""),
                "terminal_reason": str(cell.get("terminal_reason") or ""),
            }
            for cell in sorted(cells, key=_cell_sort_key)
        ],
        "initial_blockers": [
            {
                "generated_strategy_id": "qgs_e565b01bd0a162d0",
                "primary_blocker": "non_authoritative_universe_alias_only",
            },
            {
                "generated_strategy_id": "qgs_5af8f605ba82ae53",
                "primary_blocker": "timeframe_not_resolved",
            },
        ],
        "remaining_blockers": sorted(
            {
                str(blocker["reason"])
                for blocker in all_blockers
                if str(blocker["reason"])
            }
        ),
        "exact_next_action": (
            "create_second_campaign_preregistration_manifest"
            if ready_cells
            else "preserve_fail_closed_readiness_closure_and_route_window_or_data_capacity_blockers"
        ),
        "manifest": manifest or {},
    }
    _write_reports(
        repo_root=root,
        blockers=all_blockers,
        universe_rows=sorted(universe_rows, key=lambda row: (str(row.get("generated_strategy_id") or ""), str(row.get("campaign_cell_id") or ""))),
        timeframe_rows=sorted(timeframe_rows, key=lambda row: (str(row.get("generated_strategy_id") or ""), str(row.get("campaign_cell_id") or ""))),
        preset_rows=sorted(preset_rows, key=lambda row: (str(row.get("generated_strategy_id") or ""), str(row.get("campaign_cell_id") or ""))),
        data_rows=sorted(data_rows, key=lambda row: (str(row.get("generated_strategy_id") or ""), str(row.get("campaign_cell_id") or ""))),
        window_rows=sorted(window_rows, key=lambda row: (str(row.get("generated_strategy_id") or ""), str(row.get("campaign_cell_id") or ""))),
        null_rows=sorted(null_rows, key=lambda row: (str(row.get("generated_strategy_id") or ""), str(row.get("campaign_cell_id") or ""), str(row.get("control_class") or ""))),
        campaign_metadata_rows=sorted(campaign_metadata_rows, key=lambda row: (str(row.get("generated_strategy_id") or ""), str(row.get("campaign_cell_id") or ""))),
        lineage_rows=sorted(lineage_rows, key=lambda row: (str(row.get("generated_strategy_id") or ""), str(row.get("campaign_cell_id") or ""))),
        portfolio_rows=sorted(portfolio_rows, key=lambda row: (str(row.get("generated_strategy_id") or ""), str(row.get("campaign_cell_id") or ""))),
        iteration_rows=iteration_rows,
        closeout=closeout,
    )
    return closeout


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="ADE-QRE-023 autonomous research-readiness closure loop")
    parser.add_argument("--strategy", action="append", default=[])
    parser.add_argument("--max-iterations", type=int, default=8)
    args = parser.parse_args(argv)
    result = run_autonomous_closure(
        strategy_ids=args.strategy or None,
        max_iterations=args.max_iterations,
    )
    print(json.dumps(result, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
