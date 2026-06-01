from __future__ import annotations

import json
from pathlib import Path

import pytest

from reporting import qre_research_action_consumer_gate as gate


def _write_queue(path: Path, *, items: list[dict]) -> Path:
    path.write_text(
        json.dumps(
            {
                "schema_version": "research_action_queue.v1",
                "run_id": "run-qre",
                "preset": "trend_pullback_equities_4h",
                "item_count": len(items),
                "items": items,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    return path


def _item(**overrides):
    base = {
        "action_id": "inspect_paper_engine_divergence",
        "source_section": "no_paper_candidate_next_action_plan",
        "target_candidate_id": "strategy|HD|4h|{}",
        "priority": "high",
        "status": "pending",
        "outcome_status": "not_recorded",
        "operator_approval_required": False,
        "forbidden_actions": [],
        "reason_codes": ["paper_engine_divergence_pending"],
        "bounded_next_step": "Inspect paper engine divergence before strategy changes.",
    }
    base.update(overrides)
    return base


def test_eligible_item_is_ready_for_ade_proposal_intake(tmp_path: Path) -> None:
    source = _write_queue(tmp_path / "queue.json", items=[_item()])

    snap = gate.collect_snapshot(source_path=source, frozen_utc="2026-06-01T12:00:00Z")

    assert snap["final_recommendation"] == "ready_for_ade_proposal_intake"
    assert snap["safe_to_execute"] is False
    assert snap["writes_ade_queue"] is False
    assert snap["writes_proposal_queue"] is False
    assert snap["mutates_campaign_queue"] is False
    assert snap["mutates_strategy_or_preset"] is False
    assert snap["mutates_paper_shadow_live_runtime"] is False
    assert snap["counts"] == {
        "eligible_for_ade_proposal_intake": 1,
        "operator_approval_required": 0,
        "blocked": 0,
    }
    row = snap["rows"][0]
    assert row["verdict"] == "eligible_for_ade_proposal_intake"
    assert row["eligible_for_ade_proposal_intake"] is True
    assert row["eligible_for_direct_execution"] is False
    assert row["safe_to_execute"] is False


def test_operator_required_item_remains_operator_gated(tmp_path: Path) -> None:
    source = _write_queue(
        tmp_path / "queue.json",
        items=[_item(operator_approval_required=True)],
    )

    snap = gate.collect_snapshot(source_path=source, frozen_utc="2026-06-01T12:00:00Z")

    assert snap["final_recommendation"] == "operator_review_required"
    assert snap["counts"]["operator_approval_required"] == 1
    assert snap["rows"][0]["verdict"] == "operator_approval_required"
    assert snap["rows"][0]["eligible_for_ade_proposal_intake"] is False


def test_forbidden_action_blocks_item(tmp_path: Path) -> None:
    source = _write_queue(
        tmp_path / "queue.json",
        items=[_item(forbidden_actions=["automatic_campaign_queue_mutation"])],
    )

    snap = gate.collect_snapshot(source_path=source, frozen_utc="2026-06-01T12:00:00Z")

    assert snap["final_recommendation"] == "operator_review_required_blocked_items_present"
    assert snap["counts"]["blocked"] == 1
    row = snap["rows"][0]
    assert row["verdict"] == "blocked"
    assert row["reason"] == "forbidden_action_present"
    assert row["forbidden_action_hits"] == ["automatic_campaign_queue_mutation"]


def test_non_pending_item_blocks(tmp_path: Path) -> None:
    source = _write_queue(tmp_path / "queue.json", items=[_item(status="completed")])

    snap = gate.collect_snapshot(source_path=source, frozen_utc="2026-06-01T12:00:00Z")

    assert snap["counts"]["blocked"] == 1
    assert "item_status_not_pending" in snap["rows"][0]["blocked_reasons"]


def test_missing_source_fails_closed(tmp_path: Path) -> None:
    snap = gate.collect_snapshot(
        source_path=tmp_path / "missing.json",
        frozen_utc="2026-06-01T12:00:00Z",
    )

    assert snap["final_recommendation"] == "no_source_queue_available"
    assert snap["rows"] == []
    assert snap["safe_to_execute"] is False


def test_unsupported_schema_blocks(tmp_path: Path) -> None:
    source = tmp_path / "queue.json"
    source.write_text(
        json.dumps({"schema_version": "other.v1", "items": [_item()]}),
        encoding="utf-8",
    )

    snap = gate.collect_snapshot(source_path=source, frozen_utc="2026-06-01T12:00:00Z")

    assert snap["final_recommendation"] == "blocked_unsupported_source_schema"
    assert snap["rows"] == []


def test_write_outputs_refuses_outside_artifact_dir(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        gate._atomic_write_json(tmp_path / "latest.json", {"x": 1})  # pyright: ignore[reportPrivateUsage]


def test_write_outputs_writes_latest(monkeypatch, tmp_path: Path) -> None:
    artifact_dir = tmp_path / "logs" / "qre_research_action_consumer_gate"
    latest = artifact_dir / "latest.json"
    monkeypatch.setattr(gate, "ARTIFACT_DIR", artifact_dir)
    monkeypatch.setattr(gate, "ARTIFACT_LATEST", latest)

    out = gate.write_outputs({"schema_version": 1, "rows": []})

    assert out == latest
    assert json.loads(latest.read_text(encoding="utf-8"))["schema_version"] == 1


def test_module_does_not_import_research_or_execution_paths() -> None:
    text = Path(gate.__file__).read_text(encoding="utf-8")
    forbidden = [
        "import research",
        "from research",
        "import broker",
        "from broker",
        "import execution",
        "from execution",
        "subprocess",
        "git ",
        "gh ",
    ]
    assert not any(token in text for token in forbidden)
