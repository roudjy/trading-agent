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
EVIDENCE_ARTIFACTS: Final[tuple[tuple[str, Path], ...]] = (
    ("source_quality", Path("logs/qre_data_source_quality_readiness/latest.json")),
    ("cache_manifest", Path("logs/qre_data_cache_manifest/latest.json")),
    ("null_model", Path("logs/qre_null_model_baseline/latest.json")),
    ("state_transition", Path("logs/qre_state_transition_diagnostics/latest.json")),
    ("tail_entropy", Path("logs/qre_tail_entropy_hardening/latest.json")),
)


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


def _load_json_artifact(repo_root: Path, relative_path: Path) -> Mapping[str, Any] | None:
    path = repo_root / relative_path
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, Mapping) else None


def _limit_mappings(rows: Any, limit: int) -> list[Mapping[str, Any]]:
    if not isinstance(rows, list):
        return []
    result: list[Mapping[str, Any]] = []
    for row in rows:
        if isinstance(row, Mapping):
            result.append(row)
        if len(result) >= limit:
            break
    return result


def _rows_from_source_quality_report(report: Mapping[str, Any] | None) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for row in _limit_mappings((report or {}).get("rows"), 2):
        instrument = str(row.get("instrument") or "unknown")
        timeframe = str(row.get("timeframe") or "unknown")
        quality_status = str(row.get("quality_status") or "unknown")
        manifest_status = str(row.get("manifest_status") or "unknown")
        identity_confidence = str(row.get("identity_confidence") or "unknown")
        rows.append(
            {
                "subject_id": f"source_quality:{instrument}:{timeframe}",
                "asset_class": "equity",
                "research_scope": "target_source_data_research",
                "readiness_state": quality_status,
                "title": f"{instrument} {timeframe} source quality {quality_status}",
                "text_preview": str(row.get("operator_explanation") or ""),
                "metadata": {
                    "source": row.get("source"),
                    "cache_kind": row.get("cache_kind"),
                    "manifest_status": manifest_status,
                    "identity_confidence": identity_confidence,
                    "blocking_reasons": list(row.get("blocking_reasons") or []),
                },
                "evidence_refs": [
                    "logs/qre_data_source_quality_readiness/latest.json",
                    "logs/qre_data_cache_manifest/latest.json",
                ],
                "evidence_presence": {
                    "source_quality_ready": quality_status == "ready",
                    "source_identity_ready": identity_confidence == "high",
                    "manifest_ready": manifest_status == "ready",
                },
                "artifact_id": str(row.get("path") or ""),
            }
        )
    return rows


def _rows_from_cache_manifest_report(report: Mapping[str, Any] | None) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for row in _limit_mappings((report or {}).get("coverage"), 2):
        instrument = str(row.get("instrument") or "unknown")
        timeframe = str(row.get("timeframe") or "unknown")
        ready = bool(row.get("ready"))
        rows.append(
            {
                "subject_id": f"cache_manifest:{instrument}:{timeframe}",
                "asset_class": "equity",
                "research_scope": "target_source_data_research",
                "readiness_state": "ready" if ready else "blocked",
                "title": f"{instrument} {timeframe} cache coverage {'ready' if ready else 'blocked'}",
                "text_preview": f"row_count={row.get('row_count')} file_count={row.get('file_count')}",
                "metadata": {
                    "source": row.get("source"),
                    "cache_kind": "coverage",
                    "ready": ready,
                    "status_counts": row.get("status_counts"),
                    "content_hash": row.get("content_hash"),
                },
                "evidence_refs": ["logs/qre_data_cache_manifest/latest.json"],
                "evidence_presence": {
                    "cache_ready": ready,
                    "coverage_present": True,
                    "data_ready": ready,
                },
                "artifact_id": str(row.get("content_hash") or ""),
            }
        )
    return rows


