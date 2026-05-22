"""Tests for research.synthesis_gate sidecars."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from research import synthesis_gate as sg


def _statuses(status: str = "present") -> dict[str, dict[str, str]]:
    return {
        name: {"path": path.as_posix(), "status": status}
        for name, path in sg.ARTIFACT_PATHS.items()
    }


def _record(
    *,
    campaign_id: str = "col-1",
    preset_name: str = "trend_pullback_crypto_1h",
    outcome: str = "completed_no_survivor",
) -> dict:
    return {
        "campaign_id": campaign_id,
        "preset_name": preset_name,
        "state": "completed",
        "outcome": outcome,
        "finished_at_utc": "2026-05-22T10:00:00Z",
    }


def _eligible_artifacts(**overrides) -> dict:
    artifacts = {
        "research_state": {
            "hypothesis_state": "needs_more_diagnostic_evidence",
            "preset_state": "completed_no_survivor",
            "policy_state": "can_spawn",
            "evidence_quality": {"state": "completed_no_survivor"},
            "failure_attribution": {
                "state": "gate_rejection_attributed",
                "attributed": True,
                "primary_blocker": "validation_or_promotion_gate",
            },
            "campaign_summary": {
                "outcome_counts": {"completed_no_survivor": 2},
                "preset_names": [
                    "trend_pullback_crypto_1h",
                    "vol_compression_breakout_crypto_4h",
                ],
            },
        },
        "research_action_plan": {},
        "policy_filter_diagnostics": {},
        "screening_failure_attribution": {
            "summary": {
                "primary_classification": "strict_gate_rejection",
                "attributed": True,
            }
        },
        "controlled_eval": {},
        "policy_decision": {"decision": {"action": "spawn", "reason": "eligible"}},
        "campaign_registry": {
            "campaigns": {
                "col-1": _record(),
                "col-2": _record(
                    campaign_id="col-2",
                    preset_name="vol_compression_breakout_crypto_4h",
                ),
            }
        },
        "campaign_evidence_ledger": [],
        "discovery_sprint_progress": {},
        "information_gain": {
            "market_context_insight": "Breakout failures cluster in low volatility regimes.",
            "hypothesis": "Trend continuation needs a regime-aware entry filter.",
            "preset_space_exhausted": True,
        },
        "viability": {},
    }
    artifacts.update(overrides)
    return artifacts


def _payload(artifacts: dict, statuses: dict[str, dict[str, str]] | None = None) -> dict:
    return sg.build_synthesis_gate_payload(
        artifacts=artifacts,
        artifact_status=statuses or _statuses(),
        generated_at_utc=datetime(2026, 5, 22, 12, 0, tzinfo=UTC),
    )


def test_no_candidates_blocks_synthesis() -> None:
    payload = _payload(
        _eligible_artifacts(
            research_state={
                "policy_state": "blocked_no_candidates",
                "evidence_quality": {"state": "policy_only"},
            },
            policy_decision={
                "decision": {"action": "idle_noop", "reason": "no_candidates"},
                "candidates_considered": [],
            },
        )
    )

    assert payload["synthesis_gate_state"] == "blocked_policy_only_failure"
    assert payload["allowed"] is False
    assert "policy_only_idle_noop_no_candidates" in payload["reason_codes"]


def test_unattributed_screening_failures_block_synthesis() -> None:
    payload = _payload(
        _eligible_artifacts(
            research_state={
                "hypothesis_state": "active_but_blocked_by_evaluability",
                "failure_attribution": {
                    "state": "screening_evaluability_unattributed",
                    "attributed": False,
                    "primary_blocker": "screening_or_evaluability",
                },
            },
            screening_failure_attribution={
                "summary": {
                    "primary_classification": "unknown_screening_failure",
                    "attributed": False,
                }
            },
        )
    )

    assert payload["synthesis_gate_state"] == "blocked_insufficient_attribution"
    assert payload["allowed"] is False
    assert "screening_failure_attribution" in payload["required_missing_evidence"]


def test_evaluability_primary_blocks_synthesis() -> None:
    payload = _payload(
        _eligible_artifacts(
            research_state={
                "hypothesis_state": "active_but_blocked_by_evaluability",
                "failure_attribution": {
                    "state": "screening_failure_attributed",
                    "attributed": True,
                    "primary_blocker": "screening_or_evaluability",
                },
            },
            screening_failure_attribution={
                "summary": {
                    "primary_classification": "data_coverage_gap",
                    "attributed": True,
                }
            },
        )
    )

    assert payload["synthesis_gate_state"] == "blocked_evaluability_primary"
    assert payload["allowed"] is False
    assert "evaluable_candidate_evidence" in payload["required_missing_evidence"]


def test_missing_market_context_blocks_synthesis() -> None:
    artifacts = _eligible_artifacts(information_gain={"preset_space_exhausted": True})

    payload = _payload(artifacts)

    assert payload["synthesis_gate_state"] == "blocked_missing_market_context"
    assert payload["allowed"] is False
    assert "linked_market_context_insight" in payload["required_missing_evidence"]


def test_no_preset_space_exhaustion_blocks_synthesis() -> None:
    artifacts = _eligible_artifacts(
        information_gain={
            "market_context_insight": "Breakout failures cluster in low volatility regimes.",
            "hypothesis": "Trend continuation needs a regime-aware entry filter.",
        },
        research_state={
            "hypothesis_state": "needs_more_diagnostic_evidence",
            "preset_state": "insufficient_evidence",
            "failure_attribution": {
                "state": "gate_rejection_attributed",
                "attributed": True,
                "primary_blocker": "validation_or_promotion_gate",
            },
            "campaign_summary": {"outcome_counts": {"completed_no_survivor": 1}},
        },
        campaign_registry={"campaigns": {"col-1": _record()}},
    )

    payload = _payload(artifacts)

    assert payload["synthesis_gate_state"] == "blocked_no_preset_space_exhaustion"
    assert payload["allowed"] is False
    assert "preset_space_exhaustion_evidence" in payload["required_missing_evidence"]


def test_allowed_for_sandbox_review_only_when_all_required_evidence_is_present() -> None:
    payload = _payload(_eligible_artifacts())

    assert payload["synthesis_gate_state"] == "allowed_for_sandbox_review"
    assert payload["allowed"] is True
    assert payload["operator_review_required"] is False
    assert payload["allowed_paths"] == list(sg.ALLOWED_SANDBOX_PATHS)
    assert payload["required_missing_evidence"] == []


def test_forbidden_trading_paths_are_always_disallowed() -> None:
    blocked = _payload({"research_state": {}, "campaign_evidence_ledger": []})
    allowed = _payload(_eligible_artifacts())

    for payload in (blocked, allowed):
        disallowed = set(payload["disallowed_paths"])
        assert {"paper/**", "shadow/**", "live/**"} <= disallowed
        assert {"risk/**", "broker/**", "execution/**"} <= disallowed
        assert "agent/backtesting/strategies.py" in disallowed
        assert "registry.py" in disallowed


def test_missing_artifacts_are_handled_gracefully_with_cli(tmp_path: Path) -> None:
    artifacts, statuses = sg.load_current_artifacts(root=tmp_path)
    payload = _payload(artifacts, statuses)

    assert payload["allowed"] is False
    assert payload["synthesis_gate_state"] in sg.GATE_STATES
    assert payload["supporting_evidence"]["artifact_inputs"]["research_state"][
        "status"
    ] == "missing"

    rc = sg.main(
        [
            "--from-current-artifacts",
            "--report-json",
            str(tmp_path / "gate.json"),
            "--report-md",
            str(tmp_path / "gate.md"),
        ]
    )

    assert rc == 0
    written = json.loads((tmp_path / "gate.json").read_text(encoding="utf-8"))
    assert written["schema_version"] == "1.0"
    assert (tmp_path / "gate.md").exists()
