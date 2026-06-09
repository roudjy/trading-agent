"""QRE null-model baseline report surface.

This report materializes a read-only, context-only null-model readiness surface.
It is diagnostic only and cannot promote candidates, register strategies,
fetch data, or authorize paper/shadow/live execution.
"""

from __future__ import annotations

import argparse
import json
import os
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Final

from research.qre_null_model_baseline import (
    compare_metric_to_baseline,
    median_candidate_baseline,
    null_model_manifest,
)


REPORT_KIND: Final[str] = "qre_null_model_baseline_report"
SCHEMA_VERSION: Final[str] = "1.0"
DEFAULT_OUTPUT_DIR: Final[Path] = Path("logs/qre_null_model_baseline")
LATEST_NAME: Final[str] = "latest.json"
OPERATOR_SUMMARY_NAME: Final[str] = "operator_summary.md"
WRITE_PREFIX: Final[str] = "logs/qre_null_model_baseline/"


def build_null_model_baseline_report(*, repo_root: Path = Path(".")) -> dict[str, Any]:
    manifest = null_model_manifest()

    sample_rows = [
        {"candidate_id": "sample:below", "score": -0.01},
        {"candidate_id": "sample:baseline", "score": 0.00},
        {"candidate_id": "sample:above", "score": 0.02},
    ]
    baseline_metric = median_candidate_baseline(sample_rows, metric_field="score")
    sample_comparisons = [
        compare_metric_to_baseline(
            candidate_metric=row.get("score"),
            baseline_metric=baseline_metric,
            baseline_type="median_candidate",
        )
        for row in sample_rows
    ]

    comparison_counts: dict[str, int] = {}
    for comparison in sample_comparisons:
        comparison_counts[comparison.comparison_state] = (
            comparison_counts.get(comparison.comparison_state, 0) + 1
        )

    return {
        "schema_version": SCHEMA_VERSION,
        "report_kind": REPORT_KIND,
        "summary": {
            "null_model_baseline_ready": True,
            "baseline_type_count": len(manifest["baseline_types"]),
            "sample_row_count": len(sample_rows),
            "sample_baseline_metric": baseline_metric,
            "sample_comparison_counts": dict(sorted(comparison_counts.items())),
            "final_recommendation": "null_model_baseline_scaffold_ready",
            "operator_summary": (
                "Null-model baseline scaffold is available as deterministic, read-only "
                "diagnostic context only. It does not promote candidates or authorize execution."
            ),
        },
        "manifest": manifest,
        "sample_rows": sample_rows,
        "sample_comparisons": [
            {
                "baseline_type": item.baseline_type,
                "candidate_metric": item.candidate_metric,
                "baseline_metric": item.baseline_metric,
                "delta_vs_baseline": item.delta_vs_baseline,
                "comparison_state": item.comparison_state,
                "explanation": item.explanation,
            }
            for item in sample_comparisons
        ],
        "safety_invariants": {
            "read_only": True,
            "uses_network": False,
            "uses_external_data": False,
            "uses_embeddings": False,
            "uses_vector_db": False,
            "uses_llm_authority": False,
            "mutates_candidates": False,
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
            "# QRE Null Model Baseline",
            "",
            f"- {summary.get('operator_summary') or ''}",
            "",
            "## Current Status",
            "",
            f"- null_model_baseline_ready: {summary.get('null_model_baseline_ready')}",
            f"- baseline_type_count: {summary.get('baseline_type_count')}",
            f"- sample_row_count: {summary.get('sample_row_count')}",
            f"- sample_baseline_metric: {summary.get('sample_baseline_metric')}",
            f"- final_recommendation: {summary.get('final_recommendation')}",
            "",
        ]
    )


def _validate_write_target(path: Path) -> None:
    if WRITE_PREFIX not in path.as_posix():
        raise ValueError(f"qre_null_model_baseline_report: refusing write outside allowlist: {path!r}")


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
        prog="python -m research.qre_null_model_baseline_report",
        description="Build read-only QRE null-model baseline report.",
    )
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args(argv)

    report = build_null_model_baseline_report()
    if args.write:
        report["_artifact_paths"] = write_outputs(report)

    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())