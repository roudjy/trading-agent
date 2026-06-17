from __future__ import annotations

import json
from pathlib import Path

from research import qre_first_batch_evidence_recovery_cascade as cascade


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _seed_repo(tmp_path: Path) -> None:
    _write_json(
        tmp_path / "logs" / "qre_controlled_validation_execution" / "controlled_eval_latest.v1.json",
        {
            "stdout_tail": "validation progress AAPL 4h NVDA 4h TSM 4h validated_count=6 results_written=6",
        },
    )
    _write_json(
        tmp_path / "research" / "history" / "20260604T170735770553Z" / "run_candidates.v1.json",
        {
            "run_id": "20260604T170735770553Z",
            "summary": {"validated_count": 6},
            "candidates": [
                {
                    "candidate_id": "cand-aapl",
                    "current_status": "validated",
                    "asset": "AAPL",
                    "interval": "4h",
                    "strategy_name": "trend_pullback_v1",
                    "validation": {"evidence_status": "no_oos_trades"},
                },
                {
                    "candidate_id": "cand-nvda",
                    "current_status": "validated",
                    "asset": "NVDA",
                    "interval": "4h",
                    "strategy_name": "trend_pullback_v1",
                    "validation": {"evidence_status": "no_oos_trades"},
                },
            ],
        },
    )
    _write_json(
        tmp_path / "research" / "history" / "20260604T170735770553Z" / "run_campaign_manifest.v1.json",
        {
            "campaign_id": "campaign-20260604T170735770553Z",
            "run_id": "20260604T170735770553Z",
            "col_campaign_id": "col-20260604T190732878212Z-trend_pullback_equities_4h-74e2345880",
            "batches": [{"batch_id": "batch-trend_pullback-4h-104ec37e"}],
        },
    )
    _write_json(
        tmp_path / "research" / "campaign_registry_latest.v1.json",
        {
            "campaigns": {
                "col-20260605T122346491432Z-trend_pullback_equities_4h-b68c030d9c": {
                    "campaign_id": "col-20260605T122346491432Z-trend_pullback_equities_4h-b68c030d9c",
                    "universe": ["AAPL", "NVDA", "TSM"],
                }
            }
        },
    )
    _write_json(
        tmp_path / "logs" / "qre_trusted_loop_review" / "latest.json",
        {"summary": {"trust_verdict": "read_only_context_fail_closed", "trust_level": "1"}},
    )
    _write_json(
        tmp_path / ".tmp" / "qre_grid_smoke_complete" / "combination_results.v1.jsonl",
        [
            {
                "run_id": "qre_grid_smoke_complete",
                "instrument_symbol": "ADYEN",
                "behavior_preset_id": "trend_continuation_daily_v1",
            }
        ],
    )
    _write_json(
        tmp_path / "tests" / "fixtures" / "qre_controlled_validation" / "equities_exploratory_v1_blocker_diagnosis.json",
        {"rows": [{"asset": "AAPL", "interval": "4h", "strategy_name": "trend_pullback_v1"}]},
    )
    _write_json(tmp_path / "research" / "research_latest.json", {"report_kind": "seed"})
    (tmp_path / "research" / "strategy_matrix.csv").write_text("seed\n", encoding="utf-8")


def _stub_upstream(monkeypatch) -> None:
    monkeypatch.setattr(
        cascade.readiness,
        "build_first_batch_evidence_recovery_readiness",
        lambda **_: {"report_kind": "qre_first_batch_evidence_recovery_readiness", "first_batch_summary": {"first_batch": ["AAPL", "NVDA"]}},
    )
    monkeypatch.setattr(
        cascade.closure,
        "build_evidence_complete_basket_closure",
        lambda **_: {
            "summary": {"evidence_complete_count": 0, "unknown_blocker_count": 0},
            "rows": [
                {"symbol": "AAPL", "exact_blockers": ["campaign_lineage_missing", "no_oos_evidence"]},
                {"symbol": "NVDA", "exact_blockers": ["campaign_lineage_missing", "no_oos_evidence"]},
            ],
        },
    )


