"""Unit tests for research.diagnostics.throughput."""

from __future__ import annotations

import json
from datetime import UTC, datetime

import pytest

from research.diagnostics.throughput import compute_throughput_metrics


@pytest.fixture
def fixed_now() -> datetime:
    return datetime(2026, 4, 28, 10, 0, 0, tzinfo=UTC)


def _campaign(
    *,
    campaign_id: str,
    outcome: str,
    runtime_min: float | None = None,
    started: str | None = None,
    finished: str | None = None,
    queued: str | None = None,
    preset: str | None = None,
    timeframe: str | None = None,
    failure_reason: str | None = None,
):
    rec = {"campaign_id": campaign_id, "outcome": outcome}
    if runtime_min is not None:
        rec["runtime_min"] = runtime_min
    if started:
        rec["started_at_utc"] = started
    if finished:
        rec["finished_at_utc"] = finished
    if queued:
        rec["queued_at_utc"] = queued
    if preset:
        rec["preset"] = preset
    if timeframe:
        rec["timeframe"] = timeframe
    if failure_reason:
        rec["failure_reason"] = failure_reason
    return rec


def test_empty_registry(fixed_now: datetime):
    out = compute_throughput_metrics(now_utc=fixed_now)
    assert out["campaigns_per_day"] == 0.0
    assert out["meaningful_campaigns_per_day"] == 0.0
    assert out["runtime_minutes"]["count"] == 0
    assert out["queue_wait_seconds"]["count"] == 0
    assert out["success_rate"] is None


def test_campaigns_in_window_counted(fixed_now: datetime):
    in_window_iso = "2026-04-28T05:00:00Z"  # 5h ago, within 1d window
    out_of_window_iso = "2026-04-26T05:00:00Z"  # 2 days ago, outside 1d
    out = compute_throughput_metrics(
        registry_payload={
            "campaigns": [
                _campaign(
                    campaign_id="c1",
                    outcome="completed",
                    runtime_min=10.0,
                    started=in_window_iso,
                    finished=in_window_iso,
                ),
                _campaign(
                    campaign_id="c_old",
                    outcome="completed",
                    runtime_min=20.0,
                    finished=out_of_window_iso,
                ),
            ]
        },
        now_utc=fixed_now,
        window_days=1,
    )
    assert out["source"]["campaigns_in_window"] == 1
    assert out["campaigns_per_day"] == 1.0
    assert out["completed_campaigns_per_day"] == 1.0


def test_meaningful_count_excludes_worker_crashes(fixed_now: datetime):
    finished = "2026-04-28T05:00:00Z"
    out = compute_throughput_metrics(
        registry_payload={
            "campaigns": [
                _campaign(
                    campaign_id="ok",
                    outcome="completed",
                    finished=finished,
                ),
                _campaign(
                    campaign_id="rejected",
                    outcome="failed",
                    failure_reason="screening_no_survivors",
                    finished=finished,
                ),
                _campaign(
                    campaign_id="crash",
                    outcome="failed",
                    failure_reason="worker_crash",
                    finished=finished,
                ),
            ]
        },
        now_utc=fixed_now,
    )
    assert out["meaningful_campaigns_per_day"] == 2.0


def test_p50_p95_runtime_deterministic(fixed_now: datetime):
    finished = "2026-04-28T05:00:00Z"
    runtimes = [1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 9.0, 10.0]
    out = compute_throughput_metrics(
        registry_payload={
            "campaigns": [
                _campaign(
                    campaign_id=f"c{i}",
                    outcome="completed",
                    runtime_min=v,
                    finished=finished,
                )
                for i, v in enumerate(runtimes)
            ]
        },
        now_utc=fixed_now,
    )
    assert out["runtime_minutes"]["count"] == 10
    # Linear-interpolation p50 of 1..10 is 5.5 ; p95 is 9.55.
    assert out["runtime_minutes"]["p50"] == 5.5
    assert abs(out["runtime_minutes"]["p95"] - 9.55) < 1e-6


def test_queue_wait_computed(fixed_now: datetime):
    out = compute_throughput_metrics(
        registry_payload={
            "campaigns": [
                _campaign(
                    campaign_id="c1",
                    outcome="completed",
                    queued="2026-04-28T05:00:00Z",
                    started="2026-04-28T05:00:30Z",
                    finished="2026-04-28T05:05:00Z",
                ),
            ]
        },
        now_utc=fixed_now,
    )
    assert out["queue_wait_seconds"]["count"] == 1
    assert out["queue_wait_seconds"]["p50"] == 30.0


def test_workers_busy_rate(fixed_now: datetime):
    out = compute_throughput_metrics(
        queue_payload={"queue": [], "workers_busy": 3, "workers_total": 4},
        now_utc=fixed_now,
    )
    assert out["workers"]["busy_rate"] == 0.75
    assert out["workers"]["idle_rate"] == 0.25


