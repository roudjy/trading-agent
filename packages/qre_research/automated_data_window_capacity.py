from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import tempfile
from contextlib import suppress
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, Final

from packages.qre_research import automated_campaign_readiness as acr
from packages.qre_research import autonomous_readiness_closure as arc
from packages.qre_research.generated_strategy_paths import REPO_ROOT, validate_write_target

SCHEMA_VERSION: Final[str] = "1.0"
MODULE_VERSION: Final[str] = "ade-qre-024.1"
REPORT_KIND: Final[str] = "qre_automated_data_window_capacity"
WINDOW_POLICY_VERSION: Final[str] = "ade-qre-024.window-policy.1"
WINDOW_LEDGER_VERSION: Final[str] = "ade-qre-024.window-ledger.1"
SNAPSHOT_VERSION: Final[str] = "ade-qre-024.snapshot.1"
DATA_RESOLVER_VERSION: Final[str] = "ade-qre-024.data-resolver.1"

TERMINAL_OUTCOME: Final[tuple[str, ...]] = (
    "READY_FOR_SECOND_CAMPAIGN",
    "PARTIAL_DATA_AND_WINDOW_CLOSURE",
    "DATA_SOURCE_UNAVAILABLE",
    "DATA_COVERAGE_INSUFFICIENT",
    "INDEPENDENT_OOS_CAPACITY_BLOCKED",
    "WINDOW_POLICY_BLOCKED",
    "POINT_IN_TIME_UNIVERSE_BLOCKED",
    "SIGNAL_DENSITY_CAPACITY_BLOCKED",
    "NO_SAFE_AUTOMATED_REMEDIATION",
    "LOOP_STALLED_WITH_EVIDENCE",
)

DIAGNOSIS_OUTCOME: Final[tuple[str, ...]] = (
    "DATA_CAPACITY_READY",
    "CACHE_ROW_MISSING",
    "CACHE_RANGE_INCOMPLETE",
    "SOURCE_BINDING_MISSING",
    "DATASET_BINDING_MISSING",
    "SNAPSHOT_MISSING",
    "SCHEMA_INCOMPATIBLE",
    "FREQUENCY_INCOMPATIBLE",
    "COVERAGE_INSUFFICIENT",
    "POINT_IN_TIME_MEMBERSHIP_INCOMPLETE",
    "CROSS_SECTION_BREADTH_INSUFFICIENT",
    "QUALITY_BLOCKED",
    "EXTERNAL_DATA_REQUIRED",
)

WINDOW_POLICY_OUTCOME: Final[tuple[str, ...]] = (
    "WINDOW_POLICY_READY",
    "WINDOW_POLICY_READY_WITH_LIMITATIONS",
    "INSUFFICIENT_USABLE_HISTORY",
    "INSUFFICIENT_SIGNAL_CAPACITY",
    "INSUFFICIENT_REGIME_COVERAGE",
    "NO_INDEPENDENT_OOS_AVAILABLE",
    "POINT_IN_TIME_UNIVERSE_BLOCKED",
    "POLICY_INPUT_INCOMPLETE",
)

INDEPENDENCE_OUTCOME: Final[tuple[str, ...]] = (
    "INDEPENDENCE_PROVEN",
    "INDEPENDENCE_PROVEN_WITH_LIMITATIONS",
    "WINDOW_PREVIOUSLY_CONSUMED",
    "OVERLAP_BLOCKED",
    "TUNING_EXPOSURE_BLOCKED",
    "EMBARGO_VIOLATION",
    "POINT_IN_TIME_VIOLATION",
    "INSUFFICIENT_EVIDENCE_TO_PROVE_INDEPENDENCE",
)

SIGNAL_CAPACITY_OUTCOME: Final[tuple[str, ...]] = (
    "SIGNAL_CAPACITY_READY",
    "SIGNAL_CAPACITY_READY_WITH_LIMITATIONS",
    "EXPECTED_TRADES_INSUFFICIENT",
    "EXPECTED_SIGNALS_INSUFFICIENT",
    "CROSS_SECTION_BREADTH_INSUFFICIENT",
    "REGIME_OCCURRENCE_INSUFFICIENT",
    "INSUFFICIENT_EVIDENCE_TO_ESTIMATE",
)

PORTFOLIO_STATUS: Final[tuple[str, ...]] = (
    "READY_FOR_PREREGISTRATION",
    "BLOCKED_IDENTITY",
    "BLOCKED_DATA",
    "BLOCKED_WINDOWS",
    "BLOCKED_NULL_CONTROLS",
    "BLOCKED_SIGNAL_DENSITY",
    "INSUFFICIENT_EVIDENCE",
)

ITERATION_PROGRESS: Final[tuple[str, ...]] = (
    "RESOLVED_BLOCKER",
    "DOWNSTREAM_BLOCKER_EXPOSED",
    "IRREDUCIBLE_BLOCKER_PROVEN",
    "NO_PROGRESS",
)

GENERATED_READINESS_ROOT: Final[Path] = REPO_ROOT / "generated_research" / "readiness"
DATA_CAPACITY_DIR: Final[Path] = GENERATED_READINESS_ROOT / "data_capacity"
SNAPSHOTS_DIR: Final[Path] = GENERATED_READINESS_ROOT / "snapshots"
WINDOW_LEDGER_DIR: Final[Path] = GENERATED_READINESS_ROOT / "window_ledger"
CAMPAIGNS_DIR: Final[Path] = GENERATED_READINESS_ROOT / "campaigns"
REPORTS_DIR: Final[Path] = GENERATED_READINESS_ROOT / "reports"

DATA_DIAGNOSIS_PATH: Final[Path] = DATA_CAPACITY_DIR / "strategy_data_capacity_diagnosis.v1.json"
DATA_AUTHORITY_PATH: Final[Path] = DATA_CAPACITY_DIR / "canonical_data_cache_authority.v1.json"
MATERIALIZED_CACHE_ROWS_PATH: Final[Path] = DATA_CAPACITY_DIR / "materialized_cache_rows.v1.json"
QUALITY_PATH: Final[Path] = DATA_CAPACITY_DIR / "strategy_data_quality_coverage.v1.json"
SNAPSHOTS_PATH: Final[Path] = SNAPSHOTS_DIR / "immutable_strategy_snapshots.v1.json"
WINDOW_POLICY_PATH: Final[Path] = GENERATED_READINESS_ROOT / "window_capacity" / "authoritative_window_policy.v1.json"
WINDOW_LEDGER_PATH: Final[Path] = WINDOW_LEDGER_DIR / "canonical_window_ledger.v1.json"
WINDOW_ASSIGNMENTS_PATH: Final[Path] = GENERATED_READINESS_ROOT / "window_capacity" / "authoritative_window_assignments.v1.json"
INDEPENDENCE_PATH: Final[Path] = GENERATED_READINESS_ROOT / "window_capacity" / "oos_independence_proof.v1.json"
PIT_UNIVERSE_PATH: Final[Path] = GENERATED_READINESS_ROOT / "window_capacity" / "point_in_time_universe_validation.v1.json"
SIGNAL_CAPACITY_PATH: Final[Path] = GENERATED_READINESS_ROOT / "window_capacity" / "signal_density_capacity.v1.json"
PORTFOLIO_PATH: Final[Path] = CAMPAIGNS_DIR / "automated_portfolio_readiness.v1.json"
MANIFEST_PATH: Final[Path] = CAMPAIGNS_DIR / "generated_second_campaign_manifest.v1.json"
ITERATION_LEDGER_PATH: Final[Path] = REPORTS_DIR / "automated_data_window_iteration_ledger.v1.json"
CLOSEOUT_JSON_PATH: Final[Path] = REPORTS_DIR / "automated_data_window_capacity_closeout.v1.json"
CLOSEOUT_MD_PATH: Final[Path] = REPORTS_DIR / "automated_data_window_capacity_closeout.v1.md"

