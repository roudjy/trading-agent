from __future__ import annotations

import json
from pathlib import Path

from research import qre_bounded_generation_artifact_acceptance_verifier as verifier
from research import qre_controlled_validation_adapter as adapter
from research import qre_controlled_validation_adapter_result_materialization as materializer
from research import qre_evidence_complete_basket_closure as closure


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _request_payload() -> dict[str, object]:
    return {
        "request_id": "req-verifier-001",
        "symbols": ["AAPL", "NVDA"],
        "preset_id": "trend_pullback_continuation_daily_v1",
        "timeframe": "daily_v1",
        "approval_ref": "approval-001",
        "required_artifact_types": [
            "generation_manifest",
            "structured_lineage_artifact",
            "structured_oos_artifact",
        ],
        "allowed_output_paths": ["logs/qre_controlled_validation_adapter_results/"],
        "forbidden_capabilities": [],
        "created_at_utc": "2026-06-18T00:00:00Z",
        "source": "operator_approval_manifest",
    }


def _structured_source(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "source_type": "structured_controlled_validation",
        "source_authority": "structured_source",
        "source_ref": "artifacts/qre_controlled_validation/source-001.json",
        "lineage_records": [
            {
                "candidate_id": "cand-001",
                "campaign_id": "camp-001",
                "generation_run_id": "gen-001",
                "validation_status": "accepted",
                "reason_record_refs": ["rr-lineage-001"],
            }
        ],
        "oos_records": [
            {
                "candidate_id": "cand-001",
                "oos_window": {"start": "2025-01-01", "end": "2025-06-30"},
                "oos_metric_fields": {"oos_trade_count": 24, "oos_return_pct": 3.1},
                "cost_slippage_assumption_refs": ["cost-model-001"],
                "validation_status": "accepted",
                "reason_record_refs": ["rr-oos-001"],
            }
        ],
    }
    payload.update(overrides)
    return payload


def _accepted_materialized_payload() -> dict[str, object]:
    return materializer.build_controlled_validation_adapter_result_materialization(
        adapter.build_controlled_validation_adapter_result(
            _request_payload(),
            controlled_validation_source=_structured_source(),
        )
    )


def test_verifier_rejects_context_only_and_stdout_only_artifacts(tmp_path: Path) -> None:
    _write_json(
        tmp_path / "logs" / "legacy_context.json",
        {"preset_id": "trend_pullback_v1", "timeframe": "4h", "stdout_tail": "legacy"},
    )
    _write_json(
        tmp_path / "logs" / "current_candidate.json",
        {"symbol": "AAPL", "preset_id": "trend_pullback_continuation_daily_v1", "timeframe": "daily_v1"},
    )

    report = verifier.build_bounded_generation_artifact_acceptance_verifier(repo_root=tmp_path)
    rows = {row["relative_path"]: row for row in report["rows"]}

    assert rows["logs/legacy_context.json"]["classification"] == "rejected_stdout_only"
    assert rows["logs/current_candidate.json"]["classification"] == "rejected_missing_identity"


def test_accepts_valid_structured_lineage_artifact_from_materialized_adapter_record(tmp_path: Path) -> None:
    _write_json(
        tmp_path / "logs" / "qre_controlled_validation_adapter_results" / "latest.json",
        _accepted_materialized_payload(),
    )

    report = verifier.build_bounded_generation_artifact_acceptance_verifier(repo_root=tmp_path)
    row = report["rows"][0]

    assert row["classification"] == "accepted_for_campaign_lineage"
    assert row["accepted_for_campaign_lineage"] is True
    assert row["accepted_lineage_count"] == 1
    assert row["accepted_lineage_records"][0]["candidate_id"] == "cand-001"
    assert report["summary"]["accepted_lineage_candidate_count"] == 1


def test_accepts_valid_structured_oos_artifact_from_materialized_adapter_record(tmp_path: Path) -> None:
    _write_json(
        tmp_path / "logs" / "qre_controlled_validation_adapter_results" / "latest.json",
        _accepted_materialized_payload(),
    )

    report = verifier.build_bounded_generation_artifact_acceptance_verifier(repo_root=tmp_path)
    row = report["rows"][0]

    assert row["accepted_for_oos_evidence"] is True
    assert row["accepted_oos_count"] == 1
    assert row["accepted_oos_records"][0]["cost_slippage_assumption_refs"] == ["cost-model-001"]
    assert report["summary"]["accepted_oos_candidate_count"] == 1


def test_rejects_lineage_with_missing_candidate_campaign_or_generation_id(tmp_path: Path) -> None:
    payload = _accepted_materialized_payload()
    payload["lineage_candidates"][0]["candidate_id"] = ""
    payload["lineage_candidates"][0]["campaign_id"] = ""
    payload["lineage_candidates"][0]["generation_id"] = ""
    _write_json(tmp_path / "logs" / "qre_controlled_validation_adapter_results" / "latest.json", payload)

    report = verifier.build_bounded_generation_artifact_acceptance_verifier(repo_root=tmp_path)
    row = report["rows"][0]

    assert row["classification"] == "accepted_for_oos_evidence_only"
    assert row["accepted_for_campaign_lineage"] is False
    assert row["accepted_lineage_count"] == 0
    assert row["accepted_for_oos_evidence"] is True
    assert "missing_candidate_id" in row["lineage_rejection_reasons"]
    assert "missing_campaign_or_generation_id" in row["lineage_rejection_reasons"]


