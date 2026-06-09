"""QRE sampling calibration report surface.

This report materializes deterministic, read-only sampling calibration context.
It does not mutate candidates, campaigns, strategies, presets, or execution state.
"""

from __future__ import annotations

import argparse
import json
import os
from collections import Counter
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Final

from research.qre_sampling_calibration import (
    calibrate_sampling_rows,
    sampling_calibration_manifest,
)


REPORT_KIND: Final[str] = "qre_sampling_calibration_report"
SCHEMA_VERSION: Final[str] = "1.0"
DEFAULT_OUTPUT_DIR: Final[Path] = Path("logs/qre_sampling_calibration")
LATEST_NAME: Final[str] = "latest.json"
OPERATOR_SUMMARY_NAME: Final[str] = "operator_summary.md"
WRITE_PREFIX: Final[str] = "logs/qre_sampling_calibration/"


def _sample_rows() -> list[dict[str, Any]]:
    return [
        {
            "subject_id": "sample:crypto_legacy",
            "ontology_classification": {
                "asset_class": "crypto_legacy",
                "research_scope": "excluded_from_current_research_scope",
                "readiness_state": "blocked",
            },
            "title": "BTC-USD crypto legacy candidate",
        },
        {
            "subject_id": "sample:netherlands_fundamental",
            "asset_class": "fundamental_equity",
            "research_scope": "target_equity_research",
            "readiness_state": "ready",
            "title": "AEX Netherlands fundamental factor field_coverage source_manifest",
            "metadata": {"provider": "openfigi", "exchange": "euronext amsterdam"},
        },
        {
            "subject_id": "sample:us_source_quality",
            "asset_class": "equity",
            "research_scope": "target_source_data_research",
            "readiness_state": "partial",
            "title": "NASDAQ US equity source_manifest provider quality",
        },
        {
            "subject_id": "sample:asia_factor",
            "asset_class": "index",
            "research_scope": "target_factor_research",
            "readiness_state": "ready",
            "title": "Asia Japan Nikkei factor coverage",
        },
        {
            "subject_id": "sample:blocked_unknown",
            "asset_class": "equity",
            "research_scope": "target_equity_research",
            "readiness_state": "blocked",
            "title": "equity candidate missing source lineage",
        },
    ]


def build_sampling_calibration_report(
    *,
    repo_root: Path = Path("."),
    rows: list[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    manifest = sampling_calibration_manifest()
    input_rows = list(rows) if rows is not None else _sample_rows()
    calibrations = calibrate_sampling_rows(input_rows)

    decision_counts = Counter(item.sampling_decision for item in calibrations)
    preferred_axis_counts = Counter(
        axis for item in calibrations for axis in item.preferred_axes
    )
    penalty_axis_counts = Counter(axis for item in calibrations for axis in item.penalty_axes)

    return {
        "schema_version": SCHEMA_VERSION,
        "report_kind": REPORT_KIND,
        "summary": {
            "sampling_calibration_ready": True,
            "input_row_count": len(input_rows),
            "calibration_count": len(calibrations),
            "sampling_decision_counts": dict(sorted(decision_counts.items())),
            "preferred_axis_counts": dict(sorted(preferred_axis_counts.items())),
            "penalty_axis_counts": dict(sorted(penalty_axis_counts.items())),
            "crypto_legacy_excluded_count": penalty_axis_counts.get("asset_class:crypto_legacy", 0),
            "final_recommendation": "sampling_calibration_scaffold_ready",
            "operator_summary": (
                "Sampling calibration is available as deterministic, read-only context. "
                "Crypto legacy is excluded, while equity/fundamental/source/factor and "
                "regional diversity axes are preferred."
            ),
        },
        "manifest": manifest,
        "input_rows": input_rows,
        "calibrations": [
            {
                "subject_id": item.subject_id,
                "sampling_score": item.sampling_score,
                "sampling_decision": item.sampling_decision,
                "preferred_axes": list(item.preferred_axes),
                "penalty_axes": list(item.penalty_axes),
                "explanation": item.explanation,
            }
            for item in calibrations
        ],
        "safety_invariants": {
            "read_only": True,
            "uses_network": False,
            "uses_external_data": False,
            "uses_embeddings": False,
            "uses_vector_db": False,
            "uses_llm_authority": False,
            "mutates_candidates": False,
            "mutates_campaigns": False,
            "mutates_strategies": False,
            "mutates_presets": False,
            "mutates_frozen_contracts": False,
            "promotion_forbidden": True,
            "campaign_mutation_forbidden": True,
            "paper_shadow_live_forbidden": True,
            "broker_risk_execution_forbidden": True,
        },
    }


def render_operator_summary(report: Mapping[str, Any]) -> str:
    summary = report.get("summary") if isinstance(report.get("summary"), Mapping) else {}
    return "\n".join(
        [
            "# QRE Sampling Calibration",
            "",
            f"- {summary.get('operator_summary') or ''}",
            "",
            "## Current Status",
            "",
            f"- sampling_calibration_ready: {summary.get('sampling_calibration_ready')}",
            f"- input_row_count: {summary.get('input_row_count')}",
            f"- calibration_count: {summary.get('calibration_count')}",
            f"- crypto_legacy_excluded_count: {summary.get('crypto_legacy_excluded_count')}",
            f"- final_recommendation: {summary.get('final_recommendation')}",
            "",
        ]
    )


def _validate_write_target(path: Path) -> None:
    if WRITE_PREFIX not in path.as_posix():
        raise ValueError(f"qre_sampling_calibration_report: refusing write outside allowlist: {path!r}")


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
        prog="python -m research.qre_sampling_calibration_report",
        description="Build read-only QRE sampling calibration report.",
    )
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args(argv)

    report = build_sampling_calibration_report()
    if args.write:
        report["_artifact_paths"] = write_outputs(report)

    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())