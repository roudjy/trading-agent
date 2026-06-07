from __future__ import annotations

import argparse
import json
import os
from collections import Counter
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Final

from packages.qre_data import cache_manifest
from packages.qre_data import source_quality_readiness


REPORT_KIND: Final[str] = "qre_source_cache_readiness_materialization"
SCHEMA_VERSION: Final[str] = "1.0"
DEFAULT_OUTPUT_DIR: Final[Path] = Path("logs/qre_source_cache_readiness_materialization")
LATEST_NAME: Final[str] = "latest.json"
OPERATOR_SUMMARY_NAME: Final[str] = "operator_summary.md"
_WRITE_PREFIX: Final[str] = "logs/qre_source_cache_readiness_materialization/"
_ARTIFACT_CACHE_DIR: Final[Path] = Path("artifacts/cache")
_ARTIFACT_MANIFEST_NAME: Final[str] = "cache_manifest_latest.v1.json"
_ARTIFACT_COVERAGE_NAME: Final[str] = "cache_coverage_latest.v1.json"
_ARTIFACT_WRITE_PREFIX: Final[str] = "artifacts/cache/"
_CACHE_MANIFEST_PATH: Final[Path] = Path("logs/qre_data_cache_manifest/latest.json")
_SOURCE_QUALITY_PATH: Final[Path] = Path("logs/qre_data_source_quality_readiness/latest.json")


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


def _artifact_status(status: Mapping[str, Any]) -> str:
    raw = str(status.get("status") or "")
    if raw == "ready":
        return "present_ready"
    if raw in {"not_ready", "invalid_manifest", "invalid_source_quality_report"}:
        return "present_not_ready"
    return "missing"


def _cache_sidecar_row(
    *,
    repo_root: Path,
    status: Mapping[str, Any],
    payload: Mapping[str, Any] | None,
) -> dict[str, Any]:
    summary = payload.get("summary") if isinstance(payload, Mapping) else {}
    coverage = payload.get("coverage") if isinstance(payload, Mapping) else []
    files = payload.get("files") if isinstance(payload, Mapping) else []
    if not isinstance(summary, Mapping):
        summary = {}
    if not isinstance(coverage, list):
        coverage = []
    if not isinstance(files, list):
        files = []
    artifact_status = _artifact_status(status)
    blocking_reasons: list[str] = []
    if artifact_status == "missing":
        blocking_reasons.append("cache_manifest_missing")
    elif not bool(status.get("research_ready")):
        blocking_reasons.append("cache_manifest_not_ready")
    return {
        "sidecar_kind": "cache_manifest",
        "path": str(status.get("path") or _CACHE_MANIFEST_PATH.as_posix()),
        "artifact_status": artifact_status,
        "research_ready": bool(status.get("research_ready")),
        "schema_version": payload.get("schema_version") if isinstance(payload, Mapping) else None,
        "coverage_row_count": len([row for row in coverage if isinstance(row, Mapping)]),
        "file_row_count": len([row for row in files if isinstance(row, Mapping)]),
        "ready_coverage_row_count": sum(
            1
            for row in coverage
            if isinstance(row, Mapping) and bool(row.get("ready"))
        ),
        "blocking_reasons": blocking_reasons,
        "operator_explanation": (
            "Cache manifest sidecar is present and research-ready."
            if artifact_status == "present_ready"
            else "Cache manifest sidecar is present but not research-ready."
            if artifact_status == "present_not_ready"
            else "Cache manifest sidecar is missing in this environment."
        ),
    }


