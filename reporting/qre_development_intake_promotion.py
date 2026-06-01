"""Read-only QRE proposal intake to ADE development intake projector."""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
import sys
import tempfile
from collections import Counter
from pathlib import Path
from typing import Any, Final

from reporting import execution_authority as ea

REPO_ROOT: Final[Path] = Path(__file__).resolve().parent.parent

SCHEMA_VERSION: Final[int] = 1
REPORT_KIND: Final[str] = "qre_development_intake_promotion"
INPUT_REPORT_KIND: Final[str] = "qre_research_action_proposal_intake"

INPUT_ARTIFACT_RELATIVE_PATH: Final[str] = (
    "logs/qre_research_action_proposal_intake/latest.json"
)
INPUT_ARTIFACT_PATH: Final[Path] = REPO_ROOT / INPUT_ARTIFACT_RELATIVE_PATH

ARTIFACT_DIR: Final[Path] = REPO_ROOT / "logs" / "qre_development_intake_promotion"
OUTPUT_ARTIFACT_RELATIVE_PATH: Final[str] = (
    "logs/qre_development_intake_promotion/latest.json"
)
ARTIFACT_LATEST: Final[Path] = REPO_ROOT / OUTPUT_ARTIFACT_RELATIVE_PATH

DECISION_PENDING: Final[str] = "pending"
DECISION_ELIGIBLE: Final[str] = "eligible"
DECISION_HUMAN_NEEDED: Final[str] = "human_needed"
DECISION_BLOCKED: Final[str] = "blocked"

DECISION_STATES: Final[tuple[str, ...]] = (
    DECISION_PENDING,
    DECISION_ELIGIBLE,
    DECISION_HUMAN_NEEDED,
    DECISION_BLOCKED,
)

PROMOTION_TARGET_NONE: Final[str] = "none"
PROMOTION_TARGET_DEVELOPMENT_WORK_QUEUE: Final[str] = "development_work_queue"

PROMOTION_INTENT_SCHEMA_KEYS: Final[tuple[str, ...]] = (
    "candidate_id",
    "title",
    "source_kind",
    "candidate_kind",
    "category",
    "risk_level",
    "target_path",
    "upstream_proposal_status",
    "upstream_execution_authority_decision",
    "reclassified_execution_authority_decision",
    "classification_drift",
    "human_needed",
    "human_needed_reason",
    "promotion_target",
    "decision_state",
    "safe_to_execute",
    "eligible_for_direct_execution",
    "suggested_branch_name",
    "required_tests",
    "affected_files",
    "forbidden_actions",
    "validation_warnings",
)

SAFETY_DENIAL_FORBIDDEN_ACTIONS: Final[frozenset[str]] = frozenset(
    {
        "launch_codex",
        "mutate_campaign_queue",
        "mutate_strategy_or_preset",
        "enable_paper_runtime",
        "enable_shadow_runtime",
        "enable_live_runtime",
        "place_order",
        "allocate_capital",
    }
)

NOTE_INPUT_ABSENT: Final[str] = "proposal_intake_artifact_absent"
NOTE_INPUT_UNPARSEABLE: Final[str] = "proposal_intake_artifact_unparseable"
NOTE_NO_PROPOSALS: Final[str] = "no_qre_proposals_to_project"
NOTE_ROWS_PRESENT: Final[str] = "qre_promotion_intents_present"


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


def _read_json(path: Path) -> dict[str, Any] | None:
    try:
        raw = path.read_text(encoding="utf-8-sig")
    except OSError:
        return None
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def _bounded_str(value: Any, *, max_len: int = 240) -> str:
    text = str(value or "").strip()
    if len(text) <= max_len:
        return text
    return text[: max_len - 3].rstrip() + "..."


def _str_list(value: Any, *, max_items: int = 25, max_len: int = 240) -> list[str]:
    if not isinstance(value, list):
        return []
    out: list[str] = []
    for item in value[:max_items]:
        if isinstance(item, str) and item.strip():
            out.append(_bounded_str(item, max_len=max_len))
    return out


def _candidate_id(proposal: dict[str, Any], *, index: int) -> str:
    proposal_id = proposal.get("proposal_id")
    if isinstance(proposal_id, str) and proposal_id.strip():
        return _bounded_str(proposal_id, max_len=160)
    return f"invalid-proposal-{index:04d}"


