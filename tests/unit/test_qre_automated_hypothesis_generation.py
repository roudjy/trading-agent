from __future__ import annotations

import json
from pathlib import Path

from packages.qre_research import automated_hypothesis_generation as a20
from packages.qre_research.generated_hypothesis_paths import (
    GENERATED_THESIS_REGISTRY_PATH,
    INTEGRATED_CLOSEOUT_PATH,
    RESOLVED_THESIS_CATALOG_PATH,
    validate_write_target,
)


REPO_ROOT = Path(__file__).resolve().parents[2]


def test_generated_hypothesis_write_surface_refuses_research_contract_paths() -> None:
    bad = REPO_ROOT / "research" / "research_latest.json"
    try:
        validate_write_target(bad)
    except ValueError as exc:
        assert "generated hypothesis surfaces" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("research/** path unexpectedly accepted")


def test_evidence_snapshot_is_deterministic() -> None:
    left = a20.build_evidence_snapshot(repo_root=REPO_ROOT)
    right = a20.build_evidence_snapshot(repo_root=REPO_ROOT)
    assert left == right
    assert left["evidence_snapshot_id"].startswith("qhs_")


def test_candidate_pipeline_uses_closed_vocabularies() -> None:
    compiled = a20.compile_candidate_theses(repo_root=REPO_ROOT)
    assert compiled["summary"]["candidate_count"] >= 1
    for row in compiled["rows"]:
        assert row["lifecycle_state"] in a20.THESIS_LIFECYCLE_STATES
        assert row["novelty_outcome"] in a20.NOVELTY_OUTCOMES
        assert row["testability_state"] in a20.TESTABILITY_STATES
        assert row["primitive_compatibility"] in a20.COMPATIBILITY_STATES


def test_rejected_trend_pullback_lineage_is_preserved() -> None:
    compiled = a20.compile_candidate_theses(repo_root=REPO_ROOT)
    rows = {row["source_hypothesis_id"]: row for row in compiled["rows"]}
    trend = rows["trend_pullback_v1"]
    assert trend["lifecycle_state"] == "REJECTED_UNFALSIFIABLE" or trend["lifecycle_state"] == "REJECTED_REJECTED_LINEAGE"
    assert trend["novelty_outcome"] == "REJECTED_LINEAGE_MATCH"


def test_cross_sectional_candidate_creates_bounded_extension_request() -> None:
    compiled = a20.compile_candidate_theses(repo_root=REPO_ROOT)
    rows = {row["source_hypothesis_id"]: row for row in compiled["rows"]}
    cross = rows["cross_sectional_momentum_v0"]
    assert cross["primitive_compatibility"] == "COMPILABLE_AFTER_BOUNDED_PRIMITIVE_EXTENSION"
    requests = compiled["primitive_extension_requests"]
    assert any(row["required_primitive"] == "cross_sectional_rank" for row in requests)


def test_resolved_thesis_catalog_has_single_authority_view() -> None:
    catalog = a20.build_resolved_thesis_catalog(repo_root=REPO_ROOT)
    origins = {row["origin"] for row in catalog["rows"]}
    assert "MANUAL" in origins
    assert "GENERATED_AUTOMATED" in origins or catalog["summary"]["generated_count"] == 0
    assert catalog["resolved_thesis_catalog_id"].startswith("qtc_")


def test_a20_does_not_generate_strategy_code_directly() -> None:
    before = sorted(
        path.name
        for path in (REPO_ROOT / "agent" / "backtesting" / "generated_strategies").glob("generated_*.py")
    )
    a20.run_automated_hypothesis_generation(repo_root=REPO_ROOT)
    after = sorted(
        path.name
        for path in (REPO_ROOT / "agent" / "backtesting" / "generated_strategies").glob("generated_*.py")
    )
    assert after == before


def test_a20_integration_preserves_fail_closed_submission() -> None:
    submission = a20.integrate_with_ade_qre_019(repo_root=REPO_ROOT)
    for row in submission["rows"]:
        assert row["submission_state"] in {"submitted", "blocked"}
    assert submission["summary"]["submitted_count"] == 0


def test_run_outputs_are_present_and_deterministic() -> None:
    left = a20.run_automated_hypothesis_generation(repo_root=REPO_ROOT)
    right = a20.run_automated_hypothesis_generation(repo_root=REPO_ROOT)
    assert left == right
    for path in (
        GENERATED_THESIS_REGISTRY_PATH,
        RESOLVED_THESIS_CATALOG_PATH,
        INTEGRATED_CLOSEOUT_PATH,
    ):
        assert (REPO_ROOT / path).is_file(), path
    closeout = json.loads((REPO_ROOT / INTEGRATED_CLOSEOUT_PATH).read_text(encoding="utf-8"))
    assert closeout["program_outcome"] in a20.PROGRAM_OUTCOMES
    assert closeout["summary"]["submitted_count"] == 0


def test_generated_registry_is_not_second_final_authority() -> None:
    registry = json.loads((REPO_ROOT / GENERATED_THESIS_REGISTRY_PATH).read_text(encoding="utf-8"))
    catalog = json.loads((REPO_ROOT / RESOLVED_THESIS_CATALOG_PATH).read_text(encoding="utf-8"))
    assert registry["report_kind"] == "qre_generated_thesis_registry"
    assert catalog["report_kind"] == "qre_resolved_thesis_catalog"
    assert catalog["summary"]["manual_count"] >= 1
