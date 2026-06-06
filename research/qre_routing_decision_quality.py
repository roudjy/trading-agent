from __future__ import annotations

import argparse
import json
import os
from collections import Counter
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Final

from research import qre_failure_action_from_basket as failure_action
from research import qre_reason_records_v1 as reason_records
from research import qre_routing_readiness_from_basket as routing


REPORT_KIND: Final[str] = "qre_routing_decision_quality"
SCHEMA_VERSION: Final[str] = "1.0"
DEFAULT_OUTPUT_DIR: Final[Path] = Path("logs/qre_routing_decision_quality")
LATEST_NAME: Final[str] = "latest.json"
OPERATOR_SUMMARY_NAME: Final[str] = "operator_summary.md"
_WRITE_PREFIX: Final[str] = "logs/qre_routing_decision_quality/"


def _table(headers: Sequence[str], rows: Sequence[Sequence[str]]) -> str:
    head = "| " + " | ".join(headers) + " |"
    divider = "| " + " | ".join(["---"] * len(headers)) + " |"
    body = ["| " + " | ".join(row) + " |" for row in rows]
    return "\n".join([head, divider, *body])


def _reason_ref_index(records: Sequence[Mapping[str, Any]]) -> dict[str, dict[str, list[str]]]:
    by_subject: dict[str, dict[str, list[str]]] = {}
    for record in records:
        subject_id = str(record.get("subject_id") or "")
        if not subject_id:
            continue
        bucket = by_subject.setdefault(
            subject_id,
            {"record_ids": [], "record_families": [], "evidence_refs": []},
        )
        for key, values in (
            ("record_ids", [record.get("record_id")]),
            ("record_families", [record.get("record_family")]),
            ("evidence_refs", record.get("evidence_refs") or []),
        ):
            for value in values:
                text = str(value or "").strip()
                if text and text not in bucket[key]:
                    bucket[key].append(text[:160])
    return by_subject


def _decision_quality(
    routing_row: Mapping[str, Any],
    failure_row: Mapping[str, Any],
    *,
    has_reason_refs: bool,
) -> tuple[str, bool, bool, bool, list[str], str]:
    state = str(routing_row.get("routing_readiness_state") or "fail_closed")
    follow_up = str(routing_row.get("follow_up") or "keep_fail_closed")
    action = str(failure_row.get("recommended_action") or "keep_blocked")
    action_status = str(
        ((failure_row.get("actionability") or {}) if isinstance(failure_row, Mapping) else {}).get(
            "status"
        )
        or "non_actionable"
    )
    diagnosis_class = str(routing_row.get("diagnosis_class") or "unknown_fail_closed")
    reasons: list[str] = []

    if state == "ready":
        false_ready = (
            not has_reason_refs
            or action != "eligible_for_readonly_routing"
            or action_status != "actionable"
            or diagnosis_class != "diagnosable"
            or follow_up != "eligible_for_readonly_routing"
        )
        if false_ready:
            if not has_reason_refs:
                reasons.append("missing_reason_refs")
            if action != "eligible_for_readonly_routing":
                reasons.append("routing_action_misaligned")
            if action_status != "actionable":
                reasons.append("routing_action_non_actionable")
            if diagnosis_class != "diagnosable":
                reasons.append("routing_ready_without_diagnosable_state")
            if follow_up != "eligible_for_readonly_routing":
                reasons.append("routing_follow_up_misaligned")
            return (
                "false_ready",
                True,
                False,
                False,
                reasons,
                "Routing marked this basket ready, but downstream read-only evidence did not confirm the decision.",
            )
        return (
            "ready_sound",
            False,
            False,
            True,
            ["ready_evidence_follow_through"],
            "Routing readiness is supported by durable reason refs and an aligned read-only follow-up action.",
        )

    if state == "fail_closed":
        correct = (
            diagnosis_class == "unknown_fail_closed"
            or action == "keep_blocked"
            or "supporting_artifacts_missing"
            in [str(code) for code in (failure_row.get("actionability") or {}).get("reason_codes") or []]
        )
        reasons.append("supporting_artifacts_missing" if correct else "fail_closed_without_support")
        return (
            "fail_closed_correct" if correct else "fail_closed_ambiguous",
            False,
            correct,
            has_reason_refs,
            reasons,
            "Routing correctly fails closed when upstream artifacts are missing or non-deterministic."
            if correct
            else "Routing failed closed, but the downstream evidence trail is incomplete.",
        )

    if state == "blocked":
        correct = action in {"require_identity_resolution", "require_source_readiness", "keep_blocked"}
        reasons.append("blocked_alignment_ok" if correct else "blocked_alignment_missing")
        return (
            "blocked_correct" if correct else "blocked_ambiguous",
            False,
            correct,
            has_reason_refs,
            reasons,
            "Routing blockers align with bounded source identity or readiness actions."
            if correct
            else "Routing blockers are present, but the bounded follow-up action is misaligned.",
        )

    correct = action in {"collect_more_evidence", "expand_basket_coverage", "route_to_manual_review", "defer_as_duplicate"}
    reasons.append("deferred_alignment_ok" if correct else "deferred_alignment_missing")
    return (
        "deferred_correct" if correct else "deferred_ambiguous",
        False,
        correct,
        has_reason_refs,
        reasons,
        "Deferred routing decisions align with bounded evidence-collection or review actions."
        if correct
        else "The routing decision is deferred, but the downstream action is not specific enough.",
    )


