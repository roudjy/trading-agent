from __future__ import annotations

from datetime import UTC, datetime

from reporting.qre_validation_source_linkage_contract import (
    validate_source_linkage_contract,
)
from research.screening_evidence import (
    SCREENING_EVIDENCE_SOURCE_ARTIFACT,
    SCREENING_EVIDENCE_SOURCE_REPORT_KIND,
    build_qre_validation_linkage_authority,
    build_screening_evidence_payload,
)

FROZEN = datetime(2026, 6, 1, 12, 0, 0, tzinfo=UTC)
HYPOTHESIS_ID = "qre-hyp-fixture-001"
EXECUTABLE_HYPOTHESIS_ID = "trend_pullback_v1"
PLAN_ID = "qre-plan-fixture-001"
RUN_MANIFEST_ID = "qre-run-fixture-001"
_DEFAULT = object()


def _authority(
    *,
    hypotheses: dict | None | object = _DEFAULT,
    plans: dict | None | object = _DEFAULT,
    manifests: dict | None | object = _DEFAULT,
) -> dict:
    return build_qre_validation_linkage_authority(
        hypothesis_candidates_payload=(
            hypotheses
            if hypotheses is not _DEFAULT
            else {
                "report_kind": "qre_hypothesis_candidates",
                "hypotheses": [{"hypothesis_id": HYPOTHESIS_ID}],
            }
        ),
        validation_plans_payload=(
            plans
            if plans is not _DEFAULT
            else {
                "report_kind": "qre_hypothesis_validation_plan",
                "validation_plans": [
                    {
                        "hypothesis_id": HYPOTHESIS_ID,
                        "validation_plan_id": PLAN_ID,
                    }
                ],
            }
        ),
        run_manifest_payload=(
            manifests
            if manifests is not _DEFAULT
            else {
                "report_kind": "qre_research_run_manifest",
                "run_manifests": [
                    {
                        "run_manifest_id": RUN_MANIFEST_ID,
                        "target_hypothesis_id": HYPOTHESIS_ID,
                        "target_validation_plan_id": PLAN_ID,
                    }
                ],
            }
        ),
    )


def _bridge_authority() -> dict:
    return _authority(
        hypotheses={
            "report_kind": "qre_hypothesis_candidates",
            "hypotheses": [
                {
                    "hypothesis_id": HYPOTHESIS_ID,
                    "executable_hypothesis_id": EXECUTABLE_HYPOTHESIS_ID,
                    "source_hypothesis_id": "source-trend-pullback",
                    "strategy_family": "trend",
                    "strategy_template_id": "trend_pullback",
                    "preset_name": "trend_pullback_crypto_1h",
                }
            ],
        },
    )


def _payload(*, candidate: dict | None = None, authority: dict | None = None) -> dict:
    row = {
        "candidate_id": "candidate-001",
        "strategy_id": "strategy-a",
        "strategy_name": "strategy-a",
        "asset": "BTC-USD",
        "interval": "1h",
        "hypothesis_id": HYPOTHESIS_ID,
    }
    if candidate is not None:
        row.update(candidate)
    return build_screening_evidence_payload(
        run_id="run-1",
        as_of_utc=FROZEN,
        git_revision="abc123",
        campaign_id="cmp-1",
        col_campaign_id="cmp-1",
        preset_name="preset-a",
        screening_phase="exploratory",
        candidates=[row],
        screening_records=[
            {
                "candidate_id": row["candidate_id"],
                "final_status": "passed",
                "decision": "promoted_to_validation",
                "diagnostic_metrics": {"profit_factor": 1.4},
            }
        ],
        screening_pass_kinds={"strategy-a": "exploratory"},
        paper_blocked_index={},
        qre_validation_linkage_authority=authority,
    )


def test_screening_rows_include_source_artifact_kind_and_stable_row_id() -> None:
    row = _payload(authority=_authority())["candidates"][0]

    assert row["source_artifact"] == SCREENING_EVIDENCE_SOURCE_ARTIFACT
    assert row["source_report_kind"] == SCREENING_EVIDENCE_SOURCE_REPORT_KIND
    assert row["source_row_id"] == "candidate-001"


def test_exact_qre_authority_adds_all_strict_linkage_fields() -> None:
    row = _payload(authority=_authority())["candidates"][0]

    assert row["hypothesis_id"] == HYPOTHESIS_ID
    assert row["validation_plan_id"] == PLAN_ID
    assert row["run_manifest_id"] == RUN_MANIFEST_ID
    assert row["qre_validation_linkage_status"] == "linked_exact_ids"
    assert row["qre_validation_linkage_warnings"] == []


