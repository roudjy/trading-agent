from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

from research import run_research as run_research_module
from research.empty_run_reporting import DegenerateResearchRunError


AS_OF_UTC = datetime(2026, 4, 13, 12, 0, 0, tzinfo=UTC)


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _patch_common_runner(monkeypatch, tmp_path: Path, engine_cls) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / "research").mkdir()
    monkeypatch.setattr(run_research_module, "BacktestEngine", engine_cls)
    monkeypatch.setattr(
        run_research_module,
        "get_enabled_strategies",
        lambda: [
            {
                "name": "fake_strategy",
                "family": "trend",
                "strategy_family": "trend_following",
                "position_structure": "outright",
                "initial_lane_support": "supported",
                "hypothesis": "Fixture hypothesis",
                "factory": lambda **params: None,
                "params": {"periode": [14]},
            }
        ],
    )
    monkeypatch.setattr(
        run_research_module,
        "build_research_universe",
        lambda config: (
            [SimpleNamespace(symbol="BTC-USD", asset_type="crypto", asset_class="crypto")],
            ["1h"],
            lambda interval: ("2024-05-13", "2026-04-13"),
            AS_OF_UTC,
            {"version": "v1", "resolved_count": 1},
        ),
    )
    monkeypatch.setattr(
        run_research_module,
        "load_research_config",
        lambda config_path="config/config.yaml": {},
    )
    monkeypatch.setattr(run_research_module, "_git_revision", lambda: "deadbeef")


class _EligibilityDegenerateEngine:
    def __init__(self, start_datum, eind_datum, evaluation_config=None, regime_config=None):
        self.start = start_datum
        self.eind = eind_datum
        self._provenance_events = []
        self.last_evaluation_report = None

    def inspect_asset_readiness(self, assets, interval):
        return [
            {
                "asset": asset,
                "interval": interval,
                "requested_start": self.start,
                "requested_end": self.eind,
                "bar_count": 0,
                "fold_count": 0,
                "status": "dropped",
                "drop_reason": "empty_dataset",
            }
            for asset in assets
        ]

    def grid_search(self, strategie_factory, param_grid, assets, interval="1d"):
        raise AssertionError("grid_search should not run when eligibility has zero candidates")


class _PostRunDegenerateEngine:
    def __init__(self, start_datum, eind_datum, evaluation_config=None, regime_config=None):
        self.start = start_datum
        self.eind = eind_datum
        self._provenance_events = []
        self.last_evaluation_report = None

    def inspect_asset_readiness(self, assets, interval):
        return [
            {
                "asset": asset,
                "interval": interval,
                "requested_start": self.start,
                "requested_end": self.eind,
                "bar_count": 700,
                "fold_count": 2,
                "status": "evaluable",
                "drop_reason": None,
            }
            for asset in assets
        ]

    def grid_search(self, strategie_factory, param_grid, assets, interval="1d"):
        self.last_evaluation_report = {
            "selection_metric": "sharpe",
            "is_summary": {
                "win_rate": 0.0,
                "sharpe": 0.0,
                "deflated_sharpe": 0.0,
                "max_drawdown": 0.0,
                "trades_per_maand": 0.0,
                "consistentie": 0.0,
                "totaal_trades": 0,
                "goedgekeurd": False,
                "criteria_checks": {},
            },
            "oos_summary": {
                "win_rate": 0.0,
                "sharpe": 0.0,
                "deflated_sharpe": 0.0,
                "max_drawdown": 0.0,
                "trades_per_maand": 0.0,
                "consistentie": 0.0,
                "totaal_trades": 0,
                "goedgekeurd": False,
                "criteria_checks": {},
            },
            "folds": [{"train": [0, 499], "test": [500, 599], "leakage_ok": True}],
            "leakage_checks_ok": True,
            "evaluation_samples": {
                "daily_returns": [],
                "trade_pnls": [],
                "monthly_returns": [],
            },
            "evaluation_streams": {
                "oos_daily_returns": [],
                "oos_bar_returns": [],
                "oos_trade_events": [],
            },
            "sample_statistics": {
                "daily_returns": {"count": 0, "mean": 0.0, "std": 0.0, "skew": 0.0, "kurt": 0.0},
                "trade_pnls": {"count": 0, "mean": 0.0, "std": 0.0, "skew": 0.0, "kurt": 0.0},
                "monthly_returns": {"count": 0, "mean": 0.0, "std": 0.0, "skew": 0.0, "kurt": 0.0},
            },
        }
        return {
            "beste_params": {"periode": 14},
            "win_rate": 0.0,
            "sharpe": 0.0,
            "deflated_sharpe": 0.0,
            "max_drawdown": 0.0,
            "trades_per_maand": 0.0,
            "consistentie": 0.0,
            "totaal_trades": 0,
            "goedgekeurd": False,
            "criteria_checks": {},
            "reden": "Te weinig trades: 0",
        }


