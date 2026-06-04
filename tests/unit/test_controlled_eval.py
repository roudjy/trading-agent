"""Tests for research.controlled_eval (v3.16.x-eval harness)."""

from __future__ import annotations

import json
import subprocess
from datetime import UTC, datetime
from pathlib import Path

import pytest

from research import controlled_eval as ce


def _sprint_registry() -> dict:
    return {
        "sprint_id": "sprt-test",
        "state": "active",
        "started_at_utc": "2026-05-22T10:00:00Z",
        "profile": {"name": "crypto_exploratory_v1"},
        "plan": {
            "entries": [
                {"preset_name": "trend_pullback_crypto_1h"},
                {"preset_name": "vol_compression_breakout_crypto_1h"},
            ]
        },
    }


def _completed_campaign(
    *,
    campaign_id: str = "col-1",
    outcome: str = "degenerate_no_survivors",
    reason_code: str = "degenerate_no_evaluable_pairs",
    meaningful: str | None = "meaningful_failure_confirmed",
) -> dict:
    return {
        "campaign_id": campaign_id,
        "preset_name": "trend_pullback_crypto_1h",
        "state": "completed",
        "outcome": outcome,
        "reason_code": reason_code,
        "meaningful_classification": meaningful,
        "spawned_at_utc": "2026-05-22T10:01:00Z",
        "finished_at_utc": "2026-05-22T10:05:00Z",
        "extra": {"sprint_id": "sprt-test"},
    }


def _registry(record: dict | None = None) -> dict:
    return {"campaigns": {record["campaign_id"]: record} if record else {}}


def _idle_no_candidates_policy() -> dict:
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


def _ledger_event(
    *,
    campaign_id: str = "col-1",
    meaningful: str = "meaningful_failure_confirmed",
) -> dict:
    return {
        "campaign_id": campaign_id,
        "event_type": "campaign_completed",
        "outcome": "degenerate_no_survivors",
        "meaningful_classification": meaningful,
    }


def test_report_summarization_from_fake_payloads() -> None:
    payload = ce.build_report_payload(
        profile="crypto_exploratory_v1",
        max_campaigns=3,
        sprint_started_by_harness=False,
        sprint_reused=True,
        observed_total_before=1,
        observed_total_after=2,
        campaigns_attempted=1,
        sprint_registry=_sprint_registry(),
        sprint_progress={"state": "active"},
        registry=_registry(_completed_campaign()),
        ledger_events=[_ledger_event()],
        run_campaign_payload={
            "run_id": "run-1",
            "status": "completed",
            "summary": {
                "screening_rejected_count": 4,
                "validation_candidate_count": 0,
            },
        },
        intelligence_artifact_status={
            "information_gain": "present",
            "viability": "present",
            "stop_conditions": "present",
            "spawn_proposals": "present",
        },
        latest_policy_decision_payload=None,
        queue_payload={"queue": []},
        ticks=[],
        generated_at_utc=datetime(2026, 5, 22, 12, 0, tzinfo=UTC),
    )

    assert payload["schema_version"] == "1.0"
    assert payload["sprint_id"] == "sprt-test"
    assert payload["sprint_reused"] is True
    assert payload["observed_total_before"] == 1
    assert payload["observed_total_after"] == 2
    assert payload["campaigns_completed"] == 1
    assert payload["campaigns_by_preset"] == {"trend_pullback_crypto_1h": 1}
    assert payload["campaigns_by_outcome"] == {"degenerate_no_survivors": 1}
    assert payload["latest_run_summary"]["run_id"] == "run-1"
    assert payload["latest_run_summary"]["screening_rejected_count"] == 4