def test_screening_evidence_executable_hypothesis_id_links_through_bridge() -> None:
    row = _payload(
        candidate={"hypothesis_id": EXECUTABLE_HYPOTHESIS_ID},
        authority=_bridge_authority(),
    )["candidates"][0]

    assert row["hypothesis_id"] == HYPOTHESIS_ID
    assert row["executable_hypothesis_id"] == EXECUTABLE_HYPOTHESIS_ID
    assert row["validation_plan_id"] == PLAN_ID
    assert row["run_manifest_id"] == RUN_MANIFEST_ID
    assert row["qre_validation_linkage_status"] == "linked_executable_hypothesis_bridge"
    assert row["qre_validation_linkage_warnings"] == []




def test_catalog_active_discovery_hypothesis_links_without_exact_qre_ids() -> None:
    row = _payload(
        candidate={"hypothesis_id": EXECUTABLE_HYPOTHESIS_ID},
        authority=_authority(
            hypotheses={
                "report_kind": "qre_hypothesis_candidates",
                "hypotheses": [{"hypothesis_id": HYPOTHESIS_ID}],
            },
            plans={
                "report_kind": "qre_hypothesis_validation_plan",
                "validation_plans": [
                    {
                        "hypothesis_id": HYPOTHESIS_ID,
                        "validation_plan_id": PLAN_ID,
                    }
                ],
            },
            manifests={
                "report_kind": "qre_research_run_manifest",
                "run_manifests": [
                    {
                        "run_manifest_id": RUN_MANIFEST_ID,
                        "target_hypothesis_id": HYPOTHESIS_ID,
                        "target_validation_plan_id": PLAN_ID,
                    }
                ],
            },
        ),
    )["candidates"][0]

    assert row["hypothesis_id"] == EXECUTABLE_HYPOTHESIS_ID
    assert row["executable_hypothesis_id"] == EXECUTABLE_HYPOTHESIS_ID
    assert row["validation_plan_id"] is None
    assert row["run_manifest_id"] is None
    assert row["qre_validation_linkage_status"] == "linked_catalog_active_discovery"
    assert row["qre_validation_linkage_warnings"] == []


def test_ambiguous_executable_bridge_fails_closed_for_screening_evidence() -> None:
    authority = _authority(
        hypotheses={
            "report_kind": "qre_hypothesis_candidates",
            "hypotheses": [
                {
                    "hypothesis_id": HYPOTHESIS_ID,
                    "executable_hypothesis_id": EXECUTABLE_HYPOTHESIS_ID,
                },
                {
                    "hypothesis_id": "qre-hyp-fixture-002",
                    "executable_hypothesis_id": EXECUTABLE_HYPOTHESIS_ID,
                },
            ],
        },
        plans={
            "report_kind": "qre_hypothesis_validation_plan",
            "validation_plans": [
                {
                    "hypothesis_id": HYPOTHESIS_ID,
                    "validation_plan_id": PLAN_ID,
                },
                {
                    "hypothesis_id": "qre-hyp-fixture-002",
                    "validation_plan_id": "qre-plan-fixture-002",
                },
            ],
        },
        manifests={
            "report_kind": "qre_research_run_manifest",
            "run_manifests": [
                {
                    "run_manifest_id": RUN_MANIFEST_ID,
                    "target_validation_plan_id": PLAN_ID,
                },
                {
                    "run_manifest_id": "qre-run-fixture-002",
                    "target_validation_plan_id": "qre-plan-fixture-002",
                },
            ],
        },
    )

    row = _payload(
        candidate={"hypothesis_id": EXECUTABLE_HYPOTHESIS_ID},
        authority=authority,
    )["candidates"][0]

    assert EXECUTABLE_HYPOTHESIS_ID not in authority["by_executable_hypothesis_id"]
    assert authority["bridge_summary"]["ambiguous_bridge_count"] == 1
    assert row["hypothesis_id"] == EXECUTABLE_HYPOTHESIS_ID
    assert row["executable_hypothesis_id"] == EXECUTABLE_HYPOTHESIS_ID
    assert row["qre_validation_linkage_status"] == "unlinked_unknown_hypothesis_id"




def test_summary_no_longer_counts_catalog_linked_sufficient_oos_as_qre_blocked() -> None:
    payload = _payload(
        candidate={
            "candidate_id": "hd-candidate",
            "strategy_id": "trend_pullback_v1",
            "strategy_name": "trend_pullback_v1",
            "asset": "HD",
            "interval": "4h",
            "hypothesis_id": EXECUTABLE_HYPOTHESIS_ID,
            "validation": {
                "evidence_status": "sufficient_oos_evidence",
                "oos_trade_count": 14,
                "min_oos_trades": 10,
            },
        },
        authority=_authority(),
    )

    row = payload["candidates"][0]
    summary = payload["summary"]

    assert row["qre_validation_linkage_status"] == "linked_catalog_active_discovery"
    assert row["validation_evidence"]["status"] == "sufficient_oos_evidence"
    assert row["validation_evidence"]["oos_trade_count"] == 14
    assert row["validation_evidence"]["min_oos_trades"] == 10
    assert summary["sufficient_oos_evidence_candidates"] == 1
    assert summary["sufficient_oos_but_unlinked_candidates"] == 0
    assert summary["qre_linkage_blocked_candidates"] == 0
    assert summary["promotion_grade_candidates"] == 0