def _rows_from_null_model_report(report: Mapping[str, Any] | None) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    sample_comparisons = _limit_mappings((report or {}).get("sample_comparisons"), 2)
    suite_comparisons = _limit_mappings((report or {}).get("suite_comparisons"), 2)

    for row in sample_comparisons:
        comparison_state = str(row.get("comparison_state") or "unknown")
        candidate_id = str(row.get("candidate_id") or "unknown")
        rows.append(
            {
                "subject_id": f"null_model_sample:{candidate_id}",
                "asset_class": "fundamental_equity",
                "research_scope": "target_factor_research",
                "readiness_state": (
                    "ready" if comparison_state in {"candidate_above_baseline", "candidate_equal_to_baseline"} else "blocked"
                ),
                "comparison_state": comparison_state,
                "baseline_type": str(row.get("baseline_type") or "median_candidate"),
                "title": f"{candidate_id} {comparison_state}",
                "text_preview": str(row.get("explanation") or ""),
                "metadata": {
                    "baseline_metric": row.get("baseline_metric"),
                    "candidate_metric": row.get("candidate_metric"),
                    "delta_vs_baseline": row.get("delta_vs_baseline"),
                },
                "evidence_refs": ["logs/qre_null_model_baseline/latest.json"],
                "evidence_presence": {
                    "null_model_ready": True,
                    "baseline_ready": True,
                    "comparison_ready": True,
                },
                "artifact_id": f"{candidate_id}:{comparison_state}",
            }
        )

    for row in suite_comparisons:
        comparison_state = str(row.get("comparison_state") or "unknown")
        candidate_id = str(row.get("candidate_id") or "unknown")
        family = str(row.get("family") or "unknown")
        rows.append(
            {
                "subject_id": f"null_model_suite:{family}:{candidate_id}",
                "asset_class": "fundamental_equity",
                "research_scope": "target_factor_research",
                "readiness_state": (
                    "ready" if comparison_state in {"candidate_above_baseline", "candidate_equal_to_baseline"} else "blocked"
                ),
                "comparison_state": comparison_state,
                "baseline_type": family,
                "title": f"{family} {candidate_id} {comparison_state}",
                "text_preview": str(row.get("explanation") or ""),
                "metadata": {
                    "baseline_metric": row.get("baseline_metric"),
                    "candidate_metric": row.get("candidate_metric"),
                    "delta_vs_baseline": row.get("delta_vs_baseline"),
                    "family": family,
                },
                "evidence_refs": ["logs/qre_null_model_baseline/latest.json"],
                "evidence_presence": {
                    "null_model_ready": True,
                    "baseline_ready": True,
                    "comparison_ready": True,
                },
                "artifact_id": f"{family}:{candidate_id}:{comparison_state}",
            }
        )
    return rows


def _rows_from_state_transition_report(report: Mapping[str, Any] | None) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for row in _limit_mappings((report or {}).get("diagnostics"), 2):
        subject_id = str(row.get("subject_id") or "unknown")
        transition_state = str(row.get("transition_state") or "unknown")
        rows.append(
            {
                "subject_id": f"state_transition:{subject_id}",
                "asset_class": "equity",
                "research_scope": "target_equity_research",
                "readiness_state": "blocked" if transition_state == "terminal_negative_transition" else "ready",
                "title": f"{subject_id} {transition_state}",
                "text_preview": str(row.get("transition_reason") or ""),
                "metadata": {
                    "prior_state": row.get("prior_state"),
                    "new_state": row.get("new_state"),
                    "blocker_class": row.get("blocker_class"),
                    "transition_state": transition_state,
                },
                "evidence_refs": ["logs/qre_state_transition_diagnostics/latest.json"],
                "evidence_presence": {
                    "diagnostic_ready": True,
                    "state_transition_ready": True,
                    "regime_ready": True,
                },
                "artifact_id": str(row.get("artifact_ref") or ""),
            }
        )

    for row in _limit_mappings((report or {}).get("sequence_diagnostics"), 2):
        subject_id = str(row.get("subject_id") or "unknown")
        sparse_data = bool(row.get("sparse_data"))
        rows.append(
            {
                "subject_id": f"regime:{subject_id}",
                "asset_class": "equity",
                "research_scope": "target_equity_research",
                "readiness_state": "blocked" if sparse_data else "ready",
                "title": f"{subject_id} regime duration {row.get('regime_duration_steps')}",
                "text_preview": str(row.get("explanation") or ""),
                "metadata": {
                    "sequence_state": row.get("sequence_state"),
                    "dwell_state": row.get("dwell_state"),
                    "dwell_steps": row.get("dwell_steps"),
                    "regime_duration_steps": row.get("regime_duration_steps"),
                },
                "evidence_refs": ["logs/qre_state_transition_diagnostics/latest.json"],
                "evidence_presence": {
                    "diagnostic_ready": True,
                    "sequence_ready": True,
                    "regime_ready": True,
                },
                "artifact_id": str(row.get("subject_id") or ""),
            }
        )
    return rows


def _rows_from_tail_entropy_report(report: Mapping[str, Any] | None) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for row in _limit_mappings((report or {}).get("diagnostics"), 2):
        subject_id = str(row.get("subject_id") or "unknown")
        risk_state = str(row.get("risk_state") or "unknown")
        density_state = str(row.get("density_state") or "unknown")
        rows.append(
            {
                "subject_id": f"tail_entropy:{subject_id}",
                "asset_class": "equity",
                "research_scope": "target_equity_research",
                "readiness_state": "blocked" if risk_state != "tail_entropy_clear" else "ready",
                "title": f"{subject_id} {risk_state} {density_state}",
                "text_preview": str(row.get("explanation") or ""),
                "metadata": {
                    "risk_state": risk_state,
                    "density_state": density_state,
                    "null_challenge_count": row.get("null_challenge_count"),
                    "evidence_ref_count": row.get("evidence_ref_count"),
                },
                "evidence_refs": ["logs/qre_tail_entropy_hardening/latest.json"],
                "evidence_presence": {
                    "diagnostic_ready": True,
                    "tail_entropy_ready": True,
                    "regime_ready": True,
                },
                "artifact_id": str(subject_id),
            }
        )
    return rows


