from __future__ import annotations

import json
from pathlib import Path

from research import qre_empirical_trust_closure as etc


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def test_empirical_trust_closure_materializes_campaign_history_and_acceptance(
    tmp_path: Path,
    monkeypatch,
) -> None:
    _write_json(
        tmp_path / "generated_research/campaign_execution/reports/second_campaign_closeout.v1.json",
        {
            "selection": {
                "dataset_identity": "qds_cross",
                "snapshot_identity": "qsn_cross",
            },
            "campaign_classification": {"new_empirical_campaigns_completed": 1},
            "executed_campaign_cell": "qrcell_cross",
        },
    )
    _write_json(
        tmp_path / "generated_research/campaign_execution/evidence/empirical_evidence_pack.v1.json",
        {
            "campaign_identity": "qcx_cross",
            "campaign_cell_id": "qrcell_cross",
            "generated_strategy_id": "qgs_cross",
            "source_hypothesis_id": "cross_v0",
            "timeframe": "1d",
            "disposition": "NEEDS_MORE_EVIDENCE",
            "recommended_next_action": "launch_data_oos_capacity_expansion",
            "terminal_outcome": "DATA_OR_OOS_CAPACITY_BLOCKED",
            "active_blockers": ["REQUEST_MORE_EVIDENCE"],
            "resolved_blockers": ["DATA_OR_OOS_CAPACITY_BLOCKED"],
            "oos": {"trade_count": 0, "sufficiency": "INSUFFICIENT"},
            "null_model": {"outcome": "FAIL"},
        },
    )
    _write_json(
        tmp_path / "generated_research/registry/generated_strategy_registry.v1.json",
        {
            "rows": [
                {
                    "generated_strategy_id": "qgs_cross",
                    "source_hypothesis_id": "cross_v0",
                    "strategy_spec_id": "qsp_cross",
                    "thesis_id": "qhc_cross",
                },
                {
                    "generated_strategy_id": "qgs_atr",
                    "source_hypothesis_id": "atr_v0",
                    "strategy_spec_id": "qsp_atr",
                    "thesis_id": "qbt_atr",
                },
            ]
        },
    )
    _write_json(
        tmp_path / "generated_research/specs/qsp_cross.json",
        {"behavior_family": "relative_strength", "source_hypothesis_id": "cross_v0"},
    )
    _write_json(
        tmp_path / "generated_research/specs/qsp_atr.json",
        {"behavior_family": "trend_continuation", "source_hypothesis_id": "atr_v0"},
    )
    _write_json(
        tmp_path / "generated_research/readiness/campaigns/automated_portfolio_readiness.v1.json",
        {
            "rows": [
                {
                    "campaign_cell_id": "qrcell_cross",
                    "generated_strategy_id": "qgs_cross",
                    "status": "READY_FOR_PREREGISTRATION",
                    "blockers": [],
                },
                {
                    "campaign_cell_id": "qrcell_atr",
                    "generated_strategy_id": "qgs_atr",
                    "status": "READY_FOR_PREREGISTRATION",
                    "blockers": [],
                },
            ]
        },
    )

    def _fake_execute(repo_root: Path, readiness_row: dict, history_rows: list[dict]):
        closeout = {
            "selection": {
                "dataset_identity": "qds_atr",
                "snapshot_identity": "qsn_atr",
            }
        }
        pack = {
            "campaign_identity": "qcx_atr",
            "campaign_cell_id": "qrcell_atr",
            "generated_strategy_id": "qgs_atr",
            "source_hypothesis_id": "atr_v0",
            "timeframe": "4h",
            "disposition": "NEEDS_MORE_EVIDENCE",
            "recommended_next_action": "launch_data_oos_capacity_expansion",
            "terminal_outcome": "DATA_OR_OOS_CAPACITY_BLOCKED",
            "active_blockers": ["REQUEST_MORE_EVIDENCE"],
            "resolved_blockers": ["DATA_OR_OOS_CAPACITY_BLOCKED"],
            "oos": {"trade_count": 2, "sufficiency": "INSUFFICIENT"},
            "null_model": {"outcome": "FAIL"},
        }
        history_row = etc._history_row(
            repo_root=repo_root,
            closeout=closeout,
            pack=pack,
            novelty_type="NEW_CAMPAIGN_CELL",
            prior_campaign_identity="",
            expected_information_gain="new_real_oos_evidence_for_distinct_strategy_cell",
            falsification_condition="bounded",
            new_this_run=True,
        )
        return closeout, pack, history_row

    monkeypatch.setattr(etc, "_execute_campaign", _fake_execute)
    monkeypatch.setattr(etc, "validate_write_target", lambda path: None)

    payload = etc.run_empirical_trust_closure(repo_root=tmp_path, write_outputs=True, max_new_campaigns=1)

    history = json.loads((tmp_path / etc.CAMPAIGN_HISTORY_PATH).read_text(encoding="utf-8"))
    acceptance = json.loads((tmp_path / etc.ACCEPTANCE_PATH).read_text(encoding="utf-8"))
    assert len(history["rows"]) == 2
    assert history["summary"]["new_real_empirical_campaigns_executed_this_run"] == 1
    assert payload["execution_summary"]["summary"]["new_real_campaigns"] == 1
    assert acceptance["summary"]["evidence_changing_acceptance_cycle_count"] == 1
    assert acceptance["summary"]["deterministic_acceptance_replay_count"] == 3