def test_report_includes_screening_evidence_summary_linkage_counters() -> None:
    payload = ce.build_report_payload(
        profile="equities_exploratory_v1",
        max_campaigns=1,
        sprint_started_by_harness=True,
        sprint_reused=False,
        observed_total_before=0,
        observed_total_after=1,
        campaigns_attempted=1,
        sprint_registry=_sprint_registry(),
        sprint_progress={"state": "active"},
        registry=_registry(_completed_campaign()),
        ledger_events=[_ledger_event()],
        run_campaign_payload={
            "run_id": "run-1",
            "status": "completed",
            "summary": {
                "screening_rejected_count": 9,
                "validation_candidate_count": 6,
            },
        },
        screening_evidence_payload={
            "summary": {
                "total_candidates": 15,
                "passed_screening": 6,
                "rejected_screening": 9,
                "promotion_grade_candidates": 0,
                "sufficient_oos_evidence_candidates": 1,
                "qre_linkage_blocked_candidates": 1,
                "sufficient_oos_but_unlinked_candidates": 1,
            }
        },
        latest_policy_decision_payload=None,
        queue_payload={"queue": []},
        intelligence_artifact_status={
            "information_gain": "present",
            "viability": "present",
            "stop_conditions": "present",
            "spawn_proposals": "present",
        },
        ticks=[],
    )

    assert payload["screening_evidence_summary"] == {
        "present": True,
        "total_candidates": 15,
        "passed_screening": 6,
        "rejected_screening": 9,
        "promotion_grade_candidates": 0,
        "sufficient_oos_evidence_candidates": 1,
        "qre_linkage_blocked_candidates": 1,
        "sufficient_oos_but_unlinked_candidates": 1,
    }


def test_degenerate_no_survivors_is_useful_meaningful_failure() -> None:
    payload = ce.build_report_payload(
        profile="crypto_exploratory_v1",
        max_campaigns=1,
        sprint_started_by_harness=True,
        sprint_reused=False,
        observed_total_before=0,
        observed_total_after=1,
        campaigns_attempted=1,
        sprint_registry=_sprint_registry(),
        sprint_progress={"state": "active"},
        registry=_registry(_completed_campaign()),
        ledger_events=[_ledger_event()],
        run_campaign_payload=None,
        intelligence_artifact_status={
            "information_gain": "present",
            "viability": "present",
            "stop_conditions": "present",
            "spawn_proposals": "present",
        },
        latest_policy_decision_payload=None,
        queue_payload={"queue": []},
        ticks=[],
    )

    assert payload["verdict"]["status"] == "useful_observation"
    assert "degenerate_no_survivors" in payload["verdict"]["reason_codes"]
    assert payload["recommended_next_action"] == "stop_due_to_no_survivors"
    assert payload["campaign_records"][0]["meaningful_classification"] == (
        "meaningful_failure_confirmed"
    )


def test_missing_intelligence_artifacts_are_reported_as_observability_gap() -> None:
    payload = ce.build_report_payload(
        profile="crypto_exploratory_v1",
        max_campaigns=1,
        sprint_started_by_harness=True,
        sprint_reused=False,
        observed_total_before=0,
        observed_total_after=1,
        campaigns_attempted=1,
        sprint_registry=_sprint_registry(),
        sprint_progress={"state": "active"},
        registry=_registry(_completed_campaign()),
        ledger_events=[_ledger_event()],
        run_campaign_payload=None,
        intelligence_artifact_status={
            "information_gain": "missing",
            "viability": "missing",
            "stop_conditions": "missing",
            "spawn_proposals": "missing",
        },
        latest_policy_decision_payload=None,
        queue_payload={"queue": []},
        ticks=[],
    )

    assert payload["verdict"]["status"] == "useful_observation"
    assert "missing_intelligence_artifacts" in payload["verdict"]["reason_codes"]
    assert payload["recommended_next_action"] == "inspect_failure_observability"
    assert payload["intelligence_artifact_status"]["information_gain"] == "missing"