def test_phase_one_artifact_classification_is_deterministic_and_fail_closed(tmp_path: Path, monkeypatch) -> None:
    _seed_repo(tmp_path)
    _stub_upstream(monkeypatch)

    first = cascade.build_first_batch_evidence_recovery_cascade(repo_root=tmp_path)
    second = cascade.build_first_batch_evidence_recovery_cascade(repo_root=tmp_path)

    assert first == second
    assert first["first_batch_summary"]["first_batch"] == ["AAPL", "NVDA"]
    assert first["first_batch_summary"]["evidence_complete_count"] == 0
    assert first["first_batch_summary"]["trusted_loop_verdict"] == "read_only_context_fail_closed"
    assert first["first_batch_summary"]["current_top_blocker"] == "preset_timeframe_alias_unproven"
    assert first["overall_result"] == "PRESET_TIMEFRAME_ALIAS_BLOCKED"
    assert first["safety_invariants"]["does_not_change_evidence_complete_count"] is True

    rows = {row["relative_path"]: row for row in first["artifact_discovery"]["rows"]}
    assert rows[".tmp/qre_grid_smoke_complete/combination_results.v1.jsonl"]["classification_status"] == "smoke_temp_not_authoritative"
    assert rows["tests/fixtures/qre_controlled_validation/equities_exploratory_v1_blocker_diagnosis.json"]["classification_status"] == "test_fixture_not_authoritative"
    assert rows["research/campaign_registry_latest.v1.json"]["classification_status"] == "registry_snapshot_not_lineage_proof"
    assert rows["logs/qre_controlled_validation_execution/controlled_eval_latest.v1.json"]["classification_status"] == "legacy_validation_stdout_only"
    assert rows["research/history/20260604T170735770553Z/run_candidates.v1.json"]["classification_status"] == "missing_required_identity_fields"
    assert rows["research/history/20260604T170735770553Z/run_campaign_manifest.v1.json"]["classification_status"] == "legacy_validation_evidence_candidate"

    locator = first["validation_result_locator"]["rows"]
    assert len(locator) == 1
    assert locator[0]["expected_result_count"] == 6
    assert locator[0]["found_result_count"] == 2
    assert locator[0]["missing_result_count"] == 4
    assert locator[0]["can_use_as_oos_evidence"] is False
    assert locator[0]["can_use_as_campaign_lineage"] is False
    assert locator[0]["result_schema_status"] == "structured_validation_results_found"

    compatibility = {row["symbol"]: row for row in first["legacy_compatibility"]["rows"]}
    assert compatibility["AAPL"]["preset_alias_outcome"] == "alias_allowed_for_context_only"
    assert compatibility["AAPL"]["timeframe_alias_outcome"] == "alias_blocked_timeframe_mismatch"
    assert compatibility["AAPL"]["campaign_lineage_eligible"] is False
    assert compatibility["NVDA"]["target_preset_id"] == "trend_pullback_continuation_daily_v1"


def test_generated_reports_are_not_treated_as_source_artifacts(tmp_path: Path, monkeypatch) -> None:
    _seed_repo(tmp_path)
    _stub_upstream(monkeypatch)
    _write_json(
        tmp_path / "logs" / "qre_discovery_basket_grid_evidence_materialization" / "latest.json",
        {"report_kind": "qre_discovery_basket_grid_evidence_materialization", "rows": [{"asset": "AAPL"}]},
    )

    report = cascade.build_first_batch_evidence_recovery_cascade(repo_root=tmp_path)
    rows = {row["relative_path"]: row for row in report["artifact_discovery"]["rows"]}

    assert rows["logs/qre_discovery_basket_grid_evidence_materialization/latest.json"]["classification_status"] == "generated_report_not_source_artifact"


def test_results_written_without_structured_outputs_stays_fail_closed(tmp_path: Path, monkeypatch) -> None:
    _seed_repo(tmp_path)
    _stub_upstream(monkeypatch)
    (tmp_path / "research" / "history").rename(tmp_path / "research" / "history_hidden")

    report = cascade.build_first_batch_evidence_recovery_cascade(repo_root=tmp_path)

    locator = report["validation_result_locator"]["rows"]
    assert len(locator) == 1
    assert locator[0]["expected_result_count"] == 6
    assert locator[0]["found_result_count"] == 0
    assert locator[0]["result_schema_status"] == "structured_validation_results_missing"
    assert report["first_batch_summary"]["current_top_blocker"] == "legacy_results_missing"


def test_write_outputs_stays_allowlisted(tmp_path: Path, monkeypatch) -> None:
    _seed_repo(tmp_path)
    _stub_upstream(monkeypatch)

    report = cascade.build_first_batch_evidence_recovery_cascade(repo_root=tmp_path)
    paths = cascade.write_outputs(report, repo_root=tmp_path)

    assert paths["latest"] == "logs/qre_first_batch_evidence_recovery_cascade/latest.json"
    assert paths["operator_summary"] == "logs/qre_first_batch_evidence_recovery_cascade/operator_summary.md"
    assert (tmp_path / paths["latest"]).is_file()
    assert (tmp_path / paths["operator_summary"]).is_file()
