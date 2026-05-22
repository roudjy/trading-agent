"""Tests for research.research_state decision-state sidecars."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from research import research_state as rs


def _statuses() -> dict[str, dict[str, str]]:
    return {
        name: {"path": path.as_posix(), "status": "present"}
        for name, path in rs.ARTIFACT_PATHS.items()
    }


def _artifacts(**overrides) -> dict:
    base = {
        "controlled_eval": {},
        "policy_decision": {},
        "campaign_registry": {"campaigns": {}},
        "campaign_evidence_ledger": [],
        "discovery_sprint_progress": {},
        "information_gain": {},
        "viability": {},
        "stop_conditions": {},
        "spawn_proposals": {},
    }
    base.update(overrides)
    return base


def _policy_no_candidates() -> dict:
    return {
        "decision": {"action": "idle_noop", "reason": "no_candidates"},
        "rules_evaluated": [
            {"rule_id": "R3_single_worker", "result": "allow"},
            {
                "rule_id": "R4_R7_filtering",
                "result": "candidates",
                "surviving": 0,
                "rejected": 7,
            },
            {"rule_id": "R8_idle", "result": "fire"},
        ],
        "candidates_considered": [],
    }


def _record(
    *,
    campaign_id: str = "col-1",
    preset_name: str = "trend_pullback_crypto_1h",
    outcome: str,
    reason_code: str = "none",
    extra: dict | None = None,
    failure_attribution: dict | None = None,
) -> dict:
    record = {
        "campaign_id": campaign_id,
        "preset_name": preset_name,
        "state": "completed",
        "outcome": outcome,
        "reason_code": reason_code,
        "finished_at_utc": "2026-05-22T10:00:00Z",
        "extra": extra or {},
    }
    if failure_attribution is not None:
        record["failure_attribution"] = failure_attribution
    return record


def _payload(artifacts: dict, statuses: dict | None = None) -> dict:
    return rs.build_research_state_payload(
        artifacts=artifacts,
        artifact_status=statuses or _statuses(),
        generated_at_utc=datetime(2026, 5, 22, 12, 0, tzinfo=UTC),
    )


def test_no_candidates_policy_block_does_not_falsify_hypothesis() -> None:
    payload = _payload(
        _artifacts(
            controlled_eval={"verdict": {"status": "no_campaign_completed"}},
            policy_decision=_policy_no_candidates(),
        )
    )

    assert payload["policy_state"] == "blocked_no_candidates"
    assert payload["hypothesis_state"] == "blocked_by_policy"
    assert payload["hypothesis_state"] not in {
        "weakly_falsified",
        "strong_falsification_not_supported",
    }
    assert "inspect_campaign_policy_filters" in payload["next_allowed_actions"]
    assert payload["synthesis_gate"] == "blocked_policy_only_failure"
    assert payload["next_best_test"] == "inspect_campaign_policy_filters"


def test_degenerate_no_survivors_requires_drop_reason_attribution() -> None:
    payload = _payload(
        _artifacts(
            campaign_registry={
                "campaigns": {
                    "col-1": _record(
                        outcome="degenerate_no_survivors",
                        reason_code="degenerate_no_evaluable_pairs",
                    )
                }
            }
        )
    )

    assert payload["preset_state"] == "degenerate_screening_failure"
    assert payload["hypothesis_state"] == "active_but_blocked_by_evaluability"
    assert payload["failure_attribution"]["state"] == "screening_evaluability_unattributed"
    assert payload["failure_attribution"]["attributed"] is False
    assert payload["failure_attribution"]["missing"] == ["screening_drop_reasons"]
    assert "explain_screening_drop_reasons" in payload["next_allowed_actions"]
    assert payload["synthesis_gate"] == "blocked_insufficient_attribution"


def test_completed_no_survivor_is_stronger_evidence_than_degenerate() -> None:
    degenerate = _payload(
        _artifacts(
            campaign_registry={
                "campaigns": {
                    "col-deg": _record(
                        campaign_id="col-deg",
                        outcome="degenerate_no_survivors",
                        reason_code="degenerate_no_evaluable_pairs",
                    )
                }
            }
        )
    )
    completed = _payload(
        _artifacts(
            campaign_registry={
                "campaigns": {
                    "col-complete": _record(
                        campaign_id="col-complete",
                        outcome="completed_no_survivor",
                    )
                }
            }
        )
    )

    assert completed["preset_state"] == "completed_no_survivor"
    assert completed["evidence_quality"]["rank"] > degenerate["evidence_quality"]["rank"]
    assert completed["hypothesis_state"] == "needs_more_diagnostic_evidence"
    assert "inspect_gate_diagnostics" in completed["next_allowed_actions"]
    assert completed["synthesis_gate"] == "blocked_insufficient_attribution"


def test_sprint_observed_total_with_zero_viability_count_is_misaligned() -> None:
    payload = _payload(
        _artifacts(
            discovery_sprint_progress={"observed_total": 2},
            viability={"campaign_count": 0},
        )
    )

    assert "viability_window_misaligned" in payload["instrumentation_states"]
    assert "viability_window_misaligned" in payload["instrumentation_gaps"]
    assert "check_evidence_window_alignment" in payload["next_allowed_actions"]


def test_missing_artifacts_are_handled_gracefully(tmp_path: Path) -> None:
    artifacts, statuses = rs.load_current_artifacts(root=tmp_path)
    payload = _payload(artifacts, statuses)

    assert payload["artifact_inputs"]["controlled_eval"]["status"] == "missing"
    assert payload["hypothesis_state"] == "unknown"
    assert "missing_artifacts" in payload["instrumentation_states"]
    assert payload["synthesis_gate"] == "not_allowed_yet"
    assert payload["safety_invariants"]["runs_research"] is False
    assert payload["safety_invariants"]["mutates_campaign_artifacts"] is False


def test_synthesis_is_blocked_unless_conditions_are_met() -> None:
    blocked = _payload(
        _artifacts(
            controlled_eval={"verdict": {"status": "no_campaign_completed"}},
            policy_decision=_policy_no_candidates(),
        )
    )
    allowed = _payload(
        _artifacts(
            campaign_registry={
                "campaigns": {
                    "col-1": _record(
                        campaign_id="col-1",
                        preset_name="trend_pullback_crypto_1h",
                        outcome="completed_no_survivor",
                        failure_attribution={"primary": "strict_gate_rejection"},
                    ),
                    "col-2": _record(
                        campaign_id="col-2",
                        preset_name="vol_compression_breakout_crypto_4h",
                        outcome="completed_no_survivor",
                        failure_attribution={"primary": "strict_gate_rejection"},
                    ),
                }
            },
            spawn_proposals={
                "market_context_insight": "Breakout volatility regimes remain plausible."
            },
        )
    )

    assert blocked["synthesis_gate"] != "allowed_for_sandbox_review"
    assert "strategy_synthesis_without_attribution" in blocked["disallowed_actions"]
    assert allowed["synthesis_gate"] == "allowed_for_sandbox_review"
    assert "review_sandbox_synthesis_inputs" in allowed["next_allowed_actions"]
