from __future__ import annotations

from datetime import UTC, datetime

from reporting.qre_validation_source_linkage_contract import (
    validate_source_linkage_contract,
)
from research.candidate_pipeline import (
    RUN_CANDIDATES_SOURCE_ARTIFACT,
    RUN_CANDIDATES_SOURCE_REPORT_KIND,
    build_candidate_artifact_payload,
)
from research.screening_evidence import build_qre_validation_linkage_authority

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


def _candidate(**overrides: object) -> dict:
    row: dict[str, object] = {
        "candidate_id": "candidate-001",
        "current_status": "planned",
        "strategy_name": "strategy-a",
        "family": "trend",
        "strategy_family": "trend_following",
        "asset": "BTC-USD",
        "asset_type": "crypto",
        "asset_class": "crypto",
        "interval": "1h",
        "hypothesis_id": HYPOTHESIS_ID,
        "parameter_space_identity": {
            "param_grid_hash": "hash",
            "combination_count": 1,
        },
        "strategy_requirements": {
            "position_structure": "outright",
            "initial_lane_support": "supported",
        },
        "fit_prior": {"status": "allowed", "reason": None},
        "dedupe": {"duplicate_removed": False, "raw_occurrences": 1},
        "eligibility": {"status": "eligible", "reason": None},
        "screening": {"status": "promoted_to_validation", "reason": None},
        "validation": {"status": "pending", "result_success": None},
    }
    row.update(overrides)
    return row


def _row(*, candidate: dict | None = None, authority: dict | None = None) -> dict:
    payload = build_candidate_artifact_payload(
        run_id="run-1",
        as_of_utc=FROZEN,
        candidates=[candidate or _candidate()],
        qre_validation_linkage_authority=authority,
    )
    return payload["candidates"][0]


def test_run_candidates_rows_include_source_artifact_kind_and_stable_row_id() -> None:
    row = _row(authority=_authority())

    assert row["source_artifact"] == RUN_CANDIDATES_SOURCE_ARTIFACT
    assert row["source_report_kind"] == RUN_CANDIDATES_SOURCE_REPORT_KIND
    assert row["source_row_id"] == "candidate-001"


def test_exact_qre_authority_adds_all_strict_linkage_fields() -> None:
    row = _row(authority=_authority())

    assert row["hypothesis_id"] == HYPOTHESIS_ID
    assert row["validation_plan_id"] == PLAN_ID
    assert row["run_manifest_id"] == RUN_MANIFEST_ID
    assert row["qre_validation_linkage_status"] == "linked_exact_ids"
    assert row["qre_validation_linkage_warnings"] == []


def test_qre_hypothesis_row_with_executable_id_builds_safe_bridge_authority() -> None:
    authority = _bridge_authority()

    bridge = authority["by_executable_hypothesis_id"][EXECUTABLE_HYPOTHESIS_ID]
    assert bridge["safe_to_bridge"] is True
    assert bridge["bridge_status"] == "bridge_exact"
    assert bridge["qre_hypothesis_id"] == HYPOTHESIS_ID
    assert bridge["validation_plan_id"] == PLAN_ID
    assert bridge["run_manifest_id"] == RUN_MANIFEST_ID
    assert authority["bridge_summary"] == {
        "exact_bridge_count": 1,
        "ambiguous_bridge_count": 0,
        "unsafe_bridge_count": 0,
    }


def test_trend_pullback_v1_bridges_safely_to_qre_fixture() -> None:
    bridge = _bridge_authority()["by_executable_hypothesis_id"][EXECUTABLE_HYPOTHESIS_ID]

    assert bridge["executable_hypothesis_id"] == EXECUTABLE_HYPOTHESIS_ID
    assert bridge["qre_hypothesis_id"] == HYPOTHESIS_ID
    assert bridge["source_hypothesis_id"] == "source-trend-pullback"


def test_run_candidate_executable_hypothesis_id_links_through_bridge() -> None:
    row = _row(
        candidate=_candidate(hypothesis_id=EXECUTABLE_HYPOTHESIS_ID),
        authority=_bridge_authority(),
    )

    assert row["hypothesis_id"] == HYPOTHESIS_ID
    assert row["executable_hypothesis_id"] == EXECUTABLE_HYPOTHESIS_ID
    assert row["validation_plan_id"] == PLAN_ID
    assert row["run_manifest_id"] == RUN_MANIFEST_ID
    assert row["qre_validation_linkage_status"] == "linked_executable_hypothesis_bridge"
    assert row["qre_validation_linkage_warnings"] == []


def test_ambiguous_executable_bridge_fails_closed_for_run_candidates() -> None:
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

    row = _row(
        candidate=_candidate(hypothesis_id=EXECUTABLE_HYPOTHESIS_ID),
        authority=authority,
    )

    assert EXECUTABLE_HYPOTHESIS_ID not in authority["by_executable_hypothesis_id"]
    assert authority["bridge_summary"]["ambiguous_bridge_count"] == 1
    assert row["hypothesis_id"] == EXECUTABLE_HYPOTHESIS_ID
    assert row["executable_hypothesis_id"] is None
    assert row["qre_validation_linkage_status"] == "unlinked_unknown_hypothesis_id"