def test_rejects_oos_with_missing_window_metrics_and_cost_refs(tmp_path: Path) -> None:
    payload = _accepted_materialized_payload()
    payload["oos_candidates"][0]["oos_window"] = {}
    payload["oos_candidates"][0]["oos_metric_fields"] = {}
    payload["oos_candidates"][0]["cost_slippage_assumption_refs"] = []
    _write_json(tmp_path / "logs" / "qre_controlled_validation_adapter_results" / "latest.json", payload)

    report = verifier.build_bounded_generation_artifact_acceptance_verifier(repo_root=tmp_path)
    row = report["rows"][0]

    assert row["classification"] == "accepted_for_campaign_lineage_only"
    assert row["accepted_for_campaign_lineage"] is True
    assert row["accepted_for_oos_evidence"] is False
    assert row["accepted_oos_count"] == 0
    assert "missing_oos_window" in row["oos_rejection_reasons"]
    assert "missing_oos_metrics" in row["oos_rejection_reasons"]
    assert "missing_cost_slippage_refs" in row["oos_rejection_reasons"]


def test_rejects_context_only_stdout_legacy_provisional_and_fixture_materialized_records(tmp_path: Path) -> None:
    accepted = _accepted_materialized_payload()
    accepted["lineage_candidates"][0]["source_ref"] = "tests/fixtures/qre_controlled_validation/source-001.json"

    provisional = materializer.build_controlled_validation_adapter_result_materialization(
        adapter.build_controlled_validation_adapter_result(
            _request_payload(),
            controlled_validation_source=_structured_source(
                lineage_records=[{"candidate_id": "", "campaign_id": "", "generation_run_id": ""}]
            ),
        )
    )
    rejected = materializer.build_controlled_validation_adapter_result_materialization(
        adapter.build_controlled_validation_adapter_result(
            _request_payload(),
            controlled_validation_source={"source_type": "context_only", "source_ref": "report"},
        )
    )
    _write_json(tmp_path / "logs" / "qre_controlled_validation_adapter_results" / "accepted_fixture.json", accepted)
    _write_json(tmp_path / "logs" / "qre_controlled_validation_adapter_results" / "provisional.json", provisional)
    _write_json(tmp_path / "logs" / "qre_controlled_validation_adapter_results" / "rejected.json", rejected)

    report = verifier.build_bounded_generation_artifact_acceptance_verifier(repo_root=tmp_path)
    rows = {row["relative_path"]: row for row in report["rows"]}

    assert rows["logs/qre_controlled_validation_adapter_results/accepted_fixture.json"]["classification"] == (
        "accepted_for_oos_evidence_only"
    )
    assert "fixture_only_source_ref" in rows[
        "logs/qre_controlled_validation_adapter_results/accepted_fixture.json"
    ]["lineage_rejection_reasons"]
    assert rows["logs/qre_controlled_validation_adapter_results/provisional.json"]["classification"] == (
        "rejected_materialized_provisional_only"
    )
    assert rows["logs/qre_controlled_validation_adapter_results/rejected.json"]["classification"] == (
        "rejected_materialized_rejected_source"
    )


def test_accepted_counts_are_deterministic(tmp_path: Path) -> None:
    _write_json(
        tmp_path / "logs" / "qre_controlled_validation_adapter_results" / "latest.json",
        _accepted_materialized_payload(),
    )

    first = verifier.build_bounded_generation_artifact_acceptance_verifier(repo_root=tmp_path)
    second = verifier.build_bounded_generation_artifact_acceptance_verifier(repo_root=tmp_path)

    assert first == second
    assert first["summary"]["accepted_lineage_candidate_count"] == 1
    assert first["summary"]["accepted_oos_candidate_count"] == 1


def test_accepted_counts_do_not_clear_closure_without_closure_integration(tmp_path: Path, monkeypatch) -> None:
    _write_json(
        tmp_path / "logs" / "qre_controlled_validation_adapter_results" / "latest.json",
        _accepted_materialized_payload(),
    )
    monkeypatch.setattr(
        closure,
        "_guarded_alias_bounded_generation_snapshot",
        lambda *_: {"overall_result": "ALIAS_POLICY_CONTEXT_ONLY_BOUNDED_GENERATION_READY"},
    )

    report = closure.build_evidence_complete_basket_closure(repo_root=tmp_path)
    assert report["summary"]["evidence_complete_count"] == 0


def test_verifier_never_invents_fields() -> None:
    payload = _accepted_materialized_payload()

    assert payload["lineage_candidates"][0]["candidate_id"] == "cand-001"
    assert payload["lineage_candidates"][0]["campaign_id"] == "camp-001"
    assert payload["oos_candidates"][0]["oos_metric_fields"] == {
        "oos_return_pct": 3.1,
        "oos_trade_count": 24,
    }


def test_core_verifier_logic_has_no_aapl_or_nvda_hardcoding_in_materialized_acceptance_path() -> None:
    source = Path("research/qre_bounded_generation_artifact_acceptance_verifier.py").read_text(
        encoding="utf-8"
    )
    assert "fixture_only_source_ref" in source
    assert "AAPL" not in source.split("if report_kind == adapter_materialization.REPORT_KIND:")[1]
    assert "NVDA" not in source.split("if report_kind == adapter_materialization.REPORT_KIND:")[1]
