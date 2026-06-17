from __future__ import annotations

import json
from pathlib import Path

from research import qre_first_batch_evidence_recovery_readiness as readiness
from research import qre_trusted_loop_review_packet as packet_module


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _seed_repo_files(tmp_path: Path) -> None:
    _write_json(
        tmp_path / "research" / "campaign_registry_latest.v1.json",
        {
            "symbols": ["AAPL", "NVDA", "TSM"],
            "campaigns": [{"symbol": "AAPL"}, {"symbol": "NVDA"}, {"symbol": "TSM"}],
        },
    )
    _write_json(tmp_path / "research" / "research_latest.json", {"report_kind": "seed"})
    (tmp_path / "research" / "strategy_matrix.csv").write_text("seed\n", encoding="utf-8")
    _write_json(
        tmp_path / "research" / "history" / "20260605T093946819907Z" / "run_candidates.v1.json",
        {"rows": [{"asset": "AAPL"}, {"asset": "NVDA"}, {"asset": "TSM"}]},
    )


def _stub_reports(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(
        readiness.density,
        "build_basket_evidence_density_materialization",
        lambda **_: {
            "rows": [
                {
                    "candidate_id": "seed::trend_pullback_continuation_daily_v1::AAPL",
                    "symbol": "AAPL",
                    "preset_id": "trend_pullback_continuation_daily_v1",
                    "screening_evidence_rows": 1,
                    "screening_evidence_refs": ["research/screening_evidence_latest.v1.json#aapl"],
                    "oos_evidence_status": "no_oos_evidence",
                    "oos_evidence_refs": ["research/screening_evidence_latest.v1.json#aapl"],
                    "source_quality_rows": 476,
                    "source_quality_refs": ["logs/qre_data_source_quality_readiness/latest.json"],
                    "cache_coverage_rows": 1,
                    "cache_coverage_refs": ["logs/qre_data_cache_manifest/latest.json"],
                    "candidate_lineage_rows": 1,
                    "candidate_lineage_refs": ["logs/qre_discovery_basket_grid_evidence_materialization/latest.json#AAPL|trend_pullback_continuation_daily_v1"],
                    "campaign_lineage_rows": 0,
                    "campaign_lineage_refs": [],
                    "source_identity_status": "provider_symbol_verified",
                },
                {
                    "candidate_id": "seed::trend_pullback_continuation_daily_v1::NVDA",
                    "symbol": "NVDA",
                    "preset_id": "trend_pullback_continuation_daily_v1",
                    "screening_evidence_rows": 1,
                    "screening_evidence_refs": ["research/screening_evidence_latest.v1.json#nvda"],
                    "oos_evidence_status": "no_oos_evidence",
                    "oos_evidence_refs": ["research/screening_evidence_latest.v1.json#nvda"],
                    "source_quality_rows": 485,
                    "source_quality_refs": ["logs/qre_data_source_quality_readiness/latest.json"],
                    "cache_coverage_rows": 1,
                    "cache_coverage_refs": ["logs/qre_data_cache_manifest/latest.json"],
                    "candidate_lineage_rows": 1,
                    "candidate_lineage_refs": ["logs/qre_discovery_basket_grid_evidence_materialization/latest.json#NVDA|trend_pullback_continuation_daily_v1"],
                    "campaign_lineage_rows": 0,
                    "campaign_lineage_refs": [],
                    "source_identity_status": "provider_symbol_verified",
                },
                {
                    "candidate_id": "seed::vol_compression_breakout_daily_v1::TSM",
                    "symbol": "TSM",
                    "preset_id": "vol_compression_breakout_daily_v1",
                    "screening_evidence_rows": 1,
                    "screening_evidence_refs": ["research/screening_evidence_latest.v1.json#tsm"],
                    "oos_evidence_status": "no_oos_evidence",
                    "oos_evidence_refs": ["research/screening_evidence_latest.v1.json#tsm"],
                    "source_quality_rows": 0,
                    "source_quality_refs": [],
                    "cache_coverage_rows": 0,
                    "cache_coverage_refs": [],
                    "candidate_lineage_rows": 1,
                    "candidate_lineage_refs": ["logs/qre_discovery_basket_grid_evidence_materialization/latest.json#TSM|vol_compression_breakout_daily_v1"],
                    "campaign_lineage_rows": 0,
                    "campaign_lineage_refs": [],
                    "source_identity_status": "provider_symbol_verified",
                },
                {
                    "candidate_id": "seed::relative_strength_vs_region_daily_v1::AMD",
                    "symbol": "AMD",
                    "preset_id": "relative_strength_vs_region_daily_v1",
                    "screening_evidence_rows": 1,
                    "screening_evidence_refs": ["research/screening_evidence_latest.v1.json#amd"],
                    "oos_evidence_status": "oos_evidence_unknown",
                    "oos_evidence_refs": ["research/screening_evidence_latest.v1.json#amd"],
                    "source_quality_rows": 454,
                    "source_quality_refs": ["logs/qre_data_source_quality_readiness/latest.json"],
                    "cache_coverage_rows": 1,
                    "cache_coverage_refs": ["logs/qre_data_cache_manifest/latest.json"],
                    "candidate_lineage_rows": 0,
                    "candidate_lineage_refs": [],
                    "campaign_lineage_rows": 0,
                    "campaign_lineage_refs": [],
                    "source_identity_status": "provider_symbol_verified",
                },
                {
                    "candidate_id": "seed::trend_continuation_daily_v1::ASML",
                    "symbol": "ASML",
                    "preset_id": "trend_continuation_daily_v1",
                    "screening_evidence_rows": 1,
                    "screening_evidence_refs": ["research/screening_evidence_latest.v1.json#asml"],
                    "oos_evidence_status": "oos_evidence_unknown",
                    "oos_evidence_refs": ["research/screening_evidence_latest.v1.json#asml"],
                    "source_quality_rows": 463,
                    "source_quality_refs": ["logs/qre_data_source_quality_readiness/latest.json"],
                    "cache_coverage_rows": 1,
                    "cache_coverage_refs": ["logs/qre_data_cache_manifest/latest.json"],
                    "candidate_lineage_rows": 0,
                    "candidate_lineage_refs": [],
                    "campaign_lineage_rows": 0,
                    "campaign_lineage_refs": [],
                    "source_identity_status": "provider_symbol_verified",
                },
                {
                    "candidate_id": "seed::relative_strength_vs_region_daily_v1::MSFT",
                    "symbol": "MSFT",
                    "preset_id": "relative_strength_vs_region_daily_v1",
                    "screening_evidence_rows": 1,
                    "screening_evidence_refs": ["research/screening_evidence_latest.v1.json#msft"],
                    "oos_evidence_status": "oos_evidence_unknown",
                    "oos_evidence_refs": ["research/screening_evidence_latest.v1.json#msft"],
                    "source_quality_rows": 465,
                    "source_quality_refs": ["logs/qre_data_source_quality_readiness/latest.json"],
                    "cache_coverage_rows": 1,
                    "cache_coverage_refs": ["logs/qre_data_cache_manifest/latest.json"],
                    "candidate_lineage_rows": 0,
                    "candidate_lineage_refs": [],
                    "campaign_lineage_rows": 0,
                    "campaign_lineage_refs": [],
                    "source_identity_status": "provider_symbol_verified",
                },
                {
                    "candidate_id": "seed::relative_strength_vs_sector_daily_v1::ASMI",
                    "symbol": "ASMI",
                    "preset_id": "relative_strength_vs_sector_daily_v1",
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
                },
            ],
        },
    )
    monkeypatch.setattr(
        readiness.grid_materialization,
        "build_discovery_basket_grid_evidence_materialization",
        lambda **_: {
            "grid_runs_scanned_count": 0,
            "grid_rows_scanned_count": 0,
            "baskets_with_matched_grid_rows": 0,
            "baskets_with_sufficient_oos_in_grid": 0,
            "rows": [
                {
                    "asset": "AAPL",
                    "preset": "trend_pullback_continuation_daily_v1",
                    "basket_id": "seed::trend_pullback_continuation_daily_v1::AAPL",
                    "exact_blocker_category": "no_grid_run_found",
                    "matched_grid_rows_count": 0,
                    "join_key_status": "no_grid_run_found",
                    "evidence_exists_in_grid": False,
                    "controlled_grid_run_id": "",
                },
                {
                    "asset": "NVDA",
                    "preset": "trend_pullback_continuation_daily_v1",
                    "basket_id": "seed::trend_pullback_continuation_daily_v1::NVDA",
                    "exact_blocker_category": "no_grid_run_found",
                    "matched_grid_rows_count": 0,
                    "join_key_status": "no_grid_run_found",
                    "evidence_exists_in_grid": False,
                    "controlled_grid_run_id": "",
                },
                {
                    "asset": "TSM",
                    "preset": "vol_compression_breakout_daily_v1",
                    "basket_id": "seed::vol_compression_breakout_daily_v1::TSM",
                    "exact_blocker_category": "no_grid_run_found",
                    "matched_grid_rows_count": 0,
                    "join_key_status": "no_grid_run_found",
                    "evidence_exists_in_grid": False,
                    "controlled_grid_run_id": "",
                },
            ],
        },
    )
    monkeypatch.setattr(
        readiness.lineage_bridge,
        "build_grid_candidate_campaign_lineage_bridge",
        lambda **_: {
            "rows": [
                {
                    "asset": "AAPL",
                    "preset": "trend_pullback_continuation_daily_v1",
                    "lineage_bridge_status": "blocked_no_grid_match",
                    "matched_grid_rows_count": 0,
                },
                {
                    "asset": "NVDA",
                    "preset": "trend_pullback_continuation_daily_v1",
                    "lineage_bridge_status": "blocked_no_grid_match",
                    "matched_grid_rows_count": 0,
                },
                {
                    "asset": "TSM",
                    "preset": "vol_compression_breakout_daily_v1",
                    "lineage_bridge_status": "blocked_no_grid_match",
                    "matched_grid_rows_count": 0,
                },
            ]
        },
    )
    monkeypatch.setattr(
        readiness.lineage_diag,
        "build_basket_lineage_recovery_diagnostics",
        lambda **_: {
            "summary": {
                "candidate_lineage_proven_count": 3,
                "campaign_lineage_proven_count": 0,
            },
            "rows": [
                {
                    "candidate_id": "seed::trend_pullback_continuation_daily_v1::AAPL",
                    "symbol": "AAPL",
                    "candidate_lineage_proof_status": "candidate_proven_campaign_missing",
                    "campaign_lineage_proof_status": "gap",
                },
                {
                    "candidate_id": "seed::trend_pullback_continuation_daily_v1::NVDA",
                    "symbol": "NVDA",
                    "candidate_lineage_proof_status": "candidate_proven_campaign_missing",
                    "campaign_lineage_proof_status": "gap",
                },
                {
                    "candidate_id": "seed::vol_compression_breakout_daily_v1::TSM",
                    "symbol": "TSM",
                    "candidate_lineage_proof_status": "candidate_proven_campaign_missing",
                    "campaign_lineage_proof_status": "gap",
                },
                {
                    "candidate_id": "seed::relative_strength_vs_region_daily_v1::AMD",
                    "symbol": "AMD",
                    "candidate_lineage_proof_status": "lineage_gap",
                    "campaign_lineage_proof_status": "gap",
                },
                {
                    "candidate_id": "seed::trend_continuation_daily_v1::ASML",
                    "symbol": "ASML",
                    "candidate_lineage_proof_status": "lineage_gap",
                    "campaign_lineage_proof_status": "gap",
                },
                {
                    "candidate_id": "seed::relative_strength_vs_region_daily_v1::MSFT",
                    "symbol": "MSFT",
                    "candidate_lineage_proof_status": "lineage_gap",
                    "campaign_lineage_proof_status": "gap",
                },
                {
                    "candidate_id": "seed::relative_strength_vs_sector_daily_v1::ASMI",
                    "symbol": "ASMI",
                    "candidate_lineage_proof_status": "lineage_gap",
                    "campaign_lineage_proof_status": "gap",
                },
            ],
        },
    )
    monkeypatch.setattr(
        readiness.closure,
        "build_evidence_complete_basket_closure",
        lambda **_: {
            "summary": {
                "evidence_complete_count": 0,
                "unknown_blocker_count": 0,
            },
            "rows": [
                {
                    "candidate_id": "seed::trend_pullback_continuation_daily_v1::AAPL",
                    "symbol": "AAPL",
                    "preset_id": "trend_pullback_continuation_daily_v1",
                    "evidence_completeness_score_pct": 71,
                    "exact_blockers": ["no_oos_evidence", "campaign_lineage_missing"],
                },
                {
                    "candidate_id": "seed::trend_pullback_continuation_daily_v1::NVDA",
                    "symbol": "NVDA",
                    "preset_id": "trend_pullback_continuation_daily_v1",
                    "evidence_completeness_score_pct": 71,
                    "exact_blockers": ["no_oos_evidence", "campaign_lineage_missing"],
                },
                {
                    "candidate_id": "seed::vol_compression_breakout_daily_v1::TSM",
                    "symbol": "TSM",
                    "preset_id": "vol_compression_breakout_daily_v1",
                    "evidence_completeness_score_pct": 43,
                    "exact_blockers": ["no_oos_evidence", "campaign_lineage_missing", "source_quality_rows_missing"],
                },
                {
                    "candidate_id": "seed::relative_strength_vs_region_daily_v1::AMD",
                    "symbol": "AMD",
                    "preset_id": "relative_strength_vs_region_daily_v1",
                    "evidence_completeness_score_pct": 57,
                    "exact_blockers": ["oos_evidence_unknown", "campaign_lineage_missing"],
                },
                {
                    "candidate_id": "seed::trend_continuation_daily_v1::ASML",
                    "symbol": "ASML",
                    "preset_id": "trend_continuation_daily_v1",
                    "evidence_completeness_score_pct": 57,
                    "exact_blockers": ["oos_evidence_unknown", "campaign_lineage_missing"],
                },
                {
                    "candidate_id": "seed::relative_strength_vs_region_daily_v1::MSFT",
                    "symbol": "MSFT",
                    "preset_id": "relative_strength_vs_region_daily_v1",
                    "evidence_completeness_score_pct": 57,
                    "exact_blockers": ["oos_evidence_unknown", "campaign_lineage_missing"],
                },
                {
                    "candidate_id": "seed::relative_strength_vs_sector_daily_v1::ASMI",
                    "symbol": "ASMI",
                    "preset_id": "relative_strength_vs_sector_daily_v1",
                    "evidence_completeness_score_pct": 0,
                    "exact_blockers": ["source_identity_blocked", "campaign_lineage_missing"],
                },
            ],
        },
    )
    monkeypatch.setattr(
        readiness.coverage,
        "build_real_basket_evidence_coverage",
        lambda **_: {
            "rows": [
                {
                    "candidate_id": "seed::trend_pullback_continuation_daily_v1::AAPL",
                    "symbol": "AAPL",
                    "evidence_completeness_score_pct": 71,
                    "evidence_presence": {"source_quality_ready": True, "cache_ready": True},
                },
                {
                    "candidate_id": "seed::trend_pullback_continuation_daily_v1::NVDA",
                    "symbol": "NVDA",
                    "evidence_completeness_score_pct": 71,
                    "evidence_presence": {"source_quality_ready": True, "cache_ready": True},
                },
                {
                    "candidate_id": "seed::vol_compression_breakout_daily_v1::TSM",
                    "symbol": "TSM",
                    "evidence_completeness_score_pct": 43,
                    "evidence_presence": {"source_quality_ready": False, "cache_ready": False},
                },
                {
                    "candidate_id": "seed::relative_strength_vs_region_daily_v1::AMD",
                    "symbol": "AMD",
                    "evidence_completeness_score_pct": 57,
                    "evidence_presence": {"source_quality_ready": True, "cache_ready": True},
                },
                {
                    "candidate_id": "seed::trend_continuation_daily_v1::ASML",
                    "symbol": "ASML",
                    "evidence_completeness_score_pct": 57,
                    "evidence_presence": {"source_quality_ready": True, "cache_ready": True},
                },
                {
                    "candidate_id": "seed::relative_strength_vs_region_daily_v1::MSFT",
                    "symbol": "MSFT",
                    "evidence_completeness_score_pct": 57,
                    "evidence_presence": {"source_quality_ready": True, "cache_ready": True},
                },
                {
                    "candidate_id": "seed::relative_strength_vs_sector_daily_v1::ASMI",
                    "symbol": "ASMI",
                    "evidence_completeness_score_pct": 0,
                    "evidence_presence": {"source_quality_ready": False, "cache_ready": False},
                },
            ],
        },
    )
    monkeypatch.setattr(
        readiness.recovery_plan,
        "build_basket_evidence_recovery_plan",
        lambda **_: {
            "rows": [
                {"candidate_id": "seed::trend_pullback_continuation_daily_v1::AAPL", "blockers": []},
                {"candidate_id": "seed::trend_pullback_continuation_daily_v1::NVDA", "blockers": []},
                {"candidate_id": "seed::vol_compression_breakout_daily_v1::TSM", "blockers": []},
                {"candidate_id": "seed::relative_strength_vs_region_daily_v1::AMD", "blockers": []},
                {"candidate_id": "seed::trend_continuation_daily_v1::ASML", "blockers": []},
                {"candidate_id": "seed::relative_strength_vs_region_daily_v1::MSFT", "blockers": []},
                {"candidate_id": "seed::relative_strength_vs_sector_daily_v1::ASMI", "blockers": []},
            ],
        },
    )


def test_first_batch_readiness_report_is_deterministic_and_fail_closed(tmp_path: Path, monkeypatch) -> None:
    _seed_repo_files(tmp_path)
    _stub_reports(monkeypatch, tmp_path)

    first = readiness.build_first_batch_evidence_recovery_readiness(repo_root=tmp_path, max_candidates=15)
    second = readiness.build_first_batch_evidence_recovery_readiness(repo_root=tmp_path, max_candidates=15)

    assert first == second
    assert first["first_batch_summary"]["first_batch"] == ["AAPL", "NVDA"]
    assert first["first_batch_summary"]["second_line_lineage"] == ["TSM"]
    assert first["first_batch_summary"]["identity_gated"] == ["ASMI"]
    assert first["first_batch_summary"]["evidence_complete_count"] == 0
    assert first["grid_artifact_recovery_readiness"]["grid_runs_scanned"] == 0
    assert first["grid_artifact_recovery_readiness"]["top_blocker"] == "no_grid_run_found"
    assert first["campaign_lineage_readiness"]["campaign_lineage_proven_count"] == 0
    assert first["authority_boundary"]["not_campaign_launcher"] is True
    assert first["safety_invariants"]["does_not_change_evidence_complete_count"] is True

    rows = {row["symbol"]: row for row in first["candidate_preconditions"]}
    assert rows["AAPL"]["campaign_lineage_status"] == "gap"
    assert rows["AAPL"]["oos_evidence_status"] == "verified_absent"
    assert rows["AAPL"]["oos_evidence_truly_absent"] is True
    assert rows["AAPL"]["screening_evidence_exists"] is True
    assert rows["AAPL"]["source_quality_status"] == "sufficient"
    assert rows["AAPL"]["cache_coverage_status"] == "sufficient"
    assert rows["AAPL"]["grid_artifact_status"] == "no_local_grid_run_found_archive_hint_present"
    assert rows["AAPL"]["candidate_lineage_proven_campaign_missing"] is True
    assert rows["AAPL"]["auto_run_allowed"] is False
    assert rows["NVDA"]["auto_run_allowed"] is False
    assert rows["ASMI"]["batch_classification"] == "identity_gated"
    assert rows["AMD"]["batch_classification"] == "second_line_oos_classification"

    for row in first["candidate_preconditions"]:
        assert row["stop_conditions"]
        assert row["authority_boundary"]["read_only_report_only"] is True


def test_command_safety_classifier_blocks_mutating_or_unproven_actions() -> None:
    safe = readiness.classify_command_safety("python -m research.qre_first_batch_evidence_recovery_readiness --write")
    unsafe = readiness.classify_command_safety("campaign_launcher")
    bounded = readiness.classify_command_safety("controlled_grid_artifact_generation")

    assert safe["classification"] == "safe_read_only"
    assert unsafe["safe_command_available"] is False
    assert unsafe["operator_approval_required"] is True
    assert bounded["candidate_recovery_action"] == "operator_approve_bounded_controlled_grid_artifact_generation"
    assert bounded["auto_run_allowed"] is False
    assert bounded["reason"] == "controlled_grid_artifact_generation_not_proven_read_only"


def test_trusted_loop_does_not_improve_trust_level_merely_because_readiness_exists(tmp_path: Path, monkeypatch) -> None:
    _seed_repo_files(tmp_path)
    monkeypatch.setattr(
        packet_module.trusted_readiness,
        "collect_snapshot",
        lambda **_: {
            "readiness_state": "working_capability",
            "operator_report_available": True,
            "contradiction_visibility": {"status": "visible"},
            "source_lineage": {"status": "complete"},
            "repeatability_status": "no_repeatability_evidence",
        },
    )
    monkeypatch.setattr(packet_module.reason_records, "build_reason_records_snapshot", lambda **_: {"meta": {"record_count": 0}})
    monkeypatch.setattr(packet_module.failure_action, "build_failure_action_from_basket", lambda **_: {"summary": {"actionable_count": 0}})
    monkeypatch.setattr(packet_module.basket_closure, "build_evidence_complete_basket_closure", lambda **_: {"summary": {"evidence_complete_count": 0}})
    monkeypatch.setattr(packet_module.routing_calibration, "build_routing_calibration_report", lambda **_: {"summary": {"final_recommendation": "routing_calibration_scaffold_ready"}})
    monkeypatch.setattr(packet_module.sampling_calibration, "build_sampling_calibration_report", lambda **_: {"summary": {"final_recommendation": "sampling_calibration_scaffold_ready"}})
    monkeypatch.setattr(packet_module.research_memory, "build_research_memory_current_artifacts", lambda **_: {"summary": {"final_recommendation": "research_memory_current_artifacts_partial"}})
    monkeypatch.setattr(packet_module.basket_action_plan, "build_basket_operator_action_plan", lambda **_: {"summary": {"final_recommendation": "basket_operator_action_plan_ready", "first_batch_candidate_symbols": ["AAPL", "NVDA"]}})
    monkeypatch.setattr(
        packet_module.first_batch_readiness,
        "build_first_batch_evidence_recovery_readiness",
        lambda **_: {"report_kind": "qre_first_batch_evidence_recovery_readiness"},
    )

    packet = packet_module.build_trusted_loop_review_packet(repo_root=tmp_path)

    assert packet["summary"]["first_batch_readiness_available"] is True
    assert packet["summary"]["trust_level"] == "1"
    assert packet["summary"]["trust_verdict"] == "read_only_context_fail_closed"


def test_readiness_write_outputs_stays_allowlisted(tmp_path: Path, monkeypatch) -> None:
    _seed_repo_files(tmp_path)
    _stub_reports(monkeypatch, tmp_path)

    report = readiness.build_first_batch_evidence_recovery_readiness(repo_root=tmp_path, max_candidates=15)
    paths = readiness.write_outputs(report, repo_root=tmp_path)

    assert paths["latest"] == "logs/qre_first_batch_evidence_recovery_readiness/latest.json"
    assert paths["operator_summary"] == "logs/qre_first_batch_evidence_recovery_readiness/operator_summary.md"
    assert (tmp_path / paths["latest"]).is_file()
    assert (tmp_path / paths["operator_summary"]).is_file()
