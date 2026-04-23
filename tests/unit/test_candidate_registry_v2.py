"""Tests for research.candidate_registry_v2 (v3.12 first-class registry)."""

from __future__ import annotations

import json

from research._sidecar_io import serialize_canonical
from research.candidate_registry_v2 import (
    REGISTRY_V2_SCHEMA_VERSION,
    build_candidate_id,
    build_registry_v2_payload,
)


RUN_ID = "20260423T120000000000Z"
GIT = "abc123"
NOW = "2026-04-23T12:00:00+00:00"


def _v1_candidate(
    strategy_name: str = "sma_crossover",
    asset: str = "NVDA",
    interval: str = "4h",
    status: str = "candidate",
    params: dict | None = None,
    failed: list[str] | None = None,
    escalated: list[str] | None = None,
) -> dict:
    params = params if params is not None else {"fast": 20, "slow": 100}
    reasoning = {
        "passed": ["leakage_checks_ok"],
        "failed": list(failed or []),
        "escalated": list(escalated or []),
    }
    return {
        "strategy_id": build_candidate_id(strategy_name, asset, interval, params),
        "strategy_name": strategy_name,
        "asset": asset,
        "interval": interval,
        "selected_params": params,
        "status": status,
        "reasoning": reasoning,
    }


def _v1_registry(candidates: list[dict]) -> dict:
    return {
        "version": "v1",
        "generated_at_utc": NOW,
        "git_revision": GIT,
        "promotion_config": {},
        "candidates": candidates,
        "summary": {"total": len(candidates)},
    }


def _research_latest(rows: list[dict]) -> dict:
    return {
        "generated_at_utc": NOW,
        "count": len(rows),
        "summary": {"success": len(rows), "failed": 0, "goedgekeurd": 0},
        "results": rows,
    }


def _research_row(
    strategy_name: str = "sma_crossover",
    asset: str = "NVDA",
    interval: str = "4h",
    params: dict | None = None,
    max_drawdown: float = 0.2,
    trades_per_maand: float = 5.0,
) -> dict:
    params = params if params is not None else {"fast": 20, "slow": 100}
    return {
        "timestamp_utc": NOW,
        "strategy_name": strategy_name,
        "family": "trend",
        "hypothesis": "",
        "asset": asset,
        "interval": interval,
        "params_json": json.dumps(params, sort_keys=True),
        "success": True,
        "error": "",
        "win_rate": 0.55,
        "sharpe": 1.1,
        "deflated_sharpe": 0.8,
        "max_drawdown": max_drawdown,
        "trades_per_maand": trades_per_maand,
        "consistentie": 0.5,
        "totaal_trades": 50,
        "goedgekeurd": True,
        "criteria_checks_json": "{}",
        "reden": "",
    }


def _run_meta() -> dict:
    return {
        "preset_name": "trend_equities_4h_baseline",
        "preset_universe": ["NVDA", "AMD", "ASML"],
        "config_hash": "deadbeef",
        "data_snapshot_id": "snap-1",
        "random_seed": 42,
        "adapter_versions": {"yfinance": "0.2"},
        "feature_versions": {},
        "evaluation_version": "1.0",
    }


def test_payload_top_level_shape() -> None:
    payload = build_registry_v2_payload(
        candidate_registry_v1=_v1_registry([_v1_candidate()]),
        research_latest=_research_latest([_research_row()]),
        run_candidates=None,
        run_meta=_run_meta(),
        defensibility=None,
        regime=None,
        cost_sens=None,
        breadth_context=None,
        run_id=RUN_ID,
        git_revision=GIT,
        generated_at_utc=NOW,
    )
    assert payload["schema_version"] == REGISTRY_V2_SCHEMA_VERSION == "2.0"
    assert payload["status_model_version"] == "v3.12.0"
    assert payload["generated_at_utc"] == NOW
    assert payload["run_id"] == RUN_ID
    assert payload["git_revision"] == GIT
    assert "summary" in payload
    assert "entries" in payload


def test_entry_contains_required_v3_12_fields() -> None:
    payload = build_registry_v2_payload(
        candidate_registry_v1=_v1_registry([_v1_candidate()]),
        research_latest=_research_latest([_research_row()]),
        run_candidates=None,
        run_meta=_run_meta(),
        defensibility=None,
        regime=None,
        cost_sens=None,
        breadth_context=None,
        run_id=RUN_ID,
        git_revision=GIT,
        generated_at_utc=NOW,
    )
    (entry,) = payload["entries"]
    required_keys = {
        "candidate_id",
        "experiment_family",
        "preset_origin",
        "strategy_name",
        "parameter_set",
        "asset",
        "interval",
        "asset_universe",
        "processing_state",
        "lifecycle_status",
        "legacy_verdict",
        "mapping_reason",
        "observed_reason_codes",
        "taxonomy_rejection_codes",
        "taxonomy_derivations",
        "scores",
        "paper_readiness_flags",
        "paper_readiness_assessment_status",
        "deployment_eligibility",
        "lineage_metadata",
        "source_artifact_references",
    }
    assert required_keys.issubset(entry.keys())


