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


# ---------------------------------------------------------------------------
# v3.15.15.6 — split status fields, evidence-warning propagation, sprint freshness
# ---------------------------------------------------------------------------


def test_overall_status_unchanged_for_backward_compat(tmp_path: Path, fixed_now: datetime):
    """``overall_status`` MUST keep the legacy enum values + semantics so
    pre-v3.15.15.6 consumers don't break. Healthy infrastructure stays
    ``healthy`` even when evidence is partial."""
    obs = tmp_path / "observability"
    components = _components(obs)
    for name, _, p in components:
        _write(p, {"schema_version": "1.0", "name": name})
    summary = agg.build_observability_summary(
        now_utc=fixed_now, active_components=components, deferred_components=()
    )
    assert summary["overall_status"] == agg.OVERALL_HEALTHY
    # Backward-compat: infrastructure_status mirrors overall_status.
    assert summary["infrastructure_status"] == agg.INFRA_HEALTHY


def test_diagnostic_evidence_status_propagates_from_failure_modes(
    tmp_path: Path, fixed_now: datetime
):
    """The aggregator reads ``failure_modes.diagnostic_context.diagnostic_evidence_status``
    and copies it into the top-level summary."""
    obs = tmp_path / "observability"
    components = _components(obs)
    fm_payload_path = next(p for name, _, p in components if name == "failure_modes")
    other = [(n, s, p) for n, s, p in components if n != "failure_modes"]
    for _, _, p in other:
        _write(p, {"schema_version": "1.0"})
    _write(
        fm_payload_path,
        {
            "schema_version": "1.0",
            "diagnostic_context": {
                "diagnostic_mode": "registry_only",
                "diagnostic_evidence_status": "partial",
                "limitations": [
                    "campaign_evidence_ledger_absent",
                    "screening_evidence_absent",
                ],
            },
        },
    )
    summary = agg.build_observability_summary(
        now_utc=fixed_now, active_components=components, deferred_components=()
    )
    assert summary["diagnostic_evidence_status"] == "partial"
    assert summary["diagnostic_mode"] == "registry_only"
    # Limitations from failure_modes are propagated as warnings.
    assert any(
        "diagnostic_evidence_limitation: campaign_evidence_ledger_absent" in w
        for w in summary["warnings"]
    )
    assert any(
        "diagnostic_evidence_limitation: screening_evidence_absent" in w
        for w in summary["warnings"]
    )
    # Aggregate "partial" warning fires when infra is healthy.
    assert any(
        "diagnostic_evidence_partial" in w for w in summary["warnings"]
    )


def test_diagnostic_evidence_status_unavailable_when_no_failure_modes(
    tmp_path: Path, fixed_now: datetime
):
    obs = tmp_path / "observability"
    components = _components(obs)
    summary = agg.build_observability_summary(
        now_utc=fixed_now, active_components=components, deferred_components=()
    )
    # No artifacts written → all unavailable.
    assert summary["diagnostic_evidence_status"] == agg.EVIDENCE_UNAVAILABLE
    assert summary["diagnostic_mode"] is None


def test_sprint_progress_freshness_warning_only(tmp_path: Path, fixed_now: datetime):
    """A stale sprint progress emits a WARNING but never flips
    ``infrastructure_status`` to degraded."""
    obs = tmp_path / "observability"
    components = _components(obs)
    for name, _, p in components:
        _write(p, {"schema_version": "1.0", "name": name})

    research_root = tmp_path / "research"
    research_root.mkdir(exist_ok=True)
    sprints = research_root / "discovery_sprints"
    sprints.mkdir()
    progress_path = sprints / "discovery_sprint_progress_latest.v1.json"
    registry_path = research_root / "campaign_registry_latest.v1.json"

    progress_path.write_text(
        '{"schema_version":"1.0","generated_at_utc":"2026-04-28T12:00:00Z"}',
        encoding="utf-8",
    )
    # Backdate progress mtime by 5h.
    import os
    five_hours_ago = fixed_now.timestamp() - 5 * 3600
    os.utime(progress_path, (five_hours_ago, five_hours_ago))

    registry_path.write_text(
        '{"schema_version":"1.0","generated_at_utc":"2026-04-28T17:00:00Z"}',
        encoding="utf-8",
    )
    # Registry is "now" mtime (fresh).
    os.utime(registry_path, (fixed_now.timestamp(), fixed_now.timestamp()))

    summary = agg.build_observability_summary(
        now_utc=fixed_now,
        active_components=components,
        deferred_components=(),
        sprint_progress_path=progress_path,
        campaign_registry_path=registry_path,
        sprint_stale_threshold_seconds=60 * 60,
    )

    # Infrastructure must remain healthy despite stale sprint.
    assert summary["infrastructure_status"] == agg.INFRA_HEALTHY
    assert summary["overall_status"] == agg.OVERALL_HEALTHY
    # Freshness block is populated.
    f = summary["sprint_progress_freshness"]
    assert f["available"] is True
    assert f["stale_relative_to_campaign_registry"] is True
    assert f["age_delta_seconds"] >= 5 * 3600
    assert f["threshold_seconds"] == 60 * 60
    # Warning fires.
    assert any(
        "sprint_progress_stale_relative_to_registry" in w
        for w in summary["warnings"]
    )


def test_sprint_progress_freshness_no_warning_when_within_threshold(
    tmp_path: Path, fixed_now: datetime
):
    obs = tmp_path / "observability"
    components = _components(obs)
    for name, _, p in components:
        _write(p, {"schema_version": "1.0", "name": name})

    research_root = tmp_path / "research"
    research_root.mkdir(exist_ok=True)
    sprints = research_root / "discovery_sprints"
    sprints.mkdir()
    progress_path = sprints / "discovery_sprint_progress_latest.v1.json"
    registry_path = research_root / "campaign_registry_latest.v1.json"

    progress_path.write_text('{"schema_version":"1.0"}', encoding="utf-8")
    registry_path.write_text('{"schema_version":"1.0"}', encoding="utf-8")
    # Both fresh — no delta.

    summary = agg.build_observability_summary(
        now_utc=fixed_now,
        active_components=components,
        deferred_components=(),
        sprint_progress_path=progress_path,
        campaign_registry_path=registry_path,
        sprint_stale_threshold_seconds=60 * 60,
    )
    assert summary["sprint_progress_freshness"]["stale_relative_to_campaign_registry"] is False
    assert not any(
        "sprint_progress_stale_relative_to_registry" in w
        for w in summary["warnings"]
    )


def test_sprint_progress_freshness_unavailable_when_files_missing(
    tmp_path: Path, fixed_now: datetime
):
    obs = tmp_path / "observability"
    components = _components(obs)
    for name, _, p in components:
        _write(p, {"schema_version": "1.0", "name": name})
    summary = agg.build_observability_summary(
        now_utc=fixed_now,
        active_components=components,
        deferred_components=(),
        sprint_progress_path=tmp_path / "missing_progress.json",
        campaign_registry_path=tmp_path / "missing_registry.json",
    )
    f = summary["sprint_progress_freshness"]
    assert f["available"] is False
    assert f["stale_relative_to_campaign_registry"] is False
    assert f["age_delta_seconds"] is None
