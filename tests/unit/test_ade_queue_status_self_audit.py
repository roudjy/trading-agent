from __future__ import annotations

import json
import textwrap
from pathlib import Path

from reporting import ade_queue_status_self_audit as audit


def _write_queue(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(textwrap.dedent(text).strip() + "\n", encoding="utf-8")
    return path


def test_fixture_selects_single_non_stale_ready_item(tmp_path: Path) -> None:
    queue_path = _write_queue(
        tmp_path / "docs" / "governance" / "queue.md",
        """
### ITEM-A - Historical Ready

- queue id: `ITEM-A`
- status: `ready`

### ITEM-B - Done Item

- queue id: `ITEM-B`
- status: `done`
- completion evidence: PR #1, merge SHA `abc1234`; checks green; frozen contracts unchanged; protected/execution paths untouched.

### ITEM-C - Current Ready

- queue id: `ITEM-C`
- status: `ready`
- depends on: `ITEM-B done`

### ITEM-D - Blocked Next

- queue id: `ITEM-D`
- status: `blocked until ITEM-C done`
- depends on: `ITEM-C done`
""",
    )

    snap = audit.collect_snapshot(
        queue_doc_path=queue_path,
        frozen_utc="2026-05-27T00:00:00Z",
    )

    assert snap["summary"]["stale_historical_ready_items"] == ["ITEM-A"]
    assert snap["summary"]["eligible_ready_items"] == ["ITEM-C"]
    assert snap["summary"]["next_eligible_ready_item"] == "ITEM-C"
    assert snap["final_recommendation"] == "queue_status_audit_passed"


def test_missing_done_evidence_is_flagged(tmp_path: Path) -> None:
    queue_path = _write_queue(
        tmp_path / "queue.md",
        """
### ITEM-A - Incomplete Done Item

- queue id: `ITEM-A`
- status: `done`
- completion evidence: PR #1; checks green; protected/execution paths untouched.
""",
    )

    snap = audit.collect_snapshot(
        queue_doc_path=queue_path,
        frozen_utc="2026-05-27T00:00:00Z",
    )
    row = snap["items"][0]

    assert snap["summary"]["missing_done_evidence_items"] == ["ITEM-A"]
    assert row["done_evidence"]["complete"] is False
    assert row["done_evidence"]["missing"] == [
        "merge_sha",
        "frozen_contracts",
    ]


def test_blocked_and_deferred_reason_gaps_are_explicit(tmp_path: Path) -> None:
    queue_path = _write_queue(
        tmp_path / "queue.md",
        """
### ITEM-A - Done Item

- queue id: `ITEM-A`
- status: `done`
- completion evidence: PR #1, merge SHA `abc1234`; checks green; frozen contracts unchanged; protected/execution paths untouched.

### ITEM-B - Blocked Without Reason

- queue id: `ITEM-B`
- status: `blocked`
- depends on: `ITEM-A done`

### ITEM-C - Deferred Without Reason

- queue id: `ITEM-C`
- status: `deferred`
- depends on: `ITEM-A done`
""",
    )

    snap = audit.collect_snapshot(
        queue_doc_path=queue_path,
        frozen_utc="2026-05-27T00:00:00Z",
    )

    assert snap["summary"]["blocked_items_missing_reason"] == ["ITEM-B"]
    assert snap["summary"]["deferred_items_missing_reason"] == ["ITEM-C"]
    assert snap["final_recommendation"] == (
        "operator_review_required_queue_selection_ambiguous"
    )


def test_current_queue_selects_016d_after_016c_done() -> None:
    snap = audit.collect_snapshot(frozen_utc="2026-05-27T00:00:00Z")
    rows = {row["queue_item"]: row for row in snap["items"]}

    assert snap["summary"]["next_eligible_ready_item"] == "ADE-QRE-016D"
    assert "ADE-QRE-011" in snap["summary"]["stale_historical_ready_items"]
    assert rows["ADE-QRE-014N"]["status"] == "done"
    assert rows["ADE-QRE-014N"]["done_evidence"]["complete"] is True
    assert rows["ADE-QRE-014O"]["status"] == "done"
    assert rows["ADE-QRE-014O"]["done_evidence"]["complete"] is True
    assert rows["ADE-QRE-015A"]["status"] == "done"
    assert rows["ADE-QRE-015A"]["done_evidence"]["complete"] is True
    assert rows["ADE-QRE-015B"]["status"] == "done"
    assert rows["ADE-QRE-015B"]["done_evidence"]["complete"] is True
    assert rows["ADE-QRE-015C"]["status"] == "done"
    assert rows["ADE-QRE-015C"]["done_evidence"]["complete"] is True
    assert rows["ADE-QRE-015D"]["auto_selectable"] is False
    assert rows["ADE-QRE-015E"]["status"] == "done"
    assert rows["ADE-QRE-015E"]["done_evidence"]["complete"] is True
    assert rows["ADE-QRE-015E"]["auto_selectable"] is False
    assert rows["ADE-QRE-015F"]["auto_selectable"] is False
    assert rows["ADE-QRE-015G"]["auto_selectable"] is False
    assert rows["ADE-QRE-015H"]["status"] == "done"
    assert rows["ADE-QRE-015H"]["done_evidence"]["complete"] is True
    assert rows["ADE-QRE-015H"]["auto_selectable"] is False
    assert rows["ADE-QRE-016A"]["status"] == "done"
    assert rows["ADE-QRE-016A"]["done_evidence"]["complete"] is True
    assert rows["ADE-QRE-016A"]["auto_selectable"] is False
    assert rows["ADE-QRE-016B"]["status"] == "done"
    assert rows["ADE-QRE-016B"]["done_evidence"]["complete"] is True
    assert rows["ADE-QRE-016B"]["auto_selectable"] is False
    assert rows["ADE-QRE-016C"]["status"] == "done"
    assert rows["ADE-QRE-016C"]["done_evidence"]["complete"] is True
    assert rows["ADE-QRE-016C"]["auto_selectable"] is False
    assert rows["ADE-QRE-016D"]["status"] == "ready"
    assert rows["ADE-QRE-016D"]["auto_selectable"] is True
    assert rows["ADE-QRE-016E"]["status"] == "blocked until ADE-QRE-016D done"
    assert rows["ADE-QRE-016E"]["auto_selectable"] is False
    assert rows["ADE-QRE-016F"]["status"] == "blocked until ADE-QRE-016E done"
    assert rows["ADE-QRE-016F"]["auto_selectable"] is False
    assert rows["ADE-QRE-016G"]["status"] == "blocked until ADE-QRE-016F done"
    assert rows["ADE-QRE-016G"]["auto_selectable"] is False
    assert rows["ADE-QRE-016H"]["status"] == "blocked until ADE-QRE-016G done"
    assert rows["ADE-QRE-016H"]["auto_selectable"] is False
    assert snap["safety_invariants"]["adds_approval_mutation"] is False
    assert snap["safety_invariants"]["expands_autonomous_authority"] is False
    assert snap["safety_invariants"]["strategy_synthesis_enabled"] is False


def test_write_outputs_stays_under_audit_log_allowlist(tmp_path: Path) -> None:
    artifact_dir = tmp_path / "logs" / "ade_queue_status_self_audit"
    snap = audit.collect_snapshot(
        queue_doc_path=tmp_path / "missing.md",
        frozen_utc="2026-05-27T00:00:00Z",
    )

    paths = audit.write_outputs(snap, artifact_dir=artifact_dir)

    latest = artifact_dir / "latest.json"
    assert paths["latest"].endswith("logs/ade_queue_status_self_audit/latest.json")
    assert json.loads(latest.read_text(encoding="utf-8"))["report_kind"] == (
        "ade_queue_status_self_audit"
    )


def test_module_does_not_import_or_enable_mutation_surfaces() -> None:
    source = Path(audit.__file__).read_text(encoding="utf-8")

    forbidden_tokens = (
        "subprocess",
        "from dashboard",
        "import dashboard",
        "from execution",
        "import execution",
        "from registry",
        "import registry",
        "strategies.py",
        "approval mutation",
    )
    for token in forbidden_tokens:
        assert token not in source
