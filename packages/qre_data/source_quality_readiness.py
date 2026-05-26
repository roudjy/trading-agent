"""Read-only source identity and quality readiness over cache manifests."""

from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import json
import os
import sys
from collections import Counter
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Final

from packages.qre_data.cache_manifest import (
    DEFAULT_OUTPUT_DIR as DEFAULT_MANIFEST_DIR,
)
from packages.qre_data.cache_manifest import (
    LATEST_NAME,
)

SCHEMA_VERSION: Final[str] = "1.0"
REPORT_KIND: Final[str] = "qre_data_source_quality_readiness"
DEFAULT_OUTPUT_DIR: Final[Path] = Path("logs/qre_data_source_quality_readiness")
HISTORY_NAME: Final[str] = "history.jsonl"
_WRITE_PREFIX: Final[str] = "logs/qre_data_source_quality_readiness/"
_UNKNOWN_VALUES: Final[set[str]] = {"", "unknown", "none", "null", "nan"}
READINESS_BLOCKER_CATEGORIES: Final[tuple[str, ...]] = ("data", "source", "identity")
ADDENDUM3_REFERENCE_TAXONOMY: Final[tuple[str, ...]] = (
    "source_manifest",
    "source_identity",
    "freshness",
    "coverage",
    "missing_data",
    "timestamp_integrity",
    "source_agreement",
    "schema_version",
)


