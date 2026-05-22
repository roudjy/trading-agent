"""Tests for research.research_action_plan sidecars."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from research import research_action_plan as rap


def _statuses(research_state_status: str = "present") -> dict[str, dict[str, str]]:
    return {
        name: {
            "path": path.as_posix(),
            "status": research_state_status if name == "research_state" else "present",
        }
        for name, path in rap.ARTIFACT_PATHS.items()
    }


def _state(**overrides) -> dict:
    base = {
        "hypothesis_state": "blocked_by_policy",
        "preset_state": "completed_no_survivor",
        "policy_state": "blocked_no_candidates",
        "evidence_quality": {
            "state": "policy_only",
            "rank": 1,
            "summary": "No-candidate policy evidence is not hypothesis evidence.",
        },
        "failure_attribution": {
            "state": "policy_only_failure",
            "attributed": True,
            "primary_blocker": "policy_no_candidates",
            "missing": ["policy_filter_diagnostics"],
        },
        "instrumentation_states": ["healthy"],
        "next_allowed_actions": [
            "inspect_campaign_policy_filters",
            "inspect_gate_diagnostics",
        ],
        "synthesis_gate": "blocked_policy_only_failure",
        "next_best_test": "inspect_campaign_policy_filters",
        "policy_summary": {
            "action": "idle_noop",
            "reason": "no_candidates",
            "candidates_considered": 0,
        },
        "campaign_summary": {
            "active_campaign_count": 0,
            "outcome_counts": {"completed_no_survivor": 1},
        },
    }
    base.update(overrides)
    return base


def _payload(state: dict | None, statuses: dict[str, dict[str, str]] | None = None) -> dict:
    artifacts = {
        "research_state": state,
        "controlled_eval": {},
        "campaign_registry": {},
        "campaign_evidence_ledger": [],
        "policy_decision": {},
        "research_state_markdown": "# state",
        "discovery_sprint_progress": {},
        "information_gain": {},
        "viability": {},
        "stop_conditions": {},
        "spawn_proposals": {},
    }
    return rap.build_action_plan_payload(
        artifacts=artifacts,
        artifact_status=statuses or _statuses(),
        generated_at_utc=datetime(2026, 5, 22, 12, 0, tzinfo=UTC),
    )


def _action_ids(payload: dict, section: str = "automatic_actions") -> list[str]:
    return [action["action_id"] for action in payload[section]]


def test_blocked_no_candidates_prioritizes_policy_filter_diagnostics() -> None:
    payload = _payload(_state())

    assert payload["next_best_action"]["action_id"] == "inspect_campaign_policy_filters"
    assert payload["next_best_action"]["priority"] == 1
    assert payload["state_summary"]["policy_filter_diagnostics_first"] is True
    assert "inspect_campaign_policy_filters" in _action_ids(payload)


def test_screening_evaluability_unattributed_adds_drop_reason_diagnostics() -> None:
    payload = _payload(
        _state(
            policy_state="can_spawn",
            preset_state="degenerate_screening_failure",
            evidence_quality={"state": "screening_or_evaluability_failure"},
            failure_attribution={
                "state": "screening_evaluability_unattributed",
                "attributed": False,
                "primary_blocker": "screening_or_evaluability",
                "missing": ["screening_drop_reasons"],
            },
            synthesis_gate="blocked_insufficient_attribution",
            next_best_test="explain_screening_drop_reasons",
            campaign_summary={
                "active_campaign_count": 0,
                "outcome_counts": {"degenerate_no_survivors": 1},
            },
        )
    )

    assert payload["next_best_action"]["action_id"] == "explain_screening_drop_reasons"
    assert payload["state_summary"]["screening_drop_reason_diagnostics_first"] is True
    assert "explain_screening_drop_reasons" in _action_ids(payload)


def test_completed_no_survivor_adds_gate_diagnostics() -> None:
    payload = _payload(
        _state(
            policy_state="can_spawn",
            failure_attribution={
                "state": "gate_rejection_unattributed",
                "attributed": False,
                "primary_blocker": "validation_or_promotion_gate",
                "missing": ["gate_diagnostics"],
            },
            synthesis_gate="blocked_insufficient_attribution",
            next_best_test="inspect_gate_diagnostics",
        )
    )

    assert payload["next_best_action"]["action_id"] == "inspect_gate_diagnostics"
    assert "inspect_gate_diagnostics" in _action_ids(payload)


def test_synthesis_blocked_state_prevents_automatic_synthesis() -> None:
    payload = _payload(_state(synthesis_gate="blocked_policy_only_failure"))

    assert payload["synthesis_status"]["status"] == "blocked"
    assert payload["synthesis_status"]["automatic_allowed"] is False
    assert "enable_synthesis_lane" in _action_ids(payload, "operator_gated_actions")
    assert "approve_sandbox_synthesis" in _action_ids(payload, "operator_gated_actions")
    assert all(
        "synthesis" not in action["action_id"]
        for action in payload["automatic_actions"]
    )


def test_forbidden_trading_actions_are_always_present() -> None:
    payload = _payload(_state())

    forbidden = set(_action_ids(payload, "forbidden_actions"))
    assert forbidden == set(rap.FORBIDDEN_ACTION_IDS)
    assert {"paper_trading", "shadow_trading", "live_trading"} <= forbidden
    assert {"broker_changes", "risk_changes", "execution_changes"} <= forbidden


def test_missing_research_state_is_handled_gracefully(tmp_path: Path) -> None:
    payload = _payload(None, _statuses(research_state_status="missing"))

    assert payload["state_summary"]["source_research_state_status"] == "missing"
    assert payload["next_best_action"]["action_id"] == "inspect_gate_diagnostics"
    assert payload["synthesis_status"]["status"] == "blocked"

    rc = rap.main(
        [
            "--from-current-artifacts",
            "--report-json",
            str(tmp_path / "plan.json"),
            "--report-md",
            str(tmp_path / "plan.md"),
        ]
    )

    assert rc == 0
    written = json.loads((tmp_path / "plan.json").read_text(encoding="utf-8"))
    assert written["state_summary"]["source_research_state_status"] == "missing"
    assert (tmp_path / "plan.md").exists()


def test_blind_rerun_is_not_top_action_for_blocked_no_candidates() -> None:
    payload = _payload(_state())

    assert payload["next_best_action"]["action_id"] != "controlled_eval_bounded"
    assert payload["next_best_action"]["action_id"] == "inspect_campaign_policy_filters"
    assert payload["state_summary"]["next_best_controlled_eval"]["allowed"] is False
    assert "Blind rerun is not appropriate" in " ".join(payload["rationale"])