_CACHE_FILE_RE: Final[re.Pattern[str]] = re.compile(
    r"(?P<source>[A-Za-z0-9_]+)__(?P<symbol>[^_]+)__(?P<timeframe>[^_]+)__(?P<start>\d{8})__(?P<end>\d{8})__"
)


def _stable_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def stable_digest(value: Any) -> str:
    return hashlib.sha256(_stable_json(value).encode("utf-8")).hexdigest()


def _content_id(prefix: str, value: Any) -> str:
    return f"{prefix}_{stable_digest(value)[:16]}"


def _atomic_write(path: Path, payload: str) -> None:
    validate_write_target(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=".ade_qre_024.", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(payload)
        os.replace(tmp_name, path)
    except Exception:
        with suppress(OSError):
            os.unlink(tmp_name)
        raise


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    _atomic_write(path, json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=True) + "\n")


def _maybe_write_json(path: Path, payload: dict[str, Any], *, write_outputs: bool) -> None:
    if write_outputs:
        _write_json(path, payload)


def _maybe_write_text(path: Path, payload: str, *, write_outputs: bool) -> None:
    if write_outputs:
        _atomic_write(path, payload)


def _read_json(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _read_rows(path: Path, *keys: str) -> list[dict[str, Any]]:
    payload = _read_json(path) or {}
    for key in keys:
        rows = payload.get(key)
        if isinstance(rows, list):
            return [dict(row) for row in rows if isinstance(row, dict)]
    return []


def _iso_to_dt(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)


def _dt_to_iso(value: datetime) -> str:
    return value.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _bar_seconds(timeframe: str) -> int:
    return {
        "1h": 3600,
        "4h": 4 * 3600,
        "1d": 24 * 3600,
    }.get(timeframe, 24 * 3600)


def _symbol_from_canonical(instrument_id: str) -> str:
    return instrument_id.split(":")[-1].strip()


def _load_specs(repo_root: Path) -> dict[str, dict[str, Any]]:
    specs: dict[str, dict[str, Any]] = {}
    for path in sorted((repo_root / "generated_research" / "specs").glob("qsp_*.json")):
        payload = _read_json(path)
        if not payload:
            continue
        strategy_spec_id = str(payload.get("strategy_spec_id") or "")
        if strategy_spec_id:
            specs[strategy_spec_id] = payload
    return specs


def _load_autonomous_rows(repo_root: Path, relative: str) -> list[dict[str, Any]]:
    return _read_rows(repo_root / relative, "rows")


def _load_a23_cells(repo_root: Path) -> list[dict[str, Any]]:
    portfolio_rows = _load_autonomous_rows(repo_root, "generated_research/readiness/campaigns/autonomous_portfolio_readiness.v1.json")
    data_rows = {
        (str(row.get("campaign_cell_id") or ""), str(row.get("generated_strategy_id") or "")): row
        for row in _load_autonomous_rows(repo_root, "generated_research/readiness/data_bindings/autonomous_strategy_data_bindings.v1.json")
    }
    universe_rows = {
        (str(row.get("campaign_cell_id") or ""), str(row.get("generated_strategy_id") or "")): row
        for row in _load_autonomous_rows(repo_root, "generated_research/readiness/identity_decisions/autonomous_universe_authority.v1.json")
        if row.get("campaign_cell_id")
    }
    preset_rows = {
        (str(row.get("campaign_cell_id") or ""), str(row.get("generated_strategy_id") or "")): row
        for row in _load_autonomous_rows(repo_root, "generated_research/readiness/presets/autonomous_completed_presets.v1.json")
    }
    null_rows = [dict(row) for row in _load_autonomous_rows(repo_root, "generated_research/readiness/null_controls/autonomous_null_control_readiness.v1.json")]
    registry_rows = {
        str(row.get("generated_strategy_id") or ""): row
        for row in _read_rows(repo_root / "generated_research/registry/generated_strategy_registry.v1.json", "rows")
    }
    specs = _load_specs(repo_root)
    cells: list[dict[str, Any]] = []
    for row in portfolio_rows:
        key = (str(row.get("campaign_cell_id") or ""), str(row.get("generated_strategy_id") or ""))
        registry_row = dict(registry_rows.get(key[1]) or {})
        spec = dict(specs.get(str(registry_row.get("strategy_spec_id") or "")) or {})
        cell = {
            **row,
            "registry_row": registry_row,
            "spec": spec,
            "data_binding": dict(data_rows.get(key) or {}),
            "universe_row": dict(universe_rows.get(key) or {}),
            "preset_row": dict(preset_rows.get(key) or {}),
            "null_rows": [item for item in null_rows if str(item.get("campaign_cell_id") or "") == key[0]],
        }
        cells.append(cell)
    return sorted(cells, key=lambda item: (str(item.get("generated_strategy_id") or ""), str(item.get("timeframe") or ""), str(item.get("campaign_cell_id") or "")))


def _load_coverage_rows(repo_root: Path) -> list[dict[str, Any]]:
    artifact_rows = _read_rows(repo_root / "artifacts/cache/cache_coverage_latest.v1.json", "coverage")
    manifest_rows = _read_rows(repo_root / "logs/qre_data_cache_manifest/latest.json", "coverage")
    combined: dict[tuple[str, str, str], dict[str, Any]] = {}
    for row in [*artifact_rows, *manifest_rows]:
        key = (
            str(row.get("source") or ""),
            str(row.get("instrument") or "").upper(),
            str(row.get("timeframe") or ""),
        )
        existing = combined.get(key)
        if existing is None or _coverage_priority(row) > _coverage_priority(existing):
            combined[key] = dict(row)
    return sorted(
        combined.values(),
        key=lambda row: (
            str(row.get("source") or ""),
            str(row.get("instrument") or ""),
            str(row.get("timeframe") or ""),
        ),
    )


def _coverage_priority(row: dict[str, Any]) -> tuple[int, str, int, int]:
    ready_rank = 1 if bool(row.get("ready")) else 0
    max_ts = str(row.get("max_timestamp_utc") or "")
    row_count = int(row.get("row_count") or 0)
    file_count = int(row.get("file_count") or 0)
    return (max_ts, ready_rank, row_count, file_count)


def _load_cache_files(repo_root: Path) -> list[dict[str, Any]]:
    return _read_rows(repo_root / "logs/qre_data_cache_manifest/latest.json", "files")


def _load_existing_manifest(repo_root: Path) -> dict[str, Any]:
    return _read_json(repo_root / "logs/qre_preregistered_campaign_manifest/latest.json") or {}


def _window_policy_for_timeframe(timeframe: str) -> dict[str, Any]:
    policy = {
        "1d": {
            "min_train_days": 30,
            "min_validation_days": 7,
            "min_oos_days": 7,
            "embargo_days": 3,
            "min_expected_signals": 2,
            "min_expected_trades": 2,
        },
        "4h": {
            "min_train_days": 365,
            "min_validation_days": 90,
            "min_oos_days": 90,
            "embargo_days": 14,
            "min_expected_signals": 6,
            "min_expected_trades": 6,
        },
        "1h": {
            "min_train_days": 120,
            "min_validation_days": 30,
            "min_oos_days": 30,
            "embargo_days": 7,
            "min_expected_signals": 6,
            "min_expected_trades": 6,
        },
    }
    return dict(policy.get(timeframe, policy["1d"]))


def _match_coverage_row(
    *,
    coverage_rows: list[dict[str, Any]],
    symbol: str,
    timeframe: str,
) -> dict[str, Any] | None:
    candidates = [
        row
        for row in coverage_rows
        if str(row.get("instrument") or "").upper() == symbol.upper()
        and str(row.get("timeframe") or "") == timeframe
        and bool(row.get("ready"))
    ]
    if len(candidates) != 1:
        return None
    return dict(candidates[0])


def _materialize_from_cache_files(
    *,
    repo_root: Path,
    symbol: str,
    timeframe: str,
) -> dict[str, Any] | None:
    matches: list[dict[str, Any]] = []
    for row in _load_cache_files(repo_root):
        path = str(row.get("path") or "")
        match = _CACHE_FILE_RE.search(Path(path).name)
        if not match:
            continue
        if match.group("symbol").upper() != symbol.upper() or match.group("timeframe") != timeframe:
            continue
        start = datetime.strptime(match.group("start"), "%Y%m%d").replace(tzinfo=UTC)
        end = datetime.strptime(match.group("end"), "%Y%m%d").replace(tzinfo=UTC)
        matches.append(
            {
                "path": path,
                "source": match.group("source"),
                "instrument": symbol,
                "timeframe": timeframe,
                "start": start,
                "end": end,
                "row_count": int(row.get("row_count") or 0),
                "content_hash": str(row.get("content_hash") or ""),
            }
        )
    if not matches:
        return None
    aggregate = {
        "instrument": symbol,
        "timeframe": timeframe,
        "source": sorted({row["source"] for row in matches})[0],
        "min_timestamp_utc": _dt_to_iso(min(row["start"] for row in matches)),
        "max_timestamp_utc": _dt_to_iso(max(row["end"] for row in matches)),
        "row_count": sum(max(int(row["row_count"]), 0) for row in matches),
        "ready": True,
        "materialized_from_files": sorted(str(row["path"]) for row in matches),
        "content_hash": f"sha256:{stable_digest(sorted(str(row['content_hash']) for row in matches))}",
    }
    aggregate["cache_row_id"] = _content_id("qcr", aggregate)
    return aggregate


def _coverage_rows_for_cell(
    *,
    repo_root: Path,
    cell: dict[str, Any],
    coverage_rows: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], dict[str, Any] | None]:
    timeframe = str(cell.get("timeframe") or "")
    universe_row = dict(cell.get("universe_row") or {})
    included = list(universe_row.get("included_members") or [])
    matched: list[dict[str, Any]] = []
    materialized_rows: list[dict[str, Any]] = []
    for member in included:
        symbol = _symbol_from_canonical(str(member.get("canonical_instrument_id") or ""))
        row = _match_coverage_row(coverage_rows=coverage_rows, symbol=symbol, timeframe=timeframe)
        if row:
            matched.append(row)
            continue
        materialized = _materialize_from_cache_files(repo_root=repo_root, symbol=symbol, timeframe=timeframe)
        if materialized:
            matched.append(materialized)
            materialized_rows.append(materialized)
    if matched:
        return matched, (materialized_rows[0] if len(materialized_rows) == 1 else None)
    return [], None


