"""v3.15.10 — pin pure funnel-policy decisions (REV 3 §7.3).

Covers all six decision codes plus the priority/sort
contract, the dedupe helper, and the no-alt-timeframe
fallback.
"""

from __future__ import annotations

from research.campaign_funnel_policy import (
    ACTIVE_CAMPAIGN_STATES,
    DECISION_PRIORITY,
    FUNNEL_DECISION_CONFIRMATION,
    FUNNEL_DECISION_COOLDOWN_REPEAT,
    FUNNEL_DECISION_COVERAGE_FOLLOWUP,
    FUNNEL_DECISION_NEAR_PASS_FOLLOWUP,
    FUNNEL_DECISION_NO_ACTION_TECHNICAL,
    FunnelDecision,
    REPEAT_REJECTION_STREAK_THRESHOLD,
    TERMINAL_CAMPAIGN_STATES,
    derive_funnel_decisions,
    has_alternate_timeframe_support,
    has_funnel_spawn_for,
    repeat_rejection_streak,
    sort_funnel_decisions,
)


def _evidence(
    *,
    candidates,
    col_campaign_id="cmp-1",
    preset="preset_a",
    summary=None,
):
    return {
        "schema_version": "1.0",
        "col_campaign_id": col_campaign_id,
        "campaign_id": col_campaign_id,
        "run_id": "run-1",
        "preset_name": preset,
        "screening_phase": "exploratory",
        "summary": summary or {"dominant_failure_reasons": []},
        "candidates": candidates,
    }


def _candidate(
    *,
    candidate_id="c1",
    strategy_id="s1",
    stage_result="screening_pass",
    pass_kind=None,
    failure_reasons=None,
    near_is_near=False,
    near_payload=None,
    sampling=None,
    fp="fp1",
):
    return {
        "candidate_id": candidate_id,
        "strategy_id": strategy_id,
        "stage_result": stage_result,
        "pass_kind": pass_kind,
        "evidence_fingerprint": fp,
        "failure_reasons": failure_reasons or [],
        "near_pass": {
            "is_near_pass": bool(near_is_near),
            "nearest_failed_criterion": (near_payload or {}).get("crit"),
            "distance": (near_payload or {}).get("distance"),
        },
        "sampling": sampling or {},
    }


def _parent(*, campaign_id="cmp-1", preset="preset_a", outcome=None):
    return {
        "campaign_id": campaign_id,
        "preset_name": preset,
        "lineage_root_campaign_id": "cmp-root",
        "outcome": outcome,
    }


def test_exploratory_pass_yields_confirmation_decision_with_spawn() -> None:
    decisions = derive_funnel_decisions(
        evidence=_evidence(candidates=[_candidate(
            stage_result="needs_investigation", pass_kind="exploratory",
        )]),
        expected_campaign_id="cmp-1",
        parent_campaign_record=_parent(),
        registry={"campaigns": {}},
        ledger_events=[], preset_catalog={},
    )
    assert len(decisions) == 1
    d = decisions[0]
    assert d.decision_code == FUNNEL_DECISION_CONFIRMATION
    assert d.spawn_request is not None
    assert d.spawn_request.campaign_type == "survivor_confirmation"
    assert d.spawn_request.spawn_reason == FUNNEL_DECISION_CONFIRMATION
    assert d.spawn_request.extra["lineage_candidate_id"] == "c1"
    assert d.spawn_request.extra["screening_evidence_fingerprint"] == "fp1"
    assert d.spawn_request.extra["requested_screening_phase"] == "promotion_grade"


def test_near_pass_yields_followup_decision_with_spawn_lower_priority() -> None:
    decisions = derive_funnel_decisions(
        evidence=_evidence(candidates=[_candidate(
            stage_result="near_pass",
            failure_reasons=["expectancy_not_positive"],
            near_is_near=True,
            near_payload={"crit": "expectancy_not_positive", "distance": 0.0001},
        )]),
        expected_campaign_id="cmp-1",
        parent_campaign_record=_parent(),
        registry={"campaigns": {}},
        ledger_events=[], preset_catalog={},
    )
    assert len(decisions) == 1
    d = decisions[0]
    assert d.decision_code == FUNNEL_DECISION_NEAR_PASS_FOLLOWUP
    assert d.spawn_request is not None
    # priority is the DECISION_PRIORITY constant (20), not the
    # SpawnRequest priority_tier.
    assert d.priority == DECISION_PRIORITY[FUNNEL_DECISION_NEAR_PASS_FOLLOWUP]
    # near-pass spawn does NOT carry requested_screening_phase
    assert "requested_screening_phase" not in d.spawn_request.extra
    assert d.spawn_request.extra["near_pass"]["distance"] == 0.0001


