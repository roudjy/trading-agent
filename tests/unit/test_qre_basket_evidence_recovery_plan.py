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
    rows = {row["symbol"]: row for row in report["rows"]}
    aapl = rows["AAPL"]
    assert aapl["blocker_count"] == 2
    assert aapl["exact_next_actions"] == ["collect_screening_evidence", "collect_oos_evidence"]
    assert aapl["reducible_blocker_count"] == 1
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
                {"symbol": "AAPL", "preset_id": "preset-a"},
                {"symbol": "ASMI", "preset_id": "preset-b"},
            ],
            "summary": {"evidence_complete_count": 0},
        },
    )

    report = queue.build_basket_next_action_queue(repo_root=tmp_path, max_candidates=2)

    assert report["report_kind"] == "qre_basket_next_action_queue"
    assert report["summary"]["row_count"] == 2
    assert report["summary"]["exact_next_action_counts"] == {
        "collect_screening_evidence": 1,
        "require_identity_resolution": 1,
    }
    rows = {row["symbol"]: row for row in report["rows"]}
    assert rows["AAPL"]["allowed_to_auto_run"] is False
    assert rows["ASMI"]["blocked_by_identity"] is True
    assert rows["ASMI"]["required_artifact"] == "research/production_discovery_catalog.py"


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

    report = recovery.build_basket_evidence_recovery_plan(repo_root=tmp_path, max_candidates=1)
    paths = recovery.write_outputs(report, repo_root=tmp_path)

    assert paths["latest"] == "logs/qre_basket_evidence_recovery_plan/latest.json"
    assert paths["operator_summary"] == "logs/qre_basket_evidence_recovery_plan/operator_summary.md"
    assert (tmp_path / paths["latest"]).is_file()
    assert (tmp_path / paths["operator_summary"]).is_file()
