"""Read-only KPI completeness and historical snapshot reporter for ADE-QRE-017E."""

from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import importlib
import json
import os
import tempfile
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Final

from reporting import trusted_loop_materialization as _trusted_loop_materialization

REPO_ROOT: Final[Path] = Path(__file__).resolve().parent.parent
MODULE_VERSION: Final[str] = "ade-qre-017e-2026-06-26"
SCHEMA_VERSION: Final[int] = 1
REPORT_KIND: Final[str] = "qre_kpi_snapshot_completeness"

ARTIFACT_DIR: Final[Path] = REPO_ROOT / "logs" / "qre_kpi_snapshot_completeness"
ARTIFACT_LATEST: Final[Path] = ARTIFACT_DIR / "latest.json"
MARKDOWN_LATEST: Final[Path] = ARTIFACT_DIR / "operator_summary.md"
_WRITE_PREFIX: Final[str] = "logs/qre_kpi_snapshot_completeness/"

_OPERATIONAL_KPI_ORDER: Final[tuple[str, ...]] = (
    "basket_inventory_count",
    "diagnosable_basket_count",
    "routing_ready_count",
    "sampling_ready_count",
    "reason_record_count",
    "reason_record_coverage_pct",
    "failure_actionable_count",
    "failure_actionability_pct",
    "source_ready_basket_pct",
    "evidence_complete_basket_pct",
    "duplicate_suppression_candidates",
    "unknown_failure_rate",
    "operator_explanation_completeness_score",
)


def _research_module(module_name: str) -> Any:
    return importlib.import_module(module_name)