def _source_sidecar_row(
    *,
    status: Mapping[str, Any],
    payload: Mapping[str, Any] | None,
) -> dict[str, Any]:
    summary = payload.get("summary") if isinstance(payload, Mapping) else {}
    rows = payload.get("rows") if isinstance(payload, Mapping) else []
    sources = payload.get("sources") if isinstance(payload, Mapping) else []
    if not isinstance(summary, Mapping):
        summary = {}
    if not isinstance(rows, list):
        rows = []
    if not isinstance(sources, list):
        sources = []
    artifact_status = _artifact_status(status)
    blocking_reasons: list[str] = []
    if artifact_status == "missing":
        blocking_reasons.append("source_quality_sidecar_missing")
    elif not bool(status.get("research_ready")):
        blocking_reasons.append("source_quality_sidecar_not_ready")
    return {
        "sidecar_kind": "source_quality",
        "path": str(status.get("path") or _SOURCE_QUALITY_PATH.as_posix()),
        "artifact_status": artifact_status,
        "research_ready": bool(status.get("research_ready")),
        "schema_version": payload.get("schema_version") if isinstance(payload, Mapping) else None,
        "row_count": len([row for row in rows if isinstance(row, Mapping)]),
        "source_count": len([row for row in sources if isinstance(row, Mapping)]),
        "ready_row_count": sum(
            1
            for row in rows
            if isinstance(row, Mapping) and str(row.get("quality_status") or "") == "ready"
        ),
        "blocking_reasons": blocking_reasons,
        "operator_explanation": (
            "Source quality sidecar is present and research-ready."
            if artifact_status == "present_ready"
            else "Source quality sidecar is present but not research-ready."
            if artifact_status == "present_not_ready"
            else "Source quality sidecar is missing in this environment."
        ),
    }


def _materialized_cache_manifest(
    *,
    cache_row: Mapping[str, Any],
    payload: Mapping[str, Any] | None,
) -> dict[str, Any]:
    payload = payload if isinstance(payload, Mapping) else {}
    summary = payload.get("summary") if isinstance(payload.get("summary"), Mapping) else {}
    cache_roots = payload.get("cache_roots")
    if not isinstance(cache_roots, list):
        cache_roots = []
    return {
        "schema_version": SCHEMA_VERSION,
        "report_kind": "qre_materialized_cache_manifest",
        "source_report_kind": payload.get("report_kind"),
        "source_path": cache_row.get("path"),
        "sidecar_status": cache_row.get("artifact_status"),
        "research_ready": cache_row.get("research_ready"),
        "summary": {
            "cache_file_count": int(summary.get("cache_file_count") or 0),
            "coverage_row_count": int(summary.get("coverage_row_count") or 0),
            "total_rows": int(summary.get("total_rows") or 0),
            "missing_roots": int(summary.get("missing_roots") or 0),
            "manifest_content_hash": summary.get("manifest_content_hash"),
            "research_ready": bool(summary.get("research_ready")),
            "file_row_count": int(summary.get("cache_file_count") or 0),
        },
        "cache_roots": [row for row in cache_roots if isinstance(row, Mapping)],
        "safety_invariants": {
            "read_only": True,
            "mutates_cache": False,
            "mutates_research_outputs": False,
            "mutates_frozen_contracts": False,
            "paper_shadow_live_forbidden": True,
            "broker_risk_execution_forbidden": True,
        },
    }


def _materialized_cache_coverage(
    *,
    cache_row: Mapping[str, Any],
    payload: Mapping[str, Any] | None,
) -> dict[str, Any]:
    payload = payload if isinstance(payload, Mapping) else {}
    coverage = payload.get("coverage")
    if not isinstance(coverage, list):
        coverage = []
    ready_rows = sum(
        1 for row in coverage if isinstance(row, Mapping) and bool(row.get("ready"))
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "report_kind": "qre_materialized_cache_coverage",
        "source_report_kind": payload.get("report_kind"),
        "source_path": cache_row.get("path"),
        "sidecar_status": cache_row.get("artifact_status"),
        "research_ready": cache_row.get("research_ready"),
        "summary": {
            "coverage_row_count": len([row for row in coverage if isinstance(row, Mapping)]),
            "ready_coverage_row_count": ready_rows,
            "blocked_coverage_row_count": len([row for row in coverage if isinstance(row, Mapping)])
            - ready_rows,
        },
        "coverage": [row for row in coverage if isinstance(row, Mapping)],
        "safety_invariants": {
            "read_only": True,
            "mutates_cache": False,
            "mutates_research_outputs": False,
            "mutates_frozen_contracts": False,
            "paper_shadow_live_forbidden": True,
            "broker_risk_execution_forbidden": True,
        },
    }