def _rows_from_repo_evidence(repo_root: Path) -> list[dict[str, Any]]:
    source_quality = _load_json_artifact(repo_root, EVIDENCE_ARTIFACTS[0][1])
    cache_manifest = _load_json_artifact(repo_root, EVIDENCE_ARTIFACTS[1][1])
    null_model = _load_json_artifact(repo_root, EVIDENCE_ARTIFACTS[2][1])
    state_transition = _load_json_artifact(repo_root, EVIDENCE_ARTIFACTS[3][1])
    tail_entropy = _load_json_artifact(repo_root, EVIDENCE_ARTIFACTS[4][1])
    rows: list[dict[str, Any]] = []
    rows.extend(_rows_from_source_quality_report(source_quality))
    rows.extend(_rows_from_cache_manifest_report(cache_manifest))
    rows.extend(_rows_from_null_model_report(null_model))
    rows.extend(_rows_from_state_transition_report(state_transition))
    rows.extend(_rows_from_tail_entropy_report(tail_entropy))
    return rows


def build_sampling_calibration_report(
    *,
    repo_root: Path = Path("."),
    rows: list[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    manifest = sampling_calibration_manifest()
    input_rows = list(rows) if rows is not None else _rows_from_repo_evidence(repo_root)
    if not input_rows:
        input_rows = _sample_rows()
    calibrations = calibrate_sampling_rows(input_rows)

    decision_counts = Counter(item.sampling_decision for item in calibrations)
    preferred_axis_counts = Counter(axis for item in calibrations for axis in item.preferred_axes)
    penalty_axis_counts = Counter(axis for item in calibrations for axis in item.penalty_axes)
    evidence_support_counts = Counter(item.evidence_support_state for item in calibrations)
    evidence_category_counts = Counter(
        category for item in calibrations for category in item.evidence_categories
    )

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
            "evidence_support_state_counts": dict(sorted(evidence_support_counts.items())),
            "evidence_category_counts": dict(sorted(evidence_category_counts.items())),
            "null_model_backed_count": evidence_support_counts.get("evidence_backed", 0),
            "partial_evidence_count": evidence_support_counts.get("partial_evidence", 0),
            "heuristic_only_count": evidence_support_counts.get("heuristic_only", 0),
            "crypto_legacy_excluded_count": penalty_axis_counts.get("asset_class:crypto_legacy", 0),
            "final_recommendation": (
                "sampling_calibration_evidence_ready"
                if evidence_support_counts.get("evidence_backed", 0) > 0
                else "sampling_calibration_scaffold_ready"
            ),
            "operator_summary": (
                "Sampling calibration is available as deterministic, read-only context. "
                "It now prefers source, cache, null-model, readiness, and regime evidence "
                "loaded from local report artifacts without mutating candidates or campaigns."
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
                "evidence_support_state": item.evidence_support_state,
                "evidence_categories": list(item.evidence_categories),
                "evidence_ref_count": item.evidence_ref_count,
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
            "evidence_backed_context_only": True,
        },
    }


def render_operator_summary(report: Mapping[str, Any]) -> str:
    summary = report.get("summary") if isinstance(report.get("summary"), Mapping) else {}
    counts = summary.get("sampling_decision_counts") or {}
    support_counts = summary.get("evidence_support_state_counts") or {}
    rows = report.get("calibrations") if isinstance(report.get("calibrations"), list) else []
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
            f"- null_model_backed_count: {summary.get('null_model_backed_count')}",
            f"- partial_evidence_count: {summary.get('partial_evidence_count')}",
            f"- heuristic_only_count: {summary.get('heuristic_only_count')}",
            f"- final_recommendation: {summary.get('final_recommendation')}",
            "",
            "## Decision Mix",
            ", ".join(f"{key}={value}" for key, value in sorted(counts.items())),
            "",
            "## Evidence Support Mix",
            ", ".join(f"{key}={value}" for key, value in sorted(support_counts.items())),
            "",
            "## Calibrations",
            *[
                f"- {str(row.get('subject_id') or '')}: "
                f"{', '.join(str(axis) for axis in row.get('preferred_axes') or [])} "
                f"({str(row.get('evidence_support_state') or '')})"
                for row in rows
            ],
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
