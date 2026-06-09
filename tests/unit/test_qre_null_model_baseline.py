from research.qre_null_model_baseline import (
    compare_metric_to_baseline,
    median_candidate_baseline,
    null_model_manifest,
)


def test_null_model_manifest_is_context_only():
    manifest = null_model_manifest()

    assert manifest["schema_version"] == "1.0"
    assert "zero_return" in manifest["baseline_types"]
    assert "buy_and_hold" in manifest["baseline_types"]
    assert "median_candidate" in manifest["baseline_types"]

    authority = manifest["authority"]
    assert authority["null_model_is_context_only"] is True
    assert authority["not_alpha_authority"] is True
    assert authority["not_candidate_promotion"] is True
    assert authority["not_strategy_registration"] is True
    assert authority["not_paper_shadow_live"] is True
    assert authority["not_broker_execution"] is True
    assert authority["does_not_fetch_data"] is True
    assert authority["does_not_mutate_frozen_contracts"] is True


def test_compare_metric_above_baseline():
    result = compare_metric_to_baseline(
        candidate_metric=0.12,
        baseline_metric=0.05,
        baseline_type="zero_return",
    )

    assert result.comparison_state == "candidate_above_baseline"
    assert round(result.delta_vs_baseline or 0.0, 10) == 0.07
    assert result.baseline_type == "zero_return"


def test_compare_metric_below_baseline():
    result = compare_metric_to_baseline(
        candidate_metric=-0.02,
        baseline_metric=0.03,
        baseline_type="buy_and_hold",
    )

    assert result.comparison_state == "candidate_below_baseline"
    assert round(result.delta_vs_baseline or 0.0, 10) == -0.05


def test_compare_metric_equal_baseline():
    result = compare_metric_to_baseline(
        candidate_metric=0.03,
        baseline_metric=0.03,
        baseline_type="median_candidate",
    )

    assert result.comparison_state == "candidate_equal_to_baseline"
    assert result.delta_vs_baseline == 0.0


def test_compare_metric_fail_closed_on_missing_metrics():
    result = compare_metric_to_baseline(
        candidate_metric=None,
        baseline_metric=0.03,
        baseline_type="buy_and_hold",
    )

    assert result.comparison_state == "insufficient_metric_data"
    assert result.delta_vs_baseline is None


def test_unknown_baseline_type_is_normalized():
    result = compare_metric_to_baseline(
        candidate_metric=1,
        baseline_metric=0,
        baseline_type="not_real",
    )

    assert result.baseline_type == "unknown"


def test_median_candidate_baseline_odd_count():
    rows = [
        {"score": 0.1},
        {"score": 0.3},
        {"score": 0.2},
    ]

    assert median_candidate_baseline(rows, metric_field="score") == 0.2


def test_median_candidate_baseline_even_count():
    rows = [
        {"score": 0.1},
        {"score": 0.4},
        {"score": 0.2},
        {"score": 0.3},
    ]

    assert median_candidate_baseline(rows, metric_field="score") == 0.25


def test_median_candidate_baseline_ignores_non_numeric_values():
    rows = [
        {"score": "bad"},
        {"score": None},
        {"score": 0.2},
    ]

    assert median_candidate_baseline(rows, metric_field="score") == 0.2


def test_median_candidate_baseline_returns_none_without_numeric_values():
    rows = [
        {"score": "bad"},
        {"score": None},
    ]

    assert median_candidate_baseline(rows, metric_field="score") is None