def test_legacy_needs_investigation_mapped_to_exploratory() -> None:
    payload = build_registry_v2_payload(
        candidate_registry_v1=_v1_registry([_v1_candidate(status="needs_investigation")]),
        research_latest=_research_latest([_research_row()]),
        run_candidates=None,
        run_meta=_run_meta(),
        defensibility=None,
        regime=None,
        cost_sens=None,
        breadth_context=None,
        run_id=RUN_ID,
        git_revision=GIT,
        generated_at_utc=NOW,
    )
    (entry,) = payload["entries"]
    assert entry["lifecycle_status"] == "exploratory"
    assert entry["legacy_verdict"] == "needs_investigation"
    assert entry["mapping_reason"] == "legacy_needs_investigation_mapped_to_exploratory"


def test_paper_readiness_flags_is_null_not_placeholder_dict() -> None:
    payload = build_registry_v2_payload(
        candidate_registry_v1=_v1_registry([_v1_candidate()]),
        research_latest=_research_latest([_research_row()]),
        run_candidates=None,
        run_meta=_run_meta(),
        defensibility=None,
        regime=None,
        cost_sens=None,
        breadth_context=None,
        run_id=RUN_ID,
        git_revision=GIT,
        generated_at_utc=NOW,
    )
    (entry,) = payload["entries"]
    assert entry["paper_readiness_flags"] is None
    assert entry["paper_readiness_assessment_status"] == "reserved_for_future_phase"
    assert entry["deployment_eligibility"] == "reserved_for_future_phase"


def test_entries_are_sorted_by_candidate_id() -> None:
    v1_a = _v1_candidate(strategy_name="zzz_strategy")
    v1_b = _v1_candidate(strategy_name="aaa_strategy")
    payload = build_registry_v2_payload(
        candidate_registry_v1=_v1_registry([v1_a, v1_b]),
        research_latest=_research_latest([_research_row("zzz_strategy"), _research_row("aaa_strategy")]),
        run_candidates=None,
        run_meta=_run_meta(),
        defensibility=None,
        regime=None,
        cost_sens=None,
        breadth_context=None,
        run_id=RUN_ID,
        git_revision=GIT,
        generated_at_utc=NOW,
    )
    ids = [e["candidate_id"] for e in payload["entries"]]
    assert ids == sorted(ids)


def test_scores_are_provisional_non_authoritative() -> None:
    payload = build_registry_v2_payload(
        candidate_registry_v1=_v1_registry([_v1_candidate()]),
        research_latest=_research_latest([_research_row()]),
        run_candidates=None,
        run_meta=_run_meta(),
        defensibility=None,
        regime=None,
        cost_sens=None,
        breadth_context=None,
        run_id=RUN_ID,
        git_revision=GIT,
        generated_at_utc=NOW,
    )
    (entry,) = payload["entries"]
    assert entry["scores"]["composite_status"] == "provisional"
    assert entry["scores"]["authoritative"] is False
    assert entry["scores"]["scoring_formula_version"] == "v0.1-experimental"


def test_taxonomy_derivations_have_no_per_entry_timestamp() -> None:
    payload = build_registry_v2_payload(
        candidate_registry_v1=_v1_registry([
            _v1_candidate(status="rejected", failed=["insufficient_trades"]),
        ]),
        research_latest=_research_latest([_research_row()]),
        run_candidates=None,
        run_meta=_run_meta(),
        defensibility=None,
        regime=None,
        cost_sens=None,
        breadth_context=None,
        run_id=RUN_ID,
        git_revision=GIT,
        generated_at_utc=NOW,
    )
    (entry,) = payload["entries"]
    for d in entry["taxonomy_derivations"]:
        assert "derived_at_utc" not in d
        assert "at_utc" not in d


def test_observed_reason_codes_mirror_v1_failed_and_escalated() -> None:
    v1 = _v1_candidate(
        status="rejected",
        failed=["insufficient_trades"],
        escalated=["psr_below_threshold"],
    )
    payload = build_registry_v2_payload(
        candidate_registry_v1=_v1_registry([v1]),
        research_latest=_research_latest([_research_row()]),
        run_candidates=None,
        run_meta=_run_meta(),
        defensibility=None,
        regime=None,
        cost_sens=None,
        breadth_context=None,
        run_id=RUN_ID,
        git_revision=GIT,
        generated_at_utc=NOW,
    )
    (entry,) = payload["entries"]
    assert set(entry["observed_reason_codes"]) == {"insufficient_trades", "psr_below_threshold"}