def build_routing_decision_quality(
    *,
    repo_root: Path = Path("."),
    max_candidates: int = 15,
) -> dict[str, Any]:
    routing_report = routing.build_routing_readiness_from_basket(
        repo_root=repo_root,
        max_candidates=max_candidates,
    )
    failure_report = failure_action.build_failure_action_from_basket(
        repo_root=repo_root,
        max_candidates=max_candidates,
    )
    reason_snapshot = reason_records.build_reason_records_snapshot(
        repo_root=repo_root,
        max_candidates=max_candidates,
    )

    routing_rows = routing_report.get("rows")
    if not isinstance(routing_rows, list):
        routing_rows = []
    failure_rows = failure_report.get("rows")
    if not isinstance(failure_rows, list):
        failure_rows = []
    failure_by_subject = {
        str(row.get("candidate_id") or ""): row
        for row in failure_rows
        if isinstance(row, Mapping)
    }
    reason_index = _reason_ref_index(
        [row for row in reason_snapshot.get("records") or [] if isinstance(row, Mapping)]
    )

    rows: list[dict[str, Any]] = []
    for routing_row in routing_rows:
        if not isinstance(routing_row, Mapping):
            continue
        candidate_id = str(routing_row.get("candidate_id") or "")
        failure_row = failure_by_subject.get(candidate_id, {})
        reason_refs = reason_index.get(
            candidate_id,
            {"record_ids": [], "record_families": [], "evidence_refs": []},
        )
        quality_state, false_ready, fail_closed_correct, evidence_follow_through, quality_reasons, explanation = _decision_quality(
            routing_row,
            failure_row,
            has_reason_refs=bool(reason_refs.get("record_ids")),
        )
        rows.append(
            {
                "candidate_id": candidate_id,
                "symbol": routing_row.get("symbol"),
                "preset_id": routing_row.get("preset_id"),
                "routing_readiness_state": routing_row.get("routing_readiness_state"),
                "routing_readiness_score_pct": int(routing_row.get("routing_readiness_score_pct") or 0),
                "decision_quality_state": quality_state,
                "routing_false_ready": false_ready,
                "fail_closed_correct": fail_closed_correct,
                "evidence_follow_through": evidence_follow_through,
                "duplicate_avoidance_applied": str(failure_row.get("recommended_action") or "")
                in {"suppress_until_new_evidence", "defer_as_duplicate"},
                "recommended_action": failure_row.get("recommended_action"),
                "actionability_status": str(
                    ((failure_row.get("actionability") or {}) if isinstance(failure_row, Mapping) else {}).get(
                        "status"
                    )
                    or "non_actionable"
                ),
                "reason_record_refs": reason_refs,
                "quality_reason_codes": quality_reasons,
                "operator_explanation": explanation,
            }
        )

    rows.sort(key=lambda row: (str(row.get("symbol") or ""), str(row.get("preset_id") or "")))
    counts = Counter(str(row["decision_quality_state"]) for row in rows)
    false_ready_count = sum(1 for row in rows if bool(row.get("routing_false_ready")))
    fail_closed_correct_count = sum(1 for row in rows if bool(row.get("fail_closed_correct")))
    blocker_correct_count = sum(
        1
        for row in rows
        if str(row.get("decision_quality_state") or "") in {"blocked_correct", "deferred_correct"}
    )
    duplicate_avoidance_count = sum(1 for row in rows if bool(row.get("duplicate_avoidance_applied")))
    evidence_follow_through_count = sum(1 for row in rows if bool(row.get("evidence_follow_through")))
    return {
        "schema_version": SCHEMA_VERSION,
        "report_kind": REPORT_KIND,
        "max_candidates": max_candidates,
        "summary": {
            "basket_count": len(rows),
            "decision_quality_state_counts": dict(sorted(counts.items())),
            "routing_false_ready_count": false_ready_count,
            "routing_fail_closed_correct_count": fail_closed_correct_count,
            "routing_blocker_correct_count": blocker_correct_count,
            "duplicate_avoidance_count": duplicate_avoidance_count,
            "evidence_follow_through_count": evidence_follow_through_count,
            "final_recommendation": (
                "routing_decisions_sound"
                if false_ready_count == 0
                else "routing_false_ready_items_present"
            ),
            "operator_summary": (
                "Routing decision quality audits whether read-only routing readiness "
                "states remain internally consistent with reason records and bounded "
                "failure actions."
            ),
        },
        "rows": rows,
        "safety_invariants": {
            "read_only": True,
            "policy_adaptation": False,
            "automatic_reroute": False,
            "queue_mutation": False,
            "mutates_frozen_contracts": False,
            "paper_shadow_live_forbidden": True,
            "broker_risk_execution_forbidden": True,
        },
    }


