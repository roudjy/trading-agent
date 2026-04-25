"""Regression tests for v3.15.2 eligibility enforcement (R1 hotfix).

These tests pin the contract that ``campaign_policy.decide`` must
honour ``template.eligibility`` against the real preset attributes
before any campaign candidate can be selected. The original v3.15.2
ship missed this enforcement and autonomously fired
``crypto_diagnostic_1h`` for ``daily_primary`` despite its
``excluded_from_daily_scheduler=True`` and ``diagnostic_only=True``
flags.

Cases (matching the hotfix scope):

1. ``diagnostic_only`` presets are not selected for ``daily_primary``.
2. ``excluded_from_daily_scheduler`` presets are not selected for
   ``daily_primary``.
3. ``status="diagnostic"`` is not selected when
   ``require_preset_status=("stable",)``.
4. Eligible stable presets remain selectable.
5. ``weekly_retest`` and follow-up phases do not bypass eligibility
   (specifically: a disabled preset cannot be retested or followed
   up; a frozen-but-enabled preset CAN be retested).
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from research.campaign_budget import BudgetState
from research.campaign_policy import CandidateSpec, decide
from research.campaign_preset_policy import PresetPolicyState
from research.campaign_templates import (
    CAMPAIGN_TEMPLATES,
    DEFAULT_CONFIG,
    EligibilityPredicate,
    CampaignOsConfig,
    CampaignTemplate,
    get_template,
)
from research.presets import get_preset


PRIMARY_TEMPLATE_IDS = sorted(
    t.template_id for t in CAMPAIGN_TEMPLATES if t.campaign_type == "daily_primary"
)


@pytest.fixture
def now_utc() -> datetime:
    return datetime(2026, 4, 25, 12, 0, 0, tzinfo=UTC)


def _budget() -> BudgetState:
    return BudgetState(
        date="2026-04-25",
        daily_compute_budget_seconds=DEFAULT_CONFIG.daily_compute_budget_seconds,
        reserved_for_followups_seconds=DEFAULT_CONFIG.reserved_for_followups_seconds,
        max_low_value_reruns_per_day=DEFAULT_CONFIG.max_low_value_reruns_per_day,
        tier1_fairness_cap=DEFAULT_CONFIG.tier1_fairness_cap,
    )


def _active_state(preset_name: str) -> PresetPolicyState:
    return PresetPolicyState(
        preset_name=preset_name,
        policy_state="active",
        priority_tier_delta=0,
        effective_cooldown_seconds=86_400,
        paper_followup_weekly_cap=2,
        reason="baseline",
        consecutive_event_count=0,
        last_event_ids=(),
        at_utc="2026-04-25T12:00:00Z",
    )


def _decide_with_active_states(
    now_utc: datetime,
    *,
    follow_up_specs: tuple[CandidateSpec, ...] = (),
    weekly_control_specs: tuple[CandidateSpec, ...] = (),
    preset_state_overrides: dict[str, PresetPolicyState] | None = None,
):
    preset_states = {
        t.preset_name: _active_state(t.preset_name) for t in CAMPAIGN_TEMPLATES
    }
    if preset_state_overrides:
        preset_states.update(preset_state_overrides)
    return decide(
        registry={"campaigns": {}},
        queue={"queue": []},
        events=[],
        budget=_budget(),
        templates=CAMPAIGN_TEMPLATES,
        config=DEFAULT_CONFIG,
        preset_state_by_name=preset_states,
        family_state_by_key={},
        upstream_artifact_states={},
        follow_up_candidate_specs=follow_up_specs,
        weekly_control_candidate_specs=weekly_control_specs,
        now_utc=now_utc,
    )


# ---------------------------------------------------------------------------
# Case 1 — diagnostic_only presets are not selected for daily_primary.
# ---------------------------------------------------------------------------


def test_diagnostic_only_preset_not_selected_for_daily_primary(
    now_utc: datetime,
) -> None:
    crypto = get_preset("crypto_diagnostic_1h")
    assert crypto.diagnostic_only is True, "fixture sanity"
    decision = _decide_with_active_states(now_utc)
    assert decision.decision.action == "spawn"
    assert decision.decision.preset_name != "crypto_diagnostic_1h"
    rejected = [
        c
        for c in decision.candidates_considered
        if c.get("preset_name") == "crypto_diagnostic_1h"
        and c.get("campaign_type") == "daily_primary"
    ]
    assert rejected, "diagnostic_only preset should have been considered + rejected"
    assert any(
        c.get("reject_reason") in ("preset_diagnostic_only", "preset_excluded_from_daily_scheduler")
        for c in rejected
    ), f"got reject_reasons: {[c.get('reject_reason') for c in rejected]}"


# ---------------------------------------------------------------------------
# Case 2 — excluded_from_daily_scheduler presets are not selected.
# ---------------------------------------------------------------------------


def test_excluded_from_daily_scheduler_not_selected(
    now_utc: datetime,
) -> None:
    crypto = get_preset("crypto_diagnostic_1h")
    assert crypto.excluded_from_daily_scheduler is True
    decision = _decide_with_active_states(now_utc)
    assert decision.decision.action == "spawn"
    assert decision.decision.preset_name != "crypto_diagnostic_1h"


# ---------------------------------------------------------------------------
# Case 3 — status="diagnostic" rejected when require_preset_status=("stable",)
# ---------------------------------------------------------------------------


def test_diagnostic_status_rejected_when_stable_required(
    now_utc: datetime,
) -> None:
    crypto = get_preset("crypto_diagnostic_1h")
    assert crypto.status == "diagnostic"
    template = get_template("daily_primary__crypto_diagnostic_1h")
    assert "stable" in template.eligibility.require_preset_status

    decision = _decide_with_active_states(now_utc)
    assert decision.decision.preset_name != "crypto_diagnostic_1h"

    # Confirm a status check would fire even if the other forbids were off:
    # build a one-template catalog with a status-only predicate.
    custom_template = CampaignTemplate(
        template_id="daily_primary__crypto_diagnostic_1h_status_only",
        preset_name="crypto_diagnostic_1h",
        campaign_type="daily_primary",
        priority_tier=2,
        cooldown_seconds=86_400,
        max_per_day=1,
        eligibility=EligibilityPredicate(
            require_preset_enabled=True,
            forbid_excluded_from_daily_scheduler=False,
            forbid_diagnostic_only=False,
            require_preset_status=("stable",),
        ),
        estimated_runtime_seconds_default=1_800,
        spawn_triggers=("cron_tick",),
        followup_rules=(),
    )
    custom_catalog = (custom_template,)
    custom_decision = decide(
        registry={"campaigns": {}},
        queue={"queue": []},
        events=[],
        budget=_budget(),
        templates=custom_catalog,
        config=CampaignOsConfig(max_concurrent_campaigns=1),
        preset_state_by_name={
            "crypto_diagnostic_1h": _active_state("crypto_diagnostic_1h"),
        },
        family_state_by_key={},
        upstream_artifact_states={},
        now_utc=now_utc,
    )
    assert custom_decision.decision.action == "idle_noop"
    rejected = [
        c
        for c in custom_decision.candidates_considered
        if c.get("preset_name") == "crypto_diagnostic_1h"
    ]
    assert rejected, "status-only template should reach the filter pipeline"
    assert rejected[0]["reject_reason"].startswith(
        "preset_status_diagnostic_not_in_required"
    )


# ---------------------------------------------------------------------------
# Case 4 — eligible stable preset is selected.
# ---------------------------------------------------------------------------


def test_eligible_stable_preset_is_selected(now_utc: datetime) -> None:
    eligible = get_preset("trend_equities_4h_baseline")
    assert eligible.enabled is True
    assert eligible.status == "stable"
    assert eligible.diagnostic_only is False
    assert eligible.excluded_from_daily_scheduler is False

    decision = _decide_with_active_states(now_utc)
    assert decision.decision.action == "spawn"
    assert decision.decision.campaign_type == "daily_primary"
    # Among the catalog presets that pass eligibility, the alphabetically
    # earliest template_id wins — that's deterministic.
    eligible_template_ids = sorted(
        t.template_id
        for t in CAMPAIGN_TEMPLATES
        if t.campaign_type == "daily_primary"
        and (
            (not t.eligibility.forbid_diagnostic_only or not get_preset(t.preset_name).diagnostic_only)
            and (not t.eligibility.forbid_excluded_from_daily_scheduler or not get_preset(t.preset_name).excluded_from_daily_scheduler)
            and (not t.eligibility.require_preset_status or get_preset(t.preset_name).status in t.eligibility.require_preset_status)
            and (not t.eligibility.require_preset_enabled or get_preset(t.preset_name).enabled)
        )
    )
    assert decision.decision.template_id == eligible_template_ids[0]


# ---------------------------------------------------------------------------
# Case 5 — weekly_retest / follow-ups don't bypass eligibility.
# ---------------------------------------------------------------------------


def test_weekly_retest_picks_up_frozen_but_enabled_preset(
    now_utc: datetime,
) -> None:
    """A frozen preset stays enabled, so weekly_retest CAN pick it up.

    weekly_retest's eligibility requires only ``require_preset_enabled``;
    diagnostic_only / excluded flags are deliberately permitted because
    the retest is a recovery mechanism.
    """
    frozen = PresetPolicyState(
        preset_name="trend_equities_4h_baseline",
        policy_state="frozen",
        priority_tier_delta=0,
        effective_cooldown_seconds=86_400,
        paper_followup_weekly_cap=0,
        reason="five_consecutive_non_technical_rejects",
        consecutive_event_count=5,
        last_event_ids=(),
        at_utc="2026-04-25T12:00:00Z",
    )
    overrides = {
        t.preset_name: PresetPolicyState(
            preset_name=t.preset_name,
            policy_state="frozen",
            priority_tier_delta=0,
            effective_cooldown_seconds=86_400,
            paper_followup_weekly_cap=0,
            reason="five_consecutive_non_technical_rejects",
            consecutive_event_count=5,
            last_event_ids=(),
            at_utc="2026-04-25T12:00:00Z",
        )
        for t in CAMPAIGN_TEMPLATES
    }
    overrides["trend_equities_4h_baseline"] = frozen
    decision = _decide_with_active_states(
        now_utc, preset_state_overrides=overrides
    )
    assert decision.decision.action == "spawn"
    assert decision.decision.campaign_type == "weekly_retest"


def test_disabled_preset_blocked_for_weekly_retest(
    now_utc: datetime,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Disabled presets fail ``require_preset_enabled`` at the eligibility filter,
    even when frozen state would otherwise make them weekly_retest candidates."""
    real_preset = get_preset("trend_equities_4h_baseline")
    disabled = type(real_preset)(
        **{
            **{
                f.name: getattr(real_preset, f.name)
                for f in real_preset.__dataclass_fields__.values()
            },
            "enabled": False,
            "backlog_reason": "regression_test_disabled",
        }
    )
    import research.campaign_policy as cp

    orig = cp.get_preset

    def _stub(name: str):
        if name == "trend_equities_4h_baseline":
            return disabled
        return orig(name)

    monkeypatch.setattr(cp, "get_preset", _stub)

    overrides = {
        "trend_equities_4h_baseline": PresetPolicyState(
            preset_name="trend_equities_4h_baseline",
            policy_state="frozen",
            priority_tier_delta=0,
            effective_cooldown_seconds=86_400,
            paper_followup_weekly_cap=0,
            reason="five_consecutive_non_technical_rejects",
            consecutive_event_count=5,
            last_event_ids=(),
            at_utc="2026-04-25T12:00:00Z",
        ),
    }
    # Other presets active so they don't crowd out the test result.
    decision = _decide_with_active_states(
        now_utc, preset_state_overrides=overrides
    )
    rejected_for_target = [
        c
        for c in decision.candidates_considered
        if c.get("preset_name") == "trend_equities_4h_baseline"
    ]
    # A disabled preset should be rejected with preset_disabled, not picked.
    assert any(
        c.get("reject_reason") == "preset_disabled" for c in rejected_for_target
    ), f"got: {[c.get('reject_reason') for c in rejected_for_target]}"