def build_source_cache_readiness_materialization(
    *,
    repo_root: Path = Path("."),
) -> dict[str, Any]:
    cache_status = cache_manifest.read_manifest_status(repo_root=repo_root)
    source_status = source_quality_readiness.read_source_quality_status(repo_root=repo_root)
    cache_payload = _read_json(repo_root / _CACHE_MANIFEST_PATH)
    source_payload = _read_json(repo_root / _SOURCE_QUALITY_PATH)

    cache_row = _cache_sidecar_row(
        repo_root=repo_root,
        status=cache_status,
        payload=cache_payload,
    )
    source_row = _source_sidecar_row(
        status=source_status,
        payload=source_payload,
    )
    rows = [cache_row, source_row]
    status_counts = Counter(str(row["artifact_status"]) for row in rows)
    blocking_counts = Counter(
        reason for row in rows for reason in row.get("blocking_reasons", [])
    )
    missing_sidecars = [
        str(row["sidecar_kind"])
        for row in rows
        if str(row["artifact_status"]) == "missing"
    ]
    not_ready_sidecars = [
        str(row["sidecar_kind"])
        for row in rows
        if str(row["artifact_status"]) == "present_not_ready"
    ]
    cache_materialized = _materialized_cache_manifest(
        cache_row=cache_row,
        payload=cache_payload,
    )
    coverage_materialized = _materialized_cache_coverage(
        cache_row=cache_row,
        payload=cache_payload,
    )
    both_ready = bool(cache_row["research_ready"]) and bool(source_row["research_ready"])
    return {
        "schema_version": SCHEMA_VERSION,
        "report_kind": REPORT_KIND,
        "summary": {
            "sidecar_count": len(rows),
            "sidecar_status_counts": dict(sorted(status_counts.items())),
            "blocking_reason_counts": dict(sorted(blocking_counts.items())),
            "cache_manifest_sidecar_status": str(cache_row["artifact_status"]),
            "source_quality_sidecar_status": str(source_row["artifact_status"]),
            "cache_manifest_research_ready": bool(cache_row["research_ready"]),
            "source_quality_research_ready": bool(source_row["research_ready"]),
            "cache_coverage_row_count": int(cache_row["coverage_row_count"]),
            "cache_ready_row_count": int(cache_row["ready_coverage_row_count"]),
            "source_quality_row_count": int(source_row["row_count"]),
            "source_quality_ready_row_count": int(source_row["ready_row_count"]),
            "missing_sidecars": missing_sidecars,
            "present_not_ready_sidecars": not_ready_sidecars,
            "source_cache_readiness_linked": both_ready,
            "operator_summary": (
                "Source/cache sidecar materialization makes missing or non-ready cache and "
                "source-quality sidecars explicit without fetching data, mutating cache, or "
                "unlocking readiness."
            ),
        },
        "rows": rows,
        "materialized_cache_manifest": cache_materialized,
        "materialized_cache_coverage": coverage_materialized,
        "safety_invariants": {
            "read_only": True,
            "mutates_cache": False,
            "mutates_research_outputs": False,
            "mutates_frozen_contracts": False,
            "paper_shadow_live_forbidden": True,
            "broker_risk_execution_forbidden": True,
            "promotion_forbidden": True,
        },
    }


