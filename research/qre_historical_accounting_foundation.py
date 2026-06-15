"""Read-only QRE historical accounting foundation materialization."""

from __future__ import annotations

import argparse
import json
import os
from collections import Counter
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Final

from packages.qre_data import historical_accounting
from research.data_readiness import report_lag_policy
from research.data_readiness import restatement_policy
from research.external_intelligence import source_manifest_registry


REPORT_KIND: Final[str] = "qre_historical_accounting_foundation"
SCHEMA_VERSION: Final[str] = "1.0"
DEFAULT_OUTPUT_DIR: Final[Path] = Path("logs/qre_historical_accounting_foundation")
LATEST_NAME: Final[str] = "latest.json"
SUMMARY_NAME: Final[str] = "operator_summary.md"
WRITE_PREFIX: Final[str] = "logs/qre_historical_accounting_foundation/"


def _table(headers: Sequence[str], rows: Sequence[Sequence[str]]) -> str:
    head = "| " + " | ".join(headers) + " |"
    divider = "| " + " | ".join(["---"] * len(headers)) + " |"
    body = ["| " + " | ".join(row) + " |" for row in rows]
    return "\n".join([head, divider, *body])


def build_historical_accounting_foundation() -> dict[str, Any]:
    registry = source_manifest_registry.build_source_manifest_registry()
    report_lag = report_lag_policy.build_report_lag_policy()
    restatement = restatement_policy.build_restatement_policy()
    report_lag_by_source = {
        str(row["source_id"]): row
        for row in report_lag["rows"]
        if isinstance(row, Mapping)
    }
    restatement_by_source = {
        str(row["source_id"]): row
        for row in restatement["rows"]
        if isinstance(row, Mapping)
    }

    rows: list[dict[str, Any]] = []
    for manifest in registry["rows"]:
        source_id = str(manifest["source_id"])
        row = historical_accounting.evaluate_historical_accounting_snapshot(
            manifest,
            report_lag_policy_row=report_lag_by_source[source_id],
            restatement_policy_row=restatement_by_source[source_id],
        )
        rows.append(row)
    rows.sort(key=lambda row: (str(row["provider_id"]), str(row["source_id"])))

    status_counts = Counter(str(row["snapshot_contract_status"]) for row in rows)
    blocked_counts = Counter(reason for row in rows for reason in row["blocking_reasons"])
    required_rows = [row for row in rows if bool(row["requires_historical_accounting"])]
    no_lookahead_ready_count = sum(
        1 for row in required_rows if bool(row["gate_statuses"]["no_lookahead_snapshot_contract"])
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "report_kind": REPORT_KIND,
        "summary": {
            "source_count": len(rows),
            "required_source_count": len(required_rows),
            "snapshot_contract_status_counts": dict(sorted(status_counts.items())),
            "blocking_reason_counts": dict(sorted(blocked_counts.items())),
            "no_lookahead_ready_count": no_lookahead_ready_count,
            "required_blocked_count": sum(
                1 for row in required_rows if str(row["snapshot_contract_status"]) == "BLOCKED"
            ),
            "operator_summary": (
                "Historical accounting remains read-only and fail-closed. "
                "Fundamental sources need explicit PIT policy, report-lag, restatement, "
                "and reproducible lineage before any snapshot can be treated as no-lookahead safe."
            ),
        },
        "rows": rows,
        "supporting_reports": {
            "source_manifest_registry": {"report_kind": registry["report_kind"]},
            "report_lag_policy": {"report_kind": report_lag["report_kind"]},
            "restatement_policy": {"report_kind": restatement["report_kind"]},
        },
        "safety_invariants": {
            "read_only": True,
            "fetches_external_data": False,
            "mutates_runtime_state": False,
            "mutates_research_outputs": False,
            "mutates_frozen_contracts": False,
            "paper_shadow_live_forbidden": True,
            "broker_risk_execution_forbidden": True,
            "lookahead_contamination_forbidden": True,
            "point_in_time_foundation_only": True,
        },
    }


def render_operator_summary(report: Mapping[str, Any]) -> str:
    summary = report.get("summary") if isinstance(report.get("summary"), Mapping) else {}
    rows = report.get("rows") if isinstance(report.get("rows"), list) else []
    status_table = _table(
        ["Field", "Value"],
        [
            ["source_count", str(summary.get("source_count") or 0)],
            ["required_source_count", str(summary.get("required_source_count") or 0)],
            ["no_lookahead_ready_count", str(summary.get("no_lookahead_ready_count") or 0)],
            ["required_blocked_count", str(summary.get("required_blocked_count") or 0)],
        ],
    )
    row_table = _table(
        ["source_id", "required", "snapshot_status", "report_lag", "restatement", "blocked_by"],
        [
            [
                str(row.get("source_id") or ""),
                str(row.get("requires_historical_accounting") or False),
                str(row.get("snapshot_contract_status") or ""),
                str(row.get("report_lag_policy_status") or ""),
                str(row.get("restatement_policy_status") or ""),
                ",".join(str(value) for value in row.get("blocking_reasons") or []) or "none",
            ]
            for row in rows
            if isinstance(row, Mapping)
        ],
    )
    return "\n".join(
        [
            "# QRE Historical Accounting Foundation",
            "",
            f"- {summary.get('operator_summary') or ''}",
            "",
            "## Status",
            status_table,
            "",
            "## Source Rows",
            row_table,
        ]
    )


def _validate_write_target(path: Path) -> None:
    if WRITE_PREFIX not in path.as_posix():
        raise ValueError(
            f"qre_historical_accounting_foundation: refusing write outside allowlist: {path!r}"
        )


def write_outputs(
    report: Mapping[str, Any],
    *,
    repo_root: Path = Path("."),
) -> dict[str, str]:
    base = repo_root / DEFAULT_OUTPUT_DIR
    base.mkdir(parents=True, exist_ok=True)
    latest = base / LATEST_NAME
    summary = base / SUMMARY_NAME
    for target in (latest, summary):
        _validate_write_target(target)

    tmp_latest = latest.with_suffix(latest.suffix + ".tmp")
    tmp_latest.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(tmp_latest, latest)

    tmp_summary = summary.with_suffix(summary.suffix + ".tmp")
    tmp_summary.write_text(render_operator_summary(report) + "\n", encoding="utf-8")
    os.replace(tmp_summary, summary)

    return {
        "latest": latest.relative_to(repo_root).as_posix(),
        "operator_summary": summary.relative_to(repo_root).as_posix(),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m research.qre_historical_accounting_foundation",
        description="Materialize the read-only QRE historical accounting foundation report.",
    )
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args(argv)
    report = build_historical_accounting_foundation()
    if args.write:
        report["_artifact_paths"] = write_outputs(report)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
