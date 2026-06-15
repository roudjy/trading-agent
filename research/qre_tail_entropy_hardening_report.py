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
            "evidence_refs": [
                "logs/qre_state_transition_diagnostics/latest.json",
                "logs/qre_null_model_baseline/latest.json",
            ],
            "null_challenges": [
                "sign_entropy_null",
                "random_walk_null",
            ],
        },
        {
            "subject_id": "sample:single_trade_concentration",
            "observations": [0.90, 0.01, -0.01, 0.01, -0.01, 0.01],
            "description": "One observation dominates total absolute contribution.",
            "evidence_refs": ["logs/qre_null_model_baseline/latest.json"],
            "null_challenges": ["single_trade_concentration_null"],
        },
        {
            "subject_id": "sample:insufficient",
            "observations": [0.01, -0.01],
            "description": "Insufficient observations for trusted tail/entropy assessment.",
            "evidence_refs": [],
            "null_challenges": ["insufficient_return_data_null"],
        },
    ]


def _density_state(*, evidence_ref_count: int, null_challenge_count: int, observation_count: int) -> str:
    if observation_count < 5:
        return "missing_density"
    if evidence_ref_count == 0 or null_challenge_count == 0:
        return "partial_density"
    if evidence_ref_count < 2 or null_challenge_count < 2:
        return "thin_density"
    return "density_ready"


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
        evidence_refs = row.get("evidence_refs") if isinstance(row, Mapping) else []
        null_challenges = row.get("null_challenges") if isinstance(row, Mapping) else []
        diagnostic = diagnose_tail_entropy(observations if isinstance(observations, list) else [])
        evidence_ref_count = len(evidence_refs) if isinstance(evidence_refs, list) else 0
        null_challenge_count = len(null_challenges) if isinstance(null_challenges, list) else 0
        evidence_density_ratio = (
            round(evidence_ref_count / diagnostic.observation_count, 6)
            if diagnostic.observation_count
            else 0.0
        )
        density_state = _density_state(
            evidence_ref_count=evidence_ref_count,
            null_challenge_count=null_challenge_count,
            observation_count=diagnostic.observation_count,
        )
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
                "evidence_ref_count": evidence_ref_count,
                "null_challenge_count": null_challenge_count,
                "evidence_density_ratio": evidence_density_ratio,
                "density_state": density_state,
                "risk_state": diagnostic.risk_state,
                "explanation": diagnostic.explanation,
            }
        )

    risk_state_counts = Counter(item["risk_state"] for item in diagnostics)
    density_state_counts = Counter(item["density_state"] for item in diagnostics)
    sparse_density_count = sum(1 for item in diagnostics if item["density_state"] == "missing_density")
    challenged_density_count = sum(1 for item in diagnostics if item["null_challenge_count"] > 0)

    return {
        "schema_version": SCHEMA_VERSION,
        "report_kind": REPORT_KIND,
        "summary": {
            "tail_entropy_hardening_ready": True,
            "observation_set_count": len(rows),
            "diagnostic_count": len(diagnostics),
            "risk_state_counts": dict(sorted(risk_state_counts.items())),
            "density_state_counts": dict(sorted(density_state_counts.items())),
            "sparse_density_count": sparse_density_count,
            "challenged_density_count": challenged_density_count,
            "final_recommendation": "tail_entropy_evidence_density_ready",
            "operator_summary": (
                "Tail/entropy hardening diagnostics are available as deterministic, read-only "
                "context with evidence-density and null-challenge annotations. They identify "
                "fragility but do not mutate candidates."
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
            "evidence_density_context_only": True,
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
            f"- sparse_density_count: {summary.get('sparse_density_count')}",
            f"- challenged_density_count: {summary.get('challenged_density_count')}",
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