def render_operator_summary(report: Mapping[str, Any]) -> str:
    summary = report.get("summary") or {}
    rows = report.get("rows") if isinstance(report.get("rows"), list) else []
    counts = summary.get("decision_quality_state_counts") or {}
    count_table = _table(
        ["Field", "Count"],
        [
            ["basket count", str(summary.get("basket_count") or 0)],
            ["false ready", str(summary.get("routing_false_ready_count") or 0)],
            ["fail closed correct", str(summary.get("routing_fail_closed_correct_count") or 0)],
            ["blocker correct", str(summary.get("routing_blocker_correct_count") or 0)],
            ["duplicate avoidance", str(summary.get("duplicate_avoidance_count") or 0)],
            ["evidence follow-through", str(summary.get("evidence_follow_through_count") or 0)],
        ],
    )
    state_table = _table(
        ["State", "Count"],
        [[str(key), str(value)] for key, value in sorted(counts.items())],
    )
    row_table = _table(
        ["Symbol", "Preset", "Routing state", "Quality state", "Action", "Reason codes"],
        [
            [
                str(row.get("symbol") or ""),
                str(row.get("preset_id") or ""),
                str(row.get("routing_readiness_state") or ""),
                str(row.get("decision_quality_state") or ""),
                str(row.get("recommended_action") or ""),
                ", ".join(str(code) for code in row.get("quality_reason_codes") or []),
            ]
            for row in rows
        ],
    )
    return "\n".join(
        [
            "# QRE Routing Decision Quality Audit",
            "",
            "## 1. Korte conclusie",
            f"- {summary.get('operator_summary') or ''}",
            "",
            "## 2. Routing decision quality counts",
            count_table,
            "",
            "## 3. Routing decision quality states",
            state_table,
            "",
            "## 4. Routing decision quality by basket",
            row_table,
        ]
    )


def _validate_write_target(path: Path) -> None:
    if _WRITE_PREFIX not in path.as_posix():
        raise ValueError(f"qre_routing_decision_quality: refusing write outside allowlist: {path!r}")


def write_outputs(
    report: Mapping[str, Any],
    *,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    repo_root: Path = Path("."),
) -> dict[str, str]:
    base = repo_root / output_dir
    base.mkdir(parents=True, exist_ok=True)
    latest = base / LATEST_NAME
    summary_path = base / OPERATOR_SUMMARY_NAME
    for target in (latest, summary_path):
        _validate_write_target(target)
    tmp_json = latest.with_suffix(latest.suffix + ".tmp")
    tmp_json.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(tmp_json, latest)
    tmp_summary = summary_path.with_suffix(summary_path.suffix + ".tmp")
    tmp_summary.write_text(render_operator_summary(report) + "\n", encoding="utf-8")
    os.replace(tmp_summary, summary_path)
    return {
        "latest": latest.relative_to(repo_root).as_posix(),
        "operator_summary": summary_path.relative_to(repo_root).as_posix(),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m research.qre_routing_decision_quality",
        description="Build read-only QRE routing decision quality diagnostics.",
    )
    parser.add_argument("--max-candidates", type=int, default=15)
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args(argv)
    report = build_routing_decision_quality(max_candidates=args.max_candidates)
    if args.write:
        report["_artifact_paths"] = write_outputs(report)
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