class _ScreeningDegenerateEngine:
    def __init__(self, start_datum, eind_datum, evaluation_config=None, regime_config=None):
        self.start = start_datum
        self.eind = eind_datum
        self._provenance_events = []
        self.last_evaluation_report = None

    def inspect_asset_readiness(self, assets, interval):
        return [
            {
                "asset": asset,
                "interval": interval,
                "requested_start": self.start,
                "requested_end": self.eind,
                "bar_count": 700,
                "fold_count": 2,
                "status": "evaluable",
                "drop_reason": None,
            }
            for asset in assets
        ]

    def run(self, strategie_func, assets, interval="1d"):
        self.last_evaluation_report = {
            "evaluation_samples": {
                "daily_returns": [0.01, -0.005, 0.003],
                "trade_pnls": [0.02, -0.01],
                "monthly_returns": [0.008],
            }
        }
        return {
            "win_rate": 0.45,
            "sharpe": -0.2,
            "deflated_sharpe": -0.1,
            "max_drawdown": 0.12,
            "trades_per_maand": 2.5,
            "consistentie": 0.3,
            "totaal_trades": 12,
            "goedgekeurd": False,
            "criteria_checks": {},
            "reden": "",
        }

    def grid_search(self, strategie_factory, param_grid, assets, interval="1d"):
        raise AssertionError("grid_search should not run when screening has zero survivors")


def test_run_research_fails_fast_before_public_outputs_when_eligibility_is_empty(monkeypatch, tmp_path):
    _patch_common_runner(monkeypatch, tmp_path, _EligibilityDegenerateEngine)

    with pytest.raises(DegenerateResearchRunError, match="eligibility_no_candidates"):
        run_research_module.run_research()

    diagnostics = _load_json(tmp_path / "research" / "empty_run_diagnostics_latest.v1.json")
    filter_summary = _load_json(tmp_path / "research" / "run_filter_summary_latest.v1.json")
    assert diagnostics["failure_stage"] == "eligibility_no_candidates"
    assert diagnostics["summary"]["evaluable_pair_count"] == 0
    assert diagnostics["summary"]["primary_drop_reasons"] == ["empty_dataset"]
    assert filter_summary["eligibility_rejection_reasons"] == {"empty_dataset": 1}
    assert not (tmp_path / "research" / "research_latest.json").exists()
    assert not (tmp_path / "research" / "strategy_matrix.csv").exists()


def test_run_research_fails_fast_before_public_outputs_when_oos_samples_are_empty(monkeypatch, tmp_path):
    _patch_common_runner(monkeypatch, tmp_path, _PostRunDegenerateEngine)

    with pytest.raises(DegenerateResearchRunError, match="postrun_no_oos_daily_returns"):
        run_research_module.run_research()

    diagnostics = _load_json(tmp_path / "research" / "empty_run_diagnostics_latest.v1.json")
    assert diagnostics["failure_stage"] == "postrun_no_oos_daily_returns"
    assert diagnostics["summary"]["evaluable_pair_count"] == 1
    assert diagnostics["summary"]["evaluations_count"] == 1
    assert diagnostics["summary"]["evaluations_with_oos_daily_returns"] == 0
    assert not (tmp_path / "research" / "research_latest.json").exists()
    assert not (tmp_path / "research" / "strategy_matrix.csv").exists()


def test_run_research_fails_fast_before_public_outputs_when_screening_has_no_survivors(monkeypatch, tmp_path):
    _patch_common_runner(monkeypatch, tmp_path, _ScreeningDegenerateEngine)

    with pytest.raises(DegenerateResearchRunError, match="screening_no_survivors"):
        run_research_module.run_research()

    diagnostics = _load_json(tmp_path / "research" / "empty_run_diagnostics_latest.v1.json")
    filter_summary = _load_json(tmp_path / "research" / "run_filter_summary_latest.v1.json")
    assert diagnostics["failure_stage"] == "screening_no_survivors"
    assert filter_summary["summary"]["screening_rejected_count"] == 1
    assert filter_summary["screening_rejection_reasons"] == {"screening_criteria_not_met": 1}
    assert not (tmp_path / "research" / "research_latest.json").exists()
    assert not (tmp_path / "research" / "strategy_matrix.csv").exists()