def _diagnose_data_capacity(
    *,
    repo_root: Path,
    cell: dict[str, Any],
    coverage_rows: list[dict[str, Any]],
) -> tuple[dict[str, Any], dict[str, Any] | None]:
    matched_rows, materialized = _coverage_rows_for_cell(repo_root=repo_root, cell=cell, coverage_rows=coverage_rows)
    timeframe = str(cell.get("timeframe") or "")
    universe_row = dict(cell.get("universe_row") or {})
    included = list(universe_row.get("included_members") or [])
    expected_members = len(included)
    if not matched_rows:
        return (
            {
                "campaign_cell_id": str(cell.get("campaign_cell_id") or ""),
                "generated_strategy_id": str(cell.get("generated_strategy_id") or ""),
                "timeframe": timeframe,
                "status": "CACHE_ROW_MISSING",
                "remediation_class": "materialize_cache_row_from_authorized_local_inputs",
                "next_action": "materialize_missing_cache_row_if_authoritative_local_input_exists",
                "provenance": [
                    "artifacts/cache/cache_coverage_latest.v1.json",
                    "logs/qre_data_cache_manifest/latest.json",
                ],
            },
            materialized,
        )
    if expected_members > 1 and len(matched_rows) < expected_members:
        return (
            {
                "campaign_cell_id": str(cell.get("campaign_cell_id") or ""),
                "generated_strategy_id": str(cell.get("generated_strategy_id") or ""),
                "timeframe": timeframe,
                "status": "CROSS_SECTION_BREADTH_INSUFFICIENT",
                "remediation_class": "fail_closed_missing_member_coverage",
                "next_action": "preserve_fail_closed_cross_sectional_member_gap",
                "matched_member_count": len(matched_rows),
                "expected_member_count": expected_members,
                "provenance": [
                    "generated_research/readiness/identity_decisions/autonomous_universe_authority.v1.json",
                    "artifacts/cache/cache_coverage_latest.v1.json",
                ],
            },
            materialized,
        )
    start = max(_iso_to_dt(str(row.get("min_timestamp_utc") or "1970-01-01T00:00:00Z")) for row in matched_rows)
    end = min(_iso_to_dt(str(row.get("max_timestamp_utc") or "1970-01-01T00:00:00Z")) for row in matched_rows)
    if start >= end:
        return (
            {
                "campaign_cell_id": str(cell.get("campaign_cell_id") or ""),
                "generated_strategy_id": str(cell.get("generated_strategy_id") or ""),
                "timeframe": timeframe,
                "status": "CACHE_RANGE_INCOMPLETE",
                "remediation_class": "fail_closed_non_overlapping_coverage",
                "next_action": "preserve_fail_closed_non_overlapping_coverage",
                "provenance": ["artifacts/cache/cache_coverage_latest.v1.json"],
            },
            materialized,
        )
    quality_limitations: list[str] = []
    if len(matched_rows) > 1:
        quality_limitations.append("cross_sectional_common_range_intersection_applied")
    return (
        {
            "campaign_cell_id": str(cell.get("campaign_cell_id") or ""),
            "generated_strategy_id": str(cell.get("generated_strategy_id") or ""),
            "timeframe": timeframe,
            "status": "DATA_CAPACITY_READY",
            "authoritative_value": {
                "source_identity": sorted({str(row.get("source") or "") for row in matched_rows})[0],
                "instrument_count": len(matched_rows),
                "earliest_timestamp_utc": _dt_to_iso(start),
                "latest_timestamp_utc": _dt_to_iso(end),
            },
            "quality_limitations": quality_limitations,
            "coverage_rows": matched_rows,
            "remediation_class": "none",
            "next_action": "materialize_immutable_snapshot_and_assign_authoritative_windows",
            "provenance": [
                "artifacts/cache/cache_coverage_latest.v1.json",
                "logs/qre_data_cache_manifest/latest.json",
            ],
        },
        materialized,
    )


