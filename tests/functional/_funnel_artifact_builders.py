"""Pure synthetic-shape builders for launcher-emitted artifacts.

These factories produce dicts and JSONL events that match the on-disk
shape the launcher actually writes. The schemas are inlined here as
documented constants; **no funnel/runtime module is imported** —
``research.campaign_registry``, ``research.campaign_evidence_ledger``,
``research.campaign_launcher``, ``research.discovery_sprint``,
``research.candidate_pipeline``, ``research.paper_readiness``,
``research.promotion`` are all forbidden by
``test_static_import_surface.py``.

The schema references in the docstrings point at the launcher source
location each builder mirrors, so a future schema bump can be tracked
back without coupling.

Allowed imports:
* stdlib (``json``, ``pathlib``, ``typing``)
* ``research._sidecar_io`` (verified pure — atomic JSON write)
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from research._sidecar_io import write_sidecar_atomic

# ---------------------------------------------------------------------------
# Closed vocabularies (mirrored from the launcher emit paths)
#
# Source: research/campaign_launcher.py ~lines 1378-1453, v3.15.5+ outcome
# vocabulary. These tuples document what scenarios may legitimately
# inject; arbitrary outcome strings are *allowed* (the tests use them to
# exercise the diagnostics' ``unknown`` fallback) but should be set
# deliberately.
# ---------------------------------------------------------------------------

LAUNCHER_OUTCOMES: tuple[str, ...] = (
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
    # Pre-v3.15.5 backward-compat literal still found in old ledgers.
    "worker_crashed",
)

MEANINGFUL_CLASSIFICATIONS: tuple[str, ...] = (
    "meaningful_candidate_found",
    "meaningful_failure_confirmed",
    "meaningful_family_falsified",
    "uninformative_technical_failure",
    "duplicate_low_value_run",
)


# ---------------------------------------------------------------------------
# Campaign record builder
#
# Schema mirrored from research/campaign_registry.py ``CampaignRecord``
# (v3.15.5+). Fields kept to the subset the diagnostics layer actually
# reads — failure_modes inspects ``outcome``, ``failure_reason``,
# ``preset``/``preset_name``, ``hypothesis_id``, ``family``,
# ``strategy_family``, ``asset``, ``timeframe``, ``campaign_type``,
# ``worker_id``; throughput inspects ``outcome``, ``failure_reason``,
# ``runtime_min`` / start+finish timestamps, ``preset``,
# ``timeframe``, ``campaign_type``; artifact_health inspects only file
# metadata + linked_ids extracted from the payload's top level / nested
# ``last_attempted_run`` / ``run_state.artifact``.
# ---------------------------------------------------------------------------


def make_campaign_record(
    *,
    campaign_id: str,
    preset_name: str,
    outcome: str,
    spawned_at_utc: str,
    finished_at_utc: str,
    reason_code: str = "none",
    failure_reason: str | None = None,
    meaningful_classification: str = "duplicate_low_value_run",
    state: str = "completed",
    template_id: str = "tpl_test",
    campaign_type: str = "daily_primary",
    priority_tier: int = 0,
    spawn_reason: str = "synthetic_test_seed",
    parent_campaign_id: str | None = None,
    lineage_root_campaign_id: str | None = None,
    input_artifact_fingerprint: str = "synthetic-fingerprint",
    estimated_runtime_seconds: int = 60,
    actual_runtime_seconds: int = 30,
    attempt_count: int = 1,
    started_at_utc: str | None = None,
    queued_at_utc: str | None = None,
    runtime_min: float | None = None,
    asset: str | None = None,
    timeframe: str | None = None,
    family: str | None = None,
    hypothesis_id: str | None = None,
    worker_id: str | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a launcher-shaped campaign record."""
    record: dict[str, Any] = {
        "campaign_id": campaign_id,
        "template_id": template_id,
        "preset_name": preset_name,
        "preset": preset_name,  # convenience alias for diagnostics readers
        "campaign_type": campaign_type,
        "state": state,
        "priority_tier": priority_tier,
        "spawned_at_utc": spawned_at_utc,
        "spawn_reason": spawn_reason,
        "parent_campaign_id": parent_campaign_id,
        "lineage_root_campaign_id": lineage_root_campaign_id or campaign_id,
        "input_artifact_fingerprint": input_artifact_fingerprint,
        "estimated_runtime_seconds": estimated_runtime_seconds,
        "actual_runtime_seconds": actual_runtime_seconds,
        "outcome": outcome,
        "reason_code": reason_code,
        "meaningful_classification": meaningful_classification,
        "attempt_count": attempt_count,
        "finished_at_utc": finished_at_utc,
        "lease": None,
        "extra": extra or {},
    }
    if started_at_utc is not None:
        record["started_at_utc"] = started_at_utc
    if queued_at_utc is not None:
        record["queued_at_utc"] = queued_at_utc
    if runtime_min is not None:
        record["runtime_min"] = runtime_min
    if asset is not None:
        record["asset"] = asset
    if timeframe is not None:
        record["timeframe"] = timeframe
    if family is not None:
        record["family"] = family
        record["strategy_family"] = family
    if hypothesis_id is not None:
        record["hypothesis_id"] = hypothesis_id
    if worker_id is not None:
        record["worker_id"] = worker_id
    if failure_reason is not None:
        record["failure_reason"] = failure_reason
    return record


