from __future__ import annotations

import json
from pathlib import Path

import pytest

from reporting import qre_synthesis_readiness_review as review


FROZEN = "2026-06-28T16:00:00Z"


def _write_json(path: Path, payload: dict[str, object]) -> Path:
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path


def _maturity_payload() -> dict[str, object]:
    return {
        "report_kind": "qre_trusted_research_maturity_matrix",
        "summary": {
            "evidence_authoritative_surface_count": 0,
            "operator_trusted_surface_count": 0,
            "overall_baseline": "mixed_decision_useful_pockets_not_operator_trusted",
        },
    }


def _evidence_density_payload() -> dict[str, object]:
    return {"report_kind": "qre_evidence_density_inventory", "summary": {"final_recommendation": "ready"}}


def _reason_maturity_payload() -> dict[str, object]:
    return {
        "report_kind": "qre_reason_record_maturity",
        "summary": {
            "record_count": 45,
            "linked_record_count": 45,
            "exact_next_action": "normalize_reason_record_contract_gaps_before_authority_upgrade",
        },
    }


def _reason_audit_payload() -> dict[str, object]:
    return {
        "report_kind": "qre_reason_record_audit",
        "summary": {
            "reason_records_manifest_total": 0,
            "reason_record_coverage_pct": 98.94,
        },
    }


def _routing_baseline_payload() -> dict[str, object]:
    return {"report_kind": "qre_routing_baseline_comparison", "summary": {"current_routing_score": 2.0}}


def _routing_sampling_readiness_payload() -> dict[str, object]:
    return {
        "report_kind": "qre_routing_sampling_readiness",
        "summary": {
            "routing_ready_count": 2,
            "sampling_ready_count": 2,
            "exact_next_action": "preserve_evidence_backed_ready_and_non_ready_states",
        },
    }


def _sampling_baseline_payload() -> dict[str, object]:
    return {"report_kind": "qre_sampling_baseline_comparison", "summary": {"current_sampling_score": 2.0}}


def _suppression_payload() -> dict[str, object]:
    return {
        "report_kind": "qre_suppression_efficacy",
        "summary": {"final_recommendation": "suppression_efficacy_insufficient_baseline"},
    }


def _source_identity_payload() -> dict[str, object]:
    return {
        "report_kind": "qre_source_identity_authority_normalization",
        "summary": {
            "blocked_scope_count": 8,
            "exact_next_action": "materialize_identity_inventory_for_bounded_scope",
        },
    }


def _source_usefulness_payload() -> dict[str, object]:
    return {
        "report_kind": "qre_source_usefulness_ledger",
        "summary": {
            "source_quality_ready": True,
            "research_ready": True,
        },
    }


def _data_payload() -> dict[str, object]:
    return {
        "report_kind": "qre_data_cache_manifest",
        "summary": {
            "research_ready": True,
        },
    }


def _lineage_payload() -> dict[str, object]:
    return {
        "report_kind": "qre_contradiction_hypothesis_lineage",
        "summary": {
            "complete_lineage_count": 1,
            "missing_lineage_count": 6,
            "contradiction_visible_count": 7,
            "thesis_count": 7,
        },
    }


def _decay_payload() -> dict[str, object]:
    return {
        "report_kind": "qre_evidence_decay",
        "summary": {
            "blocked_count": 7,
            "final_recommendation": "evidence_decay_visible_fail_closed",
        },
    }


def _operator_payload() -> dict[str, object]:
    return {
        "report_kind": "qre_operator_decision_report",
        "summary": {
            "decision_counts": {
                "BLOCKED": 1,
                "INSUFFICIENT_EVIDENCE": 0,
                "REJECTED": 1,
                "SUPPORTED_FOR_REVIEW": 0,
            },
            "thesis_count": 2,
        },
        "rows": [
            {
                "source_hypothesis_id": "alpha_v0",
                "title": "Alpha",
                "final_decision": "BLOCKED",
                "next_action": "establish_campaign_lineage_for_thesis",
                "oos": {"accepted_oos_count": None},
                "provenance_refs": ["operator:alpha"],
            },
            {
                "source_hypothesis_id": "trend_pullback_v1",
                "title": "Trend Pullback",
                "final_decision": "REJECTED",
                "next_action": "reject_hypothesis",
                "oos": {"accepted_oos_count": 0},
                "provenance_refs": ["operator:trend"],
            },
        ],
    }


def _why_payload() -> dict[str, object]:
    return {"report_kind": "qre_why_surfaces", "summary": {"decision_counts": {"BLOCKED": 1, "REJECTED": 1}}}


def _portfolio_payload() -> dict[str, object]:
    return {
        "report_kind": "qre_campaign_portfolio_plan",
        "portfolio_identity": "qcpp_fixture",
        "summary": {"ready_cell_count": 0, "cell_count": 2},
    }