def test_deterministic_output(fixed_now: datetime):
    payload = {
        "campaigns": [
            _campaign(
                campaign_id="c1",
                outcome="completed",
                runtime_min=10,
                finished="2026-04-28T05:00:00Z",
            )
        ]
    }
    a = compute_throughput_metrics(registry_payload=payload, now_utc=fixed_now)
    b = compute_throughput_metrics(registry_payload=payload, now_utc=fixed_now)
    assert json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)


# ---------------------------------------------------------------------------
# v3.15.15.4 — meaningful-campaign taxonomy patch tests
#
# Existing meaningful semantics for ``no_signal`` / ``near_pass`` /
# ``completed`` / ``failed`` are unchanged (covered by the regression
# below). The patch adds recognition of launcher-literal outcomes so
# they are correctly counted (or correctly excluded).
# ---------------------------------------------------------------------------


from research.diagnostics.throughput import _is_meaningful  # private API for testing


# Pre-v3.15.15.4 semantics — pinned by this regression.
_PRE_PATCH_MEANINGFUL = [
    # (record, expected_meaningful)
    ({"outcome": "no_signal"}, True),
    ({"outcome": "near_pass"}, True),
    ({"outcome": "completed"}, True),
    ({"outcome": "completed", "failure_reason": "no_survivor"}, True),
    ({"outcome": "failed", "failure_reason": "screening_no_survivors"}, True),
    ({"outcome": "failed", "failure_reason": "worker_crash"}, False),
    ({"outcome": "failed", "failure_reason": "lease_lost"}, False),
    ({"outcome": "failed", "failure_reason": "missing_artifact"}, False),
    ({"outcome": "failed"}, False),  # no failure_reason → not meaningful
    ({"outcome": "canceled"}, False),
    ({"outcome": "running"}, False),
    ({"outcome": "weird_unknown"}, False),
    ({}, False),
]


@pytest.mark.parametrize("record, expected", _PRE_PATCH_MEANINGFUL)
def test_pre_patch_meaningful_unchanged(record: dict, expected: bool):
    """Backward-compat: no pre-existing meaningful classification changes."""
    assert _is_meaningful(record) is expected


# v3.15.15.4 — launcher-literal records and their meaningful classification.
_LAUNCHER_LITERAL_MEANINGFUL = [
    # (record, expected_meaningful, comment)
    ({"outcome": "completed_with_candidates"}, True, "candidate found"),
    ({"outcome": "completed_no_survivor"}, True, "informative no-survivor"),
    ({"outcome": "research_rejection"}, True, "explainable research-side rejection"),
    ({"outcome": "degenerate_no_survivors"}, True, "informative failure"),
    ({"outcome": "paper_blocked"}, True, "candidate found, downstream gate blocked"),
    ({"outcome": "technical_failure"}, False, "no usable evidence"),
    ({"outcome": "worker_crashed"}, False, "legacy crash literal"),
    ({"outcome": "integrity_failed"}, False, "data integrity violation"),
    ({"outcome": "aborted"}, False, "operator-initiated cancel"),
    ({"outcome": "canceled_duplicate"}, False, "duplicate-detection cancel"),
    ({"outcome": "canceled_upstream_stale"}, False, "stale-upstream cancel"),
]


@pytest.mark.parametrize(
    "record, expected, _",
    _LAUNCHER_LITERAL_MEANINGFUL,
    ids=[r[0]["outcome"] for r in _LAUNCHER_LITERAL_MEANINGFUL],
)
def test_launcher_literal_meaningful_classification(
    record: dict, expected: bool, _: str
):
    """Launcher v3.15.5+ outcomes classify correctly. Technical failures
    and cancellations are NOT counted as meaningful; everything else is."""
    assert _is_meaningful(record) is expected


def test_meaningful_per_day_counts_launcher_literals(fixed_now: datetime):
    """End-to-end via compute_throughput_metrics: a registry containing
    one ``technical_failure`` + one ``completed_with_candidates`` yields
    ``meaningful_campaigns_per_day == 1.0``."""
    out = compute_throughput_metrics(
        registry_payload={
            "campaigns": [
                _campaign(
                    campaign_id="c-tech",
                    outcome="technical_failure",
                    finished="2026-04-28T05:00:00Z",
                ),
                _campaign(
                    campaign_id="c-good",
                    outcome="completed_with_candidates",
                    finished="2026-04-28T05:01:00Z",
                ),
            ]
        },
        now_utc=fixed_now,
    )
    assert out["meaningful_campaigns_per_day"] == 1.0


def test_paper_blocked_is_meaningful(fixed_now: datetime):
    """``paper_blocked`` campaigns are meaningful — a candidate was found,
    paper-readiness blocked promotion, the failure reason is explainable."""
    out = compute_throughput_metrics(
        registry_payload={
            "campaigns": [
                _campaign(
                    campaign_id="c-paper",
                    outcome="paper_blocked",
                    failure_reason="insufficient_oos_days",
                    finished="2026-04-28T05:00:00Z",
                )
            ]
        },
        now_utc=fixed_now,
    )
    assert out["meaningful_campaigns_per_day"] == 1.0
