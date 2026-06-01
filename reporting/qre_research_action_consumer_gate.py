"""Read-only ADE consumer gate for QRE research action sidecars.

This module reads ``research/research_action_queue_latest.v1.json`` and emits a
bounded classification artifact under ``logs/qre_research_action_consumer_gate``.

It does not execute actions, launch Codex, mutate campaigns, write the ADE work
queue, or change paper/shadow/live runtime behavior.
"""

from __future__ import annotations

import argparse
import json
import os
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
        raw = path.read_text(encoding="utf-8")
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


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="reporting.qre_research_action_consumer_gate",
        description="Gate QRE research action sidecars for ADE proposal intake.",
    )
    parser.add_argument("--status", action="store_true")
    parser.add_argument("--no-write", action="store_true")
    parser.add_argument("--source", type=Path, default=None)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    snapshot = collect_snapshot(source_path=args.source)
    if args.status:
        print(json.dumps(snapshot, indent=2, sort_keys=False))
    if not args.no_write:
        write_outputs(snapshot)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = [
    "ARTIFACT_LATEST",
    "ARTIFACT_RELATIVE_PATH",
    "QRE_ACTION_QUEUE_LATEST",
    "REPORT_KIND",
    "SCHEMA_VERSION",
    "VERDICT_BLOCKED",
    "VERDICT_ELIGIBLE",
    "VERDICT_OPERATOR_REQUIRED",
    "collect_snapshot",
    "write_outputs",
]