def _quality_row(cell: dict[str, Any], diagnosis: dict[str, Any]) -> dict[str, Any]:
    if diagnosis["status"] != "DATA_CAPACITY_READY":
        return {
            "campaign_cell_id": diagnosis["campaign_cell_id"],
            "generated_strategy_id": diagnosis["generated_strategy_id"],
            "quality_state": "QUALITY_BLOCKED",
            "usable_range_decision": "blocked",
            "exact_blockers": [diagnosis["status"].lower()],
            "quality_identity": _content_id("qdq", diagnosis),
        }
    coverage_rows = list(diagnosis.get("coverage_rows") or [])
    exact_blockers: list[str] = []
    for row in coverage_rows:
        if not bool(row.get("ready")):
            exact_blockers.append("row_not_ready")
        if not str(row.get("content_hash") or "").startswith("sha256:"):
            exact_blockers.append("missing_content_hash")
    quality_state = "QUALITY_READY" if not exact_blockers else "QUALITY_BLOCKED"
    return {
        "campaign_cell_id": diagnosis["campaign_cell_id"],
        "generated_strategy_id": diagnosis["generated_strategy_id"],
        "quality_state": quality_state,
        "usable_range_decision": "authoritative_common_range",
        "coverage_map": [
            {
                "instrument": str(row.get("instrument") or ""),
                "timeframe": str(row.get("timeframe") or ""),
                "start": str(row.get("min_timestamp_utc") or ""),
                "end": str(row.get("max_timestamp_utc") or ""),
                "source": str(row.get("source") or ""),
            }
            for row in coverage_rows
        ],
        "gap_map": [],
        "exact_blockers": exact_blockers,
        "quality_identity": _content_id("qdq", {"cell": diagnosis["campaign_cell_id"], "rows": coverage_rows}),
    }


def _snapshot_row(cell: dict[str, Any], diagnosis: dict[str, Any], quality: dict[str, Any]) -> dict[str, Any]:
    if diagnosis["status"] != "DATA_CAPACITY_READY" or quality["quality_state"] != "QUALITY_READY":
        return {
            "campaign_cell_id": str(cell.get("campaign_cell_id") or ""),
            "generated_strategy_id": str(cell.get("generated_strategy_id") or ""),
            "snapshot_state": "SNAPSHOT_BLOCKED",
            "reason": "data_capacity_or_quality_not_ready",
            "snapshot_identity": "",
        }
    coverage_rows = list(diagnosis.get("coverage_rows") or [])
    snapshot_core = {
        "source": diagnosis["authoritative_value"]["source_identity"],
        "timeframe": str(cell.get("timeframe") or ""),
        "universe": str(cell.get("universe_identity") or ""),
        "membership_snapshot_id": str(cell.get("membership_snapshot_id") or ""),
        "coverage_hashes": sorted(str(row.get("content_hash") or "") for row in coverage_rows),
        "range": {
            "start": diagnosis["authoritative_value"]["earliest_timestamp_utc"],
            "end": diagnosis["authoritative_value"]["latest_timestamp_utc"],
        },
        "version": SNAPSHOT_VERSION,
    }
    return {
        "campaign_cell_id": str(cell.get("campaign_cell_id") or ""),
        "generated_strategy_id": str(cell.get("generated_strategy_id") or ""),
        "snapshot_state": "SNAPSHOT_READY",
        "snapshot_identity": _content_id("qsn", snapshot_core),
        "dataset_identity": _content_id("qds", snapshot_core),
        "source_identity": diagnosis["authoritative_value"]["source_identity"],
        "row_count": len(coverage_rows),
        "content_hashes": sorted(str(row.get("content_hash") or "") for row in coverage_rows),
        "coverage_start_utc": diagnosis["authoritative_value"]["earliest_timestamp_utc"],
        "coverage_end_utc": diagnosis["authoritative_value"]["latest_timestamp_utc"],
        "snapshot_core": snapshot_core,
    }


