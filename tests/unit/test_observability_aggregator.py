"""Unit tests for research.diagnostics.aggregator."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from research.diagnostics import aggregator as agg


@pytest.fixture
def fixed_now() -> datetime:
    return datetime(2026, 4, 28, 10, 0, 0, tzinfo=UTC)


def _write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def _components(obs_dir: Path) -> tuple[tuple[str, str, Path], ...]:
    return (
        ("artifact_health", "artifact-health", obs_dir / "artifact_health_latest.v1.json"),
        ("failure_modes", "failure-modes", obs_dir / "failure_modes_latest.v1.json"),
        ("throughput_metrics", "throughput", obs_dir / "throughput_metrics_latest.v1.json"),
        ("system_integrity", "system-integrity", obs_dir / "system_integrity_latest.v1.json"),
    )


def test_all_available_healthy(tmp_path: Path, fixed_now: datetime):
    obs = tmp_path / "observability"
    components = _components(obs)
    for name, _, p in components:
        _write(p, {"schema_version": "1.0", "generated_at_utc": "2026-04-28T09:00:00Z", "name": name})

    summary = agg.build_observability_summary(
        now_utc=fixed_now,
        active_components=components,
        deferred_components=(),
    )

    assert summary["overall_status"] == agg.OVERALL_HEALTHY
    assert summary["recommended_next_human_action"] == agg.ACTION_NONE
    assert summary["component_status_counts"][agg.STATUS_AVAILABLE] == 4


def test_corrupt_component_marks_degraded(tmp_path: Path, fixed_now: datetime):
    obs = tmp_path / "observability"
    obs.mkdir()
    components = _components(obs)
    # Three valid + one corrupt
    for name, _, p in components[:-1]:
        _write(p, {"schema_version": "1.0", "name": name})
    components[-1][2].write_text("{not json", encoding="utf-8")

    summary = agg.build_observability_summary(
        now_utc=fixed_now,
        active_components=components,
        deferred_components=(),
    )

    assert summary["overall_status"] == agg.OVERALL_DEGRADED
    assert summary["recommended_next_human_action"] == agg.ACTION_INVESTIGATION_REQUIRED
    assert summary["component_status_counts"][agg.STATUS_CORRUPT] == 1
    assert any("is corrupt" in f for f in summary["critical_findings"])


def test_all_unavailable_insufficient_evidence(tmp_path: Path, fixed_now: datetime):
    obs = tmp_path / "observability"
    components = _components(obs)
    summary = agg.build_observability_summary(
        now_utc=fixed_now,
        active_components=components,
        deferred_components=(),
    )
    assert summary["overall_status"] == agg.OVERALL_INSUFFICIENT_EVIDENCE
    assert summary["recommended_next_human_action"] == agg.ACTION_INSPECT_ARTIFACTS


def test_partial_available_degraded(tmp_path: Path, fixed_now: datetime):
    obs = tmp_path / "observability"
    components = _components(obs)
    _write(components[0][2], {"schema_version": "1.0"})
    summary = agg.build_observability_summary(
        now_utc=fixed_now,
        active_components=components,
        deferred_components=(),
    )
    assert summary["overall_status"] == agg.OVERALL_DEGRADED


def test_deferred_components_listed(tmp_path: Path, fixed_now: datetime):
    obs = tmp_path / "observability"
    components = _components(obs)
    deferred = (("funnel_stage_summary", "funnel"),)
    summary = agg.build_observability_summary(
        now_utc=fixed_now,
        active_components=components,
        deferred_components=deferred,
    )
    deferred_rows = [c for c in summary["components"] if c["status"] == agg.STATUS_DEFERRED]
    assert len(deferred_rows) == 1
    assert deferred_rows[0]["name"] == "funnel_stage_summary"
    assert summary["deferred_component_count"] == 1


def test_components_sorted_alphabetically(tmp_path: Path, fixed_now: datetime):
    obs = tmp_path / "observability"
    components = _components(obs)
    summary = agg.build_observability_summary(
        now_utc=fixed_now,
        active_components=components,
        deferred_components=(),
    )
    names = [c["name"] for c in summary["components"]]
    assert names == sorted(names)


def test_critical_findings_sorted(tmp_path: Path, fixed_now: datetime):
    obs = tmp_path / "observability"
    obs.mkdir()
    components = _components(obs)
    # Make two corrupt to verify ordering.
    components[0][2].write_text("{bad", encoding="utf-8")
    components[1][2].write_text("[bad", encoding="utf-8")
    _write(components[2][2], {"schema_version": "1.0"})
    _write(components[3][2], {"schema_version": "1.0"})

    summary = agg.build_observability_summary(
        now_utc=fixed_now,
        active_components=components,
        deferred_components=(),
    )
    assert summary["critical_findings"] == sorted(summary["critical_findings"])


def test_byte_identical_for_fixed_inputs(tmp_path: Path, fixed_now: datetime):
    obs = tmp_path / "observability"
    components = _components(obs)
    for name, _, p in components:
        _write(p, {"schema_version": "1.0", "name": name})
    a = agg.build_observability_summary(
        now_utc=fixed_now, active_components=components, deferred_components=()
    )
    b = agg.build_observability_summary(
        now_utc=fixed_now, active_components=components, deferred_components=()
    )
    assert json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)
