"""v3.15.11 — stop-condition engine unit tests (advisory only)."""

from __future__ import annotations

import inspect
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from research import campaign_policy as _campaign_policy
from research._sidecar_io import serialize_canonical
from research.stop_condition_engine import (
    DECISION_COOLDOWN,
    DECISION_FREEZE_PRESET,
    DECISION_RETIRE_FAMILY,
    DECISION_REVIEW_REQUIRED,
    ENFORCEMENT_STATE_ADVISORY,
    STOP_CONDITIONS_SCHEMA_VERSION,
    STOP_INSUFFICIENT_TRADES_COOLDOWN,
    STOP_REPEAT_REJECTION_FREEZE,
    STOP_REPEAT_REJECTION_RETIRE,
    STOP_TECHNICAL_FAILURE_REVIEW,
    build_stop_conditions_payload,
    derive_stop_conditions,
    write_stop_conditions_artifact,
)


_AS_OF = datetime(2026, 4, 27, 12, 0, 0, tzinfo=UTC)


def _hyp_row(
    *,
    preset: str = "p1",
    family: str = "f1",
    rejection_count: int = 0,
    technical_failure_count: int = 0,
    promotion_candidate_count: int = 0,
    paper_ready_count: int = 0,
    exploratory_pass_count: int = 0,
    dominant: str | None = None,
    campaign_count: int | None = None,
) -> dict[str, Any]:
    return {
        "preset_name": preset,
        "strategy_family": family,
        "hypothesis_id": "h",
        "rejection_count": rejection_count,
        "technical_failure_count": technical_failure_count,
        "promotion_candidate_count": promotion_candidate_count,
        "paper_ready_count": paper_ready_count,
        "exploratory_pass_count": exploratory_pass_count,
        "degenerate_count": 0,
        "dominant_failure_mode": dominant,
        "campaign_count": campaign_count
        or (
            rejection_count
            + technical_failure_count
            + promotion_candidate_count
            + paper_ready_count
            + exploratory_pass_count
        ),
        "last_outcome": "unknown",
        "last_seen_at_utc": "2026-04-27T10:00:00+00:00",
    }


def _ledger(rows: list[dict[str, Any]]) -> dict[str, Any]:
    return {"hypothesis_evidence": rows}


def test_three_insufficient_trades_recommends_cooldown() -> None:
    decisions = derive_stop_conditions(
        _ledger([
            _hyp_row(
                rejection_count=STOP_INSUFFICIENT_TRADES_COOLDOWN,
                dominant="insufficient_trades",
            )
        ])
    )
    cooldowns = [d for d in decisions if d.recommended_decision == DECISION_COOLDOWN]
    assert len(cooldowns) == 1
    assert cooldowns[0].reason_codes == ["repeated_insufficient_trades"]
    assert cooldowns[0].enforcement_state == ENFORCEMENT_STATE_ADVISORY


def test_five_rejections_recommend_freeze_preset() -> None:
    decisions = derive_stop_conditions(
        _ledger([
            _hyp_row(
                rejection_count=STOP_REPEAT_REJECTION_FREEZE,
                dominant="screening_criteria_not_met",
            )
        ])
    )
    freezes = [d for d in decisions if d.recommended_decision == DECISION_FREEZE_PRESET]
    assert len(freezes) == 1
    assert freezes[0].enforcement_state == ENFORCEMENT_STATE_ADVISORY


def test_technical_failures_only_recommend_review_not_retire() -> None:
    decisions = derive_stop_conditions(
        _ledger([
            _hyp_row(technical_failure_count=STOP_TECHNICAL_FAILURE_REVIEW)
        ])
    )
    kinds = {d.recommended_decision for d in decisions}
    assert DECISION_REVIEW_REQUIRED in kinds
    assert DECISION_RETIRE_FAMILY not in kinds
    assert DECISION_FREEZE_PRESET not in kinds


def test_existing_promotion_candidate_blocks_freeze_and_retire() -> None:
    decisions = derive_stop_conditions(
        _ledger([
            _hyp_row(
                rejection_count=STOP_REPEAT_REJECTION_RETIRE,
                promotion_candidate_count=1,
                dominant="screening_criteria_not_met",
            )
        ])
    )
    kinds = {d.recommended_decision for d in decisions}
    assert DECISION_FREEZE_PRESET not in kinds
    assert DECISION_RETIRE_FAMILY not in kinds


def test_paper_ready_blocks_retire() -> None:
    decisions = derive_stop_conditions(
        _ledger([
            _hyp_row(
                rejection_count=STOP_REPEAT_REJECTION_RETIRE,
                paper_ready_count=1,
                dominant="screening_criteria_not_met",
            )
        ])
    )
    assert all(d.recommended_decision != DECISION_RETIRE_FAMILY for d in decisions)


