"""Unit tests for research.integrity check functions.

Covers each pure check function under pass / fail conditions and
verifies the typed reason codes propagate unchanged. Also covers
IntegrityReport aggregation and the ArtifactIntegrityError typing.

The D4 boundary rule — integrity emits evidence only, never a
promotion status — is pinned separately in the regression suite; here
we just confirm the typed-reason-code vocabulary is stable.
"""

from __future__ import annotations

import pytest

from research.integrity import (
    ARTIFACT_INCOMPLETE,
    ARTIFACT_RUNID_MISMATCH,
    ArtifactIntegrityError,
    DATA_INSUFFICIENT_BARS,
    EVAL_INSUFFICIENT_OOS_BARS,
    EVAL_INSUFFICIENT_TRADES,
    EVAL_NO_VALID_FOLDS,
    FEATURE_INCOMPLETE,
    FEATURE_WARMUP_STARVED,
    IntegrityCheck,
    IntegrityReport,
    REASON_CODES,
    STRATEGY_NOT_APPLICABLE,
    check_artifact_integrity,
    check_data_sufficiency,
    check_evaluation_completeness,
    check_feature_completeness,
    check_strategy_applicability,
)


def test_reason_codes_frozenset_is_stable():
    expected = {
        "DATA_INSUFFICIENT_BARS",
        "DATA_NO_OVERLAP",
        "FEATURE_WARMUP_STARVED",
        "FEATURE_INCOMPLETE",
        "STRATEGY_MISSING_FEATURES",
        "STRATEGY_NOT_APPLICABLE",
        "EVAL_INSUFFICIENT_TRADES",
        "EVAL_INSUFFICIENT_OOS_BARS",
        "EVAL_NO_VALID_FOLDS",
        "ARTIFACT_INCOMPLETE",
        "ARTIFACT_RUNID_MISMATCH",
    }
    assert set(REASON_CODES) == expected


def test_check_data_sufficiency_passes_when_enough_bars():
    check = check_data_sufficiency(asset="BTC/EUR", interval="1h", bar_count=500, min_bars=200)

    assert check.passed is True
    assert check.reason_code is None


def test_check_data_sufficiency_fails_with_typed_reason_when_insufficient():
    check = check_data_sufficiency(asset="BTC/EUR", interval="1h", bar_count=50, min_bars=200)

    assert check.passed is False
    assert check.reason_code == DATA_INSUFFICIENT_BARS
    assert check.details["bar_count"] == 50
    assert check.details["min_bars"] == 200


def test_check_feature_completeness_passes_when_all_features_available():
    check = check_feature_completeness(
        strategy_name="sma_crossover",
        asset="BTC/EUR",
        interval="1h",
        required_features=["sma"],
        available_features=["sma", "ema", "zscore"],
        warmup_bars=50,
        bar_count=200,
    )

    assert check.passed is True
    assert check.reason_code is None


def test_check_feature_completeness_fails_with_feature_incomplete_for_missing_feature():
    check = check_feature_completeness(
        strategy_name="pairs_zscore",
        asset="BTC/EUR",
        interval="1h",
        required_features=["spread_zscore"],
        available_features=["sma", "ema"],
        warmup_bars=30,
        bar_count=200,
    )

    assert check.passed is False
    assert check.reason_code == FEATURE_INCOMPLETE
    assert "spread_zscore" in check.details["missing_features"]


def test_check_feature_completeness_fails_with_warmup_starved_when_warmup_exceeds_bars():
    check = check_feature_completeness(
        strategy_name="sma_crossover",
        asset="BTC/EUR",
        interval="1h",
        required_features=["sma"],
        available_features=["sma"],
        warmup_bars=500,
        bar_count=100,
    )

    assert check.passed is False
    assert check.reason_code == FEATURE_WARMUP_STARVED
    assert check.details["warmup_bars"] == 500
    assert check.details["bar_count"] == 100


def test_check_strategy_applicability_passes_for_supported_lane():
    check = check_strategy_applicability(
        strategy_name="sma_crossover",
        asset="BTC/EUR",
        interval="1h",
        position_structure="outright",
        initial_lane_support="supported",
    )

    assert check.passed is True
    assert check.reason_code is None


def test_check_strategy_applicability_fails_with_not_applicable_for_blocked_lane():
    check = check_strategy_applicability(
        strategy_name="pairs_zscore",
        asset="BTC/EUR",
        interval="1h",
        position_structure="spread",
        initial_lane_support="blocked",
    )

    assert check.passed is False
    assert check.reason_code == STRATEGY_NOT_APPLICABLE


