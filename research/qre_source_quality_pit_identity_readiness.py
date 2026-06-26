"""Read-only QRE source quality, PIT, and identity readiness materialization."""

from __future__ import annotations

import argparse
import functools
import json
import os
from collections import Counter
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Final

from packages.qre_data import cache_manifest, source_quality_readiness
from research import (
    qre_historical_accounting_foundation,
    qre_source_cache_readiness_materialization,
    qre_source_lifecycle_quality_gate,
    qre_symbology_resolver_foundation,
)
from research.data_readiness import point_in_time_policy, report_lag_policy, restatement_policy
from research.external_intelligence import source_manifest_registry

REPORT_KIND: Final[str] = "qre_source_quality_pit_identity_readiness"
SCHEMA_VERSION: Final[str] = "1.0"
DEFAULT_OUTPUT_DIR: Final[Path] = Path("logs/qre_source_quality_pit_identity_readiness")
LATEST_NAME: Final[str] = "latest.json"
SUMMARY_NAME: Final[str] = "operator_summary.md"
WRITE_PREFIX: Final[str] = "logs/qre_source_quality_pit_identity_readiness/"
ARTIFACT_DIR: Final[Path] = Path("artifacts/data_readiness")
ARTIFACT_NAME: Final[str] = "source_quality_pit_identity_readiness_latest.v1.json"
ARTIFACT_WRITE_PREFIX: Final[str] = "artifacts/data_readiness/"
READINESS_STATUS_VOCABULARY: Final[tuple[str, ...]] = (
    "READY",
    "PARTIAL",
    "BLOCKED",
    "UNAVAILABLE",
    "NOT_APPLICABLE",
)


def _table(headers: Sequence[str], rows: Sequence[Sequence[str]]) -> str:
    head = "| " + " | ".join(headers) + " |"
    divider = "| " + " | ".join(["---"] * len(headers)) + " |"
    body = ["| " + " | ".join(row) + " |" for row in rows]
    return "\n".join([head, divider, *body])


def _normalize(text: Any) -> str:
    return str(text or "").strip().lower()


def _quality_row_by_source(
    source_quality_report: Mapping[str, Any],
) -> dict[str, Mapping[str, Any]]:
    rows = source_quality_report.get("sources")
    if not isinstance(rows, list):
        return {}
    result: dict[str, Mapping[str, Any]] = {}
    for row in rows:
        if not isinstance(row, Mapping):
            continue
        result[_normalize(row.get("source"))] = row
    return result


def _coverage_rows_by_source(cache_report: Mapping[str, Any]) -> dict[str, list[Mapping[str, Any]]]:
    rows = cache_report.get("coverage")
    if not isinstance(rows, list):
        return {}
    grouped: dict[str, list[Mapping[str, Any]]] = {}
    for row in rows:
        if not isinstance(row, Mapping):
            continue
        grouped.setdefault(_normalize(row.get("source")), []).append(row)
    return grouped


@functools.lru_cache(maxsize=8)
def _load_cache_report(repo_root_text: str) -> dict[str, Any]:
    repo_root = Path(repo_root_text)
    status = cache_manifest.read_manifest_status(repo_root=repo_root)
    path_text = str(status.get("path") or "")
    if status.get("status") in {"ready", "not_ready"} and path_text:
        path = repo_root / path_text
        if path.is_file():
            return json.loads(path.read_text(encoding="utf-8"))
    return cache_manifest.build_cache_manifest(repo_root=repo_root)


@functools.lru_cache(maxsize=8)
def _load_source_quality_status_and_report(
    repo_root_text: str,
) -> tuple[dict[str, Any], dict[str, Any]]:
    repo_root = Path(repo_root_text)
    status = source_quality_readiness.read_source_quality_status(repo_root=repo_root)
    path_text = str(status.get("path") or "")
    if status.get("status") in {"ready", "not_ready"} and path_text:
        path = repo_root / path_text
        if path.is_file():
            return status, json.loads(path.read_text(encoding="utf-8"))
    manifest = _load_cache_report(repo_root_text)
    report = source_quality_readiness.build_source_quality_report(manifest)
    return status, report


