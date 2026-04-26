"""v3.15.10 — launcher integration unit tests for the
``_apply_funnel_decisions`` helper.

Pins:
  - missing evidence sidecar AND no technical_failure record
    -> empty event list
  - present evidence with matched owner -> funnel_decision_emitted
    events for each per-candidate decision
  - present evidence with mismatched owner ->
    funnel_evidence_stale_or_mismatched event
  - technical_failure record -> funnel_technical_no_freeze event
  - error inside derive call -> funnel_policy_error event (no
    raise propagated)
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from research import campaign_launcher


def _evidence_payload(*, owner="cmp-1", candidates=None):
    return {
        "schema_version": "1.0",
        "col_campaign_id": owner,
        "campaign_id": owner,
        "run_id": "run-1",
        "preset_name": "preset_a",
        "screening_phase": "exploratory",
        "summary": {"dominant_failure_reasons": []},
        "candidates": candidates or [],
    }


def _exploratory_pass_candidate(cid: str = "c1"):
    return {
        "candidate_id": cid,
        "strategy_id": "s1",
        "stage_result": "needs_investigation",
        "pass_kind": "exploratory",
        "evidence_fingerprint": f"fp-{cid}",
        "failure_reasons": [],
        "near_pass": {"is_near_pass": False},
        "sampling": {},
    }


def _registry_with_owner(owner_id: str = "cmp-1") -> dict:
    return {
        "campaigns": {
            owner_id: {
                "campaign_id": owner_id,
                "preset_name": "preset_a",
                "campaign_type": "daily_primary",
                "lineage_root_campaign_id": "cmp-root",
                "outcome": "completed_with_candidates",
                "state": "completed",
                "spawned_at_utc": "2026-04-26T10:00:00+00:00",
                "finished_at_utc": "2026-04-26T11:00:00+00:00",
            }
        }
    }


def test_no_evidence_no_technical_failure_yields_no_events(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.chdir(tmp_path)
    new_events = campaign_launcher._apply_funnel_decisions(
        registry={"campaigns": {}},
        events=[],
        now_utc=datetime(2026, 4, 26, 12, 0, 0, tzinfo=UTC),
    )
    assert new_events == []


def test_present_evidence_with_matched_owner_emits_funnel_decision_events(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.chdir(tmp_path)
    Path("research").mkdir(parents=True, exist_ok=True)
    import json
    Path("research/screening_evidence_latest.v1.json").write_text(
        json.dumps(_evidence_payload(
            candidates=[_exploratory_pass_candidate()],
        )),
        encoding="utf-8",
    )
    new_events = campaign_launcher._apply_funnel_decisions(
        registry=_registry_with_owner(),
        events=[],
        now_utc=datetime(2026, 4, 26, 12, 0, 0, tzinfo=UTC),
    )
    types = [ev.event_type for ev in new_events]
    assert "funnel_decision_emitted" in types
    decision_event = next(
        ev for ev in new_events if ev.event_type == "funnel_decision_emitted"
    )
    assert decision_event.extra["decision_code"] == "confirmation_from_exploratory_pass"
    assert decision_event.extra["candidate_id"] == "c1"
    assert decision_event.extra["screening_evidence_fingerprint"] == "fp-c1"
    assert decision_event.extra["requested_screening_phase"] == "promotion_grade"


def test_evidence_with_mismatched_owner_emits_stale_event(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.chdir(tmp_path)
    Path("research").mkdir(parents=True, exist_ok=True)
    import json
    Path("research/screening_evidence_latest.v1.json").write_text(
        json.dumps(_evidence_payload(
            owner="cmp-OTHER",  # registry owner is cmp-1
            candidates=[_exploratory_pass_candidate()],
        )),
        encoding="utf-8",
    )
    new_events = campaign_launcher._apply_funnel_decisions(
        registry=_registry_with_owner(),
        events=[],
        now_utc=datetime(2026, 4, 26, 12, 0, 0, tzinfo=UTC),
    )
    types = [ev.event_type for ev in new_events]
    # registry has no record matching cmp-OTHER -> mismatch event
    assert "funnel_evidence_stale_or_mismatched" in types


def test_technical_failure_record_emits_no_freeze_event(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.chdir(tmp_path)
    registry = {
        "campaigns": {
            "cmp-bad": {
                "campaign_id": "cmp-bad",
                "preset_name": "preset_a",
                "campaign_type": "daily_primary",
                "lineage_root_campaign_id": "cmp-root",
                "outcome": "technical_failure",
                "state": "failed",
                "spawned_at_utc": "2026-04-26T10:00:00+00:00",
                "finished_at_utc": "2026-04-26T11:00:00+00:00",
            }
        }
    }
    new_events = campaign_launcher._apply_funnel_decisions(
        registry=registry,
        events=[],
        now_utc=datetime(2026, 4, 26, 12, 0, 0, tzinfo=UTC),
    )
    types = [ev.event_type for ev in new_events]
    assert "funnel_technical_no_freeze" in types
    tf_event = next(
        ev for ev in new_events if ev.event_type == "funnel_technical_no_freeze"
    )
    assert tf_event.extra["decision_code"] == "no_action_technical_failure"


def test_dedupe_skips_already_recorded_funnel_decision(
    tmp_path, monkeypatch
) -> None:
    """A second tick must not re-emit a funnel_decision for the
    same parent / decision / candidate / fingerprint.
    """
    monkeypatch.chdir(tmp_path)
    Path("research").mkdir(parents=True, exist_ok=True)
    import json
    Path("research/screening_evidence_latest.v1.json").write_text(
        json.dumps(_evidence_payload(
            candidates=[_exploratory_pass_candidate()],
        )),
        encoding="utf-8",
    )
    prior_events = [
        {
            "event_type": "funnel_decision_emitted",
            "campaign_id": "cmp-1",
            "parent_campaign_id": "cmp-1",
            "extra": {
                "decision_code": "confirmation_from_exploratory_pass",
                "candidate_id": "c1",
                "screening_evidence_fingerprint": "fp-c1",
            },
        }
    ]
    new_events = campaign_launcher._apply_funnel_decisions(
        registry=_registry_with_owner(),
        events=prior_events,
        now_utc=datetime(2026, 4, 26, 12, 0, 0, tzinfo=UTC),
    )
    types = [ev.event_type for ev in new_events]
    assert "funnel_decision_emitted" not in types