def test_insufficient_trades_yields_cooldown_with_alt_unavailable() -> None:
    decisions = derive_funnel_decisions(
        evidence=_evidence(candidates=[_candidate(
            stage_result="screening_reject",
            failure_reasons=["insufficient_trades"],
        )]),
        expected_campaign_id="cmp-1",
        parent_campaign_record=_parent(),
        registry={"campaigns": {}},
        ledger_events=[], preset_catalog={},
    )
    assert len(decisions) == 1
    d = decisions[0]
    assert d.decision_code == FUNNEL_DECISION_COOLDOWN_REPEAT
    assert d.spawn_request is None
    assert d.rationale["alternate_timeframe_unavailable"] is True
    assert d.rationale["dominant_reason"] == "insufficient_trades"


def test_low_coverage_yields_coverage_followup_no_spawn() -> None:
    decisions = derive_funnel_decisions(
        evidence=_evidence(candidates=[_candidate(
            stage_result="screening_reject",
            failure_reasons=["screening_criteria_not_met"],
            sampling={
                "grid_size": 12, "sampled_count": 8, "coverage_pct": 0.667,
                "sampling_policy": "stratified_small",
                "sampled_parameter_digest": "abc",
                "coverage_warning": "below_threshold_for_small_grid",
            },
        )]),
        expected_campaign_id="cmp-1",
        parent_campaign_record=_parent(),
        registry={"campaigns": {}},
        ledger_events=[], preset_catalog={},
    )
    codes = [d.decision_code for d in decisions]
    assert FUNNEL_DECISION_COVERAGE_FOLLOWUP in codes
    cov = next(d for d in decisions if d.decision_code == FUNNEL_DECISION_COVERAGE_FOLLOWUP)
    assert cov.spawn_request is None
    assert cov.rationale["sampling_defect_review_required"] is True


def test_grid_unavailable_also_triggers_coverage_followup() -> None:
    decisions = derive_funnel_decisions(
        evidence=_evidence(candidates=[_candidate(
            stage_result="screening_reject",
            failure_reasons=["screening_criteria_not_met"],
            sampling={
                "grid_size": None, "sampled_count": 1, "coverage_pct": None,
                "sampling_policy": "grid_size_unavailable",
                "sampled_parameter_digest": "",
                "coverage_warning": "grid_size_unavailable",
            },
        )]),
        expected_campaign_id="cmp-1",
        parent_campaign_record=_parent(),
        registry={"campaigns": {}},
        ledger_events=[], preset_catalog={},
    )
    cov = [d for d in decisions if d.decision_code == FUNNEL_DECISION_COVERAGE_FOLLOWUP]
    assert len(cov) == 1
    assert cov[0].rationale["grid_size_unavailable"] is True


def test_technical_failure_yields_no_action_without_evidence() -> None:
    """MF-13 — technical-failure decision derives from the
    registry record alone; works even when no evidence exists.
    """
    decisions = derive_funnel_decisions(
        evidence=None,
        expected_campaign_id=None,
        parent_campaign_record=None,
        registry={"campaigns": {}},
        ledger_events=[], preset_catalog={},
        technical_failure_record={
            "campaign_id": "cmp-bad", "preset_name": "preset_a",
            "outcome": "technical_failure",
        },
    )
    assert len(decisions) == 1
    d = decisions[0]
    assert d.decision_code == FUNNEL_DECISION_NO_ACTION_TECHNICAL
    assert d.spawn_request is None
    assert d.rationale["research_freeze_blocked"] is True


