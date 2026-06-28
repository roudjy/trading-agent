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
_FINAL_REVIEW_DOC = (
    Path(__file__).resolve().parents[2]
    / "docs"
    / "governance"
    / "ade_qre_014o_final_trusted_loop_queue_readiness_review.md"
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


def test_ade_qre_active_queue_lifecycle_is_consistent() -> None:
    """Pin the active ADE-QRE done -> ready -> blocked lifecycle.

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
    item_i = items["ADE-QRE-014I"]
    item_j = items["ADE-QRE-014J"]
    item_k = items["ADE-QRE-014K"]
    item_l = items["ADE-QRE-014L"]
    item_m = items["ADE-QRE-014M"]
    item_n = items["ADE-QRE-014N"]
    item_o = items["ADE-QRE-014O"]
    item_15a = items["ADE-QRE-015A"]
    item_15b = items["ADE-QRE-015B"]
    item_15c = items["ADE-QRE-015C"]
    item_15d = items["ADE-QRE-015D"]
    item_15e = items["ADE-QRE-015E"]
    item_15f = items["ADE-QRE-015F"]
    item_15g = items["ADE-QRE-015G"]
    item_15h = items["ADE-QRE-015H"]
    item_16a = items["ADE-QRE-016A"]
    item_16b = items["ADE-QRE-016B"]
    item_16c = items["ADE-QRE-016C"]
    item_16d = items["ADE-QRE-016D"]
    item_16e = items["ADE-QRE-016E"]
    item_16f = items["ADE-QRE-016F"]
    item_16g = items["ADE-QRE-016G"]
    item_16h = items["ADE-QRE-016H"]
    item_17 = items["ADE-QRE-017"]
    item_17a = items["ADE-QRE-017A"]
    item_17b = items["ADE-QRE-017B"]
    item_17c = items["ADE-QRE-017C"]
    item_17y = items["ADE-QRE-017Y"]
    item_17ad = items["ADE-QRE-017AD"]

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

    item_f = items["ADE-QRE-014F"]
    assert item_f.status.startswith("deferred")
    assert _auto_selectable_status(item_f) is False

    assert item_g.status == "done"
    assert _done_evidence_is_complete(item_g)
    assert item_g.dependencies == ("ADE-QRE-014E",)
    assert _dependencies_done(item_g, items) is True
    assert _auto_selectable_status(item_g) is False

    assert item_h.status == "done"
    assert _done_evidence_is_complete(item_h)
    assert item_h.dependencies == ("ADE-QRE-014G",)
    assert _dependencies_done(item_h, items) is True
    assert _auto_selectable_status(item_h) is False

    assert item_i.status == "done"
    assert _done_evidence_is_complete(item_i)
    assert item_i.dependencies == ("ADE-QRE-014H",)
    assert _dependencies_done(item_i, items) is True
    assert _auto_selectable_status(item_i) is False

    assert item_j.status == "done"
    assert _done_evidence_is_complete(item_j)
    assert item_j.dependencies == ("ADE-QRE-014I",)
    assert _dependencies_done(item_j, items) is True
    assert _auto_selectable_status(item_j) is False

    assert item_k.status == "done"
    assert _done_evidence_is_complete(item_k)
    assert item_k.dependencies == ("ADE-QRE-014J",)
    assert _dependencies_done(item_k, items) is True
    assert _auto_selectable_status(item_k) is False

    assert item_l.status == "done"
    assert _done_evidence_is_complete(item_l)
    assert item_l.dependencies == ("ADE-QRE-014K",)
    assert _dependencies_done(item_l, items) is True
    assert _auto_selectable_status(item_l) is False

    assert item_m.status == "done"
    assert _done_evidence_is_complete(item_m)
    assert item_m.dependencies == ("ADE-QRE-014L",)
    assert _dependencies_done(item_m, items) is True
    assert _auto_selectable_status(item_m) is False

    assert item_n.status == "done"
    assert _done_evidence_is_complete(item_n)
    assert item_n.dependencies == ("ADE-QRE-014M",)
    assert _dependencies_done(item_n, items) is True
    assert _auto_selectable_status(item_n) is False

    assert item_o.status == "done"
    assert _done_evidence_is_complete(item_o)
    assert item_o.dependencies == ("ADE-QRE-014N",)
    assert _dependencies_done(item_o, items) is True
    assert _auto_selectable_status(item_o) is False

    assert item_15a.status == "done"
    assert _done_evidence_is_complete(item_15a)
    assert item_15a.dependencies == ("ADE-QRE-014O",)
    assert _dependencies_done(item_15a, items) is True
    assert _auto_selectable_status(item_15a) is False

    assert item_15b.status == "done"
    assert _done_evidence_is_complete(item_15b)
    assert item_15b.dependencies == ("ADE-QRE-015A",)
    assert _dependencies_done(item_15b, items) is True
    assert _auto_selectable_status(item_15b) is False

    assert item_15c.status == "done"
    assert _done_evidence_is_complete(item_15c)
    assert item_15c.dependencies == ("ADE-QRE-015B",)
    assert _dependencies_done(item_15c, items) is True
    assert _auto_selectable_status(item_15c) is False

    assert item_15d.status.startswith("blocked until ADE-QRE-015C done")
    assert _auto_selectable_status(item_15d) is False
    assert item_15e.status == "done"
    assert _done_evidence_is_complete(item_15e)
    assert item_15e.dependencies == ("ADE-QRE-015C",)
    assert _dependencies_done(item_15e, items) is True
    assert _auto_selectable_status(item_15e) is False
    assert item_15f.status.startswith("blocked until ADE-QRE-015C done")
    assert _auto_selectable_status(item_15f) is False
    assert item_15g.status.startswith("blocked until ADE-QRE-015C done")
    assert _auto_selectable_status(item_15g) is False
    assert item_15h.status == "done"
    assert _done_evidence_is_complete(item_15h)
    assert item_15h.dependencies == ("ADE-QRE-015E",)
    assert _dependencies_done(item_15h, items) is True
    assert _auto_selectable_status(item_15h) is False

    assert item_16a.status == "done"
    assert item_16a.dependencies == ("ADE-QRE-015H",)
    assert _dependencies_done(item_16a, items) is True
    assert _done_evidence_is_complete(item_16a)
    assert _auto_selectable_status(item_16a) is False
    assert item_16b.status == "done"
    assert item_16b.dependencies == ("ADE-QRE-016A",)
    assert _dependencies_done(item_16b, items) is True
    assert _done_evidence_is_complete(item_16b)
    assert _auto_selectable_status(item_16b) is False
    assert item_16c.status == "done"
    assert item_16c.dependencies == ("ADE-QRE-016B",)
    assert _dependencies_done(item_16c, items) is True
    assert _done_evidence_is_complete(item_16c)
    assert _auto_selectable_status(item_16c) is False
    assert item_16d.status == "done"
    assert item_16d.dependencies == ("ADE-QRE-016C",)
    assert _dependencies_done(item_16d, items) is True
    assert _done_evidence_is_complete(item_16d)
    assert _auto_selectable_status(item_16d) is False
    assert item_16e.status == "done"
    assert item_16e.dependencies == ("ADE-QRE-016D",)
    assert _dependencies_done(item_16e, items) is True
    assert _done_evidence_is_complete(item_16e)
    assert _auto_selectable_status(item_16e) is False
    assert item_16f.status == "done"
    assert item_16f.dependencies == ("ADE-QRE-016E",)
    assert _dependencies_done(item_16f, items) is True
    assert _done_evidence_is_complete(item_16f)
    assert _auto_selectable_status(item_16f) is False
    assert item_16g.status == "done"
    assert item_16g.dependencies == ("ADE-QRE-016F",)
    assert _dependencies_done(item_16g, items) is True
    assert _done_evidence_is_complete(item_16g)
    assert _auto_selectable_status(item_16g) is False
    assert item_16h.status == "done"
    assert item_16h.dependencies == ("ADE-QRE-016G",)
    assert _dependencies_done(item_16h, items) is True
    assert _done_evidence_is_complete(item_16h)
    assert _auto_selectable_status(item_16h) is False
    assert _stale_historical_ready_items(items) == ("ADE-QRE-011",)
    assert item_17.status == "blocked until ADE-QRE-017AD done"
    assert item_17.dependencies == ("ADE-QRE-016H",)
    assert _dependencies_done(item_17, items) is True
    assert _auto_selectable_status(item_17) is False
    assert item_17a.status == "done"
    assert item_17a.dependencies == ("ADE-QRE-016H",)
    assert _dependencies_done(item_17a, items) is True
    assert _auto_selectable_status(item_17a) is False
    assert item_17b.status == "done"
    assert item_17b.dependencies == ("ADE-QRE-017A",)
    assert _dependencies_done(item_17b, items) is True
    assert _auto_selectable_status(item_17b) is False
    assert item_17c.status == "done"
    assert item_17c.dependencies == ("ADE-QRE-017B",)
    assert _dependencies_done(item_17c, items) is True
    item_17d = items["ADE-QRE-017D"]
    assert item_17d.status == "done"
    item_17e = items["ADE-QRE-017E"]
    assert item_17e.status == "done"
    assert _done_evidence_is_complete(item_17e) is True
    item_17f = items["ADE-QRE-017F"]
    assert item_17f.status == "done"
    assert _done_evidence_is_complete(item_17f) is True
    item_17g = items["ADE-QRE-017G"]
    assert item_17g.status == "done"
    assert _done_evidence_is_complete(item_17g) is True
    item_17h = items["ADE-QRE-017H"]
    item_17i = items["ADE-QRE-017I"]
    item_17j = items["ADE-QRE-017J"]
    item_17k = items["ADE-QRE-017K"]
    item_17l = items["ADE-QRE-017L"]
    item_17m = items["ADE-QRE-017M"]
    item_17n = items["ADE-QRE-017N"]
    item_17o = items["ADE-QRE-017O"]
    assert item_17h.status == "done"
    assert _done_evidence_is_complete(item_17h)
    assert item_17i.status == "done"
    assert _done_evidence_is_complete(item_17i)
    assert item_17j.status == "done"
    assert _done_evidence_is_complete(item_17j)
    assert item_17k.status == "done"
    assert _done_evidence_is_complete(item_17k)
    assert item_17l.status == "done"
    assert _done_evidence_is_complete(item_17l)
    assert item_17m.status == "done"
    assert _done_evidence_is_complete(item_17m)
    assert item_17n.status == "done"
    assert _done_evidence_is_complete(item_17n)
    assert item_17o.status == "done"
    assert _done_evidence_is_complete(item_17o)
    item_17p = items["ADE-QRE-017P"]
    item_17q = items["ADE-QRE-017Q"]
    item_17r = items["ADE-QRE-017R"]
    item_17s = items["ADE-QRE-017S"]
    item_17t = items["ADE-QRE-017T"]
    assert item_17p.status == "done"
    assert _done_evidence_is_complete(item_17p)
    assert item_17q.status == "done"
    assert _done_evidence_is_complete(item_17q)
    assert item_17r.status == "done"
    assert _done_evidence_is_complete(item_17r)
    assert item_17s.status == "done"
    assert _done_evidence_is_complete(item_17s)
    assert item_17t.status == "done"
    assert _done_evidence_is_complete(item_17t)
    assert items["ADE-QRE-017X"].status == "done"
    assert _done_evidence_is_complete(items["ADE-QRE-017X"])
    assert item_17y.status == "done"
    assert _done_evidence_is_complete(item_17y)
    assert items["ADE-QRE-017Z"].status == "done"
    assert _done_evidence_is_complete(items["ADE-QRE-017Z"])
    assert items["ADE-QRE-017AA"].status == "ready"
    assert item_17ad.status == "blocked until ADE-QRE-017AC done"
    assert items["ADE-QRE-017U"].status == "done"
    assert items["ADE-QRE-017V"].status == "done"
    assert items["ADE-QRE-017W"].status == "done"
    assert _done_evidence_is_complete(items["ADE-QRE-017W"])
    assert _next_eligible_ready_item(items) == items["ADE-QRE-017AA"]


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


def test_ade_qre_014o_review_selects_one_allowed_next_direction() -> None:
    text = _FINAL_REVIEW_DOC.read_text(encoding="utf-8")

    allowed_directions = (
        "continue trusted-loop maturity sprint",
        "return to QRE Feature Build Track",
        "operator review required",
        "no eligible work remains",
    )
    selected_lines = [
        line.strip()
        for line in text.splitlines()
        if line.startswith("Selected next direction:")
    ]

    assert selected_lines == [
        "Selected next direction: **continue trusted-loop maturity sprint**."
    ]
    assert sum(direction in selected_lines[0] for direction in allowed_directions) == 1
    assert "`return to QRE Feature Build Track` is not selected" in text
    assert "`operator review required` is not selected" in text
    assert "`no eligible work remains` is not selected" in text
    assert "Strategy synthesis remains blocked." in text
    assert "Addendum 4 remains `DEFERRED / REFERENCE-ONLY`." in text
