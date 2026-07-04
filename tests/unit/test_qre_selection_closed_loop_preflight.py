from __future__ import annotations

import json

import reporting.qre_selection_closed_loop_preflight as preflight


def test_preflight_allows_considering_controlled_regeneration_from_selection_route() -> None:
    snapshot = preflight.collect_snapshot(generated_at_utc="2026-06-03T16:00:00Z")

    assert snapshot["report_kind"] == "qre_selection_closed_loop_preflight"
    assert snapshot["safe_to_execute"] is False
    assert snapshot["read_only"] is True
    assert snapshot["eligible_for_direct_execution"] is False

    assert snapshot["selection_route"]["ready"] is True
    assert snapshot["selection_route"]["counts"]["request_ready_for_operator_review"] == 3
    assert snapshot["selection_route"]["counts"]["dry_run_ready"] == 3

    assert snapshot["legacy_bridge"]["regeneration_linkage_expected"] is True
    assert snapshot["legacy_bridge"]["primary_blocker"] == "no_primary_blocker"

    assert snapshot["controlled_regeneration_preflight"]["can_be_considered"] is False
    assert (
        "selection_route_validation_flow_ready"
        in snapshot["controlled_regeneration_preflight"]["reason_codes"]
    )
    assert (
        snapshot["final_recommendation"] == "selection_route_preflight_blocked"
    )


def test_preflight_blocks_when_selection_flow_not_ready() -> None:
    flow_snapshot = {
        "report_kind": "qre_selection_route_validation_flow",
        "counts": {
            "materialized_route_ready": 0,
            "hypothesis_ready": 0,
            "request_ready_for_operator_review": 0,
            "dry_run_ready": 0,
            "selection_validation_flow_ready": 0,
        },
        "final_recommendation": "selection_route_validation_flow_blocked",
        "validation_warnings": [],
    }
    bridge_snapshot = {
        "report_kind": "qre_executable_hypothesis_identity_bridge_diagnostics",
        "bridge": {
            "regeneration_linkage_expected": False,
            "deterministic_mapping_possible": False,
            "primary_blocker": "executable_hypothesis_id_not_in_qre_authority",
        },
        "final_recommendation": "executable_hypothesis_identity_bridge_required_before_regeneration",
        "validation_warnings": [],
    }

    snapshot = preflight.collect_snapshot(
        flow_snapshot=flow_snapshot,
        bridge_snapshot=bridge_snapshot,
        generated_at_utc="2026-06-03T16:00:00Z",
    )

    assert snapshot["selection_route"]["ready"] is False
    assert snapshot["controlled_regeneration_preflight"]["can_be_considered"] is False
    assert (
        "selection_route_validation_flow_not_ready"
        in snapshot["controlled_regeneration_preflight"]["reason_codes"]
    )
    assert snapshot["final_recommendation"] == "selection_route_preflight_blocked"


def test_preflight_blocks_when_legacy_bridge_already_expects_regeneration() -> None:
    flow_snapshot = {
        "report_kind": "qre_selection_route_validation_flow",
        "counts": {
            "materialized_route_ready": 3,
            "hypothesis_ready": 3,
            "request_ready_for_operator_review": 3,
            "dry_run_ready": 3,
            "selection_validation_flow_ready": 3,
        },
        "final_recommendation": "selection_route_validation_flow_ready_for_operator_review",
        "validation_warnings": [],
    }
    bridge_snapshot = {
        "report_kind": "qre_executable_hypothesis_identity_bridge_diagnostics",
        "bridge": {
            "regeneration_linkage_expected": True,
            "deterministic_mapping_possible": True,
            "primary_blocker": None,
        },
        "final_recommendation": "legacy_bridge_ready",
        "validation_warnings": [],
    }

    snapshot = preflight.collect_snapshot(
        flow_snapshot=flow_snapshot,
        bridge_snapshot=bridge_snapshot,
        generated_at_utc="2026-06-03T16:00:00Z",
    )

    assert snapshot["selection_route"]["ready"] is True
    assert snapshot["legacy_bridge"]["regeneration_linkage_expected"] is True
    assert snapshot["controlled_regeneration_preflight"]["can_be_considered"] is False
    assert snapshot["final_recommendation"] == "selection_route_preflight_blocked"


def test_preflight_cli_write_and_no_write(tmp_path, monkeypatch) -> None:
    artifact_path = tmp_path / "preflight.json"
    monkeypatch.setattr(preflight, "ARTIFACT_LATEST", artifact_path)

    rc = preflight.main(
        [
            "--no-write",
            "--frozen-utc",
            "2026-06-03T16:00:00Z",
            "--indent",
            "2",
        ]
    )
    assert rc == 0
    assert not artifact_path.exists()

    rc = preflight.main(
        [
            "--frozen-utc",
            "2026-06-03T16:00:00Z",
            "--indent",
            "2",
        ]
    )
    assert rc == 0
    assert artifact_path.exists()

    payload = json.loads(artifact_path.read_text(encoding="utf-8"))
    assert payload["report_kind"] == "qre_selection_closed_loop_preflight"
    assert payload["safe_to_execute"] is False
    assert payload["controlled_regeneration_preflight"]["can_be_considered"] is False

def test_equities_preflight_allows_considering_controlled_regeneration() -> None:
    snapshot = preflight.collect_snapshot(
        profile_name="equities_exploratory_v1",
        generated_at_utc="2026-06-03T16:00:00Z",
    )

    assert snapshot["report_kind"] == "qre_selection_closed_loop_preflight"
    assert snapshot["safe_to_execute"] is False
    assert snapshot["read_only"] is True
    assert snapshot["eligible_for_direct_execution"] is False
    assert snapshot["selection_route"]["ready"] is True
    assert snapshot["selection_route"]["counts"]["request_ready_for_operator_review"] == 1
    assert snapshot["selection_route"]["counts"]["dry_run_ready"] == 1
    assert snapshot["controlled_regeneration_preflight"]["can_be_considered"] is False
    assert (
        "selection_route_validation_flow_ready"
        in snapshot["controlled_regeneration_preflight"]["reason_codes"]
    )
    assert (
        snapshot["final_recommendation"] == "selection_route_preflight_blocked"
    )

def test_preflight_reports_next_capability_gaps() -> None:
    snapshot = preflight.collect_snapshot(
        profile_name="equities_exploratory_v1",
        generated_at_utc="2026-06-03T16:00:00Z",
    )

    gaps = snapshot["next_capability_gaps"]

    assert gaps["real_market_data_intake"]["status"] == (
        "not_implemented_in_this_preflight"
    )
    assert gaps["autonomous_hypothesis_generation"]["status"] == (
        "not_implemented_in_this_preflight"
    )
    assert gaps["controlled_validation_execution"]["status"] == "operator_go_required"
    assert gaps["result_analysis"]["status"] == "requires_completed_validation_run"
    assert gaps["learning_update"]["status"] == "requires_completed_validation_run"
    assert gaps["research_action_queue_mutation"]["status"] == (
        "blocked_without_explicit_operator_go"
    )

    assert gaps["real_market_data_intake"]["may_mutate_state"] is False
    assert gaps["autonomous_hypothesis_generation"]["may_mutate_state"] is False
    assert gaps["controlled_validation_execution"]["may_mutate_state"] is True
    assert gaps["result_analysis"]["may_mutate_state"] is False
    assert gaps["learning_update"]["may_mutate_state"] is False
    assert gaps["research_action_queue_mutation"]["may_mutate_state"] is True