def test_check_evaluation_completeness_passes_when_all_conditions_met():
    check = check_evaluation_completeness(
        strategy_name="sma_crossover",
        asset="BTC/EUR",
        interval="1h",
        totaal_trades=50,
        min_trades=30,
        oos_bar_count=200,
        min_oos_bars=100,
        valid_fold_count=3,
    )

    assert check.passed is True


def test_check_evaluation_completeness_fails_no_valid_folds_first():
    check = check_evaluation_completeness(
        strategy_name="sma_crossover",
        asset="BTC/EUR",
        interval="1h",
        totaal_trades=0,
        min_trades=30,
        oos_bar_count=0,
        min_oos_bars=100,
        valid_fold_count=0,
    )

    assert check.passed is False
    assert check.reason_code == EVAL_NO_VALID_FOLDS


def test_check_evaluation_completeness_fails_with_insufficient_oos_bars():
    check = check_evaluation_completeness(
        strategy_name="sma_crossover",
        asset="BTC/EUR",
        interval="1h",
        totaal_trades=0,
        min_trades=30,
        oos_bar_count=50,
        min_oos_bars=100,
        valid_fold_count=2,
    )

    assert check.passed is False
    assert check.reason_code == EVAL_INSUFFICIENT_OOS_BARS


def test_check_evaluation_completeness_fails_with_insufficient_trades():
    check = check_evaluation_completeness(
        strategy_name="sma_crossover",
        asset="BTC/EUR",
        interval="1h",
        totaal_trades=5,
        min_trades=30,
        oos_bar_count=200,
        min_oos_bars=100,
        valid_fold_count=2,
    )

    assert check.passed is False
    assert check.reason_code == EVAL_INSUFFICIENT_TRADES


def test_check_artifact_integrity_passes_when_all_run_ids_match():
    check = check_artifact_integrity(
        state_payload={"run_id": "run-1", "status": "aborted"},
        manifest_payload={"run_id": "run-1", "status": "aborted"},
        batches_payload={"run_id": "run-1", "batches": []},
    )

    assert check.passed is True
    assert check.details["run_id"] == "run-1"


def test_check_artifact_integrity_fails_incomplete_when_a_payload_is_none():
    check = check_artifact_integrity(
        state_payload={"run_id": "run-1"},
        manifest_payload=None,
        batches_payload={"run_id": "run-1"},
    )

    assert check.passed is False
    assert check.reason_code == ARTIFACT_INCOMPLETE
    assert "manifest" in check.details["missing_or_invalid"]


def test_check_artifact_integrity_fails_runid_mismatch_when_ids_differ():
    check = check_artifact_integrity(
        state_payload={"run_id": "run-a"},
        manifest_payload={"run_id": "run-b"},
        batches_payload={"run_id": "run-a"},
    )

    assert check.passed is False
    assert check.reason_code == ARTIFACT_RUNID_MISMATCH
    assert check.details["run_ids_by_payload"] == {
        "state": "run-a",
        "manifest": "run-b",
        "batches": "run-a",
    }


def test_check_artifact_integrity_fails_when_any_run_id_is_empty_string():
    check = check_artifact_integrity(
        state_payload={"run_id": "run-1"},
        manifest_payload={"run_id": "   "},
        batches_payload={"run_id": "run-1"},
    )

    assert check.passed is False
    assert check.reason_code == ARTIFACT_RUNID_MISMATCH


def test_integrity_check_is_frozen_dataclass():
    check = IntegrityCheck(name="x", passed=True)

    with pytest.raises(Exception):
        check.name = "y"  # type: ignore[misc]


def test_integrity_report_aggregates_rejection_counts_by_reason():
    report = IntegrityReport()
    report.record(IntegrityCheck(name="a", passed=False, reason_code=FEATURE_INCOMPLETE))
    report.record(IntegrityCheck(name="b", passed=False, reason_code=FEATURE_INCOMPLETE))
    report.record(IntegrityCheck(name="c", passed=False, reason_code=DATA_INSUFFICIENT_BARS))
    report.record(IntegrityCheck(name="d", passed=True))

    counts = report.rejection_counts_by_reason()

    assert counts == {FEATURE_INCOMPLETE: 2, DATA_INSUFFICIENT_BARS: 1}


def test_integrity_report_ignores_passing_checks():
    report = IntegrityReport()
    report.record(IntegrityCheck(name="a", passed=True))
    report.record(IntegrityCheck(name="b", passed=True))

    assert report.rejection_counts_by_reason() == {}


def test_artifact_integrity_error_carries_typed_reason_code():
    err = ArtifactIntegrityError("resume refused", reason_code=ARTIFACT_RUNID_MISMATCH)

    assert isinstance(err, RuntimeError)
    assert err.reason_code == ARTIFACT_RUNID_MISMATCH
    assert str(err) == "resume refused"
