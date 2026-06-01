"""Read-only QRE trusted-loop readiness gate."""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
import tempfile
from pathlib import Path
from typing import Any, Final

REPO_ROOT: Final[Path] = Path(__file__).resolve().parent.parent

SCHEMA_VERSION: Final[int] = 1
REPORT_KIND: Final[str] = "qre_trusted_loop_readiness"

ARTIFACT_DIR: Final[Path] = REPO_ROOT / "logs" / "qre_trusted_loop_readiness"
OUTPUT_ARTIFACT_RELATIVE_PATH: Final[str] = "logs/qre_trusted_loop_readiness/latest.json"
ARTIFACT_LATEST: Final[Path] = REPO_ROOT / OUTPUT_ARTIFACT_RELATIVE_PATH

DEFAULT_OBSERVATIONS_PATH: Final[Path] = (
    REPO_ROOT / "logs" / "qre_market_observations" / "latest.json"
)
DEFAULT_HYPOTHESES_PATH: Final[Path] = (
    REPO_ROOT / "logs" / "qre_hypothesis_candidates" / "latest.json"
)
DEFAULT_PLANS_PATH: Final[Path] = (
    REPO_ROOT / "logs" / "qre_hypothesis_validation_plans" / "latest.json"
)
DEFAULT_ACTIONS_PATH: Final[Path] = (
    REPO_ROOT / "logs" / "qre_validation_research_action_candidates" / "latest.json"
)
DEFAULT_RUN_MANIFESTS_PATH: Final[Path] = (
    REPO_ROOT / "logs" / "qre_research_run_manifest" / "latest.json"
)
DEFAULT_RESULTS_PATH: Final[Path] = (
    REPO_ROOT / "logs" / "qre_hypothesis_validation_results" / "latest.json"
)
DEFAULT_EVIDENCE_UPDATES_PATH: Final[Path] = (
    REPO_ROOT / "logs" / "qre_hypothesis_evidence_updates" / "latest.json"
)
DEFAULT_OPERATOR_REPORT_PATH: Final[Path] = (
    REPO_ROOT / "logs" / "qre_closed_loop_operator_report" / "latest.json"
)

READINESS_STATES: Final[tuple[str, ...]] = (
    "scaffold",
    "working_capability",
    "operator_trusted_candidate",
    "operator_trusted",
)

NOTE_READINESS_EVALUATED: Final[str] = "trusted_loop_readiness_evaluated"


