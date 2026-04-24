"""Unit tests for the v3.15.1 public-artifact freshness sidecar."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from research.public_artifact_status import (
    PUBLIC_ARTIFACT_STATUS_SCHEMA_VERSION,
    PUBLIC_ARTIFACT_STATUS_VERSION,
    STALE_REASON_DEGENERATE,
    STALE_REASON_ERROR,
    STALE_REASON_NEVER,
    build_public_artifact_status,
    read_public_artifact_status,
    serialize_public_artifact_status,
    write_public_artifact_status,
)


def _iso(year: int, month: int, day: int, hour: int = 12, minute: int = 0) -> str:
    return datetime(year, month, day, hour, minute, tzinfo=UTC).isoformat()


def test_version_and_schema_constants() -> None:
    assert PUBLIC_ARTIFACT_STATUS_SCHEMA_VERSION == "1.0"
    assert PUBLIC_ARTIFACT_STATUS_VERSION == "v0.1"


def test_success_outcome_yields_fresh_status() -> None:
    attempted = _iso(2026, 4, 24)
    payload = build_public_artifact_status(
        outcome="success",
        run_id="run-success-1",
        attempted_at_utc=attempted,
        preset="trend_equities_4h_baseline",
        now=datetime(2026, 4, 24, 12, 0, tzinfo=UTC),
    )

    assert payload["schema_version"] == "1.0"
    assert payload["public_artifact_status_version"] == "v0.1"
    assert payload["public_artifacts_stale"] is False
    assert payload["stale_reason"] is None
    assert payload["stale_since_utc"] is None
    assert payload["last_attempted_run"]["outcome"] == "success"
    assert payload["last_attempted_run"]["run_id"] == "run-success-1"
    assert payload["last_public_artifact_write"]["run_id"] == "run-success-1"
    assert payload["last_public_artifact_write"]["preset"] == (
        "trend_equities_4h_baseline"
    )
    assert payload["last_public_write_age_seconds"] == 0


def test_degenerate_without_prior_yields_never_reason() -> None:
    payload = build_public_artifact_status(
        outcome="degenerate",
        run_id="run-degen-1",
        attempted_at_utc=_iso(2026, 4, 24),
        preset="trend_equities_4h_baseline",
        failure_stage="screening_no_survivors",
        existing=None,
        now=datetime(2026, 4, 24, 12, 0, tzinfo=UTC),
    )

    assert payload["public_artifacts_stale"] is True
    assert payload["stale_reason"] == STALE_REASON_NEVER
    assert payload["last_attempted_run"]["failure_stage"] == (
        "screening_no_survivors"
    )
    assert payload["last_public_artifact_write"] == {
        "run_id": None,
        "written_at_utc": None,
        "preset": None,
    }
    assert payload["last_public_write_age_seconds"] is None
    assert payload["stale_since_utc"] == _iso(2026, 4, 24)


def test_degenerate_with_prior_success_preserves_write_block() -> None:
    prior_success = build_public_artifact_status(
        outcome="success",
        run_id="run-success-1",
        attempted_at_utc=_iso(2026, 4, 23),
        preset="trend_equities_4h_baseline",
        now=datetime(2026, 4, 23, 12, 0, tzinfo=UTC),
    )

    payload = build_public_artifact_status(
        outcome="degenerate",
        run_id="run-degen-2",
        attempted_at_utc=_iso(2026, 4, 24),
        preset="trend_equities_4h_baseline",
        failure_stage="validation_no_survivors",
        existing=prior_success,
        now=datetime(2026, 4, 24, 12, 0, tzinfo=UTC),
    )

    assert payload["public_artifacts_stale"] is True
    assert payload["stale_reason"] == STALE_REASON_DEGENERATE
    assert payload["last_public_artifact_write"]["run_id"] == "run-success-1"
    assert payload["last_public_artifact_write"]["written_at_utc"] == (
        _iso(2026, 4, 23)
    )
    assert payload["stale_since_utc"] == _iso(2026, 4, 24)
    assert payload["last_public_write_age_seconds"] == int(
        timedelta(days=1).total_seconds()
    )


def test_stale_since_utc_is_preserved_across_consecutive_stale_runs() -> None:
    first_stale = build_public_artifact_status(
        outcome="degenerate",
        run_id="run-degen-1",
        attempted_at_utc=_iso(2026, 4, 22),
        preset="trend_equities_4h_baseline",
        failure_stage="screening_no_survivors",
        existing=None,
        now=datetime(2026, 4, 22, 12, 0, tzinfo=UTC),
    )

    second_stale = build_public_artifact_status(
        outcome="degenerate",
        run_id="run-degen-2",
        attempted_at_utc=_iso(2026, 4, 24),
        preset="trend_equities_4h_baseline",
        failure_stage="screening_no_survivors",
        existing=first_stale,
        now=datetime(2026, 4, 24, 12, 0, tzinfo=UTC),
    )

    assert second_stale["stale_since_utc"] == first_stale["stale_since_utc"]
    assert second_stale["stale_since_utc"] == _iso(2026, 4, 22)


def test_stale_to_fresh_transition_after_later_success() -> None:
    stale = build_public_artifact_status(
        outcome="degenerate",
        run_id="run-degen-1",
        attempted_at_utc=_iso(2026, 4, 23),
        preset="trend_equities_4h_baseline",
        failure_stage="screening_no_survivors",
        existing=None,
        now=datetime(2026, 4, 23, 12, 0, tzinfo=UTC),
    )

    recovered = build_public_artifact_status(
        outcome="success",
        run_id="run-success-2",
        attempted_at_utc=_iso(2026, 4, 24),
        preset="trend_equities_4h_baseline",
        existing=stale,
        now=datetime(2026, 4, 24, 12, 0, tzinfo=UTC),
    )

    assert recovered["public_artifacts_stale"] is False
    assert recovered["stale_reason"] is None
    assert recovered["stale_since_utc"] is None
    assert recovered["last_public_artifact_write"]["run_id"] == "run-success-2"
    assert recovered["last_public_write_age_seconds"] == 0


def test_error_outcome_uses_error_reason_code() -> None:
    prior_success = build_public_artifact_status(
        outcome="success",
        run_id="run-success-1",
        attempted_at_utc=_iso(2026, 4, 23),
        preset="trend_equities_4h_baseline",
        now=datetime(2026, 4, 23, 12, 0, tzinfo=UTC),
    )

    payload = build_public_artifact_status(
        outcome="error",
        run_id="run-error-1",
        attempted_at_utc=_iso(2026, 4, 24),
        preset="trend_equities_4h_baseline",
        existing=prior_success,
        now=datetime(2026, 4, 24, 12, 0, tzinfo=UTC),
    )

    assert payload["public_artifacts_stale"] is True
    assert payload["stale_reason"] == STALE_REASON_ERROR
    assert payload["last_public_artifact_write"]["run_id"] == "run-success-1"


def test_invalid_outcome_raises() -> None:
    with pytest.raises(ValueError):
        build_public_artifact_status(
            outcome="bogus",  # type: ignore[arg-type]
            run_id="r",
            attempted_at_utc=_iso(2026, 4, 24),
            preset="p",
        )


def test_write_and_read_round_trip(tmp_path: Path) -> None:
    path = tmp_path / "public_artifact_status_latest.v1.json"
    payload = build_public_artifact_status(
        outcome="success",
        run_id="run-success-1",
        attempted_at_utc=_iso(2026, 4, 24),
        preset="trend_equities_4h_baseline",
        now=datetime(2026, 4, 24, 12, 0, tzinfo=UTC),
    )

    written = write_public_artifact_status(payload, path=path)
    assert written == path
    assert path.exists()

    on_disk = read_public_artifact_status(path)
    assert on_disk == payload


def test_write_is_byte_identical_on_repeat(tmp_path: Path) -> None:
    path = tmp_path / "public_artifact_status_latest.v1.json"
    payload = build_public_artifact_status(
        outcome="degenerate",
        run_id="run-degen-1",
        attempted_at_utc=_iso(2026, 4, 24),
        preset="trend_equities_4h_baseline",
        failure_stage="screening_no_survivors",
        existing=None,
        now=datetime(2026, 4, 24, 12, 0, tzinfo=UTC),
    )
    write_public_artifact_status(payload, path=path)
    first = path.read_bytes()
    write_public_artifact_status(payload, path=path)
    second = path.read_bytes()
    assert first == second


def test_serialize_is_canonical_ascii_safe() -> None:
    payload = build_public_artifact_status(
        outcome="success",
        run_id="run-1",
        attempted_at_utc=_iso(2026, 4, 24),
        preset="trend_equities_4h_baseline",
        now=datetime(2026, 4, 24, 12, 0, tzinfo=UTC),
    )
    serialized = serialize_public_artifact_status(payload)
    assert serialized.endswith("\n")
    parsed = json.loads(serialized)
    assert parsed == payload


def test_live_eligible_not_present() -> None:
    payload = build_public_artifact_status(
        outcome="success",
        run_id="run-1",
        attempted_at_utc=_iso(2026, 4, 24),
        preset="trend_equities_4h_baseline",
        now=datetime(2026, 4, 24, 12, 0, tzinfo=UTC),
    )
    # This sidecar has no trading semantics — explicit N/A for live_eligible.
    assert "live_eligible" not in payload


def test_read_returns_none_when_missing(tmp_path: Path) -> None:
    assert read_public_artifact_status(tmp_path / "missing.json") is None


def test_read_returns_none_when_invalid(tmp_path: Path) -> None:
    path = tmp_path / "status.json"
    path.write_text("not json", encoding="utf-8")
    assert read_public_artifact_status(path) is None


def test_write_rejects_wrong_schema_version(tmp_path: Path) -> None:
    bad = {"schema_version": "9.9"}
    with pytest.raises(ValueError):
        write_public_artifact_status(bad, path=tmp_path / "x.json")


def test_write_rejects_unknown_stale_reason(tmp_path: Path) -> None:
    payload = build_public_artifact_status(
        outcome="degenerate",
        run_id="r",
        attempted_at_utc=_iso(2026, 4, 24),
        preset="p",
        failure_stage="screening_no_survivors",
        existing=None,
        now=datetime(2026, 4, 24, 12, 0, tzinfo=UTC),
    )
    payload["stale_reason"] = "not_a_real_reason"
    with pytest.raises(ValueError):
        write_public_artifact_status(payload, path=tmp_path / "x.json")
