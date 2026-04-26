"""v3.15.9 — summary aggregation invariants (REV 3 §6.2 + MF-19).

Pins:
  - dominant_failure_reasons sorted by frequency desc, then alphabetical
  - exploratory_passes counts pass_kind == "exploratory"
  - near_passes counts records with near_pass.is_near_pass == True
  - coverage_warnings counts non-null sampling.coverage_warning
  - identity_fallbacks counts records with identity_fallback_used == True
"""

from __future__ import annotations

from datetime import UTC, datetime

from research.screening_evidence import (
    build_screening_evidence_payload,
    dominant_failure_reasons,
)


def test_dominant_failure_reasons_orders_by_frequency_then_alpha() -> None:
    candidates = [
        {"failure_reasons": ["a"]},
        {"failure_reasons": ["b"]},
        {"failure_reasons": ["a"]},
        {"failure_reasons": ["c", "b"]},
        {"failure_reasons": ["a"]},
    ]
    # a:3, b:2, c:1 -> ["a", "b", "c"]
    assert dominant_failure_reasons(candidates) == ["a", "b", "c"]


def test_dominant_failure_reasons_alphabetical_tiebreak() -> None:
    candidates = [
        {"failure_reasons": ["zeta"]},
        {"failure_reasons": ["alpha"]},
        {"failure_reasons": ["mu"]},
    ]
    assert dominant_failure_reasons(candidates) == ["alpha", "mu", "zeta"]


def test_dominant_failure_reasons_empty() -> None:
    assert dominant_failure_reasons([]) == []
    assert dominant_failure_reasons([{"failure_reasons": []}]) == []


def test_summary_counts_near_passes_and_coverage_warnings() -> None:
    candidate = {
        "candidate_id": "c1",
        "strategy_id": "s1",
        "strategy_name": "s1",
        "asset": "BTC",
        "interval": "1h",
    }
    near_pass_record = {
        "candidate_id": "c1",
        "final_status": "rejected",
        "reason_code": "expectancy_not_positive",
        "screening_criteria_set": "exploratory",
        "diagnostic_metrics": {
            "expectancy": -0.0001,  # inside near band
            "profit_factor": 1.5,
            "win_rate": 0.4,
            "max_drawdown": 0.2,
        },
        "sampling": {
            "grid_size": None, "sampled_count": 1, "coverage_pct": None,
            "sampling_policy": "grid_size_unavailable",
            "sampled_parameter_digest": "",
            "coverage_warning": "grid_size_unavailable",
        },
    }
    payload = build_screening_evidence_payload(
        run_id="run-1",
        as_of_utc=datetime(2026, 4, 26, tzinfo=UTC),
        git_revision="abc",
        campaign_id="cmp-1",
        col_campaign_id="cmp-1",
        preset_name="preset_a",
        screening_phase="exploratory",
        candidates=[candidate],
        screening_records=[near_pass_record],
        screening_pass_kinds={},
        paper_blocked_index={},
    )
    summary = payload["summary"]
    assert summary["near_passes"] == 1
    assert summary["coverage_warnings"] == 1
    assert summary["rejected_screening"] == 1
    assert summary["passed_screening"] == 0


def test_summary_counts_exploratory_passes() -> None:
    candidate = {
        "candidate_id": "c1",
        "strategy_id": "s1",
        "strategy_name": "s1",
        "asset": "BTC",
        "interval": "1h",
    }
    record = {
        "candidate_id": "c1",
        "final_status": "passed",
        "decision": "promoted_to_validation",
        "screening_criteria_set": "exploratory",
        "diagnostic_metrics": {"expectancy": 0.001, "profit_factor": 1.5,
                               "win_rate": 0.4, "max_drawdown": 0.2},
        "sampling": {"grid_size": 1, "sampled_count": 1, "coverage_pct": 1.0,
                     "sampling_policy": "full_coverage",
                     "sampled_parameter_digest": "abc",
                     "coverage_warning": None},
    }
    payload = build_screening_evidence_payload(
        run_id="run-1",
        as_of_utc=datetime(2026, 4, 26, tzinfo=UTC),
        git_revision="abc",
        campaign_id="cmp-1",
        col_campaign_id="cmp-1",
        preset_name="preset_a",
        screening_phase="exploratory",
        candidates=[candidate],
        screening_records=[record],
        screening_pass_kinds={"s1": "exploratory"},
        paper_blocked_index={},
    )
    summary = payload["summary"]
    assert summary["exploratory_passes"] == 1
    assert summary["needs_investigation"] == 1
    assert summary["passed_screening"] == 1
    assert summary["promotion_grade_candidates"] == 0
