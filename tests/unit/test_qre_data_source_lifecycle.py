from __future__ import annotations

from packages.qre_data import source_lifecycle


REQUIRED_FORBIDDEN = (
    "trade_signal",
    "buy_list",
    "sell_list",
    "strategy_registration",
    "candidate_promotion",
    "paper_activation",
    "shadow_activation",
    "live_activation",
    "capital_allocation",
    "broker_execution",
    "fundamental_field_readiness",
)


def _manifest(**overrides: object) -> dict[str, object]:
    base: dict[str, object] = {
        "source_id": "fixture_source",
        "provider_id": "fixture_provider",
        "source_status": "candidate",
        "manifest_status": "VALID",
        "license_terms_reference": "fixture_terms",
        "schema_version": "1.0",
        "allowed_use": ["identity_mapping", "operator_explanation", "source_candidate_research"],
        "forbidden_use": list(REQUIRED_FORBIDDEN),
        "required_quality_gates": ["identity_mapping_quality_gate", "source_manifest_quality_pass"],
        "activation_requirements": [
            "identity_mapping_quality_gate",
            "source_manifest_quality_pass",
            "historical_lineage_present",
        ],
        "factor_field_coverage_claims": ["identity_mapping"],
        "manifest_block_reasons": [],
        "reproducibility_method": "snapshot_lineage_manifest_v1",
    }
    base.update(overrides)
    return base


def test_candidate_cannot_jump_directly_to_active_read_only() -> None:
    result = source_lifecycle.evaluate_source_lifecycle(
        _manifest(),
        required_forbidden_use=REQUIRED_FORBIDDEN,
        source_quality_ready=True,
        license_allows_quality_gate=True,
        license_allows_active_read_only=True,
    )

    assert result["transition_targets"]["quality_gated"]["allowed"] is True
    assert result["transition_targets"]["active_read_only"]["allowed"] is False
    assert result["transition_targets"]["active_read_only"]["blocking_reasons"] == [
        "transition_requires_quality_gated_state"
    ]


def test_active_read_only_requires_historical_lineage_and_identity_mapping() -> None:
    result = source_lifecycle.evaluate_source_lifecycle(
        _manifest(
            source_status="quality_gated",
            reproducibility_method="static_registry_stub_only",
            allowed_use=["operator_explanation", "source_candidate_research"],
            required_quality_gates=["source_manifest_quality_pass"],
            activation_requirements=["historical_lineage_present"],
            factor_field_coverage_claims=["fundamental_field_candidate"],
        ),
        required_forbidden_use=REQUIRED_FORBIDDEN,
        source_quality_ready=True,
        license_allows_quality_gate=True,
        license_allows_active_read_only=True,
    )

    assert result["transition_targets"]["active_read_only"]["allowed"] is False
    assert result["gate_statuses"]["identity_mapping_present"] is False
    assert result["gate_statuses"]["historical_lineage_present"] is False
    assert "identity_mapping_present" in result["transition_targets"]["active_read_only"][
        "blocking_reasons"
    ]
    assert "historical_lineage_present" in result["transition_targets"]["active_read_only"][
        "blocking_reasons"
    ]


def test_active_read_only_requires_all_declared_gates_to_pass() -> None:
    result = source_lifecycle.evaluate_source_lifecycle(
        _manifest(source_status="quality_gated"),
        required_forbidden_use=REQUIRED_FORBIDDEN,
        source_quality_ready=False,
        license_allows_quality_gate=True,
        license_allows_active_read_only=False,
    )

    assert result["transition_targets"]["active_read_only"]["allowed"] is False
    assert result["gate_statuses"]["quality_gates_passed"] is False
    assert result["transition_targets"]["active_read_only"]["blocking_reasons"] == [
        "license_allows_active_read_only",
        "quality_gates_passed",
    ]


def test_quality_gated_and_active_read_only_are_allowed_only_when_all_gates_are_explicit() -> None:
    result = source_lifecycle.evaluate_source_lifecycle(
        _manifest(source_status="active_read_only"),
        required_forbidden_use=REQUIRED_FORBIDDEN,
        source_quality_ready=True,
        license_allows_quality_gate=True,
        license_allows_active_read_only=True,
    )

    assert result["lifecycle_status"] == "active_read_only_ready"
    assert result["transition_targets"]["quality_gated"]["allowed"] is True
    assert result["transition_targets"]["active_read_only"]["allowed"] is True
    assert all(result["gate_statuses"].values()) is True
