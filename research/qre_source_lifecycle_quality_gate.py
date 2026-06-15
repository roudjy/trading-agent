"""Read-only QRE source lifecycle and quality gate materialization."""

from __future__ import annotations

import argparse
import json
import os
from collections import Counter
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Final

from packages.qre_data import source_lifecycle
from packages.qre_data import source_quality_readiness
from research.external_intelligence import source_license_policy
from research.external_intelligence import source_manifest_registry
from research.external_intelligence.source_manifest_schema import (
    FORBIDDEN_USE_VOCABULARY,
)


REPORT_KIND: Final[str] = "qre_source_lifecycle_quality_gate"
SCHEMA_VERSION: Final[str] = "1.0"
DEFAULT_OUTPUT_DIR: Final[Path] = Path("logs/qre_source_lifecycle_quality_gate")
LATEST_NAME: Final[str] = "latest.json"
SUMMARY_NAME: Final[str] = "operator_summary.md"
WRITE_PREFIX: Final[str] = "logs/qre_source_lifecycle_quality_gate/"


def _table(headers: Sequence[str], rows: Sequence[Sequence[str]]) -> str:
    head = "| " + " | ".join(headers) + " |"
    divider = "| " + " | ".join(["---"] * len(headers)) + " |"
    body = ["| " + " | ".join(row) + " |" for row in rows]
    return "\n".join([head, divider, *body])


def build_source_lifecycle_quality_gate(
    *,
    repo_root: Path = Path("."),
) -> dict[str, Any]:
    registry = source_manifest_registry.build_source_manifest_registry()
    source_quality_status = source_quality_readiness.read_source_quality_status(repo_root=repo_root)
    source_quality_ready = bool(source_quality_status.get("research_ready"))

    rows: list[dict[str, Any]] = []
    for manifest in registry["rows"]:
        policy = source_license_policy.evaluate_license_policy(manifest)
        lifecycle = source_lifecycle.evaluate_source_lifecycle(
            manifest,
            required_forbidden_use=FORBIDDEN_USE_VOCABULARY,
            source_quality_ready=source_quality_ready,
            license_allows_quality_gate=bool(policy["allowed_for_quality_gate"]),
            license_allows_active_read_only=bool(policy["allowed_for_active_read_only"]),
        )
        row = {
            "source_id": lifecycle["source_id"],
            "provider_id": lifecycle["provider_id"],
            "current_state": lifecycle["current_state"],
            "lifecycle_status": lifecycle["lifecycle_status"],
            "gate_statuses": lifecycle["gate_statuses"],
            "transition_targets": lifecycle["transition_targets"],
            "license_policy_status": policy["license_policy_status"],
            "license_block_reasons": policy["block_reasons"],
            "source_quality_ready": lifecycle["source_quality_ready"],
            "operator_explanation": lifecycle["operator_explanation"],
        }
        rows.append(row)
    rows.sort(key=lambda row: (str(row["provider_id"]), str(row["source_id"])))

    lifecycle_counts = Counter(str(row["lifecycle_status"]) for row in rows)
    current_state_counts = Counter(str(row["current_state"]) for row in rows)
    blocked_active_counts = Counter(
        reason
        for row in rows
        for reason in row["transition_targets"]["active_read_only"]["blocking_reasons"]
    )

    return {
        "schema_version": SCHEMA_VERSION,
        "report_kind": REPORT_KIND,
        "summary": {
            "source_count": len(rows),
            "current_state_counts": dict(sorted(current_state_counts.items())),
            "lifecycle_status_counts": dict(sorted(lifecycle_counts.items())),
            "active_read_only_ready_count": sum(
                1 for row in rows if bool(row["transition_targets"]["active_read_only"]["allowed"])
            ),
            "quality_gated_ready_count": sum(
                1 for row in rows if bool(row["transition_targets"]["quality_gated"]["allowed"])
            ),
            "active_read_only_blocking_reason_counts": dict(sorted(blocked_active_counts.items())),
            "source_quality_report_status": str(source_quality_status.get("status") or "missing"),
            "source_quality_report_ready": source_quality_ready,
            "operator_summary": (
                "Source lifecycle promotion remains fail-closed. Candidate, manual, and staging "
                "sources cannot become active_read_only until manifest completeness, declared "
                "allowed/forbidden use, quality gates, identity mapping, and historical lineage "
                "or reproducibility are all explicit."
            ),
        },
        "rows": rows,
        "supporting_reports": {
            "source_manifest_registry": {
                "report_kind": registry["report_kind"],
                "active_read_only_eligible_providers": registry["summary"][
                    "active_read_only_eligible_providers"
                ],
                "quality_gated_eligible_providers": registry["summary"][
                    "quality_gated_eligible_providers"
                ],
            },
            "source_quality_status": source_quality_status,
        },
        "safety_invariants": {
            "read_only": True,
            "fetches_external_data": False,
            "mutates_runtime_state": False,
            "mutates_research_outputs": False,
            "paper_shadow_live_forbidden": True,
            "broker_risk_execution_forbidden": True,
            "promotion_forbidden": True,
        },
    }


def render_operator_summary(report: Mapping[str, Any]) -> str:
    summary = report.get("summary") if isinstance(report.get("summary"), Mapping) else {}
    rows = report.get("rows") if isinstance(report.get("rows"), list) else []
    state_table = _table(
        ["Field", "Value"],
        [
            ["source_count", str(summary.get("source_count") or 0)],
            ["source_quality_report_status", str(summary.get("source_quality_report_status") or "")],
            ["source_quality_report_ready", str(summary.get("source_quality_report_ready") or False)],
            ["quality_gated_ready_count", str(summary.get("quality_gated_ready_count") or 0)],
            ["active_read_only_ready_count", str(summary.get("active_read_only_ready_count") or 0)],
        ],
    )
    row_table = _table(
        ["source_id", "current_state", "quality_gated", "active_read_only", "license_policy_status"],
        [
            [
                str(row.get("source_id") or ""),
                str(row.get("current_state") or ""),
                str((row.get("transition_targets") or {}).get("quality_gated", {}).get("allowed") or False),
                str((row.get("transition_targets") or {}).get("active_read_only", {}).get("allowed") or False),
                str(row.get("license_policy_status") or ""),
            ]
            for row in rows
            if isinstance(row, Mapping)
        ],
    )
    return "\n".join(
        [
            "# QRE Source Lifecycle and Quality Gate",
            "",
            f"- {summary.get('operator_summary') or ''}",
            "",
            "## Status",
            state_table,
            "",
            "## Source Rows",
            row_table,
        ]
    )


def _validate_write_target(path: Path) -> None:
    if WRITE_PREFIX not in path.as_posix():
        raise ValueError(
            f"qre_source_lifecycle_quality_gate: refusing write outside allowlist: {path!r}"
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
        prog="python -m research.qre_source_lifecycle_quality_gate",
        description="Materialize the read-only QRE source lifecycle quality gate report.",
    )
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args(argv)
    report = build_source_lifecycle_quality_gate()
    if args.write:
        report["_artifact_paths"] = write_outputs(report)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
