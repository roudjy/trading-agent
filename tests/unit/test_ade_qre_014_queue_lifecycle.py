from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

_QUEUE_DOC = (
    Path(__file__).resolve().parents[2]
    / "docs"
    / "governance"
    / "ade_queue_001_post_package_qre_ade_work_queue.md"
)


@dataclass(frozen=True)
class QueueItem:
    item_id: str
    order: int
    status: str
    body: str
    dependencies: tuple[str, ...]


def _parse_queue_items(text: str) -> dict[str, QueueItem]:
    headings = list(
        re.finditer(r"^### (?P<item_id>[A-Z0-9-]+) - .+$", text, re.M)
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
            order=index,
            status=status_match.group(1),
            body=body,
            dependencies=dependencies,
        )
    return items


def _done_evidence_is_complete(item: QueueItem) -> bool:
    text = re.sub(r"\s+", " ", item.body.lower())
    has_pr = re.search(r"\bpr #\d+\b", item.body, re.I) is not None
    has_merge_sha = "merge" in text and (
        re.search(r"\b[0-9a-f]{7,40}\b", item.body) is not None
    )
    has_green_or_non_blocking = any(
        marker in text
        for marker in (
            "checks green",
            "gate green",
            "runs green",
            "completed/success",
            "non-blocking",
        )
    )
    has_frozen_status = "frozen contracts unchanged" in text
    has_protected_status = (
        "protected/execution paths untouched" in text
        or "protected paths untouched" in text
        or "no protected or frozen path diff" in text
    )
    return bool(
        has_pr
        and has_merge_sha
        and has_green_or_non_blocking
        and has_frozen_status
        and has_protected_status
    )


def _dependencies_done(item: QueueItem, items: dict[str, QueueItem]) -> bool:
    return all(items[dep].status == "done" for dep in item.dependencies)


def _auto_selectable_status(item: QueueItem) -> bool:
    return item.status == "ready"


def _stale_historical_ready_items(items: dict[str, QueueItem]) -> tuple[str, ...]:
    max_done_order = max(
        (item.order for item in items.values() if item.status == "done"),
        default=-1,
    )
    stale = sorted(
        item.item_id
        for item in items.values()
        if item.status == "ready" and item.order < max_done_order
    )
    return tuple(stale)


def _next_eligible_ready_item(items: dict[str, QueueItem]) -> QueueItem | None:
    stale_items = set(_stale_historical_ready_items(items))
    candidates = [
        item
        for item in items.values()
        if _auto_selectable_status(item)
        and item.item_id not in stale_items
        and _dependencies_done(item, items)
    ]
    if not candidates:
        return None
    return min(candidates, key=lambda item: item.order)


def test_ade_qre_014_active_queue_lifecycle_is_consistent() -> None:
    """Pin the ADE-QRE-014 done -> ready -> blocked lifecycle.

    This is a docs/governance-only guardrail: it validates the active
    queue document without mutating runtime state, strategy code, or
    research outputs.
    """
    items = _parse_queue_items(_QUEUE_DOC.read_text(encoding="utf-8"))

    item_a = items["ADE-QRE-014A"]
    item_b = items["ADE-QRE-014B"]
    item_c = items["ADE-QRE-014C"]
    item_d = items["ADE-QRE-014D"]
    item_e = items["ADE-QRE-014E"]
    item_g = items["ADE-QRE-014G"]
    item_h = items["ADE-QRE-014H"]

    assert item_a.status == "done"
    assert _done_evidence_is_complete(item_a)
    assert item_b.status == "done"
    assert _done_evidence_is_complete(item_b)

    assert item_c.status == "done"
    assert _done_evidence_is_complete(item_c)
    assert item_c.dependencies == ("ADE-QRE-014B",)
    assert _dependencies_done(item_c, items) is True

    assert item_d.status == "done"
    assert _done_evidence_is_complete(item_d)
    assert item_d.dependencies == ("ADE-QRE-014C",)
    assert _dependencies_done(item_d, items) is True
    assert _auto_selectable_status(item_d) is False

    assert item_e.status == "done"
    assert _done_evidence_is_complete(item_e)
    assert item_e.dependencies == ("ADE-QRE-014D",)
    assert _dependencies_done(item_e, items) is True
    assert _auto_selectable_status(item_e) is False

    assert "ADE-QRE-011" in _stale_historical_ready_items(items)

    item_f = items["ADE-QRE-014F"]
    assert item_f.status.startswith("deferred")
    assert _auto_selectable_status(item_f) is False

    assert item_g.status == "done"
    assert _done_evidence_is_complete(item_g)
    assert item_g.dependencies == ("ADE-QRE-014E",)
    assert _dependencies_done(item_g, items) is True
    assert _auto_selectable_status(item_g) is False

    assert item_h.status == "ready"
    assert item_h.dependencies == ("ADE-QRE-014G",)
    assert _dependencies_done(item_h, items) is True
    assert _auto_selectable_status(item_h) is True
    assert _next_eligible_ready_item(items) == item_h


