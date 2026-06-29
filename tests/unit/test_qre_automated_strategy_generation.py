from __future__ import annotations

import json
from pathlib import Path

from packages.qre_research import automated_strategy_generation as gen
from packages.qre_research.generated_strategy_paths import (
    GENERATED_CLOSEOUT_PATH,
    GENERATED_LINEAGE_PATH,
    GENERATED_PRESETS_PATH,
    GENERATED_REGISTRY_PATH,
    GENERATED_SPECS_DIR,
    validate_write_target,
)
from reporting import qre_automated_generation_closeout as closeout
from reporting import qre_blocked_thesis_lineage_census as census
from reporting import qre_campaign_lineage_materialization as materialization
from reporting import qre_campaign_portfolio_reconstruction as portfolio
from reporting import qre_null_control_readiness as controls


REPO_ROOT = Path(__file__).resolve().parents[2]


def test_generated_write_surface_refuses_research_contract_paths() -> None:
    bad = REPO_ROOT / "research" / "research_latest.json"
    try:
        validate_write_target(bad)
    except ValueError as exc:
        assert "generated-research surface" in str(exc)
    else:  # pragma: no cover
        raise AssertionError("research/** path unexpectedly accepted")


def test_compile_outcomes_for_current_blocked_theses_are_closed() -> None:
    cross_expected = (
        "SPECIFICATION_READY"
        if (
            REPO_ROOT
            / "generated_research"
            / "primitives"
            / "registry"
            / "generated_primitive_registry.v1.json"
        ).is_file()
        else "BLOCKED_UNSUPPORTED_PRIMITIVE"
    )
    expected = {
        "atr_adaptive_trend_v0": "SPECIFICATION_READY",
        "regime_diagnostics_v1": "BLOCKED_IDENTITY",
        "multi_asset_trend_sleeve_v0": "BLOCKED_POLICY",
        "cross_sectional_momentum_v0": cross_expected,
        "dynamic_pairs_v0": "BLOCKED_IDENTITY",
        "volatility_compression_breakout_v0": "BLOCKED_IDENTITY",
    }
    for hypothesis_id, outcome in expected.items():
        result = gen.compile_strategy_spec(
            repo_root=REPO_ROOT,
            source_hypothesis_id=hypothesis_id,
        )
        assert result["outcome"] == outcome, (hypothesis_id, result)


def test_generated_artifacts_exist_and_manifest_matches_strategy_source() -> None:
    registry = json.loads((REPO_ROOT / GENERATED_REGISTRY_PATH).read_text(encoding="utf-8"))
    rows = registry["rows"]
    assert len(rows) >= 1
    entry = rows[0]
    strategy_id = entry["generated_strategy_id"]
    spec_path = REPO_ROOT / GENERATED_SPECS_DIR / f"{entry['strategy_spec_id']}.json"
    manifest_path = REPO_ROOT / "generated_research" / "manifests" / f"{strategy_id}.json"
    strategy_path = REPO_ROOT / entry["module_path"]
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    source = strategy_path.read_text(encoding="utf-8")
    assert manifest["generated_strategy_id"] == strategy_id
    assert gen.stable_digest(source) == manifest["code_hash"]
    assert spec_path.is_file()


def test_resolved_catalog_includes_manual_and_generated_origins() -> None:
    catalog = gen.build_resolved_strategy_catalog(REPO_ROOT)
    origins = {row["origin"] for row in catalog["rows"]}
    assert "MANUAL" in origins
    assert "GENERATED_AUTOMATED" in origins
    generated_rows = [row for row in catalog["rows"] if row["origin"] == "GENERATED_AUTOMATED"]
    assert len(generated_rows) >= 1
    assert all(row["authority"] == gen.REGISTRY_AUTHORITY for row in generated_rows)
    assert all(row["research_only"] is True for row in generated_rows)


def test_reporting_surfaces_shift_atr_from_implementation_missing() -> None:
    census_snapshot = census.collect_snapshot(repo_root=REPO_ROOT)
    census_rows = {row["source_hypothesis_id"]: row for row in census_snapshot["rows"]}
    assert census_rows["atr_adaptive_trend_v0"]["lineage_status"] == "PRESET_MISSING"

    materialization_snapshot = materialization.collect_snapshot(repo_root=REPO_ROOT)
    materialization_rows = {row["source_hypothesis_id"]: row for row in materialization_snapshot["rows"]}
    assert materialization_rows["atr_adaptive_trend_v0"]["materialization_state"] == "PRESET_MISSING"

    controls_snapshot = controls.collect_snapshot(repo_root=REPO_ROOT)
    controls_rows = {row["source_hypothesis_id"]: row for row in controls_snapshot["rows"]}
    assert controls_rows["atr_adaptive_trend_v0"]["completeness_state"] == "SPECIFIED_NOT_EXECUTED"

    portfolio_snapshot = portfolio.collect_snapshot(repo_root=REPO_ROOT)
    portfolio_rows = [row for row in portfolio_snapshot["rows"] if row["source_hypothesis_id"] == "atr_adaptive_trend_v0"]
    assert portfolio_rows
    assert all(row["inclusion_status"] == "BLOCKED" for row in portfolio_rows)
    assert any("generated_preset_missing" in row["blockers"] for row in portfolio_rows)


def test_automated_generation_closeout_reports_registered_strategy() -> None:
    snapshot = closeout.collect_snapshot(repo_root=REPO_ROOT)
    assert snapshot["summary"]["registered_count"] >= 1
    rows = {row["source_hypothesis_id"]: row for row in snapshot["rows"]}
    assert "atr_adaptive_trend_v0" in rows
    assert rows["atr_adaptive_trend_v0"]["final_generation_outcome"] == "RESEARCH_REGISTERED_AUTOMATED"
    assert rows["atr_adaptive_trend_v0"]["generated_strategy_id"]
    assert rows["atr_adaptive_trend_v0"]["campaign_readiness_state"] == "BLOCKED"


def test_generated_closeout_artifacts_are_present() -> None:
    for path in (
        GENERATED_CLOSEOUT_PATH,
        GENERATED_LINEAGE_PATH,
        GENERATED_PRESETS_PATH,
        GENERATED_REGISTRY_PATH,
    ):
        assert (REPO_ROOT / path).is_file(), path
