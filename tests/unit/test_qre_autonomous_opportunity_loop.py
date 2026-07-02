from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from packages.qre_research import autonomous_opportunity_loop as aol
from reporting import execution_authority as ea
from reporting import qre_research_operations as qro


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


@pytest.fixture()
def repo_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    repo = tmp_path / "repo"
    _write_json(
        repo / "logs/qre_data_cache_manifest/latest.json",
        {
            "cache_roots": [{"cache_kind": "ohlcv", "status": "ready"}],
            "coverage": [
                {
                    "source": "polygon",
                    "instrument": "AAPL",
                    "timeframe": "4h",
                    "content_hash": "hash-a",
                    "max_timestamp_utc": "2026-06-30T20:00:00Z",
                }
            ],
        },
    )
    _write_json(
        repo / "logs/qre_data_source_quality_readiness/latest.json",
        {"sources": [{"source": "polygon", "ready": "READY"}]},
    )
    _write_json(
        repo / "generated_research/readiness/campaigns/automated_portfolio_readiness.v1.json",
        {
            "rows": [
                {
                    "campaign_cell_id": "qrcell_1",
                    "generated_strategy_id": "qgs_1",
                    "timeframe": "4h",
                    "status": "READY_FOR_PREREGISTRATION",
                    "blockers": [],
                    "dataset_identity": "qds_1",
                    "snapshot_identity": "qsn_1",
                    "train_window": {"end": "2025-09-30T20:00:00Z"},
                    "validation_window": {"end": "2025-12-31T20:00:00Z"},
                    "oos_window": {"start": "2026-01-01T20:00:00Z", "end": "2026-06-30T20:00:00Z"},
                }
            ]
        },
    )
    _write_json(
        repo / "generated_research/registry/generated_strategy_registry.v1.json",
        {"rows": [{"generated_strategy_id": "qgs_1", "source_hypothesis_id": "hyp_source_1"}]},
    )
    _write_json(
        repo / "generated_research/primitives/registry/generated_primitive_registry.v1.json",
        {"rows": [{"primitive_id": "atr", "generated_primitive_id": "qgp_1", "state": "PRIMITIVE_REGISTERED_AUTOMATED"}]},
    )
    _write_json(
        repo / "generated_research/readiness/identity_decisions/autonomous_universe_authority.v1.json",
        {"rows": [{"generated_strategy_id": "qgs_1", "outcome": "IDENTITY_RESOLVED"}]},
    )
    _write_json(
        repo / "generated_research/hypotheses/registry/generated_thesis_registry.v1.json",
        {"rows": [{"thesis_id": "qht_1"}]},
    )
    _write_json(
        repo / "generated_research/hypotheses/lifecycle/research_memory.v1.json",
        {"rows": []},
    )
    _write_json(
        repo / "generated_research/hypotheses/lifecycle/evidence_updates.v1.json",
        {"rows": []},
    )
    _write_json(
        repo / "generated_research/orchestration/trust_closure/research_continuation_plan.v1.json",
        {"required_novelty": ["NEW_COMPLETE_MARKET_DATA"], "active_blocker": "signal_density", "blocked_cells": ["qrcell_1"]},
    )
    _write_json(
        repo / "generated_research/orchestration/trust_closure/shadow_readiness.v1.json",
        {"shadow_readiness": "INSUFFICIENT_HISTORY"},
    )
    _write_json(
        repo / "generated_research/campaign_execution/evidence/empirical_campaign_history.v1.json",
        {"rows": []},
    )
    monkeypatch.setattr(
        aol.a20,
        "compile_candidate_theses",
        lambda *, repo_root=None: {
            "rows": [
                {
                    "thesis_id": "qht_1",
                    "source_hypothesis_id": "hyp_source_1",
                    "mechanism_class": "trend_persistence",
                    "behavior_family": "trend",
                    "regimes": ["trend"],
                    "novelty_outcome": "NOVEL",
                    "lifecycle_state": "HYPOTHESIS_ADMITTED_AUTOMATED",
                    "primitive_compatibility": "COMPILABLE_WITH_CURRENT_PRIMITIVES",
                    "required_features": ["atr"],
                    "required_diagnostics": ["null_control"],
                    "null_control_requirements": ["null_control"],
                    "falsification_criteria": ["breaks below trail"],
                    "strongest_supporting_evidence": ["support"],
                    "strongest_contradicting_evidence": [],
                    "required_data": ["ohlcv"],
                    "testability_state": "READY",
                    "parameter_schema": [{"name": "lookback"}, {"name": "threshold"}, {"name": "warmup"}, {"name": "extra"}],
                    "causal_mechanism": "trend persists after volatility compression",
                    "title": "Trend persistence after compression",
                    "timeframe": "4h",
                    "universe": "US_LARGE_CAP",
                    "expected_signal_density_range": "medium",
                    "entry_relevant_observations": ["compression"],
                    "null_hypothesis": "no persistence",
                }
            ]
        },
    )
    monkeypatch.setattr(
        aol.a20,
        "build_evidence_snapshot",
        lambda *, repo_root=None: {"manual_thesis_digest": "manual-digest"},
    )
    monkeypatch.setattr(
        aol.a20,
        "detect_opportunities",
        lambda *, repo_root=None: {
            "rows": [{"opportunity_id": "opp_1", "opportunity_class": "DATA_DELTA", "priority": 1}],
            "summary": {"opportunity_count": 1},
        },
    )
    return repo


