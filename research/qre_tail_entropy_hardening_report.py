"""QRE tail/entropy hardening report surface.

This report materializes deterministic, read-only tail/entropy diagnostics.
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

from research.qre_tail_entropy_hardening import (
    diagnose_tail_entropy,
    tail_entropy_manifest,
)


REPORT_KIND: Final[str] = "qre_tail_entropy_hardening_report"
SCHEMA_VERSION: Final[str] = "1.0"
DEFAULT_OUTPUT_DIR: Final[Path] = Path("logs/qre_tail_entropy_hardening")
LATEST_NAME: Final[str] = "latest.json"
OPERATOR_SUMMARY_NAME: Final[str] = "operator_summary.md"
WRITE_PREFIX: Final[str] = "logs/qre_tail_entropy_hardening/"


def _sample_observation_sets() -> list[dict[str, Any]]:
    return [
        {
            "subject_id": "sample:balanced",
            "observations": [0.01, -0.01, 0.02, -0.02, 0.015, -0.015],
            "description": "Balanced positive/negative sample.",
        },
        {
            "subject_id": "sample:single_trade_concentration",
            "observations": [0.90, 0.01, -0.01, 0.01, -0.01, 0.01],
            "description": "One observation dominates total absolute contribution.",
        },
        {
            "subject_id": "sample:insufficient",
            "observations": [0.01, -0.01],
            "description": "Insufficient observations for trusted tail/entropy assessment.",
        },
    ]


def build_tail_entropy_hardening_report(
    *,
    repo_root: Path = Path("."),
    observation_sets: list[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    manifest = tail_entropy_manifest()
    rows = list(observation_sets) if observation_sets is not None else _sample_observation_sets()

    diagnostics = []
    for row in rows:
        observations = row.get("observations") if isinstance(row, Mapping) else []
        diagnostic = diagnose_tail_entropy(observations if isinstance(observations, list) else [])
        diagnostics.append(
            {
                "subject_id": str(row.get("subject_id") or "unknown"),
                "description": str(row.get("description") or ""),
                "observation_count": diagnostic.observation_count,
                "negative_observation_count": diagnostic.negative_observation_count,
                "worst_observation": diagnostic.worst_observation,
                "best_observation": diagnostic.best_observation,
                "mean_observation": diagnostic.mean_observation,
                "largest_abs_contribution_share": diagnostic.largest_abs_contribution_share,
                "negative_contribution_share": diagnostic.negative_contribution_share,
                "sign_entropy_bits": diagnostic.sign_entropy_bits,
                "risk_state": diagnostic.risk_state,
                "explanation": diagnostic.explanation,
            }
        )

    risk_state_counts = Counter(item["risk_state"] for item in diagnostics)

    return {
        "schema_version": SCHEMA_VERSION,
        "report_kind": REPORT_KIND,
        "summary": {
            "tail_entropy_hardening_ready": True,
            "observation_set_count": len(rows),
            "diagnostic_count": len(diagnostics),
            "risk_state_counts": dict(sorted(risk_state_counts.items())),
            "final_recommendation": "tail_entropy_hardening_scaffold_ready",
            "operator_summary": (
                "Tail/entropy hardening diagnostics are available as deterministic, "
                "read-only context. They identify fragility but do not mutate candidates."
            ),
        },
        "manifest": manifest,
        "observation_sets": rows,
        "diagnostics": diagnostics,
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
            "# QRE Tail Entropy Hardening",
            "",
            f"- {summary.get('operator_summary') or ''}",
            "",
            "## Current Status",
            "",
            f"- tail_entropy_hardening_ready: {summary.get('tail_entropy_hardening_ready')}",
            f"- observation_set_count: {summary.get('observation_set_count')}",
            f"- diagnostic_count: {summary.get('diagnostic_count')}",
            f"- final_recommendation: {summary.get('final_recommendation')}",
            "",
        ]
    )


def _validate_write_target(path: Path) -> None:
    if WRITE_PREFIX not in path.as_posix():
        raise ValueError(
            f"qre_tail_entropy_hardening_report: refusing write outside allowlist: {path!r}"
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
        prog="python -m research.qre_tail_entropy_hardening_report",
        description="Build read-only QRE tail/entropy hardening report.",
    )
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args(argv)

    report = build_tail_entropy_hardening_report()
    if args.write:
        report["_artifact_paths"] = write_outputs(report)

    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())