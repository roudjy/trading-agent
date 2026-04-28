"""Scenario F-lite — diagnostics build + cross-cutting observability.

Parametrised over (degenerate, technical_failure, legacy worker_crashed).
For each scenario:

* Build registry + ledger with a single launcher-shaped record.
* Run ``run_diagnostics_build`` over the sandbox (the harness's
  helper that orchestrates the same per-component pure APIs as
  ``research.diagnostics.cli.cmd_build``, but parameterised on
  sandbox paths). cmd_build itself is unit-tested separately in
  ``tests/unit/test_observability_cli.py``.
* Assert ``failure_modes`` outcome-class counts.
* Assert ``throughput`` meaningful-per-day count.
* Assert ``observability_summary.overall_status == "healthy"`` and
  no ``unknown`` component status.

Plus one deliberate corruption test that verifies the aggregator
transitions ``healthy → degraded`` when a component artifact is
malformed.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from research.diagnostics import aggregator as agg_mod

from .conftest import run_diagnostics_build
from ._funnel_artifact_builders import (
    make_campaign_record,
    make_ledger_event,
    write_frozen_contracts,
    write_ledger_jsonl,
    write_registry,
)

FROZEN_NOW = datetime(2026, 4, 28, 12, 0, 0, tzinfo=UTC)


def _seed_degenerate(sandbox):
    write_frozen_contracts(sandbox.research_dir)
    write_registry(
        sandbox.registry_path,
        campaigns=[
            make_campaign_record(
                campaign_id="c-degen-f",
                preset_name="trend_4h",
                outcome="degenerate_no_survivors",
                reason_code="degenerate_no_evaluable_pairs",
                failure_reason="degenerate_no_evaluable_pairs",
                meaningful_classification="meaningful_failure_confirmed",
                spawned_at_utc="2026-04-28T11:00:00Z",
                finished_at_utc="2026-04-28T11:05:00Z",
            )
        ],
    )
    write_ledger_jsonl(sandbox.ledger_path, [])


def _seed_technical(sandbox):
    write_frozen_contracts(sandbox.research_dir)
    write_registry(
        sandbox.registry_path,
        campaigns=[
            make_campaign_record(
                campaign_id="c-tech-f",
                preset_name="ema_1h",
                outcome="technical_failure",
                reason_code="worker_crash",
                failure_reason="worker_crash",
                meaningful_classification="uninformative_technical_failure",
                spawned_at_utc="2026-04-28T11:00:00Z",
                finished_at_utc="2026-04-28T11:00:30Z",
            )
        ],
    )
    write_ledger_jsonl(sandbox.ledger_path, [])


def _seed_legacy_worker_crashed(sandbox):
    write_frozen_contracts(sandbox.research_dir)
    write_registry(
        sandbox.registry_path,
        campaigns=[
            make_campaign_record(
                campaign_id="c-legacy-f",
                preset_name="vol_compression_breakout_crypto_1h",
                outcome="worker_crashed",
                reason_code="worker_crash",
                failure_reason="worker_crash",
                meaningful_classification="uninformative_technical_failure",
                spawned_at_utc="2026-04-27T11:00:00Z",
                finished_at_utc="2026-04-27T11:00:15Z",
            )
        ],
    )
    write_ledger_jsonl(sandbox.ledger_path, [])


@pytest.mark.parametrize(
    "scenario_seeder, expected_class, expected_meaningful_per_day",
    [
        pytest.param(
            _seed_degenerate, "degenerate_no_survivors", 1.0,
            id="degenerate_no_survivors",
        ),
        pytest.param(
            _seed_technical, "technical_failure", 0.0,
            id="technical_failure",
        ),
        pytest.param(
            _seed_legacy_worker_crashed, "technical_failure", 0.0,
            id="legacy_worker_crashed",
        ),
    ],
)
def test_diagnostics_build_classifies_scenario(
    sandbox,
    scenario_seeder,
    expected_class: str,
    expected_meaningful_per_day: float,
):
    scenario_seeder(sandbox)

    run_diagnostics_build(sandbox, now_utc=FROZEN_NOW)

    fm = json.loads(sandbox.failure_modes_path.read_text(encoding="utf-8"))
    counts = fm["campaigns_by_outcome_class"]
    assert counts[expected_class] == 1, (
        f"expected {expected_class}=1, got {counts}"
    )
    assert counts["unknown"] == 0, "known outcome must not land in unknown"

    tp = json.loads(sandbox.throughput_metrics_path.read_text(encoding="utf-8"))
    assert tp["meaningful_campaigns_per_day"] == expected_meaningful_per_day

    summary = json.loads(
        sandbox.observability_summary_path.read_text(encoding="utf-8")
    )
    assert summary["overall_status"] == "healthy"
    assert summary["component_status_counts"]["available"] == 4
    # Aggregator must not report any active component as unknown.
    assert "unknown" not in summary["component_status_counts"]


def test_aggregator_overall_degraded_on_corrupt_component(sandbox):
    """Healthy → degraded transition when one observability artifact is malformed."""
    _seed_degenerate(sandbox)
    run_diagnostics_build(sandbox, now_utc=FROZEN_NOW)

    summary_first = json.loads(
        sandbox.observability_summary_path.read_text(encoding="utf-8")
    )
    assert summary_first["overall_status"] == "healthy"

    # Corrupt one component artifact in place (simulates a half-write).
    sandbox.throughput_metrics_path.write_text("{not json", encoding="utf-8")

    # Re-run aggregator only (a full build would re-write the corrupt file).
    refreshed = agg_mod.build_observability_summary(now_utc=FROZEN_NOW)
    agg_mod.write_observability_summary(
        refreshed, path=sandbox.observability_summary_path
    )

    summary_second = json.loads(
        sandbox.observability_summary_path.read_text(encoding="utf-8")
    )
    assert summary_second["overall_status"] == "degraded"
    assert summary_second["recommended_next_human_action"] == "investigation_required"
    counts = summary_second["component_status_counts"]
    assert counts.get("corrupt", 0) >= 1


def test_paper_blocked_class_present_in_summary_taxonomy(sandbox):
    """v3.15.15.4 introduced ``paper_blocked`` as a dedicated class.

    Even when no paper_blocked campaigns are present in the registry,
    the failure_modes payload must still surface ``paper_blocked`` as a
    key with count 0 (so the frontend renders the bucket consistently).
    """
    _seed_degenerate(sandbox)
    run_diagnostics_build(sandbox, now_utc=FROZEN_NOW)
    fm = json.loads(sandbox.failure_modes_path.read_text(encoding="utf-8"))
    assert "paper_blocked" in fm["campaigns_by_outcome_class"]
    assert fm["campaigns_by_outcome_class"]["paper_blocked"] == 0
