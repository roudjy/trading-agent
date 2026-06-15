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


def _sample_sequence_rows() -> list[dict[str, Any]]:
    return [
        {"subject_id": "sample:candidate:progress", "step_index": 1, "state": "candidate_discovered"},
        {"subject_id": "sample:candidate:progress", "step_index": 2, "state": "screened"},
        {"subject_id": "sample:candidate:progress", "step_index": 3, "state": "validation_candidate"},
        {"subject_id": "sample:candidate:progress", "step_index": 4, "state": "validated"},
        {"subject_id": "sample:candidate:blocked", "step_index": 1, "state": "candidate_discovered"},
        {"subject_id": "sample:candidate:blocked", "step_index": 2, "state": "blocked"},
        {"subject_id": "sample:candidate:blocked", "step_index": 3, "state": "fail_closed"},
    ]


def _diagnose_sequence_rows(rows: list[Mapping[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[Mapping[str, Any]]] = {}
    for row in rows:
        if not isinstance(row, Mapping):
            continue
        subject_id = str(row.get("subject_id") or "unknown")
        grouped.setdefault(subject_id, []).append(row)

    diagnostics: list[dict[str, Any]] = []
    for subject_id, subject_rows in sorted(grouped.items()):
        ordered = sorted(subject_rows, key=lambda row: int(row.get("step_index") or 0))
        states = [str(row.get("state") or "unknown") for row in ordered]
        if not states:
            diagnostics.append(
                {
                    "subject_id": subject_id,
                    "sequence_length": 0,
                    "state_sequence": [],
                    "dwell_state": "unknown",
                    "dwell_steps": 0,
                    "regime_duration_steps": 0,
                    "sparse_data": True,
                    "sequence_state": "blocked",
                    "explanation": "Sequence rows are missing; state duration diagnostics fail closed.",
                }
            )
            continue

        dwell_state = states[-1]
        dwell_steps = 1
        for state in reversed(states[:-1]):
            if state != dwell_state:
                break
            dwell_steps += 1

        longest_run_state = states[0]
        longest_run_steps = 1
        run_state = states[0]
        run_steps = 1
        for state in states[1:]:
            if state == run_state:
                run_steps += 1
            else:
                if run_steps > longest_run_steps:
                    longest_run_state = run_state
                    longest_run_steps = run_steps
                run_state = state
                run_steps = 1
        if run_steps > longest_run_steps:
            longest_run_state = run_state
            longest_run_steps = run_steps

        sparse_data = len(states) < 2
        diagnostics.append(
            {
                "subject_id": subject_id,
                "sequence_length": len(states),
                "state_sequence": states,
                "dwell_state": dwell_state,
                "dwell_steps": dwell_steps,
                "regime_duration_steps": len(states),
                "longest_run_state": longest_run_state,
                "longest_run_steps": longest_run_steps,
                "sparse_data": sparse_data,
                "sequence_state": "blocked" if sparse_data else "ready",
                "explanation": (
                    "Sequence is sparse and fails closed."
                    if sparse_data
                    else "State sequence and dwell duration are deterministic diagnostic context only."
                ),
            }
        )

    return diagnostics


def build_state_transition_diagnostics_report(
    *,
    repo_root: Path = Path("."),
    transition_rows: list[Mapping[str, Any]] | None = None,
    sequence_rows: list[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    manifest = transition_diagnostic_manifest()
    rows = list(transition_rows) if transition_rows is not None else _sample_transition_rows()
    sequence_input = list(sequence_rows) if sequence_rows is not None else _sample_sequence_rows()
    diagnostics = diagnose_transition_rows(rows)
    sequence_diagnostics = _diagnose_sequence_rows(sequence_input)

    transition_state_counts = Counter(item.transition_state for item in diagnostics)
    new_state_counts = Counter(item.new_state for item in diagnostics)
    reason_counts = Counter(item.transition_reason for item in diagnostics)
    sequence_state_counts = Counter(item["sequence_state"] for item in sequence_diagnostics)
    sparse_sequence_count = sum(1 for item in sequence_diagnostics if item["sparse_data"])
    longest_regime_duration = max((int(item["regime_duration_steps"]) for item in sequence_diagnostics), default=0)

    return {
        "schema_version": SCHEMA_VERSION,
        "report_kind": REPORT_KIND,
        "summary": {
            "state_transition_diagnostics_ready": True,
            "transition_row_count": len(rows),
            "sequence_row_count": len(sequence_input),
            "diagnostic_count": len(diagnostics),
            "sequence_diagnostic_count": len(sequence_diagnostics),
            "transition_state_counts": dict(sorted(transition_state_counts.items())),
            "new_state_counts": dict(sorted(new_state_counts.items())),
            "transition_reason_counts": dict(sorted(reason_counts.items())),
            "sequence_state_counts": dict(sorted(sequence_state_counts.items())),
            "sparse_sequence_count": sparse_sequence_count,
            "longest_regime_duration_steps": longest_regime_duration,
            "final_recommendation": "state_transition_sequence_duration_ready",
            "operator_summary": (
                "State-transition, sequence, and dwell-duration diagnostics are available as "
                "deterministic, read-only context. They explain progression but do not mutate candidate state."
            ),
        },
        "manifest": manifest,
        "transition_rows": rows,
        "sequence_rows": sequence_input,
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
        "sequence_diagnostics": sequence_diagnostics,
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
            "sparse_data_fails_closed": True,
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
            f"- sequence_row_count: {summary.get('sequence_row_count')}",
            f"- diagnostic_count: {summary.get('diagnostic_count')}",
            f"- sequence_diagnostic_count: {summary.get('sequence_diagnostic_count')}",
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