def render_operator_summary(report: Mapping[str, Any]) -> str:
    summary = report.get("summary") or {}
    rows = report.get("rows") if isinstance(report.get("rows"), list) else []
    status_table = _table(
        ["Field", "Value"],
        [
            ["cache_manifest_sidecar_status", str(summary.get("cache_manifest_sidecar_status") or "")],
            ["source_quality_sidecar_status", str(summary.get("source_quality_sidecar_status") or "")],
            ["cache_manifest_research_ready", str(summary.get("cache_manifest_research_ready") or False)],
            ["source_quality_research_ready", str(summary.get("source_quality_research_ready") or False)],
            ["cache_coverage_row_count", str(summary.get("cache_coverage_row_count") or 0)],
            ["source_quality_row_count", str(summary.get("source_quality_row_count") or 0)],
            ["source_cache_readiness_linked", str(summary.get("source_cache_readiness_linked") or False)],
        ],
    )
    row_table = _table(
        ["Sidecar", "Status", "Research ready", "Blocking reasons", "Explanation"],
        [
            [
                str(row.get("sidecar_kind") or ""),
                str(row.get("artifact_status") or ""),
                str(row.get("research_ready") or False),
                ",".join(str(value) for value in row.get("blocking_reasons") or []) or "none",
                str(row.get("operator_explanation") or ""),
            ]
            for row in rows
        ],
    )
    return "\n".join(
        [
            "# QRE Source/Cache Readiness Materialization",
            "",
            "## 1. Korte conclusie",
            f"- {summary.get('operator_summary') or ''}",
            "",
            "## 2. Sidecar status",
            status_table,
            "",
            "## 3. Sidecar rows",
            row_table,
        ]
    )


def _validate_log_target(path: Path) -> None:
    if _WRITE_PREFIX not in path.as_posix():
        raise ValueError(
            f"qre_source_cache_readiness_materialization: refusing write outside allowlist: {path!r}"
        )


def _validate_artifact_target(path: Path) -> None:
    if _ARTIFACT_WRITE_PREFIX not in path.as_posix():
        raise ValueError(
            f"qre_source_cache_readiness_materialization: refusing artifact write outside allowlist: {path!r}"
        )


def write_outputs(
    report: Mapping[str, Any],
    *,
    repo_root: Path = Path("."),
) -> dict[str, str]:
    log_base = repo_root / DEFAULT_OUTPUT_DIR
    log_base.mkdir(parents=True, exist_ok=True)
    artifact_base = repo_root / _ARTIFACT_CACHE_DIR
    artifact_base.mkdir(parents=True, exist_ok=True)

    latest = log_base / LATEST_NAME
    summary_path = log_base / OPERATOR_SUMMARY_NAME
    artifact_manifest = artifact_base / _ARTIFACT_MANIFEST_NAME
    artifact_coverage = artifact_base / _ARTIFACT_COVERAGE_NAME
    for target in (latest, summary_path):
        _validate_log_target(target)
    for target in (artifact_manifest, artifact_coverage):
        _validate_artifact_target(target)

    latest_payload = json.dumps(report, indent=2, sort_keys=True) + "\n"
    tmp_latest = latest.with_suffix(latest.suffix + ".tmp")
    tmp_latest.write_text(latest_payload, encoding="utf-8")
    os.replace(tmp_latest, latest)

    tmp_summary = summary_path.with_suffix(summary_path.suffix + ".tmp")
    tmp_summary.write_text(render_operator_summary(report) + "\n", encoding="utf-8")
    os.replace(tmp_summary, summary_path)

    manifest_payload = json.dumps(
        report.get("materialized_cache_manifest") or {},
        indent=2,
        sort_keys=True,
    ) + "\n"
    tmp_manifest = artifact_manifest.with_suffix(artifact_manifest.suffix + ".tmp")
    tmp_manifest.write_text(manifest_payload, encoding="utf-8")
    os.replace(tmp_manifest, artifact_manifest)

    coverage_payload = json.dumps(
        report.get("materialized_cache_coverage") or {},
        indent=2,
        sort_keys=True,
    ) + "\n"
    tmp_coverage = artifact_coverage.with_suffix(artifact_coverage.suffix + ".tmp")
    tmp_coverage.write_text(coverage_payload, encoding="utf-8")
    os.replace(tmp_coverage, artifact_coverage)

    return {
        "latest": latest.relative_to(repo_root).as_posix(),
        "operator_summary": summary_path.relative_to(repo_root).as_posix(),
        "cache_manifest_artifact": artifact_manifest.relative_to(repo_root).as_posix(),
        "cache_coverage_artifact": artifact_coverage.relative_to(repo_root).as_posix(),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m research.qre_source_cache_readiness_materialization",
        description="Materialize read-only source/cache sidecar readiness state.",
    )
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args(argv)
    report = build_source_cache_readiness_materialization()
    if args.write:
        report["_artifact_paths"] = write_outputs(report)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