def test_sustained_rejection_without_protection_recommends_retire() -> None:
    decisions = derive_stop_conditions(
        _ledger([
            _hyp_row(
                rejection_count=STOP_REPEAT_REJECTION_RETIRE,
                dominant="screening_criteria_not_met",
            )
        ])
    )
    retires = [d for d in decisions if d.recommended_decision == DECISION_RETIRE_FAMILY]
    assert len(retires) == 1
    assert retires[0].scope_type == "strategy_family"


def test_empty_ledger_no_decisions() -> None:
    assert derive_stop_conditions(_ledger([])) == []


def test_decision_ordering_is_deterministic() -> None:
    rows = [
        _hyp_row(
            preset="z_preset",
            rejection_count=STOP_REPEAT_REJECTION_FREEZE,
            dominant="screening_criteria_not_met",
        ),
        _hyp_row(
            preset="a_preset",
            rejection_count=STOP_REPEAT_REJECTION_FREEZE,
            dominant="screening_criteria_not_met",
        ),
    ]
    decisions = derive_stop_conditions(_ledger(rows))
    presets = [d.scope_id for d in decisions]
    assert presets == sorted(presets)


def test_low_information_window_recommends_review() -> None:
    history = [
        {"information_gain": {"is_meaningful_campaign": False}}
        for _ in range(10)
    ]
    decisions = derive_stop_conditions(_ledger([]), information_gain_history=history)
    assert any(
        d.recommended_decision == DECISION_REVIEW_REQUIRED
        and "no_meaningful_information_in_recent_window" in d.reason_codes
        for d in decisions
    )


def test_low_information_window_meaningful_present_no_review() -> None:
    history = [
        {"information_gain": {"is_meaningful_campaign": False}}
        for _ in range(9)
    ] + [{"information_gain": {"is_meaningful_campaign": True}}]
    decisions = derive_stop_conditions(_ledger([]), information_gain_history=history)
    assert not any(
        d.recommended_decision == DECISION_REVIEW_REQUIRED
        and "no_meaningful_information_in_recent_window" in d.reason_codes
        for d in decisions
    )


def test_payload_top_level_enforcement_state_is_advisory_only() -> None:
    payload = build_stop_conditions_payload(
        run_id="run_a",
        as_of_utc=_AS_OF,
        git_revision=None,
        evidence_ledger=_ledger([
            _hyp_row(
                rejection_count=STOP_REPEAT_REJECTION_FREEZE,
                dominant="screening_criteria_not_met",
            )
        ]),
    )
    assert payload["schema_version"] == STOP_CONDITIONS_SCHEMA_VERSION
    assert payload["enforcement_state"] == ENFORCEMENT_STATE_ADVISORY
    for d in payload["decisions"]:
        assert d["enforcement_state"] == ENFORCEMENT_STATE_ADVISORY
        assert "recommended_decision" in d
        assert "decision" not in d  # the field MUST be the advisory name


def test_byte_identical_payload_for_repeated_build() -> None:
    led = _ledger([
        _hyp_row(
            rejection_count=STOP_REPEAT_REJECTION_FREEZE,
            dominant="screening_criteria_not_met",
        )
    ])
    p1 = build_stop_conditions_payload(
        run_id="r",
        as_of_utc=_AS_OF,
        git_revision="x",
        evidence_ledger=led,
    )
    p2 = build_stop_conditions_payload(
        run_id="r",
        as_of_utc=_AS_OF,
        git_revision="x",
        evidence_ledger=led,
    )
    assert serialize_canonical(p1) == serialize_canonical(p2)


def test_io_wrapper_creates_subdir(tmp_path: Path) -> None:
    out = tmp_path / "research" / "campaigns" / "evidence" / "sc.json"
    payload = write_stop_conditions_artifact(
        run_id="r",
        as_of_utc=_AS_OF,
        git_revision=None,
        evidence_ledger=_ledger([]),
        output_path=out,
    )
    assert out.exists()
    assert payload["enforcement_state"] == ENFORCEMENT_STATE_ADVISORY


def test_campaign_policy_decide_signature_unchanged() -> None:
    """Regression: this release does NOT consume stop-conditions in policy.

    If policy.decide() ever takes a stop_conditions kwarg, that's a
    new release boundary and this test must be updated alongside it.
    """
    sig = inspect.signature(_campaign_policy.decide)
    forbidden_params = {
        "stop_conditions",
        "stop_condition_decisions",
        "advisory_decisions",
    }
    intersection = forbidden_params.intersection(sig.parameters.keys())
    assert intersection == set(), (
        "campaign_policy.decide() unexpectedly accepts advisory inputs: "
        f"{intersection}"
    )
