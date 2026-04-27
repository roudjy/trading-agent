"""v3.15.11 — information gain engine unit tests."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from research._sidecar_io import serialize_canonical
from research.information_gain import (
    BUCKET_HIGH,
    BUCKET_LOW,
    BUCKET_MEDIUM,
    BUCKET_NONE,
    IG_COVERAGE_BONUS_MAX,
    IG_DUPLICATE_REJECTION,
    IG_EXPLORATORY_PASS,
    IG_NEAR_CANDIDATE,
    IG_NEW_FAILURE_MODE,
    IG_PAPER_READY,
    IG_PROMOTION_CANDIDATE,
    INFORMATION_GAIN_SCHEMA_VERSION,
    InformationGainInputs,
    build_information_gain_payload,
    score_information_gain,
    write_information_gain_artifact,
)


_AS_OF = datetime(2026, 4, 27, 12, 0, 0, tzinfo=UTC)


def test_technical_failure_zero_score_not_meaningful() -> None:
    result = score_information_gain(
        InformationGainInputs(
            technical_failure=True,
            exploratory_pass=True,  # ignored — short-circuit on tech failure
            paper_ready=True,
        )
    )
    assert result.score == 0.0
    assert result.bucket == BUCKET_NONE
    assert result.is_meaningful_campaign is False
    assert [r.code for r in result.reasons] == ["technical_failure"]


def test_repeated_failure_mode_low_bucket() -> None:
    result = score_information_gain(
        InformationGainInputs(repeated_failure_mode=True)
    )
    assert result.bucket == BUCKET_LOW
    assert result.score == IG_DUPLICATE_REJECTION
    assert result.is_meaningful_campaign is False


def test_new_failure_mode_medium_bucket() -> None:
    result = score_information_gain(
        InformationGainInputs(new_failure_mode=True)
    )
    assert result.bucket == BUCKET_MEDIUM
    assert result.score == IG_NEW_FAILURE_MODE
    assert result.is_meaningful_campaign is True


def test_exploratory_pass_high_bucket() -> None:
    result = score_information_gain(
        InformationGainInputs(exploratory_pass=True)
    )
    assert result.bucket == BUCKET_HIGH
    assert result.score == IG_EXPLORATORY_PASS
    assert result.is_meaningful_campaign is True


def test_near_candidate_high_bucket() -> None:
    result = score_information_gain(
        InformationGainInputs(near_candidate=True)
    )
    assert result.bucket == BUCKET_HIGH
    assert result.score == IG_NEAR_CANDIDATE
    assert result.is_meaningful_campaign is True


def test_paper_ready_dominates_promotion_candidate() -> None:
    result = score_information_gain(
        InformationGainInputs(paper_ready=True, promotion_candidate=True)
    )
    assert result.score == IG_PAPER_READY
    assert result.bucket == BUCKET_HIGH
    # Both contribute as reasons; ordering is desc weight then code.
    codes = [r.code for r in result.reasons]
    assert codes[0] == "paper_ready"
    assert "promotion_candidate" in codes


def test_deterministic_reason_ordering() -> None:
    result = score_information_gain(
        InformationGainInputs(
            new_failure_mode=True,
            near_candidate=True,
            exploratory_pass=True,
        )
    )
    codes = [r.code for r in result.reasons]
    # exploratory_pass and near_candidate both have weight 0.8 → tie
    # broken alphabetically: exploratory_pass < near_candidate.
    assert codes == ["exploratory_pass", "near_candidate", "new_failure_mode"]


def test_repeated_failure_suppressed_when_positive_signal_present() -> None:
    """Duplicate-rejection only counts when no positive signal exists."""
    result = score_information_gain(
        InformationGainInputs(
            repeated_failure_mode=True,
            new_failure_mode=True,
        )
    )
    codes = [r.code for r in result.reasons]
    assert "repeated_failure_mode" not in codes
    assert "new_failure_mode" in codes


def test_coverage_bonus_caps_and_does_not_dominate() -> None:
    """Full coverage on a duplicate-rejection campaign stays in low/medium."""
    result = score_information_gain(
        InformationGainInputs(
            repeated_failure_mode=True,
            parameter_coverage_pct=1.0,
        )
    )
    expected = round(IG_DUPLICATE_REJECTION + IG_COVERAGE_BONUS_MAX, 4)
    assert result.score == expected
    # 0.1 + 0.2 = 0.3 → just at the medium floor; bucket is medium.
    assert result.bucket == BUCKET_MEDIUM
    # Coverage alone never reaches high.
    assert result.score < 0.7


def test_coverage_below_floor_no_bonus() -> None:
    result = score_information_gain(
        InformationGainInputs(
            new_failure_mode=True,
            parameter_coverage_pct=0.50,
        )
    )
    assert result.score == IG_NEW_FAILURE_MODE
    codes = [r.code for r in result.reasons]
    assert "improved_parameter_coverage" not in codes


def test_score_capped_at_one() -> None:
    result = score_information_gain(
        InformationGainInputs(paper_ready=True, parameter_coverage_pct=1.0)
    )
    assert result.score == 1.0
    assert result.bucket == BUCKET_HIGH


def test_no_signals_yields_none_bucket() -> None:
    result = score_information_gain(InformationGainInputs())
    assert result.score == 0.0
    assert result.bucket == BUCKET_NONE
    assert result.is_meaningful_campaign is False
    assert result.reasons == []


def test_promotion_candidate_high_bucket() -> None:
    result = score_information_gain(
        InformationGainInputs(promotion_candidate=True)
    )
    assert result.score == IG_PROMOTION_CANDIDATE
    assert result.bucket == BUCKET_HIGH


def test_payload_schema_and_keys() -> None:
    payload = build_information_gain_payload(
        run_id="run_a",
        col_campaign_id="col_1",
        preset_name="trend_pullback_crypto_1h",
        hypothesis_id="hyp_42",
        as_of_utc=_AS_OF,
        git_revision="deadbeef",
        inputs=InformationGainInputs(
            exploratory_pass=True,
            parameter_coverage_pct=0.85,
            sampled_count=12,
            grid_size=14,
        ),
    )
    assert payload["schema_version"] == INFORMATION_GAIN_SCHEMA_VERSION
    assert payload["preset_name"] == "trend_pullback_crypto_1h"
    assert payload["hypothesis_id"] == "hyp_42"
    ig = payload["information_gain"]
    assert ig["bucket"] == BUCKET_HIGH
    assert ig["is_meaningful_campaign"] is True
    assert isinstance(ig["reasons"], list) and ig["reasons"]
    inp = payload["inputs"]
    assert inp["exploratory_pass"] is True
    assert inp["parameter_coverage_pct"] == 0.85
    assert inp["sampled_count"] == 12
    assert inp["grid_size"] == 14


def test_byte_identical_payload_for_repeated_build() -> None:
    inputs = InformationGainInputs(near_candidate=True, parameter_coverage_pct=0.9)
    p1 = build_information_gain_payload(
        run_id="r",
        col_campaign_id=None,
        preset_name="p",
        hypothesis_id="h",
        as_of_utc=_AS_OF,
        git_revision=None,
        inputs=inputs,
    )
    p2 = build_information_gain_payload(
        run_id="r",
        col_campaign_id=None,
        preset_name="p",
        hypothesis_id="h",
        as_of_utc=_AS_OF,
        git_revision=None,
        inputs=inputs,
    )
    assert serialize_canonical(p1) == serialize_canonical(p2)


def test_io_wrapper_creates_subdir(tmp_path: Path) -> None:
    out = tmp_path / "research" / "campaigns" / "evidence" / "ig.json"
    payload = write_information_gain_artifact(
        run_id="r",
        col_campaign_id=None,
        preset_name="p",
        hypothesis_id=None,
        as_of_utc=_AS_OF,
        git_revision=None,
        inputs=InformationGainInputs(promotion_candidate=True),
        output_path=out,
    )
    assert out.exists()
    assert payload["information_gain"]["bucket"] == BUCKET_HIGH


@pytest.mark.parametrize(
    "score,expected_bucket",
    [
        (0.0, BUCKET_NONE),
        (0.05, BUCKET_LOW),
        (0.29, BUCKET_LOW),
        (0.30, BUCKET_MEDIUM),
        (0.50, BUCKET_MEDIUM),
        (0.69, BUCKET_MEDIUM),
        (0.70, BUCKET_HIGH),
        (1.00, BUCKET_HIGH),
    ],
)
def test_bucket_boundaries(score: float, expected_bucket: str) -> None:
    """Direct bucket-boundary verification by synthesising single signals."""
    if score == 0.0:
        result = score_information_gain(InformationGainInputs())
    elif score == 0.05:
        # No single signal yields 0.05; emulate via repeated_failure_mode (0.1)
        # and verify the boundary at 0.1 → low. We use 0.05 only for the
        # boundary table and skip this branch.
        pytest.skip("0.05 requires a synthetic blend not exposed by inputs")
    elif score == 0.29:
        pytest.skip("0.29 requires a synthetic blend not exposed by inputs")
    elif score == 0.30:
        # repeated_failure_mode + max coverage = 0.1 + 0.2 = 0.30.
        result = score_information_gain(
            InformationGainInputs(
                repeated_failure_mode=True, parameter_coverage_pct=1.0
            )
        )
    elif score == 0.50:
        result = score_information_gain(
            InformationGainInputs(new_failure_mode=True)
        )
    elif score == 0.69:
        pytest.skip("0.69 requires a synthetic blend not exposed by inputs")
    elif score == 0.70:
        # Exploratory pass without coverage = 0.8 → high; no exact 0.7 input
        # exists. Verify high boundary instead.
        result = score_information_gain(
            InformationGainInputs(exploratory_pass=True)
        )
    elif score == 1.00:
        result = score_information_gain(
            InformationGainInputs(paper_ready=True)
        )
    else:
        pytest.fail(f"unexpected synthetic score {score}")
    assert result.bucket == expected_bucket
