"""QRE state-transition diagnostics report surface.

This report materializes deterministic, read-only state-transition diagnostics.
It is diagnostic context only and cannot mutate candidates, promote strategies,
fetch data, or authorize paper/shadow/live/broker execution.
"""

from __future__ import annotations

import argparse
import json
import os
from collections import Counter
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Final

from research.qre_state_transition_diagnostics import (
    diagnose_transition_rows,
    transition_diagnostic_manifest,
)


REPORT_KIND: Final[str] = "qre_state_transition_diagnostics_report"
SCHEMA_VERSION: Final[str] = "1.0"
DEFAULT_OUTPUT_DIR: Final[Path] = Path("logs/qre_state_transition_diagnostics")
LATEST_NAME: Final[str] = "latest.json"
OPERATOR_SUMMARY_NAME: Final[str] = "operator_summary.md"
WRITE_PREFIX: Final[str] = "logs/qre_state_transition_diagnostics/"


def _sample_transition_rows() -> list[dict[str, Any]]:
    return [
        {
            "subject_id": "sample:candidate:discovered_to_screened",
            "prior_state": "candidate_discovered",
            "new_state": "screened",
            "transition_reason": "criteria_passed",
            "evidence_ref": "logs/qre_state_transition_diagnostics/sample.json",
            "artifact_ref": "logs/qre_state_transition_diagnostics/latest.json",
        },
        {
            "subject_id": "sample:candidate:screened_to_validation",
            "prior_state": "screened",
            "new_state": "validation_candidate",
            "transition_reason": "null_model_required",
            "evidence_ref": "logs/qre_null_model_baseline/latest.json",
            "artifact_ref": "logs/qre_state_transition_diagnostics/latest.json",
        },
        {
            "subject_id": "sample:candidate:screened_to_blocked",
            "prior_state": "screened",
            "new_state": "blocked",
            "transition_reason": "data_readiness_blocked",
            "blocker_class": "missing_required_field",
            "evidence_ref": "research/factor_field_coverage_manifest.json",
            "artifact_ref": "logs/qre_state_transition_diagnostics/latest.json",
        },
    ]


def build_state_transition_diagnostics_report(
    *,
    repo_root: Path = Path("."),
    transition_rows: list[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    manifest = transition_diagnostic_manifest()
    rows = list(transition_rows) if transition_rows is not None else _sample_transition_rows()
    diagnostics = diagnose_transition_rows(rows)

    transition_state_counts = Counter(item.transition_state for item in diagnostics)
    new_state_counts = Counter(item.new_state for item in diagnostics)
    reason_counts = Counter(item.transition_reason for item in diagnostics)

    return {
        "schema_version": SCHEMA_VERSION,
        "report_kind": REPORT_KIND,
        "summary": {
            "state_transition_diagnostics_ready": True,
            "transition_row_count": len(rows),
            "diagnostic_count": len(diagnostics),
            "transition_state_counts": dict(sorted(transition_state_counts.items())),
            "new_state_counts": dict(sorted(new_state_counts.items())),
            "transition_reason_counts": dict(sorted(reason_counts.items())),
            "final_recommendation": "state_transition_diagnostics_scaffold_ready",
            "operator_summary": (
                "State-transition diagnostics are available as deterministic, read-only "
                "context. They explain transitions but do not mutate candidate state."
            ),
        },
        "manifest": manifest,
        "transition_rows": rows,
        "diagnostics": [
            {
                "subject_id": item.subject_id,
                "prior_state": item.prior_state,
                "new_state": item.new_state,
                "transition_reason": item.transition_reason,
                "blocker_class": item.blocker_class,
                "evidence_ref": item.evidence_ref,
                "artifact_ref": item.artifact_ref,
                "transition_state": item.transition_state,
                "explanation": item.explanation,
            }
            for item in diagnostics
        ],
        "safety_invariants": {
            "read_only": True,
            "uses_network": False,
            "uses_external_data": False,
            "uses_embeddings": False,
            "uses_vector_db": False,
            "uses_llm_authority": False,
            "mutates_candidates": False,
            "mutates_candidate_state": False,
            "mutates_strategies": False,
            "mutates_frozen_contracts": False,
            "promotion_forbidden": True,
            "paper_shadow_live_forbidden": True,
            "broker_risk_execution_forbidden": True,
        },
    }


def render_operator_summary(report: Mapping[str, Any]) -> str:
    summary = report.get("summary") if isinstance(report.get("summary"), Mapping) else {}
    return "\n".join(
        [
            "# QRE State Transition Diagnostics",
            "",
            f"- {summary.get('operator_summary') or ''}",
            "",
            "## Current Status",
            "",
            f"- state_transition_diagnostics_ready: {summary.get('state_transition_diagnostics_ready')}",
            f"- transition_row_count: {summary.get('transition_row_count')}",
            f"- diagnostic_count: {summary.get('diagnostic_count')}",
            f"- final_recommendation: {summary.get('final_recommendation')}",
            "",
        ]
    )


def _validate_write_target(path: Path) -> None:
    if WRITE_PREFIX not in path.as_posix():
        raise ValueError(
            f"qre_state_transition_diagnostics_report: refusing write outside allowlist: {path!r}"
        )


def write_outputs(report: Mapping[str, Any], *, repo_root: Path = Path(".")) -> dict[str, str]:
    base = repo_root / DEFAULT_OUTPUT_DIR
    base.mkdir(parents=True, exist_ok=True)
    latest = base / LATEST_NAME
    summary_path = base / OPERATOR_SUMMARY_NAME

    for target in (latest, summary_path):
        _validate_write_target(target)

    tmp_json = latest.with_suffix(latest.suffix + ".tmp")
    tmp_json.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(tmp_json, latest)

    tmp_md = summary_path.with_suffix(summary_path.suffix + ".tmp")
    tmp_md.write_text(render_operator_summary(report), encoding="utf-8")
    os.replace(tmp_md, summary_path)

    return {
        "latest": latest.relative_to(repo_root).as_posix(),
        "operator_summary": summary_path.relative_to(repo_root).as_posix(),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m research.qre_state_transition_diagnostics_report",
        description="Build read-only QRE state-transition diagnostics report.",
    )
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args(argv)

    report = build_state_transition_diagnostics_report()
    if args.write:
        report["_artifact_paths"] = write_outputs(report)

    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())