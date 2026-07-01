from __future__ import annotations

import json
from pathlib import Path

import pytest

from packages.qre_research import decision_calibration as dcal
from packages.qre_research import empirical_evidence_pack as eep


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _closeout(*, strategy_decision: str, hypothesis_decision: str, terminal_outcome: str) -> dict[str, object]:
    return {
        "executed_campaign_identity": "qcx_fixture",
        "executed_campaign_cell": "qrcell_fixture",
        "train_stage": {"trade_count": 12, "net_return_compound": 0.11},
        "validation_stage": {"trade_count": 4, "net_return_compound": 0.03},
        "oos_stage": {
            "trade_count": 0,
            "net_return_compound": 0.0,
            "oos_outcome": "INSUFFICIENT_SIGNALS",
            "costs": 0.0,
            "slippage": 0.0,
            "trades": [],
        },
        "null_controls": {
            "null_control_passed": False,
            "rows": [{"control_class": "matched_frequency_null"}],
        },
        "campaign_classification": {
            "current_hypothesis_campaigns_executed": 1,
            "new_empirical_campaigns_completed": 1,
            "historical_campaigns_consumed": 0,
            "fixture_campaigns_consumed": 0,
            "null_or_synthetic_campaigns_executed": 0,
        },
        "decision": {
            "hypothesis_decision": hypothesis_decision,
            "strategy_decision": strategy_decision,
            "failure_memory_update": {"generated_strategy_id": "qgs_fixture"},
            "contradiction_update": {"evidence": "oos_sample_size_insufficient_after_ready_cell_execution"},
        },
        "feedback_routing": {"next_action": "launch_data_oos_capacity_expansion"},
        "terminal_outcome": terminal_outcome,
    }


def test_terminal_precedence_prefers_insufficient_activity_over_rejected_screening(tmp_path: Path) -> None:
    repo_root = tmp_path / "repo"
    _write_json(
        repo_root / "generated_research/registry/generated_strategy_registry.v1.json",
        {
            "rows": [
                {
                    "generated_strategy_id": "qgs_fixture",
                    "source_hypothesis_id": "cross_sectional_momentum_v0",
                    "strategy_spec_id": "qsp_fixture",
                    "sandbox_validation_path": "generated_research/validation/qgs_fixture.json",
                }
            ]
        },
    )
    _write_json(
        repo_root / "generated_research/readiness/campaigns/automated_portfolio_readiness.v1.json",
        {
            "rows": [
                {
                    "campaign_cell_id": "qrcell_fixture",
                    "timeframe": "4h",
                    "train_window": {"start": "2024-01-01T00:00:00Z", "end": "2024-06-01T00:00:00Z"},
                    "validation_window": {"start": "2024-06-15T00:00:00Z", "end": "2024-09-01T00:00:00Z"},
                    "oos_window": {"start": "2024-09-15T00:00:00Z", "end": "2024-12-01T00:00:00Z"},
                }
            ]
        },
    )
    _write_json(
        repo_root / "generated_research/specs/qsp_fixture.json",
        {
            "cost_assumptions": {"mode": "cost_class_visible_only"},
            "slippage_assumptions": {"status": "visible"},
        },
    )

    pack = eep.build_empirical_evidence_pack(
        repo_root=repo_root,
        closeout=_closeout(
            strategy_decision="REJECTED_SCREENING",
            hypothesis_decision="BLOCKED_SAMPLE_SIZE",
            terminal_outcome="DATA_OR_OOS_CAPACITY_BLOCKED",
        ),
    )

    semantics = pack["decision_semantics"]
    assert pack["disposition"] == "NEEDS_MORE_EVIDENCE"
    assert semantics["active_blocker"] == "REQUEST_MORE_EVIDENCE"
    assert semantics["next_action"] == "launch_data_oos_capacity_expansion"
    assert semantics["resolved_blockers"] == ["DATA_OR_OOS_CAPACITY_BLOCKED"]
    assert semantics["precedence"] == "insufficient_activity"
    assert pack["transaction_costs"]["applicability"] == "NOT_EVALUABLE"
    assert pack["transaction_costs"]["sufficiency"] == "INSUFFICIENT"
    assert pack["transaction_costs"]["outcome"] == "INCONCLUSIVE"
    assert pack["evidence_semantics"]["transaction_costs"]["presence"] == "AVAILABLE"
    assert pack["evidence_semantics"]["transaction_costs"]["sufficiency"] == "INSUFFICIENT"


@pytest.mark.parametrize("case", dcal.BENCHMARK_CASES, ids=lambda row: row["benchmark_id"])
def test_benchmark_cases_are_deterministic_and_closed(case: dict[str, object]) -> None:
    first = dcal.evaluate_benchmark_case(case)
    second = dcal.evaluate_benchmark_case(case)

    assert first == second
    assert first["matches"] is True
    assert first["terminal_disposition"] in dcal.TERMINAL_DISPOSITIONS
    assert first["active_blocker"] in dcal.ACTIVE_BLOCKERS
    assert first["reason_records"]


def test_benchmark_portfolio_has_one_synthesis_opener() -> None:
    results = [dcal.evaluate_benchmark_case(case) for case in dcal.BENCHMARK_CASES]
    summary = dcal.build_decision_quality_summary(results, replay_results=[dict(row) for row in results])

    assert len(results) == 10
    assert summary["benchmark_decision_accuracy"] == 100.0
    assert summary["deterministic_replay_match"] == 100.0
    assert summary["false_synthesis_ready_count"] == 0
    assert summary["unknown_terminal_decision_count"] == 0
    assert sum(1 for row in results if row["terminal_disposition"] == "READY_FOR_SYNTHESIS") == 1
    assert results[-1]["benchmark_id"] == "robust_survivor"
    assert results[-1]["terminal_disposition"] == "READY_FOR_SYNTHESIS"
    assert results[-1]["active_blocker"] == "NO_CAUSAL_PROGRESS"