def test_emitted_strict_linked_row_passes_source_linkage_contract() -> None:
    row = _payload(authority=_authority())["candidates"][0]

    result = validate_source_linkage_contract(row)

    assert result["is_contract_compliant"] is True
    assert result["safe_to_link"] is True
    assert result["primary_linkage_mode"] == "exact_ids"


def test_source_row_id_is_deterministic_across_repeated_generation() -> None:
    authority = _authority()
    row_a = _payload(authority=authority)["candidates"][0]
    row_b = _payload(authority=authority)["candidates"][0]

    assert row_a["source_row_id"] == row_b["source_row_id"] == "candidate-001"
    assert row_a["source_artifact"] == row_b["source_artifact"]
    assert row_a["source_report_kind"] == row_b["source_report_kind"]


def test_asset_symbol_timeframe_only_linkage_is_not_contract_compliant() -> None:
    result = validate_source_linkage_contract(
        {"asset": "BTC-USD", "symbol": "BTC-USD", "timeframe": "1h"}
    )

    assert result["is_contract_compliant"] is False
    assert result["safe_to_link"] is False
    assert "asset_timeframe_only_not_allowed" in result["reason_codes"]
    assert "symbol_timeframe_only_not_allowed" in result["reason_codes"]


def test_missing_reference_artifacts_do_not_fabricate_plan_or_run_ids() -> None:
    row = _payload(authority=_authority(hypotheses=None, plans=None, manifests=None))["candidates"][
        0
    ]

    assert row["validation_plan_id"] is None
    assert row["run_manifest_id"] is None
    assert row["qre_validation_linkage_status"] != "linked_exact_ids"


def test_runtime_hypothesis_id_is_preserved_as_executable_identity_without_authority() -> None:
    row = _payload(
        candidate={"hypothesis_id": EXECUTABLE_HYPOTHESIS_ID},
        authority=None,
    )["candidates"][0]

    assert row["hypothesis_id"] == EXECUTABLE_HYPOTHESIS_ID
    assert row["executable_hypothesis_id"] == EXECUTABLE_HYPOTHESIS_ID
    assert row["validation_plan_id"] is None
    assert row["run_manifest_id"] is None
    assert row["qre_validation_linkage_status"] == "unlinked_reference_authority_unavailable"


def test_canonical_qre_hypothesis_id_is_not_fabricated_as_executable_identity() -> None:
    row = _payload(candidate={"hypothesis_id": HYPOTHESIS_ID}, authority=None)["candidates"][0]

    assert row["hypothesis_id"] == HYPOTHESIS_ID
    assert row["executable_hypothesis_id"] is None


def test_missing_hypothesis_artifact_fails_closed() -> None:
    row = _payload(authority=_authority(hypotheses={"report_kind": "wrong"}))["candidates"][0]

    assert row["validation_plan_id"] is None
    assert row["run_manifest_id"] is None
    assert (
        "qre_hypothesis_authority_absent_or_unparseable" in row["qre_validation_linkage_warnings"]
    )


def test_missing_validation_plan_artifact_fails_closed() -> None:
    row = _payload(authority=_authority(plans={"report_kind": "wrong"}))["candidates"][0]

    assert row["validation_plan_id"] is None
    assert row["run_manifest_id"] is None
    assert (
        "qre_validation_plan_authority_absent_or_unparseable"
        in row["qre_validation_linkage_warnings"]
    )


def test_missing_run_manifest_artifact_fails_closed() -> None:
    row = _payload(authority=_authority(manifests={"report_kind": "wrong"}))["candidates"][0]

    assert row["validation_plan_id"] is None
    assert row["run_manifest_id"] is None
    assert (
        "qre_run_manifest_authority_absent_or_unparseable" in row["qre_validation_linkage_warnings"]
    )


def test_unknown_hypothesis_id_does_not_fabricate_ids() -> None:
    row = _payload(
        candidate={"hypothesis_id": "not-in-qre-authority"},
        authority=_authority(),
    )["candidates"][0]

    assert row["validation_plan_id"] is None
    assert row["run_manifest_id"] is None
    assert row["qre_validation_linkage_status"] == "unlinked_unknown_hypothesis_id"


def test_candidate_id_only_is_not_used_as_primary_linkage() -> None:
    row = _payload(candidate={"hypothesis_id": None}, authority=_authority())["candidates"][0]

    assert row["hypothesis_id"] is None
    assert row["validation_plan_id"] is None
    assert row["run_manifest_id"] is None
    assert row["qre_validation_linkage_status"] == "unlinked_missing_hypothesis_id"