def _utcnow() -> str:
    return (
        _dt.datetime.now(_dt.UTC)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def _rel(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(REPO_ROOT.resolve())).replace("\\", "/")
    except ValueError:
        return str(path).replace("\\", "/")


def _validate_write_target(path: Path) -> None:
    normalized = str(path).replace("\\", "/")
    if _WRITE_PREFIX not in normalized:
        raise ValueError(
            "qre_kpi_snapshot_completeness: refusing write outside allowlist: "
            f"{path!r}"
        )


def _stable_hash(payload: Mapping[str, Any]) -> str:
    compact = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(compact.encode("utf-8")).hexdigest()


def _bounded_str(value: Any, *, max_len: int = 240) -> str:
    text = str(value or "").strip()
    if len(text) <= max_len:
        return text
    return text[: max_len - 3].rstrip() + "..."


def _numeric(value: Any) -> int | float | None:
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    return value


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _research_quality_rows(snapshot: Mapping[str, Any]) -> list[dict[str, Any]]:
    readiness = _mapping(snapshot.get("research_quality_kpi_readiness"))
    values = _mapping(readiness.get("values"))
    rows: list[dict[str, Any]] = []
    for kpi_id, raw_row in sorted(values.items()):
        row = _mapping(raw_row)
        numeric_value = _numeric(row.get("value"))
        available_components = row.get("available_components")
        rows.append(
            {
                "kpi_family": "research_quality",
                "kpi_id": str(kpi_id),
                "status": "numeric" if numeric_value is not None else "explicit_unavailable",
                "value": numeric_value,
                "source": _bounded_str(row.get("source") or "trusted_loop_materialization"),
                "required_evidence": list(row.get("required_evidence") or []),
                "missing_evidence": list(row.get("missing_evidence") or []),
                "partial_evidence_count": int(row.get("partial_evidence_count") or 0),
                "available_components": (
                    dict(sorted(available_components.items()))
                    if isinstance(available_components, Mapping)
                    else {}
                ),
                "note": (
                    "numeric_value_ready"
                    if numeric_value is not None
                    else "explicit_unavailable_fail_closed"
                ),
            }
        )
    return rows


def _operational_rows(report: Mapping[str, Any]) -> list[dict[str, Any]]:
    summary = _mapping(report.get("summary"))
    rows: list[dict[str, Any]] = []
    for kpi_id in _OPERATIONAL_KPI_ORDER:
        value = _numeric(summary.get(kpi_id))
        rows.append(
            {
                "kpi_family": "trusted_loop_operational",
                "kpi_id": kpi_id,
                "status": "numeric" if value is not None else "explicit_unavailable",
                "value": value,
                "source": "research.qre_trusted_loop_operator_kpis.summary",
                "required_evidence": [],
                "missing_evidence": [] if value is not None else ["summary_numeric_value_missing"],
                "partial_evidence_count": 0,
                "available_components": {},
                "note": (
                    "aggregated_numeric_projection"
                    if value is not None
                    else "explicit_unavailable_missing_summary_value"
                ),
            }
        )
    return rows


def collect_snapshot(
    *,
    repo_root: Path = REPO_ROOT,
    max_candidates: int = 15,
    frozen_utc: str | None = None,
) -> dict[str, Any]:
    generated_at_utc = frozen_utc or _utcnow()
    trusted_loop_kpis = _research_module("research.qre_trusted_loop_operator_kpis")
    trusted_loop_report = trusted_loop_kpis.build_trusted_loop_operator_kpis(
        repo_root=repo_root,
        max_candidates=max_candidates,
    )
    materialized = _trusted_loop_materialization.collect_snapshot(
        frozen_utc=generated_at_utc
    )

    research_quality_rows = _research_quality_rows(materialized)
    operational_rows = _operational_rows(trusted_loop_report)
    all_rows = research_quality_rows + operational_rows
    numeric_count = sum(1 for row in all_rows if row["status"] == "numeric")
    unavailable_count = sum(
        1 for row in all_rows if row["status"] == "explicit_unavailable"
    )
    trusted_summary = _mapping(trusted_loop_report.get("summary"))
    snapshot_id = _stable_hash(
        {
            "generated_at_utc": generated_at_utc,
            "research_quality_rows": research_quality_rows,
            "operational_rows": operational_rows,
            "trusted_loop_maturity_state": trusted_summary.get("trusted_loop_maturity_state"),
        }
    )

    return {
        "generated_at_utc": generated_at_utc,
        "module_version": MODULE_VERSION,
        "schema_version": SCHEMA_VERSION,
        "report_kind": REPORT_KIND,
        "snapshot_identity": {
            "snapshot_id": snapshot_id,
            "max_candidates": max_candidates,
            "source_report_kinds": {
                "trusted_loop_operator_kpis": _bounded_str(
                    trusted_loop_report.get("report_kind")
                ),
                "trusted_loop_materialization": _bounded_str(
                    materialized.get("report_kind")
                ),
            },
        },
        "source_status": {
            "trusted_loop_operator_kpis": {
                "report_kind": _bounded_str(trusted_loop_report.get("report_kind")),
                "available": bool(trusted_loop_report),
                "final_recommendation": _bounded_str(
                    trusted_summary.get("final_recommendation")
                ),
            },
            "trusted_loop_materialization": {
                "report_kind": _bounded_str(materialized.get("report_kind")),
                "available": bool(materialized),
                "final_recommendation": _bounded_str(
                    materialized.get("final_recommendation")
                ),
            },
        },
        "kpi_rows": all_rows,
        "summary": {
            "total_kpi_count": len(all_rows),
            "numeric_value_count": numeric_count,
            "explicit_unavailable_count": unavailable_count,
            "all_kpis_numeric_or_explicit_unavailable": (
                numeric_count + unavailable_count == len(all_rows)
            ),
            "research_quality_complete_value_count": int(
                _mapping(materialized.get("research_quality_kpi_readiness")).get(
                    "complete_value_count"
                )
                or 0
            ),
            "research_quality_fail_closed_count": int(
                _mapping(materialized.get("research_quality_kpi_readiness")).get(
                    "fail_closed_count"
                )
                or 0
            ),
            "trusted_loop_maturity_state": _bounded_str(
                trusted_summary.get("trusted_loop_maturity_state")
            ),
            "operator_summary": (
                "KPI snapshot completeness combines current trusted-loop operational KPI "
                "projection with research-quality KPI readiness. Every row is either "
                "numeric or explicitly unavailable, and historical snapshots preserve "
                "evidence time context without mutating runtime behavior."
            ),
            "final_recommendation": "kpi_snapshot_completeness_ready",
            "exact_next_action": "preserve_snapshot_history_and_use_explicit_unavailable_states",
        },
        "safety_invariants": {
            "read_only": True,
            "mutates_frozen_contracts": False,
            "mutates_strategy_or_registry": False,
            "paper_shadow_live_forbidden": True,
            "broker_risk_execution_forbidden": True,
        },
    }


def render_operator_summary(snapshot: Mapping[str, Any]) -> str:
    summary = _mapping(snapshot.get("summary"))
    rows = snapshot.get("kpi_rows")
    if not isinstance(rows, list):
        rows = []
    lines = [
        "# QRE KPI Snapshot Completeness",
        "",
        "## 1. Summary",
        f"- snapshot_id: `{_mapping(snapshot.get('snapshot_identity')).get('snapshot_id', '')}`",
        f"- total_kpi_count: {summary.get('total_kpi_count')}",
        f"- numeric_value_count: {summary.get('numeric_value_count')}",
        f"- explicit_unavailable_count: {summary.get('explicit_unavailable_count')}",
        f"- trusted_loop_maturity_state: {summary.get('trusted_loop_maturity_state')}",
        f"- final_recommendation: {summary.get('final_recommendation')}",
        "",
        "## 2. KPI rows",
        "| KPI family | KPI id | Status | Value | Note |",
        "| --- | --- | --- | --- | --- |",
    ]
    for row in rows:
        if not isinstance(row, Mapping):
            continue
        value = row.get("value")
        lines.append(
            "| "
            + " | ".join(
                [
                    str(row.get("kpi_family") or ""),
                    str(row.get("kpi_id") or ""),
                    str(row.get("status") or ""),
                    "" if value is None else str(value),
                    str(row.get("note") or ""),
                ]
            )
            + " |"
        )
    return "\n".join(lines) + "\n"


def write_outputs(
    snapshot: Mapping[str, Any],
    *,
    output_dir: Path = ARTIFACT_DIR,
    repo_root: Path = REPO_ROOT,
) -> dict[str, str]:
    base = output_dir if output_dir.is_absolute() else repo_root / output_dir
    base.mkdir(parents=True, exist_ok=True)
    timestamp = str(snapshot["generated_at_utc"]).replace(":", "-")
    latest = base / "latest.json"
    timestamped = base / f"{timestamp}.json"
    history = base / "history.jsonl"
    markdown = base / "operator_summary.md"
    payload = json.dumps(snapshot, sort_keys=True, indent=2) + "\n"
    summary_md = render_operator_summary(snapshot)

    for target in (latest, timestamped, history, markdown):
        _validate_write_target(target)

    def _atomic_write(target: Path, content: str) -> None:
        with tempfile.NamedTemporaryFile(
            "w", delete=False, dir=str(target.parent), encoding="utf-8"
        ) as handle:
            handle.write(content)
            tmp_path = Path(handle.name)
        os.replace(tmp_path, target)

    _atomic_write(latest, payload)
    _atomic_write(timestamped, payload)
    _atomic_write(markdown, summary_md)
    compact = json.dumps(snapshot, sort_keys=True, separators=(",", ":"))
    with history.open("a", encoding="utf-8") as handle:
        handle.write(compact + "\n")

    return {
        "latest": _rel(latest),
        "timestamped": _rel(timestamped),
        "history": _rel(history),
        "operator_summary": _rel(markdown),
    }


def read_latest_snapshot(
    *,
    output_dir: Path = ARTIFACT_DIR,
    repo_root: Path = REPO_ROOT,
) -> dict[str, Any] | None:
    latest = output_dir if output_dir.is_absolute() else repo_root / output_dir
    latest = latest / "latest.json"
    if not latest.is_file():
        return None
    try:
        payload = json.loads(latest.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="reporting.qre_kpi_snapshot_completeness")
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--status", action="store_true")
    parser.add_argument("--frozen-utc")
    parser.add_argument("--max-candidates", type=int, default=15)
    args = parser.parse_args(argv)

    if args.status:
        snapshot = read_latest_snapshot()
        if snapshot is None:
            snapshot = {
                "report_kind": REPORT_KIND,
                "status": "missing_latest_snapshot",
                "path": _rel(ARTIFACT_LATEST),
            }
        print(json.dumps(snapshot, sort_keys=True, indent=2))
        return 0

    snapshot = collect_snapshot(
        repo_root=REPO_ROOT,
        max_candidates=args.max_candidates,
        frozen_utc=args.frozen_utc,
    )
    if args.write:
        snapshot["_artifact_paths"] = write_outputs(snapshot, repo_root=REPO_ROOT)
    print(json.dumps(snapshot, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