def _manifest_payload() -> dict[str, object]:
    return {
        "report_kind": "qre_preregistered_campaign_manifest",
        "manifest_identity": "qcm_fixture",
        "replay_identity": "qcr_fixture",
        "summary": {"executable_cell_count": 0},
    }


def _execution_payload() -> dict[str, object]:
    return {
        "report_kind": "qre_broad_campaign_execution",
        "campaign_execution_identity": "qcy_fixture",
        "summary": {"completed": 0},
    }


def _diagnosis_payload() -> dict[str, object]:
    return {
        "report_kind": "qre_broad_campaign_funnel_diagnosis",
        "diagnosis_identity": "qcz_fixture",
        "summary": {"primary_bottleneck": "evidence_completeness"},
        "funnel_counts": {
            "oos_accepted_count": 0,
            "null_control_complete_count": 0,
            "validation_completed_count": 0,
        },
    }


def _recalibration_payload() -> dict[str, object]:
    return {
        "report_kind": "qre_single_class_recalibration",
        "recalibration_identity": "qraa_fixture",
        "decision": "INSUFFICIENT_EVIDENCE",
        "summary": {"final_recommendation": "single_class_recalibration_not_justified"},
    }


def _replay_payload() -> dict[str, object]:
    return {
        "report_kind": "qre_same_input_replay",
        "replay_assessment_identity": "qrab_fixture",
        "summary": {"supported_for_review_count": 0},
    }


def _independent_payload() -> dict[str, object]:
    return {
        "report_kind": "qre_repeated_independent_oos",
        "independent_oos_identity": "qrao_fixture",
        "summary": {
            "independent_ready_count": 0,
            "supported_for_review_count": 0,
        },
        "rows": [
            {
                "source_hypothesis_id": "alpha_v0",
                "independent_oos_status": "BLOCKED_MISSING_CAMPAIGN_LINEAGE",
            },
            {
                "source_hypothesis_id": "trend_pullback_v1",
                "independent_oos_status": "BLOCKED_REJECTED_NO_ACCEPTED_OOS",
            },
        ],
    }


def test_collect_snapshot_emits_continue_blocked_with_ordered_remediation(tmp_path: Path) -> None:
    snapshot = review.collect_snapshot(
        maturity_path=_write_json(tmp_path / "maturity.json", _maturity_payload()),
        evidence_density_path=_write_json(tmp_path / "evidence_density.json", _evidence_density_payload()),
        reason_maturity_path=_write_json(tmp_path / "reason_maturity.json", _reason_maturity_payload()),
        reason_audit_path=_write_json(tmp_path / "reason_audit.json", _reason_audit_payload()),
        routing_baseline_path=_write_json(tmp_path / "routing_baseline.json", _routing_baseline_payload()),
        routing_sampling_readiness_path=_write_json(tmp_path / "routing_sampling.json", _routing_sampling_readiness_payload()),
        sampling_baseline_path=_write_json(tmp_path / "sampling_baseline.json", _sampling_baseline_payload()),
        suppression_path=_write_json(tmp_path / "suppression.json", _suppression_payload()),
        source_identity_path=_write_json(tmp_path / "source_identity.json", _source_identity_payload()),
        source_usefulness_path=_write_json(tmp_path / "source_usefulness.json", _source_usefulness_payload()),
        data_readiness_path=_write_json(tmp_path / "data.json", _data_payload()),
        lineage_path=_write_json(tmp_path / "lineage.json", _lineage_payload()),
        decay_path=_write_json(tmp_path / "decay.json", _decay_payload()),
        operator_path=_write_json(tmp_path / "operator.json", _operator_payload()),
        why_path=_write_json(tmp_path / "why.json", _why_payload()),
        portfolio_path=_write_json(tmp_path / "portfolio.json", _portfolio_payload()),
        manifest_path=_write_json(tmp_path / "manifest.json", _manifest_payload()),
        execution_path=_write_json(tmp_path / "execution.json", _execution_payload()),
        diagnosis_path=_write_json(tmp_path / "diagnosis.json", _diagnosis_payload()),
        recalibration_path=_write_json(tmp_path / "recalibration.json", _recalibration_payload()),
        replay_path=_write_json(tmp_path / "replay.json", _replay_payload()),
        independent_path=_write_json(tmp_path / "independent.json", _independent_payload()),
        generated_at_utc=FROZEN,
    )

    assert snapshot["final_readiness_outcome"] == "CONTINUE_BLOCKED"
    assert snapshot["summary"]["supported_for_review_hypothesis_count"] == 0
    assert snapshot["summary"]["accepted_oos_count"] == 0
    assert snapshot["summary"]["null_control_complete_count"] == 0
    assert snapshot["exact_next_permitted_action"].startswith("launch_separate_remediation_program")
    assert snapshot["remediation_backlog"][0]["remediation_class"] == "campaign_lineage_establishment"
    assert snapshot["remediation_backlog"][-1]["remediation_class"] == "synthesis_design"

    criteria = {row["criterion_id"]: row for row in snapshot["readiness_matrix"]}
    assert criteria["routing_usefulness"]["status"] == "SATISFIED"
    assert criteria["sampling_usefulness"]["status"] == "SATISFIED"
    assert criteria["source_quality"]["status"] == "SATISFIED"
    assert criteria["data_readiness"]["status"] == "SATISFIED"
    assert criteria["identity_readiness"]["status"] == "BLOCKED"
    assert criteria["accepted_oos"]["status"] == "BLOCKED"
    assert criteria["repeated_independent_oos"]["status"] == "BLOCKED"
    assert criteria["null_control_completeness"]["status"] == "BLOCKED"
    assert criteria["trading_authority_leakage_absent"]["status"] == "SATISFIED"

    thesis_rows = {row["source_hypothesis_id"]: row for row in snapshot["thesis_rows"]}
    assert thesis_rows["trend_pullback_v1"]["synthesis_state"] == "REJECTED_NOT_SYNTHESIS_ELIGIBLE"
    assert thesis_rows["alpha_v0"]["synthesis_state"] == "BLOCKED_PRE_SYNTHESIS"


