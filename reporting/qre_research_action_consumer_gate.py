"""Read-only ADE consumer gate for QRE research action sidecars.

This module reads ``research/research_action_queue_latest.v1.json`` and emits a
bounded classification artifact under ``logs/qre_research_action_consumer_gate``.

It does not execute actions, launch Codex, mutate campaigns, write the ADE work
queue, or change paper/shadow/live runtime behavior.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
from collections import Counter
from pathlib import Path
from typing import Any, Final

REPO_ROOT: Final[Path] = Path(__file__).resolve().parent.parent

QRE_ACTION_QUEUE_LATEST: Final[Path] = (
    REPO_ROOT / "research" / "research_action_queue_latest.v1.json"
)
ARTIFACT_DIR: Final[Path] = REPO_ROOT / "logs" / "qre_research_action_consumer_gate"
ARTIFACT_LATEST: Final[Path] = ARTIFACT_DIR / "latest.json"
ARTIFACT_RELATIVE_PATH: Final[str] = (
    "logs/qre_research_action_consumer_gate/latest.json"
)
PROPOSAL_INTAKE_DIR: Final[Path] = (
    REPO_ROOT / "logs" / "qre_research_action_proposal_intake"
)
PROPOSAL_INTAKE_LATEST: Final[Path] = PROPOSAL_INTAKE_DIR / "latest.json"
PROPOSAL_INTAKE_RELATIVE_PATH: Final[str] = (
    "logs/qre_research_action_proposal_intake/latest.json"
)

SCHEMA_VERSION: Final[int] = 1
REPORT_KIND: Final[str] = "qre_research_action_consumer_gate"

VERDICT_ELIGIBLE: Final[str] = "eligible_for_ade_proposal_intake"
VERDICT_OPERATOR_REQUIRED: Final[str] = "operator_approval_required"
VERDICT_BLOCKED: Final[str] = "blocked"

VERDICTS: Final[tuple[str, ...]] = (
    VERDICT_ELIGIBLE,
    VERDICT_OPERATOR_REQUIRED,
    VERDICT_BLOCKED,
)

SUPPORTED_SOURCE_SCHEMA: Final[str] = "research_action_queue.v1"

_REQUIRED_ITEM_FIELDS: Final[tuple[str, ...]] = (
    "action_id",
    "source_section",
    "priority",
    "status",
    "outcome_status",
    "operator_approval_required",
    "forbidden_actions",
)

_BLOCKING_FORBIDDEN_ACTIONS: Final[tuple[str, ...]] = (
    "live_runtime_activation",
    "paper_runtime_activation",
    "shadow_runtime_activation",
    "broker_order_placement",
    "capital_allocation",
    "risk_engine_mutation",
    "strategy_or_preset_mutation",
    "automatic_campaign_queue_mutation",
    "campaign_queue_mutation",
    "ade_queue_execution",
    "codex_execution",
)


def _utcnow() -> str:
    from datetime import UTC, datetime

    return datetime.now(UTC).isoformat(timespec="seconds")


def _rel(path: Path) -> str:
    try:
        return path.resolve().relative_to(REPO_ROOT.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def _read_json(path: Path) -> dict[str, Any] | None:
    try:
        # Windows PowerShell Set-Content -Encoding UTF8 may write a UTF-8 BOM.
        # Accept it so local operator-generated sidecar fixtures do not fail closed
        # as missing_or_unreadable.
        raw = path.read_text(encoding="utf-8-sig")
    except OSError:
        return None
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def _bounded_str(value: Any, max_len: int = 240) -> str:
    text = str(value or "").strip()
    if len(text) <= max_len:
        return text
    return text[: max_len - 3].rstrip() + "..."


def _slug(value: str, *, max_len: int = 48) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    if not slug:
        slug = "qre-research-action"
    return slug[:max_len].strip("-") or "qre-research-action"


def _proposal_id(row: dict[str, Any]) -> str:
    seed = "|".join(
        [
            "qre_research_action",
            str(row.get("action_id") or ""),
            str(row.get("source_section") or ""),
            str(row.get("target_candidate_id") or ""),
        ]
    )
    return "qre-" + hashlib.sha256(seed.encode("utf-8")).hexdigest()[:16]


def _proposal_title(row: dict[str, Any]) -> str:
    action_id = _bounded_str(row.get("action_id"), 120)
    if not action_id:
        action_id = "qre_research_action"
    return f"QRE research action: {action_id}"


def _proposal_summary(row: dict[str, Any]) -> str:
    source_item = row.get("source_item") if isinstance(row.get("source_item"), dict) else {}
    parts = [
        f"Gate verdict: {row.get('verdict')}.",
        f"Reason: {row.get('reason')}.",
    ]
    target = row.get("target_candidate_id")
    if target:
        parts.append(f"Target candidate: {target}.")
    bounded_next = source_item.get("bounded_next_step")
    if bounded_next:
        parts.append(f"Bounded next step: {bounded_next}")
    reason_codes = source_item.get("reason_codes")
    if reason_codes:
        parts.append("Reason codes: " + ", ".join(str(x) for x in reason_codes) + ".")
    return _bounded_str(" ".join(parts), 600)


def _proposal_status_for_row(row: dict[str, Any]) -> str:
    verdict = row.get("verdict")
    if verdict == VERDICT_ELIGIBLE:
        return "proposed"
    if verdict == VERDICT_OPERATOR_REQUIRED:
        return "needs_human"
    return "blocked"


def _proposal_risk_for_row(row: dict[str, Any]) -> str:
    if row.get("verdict") == VERDICT_ELIGIBLE:
        return "LOW"
    if row.get("verdict") == VERDICT_OPERATOR_REQUIRED:
        return "MEDIUM"
    return "HIGH"


def _proposal_allowed_actions(row: dict[str, Any]) -> list[str]:
    if row.get("verdict") == VERDICT_ELIGIBLE:
        return ["create_branch", "open_pr"]
    return []


def _proposal_forbidden_actions(row: dict[str, Any]) -> list[str]:
    base = [
        "execute_research_action",
        "launch_codex",
        "mutate_campaign_queue",
        "mutate_strategy_or_preset",
        "enable_paper_runtime",
        "enable_shadow_runtime",
        "enable_live_runtime",
        "place_order",
        "allocate_capital",
    ]
    source_item = row.get("source_item") if isinstance(row.get("source_item"), dict) else {}
    for action in source_item.get("forbidden_actions") or []:
        if isinstance(action, str) and action not in base:
            base.append(action)
    return base


def _build_proposal_from_gate_row(row: dict[str, Any]) -> dict[str, Any]:
    proposal_id = _proposal_id(row)
    title = _proposal_title(row)
    branch_slug = _slug(str(row.get("action_id") or proposal_id))
    status = _proposal_status_for_row(row)
    risk_class = _proposal_risk_for_row(row)
    proposal_type = "qre_research_action"

    return {
        "proposal_id": proposal_id,
        "source": ARTIFACT_RELATIVE_PATH,
        "source_type": "qre_research_action_consumer_gate",
        "source_action_id": row.get("action_id"),
        "title": title,
        "summary": _proposal_summary(row),
        "proposal_type": proposal_type,
        "status": status,
        "risk_class": risk_class,
        "risk_reason": row.get("reason"),
        "affected_files": [
            "research/research_action_queue_latest.v1.json",
            "logs/qre_research_action_consumer_gate/latest.json",
        ],
        "required_tests": [
            "python -m pytest tests/unit/test_qre_research_action_consumer_gate.py -q"
        ],
        "suggested_branch_name": f"fix/qre-action-{branch_slug}",
        "allowed_actions": _proposal_allowed_actions(row),
        "forbidden_actions": _proposal_forbidden_actions(row),
        "operator_approval_required": row.get("operator_approval_required") is True,
        "safe_to_execute": False,
        "eligible_for_direct_execution": False,
        "eligible_for_ade_proposal_intake": row.get("eligible_for_ade_proposal_intake")
        is True,
        "parent_proposal_id": None,
        "evidence": {
            "gate_verdict": row.get("verdict"),
            "gate_reason": row.get("reason"),
            "source_section": row.get("source_section"),
            "target_candidate_id": row.get("target_candidate_id"),
            "blocked_reasons": row.get("blocked_reasons") or [],
            "warnings": row.get("warnings") or [],
        },
    }


def build_proposal_intake_snapshot(
    gate_snapshot: dict[str, Any],
    *,
    frozen_utc: str | None = None,
) -> dict[str, Any]:
    generated = frozen_utc or str(gate_snapshot.get("generated_at_utc") or _utcnow())
    rows = gate_snapshot.get("rows")
    valid_rows = [row for row in rows if isinstance(row, dict)] if isinstance(rows, list) else []
    proposals = [_build_proposal_from_gate_row(row) for row in valid_rows]

    counts = Counter(str(p.get("status") or "blocked") for p in proposals)
    return {
        "schema_version": SCHEMA_VERSION,
        "report_kind": "qre_research_action_proposal_intake",
        "generated_at_utc": generated,
        "source_gate": {
            "path": ARTIFACT_RELATIVE_PATH,
            "report_kind": gate_snapshot.get("report_kind"),
            "final_recommendation": gate_snapshot.get("final_recommendation"),
            "source": gate_snapshot.get("source"),
        },
        "mode": "proposal_intake_bridge",
        "safe_to_execute": False,
        "writes_ade_work_queue": False,
        "writes_development_work_queue": False,
        "mutates_campaign_queue": False,
        "mutates_strategy_or_preset": False,
        "mutates_paper_shadow_live_runtime": False,
        "proposal_count": len(proposals),
        "counts": {
            "proposed": counts.get("proposed", 0),
            "needs_human": counts.get("needs_human", 0),
            "blocked": counts.get("blocked", 0),
        },
        "proposals": proposals,
        "final_recommendation": (
            "ready_for_existing_ade_proposal_intake"
            if proposals and not counts.get("blocked", 0)
            else "operator_review_required_or_no_proposals"
        ),
    }


def _as_str_list(value: Any, *, max_items: int = 20) -> list[str]:
    if not isinstance(value, list):
        return []
    out: list[str] = []
    for item in value[:max_items]:
        if isinstance(item, str) and item.strip():
            out.append(_bounded_str(item, 160))
    return out


def _item_missing_fields(item: dict[str, Any]) -> list[str]:
    return [field for field in _REQUIRED_ITEM_FIELDS if field not in item]


def _forbidden_action_hits(item: dict[str, Any]) -> list[str]:
    forbidden = set(_as_str_list(item.get("forbidden_actions")))
    return sorted(action for action in _BLOCKING_FORBIDDEN_ACTIONS if action in forbidden)


def _gate_item(item: dict[str, Any], *, index: int) -> dict[str, Any]:
    missing = _item_missing_fields(item)
    forbidden_hits = _forbidden_action_hits(item)

    action_id = _bounded_str(item.get("action_id"), 160)
    status = _bounded_str(item.get("status"), 80)
    outcome_status = _bounded_str(item.get("outcome_status"), 80)
    operator_required = item.get("operator_approval_required") is True

    blockers: list[str] = []
    warnings: list[str] = []

    if missing:
        blockers.append("missing_required_item_fields")
    if forbidden_hits:
        blockers.append("forbidden_action_present")
    if status != "pending":
        blockers.append("item_status_not_pending")
    if outcome_status not in ("not_recorded", ""):
        blockers.append("item_outcome_already_recorded")
    if not action_id:
        blockers.append("missing_action_id")

    if item.get("execution_enabled") is True:
        blockers.append("item_execution_enabled_true")
    if item.get("ade_queue_written") is True:
        blockers.append("item_ade_queue_written_true")
    if item.get("campaign_queue_mutated") is True:
        blockers.append("item_campaign_queue_mutated_true")
    if item.get("paper_runtime_enabled") is True:
        blockers.append("item_paper_runtime_enabled_true")
    if item.get("shadow_runtime_enabled") is True:
        blockers.append("item_shadow_runtime_enabled_true")
    if item.get("live_eligible") is True:
        blockers.append("item_live_eligible_true")

    if item.get("priority") not in ("high", "medium", "low"):
        warnings.append("unknown_priority")

    if blockers:
        verdict = VERDICT_BLOCKED
        reason = ",".join(blockers)
    elif operator_required:
        verdict = VERDICT_OPERATOR_REQUIRED
        reason = "operator_approval_required"
    else:
        verdict = VERDICT_ELIGIBLE
        reason = "safe_for_ade_proposal_intake"

    return {
        "index": index,
        "action_id": action_id,
        "source_section": _bounded_str(item.get("source_section"), 160),
        "target_candidate_id": _bounded_str(item.get("target_candidate_id"), 240),
        "priority": _bounded_str(item.get("priority"), 40),
        "verdict": verdict,
        "reason": reason,
        "operator_approval_required": operator_required,
        "status": status,
        "outcome_status": outcome_status,
        "blocked_reasons": blockers,
        "warnings": warnings,
        "forbidden_action_hits": forbidden_hits,
        "safe_to_execute": False,
        "eligible_for_ade_proposal_intake": verdict == VERDICT_ELIGIBLE,
        "eligible_for_direct_execution": False,
        "source_item": {
            "action_id": action_id,
            "reason_codes": _as_str_list(item.get("reason_codes")),
            "bounded_next_step": _bounded_str(item.get("bounded_next_step"), 240),
            "forbidden_actions": _as_str_list(item.get("forbidden_actions")),
        },
    }


def _empty_counts() -> dict[str, int]:
    return {verdict: 0 for verdict in VERDICTS}


def _counts(rows: list[dict[str, Any]]) -> dict[str, int]:
    counter = Counter(str(row.get("verdict") or VERDICT_BLOCKED) for row in rows)
    out = _empty_counts()
    for key in out:
        out[key] = counter.get(key, 0)
    return out


def collect_snapshot(
    *,
    source_path: Path | None = None,
    frozen_utc: str | None = None,
) -> dict[str, Any]:
    generated = frozen_utc or _utcnow()
    source = source_path or QRE_ACTION_QUEUE_LATEST
    payload = _read_json(source)

    if payload is None:
        return {
            "schema_version": SCHEMA_VERSION,
            "report_kind": REPORT_KIND,
            "generated_at_utc": generated,
            "source": {
                "path": _rel(source),
                "status": "missing_or_unreadable",
                "schema_version": None,
            },
            "mode": "read_only_gate",
            "safe_to_execute": False,
            "writes_ade_queue": False,
            "writes_proposal_queue": False,
            "mutates_campaign_queue": False,
            "mutates_strategy_or_preset": False,
            "mutates_paper_shadow_live_runtime": False,
            "rows": [],
            "counts": _empty_counts(),
            "final_recommendation": "no_source_queue_available",
        }

    schema = payload.get("schema_version")
    items_raw = payload.get("items")
    rows: list[dict[str, Any]] = []

    source_blocked = schema != SUPPORTED_SOURCE_SCHEMA
    if isinstance(items_raw, list) and not source_blocked:
        for index, raw in enumerate(items_raw, start=1):
            if isinstance(raw, dict):
                rows.append(_gate_item(raw, index=index))
            else:
                rows.append(
                    {
                        "index": index,
                        "action_id": "",
                        "source_section": "",
                        "target_candidate_id": "",
                        "priority": "",
                        "verdict": VERDICT_BLOCKED,
                        "reason": "item_not_object",
                        "operator_approval_required": False,
                        "status": "",
                        "outcome_status": "",
                        "blocked_reasons": ["item_not_object"],
                        "warnings": [],
                        "forbidden_action_hits": [],
                        "safe_to_execute": False,
                        "eligible_for_ade_proposal_intake": False,
                        "eligible_for_direct_execution": False,
                        "source_item": {},
                    }
                )

    if source_blocked:
        final = "blocked_unsupported_source_schema"
    elif not isinstance(items_raw, list):
        final = "blocked_items_field_not_list"
    elif not rows:
        final = "no_queue_items"
    elif any(row["verdict"] == VERDICT_BLOCKED for row in rows):
        final = "operator_review_required_blocked_items_present"
    elif any(row["verdict"] == VERDICT_OPERATOR_REQUIRED for row in rows):
        final = "operator_review_required"
    else:
        final = "ready_for_ade_proposal_intake"

    return {
        "schema_version": SCHEMA_VERSION,
        "report_kind": REPORT_KIND,
        "generated_at_utc": generated,
        "source": {
            "path": _rel(source),
            "status": "ok",
            "schema_version": schema,
            "run_id": payload.get("run_id"),
            "preset": payload.get("preset"),
            "item_count": payload.get("item_count"),
        },
        "mode": "read_only_gate",
        "safe_to_execute": False,
        "writes_ade_queue": False,
        "writes_proposal_queue": False,
        "mutates_campaign_queue": False,
        "mutates_strategy_or_preset": False,
        "mutates_paper_shadow_live_runtime": False,
        "rows": rows,
        "counts": _counts(rows),
        "final_recommendation": final,
    }


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    if not path.resolve().is_relative_to(ARTIFACT_DIR.resolve()):
        raise ValueError(f"refusing write outside artifact dir: {path}")
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(f"{path.suffix}.tmp")
    tmp.write_text(json.dumps(payload, indent=2, sort_keys=False), encoding="utf-8")
    os.replace(tmp, path)


def write_outputs(snapshot: dict[str, Any]) -> Path:
    _atomic_write_json(ARTIFACT_LATEST, snapshot)
    return ARTIFACT_LATEST


def write_proposal_intake_outputs(snapshot: dict[str, Any]) -> Path:
    if not PROPOSAL_INTAKE_LATEST.resolve().is_relative_to(
        PROPOSAL_INTAKE_DIR.resolve()
    ):
        raise ValueError(
            f"refusing write outside proposal intake dir: {PROPOSAL_INTAKE_LATEST}"
        )
    PROPOSAL_INTAKE_DIR.mkdir(parents=True, exist_ok=True)
    tmp = PROPOSAL_INTAKE_LATEST.with_suffix(
        f"{PROPOSAL_INTAKE_LATEST.suffix}.tmp"
    )
    tmp.write_text(json.dumps(snapshot, indent=2, sort_keys=False), encoding="utf-8")
    os.replace(tmp, PROPOSAL_INTAKE_LATEST)
    return PROPOSAL_INTAKE_LATEST


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="reporting.qre_research_action_consumer_gate",
        description="Gate QRE research action sidecars for ADE proposal intake.",
    )
    parser.add_argument("--status", action="store_true")
    parser.add_argument("--no-write", action="store_true")
    parser.add_argument("--source", type=Path, default=None)
    parser.add_argument(
        "--write-proposal-intake",
        action="store_true",
        help="Also write proposal-queue-compatible QRE proposal intake artifact.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    snapshot = collect_snapshot(source_path=args.source)
    proposal_intake = build_proposal_intake_snapshot(snapshot)
    if args.status:
        print(json.dumps(snapshot, indent=2, sort_keys=False))
    if not args.no_write:
        write_outputs(snapshot)
        if args.write_proposal_intake:
            write_proposal_intake_outputs(proposal_intake)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "ARTIFACT_LATEST",
    "ARTIFACT_RELATIVE_PATH",
    "QRE_ACTION_QUEUE_LATEST",
    "PROPOSAL_INTAKE_LATEST",
    "PROPOSAL_INTAKE_RELATIVE_PATH",
    "REPORT_KIND",
    "SCHEMA_VERSION",
    "VERDICT_BLOCKED",
    "VERDICT_ELIGIBLE",
    "VERDICT_OPERATOR_REQUIRED",
    "build_proposal_intake_snapshot",
    "collect_snapshot",
    "write_outputs",
    "write_proposal_intake_outputs",
]