def _risk_level(proposal: dict[str, Any]) -> str:
    value = proposal.get("risk_class", proposal.get("risk_level"))
    return _bounded_str(value, max_len=40) or ea.RISK_UNKNOWN


def _upstream_authority_decision(proposal: dict[str, Any]) -> str:
    for key in (
        "execution_authority_decision",
        "upstream_execution_authority_decision",
    ):
        value = proposal.get(key)
        if isinstance(value, str) and value.strip():
            return _bounded_str(value, max_len=80)
    return ""


def _safe_target_path(affected_files: list[str]) -> str:
    if not affected_files:
        return ""
    raw = affected_files[0].replace("\\", "/").strip()
    if not raw or raw.startswith("/") or raw.startswith("../") or "/../" in raw:
        return ""
    if len(raw) > 240:
        return ""
    return raw.lstrip("./")


def _decision_state(
    *,
    status: str,
    risk_level: str,
    target_path: str,
    upstream_decision: str,
    reclassified_decision: str,
    classification_drift: bool,
    source_safe_to_execute: bool,
    source_eligible_for_direct_execution: bool,
    missing_required: list[str],
) -> tuple[str, bool, str]:
    if missing_required:
        return (DECISION_BLOCKED, False, "missing_required_proposal_fields")
    if source_safe_to_execute:
        return (DECISION_BLOCKED, False, "upstream_safe_to_execute_true")
    if source_eligible_for_direct_execution:
        return (
            DECISION_BLOCKED,
            False,
            "upstream_eligible_for_direct_execution_true",
        )
    if classification_drift:
        return (DECISION_BLOCKED, False, "classification_drift")
    if status == "blocked":
        return (DECISION_BLOCKED, False, "upstream_status_blocked")
    if status == "needs_human":
        return (DECISION_HUMAN_NEEDED, True, "upstream_status_needs_human")
    if status == "proposed":
        return (DECISION_PENDING, False, "")
    if status != "eligible":
        return (DECISION_BLOCKED, False, "unknown_upstream_status")
    if not target_path:
        return (DECISION_HUMAN_NEEDED, True, "missing_target_path")
    if reclassified_decision == ea.DECISION_NEEDS_HUMAN:
        return (DECISION_HUMAN_NEEDED, True, "reclassification_needs_human")
    if reclassified_decision == ea.DECISION_PERMANENTLY_DENIED:
        return (DECISION_BLOCKED, False, "reclassification_permanently_denied")
    if (
        risk_level == ea.RISK_LOW
        and reclassified_decision == ea.DECISION_AUTO_ALLOWED
        and (not upstream_decision or upstream_decision == ea.DECISION_AUTO_ALLOWED)
    ):
        return (DECISION_ELIGIBLE, False, "")
    return (DECISION_HUMAN_NEEDED, True, "not_low_risk_auto_allowed")


