from __future__ import annotations

from packages.qre_data import historical_accounting


def _manifest(**overrides: object) -> dict[str, object]:
    row: dict[str, object] = {
        "source_id": "sec_companyfacts_manifest",
        "provider_id": "sec",
        "source_type": "fundamentals",
        "activation_requirements": [
            "operator_license_approval",
            "point_in_time_policy_defined",
            "source_manifest_quality_pass",
        ],
        "reproducibility_method": "versioned_quarterly_snapshot",
    }
    row.update(overrides)
    return row


def _policy_row(status: str, support: str) -> dict[str, object]:
    return {
        "policy_status": status,
        "support_status": support,
    }


def test_historical_accounting_blocks_missing_policy_and_lineage() -> None:
    report = historical_accounting.evaluate_historical_accounting_snapshot(
        _manifest(
            activation_requirements=["operator_license_approval"],
            reproducibility_method="static_registry_stub_only",
        ),
        report_lag_policy_row=_policy_row("POLICY_MISSING", "UNKNOWN"),
        restatement_policy_row=_policy_row("FAIL_CLOSED", "UNKNOWN"),
    )

    assert report["requires_historical_accounting"] is True
    assert report["snapshot_contract_status"] == "BLOCKED"
    assert report["gate_statuses"]["no_lookahead_snapshot_contract"] is False
    assert report["blocking_reasons"] == [
        "point_in_time_policy_declared",
        "report_lag_policy_supported",
        "restatement_policy_supported",
        "historical_lineage_reproducible",
        "no_lookahead_snapshot_contract",
    ]


def test_historical_accounting_allows_ready_snapshot_contract_only_when_all_gates_pass() -> None:
    report = historical_accounting.evaluate_historical_accounting_snapshot(
        _manifest(),
        report_lag_policy_row=_policy_row("SUPPORTED", "SUPPORTED"),
        restatement_policy_row=_policy_row("PARTIALLY_SUPPORTED", "PARTIALLY_SUPPORTED"),
    )

    assert report["snapshot_contract_status"] == "READY"
    assert report["gate_statuses"]["no_lookahead_snapshot_contract"] is True
    assert report["blocking_reasons"] == []


def test_historical_accounting_is_not_required_for_identity_only_sources() -> None:
    report = historical_accounting.evaluate_historical_accounting_snapshot(
        _manifest(
            source_id="openfigi_symbology_manifest",
            provider_id="openfigi",
            source_type="symbology",
        ),
        report_lag_policy_row=_policy_row("NOT_REQUIRED", "UNSUPPORTED"),
        restatement_policy_row=_policy_row("NOT_REQUIRED", "UNSUPPORTED"),
    )

    assert report["requires_historical_accounting"] is False
    assert report["snapshot_contract_status"] == "NOT_REQUIRED"
    assert report["operator_explanation"].startswith(
        "Historical accounting snapshot contract is not required"
    )