def _assign_windows(cell: dict[str, Any], snapshot: dict[str, Any], ledger_rows: list[dict[str, Any]]) -> tuple[dict[str, Any], list[dict[str, Any]], dict[str, Any]]:
    timeframe = str(cell.get("timeframe") or "")
    policy = _window_policy_for_timeframe(timeframe)
    policy_identity = _content_id(
        "qwp",
        {
            "timeframe": timeframe,
            "policy": policy,
            "version": WINDOW_POLICY_VERSION,
        },
    )
    if snapshot.get("snapshot_state") != "SNAPSHOT_READY":
        return (
            {
                "campaign_cell_id": str(cell.get("campaign_cell_id") or ""),
                "generated_strategy_id": str(cell.get("generated_strategy_id") or ""),
                "window_policy_identity": policy_identity,
                "window_policy_outcome": "POLICY_INPUT_INCOMPLETE",
                "reason": "snapshot_not_ready",
            },
            [],
            {"outcome": "INSUFFICIENT_EVIDENCE_TO_PROVE_INDEPENDENCE", "reason": "windows_not_assigned"},
        )
    start = _iso_to_dt(str(snapshot.get("coverage_start_utc") or ""))
    end = _iso_to_dt(str(snapshot.get("coverage_end_utc") or ""))
    required_span = timedelta(
        days=policy["min_train_days"] + policy["min_validation_days"] + policy["min_oos_days"] + policy["embargo_days"] * 2
    )
    if (end - start) < required_span:
        return (
            {
                "campaign_cell_id": str(cell.get("campaign_cell_id") or ""),
                "generated_strategy_id": str(cell.get("generated_strategy_id") or ""),
                "window_policy_identity": policy_identity,
                "window_policy_outcome": "INSUFFICIENT_USABLE_HISTORY",
                "reason": "usable_history_below_minimum_policy_span",
                "usable_span_days": (end - start).days,
                "required_span_days": required_span.days,
            },
            [],
            {"outcome": "INSUFFICIENT_EVIDENCE_TO_PROVE_INDEPENDENCE", "reason": "usable_history_below_minimum_policy_span"},
        )
    oos_end = end
    oos_start = oos_end - timedelta(days=policy["min_oos_days"])
    validation_end = oos_start - timedelta(days=policy["embargo_days"])
    validation_start = validation_end - timedelta(days=policy["min_validation_days"])
    train_end = validation_start - timedelta(days=policy["embargo_days"])
    train_start = start
    windows = {
        "train_window": {"start": _dt_to_iso(train_start), "end": _dt_to_iso(train_end)},
        "validation_window": {"start": _dt_to_iso(validation_start), "end": _dt_to_iso(validation_end)},
        "oos_window": {"start": _dt_to_iso(oos_start), "end": _dt_to_iso(oos_end)},
        "embargo_days": policy["embargo_days"],
    }
    overlap = next(
        (
            row
            for row in ledger_rows
            if str(row.get("purpose") or "") == "OOS"
            and str(row.get("status") or "") in {"RESERVED", "CONSUMED"}
            and str(row.get("snapshot_identity") or "") == str(snapshot.get("snapshot_identity") or "")
            and str(row.get("timeframe") or "") == timeframe
            and row.get("window") == windows["oos_window"]
        ),
        None,
    )
    if overlap:
        return (
            {
                "campaign_cell_id": str(cell.get("campaign_cell_id") or ""),
                "generated_strategy_id": str(cell.get("generated_strategy_id") or ""),
                "window_policy_identity": policy_identity,
                "window_policy_outcome": "NO_INDEPENDENT_OOS_AVAILABLE",
                "reason": "oos_window_already_reserved_or_consumed",
                **windows,
            },
            [],
            {"outcome": "WINDOW_PREVIOUSLY_CONSUMED", "reason": "matching_oos_window_already_reserved_or_consumed"},
        )
    reservations = []
    for purpose, window in (("TRAIN", windows["train_window"]), ("VALIDATION", windows["validation_window"]), ("OOS", windows["oos_window"])):
        reservation_core = {
            "snapshot_identity": str(snapshot.get("snapshot_identity") or ""),
            "timeframe": timeframe,
            "campaign_cell_id": str(cell.get("campaign_cell_id") or ""),
            "purpose": purpose,
            "window": window,
            "version": WINDOW_LEDGER_VERSION,
        }
        reservations.append(
            {
                "window_id": _content_id("qwl", reservation_core),
                "snapshot_identity": str(snapshot.get("snapshot_identity") or ""),
                "dataset_identity": str(snapshot.get("dataset_identity") or ""),
                "generated_strategy_id": str(cell.get("generated_strategy_id") or ""),
                "campaign_cell_id": str(cell.get("campaign_cell_id") or ""),
                "timeframe": timeframe,
                "purpose": purpose,
                "status": "RESERVED",
                "window": window,
                "independence_group": _content_id("qig", {"snapshot": snapshot.get("snapshot_identity"), "timeframe": timeframe}),
                "provenance": [
                    "generated_research/readiness/snapshots/immutable_strategy_snapshots.v1.json",
                    "generated_research/readiness/window_capacity/authoritative_window_policy.v1.json",
                ],
            }
        )
    return (
        {
            "campaign_cell_id": str(cell.get("campaign_cell_id") or ""),
            "generated_strategy_id": str(cell.get("generated_strategy_id") or ""),
            "window_policy_identity": policy_identity,
            "window_policy_outcome": "WINDOW_POLICY_READY",
            "reason": "",
            **windows,
            "minimum_train_days": policy["min_train_days"],
            "minimum_validation_days": policy["min_validation_days"],
            "minimum_oos_days": policy["min_oos_days"],
        },
        reservations,
        {"outcome": "INDEPENDENCE_PROVEN", "reason": "window_not_previously_reserved_or_consumed_for_matching_snapshot_scope"},
    )


def _validate_point_in_time_universe(cell: dict[str, Any], diagnosis: dict[str, Any], spec: dict[str, Any]) -> dict[str, Any]:
    universe_row = dict(cell.get("universe_row") or {})
    included = list(universe_row.get("included_members") or [])
    minimum_size = int(spec.get("parameters", {}).get("minimum_universe_size") or 1)
    if str(cell.get("source_hypothesis_id") or "") == "cross_sectional_momentum_v0":
        if not universe_row.get("effective_from_utc") or not universe_row.get("effective_to_utc"):
            return {
                "campaign_cell_id": str(cell.get("campaign_cell_id") or ""),
                "generated_strategy_id": str(cell.get("generated_strategy_id") or ""),
                "outcome": "POINT_IN_TIME_UNIVERSE_BLOCKED",
                "reason": "effective_membership_dates_missing",
            }
        if len(included) < minimum_size:
            return {
                "campaign_cell_id": str(cell.get("campaign_cell_id") or ""),
                "generated_strategy_id": str(cell.get("generated_strategy_id") or ""),
                "outcome": "POINT_IN_TIME_UNIVERSE_BLOCKED",
                "reason": "minimum_cross_sectional_breadth_not_met",
            }
    elif not included:
        return {
            "campaign_cell_id": str(cell.get("campaign_cell_id") or ""),
            "generated_strategy_id": str(cell.get("generated_strategy_id") or ""),
            "outcome": "POINT_IN_TIME_UNIVERSE_BLOCKED",
            "reason": "single_instrument_membership_missing",
        }
    return {
        "campaign_cell_id": str(cell.get("campaign_cell_id") or ""),
        "generated_strategy_id": str(cell.get("generated_strategy_id") or ""),
        "outcome": "POINT_IN_TIME_UNIVERSE_READY",
        "reason": "",
        "included_member_count": len(included),
        "minimum_required": minimum_size,
    }


