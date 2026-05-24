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
            status=status_match.group(1),
            body=body,
            dependencies=dependencies,
        )
    return items


def _done_evidence_is_complete(item: QueueItem) -> bool:
    text = item.body.lower()
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

    assert item_a.status == "done"
    assert _done_evidence_is_complete(item_a)
    assert item_b.status == "done"
    assert _done_evidence_is_complete(item_b)

    assert item_c.status == "ready"
    assert item_c.dependencies == ("ADE-QRE-014B",)
    assert _dependencies_done(item_c, items) is True

    assert item_d.status == "blocked until ADE-QRE-014C done"
    assert item_d.dependencies == ("ADE-QRE-014C",)
    assert _dependencies_done(item_d, items) is False


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
