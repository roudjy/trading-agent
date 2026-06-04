from __future__ import annotations

import json

import reporting.qre_selection_route_materialization as materialization
import reporting.qre_selection_route_validation_flow as flow


def test_selection_route_validation_flow_is_ready() -> None:
    snapshot = flow.collect_snapshot(generated_at_utc="2026-06-03T15:00:00Z")

    assert snapshot["report_kind"] == "qre_selection_route_validation_flow"
    assert snapshot["safe_to_execute"] is False
    assert snapshot["read_only"] is True
    assert snapshot["eligible_for_direct_execution"] is False
    assert snapshot["counts"]["materialized_route_ready"] == 3
    assert snapshot["counts"]["hypothesis_ready"] == 3
    assert snapshot["counts"]["request_ready_for_operator_review"] == 3
    assert snapshot["counts"]["dry_run_ready"] == 3
    assert snapshot["counts"]["selection_validation_flow_ready"] == 3
    assert (
        snapshot["final_recommendation"]
        == "selection_route_validation_flow_ready_for_operator_review"
    )


def test_flow_preserves_child_summary_counts() -> None:
    snapshot = flow.collect_snapshot(generated_at_utc="2026-06-03T15:00:00Z")

    assert snapshot["materialization"]["counts"]["materialized_route_ready"] == 3
    assert snapshot["readiness"]["counts"]["hypothesis_ready"] == 3
    assert snapshot["validation_request"]["counts"]["ready"] == 3
    assert snapshot["dry_run"]["counts"]["ready"] == 3
    assert snapshot["dry_run"]["executed_anything"] is False


def test_flow_fails_closed_when_materialization_has_no_ready_rows() -> None:
    materialization_snapshot = materialization.collect_snapshot(
        selection_snapshot={
            "report_kind": "qre_executable_hypothesis_selection",
            "counts": {"selected": 0, "blocked": 1, "total": 1},
            "selection_rows": [
                {
                    "selection_id": "blocked-row",
                    "selection_status": "selection_preset_bundle_empty",
                }
            ],
        },
        generated_at_utc="2026-06-03T15:00:00Z",
    )

    snapshot = flow.collect_snapshot(
        materialization_snapshot=materialization_snapshot,
        generated_at_utc="2026-06-03T15:00:00Z",
    )

    assert snapshot["counts"]["materialized_route_ready"] == 0
    assert snapshot["counts"]["hypothesis_ready"] == 0
    assert snapshot["counts"]["request_ready_for_operator_review"] == 0
    assert snapshot["counts"]["dry_run_ready"] == 0
    assert snapshot["counts"]["selection_validation_flow_ready"] == 0
    assert snapshot["final_recommendation"] == "selection_route_validation_flow_blocked"


def test_flow_uses_temp_files_without_mutating_legacy_artifacts(tmp_path, monkeypatch) -> None:
    artifact_path = tmp_path / "flow.json"
    monkeypatch.setattr(flow, "ARTIFACT_LATEST", artifact_path)

    rc = flow.main(
        [
            "--frozen-utc",
            "2026-06-03T15:00:00Z",
            "--indent",
            "2",
        ]
    )

    assert rc == 0
    assert artifact_path.exists()
    payload = json.loads(artifact_path.read_text(encoding="utf-8"))
    assert payload["report_kind"] == "qre_selection_route_validation_flow"
    assert payload["safe_to_execute"] is False
    assert payload["counts"]["selection_validation_flow_ready"] == 3


def test_no_write_cli_does_not_write_artifact(tmp_path, monkeypatch) -> None:
    artifact_path = tmp_path / "flow.json"
    monkeypatch.setattr(flow, "ARTIFACT_LATEST", artifact_path)

    rc = flow.main(
        [
            "--no-write",
            "--frozen-utc",
            "2026-06-03T15:00:00Z",
            "--indent",
            "2",
        ]
    )

    assert rc == 0
    assert not artifact_path.exists()


def test_selection_route_validation_flow_includes_bounded_request_and_dry_run_examples() -> None:
    snapshot = flow.collect_snapshot(generated_at_utc="2026-06-03T15:00:00Z")

    request_examples = snapshot["validation_request"]["examples"]
    dry_run_examples = snapshot["dry_run"]["examples"]

    assert len(request_examples) == 3
    assert len(dry_run_examples) == 3

    for example in request_examples:
        assert example["request_id"]
        assert example["request_status"] == "request_ready_for_operator_review"
        assert example["qre_hypothesis_id"].startswith("qre-hyp-sel-")
        assert example["executable_hypothesis_id"]
        assert example["preset_name"]
        assert example["asset"] == "BTC-EUR"
        assert example["timeframe"] in {"1h", "4h"}
        assert example["allowed_command_preview"]
        assert example["requires_operator_approval"] is True
        assert example["safe_to_execute"] is False

    for example in dry_run_examples:
        assert example["request_id"]
        assert example["dry_run_status"] == "dry_run_ready"
        assert example["qre_hypothesis_id"].startswith("qre-hyp-sel-")
        assert example["asset"] == "BTC-EUR"
        assert example["timeframe"] in {"1h", "4h"}
        assert example["would_run_command_preview"]
        assert example["would_write_artifacts"] == [
            "research/run_candidates_latest.v1.json",
            "research/screening_evidence_latest.v1.json",
            "research/history/<run_id>/...",
        ]
        assert example["backup_required"] is True
        assert example["executed"] is False
        assert example["safe_to_execute"] is False