def test_collect_snapshot_is_deterministic(tmp_path: Path) -> None:
    kwargs = {
        "maturity_path": _write_json(tmp_path / "maturity.json", _maturity_payload()),
        "evidence_density_path": _write_json(tmp_path / "evidence_density.json", _evidence_density_payload()),
        "reason_maturity_path": _write_json(tmp_path / "reason_maturity.json", _reason_maturity_payload()),
        "reason_audit_path": _write_json(tmp_path / "reason_audit.json", _reason_audit_payload()),
        "routing_baseline_path": _write_json(tmp_path / "routing_baseline.json", _routing_baseline_payload()),
        "routing_sampling_readiness_path": _write_json(tmp_path / "routing_sampling.json", _routing_sampling_readiness_payload()),
        "sampling_baseline_path": _write_json(tmp_path / "sampling_baseline.json", _sampling_baseline_payload()),
        "suppression_path": _write_json(tmp_path / "suppression.json", _suppression_payload()),
        "source_identity_path": _write_json(tmp_path / "source_identity.json", _source_identity_payload()),
        "source_usefulness_path": _write_json(tmp_path / "source_usefulness.json", _source_usefulness_payload()),
        "data_readiness_path": _write_json(tmp_path / "data.json", _data_payload()),
        "lineage_path": _write_json(tmp_path / "lineage.json", _lineage_payload()),
        "decay_path": _write_json(tmp_path / "decay.json", _decay_payload()),
        "operator_path": _write_json(tmp_path / "operator.json", _operator_payload()),
        "why_path": _write_json(tmp_path / "why.json", _why_payload()),
        "portfolio_path": _write_json(tmp_path / "portfolio.json", _portfolio_payload()),
        "manifest_path": _write_json(tmp_path / "manifest.json", _manifest_payload()),
        "execution_path": _write_json(tmp_path / "execution.json", _execution_payload()),
        "diagnosis_path": _write_json(tmp_path / "diagnosis.json", _diagnosis_payload()),
        "recalibration_path": _write_json(tmp_path / "recalibration.json", _recalibration_payload()),
        "replay_path": _write_json(tmp_path / "replay.json", _replay_payload()),
        "independent_path": _write_json(tmp_path / "independent.json", _independent_payload()),
        "generated_at_utc": FROZEN,
    }
    first = review.collect_snapshot(**kwargs)
    second = review.collect_snapshot(**kwargs)

    assert first == second
    assert first["synthesis_readiness_identity"].startswith("qrsr_")
    assert first["final_readiness_outcome"] in review.FINAL_DECISIONS
    for row in first["readiness_matrix"]:
        assert row["status"] in review.CRITERION_STATUSES


def test_atomic_write_refuses_outside_allowlist(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        review._atomic_write(tmp_path / "latest.json", "{}")


def test_source_has_no_strategy_synthesis_registration_or_runtime_calls() -> None:
    src = Path(review.__file__).read_text(encoding="utf-8")
    forbidden = (
        "def register_strategy",
        "def generate_executable_strategy",
        "activate_paper(",
        "activate_shadow(",
        "activate_live(",
        "import subprocess",
        "from subprocess",
        "subprocess.",
        "import socket",
        "from socket",
        "import requests",
        "import httpx",
        "import aiohttp",
        "import urllib",
        "from urllib",
        "os.system",
        "os.popen",
        "shell=True",
        "git ",
        "gh ",
        "codex ",
    )
    for token in forbidden:
        assert token not in src, token