def test_done_queue_item_without_merge_evidence_is_rejected() -> None:
    fixture = """
### ITEM-A - Completed Item

- queue id: `ITEM-A`
- status: `done`
- completion evidence: PR #1, merge SHA `abc1234`; checks green; frozen contracts unchanged; protected/execution paths untouched.

### ITEM-B - Next Ready Item

- queue id: `ITEM-B`
- status: `ready`
- depends on: `ITEM-A done`

### ITEM-C - Blocked Item

- queue id: `ITEM-C`
- status: `blocked until ITEM-B done`
- depends on: `ITEM-B done`

### ITEM-D - Invalid Done Item

- queue id: `ITEM-D`
- status: `done`
- completion evidence: PR #2; checks green; frozen contracts unchanged; protected/execution paths untouched.
"""
    items = _parse_queue_items(fixture)

    assert _done_evidence_is_complete(items["ITEM-A"]) is True
    assert items["ITEM-B"].status == "ready"
    assert _dependencies_done(items["ITEM-B"], items) is True
    assert _dependencies_done(items["ITEM-C"], items) is False
    assert _done_evidence_is_complete(items["ITEM-D"]) is False


def test_done_queue_item_without_validation_evidence_is_rejected() -> None:
    fixture = """
### ITEM-A - Completed Item Without Validation

- queue id: `ITEM-A`
- status: `done`
- completion evidence: PR #1, merge SHA `abc1234`; frozen contracts unchanged; protected/execution paths untouched.
"""
    items = _parse_queue_items(fixture)

    assert _done_evidence_is_complete(items["ITEM-A"]) is False


def test_done_queue_item_with_explicit_non_blocking_rationale_is_accepted() -> None:
    fixture = """
### ITEM-A - Completed Item With Non Blocking Rationale

- queue id: `ITEM-A`
- status: `done`
- completion evidence: PR #1, merge SHA `abc1234`; post-merge absence recorded as non-blocking; frozen contracts unchanged; protected/execution paths untouched.
"""
    items = _parse_queue_items(fixture)

    assert _done_evidence_is_complete(items["ITEM-A"]) is True


def test_deferred_and_operator_review_items_are_not_auto_selected() -> None:
    fixture = """
### ITEM-A - Completed Item

- queue id: `ITEM-A`
- status: `done`
- completion evidence: PR #1, merge SHA `abc1234`; checks green; frozen contracts unchanged; protected/execution paths untouched.

### ITEM-B - Deferred Item

- queue id: `ITEM-B`
- status: `deferred unless ITEM-A done and no operator gate exists`
- depends on: `ITEM-A done`

### ITEM-C - Operator Review Item

- queue id: `ITEM-C`
- status: `operator_review`
- depends on: `ITEM-A done`

### ITEM-D - Ready Item

- queue id: `ITEM-D`
- status: `ready`
- depends on: `ITEM-A done`
"""
    items = _parse_queue_items(fixture)

    assert _auto_selectable_status(items["ITEM-B"]) is False
    assert _auto_selectable_status(items["ITEM-C"]) is False
    assert _next_eligible_ready_item(items) == items["ITEM-D"]


def test_stale_historical_ready_item_does_not_override_new_dependency_chain() -> None:
    fixture = """
### ITEM-A - Old Ready Item

- queue id: `ITEM-A`
- status: `ready`

### ITEM-B - Later Completed Item

- queue id: `ITEM-B`
- status: `done`
- completion evidence: PR #1, merge SHA `abc1234`; checks green; frozen contracts unchanged; protected/execution paths untouched.

### ITEM-C - New Ready Item

- queue id: `ITEM-C`
- status: `ready`
- depends on: `ITEM-B done`
"""
    items = _parse_queue_items(fixture)

    assert _stale_historical_ready_items(items) == ("ITEM-A",)
    assert _next_eligible_ready_item(items) == items["ITEM-C"]