def _build_row(proposal: dict[str, Any], *, index: int) -> dict[str, Any]:
    warnings: list[str] = []
    candidate_id = _candidate_id(proposal, index=index)
    title = _bounded_str(proposal.get("title"))
    status = _bounded_str(proposal.get("status"), max_len=40)
    risk_level = _risk_level(proposal)
    affected_files = _str_list(proposal.get("affected_files"))
    target_path = _safe_target_path(affected_files)
    forbidden_actions = _str_list(proposal.get("forbidden_actions"))
    required_tests = _str_list(proposal.get("required_tests"), max_items=20)
    upstream_decision = _upstream_authority_decision(proposal)

    missing_required: list[str] = []
    if not isinstance(proposal.get("proposal_id"), str) or not proposal.get(
        "proposal_id"
    ):
        missing_required.append("proposal_id")
    if not title:
        missing_required.append("title")
    if not status:
        missing_required.append("status")
    if not isinstance(proposal.get("risk_class", proposal.get("risk_level")), str):
        missing_required.append("risk_class")
    for field in missing_required:
        warnings.append(f"missing_required_field:{field}")
    if not target_path:
        warnings.append("missing_or_unsafe_target_path")
    if risk_level not in ea.RISK_CLASSES:
        warnings.append("invalid_risk_class")

    reclassified = ea.classify(
        action_type="file_edit",
        target_path=target_path or None,
        risk_class=risk_level or ea.RISK_UNKNOWN,
    )
    classification_drift = bool(
        upstream_decision and upstream_decision != reclassified.decision
    )
    if classification_drift:
        warnings.append("classification_drift")

    source_safe_to_execute = proposal.get("safe_to_execute") is True
    source_eligible_for_direct_execution = (
        proposal.get("eligible_for_direct_execution") is True
    )
    if source_safe_to_execute:
        warnings.append("upstream_safe_to_execute_true")
    if source_eligible_for_direct_execution:
        warnings.append("upstream_eligible_for_direct_execution_true")

    safety_denials = sorted(
        action
        for action in forbidden_actions
        if action in SAFETY_DENIAL_FORBIDDEN_ACTIONS
    )
    if safety_denials:
        warnings.append("safety_denials_preserved")

    decision_state, human_needed, human_reason = _decision_state(
        status=status,
        risk_level=risk_level,
        target_path=target_path,
        upstream_decision=upstream_decision,
        reclassified_decision=reclassified.decision,
        classification_drift=classification_drift,
        source_safe_to_execute=source_safe_to_execute,
        source_eligible_for_direct_execution=source_eligible_for_direct_execution,
        missing_required=missing_required,
    )

    promotion_target = (
        PROMOTION_TARGET_DEVELOPMENT_WORK_QUEUE
        if decision_state == DECISION_ELIGIBLE
        else PROMOTION_TARGET_NONE
    )

    return {
        "candidate_id": candidate_id,
        "title": title,
        "source_kind": _bounded_str(
            proposal.get("source_type", proposal.get("source_kind"))
        ),
        "candidate_kind": _bounded_str(
            proposal.get("proposal_type", proposal.get("candidate_kind"))
        ),
        "category": _bounded_str(proposal.get("category")),
        "risk_level": risk_level,
        "target_path": target_path,
        "upstream_proposal_status": status,
        "upstream_execution_authority_decision": upstream_decision,
        "reclassified_execution_authority_decision": reclassified.decision,
        "classification_drift": classification_drift,
        "human_needed": human_needed,
        "human_needed_reason": _bounded_str(
            proposal.get("human_needed_reason") or human_reason
        ),
        "promotion_target": promotion_target,
        "decision_state": decision_state,
        "safe_to_execute": False,
        "eligible_for_direct_execution": False,
        "suggested_branch_name": _bounded_str(
            proposal.get("suggested_branch_name"), max_len=120
        ),
        "required_tests": required_tests,
        "affected_files": affected_files,
        "forbidden_actions": forbidden_actions,
        "validation_warnings": warnings,
    }


def _empty_counts() -> dict[str, Any]:
    return {
        "total": 0,
        "by_decision_state": {state: 0 for state in DECISION_STATES},
    }


def _counts(rows: list[dict[str, Any]]) -> dict[str, Any]:
    counter = Counter(str(row.get("decision_state") or DECISION_BLOCKED) for row in rows)
    out = _empty_counts()
    out["total"] = len(rows)
    for state in DECISION_STATES:
        out["by_decision_state"][state] = counter.get(state, 0)
        out[state] = counter.get(state, 0)
    return out


def _final_recommendation(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return "no_qre_promotion_intents"
    if any(row["decision_state"] == DECISION_BLOCKED for row in rows):
        return "operator_review_required_blocked_rows_present"
    if any(row["decision_state"] == DECISION_HUMAN_NEEDED for row in rows):
        return "operator_review_required"
    if any(row["decision_state"] == DECISION_ELIGIBLE for row in rows):
        return "eligible_promotion_intents_ready_for_operator_review"
    return "pending_promotion_intents_only"


def _base_snapshot(
    *,
    generated_at_utc: str,
    input_artifact_path: Path,
    input_artifact_available: bool,
    rows: list[dict[str, Any]],
    validation_warnings: list[str],
    note: str,
) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "report_kind": REPORT_KIND,
        "generated_at_utc": generated_at_utc,
        "input_artifact_path": _rel(input_artifact_path),
        "input_artifact_available": input_artifact_available,
        "safe_to_execute": False,
        "writes_development_work_queue": False,
        "writes_seed_jsonl": False,
        "writes_delegation_seed_jsonl": False,
        "writes_generated_seed_jsonl": False,
        "mutates_campaign_queue": False,
        "mutates_strategy_or_preset": False,
        "mutates_paper_shadow_live_runtime": False,
        "rows": rows,
        "counts": _counts(rows),
        "validation_warnings": validation_warnings,
        "final_recommendation": _final_recommendation(rows),
        "note": note,
        "execution_authority_module_version": ea.MODULE_VERSION,
    }


