"""QRE routing calibration report surface.

This report materializes deterministic, read-only routing calibration context.
It does not mutate queues, candidates, campaigns, strategies, presets, or execution state.
"""

from __future__ import annotations

import argparse
import json
import os
from collections import Counter
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Final

from research.qre_routing_calibration import (
    calibrate_routing_rows,
    routing_calibration_manifest,
)


REPORT_KIND: Final[str] = "qre_routing_calibration_report"
SCHEMA_VERSION: Final[str] = "1.0"
DEFAULT_OUTPUT_DIR: Final[Path] = Path("logs/qre_routing_calibration")
LATEST_NAME: Final[str] = "latest.json"
OPERATOR_SUMMARY_NAME: Final[str] = "operator_summary.md"
WRITE_PREFIX: Final[str] = "logs/qre_routing_calibration/"


def _sample_rows() -> list[dict[str, Any]]:
    return [
        {
            "subject_id": "sample:crypto_archive",
            "ontology_classification": {
                "asset_class": "crypto_legacy",
                "research_scope": "excluded_from_current_research_scope",
            },
            "title": "BTC-USD crypto legacy archive context",
        },
        {
            "subject_id": "sample:source_identity",
            "asset_class": "equity",
            "research_scope": "target_source_data_research",
            "title": "OpenFIGI provider source_manifest identity ticker ambiguity",
        },
        {
            "subject_id": "sample:factor_null",
            "asset_class": "fundamental_equity",
            "research_scope": "target_factor_research",
            "title": "fundamental factor field_coverage null_model baseline",
        },
        {
            "subject_id": "sample:state_tail",
            "asset_class": "equity",
            "research_scope": "target_equity_research",
            "title": "state transition blocked tail entropy drawdown concentration",
        },
        {
            "subject_id": "sample:blocked_failure",
            "asset_class": "equity",
            "research_scope": "target_equity_research",
            "readiness_state": "blocked",
            "blocker_class": "missing_required_field",
            "record_kind": "failure_action",
        },
    ]


def build_routing_calibration_report(
    *,
    repo_root: Path = Path("."),
    rows: list[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    manifest = routing_calibration_manifest()
    input_rows = list(rows) if rows is not None else _sample_rows()
    calibrations = calibrate_routing_rows(input_rows)

    decision_counts = Counter(item.routing_decision for item in calibrations)
    target_counts = Counter(target for item in calibrations for target in item.routing_targets)

    return {
        "schema_version": SCHEMA_VERSION,
        "report_kind": REPORT_KIND,
        "summary": {
            "routing_calibration_ready": True,
            "input_row_count": len(input_rows),
            "calibration_count": len(calibrations),
            "routing_decision_counts": dict(sorted(decision_counts.items())),
            "routing_target_counts": dict(sorted(target_counts.items())),
            "excluded_scope_archive_count": target_counts.get("excluded_scope_archive", 0),
            "final_recommendation": "routing_calibration_scaffold_ready",
            "operator_summary": (
                "Routing calibration is available as deterministic, read-only context. "
                "It recommends diagnostic routing targets without mutating queues or campaigns."
            ),
        },
        "manifest": manifest,
        "input_rows": input_rows,
        "calibrations": [
            {
                "subject_id": item.subject_id,
                "routing_targets": list(item.routing_targets),
                "routing_priority": item.routing_priority,
                "routing_decision": item.routing_decision,
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
            "mutates_queues": False,
            "mutates_candidates": False,
            "mutates_campaigns": False,
            "mutates_strategies": False,
            "mutates_presets": False,
            "mutates_frozen_contracts": False,
            "queue_mutation_forbidden": True,
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
            "# QRE Routing Calibration",
            "",
            f"- {summary.get('operator_summary') or ''}",
            "",
            "## Current Status",
            "",
            f"- routing_calibration_ready: {summary.get('routing_calibration_ready')}",
            f"- input_row_count: {summary.get('input_row_count')}",
            f"- calibration_count: {summary.get('calibration_count')}",
            f"- excluded_scope_archive_count: {summary.get('excluded_scope_archive_count')}",
            f"- final_recommendation: {summary.get('final_recommendation')}",
            "",
        ]
    )


def _validate_write_target(path: Path) -> None:
    if WRITE_PREFIX not in path.as_posix():
        raise ValueError(f"qre_routing_calibration_report: refusing write outside allowlist: {path!r}")


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
        prog="python -m research.qre_routing_calibration_report",
        description="Build read-only QRE routing calibration report.",
    )
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args(argv)

    report = build_routing_calibration_report()
    if args.write:
        report["_artifact_paths"] = write_outputs(report)

    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())