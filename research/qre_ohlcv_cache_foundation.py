"""Read-only QRE OHLCV/cache foundation materialization."""

from __future__ import annotations

import argparse
import json
import os
from collections import Counter
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Final

from packages.qre_data import cache_manifest, source_quality_readiness
from research import qre_cache_throughput_manifest, qre_source_cache_readiness_materialization
from research.external_intelligence import source_manifest_registry

REPORT_KIND: Final[str] = "qre_ohlcv_cache_foundation"
SCHEMA_VERSION: Final[str] = "1.0"
DEFAULT_OUTPUT_DIR: Final[Path] = Path("logs/qre_ohlcv_cache_foundation")
LATEST_NAME: Final[str] = "latest.json"
SUMMARY_NAME: Final[str] = "operator_summary.md"
WRITE_PREFIX: Final[str] = "logs/qre_ohlcv_cache_foundation/"
ARTIFACT_DIR: Final[Path] = Path("artifacts/cache")
ARTIFACT_NAME: Final[str] = "cache_foundation_latest.v1.json"
ARTIFACT_WRITE_PREFIX: Final[str] = "artifacts/cache/"
_CACHE_MANIFEST_PATH: Final[Path] = Path("logs/qre_data_cache_manifest/latest.json")
_SOURCE_QUALITY_PATH: Final[Path] = Path("logs/qre_data_source_quality_readiness/latest.json")
_THROUGHPUT_PATH: Final[Path] = Path("logs/qre_cache_throughput_manifest/latest.json")


def _table(headers: Sequence[str], rows: Sequence[Sequence[str]]) -> str:
    head = "| " + " | ".join(headers) + " |"
    divider = "| " + " | ".join(["---"] * len(headers)) + " |"
    body = ["| " + " | ".join(row) + " |" for row in rows]
    return "\n".join([head, divider, *body])