def test_emitted_strict_linked_run_candidate_passes_source_linkage_contract() -> None:
    row = _row(authority=_authority())

    result = validate_source_linkage_contract(row)

    assert result["is_contract_compliant"] is True
    assert result["safe_to_link"] is True
    assert "contract_compliant_exact_ids" in result["reason_codes"]


def test_source_row_id_is_deterministic_across_repeated_generation() -> None:
    authority = _authority()
    row_a = _row(authority=authority)
    row_b = _row(authority=authority)

    assert row_a["source_row_id"] == row_b["source_row_id"] == "candidate-001"


def test_candidate_id_only_row_is_not_strict_compliant() -> None:
    row = _row(candidate=_candidate(hypothesis_id=None), authority=_authority())

    emitted_result = validate_source_linkage_contract(row)
    candidate_only_result = validate_source_linkage_contract({"candidate_id": "candidate-001"})

    assert row["qre_validation_linkage_status"] == "unlinked_missing_hypothesis_id"
    assert emitted_result["safe_to_link"] is False
    assert candidate_only_result["safe_to_link"] is False
    assert "candidate_id_context_only_not_allowed" in candidate_only_result["reason_codes"]


def test_asset_timeframe_only_linkage_is_not_accepted() -> None:
    result = validate_source_linkage_contract({"asset": "BTC-USD", "timeframe": "1h"})

    assert result["safe_to_link"] is False
    assert "asset_timeframe_only_not_allowed" in result["reason_codes"]


def test_reference_artifacts_missing_do_not_fabricate_ids() -> None:
    row = _row(authority=_authority(hypotheses=None, plans=None, manifests=None))

    assert row["validation_plan_id"] is None
    assert row["run_manifest_id"] is None
    assert row["qre_validation_linkage_status"] == "unlinked_authority_absent"


def test_missing_hypothesis_authority_fails_closed() -> None:
    row = _row(authority=_authority(hypotheses={"report_kind": "wrong"}))

    assert row["validation_plan_id"] is None
    assert row["run_manifest_id"] is None
    assert (
        "qre_hypothesis_authority_absent_or_unparseable" in row["qre_validation_linkage_warnings"]
    )


def test_missing_validation_plan_authority_fails_closed() -> None:
    row = _row(authority=_authority(plans={"report_kind": "wrong"}))

    assert row["validation_plan_id"] is None
    assert row["run_manifest_id"] is None
    assert (
        "qre_validation_plan_authority_absent_or_unparseable"
        in row["qre_validation_linkage_warnings"]
    )


def test_missing_run_manifest_authority_fails_closed() -> None:
    row = _row(authority=_authority(manifests={"report_kind": "wrong"}))

    assert row["validation_plan_id"] is None
    assert row["run_manifest_id"] is None
    assert (
        "qre_run_manifest_authority_absent_or_unparseable" in row["qre_validation_linkage_warnings"]
    )


def test_missing_validation_plan_for_hypothesis_fails_closed() -> None:
    row = _row(
        authority=_authority(
            plans={
                "report_kind": "qre_hypothesis_validation_plan",
                "validation_plans": [],
            }
        )
    )

    assert row["validation_plan_id"] is None
    assert row["run_manifest_id"] is None
    assert row["qre_validation_linkage_status"] == "unlinked_missing_validation_plan_id"


def test_missing_run_manifest_for_validation_plan_fails_closed() -> None:
    row = _row(
        authority=_authority(
            manifests={
                "report_kind": "qre_research_run_manifest",
                "run_manifests": [],
            }
        )
    )

    assert row["validation_plan_id"] is None
    assert row["run_manifest_id"] is None
    assert row["qre_validation_linkage_status"] == "unlinked_missing_run_manifest_id"


def test_ambiguous_validation_plan_authority_fails_closed() -> None:
    row = _row(
        authority=_authority(
            plans={
                "report_kind": "qre_hypothesis_validation_plan",
                "validation_plans": [
                    {
                        "hypothesis_id": HYPOTHESIS_ID,
                        "validation_plan_id": PLAN_ID,
                    },
                    {
                        "hypothesis_id": HYPOTHESIS_ID,
                        "validation_plan_id": "qre-plan-fixture-002",
                    },
                ],
            }
        )
    )

    assert row["validation_plan_id"] is None
    assert row["run_manifest_id"] is None
    assert row["qre_validation_linkage_status"] == "unlinked_ambiguous_validation_plan_id"


def test_ambiguous_run_manifest_authority_fails_closed() -> None:
    row = _row(
        authority=_authority(
            manifests={
                "report_kind": "qre_research_run_manifest",
                "run_manifests": [
                    {
                        "run_manifest_id": RUN_MANIFEST_ID,
                        "target_validation_plan_id": PLAN_ID,
                    },
                    {
                        "run_manifest_id": "qre-run-fixture-002",
                        "target_validation_plan_id": PLAN_ID,
                    },
                ],
            }
        )
    )

    assert row["validation_plan_id"] is None
    assert row["run_manifest_id"] is None
    assert row["qre_validation_linkage_status"] == "unlinked_ambiguous_run_manifest_id"