def test_no_completed_campaign_with_no_candidates_policy_is_diagnostic() -> None:
    payload = ce.build_report_payload(
        profile="crypto_exploratory_v1",
        max_campaigns=3,
        sprint_started_by_harness=False,
        sprint_reused=True,
        observed_total_before=0,
        observed_total_after=0,
        campaigns_attempted=3,
        sprint_registry=_sprint_registry(),
        sprint_progress={"state": "active"},
        registry=_registry(),
        ledger_events=[],
        run_campaign_payload=None,
        latest_policy_decision_payload=_idle_no_candidates_policy(),
        queue_payload={
            "queue": [
                {"campaign_id": "old-done", "state": "completed"},
                {"campaign_id": "old-failed", "state": "failed"},
            ]
        },
        intelligence_artifact_status={
            "information_gain": "missing",
            "viability": "missing",
            "stop_conditions": "missing",
            "spawn_proposals": "missing",
        },
        ticks=[
            ce.LauncherTick(
                tick_index=1,
                returncode=0,
                timed_out=False,
                elapsed_seconds=0,
                stdout_tail="",
                stderr_tail="",
                completed_campaign_ids=(),
            )
        ],
    )

    assert payload["campaigns_completed"] == 0
    assert payload["latest_policy_decision_present"] is True
    assert payload["latest_policy_action"] == "idle_noop"
    assert payload["latest_policy_reason"] == "no_candidates"
    assert payload["latest_policy_candidates_considered_count"] == 0
    assert payload["latest_policy_rules_summary"]["R4_R7_filtering"]["surviving"] == 0
    assert payload["latest_policy_rules_summary"]["R4_R7_filtering"]["rejected"] == 7
    assert payload["latest_policy_rules_summary"]["R8_idle"]["result"] == "fire"
    assert payload["active_campaign_count"] == 0
    assert payload["queue_item_count"] == 2
    assert payload["queue_active_count"] == 0
    assert payload["queue_terminal_count"] == 2
    assert payload["verdict"]["status"] == "no_campaign_completed"
    assert "no_candidates_policy_block" in payload["verdict"]["reason_codes"]
    assert payload["recommended_next_action"] == "inspect_campaign_policy_filters"

    markdown = ce.render_markdown_report(payload)
    assert "- Latest launcher decision: idle_noop / no_candidates" in markdown
    assert "- Candidates considered: 0" in markdown
    assert "- R4_R7 surviving: 0" in markdown
    assert "- Active campaigns: 0" in markdown
    assert "- Policy/no-candidate condition, not a running campaign: True" in markdown


def test_active_campaign_count_includes_nonterminal_registry_records() -> None:
    registry = {
        "campaigns": {
            "col-leased": {
                "campaign_id": "col-leased",
                "preset_name": "trend_pullback_crypto_1h",
                "state": "leased",
                "spawned_at_utc": "2026-05-22T10:01:00Z",
                "extra": {"sprint_id": "sprt-test"},
            },
            "col-running": {
                "campaign_id": "col-running",
                "preset_name": "trend_pullback_crypto_1h",
                "state": "running",
                "spawned_at_utc": "2026-05-22T10:02:00Z",
                "extra": {"sprint_id": "sprt-test"},
            },
            "col-completed": _completed_campaign(campaign_id="col-completed"),
        }
    }
    payload = ce.build_report_payload(
        profile="crypto_exploratory_v1",
        max_campaigns=3,
        sprint_started_by_harness=False,
        sprint_reused=True,
        observed_total_before=0,
        observed_total_after=0,
        campaigns_attempted=1,
        sprint_registry=_sprint_registry(),
        sprint_progress={"state": "active"},
        registry=registry,
        ledger_events=[],
        run_campaign_payload=None,
        latest_policy_decision_payload=None,
        queue_payload={
            "queue": [
                {"campaign_id": "col-leased", "state": "leased"},
                {"campaign_id": "col-running", "state": "running"},
                {"campaign_id": "old-failed", "state": "failed"},
            ]
        },
        intelligence_artifact_status={
            "information_gain": "present",
            "viability": "present",
            "stop_conditions": "present",
            "spawn_proposals": "present",
        },
        ticks=[],
    )

    assert payload["active_campaign_count"] == 2
    assert payload["active_campaign_ids"] == ["col-leased", "col-running"]
    assert payload["queue_item_count"] == 3
    assert payload["queue_active_count"] == 2
    assert payload["queue_terminal_count"] == 1


