"""Read-only QRE development queue admission-policy projector."""

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
from reporting import qre_development_intake_promotion as qdip
from reporting.agent_audit_summary import assert_no_secrets

REPO_ROOT: Final[Path] = Path(__file__).resolve().parent.parent

SCHEMA_VERSION: Final[int] = 1
REPORT_KIND: Final[str] = "qre_development_queue_admission_policy"

INPUT_ARTIFACT_RELATIVE_PATH: Final[str] = (
    "logs/qre_development_intake_promotion/latest.json"
)
INPUT_ARTIFACT_PATH: Final[Path] = REPO_ROOT / INPUT_ARTIFACT_RELATIVE_PATH

ARTIFACT_DIR: Final[Path] = (
    REPO_ROOT / "logs" / "qre_development_queue_admission_policy"
)
OUTPUT_ARTIFACT_RELATIVE_PATH: Final[str] = (
    "logs/qre_development_queue_admission_policy/latest.json"
)
ARTIFACT_LATEST: Final[Path] = REPO_ROOT / OUTPUT_ARTIFACT_RELATIVE_PATH

POLICY_VERSION: Final[str] = "qre_development_queue_admission_policy.v1"

ADMISSION_DECISIONS: Final[tuple[str, ...]] = (
    "admissible",
    "needs_human",
    "blocked",
    "duplicate_of_existing",
    "not_eligible_upstream",
)

ADMISSION_REASONS: Final[tuple[str, ...]] = (
    "auto_allowed_low_risk_eligible_qre_promotion",
    "needs_human_authority_decision",
    "needs_human_unknown_or_invalid_risk",
    "needs_human_classification_drift",
    "needs_human_protected_target_path",
    "blocked_authority_permanently_denied",
    "blocked_classification_drift_to_denied",
    "upstream_decision_state_not_eligible",
    "upstream_safe_to_execute_true",
    "upstream_eligible_for_direct_execution_true",
    "duplicate_candidate_id",
    "malformed_upstream_record",
)

ADMISSION_SCHEMA_KEYS: Final[tuple[str, ...]] = (
    "candidate_id",
    "title",
    "source_kind",
    "candidate_kind",
    "category",
    "risk_level",
    "target_path",
    "upstream_proposal_status",
    "upstream_decision_state",
    "upstream_execution_authority_decision",
    "reclassified_execution_authority_decision",
    "classification_drift",
    "human_needed",
    "human_needed_reason",
    "admission_decision",
    "admission_reason",
    "would_target_lane",
    "safe_to_execute",
    "eligible_for_direct_execution",
    "policy_version",
    "evaluated_at",
)

NOTE_INPUT_ABSENT: Final[str] = "qre_promotion_artifact_absent"
NOTE_INPUT_UNPARSEABLE: Final[str] = "qre_promotion_artifact_unparseable"
NOTE_NO_ROWS: Final[str] = "no_qre_promotion_intents_to_evaluate"
NOTE_ROWS_PRESENT: Final[str] = "qre_admission_policy_rows_present"

_PROTECTED_TARGET_CATEGORIES: Final[frozenset[str]] = frozenset(
    {
        "canonical_roadmap",
        "canonical_policy_doc",
        "branch_protection_config",
        "ci_workflow",
        "claude_governance_hook",
        "dashboard_wiring",
        "deploy_script",
        "frozen_contract",
        "live_path",
    }
)


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
    if not isinstance(parsed, dict):
        return (True, None)
    return (True, parsed)


def _bounded_str(value: Any, *, max_len: int = 240) -> str:
    text = str(value or "").strip()
    if len(text) <= max_len:
        return text
    return text[: max_len - 3].rstrip() + "..."


def _bool_true(value: Any) -> bool:
    return value is True


def _classify_target(risk_level: str, target_path: str) -> ea.AuthorityDecision:
    return ea.classify(
        action_type="file_edit",
        target_path=target_path or None,
        risk_class=risk_level or ea.RISK_UNKNOWN,
    )


def _candidate_id(row: dict[str, Any], *, index: int) -> str:
    value = row.get("candidate_id")
    if isinstance(value, str) and value.strip():
        return _bounded_str(value, max_len=160)
    return f"malformed-upstream-record-{index:04d}"


