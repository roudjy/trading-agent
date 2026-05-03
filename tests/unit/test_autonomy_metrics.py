"""Unit tests for ``reporting.autonomy_metrics``.

Properties enforced:

* Empty / missing artifacts produce ``not_available`` /
  ``degraded_*`` recommendations, never crash.
* Malformed artifacts are counted under ``reliability``.
* Output is deterministic for a fixed input set
  (byte-identical when ``--frozen-utc`` is used).
* Throughput / operator-burden / reliability / safety counters
  reflect their inputs.
* ``high_or_unknown_executable_count`` is 0 for safe inputs and
  non-zero when execute-safe lists a HIGH/UNKNOWN action as
  ``eligible``; the latter flips ``final_recommendation`` to
  ``unsafe_state_detected``.
* History trend windows return ``not_available`` when no
  history file exists, and ``ok`` aggregates when it does.
* Atomic write: ``latest.json`` is byte-identical to the
  timestamped copy of the same run.
* History append-only: a new run extends ``history.jsonl``
  rather than overwriting.
* Credential-shaped values in upstream artifacts trip the guard.
* ``source_statuses`` always includes one row per source, in
  canonical order.
* The CLI never accepts free-form command flags.
* No mutation routes / no forbidden tokens in the module.
* The status surface includes the metrics block when wired.
* Frozen contract paths are unchanged by collection.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from reporting import autonomy_metrics as am


REPO_ROOT = Path(__file__).resolve().parent.parent.parent


# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------


@pytest.fixture
def isolated_dirs(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    """Redirect every source artifact path + the digest dir into
    ``tmp_path`` so the test never touches real artifacts."""
    monkeypatch.setattr(am, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(am, "DIGEST_DIR_JSON", tmp_path / "logs" / "autonomy_metrics")
    monkeypatch.setattr(
        am,
        "SOURCE_WORKLOOP_RUNTIME",
        tmp_path / "logs" / "workloop_runtime" / "latest.json",
    )
    monkeypatch.setattr(
        am,
        "SOURCE_WORKLOOP_RUNTIME_HISTORY",
        tmp_path / "logs" / "workloop_runtime" / "history.jsonl",
    )
    monkeypatch.setattr(
        am,
        "SOURCE_RECURRING_MAINTENANCE",
        tmp_path / "logs" / "recurring_maintenance" / "latest.json",
    )
    monkeypatch.setattr(
        am,
        "SOURCE_RECURRING_MAINTENANCE_HISTORY",
        tmp_path / "logs" / "recurring_maintenance" / "history.jsonl",
    )
    monkeypatch.setattr(
        am,
        "SOURCE_PROPOSAL_QUEUE",
        tmp_path / "logs" / "proposal_queue" / "latest.json",
    )
    monkeypatch.setattr(
        am,
        "SOURCE_APPROVAL_INBOX",
        tmp_path / "logs" / "approval_inbox" / "latest.json",
    )
    monkeypatch.setattr(
        am,
        "SOURCE_PR_LIFECYCLE",
        tmp_path / "logs" / "github_pr_lifecycle" / "latest.json",
    )
    monkeypatch.setattr(
        am,
        "SOURCE_EXECUTE_SAFE_CONTROLS",
        tmp_path / "logs" / "execute_safe_controls" / "latest.json",
    )
    return tmp_path


def _write(p: Path, payload: dict[str, Any]) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(payload), encoding="utf-8")


def _ok_workloop_runtime() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "report_kind": "workloop_runtime_digest",
        "module_version": "v3.15.15.22",
        "generated_at_utc": "2026-05-03T07:00:00Z",
        "mode": "once",
        "iteration": 0,
        "max_iterations": 1,
        "duration_ms": 100,
        "safe_to_execute": False,
        "loop_health": {
            "consecutive_failures": 0,
            "iterations_completed": 1,
            "iterations_failed": 0,
            "last_success_utc": "2026-05-03T07:00:00Z",
            "last_failure_utc": None,
        },
        "sources": [
            {"source": "governance_status", "state": "ok"},
            {"source": "approval_inbox", "state": "ok"},
            {"source": "proposal_queue", "state": "ok"},
            {"source": "github_pr_lifecycle", "state": "not_available"},
            {"source": "agent_audit_summary", "state": "ok"},
            {"source": "autonomous_workloop", "state": "ok"},
            {"source": "execute_safe_controls", "state": "ok"},
        ],
        "counts": {
            "by_state": {"ok": 6, "not_available": 1},
            "total": 7,
        },
        "final_recommendation": "all_sources_ok",
    }


def _ok_recurring_maintenance() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "module_version": "v3.15.15.23",
        "generated_at_utc": "2026-05-03T07:00:30Z",
        "mode": "list",
        "safe_to_execute": False,
        "jobs": [
            {"job_type": "refresh_proposal_queue", "last_status": "succeeded", "consecutive_failures": 0, "enabled": True},
            {"job_type": "refresh_approval_inbox", "last_status": "succeeded", "consecutive_failures": 0, "enabled": True},
            {"job_type": "refresh_github_pr_lifecycle_dry_run", "last_status": "blocked", "consecutive_failures": 1, "enabled": True},
            {"job_type": "refresh_workloop_runtime_once", "last_status": "succeeded", "consecutive_failures": 0, "enabled": True},
            {"job_type": "dependabot_low_medium_execute_safe", "last_status": "skipped", "consecutive_failures": 0, "enabled": False},
        ],
        "counts": {
            "total": 5,
            "by_status": {"succeeded": 3, "blocked": 1, "skipped": 1},
        },
        "final_recommendation": "all_jobs_ok",
    }


def _ok_proposal_queue() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "module_version": "v3.15.15.19",
        "generated_at_utc": "2026-05-03T07:01:00Z",
        "proposals": [],
        "counts": {
            "total": 4,
            "by_status": {"proposed": 3, "needs_human": 1},
            "by_risk": {"LOW": 2, "MEDIUM": 1, "HIGH": 1},
            "by_type": {"observability_gap": 2, "ci_hygiene": 2},
        },
        "final_recommendation": "needs_human_on_1_items",
    }


def _ok_approval_inbox() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "module_version": "v3.15.15.20",
        "generated_at_utc": "2026-05-03T07:01:30Z",
        "items": [
            {"category": "high_risk_pr", "severity": "high"},
            {"category": "tooling_requires_approval", "severity": "medium"},
            {"category": "manual_route_wiring_required", "severity": "low"},
        ],
        "counts": {
            "total": 3,
            "by_category": {
                "high_risk_pr": 1,
                "tooling_requires_approval": 1,
                "manual_route_wiring_required": 1,
            },
            "by_severity": {"high": 1, "medium": 1, "low": 1},
        },
    }


def _ok_pr_lifecycle() -> dict[str, Any]:
    return {
        "schema_version": 1,
        "module_version": "v3.15.15.17",
        "generated_at_utc": "2026-05-03T07:02:00Z",
        "prs": [
            {"decision": "merge_allowed"},
            {"decision": "blocked_high_risk"},
            {"decision": "wait_for_rebase"},
        ],
        "final_recommendation": "ok",
    }


def _ok_execute_safe_controls(*, leak_high_eligible: bool = False) -> dict[str, Any]:
    actions = [
        {"action_type": "refresh_pr_lifecycle", "risk_class": "LOW", "eligibility": "eligible"},
        {"action_type": "refresh_proposal_queue", "risk_class": "LOW", "eligibility": "eligible"},
        {"action_type": "refresh_approval_inbox", "risk_class": "LOW", "eligibility": "eligible"},
        {"action_type": "run_dependabot_execute_safe", "risk_class": "MEDIUM", "eligibility": "blocked"},
    ]
    if leak_high_eligible:
        actions.append(
            {"action_type": "fake_high", "risk_class": "HIGH", "eligibility": "eligible"}
        )
    return {
        "schema_version": 1,
        "module_version": "v3.15.15.21",
        "generated_at_utc": "2026-05-03T07:02:30Z",
        "actions": actions,
        "counts": {
            "total": len(actions),
            "by_eligibility": {
                "eligible": sum(1 for a in actions if a["eligibility"] == "eligible"),
                "blocked": sum(1 for a in actions if a["eligibility"] == "blocked"),
            },
            "by_risk_class": {
                "LOW": sum(1 for a in actions if a["risk_class"] == "LOW"),
                "MEDIUM": sum(1 for a in actions if a["risk_class"] == "MEDIUM"),
                "HIGH": sum(1 for a in actions if a["risk_class"] == "HIGH"),
            },
        },
    }


def _write_all_ok(tmp_path: Path) -> None:
    _write(tmp_path / "logs" / "workloop_runtime" / "latest.json", _ok_workloop_runtime())
    _write(tmp_path / "logs" / "recurring_maintenance" / "latest.json", _ok_recurring_maintenance())
    _write(tmp_path / "logs" / "proposal_queue" / "latest.json", _ok_proposal_queue())
    _write(tmp_path / "logs" / "approval_inbox" / "latest.json", _ok_approval_inbox())
    _write(tmp_path / "logs" / "github_pr_lifecycle" / "latest.json", _ok_pr_lifecycle())
    _write(tmp_path / "logs" / "execute_safe_controls" / "latest.json", _ok_execute_safe_controls())


# ---------------------------------------------------------------------------
# Module-level invariants
# ---------------------------------------------------------------------------


def test_module_version_is_v3_15_15_25() -> None:
    assert am.MODULE_VERSION == "v3.15.15.25"


def test_metrics_version_is_v1() -> None:
    assert am.METRICS_VERSION == "v1"


def test_schema_version_is_1() -> None:
    assert am.SCHEMA_VERSION == 1


def test_source_order_is_six_items_in_canonical_order() -> None:
    names = [n for n, _ in am.SOURCE_ORDER]
    assert names == [
        "workloop_runtime",
        "recurring_maintenance",
        "proposal_queue",
        "approval_inbox",
        "github_pr_lifecycle",
        "execute_safe_controls",
    ]


def test_no_subprocess_or_network_imports_in_module() -> None:
    src = Path(am.__file__).read_text(encoding="utf-8")
    forbidden = (
        "import subprocess",
        "from subprocess",
        "Popen(",
        "import requests",
        "import urllib.request",
        "from urllib.request",
        "import socket",
    )
    for token in forbidden:
        assert token not in src, f"forbidden import in autonomy_metrics: {token!r}"


def test_no_gh_or_git_invocation_in_module() -> None:
    src = Path(am.__file__).read_text(encoding="utf-8")
    forbidden = ('"gh"', "'gh'", "/usr/bin/gh", '"git"', "'git'", "/usr/bin/git")
    for token in forbidden:
        assert token not in src, f"forbidden tool spawn: {token!r}"


# ---------------------------------------------------------------------------
# Empty / missing source semantics
# ---------------------------------------------------------------------------


def test_collect_with_no_artifacts_returns_not_available(isolated_dirs) -> None:
    snap = am.collect_snapshot(frozen_utc="2026-05-03T08:00:00Z")
    # Every source row reports missing.
    states = [s["state"] for s in snap["source_statuses"]]
    assert all(st == am.STATE_MISSING for st in states), states
    assert snap["final_recommendation"] == am.REC_NOT_AVAILABLE
    # safe_to_execute is hard-coded false.
    assert snap["safe_to_execute"] is False


def test_collect_with_some_artifacts_missing_reports_degraded(isolated_dirs) -> None:
    # Provide only proposal_queue + approval_inbox; others missing.
    _write(isolated_dirs / "logs" / "proposal_queue" / "latest.json", _ok_proposal_queue())
    _write(isolated_dirs / "logs" / "approval_inbox" / "latest.json", _ok_approval_inbox())
    snap = am.collect_snapshot(frozen_utc="2026-05-03T08:00:00Z")
    # 4 sources missing => degraded_missing_sources.
    assert snap["final_recommendation"] in (
        am.REC_DEGRADED_MISSING,
        am.REC_ACTION_REQUIRED,
    )
    # Reliability counts the missing.
    assert snap["reliability"]["missing_artifact_count"] >= 2


def test_malformed_artifact_is_counted(isolated_dirs) -> None:
    p = isolated_dirs / "logs" / "workloop_runtime" / "latest.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("{not json", encoding="utf-8")
    _write_all_ok_excluding_runtime = lambda: None  # noqa: E731 — placeholder
    _write(isolated_dirs / "logs" / "recurring_maintenance" / "latest.json", _ok_recurring_maintenance())
    _write(isolated_dirs / "logs" / "proposal_queue" / "latest.json", _ok_proposal_queue())
    _write(isolated_dirs / "logs" / "approval_inbox" / "latest.json", _ok_approval_inbox())
    _write(isolated_dirs / "logs" / "github_pr_lifecycle" / "latest.json", _ok_pr_lifecycle())
    _write(isolated_dirs / "logs" / "execute_safe_controls" / "latest.json", _ok_execute_safe_controls())
    snap = am.collect_snapshot(frozen_utc="2026-05-03T08:00:00Z")
    assert snap["reliability"]["malformed_artifact_count"] >= 1
    states = [s["state"] for s in snap["source_statuses"] if s["source"] == "workloop_runtime"]
    assert states == [am.STATE_MALFORMED]


def test_array_top_level_artifact_is_not_an_object(isolated_dirs) -> None:
    p = isolated_dirs / "logs" / "approval_inbox" / "latest.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text("[1, 2, 3]", encoding="utf-8")
    _write(isolated_dirs / "logs" / "workloop_runtime" / "latest.json", _ok_workloop_runtime())
    snap = am.collect_snapshot(frozen_utc="2026-05-03T08:00:00Z")
    states = [s["state"] for s in snap["source_statuses"] if s["source"] == "approval_inbox"]
    assert states == [am.STATE_NOT_AN_OBJECT]


# ---------------------------------------------------------------------------
# Throughput counters
# ---------------------------------------------------------------------------


def test_throughput_counts_match_inputs(isolated_dirs) -> None:
    _write_all_ok(isolated_dirs)
    snap = am.collect_snapshot(frozen_utc="2026-05-03T08:00:00Z")
    t = snap["throughput"]
    assert t["proposals_total"] == 4
    assert t["proposals_by_status"] == {"needs_human": 1, "proposed": 3}
    assert t["proposals_by_risk"] == {"HIGH": 1, "LOW": 2, "MEDIUM": 1}
    assert t["inbox_items_total"] == 3
    assert t["pr_lifecycle_prs_seen"] == 3
    assert t["pr_lifecycle_merge_allowed"] == 1
    assert t["pr_lifecycle_blocked"] == 1
    assert t["pr_lifecycle_wait_for_rebase"] == 1
    assert t["recurring_jobs_total"] == 5
    assert t["recurring_jobs_succeeded"] == 3
    assert t["recurring_jobs_blocked"] == 1
    assert t["recurring_jobs_skipped"] == 1
    assert t["runtime_sources_total"] == 7
    assert t["runtime_sources_ok"] == 6
    assert t["runtime_sources_degraded"] == 1
    assert t["execute_safe_actions_total"] == 4


def test_operator_burden_counts_aggregate_across_sources(isolated_dirs) -> None:
    _write_all_ok(isolated_dirs)
    snap = am.collect_snapshot(frozen_utc="2026-05-03T08:00:00Z")
    b = snap["operator_burden"]
    # 1 needs_human in proposal_queue, 0 in pr_lifecycle decisions.
    assert b["needs_human_total"] == 1
    # blocked_total: proposals=0 + pr_lifecycle=1.
    assert b["blocked_total"] == 1
    assert b["high_risk_blocked_total"] == 1
    assert b["approval_required_total"] == 1
    assert b["manual_route_wiring_required_total"] == 1
    assert b["estimated_operator_actions_total"] == (
        b["needs_human_total"]
        + b["blocked_total"]
        + b["approval_required_total"]
        + b["manual_route_wiring_required_total"]
        + b["high_risk_blocked_total"]
        + b["unknown_state_total"]
    )
    assert isinstance(b["top_operator_action_categories"], list)


def test_reliability_counts(isolated_dirs) -> None:
    _write_all_ok(isolated_dirs)
    snap = am.collect_snapshot(frozen_utc="2026-05-03T08:00:00Z")
    r = snap["reliability"]
    assert r["runtime_consecutive_failures"] == 0
    assert r["recurring_consecutive_failures_max"] == 1
    # No missing artifacts in the all-ok scenario.
    assert r["missing_artifact_count"] == 0
    assert r["malformed_artifact_count"] == 0
    # 1 not_available in the runtime sources -> failure_rate > 0.
    assert r["source_failure_rate"] > 0
    assert r["last_success_at_utc"] == "2026-05-03T07:00:00Z"


def test_safety_counts_high_or_unknown_executable_is_zero_for_safe_inputs(
    isolated_dirs,
) -> None:
    _write_all_ok(isolated_dirs)
    snap = am.collect_snapshot(frozen_utc="2026-05-03T08:00:00Z")
    assert snap["safety"]["high_or_unknown_executable_count"] == 0
    assert snap["safety"]["summary"] == "ok"


def test_safety_detects_high_eligible_action(isolated_dirs) -> None:
    """If the execute_safe_controls catalog ever lists a HIGH action
    as ``eligible``, the metrics digest must surface it as
    unsafe_state_detected."""
    _write(isolated_dirs / "logs" / "workloop_runtime" / "latest.json", _ok_workloop_runtime())
    _write(isolated_dirs / "logs" / "recurring_maintenance" / "latest.json", _ok_recurring_maintenance())
    _write(isolated_dirs / "logs" / "proposal_queue" / "latest.json", _ok_proposal_queue())
    _write(isolated_dirs / "logs" / "approval_inbox" / "latest.json", _ok_approval_inbox())
    _write(isolated_dirs / "logs" / "github_pr_lifecycle" / "latest.json", _ok_pr_lifecycle())
    _write(
        isolated_dirs / "logs" / "execute_safe_controls" / "latest.json",
        _ok_execute_safe_controls(leak_high_eligible=True),
    )
    snap = am.collect_snapshot(frozen_utc="2026-05-03T08:00:00Z")
    assert snap["safety"]["high_or_unknown_executable_count"] >= 1
    assert snap["safety"]["summary"] == "unsafe_state_detected"
    assert snap["final_recommendation"] == am.REC_UNSAFE


# ---------------------------------------------------------------------------
# Final recommendation logic
# ---------------------------------------------------------------------------


def test_final_recommendation_healthy_for_clean_inputs(isolated_dirs) -> None:
    # Use a "clean" inbox/proposal set: zero needs_human, zero
    # blocked, zero high_risk, zero unknown.
    inbox = {
        "schema_version": 1,
        "items": [],
        "counts": {"total": 0, "by_category": {}, "by_severity": {}},
    }
    proposals = {
        "schema_version": 1,
        "proposals": [],
        "counts": {
            "total": 0,
            "by_status": {},
            "by_risk": {},
            "by_type": {},
        },
    }
    pr = {"prs": []}
    rt = _ok_workloop_runtime()
    rc = _ok_recurring_maintenance()
    # Clean recurring: no blocked job, all succeeded.
    rc["jobs"] = [
        {"job_type": j["job_type"], "last_status": "succeeded", "consecutive_failures": 0, "enabled": True}
        for j in rc["jobs"]
    ]
    rc["counts"] = {"total": 5, "by_status": {"succeeded": 5}}
    es = _ok_execute_safe_controls()
    _write(isolated_dirs / "logs" / "workloop_runtime" / "latest.json", rt)
    _write(isolated_dirs / "logs" / "recurring_maintenance" / "latest.json", rc)
    _write(isolated_dirs / "logs" / "proposal_queue" / "latest.json", proposals)
    _write(isolated_dirs / "logs" / "approval_inbox" / "latest.json", inbox)
    _write(isolated_dirs / "logs" / "github_pr_lifecycle" / "latest.json", pr)
    _write(isolated_dirs / "logs" / "execute_safe_controls" / "latest.json", es)

    snap = am.collect_snapshot(frozen_utc="2026-05-03T08:00:00Z")
    assert snap["final_recommendation"] == am.REC_HEALTHY


def test_final_recommendation_action_required_when_burden_nonzero(isolated_dirs) -> None:
    _write_all_ok(isolated_dirs)
    snap = am.collect_snapshot(frozen_utc="2026-05-03T08:00:00Z")
    assert snap["final_recommendation"] == am.REC_ACTION_REQUIRED


def test_final_recommendation_degraded_failures_on_three_consecutive_failures(
    isolated_dirs,
) -> None:
    _write_all_ok(isolated_dirs)
    rt = _ok_workloop_runtime()
    rt["loop_health"]["consecutive_failures"] = 3
    _write(isolated_dirs / "logs" / "workloop_runtime" / "latest.json", rt)
    snap = am.collect_snapshot(frozen_utc="2026-05-03T08:00:00Z")
    assert snap["final_recommendation"] == am.REC_DEGRADED_FAILURES


# ---------------------------------------------------------------------------
# Determinism + atomic writes + history
# ---------------------------------------------------------------------------


def test_collect_is_deterministic_with_pinned_utc(isolated_dirs) -> None:
    _write_all_ok(isolated_dirs)
    a = am.collect_snapshot(frozen_utc="2026-05-03T08:00:00Z")
    b = am.collect_snapshot(frozen_utc="2026-05-03T08:00:00Z")
    assert json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)


def test_atomic_write_latest_matches_timestamped(isolated_dirs) -> None:
    _write_all_ok(isolated_dirs)
    snap = am.collect_snapshot(frozen_utc="2026-05-03T08:00:00Z")
    paths = am.write_outputs(snap)
    latest = (isolated_dirs / paths["latest"]).read_bytes()
    timestamped = (isolated_dirs / paths["timestamped"]).read_bytes()
    assert latest == timestamped


def test_history_is_append_only(isolated_dirs) -> None:
    _write_all_ok(isolated_dirs)
    s1 = am.collect_snapshot(frozen_utc="2026-05-03T08:00:00Z")
    am.write_outputs(s1)
    s2 = am.collect_snapshot(frozen_utc="2026-05-03T08:01:00Z")
    am.write_outputs(s2)
    hist = (isolated_dirs / "logs" / "autonomy_metrics" / "history.jsonl").read_text(
        encoding="utf-8"
    )
    lines = [ln for ln in hist.splitlines() if ln.strip()]
    assert len(lines) == 2
    parsed = [json.loads(ln) for ln in lines]
    assert parsed[0]["generated_at_utc"] == "2026-05-03T08:00:00Z"
    assert parsed[1]["generated_at_utc"] == "2026-05-03T08:01:00Z"


def test_read_latest_snapshot_returns_none_on_missing(isolated_dirs) -> None:
    snap = am.read_latest_snapshot()
    assert snap is None


def test_read_latest_snapshot_returns_dict_when_present(isolated_dirs) -> None:
    _write_all_ok(isolated_dirs)
    s = am.collect_snapshot(frozen_utc="2026-05-03T08:00:00Z")
    am.write_outputs(s)
    rt = am.read_latest_snapshot()
    assert isinstance(rt, dict)
    assert rt["report_kind"] == "autonomy_metrics_digest"


# ---------------------------------------------------------------------------
# Trend windows
# ---------------------------------------------------------------------------


def test_trends_not_available_without_history(isolated_dirs) -> None:
    _write_all_ok(isolated_dirs)
    snap = am.collect_snapshot(frozen_utc="2026-05-03T08:00:00Z")
    assert snap["trends"]["last_24h"]["runtime"]["status"] == "not_available"
    assert snap["trends"]["all_time_from_available_history"]["runtime"]["status"] == "not_available"


def test_trends_ok_when_history_present(isolated_dirs) -> None:
    _write_all_ok(isolated_dirs)
    hist = isolated_dirs / "logs" / "workloop_runtime" / "history.jsonl"
    hist.parent.mkdir(parents=True, exist_ok=True)
    rows = [
        {"generated_at_utc": "2026-05-03T07:00:00Z", "final_recommendation": "all_sources_ok", "loop_health": {"consecutive_failures": 0}},
        {"generated_at_utc": "2026-05-03T07:30:00Z", "final_recommendation": "runtime_halt_after_3_consecutive_failures", "loop_health": {"consecutive_failures": 3}},
    ]
    with hist.open("w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    snap = am.collect_snapshot(frozen_utc="2026-05-03T08:00:00Z")
    agg = snap["trends"]["last_24h"]["runtime"]
    assert agg["status"] == "ok"
    assert agg["total_runs"] == 2
    assert agg["failed_runs"] == 1
    assert agg["consecutive_failures_max"] == 3


def test_trends_filter_old_rows_outside_window(isolated_dirs) -> None:
    _write_all_ok(isolated_dirs)
    hist = isolated_dirs / "logs" / "workloop_runtime" / "history.jsonl"
    hist.parent.mkdir(parents=True, exist_ok=True)
    # One ancient row + one recent row.
    rows = [
        {"generated_at_utc": "2024-01-01T00:00:00Z", "final_recommendation": "all_sources_ok", "loop_health": {"consecutive_failures": 0}},
        {"generated_at_utc": "2026-05-03T07:00:00Z", "final_recommendation": "all_sources_ok", "loop_health": {"consecutive_failures": 0}},
    ]
    with hist.open("w", encoding="utf-8") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")
    snap = am.collect_snapshot(frozen_utc="2026-05-03T08:00:00Z")
    last_24h = snap["trends"]["last_24h"]["runtime"]
    all_time = snap["trends"]["all_time_from_available_history"]["runtime"]
    assert last_24h["status"] == "ok"
    assert last_24h["total_runs"] == 1
    assert all_time["status"] == "ok"
    assert all_time["total_runs"] == 2


# ---------------------------------------------------------------------------
# Source statuses
# ---------------------------------------------------------------------------


def test_source_statuses_always_six_rows_in_canonical_order(isolated_dirs) -> None:
    snap = am.collect_snapshot(frozen_utc="2026-05-03T08:00:00Z")
    rows = snap["source_statuses"]
    assert len(rows) == 6
    names = [r["source"] for r in rows]
    expected = [n for n, _ in am.SOURCE_ORDER]
    assert names == expected


def test_source_statuses_path_strings_are_relative(isolated_dirs) -> None:
    snap = am.collect_snapshot(frozen_utc="2026-05-03T08:00:00Z")
    for r in snap["source_statuses"]:
        ap = r["artifact_path"]
        assert ap.startswith("logs/"), f"non-relative path: {ap!r}"


# ---------------------------------------------------------------------------
# Safety: credential redaction on raw upstream content
# ---------------------------------------------------------------------------


def test_credential_value_in_upstream_artifact_trips_guard(isolated_dirs) -> None:
    _write_all_ok(isolated_dirs)
    # Inject a credential-shaped value into the workloop_runtime's
    # loop_health.last_success_utc — that string is carried verbatim
    # into ``reliability.last_success_at_utc`` and must trip the
    # narrow credential-value redaction guard.
    rt = _ok_workloop_runtime()
    rt["loop_health"]["last_success_utc"] = "sk-ant-XXXXXXXX"
    _write(isolated_dirs / "logs" / "workloop_runtime" / "latest.json", rt)
    with pytest.raises(AssertionError):
        am.collect_snapshot(frozen_utc="2026-05-03T08:00:00Z")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def test_cli_no_freeform_flags(isolated_dirs) -> None:
    src = Path(am.__file__).read_text(encoding="utf-8")
    forbidden = ("--command", "--argv", "--shell", "--exec")
    for tok in forbidden:
        assert tok not in src, f"free-form flag in CLI: {tok!r}"


def test_cli_collect_no_write_does_not_create_artifact(
    isolated_dirs, capsys
) -> None:
    _write_all_ok(isolated_dirs)
    rc = am.main(["--collect", "--no-write", "--frozen-utc", "2026-05-03T08:00:00Z"])
    assert rc == 0
    assert not (isolated_dirs / "logs" / "autonomy_metrics" / "latest.json").exists()


def test_cli_status_with_missing_artifact_exits_nonzero(isolated_dirs) -> None:
    rc = am.main(["--status"])
    assert rc != 0


def test_cli_collect_writes_artifact(isolated_dirs) -> None:
    _write_all_ok(isolated_dirs)
    rc = am.main(["--collect", "--frozen-utc", "2026-05-03T08:00:00Z"])
    assert rc == 0
    assert (isolated_dirs / "logs" / "autonomy_metrics" / "latest.json").exists()


# ---------------------------------------------------------------------------
# Schema-doc presence
# ---------------------------------------------------------------------------


def test_schema_doc_exists() -> None:
    p = REPO_ROOT / "docs" / "governance" / "autonomy_metrics" / "schema.v1.md"
    assert p.exists()
    text = p.read_text(encoding="utf-8")
    assert "v3.15.15.25" in text


def test_runbook_doc_exists() -> None:
    p = REPO_ROOT / "docs" / "governance" / "autonomy_metrics.md"
    assert p.exists()
    text = p.read_text(encoding="utf-8")
    assert "v3.15.15.25" in text


# ---------------------------------------------------------------------------
# Frozen contract paths unchanged
# ---------------------------------------------------------------------------


def test_collect_does_not_mutate_frozen_contract_paths(isolated_dirs) -> None:
    """Defensive: the digest dir is under logs/, never under
    research/. Verify the only writes target logs/autonomy_metrics."""
    _write_all_ok(isolated_dirs)
    snap = am.collect_snapshot(frozen_utc="2026-05-03T08:00:00Z")
    paths = am.write_outputs(snap)
    for label, rel in paths.items():
        assert rel.startswith("logs/autonomy_metrics/"), f"{label} -> {rel}"
