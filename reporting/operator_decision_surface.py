"""Read-only operator decision surface for the ADE-QRE queue.

ADE-QRE-014I asks for an operator-facing report that explains why the
next item is next, why later items are blocked, why deferred items stay
deferred, and why strategy synthesis remains unavailable. This module
only reads governance docs and existing sidecars; it never mutates
queues, routes, campaigns, approvals, strategies, or execution paths.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
import re
import sys
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

REPO_ROOT: Final[Path] = Path(__file__).resolve().parent.parent
MODULE_VERSION: Final[str] = "ade-qre-014i-2026-05-24"
SCHEMA_VERSION: Final[int] = 1
REPORT_KIND: Final[str] = "operator_decision_surface_readiness"

QUEUE_DOC: Final[Path] = (
    REPO_ROOT
    / "docs"
    / "governance"
    / "ade_queue_001_post_package_qre_ade_work_queue.md"
)
TRUSTED_LOOP_LATEST: Final[Path] = (
    REPO_ROOT / "logs" / "trusted_loop_materialization" / "latest.json"
)
OBSERVABILITY_LATEST: Final[Path] = (
    REPO_ROOT / "logs" / "research_observability_minimal" / "latest.json"
)

ARTIFACT_DIR: Final[Path] = REPO_ROOT / "logs" / "operator_decision_surface"
ARTIFACT_LATEST: Final[Path] = ARTIFACT_DIR / "latest.json"
HISTORY: Final[Path] = ARTIFACT_DIR / "history.jsonl"
_WRITE_PREFIX: Final[str] = "logs/operator_decision_surface/"


@dataclass(frozen=True)
class QueueItem:
    item_id: str
    title: str
    order: int
    status: str
    body: str
    dependencies: tuple[str, ...]


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


def _validate_write_target(path: Path) -> None:
    normalised = str(path).replace("\\", "/")
    if _WRITE_PREFIX not in normalised:
        raise ValueError(
            "operator_decision_surface: refusing write outside allowlist: "
            f"{path!r}"
        )


def _read_json(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _read_text(path: Path) -> str | None:
    if not path.is_file():
        return None
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return None


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
        status_match = re.search(r"^- status:\s+`([^`]+)`", body, re.M)
        if status_match is None:
            continue
        dependencies = tuple(
            dep_match.group("item_id")
            for dep_match in re.finditer(
                r"^- depends on:\s+`(?P<item_id>[A-Z0-9-]+) done`",
                body,
                re.M,
            )
        )
        items[item_id] = QueueItem(
            item_id=item_id,
            title=match.group("title").strip(),
            order=index,
            status=status_match.group(1),
            body=body,
            dependencies=dependencies,
        )
    return items


def _field(item: QueueItem, name: str) -> str:
    lines = item.body.splitlines()
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


def _dependencies_done(item: QueueItem, items: Mapping[str, QueueItem]) -> bool:
    return all(items.get(dep) and items[dep].status == "done" for dep in item.dependencies)


def _stale_historical_ready_items(items: Mapping[str, QueueItem]) -> set[str]:
    max_done_order = max(
        (item.order for item in items.values() if item.status == "done"),
        default=-1,
    )
    return {
        item.item_id
        for item in items.values()
        if item.status == "ready" and item.order < max_done_order
    }


def _next_eligible_ready_item(items: Mapping[str, QueueItem]) -> QueueItem | None:
    stale = _stale_historical_ready_items(items)
    candidates = [
        item
        for item in items.values()
        if item.status == "ready"
        and item.item_id not in stale
        and _dependencies_done(item, items)
    ]
    if not candidates:
        return None
    return min(candidates, key=lambda item: item.order)


def _source_status(path: Path, payload: Mapping[str, Any] | None = None) -> dict[str, Any]:
    return {
        "available": path.is_file() and payload is not None,
        "path": _rel(path),
        "status": "present" if path.is_file() and payload is not None else "missing_or_invalid",
        "fails_closed": not (path.is_file() and payload is not None),
    }


def _queue_source_status(path: Path, text: str | None) -> dict[str, Any]:
    return {
        "available": text is not None,
        "path": _rel(path),
        "status": "present" if text is not None else "missing_or_unreadable",
        "fails_closed": text is None,
    }


def _dependency_explanation(item: QueueItem, items: Mapping[str, QueueItem]) -> str:
    if not item.dependencies:
        return "No explicit dependency is listed."
    states = [
        f"{dep}={items[dep].status if dep in items else 'missing'}"
        for dep in item.dependencies
    ]
    return "Dependencies: " + ", ".join(states) + "."


def _next_section(
    item: QueueItem | None,
    items: Mapping[str, QueueItem],
) -> dict[str, Any]:
    if item is None:
        return {
            "status": "fail_closed",
            "queue_item": None,
            "operator_explanation": (
                "No eligible ready queue item can be selected from the current "
                "queue evidence."
            ),
            "missing_evidence": ["eligible_ready_queue_item"],
            "evidence_refs": [_rel(QUEUE_DOC)],
        }
    return {
        "status": "ready",
        "queue_item": item.item_id,
        "title": item.title,
        "queue_status": item.status,
        "dependencies": list(item.dependencies),
        "dependencies_done": _dependencies_done(item, items),
        "purpose": _field(item, "purpose") or _field(item, "goal"),
        "operator_explanation": (
            f"{item.item_id} is next because it is the earliest non-stale "
            "ready item and all listed dependencies are done. "
            + _dependency_explanation(item, items)
        ),
        "missing_evidence": [],
        "evidence_refs": [_rel(QUEUE_DOC), f"{item.item_id}.status", f"{item.item_id}.depends_on"],
    }


def _blocked_dependency(status: str) -> str | None:
    match = re.match(r"blocked until ([A-Z0-9-]+) done", status)
    return match.group(1) if match else None


def _blocked_sections(items: Mapping[str, QueueItem]) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for item in sorted(items.values(), key=lambda row: row.order):
        if not item.status.startswith("blocked"):
            continue
        dependency = _blocked_dependency(item.status)
        dependency_status = (
            items[dependency].status
            if dependency is not None and dependency in items
            else "missing"
        )
        rows.append(
            {
                "queue_item": item.item_id,
                "title": item.title,
                "queue_status": item.status,
                "blocked_by": dependency,
                "blocked_by_status": dependency_status,
                "operator_explanation": (
                    f"{item.item_id} is blocked because {dependency or 'a prerequisite'} "
                    f"is not done; current prerequisite status is {dependency_status}."
                ),
                "fail_closed": True,
                "evidence_refs": [_rel(QUEUE_DOC), f"{item.item_id}.status"],
            }
        )
    return {
        "count": len(rows),
        "items": rows,
        "operator_summary": (
            f"{len(rows)} blocked queue items are visible with dependency reasons."
        ),
    }


def _deferred_sections(items: Mapping[str, QueueItem]) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    for item in sorted(items.values(), key=lambda row: row.order):
        if not item.status.startswith("deferred"):
            continue
        condition = item.status.removeprefix("deferred").strip()
        rows.append(
            {
                "queue_item": item.item_id,
                "title": item.title,
                "queue_status": item.status,
                "defer_condition": condition or "not specified",
                "operator_explanation": (
                    f"{item.item_id} remains deferred by queue status: {item.status}."
                ),
                "fail_closed": True,
                "evidence_refs": [_rel(QUEUE_DOC), f"{item.item_id}.status"],
            }
        )
    return {
        "count": len(rows),
        "items": rows,
        "operator_summary": f"{len(rows)} deferred queue items remain non-selectable.",
    }


def _trusted_loop_synthesis_blockers(payload: Mapping[str, Any] | None) -> dict[str, Any]:
    if not isinstance(payload, Mapping):
        return {
            "available": False,
            "fail_closed": True,
            "active_blocker_count": None,
            "explained_blocker_count": 0,
            "missing_evidence": ["trusted_loop_materialization_latest"],
            "operator_summary": (
                "Trusted-loop materialization is missing; synthesis stays blocked "
                "because blocker evidence cannot be proven complete."
            ),
        }
    density = payload.get("synthesis_blocker_explanation_density")
    if not isinstance(density, Mapping):
        return {
            "available": True,
            "fail_closed": True,
            "active_blocker_count": None,
            "explained_blocker_count": 0,
            "missing_evidence": ["synthesis_blocker_explanation_density"],
            "operator_summary": (
                "Trusted-loop materialization is present but does not contain "
                "the synthesis blocker explanation density."
            ),
        }
    return {
        "available": True,
        "fail_closed": bool(density.get("overall_status") != "blocked_explained"),
        "active_blocker_count": density.get("active_blocker_count"),
        "explained_blocker_count": density.get("explained_blocker_count"),
        "missing_evidence": list(density.get("unexplained_block_reasons") or []),
        "operator_summary": density.get("operator_summary")
        or "Trusted-loop synthesis blocker summary is present but thin.",
    }


def _observability_evidence(payload: Mapping[str, Any] | None) -> dict[str, Any]:
    if not isinstance(payload, Mapping):
        return {
            "available": False,
            "operator_state": "missing",
            "fail_closed": True,
            "missing_evidence": ["research_observability_minimal_latest"],
        }
    qre = payload.get("qre_operator_summary")
    qre = qre if isinstance(qre, Mapping) else {}
    return {
        "available": True,
        "operator_state": qre.get("operator_state"),
        "unknown_failure_rate": qre.get("unknown_failure_rate"),
        "actionable_failure_rate": qre.get("actionable_failure_rate"),
        "attribution_depth_score": qre.get("attribution_depth_score"),
        "fail_closed": qre.get("operator_state") == "missing_upstream_evidence",
        "missing_evidence": list(qre.get("missing_sources") or []),
    }


def _no_synthesis_section(
    *,
    trusted_loop_payload: Mapping[str, Any] | None,
    observability_payload: Mapping[str, Any] | None,
) -> dict[str, Any]:
    trusted = _trusted_loop_synthesis_blockers(trusted_loop_payload)
    observability = _observability_evidence(observability_payload)
    missing = []
    missing.extend(trusted["missing_evidence"])
    missing.extend(observability["missing_evidence"])
    return {
        "status": "blocked",
        "synthesis_enabled": False,
        "safe_to_execute": False,
        "reason_codes": [
            "no_strategy_synthesis_scope_authorized",
            "read_only_decision_surface_only",
            "missing_or_thin_evidence_fails_closed",
        ],
        "missing_evidence": sorted(dict.fromkeys(str(item) for item in missing)),
        "trusted_loop_blockers": trusted,
        "observability_evidence": observability,
        "operator_explanation": (
            "Strategy synthesis remains blocked: the current queue authorizes "
            "only read-only decision-surface reporting, and missing or thin "
            "trusted-loop evidence fails closed."
        ),
        "evidence_refs": [
            _rel(QUEUE_DOC),
            _rel(TRUSTED_LOOP_LATEST),
            _rel(OBSERVABILITY_LATEST),
        ],
    }


def collect_snapshot(
    *,
    queue_doc_path: Path | None = None,
    trusted_loop_path: Path | None = None,
    observability_path: Path | None = None,
    frozen_utc: str | None = None,
) -> dict[str, Any]:
    ts = frozen_utc or _utcnow()
    queue_path = queue_doc_path or QUEUE_DOC
    trusted_path = trusted_loop_path or TRUSTED_LOOP_LATEST
    observability_path = observability_path or OBSERVABILITY_LATEST

    queue_text = _read_text(queue_path)
    trusted_loop = _read_json(trusted_path)
    observability = _read_json(observability_path)
    items = parse_queue_items(queue_text) if queue_text is not None else {}
    next_item = _next_eligible_ready_item(items)
    blocked = _blocked_sections(items)
    deferred = _deferred_sections(items)
    no_synthesis = _no_synthesis_section(
        trusted_loop_payload=trusted_loop,
        observability_payload=observability,
    )

    queue_ready = queue_text is not None and next_item is not None
    return {
        "schema_version": SCHEMA_VERSION,
        "module_version": MODULE_VERSION,
        "report_kind": REPORT_KIND,
        "generated_at_utc": ts,
        "mode": "dry-run",
        "safe_to_execute": False,
        "source_status": {
            "queue_doc": _queue_source_status(queue_path, queue_text),
            "trusted_loop_materialization": _source_status(trusted_path, trusted_loop),
            "research_observability_minimal": _source_status(
                observability_path,
                observability,
            ),
        },
        "decision_surface": {
            "next": _next_section(next_item, items),
            "blocked": blocked,
            "deferred": deferred,
            "no_synthesis": no_synthesis,
        },
        "operator_lines": [
            _next_section(next_item, items)["operator_explanation"],
            blocked["operator_summary"],
            deferred["operator_summary"],
            no_synthesis["operator_explanation"],
        ],
        "final_recommendation": (
            "operator_decision_surface_ready"
            if queue_ready
            else "fail_closed_no_next_item"
        ),
        "safety_invariants": {
            "read_only": True,
            "adds_dashboard_mutation_routes": False,
            "adds_approval_mutation": False,
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
        prog="reporting.operator_decision_surface",
        description="Build a read-only ADE-QRE operator decision surface.",
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
    "collect_snapshot",
    "parse_queue_items",
    "read_latest_snapshot",
    "write_outputs",
]