def test_follow_up_eligibility_rejects_disabled_preset(
    now_utc: datetime,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A follow-up CandidateSpec for a disabled preset must be rejected
    via the new eligibility filter, not silently allowed through Phase A."""
    real_preset = get_preset("trend_equities_4h_baseline")
    disabled = type(real_preset)(
        **{
            **{f.name: getattr(real_preset, f.name) for f in real_preset.__dataclass_fields__.values()},
            "enabled": False,
            "backlog_reason": "regression_test_disabled",
        }
    )
    import research.campaign_policy as cp
    orig = cp.get_preset

    def _stub(name: str):
        if name == "trend_equities_4h_baseline":
            return disabled
        return orig(name)

    monkeypatch.setattr(cp, "get_preset", _stub)

    survivor_template = get_template(
        "survivor_confirmation__trend_equities_4h_baseline"
    )
    follow_up = CandidateSpec(
        template=survivor_template,
        appended_in_phase="A",
        appended_index=0,
        preset_name="trend_equities_4h_baseline",
        campaign_type="survivor_confirmation",
        parent_campaign_id="col-parent",
        lineage_root_campaign_id="col-parent",
        spawn_reason="survivor_found",
        subtype=None,
        input_artifact_fingerprint="",
        estimate_seconds=1_800,
        effective_priority_tier=1,
    )
    decision = _decide_with_active_states(
        now_utc, follow_up_specs=(follow_up,)
    )
    rejected_followups = [
        c
        for c in decision.candidates_considered
        if c.get("campaign_type") == "survivor_confirmation"
    ]
    assert rejected_followups, "follow-up should reach the filter pipeline"
    assert rejected_followups[0]["reject_reason"] == "preset_disabled"


# ---------------------------------------------------------------------------
# Determinism — the hotfix must not affect invariant I6.
# ---------------------------------------------------------------------------


def test_eligibility_filter_keeps_decision_pure(now_utc: datetime) -> None:
    from research._sidecar_io import serialize_canonical
    a = _decide_with_active_states(now_utc)
    b = _decide_with_active_states(now_utc)
    assert serialize_canonical(a.to_payload()) == serialize_canonical(b.to_payload())
