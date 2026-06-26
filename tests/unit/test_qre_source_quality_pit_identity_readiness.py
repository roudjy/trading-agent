from __future__ import annotations

import json
from pathlib import Path

from research import qre_source_quality_pit_identity_readiness as report_module


def test_report_is_deterministic_and_fail_closed() -> None:
    left = report_module.build_source_quality_pit_identity_readiness()
    right = report_module.build_source_quality_pit_identity_readiness()

    assert left == right
    assert left["summary"]["source_manifest_count"] >= 1
    assert left["summary"]["pit_required_blocked_count"] >= 1
    assert left["summary"]["identity_ambiguity_blocked_count"] >= 1


def test_local_observed_cache_evidence_is_separate_from_manifest_governance() -> None:
    report = report_module.build_source_quality_pit_identity_readiness()
    observed = {
        row["observed_source"]: row
        for row in report["observed_source_rows"]
    }
    manifest = {
        row["source_id"]: row
        for row in report["manifest_rows"]
    }

    yfinance = observed["yfinance"]
    assert yfinance["dimension_statuses"]["freshness"] == "PARTIAL"
    assert yfinance["dimension_statuses"]["coverage"] == "PARTIAL"
    assert yfinance["dimension_statuses"]["timestamp_monotonicity"] == "UNAVAILABLE"
    assert yfinance["dimension_statuses"]["duplicate_detection"] == "UNAVAILABLE"

    manifest_row = manifest["yahoo_finance_yfinance_manifest"]
    assert manifest_row["dimension_statuses"]["allowed_use_and_license"] == "BLOCKED"
    assert manifest_row["dimension_statuses"]["identity_readiness"] == "NOT_APPLICABLE"


def test_sec_and_openfigi_remain_blocked_or_partial_without_fake_pit_or_identity_passes() -> None:
    rows = {
        row["source_id"]: row
        for row in report_module.build_source_quality_pit_identity_readiness()["manifest_rows"]
    }

    sec = rows["sec_companyfacts_manifest"]
    assert sec["dimension_statuses"]["point_in_time_policy"] == "BLOCKED"
    assert sec["dimension_statuses"]["report_lag_policy"] == "BLOCKED"
    assert sec["dimension_statuses"]["restatement_policy"] == "BLOCKED"
    assert "MISSING_POINT_IN_TIME_POLICY" in sec["blocking_reasons"]

    openfigi = rows["openfigi_symbology_manifest"]
    assert openfigi["dimension_statuses"]["point_in_time_policy"] == "NOT_APPLICABLE"
    assert openfigi["dimension_statuses"]["identity_readiness"] in {"PARTIAL", "BLOCKED"}
    assert "identity_alias_ambiguity_present" in openfigi["blocking_reasons"]


def test_write_outputs_persists_log_and_artifact(tmp_path: Path) -> None:
    report = report_module.build_source_quality_pit_identity_readiness()
    paths = report_module.write_outputs(report, repo_root=tmp_path)

    payload = json.loads((tmp_path / paths["latest"]).read_text(encoding="utf-8"))
    artifact = json.loads((tmp_path / paths["artifact"]).read_text(encoding="utf-8"))
    summary = (tmp_path / paths["operator_summary"]).read_text(encoding="utf-8")

    assert payload["report_kind"] == "qre_source_quality_pit_identity_readiness"
    assert artifact["schema_version"] == "1.0"
    assert "# QRE Source Quality, PIT, and Identity Readiness" in summary


def test_safety_invariants_keep_report_read_only() -> None:
    report = report_module.build_source_quality_pit_identity_readiness()

    assert report["safety_invariants"] == {
        "read_only": True,
        "fetches_external_data": False,
        "mutates_runtime_state": False,
        "mutates_research_outputs": False,
        "mutates_frozen_contracts": False,
        "provider_activation_forbidden": True,
        "paper_shadow_live_forbidden": True,
        "broker_risk_execution_forbidden": True,
        "retrieval_not_authority": True,
        "diagnostics_do_not_trade": True,
    }
    assert tuple(report["readiness_status_vocabulary"]) == report_module.READINESS_STATUS_VOCABULARY
