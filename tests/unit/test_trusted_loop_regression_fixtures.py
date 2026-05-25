"""Regression fixture coverage for ADE-QRE-014K trusted-loop evidence."""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pytest

from reporting import trusted_loop_materialization as tlm

FIXTURE_PATH = (
    Path(__file__).resolve().parents[1]
    / "fixtures"
    / "trusted_loop_regression"
    / "evidence_cases.v1.json"
)

EXPECTED_CASE_IDS = {
    "complete",
    "thin",
    "missing",
    "contradictory",
    "blocked",
    "non_actionable",
}


def _load_fixture() -> dict[str, Any]:
    return json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, sort_keys=True, indent=2), encoding="utf-8")


def _case_summary(case: Mapping[str, Any], tmp_path: Path) -> dict[str, Any]:
    case_root = tmp_path / str(case["case_id"])
    routing_path = case_root / "logs" / "intelligent_routing_minimal" / "latest.json"
    sampling_path = case_root / "logs" / "sampling_intelligence_minimal" / "latest.json"
    artifact_present = case["artifact_present"]

    if artifact_present["routing"]:
        _write_json(routing_path, case["routing_snapshot"])
    if artifact_present["sampling"]:
        _write_json(sampling_path, case["sampling_snapshot"])

    kpis = tlm._research_quality_kpi_readiness(
        {"research_quality_kpi_evidence": case["kpi_evidence"]}
    )
    routing_sampling = tlm._routing_sampling_readiness_density(
        routing_snapshot=case["routing_snapshot"],
        sampling_snapshot=case["sampling_snapshot"],
        routing_artifact_path=routing_path,
        sampling_artifact_path=sampling_path,
    )
    blockers = tlm._synthesis_blocker_explanation_density(
        block_reasons=list(case["block_reasons"]),
        failure_action_mapping=case["failure_action_mapping"],
        kpi_readiness=kpis,
        routing_sampling_readiness=routing_sampling,
        reason_density=case["reason_density"],
    )

    routing_ready = routing_sampling["values"]["routing_ready"]
    sampling_ready = routing_sampling["values"]["sampling_ready"]
    failure_blocker = blockers["values"].get(
        "failure_action_mapping_not_ready_when_total_failures_zero",
        {},
    )
    return {
        "case_id": case["case_id"],
        "kpi_complete_value_count": kpis["complete_value_count"],
        "kpi_partial_value_count": kpis["partial_value_count"],
        "kpi_fail_closed_count": kpis["fail_closed_count"],
        "routing_status": routing_ready["status"],
        "sampling_status": sampling_ready["status"],
        "routing_missing_evidence": routing_ready["missing_evidence"],
        "sampling_missing_evidence": sampling_ready["missing_evidence"],
        "failure_missing_evidence": failure_blocker.get("missing_evidence", []),
        "blocker_overall_status": blockers["overall_status"],
        "explained_blocker_count": blockers["explained_blocker_count"],
        "unexplained_blocker_count": blockers["unexplained_blocker_count"],
        "synthesis_remains_blocked": blockers["synthesis_remains_blocked"],
        "read_only": blockers["read_only"],
        "all_blockers_read_only": all(
            row["read_only"] is True for row in blockers["values"].values()
        ),
        "no_blocker_enables_strategy_synthesis": all(
            row["enables_strategy_synthesis"] is False
            for row in blockers["values"].values()
        ),
    }


def _cases() -> list[dict[str, Any]]:
    return list(_load_fixture()["cases"])


def test_fixture_inventory_is_complete_and_read_only() -> None:
    fixture = _load_fixture()

    assert fixture["schema_version"] == 1
    assert {case["case_id"] for case in fixture["cases"]} == EXPECTED_CASE_IDS
    assert fixture["safety_invariants"] == {
        "read_only": True,
        "mutates_research_outputs": False,
        "mutates_frozen_contracts": False,
        "enables_strategy_synthesis": False,
        "activates_addendum_runtime": False,
        "paper_shadow_live_forbidden": True,
        "broker_risk_execution_forbidden": True,
    }


@pytest.mark.parametrize("case", _cases(), ids=lambda case: case["case_id"])
def test_trusted_loop_fixture_cases_are_deterministic(
    case: Mapping[str, Any],
    tmp_path: Path,
) -> None:
    left = _case_summary(case, tmp_path)
    right = _case_summary(case, tmp_path)

    assert left == right


@pytest.mark.parametrize("case", _cases(), ids=lambda case: case["case_id"])
def test_trusted_loop_fixture_cases_match_expected_reporting_outcomes(
    case: Mapping[str, Any],
    tmp_path: Path,
) -> None:
    summary = _case_summary(case, tmp_path)
    expected = case["expected"]

    for key, value in expected.items():
        assert summary[key] == value
    assert summary["synthesis_remains_blocked"] is True
    assert summary["read_only"] is True
    assert summary["all_blockers_read_only"] is True
    assert summary["no_blocker_enables_strategy_synthesis"] is True