def test_build_precheck_same_watermark_is_no_material_change(repo_root: Path) -> None:
    watermark = aol.build_watermark(repo_root=repo_root)

    payload = aol.build_precheck(watermark, watermark)

    assert payload["precheck_status"] == "NO_MATERIAL_CHANGE"
    assert payload["triggers"] == []


def test_build_precheck_new_oos_boundary_is_material_data_change(repo_root: Path) -> None:
    previous = aol.build_watermark(repo_root=repo_root)
    current = json.loads(json.dumps(previous))
    current["usable_oos_end_by_cell"]["qrcell_1"] = "2026-07-31T20:00:00Z"
    current["watermark_id"] = "changed"

    payload = aol.build_precheck(previous, current)

    assert payload["precheck_status"] in {"MATERIAL_DATA_CHANGE", "MULTIPLE_MATERIAL_CHANGES"}
    assert "NEW_USABLE_OOS_WINDOW" in payload["triggers"]


def test_generate_hypothesis_batch_is_deterministic_and_bounded(repo_root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        aol.a20,
        "run_automated_hypothesis_generation",
        lambda *, repo_root=None, write_outputs=True: {"provenance": ["fixture"]},
    )
    opportunities = {
        "rows": [{"opportunity_id": "opp_1"}],
        "summary": {"opportunity_count": 1},
    }

    first = aol.generate_hypothesis_batch(
        repo_root=repo_root,
        opportunities=opportunities,
        max_generated=8,
        write_outputs=False,
    )
    second = aol.generate_hypothesis_batch(
        repo_root=repo_root,
        opportunities=opportunities,
        max_generated=8,
        write_outputs=False,
    )
    row = first["batch"]["rows"][0]

    assert first == second
    assert row["admission_status"] == "HYPOTHESIS_ADMITTED"
    assert row["parameter_count"] == 3
    assert len(row["parameter_schema"]) == 3
    assert "def " not in json.dumps(row, sort_keys=True)


