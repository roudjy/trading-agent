from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

from research import campaign_launcher as launcher
from research.campaign_policy import CampaignDecision, DecisionRecord
from research.campaign_registry import build_campaign_id


def _write_evidence(
    path: Path,
    *,
    owner: str | None,
    summary: dict,
    campaign_alias: str | None = None,
) -> Path:
    path.write_text(
        json.dumps(
            {
                "schema_version": "1.1",
                "run_id": "run-owned",
                "campaign_id": campaign_alias,
                "col_campaign_id": owner,
                "artifact_fingerprint": "fingerprint-1",
                "summary": summary,
                "candidates": [],
            }
        ),
        encoding="utf-8",
    )
    return path


def test_owned_evidence_builds_promotion_gate_diagnostics(
    tmp_path: Path,
) -> None:
    campaign_id = "col-owned"
    evidence = _write_evidence(
        tmp_path / "screening.json",
        owner=campaign_id,
        summary={
            "total_candidates": 15,
            "passed_screening": 6,
            "rejected_screening": 9,
            "promotion_grade_candidates": 0,
            "exploratory_passes": 0,
            "near_passes": 0,
            "sufficient_oos_evidence_candidates": 1,
            "dominant_failure_reasons": ["insufficient_trades"],
        },
    )

    diagnostic = launcher._load_owned_gate_diagnostics(
        campaign_id=campaign_id,
        path=evidence,
    )

    assert diagnostic is not None
    assert diagnostic["owner_verified"] is True
    assert diagnostic["classification"] == "promotion_gate_rejected_all"
    assert diagnostic["stage"] == "promotion"
    assert diagnostic["counts"]["total_candidates"] == 15
    assert diagnostic["counts"]["passed_screening"] == 6
    assert diagnostic["counts"]["promotion_grade_candidates"] == 0
    assert diagnostic["dominant_failure_reasons"] == ["insufficient_trades"]


def test_zero_screening_passes_are_attributed_to_screening(
    tmp_path: Path,
) -> None:
    evidence = _write_evidence(
        tmp_path / "screening.json",
        owner="col-owned",
        summary={
            "total_candidates": 12,
            "passed_screening": 0,
            "rejected_screening": 12,
            "promotion_grade_candidates": 0,
            "dominant_failure_reasons": ["screening_criteria_not_met"],
        },
    )

    diagnostic = launcher._load_owned_gate_diagnostics(
        campaign_id="col-owned",
        path=evidence,
    )

    assert diagnostic is not None
    assert diagnostic["classification"] == "screening_rejected_all"
    assert diagnostic["stage"] == "screening"


def test_mismatched_authoritative_owner_fails_closed(
    tmp_path: Path,
) -> None:
    evidence = _write_evidence(
        tmp_path / "screening.json",
        owner="col-other",
        campaign_alias="col-current",
        summary={
            "total_candidates": 15,
            "passed_screening": 6,
            "promotion_grade_candidates": 0,
        },
    )

    assert (
        launcher._load_owned_gate_diagnostics(
            campaign_id="col-current",
            path=evidence,
        )
        is None
    )


def test_campaign_alias_is_fallback_when_col_owner_is_absent(
    tmp_path: Path,
) -> None:
    evidence = _write_evidence(
        tmp_path / "screening.json",
        owner=None,
        campaign_alias="col-current",
        summary={
            "total_candidates": 3,
            "passed_screening": 1,
            "rejected_screening": 2,
            "promotion_grade_candidates": 0,
        },
    )

    diagnostic = launcher._load_owned_gate_diagnostics(
        campaign_id="col-current",
        path=evidence,
    )

    assert diagnostic is not None
    assert diagnostic["classification"] == "promotion_gate_rejected_all"


def test_missing_malformed_and_missing_summary_fail_closed(
    tmp_path: Path,
) -> None:
    missing = tmp_path / "missing.json"
    malformed = tmp_path / "malformed.json"
    missing_summary = tmp_path / "missing-summary.json"

    malformed.write_text("{not-json", encoding="utf-8")
    missing_summary.write_text(
        json.dumps(
            {
                "col_campaign_id": "col-current",
                "run_id": "run-owned",
            }
        ),
        encoding="utf-8",
    )

    for path in (missing, malformed, missing_summary):
        assert (
            launcher._load_owned_gate_diagnostics(
                campaign_id="col-current",
                path=path,
            )
            is None
        )