def _evaluate_row(
    *,
    upstream: dict[str, Any] | None,
    candidate_id: str,
    duplicate_candidate_id: bool,
    risk_level: str,
    target_path: str,
    upstream_decision_state: str,
    upstream_authority_decision: str,
    reclassified_decision: str,
    reclassified_target_category: str,
    classification_drift: bool,
    human_needed: bool,
    safe_to_execute: bool,
    eligible_for_direct_execution: bool,
) -> tuple[str, str]:
    if upstream is None or candidate_id.startswith("malformed-upstream-record-"):
        return ("blocked", "malformed_upstream_record")

    if duplicate_candidate_id:
        return ("duplicate_of_existing", "duplicate_candidate_id")

    if safe_to_execute:
        return ("blocked", "upstream_safe_to_execute_true")

    if eligible_for_direct_execution:
        return ("blocked", "upstream_eligible_for_direct_execution_true")

    if upstream_decision_state == qdip.DECISION_HUMAN_NEEDED:
        return ("needs_human", "needs_human_authority_decision")

    if upstream_decision_state != qdip.DECISION_ELIGIBLE:
        return ("not_eligible_upstream", "upstream_decision_state_not_eligible")

    if (
        classification_drift
        and reclassified_decision == ea.DECISION_PERMANENTLY_DENIED
    ):
        return ("blocked", "blocked_classification_drift_to_denied")

    if (
        upstream_authority_decision == ea.DECISION_PERMANENTLY_DENIED
        or reclassified_decision == ea.DECISION_PERMANENTLY_DENIED
    ):
        return ("blocked", "blocked_authority_permanently_denied")

    if classification_drift:
        return ("needs_human", "needs_human_classification_drift")

    if risk_level not in ea.RISK_CLASSES or risk_level == ea.RISK_UNKNOWN:
        return ("needs_human", "needs_human_unknown_or_invalid_risk")

    if (
        upstream_authority_decision == ea.DECISION_NEEDS_HUMAN
        or reclassified_decision == ea.DECISION_NEEDS_HUMAN
        or human_needed
    ):
        if reclassified_target_category in _PROTECTED_TARGET_CATEGORIES:
            return ("needs_human", "needs_human_protected_target_path")
        return ("needs_human", "needs_human_authority_decision")

    if (
        reclassified_decision == ea.DECISION_AUTO_ALLOWED
        and risk_level == ea.RISK_LOW
    ):
        return ("admissible", "auto_allowed_low_risk_eligible_qre_promotion")

    return ("needs_human", "needs_human_authority_decision")


def _build_row(
    upstream: dict[str, Any] | None,
    *,
    index: int,
    seen_candidate_ids: set[str],
    evaluated_at: str,
) -> dict[str, Any]:
    source = upstream or {}
    candidate_id = _candidate_id(source, index=index)
    duplicate_candidate_id = candidate_id in seen_candidate_ids
    seen_candidate_ids.add(candidate_id)

    risk_level = _bounded_str(source.get("risk_level"), max_len=40)
    target_path = _bounded_str(source.get("target_path"))
    upstream_authority_decision = _bounded_str(
        source.get("upstream_execution_authority_decision"), max_len=80
    )
    upstream_reclassified_decision = _bounded_str(
        source.get("reclassified_execution_authority_decision"), max_len=80
    )
    authority = _classify_target(risk_level, target_path)
    reclassified_decision = upstream_reclassified_decision or authority.decision
    upstream_drift = _bool_true(source.get("classification_drift"))
    classification_drift = bool(
        upstream_drift
        or (
            upstream_authority_decision
            and upstream_authority_decision != reclassified_decision
        )
    )
    safe_to_execute = _bool_true(source.get("safe_to_execute"))
    eligible_for_direct_execution = _bool_true(
        source.get("eligible_for_direct_execution")
    )

    decision, reason = _evaluate_row(
        upstream=upstream,
        candidate_id=candidate_id,
        duplicate_candidate_id=duplicate_candidate_id,
        risk_level=risk_level,
        target_path=target_path,
        upstream_decision_state=_bounded_str(source.get("decision_state"), max_len=40),
        upstream_authority_decision=upstream_authority_decision,
        reclassified_decision=reclassified_decision,
        reclassified_target_category=authority.target_path_category,
        classification_drift=classification_drift,
        human_needed=_bool_true(source.get("human_needed")),
        safe_to_execute=safe_to_execute,
        eligible_for_direct_execution=eligible_for_direct_execution,
    )

    return {
        "candidate_id": candidate_id,
        "title": _bounded_str(source.get("title")),
        "source_kind": _bounded_str(source.get("source_kind"), max_len=80),
        "candidate_kind": _bounded_str(source.get("candidate_kind"), max_len=80),
        "category": _bounded_str(source.get("category"), max_len=80),
        "risk_level": risk_level,
        "target_path": target_path,
        "upstream_proposal_status": _bounded_str(
            source.get("upstream_proposal_status"), max_len=40
        ),
        "upstream_decision_state": _bounded_str(
            source.get("decision_state"), max_len=40
        ),
        "upstream_execution_authority_decision": upstream_authority_decision,
        "reclassified_execution_authority_decision": reclassified_decision,
        "classification_drift": classification_drift,
        "human_needed": _bool_true(source.get("human_needed")),
        "human_needed_reason": _bounded_str(source.get("human_needed_reason")),
        "admission_decision": decision,
        "admission_reason": reason,
        "would_target_lane": (
            qdip.PROMOTION_TARGET_DEVELOPMENT_WORK_QUEUE
            if decision == "admissible"
            else qdip.PROMOTION_TARGET_NONE
        ),
        "safe_to_execute": safe_to_execute,
        "eligible_for_direct_execution": eligible_for_direct_execution,
        "policy_version": POLICY_VERSION,
        "evaluated_at": evaluated_at,
    }


def _empty_counts() -> dict[str, Any]:
    return {
        "total": 0,
        "by_admission_decision": {decision: 0 for decision in ADMISSION_DECISIONS},
        "by_admission_reason": {reason: 0 for reason in ADMISSION_REASONS},
    }