def test_materialize_campaign_cells_suppresses_duplicate_frozen_work(repo_root: Path) -> None:
    _write_json(
        repo_root / "generated_research/campaign_execution/evidence/empirical_campaign_history.v1.json",
        {
            "rows": [
                {
                    "source_hypothesis_id": "hyp_source_1",
                    "timeframe": "4h",
                    "oos_window": {"end": "2026-06-30T20:00:00Z"},
                    "campaign_cell_id": "qrcell_1",
                }
            ]
        },
    )
    hypotheses = {
        "rows": [
            {
                "hypothesis_id": "qht_1",
                "admission_status": "HYPOTHESIS_ADMITTED",
                "source_hypothesis_id": "hyp_source_1",
                "mechanism_family": "trend_persistence",
                "universe_definition": "US_LARGE_CAP",
                "regime_scope": ["trend"],
                "required_primitives": ["atr"],
                "cost_assumptions": {"estimated_compute_cost": "low"},
                "slippage_assumptions": {"bounded": True},
                "required_controls": ["null_control"],
                "novelty_dimensions": ["new_causal_mechanism"],
                "timeframe": "4h",
            }
        ]
    }

    payload = aol.materialize_campaign_cells(repo_root=repo_root, hypotheses=hypotheses, max_cells=8)

    assert payload["registry"]["rows"][0]["genuine_novelty_decision"] == "SUPPRESSED"
    assert payload["novelty"]["rows"][0]["reason_codes"] == ["identical_frozen_campaign_already_executed"]


def test_build_ade_requests_deduplicates_persistent_generic_gap(repo_root: Path) -> None:
    gap_registry = {
        "rows": [
            {
                "gap_id": "gap_1",
                "gap_class": "PRIMITIVE_CAPABILITY_GAP",
                "persistent": True,
                "code_addressable": True,
                "deduplication_key": "dedup_1",
                "occurrence_count": 2,
                "first_seen_state": "state_1",
                "latest_seen_state": "state_2",
                "evidence_refs": [aol.CAMPAIGN_CELL_PATH.as_posix()],
                "source_hypothesis_id": "hyp_source_1",
                "campaign_cell_id": "qrcell_1",
            }
        ]
    }

    first = aol.build_ade_requests(repo_root=repo_root, gap_registry=gap_registry, run_id="run_1")
    _write_json(repo_root / aol.ADE_REQUESTS_PATH, first["requests"])
    second = aol.build_ade_requests(repo_root=repo_root, gap_registry=gap_registry, run_id="run_2")

    assert first["requests"]["summary"]["new_requests"] == 1
    assert second["requests"]["summary"]["new_requests"] == 1
    assert len(second["requests"]["rows"]) == 1
    assert second["requests"]["rows"][0]["occurrence_count"] == 4
    assert second["requests"]["rows"][0]["execution_authority_result"] in {
        ea.DECISION_AUTO_ALLOWED,
        ea.DECISION_NEEDS_HUMAN,
        ea.DECISION_PERMANENTLY_DENIED,
    }


def test_consume_resolution_feedback_reopens_resolved_request(repo_root: Path) -> None:
    _write_json(
        repo_root / "logs/development_work_queue/latest.json",
        {
            "items": [
                {
                    "item_id": "dwq_1",
                    "title": "Resolve qrdr_123 primitive gap",
                    "notes": "Request qrdr_123 completed",
                    "status": "done",
                }
            ]
        },
    )

    payload = aol.consume_resolution_feedback(
        repo_root=repo_root,
        request_rows=[{"request_id": "qrdr_123"}],
    )

    assert payload["summary"]["resolved_request_count"] == 1
    assert payload["rows"][0]["capability_gap_resolved_trigger"] == "CAPABILITY_GAP_RESOLVED"


def test_write_ade_bridge_artifacts_uses_canonical_log_intake(
    repo_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        aol.qdip,
        "collect_snapshot",
        lambda *, input_artifact_path, generated_at_utc: {
            "report_kind": "qre_development_intake_promotion",
            "input_artifact_path": str(input_artifact_path),
        },
    )
    monkeypatch.setattr(aol.qdip, "write_outputs", lambda snapshot: repo_root / "logs/qre_development_intake_promotion/latest.json")
    monkeypatch.setattr(
        aol.qdap,
        "collect_snapshot",
        lambda *, input_artifact_path, generated_at_utc: {
            "report_kind": "qre_development_queue_admission_policy",
            "input_artifact_path": str(input_artifact_path),
        },
    )
    monkeypatch.setattr(aol.qdap, "write_outputs", lambda snapshot: repo_root / "logs/qre_development_queue_admission_policy/latest.json")

    payload = aol._write_ade_bridge_artifacts(
        repo_root=repo_root,
        proposal_intake_payload={
            "schema_version": 1,
            "report_kind": "qre_research_action_proposal_intake",
            "generated_at_utc": "2026-07-02T00:00:00Z",
            "safe_to_execute": False,
            "proposals": [],
        },
    )

    assert (repo_root / aol.PROPOSAL_INTAKE_PATH).is_file()
    assert payload["promotion_snapshot"]["report_kind"] == "qre_development_intake_promotion"


