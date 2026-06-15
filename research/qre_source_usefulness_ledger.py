"""Read-only source usefulness ledger over cache and source-quality sidecars.

The ledger tracks source utility, failures, false-positive proxies, and cache
hit proxies using existing local read-only sidecars only. It does not fetch
data, mutate caches, promote sources, or change trading authority.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections import Counter
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Final

SCHEMA_VERSION: Final[str] = "1.0"
REPORT_KIND: Final[str] = "qre_source_usefulness_ledger"
DEFAULT_OUTPUT_DIR: Final[Path] = Path("logs/qre_source_usefulness_ledger")
LATEST_NAME: Final[str] = "latest.json"
HISTORY_NAME: Final[str] = "history.jsonl"
SUMMARY_NAME: Final[str] = "operator_summary.md"
_WRITE_PREFIX: Final[str] = "logs/qre_source_usefulness_ledger/"
DEFAULT_CACHE_MANIFEST_PATH: Final[Path] = Path("logs/qre_data_cache_manifest/latest.json")
DEFAULT_SOURCE_QUALITY_PATH: Final[Path] = Path("logs/qre_data_source_quality_readiness/latest.json")


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


def _rows(payload: Mapping[str, Any] | None, key: str) -> list[dict[str, Any]]:
    rows = payload.get(key) if isinstance(payload, Mapping) else None
    if not isinstance(rows, list):
        return []
    return [row for row in rows if isinstance(row, dict)]


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


def _source_rows(
    *,
    cache_rows: list[dict[str, Any]],
    quality_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    cache_index: dict[str, list[dict[str, Any]]] = {}
    for row in cache_rows:
        source = str(row.get("source") or "unknown")
        cache_index.setdefault(source, []).append(row)

    quality_index: dict[str, list[dict[str, Any]]] = {}
    for row in quality_rows:
        source = str(row.get("source") or "unknown")
        quality_index.setdefault(source, []).append(row)

    rows: list[dict[str, Any]] = []
    for source in sorted(set(cache_index) | set(quality_index)):
        cache_source_rows = cache_index.get(source, [])
        quality_source_rows = quality_index.get(source, [])
        cache_ready_rows = [row for row in cache_source_rows if str(row.get("status") or "") == "ready"]
        quality_ready_rows = [row for row in quality_source_rows if str(row.get("quality_status") or "") == "ready"]
        cache_blocked_rows = [row for row in cache_source_rows if str(row.get("status") or "") != "ready"]
        quality_blocked_rows = [
            row for row in quality_source_rows if str(row.get("quality_status") or "") != "ready"
        ]
        blocked_reasons = Counter(
            reason for row in quality_blocked_rows for reason in row.get("blocking_reasons", [])
        )
        cache_hit_proxy_rows = len(cache_ready_rows)
        quality_failure_rows = len(quality_blocked_rows)
        false_positive_proxy_rows = sum(
            1
            for row in quality_blocked_rows
            if str(row.get("identity_confidence") or "") == "high"
        )
        ready_ratio = (
            round(cache_hit_proxy_rows / len(cache_source_rows), 6)
            if cache_source_rows
            else 0.0
        )
        usefulness_state = "useful" if cache_hit_proxy_rows > 0 and not quality_blocked_rows else "blocked"
        rows.append(
            {
                "source": source,
                "cache_file_count": len(cache_source_rows),
                "cache_ready_file_count": len(cache_ready_rows),
                "cache_blocked_file_count": len(cache_blocked_rows),
                "quality_row_count": len(quality_source_rows),
                "quality_ready_row_count": len(quality_ready_rows),
                "quality_blocked_row_count": len(quality_blocked_rows),
                "cache_hit_proxy_rows": cache_hit_proxy_rows,
                "quality_failure_rows": quality_failure_rows,
                "false_positive_proxy_rows": false_positive_proxy_rows,
                "ready_ratio": ready_ratio,
                "blocked_reason_counts": dict(sorted(blocked_reasons.items())),
                "usefulness_state": usefulness_state,
                "operator_explanation": (
                    f"{source} usefulness is derived from existing cache and quality sidecars; "
                    "it remains advisory and read-only."
                ),
            }
        )

    rows.sort(key=lambda row: row["source"])
    return rows


def build_source_usefulness_ledger(
    *,
    repo_root: Path = Path("."),
    cache_manifest_path: Path = DEFAULT_CACHE_MANIFEST_PATH,
    source_quality_path: Path = DEFAULT_SOURCE_QUALITY_PATH,
) -> dict[str, Any]:
    cache_file = repo_root / cache_manifest_path
    source_file = repo_root / source_quality_path
    cache_payload = _read_json(cache_file)
    source_payload = _read_json(source_file)
    cache_summary = cache_payload.get("summary") if isinstance(cache_payload, Mapping) else {}
    source_summary = source_payload.get("summary") if isinstance(source_payload, Mapping) else {}
    if not isinstance(cache_summary, Mapping):
        cache_summary = {}
    if not isinstance(source_summary, Mapping):
        source_summary = {}

    cache_ready = bool(cache_summary.get("research_ready"))
    source_ready = bool(source_summary.get("research_ready"))
    cache_rows = _rows(cache_payload, "files")
    quality_rows = _rows(source_payload, "rows")
    rows = _source_rows(cache_rows=cache_rows, quality_rows=quality_rows)
    row_status_counts = Counter(str(row["usefulness_state"]) for row in rows)
    blocked_reason_counts = Counter(
        reason for row in rows for reason in row.get("blocked_reason_counts", {})
    )
    ready_source_count = sum(1 for row in rows if row["usefulness_state"] == "useful")
    blocked_source_count = sum(1 for row in rows if row["usefulness_state"] == "blocked")
    cache_hit_proxy_rows = sum(int(row["cache_hit_proxy_rows"]) for row in rows)
    quality_failure_rows = sum(int(row["quality_failure_rows"]) for row in rows)
    false_positive_proxy_rows = sum(int(row["false_positive_proxy_rows"]) for row in rows)
    total_cache_rows = sum(int(row.get("row_count") or 0) for row in cache_rows if isinstance(row, Mapping))
    ready_cache_rows = sum(
        int(row.get("row_count") or 0)
        for row in cache_rows
        if isinstance(row, Mapping) and str(row.get("status") or "") == "ready"
    )
    cache_hit_ratio = round(ready_cache_rows / total_cache_rows, 6) if total_cache_rows else 0.0
    blockers: list[dict[str, Any]] = []
    if not cache_payload:
        blockers.append(
            _blocker(
                reason="cache_manifest_missing",
                evidence_field="cache_manifest",
                evidence_status="missing",
                operator_explanation=(
                    "The cache manifest sidecar is missing, so source usefulness "
                    "cannot be established."
                ),
            )
        )
    elif not cache_ready:
        blockers.append(
            _blocker(
                reason="cache_manifest_not_research_ready",
                evidence_field="cache_manifest.summary.research_ready",
                evidence_status="false",
                operator_explanation=(
                    "The cache manifest sidecar is present but not research-ready."
                ),
            )
        )
    if not source_payload:
        blockers.append(
            _blocker(
                reason="source_quality_missing",
                evidence_field="source_quality",
                evidence_status="missing",
                operator_explanation=(
                    "The source-quality sidecar is missing, so usefulness cannot be established."
                ),
            )
        )
    elif not source_ready:
        blockers.append(
            _blocker(
                reason="source_quality_not_research_ready",
                evidence_field="source_quality.summary.research_ready",
                evidence_status="false",
                operator_explanation=(
                    "The source-quality sidecar is present but not research-ready."
                ),
            )
        )
    if not rows:
        blockers.append(
            _blocker(
                reason="source_rows_missing",
                evidence_field="rows",
                evidence_status="missing",
                operator_explanation=(
                    "No source rows are available, so the ledger fails closed."
                ),
            )
        )
    ledger_ready = not blockers
    return {
        "schema_version": SCHEMA_VERSION,
        "report_kind": REPORT_KIND,
        "summary": {
            "status": "ready" if ledger_ready else "not_ready",
            "research_ready": ledger_ready,
            "cache_manifest_ready": cache_ready,
            "source_quality_ready": source_ready,
            "source_count": len(rows),
            "ready_source_count": ready_source_count,
            "blocked_source_count": blocked_source_count,
            "cache_hit_proxy_rows": cache_hit_proxy_rows,
            "quality_failure_rows": quality_failure_rows,
            "false_positive_proxy_rows": false_positive_proxy_rows,
            "cache_hit_ratio": cache_hit_ratio,
            "row_status_counts": dict(sorted(row_status_counts.items())),
            "blocked_reason_counts": dict(sorted(blocked_reason_counts.items())),
            "blocking_reasons": [row["reason"] for row in blockers],
            "operator_summary": (
                "Source usefulness is read-only and advisory; it aggregates cache and "
                "source-quality sidecars into utility, failure, and false-positive proxies."
            ),
        },
        "cache_manifest_reference": {
            "path": _rel(cache_file, root=repo_root),
            "research_ready": cache_ready,
            "schema_version": cache_payload.get("schema_version") if isinstance(cache_payload, Mapping) else None,
        },
        "source_quality_reference": {
            "path": _rel(source_file, root=repo_root),
            "research_ready": source_ready,
            "schema_version": source_payload.get("schema_version") if isinstance(source_payload, Mapping) else None,
        },
        "rows": rows,
        "blockers": blockers,
        "safety_invariants": {
            "read_only": True,
            "fetches_external_data": False,
            "mutates_cache": False,
            "mutates_research_outputs": False,
            "frozen_contracts_unchanged": True,
            "paper_shadow_live_forbidden": True,
            "broker_risk_execution_forbidden": True,
            "source_usefulness_is_not_alpha": True,
            "source_usefulness_is_not_trading_authority": True,
        },
    }


def _validate_write_target(path: Path) -> None:
    normalized = path.as_posix()
    if _WRITE_PREFIX not in normalized:
        raise ValueError(
            "qre_source_usefulness_ledger: refusing write outside allowlist: " f"{path!r}"
        )


def _table(headers: Sequence[str], rows: Sequence[Sequence[str]]) -> str:
    head = "| " + " | ".join(headers) + " |"
    divider = "| " + " | ".join(["---"] * len(headers)) + " |"
    body = ["| " + " | ".join(row) + " |" for row in rows]
    return "\n".join([head, divider, *body])


def render_operator_summary(report: Mapping[str, Any]) -> str:
    summary = report.get("summary") if isinstance(report.get("summary"), Mapping) else {}
    rows = report.get("rows") if isinstance(report.get("rows"), list) else []
    summary_table = _table(
        ["Field", "Value"],
        [
            ["status", str(summary.get("status") or "")],
            ["research_ready", str(summary.get("research_ready") or False)],
            ["cache_manifest_ready", str(summary.get("cache_manifest_ready") or False)],
            ["source_quality_ready", str(summary.get("source_quality_ready") or False)],
            ["source_count", str(summary.get("source_count") or 0)],
            ["ready_source_count", str(summary.get("ready_source_count") or 0)],
            ["blocked_source_count", str(summary.get("blocked_source_count") or 0)],
            ["cache_hit_ratio", str(summary.get("cache_hit_ratio") or 0.0)],
        ],
    )
    row_table = _table(
        ["Source", "State", "Cache files", "Quality rows", "False-positive proxy", "Explanation"],
        [
            [
                str(row.get("source") or ""),
                str(row.get("usefulness_state") or ""),
                str(row.get("cache_file_count") or 0),
                str(row.get("quality_row_count") or 0),
                str(row.get("false_positive_proxy_rows") or 0),
                str(row.get("operator_explanation") or ""),
            ]
            for row in rows
            if isinstance(row, Mapping)
        ],
    )
    return "\n".join(
        [
            "# QRE Source Usefulness Ledger",
            "",
            "## 1. Korte conclusie",
            f"- {summary.get('operator_summary') or ''}",
            "",
            "## 2. Ledger status",
            summary_table,
            "",
            "## 3. Source rows",
            row_table,
        ]
    )


def write_outputs(
    report: Mapping[str, Any],
    *,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    repo_root: Path = Path("."),
) -> dict[str, str]:
    base = repo_root / output_dir
    base.mkdir(parents=True, exist_ok=True)
    timestamp = str(report["summary"].get("status") or report["schema_version"]).replace(":", "-")
    latest = base / LATEST_NAME
    timestamped = base / f"{timestamp}.json"
    history = base / HISTORY_NAME
    summary_path = base / SUMMARY_NAME
    payload = json.dumps(report, sort_keys=True, indent=2) + "\n"

    for target in (latest, timestamped, history, summary_path):
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

    tmp_summary = summary_path.with_suffix(summary_path.suffix + ".tmp")
    tmp_summary.write_text(render_operator_summary(report) + "\n", encoding="utf-8")
    os.replace(tmp_summary, summary_path)

    return {
        "latest": latest.relative_to(repo_root).as_posix(),
        "timestamped": timestamped.relative_to(repo_root).as_posix(),
        "history": history.relative_to(repo_root).as_posix(),
        "operator_summary": summary_path.relative_to(repo_root).as_posix(),
    }


def read_ledger_status(
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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m research.qre_source_usefulness_ledger",
        description="Build a read-only source usefulness ledger from local sidecars.",
    )
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--status", action="store_true")
    args = parser.parse_args(argv)

    if args.status:
        print(json.dumps(read_ledger_status(), sort_keys=True, indent=2))
        return 0

    report = build_source_usefulness_ledger()
    if args.write:
        report["_artifact_paths"] = write_outputs(report)
    print(json.dumps(report, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())


__all__ = [
    "DEFAULT_CACHE_MANIFEST_PATH",
    "DEFAULT_OUTPUT_DIR",
    "DEFAULT_SOURCE_QUALITY_PATH",
    "HISTORY_NAME",
    "LATEST_NAME",
    "REPORT_KIND",
    "SCHEMA_VERSION",
    "build_source_usefulness_ledger",
    "read_ledger_status",
    "render_operator_summary",
    "write_outputs",
]
