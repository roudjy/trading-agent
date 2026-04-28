"""Unit tests for research.diagnostics.failure_modes."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from research.diagnostics.failure_modes import (
    OUTCOME_CLASSES,
    build_failure_modes_artifact,
    compute_failure_mode_distribution,
)


@pytest.fixture
def fixed_now() -> datetime:
    return datetime(2026, 4, 28, 10, 0, 0, tzinfo=UTC)


def test_empty_inputs(fixed_now: datetime):
    out = compute_failure_mode_distribution(now_utc=fixed_now)
    assert out["schema_version"] == "1.0"
    assert out["total_campaigns_observed"] == 0
    assert out["total_failure_events_observed"] == 0
    assert out["top_failure_reasons"] == []
    assert out["technical_vs_research_failure_counts"]["unknown"] == 0


def test_completed_no_survivor_classified(fixed_now: datetime):
    out = compute_failure_mode_distribution(
        registry_payload={
            "campaigns": [
                {
                    "campaign_id": "c1",
                    "outcome": "completed",
                    "failure_reason": "no_survivor",
                    "preset": "trend_4h",
                }
            ]
        },
        now_utc=fixed_now,
    )
    assert out["campaigns_by_outcome_class"]["completed_no_survivor"] == 1


def test_degenerate_no_survivor_classified(fixed_now: datetime):
    out = compute_failure_mode_distribution(
        registry_payload={
            "campaigns": [
                {
                    "campaign_id": "c1",
                    "outcome": "completed",
                    "failure_reason": "screening_no_survivors",
                }
            ]
        },
        now_utc=fixed_now,
    )
    assert out["campaigns_by_outcome_class"]["degenerate_no_survivors"] == 1


def test_technical_failure_classified(fixed_now: datetime):
    out = compute_failure_mode_distribution(
        registry_payload={
            "campaigns": [
                {
                    "campaign_id": "c1",
                    "outcome": "failed",
                    "failure_reason": "worker_crash",
                    "preset": "trend_4h",
                }
            ]
        },
        now_utc=fixed_now,
    )
    assert out["campaigns_by_outcome_class"]["technical_failure"] == 1
    # Surfaces in by_preset because it failed.
    by_preset_names = {p["name"] for p in out["by_preset"]}
    assert "trend_4h" in by_preset_names


def test_repeated_failure_cluster_detected(fixed_now: datetime):
    campaigns = [
        {
            "campaign_id": f"c{i}",
            "outcome": "failed",
            "failure_reason": "lease_lost",
            "preset": "ema_1h",
        }
        for i in range(4)
    ]
    out = compute_failure_mode_distribution(
        registry_payload={"campaigns": campaigns},
        now_utc=fixed_now,
    )
    clusters = out["repeated_failure_clusters"]
    assert clusters
    assert clusters[0]["preset"] == "ema_1h"
    assert clusters[0]["failure_reason"] == "lease_lost"
    assert clusters[0]["count"] == 4


def test_unknown_outcome_lands_in_unknown_bucket(fixed_now: datetime):
    out = compute_failure_mode_distribution(
        registry_payload={"campaigns": [{"campaign_id": "c1", "outcome": "weird"}]},
        now_utc=fixed_now,
    )
    assert out["campaigns_by_outcome_class"]["unknown"] == 1
    assert out["unknown_or_unclassified_count"] == 0  # not a failure event


def test_ledger_events_contribute_to_failure_aggregates(fixed_now: datetime):
    out = compute_failure_mode_distribution(
        ledger_events=[
            {
                "outcome": "failed",
                "failure_reason": "worker_crash",
                "preset": "trend_4h",
                "asset": "BTC",
                "timeframe": "1h",
            },
            {
                "outcome": "failed",
                "failure_reason": "worker_crash",
                "preset": "trend_4h",
                "asset": "ETH",
                "timeframe": "1h",
            },
        ],
        now_utc=fixed_now,
    )
    reasons = {r["name"]: r["count"] for r in out["top_failure_reasons"]}
    assert reasons.get("worker_crash") == 2
    assert {a["name"] for a in out["by_asset"]} == {"BTC", "ETH"}


def test_outcome_classes_taxonomy_stable():
    # Stable identifiers — frontends must be able to rely on these strings.
    assert "technical_failure" in OUTCOME_CLASSES
    assert "research_rejection" in OUTCOME_CLASSES
    assert "completed_with_survivor" in OUTCOME_CLASSES
    assert "unknown" in OUTCOME_CLASSES


def test_deterministic_output_for_fixed_inputs(fixed_now: datetime):
    inputs = {
        "campaigns": [
            {"campaign_id": "c1", "outcome": "completed"},
            {"campaign_id": "c2", "outcome": "failed", "failure_reason": "x", "preset": "p"},
        ]
    }
    a = compute_failure_mode_distribution(
        registry_payload=inputs, now_utc=fixed_now
    )
    b = compute_failure_mode_distribution(
        registry_payload=inputs, now_utc=fixed_now
    )
    assert json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)


def test_build_failure_modes_artifact_with_real_files(
    tmp_path: Path, fixed_now: datetime
):
    reg = tmp_path / "registry.json"
    reg.write_text(
        json.dumps(
            {
                "campaigns": [
                    {
                        "campaign_id": "c1",
                        "outcome": "failed",
                        "failure_reason": "worker_crash",
                        "preset": "trend_4h",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    led = tmp_path / "ledger.jsonl"
    led.write_text(
        json.dumps({"outcome": "failed", "failure_reason": "lease_lost", "preset": "ema_1h"})
        + "\n",
        encoding="utf-8",
    )
    out = build_failure_modes_artifact(
        now_utc=fixed_now,
        registry_path=reg,
        ledger_path=led,
    )
    assert out["total_campaigns_observed"] == 1
    assert out["total_failure_events_observed"] == 2
    assert out["source"]["ledger_state"] == "valid"
    assert out["source"]["registry_state"] == "valid"
    assert out["source"]["max_ledger_lines"] == 10000


# ---------------------------------------------------------------------------
# v3.15.15.4 — taxonomy patch tests
#
# These tests verify two things at once:
#   1. The pre-v3.15.15.4 mapping is preserved byte-for-byte (no silent
#      reinterpretation of older artifacts);
#   2. The launcher-literal outcomes the diagnostics layer used to classify
#      as ``"unknown"`` now land in their dedicated outcome class.
# ---------------------------------------------------------------------------


from research.diagnostics.failure_modes import _classify  # private API for testing


# Pre-v3.15.15.4 (outcome, failure_reason) pairs and their expected class.
# This is the entire historical surface; the regression below pins it.
_PRE_PATCH_PAIRS = [
    # (outcome, failure_reason, expected_class)
    ("completed", None, "completed_no_survivor"),
    ("completed", "no_survivor", "completed_no_survivor"),
    ("completed", "candidate_promoted", "completed_with_survivor"),
    ("completed", "promotion_pass", "completed_with_survivor"),
    ("no_signal", None, "research_rejection"),
    ("near_pass", None, "research_rejection"),
    ("failed", None, "technical_failure"),
    ("failed", "screening_no_survivors", "degenerate_no_survivors"),
    ("failed", "worker_crash", "technical_failure"),
    ("failed", "lease_lost", "technical_failure"),
    ("canceled", None, "canceled"),
    ("running", None, "running"),
    ("weird_unknown_value", None, "unknown"),
    (None, None, "unknown"),
]


@pytest.mark.parametrize(
    "outcome, failure_reason, expected_class", _PRE_PATCH_PAIRS
)
def test_pre_patch_classification_unchanged(
    outcome: str | None, failure_reason: str | None, expected_class: str
):
    """Backward-compat: every (outcome, failure_reason) pair recognised
    pre-v3.15.15.4 must classify identically post-patch."""
    assert _classify(outcome, failure_reason) == expected_class


# v3.15.15.4 — launcher-literal outcomes that previously landed in "unknown".
# Each row asserts the literal now classifies into its dedicated bucket.
_LAUNCHER_LITERAL_PAIRS = [
    # outcome, failure_reason, expected_class
    ("degenerate_no_survivors", "degenerate_no_evaluable_pairs", "degenerate_no_survivors"),
    ("technical_failure", "worker_crash", "technical_failure"),
    ("technical_failure", "timeout", "technical_failure"),
    ("completed_with_candidates", "none", "completed_with_survivor"),
    ("completed_no_survivor", "none", "completed_no_survivor"),
    ("research_rejection", "screening_failed_oos_returns", "research_rejection"),
    ("paper_blocked", "insufficient_oos_days", "paper_blocked"),
    ("paper_blocked", "excessive_divergence", "paper_blocked"),
    ("integrity_failed", "integrity_violation", "technical_failure"),
    ("aborted", "operator_aborted", "canceled"),
    ("canceled_duplicate", "duplicate_detected", "canceled"),
    ("canceled_upstream_stale", "upstream_artifact_stale", "canceled"),
    # Pre-v3.15.5 backward-compat — old ledgers may still contain this literal.
    ("worker_crashed", "worker_crash", "technical_failure"),
]


@pytest.mark.parametrize(
    "outcome, failure_reason, expected_class", _LAUNCHER_LITERAL_PAIRS
)
def test_launcher_literal_outcome_classifies_correctly(
    outcome: str, failure_reason: str | None, expected_class: str
):
    """Every launcher v3.15.5+ outcome literal lands in its dedicated class
    (not in ``unknown``)."""
    assert _classify(outcome, failure_reason) == expected_class


def test_paper_blocked_is_a_dedicated_outcome_class():
    """v3.15.15.4 introduces ``paper_blocked`` as its own class (NOT folded
    into ``completed_no_survivor``). A candidate exists but paper-readiness
    blocked promotion — that is semantically distinct from no-survivor.
    """
    assert "paper_blocked" in OUTCOME_CLASSES
    out = compute_failure_mode_distribution(
        registry_payload={
            "campaigns": [
                {
                    "campaign_id": "c1",
                    "outcome": "paper_blocked",
                    "failure_reason": "insufficient_oos_days",
                    "preset": "trend_4h",
                }
            ]
        },
        now_utc=datetime(2026, 4, 28, 10, 0, 0, tzinfo=UTC),
    )
    assert out["campaigns_by_outcome_class"]["paper_blocked"] == 1
    assert out["campaigns_by_outcome_class"]["completed_no_survivor"] == 0
    assert out["campaigns_by_outcome_class"]["unknown"] == 0


def test_known_launcher_outcomes_never_land_in_unknown(fixed_now: datetime):
    """Comprehensive: feed every launcher v3.15.5+ literal once. Every
    record must land in a recognised outcome_class — none in ``unknown``."""
    launcher_literals = [
        "completed_with_candidates",
        "completed_no_survivor",
        "degenerate_no_survivors",
        "technical_failure",
        "research_rejection",
        "paper_blocked",
        "integrity_failed",
        "aborted",
        "canceled_duplicate",
        "canceled_upstream_stale",
        "worker_crashed",
    ]
    out = compute_failure_mode_distribution(
        registry_payload={
            "campaigns": [
                {"campaign_id": f"c{i}", "outcome": lit, "preset": "p"}
                for i, lit in enumerate(launcher_literals)
            ]
        },
        now_utc=fixed_now,
    )
    assert out["campaigns_by_outcome_class"]["unknown"] == 0


def test_unknown_outcome_still_lands_in_unknown(fixed_now: datetime):
    """The ``unknown`` bucket remains the catch-all for genuinely
    unrecognised values — the v3.15.15.4 patch only adds known ones."""
    out = compute_failure_mode_distribution(
        registry_payload={
            "campaigns": [
                {"campaign_id": "c1", "outcome": "made_up_outcome_xyz"}
            ]
        },
        now_utc=fixed_now,
    )
    assert out["campaigns_by_outcome_class"]["unknown"] == 1


def test_outcome_classes_taxonomy_includes_paper_blocked_v3_15_15_4():
    """Pin the taxonomy size + ``paper_blocked`` membership."""
    assert "paper_blocked" in OUTCOME_CLASSES
    assert len(OUTCOME_CLASSES) == 9
