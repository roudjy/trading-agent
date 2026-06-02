"""Read-only QRE closed-loop operator report."""

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
REPORT_KIND: Final[str] = "qre_closed_loop_operator_report"

ARTIFACT_DIR: Final[Path] = REPO_ROOT / "logs" / "qre_closed_loop_operator_report"
OUTPUT_ARTIFACT_RELATIVE_PATH: Final[str] = "logs/qre_closed_loop_operator_report/latest.json"
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

NOTE_INPUT_ISSUES: Final[str] = "closed_loop_inputs_missing_or_unparseable"
NOTE_REPORT_READY: Final[str] = "closed_loop_operator_report_ready"


def _utcnow() -> str:
    return _dt.datetime.now(_dt.UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


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


def _bounded_str(value: Any, *, max_len: int = 240) -> str:
    text = str(value or "").strip()
    if len(text) <= max_len:
        return text
    return text[: max_len - 3].rstrip() + "..."


def _safe_rows(payload: dict[str, Any] | None, field: str) -> list[dict[str, Any]]:
    if payload is None:
        return []
    rows = payload.get(field)
    if not isinstance(rows, list) or not all(isinstance(item, dict) for item in rows):
        return []
    return rows


def _str_list(value: Any, *, max_items: int = 24, max_len: int = 180) -> list[str]:
    if not isinstance(value, list):
        return []
    out: list[str] = []
    for item in value[:max_items]:
        text = _bounded_str(item, max_len=max_len)
        if text:
            out.append(text)
    return out


def _load(
    path: Path,
    *,
    expected_kind: str,
    field: str,
    label: str,
) -> tuple[list[dict[str, Any]], list[str], dict[str, Any]]:
    available, payload = _read_json(path)
    meta = {"path": _rel(path), "available": available, "valid": False}
    if payload is None or payload.get("report_kind") != expected_kind:
        return ([], [f"{label}:missing_or_unparseable"], meta)
    raw_rows = payload.get(field)
    if (
        field not in payload
        or not isinstance(raw_rows, list)
        or not all(isinstance(item, dict) for item in raw_rows)
    ):
        return ([], [f"{label}:missing_field"], meta)
    rows = _safe_rows(payload, field)
    meta["valid"] = True
    return (rows, [], meta)


def _blocked_links(
    hypotheses: list[dict[str, Any]],
    plans: list[dict[str, Any]],
    actions: list[dict[str, Any]],
    run_manifests: list[dict[str, Any]],
    results: list[dict[str, Any]],
    evidence_updates: list[dict[str, Any]],
) -> list[str]:
    blockers: list[str] = []
    hypothesis_ids = {_bounded_str(item.get("hypothesis_id"), max_len=160) for item in hypotheses}
    plan_hypothesis_ids = {_bounded_str(item.get("hypothesis_id"), max_len=160) for item in plans}
    action_plan_ids = {
        _bounded_str(item.get("target_validation_plan_id"), max_len=160) for item in actions
    }
    plan_ids = {_bounded_str(item.get("validation_plan_id"), max_len=160) for item in plans}
    manifest_action_ids = {
        _bounded_str(item.get("source_action_id"), max_len=160) for item in run_manifests
    }
    action_ids = {_bounded_str(item.get("action_id"), max_len=160) for item in actions}
    result_hypothesis_ids = {
        _bounded_str(item.get("hypothesis_id"), max_len=160) for item in results
    }
    update_hypothesis_ids = {
        _bounded_str(item.get("hypothesis_id"), max_len=160) for item in evidence_updates
    }
    if hypothesis_ids - plan_hypothesis_ids:
        blockers.append("hypothesis_without_validation_plan")
    if plan_ids - action_plan_ids:
        blockers.append("validation_plan_without_action_candidate")
    if action_ids - manifest_action_ids:
        blockers.append("action_candidate_without_run_manifest")
    if hypothesis_ids - result_hypothesis_ids:
        blockers.append("hypothesis_without_validation_result")
    if hypothesis_ids - update_hypothesis_ids:
        blockers.append("hypothesis_without_evidence_update")
    return blockers


def _operator_decisions_required(
    missing_validation_results: list[dict[str, Any]],
    run_manifests: list[dict[str, Any]],
    evidence_updates: list[dict[str, Any]],
    blocked_links: list[str],
) -> list[str]:
    decisions: list[str] = []
    if run_manifests:
        decisions.append("approve_or_reject_pending_run_manifests")
    if any(
        item.get("evidence_decision") in {"contradiction_detected", "needs_more_data"}
        for item in evidence_updates
    ):
        decisions.append("resolve_evidence_update_decisions")
    if missing_validation_results:
        decisions.append("provide_or_accept_missing_validation_results")
    if blocked_links:
        decisions.append("repair_or_accept_blocked_closed_loop_links")
    return decisions


def _result_index(results: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    by_hypothesis: dict[str, list[dict[str, Any]]] = {}
    for item in results:
        hypothesis_id = _bounded_str(item.get("hypothesis_id"), max_len=160)
        if hypothesis_id:
            by_hypothesis.setdefault(hypothesis_id, []).append(item)
    for rows in by_hypothesis.values():
        rows.sort(key=lambda row: _bounded_str(row.get("result_id"), max_len=160))
    return by_hypothesis


def _missing_validation_results(
    hypotheses: list[dict[str, Any]],
    results: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    result_by_hypothesis = _result_index(results)
    missing: list[dict[str, Any]] = []
    for hypothesis in hypotheses:
        hypothesis_id = _bounded_str(hypothesis.get("hypothesis_id"), max_len=160)
        if not hypothesis_id or hypothesis_id in result_by_hypothesis:
            continue
        missing.append(
            {
                "hypothesis_id": hypothesis_id,
                "title": _bounded_str(hypothesis.get("title"), max_len=180),
                "reason": "no_validation_result_linked",
                "safe_to_execute": False,
            }
        )
    missing.sort(key=lambda item: item["hypothesis_id"])
    return missing


def _bucketed_hypotheses(
    hypotheses: list[dict[str, Any]],
    evidence_updates: list[dict[str, Any]],
) -> dict[str, list[dict[str, Any]]]:
    hypotheses_by_id = {
        _bounded_str(item.get("hypothesis_id"), max_len=160): item
        for item in hypotheses
        if _bounded_str(item.get("hypothesis_id"), max_len=160)
    }
    buckets = {
        "top_supported_hypotheses": [],
        "top_falsified_hypotheses": [],
        "needs_more_data_hypotheses": [],
        "contradiction_hypotheses": [],
    }
    bucket_by_decision = {
        "supported": "top_supported_hypotheses",
        "falsified": "top_falsified_hypotheses",
        "needs_more_data": "needs_more_data_hypotheses",
        "inconclusive": "needs_more_data_hypotheses",
        "contradiction_detected": "contradiction_hypotheses",
    }
    for update in evidence_updates:
        hypothesis_id = _bounded_str(update.get("hypothesis_id"), max_len=160)
        bucket_name = bucket_by_decision.get(
            _bounded_str(update.get("evidence_decision"), max_len=80)
        )
        if not hypothesis_id or bucket_name is None:
            continue
        hypothesis = hypotheses_by_id.get(hypothesis_id, {})
        row = {
            "hypothesis_id": hypothesis_id,
            "title": _bounded_str(hypothesis.get("title"), max_len=180),
            "evidence_update_id": _bounded_str(update.get("evidence_update_id"), max_len=160),
            "evidence_decision": _bounded_str(update.get("evidence_decision"), max_len=80),
            "supporting_evidence_refs": _str_list(update.get("supporting_evidence_refs")),
            "contradicting_evidence_refs": _str_list(update.get("contradicting_evidence_refs")),
            "source_artifact": _bounded_str(update.get("source_artifact"), max_len=240),
            "safe_to_execute": False,
        }
        buckets[bucket_name].append(row)
    for rows in buckets.values():
        rows.sort(key=lambda item: (item["hypothesis_id"], item["evidence_update_id"]))
    return buckets


def _operator_guidance(
    *,
    missing_validation_results: list[dict[str, Any]],
    evidence_updates: list[dict[str, Any]],
    validation_warnings: list[str],
) -> tuple[str, list[str], list[str]]:
    if validation_warnings:
        readiness = "Input artifacts are missing or malformed; the loop remains scaffold-level."
    elif missing_validation_results:
        readiness = "Some hypotheses have no validation result; the loop is not trusted."
    elif any(
        item.get("evidence_decision") == "contradiction_detected" for item in evidence_updates
    ):
        readiness = "Contradictory evidence is visible and requires operator resolution."
    elif evidence_updates:
        readiness = "Evidence updates are available for manual readiness review."
    else:
        readiness = "No evidence updates are available; the loop remains planning-only."
    forbidden = [
        "QRE closed-loop reports are read-only operator aids.",
        "Research execution, queue writes, campaign mutation, and runtime activation require separate approved workflows.",
        "All safe_to_execute flags remain false in this report.",
    ]
    manual_actions: list[str] = []
    if missing_validation_results:
        manual_actions.append("review_missing_validation_results")
    if any(item.get("evidence_decision") == "contradiction_detected" for item in evidence_updates):
        manual_actions.append("resolve_contradictory_evidence")
    if any(
        item.get("evidence_decision") in {"needs_more_data", "inconclusive"}
        for item in evidence_updates
    ):
        manual_actions.append("decide_whether_more_data_is_required")
    if not manual_actions:
        manual_actions.append("review_evidence_lineage_before_any_follow_up")
    return (readiness, forbidden, manual_actions)


def _base_snapshot(
    *,
    generated_at_utc: str,
    operator_report: dict[str, Any],
    input_artifacts: dict[str, dict[str, Any]],
    validation_warnings: list[str],
) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "report_kind": REPORT_KIND,
        "generated_at_utc": generated_at_utc,
        "input_artifacts": input_artifacts,
        "note": NOTE_INPUT_ISSUES if validation_warnings else NOTE_REPORT_READY,
        "operator_report": operator_report,
        "validation_warnings": validation_warnings,
        "final_recommendation": operator_report["final_recommendation"],
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


def collect_snapshot(
    *,
    observations_path: Path | None = None,
    hypotheses_path: Path | None = None,
    validation_plans_path: Path | None = None,
    action_candidates_path: Path | None = None,
    run_manifests_path: Path | None = None,
    validation_results_path: Path | None = None,
    evidence_updates_path: Path | None = None,
    generated_at_utc: str | None = None,
) -> dict[str, Any]:
    generated = generated_at_utc or _utcnow()
    paths = {
        "observations": observations_path or DEFAULT_OBSERVATIONS_PATH,
        "hypotheses": hypotheses_path or DEFAULT_HYPOTHESES_PATH,
        "validation_plans": validation_plans_path or DEFAULT_PLANS_PATH,
        "action_candidates": action_candidates_path or DEFAULT_ACTIONS_PATH,
        "run_manifests": run_manifests_path or DEFAULT_RUN_MANIFESTS_PATH,
        "validation_results": validation_results_path or DEFAULT_RESULTS_PATH,
        "evidence_updates": evidence_updates_path or DEFAULT_EVIDENCE_UPDATES_PATH,
    }
    observations, warnings_a, meta_a = _load(
        paths["observations"],
        expected_kind="qre_market_observation_snapshot",
        field="observations",
        label="observations",
    )
    hypotheses, warnings_b, meta_b = _load(
        paths["hypotheses"],
        expected_kind="qre_hypothesis_candidates",
        field="hypotheses",
        label="hypotheses",
    )
    plans, warnings_c, meta_c = _load(
        paths["validation_plans"],
        expected_kind="qre_hypothesis_validation_plan",
        field="validation_plans",
        label="validation_plans",
    )
    actions, warnings_d, meta_d = _load(
        paths["action_candidates"],
        expected_kind="qre_validation_research_action_candidates",
        field="action_candidates",
        label="action_candidates",
    )
    run_manifests, warnings_e, meta_e = _load(
        paths["run_manifests"],
        expected_kind="qre_research_run_manifest",
        field="run_manifests",
        label="run_manifests",
    )
    results, warnings_f, meta_f = _load(
        paths["validation_results"],
        expected_kind="qre_hypothesis_validation_results",
        field="validation_results",
        label="validation_results",
    )
    updates, warnings_g, meta_g = _load(
        paths["evidence_updates"],
        expected_kind="qre_hypothesis_evidence_update",
        field="evidence_updates",
        label="evidence_updates",
    )
    validation_warnings = (
        warnings_a + warnings_b + warnings_c + warnings_d + warnings_e + warnings_f + warnings_g
    )
    blocked_links = _blocked_links(hypotheses, plans, actions, run_manifests, results, updates)
    missing_results = _missing_validation_results(hypotheses, results)
    decisions = _operator_decisions_required(
        missing_results,
        run_manifests,
        updates,
        blocked_links,
    )
    buckets = _bucketed_hypotheses(hypotheses, updates)
    readiness_explanation, forbidden_reasons, next_manual_actions = _operator_guidance(
        missing_validation_results=missing_results,
        evidence_updates=updates,
        validation_warnings=validation_warnings,
    )
    active_hypotheses = [
        item
        for item in hypotheses
        if _bounded_str(item.get("status"), max_len=80) not in {"rejected", "closed"}
    ]
    operator_report = {
        "active_hypotheses": active_hypotheses,
        "proposed_hypotheses": hypotheses,
        "validation_plans": plans,
        "pending_run_manifests": [
            item for item in run_manifests if item.get("status") == "operator_review_required"
        ],
        "validation_results": results,
        "evidence_updates": updates,
        "top_supported_hypotheses": buckets["top_supported_hypotheses"],
        "top_falsified_hypotheses": buckets["top_falsified_hypotheses"],
        "needs_more_data_hypotheses": buckets["needs_more_data_hypotheses"],
        "contradiction_hypotheses": buckets["contradiction_hypotheses"],
        "missing_validation_results": missing_results,
        "blocked_or_missing_links": blocked_links + validation_warnings,
        "operator_decisions_required": decisions,
        "readiness_explanation": readiness_explanation,
        "why_auto_execution_is_forbidden": forbidden_reasons,
        "next_manual_actions": next_manual_actions,
        "summary": (
            f"Closed-loop report: {len(observations)} observations, "
            f"{len(hypotheses)} hypotheses, {len(results)} validation results."
        ),
        "final_recommendation": (
            "operator_review_required"
            if decisions or validation_warnings
            else "closed_loop_evidence_ready_for_readiness_review"
        ),
        "safe_to_execute": False,
    }
    input_artifacts = {
        "observations": meta_a,
        "hypotheses": meta_b,
        "validation_plans": meta_c,
        "action_candidates": meta_d,
        "run_manifests": meta_e,
        "validation_results": meta_f,
        "evidence_updates": meta_g,
    }
    return _base_snapshot(
        generated_at_utc=generated,
        operator_report=operator_report,
        input_artifacts=input_artifacts,
        validation_warnings=validation_warnings,
    )


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    if not path.resolve().is_relative_to(ARTIFACT_DIR.resolve()):
        raise ValueError(f"refusing write outside QRE operator report dir: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    fd, tmp_name = tempfile.mkstemp(
        prefix=".qre_closed_loop_operator_report.",
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
        prog="reporting.qre_closed_loop_operator_report",
        description="Build a read-only closed-loop operator report.",
    )
    parser.add_argument("--no-write", action="store_true")
    parser.add_argument("--observations-source", type=Path, default=None)
    parser.add_argument("--hypotheses-source", type=Path, default=None)
    parser.add_argument("--plans-source", type=Path, default=None)
    parser.add_argument("--actions-source", type=Path, default=None)
    parser.add_argument("--run-manifests-source", type=Path, default=None)
    parser.add_argument("--results-source", type=Path, default=None)
    parser.add_argument("--evidence-updates-source", type=Path, default=None)
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
    "REPORT_KIND",
    "SCHEMA_VERSION",
    "collect_snapshot",
    "main",
    "write_outputs",
]
