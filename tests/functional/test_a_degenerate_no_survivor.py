"""Scenario A — degenerate_no_survivors.

A campaign that exits with launcher rc=2 (no evaluable pairs after
screening). Outcome literal: ``"degenerate_no_survivors"``,
reason_code: ``"degenerate_no_evaluable_pairs"``,
meaningful_classification: ``"meaningful_failure_confirmed"``.

Expected post-v3.15.15.4:
* failure_modes classifies it under
  ``campaigns_by_outcome_class["degenerate_no_survivors"]``.
* throughput counts it as meaningful (informative failure).
* No record lands in ``"unknown"``.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime

from .conftest import run_diagnostics_build
from ._funnel_artifact_builders import (
    make_campaign_record,
    make_ledger_event,
    write_frozen_contracts,
    write_ledger_jsonl,
    write_registry,
)

FROZEN_NOW = datetime(2026, 4, 28, 12, 0, 0, tzinfo=UTC)


def test_degenerate_no_survivor_classified_correctly(sandbox):
    write_frozen_contracts(sandbox.research_dir)

    record = make_campaign_record(
        campaign_id="c-degen-1",
        preset_name="trend_4h",
        outcome="degenerate_no_survivors",
        reason_code="degenerate_no_evaluable_pairs",
        meaningful_classification="meaningful_failure_confirmed",
        spawned_at_utc="2026-04-28T11:00:00Z",
        started_at_utc="2026-04-28T11:00:30Z",
        finished_at_utc="2026-04-28T11:05:00Z",
        runtime_min=4.5,
        state="completed",
        asset="BTC",
        timeframe="4h",
        family="trend",
        hypothesis_id="h_trend_v0",
    )
    write_registry(sandbox.registry_path, campaigns=[record])
    write_ledger_jsonl(
        sandbox.ledger_path,
        [
            make_ledger_event(
                campaign_id="c-degen-1",
                preset_name="trend_4h",
                event_type="terminal",
                outcome="degenerate_no_survivors",
                failure_reason="degenerate_no_evaluable_pairs",
                reason_code="degenerate_no_evaluable_pairs",
                meaningful_classification="meaningful_failure_confirmed",
                at_utc="2026-04-28T11:05:00Z",
                asset="BTC",
                timeframe="4h",
                family="trend",
                hypothesis_id="h_trend_v0",
            )
        ],
    )

    run_diagnostics_build(sandbox, now_utc=FROZEN_NOW)

    # --- failure_modes ---
    fm = json.loads(sandbox.failure_modes_path.read_text(encoding="utf-8"))
    counts = fm["campaigns_by_outcome_class"]
    assert counts["degenerate_no_survivors"] == 1, counts
    assert counts["unknown"] == 0, "known outcome must not land in unknown"
    assert counts["technical_failure"] == 0
    assert counts["research_rejection"] == 0
    assert counts["paper_blocked"] == 0  # taxonomy class present, value zero
    # The outcome literal is also present in the raw outcome counter.
    raw = {row["name"]: row["count"] for row in fm["campaigns_by_outcome"]}
    assert raw.get("degenerate_no_survivors") == 1
    # v3.15.15.6: top_failure_reasons populated (was empty pre-patch).
    reasons = {r["name"]: r["count"] for r in fm["top_failure_reasons"]}
    assert reasons.get("degenerate_no_evaluable_pairs") == 2  # registry + ledger
    # v3.15.15.6: by_meaningful_classification populated.
    meaningful = {
        m["name"]: m["count"] for m in fm["by_meaningful_classification"]
    }
    assert meaningful.get("meaningful_failure_confirmed") == 1
    # v3.15.15.6: diagnostic_context block present and reports
    # registry_only_mode + the documented limitations.
    ctx = fm["diagnostic_context"]
    # The harness writes a synthetic ledger via ``write_ledger_jsonl``,
    # so this scenario reaches ``ledger_enriched`` mode.
    assert ctx["diagnostic_mode"] == "ledger_enriched"
    assert ctx["registry_available"] is True
    assert ctx["ledger_available"] is True
    assert ctx["screening_evidence_available"] is False
    assert "screening_evidence_absent" in ctx["limitations"]
    assert "research/screening_evidence_latest.v1.json" in ctx["missing_evidence_artifacts"]
    assert "campaign_record.hypothesis_id" in ctx["future_writer_enrichment_required"]
    # technical_vs_research_failure_counts now ranges over ALL campaigns
    # and reports degenerate_no_survivors as a first-class bucket.
    tvr = fm["technical_vs_research_failure_counts"]
    assert tvr["degenerate_no_survivors"] == 1
    assert tvr["technical_failure"] == 0
    assert tvr["research_rejection"] == 0

    # --- throughput ---
    tp = json.loads(sandbox.throughput_metrics_path.read_text(encoding="utf-8"))
    # degenerate_no_survivors IS meaningful (informative failure).
    assert tp["meaningful_campaigns_per_day"] == 1.0
    assert tp["source"]["registry_state"] == "valid"

    # --- aggregator summary ---
    summary = json.loads(
        sandbox.observability_summary_path.read_text(encoding="utf-8")
    )
    assert summary["overall_status"] == "healthy"
    assert summary["component_status_counts"]["available"] == 4
    assert "unknown" not in summary["component_status_counts"]
    # v3.15.15.6: split status fields are present.
    assert summary["infrastructure_status"] == "healthy"
    assert summary["diagnostic_evidence_status"] in ("partial", "sufficient")
    assert summary["diagnostic_mode"] == "ledger_enriched"
    # Evidence-limitation warnings propagated from failure_modes.
    assert any(
        "diagnostic_evidence_limitation: screening_evidence_absent" in w
        for w in summary["warnings"]
    )


def test_degenerate_failure_reason_aggregates_correctly(sandbox):
    """Two distinct campaigns, same preset+failure_reason → one cluster."""
    write_frozen_contracts(sandbox.research_dir)

    campaigns = [
        make_campaign_record(
            campaign_id=f"c-degen-{i}",
            preset_name="trend_4h",
            outcome="degenerate_no_survivors",
            reason_code="degenerate_no_evaluable_pairs",
            failure_reason="degenerate_no_evaluable_pairs",
            meaningful_classification="meaningful_failure_confirmed",
            spawned_at_utc="2026-04-28T11:00:00Z",
            finished_at_utc=f"2026-04-28T11:0{i}:00Z",
            asset="BTC",
            timeframe="4h",
        )
        for i in range(3)
    ]
    write_registry(sandbox.registry_path, campaigns=campaigns)
    write_ledger_jsonl(sandbox.ledger_path, [])  # empty ledger is fine

    run_diagnostics_build(sandbox, now_utc=FROZEN_NOW)

    fm = json.loads(sandbox.failure_modes_path.read_text(encoding="utf-8"))
    assert fm["campaigns_by_outcome_class"]["degenerate_no_survivors"] == 3
    assert fm["campaigns_by_outcome_class"]["unknown"] == 0
    assert fm["total_campaigns_observed"] == 3
    # v3.15.15.6: repeated_failure_clusters populated under registry-only
    # mode using the partial-key fallback (preset_name present;
    # hypothesis_id / asset / timeframe absent in production registry
    # records but present here in the synthetic builders).
    clusters = fm["repeated_failure_clusters"]
    assert clusters
    cluster = clusters[0]
    assert cluster["count"] == 3
    assert cluster["outcome_class"] == "degenerate_no_survivors"
    assert cluster["preset_name"] == "trend_4h"
    assert cluster["source"] == "registry"
    # The synthetic builder fills asset + timeframe but not
    # hypothesis_id or strategy_family in this scenario → "partial".
    assert cluster["cluster_key_quality"] == "partial"
    # Note: the comment below is no longer accurate — v3.15.15.6 widens
    # both the failure-event filter AND the cluster key, so degenerate
    # records DO form clusters now.
    # Note: ``repeated_failure_clusters`` currently feeds off
    # ``failed_campaigns`` (records that classify as ``technical_failure``
    # or have ``outcome=="failed"``). degenerate_no_survivors records do
    # NOT flow into that filter today; widening it is a future
    # research/diagnostics enhancement, out of scope for v3.15.15.5.
    # Throughput correctly counts these three as meaningful (informative).
    tp = json.loads(sandbox.throughput_metrics_path.read_text(encoding="utf-8"))
    assert tp["meaningful_campaigns_per_day"] == 3.0
