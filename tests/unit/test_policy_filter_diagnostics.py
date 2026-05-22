"""Tests for research.policy_filter_diagnostics sidecars."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from research import policy_filter_diagnostics as pfd


def _statuses() -> dict[str, dict[str, str]]:
    return {
        name: {"path": path.as_posix(), "status": "present"}
        for name, path in pfd.ARTIFACT_PATHS.items()
    }


def _policy(
    *,
    action: str = "idle_noop",
    reason: str = "no_candidates",
    candidates: list[dict] | None = None,
    r3_result: str = "allow",
) -> dict:
    candidates = candidates or []
    rejected = sum(1 for item in candidates if item.get("result") == "rejected")
    surviving = sum(1 for item in candidates if item.get("result") == "surviving")
    return {
        "decision": {"action": action, "reason": reason},
        "rules_evaluated": [
            {"rule_id": "R3_single_worker", "result": r3_result},
            {
                "rule_id": "R4_R7_filtering",
                "result": "candidates",
                "surviving": surviving,
                "rejected": rejected,
            },
            {"rule_id": "R8_idle", "result": "fire" if not surviving else "n/a"},
        ],
        "candidates_considered": candidates,
    }


def _rejected(reason: str, *, preset: str = "p", template: str = "t") -> dict:
    return {
        "template_id": template,
        "preset_name": preset,
        "campaign_type": "daily_primary",
        "appended_in_phase": "B",
        "appended_index": 0,
        "reject_reason": reason,
        "details": {},
        "result": "rejected",
    }


def _payload(policy: dict, **artifact_overrides) -> dict:
    artifacts = {
        "policy_decision": policy,
        "controlled_eval": {},
        "campaign_registry": {"campaigns": {}},
        "campaign_queue": {"queue": []},
        "campaign_evidence_ledger": [],
        "sprint_routing_decision": {},
        "discovery_sprint_progress": {},
        "research_state": {},
        "research_action_plan": {},
    }
    artifacts.update(artifact_overrides)
    return pfd.build_policy_filter_diagnostics_payload(
        artifacts=artifacts,
        artifact_status=_statuses(),
        generated_at_utc=datetime(2026, 5, 22, 12, 0, tzinfo=UTC),
    )


def _row(payload: dict, diagnostic_id: str) -> dict:
    return next(
        row for row in payload["diagnostics"] if row["diagnostic_id"] == diagnostic_id
    )


def test_no_candidates_idle_reports_counts_and_r8_status() -> None:
    payload = _payload(_policy(candidates=[]))

    assert payload["policy_summary"]["action"] == "idle_noop"
    assert payload["policy_summary"]["reason"] == "no_candidates"
    assert payload["policy_summary"]["candidates_considered_count"] == 0
    assert payload["policy_summary"]["r4_r7"]["surviving"] == 0
    assert payload["policy_summary"]["r8_idle"]["result"] == "fire"
    assert _row(payload, "no_eligible_template")["status"] == "explained"
    assert payload["primary_explanations"] == ["no_eligible_template"]


def test_rejection_reasons_are_grouped_into_policy_filter_categories() -> None:
    payload = _payload(
        _policy(
            candidates=[
                _rejected("budget"),
                _rejected("daily_cap_reached"),
                _rejected("duplicate_forbidden"),
                _rejected("preset_disabled"),
                _rejected("family_frozen:trend"),
            ]
        )
    )

    categories = payload["candidate_rejection_summary"]["by_category"]
    assert categories["budget_cap"] == 2
    assert categories["duplicate_fingerprint"] == 1
    assert categories["family_preset_policy_block"] == 2
    assert _row(payload, "budget_cap")["status"] == "explained"
    assert _row(payload, "family_preset_policy_block")["count"] == 2


def test_single_worker_block_is_explained_from_r3_and_decision() -> None:
    payload = _payload(
        _policy(action="idle_noop", reason="worker_busy", candidates=[], r3_result="block")
    )

    assert _row(payload, "single_worker_block")["status"] == "explained"
    assert _row(payload, "single_worker_block")["count"] == 1
    assert payload["primary_explanations"] == ["single_worker_block"]


def test_sprint_routing_exclusion_uses_routing_sidecar_counts() -> None:
    payload = _payload(
        _policy(candidates=[]),
        sprint_routing_decision={
            "routing_active": True,
            "counts": {
                "templates_total": 20,
                "templates_filtered": 15,
                "followups_filtered": 1,
                "weekly_controls_filtered": 0,
            },
            "sprint": {"profile_name": "crypto_exploratory_v1"},
        },
    )

    assert payload["routing_summary"]["filtered_count"] == 16
    assert _row(payload, "sprint_routing_exclusion")["status"] == "explained"
    assert payload["primary_explanations"][0] == "sprint_routing_exclusion"


def test_queue_registry_terminal_state_effect_is_reported() -> None:
    payload = _payload(
        _policy(candidates=[]),
        campaign_registry={
            "campaigns": {"col-1": {"campaign_id": "col-1", "state": "completed"}}
        },
        campaign_queue={"queue": [{"campaign_id": "col-1", "state": "completed"}]},
    )

    summary = payload["registry_queue_summary"]
    assert summary["terminal_state_effect"] == "terminal_only_no_active_work"
    assert _row(payload, "queue_registry_terminal_state_effect")["status"] == "explained"


def test_missing_policy_artifact_falls_back_to_controlled_eval_and_cli(
    tmp_path: Path,
) -> None:
    statuses = _statuses()
    statuses["policy_decision"]["status"] = "missing"
    payload = pfd.build_policy_filter_diagnostics_payload(
        artifacts={
            "policy_decision": None,
            "controlled_eval": {
                "latest_policy_action": "idle_noop",
                "latest_policy_reason": "no_candidates",
                "latest_policy_candidates_considered_count": 0,
                "latest_policy_rules_summary": {
                    "R4_R7_filtering": {
                        "result": "candidates",
                        "surviving": 0,
                        "rejected": 0,
                    },
                    "R8_idle": {"result": "fire"},
                },
            },
            "campaign_registry": {},
            "campaign_queue": {},
            "campaign_evidence_ledger": [],
            "sprint_routing_decision": {},
            "discovery_sprint_progress": {},
            "research_state": {},
            "research_action_plan": {},
        },
        artifact_status=statuses,
        generated_at_utc=datetime(2026, 5, 22, 12, 0, tzinfo=UTC),
    )

    assert payload["policy_summary"]["action"] == "idle_noop"
    assert payload["policy_summary"]["reason"] == "no_candidates"

    rc = pfd.main(
        [
            "--from-current-artifacts",
            "--report-json",
            str(tmp_path / "policy.json"),
            "--report-md",
            str(tmp_path / "policy.md"),
        ]
    )

    assert rc == 0
    written = json.loads((tmp_path / "policy.json").read_text(encoding="utf-8"))
    assert written["schema_version"] == "1.0"
    assert (tmp_path / "policy.md").exists()
