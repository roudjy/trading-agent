from __future__ import annotations

import json
from pathlib import Path

from packages.qre_research import empirical_evidence_pack as eep


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def test_build_empirical_evidence_pack_is_canonical_and_fail_closed(tmp_path: Path) -> None:
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
    closeout = {
        "executed_campaign_identity": "qcx_fixture",
        "executed_campaign_cell": "qrcell_fixture",
        "train_stage": {"trade_count": 12, "net_return_compound": 0.11},
        "validation_stage": {"trade_count": 4, "net_return_compound": 0.03},
        "oos_stage": {
            "trade_count": 3,
            "net_return_compound": 0.02,
            "oos_outcome": "INSUFFICIENT_TRADES",
            "costs": 0.0,
            "slippage": 0.0,
            "trades": [{"net_return": 0.02}, {"net_return": -0.01}, {"net_return": 0.005}],
        },
        "null_controls": {
            "null_control_passed": False,
            "rows": [{"control_class": "matched_frequency_null"}],
        },
        "decision": {
            "hypothesis_decision": "BLOCKED_SAMPLE_SIZE",
            "strategy_decision": "INSUFFICIENT_EVIDENCE",
            "failure_memory_update": {"generated_strategy_id": "qgs_fixture"},
            "contradiction_update": {"evidence": "oos_sample_size_insufficient_after_ready_cell_execution"},
        },
        "feedback_routing": {"next_action": "launch_data_oos_capacity_expansion"},
        "terminal_outcome": "DATA_OR_OOS_CAPACITY_BLOCKED",
    }

    payload = eep.build_empirical_evidence_pack(repo_root=repo_root, closeout=closeout)

    assert payload["source_hypothesis_id"] == "cross_sectional_momentum_v0"
    assert payload["generated_strategy_id"] == "qgs_fixture"
    assert payload["controlled_evaluation"]["status"] == "AVAILABLE"
    assert payload["walk_forward"]["status"] == "AVAILABLE"
    assert payload["oos"]["status"] == "AVAILABLE"
    assert payload["null_model"]["status"] == "AVAILABLE"
    assert payload["disposition"] == "NEEDS_MORE_EVIDENCE"
    assert payload["recommended_next_action"] == "launch_data_oos_capacity_expansion"
