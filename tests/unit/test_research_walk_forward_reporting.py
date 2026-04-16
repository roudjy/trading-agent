from __future__ import annotations

import csv
import json
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

from agent.backtesting.engine import FoldLeakageError
from research import run_research as run_research_module
from research.results import make_result_row, write_latest_json, write_results_to_csv

AS_OF_UTC = datetime(2026, 4, 8, 10, 59, 31, 381566, tzinfo=UTC)
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
FORBIDDEN_PUBLIC_KEYS = {
    "is_sharpe",
    "train_sharpe",
    "insample_sharpe",
    "is_summary",
    "oos_summary",
}


def _metrics() -> dict:
    return {
        "beste_params": {"periode": 14},
        "win_rate": 0.35,
        "sharpe": -1.5,
        "deflated_sharpe": -1.24,
        "max_drawdown": 0.22,
        "trades_per_maand": 2.5,
        "consistentie": 0.25,
        "totaal_trades": 12,
        "goedgekeurd": False,
        "criteria_checks": {
            "consistentie": False,
            "deflated_sharpe": False,
            "max_drawdown": True,
            "trades_per_maand": True,
            "win_rate": False,
        },
        "reden": "",
    }


def _report(evaluation_config: dict, leakage_checks_ok: bool = True) -> dict:
    return {
        "evaluation_config": evaluation_config,
        "selection_metric": "sharpe",
        "selected_params": {"periode": 14},
        "is_summary": {
            "win_rate": 0.7,
            "sharpe": 2.4,
            "deflated_sharpe": 1.987,
            "max_drawdown": 0.08,
            "trades_per_maand": 2.5,
            "consistentie": 0.75,
            "totaal_trades": 12,
            "goedgekeurd": True,
            "criteria_checks": {},
        },
        "oos_summary": {
            "win_rate": 0.35,
            "sharpe": -1.5,
            "deflated_sharpe": -1.24,
            "max_drawdown": 0.22,
            "trades_per_maand": 2.5,
            "consistentie": 0.25,
            "totaal_trades": 12,
            "goedgekeurd": False,
            "criteria_checks": {},
        },
        "folds": [
            {"train": [0, 69], "test": [70, 99], "leakage_ok": leakage_checks_ok},
        ],
        "leakage_checks_ok": leakage_checks_ok,
        "evaluation_samples": {
            "daily_returns": [0.01, -0.005, 0.003],
            "trade_pnls": [0.02, -0.01],
            "monthly_returns": [0.008],
        },
        "sample_statistics": {
            "daily_returns": {"count": 3, "mean": 0.0027, "std": 0.006, "skew": 0.0, "kurt": 3.0},
        },
    }


class FakeEngine:
    def __init__(self, start_datum, eind_datum, evaluation_config=None):
        self.start = start_datum
        self.end = eind_datum
        self.evaluation_config = evaluation_config or {}
        self._provenance_events = []
        self.last_evaluation_report = None

    def grid_search(self, strategie_factory, param_grid, assets, interval="1d"):
        self.last_evaluation_report = _report(self.evaluation_config)
        return _metrics()


class LeakageEngine(FakeEngine):
    def grid_search(self, strategie_factory, param_grid, assets, interval="1d"):
        self.last_evaluation_report = _report(self.evaluation_config, leakage_checks_ok=False)
        return _metrics()


def _patch_runner(monkeypatch, tmp_path: Path, engine_cls=FakeEngine, research_config=None):
    research_config = research_config or {}
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
    monkeypatch.setattr(run_research_module, "load_research_config", lambda config_path="config/config.yaml": research_config)
    monkeypatch.setattr(run_research_module, "_git_revision", lambda: "deadbeef")
    monkeypatch.setattr(run_research_module, "_write_provenance_sidecar", lambda **kwargs: None)
    monkeypatch.setattr(run_research_module, "_write_statistical_defensibility_sidecar", lambda **kwargs: None)
    monkeypatch.setattr(run_research_module, "_write_candidate_registry", lambda **kwargs: None)
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


def _load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def test_sidecar_written_with_v1_schema_and_version_field(monkeypatch, tmp_path):
    _patch_runner(monkeypatch, tmp_path)

    run_research_module.run_research()

    payload = _load_json(tmp_path / "research" / "walk_forward_latest.v1.json")
    assert payload["version"] == "v1"
    assert payload["generated_at_utc"] == AS_OF_UTC.isoformat()
    assert payload["evaluation_config"] == {
        "mode": "anchored",
        "selection_metric": "sharpe",
        "initial_train_bars": 500,
        "test_bars": 100,
        "step_bars": 100,
    }