def test_repeat_rejection_streak_triggers_cooldown_at_threshold() -> None:
    base_event = {
        "preset_name": "preset_a",
        "event_type": "campaign_completed",
        "outcome": "research_rejection",
        "reason_code": "expectancy_not_positive",
    }
    events = [
        dict(base_event, at_utc=f"2026-04-{day:02d}T12:00:00+00:00")
        for day in (20, 21, 22)
    ]
    streak = repeat_rejection_streak(
        ledger_events=events,
        preset_name="preset_a",
        dominant_reason="expectancy_not_positive",
    )
    assert streak == REPEAT_REJECTION_STREAK_THRESHOLD


def test_streak_skips_technical_failure_and_degenerate() -> None:
    events = [
        {"preset_name": "p", "event_type": "campaign_completed",
         "outcome": "research_rejection", "reason_code": "x",
         "at_utc": "2026-04-20T00:00:00+00:00"},
        {"preset_name": "p", "event_type": "campaign_completed",
         "outcome": "technical_failure",
         "at_utc": "2026-04-21T00:00:00+00:00"},
        {"preset_name": "p", "event_type": "campaign_completed",
         "outcome": "degenerate_no_survivors",
         "at_utc": "2026-04-22T00:00:00+00:00"},
        {"preset_name": "p", "event_type": "campaign_completed",
         "outcome": "research_rejection", "reason_code": "x",
         "at_utc": "2026-04-23T00:00:00+00:00"},
        {"preset_name": "p", "event_type": "campaign_completed",
         "outcome": "research_rejection", "reason_code": "x",
         "at_utc": "2026-04-24T00:00:00+00:00"},
    ]
    streak = repeat_rejection_streak(
        ledger_events=events, preset_name="p", dominant_reason="x",
    )
    # 3 research_rejection events; technical_failure and
    # degenerate_no_survivors between them are skipped (neutral),
    # so the streak walks across them.
    assert streak == 3


def test_streak_breaks_on_other_outcome() -> None:
    events = [
        {"preset_name": "p", "event_type": "campaign_completed",
         "outcome": "research_rejection", "reason_code": "x",
         "at_utc": "2026-04-20T00:00:00+00:00"},
        {"preset_name": "p", "event_type": "campaign_completed",
         "outcome": "completed_with_candidates",
         "at_utc": "2026-04-21T00:00:00+00:00"},
        {"preset_name": "p", "event_type": "campaign_completed",
         "outcome": "research_rejection", "reason_code": "x",
         "at_utc": "2026-04-22T00:00:00+00:00"},
    ]
    streak = repeat_rejection_streak(
        ledger_events=events, preset_name="p", dominant_reason="x",
    )
    # Walking from tail: 1 rejection, then completed -> break
    assert streak == 1


def test_decision_priority_constants_are_increasing() -> None:
    expected_order = [
        FUNNEL_DECISION_CONFIRMATION,
        FUNNEL_DECISION_NEAR_PASS_FOLLOWUP,
        "alternate_timeframe_from_insufficient_trades",
        FUNNEL_DECISION_COVERAGE_FOLLOWUP,
        FUNNEL_DECISION_COOLDOWN_REPEAT,
        FUNNEL_DECISION_NO_ACTION_TECHNICAL,
    ]
    priorities = [DECISION_PRIORITY[c] for c in expected_order]
    assert priorities == sorted(priorities)


def test_sort_funnel_decisions_is_deterministic_independent_of_input_order() -> None:
    a = FunnelDecision(
        decision_code=FUNNEL_DECISION_NEAR_PASS_FOLLOWUP,
        candidate_id="c2", strategy_id="s2", preset_name="p",
        priority=DECISION_PRIORITY[FUNNEL_DECISION_NEAR_PASS_FOLLOWUP],
        spawn_request=None, rationale={},
    )
    b = FunnelDecision(
        decision_code=FUNNEL_DECISION_CONFIRMATION,
        candidate_id="c1", strategy_id="s1", preset_name="p",
        priority=DECISION_PRIORITY[FUNNEL_DECISION_CONFIRMATION],
        spawn_request=None, rationale={},
    )
    sorted_ab = sort_funnel_decisions([a, b])
    sorted_ba = sort_funnel_decisions([b, a])
    assert sorted_ab == sorted_ba
    assert sorted_ab[0].decision_code == FUNNEL_DECISION_CONFIRMATION