def _observed_source_row(
    *,
    source_name: str,
    quality_row: Mapping[str, Any] | None,
    coverage_rows: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    quality_status_counts = (
        quality_row.get("quality_status_counts") if isinstance(quality_row, Mapping) else {}
    )
    if not isinstance(quality_status_counts, Mapping):
        quality_status_counts = {}

    ready_quality = int(quality_status_counts.get("ready") or 0)
    coverage_ready_rows = sum(bool(row.get("ready")) for row in coverage_rows)
    coverage_row_count = len(coverage_rows)
    timestamp_complete_rows = sum(
        bool(row.get("min_timestamp_utc")) and bool(row.get("max_timestamp_utc"))
        for row in coverage_rows
    )
    statuses = {
        "freshness": "PARTIAL" if timestamp_complete_rows else "BLOCKED",
        "missing_data_checks": "PARTIAL" if ready_quality else "BLOCKED",
        "timestamp_monotonicity": "UNAVAILABLE",
        "duplicate_detection": "UNAVAILABLE",
        "outlier_handling": "UNAVAILABLE",
        "coverage": "PARTIAL" if coverage_ready_rows else "BLOCKED",
        "source_agreement": "UNAVAILABLE",
    }
    blockers: list[str] = []
    if not timestamp_complete_rows:
        blockers.append("timestamp_range_missing")
    if not ready_quality:
        blockers.append("source_quality_rows_not_ready")
    if coverage_row_count == 0:
        blockers.append("coverage_rows_missing")
    return {
        "observed_source": source_name,
        "coverage_row_count": coverage_row_count,
        "ready_coverage_row_count": coverage_ready_rows,
        "timestamp_complete_row_count": timestamp_complete_rows,
        "quality_ready_row_count": ready_quality,
        "dimension_statuses": statuses,
        "blocking_reasons": blockers,
        "operator_explanation": (
            "Observed cache evidence is present for this source, but monotonicity, duplicate-bar, "
            "outlier, and cross-source agreement checks are not yet explicit."
            if coverage_row_count
            else "No observed cache evidence is present for this source."
        ),
    }


def _historical_row_by_source(report: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    rows = report.get("rows")
    if not isinstance(rows, list):
        return {}
    return {
        str(row["source_id"]): row
        for row in rows
        if isinstance(row, Mapping) and "source_id" in row
    }


def _policy_row_by_source(report: Mapping[str, Any]) -> dict[str, Mapping[str, Any]]:
    rows = report.get("rows")
    if not isinstance(rows, list):
        return {}
    return {
        str(row["source_id"]): row
        for row in rows
        if isinstance(row, Mapping) and "source_id" in row
    }


def _identity_summary_status(symbology_report: Mapping[str, Any]) -> tuple[str, list[str]]:
    summary = symbology_report.get("summary")
    if not isinstance(summary, Mapping):
        return "UNAVAILABLE", ["symbology_summary_missing"]
    blocked = int(summary.get("ambiguity_blocked_count") or 0)
    verified = int(summary.get("verified_count") or 0)
    if verified <= 0:
        return "BLOCKED", ["no_verified_provider_symbols"]
    if blocked > 0:
        return "PARTIAL", ["identity_alias_ambiguity_present"]
    return "READY", []


def _manifest_readiness_row(
    manifest: Mapping[str, Any],
    *,
    policy_by_source: Mapping[str, Mapping[str, Any]],
    pit_by_source: Mapping[str, Mapping[str, Any]],
    report_lag_by_source: Mapping[str, Mapping[str, Any]],
    restatement_by_source: Mapping[str, Mapping[str, Any]],
    historical_by_source: Mapping[str, Mapping[str, Any]],
    lifecycle_by_source: Mapping[str, Mapping[str, Any]],
    symbology_report: Mapping[str, Any],
) -> dict[str, Any]:
    source_id = str(manifest["source_id"])
    source_type = str(manifest["source_type"])
    policy_row = policy_by_source[source_id]
    pit_row = pit_by_source[source_id]
    report_lag_row = report_lag_by_source[source_id]
    restatement_row = restatement_by_source[source_id]
    historical_row = historical_by_source[source_id]
    lifecycle_row = lifecycle_by_source[source_id]

    identity_status, identity_blockers = _identity_summary_status(symbology_report)
    if source_type not in {"identity_symbology", "listing_metadata", "issuer_metadata", "fundamental_statement_data"}:
        identity_status = "NOT_APPLICABLE"
        identity_blockers = []

    dimension_statuses = {
        "allowed_use_and_license": (
            "READY" if bool(policy_row.get("allowed_for_quality_gate")) else "BLOCKED"
        ),
        "point_in_time_policy": (
            "READY"
            if str(pit_row.get("policy_status")) == "SUPPORTED"
            else "PARTIAL"
            if str(pit_row.get("policy_status")) == "PARTIALLY_SUPPORTED"
            else "BLOCKED"
            if str(pit_row.get("requirement_status")) == "REQUIRED"
            else "NOT_APPLICABLE"
        ),
        "report_lag_policy": (
            "READY"
            if str(report_lag_row.get("policy_status")) == "SUPPORTED"
            else "PARTIAL"
            if str(report_lag_row.get("policy_status")) == "PARTIALLY_SUPPORTED"
            else "BLOCKED"
            if str(report_lag_row.get("requirement_status")) == "REQUIRED"
            else "NOT_APPLICABLE"
        ),
        "restatement_policy": (
            "READY"
            if str(restatement_row.get("policy_status")) == "SUPPORTED"
            else "PARTIAL"
            if str(restatement_row.get("policy_status")) == "PARTIALLY_SUPPORTED"
            else "BLOCKED"
            if str(restatement_row.get("requirement_status")) == "REQUIRED"
            else "NOT_APPLICABLE"
        ),
        "historical_lineage": (
            "READY"
            if bool(historical_row.get("gate_statuses", {}).get("historical_lineage_reproducible"))
            else "BLOCKED"
            if bool(historical_row.get("requires_historical_accounting"))
            else "NOT_APPLICABLE"
        ),
        "identity_readiness": identity_status,
        "freshness": (
            "BLOCKED"
            if _normalize(manifest.get("expected_freshness")).endswith("unknown")
            or _normalize(manifest.get("expected_freshness")) == "unknown"
            else "NOT_APPLICABLE"
            if _normalize(manifest.get("source_type")) in {"identity_symbology", "listing_metadata", "issuer_metadata"}
            else "PARTIAL"
        ),
        "missing_data_checks": "UNAVAILABLE",
        "timestamp_monotonicity": "UNAVAILABLE",
        "duplicate_detection": "UNAVAILABLE",
        "outlier_handling": "UNAVAILABLE",
        "coverage": (
            "PARTIAL"
            if bool(manifest.get("factor_field_coverage_claims"))
            else "BLOCKED"
        ),
        "source_agreement": "UNAVAILABLE",
    }

    blocking_reasons: list[str] = []
    blocking_reasons.extend(str(reason) for reason in policy_row.get("block_reasons") or [])
    blocking_reasons.extend(str(reason) for reason in pit_row.get("block_reasons") or [])
    blocking_reasons.extend(str(reason) for reason in report_lag_row.get("block_reasons") or [])
    blocking_reasons.extend(str(reason) for reason in restatement_row.get("block_reasons") or [])
    blocking_reasons.extend(str(reason) for reason in historical_row.get("blocking_reasons") or [])
    blocking_reasons.extend(identity_blockers)
    if not bool(lifecycle_row.get("source_quality_ready")):
        blocking_reasons.append("source_quality_sidecar_not_ready")
    if not bool(lifecycle_row.get("gate_statuses", {}).get("identity_mapping_present")):
        blocking_reasons.append("identity_mapping_not_explicit")
    if not bool(lifecycle_row.get("gate_statuses", {}).get("quality_gates_passed")):
        blocking_reasons.append("quality_gates_not_passed")

    return {
        "source_id": source_id,
        "provider_id": str(manifest["provider_id"]),
        "source_type": source_type,
        "source_status": str(manifest["source_status"]),
        "manifest_status": str(manifest["manifest_status"]),
        "license_policy_status": str(policy_row.get("license_policy_status") or "UNKNOWN"),
        "lifecycle_status": str(lifecycle_row.get("lifecycle_status") or "blocked"),
        "dimension_statuses": dimension_statuses,
        "blocking_reasons": sorted(set(blocking_reasons)),
        "operator_explanation": (
            "Source readiness remains fail-closed until license, PIT, report-lag, restatement, "
            "identity, and declared quality-gate evidence are explicit."
        ),
    }


def build_source_quality_pit_identity_readiness(
    *,
    repo_root: Path = Path("."),
) -> dict[str, Any]:
    repo_root_text = str(repo_root.resolve())
    manifest_registry = source_manifest_registry.build_source_manifest_registry()
    lifecycle_report = qre_source_lifecycle_quality_gate.build_source_lifecycle_quality_gate(
        repo_root=repo_root
    )
    historical_report = (
        qre_historical_accounting_foundation.build_historical_accounting_foundation()
    )
    pit_report = point_in_time_policy.build_point_in_time_policy()
    report_lag_report = report_lag_policy.build_report_lag_policy()
    restatement_report = restatement_policy.build_restatement_policy()
    symbology_report = qre_symbology_resolver_foundation.build_symbology_resolver_foundation()
    cache_report = _load_cache_report(repo_root_text)
    source_quality_status, source_quality_report = _load_source_quality_status_and_report(
        repo_root_text
    )
    source_cache_report = (
        qre_source_cache_readiness_materialization.build_source_cache_readiness_materialization(
            repo_root=repo_root
        )
    )

    lifecycle_by_source = _historical_row_by_source(lifecycle_report)
    historical_by_source = _historical_row_by_source(historical_report)
    policy_by_source = {
        str(row["source_id"]): row
        for row in manifest_registry["license_policy_rows"]
        if isinstance(row, Mapping)
    }
    pit_by_source = _policy_row_by_source(pit_report)
    report_lag_by_source = _policy_row_by_source(report_lag_report)
    restatement_by_source = _policy_row_by_source(restatement_report)

    manifest_rows = [
        _manifest_readiness_row(
            row,
            policy_by_source=policy_by_source,
            pit_by_source=pit_by_source,
            report_lag_by_source=report_lag_by_source,
            restatement_by_source=restatement_by_source,
            historical_by_source=historical_by_source,
            lifecycle_by_source=lifecycle_by_source,
            symbology_report=symbology_report,
        )
        for row in manifest_registry["rows"]
        if isinstance(row, Mapping)
    ]
    manifest_rows.sort(key=lambda row: row["source_id"])

    quality_by_source = _quality_row_by_source(source_quality_report)
    coverage_by_source = _coverage_rows_by_source(cache_report)
    observed_rows = [
        _observed_source_row(
            source_name=source_name,
            quality_row=quality_by_source.get(source_name),
            coverage_rows=rows,
        )
        for source_name, rows in sorted(coverage_by_source.items())
    ]

    manifest_dimension_counts = Counter(
        status
        for row in manifest_rows
        for status in row["dimension_statuses"].values()
    )
    observed_dimension_counts = Counter(
        status
        for row in observed_rows
        for status in row["dimension_statuses"].values()
    )
    manifest_blockers = Counter(
        blocker for row in manifest_rows for blocker in row["blocking_reasons"]
    )
    observed_blockers = Counter(
        blocker for row in observed_rows for blocker in row["blocking_reasons"]
    )

    return {
        "schema_version": SCHEMA_VERSION,
        "report_kind": REPORT_KIND,
        "readiness_status_vocabulary": list(READINESS_STATUS_VOCABULARY),
        "summary": {
            "source_manifest_count": len(manifest_rows),
            "observed_source_count": len(observed_rows),
            "cache_manifest_research_ready": bool(cache_report["summary"]["research_ready"]),
            "source_quality_report_status": str(source_quality_status.get("status") or "missing"),
            "source_quality_report_ready": bool(source_quality_status.get("research_ready")),
            "manifest_dimension_status_counts": dict(sorted(manifest_dimension_counts.items())),
            "observed_dimension_status_counts": dict(sorted(observed_dimension_counts.items())),
            "manifest_blocking_reason_counts": dict(sorted(manifest_blockers.items())),
            "observed_blocking_reason_counts": dict(sorted(observed_blockers.items())),
            "identity_ambiguity_blocked_count": int(
                symbology_report["summary"]["ambiguity_blocked_count"]
            ),
            "pit_required_blocked_count": int(
                historical_report["summary"]["required_blocked_count"]
            ),
            "operator_summary": (
                "Local cache evidence is present for observed sources, but source governance, PIT, "
                "report-lag, restatement, and identity readiness remain fail-closed at the manifest level."
            ),
        },
        "manifest_rows": manifest_rows,
        "observed_source_rows": observed_rows,
        "supporting_reports": {
            "cache_manifest": {
                "report_kind": cache_report["report_kind"],
                "research_ready": cache_report["summary"]["research_ready"],
                "manifest_content_hash": cache_report["summary"]["manifest_content_hash"],
            },
            "source_quality_status": source_quality_status,
            "source_cache_readiness_materialization": {
                "report_kind": source_cache_report["report_kind"],
                "source_cache_readiness_linked": source_cache_report["summary"][
                    "source_cache_readiness_linked"
                ],
            },
            "source_lifecycle_quality_gate": {
                "report_kind": lifecycle_report["report_kind"],
                "source_quality_report_ready": lifecycle_report["summary"][
                    "source_quality_report_ready"
                ],
            },
            "historical_accounting_foundation": {
                "report_kind": historical_report["report_kind"],
                "required_blocked_count": historical_report["summary"]["required_blocked_count"],
            },
            "symbology_resolver_foundation": {
                "report_kind": symbology_report["report_kind"],
                "ambiguity_blocked_count": symbology_report["summary"]["ambiguity_blocked_count"],
                "verified_count": symbology_report["summary"]["verified_count"],
            },
        },
        "safety_invariants": {
            "read_only": True,
            "fetches_external_data": False,
            "mutates_runtime_state": False,
            "mutates_research_outputs": False,
            "mutates_frozen_contracts": False,
            "provider_activation_forbidden": True,
            "paper_shadow_live_forbidden": True,
            "broker_risk_execution_forbidden": True,
            "retrieval_not_authority": True,
            "diagnostics_do_not_trade": True,
        },
    }


def render_operator_summary(report: Mapping[str, Any]) -> str:
    summary = report.get("summary") if isinstance(report.get("summary"), Mapping) else {}
    manifest_rows = (
        report.get("manifest_rows") if isinstance(report.get("manifest_rows"), list) else []
    )
    observed_rows = (
        report.get("observed_source_rows")
        if isinstance(report.get("observed_source_rows"), list)
        else []
    )
    summary_table = _table(
        ["Field", "Value"],
        [
            ["source_manifest_count", str(summary.get("source_manifest_count") or 0)],
            ["observed_source_count", str(summary.get("observed_source_count") or 0)],
            ["source_quality_report_status", str(summary.get("source_quality_report_status") or "")],
            ["source_quality_report_ready", str(summary.get("source_quality_report_ready") or False)],
            ["identity_ambiguity_blocked_count", str(summary.get("identity_ambiguity_blocked_count") or 0)],
            ["pit_required_blocked_count", str(summary.get("pit_required_blocked_count") or 0)],
        ],
    )
    manifest_table = _table(
        ["source_id", "license", "pit", "report_lag", "restatement", "identity"],
        [
            [
                str(row.get("source_id") or ""),
                str((row.get("dimension_statuses") or {}).get("allowed_use_and_license") or ""),
                str((row.get("dimension_statuses") or {}).get("point_in_time_policy") or ""),
                str((row.get("dimension_statuses") or {}).get("report_lag_policy") or ""),
                str((row.get("dimension_statuses") or {}).get("restatement_policy") or ""),
                str((row.get("dimension_statuses") or {}).get("identity_readiness") or ""),
            ]
            for row in manifest_rows
            if isinstance(row, Mapping)
        ],
    )
    observed_table = _table(
        ["observed_source", "freshness", "missing_data", "coverage", "blockers"],
        [
            [
                str(row.get("observed_source") or ""),
                str((row.get("dimension_statuses") or {}).get("freshness") or ""),
                str((row.get("dimension_statuses") or {}).get("missing_data_checks") or ""),
                str((row.get("dimension_statuses") or {}).get("coverage") or ""),
                ",".join(str(value) for value in row.get("blocking_reasons") or []) or "none",
            ]
            for row in observed_rows
            if isinstance(row, Mapping)
        ],
    )
    return "\n".join(
        [
            "# QRE Source Quality, PIT, and Identity Readiness",
            "",
            f"- {summary.get('operator_summary') or ''}",
            "",
            "## Status",
            summary_table,
            "",
            "## Manifest Rows",
            manifest_table,
            "",
            "## Observed Source Rows",
            observed_table,
        ]
    )


def _validate_log_target(path: Path) -> None:
    if WRITE_PREFIX not in path.as_posix():
        raise ValueError(
            f"qre_source_quality_pit_identity_readiness: refusing write outside allowlist: {path!r}"
        )


def _validate_artifact_target(path: Path) -> None:
    if ARTIFACT_WRITE_PREFIX not in path.as_posix():
        raise ValueError(
            f"qre_source_quality_pit_identity_readiness: refusing artifact write outside allowlist: {path!r}"
        )


def write_outputs(
    report: Mapping[str, Any],
    *,
    repo_root: Path = Path("."),
) -> dict[str, str]:
    log_base = repo_root / DEFAULT_OUTPUT_DIR
    log_base.mkdir(parents=True, exist_ok=True)
    artifact_base = repo_root / ARTIFACT_DIR
    artifact_base.mkdir(parents=True, exist_ok=True)

    latest = log_base / LATEST_NAME
    summary = log_base / SUMMARY_NAME
    artifact = artifact_base / ARTIFACT_NAME
    for path in (latest, summary):
        _validate_log_target(path)
    _validate_artifact_target(artifact)

    latest_payload = json.dumps(report, indent=2, sort_keys=True) + "\n"
    tmp_latest = latest.with_suffix(latest.suffix + ".tmp")
    tmp_latest.write_text(latest_payload, encoding="utf-8")
    os.replace(tmp_latest, latest)

    tmp_summary = summary.with_suffix(summary.suffix + ".tmp")
    tmp_summary.write_text(render_operator_summary(report) + "\n", encoding="utf-8")
    os.replace(tmp_summary, summary)

    tmp_artifact = artifact.with_suffix(artifact.suffix + ".tmp")
    tmp_artifact.write_text(latest_payload, encoding="utf-8")
    os.replace(tmp_artifact, artifact)

    return {
        "latest": latest.relative_to(repo_root).as_posix(),
        "operator_summary": summary.relative_to(repo_root).as_posix(),
        "artifact": artifact.relative_to(repo_root).as_posix(),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m research.qre_source_quality_pit_identity_readiness",
        description="Materialize the read-only QRE source quality, PIT, and identity readiness report.",
    )
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args(argv)
    report = build_source_quality_pit_identity_readiness()
    if args.write:
        report["_artifact_paths"] = write_outputs(report)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
