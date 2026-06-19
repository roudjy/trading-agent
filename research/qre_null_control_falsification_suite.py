from __future__ import annotations

import argparse
import hashlib
import json
import os
from collections import Counter
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Final, Literal

from research import qre_sampling_plan as sampling_plan


SuiteStatus = Literal[
    "suite_ready_preregistered_context",
    "blocked_invalid_sampling_plan",
    "blocked_missing_control_definition",
    "blocked_unlocked_control_definition",
    "blocked_post_hoc_control_selection",
]
EvaluationStatus = Literal[
    "controls_not_run",
    "controls_incomplete",
    "controls_failed",
    "controls_passed_context_only",
]

SCHEMA_VERSION: Final[str] = "1.0"
REPORT_KIND: Final[str] = "qre_null_control_falsification_suite"
DEFAULT_OUTPUT_DIR: Final[Path] = Path("logs/qre_null_control_falsification_suite")
LATEST_NAME: Final[str] = "latest.json"
SUMMARY_NAME: Final[str] = "operator_summary.md"
WRITE_PREFIX: Final[str] = "logs/qre_null_control_falsification_suite/"
DEFAULT_CONTROL_FAMILIES: Final[tuple[dict[str, str], ...]] = (
    {"control_id": "buy_and_hold_baseline", "control_family": "buy_and_hold"},
    {"control_id": "random_entry_matched_holding", "control_family": "random_entry"},
    {"control_id": "shuffled_signal_surrogate", "control_family": "shuffled_signal"},
    {"control_id": "simple_momentum_baseline", "control_family": "simple_momentum"},
    {"control_id": "simple_mean_reversion_baseline", "control_family": "simple_mean_reversion"},
    {"control_id": "regime_matched_null", "control_family": "regime_matched_null"},
    {"control_id": "turnover_matched_null", "control_family": "turnover_matched_null"},
    {"control_id": "cost_free_vs_cost_adjusted", "control_family": "cost_sensitivity"},
)
FORBIDDEN_SELECTION_TERMS: Final[tuple[str, ...]] = (
    "best_control",
    "best-performing control",
    "choose after results",
    "post_hoc",
    "profit",
    "sharpe",
    "return",
)


def _text(value: Any) -> str:
    return str(value or "").strip()


def _unique_in_order(values: Sequence[Any]) -> list[str]:
    return list(dict.fromkeys(_text(value) for value in values if _text(value)))


def _contains_forbidden_selection(value: Any) -> bool:
    lowered = _text(value).lower()
    return any(term in lowered for term in FORBIDDEN_SELECTION_TERMS)


def _canonical_control_definition(
    definition: Mapping[str, Any],
    *,
    fallback_family: str,
) -> dict[str, Any]:
    control_id = _text(definition.get("control_id"))
    control_family = _text(definition.get("control_family")) or fallback_family
    locked = bool(definition.get("locked", True))
    required_for_evidence_complete = bool(definition.get("required_for_evidence_complete", True))
    required_for_fail_closed_rejection = bool(definition.get("required_for_fail_closed_rejection", False))
    return {
        "control_id": control_id or control_family,
        "control_family": control_family,
        "locked": locked,
        "required_for_evidence_complete": required_for_evidence_complete,
        "required_for_fail_closed_rejection": required_for_fail_closed_rejection,
        "selection_policy": _text(definition.get("selection_policy")) or "preregistered_control_family",
        "justification": _text(definition.get("justification")) or "deterministic_preregistered_null_control",
    }