def collect_snapshot(
    *,
    input_artifact_path: Path | None = None,
    generated_at_utc: str | None = None,
) -> dict[str, Any]:
    generated = generated_at_utc or _utcnow()
    source = input_artifact_path or INPUT_ARTIFACT_PATH
    payload = _read_json(source)
    warnings: list[str] = []

    if payload is None:
        warnings.append(NOTE_INPUT_ABSENT)
        return _base_snapshot(
            generated_at_utc=generated,
            input_artifact_path=source,
            input_artifact_available=False,
            rows=[],
            validation_warnings=warnings,
            note=NOTE_INPUT_ABSENT,
        )

    raw_proposals = payload.get("proposals")
    if payload.get("report_kind") != INPUT_REPORT_KIND or not isinstance(
        raw_proposals, list
    ):
        warnings.append(NOTE_INPUT_UNPARSEABLE)
        return _base_snapshot(
            generated_at_utc=generated,
            input_artifact_path=source,
            input_artifact_available=True,
            rows=[],
            validation_warnings=warnings,
            note=NOTE_INPUT_UNPARSEABLE,
        )

    rows = [
        _build_row(raw, index=index)
        for index, raw in enumerate(raw_proposals, start=1)
        if isinstance(raw, dict)
    ]
    skipped = len(raw_proposals) - len(rows)
    if skipped:
        warnings.append(f"non_object_proposals_skipped:{skipped}")

    rows.sort(key=lambda row: (row["source_kind"], row["candidate_id"]))
    for row in rows:
        for warning in row["validation_warnings"]:
            warnings.append(f"{row['candidate_id']}:{warning}")

    note = NOTE_ROWS_PRESENT if rows else NOTE_NO_PROPOSALS
    return _base_snapshot(
        generated_at_utc=generated,
        input_artifact_path=source,
        input_artifact_available=True,
        rows=rows,
        validation_warnings=warnings,
        note=note,
    )


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    if not path.resolve().is_relative_to(ARTIFACT_DIR.resolve()):
        raise ValueError(f"refusing write outside QRE promotion output dir: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    fd, tmp_name = tempfile.mkstemp(
        prefix=".qre_development_intake_promotion.",
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


def write_outputs(snapshot: dict[str, Any]) -> Path:
    _atomic_write_json(ARTIFACT_LATEST, snapshot)
    return ARTIFACT_LATEST


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="reporting.qre_development_intake_promotion",
        description="Project QRE proposal intake rows into read-only promotion intents.",
    )
    parser.add_argument("--no-write", action="store_true")
    parser.add_argument("--source", type=Path, default=None)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    snapshot = collect_snapshot(input_artifact_path=args.source)
    if not args.no_write:
        write_outputs(snapshot)
    print(json.dumps(snapshot, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "ARTIFACT_DIR",
    "ARTIFACT_LATEST",
    "DECISION_BLOCKED",
    "DECISION_ELIGIBLE",
    "DECISION_HUMAN_NEEDED",
    "DECISION_PENDING",
    "DECISION_STATES",
    "INPUT_ARTIFACT_PATH",
    "INPUT_ARTIFACT_RELATIVE_PATH",
    "OUTPUT_ARTIFACT_RELATIVE_PATH",
    "PROMOTION_INTENT_SCHEMA_KEYS",
    "PROMOTION_TARGET_DEVELOPMENT_WORK_QUEUE",
    "PROMOTION_TARGET_NONE",
    "REPORT_KIND",
    "SCHEMA_VERSION",
    "collect_snapshot",
    "main",
    "write_outputs",
]
