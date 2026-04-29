"""Scenario B — technical_failure / Scenario B2 — legacy worker_crashed.

B: launcher rc=124 (timeout) or rc≠0,≠2 (worker_crash). Outcome
literal: ``"technical_failure"``, reason_code: ``"worker_crash"`` or
``"timeout"``, meaningful_classification:
``"uninformative_technical_failure"``.

B2: pre-v3.15.5 ledgers may still contain the legacy literal
``"worker_crashed"`` (past-tense). The v3.15.15.4 taxonomy patch maps
both to the ``technical_failure`` class and treats both as
not-meaningful.

Critical invariant the brief calls out explicitly: a technical
failure must NOT be counted as a research rejection. Verified
explicitly in both scenarios.
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


def test_technical_failure_classified_correctly(sandbox):
    """Scenario B — outcome=technical_failure, reason_code=worker_crash."""
    write_frozen_contracts(sandbox.research_dir)

    record = make_campaign_record(
        campaign_id="c-tech-1",
        preset_name="ema_1h",
        outcome="technical_failure",
        reason_code="worker_crash",
        failure_reason="worker_crash",
        meaningful_classification="uninformative_technical_failure",
        spawned_at_utc="2026-04-28T11:00:00Z",
        started_at_utc="2026-04-28T11:00:30Z",
        finished_at_utc="2026-04-28T11:00:45Z",
        runtime_min=0.25,
        state="failed",
        asset="ETH",
        timeframe="1h",
        family="trend",
        worker_id="w-1",
    )
    write_registry(sandbox.registry_path, campaigns=[record])
    write_ledger_jsonl(
        sandbox.ledger_path,
        [
            make_ledger_event(
                campaign_id="c-tech-1",
                preset_name="ema_1h",
                event_type="terminal",
                outcome="technical_failure",
                failure_reason="worker_crash",
                reason_code="worker_crash",
                meaningful_classification="uninformative_technical_failure",
                at_utc="2026-04-28T11:00:45Z",
                asset="ETH",
                timeframe="1h",
                worker_id="w-1",
            )
        ],
    )

    run_diagnostics_build(sandbox, now_utc=FROZEN_NOW)

    fm = json.loads(sandbox.failure_modes_path.read_text(encoding="utf-8"))
    counts = fm["campaigns_by_outcome_class"]
    # Desired: literal outcome → technical_failure class.
    assert counts["technical_failure"] == 1, counts
    # CRITICAL: technical failures must NOT be counted as research rejection.
    assert counts["research_rejection"] == 0, (
        "technical_failure leaked into research_rejection bucket"
    )
    # Known outcome must never land in unknown.
    assert counts["unknown"] == 0
    # v3.15.15.6: ``_ledger_failure_events`` was widened to recognise
    # launcher-literal outcomes (``technical_failure``, ``worker_crashed``,
    # ``degenerate_no_survivors``, etc.). The ledger event with
    # ``outcome="technical_failure"`` is now counted alongside the
    # registry record.
    reasons = {r["name"]: r["count"] for r in fm["top_failure_reasons"]}
    assert reasons.get("worker_crash") == 2  # registry + ledger

    # v3.15.15.6: technical_vs_research_failure_counts ranges over ALL
    # campaigns; degenerate / paper_blocked are first-class buckets.
    tvr = fm["technical_vs_research_failure_counts"]
    assert tvr["technical_failure"] == 1
    assert tvr["research_rejection"] == 0
    assert tvr["degenerate_no_survivors"] == 0
    assert tvr["paper_blocked"] == 0

    # v3.15.15.6: by_worker_id populated from lease.worker_id
    # (synthetic builder sets top-level worker_id; the alias path also
    # works for production records where worker_id lives in lease).
    workers = {w["name"]: w["count"] for w in fm["by_worker_id"]}
    assert workers.get("w-1") == 2  # one from registry + one from ledger

    # v3.15.15.6: diagnostic_context block reports ledger_enriched mode
    # (the harness writes a synthetic ledger so the path is exercised).
    ctx = fm["diagnostic_context"]
    assert ctx["diagnostic_mode"] == "ledger_enriched"
    assert ctx["ledger_available"] is True
    assert ctx["screening_evidence_available"] is False
    assert "screening_evidence_absent" in ctx["limitations"]

    tp = json.loads(sandbox.throughput_metrics_path.read_text(encoding="utf-8"))
    # Technical failures are NOT meaningful — no usable evidence.
    assert tp["meaningful_campaigns_per_day"] == 0.0
    # v3.15.15.6: digest passthroughs are None when no digest is present.
    assert tp["meaningful_by_classification_from_digest"] is None
    assert tp["campaigns_by_type_from_digest"] is None


def test_technical_failure_reason_timeout_classified_correctly(sandbox):
    """Same outcome literal, different reason_code (timeout vs worker_crash)."""
    write_frozen_contracts(sandbox.research_dir)

    record = make_campaign_record(
        campaign_id="c-timeout-1",
        preset_name="ema_1h",
        outcome="technical_failure",
        reason_code="timeout",
        failure_reason="timeout",
        meaningful_classification="uninformative_technical_failure",
        spawned_at_utc="2026-04-28T11:00:00Z",
        finished_at_utc="2026-04-28T11:30:00Z",
        runtime_min=30.0,
        state="failed",
    )
    write_registry(sandbox.registry_path, campaigns=[record])
    write_ledger_jsonl(sandbox.ledger_path, [])

    run_diagnostics_build(sandbox, now_utc=FROZEN_NOW)

    fm = json.loads(sandbox.failure_modes_path.read_text(encoding="utf-8"))
    counts = fm["campaigns_by_outcome_class"]
    assert counts["technical_failure"] == 1
    assert counts["research_rejection"] == 0
    assert counts["unknown"] == 0


def test_legacy_worker_crashed_literal_classified_as_technical_failure(sandbox):
    """Scenario B2 — pre-v3.15.5 backward-compat literal."""
    write_frozen_contracts(sandbox.research_dir)

    record = make_campaign_record(
        campaign_id="c-legacy-1",
        preset_name="vol_compression_breakout_crypto_1h",
        outcome="worker_crashed",
        reason_code="worker_crash",
        failure_reason="worker_crash",
        meaningful_classification="uninformative_technical_failure",
        spawned_at_utc="2026-04-27T11:00:00Z",
        finished_at_utc="2026-04-27T11:00:15Z",
        runtime_min=0.25,
        state="failed",
    )
    write_registry(sandbox.registry_path, campaigns=[record])
    write_ledger_jsonl(
        sandbox.ledger_path,
        [
            make_ledger_event(
                campaign_id="c-legacy-1",
                preset_name="vol_compression_breakout_crypto_1h",
                event_type="terminal",
                outcome="worker_crashed",
                failure_reason="worker_crash",
                reason_code="worker_crash",
                meaningful_classification="uninformative_technical_failure",
                at_utc="2026-04-27T11:00:15Z",
            )
        ],
    )

    run_diagnostics_build(sandbox, now_utc=FROZEN_NOW)

    fm = json.loads(sandbox.failure_modes_path.read_text(encoding="utf-8"))
    counts = fm["campaigns_by_outcome_class"]
    # Legacy literal collapses into the technical_failure class.
    assert counts["technical_failure"] == 1
    assert counts["unknown"] == 0
    # Verified explicitly: the legacy literal is in the raw outcome counter.
    raw = {row["name"]: row["count"] for row in fm["campaigns_by_outcome"]}
    assert raw.get("worker_crashed") == 1

    tp = json.loads(sandbox.throughput_metrics_path.read_text(encoding="utf-8"))
    assert tp["meaningful_campaigns_per_day"] == 0.0