def test_terminal_campaign_states_match_real_registry_values() -> None:
    from research.campaign_registry import CAMPAIGN_STATES
    assert TERMINAL_CAMPAIGN_STATES == frozenset(
        {"completed", "failed", "canceled", "archived"}
    )
    assert ACTIVE_CAMPAIGN_STATES == frozenset(
        {"pending", "leased", "running"}
    )
    assert TERMINAL_CAMPAIGN_STATES | ACTIVE_CAMPAIGN_STATES == set(CAMPAIGN_STATES)


def test_alternate_timeframe_support_is_explicit_false() -> None:
    assert has_alternate_timeframe_support({}, "any_preset") is False


def test_dedupe_blocks_same_candidate_same_fingerprint() -> None:
    registry = {
        "campaigns": {
            "child-1": {
                "campaign_id": "child-1",
                "parent_campaign_id": "cmp-1",
                "spawn_reason": FUNNEL_DECISION_CONFIRMATION,
                "state": "running",
                "extra": {
                    "lineage_candidate_id": "c1",
                    "screening_evidence_fingerprint": "fp1",
                },
            }
        }
    }
    assert has_funnel_spawn_for(
        registry, parent_campaign_id="cmp-1",
        decision_code=FUNNEL_DECISION_CONFIRMATION,
        lineage_candidate_id="c1", evidence_fingerprint="fp1",
    ) is True


def test_dedupe_blocks_same_candidate_new_fp_while_prior_active() -> None:
    registry = {
        "campaigns": {
            "child-1": {
                "campaign_id": "child-1",
                "parent_campaign_id": "cmp-1",
                "spawn_reason": FUNNEL_DECISION_CONFIRMATION,
                "state": "running",
                "extra": {
                    "lineage_candidate_id": "c1",
                    "screening_evidence_fingerprint": "fp1",
                },
            }
        }
    }
    assert has_funnel_spawn_for(
        registry, parent_campaign_id="cmp-1",
        decision_code=FUNNEL_DECISION_CONFIRMATION,
        lineage_candidate_id="c1", evidence_fingerprint="fp2",
    ) is True


def test_dedupe_allows_same_candidate_new_fp_when_prior_terminal() -> None:
    registry = {
        "campaigns": {
            "child-1": {
                "campaign_id": "child-1",
                "parent_campaign_id": "cmp-1",
                "spawn_reason": FUNNEL_DECISION_CONFIRMATION,
                "state": "completed",
                "extra": {
                    "lineage_candidate_id": "c1",
                    "screening_evidence_fingerprint": "fp1",
                },
            }
        }
    }
    assert has_funnel_spawn_for(
        registry, parent_campaign_id="cmp-1",
        decision_code=FUNNEL_DECISION_CONFIRMATION,
        lineage_candidate_id="c1", evidence_fingerprint="fp2",
    ) is False


def test_dedupe_allows_different_candidate_same_fp() -> None:
    registry = {
        "campaigns": {
            "child-1": {
                "campaign_id": "child-1",
                "parent_campaign_id": "cmp-1",
                "spawn_reason": FUNNEL_DECISION_CONFIRMATION,
                "state": "running",
                "extra": {
                    "lineage_candidate_id": "c1",
                    "screening_evidence_fingerprint": "fp1",
                },
            }
        }
    }
    assert has_funnel_spawn_for(
        registry, parent_campaign_id="cmp-1",
        decision_code=FUNNEL_DECISION_CONFIRMATION,
        lineage_candidate_id="c2", evidence_fingerprint="fp1",
    ) is False


def test_dedupe_returns_false_on_empty_registry() -> None:
    assert has_funnel_spawn_for(
        {"campaigns": {}}, parent_campaign_id="x",
        decision_code=FUNNEL_DECISION_CONFIRMATION,
        lineage_candidate_id="c", evidence_fingerprint="f",
    ) is False
    assert has_funnel_spawn_for(
        None, parent_campaign_id="x",
        decision_code=FUNNEL_DECISION_CONFIRMATION,
        lineage_candidate_id="c", evidence_fingerprint="f",
    ) is False
