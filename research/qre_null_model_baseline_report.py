"""QRE null-model baseline report surface.

This report materializes a read-only, context-only null-model readiness surface.
It is diagnostic only and cannot promote candidates, register strategies,
fetch data, or authorize paper/shadow/live execution.
"""

from __future__ import annotations

import argparse
import hashlib
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


def _stable_hash_int(value: str) -> int:
    return int(hashlib.sha256(value.encode("utf-8")).hexdigest()[:8], 16)


def _deterministic_random_walk(rows: list[dict[str, Any]], *, start: float) -> list[float]:
    value = start
    series: list[float] = []
    for index, row in enumerate(rows, start=1):
        direction = 1 if _stable_hash_int(str(row.get("candidate_id") or row.get("score") or index)) % 2 == 0 else -1
        step = 0.005 * index
        value += direction * step
        series.append(value)
    return series


def _deterministic_shuffle(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(rows, key=lambda row: (_stable_hash_int(str(row.get("candidate_id") or "")), str(row.get("candidate_id") or "")))


def _martingale_like_series(rows: list[dict[str, Any]], *, seed: float) -> list[float]:
    series: list[float] = []
    running = seed
    for index, row in enumerate(rows, start=1):
        if index == 1:
            running = float(row.get("score") or 0.0)
        else:
            prior_values = [float(item.get("score") or 0.0) for item in rows[: index - 1]]
            running = sum(prior_values) / len(prior_values)
        series.append(running)
    return series


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
    random_walk_baseline = _deterministic_random_walk(sample_rows, start=float(baseline_metric or 0.0))
    shuffled_rows = _deterministic_shuffle(sample_rows)
    martingale_baseline = _martingale_like_series(sample_rows, seed=float(baseline_metric or 0.0))

    suite_families = {
        "random_walk": random_walk_baseline,
        "shuffled_surrogate": [float(row.get("score") or 0.0) for row in shuffled_rows],
        "martingale_like": martingale_baseline,
    }
    suite_comparisons: list[dict[str, Any]] = []
    for family, baseline_series in suite_families.items():
        for row, baseline_value in zip(sample_rows, baseline_series, strict=True):
            comparison = compare_metric_to_baseline(
                candidate_metric=row.get("score"),
                baseline_metric=baseline_value,
                baseline_type=family,
            )
            suite_comparisons.append(
                {
                    "family": family,
                    "candidate_id": row["candidate_id"],
                    "candidate_metric": comparison.candidate_metric,
                    "baseline_metric": comparison.baseline_metric,
                    "delta_vs_baseline": comparison.delta_vs_baseline,
                    "comparison_state": comparison.comparison_state,
                    "explanation": comparison.explanation,
                }
            )

    comparison_counts: dict[str, int] = {}
    for comparison in sample_comparisons:
        comparison_counts[comparison.comparison_state] = (
            comparison_counts.get(comparison.comparison_state, 0) + 1
        )
    suite_comparison_counts: dict[str, int] = {}
    for comparison in suite_comparisons:
        state = str(comparison["comparison_state"])
        suite_comparison_counts[state] = suite_comparison_counts.get(state, 0) + 1

    return {
        "schema_version": SCHEMA_VERSION,
        "report_kind": REPORT_KIND,
        "summary": {
            "null_model_baseline_ready": True,
            "baseline_type_count": len(manifest["baseline_types"]),
            "baseline_family_count": len(suite_families),
            "sample_row_count": len(sample_rows),
            "sample_baseline_metric": baseline_metric,
            "sample_comparison_counts": dict(sorted(comparison_counts.items())),
            "suite_comparison_count": len(suite_comparisons),
            "suite_comparison_counts": dict(sorted(suite_comparison_counts.items())),
            "final_recommendation": "null_model_baseline_suite_ready",
            "operator_summary": (
                "Null-model baseline suite is deterministic, read-only diagnostic context only. "
                "Random walk, shuffled surrogate, and martingale-like comparisons do not promote "
                "candidates or authorize execution."
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
        "suite_baselines": {
            "random_walk": random_walk_baseline,
            "shuffled_surrogate": [float(row.get("score") or 0.0) for row in shuffled_rows],
            "martingale_like": martingale_baseline,
        },
        "suite_comparisons": suite_comparisons,
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
            "no_edge_baselines_do_not_authorize_promotion": True,
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
