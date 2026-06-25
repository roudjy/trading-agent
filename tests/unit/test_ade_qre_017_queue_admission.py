from __future__ import annotations

from pathlib import Path

from reporting import ade_queue_status_self_audit as audit


QUEUE_DOC = Path("docs/governance/ade_queue_001_post_package_qre_ade_work_queue.md")

EXPECTED_IDS = (
    "ADE-QRE-017",
    "ADE-QRE-017A",
    "ADE-QRE-017B",
    "ADE-QRE-017C",
    "ADE-QRE-017D",
    "ADE-QRE-017E",
    "ADE-QRE-017F",
    "ADE-QRE-017G",
    "ADE-QRE-017H",
    "ADE-QRE-017I",
    "ADE-QRE-017J",
    "ADE-QRE-017K",
    "ADE-QRE-017L",
    "ADE-QRE-017M",
    "ADE-QRE-017N",
    "ADE-QRE-017O",
    "ADE-QRE-017P",
    "ADE-QRE-017Q",
    "ADE-QRE-017R",
    "ADE-QRE-017S",
    "ADE-QRE-017T",
    "ADE-QRE-017U",
    "ADE-QRE-017V",
    "ADE-QRE-017W",
    "ADE-QRE-017X",
    "ADE-QRE-017Y",
    "ADE-QRE-017Z",
    "ADE-QRE-017AA",
    "ADE-QRE-017AB",
    "ADE-QRE-017AC",
    "ADE-QRE-017AD",
)

VALID_STATUS_PREFIXES = (
    "done",
    "ready",
    "blocked until ",
    "deferred ",
    "operator_review",
)


def _items() -> dict[str, audit.QueueItem]:
    return audit.parse_queue_items(QUEUE_DOC.read_text(encoding="utf-8"))


def test_all_ade_qre_017_queue_items_are_present_once() -> None:
    items = _items()

    for item_id in EXPECTED_IDS:
        assert item_id in items

    assert len({item_id for item_id in EXPECTED_IDS}) == len(EXPECTED_IDS)


def test_ade_qre_017_statuses_use_supported_queue_vocabulary() -> None:
    items = _items()

    for item_id in EXPECTED_IDS:
        status = items[item_id].status
        assert any(
            status == prefix or status.startswith(prefix)
            for prefix in VALID_STATUS_PREFIXES
        ), (item_id, status)


def test_ade_qre_017_dependencies_reference_existing_queue_items() -> None:
    items = _items()
    known = set(items)

    for item_id in EXPECTED_IDS:
        for dep in items[item_id].dependencies:
            assert dep in known, (item_id, dep)


def test_ade_qre_017_chain_selects_017a_as_next_eligible_ready_item() -> None:
    snap = audit.collect_snapshot(frozen_utc="2026-06-25T00:00:00Z")
    rows = {row["queue_item"]: row for row in snap["items"]}

    assert snap["summary"]["next_eligible_ready_item"] == "ADE-QRE-017A"
    assert rows["ADE-QRE-017"]["status"].startswith("blocked until ADE-QRE-017AD done")
    assert rows["ADE-QRE-017A"]["status"] == "ready"
    assert rows["ADE-QRE-017B"]["status"].startswith("blocked until ADE-QRE-017A done")
    assert rows["ADE-QRE-017Y"]["status"].startswith("blocked until ADE-QRE-017X done")
    assert rows["ADE-QRE-017AD"]["status"].startswith("blocked until ADE-QRE-017AC done")


def test_ade_qre_017_queue_keeps_synthesis_blocked_and_protected_scope_explicit() -> None:
    text = QUEUE_DOC.read_text(encoding="utf-8")

    assert "synthesis implementation" in text
    assert ".claude/**" in text
    assert "research/research_latest.json" in text
    assert "research/strategy_matrix.csv" in text
    assert "live/**" in text
    assert "paper/**" in text
    assert "shadow/**" in text