def _utcnow() -> str:
    return (
        _dt.datetime.now(_dt.UTC)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def _rel(path: Path) -> str:
    try:
        return path.resolve().relative_to(REPO_ROOT.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def _read_json(path: Path) -> tuple[bool, dict[str, Any] | None]:
    try:
        raw = path.read_text(encoding="utf-8-sig")
    except OSError:
        return (False, None)
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return (True, None)
    return (True, parsed if isinstance(parsed, dict) else None)


def _safe_rows(payload: dict[str, Any] | None, field: str) -> list[dict[str, Any]]:
    if payload is None:
        return []
    rows = payload.get(field)
    if not isinstance(rows, list) or not all(isinstance(item, dict) for item in rows):
        return []
    return rows


def _load(
    path: Path,
    *,
    expected_kind: str,
    field: str | None,
    label: str,
) -> tuple[list[dict[str, Any]], dict[str, Any], list[str], dict[str, Any] | None]:
    available, payload = _read_json(path)
    meta = {"path": _rel(path), "available": available, "valid": False}
    if payload is None or payload.get("report_kind") != expected_kind:
        return ([], meta, [f"{label}:missing_or_unparseable"], payload)
    meta["valid"] = True
    if field is None:
        return ([], meta, [], payload)
    raw_rows = payload.get(field)
    if (
        field not in payload
        or not isinstance(raw_rows, list)
        or not all(isinstance(item, dict) for item in raw_rows)
    ):
        meta["valid"] = False
        return ([], meta, [f"{label}:missing_or_unparseable"], payload)
    return (_safe_rows(payload, field), meta, [], payload)


def _evidence_density(
    observations: list[dict[str, Any]],
    hypotheses: list[dict[str, Any]],
    plans: list[dict[str, Any]],
    actions: list[dict[str, Any]],
    run_manifests: list[dict[str, Any]],
    results: list[dict[str, Any]],
    updates: list[dict[str, Any]],
) -> dict[str, int]:
    return {
        "observations": len(observations),
        "hypotheses": len(hypotheses),
        "validation_plans": len(plans),
        "action_candidates": len(actions),
        "run_manifests": len(run_manifests),
        "validation_results": len(results),
        "evidence_updates": len(updates),
    }


def _contradiction_visibility(updates: list[dict[str, Any]]) -> dict[str, Any]:
    if not updates:
        return {"status": "missing", "contradiction_count": 0}
    contradiction_count = sum(
        1
        for item in updates
        if item.get("evidence_decision") == "contradiction_detected"
        or bool(item.get("contradicting_evidence_refs"))
    )
    visible_fields = all("contradicting_evidence_refs" in item for item in updates)
    return {
        "status": "visible" if visible_fields else "incomplete",
        "contradiction_count": contradiction_count,
    }


def _repeatability_status(
    results: list[dict[str, Any]],
    operator_payload: dict[str, Any] | None,
) -> str:
    approved = bool(
        operator_payload
        and operator_payload.get("operator_report", {}).get(
            "operator_approved_for_trusted_loop"
        )
    )
    repeatability_refs = [
        item.get("repeatability_evidence_refs")
        for item in results
        if isinstance(item.get("repeatability_evidence_refs"), list)
        and item.get("repeatability_evidence_refs")
    ]
    if approved and repeatability_refs:
        return "operator_approved_repeatability_evidence_present"
    if repeatability_refs:
        return "repeatability_evidence_present"
    return "no_repeatability_evidence"


def _state(
    *,
    input_warnings: list[str],
    density: dict[str, int],
    contradiction_visibility: dict[str, Any],
    operator_report_available: bool,
    repeatability_status: str,
) -> tuple[str, list[str], list[str]]:
    blockers: list[str] = []
    warnings: list[str] = []
    planning_present = all(
        density[key] > 0
        for key in (
            "observations",
            "hypotheses",
            "validation_plans",
            "action_candidates",
        )
    )
    evidence_present = density["validation_results"] > 0 and density["evidence_updates"] > 0
    contradiction_visible = contradiction_visibility["status"] == "visible"

    if input_warnings:
        blockers.extend(input_warnings)
        return ("scaffold", blockers, warnings)
    if not planning_present:
        blockers.append("planning_chain_incomplete")
        return ("scaffold", blockers, warnings)
    if not evidence_present:
        if operator_report_available:
            blockers.append("validation_results_or_evidence_updates_absent")
            return ("working_capability", blockers, warnings)
        blockers.append("operator_report_absent")
        return ("scaffold", blockers, warnings)
    if not operator_report_available:
        blockers.append("operator_report_absent")
        return ("scaffold", blockers, warnings)
    if not contradiction_visible:
        blockers.append("contradiction_visibility_incomplete")
        return ("working_capability", blockers, warnings)
    if repeatability_status == "operator_approved_repeatability_evidence_present":
        return ("operator_trusted", blockers, warnings)
    warnings.append("repeatability_or_explicit_operator_approval_absent")
    return ("operator_trusted_candidate", blockers, warnings)


def collect_snapshot(
    *,
    observations_path: Path | None = None,
    hypotheses_path: Path | None = None,
    validation_plans_path: Path | None = None,
    action_candidates_path: Path | None = None,
    run_manifests_path: Path | None = None,
    validation_results_path: Path | None = None,
    evidence_updates_path: Path | None = None,
    operator_report_path: Path | None = None,
    generated_at_utc: str | None = None,
) -> dict[str, Any]:
    generated = generated_at_utc or _utcnow()
    observations, meta_a, warnings_a, _payload_a = _load(
        observations_path or DEFAULT_OBSERVATIONS_PATH,
        expected_kind="qre_market_observation_snapshot",
        field="observations",
        label="observations",
    )
    hypotheses, meta_b, warnings_b, _payload_b = _load(
        hypotheses_path or DEFAULT_HYPOTHESES_PATH,
        expected_kind="qre_hypothesis_candidates",
        field="hypotheses",
        label="hypotheses",
    )
    plans, meta_c, warnings_c, _payload_c = _load(
        validation_plans_path or DEFAULT_PLANS_PATH,
        expected_kind="qre_hypothesis_validation_plan",
        field="validation_plans",
        label="validation_plans",
    )
    actions, meta_d, warnings_d, _payload_d = _load(
        action_candidates_path or DEFAULT_ACTIONS_PATH,
        expected_kind="qre_validation_research_action_candidates",
        field="action_candidates",
        label="action_candidates",
    )
    run_manifests, meta_e, warnings_e, _payload_e = _load(
        run_manifests_path or DEFAULT_RUN_MANIFESTS_PATH,
        expected_kind="qre_research_run_manifest",
        field="run_manifests",
        label="run_manifests",
    )
    results, meta_f, warnings_f, _payload_f = _load(
        validation_results_path or DEFAULT_RESULTS_PATH,
        expected_kind="qre_hypothesis_validation_results",
        field="validation_results",
        label="validation_results",
    )
    updates, meta_g, warnings_g, _payload_g = _load(
        evidence_updates_path or DEFAULT_EVIDENCE_UPDATES_PATH,
        expected_kind="qre_hypothesis_evidence_update",
        field="evidence_updates",
        label="evidence_updates",
    )
    _report_rows, meta_h, warnings_h, operator_payload = _load(
        operator_report_path or DEFAULT_OPERATOR_REPORT_PATH,
        expected_kind="qre_closed_loop_operator_report",
        field=None,
        label="operator_report",
    )
    input_warnings = (
        warnings_a
        + warnings_b
        + warnings_c
        + warnings_d
        + warnings_e
        + warnings_f
        + warnings_g
        + warnings_h
    )
    density = _evidence_density(
        observations,
        hypotheses,
        plans,
        actions,
        run_manifests,
        results,
        updates,
    )
    contradiction = _contradiction_visibility(updates)
    repeatability = _repeatability_status(results, operator_payload)
    operator_report_available = bool(meta_h["valid"])
    readiness_state, blockers, warnings = _state(
        input_warnings=input_warnings,
        density=density,
        contradiction_visibility=contradiction,
        operator_report_available=operator_report_available,
        repeatability_status=repeatability,
    )
    criteria = {
        "planning_chain_present": all(
            density[key] > 0
            for key in (
                "observations",
                "hypotheses",
                "validation_plans",
                "action_candidates",
            )
        ),
        "result_evidence_present": density["validation_results"] > 0
        and density["evidence_updates"] > 0,
        "operator_report_available": operator_report_available,
        "contradiction_visibility_available": contradiction["status"] == "visible",
        "repeatability_status": repeatability,
    }
    return {
        "schema_version": SCHEMA_VERSION,
        "report_kind": REPORT_KIND,
        "generated_at_utc": generated,
        "note": NOTE_READINESS_EVALUATED,
        "readiness_state": readiness_state,
        "criteria": criteria,
        "blockers": blockers,
        "warnings": warnings,
        "evidence_density": density,
        "contradiction_visibility": contradiction,
        "repeatability_status": repeatability,
        "operator_report_available": operator_report_available,
        "input_artifacts": {
            "observations": meta_a,
            "hypotheses": meta_b,
            "validation_plans": meta_c,
            "action_candidates": meta_d,
            "run_manifests": meta_e,
            "validation_results": meta_f,
            "evidence_updates": meta_g,
            "operator_report": meta_h,
        },
        "final_recommendation": (
            "trusted_loop_ready_for_operator_use"
            if readiness_state == "operator_trusted"
            else "operator_review_required_before_trusted_loop_use"
        ),
        "safe_to_execute": False,
        "writes_development_work_queue": False,
        "writes_seed_jsonl": False,
        "writes_generated_seed_jsonl": False,
        "writes_research_action_queue": False,
        "mutates_campaign_queue": False,
        "mutates_strategy_or_preset": False,
        "mutates_paper_shadow_live_runtime": False,
        "launches_codex": False,
        "eligible_for_direct_execution": False,
    }


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    if not path.resolve().is_relative_to(ARTIFACT_DIR.resolve()):
        raise ValueError(f"refusing write outside QRE trusted readiness dir: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    fd, tmp_name = tempfile.mkstemp(
        prefix=".qre_trusted_loop_readiness.",
        suffix=".tmp",
        dir=str(path.parent),
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(text)
        os.replace(tmp_name, path)
    except Exception:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise


def write_outputs(
    snapshot: dict[str, Any],
    *,
    output_path: Path | None = None,
) -> Path:
    target = output_path or ARTIFACT_LATEST
    _atomic_write_json(target, snapshot)
    return target


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="reporting.qre_trusted_loop_readiness",
        description="Evaluate read-only QRE trusted-loop readiness.",
    )
    parser.add_argument("--no-write", action="store_true")
    parser.add_argument("--observations-source", type=Path, default=None)
    parser.add_argument("--hypotheses-source", type=Path, default=None)
    parser.add_argument("--plans-source", type=Path, default=None)
    parser.add_argument("--actions-source", type=Path, default=None)
    parser.add_argument("--run-manifests-source", type=Path, default=None)
    parser.add_argument("--results-source", type=Path, default=None)
    parser.add_argument("--evidence-updates-source", type=Path, default=None)
    parser.add_argument("--operator-report-source", type=Path, default=None)
    parser.add_argument("--frozen-utc", default=None)
    parser.add_argument("--indent", type=int, default=2)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    snapshot = collect_snapshot(
        observations_path=args.observations_source,
        hypotheses_path=args.hypotheses_source,
        validation_plans_path=args.plans_source,
        action_candidates_path=args.actions_source,
        run_manifests_path=args.run_manifests_source,
        validation_results_path=args.results_source,
        evidence_updates_path=args.evidence_updates_source,
        operator_report_path=args.operator_report_source,
        generated_at_utc=args.frozen_utc,
    )
    if not args.no_write:
        write_outputs(snapshot)
    print(json.dumps(snapshot, indent=args.indent, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "ARTIFACT_DIR",
    "ARTIFACT_LATEST",
    "OUTPUT_ARTIFACT_RELATIVE_PATH",
    "READINESS_STATES",
    "REPORT_KIND",
    "SCHEMA_VERSION",
    "collect_snapshot",
    "main",
    "write_outputs",
]
