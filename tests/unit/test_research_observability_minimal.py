"""Tests for ``reporting.research_observability_minimal``.

Pins the minimal v3.15.18 reset slice declared by queue item 4 in
``docs/development_work_queue/seed.jsonl`` (per
``docs/governance/roadmap_scope_status.md`` §3).

What this suite asserts:

* the aggregator surfaces the four closed upstream sources;
* missing sources never raise — they yield deterministic
  ``available: false`` placeholders;
* the operator-attention-budget cap is enforced and overflow
  subjects are surfaced;
* the snapshot is byte-deterministic given a frozen timestamp;
* the atomic-write allowlist refuses paths outside
  ``logs/research_observability_minimal/``;
* the module is stdlib-only and imports no execution-side
  surfaces;
* the module does not modify ``dashboard/dashboard.py`` (CQD-I2);
* the module does not modify frozen contracts.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from reporting import reason_records as rr
from reporting import research_observability_minimal as rom

# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------


def _make_reason_record(
    *,
    decision_kind: str,
    subject_id: str,
    decision: str,
    reason_codes: list[str],
    info_seed: int = 0,
) -> dict[str, Any]:
    """Build a valid reason record for the given family. Inputs
    digest deterministically derived from info_seed so repeated
    calls remain idempotent."""
    inputs = {"subject_id": subject_id, "seed": info_seed}
    return rr.build_record(
        decision_kind=decision_kind,
        subject_id=subject_id,
        decision=decision,
        reason_codes=reason_codes,
        reason_text=f"test-{decision_kind}-{subject_id}-{info_seed}",
        inputs=inputs,
        frozen_utc="2026-05-21T00:00:00Z",
    )


def _seed_reason_records(
    base: Path,
    *,
    subject_to_kinds: dict[str, list[str]],
) -> None:
    """Append one record per (subject_id, kind) into ``base``.

    The decision and reason_code values are chosen from the closed
    vocab per kind.
    """
    default_decision = {
        "routing": "prioritize",
        "sampling": "stratify",
        "scoring": "keep",
    }
    default_codes = {
        "routing": ["info_gain_high"],
        "sampling": ["multiplicity_budget_remaining"],
        "scoring": ["dsr_threshold_pass"],
    }
    for sid, kinds in subject_to_kinds.items():
        for i, kind in enumerate(kinds):
            rec = _make_reason_record(
                decision_kind=kind,
                subject_id=sid,
                decision=default_decision[kind],
                reason_codes=default_codes[kind],
                info_seed=i,
            )
            rr.append(rec, artifact_dir=base)


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, sort_keys=True, indent=2), encoding="utf-8")


# ---------------------------------------------------------------------------
# Pinned constants
# ---------------------------------------------------------------------------


def test_source_ids_are_pinned() -> None:
    assert rom.SOURCE_IDS == (
        "routing_minimal",
        "sampling_minimal",
        "reason_records",
        "research_quality_kpis_doc",
    )


def test_research_quality_kpi_ids_are_pinned() -> None:
    assert rom.RESEARCH_QUALITY_KPI_IDS == (
        "TTFPRC",
        "OOS_DSR",
        "MASQ",
        "NMBR",
        "DZCR",
        "OAB",
        "CRSR",
    )
    assert len(rom.RESEARCH_QUALITY_KPI_IDS) == 7


def test_visible_surfaces_per_campaign_cap_is_pinned() -> None:
    assert rom.DEFAULT_VISIBLE_SURFACES_PER_CAMPAIGN_CAP == 3


def test_top_subjects_n_is_pinned() -> None:
    assert rom.TOP_SUBJECTS_N == 16


def test_module_version_is_pinned() -> None:
    assert rom.MODULE_VERSION == "v3.15.18-ade-qre-007-operator-grade-2026-05-23"


def test_report_kind_is_pinned() -> None:
    assert rom.REPORT_KIND == "research_observability_minimal_digest"


# ---------------------------------------------------------------------------
# Snapshot top-level shape
# ---------------------------------------------------------------------------


def test_snapshot_top_level_keys_when_sources_absent(tmp_path: Path) -> None:
    snap = rom.collect_snapshot(
        routing_minimal_path=tmp_path / "no_routing.json",
        sampling_minimal_path=tmp_path / "no_sampling.json",
        reason_records_artifact_dir=tmp_path / "no_reason_records",
        kpi_doc_path=tmp_path / "no_kpi.md",
        screening_failure_attribution_path=tmp_path / "no_screening.json",
        failure_action_mapping_path=tmp_path / "no_actions.json",
        data_manifest_path=tmp_path / "no_manifest.json",
        source_quality_path=tmp_path / "no_quality.json",
        research_memory_path=tmp_path / "no_memory.json",
        research_diagnostics_loop_path=tmp_path / "no_diagnostics.json",
        ade_queue_doc_path=tmp_path / "no_queue.md",
        frozen_utc="2026-05-21T00:00:00Z",
    )
    expected = {
        "schema_version",
        "module_version",
        "report_kind",
        "generated_at_utc",
        "mode",
        "safe_to_execute",
        "operator_attention_budget",
        "sources",
        "qre_operator_summary",
        "cross_family_subjects",
        "final_recommendation",
        "note",
    }
    assert set(snap.keys()) == expected
    assert snap["report_kind"] == "research_observability_minimal_digest"
    assert snap["mode"] == "dry-run"
    assert snap["safe_to_execute"] is False
    assert snap["final_recommendation"] == "nothing_to_review"
    assert snap["qre_operator_summary"]["operator_state"] == "missing_upstream_evidence"


def test_sources_block_carries_closed_source_id_set(tmp_path: Path) -> None:
    snap = rom.collect_snapshot(
        routing_minimal_path=tmp_path / "no_routing.json",
        sampling_minimal_path=tmp_path / "no_sampling.json",
        reason_records_artifact_dir=tmp_path / "no_reason_records",
        kpi_doc_path=tmp_path / "no_kpi.md",
        frozen_utc="2026-05-21T00:00:00Z",
    )
    assert set(snap["sources"].keys()) == set(rom.SOURCE_IDS)
    # Each source carries the matching source_id.
    for sid in rom.SOURCE_IDS:
        assert snap["sources"][sid]["source_id"] == sid


def test_qre_operator_summary_source_ids_are_pinned() -> None:
    assert rom.QRE_OPERATOR_SUMMARY_SOURCE_IDS == (
        "screening_failure_attribution",
        "failure_action_mapping",
        "data_manifest",
        "source_quality",
        "research_memory",
        "research_diagnostics_loop",
        "ade_queue",
    )


def test_qre_operator_summary_reports_rates_readiness_and_gate(
    tmp_path: Path,
) -> None:
    screening_path = tmp_path / "research" / "screening_failure_attribution_latest.v1.json"
    action_path = tmp_path / "logs" / "failure_action_mapping_minimal" / "latest.json"
    manifest_path = tmp_path / "logs" / "qre_data_cache_manifest" / "latest.json"
    source_quality_path = (
        tmp_path / "logs" / "qre_data_source_quality_readiness" / "latest.json"
    )
    memory_path = tmp_path / "logs" / "qre_research_memory" / "latest.json"
    diagnostics_path = tmp_path / "logs" / "qre_research_diagnostics_loop" / "latest.json"
    queue_path = tmp_path / "docs" / "governance" / "queue.md"
    _write_json(
        screening_path,
        {
            "summary": {
                "observation_count": 4,
                "unknown_observation_count": 1,
                "primary_classification": "data_coverage_gap",
            },
            "recommended_next_action": "repair_data_coverage_before_research_action",
            "classifications": [
                {
                    "classification": "data_coverage_gap",
                    "count": 3,
                    "sources": ["screening_evidence.summary"],
                    "raw_reasons": {"coverage_gap": 3},
                    "action_hint": {"action": "repair_data_coverage_before_research_action"},
                },
                {
                    "classification": "unknown_screening_failure",
                    "count": 1,
                    "sources": [],
                    "raw_reasons": {},
                    "action_hint": {"action": "hold_no_action_until_evidence_improves"},
                },
            ],
        },
    )
    _write_json(
        action_path,
        {
            "counts": {
                "total": 4,
                "actionable_recommendations": 3,
            },
            "final_recommendation": "actions_available",
        },
    )
    _write_json(manifest_path, {"summary": {"research_ready": True}})
    _write_json(source_quality_path, {"summary": {"research_ready": True}})
    _write_json(
        memory_path,
        {
            "summary": {"research_memory_ready": True, "entry_count": 2},
            "entries": [
                {"ontology_tags": ["failure", "data_coverage_gap"]},
                {"ontology_tags": ["hypothesis"]},
            ],
        },
    )
    _write_json(
        diagnostics_path,
        {
            "summary": {
                "status": "ready",
                "diagnostic_count": 1,
                "recommended_operator_step": "inspect_next_diagnostic",
                "blocking_reasons": [],
                "primary_failure_classification": "data_coverage_gap",
            }
        },
    )
    queue_path.parent.mkdir(parents=True, exist_ok=True)
    queue_path.write_text(
        "\n".join(
            [
                "- queue id: `ADE-QRE-007`",
                "- status: `done`",
                "- queue id: `ADE-QRE-008`",
                "- status: `operator_review`",
            ]
        ),
        encoding="utf-8",
    )

    snap = rom.collect_snapshot(
        routing_minimal_path=tmp_path / "no_routing.json",
        sampling_minimal_path=tmp_path / "no_sampling.json",
        reason_records_artifact_dir=tmp_path / "no_reason_records",
        kpi_doc_path=tmp_path / "no_kpi.md",
        screening_failure_attribution_path=screening_path,
        failure_action_mapping_path=action_path,
        data_manifest_path=manifest_path,
        source_quality_path=source_quality_path,
        research_memory_path=memory_path,
        research_diagnostics_loop_path=diagnostics_path,
        ade_queue_doc_path=queue_path,
        frozen_utc="2026-05-23T00:00:00Z",
    )
    summary = snap["qre_operator_summary"]

    assert summary["available_source_count"] == 7
    assert summary["unknown_failure_rate"] == 0.25
    assert summary["actionable_failure_rate"] == 0.75
    assert summary["attribution_depth_score"] == 0.85
    assert summary["data_readiness"]["research_ready"] is True
    assert summary["prior_similar_failures"]["prior_similar_failure_count"] == 1
    assert summary["diagnostics_loop"]["diagnostic_count"] == 1
    assert summary["governance_blockers"]["blockers"] == [
        {"queue_item": "ADE-QRE-008", "status": "operator_review"}
    ]
    assert summary["operator_state"] == "operator_gate_visible"
    assert summary["safety_invariants"]["dashboard_mutation_routes"] is False


def test_missing_sources_never_raise(tmp_path: Path) -> None:
    snap = rom.collect_snapshot(
        routing_minimal_path=tmp_path / "no_routing.json",
        sampling_minimal_path=tmp_path / "no_sampling.json",
        reason_records_artifact_dir=tmp_path / "no_reason_records",
        kpi_doc_path=tmp_path / "no_kpi.md",
        frozen_utc="2026-05-21T00:00:00Z",
    )
    for sid in ("routing_minimal", "sampling_minimal", "research_quality_kpis_doc"):
        assert snap["sources"][sid]["available"] is False
    # The reason-records source is "available: false" when the
    # manifest file is absent, but the live reader still produces a
    # deterministic empty projection.
    assert snap["sources"]["reason_records"]["available"] is False
    assert snap["sources"]["reason_records"]["total_records"] == 0


# ---------------------------------------------------------------------------
# OAB enforcement
# ---------------------------------------------------------------------------


def test_attention_overflow_empty_when_no_subjects(tmp_path: Path) -> None:
    snap = rom.collect_snapshot(
        routing_minimal_path=tmp_path / "no.json",
        sampling_minimal_path=tmp_path / "no.json",
        reason_records_artifact_dir=tmp_path / "no_rr",
        kpi_doc_path=tmp_path / "no.md",
        frozen_utc="2026-05-21T00:00:00Z",
    )
    oab = snap["operator_attention_budget"]
    assert oab["visible_surfaces_per_campaign_cap"] == 3
    assert oab["subjects_observed"] == 0
    assert oab["attention_overflow_subjects"] == []
    assert oab["near_cap_subjects"] == []


def test_attention_overflow_enforced_when_subject_exceeds_cap(
    tmp_path: Path,
) -> None:
    """A subject present in routing + sampling + scoring records
    has surface count 3. With cap 2 it overflows."""
    base = tmp_path / "logs" / "reason_records"
    _seed_reason_records(
        base,
        subject_to_kinds={
            "c_three_kinds": ["routing", "sampling", "scoring"],
            "c_two_kinds": ["routing", "sampling"],
            "c_one_kind": ["routing"],
        },
    )
    snap = rom.collect_snapshot(
        routing_minimal_path=tmp_path / "no.json",
        sampling_minimal_path=tmp_path / "no.json",
        reason_records_artifact_dir=base,
        kpi_doc_path=tmp_path / "no.md",
        visible_surfaces_per_campaign_cap=2,
        frozen_utc="2026-05-21T00:00:00Z",
    )
    oab = snap["operator_attention_budget"]
    assert oab["visible_surfaces_per_campaign_cap"] == 2
    assert oab["subjects_observed"] == 3
    assert oab["attention_overflow_subjects"] == ["c_three_kinds"]
    assert oab["near_cap_subjects"] == ["c_two_kinds"]
    assert oab["attention_overflow_count"] == 1
    assert oab["near_cap_count"] == 1


def test_default_cap_three_does_not_overflow_three_kinds(
    tmp_path: Path,
) -> None:
    """The default cap is 3; a subject in 3 kinds sits AT the cap,
    not OVER it."""
    base = tmp_path / "logs" / "reason_records"
    _seed_reason_records(
        base,
        subject_to_kinds={
            "c_all_three": ["routing", "sampling", "scoring"],
        },
    )
    snap = rom.collect_snapshot(
        routing_minimal_path=tmp_path / "no.json",
        sampling_minimal_path=tmp_path / "no.json",
        reason_records_artifact_dir=base,
        kpi_doc_path=tmp_path / "no.md",
        frozen_utc="2026-05-21T00:00:00Z",
    )
    oab = snap["operator_attention_budget"]
    assert oab["attention_overflow_subjects"] == []
    assert oab["near_cap_subjects"] == ["c_all_three"]


# ---------------------------------------------------------------------------
# Cross-family subjects
# ---------------------------------------------------------------------------


def test_cross_family_subjects_top_by_surface_count_is_deterministic(
    tmp_path: Path,
) -> None:
    base = tmp_path / "logs" / "reason_records"
    _seed_reason_records(
        base,
        subject_to_kinds={
            "c_three": ["routing", "sampling", "scoring"],
            "c_two_a": ["routing", "sampling"],
            "c_two_b": ["routing", "scoring"],
            "c_one": ["routing"],
        },
    )
    snap = rom.collect_snapshot(
        routing_minimal_path=tmp_path / "no.json",
        sampling_minimal_path=tmp_path / "no.json",
        reason_records_artifact_dir=base,
        kpi_doc_path=tmp_path / "no.md",
        frozen_utc="2026-05-21T00:00:00Z",
    )
    cfs = snap["cross_family_subjects"]
    assert cfs["total"] == 4
    # Sort: surface count DESC, then subject_id ASC. Two-kind
    # subjects must be deterministic on tiebreak (c_two_a < c_two_b).
    assert cfs["top_by_surface_count"] == {
        "c_three": 3,
        "c_two_a": 2,
        "c_two_b": 2,
        "c_one": 1,
    }


# ---------------------------------------------------------------------------
# Upstream digest reading
# ---------------------------------------------------------------------------


def test_routing_minimal_source_is_surfaced_when_present(
    tmp_path: Path,
) -> None:
    routing_path = (
        tmp_path
        / "logs"
        / "intelligent_routing_minimal"
        / "latest.json"
    )
    routing_path.parent.mkdir(parents=True, exist_ok=True)
    routing_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "module_version": "v3.15.16-minimal-reset-2026-05-21",
                "report_kind": "intelligent_routing_minimal_digest",
                "generated_at_utc": "2026-05-21T00:00:00Z",
                "counts": {
                    "total": 2,
                    "by_decision": {
                        "prioritize": 1,
                        "defer": 1,
                        "dead_zone_suppress": 0,
                        "reject": 0,
                    },
                },
                "final_recommendation": "ready_for_implementation",
            }
        ),
        encoding="utf-8",
    )
    snap = rom.collect_snapshot(
        routing_minimal_path=routing_path,
        sampling_minimal_path=tmp_path / "no.json",
        reason_records_artifact_dir=tmp_path / "no_rr",
        kpi_doc_path=tmp_path / "no.md",
        frozen_utc="2026-05-21T00:00:00Z",
    )
    rsrc = snap["sources"]["routing_minimal"]
    assert rsrc["available"] is True
    assert rsrc["counts"]["total"] == 2
    assert rsrc["counts"]["by_decision"]["prioritize"] == 1
    assert rsrc["final_recommendation"] == "ready_for_implementation"


def test_sampling_minimal_source_is_surfaced_when_present(
    tmp_path: Path,
) -> None:
    sampling_path = (
        tmp_path
        / "logs"
        / "sampling_intelligence_minimal"
        / "latest.json"
    )
    sampling_path.parent.mkdir(parents=True, exist_ok=True)
    sampling_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "module_version": "v3.15.17-minimal-reset-2026-05-21",
                "report_kind": "sampling_intelligence_minimal_digest",
                "generated_at_utc": "2026-05-21T00:00:00Z",
                "counts": {
                    "total": 3,
                    "by_decision": {
                        "stratify": 1,
                        "upsample": 1,
                        "exclude_region": 1,
                        "downsample": 0,
                        "null_baseline": 0,
                    },
                    "actionable": 2,
                },
                "final_recommendation": "ready_for_sampling",
            }
        ),
        encoding="utf-8",
    )
    snap = rom.collect_snapshot(
        routing_minimal_path=tmp_path / "no.json",
        sampling_minimal_path=sampling_path,
        reason_records_artifact_dir=tmp_path / "no_rr",
        kpi_doc_path=tmp_path / "no.md",
        frozen_utc="2026-05-21T00:00:00Z",
    )
    ssrc = snap["sources"]["sampling_minimal"]
    assert ssrc["available"] is True
    assert ssrc["counts"]["total"] == 3
    assert ssrc["counts"]["actionable"] == 2
    assert ssrc["counts"]["by_decision"]["stratify"] == 1
    assert ssrc["final_recommendation"] == "ready_for_sampling"


def test_reason_records_source_is_surfaced_when_records_present(
    tmp_path: Path,
) -> None:
    base = tmp_path / "logs" / "reason_records"
    _seed_reason_records(
        base,
        subject_to_kinds={
            "c1": ["routing", "sampling"],
            "c2": ["routing"],
        },
    )
    snap = rom.collect_snapshot(
        routing_minimal_path=tmp_path / "no.json",
        sampling_minimal_path=tmp_path / "no.json",
        reason_records_artifact_dir=base,
        kpi_doc_path=tmp_path / "no.md",
        frozen_utc="2026-05-21T00:00:00Z",
    )
    rrsrc = snap["sources"]["reason_records"]
    assert rrsrc["total_records"] == 3
    assert rrsrc["by_kind"]["routing"] == 2
    assert rrsrc["by_kind"]["sampling"] == 1
    # The manifest file is written by reason_records.append on
    # every successful append, so available is True now.
    assert rrsrc["available"] is True


def test_kpi_doc_source_surfaces_id_set_when_doc_present(
    tmp_path: Path,
) -> None:
    """When the canonical KPI doc exists, the source surfaces the
    seven KPI identifiers and an explicit not-yet-computed note."""
    snap = rom.collect_snapshot(
        routing_minimal_path=tmp_path / "no.json",
        sampling_minimal_path=tmp_path / "no.json",
        reason_records_artifact_dir=tmp_path / "no_rr",
        # Default kpi_doc_path uses the real repo doc, which exists.
        frozen_utc="2026-05-21T00:00:00Z",
    )
    kpi = snap["sources"]["research_quality_kpis_doc"]
    assert kpi["available"] is True
    assert kpi["kpi_ids"] == list(rom.RESEARCH_QUALITY_KPI_IDS)
    assert kpi["kpi_values_available"] is False


# ---------------------------------------------------------------------------
# Determinism + idempotence
# ---------------------------------------------------------------------------


def test_snapshot_is_byte_deterministic_with_frozen_timestamp(
    tmp_path: Path,
) -> None:
    base = tmp_path / "logs" / "reason_records"
    _seed_reason_records(
        base,
        subject_to_kinds={
            "c1": ["routing", "sampling"],
            "c2": ["routing"],
        },
    )
    a = rom.collect_snapshot(
        routing_minimal_path=tmp_path / "no.json",
        sampling_minimal_path=tmp_path / "no.json",
        reason_records_artifact_dir=base,
        kpi_doc_path=tmp_path / "no.md",
        frozen_utc="2026-05-21T00:00:00Z",
    )
    b = rom.collect_snapshot(
        routing_minimal_path=tmp_path / "no.json",
        sampling_minimal_path=tmp_path / "no.json",
        reason_records_artifact_dir=base,
        kpi_doc_path=tmp_path / "no.md",
        frozen_utc="2026-05-21T00:00:00Z",
    )
    assert json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)


# ---------------------------------------------------------------------------
# Atomic-write allowlist
# ---------------------------------------------------------------------------


def test_write_outputs_into_allowlisted_path(tmp_path: Path) -> None:
    base = tmp_path / "logs" / "research_observability_minimal"
    snap = rom.collect_snapshot(
        routing_minimal_path=tmp_path / "no.json",
        sampling_minimal_path=tmp_path / "no.json",
        reason_records_artifact_dir=tmp_path / "no_rr",
        kpi_doc_path=tmp_path / "no.md",
        frozen_utc="2026-05-21T00:00:00Z",
    )
    out = rom.write_outputs(snap, artifact_dir=base)
    latest = base / "latest.json"
    assert latest.is_file()
    assert "research_observability_minimal" in out["latest"]


def test_write_outputs_refuses_outside_allowlist(tmp_path: Path) -> None:
    bad = tmp_path / "evil_dir"
    bad.mkdir(parents=True, exist_ok=True)
    with pytest.raises(ValueError, match="outside allowlist"):
        rom._validate_write_target(bad / "latest.json")


# ---------------------------------------------------------------------------
# Module purity / no execution-side imports / no dashboard touch
# ---------------------------------------------------------------------------


def test_module_is_stdlib_only_in_source() -> None:
    """No subprocess / socket / requests / urllib imports."""
    src = Path(rom.__file__).resolve().read_text(encoding="utf-8")
    forbidden = (
        "import subprocess",
        "from subprocess",
        "import socket",
        "from socket",
        "import requests",
        "from requests",
        "import urllib.request",
        "from urllib.request",
    )
    for needle in forbidden:
        assert (
            needle not in src
        ), f"research_observability_minimal imports forbidden: {needle}"


def test_module_does_not_import_execution_surfaces() -> None:
    src = Path(rom.__file__).resolve().read_text(encoding="utf-8")
    forbidden = (
        "agent.execution",
        "agent.risk",
        "automation.live",
        "automation.broker",
        "broker.",
        "execution.live",
        "live.",
        "paper.",
        "shadow.",
        "trading.",
    )
    for needle in forbidden:
        assert (
            needle not in src
        ), f"research_observability_minimal imports forbidden: {needle}"


def test_module_does_not_modify_dashboard_dashboard_py_source() -> None:
    """CQD-I2: the minimal v3.15.18 slice must not import or write
    to ``dashboard/dashboard.py``."""
    src = Path(rom.__file__).resolve().read_text(encoding="utf-8")
    # The module must not import dashboard.dashboard.
    forbidden_imports = (
        "import dashboard.dashboard",
        "from dashboard.dashboard",
        "from dashboard import dashboard",
    )
    for needle in forbidden_imports:
        assert (
            needle not in src
        ), f"research_observability_minimal imports forbidden: {needle}"


def test_safe_to_execute_is_hardcoded_false() -> None:
    snap = rom.collect_snapshot(frozen_utc="2026-05-21T00:00:00Z")
    assert snap["safe_to_execute"] is False


def test_mode_is_dry_run() -> None:
    snap = rom.collect_snapshot(frozen_utc="2026-05-21T00:00:00Z")
    assert snap["mode"] == "dry-run"


# ---------------------------------------------------------------------------
# CLI smoke
# ---------------------------------------------------------------------------


def test_cli_status_returns_not_available_when_no_snapshot(
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        rom,
        "ARTIFACT_LATEST",
        tmp_path
        / "logs"
        / "research_observability_minimal"
        / "latest.json",
    )
    rc = rom.main(["--status"])
    out = capsys.readouterr().out
    assert rc == 0
    parsed = json.loads(out)
    assert parsed["final_recommendation"] == "not_available"


def test_cli_no_write_does_not_write_artifacts(
    capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    rc = rom.main(["--no-write", "--frozen-utc", "2026-05-21T00:00:00Z"])
    out = capsys.readouterr().out
    assert rc == 0
    parsed = json.loads(out)
    assert parsed["safe_to_execute"] is False
    assert "operator_attention_budget" in parsed