def test_lineage_metadata_pulls_from_run_meta() -> None:
    payload = build_registry_v2_payload(
        candidate_registry_v1=_v1_registry([_v1_candidate()]),
        research_latest=_research_latest([_research_row()]),
        run_candidates=None,
        run_meta=_run_meta(),
        defensibility=None,
        regime=None,
        cost_sens=None,
        breadth_context=None,
        run_id=RUN_ID,
        git_revision=GIT,
        generated_at_utc=NOW,
    )
    (entry,) = payload["entries"]
    lineage = entry["lineage_metadata"]
    assert lineage["run_id"] == RUN_ID
    assert lineage["git_revision"] == GIT
    assert lineage["config_hash"] == "deadbeef"
    assert lineage["random_seed"] == 42
    assert lineage["adapter_versions"] == {"yfinance": "0.2"}
    assert lineage["execution_engine_used"] == "research_only"


def test_summary_counts_by_lifecycle_and_processing() -> None:
    payload = build_registry_v2_payload(
        candidate_registry_v1=_v1_registry([
            _v1_candidate(status="candidate"),
            _v1_candidate(strategy_name="s2", status="rejected", failed=["insufficient_trades"]),
            _v1_candidate(strategy_name="s3", status="needs_investigation", escalated=["psr_below_threshold"]),
        ]),
        research_latest=_research_latest([
            _research_row(),
            _research_row("s2"),
            _research_row("s3"),
        ]),
        run_candidates=None,
        run_meta=_run_meta(),
        defensibility=None,
        regime=None,
        cost_sens=None,
        breadth_context=None,
        run_id=RUN_ID,
        git_revision=GIT,
        generated_at_utc=NOW,
    )
    summary = payload["summary"]
    assert summary["total"] == 3
    assert summary["by_lifecycle_status"]["candidate"] == 1
    assert summary["by_lifecycle_status"]["rejected"] == 1
    assert summary["by_lifecycle_status"]["exploratory"] == 1


def test_byte_reproducible_across_two_calls() -> None:
    kwargs = dict(
        candidate_registry_v1=_v1_registry([_v1_candidate()]),
        research_latest=_research_latest([_research_row()]),
        run_candidates=None,
        run_meta=_run_meta(),
        defensibility=None,
        regime=None,
        cost_sens=None,
        breadth_context=None,
        run_id=RUN_ID,
        git_revision=GIT,
        generated_at_utc=NOW,
    )
    a = build_registry_v2_payload(**kwargs)  # type: ignore[arg-type]
    b = build_registry_v2_payload(**kwargs)  # type: ignore[arg-type]
    assert serialize_canonical(a) == serialize_canonical(b)


def test_source_artifact_references_present_and_full() -> None:
    payload = build_registry_v2_payload(
        candidate_registry_v1=_v1_registry([_v1_candidate()]),
        research_latest=_research_latest([_research_row()]),
        run_candidates=None,
        run_meta=_run_meta(),
        defensibility=None,
        regime=None,
        cost_sens=None,
        breadth_context=None,
        run_id=RUN_ID,
        git_revision=GIT,
        generated_at_utc=NOW,
    )
    (entry,) = payload["entries"]
    refs = entry["source_artifact_references"]
    expected_keys = {
        "run_candidates",
        "candidate_registry_v1",
        "statistical_defensibility",
        "regime_diagnostics",
        "cost_sensitivity",
        "run_meta",
    }
    assert set(refs.keys()) == expected_keys


def test_rejected_candidate_produces_taxonomy_codes() -> None:
    v1 = _v1_candidate(
        status="rejected",
        failed=["insufficient_trades", "drawdown_above_limit"],
    )
    payload = build_registry_v2_payload(
        candidate_registry_v1=_v1_registry([v1]),
        research_latest=_research_latest([_research_row(max_drawdown=0.5)]),
        run_candidates=None,
        run_meta=_run_meta(),
        defensibility=None,
        regime=None,
        cost_sens=None,
        breadth_context=None,
        run_id=RUN_ID,
        git_revision=GIT,
        generated_at_utc=NOW,
    )
    (entry,) = payload["entries"]
    assert "insufficient_trades" in entry["taxonomy_rejection_codes"]
    assert "oos_collapse" in entry["taxonomy_rejection_codes"]


def test_preset_origin_and_universe_populated_from_run_meta() -> None:
    payload = build_registry_v2_payload(
        candidate_registry_v1=_v1_registry([_v1_candidate()]),
        research_latest=_research_latest([_research_row()]),
        run_candidates=None,
        run_meta=_run_meta(),
        defensibility=None,
        regime=None,
        cost_sens=None,
        breadth_context=None,
        run_id=RUN_ID,
        git_revision=GIT,
        generated_at_utc=NOW,
    )
    (entry,) = payload["entries"]
    assert entry["preset_origin"] == "trend_equities_4h_baseline"
    assert entry["asset_universe"] == ["NVDA", "AMD", "ASML"]
