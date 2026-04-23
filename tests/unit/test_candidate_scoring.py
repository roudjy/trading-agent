"""Tests for research.candidate_scoring (v3.12 deterministic scoring)."""

from __future__ import annotations

from research._sidecar_io import serialize_canonical
from research.candidate_scoring import (
    SCORING_FORMULA_VERSION,
    CandidateScore,
    compute_candidate_score,
    score_to_payload,
)


BASE_ENTRY = {
    "strategy_name": "sma_crossover",
    "asset": "NVDA",
    "interval": "4h",
    "max_drawdown": 0.25,
    "trades_per_maand": 4.0,
}
BASE_DEFENSIBILITY = {"psr": 0.85, "dsr_canonical": 0.6}
BASE_BREADTH = {"dominant_asset_share": 0.25}


def test_score_is_provisional_and_non_authoritative() -> None:
    score = compute_candidate_score(BASE_ENTRY, BASE_DEFENSIBILITY, BASE_BREADTH)
    assert score.composite_status == "provisional"
    assert score.authoritative is False
    assert score.scoring_formula_version == SCORING_FORMULA_VERSION == "v0.1-experimental"


def test_score_is_deterministic_across_calls() -> None:
    a = compute_candidate_score(BASE_ENTRY, BASE_DEFENSIBILITY, BASE_BREADTH)
    b = compute_candidate_score(BASE_ENTRY, BASE_DEFENSIBILITY, BASE_BREADTH)
    assert score_to_payload(a) == score_to_payload(b)


def test_score_serializes_byte_equal_across_calls() -> None:
    a = score_to_payload(compute_candidate_score(BASE_ENTRY, BASE_DEFENSIBILITY, BASE_BREADTH))
    b = score_to_payload(compute_candidate_score(BASE_ENTRY, BASE_DEFENSIBILITY, BASE_BREADTH))
    assert serialize_canonical(a) == serialize_canonical(b)


def test_all_signals_populated_when_all_inputs_present() -> None:
    score = compute_candidate_score(BASE_ENTRY, BASE_DEFENSIBILITY, BASE_BREADTH)
    c = score.components
    assert c.dsr_signal is not None
    assert c.psr_signal is not None
    assert c.drawdown_signal is not None
    assert c.stability_signal is not None
    assert c.trade_density_signal is not None
    assert c.breadth_signal is not None
    assert score.composite_score is not None


def test_all_signals_in_unit_interval() -> None:
    score = compute_candidate_score(BASE_ENTRY, BASE_DEFENSIBILITY, BASE_BREADTH)
    values = [
        score.components.dsr_signal,
        score.components.psr_signal,
        score.components.drawdown_signal,
        score.components.stability_signal,
        score.components.trade_density_signal,
        score.components.breadth_signal,
    ]
    for value in values:
        assert value is not None and 0.0 <= value <= 1.0


def test_missing_defensibility_yields_none_signals_but_works() -> None:
    score = compute_candidate_score(BASE_ENTRY, None, BASE_BREADTH)
    assert score.components.dsr_signal is None
    assert score.components.psr_signal is None
    assert score.components.stability_signal is None
    # drawdown / trade_density still computable
    assert score.components.drawdown_signal is not None
    assert score.components.trade_density_signal is not None
    # composite excludes missing components but is still computable
    assert score.composite_score is not None


def test_missing_breadth_yields_none_breadth_but_composite_still_works() -> None:
    score = compute_candidate_score(BASE_ENTRY, BASE_DEFENSIBILITY, None)
    assert score.components.breadth_signal is None
    assert score.composite_score is not None


def test_all_missing_inputs_yield_none_composite() -> None:
    score = compute_candidate_score({}, None, None)
    assert score.composite_score is None
    assert score.composite_status == "provisional"
    assert score.authoritative is False


def test_drawdown_signal_decreases_as_drawdown_grows() -> None:
    low_dd = compute_candidate_score({"max_drawdown": 0.1}, None, None).components.drawdown_signal
    high_dd = compute_candidate_score({"max_drawdown": 0.5}, None, None).components.drawdown_signal
    assert low_dd is not None and high_dd is not None
    assert low_dd > high_dd


def test_breadth_signal_decreases_with_dominance() -> None:
    low_dom = compute_candidate_score({}, None, {"dominant_asset_share": 0.2}).components.breadth_signal
    high_dom = compute_candidate_score({}, None, {"dominant_asset_share": 0.9}).components.breadth_signal
    assert low_dom is not None and high_dom is not None
    assert low_dom > high_dom


def test_extreme_drawdown_clips_to_zero() -> None:
    score = compute_candidate_score({"max_drawdown": 5.0}, None, None)
    assert score.components.drawdown_signal == 0.0


def test_negative_drawdown_handled_by_abs() -> None:
    score = compute_candidate_score({"max_drawdown": -0.3}, None, None)
    # treat -0.3 as magnitude 0.3; signal = 0.7
    assert score.components.drawdown_signal is not None
    assert abs(score.components.drawdown_signal - 0.7) < 1e-9


def test_derivation_metadata_records_missing_status() -> None:
    score = compute_candidate_score({}, None, None)
    assert score.components.derivation["dsr_signal"]["status"] == "missing"
    assert score.components.derivation["drawdown_signal"]["status"] == "missing"


def test_score_to_payload_shape_is_stable() -> None:
    score = compute_candidate_score(BASE_ENTRY, BASE_DEFENSIBILITY, BASE_BREADTH)
    payload = score_to_payload(score)
    assert set(payload.keys()) == {
        "components",
        "composite_score",
        "composite_status",
        "authoritative",
        "scoring_formula_version",
        "derivation_metadata",
    }
    assert payload["authoritative"] is False
    assert payload["composite_status"] == "provisional"