def test_sidecar_contains_folds_and_leakage_checks_ok(monkeypatch, tmp_path):
    _patch_runner(monkeypatch, tmp_path)

    run_research_module.run_research()

    strategy_entry = _load_json(tmp_path / "research" / "walk_forward_latest.v1.json")["strategies"][0]
    assert strategy_entry["folds"] == [{"train": [0, 69], "test": [70, 99], "leakage_ok": True}]
    assert strategy_entry["leakage_checks_ok"] is True


def test_sidecar_contains_robustness_metadata(monkeypatch, tmp_path):
    _patch_runner(monkeypatch, tmp_path)

    run_research_module.run_research()

    sidecar = _load_json(tmp_path / "research" / "walk_forward_latest.v1.json")
    strategy_entry = sidecar["strategies"][0]
    robustness = strategy_entry["robustness"]
    assert "fold_count" in robustness
    assert "oos_bar_coverage" in robustness
    assert "total_bars_covered" in robustness
    assert "oos_coverage_ratio" in robustness
    assert "robustness_sufficient" in robustness
    assert robustness["fold_count"] == len(strategy_entry["folds"])

    summary = sidecar["robustness_summary"]
    assert "min_robustness_folds" in summary
    assert "strategy_count" in summary
    assert "insufficient_count" in summary
    assert "all_strategies_sufficient" in summary
    assert summary["strategy_count"] == 1


def test_sidecar_separates_is_and_oos_summaries(monkeypatch, tmp_path):
    _patch_runner(monkeypatch, tmp_path)

    run_research_module.run_research()

    strategy_entry = _load_json(tmp_path / "research" / "walk_forward_latest.v1.json")["strategies"][0]
    assert strategy_entry["is_summary"]["sharpe"] == 2.4
    assert strategy_entry["oos_summary"]["sharpe"] == -1.5
    assert strategy_entry["is_summary"] != strategy_entry["oos_summary"]


def test_runner_never_writes_sidecar_on_leakage_failure(monkeypatch, tmp_path):
    _patch_runner(monkeypatch, tmp_path, engine_cls=LeakageEngine)

    with pytest.raises(FoldLeakageError, match="Leakage check failed"):
        run_research_module.run_research()

    assert not (tmp_path / "research" / "walk_forward_latest.v1.json").exists()


def test_public_research_outputs_remain_oos_only(monkeypatch, tmp_path):
    _patch_runner(monkeypatch, tmp_path)

    run_research_module.run_research()

    public_json = _load_json(tmp_path / "research" / "research_latest.json")
    sidecar = _load_json(tmp_path / "research" / "walk_forward_latest.v1.json")
    with (tmp_path / "research" / "strategy_matrix.csv").open(encoding="utf-8", newline="") as handle:
        csv_rows = list(csv.DictReader(handle))

    public_row = public_json["results"][0]
    assert list(public_row.keys()) == ROW_SCHEMA
    assert list(csv_rows[0].keys()) == ROW_SCHEMA
    assert not any(key in FORBIDDEN_PUBLIC_KEYS for key in public_row)
    assert not any(
        key.startswith(("is_", "train_", "insample"))
        for key in public_row
    )
    assert public_row["sharpe"] == sidecar["strategies"][0]["oos_summary"]["sharpe"]
    assert sidecar["strategies"][0]["is_summary"]["sharpe"] == 2.4
    assert sidecar["strategies"][0]["is_summary"]["sharpe"] != public_row["sharpe"]


def test_schema_stability_csv_and_json_bytes_unchanged_by_framework_change(tmp_path):
    row = make_result_row(
        strategy={"name": "fake_strategy", "family": "trend", "hypothesis": "Fixture hypothesis"},
        asset="BTC-USD",
        interval="1d",
        params={"periode": 14},
        as_of_utc=AS_OF_UTC,
        metrics=_metrics(),
    )
    csv_path = tmp_path / "strategy_matrix.csv"
    json_path = tmp_path / "research_latest.json"

    write_results_to_csv([row], path=csv_path)
    write_latest_json([row], as_of_utc=AS_OF_UTC, path=json_path)

    with csv_path.open(encoding="utf-8", newline="") as handle:
        csv_rows = list(csv.DictReader(handle))
    json_payload = _load_json(json_path)

    assert list(csv_rows[0].keys()) == ROW_SCHEMA
    assert list(json_payload["results"][0].keys()) == ROW_SCHEMA

