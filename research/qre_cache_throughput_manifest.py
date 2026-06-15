"""Read-only cache throughput manifest and policy report.

This module consumes the existing local cache manifest sidecar only. It does
not fetch data, mutate caches, activate execution paths, or lower source
quality gates. DuckDB and Polars are treated as availability signals for a
read-only local throughput policy, not as authority.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
import sys
from collections import Counter
from collections.abc import Mapping, Sequence
from importlib.util import find_spec
from pathlib import Path
from typing import Any, Final

SCHEMA_VERSION: Final[str] = "1.0"
REPORT_KIND: Final[str] = "qre_cache_throughput_manifest"
DEFAULT_OUTPUT_DIR: Final[Path] = Path("logs/qre_cache_throughput_manifest")
DEFAULT_CACHE_MANIFEST_PATH: Final[Path] = Path("logs/qre_data_cache_manifest/latest.json")
LATEST_NAME: Final[str] = "latest.json"
HISTORY_NAME: Final[str] = "history.jsonl"
SUMMARY_NAME: Final[str] = "operator_summary.md"
_WRITE_PREFIX: Final[str] = "logs/qre_cache_throughput_manifest/"


def _utcnow() -> str:
    return _dt.datetime.now(_dt.UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _rel(path: Path, *, root: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return path.as_posix()


def _read_json(path: Path) -> dict[str, Any] | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _manifest_files(payload: Mapping[str, Any] | None) -> list[dict[str, Any]]:
    files = payload.get("files") if isinstance(payload, Mapping) else None
    if not isinstance(files, list):
        return []
    return [row for row in files if isinstance(row, dict)]


def _manifest_coverage(payload: Mapping[str, Any] | None) -> list[dict[str, Any]]:
    coverage = payload.get("coverage") if isinstance(payload, Mapping) else None
    if not isinstance(coverage, list):
        return []
    return [row for row in coverage if isinstance(row, dict)]


def _module_available(module_name: str) -> bool:
    return find_spec(module_name) is not None


def _availability(flag: str | None, module_name: str) -> bool:
    if flag is None or flag == "auto":
        return _module_available(module_name)
    return flag == "true"


def _blocker(
    *,
    reason: str,
    evidence_field: str,
    evidence_status: str,
    operator_explanation: str,
) -> dict[str, Any]:
    return {
        "reason": reason,
        "evidence_field": evidence_field,
        "evidence_status": evidence_status,
        "fail_closed": True,
        "operator_explanation": operator_explanation,
    }


def _throughput_blockers(
    *,
    manifest_ready: bool,
    snapshot_ready: bool,
    duckdb_available: bool,
    polars_available: bool,
) -> list[dict[str, Any]]:
    blockers: list[dict[str, Any]] = []
    if not manifest_ready:
        blockers.append(
            _blocker(
                reason="cache_manifest_not_research_ready",
                evidence_field="cache_manifest.summary.research_ready",
                evidence_status="false_or_missing",
                operator_explanation=(
                    "The cache manifest is not research-ready, so throughput "
                    "manifest evaluation fails closed."
                ),
            )
        )
    if not snapshot_ready:
        blockers.append(
            _blocker(
                reason="parquet_snapshot_contract_not_ready",
                evidence_field="snapshot_contract.ready",
                evidence_status="false",
                operator_explanation=(
                    "The parquet snapshot contract is not ready, so throughput "
                    "manifest evaluation fails closed."
                ),
            )
        )
    if not duckdb_available:
        blockers.append(
            _blocker(
                reason="duckdb_module_unavailable",
                evidence_field="duckdb_catalog_manifest.module_available",
                evidence_status="false",
                operator_explanation=(
                    "DuckDB is unavailable in this environment; catalog-manifest "
                    "reporting stays read-only and fail-closed."
                ),
            )
        )
    if not polars_available:
        blockers.append(
            _blocker(
                reason="polars_module_unavailable",
                evidence_field="polars_use_policy.module_available",
                evidence_status="false",
                operator_explanation=(
                    "Polars is unavailable in this environment; read-only local "
                    "scan policy stays fail-closed."
                ),
            )
        )
    return sorted(blockers, key=lambda row: row["reason"])


def _snapshot_contract(
    *,
    manifest_path: Path,
    repo_root: Path,
    manifest: Mapping[str, Any] | None,
    manifest_ready: bool,
    snapshot_ready: bool,
) -> dict[str, Any]:
    files = _manifest_files(manifest)
    coverage = _manifest_coverage(manifest)
    parquet_only = bool(files) and all(str(row.get("path") or "").endswith(".parquet") for row in files)
    total_rows = int((manifest.get("summary") or {}).get("total_rows") or 0) if isinstance(manifest, Mapping) else 0
    manifest_content_hash = (
        str((manifest.get("summary") or {}).get("manifest_content_hash") or "")
        if isinstance(manifest, Mapping)
        else ""
    )
    blockers = []
    if not parquet_only:
        blockers.append("non_parquet_cache_files")
    if not manifest_content_hash:
        blockers.append("missing_manifest_content_hash")
    if not manifest_ready:
        blockers.append("cache_manifest_not_research_ready")
    if not snapshot_ready:
        blockers.append("snapshot_contract_not_ready")
    return {
        "contract_kind": "parquet_snapshot_contract",
        "path": _rel(manifest_path, root=repo_root),
        "file_format": "parquet",
        "cache_file_count": len(files),
        "coverage_row_count": len(coverage),
        "total_rows": total_rows,
        "manifest_content_hash": manifest_content_hash or None,
        "parquet_only": parquet_only,
        "ready": snapshot_ready,
        "blockers": blockers,
        "operator_explanation": (
            "The cache manifest describes a deterministic parquet snapshot contract "
            "for local read-only throughput analysis only."
        ),
    }


def _catalog_manifest(
    *,
    snapshot_ready: bool,
    duckdb_available: bool,
) -> dict[str, Any]:
    ready = bool(snapshot_ready and duckdb_available)
    blockers = []
    if not snapshot_ready:
        blockers.append("snapshot_contract_not_ready")
    if not duckdb_available:
        blockers.append("duckdb_module_unavailable")
    return {
        "catalog_kind": "duckdb_read_only_catalog_manifest",
        "module_name": "duckdb",
        "module_available": duckdb_available,
        "ready": ready,
        "blockers": blockers,
        "operator_explanation": (
            "DuckDB is treated as a read-only catalog-manifest capability only; "
            "it does not change cache authority, source quality, or execution."
        ),
    }


def _polars_policy(
    *,
    snapshot_ready: bool,
    polars_available: bool,
) -> dict[str, Any]:
    ready = bool(snapshot_ready and polars_available)
    blockers = []
    if not snapshot_ready:
        blockers.append("snapshot_contract_not_ready")
    if not polars_available:
        blockers.append("polars_module_unavailable")
    return {
        "policy_kind": "polars_read_only_local_scan_policy",
        "module_name": "polars",
        "module_available": polars_available,
        "allowed_for_local_read_only_scans": ready,
        "forbidden_for_authority": True,
        "ready": ready,
        "blockers": blockers,
        "operator_explanation": (
            "Polars may only be used as a local read-only scan policy signal; "
            "it never becomes authority for trading or source promotion."
        ),
    }


def build_cache_throughput_manifest(
    *,
    repo_root: Path = Path("."),
    cache_manifest_path: Path = DEFAULT_CACHE_MANIFEST_PATH,
    generated_at_utc: str | None = None,
    duckdb_available: bool | None = None,
    polars_available: bool | None = None,
) -> dict[str, Any]:
    when = generated_at_utc or _utcnow()
    manifest_file = repo_root / cache_manifest_path
    manifest = _read_json(manifest_file)
    manifest_ready = bool(
        isinstance(manifest, Mapping)
        and isinstance(manifest.get("summary"), Mapping)
        and bool(manifest["summary"].get("research_ready"))
    )
    files = _manifest_files(manifest)
    coverage = _manifest_coverage(manifest)
    snapshot_ready = bool(
        manifest_ready
        and files
        and coverage
        and all(str(row.get("path") or "").endswith(".parquet") for row in files)
        and bool((manifest.get("summary") or {}).get("manifest_content_hash"))
    )
    duckdb_state = _module_available("duckdb") if duckdb_available is None else bool(duckdb_available)
    polars_state = _module_available("polars") if polars_available is None else bool(polars_available)
    blockers = _throughput_blockers(
        manifest_ready=manifest_ready,
        snapshot_ready=snapshot_ready,
        duckdb_available=duckdb_state,
        polars_available=polars_state,
    )
    throughput_ready = not blockers
    total_rows = int((manifest.get("summary") or {}).get("total_rows") or 0) if isinstance(manifest, Mapping) else 0
    status_counts = Counter(str(row.get("status") or "unknown") for row in files)
    summary = {
        "status": "ready" if throughput_ready else "not_ready",
        "research_ready": throughput_ready,
        "cache_manifest_ready": manifest_ready,
        "snapshot_contract_ready": snapshot_ready,
        "duckdb_catalog_manifest_ready": bool(snapshot_ready and duckdb_state),
        "polars_use_policy_ready": bool(snapshot_ready and polars_state),
        "cache_file_count": len(files),
        "coverage_row_count": len(coverage),
        "total_rows": total_rows,
        "duckdb_available": duckdb_state,
        "polars_available": polars_state,
        "status_counts": dict(sorted(status_counts.items())),
        "blocked_reason_counts": dict(sorted(Counter(row["reason"] for row in blockers).items())),
        "operator_summary": (
            "Cache throughput readiness is ready."
            if throughput_ready
            else "Cache throughput readiness fails closed because "
            + ", ".join(sorted({row["reason"] for row in blockers}))
            + "."
        ),
    }
    return {
        "schema_version": SCHEMA_VERSION,
        "report_kind": REPORT_KIND,
        "generated_at_utc": when,
        "mode": "dry-run",
        "safe_to_execute": False,
        "cache_manifest_reference": {
            "path": _rel(manifest_file, root=repo_root),
            "schema_version": manifest.get("schema_version") if isinstance(manifest, Mapping) else None,
            "report_kind": manifest.get("report_kind") if isinstance(manifest, Mapping) else None,
            "research_ready": manifest_ready,
            "manifest_content_hash": (
                (manifest.get("summary") or {}).get("manifest_content_hash")
                if isinstance(manifest, Mapping)
                else None
            ),
            "cache_file_count": len(files),
            "coverage_row_count": len(coverage),
            "total_rows": total_rows,
        },
        "summary": summary,
        "snapshot_contract": _snapshot_contract(
            manifest_path=manifest_file,
            repo_root=repo_root,
            manifest=manifest,
            manifest_ready=manifest_ready,
            snapshot_ready=snapshot_ready,
        ),
        "duckdb_catalog_manifest": _catalog_manifest(
            snapshot_ready=snapshot_ready,
            duckdb_available=duckdb_state,
        ),
        "polars_use_policy": _polars_policy(
            snapshot_ready=snapshot_ready,
            polars_available=polars_state,
        ),
        "throughput_blockers": blockers,
        "safety_invariants": {
            "read_only": True,
            "fetches_external_data": False,
            "mutates_cache": False,
            "mutates_research_outputs": False,
            "frozen_contracts_unchanged": True,
            "paper_shadow_live_forbidden": True,
            "broker_risk_execution_forbidden": True,
            "throughput_cannot_bypass_source_quality": True,
            "duckdb_catalog_is_manifest_only": True,
            "polars_use_is_read_only_scan_only": True,
        },
    }


def _validate_write_target(path: Path) -> None:
    normalized = path.as_posix()
    if _WRITE_PREFIX not in normalized:
        raise ValueError(
            "qre_cache_throughput_manifest: refusing write outside allowlist: " f"{path!r}"
        )


def write_outputs(
    report: Mapping[str, Any],
    *,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    repo_root: Path = Path("."),
) -> dict[str, str]:
    base = repo_root / output_dir
    base.mkdir(parents=True, exist_ok=True)
    timestamp = str(report["generated_at_utc"]).replace(":", "-")
    latest = base / LATEST_NAME
    timestamped = base / f"{timestamp}.json"
    history = base / HISTORY_NAME
    summary = base / SUMMARY_NAME
    payload = json.dumps(report, sort_keys=True, indent=2) + "\n"

    for target in (latest, timestamped, history, summary):
        _validate_write_target(target)

    tmp_latest = latest.with_suffix(latest.suffix + ".tmp")
    tmp_latest.write_text(payload, encoding="utf-8")
    os.replace(tmp_latest, latest)

    tmp_timestamped = timestamped.with_suffix(timestamped.suffix + ".tmp")
    tmp_timestamped.write_text(payload, encoding="utf-8")
    os.replace(tmp_timestamped, timestamped)

    compact = json.dumps(report, sort_keys=True, separators=(",", ":"))
    with history.open("a", encoding="utf-8") as handle:
        handle.write(compact + "\n")

    tmp_summary = summary.with_suffix(summary.suffix + ".tmp")
    tmp_summary.write_text(render_operator_summary(report) + "\n", encoding="utf-8")
    os.replace(tmp_summary, summary)

    return {
        "latest": _rel(latest, root=repo_root),
        "timestamped": _rel(timestamped, root=repo_root),
        "history": _rel(history, root=repo_root),
        "operator_summary": _rel(summary, root=repo_root),
    }


def read_throughput_status(
    *,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    repo_root: Path = Path("."),
) -> dict[str, Any]:
    latest = repo_root / output_dir / LATEST_NAME
    if not latest.is_file():
        return {
            "status": "missing_manifest",
            "research_ready": False,
            "path": _rel(latest, root=repo_root),
            "fails_closed": True,
        }
    try:
        payload = json.loads(latest.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {
            "status": "invalid_manifest",
            "research_ready": False,
            "path": _rel(latest, root=repo_root),
            "fails_closed": True,
        }
    summary = payload.get("summary") if isinstance(payload, dict) else None
    ready = bool(summary.get("research_ready")) if isinstance(summary, dict) else False
    return {
        "status": "ready" if ready else "not_ready",
        "research_ready": ready,
        "path": _rel(latest, root=repo_root),
        "fails_closed": not ready,
        "schema_version": payload.get("schema_version") if isinstance(payload, dict) else None,
    }


def _table(headers: Sequence[str], rows: Sequence[Sequence[str]]) -> str:
    head = "| " + " | ".join(headers) + " |"
    divider = "| " + " | ".join(["---"] * len(headers)) + " |"
    body = ["| " + " | ".join(row) + " |" for row in rows]
    return "\n".join([head, divider, *body])


def render_operator_summary(report: Mapping[str, Any]) -> str:
    summary = report.get("summary") if isinstance(report.get("summary"), Mapping) else {}
    cache_manifest = (
        report.get("cache_manifest_reference")
        if isinstance(report.get("cache_manifest_reference"), Mapping)
        else {}
    )
    snapshot = (
        report.get("snapshot_contract")
        if isinstance(report.get("snapshot_contract"), Mapping)
        else {}
    )
    duckdb_catalog = (
        report.get("duckdb_catalog_manifest")
        if isinstance(report.get("duckdb_catalog_manifest"), Mapping)
        else {}
    )
    polars_policy = (
        report.get("polars_use_policy")
        if isinstance(report.get("polars_use_policy"), Mapping)
        else {}
    )
    summary_table = _table(
        ["Field", "Value"],
        [
            ["status", str(summary.get("status") or "")],
            ["research_ready", str(summary.get("research_ready") or False)],
            ["cache_manifest_ready", str(summary.get("cache_manifest_ready") or False)],
            ["snapshot_contract_ready", str(summary.get("snapshot_contract_ready") or False)],
            ["duckdb_catalog_manifest_ready", str(summary.get("duckdb_catalog_manifest_ready") or False)],
            ["polars_use_policy_ready", str(summary.get("polars_use_policy_ready") or False)],
            ["cache_file_count", str(summary.get("cache_file_count") or 0)],
            ["coverage_row_count", str(summary.get("coverage_row_count") or 0)],
            ["total_rows", str(summary.get("total_rows") or 0)],
        ],
    )
    policy_table = _table(
        ["Component", "Ready", "Blockers"],
        [
            [
                "cache_manifest_reference",
                str(cache_manifest.get("research_ready") or False),
                ", ".join(
                    str(row.get("reason") or "")
                    for row in report.get("throughput_blockers") or []
                    if isinstance(row, Mapping)
                ),
            ],
            [
                "snapshot_contract",
                str(snapshot.get("ready") or False),
                ", ".join(str(value) for value in snapshot.get("blockers") or []),
            ],
            [
                "duckdb_catalog_manifest",
                str(duckdb_catalog.get("ready") or False),
                ", ".join(str(value) for value in duckdb_catalog.get("blockers") or []),
            ],
            [
                "polars_use_policy",
                str(polars_policy.get("ready") or False),
                ", ".join(str(value) for value in polars_policy.get("blockers") or []),
            ],
        ],
    )
    return "\n".join(
        [
            "# QRE Cache Throughput Manifest",
            "",
            f"- {summary.get('operator_summary') or ''}",
            "",
            "## Summary",
            summary_table,
            "",
            "## Policy Gates",
            policy_table,
        ]
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m research.qre_cache_throughput_manifest",
        description="Build a read-only cache throughput manifest and policy report.",
    )
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--status", action="store_true")
    parser.add_argument("--frozen-utc", type=str, default=None)
    parser.add_argument("--cache-manifest-path", type=Path, default=DEFAULT_CACHE_MANIFEST_PATH)
    parser.add_argument(
        "--duckdb-available",
        choices=("auto", "true", "false"),
        default="auto",
    )
    parser.add_argument(
        "--polars-available",
        choices=("auto", "true", "false"),
        default="auto",
    )
    args = parser.parse_args(argv)

    if args.status:
        print(json.dumps(read_throughput_status(), sort_keys=True, indent=2))
        return 0

    report = build_cache_throughput_manifest(
        cache_manifest_path=args.cache_manifest_path,
        generated_at_utc=args.frozen_utc,
        duckdb_available=_availability(args.duckdb_available, "duckdb"),
        polars_available=_availability(args.polars_available, "polars"),
    )
    if args.write:
        report["_artifact_paths"] = write_outputs(report)
    print(json.dumps(report, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())


__all__ = [
    "DEFAULT_CACHE_MANIFEST_PATH",
    "DEFAULT_OUTPUT_DIR",
    "HISTORY_NAME",
    "LATEST_NAME",
    "REPORT_KIND",
    "SCHEMA_VERSION",
    "build_cache_throughput_manifest",
    "read_throughput_status",
    "render_operator_summary",
    "write_outputs",
]
