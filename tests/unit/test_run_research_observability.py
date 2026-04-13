from __future__ import annotations

import csv
import json
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

from research import run_research as run_research_module
from research.empty_run_reporting import DegenerateResearchRunError
from research.results import make_result_row, write_latest_json, write_results_to_csv


AS_OF_UTC = datetime(2026, 4, 13, 12, 0, 0, tzinfo=UTC)
ROW_SCHEMA = list(
    make_result_row(
        strategy={"name": "schema", "family": "trend", "hypothesis": "schema"},
        asset="BTC-USD",
        interval="1d",
        params={},
        as_of_utc=AS_OF_UTC,
        metrics={},
    ).keys()
)


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
            [SimpleNamespace(symbol="BTC-USD")],
            ["1d"],
            lambda interval: ("2026-01-01", "2026-02-01"),
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
    monkeypatch.setattr(run_research_module, "_write_provenance_sidecar", lambda **kwargs: None)
    monkeypatch.setattr(run_research_module, "_write_statistical_defensibility_sidecar", lambda **kwargs: None)
    monkeypatch.setattr(run_research_module, "_write_candidate_registry", lambda **kwargs: None)
    monkeypatch.setattr(run_research_module, "_write_portfolio_aggregation_sidecar", lambda **kwargs: None)
    monkeypatch.setattr(run_research_module, "_write_regime_diagnostics_sidecar", lambda **kwargs: None)
    monkeypatch.setattr(
        run_research_module,
        "write_results_to_csv",
        lambda rows: write_results_to_csv(rows, path=tmp_path / "research" / "strategy_matrix.csv"),
    )
    monkeypatch.setattr(
        run_research_module,
        "write_latest_json",
        lambda rows, as_of_utc: write_latest_json(
            rows,
            as_of_utc=as_of_utc,
            path=tmp_path / "research" / "research_latest.json",
        ),
    )


class _HealthyEngine:
    def __init__(self, start_datum, eind_datum, evaluation_config=None, regime_config=None):
        self.start = start_datum
        self.end = eind_datum
        self._provenance_events = []
        self.last_evaluation_report = None

    def inspect_asset_readiness(self, assets, interval):
        return [
            {
                "asset": asset,
                "interval": interval,
                "requested_start": self.start,
                "requested_end": self.end,
                "bar_count": 700,
                "fold_count": 2,
                "status": "evaluable",
                "drop_reason": None,
            }
            for asset in assets
        ]

    def grid_search(self, strategie_factory, param_grid, assets, interval="1d"):
        self.last_evaluation_report = {
            "evaluation_config": {
                "mode": "anchored",
                "selection_metric": "sharpe",
                "initial_train_bars": 500,
                "test_bars": 100,
                "step_bars": 100,
            },
            "selection_metric": "sharpe",
            "selected_params": {"periode": 14},
            "is_summary": {
                "win_rate": 0.6,
                "sharpe": 1.2,
                "deflated_sharpe": 1.0,
                "max_drawdown": 0.1,
                "trades_per_maand": 3.0,
                "consistentie": 0.7,
                "totaal_trades": 12,
                "goedgekeurd": True,
                "criteria_checks": {},
            },
            "oos_summary": {
                "win_rate": 0.55,
                "sharpe": 1.1,
                "deflated_sharpe": 0.9,
                "max_drawdown": 0.12,
                "trades_per_maand": 2.5,
                "consistentie": 0.65,
                "totaal_trades": 12,
                "goedgekeurd": True,
                "criteria_checks": {},
            },
            "folds": [{"train": [0, 499], "test": [500, 599], "leakage_ok": True}],
            "leakage_checks_ok": True,
            "evaluation_samples": {
                "daily_returns": [0.01, -0.005, 0.003],
                "trade_pnls": [0.02, -0.01],
                "monthly_returns": [0.008],
            },
            "evaluation_streams": {
                "oos_daily_returns": [
                    {"timestamp_utc": "2026-01-02T00:00:00+00:00", "return": 0.01},
                    {"timestamp_utc": "2026-01-03T00:00:00+00:00", "return": -0.005},
                    {"timestamp_utc": "2026-01-04T00:00:00+00:00", "return": 0.003},
                ],
                "oos_bar_returns": [],
                "oos_trade_events": [],
            },
            "sample_statistics": {
                "daily_returns": {"count": 3, "mean": 0.0027, "std": 0.006, "skew": 0.0, "kurt": 3.0},
            },
        }
        return {
            "beste_params": {"periode": 14},
            "win_rate": 0.55,
            "sharpe": 1.1,
            "deflated_sharpe": 0.9,
            "max_drawdown": 0.12,
            "trades_per_maand": 2.5,
            "consistentie": 0.65,
            "totaal_trades": 12,
            "goedgekeurd": True,
            "criteria_checks": {},
            "reden": "",
        }


class _DegenerateEngine:
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
        raise AssertionError("grid_search should not run for preflight failure")


def test_run_research_writes_completed_progress_sidecar_and_keeps_public_schema(monkeypatch, tmp_path: Path):
    _patch_common_runner(monkeypatch, tmp_path, _HealthyEngine)

    run_research_module.run_research()

    progress = _load_json(tmp_path / "research" / "run_progress_latest.v1.json")
    public_json = _load_json(tmp_path / "research" / "research_latest.json")
    with (tmp_path / "research" / "strategy_matrix.csv").open(encoding="utf-8", newline="") as handle:
        csv_rows = list(csv.DictReader(handle))

    assert progress["version"] == "v1"
    assert progress["status"] == "completed"
    assert progress["current_stage"] == "completed"
    assert progress["progress"] == {"completed": 1, "total": 1, "percent": 100.0}
    assert progress["failure"] is None
    assert list(public_json["results"][0].keys()) == ROW_SCHEMA
    assert list(csv_rows[0].keys()) == ROW_SCHEMA


def test_run_research_marks_failed_progress_sidecar_on_degenerate_run(monkeypatch, tmp_path: Path):
    _patch_common_runner(monkeypatch, tmp_path, _DegenerateEngine)

    with pytest.raises(DegenerateResearchRunError, match="preflight_no_evaluable_pairs"):
        run_research_module.run_research()

    progress = _load_json(tmp_path / "research" / "run_progress_latest.v1.json")
    assert progress["status"] == "failed"
    assert progress["current_stage"] == "failed"
    assert progress["failure"]["failure_stage"] == "preflight"
    assert progress["failure"]["error_type"] == "DegenerateResearchRunError"
