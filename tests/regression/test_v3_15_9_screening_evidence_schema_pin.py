"""v3.15.9 regression — pin the screening_evidence schema_version
and top-level/per-candidate field sets so a future change to
``research/screening_evidence.py`` cannot silently drift the
artifact contract.

Mirrors the field-set pin style used in
``test_v312_sidecar_schema_stability.py``.
"""

from __future__ import annotations

from datetime import UTC, datetime

from research.screening_evidence import (
    PER_CANDIDATE_KEYS,
    SCREENING_EVIDENCE_SCHEMA_VERSION,
    TOP_LEVEL_KEYS,
    build_screening_evidence_payload,
)

_EXPECTED_TOP_LEVEL_KEYS = frozenset(
    {
        "schema_version",
        "generated_at_utc",
        "git_revision",
        "run_id",
        "campaign_id",
        "col_campaign_id",
        "preset_name",
        "screening_phase",
        "artifact_fingerprint",
        "summary",
        "candidates",
    }
)
_EXPECTED_PER_CANDIDATE_KEYS = frozenset(
    {
        "candidate_id",
        "identity_fallback_used",
        "strategy_id",
        "strategy_name",
        "asset",
        "interval",
        "hypothesis_id",
        "executable_hypothesis_id",
        "validation_plan_id",
        "run_manifest_id",
        "source_artifact",
        "source_report_kind",
        "source_row_id",
        "qre_validation_linkage_status",
        "qre_validation_linkage_warnings",
        "preset_name",
        "screening_phase",
        "stage_result",
        "pass_kind",
        "screening_criteria_set",
        "metrics",
        "criteria",
        "failure_reasons",
        "near_pass",
        "validation_evidence",
        "sampling",
        "promotion_guard",
        "evidence_fingerprint",
    }
)
_EXPECTED_SUMMARY_KEYS = frozenset(
    {
        "total_candidates",
        "passed_screening",
        "rejected_screening",
        "needs_investigation",
        "promotion_grade_candidates",
        "exploratory_passes",
        "near_passes",
        "coverage_warnings",
        "identity_fallbacks",
        "dominant_failure_reasons",
    }
)


def test_schema_version_pinned_at_1_1() -> None:
    assert SCREENING_EVIDENCE_SCHEMA_VERSION == "1.1"


def test_module_constant_top_level_keys_match_pinned_set() -> None:
    assert TOP_LEVEL_KEYS == _EXPECTED_TOP_LEVEL_KEYS


def test_module_constant_per_candidate_keys_match_pinned_set() -> None:
    assert PER_CANDIDATE_KEYS == _EXPECTED_PER_CANDIDATE_KEYS


def test_emitted_payload_top_level_keys_match() -> None:
    payload = build_screening_evidence_payload(
        run_id="run-1",
        as_of_utc=datetime(2026, 4, 26, tzinfo=UTC),
        git_revision="abc",
        campaign_id="cmp-1",
        col_campaign_id="cmp-1",
        preset_name="preset_a",
        screening_phase="exploratory",
        candidates=[],
        screening_records=[],
        screening_pass_kinds={},
        paper_blocked_index={},
    )
    assert set(payload.keys()) == _EXPECTED_TOP_LEVEL_KEYS
    assert set(payload["summary"].keys()) == _EXPECTED_SUMMARY_KEYS


def test_screening_evidence_carries_validation_evidence_status() -> None:
    payload = build_screening_evidence_payload(
        run_id="run-1",
        as_of_utc=datetime(2026, 4, 26, 12, 0, 0, tzinfo=UTC),
        git_revision="abc123",
        campaign_id="cmp-1",
        col_campaign_id="cmp-1",
        preset_name="trend_pullback_equities_4h",
        screening_phase="exploratory",
        candidates=[
            {
                "candidate_id": "candidate-1",
                "strategy_id": "trend_pullback_v1",
                "strategy_name": "trend_pullback_v1",
                "asset": "NVDA",
                "interval": "4h",
                "validation": {
                    "status": "validated",
                    "evidence_status": "no_oos_trades",
                    "oos_trade_count": 0,
                    "min_oos_trades": 10,
                },
            }
        ],
        screening_records=[
            {
                "candidate_id": "candidate-1",
                "final_status": "passed",
                "decision": "promoted_to_validation",
                "diagnostic_metrics": {},
            }
        ],
        screening_pass_kinds={"trend_pullback_v1": "exploratory"},
        paper_blocked_index={},
    )

    assert payload["candidates"][0]["validation_evidence"] == {
        "status": "no_oos_trades",
        "oos_trade_count": 0,
        "min_oos_trades": 10,
    }