def test_negative_and_non_numeric_counts_are_bounded_to_zero(
    tmp_path: Path,
) -> None:
    evidence = _write_evidence(
        tmp_path / "screening.json",
        owner="col-owned",
        summary={
            "total_candidates": "4",
            "passed_screening": -3,
            "rejected_screening": "invalid",
            "promotion_grade_candidates": 0,
        },
    )

    diagnostic = launcher._load_owned_gate_diagnostics(
        campaign_id="col-owned",
        path=evidence,
    )

    assert diagnostic is not None
    assert diagnostic["counts"]["total_candidates"] == 4
    assert diagnostic["counts"]["passed_screening"] == 0
    assert diagnostic["counts"]["rejected_screening"] == 0
    assert diagnostic["classification"] == "screening_rejected_all"


def test_terminal_completed_no_survivor_persists_owned_gate_diagnostics(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    Path("research").mkdir(parents=True, exist_ok=True)

    now_utc = datetime(2026, 6, 20, 12, 0, 0, tzinfo=UTC)
    fingerprint = "owned-screening-evidence-fingerprint"
    preset_name = "trend_pullback_equities_4h"
    template_id = "test-template"

    campaign_id = build_campaign_id(
        preset_name=preset_name,
        now_utc=now_utc,
        parent_or_lineage_root="",
        input_artifact_fingerprint=fingerprint,
    )

    Path("research/screening_evidence_latest.v1.json").write_text(
        json.dumps(
            {
                "schema_version": "1.1",
                "run_id": "run-owned",
                "campaign_id": campaign_id,
                "col_campaign_id": campaign_id,
                "artifact_fingerprint": "screening-fingerprint",
                "summary": {
                    "total_candidates": 15,
                    "passed_screening": 6,
                    "rejected_screening": 9,
                    "promotion_grade_candidates": 0,
                    "exploratory_passes": 0,
                    "near_passes": 0,
                    "sufficient_oos_evidence_candidates": 1,
                    "dominant_failure_reasons": ["insufficient_trades"],
                },
                "candidates": [],
            }
        ),
        encoding="utf-8",
    )

    decision = CampaignDecision(
        decision=DecisionRecord(
            action="spawn",
            reason="test",
            template_id=template_id,
            preset_name=preset_name,
            campaign_type="daily_primary",
            priority_tier=2,
            spawn_reason="test",
            parent_campaign_id=None,
            lineage_root_campaign_id="",
            subtype=None,
            estimate_seconds=10,
            extra={"input_artifact_fingerprint": fingerprint},
        ),
        rules_evaluated=(),
        candidates_considered=(),
        tie_break_key=(),
    )

    monkeypatch.setattr(
        launcher,
        "build_campaign_id",
        lambda **_kwargs: campaign_id,
    )
    monkeypatch.setattr(
        launcher,
        "_invoke_subprocess",
        lambda **_kwargs: (0, 7.0),
    )
    monkeypatch.setattr(
        launcher,
        "add_reservation",
        lambda budget, **_kwargs: budget,
    )
    monkeypatch.setattr(
        launcher,
        "settle_reservation",
        lambda budget, **_kwargs: budget,
    )

    registry, queue, events = launcher._apply_decision(
        decision=decision,
        registry={"campaigns": {}},
        queue={"queue": []},
        budget=object(),
        events=[],
        now_utc=now_utc,
        config=SimpleNamespace(lease_ttl_seconds=300),
        skip_subprocess=False,
    )

    record = registry["campaigns"][campaign_id]
    diagnostic = record["extra"]["gate_diagnostics"]

    assert record["state"] == "completed"
    assert record["outcome"] == "completed_no_survivor"
    assert diagnostic["owner_verified"] is True
    assert diagnostic["classification"] == "promotion_gate_rejected_all"
    assert diagnostic["counts"]["passed_screening"] == 6

    terminal_event = next(event for event in events if event.event_type == "campaign_completed")

    assert terminal_event.outcome == "completed_no_survivor"
    assert terminal_event.extra["gate_diagnostics"] == diagnostic

    queue_entry = next(entry for entry in queue["queue"] if entry["campaign_id"] == campaign_id)
    assert queue_entry["state"] == "completed"