def _utcnow() -> str:
    return (
        _dt.datetime.now(_dt.UTC)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def _rel(path: Path, *, root: Path) -> str:
    try:
        return path.relative_to(root).as_posix()
    except ValueError:
        return path.as_posix()


def _is_known(value: Any) -> bool:
    return str(value).strip().lower() not in _UNKNOWN_VALUES


def _identity_confidence(row: Mapping[str, Any]) -> str:
    required = (
        row.get("source"),
        row.get("instrument"),
        row.get("timeframe"),
        row.get("cache_kind"),
    )
    known_count = sum(1 for value in required if _is_known(value))
    if known_count == len(required):
        return "high"
    if known_count == 0:
        return "unknown"
    return "low"


def _blocking_reasons(row: Mapping[str, Any], confidence: str) -> list[str]:
    reasons: list[str] = []
    if confidence != "high":
        reasons.append("identity_not_high_confidence")
    if row.get("status") != "ready":
        reasons.append(f"manifest_status_{row.get('status') or 'missing'}")
    if not isinstance(row.get("row_count"), int) or int(row["row_count"]) <= 0:
        reasons.append("row_count_not_positive")
    if not row.get("min_timestamp_utc") or not row.get("max_timestamp_utc"):
        reasons.append("timestamp_range_missing")
    if not row.get("content_hash"):
        reasons.append("content_hash_missing")
    return reasons


def _blocker(
    *,
    category: str,
    reason: str,
    evidence_field: str,
    evidence_status: str,
    operator_explanation: str,
) -> dict[str, Any]:
    if category not in READINESS_BLOCKER_CATEGORIES:
        raise ValueError(f"unknown readiness blocker category: {category!r}")
    return {
        "category": category,
        "reason": reason,
        "evidence_field": evidence_field,
        "evidence_status": evidence_status,
        "fail_closed": True,
        "operator_explanation": operator_explanation,
    }


def _unknown_identity_blockers(row: Mapping[str, Any]) -> list[dict[str, Any]]:
    fields = (
        ("source", "identity_source_unknown"),
        ("instrument", "identity_instrument_unknown"),
        ("timeframe", "identity_timeframe_unknown"),
        ("cache_kind", "identity_cache_kind_unknown"),
    )
    blockers: list[dict[str, Any]] = []
    for field, reason in fields:
        if _is_known(row.get(field)):
            continue
        blockers.append(
            _blocker(
                category="identity",
                reason=reason,
                evidence_field=field,
                evidence_status="missing_or_unknown",
                operator_explanation=(
                    f"Identity evidence field {field} is missing or unknown; "
                    "source readiness fails closed until the manifest identifies it."
                ),
            )
        )
    return blockers


def _readiness_blockers(
    row: Mapping[str, Any],
    *,
    confidence: str,
) -> list[dict[str, Any]]:
    blockers = _unknown_identity_blockers(row)
    if confidence != "high" and not blockers:
        blockers.append(
            _blocker(
                category="identity",
                reason="identity_not_high_confidence",
                evidence_field="source_identity",
                evidence_status=confidence,
                operator_explanation=(
                    "Source identity evidence is not high confidence; readiness "
                    "fails closed until identity is complete."
                ),
            )
        )

    manifest_status = row.get("status")
    if manifest_status != "ready":
        status = str(manifest_status or "missing")
        blockers.append(
            _blocker(
                category="source",
                reason="source_manifest_status_not_ready",
                evidence_field="status",
                evidence_status=status,
                operator_explanation=(
                    f"Source manifest status is {status}; source readiness "
                    "requires ready manifest evidence."
                ),
            )
        )
    if not row.get("content_hash"):
        blockers.append(
            _blocker(
                category="source",
                reason="source_content_hash_missing",
                evidence_field="content_hash",
                evidence_status="missing",
                operator_explanation=(
                    "Source content hash is missing; reproducibility evidence "
                    "is incomplete."
                ),
            )
        )

    if not isinstance(row.get("row_count"), int) or int(row["row_count"]) <= 0:
        blockers.append(
            _blocker(
                category="data",
                reason="data_row_count_not_positive",
                evidence_field="row_count",
                evidence_status="missing_or_non_positive",
                operator_explanation=(
                    "Data row count is missing, unknown, or non-positive; "
                    "data readiness fails closed."
                ),
            )
        )
    if not row.get("min_timestamp_utc") or not row.get("max_timestamp_utc"):
        blockers.append(
            _blocker(
                category="data",
                reason="data_timestamp_range_missing",
                evidence_field="timestamp_range",
                evidence_status="missing",
                operator_explanation=(
                    "Data timestamp range is missing; freshness and coverage "
                    "cannot be verified."
                ),
            )
        )
    return sorted(blockers, key=lambda row: (row["category"], row["reason"]))


def _explanation(
    row: Mapping[str, Any],
    *,
    confidence: str,
    blocking_reasons: Sequence[str],
) -> str:
    identity = (
        f"{row.get('source', 'unknown')}/"
        f"{row.get('instrument', 'unknown')}/"
        f"{row.get('timeframe', 'unknown')}"
    )
    if not blocking_reasons:
        return f"{identity} has high-confidence identity and ready manifest evidence."
    return (
        f"{identity} is not research-ready because "
        f"{', '.join(blocking_reasons)}; identity confidence is {confidence}."
    )


def _evaluate_file(row: Mapping[str, Any]) -> dict[str, Any]:
    confidence = _identity_confidence(row)
    reasons = _blocking_reasons(row, confidence)
    readiness_blockers = _readiness_blockers(row, confidence=confidence)
    quality_status = "ready" if not reasons else "blocked"
    return {
        "path": row.get("path"),
        "cache_kind": row.get("cache_kind"),
        "source": row.get("source"),
        "instrument": row.get("instrument"),
        "timeframe": row.get("timeframe"),
        "identity_confidence": confidence,
        "quality_status": quality_status,
        "blocking_reasons": reasons,
        "readiness_blockers": readiness_blockers,
        "manifest_status": row.get("status"),
        "row_count": row.get("row_count"),
        "min_timestamp_utc": row.get("min_timestamp_utc"),
        "max_timestamp_utc": row.get("max_timestamp_utc"),
        "content_hash": row.get("content_hash"),
        "operator_explanation": _explanation(
            row,
            confidence=confidence,
            blocking_reasons=reasons,
        ),
    }


def _source_summaries(rows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[Mapping[str, Any]]] = {}
    for row in rows:
        grouped.setdefault(str(row.get("source") or "unknown"), []).append(row)

    summaries: list[dict[str, Any]] = []
    for source, source_rows in grouped.items():
        confidence_counts = Counter(str(row["identity_confidence"]) for row in source_rows)
        quality_counts = Counter(str(row["quality_status"]) for row in source_rows)
        blocking = Counter(
            reason for row in source_rows for reason in row.get("blocking_reasons", [])
        )
        readiness_blockers = [
            blocker
            for row in source_rows
            for blocker in row.get("readiness_blockers", [])
            if isinstance(blocker, Mapping)
        ]
        blocker_categories = Counter(
            str(blocker.get("category")) for blocker in readiness_blockers
        )
        blocker_reasons = Counter(
            str(blocker.get("reason")) for blocker in readiness_blockers
        )
        summaries.append(
            {
                "source": source,
                "file_count": len(source_rows),
                "identity_confidence_counts": dict(sorted(confidence_counts.items())),
                "quality_status_counts": dict(sorted(quality_counts.items())),
                "blocking_reason_counts": dict(sorted(blocking.items())),
                "readiness_blocker_category_counts": dict(sorted(blocker_categories.items())),
                "readiness_blocker_reason_counts": dict(sorted(blocker_reasons.items())),
                "ready": quality_counts.get("blocked", 0) == 0,
            }
        )
    summaries.sort(key=lambda row: row["source"])
    return summaries


def _manifest_files(manifest: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    files = manifest.get("files")
    if not isinstance(files, list):
        return []
    return [row for row in files if isinstance(row, Mapping)]


def build_source_quality_report(
    manifest: Mapping[str, Any],
    *,
    generated_at_utc: str | None = None,
) -> dict[str, Any]:
    when = generated_at_utc or _utcnow()
    files = _manifest_files(manifest)
    rows = [_evaluate_file(row) for row in files]
    rows.sort(key=lambda row: str(row.get("path") or ""))
    source_summaries = _source_summaries(rows)

    identity_counts = Counter(str(row["identity_confidence"]) for row in rows)
    quality_counts = Counter(str(row["quality_status"]) for row in rows)
    blocking_counts = Counter(reason for row in rows for reason in row.get("blocking_reasons", []))
    readiness_blockers = [
        blocker
        for row in rows
        for blocker in row.get("readiness_blockers", [])
        if isinstance(blocker, Mapping)
    ]
    blocker_category_counts = Counter(
        str(blocker.get("category")) for blocker in readiness_blockers
    )
    blocker_reason_counts = Counter(str(blocker.get("reason")) for blocker in readiness_blockers)
    manifest_summary = (
        manifest.get("summary") if isinstance(manifest.get("summary"), Mapping) else {}
    )
    manifest_ready = bool(manifest_summary.get("research_ready"))
    source_quality_ready = bool(rows) and quality_counts.get("blocked", 0) == 0
    research_ready = manifest_ready and source_quality_ready
    evidence_hash = hashlib.sha256(
        "|".join(str(row.get("content_hash") or "") for row in rows).encode("utf-8")
    ).hexdigest()

    if not files:
        operator_summary = (
            "No manifest file rows are available; data/source/identity readiness "
            "fails closed."
        )
    elif research_ready:
        operator_summary = (
            "All manifest rows have high-confidence source identity and ready quality evidence."
        )
    else:
        categories = ", ".join(sorted(blocker_category_counts)) or "unknown"
        operator_summary = (
            "Source quality is not research-ready; inspect data/source/identity "
            f"readiness blockers ({categories}) and row explanations."
        )
    report_readiness_blockers = []
    if not files:
        report_readiness_blockers.append(
            _blocker(
                category="data",
                reason="data_source_rows_missing",
                evidence_field="files",
                evidence_status="missing",
                operator_explanation=(
                    "No manifest file rows are available, so data/source/identity "
                    "readiness cannot be established."
                ),
            )
        )
    if not manifest_ready:
        report_readiness_blockers.append(
            _blocker(
                category="source",
                reason="source_manifest_research_not_ready",
                evidence_field="summary.research_ready",
                evidence_status="false_or_missing",
                operator_explanation=(
                    "The upstream cache manifest is not research-ready; source "
                    "readiness fails closed."
                ),
            )
        )

    return {
        "schema_version": SCHEMA_VERSION,
        "report_kind": REPORT_KIND,
        "source_manifest_schema_version": manifest.get("schema_version"),
        "generated_at_utc": when,
        "mode": "dry-run",
        "safe_to_execute": False,
        "summary": {
            "status": "ready" if research_ready else "not_ready",
            "research_ready": research_ready,
            "source_quality_ready": source_quality_ready,
            "manifest_research_ready": manifest_ready,
            "fail_closed": not research_ready,
            "file_count": len(rows),
            "source_count": len({str(row.get("source")) for row in rows}),
            "identity_confidence_counts": dict(sorted(identity_counts.items())),
            "quality_status_counts": dict(sorted(quality_counts.items())),
            "blocking_reason_counts": dict(sorted(blocking_counts.items())),
            "readiness_blocker_category_counts": dict(sorted(blocker_category_counts.items())),
            "readiness_blocker_reason_counts": dict(sorted(blocker_reason_counts.items())),
            "report_readiness_blockers": report_readiness_blockers,
            "evidence_content_hash": f"sha256:{evidence_hash}",
            "operator_summary": operator_summary,
        },
        "sources": source_summaries,
        "rows": rows,
        "safety_invariants": {
            "read_only": True,
            "fetches_external_data": False,
            "activates_vendor_sources": False,
            "mutates_cache": False,
            "mutates_research_outputs": False,
            "frozen_contracts_unchanged": True,
            "paper_shadow_live_forbidden": True,
            "broker_risk_execution_forbidden": True,
            "addendum3_reference_taxonomy_only": True,
            "activates_addendum3_runtime": False,
            "source_quality_as_alpha": False,
            "source_quality_as_promotion_authority": False,
        },
        "reference_taxonomy": {
            "source": "Roadmap v6 Addendum 3",
            "runtime_activation": False,
            "terms": list(ADDENDUM3_REFERENCE_TAXONOMY),
        },
    }


def _validate_write_target(path: Path) -> None:
    normalized = path.as_posix()
    if _WRITE_PREFIX not in normalized:
        raise ValueError(
            "qre_data_source_quality_readiness: refusing write outside allowlist: " f"{path!r}"
        )


def write_source_quality_outputs(
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
    payload = json.dumps(report, sort_keys=True, indent=2) + "\n"

    for target in (latest, timestamped, history):
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

    return {
        "latest": _rel(latest, root=repo_root),
        "timestamped": _rel(timestamped, root=repo_root),
        "history": _rel(history, root=repo_root),
    }


def read_source_quality_status(
    *,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    repo_root: Path = Path("."),
) -> dict[str, Any]:
    latest = repo_root / output_dir / LATEST_NAME
    if not latest.is_file():
        return {
            "status": "missing_source_quality_report",
            "research_ready": False,
            "path": _rel(latest, root=repo_root),
            "fails_closed": True,
        }
    try:
        payload = json.loads(latest.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {
            "status": "invalid_source_quality_report",
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


def _load_latest_manifest(*, manifest_dir: Path, repo_root: Path) -> dict[str, Any] | None:
    latest = repo_root / manifest_dir / LATEST_NAME
    if not latest.is_file():
        return None
    try:
        payload = json.loads(latest.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _missing_manifest_report(*, generated_at_utc: str | None = None) -> dict[str, Any]:
    return build_source_quality_report(
        {
            "schema_version": None,
            "summary": {"research_ready": False},
            "files": [],
        },
        generated_at_utc=generated_at_utc,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="packages.qre_data.source_quality_readiness",
        description="Build a read-only source identity and quality readiness report.",
    )
    parser.add_argument("--no-write", action="store_true")
    parser.add_argument("--status", action="store_true")
    parser.add_argument("--frozen-utc", type=str, default=None)
    parser.add_argument("--manifest-dir", type=Path, default=DEFAULT_MANIFEST_DIR)
    args = parser.parse_args(argv)

    if args.status:
        print(json.dumps(read_source_quality_status(), sort_keys=True, indent=2))
        return 0

    manifest = _load_latest_manifest(manifest_dir=args.manifest_dir, repo_root=Path("."))
    report = (
        build_source_quality_report(manifest, generated_at_utc=args.frozen_utc)
        if manifest is not None
        else _missing_manifest_report(generated_at_utc=args.frozen_utc)
    )
    if not args.no_write:
        report["_artifact_paths"] = write_source_quality_outputs(report)
    print(json.dumps(report, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())


__all__ = [
    "ADDENDUM3_REFERENCE_TAXONOMY",
    "DEFAULT_OUTPUT_DIR",
    "REPORT_KIND",
    "READINESS_BLOCKER_CATEGORIES",
    "SCHEMA_VERSION",
    "build_source_quality_report",
    "read_source_quality_status",
    "write_source_quality_outputs",
]