def _counts(rows: list[dict[str, Any]]) -> dict[str, Any]:
    decision_counts = Counter(str(row.get("admission_decision") or "") for row in rows)
    reason_counts = Counter(str(row.get("admission_reason") or "") for row in rows)
    out = _empty_counts()
    out["total"] = len(rows)
    for decision in ADMISSION_DECISIONS:
        out[decision] = decision_counts.get(decision, 0)
        out["by_admission_decision"][decision] = decision_counts.get(decision, 0)
    for reason in ADMISSION_REASONS:
        out["by_admission_reason"][reason] = reason_counts.get(reason, 0)
    return out


def _final_recommendation(rows: list[dict[str, Any]]) -> str:
    if not rows:
        return "no_qre_admission_candidates"
    if any(row["admission_decision"] == "blocked" for row in rows):
        return "operator_review_required_blocked_rows_present"
    if any(row["admission_decision"] == "needs_human" for row in rows):
        return "operator_review_required"
    if any(row["admission_decision"] == "admissible" for row in rows):
        return "admissible_rows_ready_for_operator_gated_generation"
    return "no_admissible_qre_rows"


def _base_snapshot(
    *,
    generated_at_utc: str,
    input_artifact_path: Path,
    input_artifact_available: bool,
    note: str,
    rows: list[dict[str, Any]],
    validation_warnings: list[str],
) -> dict[str, Any]:
    snapshot = {
        "schema_version": SCHEMA_VERSION,
        "report_kind": REPORT_KIND,
        "generated_at_utc": generated_at_utc,
        "input_artifact_path": _rel(input_artifact_path),
        "input_artifact_available": input_artifact_available,
        "note": note,
        "rows": rows,
        "counts": _counts(rows),
        "validation_warnings": validation_warnings,
        "final_recommendation": _final_recommendation(rows),
        "safe_to_execute": False,
        "writes_development_work_queue": False,
        "writes_seed_jsonl": False,
        "writes_delegation_seed_jsonl": False,
        "writes_generated_seed_jsonl": False,
        "mutates_campaign_queue": False,
        "mutates_strategy_or_preset": False,
        "mutates_paper_shadow_live_runtime": False,
    }
    assert_no_secrets(snapshot)
    return snapshot


def collect_snapshot(
    *,
    input_artifact_path: Path | None = None,
    generated_at_utc: str | None = None,
) -> dict[str, Any]:
    generated = generated_at_utc or _utcnow()
    source = input_artifact_path or INPUT_ARTIFACT_PATH
    available, payload = _read_json(source)
    warnings: list[str] = []

    if payload is None:
        note = NOTE_INPUT_UNPARSEABLE if available else NOTE_INPUT_ABSENT
        warnings.append(note)
        return _base_snapshot(
            generated_at_utc=generated,
            input_artifact_path=source,
            input_artifact_available=available,
            note=note,
            rows=[],
            validation_warnings=warnings,
        )

    raw_rows = payload.get("rows")
    if payload.get("report_kind") != qdip.REPORT_KIND or not isinstance(
        raw_rows, list
    ):
        warnings.append(NOTE_INPUT_UNPARSEABLE)
        return _base_snapshot(
            generated_at_utc=generated,
            input_artifact_path=source,
            input_artifact_available=True,
            note=NOTE_INPUT_UNPARSEABLE,
            rows=[],
            validation_warnings=warnings,
        )

    seen_candidate_ids: set[str] = set()
    rows = [
        _build_row(
            raw if isinstance(raw, dict) else None,
            index=index,
            seen_candidate_ids=seen_candidate_ids,
            evaluated_at=generated,
        )
        for index, raw in enumerate(raw_rows, start=1)
    ]
    for row in rows:
        if row["admission_reason"] == "malformed_upstream_record":
            warnings.append(f"{row['candidate_id']}:malformed_upstream_record")

    return _base_snapshot(
        generated_at_utc=generated,
        input_artifact_path=source,
        input_artifact_available=True,
        note=NOTE_ROWS_PRESENT if rows else NOTE_NO_ROWS,
        rows=rows,
        validation_warnings=warnings,
    )


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    if not path.resolve().is_relative_to(ARTIFACT_DIR.resolve()):
        raise ValueError(f"refusing write outside QRE admission output dir: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    fd, tmp_name = tempfile.mkstemp(
        prefix=".qre_development_queue_admission_policy.",
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
        prog="reporting.qre_development_queue_admission_policy",
        description="Project QRE promotion intents into read-only queue admission decisions.",
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
    "ADMISSION_DECISIONS",
    "ADMISSION_REASONS",
    "ADMISSION_SCHEMA_KEYS",
    "ARTIFACT_DIR",
    "ARTIFACT_LATEST",
    "INPUT_ARTIFACT_PATH",
    "INPUT_ARTIFACT_RELATIVE_PATH",
    "OUTPUT_ARTIFACT_RELATIVE_PATH",
    "REPORT_KIND",
    "SCHEMA_VERSION",
    "collect_snapshot",
    "main",
    "write_outputs",
]
