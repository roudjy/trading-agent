"""v3.15.11 — research evidence ledger unit tests."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest

from research._sidecar_io import serialize_canonical
from research.research_evidence_ledger import (
    EVIDENCE_LEDGER_SCHEMA_VERSION,
    UNKNOWN,
    build_research_evidence_payload,
    write_research_evidence_artifact,
)


_AS_OF = datetime(2026, 4, 27, 12, 0, 0, tzinfo=UTC)


def _completed_event(
    *,
    campaign_id: str,
    preset: str,
    family: str | None,
    asset: str | None,
    outcome: str,
    reason: str = "none",
    meaningful: str | None = None,
    at_utc: str = "2026-04-27T11:00:00+00:00",
    run_id: str = "run_a",
) -> dict[str, Any]:
    return {
        "event_id": f"id-{campaign_id}-{outcome}-{at_utc}",
        "campaign_id": campaign_id,
        "parent_campaign_id": None,
        "lineage_root_campaign_id": campaign_id,
        "preset_name": preset,
        "strategy_family": family,
        "asset_class": asset,
        "campaign_type": "discovery",
        "event_type": "campaign_completed",
        "reason_code": reason,
        "outcome": outcome,
        "meaningful_classification": meaningful,
        "run_id": run_id,
        "source_artifact": None,
        "at_utc": at_utc,
        "extra": {},
    }


def test_empty_inputs_produce_valid_empty_ledger() -> None:
    payload = build_research_evidence_payload(
        run_id=None,
        col_campaign_id=None,
        as_of_utc=_AS_OF,
        git_revision=None,
        events=[],
        screening_evidence=None,
        candidate_registry=None,
    )
    assert payload["schema_version"] == EVIDENCE_LEDGER_SCHEMA_VERSION
    assert payload["hypothesis_evidence"] == []
    assert payload["failure_mode_counts"] == []
    assert payload["candidate_lineage"] == []
    assert payload["summary"] == {
        "campaign_count": 0,
        "hypothesis_count": 0,
        "failure_mode_count": 0,
        "candidate_lineage_count": 0,
    }


def test_rejected_campaign_increments_rejection_and_failure_mode() -> None:
    events = [
        _completed_event(
            campaign_id="c1",
            preset="trend_pullback_crypto_1h",
            family="trend_pullback",
            asset="crypto",
            outcome="research_rejection",
            reason="screening_criteria_not_met",
        )
    ]
    payload = build_research_evidence_payload(
        run_id="run_a",
        col_campaign_id=None,
        as_of_utc=_AS_OF,
        git_revision=None,
        events=events,
        screening_evidence=None,
        candidate_registry=None,
    )
    assert len(payload["hypothesis_evidence"]) == 1
    row = payload["hypothesis_evidence"][0]
    assert row["rejection_count"] == 1
    assert row["technical_failure_count"] == 0
    assert row["degenerate_count"] == 0
    assert row["dominant_failure_mode"] == "screening_criteria_not_met"
    failure_modes = payload["failure_mode_counts"]
    assert any(
        fm["scope_type"] == "preset"
        and fm["scope_id"] == "trend_pullback_crypto_1h"
        and fm["failure_mode"] == "screening_criteria_not_met"
        and fm["count"] == 1
        for fm in failure_modes
    )
    assert any(
        fm["scope_type"] == "strategy_family"
        and fm["scope_id"] == "trend_pullback"
        for fm in failure_modes
    )


def test_exploratory_pass_increments_exploratory_count() -> None:
    events = [
        _completed_event(
            campaign_id="c1",
            preset="trend_pullback_crypto_1h",
            family="trend_pullback",
            asset="crypto",
            outcome="completed_with_candidates",
            meaningful="exploratory_pass",
        )
    ]
    payload = build_research_evidence_payload(
        run_id="run_a",
        col_campaign_id=None,
        as_of_utc=_AS_OF,
        git_revision=None,
        events=events,
        screening_evidence=None,
        candidate_registry=None,
    )
    row = payload["hypothesis_evidence"][0]
    assert row["exploratory_pass_count"] == 1
    assert row["promotion_candidate_count"] == 1
    assert row["rejection_count"] == 0
    # No failure mode emitted for a successful campaign.
    assert payload["failure_mode_counts"] == []


def test_degenerate_outcome_does_not_count_as_technical_failure() -> None:
    events = [
        _completed_event(
            campaign_id="c1",
            preset="mr_reversion_eth_15m",
            family="mean_reversion",
            asset="crypto",
            outcome="degenerate_no_survivors",
        )
    ]
    payload = build_research_evidence_payload(
        run_id="run_a",
        col_campaign_id=None,
        as_of_utc=_AS_OF,
        git_revision=None,
        events=events,
        screening_evidence=None,
        candidate_registry=None,
    )
    row = payload["hypothesis_evidence"][0]
    assert row["degenerate_count"] == 1
    assert row["technical_failure_count"] == 0
    assert row["rejection_count"] == 0
    assert row["last_outcome"] == "degenerate"


def test_repeated_failure_mode_increments_counter_and_tracks_last_seen() -> None:
    events = [
        _completed_event(
            campaign_id="c1",
            preset="p1",
            family="f1",
            asset="crypto",
            outcome="research_rejection",
            reason="insufficient_trades",
            at_utc="2026-04-25T10:00:00+00:00",
        ),
        _completed_event(
            campaign_id="c2",
            preset="p1",
            family="f1",
            asset="crypto",
            outcome="research_rejection",
            reason="insufficient_trades",
            at_utc="2026-04-26T10:00:00+00:00",
        ),
        _completed_event(
            campaign_id="c3",
            preset="p1",
            family="f1",
            asset="crypto",
            outcome="research_rejection",
            reason="insufficient_trades",
            at_utc="2026-04-27T10:00:00+00:00",
        ),
    ]
    payload = build_research_evidence_payload(
        run_id="run_a",
        col_campaign_id=None,
        as_of_utc=_AS_OF,
        git_revision=None,
        events=events,
        screening_evidence=None,
        candidate_registry=None,
    )
    row = payload["hypothesis_evidence"][0]
    assert row["rejection_count"] == 3
    assert row["dominant_failure_mode"] == "insufficient_trades"
    preset_failures = [
        fm
        for fm in payload["failure_mode_counts"]
        if fm["scope_type"] == "preset" and fm["failure_mode"] == "insufficient_trades"
    ]
    assert preset_failures and preset_failures[0]["count"] == 3
    assert preset_failures[0]["last_seen_at_utc"] == "2026-04-27T10:00:00+00:00"


def test_missing_optional_artifacts_do_not_crash_and_yield_unknown() -> None:
    events = [
        _completed_event(
            campaign_id="c1",
            preset="p1",
            family=None,
            asset=None,
            outcome="research_rejection",
            reason="screening_criteria_not_met",
        )
    ]
    payload = build_research_evidence_payload(
        run_id=None,
        col_campaign_id=None,
        as_of_utc=_AS_OF,
        git_revision=None,
        events=events,
        screening_evidence=None,
        candidate_registry=None,
    )
    row = payload["hypothesis_evidence"][0]
    assert row["hypothesis_id"] == UNKNOWN
    assert row["strategy_family"] == UNKNOWN
    assert payload["candidate_lineage"] == []
    # No asset → no asset_timeframe failure-mode row, but preset row exists.
    assert any(
        fm["scope_type"] == "preset" for fm in payload["failure_mode_counts"]
    )
    assert not any(
        fm["scope_type"] == "asset_timeframe" for fm in payload["failure_mode_counts"]
    )


def test_screening_evidence_enriches_hypothesis_id() -> None:
    events = [
        _completed_event(
            campaign_id="c1",
            preset="trend_pullback_crypto_1h",
            family="trend_pullback",
            asset="crypto",
            outcome="completed_with_candidates",
            meaningful="exploratory_pass",
        )
    ]
    screening = {
        "candidates": [
            {
                "preset_name": "trend_pullback_crypto_1h",
                "hypothesis_id": "hyp_42",
                "stage_result": "needs_investigation",
            }
        ]
    }
    payload = build_research_evidence_payload(
        run_id="run_a",
        col_campaign_id=None,
        as_of_utc=_AS_OF,
        git_revision=None,
        events=events,
        screening_evidence=screening,
        candidate_registry=None,
    )
    row = payload["hypothesis_evidence"][0]
    assert row["hypothesis_id"] == "hyp_42"


def test_candidate_registry_lineage_counts_run_events() -> None:
    events = [
        _completed_event(
            campaign_id="c1",
            preset="p1",
            family="f1",
            asset="crypto",
            outcome="completed_with_candidates",
            run_id="run_x",
        ),
        _completed_event(
            campaign_id="c2",
            preset="p1",
            family="f1",
            asset="crypto",
            outcome="completed_with_candidates",
            run_id="run_x",
        ),
    ]
    registry = {
        "candidates": [
            {
                "candidate_id": "cand_1",
                "hypothesis_id": "hyp_1",
                "preset_name": "p1",
                "origin_campaign_id": "c1",
                "last_run_id": "run_x",
                "status": "candidate",
            }
        ]
    }
    payload = build_research_evidence_payload(
        run_id="run_x",
        col_campaign_id=None,
        as_of_utc=_AS_OF,
        git_revision=None,
        events=events,
        screening_evidence=None,
        candidate_registry=registry,
    )
    lineage = payload["candidate_lineage"]
    assert len(lineage) == 1
    assert lineage[0]["candidate_id"] == "cand_1"
    assert lineage[0]["evidence_count"] == 2
    assert lineage[0]["current_stage"] == "promotion"


def test_byte_identical_output_for_repeated_build() -> None:
    events = [
        _completed_event(
            campaign_id="c1",
            preset="p1",
            family="f1",
            asset="crypto",
            outcome="research_rejection",
            reason="insufficient_trades",
        )
    ]
    p1 = build_research_evidence_payload(
        run_id="run_a",
        col_campaign_id=None,
        as_of_utc=_AS_OF,
        git_revision="abc123",
        events=events,
        screening_evidence=None,
        candidate_registry=None,
    )
    p2 = build_research_evidence_payload(
        run_id="run_a",
        col_campaign_id=None,
        as_of_utc=_AS_OF,
        git_revision="abc123",
        events=events,
        screening_evidence=None,
        candidate_registry=None,
    )
    assert serialize_canonical(p1) == serialize_canonical(p2)


def test_io_wrapper_writes_artifact_and_creates_subdir(
    tmp_path: Path,
) -> None:
    out = tmp_path / "research" / "campaigns" / "evidence" / "evidence_ledger_latest.v1.json"
    payload = write_research_evidence_artifact(
        run_id="run_z",
        col_campaign_id="col_42",
        as_of_utc=_AS_OF,
        git_revision="deadbeef",
        output_path=out,
        campaign_event_ledger_path=tmp_path / "missing.jsonl",
        campaign_registry_path=tmp_path / "missing_registry.json",
        screening_evidence_path=tmp_path / "missing_screening.json",
        candidate_registry_path=tmp_path / "missing_candidates.json",
    )
    assert out.exists()
    text = out.read_text(encoding="utf-8")
    assert text.endswith("\n")
    assert payload["schema_version"] == EVIDENCE_LEDGER_SCHEMA_VERSION
    assert payload["hypothesis_evidence"] == []


def test_byte_identical_disk_write_for_repeated_build(tmp_path: Path) -> None:
    """Atomic-write produces the same bytes when inputs are unchanged."""
    out_a = tmp_path / "a.json"
    out_b = tmp_path / "b.json"
    write_research_evidence_artifact(
        run_id="run_z",
        col_campaign_id=None,
        as_of_utc=_AS_OF,
        git_revision="x",
        output_path=out_a,
        campaign_event_ledger_path=tmp_path / "missing.jsonl",
        campaign_registry_path=tmp_path / "m1.json",
        screening_evidence_path=tmp_path / "m2.json",
        candidate_registry_path=tmp_path / "m3.json",
    )
    write_research_evidence_artifact(
        run_id="run_z",
        col_campaign_id=None,
        as_of_utc=_AS_OF,
        git_revision="x",
        output_path=out_b,
        campaign_event_ledger_path=tmp_path / "missing.jsonl",
        campaign_registry_path=tmp_path / "m1.json",
        screening_evidence_path=tmp_path / "m2.json",
        candidate_registry_path=tmp_path / "m3.json",
    )
    assert out_a.read_bytes() == out_b.read_bytes()


@pytest.mark.parametrize(
    "outcome,expected_count_field",
    [
        ("research_rejection", "rejection_count"),
        ("technical_failure", "technical_failure_count"),
        ("degenerate_no_survivors", "degenerate_count"),
        ("completed_with_candidates", "promotion_candidate_count"),
    ],
)
def test_outcome_routing(outcome: str, expected_count_field: str) -> None:
    events = [
        _completed_event(
            campaign_id="c1",
            preset="p1",
            family="f1",
            asset="crypto",
            outcome=outcome,
        )
    ]
    payload = build_research_evidence_payload(
        run_id=None,
        col_campaign_id=None,
        as_of_utc=_AS_OF,
        git_revision=None,
        events=events,
        screening_evidence=None,
        candidate_registry=None,
    )
    row = payload["hypothesis_evidence"][0]
    assert row[expected_count_field] == 1
