import json
from datetime import UTC, datetime
from pathlib import Path

from data.contracts import Provenance
from research import run_research as run_research_module
from research.results import write_latest_json, write_results_to_csv


class FakeEngine:
    def __init__(self, start_datum, eind_datum):
        self.start = start_datum
        self.eind = eind_datum
        self._provenance_events = [
            Provenance(
                adapter="fake-adapter",
                fetched_at_utc=datetime(2026, 4, 8, 10, 59, 31, 381566, tzinfo=UTC),
                config_hash="fake-config-hash",
                source_version="1.0",
                cache_hit=False,
            )
        ]

    def grid_search(self, strategie_factory, param_grid, assets, interval="1d"):
        return {
            "beste_params": {"periode": 14},
            "win_rate": 0.55,
            "sharpe": 1.234,
            "deflated_sharpe": 1.111,
            "max_drawdown": 0.12,
            "trades_per_maand": 2.5,
            "consistentie": 0.75,
            "totaal_trades": 12,
            "goedgekeurd": True,
            "criteria_checks": {
                "consistentie": True,
                "deflated_sharpe": True,
                "max_drawdown": True,
                "trades_per_maand": True,
                "win_rate": True,
            },
            "reden": "",
        }


def test_research_outputs_remain_schema_stable(monkeypatch, tmp_path):
    monkeypatch.setattr(run_research_module, "BacktestEngine", FakeEngine)
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
            [type("Asset", (), {"symbol": "BTC-USD"})()],
            ["1d"],
            lambda interval: ("2026-01-01", "2026-02-01"),
            datetime(2026, 4, 8, 10, 59, 31, 381566, tzinfo=UTC),
        ),
    )
    monkeypatch.setattr(run_research_module, "load_research_config", lambda config_path="config/config.yaml": {})
    monkeypatch.setattr(run_research_module, "_git_revision", lambda: "deadbeef")
    monkeypatch.chdir(tmp_path)
    (tmp_path / "research").mkdir()

    monkeypatch.setattr(
        run_research_module,
        "write_results_to_csv",
        lambda rows: write_results_to_csv(rows, path=tmp_path / "research" / "strategy_matrix.csv"),
    )
    monkeypatch.setattr(
        run_research_module,
        "write_latest_json",
        lambda rows, as_of_utc: write_latest_json(rows, as_of_utc=as_of_utc, path=tmp_path / "research" / "research_latest.json"),
    )

    run_research_module.run_research()

    fixtures_dir = Path(__file__).resolve().parents[1] / "fixtures" / "research_schema_stability"
    expected_csv = (fixtures_dir / "strategy_matrix.csv").read_text(encoding="utf-8")
    expected_json = json.loads(
        (fixtures_dir / "research_latest.json").read_text(encoding="utf-8")
    )
    actual_csv = (tmp_path / "research" / "strategy_matrix.csv").read_text(encoding="utf-8").replace("\r\n", "\n")
    actual_json = json.loads((tmp_path / "research" / "research_latest.json").read_text(encoding="utf-8"))

    assert actual_csv == expected_csv
    assert actual_json == expected_json
