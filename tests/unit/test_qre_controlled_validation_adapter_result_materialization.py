from __future__ import annotations

import json
from pathlib import Path

from research import qre_controlled_validation_adapter as adapter
from research import qre_controlled_validation_adapter_result_materialization as materializer
from research import qre_bounded_generation_artifact_acceptance_verifier as verifier
from research import qre_evidence_complete_basket_closure as closure


def _request_payload() -> dict[str, object]:
    return {
        "request_id": "req-materialize-001",
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
        "created_at_utc": "2026-06-17T16:10:00Z",
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


def _write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def test_materializer_rejects_invalid_runner_payload() -> None:
    report = materializer.build_controlled_validation_adapter_result_materialization(
        {"report_kind": "qre_bounded_current_basket_generation_runner"}
    )

    assert report["materialization_status"] == "blocked_invalid_runner_payload"
    assert report["authority"]["non_authoritative"] is True
    assert report["authority"]["can_clear_blockers"] is False


def test_materializer_rejects_invalid_adapter_payload() -> None:
    report = materializer.build_controlled_validation_adapter_result_materialization(
        {"report_kind": adapter.REPORT_KIND, "adapter_status": "accepted_structured_evidence"}
    )

    assert report["materialization_status"] == "blocked_invalid_adapter_payload"


def test_no_safe_source_materializes_but_remains_non_authoritative() -> None:
    adapter_result = adapter.build_controlled_validation_adapter_result(
        _request_payload(),
        controlled_validation_source=None,
    )
    report = materializer.build_controlled_validation_adapter_result_materialization(adapter_result)

    assert report["materialization_status"] == "materialized_no_safe_source"
    assert report["authority"]["non_authoritative"] is True
    assert report["authority"]["can_clear_blockers"] is False


def test_provisional_adapter_state_materializes_but_cannot_clear_blockers() -> None:
    adapter_result = adapter.build_controlled_validation_adapter_result(
        _request_payload(),
        controlled_validation_source=_structured_source(
            lineage_records=[{"candidate_id": "", "campaign_id": "", "generation_run_id": ""}]
        ),
    )
    report = materializer.build_controlled_validation_adapter_result_materialization(adapter_result)

    assert report["materialization_status"] == "materialized_provisional_only"
    assert report["accepted_lineage_count"] == 0
    assert report["authority"]["can_clear_blockers"] is False


def test_rejected_source_materializes_with_reason_codes() -> None:
    adapter_result = adapter.build_controlled_validation_adapter_result(
        _request_payload(),
        controlled_validation_source={"source_type": "context_only", "source_ref": "report"},
    )
    report = materializer.build_controlled_validation_adapter_result_materialization(adapter_result)

    assert report["materialization_status"] == "materialized_rejected_source"
    assert report["rejected_reasons"] == ["context_only_source_rejected"]


def test_accepted_structured_evidence_materializes_only_when_required_fields_exist() -> None:
    adapter_result = adapter.build_controlled_validation_adapter_result(
        _request_payload(),
        controlled_validation_source=_structured_source(),
    )
    report = materializer.build_controlled_validation_adapter_result_materialization(adapter_result)

    assert report["materialization_status"] == "materialized_accepted_structured_evidence"
    assert report["accepted_lineage_count"] == 1
    assert report["accepted_oos_count"] == 1
    assert report["lineage_candidates"]
    assert report["oos_candidates"]
    assert report["authority"]["non_authoritative"] is True
    assert report["authority"]["can_authorize_execution"] is False
    assert report["authority"]["can_promote_candidate"] is False


def test_materialized_hash_is_deterministic() -> None:
    adapter_result = adapter.build_controlled_validation_adapter_result(
        _request_payload(),
        controlled_validation_source=_structured_source(),
    )
    first = materializer.build_controlled_validation_adapter_result_materialization(adapter_result)
    second = materializer.build_controlled_validation_adapter_result_materialization(adapter_result)

    assert first == second
    assert first["hash"] == materializer.compute_materialization_hash(first)


def test_materializer_does_not_invent_candidate_ids() -> None:
    report = materializer.build_controlled_validation_adapter_result_materialization(
        adapter.build_controlled_validation_adapter_result(
            _request_payload(),
            controlled_validation_source=_structured_source(),
        )
    )

    assert report["lineage_candidates"][0]["candidate_id"] == "cand-001"
    assert report["oos_candidates"][0]["candidate_id"] == "cand-001"


def test_core_materializer_logic_has_no_aapl_or_nvda_hardcoding() -> None:
    source = Path("research/qre_controlled_validation_adapter_result_materialization.py").read_text(
        encoding="utf-8"
    )
    assert "AAPL" not in source
    assert "NVDA" not in source


def test_verifier_can_read_materialized_records(tmp_path: Path) -> None:
    report = materializer.build_controlled_validation_adapter_result_materialization(
        adapter.build_controlled_validation_adapter_result(
            _request_payload(),
            controlled_validation_source=_structured_source(),
        )
    )
    _write_json(tmp_path / "logs" / "qre_controlled_validation_adapter_results" / "latest.json", report)

    verifier_report = verifier.build_bounded_generation_artifact_acceptance_verifier(repo_root=tmp_path)
    rows = {row["relative_path"]: row for row in verifier_report["rows"]}

    assert rows["logs/qre_controlled_validation_adapter_results/latest.json"]["classification"] == "accepted_for_campaign_lineage"
    assert rows["logs/qre_controlled_validation_adapter_results/latest.json"]["accepted_for_oos_evidence"] is True


def test_verifier_does_not_accept_provisional_or_no_safe_materialized_records(tmp_path: Path) -> None:
    provisional = materializer.build_controlled_validation_adapter_result_materialization(
        adapter.build_controlled_validation_adapter_result(
            _request_payload(),
            controlled_validation_source=_structured_source(
                lineage_records=[{"candidate_id": "", "campaign_id": "", "generation_run_id": ""}]
            ),
        )
    )
    no_safe = materializer.build_controlled_validation_adapter_result_materialization(
        adapter.build_controlled_validation_adapter_result(_request_payload())
    )
    _write_json(tmp_path / "logs" / "qre_controlled_validation_adapter_results" / "provisional.json", provisional)
    _write_json(tmp_path / "logs" / "qre_controlled_validation_adapter_results" / "no_safe.json", no_safe)

    verifier_report = verifier.build_bounded_generation_artifact_acceptance_verifier(repo_root=tmp_path)
    rows = {row["relative_path"]: row for row in verifier_report["rows"]}

    assert rows["logs/qre_controlled_validation_adapter_results/provisional.json"]["classification"] == "rejected_materialized_provisional_only"
    assert rows["logs/qre_controlled_validation_adapter_results/no_safe.json"]["classification"] == "rejected_materialized_no_safe_source"


def test_closure_remains_zero_when_only_provisional_or_no_safe_materialized_records_exist(tmp_path: Path, monkeypatch) -> None:
    _write_json(
        tmp_path / "logs" / "qre_controlled_validation_adapter_results" / "latest.json",
        materializer.build_controlled_validation_adapter_result_materialization(
            adapter.build_controlled_validation_adapter_result(
                _request_payload(),
                controlled_validation_source=None,
            )
        ),
    )
    monkeypatch.setattr(
        closure,
        "_guarded_alias_bounded_generation_snapshot",
        lambda *_: {"overall_result": "ALIAS_POLICY_CONTEXT_ONLY_BOUNDED_GENERATION_READY"},
    )
    report = closure.build_evidence_complete_basket_closure(repo_root=tmp_path)

    assert report["summary"]["evidence_complete_count"] == 0
