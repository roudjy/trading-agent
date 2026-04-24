"""Pin-block invariant tests for the v3.15.2 Campaign OS shared helpers."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from research.campaign_os_artifacts import (
    ARTIFACT_STATES,
    CAMPAIGN_OS_VERSION,
    assert_pin_block_invariants,
    build_pin_block,
    iso_utc,
)


@pytest.fixture
def now_utc() -> datetime:
    return datetime(2026, 4, 24, 8, 12, 33, tzinfo=UTC)


def test_build_pin_block_has_all_required_fields(now_utc: datetime) -> None:
    pins = build_pin_block(
        schema_version="1.0",
        generated_at_utc=now_utc,
        git_revision="abc1234",
        run_id="20260424T081233000000Z",
    )
    for field in (
        "schema_version",
        "campaign_os_version",
        "authoritative",
        "diagnostic_only",
        "live_eligible",
        "generated_at_utc",
        "git_revision",
        "run_id",
        "artifact_state",
    ):
        assert field in pins, f"missing field {field}"


def test_build_pin_block_hard_invariants(now_utc: datetime) -> None:
    pins = build_pin_block(
        schema_version="1.0",
        generated_at_utc=now_utc,
    )
    assert pins["authoritative"] is False
    assert pins["diagnostic_only"] is True
    assert pins["live_eligible"] is False
    assert pins["campaign_os_version"] == CAMPAIGN_OS_VERSION


def test_build_pin_block_rejects_unknown_artifact_state(now_utc: datetime) -> None:
    with pytest.raises(ValueError):
        build_pin_block(
            schema_version="1.0",
            generated_at_utc=now_utc,
            artifact_state="unknown",  # type: ignore[arg-type]
        )


def test_assert_pin_block_invariants_pass(now_utc: datetime) -> None:
    pins = build_pin_block(schema_version="1.0", generated_at_utc=now_utc)
    assert_pin_block_invariants(pins)


def test_assert_pin_block_invariants_fail_on_live_eligible_true(
    now_utc: datetime,
) -> None:
    pins = build_pin_block(schema_version="1.0", generated_at_utc=now_utc)
    pins["live_eligible"] = True
    with pytest.raises(ValueError):
        assert_pin_block_invariants(pins)


def test_assert_pin_block_invariants_fail_on_missing_field(
    now_utc: datetime,
) -> None:
    pins = build_pin_block(schema_version="1.0", generated_at_utc=now_utc)
    del pins["campaign_os_version"]
    with pytest.raises(ValueError):
        assert_pin_block_invariants(pins)


def test_iso_utc_normalises_timezone() -> None:
    ts = datetime(2026, 4, 24, 8, 12, 33, tzinfo=UTC)
    assert iso_utc(ts).endswith("Z")


def test_artifact_states_is_closed_vocabulary() -> None:
    assert set(ARTIFACT_STATES) == {"healthy", "stale", "corrupt"}