def compute_suite_hash(report: Mapping[str, Any]) -> str:
    canonical = {
        "schema_version": report.get("schema_version", SCHEMA_VERSION),
        "report_kind": report.get("report_kind", REPORT_KIND),
        "suite_id": report.get("suite_id", ""),
        "sampling_plan_ref": report.get("sampling_plan_ref", ""),
        "sampling_plan_hash": report.get("sampling_plan_hash", ""),
        "status": report.get("status", ""),
        "blocked_reasons": list(report.get("blocked_reasons", [])),
        "control_definitions": list(report.get("control_definitions", [])),
        "evaluation": dict(report.get("evaluation", {})),
        "authority": dict(report.get("authority", {})),
    }
    blob = json.dumps(canonical, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def build_preregistered_null_control_suite(
    *,
    sampling_plan_payload: Mapping[str, Any],
    control_families: Sequence[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    sampling_validation = sampling_plan.validate_sampling_plan(sampling_plan_payload)
    blocked_reasons: list[str] = []
    status: SuiteStatus = "suite_ready_preregistered_context"

    if sampling_validation["valid"] is not True or _text(sampling_plan_payload.get("status")) != "sampling_plan_ready_context_only":
        status = "blocked_invalid_sampling_plan"
        blocked_reasons.extend(list(sampling_validation.get("rejection_reasons") or []))
        blocked_reasons.extend(_unique_in_order(sampling_plan_payload.get("blocked_reasons") or []))

    supplied = list(sampling_plan_payload.get("null_control_definitions") or [])
    if not supplied:
        status = "blocked_missing_control_definition"
        blocked_reasons.append("missing_null_control_definition")

    controls_by_family = {
        _text(item.get("control_family") or item.get("control_id")): item
        for item in (control_families or DEFAULT_CONTROL_FAMILIES)
        if isinstance(item, Mapping)
    }
    control_definitions: list[dict[str, Any]] = []
    for definition in supplied:
        if not isinstance(definition, Mapping):
            continue
        supplied_family = _text(definition.get("control_family") or definition.get("control_id"))
        fallback_family = supplied_family or "unknown"
        merged = dict(controls_by_family.get(supplied_family, {}))
        merged.update(dict(definition))
        canonical = _canonical_control_definition(merged, fallback_family=fallback_family)
        if canonical["locked"] is not True:
            status = "blocked_unlocked_control_definition"
            blocked_reasons.append(f"control_not_locked:{canonical['control_id']}")
        if _contains_forbidden_selection(canonical.get("selection_policy")) or _contains_forbidden_selection(
            canonical.get("justification")
        ):
            status = "blocked_post_hoc_control_selection"
            blocked_reasons.append(f"post_hoc_control_selection:{canonical['control_id']}")
        control_definitions.append(canonical)

    suite_seed = {
        "sampling_plan_id": _text(sampling_plan_payload.get("sampling_plan_id")),
        "sampling_plan_hash": _text(sampling_plan_payload.get("hash")),
        "control_definitions": control_definitions,
    }
    suite_id = "qnc_" + hashlib.sha256(
        json.dumps(suite_seed, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    ).hexdigest()[:16]

    report = {
        "schema_version": SCHEMA_VERSION,
        "report_kind": REPORT_KIND,
        "suite_id": suite_id,
        "sampling_plan_ref": _text(sampling_plan_payload.get("sampling_plan_id")),
        "sampling_plan_hash": _text(sampling_plan_payload.get("hash")),
        "status": status,
        "blocked_reasons": _unique_in_order(blocked_reasons),
        "control_definitions": control_definitions,
        "evaluation": {
            "status": "controls_not_run",
            "required_control_count": sum(
                1 for item in control_definitions if bool(item.get("required_for_evidence_complete"))
            ),
            "completed_control_count": 0,
            "passed_control_count": 0,
            "failed_control_count": 0,
            "missing_control_ids": [
                str(item["control_id"])
                for item in control_definitions
                if bool(item.get("required_for_evidence_complete"))
            ],
            "failed_control_ids": [],
            "recommended_next_action": "materialize_preregistered_controls_before_evidence_complete",
            "blockers": [
                "null_controls_not_materialized_for_preregistered_scope"
            ]
            if control_definitions
            else ["missing_preregistered_null_control_definitions"],
            "candidate_context_refs": [],
            "control_result_rows": [],
        },
        "authority": {
            "non_authoritative": True,
            "can_authorize_execution": False,
            "can_clear_evidence_blockers": False,
            "can_promote_candidate": False,
            "evidence_authority": "context_only",
        },
    }
    report["hash"] = compute_suite_hash(report)
    return report


def evaluate_null_control_suite(
    suite_report: Mapping[str, Any],
    *,
    candidate_context: Mapping[str, Any] | None = None,
    control_results: Sequence[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    control_rows = [dict(item) for item in suite_report.get("control_definitions", []) if isinstance(item, Mapping)]
    results_index = {
        _text(item.get("control_id")): dict(item)
        for item in (control_results or [])
        if isinstance(item, Mapping) and _text(item.get("control_id"))
    }
    completed_control_count = 0
    passed_control_count = 0
    failed_control_count = 0
    missing_control_ids: list[str] = []
    failed_control_ids: list[str] = []
    result_rows: list[dict[str, Any]] = []

    for row in control_rows:
        control_id = _text(row.get("control_id"))
        result = results_index.get(control_id, {})
        result_status = _text(result.get("result_status")) or "missing"
        passed = bool(result.get("passed", False)) if result_status != "missing" else False
        if result_status != "missing":
            completed_control_count += 1
        if passed:
            passed_control_count += 1
        elif result_status != "missing":
            failed_control_count += 1
            failed_control_ids.append(control_id)
        if bool(row.get("required_for_evidence_complete")) and result_status == "missing":
            missing_control_ids.append(control_id)
        result_rows.append(
            {
                "control_id": control_id,
                "control_family": _text(row.get("control_family")),
                "required_for_evidence_complete": bool(row.get("required_for_evidence_complete")),
                "result_status": result_status,
                "passed": passed,
                "evidence_refs": _unique_in_order(result.get("evidence_refs") or []),
                "failure_reason": _text(result.get("failure_reason")),
            }
        )

    evaluation_status: EvaluationStatus
    blockers: list[str]
    recommended_next_action: str
    if failed_control_ids:
        evaluation_status = "controls_failed"
        blockers = ["null_control_failure_detected"]
        recommended_next_action = "reject_hypothesis_or_expand_falsification_review"
    elif missing_control_ids:
        evaluation_status = "controls_incomplete"
        blockers = ["null_controls_incomplete"]
        recommended_next_action = "materialize_missing_preregistered_controls"
    elif control_rows:
        evaluation_status = "controls_passed_context_only"
        blockers = []
        recommended_next_action = "route_to_operator_review_with_control_context"
    else:
        evaluation_status = "controls_not_run"
        blockers = ["missing_preregistered_null_control_definitions"]
        recommended_next_action = "define_preregistered_controls"

    updated = dict(suite_report)
    updated["evaluation"] = {
        "status": evaluation_status,
        "required_control_count": sum(
            1 for item in control_rows if bool(item.get("required_for_evidence_complete"))
        ),
        "completed_control_count": completed_control_count,
        "passed_control_count": passed_control_count,
        "failed_control_count": failed_control_count,
        "missing_control_ids": missing_control_ids,
        "failed_control_ids": _unique_in_order(failed_control_ids),
        "recommended_next_action": recommended_next_action,
        "blockers": blockers,
        "candidate_context_refs": _unique_in_order(
            [
                _text((candidate_context or {}).get("campaign_id")),
                _text((candidate_context or {}).get("sampling_plan_id")),
            ]
        ),
        "control_result_rows": result_rows,
    }
    updated["hash"] = compute_suite_hash(updated)
    return updated


def _table(headers: Sequence[str], rows: Sequence[Sequence[str]]) -> str:
    head = "| " + " | ".join(headers) + " |"
    divider = "| " + " | ".join(["---"] * len(headers)) + " |"
    body = ["| " + " | ".join(row) + " |" for row in rows]
    return "\n".join([head, divider, *body])


def render_operator_summary(report: Mapping[str, Any]) -> str:
    evaluation = report.get("evaluation") if isinstance(report.get("evaluation"), Mapping) else {}
    controls = report.get("control_definitions") if isinstance(report.get("control_definitions"), list) else []
    return "\n".join(
        [
            "# QRE Null-Control Falsification Suite",
            "",
            "- Preregistered control families are read-only context and never promote candidates or authorize execution.",
            "",
            "## Summary",
            _table(
                ["Field", "Value"],
                [
                    ["suite_id", _text(report.get("suite_id"))],
                    ["status", _text(report.get("status"))],
                    ["evaluation_status", _text(evaluation.get("status"))],
                    ["required_control_count", str(evaluation.get("required_control_count") or 0)],
                    ["completed_control_count", str(evaluation.get("completed_control_count") or 0)],
                    ["failed_control_count", str(evaluation.get("failed_control_count") or 0)],
                    ["recommended_next_action", _text(evaluation.get("recommended_next_action"))],
                ],
            ),
            "",
            "## Controls",
            _table(
                ["Control", "Family", "Locked", "Required", "Result"],
                [
                    [
                        _text(item.get("control_id")),
                        _text(item.get("control_family")),
                        str(bool(item.get("locked"))).lower(),
                        str(bool(item.get("required_for_evidence_complete"))).lower(),
                        _text(
                            next(
                                (
                                    row.get("result_status")
                                    for row in evaluation.get("control_result_rows", [])
                                    if _text((row or {}).get("control_id")) == _text(item.get("control_id"))
                                ),
                                "missing",
                            )
                        ),
                    ]
                    for item in controls
                ],
            ),
            "",
        ]
    )


def _validate_write_target(path: Path) -> None:
    if WRITE_PREFIX not in path.as_posix():
        raise ValueError(f"{REPORT_KIND}: refusing write outside allowlist: {path!r}")


def write_outputs(report: Mapping[str, Any], *, repo_root: Path = Path(".")) -> dict[str, str]:
    base = repo_root / DEFAULT_OUTPUT_DIR
    base.mkdir(parents=True, exist_ok=True)
    latest = base / LATEST_NAME
    summary_path = base / SUMMARY_NAME
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


def read_null_control_suite_status(
    *,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    repo_root: Path = Path("."),
) -> dict[str, Any]:
    latest = repo_root / output_dir / LATEST_NAME
    if not latest.is_file():
        return {
            "status": "missing_null_control_suite",
            "null_control_suite_ready": False,
            "path": latest.relative_to(repo_root).as_posix(),
            "fails_closed": True,
        }
    try:
        payload = json.loads(latest.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {
            "status": "invalid_null_control_suite",
            "null_control_suite_ready": False,
            "path": latest.relative_to(repo_root).as_posix(),
            "fails_closed": True,
        }
    status = _text(payload.get("status"))
    ready = status == "suite_ready_preregistered_context"
    return {
        "status": "ready" if ready else "not_ready",
        "null_control_suite_ready": ready,
        "path": latest.relative_to(repo_root).as_posix(),
        "fails_closed": not ready,
        "suite_status": status,
        "schema_version": payload.get("schema_version") if isinstance(payload, Mapping) else None,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m research.qre_null_control_falsification_suite",
        description="Build deterministic preregistered null/control suite context.",
    )
    parser.add_argument("--sampling-plan-file")
    parser.add_argument("--status", action="store_true")
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args(argv)
    if args.status:
        print(json.dumps(read_null_control_suite_status(), indent=2, sort_keys=True))
        return 0
    if not args.sampling_plan_file:
        raise SystemExit("--sampling-plan-file is required unless --status is used")
    sampling_payload = json.loads(Path(args.sampling_plan_file).read_text(encoding="utf-8"))
    report = build_preregistered_null_control_suite(sampling_plan_payload=sampling_payload)
    if args.write:
        report["_artifact_paths"] = write_outputs(report)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


__all__ = [
    "DEFAULT_CONTROL_FAMILIES",
    "REPORT_KIND",
    "SCHEMA_VERSION",
    "build_preregistered_null_control_suite",
    "compute_suite_hash",
    "evaluate_null_control_suite",
    "read_null_control_suite_status",
    "render_operator_summary",
    "write_outputs",
]
