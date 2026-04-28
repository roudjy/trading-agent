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
