from research.qre_routing_calibration import (
    calibrate_routing_context,
    calibrate_routing_rows,
    routing_calibration_manifest,
)


def test_routing_manifest_is_context_only():
    manifest = routing_calibration_manifest()

    assert manifest["schema_version"] == "1.0"
    assert "sampling_calibration" in manifest["routing_targets"]
    assert "excluded_scope_archive" in manifest["routing_targets"]
    assert manifest["evidence_categories"] == [
        "source",
        "data",
        "readiness",
        "diagnostic",
    ]

    authority = manifest["authority"]
    assert authority["routing_calibration_is_context_only"] is True
    assert authority["evidence_backed_context_only"] is True
    assert authority["not_queue_mutation"] is True
    assert authority["not_candidate_promotion"] is True
    assert authority["not_campaign_mutation"] is True
    assert authority["not_strategy_registration"] is True
    assert authority["not_paper_shadow_live"] is True
    assert authority["not_broker_execution"] is True
    assert authority["does_not_fetch_data"] is True
    assert authority["does_not_mutate_queues"] is True
    assert authority["does_not_mutate_candidates"] is True
    assert authority["does_not_mutate_campaigns"] is True
    assert authority["does_not_mutate_strategies"] is True
    assert authority["does_not_mutate_presets"] is True
    assert authority["does_not_mutate_frozen_contracts"] is True


def test_crypto_legacy_routes_to_archive_only():
    result = calibrate_routing_context(
        {
            "subject_id": "candidate:crypto",
            "ontology_classification": {
                "asset_class": "crypto_legacy",
                "research_scope": "excluded_from_current_research_scope",
            },
        }
    )

    assert result.routing_targets == ("excluded_scope_archive",)
    assert result.routing_decision == "route_to_archive_only"
    assert result.evidence_support_state == "archive_only"


def test_source_data_readiness_and_diagnostic_evidence_raise_priority():
    result = calibrate_routing_context(
        {
            "subject_id": "candidate:evidence",
            "asset_class": "equity",
            "research_scope": "target_equity_research",
            "readiness_state": "blocked",
            "blocker_class": "missing_required_field",
            "title": "OpenFIGI source_manifest cache coverage state transition tail entropy",
            "evidence_presence": {
                "source_quality_ready": True,
                "cache_ready": True,
                "routing_ready": True,
                "diagnostic_ready": True,
            },
            "evidence_refs": [
                "logs/qre_data_source_quality_readiness/latest.json",
                "logs/qre_data_cache_manifest/latest.json",
                "logs/qre_state_transition_diagnostics/latest.json",
                "logs/qre_tail_entropy_hardening/latest.json",
            ],
        }
    )

    assert result.evidence_support_state == "evidence_backed"
    assert set(result.evidence_categories) == {
        "data",
        "diagnostic",
        "readiness",
        "source",
    }
    assert result.evidence_ref_count == 4
    assert "source_quality" in result.routing_targets
    assert "data_readiness" in result.routing_targets
    assert "state_transition_diagnostics" in result.routing_targets
    assert "tail_entropy_hardening" in result.routing_targets
    assert result.routing_decision in {"route_standard", "route_high_priority"}


def test_source_quality_and_identity_route_targets():
    result = calibrate_routing_context(
        {
            "subject_id": "candidate:source",
            "asset_class": "equity",
            "research_scope": "target_source_data_research",
            "title": "OpenFIGI provider source_manifest identity ticker ambiguity",
        }
    )

    assert "sampling_calibration" in result.routing_targets
    assert "source_quality" in result.routing_targets
    assert "identity_resolution" in result.routing_targets
    assert result.routing_decision in {"route_standard", "route_high_priority"}


def test_factor_and_null_model_route_targets():
    result = calibrate_routing_context(
        {
            "subject_id": "candidate:factor",
            "asset_class": "fundamental_equity",
            "research_scope": "target_factor_research",
            "title": "fundamental factor field_coverage null_model baseline",
        }
    )

    assert "factor_coverage" in result.routing_targets
    assert "null_model_baseline" in result.routing_targets


def test_state_and_tail_route_targets():
    result = calibrate_routing_context(
        {
            "subject_id": "candidate:risk",
            "asset_class": "equity",
            "research_scope": "target_equity_research",
            "title": "state transition blocked tail entropy drawdown concentration",
        }
    )

    assert "state_transition_diagnostics" in result.routing_targets
    assert "tail_entropy_hardening" in result.routing_targets


def test_blocked_readiness_routes_to_data_readiness_and_failure_retrieval():
    result = calibrate_routing_context(
        {
            "subject_id": "candidate:blocked",
            "asset_class": "equity",
            "research_scope": "target_equity_research",
            "readiness_state": "blocked",
            "blocker_class": "missing_required_field",
        }
    )

    assert "data_readiness" in result.routing_targets
    assert "failure_retrieval" in result.routing_targets


def test_failure_record_kind_routes_to_failure_retrieval():
    result = calibrate_routing_context(
        {
            "subject_id": "failure:1",
            "record_kind": "failure_action",
            "asset_class": "equity",
            "research_scope": "target_equity_research",
        }
    )

    assert "failure_retrieval" in result.routing_targets


def test_rows_ignore_non_mappings():
    rows = [
        {
            "subject_id": "candidate:1",
            "asset_class": "equity",
            "research_scope": "target_equity_research",
        },
        "bad",
    ]

    results = calibrate_routing_rows(rows)  # type: ignore[arg-type]

    assert len(results) == 1
    assert results[0].subject_id == "candidate:1"
