from __future__ import annotations

import json
from pathlib import Path

from research import qre_basket_evidence_recovery_plan as recovery
from research import qre_basket_next_action_queue as queue


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def test_build_basket_evidence_recovery_plan_preserves_blockers_and_actions(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(
        recovery.density,
        "build_basket_evidence_density_materialization",
        lambda **_: {
            "rows": [
                {
                    "candidate_id": "cand-a",
                    "symbol": "AAPL",
                    "preset_id": "preset-a",
                    "hypothesis_id": "hyp-a",
                    "behavior_family": "trend_pullback",
                    "region": "US",
                    "asset_class": "equity",
                    "timeframes": ["4h"],
                    "screening_evidence_rows": 1,
                    "screening_evidence_refs": ["research/screening_evidence_latest.v1.json#cand-a"],
                    "oos_evidence_status": "no_oos_evidence",
                    "oos_evidence_refs": ["research/screening_evidence_latest.v1.json#cand-a"],
                    "source_quality_rows": 1,
                    "source_quality_refs": ["logs/qre_data_source_quality_readiness/latest.json"],
                    "cache_coverage_rows": 1,
                    "cache_coverage_refs": ["logs/qre_data_cache_manifest/latest.json"],
                    "candidate_lineage_rows": 1,
                    "candidate_lineage_refs": ["logs/qre_discovery_basket_grid_evidence_materialization/latest.json"],
                    "campaign_lineage_rows": 0,
                    "campaign_lineage_refs": [],
                    "source_identity_status": "provider_symbol_verified",
                    "source_identity_blocker": "",
                },
                {
                    "candidate_id": "cand-b",
                    "symbol": "ASMI",
                    "preset_id": "preset-b",
                    "hypothesis_id": "hyp-b",
                    "behavior_family": "trend_pullback",
                    "region": "NL/EU",
                    "asset_class": "equity",
                    "timeframes": ["1d"],
                    "screening_evidence_rows": 0,
                    "screening_evidence_refs": [],
                    "oos_evidence_status": "oos_evidence_missing",
                    "oos_evidence_refs": [],
                    "source_quality_rows": 0,
                    "source_quality_refs": [],
                    "cache_coverage_rows": 0,
                    "cache_coverage_refs": [],
                    "candidate_lineage_rows": 0,
                    "candidate_lineage_refs": [],
                    "campaign_lineage_rows": 0,
                    "campaign_lineage_refs": [],
                    "source_identity_status": "candidate_alias_only",
                    "source_identity_blocker": "source_identity_blocked",
                },
            ],
            "summary": {
                "basket_count": 2,
                "screening_evidence_present_count": 1,
                "oos_evidence_known_count": 1,
                "candidate_lineage_visible_count": 1,
                "campaign_lineage_visible_count": 0,
                "source_identity_blocked_count": 1,
            },
        },
    )
    monkeypatch.setattr(
        recovery.lineage_diag,
        "build_basket_lineage_recovery_diagnostics",
        lambda **_: {
            "rows": [
                {
                    "candidate_id": "cand-a",
                    "symbol": "AAPL",
                    "preset_id": "preset-a",
                    "candidate_lineage_proof_status": "candidate_proven_campaign_missing",
                    "campaign_lineage_proof_status": "gap",
                    "lineage_recovery_reason": "candidate_lineage_proven_campaign_lineage_missing",
                    "proof_source_refs": {"density": ["logs/qre_basket_evidence_density_materialization/latest.json#cand-a"]},
                },
                {
                    "candidate_id": "cand-b",
                    "symbol": "ASMI",
                    "preset_id": "preset-b",
                    "candidate_lineage_proof_status": "lineage_gap",
                    "campaign_lineage_proof_status": "gap",
                    "lineage_recovery_reason": "lineage_is_not_proven_by_current_local_artifacts",
                    "proof_source_refs": {"density": ["logs/qre_basket_evidence_density_materialization/latest.json#cand-b"]},
                },
            ],
        },
    )
    monkeypatch.setattr(
        recovery.coverage,
        "build_real_basket_evidence_coverage",
        lambda **_: {
            "rows": [
                {
                    "candidate_id": "cand-a",
                    "symbol": "AAPL",
                    "preset_id": "preset-a",
                    "hypothesis_id": "hyp-a",
                    "behavior_family": "trend_pullback",
                    "region": "US",
                    "asset_class": "equity",
                    "timeframes": ["4h"],
                    "evidence_completeness_status": "partial",
                    "evidence_completeness_score_pct": 50,
                    "exact_blockers": ["screening_evidence_missing", "no_oos_evidence"],
                    "reason_record_ids": ["rr-a"],
                    "reason_record_evidence_refs": ["logs/qre_reason_records/latest.json#rr-a"],
                    "failure_action": {"recommended_action": "collect_more_evidence"},
                },
                {
                    "candidate_id": "cand-b",
                    "symbol": "ASMI",
                    "preset_id": "preset-b",
                    "hypothesis_id": "hyp-b",
                    "behavior_family": "trend_pullback",
                    "region": "NL/EU",
                    "asset_class": "equity",
                    "timeframes": ["1d"],
                    "evidence_completeness_status": "missing",
                    "evidence_completeness_score_pct": 0,
                    "exact_blockers": ["source_identity_blocked", "campaign_lineage_missing"],
                    "reason_record_ids": ["rr-b"],
                    "reason_record_evidence_refs": ["logs/qre_reason_records/latest.json#rr-b"],
                    "failure_action": {"recommended_action": "require_identity_resolution"},
                },
            ],
            "summary": {"evidence_complete_count": 0},
        },
    )
    monkeypatch.setattr(
        recovery.closure,
        "build_evidence_complete_basket_closure",
        lambda **_: {
            "summary": {"evidence_complete_count": 0},
            "rows": [
                {
                    "candidate_id": "cand-a",
                    "symbol": "AAPL",
                    "preset_id": "preset-a",
                    "hypothesis_id": "hyp-a",
                    "behavior_family": "trend_pullback",
                    "region": "US",
                    "asset_class": "equity",
                    "timeframes": ["4h"],
                    "closure_status": "blocked_not_evidence_complete",
                    "evidence_completeness_status": "partial",
                    "evidence_completeness_score_pct": 50,
                    "exact_blockers": ["screening_evidence_missing", "no_oos_evidence"],
                    "unknown_blockers": [],
                    "reason_record_count": 1,
                    "reason_record_ids": ["rr-a"],
                    "reason_record_families": ["basket_diagnosis"],
                    "reason_record_evidence_refs": ["logs/qre_reason_records/latest.json#rr-a"],
                    "failure_action": {"recommended_action": "collect_more_evidence"},
                },
                {
                    "candidate_id": "cand-b",
                    "symbol": "ASMI",
                    "preset_id": "preset-b",
                    "hypothesis_id": "hyp-b",
                    "behavior_family": "trend_pullback",
                    "region": "NL/EU",
                    "asset_class": "equity",
                    "timeframes": ["1d"],
                    "closure_status": "blocked_not_evidence_complete",
                    "evidence_completeness_status": "missing",
                    "evidence_completeness_score_pct": 0,
                    "exact_blockers": ["source_identity_blocked", "campaign_lineage_missing"],
                    "unknown_blockers": [],
                    "reason_record_count": 1,
                    "reason_record_ids": ["rr-b"],
                    "reason_record_families": ["basket_diagnosis"],
                    "reason_record_evidence_refs": ["logs/qre_reason_records/latest.json#rr-b"],
                    "failure_action": {"recommended_action": "require_identity_resolution"},
                },
            ],
        },
    )
    monkeypatch.setattr(
        recovery.identity_diag,
        "build_source_identity_diagnostics",
        lambda **_: {
            "rows": [
                {
                    "instrument_symbol": "ASMI",
                    "candidate_aliases": ["ASM.AS", "ASMI.AS"],
                    "source_identity_status": "candidate_alias_only",
                    "next_action": "require_alias_verification",
                }
            ]
        },
    )

    report = recovery.build_basket_evidence_recovery_plan(repo_root=tmp_path, max_candidates=2)

    assert report["report_kind"] == "qre_basket_evidence_recovery_plan"
    assert report["summary"]["basket_count"] == 2
    assert report["summary"]["blocker_row_count"] == 4
    assert report["summary"]["reducible_blocker_count"] == 1
    assert report["summary"]["irreducible_blocker_count"] == 3
    assert report["summary"]["lineage_diagnostic_row_count"] == 2
    rows = {row["symbol"]: row for row in report["rows"]}
    aapl = rows["AAPL"]
    assert aapl["blocker_count"] == 2
    assert aapl["exact_next_actions"] == ["collect_screening_evidence", "collect_oos_evidence"]
    assert aapl["reducible_blocker_count"] == 1
    assert aapl["lineage_diagnostic"]["candidate_lineage_proof_status"] == "candidate_proven_campaign_missing"
    asmi = rows["ASMI"]
    assert asmi["blockers"][0]["exact_next_action"] == "require_identity_resolution"
    assert asmi["blockers"][0]["blocked_by_identity"] is True
    assert asmi["blockers"][1]["exact_next_action"] == "materialize_lineage_from_existing_artifacts"
    assert "research/production_discovery_catalog.py" in asmi["blockers"][0]["potential_clear_refs"]
    assert report["summary"]["exact_next_action_counts"]["require_identity_resolution"] == 1


def test_build_basket_next_action_queue_flattens_blockers_deterministically(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(
        queue.recovery_plan,
        "build_basket_evidence_recovery_plan",
        lambda **_: {
            "blocker_rows": [
                {
                    "candidate_id": "cand-a",
                    "symbol": "AAPL",
                    "region": "US",
                    "asset_class": "equity",
                    "preset_id": "preset-a",
                    "hypothesis_id": "hyp-a",
                    "blocker_code": "screening_evidence_missing",
                    "blocker_family": "screening",
                    "current_status": "partial",
                    "exact_next_action": "collect_screening_evidence",
                    "required_artifact": "research/screening_evidence_latest.v1.json",
                    "safe_action_type": "report_only",
                    "blocked_by_identity": False,
                    "blocked_by_source_cache": False,
                    "blocked_by_lineage": False,
                    "blocked_by_screening": True,
                    "blocked_by_oos": False,
                    "potential_clear_refs": ["research/screening_evidence_latest.v1.json"],
                    "reason_record_refs": {"record_ids": ["rr-a"]},
                    "operator_explanation": "AAPL remains blocked by screening_evidence_missing; the bounded next action is collect_screening_evidence.",
                },
                {
                    "candidate_id": "cand-b",
                    "symbol": "ASMI",
                    "region": "NL/EU",
                    "asset_class": "equity",
                    "preset_id": "preset-b",
                    "hypothesis_id": "hyp-b",
                    "blocker_code": "source_identity_blocked",
                    "blocker_family": "identity",
                    "current_status": "missing",
                    "exact_next_action": "require_identity_resolution",
                    "required_artifact": "research/production_discovery_catalog.py",
                    "safe_action_type": "report_only",
                    "blocked_by_identity": True,
                    "blocked_by_source_cache": False,
                    "blocked_by_lineage": False,
                    "blocked_by_screening": False,
                    "blocked_by_oos": False,
                    "potential_clear_refs": ["research/production_discovery_catalog.py"],
                    "reason_record_refs": {"record_ids": ["rr-b"]},
                    "operator_explanation": "ASMI remains blocked by source_identity_blocked; the bounded next action is require_identity_resolution.",
                },
            ],
            "rows": [
                {"candidate_id": "cand-a", "symbol": "AAPL", "preset_id": "preset-a", "evidence_completeness_score_pct": 86},
                {"candidate_id": "cand-b", "symbol": "ASMI", "preset_id": "preset-b", "evidence_completeness_score_pct": 0},
            ],
            "summary": {"evidence_complete_count": 0},
        },
    )
    monkeypatch.setattr(
        queue.lineage_diag,
        "build_basket_lineage_recovery_diagnostics",
        lambda **_: {
            "rows": [
                {
                    "candidate_id": "cand-a",
                    "symbol": "AAPL",
                    "candidate_lineage_proof_status": "candidate_proven_campaign_missing",
                    "campaign_lineage_proof_status": "gap",
                },
                {
                    "candidate_id": "cand-b",
                    "symbol": "ASMI",
                    "candidate_lineage_proof_status": "lineage_gap",
                    "campaign_lineage_proof_status": "gap",
                },
            ]
        },
    )

    report = queue.build_basket_next_action_queue(repo_root=tmp_path, max_candidates=2)

    assert report["report_kind"] == "qre_basket_next_action_queue"
    assert report["summary"]["row_count"] == 2
    assert report["summary"]["exact_next_action_counts"] == {
        "collect_screening_evidence": 1,
        "require_identity_resolution": 1,
    }
    assert report["summary"]["top_candidate_symbols"] == ["AAPL"]
    rows = {row["symbol"]: row for row in report["rows"]}
    assert rows["AAPL"]["allowed_to_auto_run"] is False
    assert rows["ASMI"]["blocked_by_identity"] is True
    assert rows["ASMI"]["required_artifact"] == "research/production_discovery_catalog.py"
    assert rows["AAPL"]["priority_bucket"] == "screening_second"
    assert rows["ASMI"]["priority_bucket"] == "identity_first"
    assert rows["AAPL"]["is_top_candidate"] is True
    assert rows["AAPL"]["requires_operator_review"] is True


def test_build_basket_next_action_queue_prioritizes_lineage_first_targets(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        queue.recovery_plan,
        "build_basket_evidence_recovery_plan",
        lambda **_: {
            "blocker_rows": [
                {
                    "candidate_id": "cand-a",
                    "symbol": "AAPL",
                    "region": "US",
                    "asset_class": "equity",
                    "preset_id": "preset-a",
                    "hypothesis_id": "hyp-a",
                    "blocker_code": "campaign_lineage_missing",
                    "blocker_family": "lineage",
                    "current_status": "partial",
                    "exact_next_action": "materialize_lineage_from_existing_artifacts",
                    "required_artifact": "logs/qre_discovery_basket_grid_evidence_materialization/latest.json",
                    "safe_action_type": "report_only",
                    "blocked_by_identity": False,
                    "blocked_by_source_cache": False,
                    "blocked_by_lineage": True,
                    "blocked_by_screening": False,
                    "blocked_by_oos": False,
                    "potential_clear_refs": ["logs/qre_discovery_basket_grid_evidence_materialization/latest.json"],
                    "reason_record_refs": {"record_ids": ["rr-a"]},
                    "operator_explanation": "AAPL remains blocked by campaign_lineage_missing; the bounded next action is materialize_lineage_from_existing_artifacts.",
                },
                {
                    "candidate_id": "cand-n",
                    "symbol": "NVDA",
                    "region": "US",
                    "asset_class": "equity",
                    "preset_id": "preset-n",
                    "hypothesis_id": "hyp-n",
                    "blocker_code": "no_oos_evidence",
                    "blocker_family": "oos",
                    "current_status": "partial",
                    "exact_next_action": "collect_oos_evidence",
                    "required_artifact": "research/screening_evidence_latest.v1.json",
                    "safe_action_type": "report_only",
                    "blocked_by_identity": False,
                    "blocked_by_source_cache": False,
                    "blocked_by_lineage": True,
                    "blocked_by_screening": False,
                    "blocked_by_oos": True,
                    "potential_clear_refs": ["research/screening_evidence_latest.v1.json"],
                    "reason_record_refs": {"record_ids": ["rr-n"]},
                    "operator_explanation": "NVDA remains blocked by no_oos_evidence; the bounded next action is collect_oos_evidence.",
                },
            ],
            "rows": [
                {
                    "candidate_id": "cand-a",
                    "symbol": "AAPL",
                    "preset_id": "preset-a",
                    "evidence_completeness_score_pct": 86,
                },
                {
                    "candidate_id": "cand-n",
                    "symbol": "NVDA",
                    "preset_id": "preset-n",
                    "evidence_completeness_score_pct": 86,
                },
            ],
            "summary": {"evidence_complete_count": 0},
        },
    )
    monkeypatch.setattr(
        queue.lineage_diag,
        "build_basket_lineage_recovery_diagnostics",
        lambda **_: {
            "rows": [
                {
                    "candidate_id": "cand-a",
                    "symbol": "AAPL",
                    "candidate_lineage_proof_status": "candidate_proven_campaign_missing",
                    "campaign_lineage_proof_status": "gap",
                },
                {
                    "candidate_id": "cand-n",
                    "symbol": "NVDA",
                    "candidate_lineage_proof_status": "candidate_proven_campaign_missing",
                    "campaign_lineage_proof_status": "gap",
                },
            ]
        },
    )

    report = queue.build_basket_next_action_queue(repo_root=tmp_path, max_candidates=2)

    assert report["summary"]["top_candidate_symbols"] == ["AAPL", "NVDA"]
    assert report["rows"][0]["priority_bucket"] == "lineage_first"
    assert report["rows"][1]["priority_bucket"] == "lineage_first"
    assert report["rows"][0]["recommended_batch"] == "batch_lineage_oos"
    assert report["rows"][0]["allowed_command_template"] == "python -m research.qre_basket_lineage_recovery_diagnostics --write"


def test_write_outputs_use_only_allowlisted_log_paths(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(
        recovery.density,
        "build_basket_evidence_density_materialization",
        lambda **_: {"rows": [], "summary": {"basket_count": 0}},
    )
    monkeypatch.setattr(
        recovery.coverage,
        "build_real_basket_evidence_coverage",
        lambda **_: {"rows": [], "summary": {"evidence_complete_count": 0}},
    )
    monkeypatch.setattr(
        recovery.closure,
        "build_evidence_complete_basket_closure",
        lambda **_: {"rows": [], "summary": {"evidence_complete_count": 0}},
    )
    monkeypatch.setattr(
        recovery.identity_diag,
        "build_source_identity_diagnostics",
        lambda **_: {"rows": []},
    )
    monkeypatch.setattr(
        recovery.lineage_diag,
        "build_basket_lineage_recovery_diagnostics",
        lambda **_: {"rows": []},
    )

    report = recovery.build_basket_evidence_recovery_plan(repo_root=tmp_path, max_candidates=1)
    paths = recovery.write_outputs(report, repo_root=tmp_path)

    assert paths["latest"] == "logs/qre_basket_evidence_recovery_plan/latest.json"
    assert paths["operator_summary"] == "logs/qre_basket_evidence_recovery_plan/operator_summary.md"
    assert (tmp_path / paths["latest"]).is_file()
    assert (tmp_path / paths["operator_summary"]).is_file()