def test_missing_policy_decision_is_handled_gracefully() -> None:
    payload = ce.build_report_payload(
        profile="crypto_exploratory_v1",
        max_campaigns=1,
        sprint_started_by_harness=True,
        sprint_reused=False,
        observed_total_before=0,
        observed_total_after=0,
        campaigns_attempted=1,
        sprint_registry=_sprint_registry(),
        sprint_progress={"state": "active"},
        registry=_registry(),
        ledger_events=[],
        run_campaign_payload=None,
        latest_policy_decision_payload=None,
        queue_payload=None,
        intelligence_artifact_status={
            "information_gain": "missing",
            "viability": "missing",
            "stop_conditions": "missing",
            "spawn_proposals": "missing",
        },
        ticks=[],
    )

    assert payload["latest_policy_decision_present"] is False
    assert payload["latest_policy_action"] is None
    assert payload["latest_policy_reason"] is None
    assert payload["latest_policy_candidates_considered_count"] == 0
    assert payload["latest_policy_rules_summary"] == {}
    assert payload["verdict"]["status"] == "no_campaign_completed"
    assert payload["verdict"]["reason_codes"] == ["no_campaign_completed"]
    assert payload["recommended_next_action"] == "rerun_with_more_campaigns"


def test_max_campaigns_cap_is_enforced(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    calls: list[int] = []

    def fake_tick(**kwargs):
        calls.append(int(kwargs["tick_index"]))
        return ce.LauncherTick(
            tick_index=int(kwargs["tick_index"]),
            returncode=0,
            timed_out=False,
            elapsed_seconds=0,
            stdout_tail="",
            stderr_tail="",
            completed_campaign_ids=(),
        )

    monkeypatch.setattr(ce, "_ensure_active_sprint", lambda _profile: (True, False))
    monkeypatch.setattr(ce.ds, "update_sprint_progress", lambda: None)
    monkeypatch.setattr(
        ce.ds,
        "load_sprint_progress",
        lambda: {"observed_total": 0, "state": "active"},
    )
    monkeypatch.setattr(ce.ds, "load_sprint_registry", _sprint_registry)
    monkeypatch.setattr(ce, "load_registry", lambda _path: {"campaigns": {}})
    monkeypatch.setattr(ce, "load_queue", lambda _path: {"queue": []})
    monkeypatch.setattr(ce, "load_events", lambda _path: [])
    monkeypatch.setattr(ce, "_read_json", lambda _path: None)
    monkeypatch.setattr(
        ce,
        "build_intelligence_artifact_status",
        lambda: {
            "information_gain": "missing",
            "viability": "missing",
            "stop_conditions": "missing",
            "spawn_proposals": "missing",
        },
    )
    monkeypatch.setattr(ce, "_run_launcher_tick", fake_tick)

    rc = ce.run_controlled_eval(
        profile="crypto_exploratory_v1",
        max_campaigns=2,
        timeout_seconds_per_campaign=60,
        poll_seconds=0,
        report_json=tmp_path / "controlled.json",
        report_md=tmp_path / "controlled.md",
    )

    assert rc == 0
    assert calls == [1, 2]
    report = json.loads((tmp_path / "controlled.json").read_text(encoding="utf-8"))
    assert report["campaigns_attempted"] == 2
    assert report["verdict"]["status"] == "no_campaign_completed"


def test_cli_smoke_with_mocked_launcher_invocation(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    launcher_calls: list[list[str]] = []

    def fake_subprocess_run(args, **kwargs):
        launcher_calls.append(list(args))
        return subprocess.CompletedProcess(args=args, returncode=0, stdout="", stderr="")

    monkeypatch.setattr(ce, "_ensure_active_sprint", lambda _profile: (False, True))
    monkeypatch.setattr(ce.ds, "update_sprint_progress", lambda: None)
    monkeypatch.setattr(
        ce.ds,
        "load_sprint_progress",
        lambda: {"observed_total": 0, "state": "active"},
    )
    monkeypatch.setattr(ce.ds, "load_sprint_registry", _sprint_registry)
    monkeypatch.setattr(ce, "load_registry", lambda _path: {"campaigns": {}})
    monkeypatch.setattr(ce, "load_queue", lambda _path: {"queue": []})
    monkeypatch.setattr(ce, "load_events", lambda _path: [])
    monkeypatch.setattr(ce, "_read_json", lambda _path: None)
    monkeypatch.setattr(
        ce,
        "build_intelligence_artifact_status",
        lambda: {
            "information_gain": "missing",
            "viability": "missing",
            "stop_conditions": "missing",
            "spawn_proposals": "missing",
        },
    )
    monkeypatch.setattr(ce.subprocess, "run", fake_subprocess_run)

    rc = ce.main(
        [
            "--profile",
            "crypto_exploratory_v1",
            "--max-campaigns",
            "1",
            "--timeout-seconds-per-campaign",
            "60",
            "--poll-seconds",
            "0",
            "--report-json",
            str(tmp_path / "controlled.json"),
            "--report-md",
            str(tmp_path / "controlled.md"),
        ]
    )

    assert rc == 0
    assert launcher_calls == [[ce.sys.executable, "-m", "research.campaign_launcher"]]
    assert (tmp_path / "controlled.json").exists()
    assert (tmp_path / "controlled.md").exists()

def test_launcher_invariant_violation_is_technical_failure() -> None:
    payload = ce.build_report_payload(
        profile="equities_exploratory_v1",
        max_campaigns=1,
        sprint_started_by_harness=True,
        sprint_reused=False,
        observed_total_before=0,
        observed_total_after=0,
        campaigns_attempted=1,
        sprint_registry={},
        sprint_progress={},
        registry={},
        ledger_events=[],
        run_campaign_payload={},
        latest_policy_decision_payload={
            "action": "spawn",
            "reason": "cron_tick",
            "candidates_considered": [{"id": "candidate-1"}],
            "rules_summary": {
                "R4_R7_filtering": {
                    "result": "candidates",
                    "surviving": 1,
                    "rejected": 0,
                }
            },
        },
        queue_payload={"items": [{"state": "terminal"}]},
        intelligence_artifact_status={
            "information_gain": "missing",
            "viability": "missing",
            "stop_conditions": "missing",
            "spawn_proposals": "missing",
        },
        ticks=[
            ce.LauncherTick(
                tick_index=1,
                returncode=2,
                timed_out=False,
                elapsed_seconds=1,
                stdout_tail="",
                stderr_tail=(
                    "campaign invariant violation: I5 violation: completed campaign "
                    "'col-example' lacks campaign_completed ledger event"
                ),
                completed_campaign_ids=(),
            )
        ],
    )

    assert payload["campaigns_completed"] == 0
    assert payload["campaign_level_evidence_valid"] is False
    assert payload["verdict"]["status"] == "technical_failure"
    assert "launcher_invariant_violation" in payload["verdict"]["reason_codes"]
    assert payload["recommended_next_action"] == "operator_review_required"
    assert payload["launcher_ticks"][0]["returncode"] == 2
    assert "campaign invariant violation" in payload["launcher_ticks"][0]["stderr_tail"]

    markdown = ce.render_markdown_report(payload)
    assert "technical_failure" in markdown
    assert "launcher_invariant_violation" in markdown