def _read_json(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _counter_dict(values: Sequence[str]) -> dict[str, int]:
    return dict(sorted(Counter(values).items()))


def _throughput_report(
    *,
    repo_root: Path,
    duckdb_available: bool | None,
    polars_available: bool | None,
) -> dict[str, Any]:
    payload = _read_json(repo_root / _THROUGHPUT_PATH)
    if isinstance(payload, dict) and isinstance(payload.get("summary"), Mapping):
        return payload
    return qre_cache_throughput_manifest.build_cache_throughput_manifest(
        repo_root=repo_root,
        cache_manifest_path=_CACHE_MANIFEST_PATH,
        duckdb_available=duckdb_available,
        polars_available=polars_available,
    )


def _local_cache_sources(coverage: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for row in coverage:
        rows.append(
            {
                "source": str(row.get("source") or "unknown"),
                "instrument": str(row.get("instrument") or "unknown"),
                "timeframe": str(row.get("timeframe") or "unknown"),
                "ready": bool(row.get("ready")),
                "file_count": int(row.get("file_count") or 0),
                "row_count": int(row.get("row_count") or 0),
                "min_timestamp_utc": row.get("min_timestamp_utc"),
                "max_timestamp_utc": row.get("max_timestamp_utc"),
                "content_hash": row.get("content_hash"),
            }
        )
    rows.sort(key=lambda item: (item["source"], item["instrument"], item["timeframe"]))
    return rows


def _future_external_source_blockers() -> list[dict[str, Any]]:
    registry = source_manifest_registry.build_source_manifest_registry()
    policy_by_source = registry["policy_by_source"]
    blocked: list[dict[str, Any]] = []
    for row in registry["rows"]:
        source_id = str(row["source_id"])
        provider_id = str(row["provider_id"])
        policy = policy_by_source[source_id]
        license_status = str(policy["license_policy_status"])
        manifest_status = str(row["manifest_status"])
        activation_requirements = [str(item) for item in row.get("activation_requirements", [])]
        block_reasons = [str(item) for item in row.get("manifest_block_reasons", [])]
        requires_operator_or_credentials = bool(row.get("authentication_required")) or (
            "operator_license_approval" in activation_requirements
        )
        if license_status == "PASS" and manifest_status == "PASS" and not requires_operator_or_credentials:
            continue
        blocked.append(
            {
                "source_id": source_id,
                "provider_id": provider_id,
                "source_type": str(row["source_type"]),
                "source_status": str(row["source_status"]),
                "license_policy_status": license_status,
                "manifest_status": manifest_status,
                "authentication_required": bool(row.get("authentication_required")),
                "requires_operator_or_credentials": requires_operator_or_credentials,
                "activation_requirements": activation_requirements,
                "manifest_block_reasons": block_reasons,
                "policy_block_reasons": [str(item) for item in policy.get("block_reasons", [])],
                "operator_explanation": str(policy["operator_explanation"]),
            }
        )
    blocked.sort(key=lambda item: (item["provider_id"], item["source_id"]))
    return blocked


def build_ohlcv_cache_foundation(
    *,
    repo_root: Path = Path("."),
    duckdb_available: bool | None = None,
    polars_available: bool | None = None,
) -> dict[str, Any]:
    manifest_status = cache_manifest.read_manifest_status(repo_root=repo_root)
    source_quality_status = source_quality_readiness.read_source_quality_status(repo_root=repo_root)
    manifest_payload = _read_json(repo_root / _CACHE_MANIFEST_PATH) or {}
    throughput = _throughput_report(
        repo_root=repo_root,
        duckdb_available=duckdb_available,
        polars_available=polars_available,
    )
    materialization = qre_source_cache_readiness_materialization.build_source_cache_readiness_materialization(
        repo_root=repo_root
    )

    manifest_summary = (
        manifest_payload.get("summary") if isinstance(manifest_payload.get("summary"), Mapping) else {}
    )
    coverage = manifest_payload.get("coverage")
    cache_roots = manifest_payload.get("cache_roots")
    if not isinstance(coverage, list):
        coverage = []
    if not isinstance(cache_roots, list):
        cache_roots = []

    local_cache_sources = _local_cache_sources(
        [row for row in coverage if isinstance(row, Mapping)]
    )
    local_ready_sources = [row for row in local_cache_sources if row["ready"]]
    external_blockers = _future_external_source_blockers()

    foundation_ready = all(
        (
            bool(manifest_status.get("research_ready")),
            bool(source_quality_status.get("research_ready")),
            bool(throughput["summary"]["research_ready"]),
            bool(materialization["summary"]["source_cache_readiness_linked"]),
        )
    )
    blocked_reasons: list[str] = []
    if not bool(manifest_status.get("research_ready")):
        blocked_reasons.append(str(manifest_status.get("status") or "cache_manifest_not_ready"))
    if not bool(source_quality_status.get("research_ready")):
        blocked_reasons.append(
            str(source_quality_status.get("status") or "source_quality_not_ready")
        )
    if not bool(throughput["summary"]["research_ready"]):
        blocked_reasons.extend(
            str(item["reason"])
            for item in throughput.get("throughput_blockers", [])
            if isinstance(item, Mapping)
        )
    if not bool(materialization["summary"]["source_cache_readiness_linked"]):
        blocked_reasons.extend(
            str(reason)
            for reason in materialization["summary"].get("missing_sidecars", [])
        )
        blocked_reasons.extend(
            f"{reason}_not_ready"
            for reason in materialization["summary"].get("present_not_ready_sidecars", [])
        )

    operator_summary = (
        "Local OHLCV/cache foundation is ready from repository-local datasets. "
        "Cache manifest, source-quality readiness, source/cache materialization, "
        "and throughput policy are aligned, while external source activation remains "
        "separately blocked until explicit manifest, license, and policy gates pass."
        if foundation_ready
        else "Local OHLCV/cache foundation remains fail-closed because "
        + ", ".join(sorted(set(blocked_reasons)))
        + "."
    )

    return {
        "schema_version": SCHEMA_VERSION,
        "report_kind": REPORT_KIND,
        "summary": {
            "status": "ready" if foundation_ready else "not_ready",
            "research_ready": foundation_ready,
            "cache_manifest_status": str(manifest_status.get("status") or "missing"),
            "source_quality_status": str(source_quality_status.get("status") or "missing"),
            "throughput_status": str(throughput["summary"]["status"]),
            "source_cache_linked": bool(materialization["summary"]["source_cache_readiness_linked"]),
            "cache_file_count": int(manifest_summary.get("cache_file_count") or 0),
            "coverage_row_count": int(manifest_summary.get("coverage_row_count") or 0),
            "ready_coverage_row_count": len(local_ready_sources),
            "source_count": len({row["source"] for row in local_cache_sources}),
            "instrument_count": len({row["instrument"] for row in local_cache_sources}),
            "timeframe_count": len({row["timeframe"] for row in local_cache_sources}),
            "cache_root_status_counts": _counter_dict(
                [str(row.get("status") or "unknown") for row in cache_roots if isinstance(row, Mapping)]
            ),
            "local_source_status_counts": _counter_dict(
                ["ready" if row["ready"] else "blocked" for row in local_cache_sources]
            ),
            "external_blocker_count": len(external_blockers),
            "external_blockers_requiring_operator_or_credentials": sum(
                1 for row in external_blockers if row["requires_operator_or_credentials"]
            ),
            "manifest_content_hash": manifest_summary.get("manifest_content_hash"),
            "operator_summary": operator_summary,
        },
        "local_cache_foundation": {
            "cache_manifest_path": str(manifest_status.get("path") or _CACHE_MANIFEST_PATH.as_posix()),
            "source_quality_path": str(
                source_quality_status.get("path") or _SOURCE_QUALITY_PATH.as_posix()
            ),
            "cache_roots": [row for row in cache_roots if isinstance(row, Mapping)],
            "sources": local_cache_sources,
        },
        "supporting_reports": {
            "cache_manifest_status": manifest_status,
            "source_quality_status": source_quality_status,
            "source_cache_materialization": {
                "cache_manifest_sidecar_status": materialization["summary"][
                    "cache_manifest_sidecar_status"
                ],
                "source_quality_sidecar_status": materialization["summary"][
                    "source_quality_sidecar_status"
                ],
                "source_cache_readiness_linked": materialization["summary"][
                    "source_cache_readiness_linked"
                ],
                "missing_sidecars": materialization["summary"]["missing_sidecars"],
                "present_not_ready_sidecars": materialization["summary"][
                    "present_not_ready_sidecars"
                ],
            },
            "cache_throughput": {
                "status": throughput["summary"]["status"],
                "research_ready": throughput["summary"]["research_ready"],
                "cache_manifest_ready": throughput["summary"]["cache_manifest_ready"],
                "snapshot_contract_ready": throughput["summary"]["snapshot_contract_ready"],
                "duckdb_catalog_manifest_ready": throughput["summary"][
                    "duckdb_catalog_manifest_ready"
                ],
                "polars_use_policy_ready": throughput["summary"]["polars_use_policy_ready"],
                "blocked_reason_counts": throughput["summary"]["blocked_reason_counts"],
            },
        },
        "future_external_source_blockers": external_blockers,
        "safety_invariants": {
            "read_only": True,
            "fetches_external_data": False,
            "mutates_cache": False,
            "mutates_research_outputs": False,
            "mutates_frozen_contracts": False,
            "paper_shadow_live_forbidden": True,
            "broker_risk_execution_forbidden": True,
            "external_source_activation_not_required": True,
            "source_activation_remains_separate": True,
        },
    }


def render_operator_summary(report: Mapping[str, Any]) -> str:
    summary = report.get("summary") if isinstance(report.get("summary"), Mapping) else {}
    local = (
        report.get("local_cache_foundation")
        if isinstance(report.get("local_cache_foundation"), Mapping)
        else {}
    )
    sources = local.get("sources") if isinstance(local.get("sources"), list) else []
    blockers = (
        report.get("future_external_source_blockers")
        if isinstance(report.get("future_external_source_blockers"), list)
        else []
    )
    summary_table = _table(
        ["Field", "Value"],
        [
            ["status", str(summary.get("status") or "")],
            ["research_ready", str(summary.get("research_ready") or False)],
            ["cache_manifest_status", str(summary.get("cache_manifest_status") or "")],
            ["source_quality_status", str(summary.get("source_quality_status") or "")],
            ["throughput_status", str(summary.get("throughput_status") or "")],
            ["source_cache_linked", str(summary.get("source_cache_linked") or False)],
            ["cache_file_count", str(summary.get("cache_file_count") or 0)],
            ["coverage_row_count", str(summary.get("coverage_row_count") or 0)],
            ["source_count", str(summary.get("source_count") or 0)],
            ["external_blocker_count", str(summary.get("external_blocker_count") or 0)],
        ],
    )
    source_table = _table(
        ["source", "instrument", "timeframe", "ready", "file_count", "row_count"],
        [
            [
                str(row.get("source") or ""),
                str(row.get("instrument") or ""),
                str(row.get("timeframe") or ""),
                str(row.get("ready") or False),
                str(row.get("file_count") or 0),
                str(row.get("row_count") or 0),
            ]
            for row in sources[:12]
            if isinstance(row, Mapping)
        ],
    )
    blocker_table = _table(
        ["source_id", "provider_id", "license", "manifest", "operator_or_credentials"],
        [
            [
                str(row.get("source_id") or ""),
                str(row.get("provider_id") or ""),
                str(row.get("license_policy_status") or ""),
                str(row.get("manifest_status") or ""),
                str(row.get("requires_operator_or_credentials") or False),
            ]
            for row in blockers[:12]
            if isinstance(row, Mapping)
        ],
    )
    return "\n".join(
        [
            "# QRE OHLCV Cache Foundation",
            "",
            f"- {summary.get('operator_summary') or ''}",
            "",
            "## Summary",
            summary_table,
            "",
            "## Local Cache Sources",
            source_table,
            "",
            "## Future External Source Blockers",
            blocker_table,
        ]
    )


def _validate_write_target(path: Path) -> None:
    if WRITE_PREFIX not in path.as_posix():
        raise ValueError(
            f"qre_ohlcv_cache_foundation: refusing write outside allowlist: {path!r}"
        )


def _validate_artifact_target(path: Path) -> None:
    if ARTIFACT_WRITE_PREFIX not in path.as_posix():
        raise ValueError(
            f"qre_ohlcv_cache_foundation: refusing artifact write outside allowlist: {path!r}"
        )


def write_outputs(
    report: Mapping[str, Any],
    *,
    repo_root: Path = Path("."),
) -> dict[str, str]:
    base = repo_root / DEFAULT_OUTPUT_DIR
    base.mkdir(parents=True, exist_ok=True)
    artifact_base = repo_root / ARTIFACT_DIR
    artifact_base.mkdir(parents=True, exist_ok=True)
    latest = base / LATEST_NAME
    summary = base / SUMMARY_NAME
    artifact = artifact_base / ARTIFACT_NAME
    for target in (latest, summary):
        _validate_write_target(target)
    _validate_artifact_target(artifact)

    payload = json.dumps(report, indent=2, sort_keys=True) + "\n"
    tmp_latest = latest.with_suffix(latest.suffix + ".tmp")
    tmp_latest.write_text(payload, encoding="utf-8")
    os.replace(tmp_latest, latest)

    tmp_summary = summary.with_suffix(summary.suffix + ".tmp")
    tmp_summary.write_text(render_operator_summary(report) + "\n", encoding="utf-8")
    os.replace(tmp_summary, summary)

    tmp_artifact = artifact.with_suffix(artifact.suffix + ".tmp")
    tmp_artifact.write_text(payload, encoding="utf-8")
    os.replace(tmp_artifact, artifact)

    return {
        "latest": latest.relative_to(repo_root).as_posix(),
        "operator_summary": summary.relative_to(repo_root).as_posix(),
        "cache_foundation_artifact": artifact.relative_to(repo_root).as_posix(),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m research.qre_ohlcv_cache_foundation",
        description="Materialize the read-only QRE OHLCV/cache foundation report.",
    )
    parser.add_argument("--write", action="store_true")
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
    duckdb_available = None if args.duckdb_available == "auto" else args.duckdb_available == "true"
    polars_available = None if args.polars_available == "auto" else args.polars_available == "true"
    report = build_ohlcv_cache_foundation(
        duckdb_available=duckdb_available,
        polars_available=polars_available,
    )
    if args.write:
        report["_artifact_paths"] = write_outputs(report)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