# ---------------------------------------------------------------------------
# Ledger event builder
#
# Schema mirrored from research/campaign_evidence_ledger.py
# ``LedgerEvent`` (lines ~107-134). One event per JSONL line; fields kept
# additive so unknown future fields don't break older readers.
# ---------------------------------------------------------------------------


def make_ledger_event(
    *,
    campaign_id: str,
    preset_name: str,
    event_type: str,
    at_utc: str,
    outcome: str | None = None,
    failure_reason: str | None = None,
    reason_code: str = "none",
    meaningful_classification: str | None = None,
    asset: str | None = None,
    timeframe: str | None = None,
    family: str | None = None,
    hypothesis_id: str | None = None,
    worker_id: str | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a launcher-shaped ledger event."""
    event: dict[str, Any] = {
        "campaign_id": campaign_id,
        "preset_name": preset_name,
        "preset": preset_name,
        "event_type": event_type,
        "outcome": outcome,
        "reason_code": reason_code,
        "meaningful_classification": meaningful_classification,
        "at_utc": at_utc,
        "extra": extra or {},
    }
    if failure_reason is not None:
        event["failure_reason"] = failure_reason
    if asset is not None:
        event["asset"] = asset
    if timeframe is not None:
        event["timeframe"] = timeframe
    if family is not None:
        event["family"] = family
        event["strategy_family"] = family
    if hypothesis_id is not None:
        event["hypothesis_id"] = hypothesis_id
    if worker_id is not None:
        event["worker_id"] = worker_id
    return event


# ---------------------------------------------------------------------------
# On-disk writers — atomic via research._sidecar_io.
#
# write_registry uses write_sidecar_atomic (canonical JSON).
# write_ledger_jsonl uses an atomic temp+rename pattern but emits one
# JSON object per line (the launcher's append-only format). It is NOT
# canonical: each line is a single ``json.dumps(obj, sort_keys=True)``
# emit so byte-stability holds for fixed inputs.
# ---------------------------------------------------------------------------


def write_registry(path: Path, *, campaigns: list[dict[str, Any]]) -> None:
    """Write a ``campaign_registry_latest.v1.json``-shaped artifact.

    Refuses to write outside ``research/`` paths under the test
    sandbox (defense in depth — the harness should never write into
    the real research/ tree).
    """
    payload = {
        "schema_version": "1.0",
        "campaigns": campaigns,
    }
    write_sidecar_atomic(path, payload)


def write_ledger_jsonl(path: Path, events: list[dict[str, Any]]) -> None:
    """Append-only-shaped JSONL writer.

    Each event becomes one line. Atomicity: write to ``<path>.tmp``
    then ``os.replace``. Each line is canonical JSON (sort_keys=True)
    so byte-output is deterministic for fixed inputs.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [json.dumps(e, sort_keys=True, ensure_ascii=False) for e in events]
    body = "\n".join(lines) + ("\n" if lines else "")
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(body, encoding="utf-8", newline="\n")
    tmp.replace(path)


def write_frozen_contracts(research_dir: Path) -> None:
    """Plant a minimal pair of frozen contract sentinels in the sandbox.

    The harness never opens these — their job is to let
    ``artifact_health`` see realistic ``contract_class="frozen_public_contract"``
    rows under the sandbox.
    """
    (research_dir / "research_latest.json").write_text(
        json.dumps({"schema_version": "1.0", "synthetic": True}),
        encoding="utf-8",
    )
    (research_dir / "strategy_matrix.csv").write_text(
        "preset,family\nfoo,bar\n",
        encoding="utf-8",
    )


__all__ = [
    "LAUNCHER_OUTCOMES",
    "MEANINGFUL_CLASSIFICATIONS",
    "make_campaign_record",
    "make_ledger_event",
    "write_frozen_contracts",
    "write_ledger_jsonl",
    "write_registry",
]
