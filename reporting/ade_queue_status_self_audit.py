"""Read-only ADE-QRE queue/status self-audit.

ADE-QRE-014N requires queue status consistency to be checkable from the
governance queue itself. This module parses the queue markdown, reports
done-evidence gaps, blocked/deferred reason gaps, stale historical ready
items, dependency state, and the single next eligible ready item.

It is intentionally read-only: no approvals, routing, campaigns, strategy
registration, dashboards, Addendum runtime layers, or execution paths are
mutated.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
import re
import sys
from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

REPO_ROOT: Final[Path] = Path(__file__).resolve().parent.parent
MODULE_VERSION: Final[str] = "ade-qre-014n-2026-05-27"
SCHEMA_VERSION: Final[int] = 1
REPORT_KIND: Final[str] = "ade_queue_status_self_audit"

QUEUE_DOC: Final[Path] = (
    REPO_ROOT
    / "docs"
    / "governance"
    / "ade_queue_001_post_package_qre_ade_work_queue.md"
)
ARTIFACT_DIR: Final[Path] = REPO_ROOT / "logs" / "ade_queue_status_self_audit"
ARTIFACT_LATEST: Final[Path] = ARTIFACT_DIR / "latest.json"
HISTORY: Final[Path] = ARTIFACT_DIR / "history.jsonl"
_WRITE_PREFIX: Final[str] = "logs/ade_queue_status_self_audit/"

_STATUS_FAMILIES: Final[tuple[str, ...]] = (
    "done",
    "ready",
    "blocked",
    "deferred",
    "operator_review",
)

WARNING_CLASSIFICATION: Final[tuple[str, ...]] = (
    "active_blocker",
    "stale_historical_state",
    "superseded",
    "missing_completion_evidence",
    "requires_operator_review",
    "non_blocking_warning",
)

_SELECTION_BLOCKING_WARNING_CLASSIFICATIONS: Final[frozenset[str]] = frozenset(
    {"active_blocker", "requires_operator_review"}
)


@dataclass(frozen=True)
class QueueItem:
    item_id: str
    title: str
    order: int
    status: str
    body: str
    dependencies: tuple[str, ...]
    next_dependency: str | None


def _utcnow() -> str:
    return (
        _dt.datetime.now(_dt.UTC)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def _rel(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(REPO_ROOT.resolve())).replace("\\", "/")
    except ValueError:
        return str(path).replace("\\", "/")


def _read_text(path: Path) -> str | None:
    if not path.is_file():
        return None
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return None


def _read_json(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _validate_write_target(path: Path) -> None:
    normalized = str(path).replace("\\", "/")
    if _WRITE_PREFIX not in normalized:
        raise ValueError(
            "ade_queue_status_self_audit: refusing write outside allowlist: "
            f"{path!r}"
        )


def _field(body: str, name: str) -> str:
    lines = body.splitlines()
    prefix = f"- {name}:"
    for index, line in enumerate(lines):
        if not line.startswith(prefix):
            continue
        parts = [line.removeprefix(prefix).strip()]
        for continuation in lines[index + 1 :]:
            if continuation.startswith("- "):
                break
            stripped = continuation.strip()
            if stripped:
                parts.append(stripped)
        return " ".join(" ".join(parts).split())
    return ""


def _strip_inline_code(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value.startswith("`") and value.endswith("`"):
        return value[1:-1].strip()
    return value


def parse_queue_items(text: str) -> dict[str, QueueItem]:
    headings = list(
        re.finditer(
            r"^### (?P<item_id>[A-Z0-9-]+) - (?P<title>.+)$",
            text,
            re.M,
        )
    )
    items: dict[str, QueueItem] = {}
    for index, match in enumerate(headings):
        start = match.end()
        end = headings[index + 1].start() if index + 1 < len(headings) else len(text)
        item_id = match.group("item_id")
        body = text[start:end]
        status = _strip_inline_code(_field(body, "status"))
        if not status:
            continue
        dependencies = tuple(
            dep_match.group("item_id")
            for dep_match in re.finditer(
                r"^- depends on:\s+`(?P<item_id>[A-Z0-9-]+) done`",
                body,
                re.M,
            )
        )
        next_dependency_match = re.search(
            r"^- next dependency:\s+`(?P<item_id>[A-Z0-9-]+)`",
            body,
            re.M,
        )
        items[item_id] = QueueItem(
            item_id=item_id,
            title=match.group("title").strip(),
            order=index,
            status=status,
            body=body,
            dependencies=dependencies,
            next_dependency=(
                next_dependency_match.group("item_id")
                if next_dependency_match is not None
                else None
            ),
        )
    return items


def status_family(status: str) -> str:
    if status in {"done", "ready", "operator_review"}:
        return status
    if status.startswith("blocked"):
        return "blocked"
    if status.startswith("deferred"):
        return "deferred"
    return "unknown"


def done_evidence(item: QueueItem) -> dict[str, Any]:
    evidence = _field(item.body, "completion evidence")
    evidence_text = " ".join((evidence or item.body).split())
    evidence_lower = evidence_text.lower()
    checks = {
        "completion_evidence_field": bool(evidence),
        "pr_reference": re.search(r"\bPR #\d+\b", evidence_text, re.I) is not None,
        "merge_sha": "merge" in evidence_lower
        and re.search(r"\b[0-9a-f]{7,40}\b", evidence_text) is not None,
        "ci_or_gate_result": any(
            marker in evidence_lower
            for marker in (
                "checks green",
                "gate green",
                "gates green",
                "runs green",
                "completed/success",
                "succeeded",
                "non-blocking",
            )
        ),
        "frozen_contracts": "frozen contracts unchanged" in evidence_lower,
        "protected_paths": any(
            marker in evidence_lower
            for marker in (
                "protected/execution paths untouched",
                "protected paths untouched",
                "protected, frozen, and execution paths untouched",
                "no protected or frozen path diff",
            )
        ),
    }
    missing = [name for name, present in checks.items() if not present]
    return {
        "complete": not missing,
        "missing": missing,
        "checks": checks,
        "evidence": evidence,
    }


def dependencies_done(
    item: QueueItem,
    items: Mapping[str, QueueItem],
) -> bool:
    return all(items.get(dep) and items[dep].status == "done" for dep in item.dependencies)


def dependency_statuses(
    item: QueueItem,
    items: Mapping[str, QueueItem],
) -> dict[str, str]:
    return {
        dep: items[dep].status if dep in items else "missing"
        for dep in item.dependencies
    }


def stale_historical_ready_items(
    items: Mapping[str, QueueItem],
) -> tuple[str, ...]:
    max_done_order = max(
        (item.order for item in items.values() if item.status == "done"),
        default=-1,
    )
    return tuple(
        item.item_id
        for item in sorted(items.values(), key=lambda row: row.order)
        if item.status == "ready" and item.order < max_done_order
    )


def _has_explicit_blocked_reason(item: QueueItem) -> bool:
    status = item.status.lower()
    return status.startswith("blocked until ") and len(status.split("blocked until ", 1)[1].strip()) > 0


def _has_explicit_deferred_reason(item: QueueItem) -> bool:
    status = item.status.lower()
    if status.startswith("deferred ") and len(status.removeprefix("deferred").strip()) > 0:
        return True
    return bool(_field(item.body, "defer criteria") or _field(item.body, "defer condition"))


def reason_audit(item: QueueItem) -> dict[str, Any]:
    family = status_family(item.status)
    if family == "blocked":
        explicit = _has_explicit_blocked_reason(item)
        return {
            "applies": True,
            "explicit": explicit,
            "kind": "blocked",
            "reason": item.status.removeprefix("blocked").strip() or None,
            "missing": [] if explicit else ["blocked_reason"],
        }
    if family == "deferred":
        explicit = _has_explicit_deferred_reason(item)
        return {
            "applies": True,
            "explicit": explicit,
            "kind": "deferred",
            "reason": item.status.removeprefix("deferred").strip() or None,
            "missing": [] if explicit else ["deferred_reason"],
        }
    return {
        "applies": False,
        "explicit": None,
        "kind": None,
        "reason": None,
        "missing": [],
    }


def eligibility_blockers(
    item: QueueItem,
    items: Mapping[str, QueueItem],
    stale_ready: set[str],
) -> list[str]:
    blockers: list[str] = []
    family = status_family(item.status)
    if item.status != "ready":
        blockers.append(f"status_{family}")
    if item.item_id in stale_ready:
        blockers.append("stale_historical_ready")
    if not dependencies_done(item, items):
        blockers.append("dependencies_not_done")
    return blockers


def _warning_classification(item: QueueItem) -> str:
    value = _strip_inline_code(_field(item.body, "warning classification"))
    if value in WARNING_CLASSIFICATION:
        return value
    return "active_blocker"


def _warning_issue_kind(
    *,
    item: QueueItem,
    done: dict[str, Any] | None,
    stale_historical_ready: bool,
) -> str | None:
    if item.status == "done" and done is not None and not done["complete"]:
        return "missing_done_evidence"
    if stale_historical_ready:
        return "stale_historical_ready"
    return None


def queue_warning(
    *,
    item: QueueItem,
    done: dict[str, Any] | None,
    stale_historical_ready: bool,
) -> dict[str, Any] | None:
    issue_kind = _warning_issue_kind(
        item=item,
        done=done,
        stale_historical_ready=stale_historical_ready,
    )
    if issue_kind is None:
        return None
    classification = _warning_classification(item)
    return {
        "issue_kind": issue_kind,
        "classification": classification,
        "selection_blocking": classification
        in _SELECTION_BLOCKING_WARNING_CLASSIFICATIONS,
        "rationale": _field(item.body, "warning rationale"),
    }


def next_eligible_ready_item(
    items: Mapping[str, QueueItem],
) -> QueueItem | None:
    stale_ready = set(stale_historical_ready_items(items))
    candidates = [
        item
        for item in items.values()
        if item.status == "ready"
        and item.item_id not in stale_ready
        and dependencies_done(item, items)
    ]
    if not candidates:
        return None
    return min(candidates, key=lambda row: row.order)


def audit_items(items: Mapping[str, QueueItem]) -> list[dict[str, Any]]:
    stale_ready = set(stale_historical_ready_items(items))
    rows: list[dict[str, Any]] = []
    for item in sorted(items.values(), key=lambda row: row.order):
        family = status_family(item.status)
        done = done_evidence(item) if item.status == "done" else None
        reason = reason_audit(item)
        blockers = eligibility_blockers(item, items, stale_ready)
        warning = queue_warning(
            item=item,
            done=done,
            stale_historical_ready=item.item_id in stale_ready,
        )
        rows.append(
            {
                "queue_item": item.item_id,
                "title": item.title,
                "order": item.order,
                "status": item.status,
                "status_family": family,
                "dependencies": list(item.dependencies),
                "dependency_statuses": dependency_statuses(item, items),
                "dependencies_done": dependencies_done(item, items),
                "next_dependency": item.next_dependency,
                "done_evidence": done,
                "queue_warning": warning,
                "blocked_deferred_reason": reason,
                "stale_historical_ready": item.item_id in stale_ready,
                "auto_selectable": not blockers,
                "eligibility_blockers": blockers,
            }
        )
    return rows


def collect_snapshot(
    *,
    queue_doc_path: Path | None = None,
    frozen_utc: str | None = None,
) -> dict[str, Any]:
    path = queue_doc_path or QUEUE_DOC
    text = _read_text(path)
    items = parse_queue_items(text) if text is not None else {}
    rows = audit_items(items)
    next_item = next_eligible_ready_item(items)
    status_counts = Counter(row["status_family"] for row in rows)
    missing_done = [
        row["queue_item"]
        for row in rows
        if row["status"] == "done"
        and row["done_evidence"] is not None
        and not row["done_evidence"]["complete"]
    ]
    blocked_missing_reason = [
        row["queue_item"]
        for row in rows
        if row["status_family"] == "blocked"
        and row["blocked_deferred_reason"]["explicit"] is False
    ]
    deferred_missing_reason = [
        row["queue_item"]
        for row in rows
        if row["status_family"] == "deferred"
        and row["blocked_deferred_reason"]["explicit"] is False
    ]
    stale_ready = [row["queue_item"] for row in rows if row["stale_historical_ready"]]
    eligible = [row["queue_item"] for row in rows if row["auto_selectable"]]
    dependency_gaps = [
        row["queue_item"]
        for row in rows
        if any(status == "missing" for status in row["dependency_statuses"].values())
    ]
    warning_rows = [
        {
            "queue_item": row["queue_item"],
            "issue_kind": row["queue_warning"]["issue_kind"],
            "classification": row["queue_warning"]["classification"],
            "selection_blocking": row["queue_warning"]["selection_blocking"],
        }
        for row in rows
        if isinstance(row["queue_warning"], dict)
    ]
    selection_blocking_warning_items = [
        row["queue_item"]
        for row in warning_rows
        if row["selection_blocking"]
    ]

    if text is None:
        final_recommendation = "fail_closed_missing_queue_doc"
    elif len(eligible) != 1:
        final_recommendation = "operator_review_required_queue_selection_ambiguous"
    elif selection_blocking_warning_items:
        final_recommendation = "operator_review_required_queue_selection_ambiguous"
    elif (
        missing_done
        or blocked_missing_reason
        or deferred_missing_reason
        or dependency_gaps
    ):
        final_recommendation = "queue_status_audit_ready_with_warnings"
    else:
        final_recommendation = "queue_status_audit_passed"

    return {
        "schema_version": SCHEMA_VERSION,
        "module_version": MODULE_VERSION,
        "report_kind": REPORT_KIND,
        "generated_at_utc": frozen_utc or _utcnow(),
        "mode": "dry-run",
        "safe_to_execute": False,
        "source_status": {
            "queue_doc": {
                "available": text is not None,
                "path": _rel(path),
                "status": "present" if text is not None else "missing_or_unreadable",
                "fails_closed": text is None,
            }
        },
        "summary": {
            "total_items": len(rows),
            "status_counts": {family: int(status_counts.get(family, 0)) for family in (*_STATUS_FAMILIES, "unknown")},
            "missing_done_evidence_items": missing_done,
            "blocked_items_missing_reason": blocked_missing_reason,
            "deferred_items_missing_reason": deferred_missing_reason,
            "stale_historical_ready_items": stale_ready,
            "dependency_gap_items": dependency_gaps,
            "warning_rows": warning_rows,
            "selection_blocking_warning_items": selection_blocking_warning_items,
            "eligible_ready_items": eligible,
            "next_eligible_ready_item": next_item.item_id if next_item is not None else None,
        },
        "items": rows,
        "final_recommendation": final_recommendation,
        "safety_invariants": {
            "read_only": True,
            "adds_dashboard_mutation_routes": False,
            "adds_approval_mutation": False,
            "expands_autonomous_authority": False,
            "mutates_campaign_queue": False,
            "mutates_routing": False,
            "mutates_strategy_or_registry": False,
            "mutates_frozen_contracts": False,
            "strategy_synthesis_enabled": False,
            "addendum_runtime_activated": False,
            "paper_shadow_live_forbidden": True,
            "broker_risk_execution_forbidden": True,
        },
    }


def write_outputs(
    snapshot: Mapping[str, Any],
    *,
    artifact_dir: Path | None = None,
) -> dict[str, str]:
    base = artifact_dir or ARTIFACT_DIR
    ts = str(snapshot["generated_at_utc"]).replace(":", "-")
    base.mkdir(parents=True, exist_ok=True)
    latest = base / ARTIFACT_LATEST.name
    timestamped = base / f"{ts}.json"
    history = base / HISTORY.name
    payload = json.dumps(snapshot, sort_keys=True, indent=2)

    for target in (latest, timestamped, history):
        _validate_write_target(target)

    tmp_latest = latest.with_suffix(latest.suffix + ".tmp")
    tmp_latest.write_text(payload, encoding="utf-8")
    os.replace(tmp_latest, latest)

    tmp_timestamped = timestamped.with_suffix(timestamped.suffix + ".tmp")
    tmp_timestamped.write_text(payload, encoding="utf-8")
    os.replace(tmp_timestamped, timestamped)

    compact = json.dumps(snapshot, sort_keys=True, separators=(",", ":"))
    with history.open("a", encoding="utf-8") as handle:
        handle.write(compact + "\n")

    return {
        "latest": _rel(latest),
        "timestamped": _rel(timestamped),
        "history": _rel(history),
    }


def read_latest_snapshot(*, artifact_dir: Path | None = None) -> dict[str, Any] | None:
    base = artifact_dir or ARTIFACT_DIR
    return _read_json(base / ARTIFACT_LATEST.name)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="reporting.ade_queue_status_self_audit",
        description="Build a read-only ADE-QRE queue/status self-audit.",
    )
    parser.add_argument("--status", action="store_true")
    parser.add_argument("--no-write", action="store_true")
    parser.add_argument("--frozen-utc", type=str, default=None)
    args = parser.parse_args(argv)

    if args.status:
        snapshot = read_latest_snapshot()
        if snapshot is None:
            snapshot = {
                "schema_version": SCHEMA_VERSION,
                "module_version": MODULE_VERSION,
                "report_kind": REPORT_KIND,
                "final_recommendation": "not_available",
            }
        print(json.dumps(snapshot, sort_keys=True, indent=2))
        return 0

    snapshot = collect_snapshot(frozen_utc=args.frozen_utc)
    if not args.no_write:
        snapshot["_artifact_paths"] = write_outputs(snapshot)
    print(json.dumps(snapshot, sort_keys=True, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())


__all__ = [
    "REPORT_KIND",
    "SCHEMA_VERSION",
    "QueueItem",
    "audit_items",
    "collect_snapshot",
    "dependencies_done",
    "done_evidence",
    "next_eligible_ready_item",
    "parse_queue_items",
    "read_latest_snapshot",
    "reason_audit",
    "stale_historical_ready_items",
    "status_family",
    "write_outputs",
]