def _estimate_signal_capacity(cell: dict[str, Any], diagnosis: dict[str, Any], spec: dict[str, Any], windows: dict[str, Any]) -> dict[str, Any]:
    if diagnosis["status"] != "DATA_CAPACITY_READY" or windows.get("window_policy_outcome") != "WINDOW_POLICY_READY":
        return {
            "campaign_cell_id": str(cell.get("campaign_cell_id") or ""),
            "generated_strategy_id": str(cell.get("generated_strategy_id") or ""),
            "outcome": "INSUFFICIENT_EVIDENCE_TO_ESTIMATE",
            "reason": "data_or_windows_not_ready",
        }
    timeframe = str(cell.get("timeframe") or "")
    coverage_rows = list(diagnosis.get("coverage_rows") or [])
    coverage_row = next(iter(coverage_rows))
    instrument_count = max(len(coverage_rows), 1)
    row_count = int(coverage_row.get("row_count") or 0)
    span_days = (_iso_to_dt(diagnosis["authoritative_value"]["latest_timestamp_utc"]) - _iso_to_dt(diagnosis["authoritative_value"]["earliest_timestamp_utc"])).days
    timeframe_divisor = {"1h": 24, "4h": 6, "1d": 1}.get(timeframe, 1)
    estimated_bars = min(max(span_days * timeframe_divisor, 0), row_count if row_count else span_days * timeframe_divisor)
    warmup = max([int(value) for value in dict(spec.get("warmup_requirements") or {}).values() if isinstance(value, int)] or [0])
    usable_bars = max(estimated_bars - warmup, 0)
    breadth_adjusted_bars = usable_bars * instrument_count if instrument_count > 1 else usable_bars
    expected_signals = max(0, breadth_adjusted_bars // 80)
    expected_trades = max(0, breadth_adjusted_bars // (80 if instrument_count > 1 else 100))
    policy = _window_policy_for_timeframe(timeframe)
    if expected_signals < policy["min_expected_signals"]:
        return {
            "campaign_cell_id": str(cell.get("campaign_cell_id") or ""),
            "generated_strategy_id": str(cell.get("generated_strategy_id") or ""),
            "outcome": "EXPECTED_SIGNALS_INSUFFICIENT",
            "reason": "estimated_signals_below_policy_minimum",
            "estimated_signals": expected_signals,
            "estimated_trades": expected_trades,
        }
    if expected_trades < policy["min_expected_trades"]:
        return {
            "campaign_cell_id": str(cell.get("campaign_cell_id") or ""),
            "generated_strategy_id": str(cell.get("generated_strategy_id") or ""),
            "outcome": "EXPECTED_TRADES_INSUFFICIENT",
            "reason": "estimated_trades_below_policy_minimum",
            "estimated_signals": expected_signals,
            "estimated_trades": expected_trades,
        }
    outcome = "SIGNAL_CAPACITY_READY_WITH_LIMITATIONS" if timeframe == "1d" else "SIGNAL_CAPACITY_READY"
    return {
        "campaign_cell_id": str(cell.get("campaign_cell_id") or ""),
        "generated_strategy_id": str(cell.get("generated_strategy_id") or ""),
        "outcome": outcome,
        "reason": "",
        "estimated_signals": expected_signals,
        "estimated_trades": expected_trades,
        "estimated_usable_bars": usable_bars,
        "breadth_adjusted_usable_bars": breadth_adjusted_bars,
        "instrument_count": instrument_count,
    }


def _null_control_ready(cell: dict[str, Any], windows: dict[str, Any]) -> tuple[str, list[str]]:
    rows = list(cell.get("null_rows") or [])
    if not rows:
        return "BLOCKED_NULL_CONTROLS", ["null_control_rows_missing"]
    blockers = [str(row.get("blocker") or "") for row in rows if str(row.get("outcome") or "").endswith("BLOCKED")]
    if windows.get("window_policy_outcome") == "WINDOW_POLICY_READY":
        blockers = []
    return ("BLOCKED_NULL_CONTROLS", sorted({value for value in blockers if value})) if blockers else ("READY", [])


def _portfolio_row(
    *,
    cell: dict[str, Any],
    diagnosis: dict[str, Any],
    snapshot: dict[str, Any],
    windows: dict[str, Any],
    independence: dict[str, Any],
    pit: dict[str, Any],
    signal: dict[str, Any],
) -> dict[str, Any]:
    status = "READY_FOR_PREREGISTRATION"
    blockers: list[str] = []
    if diagnosis["status"] != "DATA_CAPACITY_READY":
        status = "BLOCKED_DATA"
        blockers.append(str(diagnosis["status"]).lower())
    elif snapshot.get("snapshot_state") != "SNAPSHOT_READY":
        status = "BLOCKED_DATA"
        blockers.append("snapshot_not_ready")
    elif windows.get("window_policy_outcome") != "WINDOW_POLICY_READY":
        status = "BLOCKED_WINDOWS"
        blockers.append(str(windows.get("reason") or windows.get("window_policy_outcome") or "window_policy_not_ready").lower())
    elif independence.get("outcome") not in {"INDEPENDENCE_PROVEN", "INDEPENDENCE_PROVEN_WITH_LIMITATIONS"}:
        status = "BLOCKED_WINDOWS"
        blockers.append(str(independence.get("reason") or independence.get("outcome") or "independence_not_proven").lower())
    elif pit.get("outcome") != "POINT_IN_TIME_UNIVERSE_READY":
        status = "BLOCKED_IDENTITY"
        blockers.append(str(pit.get("reason") or "point_in_time_universe_blocked").lower())
    elif signal.get("outcome") not in {"SIGNAL_CAPACITY_READY", "SIGNAL_CAPACITY_READY_WITH_LIMITATIONS"}:
        status = "BLOCKED_SIGNAL_DENSITY"
        blockers.append(str(signal.get("reason") or signal.get("outcome") or "signal_capacity_blocked").lower())
    else:
        null_status, null_blockers = _null_control_ready(cell, windows)
        if null_status != "READY":
            status = "BLOCKED_NULL_CONTROLS"
            blockers.extend(null_blockers or ["null_control_execution_not_ready"])
    manifest_ready = status == "READY_FOR_PREREGISTRATION"
    return {
        "campaign_cell_id": str(cell.get("campaign_cell_id") or ""),
        "generated_strategy_id": str(cell.get("generated_strategy_id") or ""),
        "timeframe": str(cell.get("timeframe") or ""),
        "status": status,
        "blockers": blockers,
        "strategy_spec_id": str(cell.get("registry_row", {}).get("strategy_spec_id") or ""),
        "preset_id": str(cell.get("preset_id") or cell.get("preset_row", {}).get("preset_id") or ""),
        "dataset_identity": str(snapshot.get("dataset_identity") or ""),
        "snapshot_identity": str(snapshot.get("snapshot_identity") or ""),
        "manifest_ready": manifest_ready,
        "train_window": dict(windows.get("train_window") or {}),
        "validation_window": dict(windows.get("validation_window") or {}),
        "oos_window": dict(windows.get("oos_window") or {}),
        "portfolio_readiness_identity": _content_id(
            "qrp",
            {
                "campaign_cell_id": str(cell.get("campaign_cell_id") or ""),
                "status": status,
                "snapshot_identity": str(snapshot.get("snapshot_identity") or ""),
                "timeframe": str(cell.get("timeframe") or ""),
            },
        ),
        "next_action": (
            "create_second_campaign_preregistration_manifest"
            if manifest_ready
            else "preserve_fail_closed_data_window_capacity_blockers"
        ),
    }


def _manifest_payload(rows: list[dict[str, Any]]) -> dict[str, Any]:
    manifest_rows = [
        {
            "campaign_cell_id": row["campaign_cell_id"],
            "generated_strategy_id": row["generated_strategy_id"],
            "strategy_spec_id": row["strategy_spec_id"],
            "preset_id": row["preset_id"],
            "dataset_identity": row["dataset_identity"],
            "snapshot_identity": row["snapshot_identity"],
            "timeframe": row["timeframe"],
            "train_window": row["train_window"],
            "validation_window": row["validation_window"],
            "oos_window": row["oos_window"],
        }
        for row in rows
        if row["status"] == "READY_FOR_PREREGISTRATION"
    ]
    manifest_identity = _content_id("qcm", {"rows": manifest_rows, "version": MODULE_VERSION})
    return {
        "campaign_manifest_identity": manifest_identity,
        "schema_version": SCHEMA_VERSION,
        "module_version": MODULE_VERSION,
        "report_kind": "qre_generated_second_campaign_manifest",
        "rows": manifest_rows,
    }


def _closeout_markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# ADE-QRE-024 Automated Data Capacity and Window Assignment",
        "",
        f"- outcome: `{payload['overall_outcome']}`",
        f"- campaign cells processed: `{payload['summary']['campaign_cells_processed']}`",
        f"- ready-for-preregistration: `{payload['summary']['ready_for_preregistration_count']}`",
        f"- loop iterations: `{payload['summary']['loop_iterations']}`",
        f"- exact next action: `{payload['exact_next_action']}`",
        "",
        "## Final Cell Status",
    ]
    for row in payload["portfolio_rows"]:
        lines.append(
            f"- `{row['campaign_cell_id']}` / `{row['generated_strategy_id']}` / `{row['timeframe']}`: "
            f"`{row['status']}`"
            + (f" -> `{row['blockers'][0]}`" if row["blockers"] else "")
        )
    return "\n".join(lines) + "\n"


def run_data_window_closure(
    *,
    repo_root: Path = REPO_ROOT,
    max_iterations: int = 8,
    write_outputs: bool = True,
) -> dict[str, Any]:
    acr.run_readiness_remediation(repo_root=repo_root)
    arc.run_autonomous_closure(repo_root=repo_root, max_iterations=8)

    coverage_rows = _load_coverage_rows(repo_root)
    cells = _load_a23_cells(repo_root)
    existing_manifest = _load_existing_manifest(repo_root)

    diagnosis_rows: list[dict[str, Any]] = []
    authority_rows: list[dict[str, Any]] = []
    materialized_rows: list[dict[str, Any]] = []
    quality_rows: list[dict[str, Any]] = []
    snapshot_rows: list[dict[str, Any]] = []
    policy_rows: list[dict[str, Any]] = []
    ledger_rows: list[dict[str, Any]] = []
    assignment_rows: list[dict[str, Any]] = []
    independence_rows: list[dict[str, Any]] = []
    pit_rows: list[dict[str, Any]] = []
    signal_rows: list[dict[str, Any]] = []
    portfolio_rows: list[dict[str, Any]] = []
    iteration_rows: list[dict[str, Any]] = []

    current_blockers = [str(row.get("primary_blocker") or "") for row in cells]
    for iteration, cell in enumerate(cells, start=1):
        before = list(current_blockers)
        diagnosis, materialized = _diagnose_data_capacity(repo_root=repo_root, cell=cell, coverage_rows=coverage_rows)
        if materialized:
            materialized_rows.append(materialized)
        diagnosis_rows.append(diagnosis)
        authority_rows.append(
            {
                "campaign_cell_id": str(cell.get("campaign_cell_id") or ""),
                "generated_strategy_id": str(cell.get("generated_strategy_id") or ""),
                "timeframe": str(cell.get("timeframe") or ""),
                "resolver_identity": _content_id("qdr", {"cell": cell.get("campaign_cell_id"), "version": DATA_RESOLVER_VERSION}),
                "source_identity": (
                    diagnosis.get("authoritative_value", {}).get("source_identity", "")
                    if diagnosis["status"] == "DATA_CAPACITY_READY"
                    else ""
                ),
                "dataset_identity": str(cell.get("data_binding", {}).get("dataset_identity") or ""),
                "provenance": diagnosis["provenance"],
            }
        )
        quality = _quality_row(cell, diagnosis)
        quality_rows.append(quality)
        snapshot = _snapshot_row(cell, diagnosis, quality)
        snapshot_rows.append(snapshot)
        spec = dict(cell.get("spec") or {})
        windows, reservations, independence = _assign_windows(cell, snapshot, ledger_rows)
        policy_rows.append(
            {
                "campaign_cell_id": str(cell.get("campaign_cell_id") or ""),
                "generated_strategy_id": str(cell.get("generated_strategy_id") or ""),
                "timeframe": str(cell.get("timeframe") or ""),
                "window_policy_identity": str(windows.get("window_policy_identity") or ""),
                "outcome": str(windows.get("window_policy_outcome") or ""),
                "reason": str(windows.get("reason") or ""),
                "version": WINDOW_POLICY_VERSION,
            }
        )
        ledger_rows.extend(reservations)
        assignment_rows.append(windows)
        independence_rows.append(
            {
                "campaign_cell_id": str(cell.get("campaign_cell_id") or ""),
                "generated_strategy_id": str(cell.get("generated_strategy_id") or ""),
                "snapshot_identity": str(snapshot.get("snapshot_identity") or ""),
                "timeframe": str(cell.get("timeframe") or ""),
                **independence,
            }
        )
        pit = _validate_point_in_time_universe(cell, diagnosis, spec)
        pit_rows.append(pit)
        signal = _estimate_signal_capacity(cell, diagnosis, spec, windows)
        signal_rows.append(signal)
        portfolio = _portfolio_row(
            cell=cell,
            diagnosis=diagnosis,
            snapshot=snapshot,
            windows=windows,
            independence=independence,
            pit=pit,
            signal=signal,
        )
        portfolio_rows.append(portfolio)
        if portfolio["status"] == "READY_FOR_PREREGISTRATION":
            progress = "RESOLVED_BLOCKER"
            next_action = "create_second_campaign_preregistration_manifest"
        elif diagnosis["status"] == "CACHE_ROW_MISSING":
            progress = "IRREDUCIBLE_BLOCKER_PROVEN"
            next_action = "preserve_fail_closed_missing_cache_row"
        elif windows.get("window_policy_outcome") == "INSUFFICIENT_USABLE_HISTORY":
            progress = "DOWNSTREAM_BLOCKER_EXPOSED"
            next_action = "preserve_fail_closed_insufficient_usable_history"
        else:
            progress = "DOWNSTREAM_BLOCKER_EXPOSED" if portfolio["blockers"] else "NO_PROGRESS"
            next_action = portfolio["next_action"]
        iteration_rows.append(
            {
                "iteration": iteration,
                "campaign_cell_id": str(cell.get("campaign_cell_id") or ""),
                "generated_strategy_id": str(cell.get("generated_strategy_id") or ""),
                "before_blockers": before,
                "selected_blocker": (portfolio["blockers"][0] if portfolio["blockers"] else ""),
                "remediation": diagnosis["next_action"],
                "artifacts_created": [
                    "generated_research/readiness/data_capacity/strategy_data_capacity_diagnosis.v1.json",
                    "generated_research/readiness/snapshots/immutable_strategy_snapshots.v1.json",
                    "generated_research/readiness/window_ledger/canonical_window_ledger.v1.json",
                ],
                "after_blockers": portfolio["blockers"],
                "progress_classification": progress,
                "next_action": next_action,
            }
        )
        current_blockers = portfolio["blockers"]

    policy_identity = _content_id("qwp", {"rows": policy_rows, "version": WINDOW_POLICY_VERSION})
    ledger_identity = _content_id("qwlr", {"rows": ledger_rows, "version": WINDOW_LEDGER_VERSION})
    ready_rows = [row for row in portfolio_rows if row["status"] == "READY_FOR_PREREGISTRATION"]

    _maybe_write_json(
        DATA_DIAGNOSIS_PATH,
        {
            "schema_version": SCHEMA_VERSION,
            "module_version": MODULE_VERSION,
            "report_kind": "qre_strategy_data_capacity_diagnosis",
            "rows": diagnosis_rows,
        },
        write_outputs=write_outputs,
    )
    _maybe_write_json(
        DATA_AUTHORITY_PATH,
        {
            "schema_version": SCHEMA_VERSION,
            "module_version": MODULE_VERSION,
            "report_kind": "qre_canonical_data_cache_authority",
            "rows": authority_rows,
        },
        write_outputs=write_outputs,
    )
    _maybe_write_json(
        MATERIALIZED_CACHE_ROWS_PATH,
        {
            "schema_version": SCHEMA_VERSION,
            "module_version": MODULE_VERSION,
            "report_kind": "qre_materialized_cache_rows",
            "rows": materialized_rows,
        },
        write_outputs=write_outputs,
    )
    _maybe_write_json(
        QUALITY_PATH,
        {
            "schema_version": SCHEMA_VERSION,
            "module_version": MODULE_VERSION,
            "report_kind": "qre_strategy_data_quality_coverage",
            "rows": quality_rows,
        },
        write_outputs=write_outputs,
    )
    _maybe_write_json(
        SNAPSHOTS_PATH,
        {
            "schema_version": SCHEMA_VERSION,
            "module_version": MODULE_VERSION,
            "report_kind": "qre_immutable_strategy_snapshots",
            "rows": snapshot_rows,
        },
        write_outputs=write_outputs,
    )
    _maybe_write_json(
        WINDOW_POLICY_PATH,
        {
            "schema_version": SCHEMA_VERSION,
            "module_version": MODULE_VERSION,
            "report_kind": "qre_authoritative_window_policy",
            "window_policy_identity": policy_identity,
            "rows": policy_rows,
        },
        write_outputs=write_outputs,
    )
    _maybe_write_json(
        WINDOW_LEDGER_PATH,
        {
            "schema_version": SCHEMA_VERSION,
            "module_version": MODULE_VERSION,
            "report_kind": "qre_canonical_window_ledger",
            "window_ledger_identity": ledger_identity,
            "rows": ledger_rows,
        },
        write_outputs=write_outputs,
    )
    _maybe_write_json(
        WINDOW_ASSIGNMENTS_PATH,
        {
            "schema_version": SCHEMA_VERSION,
            "module_version": MODULE_VERSION,
            "report_kind": "qre_authoritative_window_assignments",
            "rows": assignment_rows,
        },
        write_outputs=write_outputs,
    )
    _maybe_write_json(
        INDEPENDENCE_PATH,
        {
            "schema_version": SCHEMA_VERSION,
            "module_version": MODULE_VERSION,
            "report_kind": "qre_oos_independence_proof",
            "rows": independence_rows,
        },
        write_outputs=write_outputs,
    )
    _maybe_write_json(
        PIT_UNIVERSE_PATH,
        {
            "schema_version": SCHEMA_VERSION,
            "module_version": MODULE_VERSION,
            "report_kind": "qre_point_in_time_universe_validation",
            "rows": pit_rows,
        },
        write_outputs=write_outputs,
    )
    _maybe_write_json(
        SIGNAL_CAPACITY_PATH,
        {
            "schema_version": SCHEMA_VERSION,
            "module_version": MODULE_VERSION,
            "report_kind": "qre_signal_density_capacity",
            "rows": signal_rows,
        },
        write_outputs=write_outputs,
    )
    _maybe_write_json(
        PORTFOLIO_PATH,
        {
            "schema_version": SCHEMA_VERSION,
            "module_version": MODULE_VERSION,
            "report_kind": "qre_automated_portfolio_readiness",
            "rows": portfolio_rows,
        },
        write_outputs=write_outputs,
    )
    _maybe_write_json(
        ITERATION_LEDGER_PATH,
        {
            "schema_version": SCHEMA_VERSION,
            "module_version": MODULE_VERSION,
            "report_kind": "qre_automated_data_window_iteration_ledger",
            "iteration_ledger_identity": _content_id("qit", iteration_rows),
            "rows": iteration_rows,
        },
        write_outputs=write_outputs,
    )

    manifest_payload: dict[str, Any] = {}
    if ready_rows:
        manifest_payload = _manifest_payload(ready_rows)
        _maybe_write_json(MANIFEST_PATH, manifest_payload, write_outputs=write_outputs)
        overall_outcome = "READY_FOR_SECOND_CAMPAIGN"
        exact_next_action = "execute_second_preregistered_campaign"
    elif any(row["status"] == "BLOCKED_DATA" for row in portfolio_rows):
        overall_outcome = "PARTIAL_DATA_AND_WINDOW_CLOSURE"
        exact_next_action = "preserve_fail_closed_data_gaps_and_window_blockers"
    else:
        overall_outcome = "INDEPENDENT_OOS_CAPACITY_BLOCKED"
        exact_next_action = "preserve_fail_closed_window_capacity_blockers"

    closeout = {
        "schema_version": SCHEMA_VERSION,
        "module_version": MODULE_VERSION,
        "report_kind": REPORT_KIND,
        "data_capacity_closeout_id": _content_id("qrdc", {"portfolio": portfolio_rows, "manifest": manifest_payload}),
        "overall_outcome": overall_outcome,
        "summary": {
            "campaign_cells_processed": len(portfolio_rows),
            "loop_iterations": len(iteration_rows),
            "ready_for_preregistration_count": len(ready_rows),
            "materialized_cache_rows": len(materialized_rows),
            "existing_manifest_present": bool(existing_manifest),
        },
        "initial_blockers": [str(row.get("blockers", [""])[0]) for row in _load_a23_cells(repo_root)],
        "portfolio_rows": portfolio_rows,
        "manifest": manifest_payload,
        "remaining_blockers": sorted({blocker for row in portfolio_rows for blocker in row["blockers"]}),
        "exact_next_action": exact_next_action,
        "window_policy_identity": policy_identity,
        "window_ledger_identity": ledger_identity,
    }
    _maybe_write_json(CLOSEOUT_JSON_PATH, closeout, write_outputs=write_outputs)
    _maybe_write_text(CLOSEOUT_MD_PATH, _closeout_markdown(closeout), write_outputs=write_outputs)
    return closeout


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="ADE-QRE-024 automated data capacity and authoritative window assignment")
    parser.add_argument("--repo-root", type=Path, default=REPO_ROOT)
    parser.add_argument("--max-iterations", type=int, default=8)
    parser.add_argument("--indent", type=int, default=2)
    parser.add_argument("--no-write", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    payload = run_data_window_closure(
        repo_root=args.repo_root,
        max_iterations=args.max_iterations,
        write_outputs=not args.no_write,
    )
    print(json.dumps(payload, indent=args.indent, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
