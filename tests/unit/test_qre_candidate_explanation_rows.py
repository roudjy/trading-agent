from __future__ import annotations

import json
from pathlib import Path

from research import qre_candidate_explanation_rows as candidate_rows
from research import qre_oos_evidence_blockers as oos_blockers


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _seed_complete_aapl_repo(tmp_path: Path) -> None:
    _write_json(
        tmp_path / "logs" / "qre_data_cache_manifest" / "latest.json",
        {"coverage": [{"instrument": "AAPL", "timeframe": "1d", "ready": True}]},
    )
    _write_json(
        tmp_path / "logs" / "qre_data_source_quality_readiness" / "latest.json",
        {"rows": [{"instrument": "AAPL", "timeframe": "1d", "quality_status": "ready"}]},
    )
    _write_json(
        tmp_path / "research" / "screening_evidence_latest.v1.json",
        {
            "candidates": [
                {
                    "asset": "AAPL",
                    "hypothesis_id": "trend_pullback_behavior_v1",
                    "stage_result": "screening_pass",
                    "validation_evidence": {
                        "status": "sufficient_oos_evidence",
                        "oos_trade_count": 12,
                    },
                }
            ]
        },
    )
    _write_json(
        tmp_path / "research" / "campaign_registry_latest.v1.json",
        {
            "campaigns": {
                "cmp-1": {
                    "preset_name": "trend_pullback_continuation_daily_v1",
                    "hypothesis_id": "trend_pullback_behavior_v1",
                    "state": "completed",
                }
            }
        },
    )
    _write_json(
        tmp_path / "research" / "candidate_registry_latest.v1.json",
        {"candidates": [{"asset": "AAPL", "status": "candidate"}]},
    )
    _write_json(
        tmp_path / "research" / "paper_readiness_latest.v1.json",
        {
            "entries": [
                {
                    "candidate_id": "candidate_0001",
                    "asset": "AAPL",
                    "readiness_status": "blocked",
                    "blocking_reasons": ["missing_execution_events"],
                }
            ]
        },
    )
    _write_json(
        tmp_path / "research" / "synthesis_gate_latest.v1.json",
        {
            "synthesis_gate_state": "blocked_insufficient_attribution",
            "allowed": False,
        },
    )


def test_build_candidate_explanation_rows_include_paper_and_synthesis_blockers(
    tmp_path: Path,
) -> None:
    _seed_complete_aapl_repo(tmp_path)

    report = candidate_rows.build_candidate_explanation_rows(
        repo_root=tmp_path,
        max_candidates=2,
    )

    rows = {row["symbol"]: row for row in report["rows"]}
    aapl = rows["AAPL"]
    assert aapl["paper_readiness_status"] == "blocked"
    assert aapl["paper_readiness_blockers"] == ["missing_execution_events"]
    assert aapl["synthesis_gate_state"] == "blocked_insufficient_attribution"
    assert aapl["safe_next_action"] == "eligible_for_readonly_routing"
    assert aapl["reason_record_refs"]["record_ids"]


def test_build_candidate_explanation_rows_fail_closed_when_optional_artifacts_missing(
    tmp_path: Path,
) -> None:
    _seed_complete_aapl_repo(tmp_path)
    (tmp_path / "research" / "paper_readiness_latest.v1.json").unlink()
    (tmp_path / "research" / "synthesis_gate_latest.v1.json").unlink()

    report = candidate_rows.build_candidate_explanation_rows(
        repo_root=tmp_path,
        max_candidates=2,
    )

    rows = {row["symbol"]: row for row in report["rows"]}
    aapl = rows["AAPL"]
    assert aapl["paper_readiness_status"] == "not_available_fail_closed"
    assert aapl["synthesis_gate_state"] == "not_available_fail_closed"


def test_candidate_explanations_surface_grid_bridge_blockers(
    tmp_path: Path,
) -> None:
    _seed_complete_aapl_repo(tmp_path)
    (tmp_path / "research" / "screening_evidence_latest.v1.json").write_text(
        json.dumps({"candidates": []}, indent=2) + "\n",
        encoding="utf-8",
    )
    _write_json(
        tmp_path / "logs" / "qre_discovery_basket_grid_evidence_materialization" / "latest.json",
        {
            "rows": [
                {
                    "basket_id": "seed::trend_pullback_continuation_daily_v1::AAPL",
                    "asset": "AAPL",
                    "provider_symbol": "AAPL",
                    "preset": "trend_pullback_continuation_daily_v1",
                    "matched_grid_rows_count": 1,
                    "matched_grid_rows": [
                        {
                            "run_id": "grid-run-1",
                            "sequence_number": 1,
                            "instrument_symbol": "AAPL",
                            "behavior_preset_id": "trend_pullback_continuation_daily_v1",
                            "status": "completed",
                            "outcome_class": "sufficient_oos_evidence",
                            "criteria_status": "criteria_consistentie_failed",
                        }
                    ],
                    "evidence_exists_in_grid": True,
                    "source_identity_status": "provider_symbol_verified",
                    "source_identity_blocker": "",
                    "metric_consistency_status": "clean_consistent",
                    "preset_executability_classification": "executable",
                    "candidate_lineage_status": "missing",
                    "oos_evidence_status": "sufficient_oos_evidence_present",
                    "sufficient_oos_evidence_status": "present",
                    "join_key_status": "grid_row_match_found",
                    "exact_next_action": "materialize_candidate_lineage",
                }
            ]
        },
    )

    report = candidate_rows.build_candidate_explanation_rows(repo_root=tmp_path, max_candidates=2)

    rows = {row["symbol"]: row for row in report["rows"]}
    aapl = rows["AAPL"]
    assert aapl["grid_readiness_bridge_status"] == "blocked_candidate_lineage_missing"
    assert aapl["primary_blocker"] == "blocked_candidate_lineage_missing"


def test_build_oos_evidence_blockers_classifies_sufficient_and_missing_oos_states(
    tmp_path: Path,
) -> None:
    _seed_complete_aapl_repo(tmp_path)

    report = oos_blockers.build_oos_evidence_blockers(
        repo_root=tmp_path,
        max_candidates=2,
    )

    rows = {row["symbol"]: row for row in report["rows"]}
    assert rows["AAPL"]["oos_blocker_class"] == "oos_evidence_present_readonly_only"
    assert rows["AAPL"]["oos_status"] == "sufficient_oos_evidence"
    assert rows["ASML"]["oos_blocker_class"] == "oos_evidence_missing"


def test_write_outputs_writes_candidate_and_oos_sidecars(tmp_path: Path) -> None:
    _seed_complete_aapl_repo(tmp_path)

    candidate_report = candidate_rows.build_candidate_explanation_rows(
        repo_root=tmp_path,
        max_candidates=2,
    )
    oos_report = oos_blockers.build_oos_evidence_blockers(
        repo_root=tmp_path,
        max_candidates=2,
    )
    candidate_paths = candidate_rows.write_outputs(candidate_report, repo_root=tmp_path)
    oos_paths = oos_blockers.write_outputs(oos_report, repo_root=tmp_path)

    assert candidate_paths["latest"] == "logs/qre_candidate_explanation_rows/latest.json"
    assert oos_paths["latest"] == "logs/qre_oos_evidence_blockers/latest.json"