def test_run_opportunity_loop_stops_early_on_no_material_change(
    repo_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    watermark = aol.build_watermark(repo_root=repo_root)
    _write_json(repo_root / aol.WATERMARK_PATH, watermark)
    _write_json(repo_root / aol.STATE_PATH, {"content_identity": "prior_state"})
    trusted_calls: list[str] = []
    monkeypatch.setattr(
        aol.qhl,
        "run_trusted_hypothesis_loop",
        lambda *, repo_root=None, write_outputs=True: trusted_calls.append("trusted") or {"summary": {}},
    )
    monkeypatch.setattr(aol, "discover_opportunities", lambda **kwargs: (_ for _ in ()).throw(AssertionError("discover should not run")))
    monkeypatch.setattr(aol, "generate_hypothesis_batch", lambda **kwargs: (_ for _ in ()).throw(AssertionError("generate should not run")))
    monkeypatch.setattr(aol, "materialize_campaign_cells", lambda **kwargs: (_ for _ in ()).throw(AssertionError("cells should not run")))
    monkeypatch.setattr(aol.spc, "run_second_preregistered_campaign", lambda **kwargs: (_ for _ in ()).throw(AssertionError("executor should not run")))

    payload = aol.run_opportunity_loop(repo_root=repo_root, write_outputs=True)

    assert payload["state"] == "WAITING_FOR_NOVELTY"
    assert payload["precheck"]["precheck_status"] == "NO_MATERIAL_CHANGE"
    assert payload["hypotheses"]["generated"] == 0
    assert payload["campaigns"]["executed"] == 0
    assert payload["ade_requests"]["new_requests"] == 0
    assert trusted_calls == ["trusted"]


def test_run_opportunity_loop_executes_material_opportunity_and_writes_artifacts(
    repo_root: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        aol,
        "discover_opportunities",
        lambda **kwargs: {
            "schema_version": aol.SCHEMA_VERSION,
            "policy_version": aol.POLICY_VERSION,
            "report_kind": "qre_research_opportunity_registry",
            "rows": [{"opportunity_id": "opp_1"}],
            "summary": {"opportunity_count": 1},
            "content_identity": "opp_identity",
        },
    )
    monkeypatch.setattr(
        aol,
        "generate_hypothesis_batch",
        lambda **kwargs: {
            "batch": {
                "schema_version": aol.SCHEMA_VERSION,
                "policy_version": aol.POLICY_VERSION,
                "report_kind": "qre_generated_hypothesis_batch",
                "rows": [
                    {
                        "hypothesis_id": "qht_1",
                        "admission_status": "HYPOTHESIS_ADMITTED",
                        "source_hypothesis_id": "hyp_source_1",
                        "mechanism_family": "trend_persistence",
                        "universe_definition": "US_LARGE_CAP",
                        "regime_scope": ["trend"],
                        "required_primitives": ["atr"],
                        "cost_assumptions": {"estimated_compute_cost": "low"},
                        "slippage_assumptions": {"bounded": True},
                        "required_controls": ["null_control"],
                        "novelty_dimensions": ["new_causal_mechanism"],
                        "timeframe": "4h",
                        "content_identity": "hyp_identity",
                    }
                ],
                "summary": {"generated": 1, "admitted": 1, "exact_duplicates": 0, "near_duplicates": 0},
                "content_identity": "batch_identity",
            },
            "novelty": {"schema_version": aol.SCHEMA_VERSION, "policy_version": aol.POLICY_VERSION, "report_kind": "qre_hypothesis_novelty_decisions", "rows": [], "content_identity": "novelty_identity"},
        },
    )
    monkeypatch.setattr(
        aol,
        "materialize_campaign_cells",
        lambda **kwargs: {
            "registry": {
                "schema_version": aol.SCHEMA_VERSION,
                "policy_version": aol.POLICY_VERSION,
                "report_kind": "qre_campaign_cell_registry",
                "rows": [
                    {
                        "campaign_cell_id": "qrcell_1",
                        "timeframe": "4h",
                        "readiness": "READY_FOR_PREREGISTRATION",
                        "expected_information_gain": "high",
                        "genuine_novelty_decision": "ADMITTED",
                        "blockers": [],
                        "content_identity": "cell_identity",
                    }
                ],
                "summary": {"materialized": 1, "admitted": 1},
                "content_identity": "cells_identity",
            },
            "novelty": {"schema_version": aol.SCHEMA_VERSION, "policy_version": aol.POLICY_VERSION, "report_kind": "qre_campaign_cell_novelty_decisions", "rows": [], "content_identity": "cell_novelty_identity"},
        },
    )
    monkeypatch.setattr(
        aol,
        "build_gap_registry",
        lambda **kwargs: {
            "schema_version": aol.SCHEMA_VERSION,
            "policy_version": aol.POLICY_VERSION,
            "report_kind": "qre_capability_gap_registry",
            "rows": [],
            "summary": {"gap_count": 0},
            "content_identity": "gap_identity",
        },
    )
    monkeypatch.setattr(
        aol,
        "build_ade_requests",
        lambda **kwargs: {
            "requests": {
                "schema_version": aol.SCHEMA_VERSION,
                "policy_version": aol.POLICY_VERSION,
                "report_kind": "qre_ade_development_requests",
                "rows": [],
                "summary": {"request_count": 0, "new_requests": 0, "auto_allowed": 0, "needs_human": 0, "permanently_denied": 0},
                "content_identity": "requests_identity",
            },
            "proposal_intake_payload": {"schema_version": 1, "report_kind": "qre_research_action_proposal_intake", "generated_at_utc": "2026-07-02T00:00:00Z", "safe_to_execute": False, "proposals": []},
            "promotion_snapshot": None,
        },
    )
    trusted_calls: list[str] = []
    monkeypatch.setattr(
        aol.qhl,
        "run_trusted_hypothesis_loop",
        lambda *, repo_root=None, write_outputs=True: trusted_calls.append("trusted") or {"summary": {}},
    )
    monkeypatch.setattr(
        aol.spc,
        "run_second_preregistered_campaign",
        lambda **kwargs: {"campaign_cell_id": kwargs["campaign_cell_id"], "terminal_outcome": "NEEDS_MORE_EVIDENCE"},
    )

    payload = aol.run_opportunity_loop(repo_root=repo_root, write_outputs=True)

    assert payload["state"] == "RESEARCH_EXECUTED"
    assert payload["campaigns"]["executed"] == 1
    assert trusted_calls == ["trusted"]
    assert (repo_root / aol.RUN_PATH).is_file()
    assert (repo_root / aol.STATE_PATH).is_file()


def test_stale_lock_is_recovered(repo_root: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _write_json(
        repo_root / aol.LOCK_PATH,
        {"run_id": "old", "acquired_at": "2026-01-01T00:00:00Z", "lease_expires_at": "2026-01-01T00:05:00Z"},
    )
    monkeypatch.setattr(
        aol.qhl,
        "run_trusted_hypothesis_loop",
        lambda *, repo_root=None, write_outputs=True: {"summary": {}},
    )
    monkeypatch.setattr(aol, "discover_opportunities", lambda **kwargs: {"schema_version": aol.SCHEMA_VERSION, "policy_version": aol.POLICY_VERSION, "report_kind": "qre_research_opportunity_registry", "rows": [], "summary": {"opportunity_count": 0}, "content_identity": "opp"})
    monkeypatch.setattr(aol, "generate_hypothesis_batch", lambda **kwargs: {"batch": {"schema_version": aol.SCHEMA_VERSION, "policy_version": aol.POLICY_VERSION, "report_kind": "qre_generated_hypothesis_batch", "rows": [], "summary": {"generated": 0, "admitted": 0, "exact_duplicates": 0, "near_duplicates": 0}, "content_identity": "batch"}, "novelty": {"schema_version": aol.SCHEMA_VERSION, "policy_version": aol.POLICY_VERSION, "report_kind": "qre_hypothesis_novelty_decisions", "rows": [], "content_identity": "novelty"}})
    monkeypatch.setattr(aol, "materialize_campaign_cells", lambda **kwargs: {"registry": {"schema_version": aol.SCHEMA_VERSION, "policy_version": aol.POLICY_VERSION, "report_kind": "qre_campaign_cell_registry", "rows": [], "summary": {"materialized": 0, "admitted": 0}, "content_identity": "cells"}, "novelty": {"schema_version": aol.SCHEMA_VERSION, "policy_version": aol.POLICY_VERSION, "report_kind": "qre_campaign_cell_novelty_decisions", "rows": [], "content_identity": "cells_novelty"}})
    monkeypatch.setattr(aol, "build_gap_registry", lambda **kwargs: {"schema_version": aol.SCHEMA_VERSION, "policy_version": aol.POLICY_VERSION, "report_kind": "qre_capability_gap_registry", "rows": [], "summary": {"gap_count": 0}, "content_identity": "gaps"})
    monkeypatch.setattr(aol, "build_ade_requests", lambda **kwargs: {"requests": {"schema_version": aol.SCHEMA_VERSION, "policy_version": aol.POLICY_VERSION, "report_kind": "qre_ade_development_requests", "rows": [], "summary": {"request_count": 0, "new_requests": 0, "auto_allowed": 0, "needs_human": 0, "permanently_denied": 0}, "content_identity": "reqs"}, "proposal_intake_payload": {"schema_version": 1, "report_kind": "qre_research_action_proposal_intake", "generated_at_utc": "2026-07-02T00:00:00Z", "safe_to_execute": False, "proposals": []}, "promotion_snapshot": None})

    payload = aol.run_opportunity_loop(repo_root=repo_root, write_outputs=True)

    assert payload["state"] == "WAITING_FOR_NOVELTY"
    assert not (repo_root / aol.LOCK_PATH).exists()


def test_qre_research_operations_exposes_opportunity_loop_status(repo_root: Path, capsys: pytest.CaptureFixture[str]) -> None:
    _write_json(
        repo_root / aol.STATE_PATH,
        {
            "schema_version": aol.SCHEMA_VERSION,
            "policy_version": aol.POLICY_VERSION,
            "report_kind": aol.REPORT_KIND,
            "state": "WAITING_FOR_NOVELTY",
            "current_wait_reason": "no_material_change",
            "content_identity": "state_identity",
        },
    )

    exit_code = qro.main(["--repo-root", str(repo_root), "opportunity-loop-status"])
    stdout = capsys.readouterr().out

    assert exit_code == 0
    assert '"state": "WAITING_FOR_NOVELTY"' in stdout


def test_qre_research_operations_runs_opportunity_loop_once(
    repo_root: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    monkeypatch.setattr(
        aol,
        "run_opportunity_loop",
        lambda *, repo_root, max_cycles=None, write_outputs=True: {
            "state": "WAITING_FOR_NOVELTY",
            "max_cycles": max_cycles,
        },
    )

    exit_code = qro.main(["--repo-root", str(repo_root), "opportunity-loop-run-once", "--max-cycles", "2"])
    stdout = capsys.readouterr().out

    assert exit_code == 0
    assert '"max_cycles": 2' in stdout
