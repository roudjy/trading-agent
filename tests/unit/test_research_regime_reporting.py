import csv
import json
from datetime import UTC, datetime
from pathlib import Path

from research import run_research as run_research_module
from research.regime_reporting import build_regime_diagnostics_payload
from research.results import make_result_row, write_latest_json, write_results_to_csv

AS_OF_UTC = datetime(2026, 4, 14, 10, 0, 0, tzinfo=UTC)
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


def _evaluation() -> dict:
    row = make_result_row(
        strategy={"name": "trend_fast", "family": "trend", "hypothesis": "trend hypothesis"},
        asset="BTC-USD",
        interval="1d",
        params={"fast": 10},
        as_of_utc=AS_OF_UTC,
        metrics={
            "win_rate": 0.6,
            "sharpe": 0.5,
            "deflated_sharpe": 0.4,
            "max_drawdown": 0.1,
            "trades_per_maand": 3.0,
            "consistentie": 0.7,
            "totaal_trades": 2,
            "goedgekeurd": True,
            "criteria_checks": {},
            "reden": "",
        },
    )
    return {
        "family": "trend",
        "interval": "1d",
        "selected_params": {"fast": 10},
        "row": row,
        "evaluation_report": {
            "selection_metric": "sharpe",
            "is_summary": {},
            "oos_summary": {},
            "folds": [],
            "leakage_checks_ok": True,
            "evaluation_samples": {
                "daily_returns": [0.01, -0.02, 0.0],
                "trade_pnls": [0.03, -0.01],
                "monthly_returns": [-0.01],
            },
            "evaluation_streams": {
                "oos_bar_returns": [
                    {
                        "timestamp_utc": "2026-01-02T00:00:00+00:00",
                        "asset": "BTC-USD",
                        "fold_index": 0,
                        "return": 0.01,
                        "trend_regime": "trending",
                        "volatility_regime": "low_vol",
                        "combined_regime": "trending|low_vol",
                    },
                    {
                        "timestamp_utc": "2026-01-03T00:00:00+00:00",
                        "asset": "BTC-USD",
                        "fold_index": 0,
                        "return": -0.02,
                        "trend_regime": "trending",
                        "volatility_regime": "high_vol",
                        "combined_regime": "trending|high_vol",
                    },
                    {
                        "timestamp_utc": "2026-01-04T00:00:00+00:00",
                        "asset": "BTC-USD",
                        "fold_index": 1,
                        "return": 0.0,
                        "trend_regime": "non_trending",
                        "volatility_regime": "low_vol",
                        "combined_regime": "non_trending|low_vol",
                    },
                ],
                "oos_trade_events": [
                    {
                        "asset": "BTC-USD",
                        "fold_index": 0,
                        "side": "long",
                        "entry_decision_timestamp_utc": "2026-01-01T00:00:00+00:00",
                        "entry_timestamp_utc": "2026-01-02T00:00:00+00:00",
                        "exit_timestamp_utc": "2026-01-03T00:00:00+00:00",
                        "pnl": 0.03,
                        "entry_trend_regime": "trending",
                        "entry_volatility_regime": "low_vol",
                        "entry_combined_regime": "trending|low_vol",
                    },
                    {
                        "asset": "BTC-USD",
                        "fold_index": 1,
                        "side": "long",
                        "entry_decision_timestamp_utc": "2026-01-03T00:00:00+00:00",
                        "entry_timestamp_utc": "2026-01-04T00:00:00+00:00",
                        "exit_timestamp_utc": "2026-01-05T00:00:00+00:00",
                        "pnl": -0.01,
                        "entry_trend_regime": "non_trending",
                        "entry_volatility_regime": "low_vol",
                        "entry_combined_regime": "non_trending|low_vol",
                    },
                ],
            },
            "sample_statistics": {
                "daily_returns": {
                    "count": 3,
                    "mean": -0.0033333333333333335,
                    "std": 0.012472191289246473,
                    "skew": 0.0,
                    "kurt": 3.0,
                }
            },
        },
    }


def test_build_regime_diagnostics_payload_is_deterministic_and_reconciles_totals():
    evaluations = [_evaluation()]

    first = build_regime_diagnostics_payload(
        evaluations=evaluations,
        as_of_utc=AS_OF_UTC,
        git_revision="deadbeef",
        config_hash="abc123",
        evaluation_config={"mode": "anchored", "selection_metric": "sharpe"},
        regime_config={
            "trend_lookback_bars": 3,
            "volatility_lookback_bars": 3,
            "volatility_baseline_lookback_bars": 3,
            "trend_strength_threshold": 0.5,
            "high_vol_ratio_threshold": 1.5,
        },
    )
    second = build_regime_diagnostics_payload(
        evaluations=evaluations,
        as_of_utc=AS_OF_UTC,
        git_revision="deadbeef",
        config_hash="abc123",
        evaluation_config={"mode": "anchored", "selection_metric": "sharpe"},
        regime_config={
            "trend_lookback_bars": 3,
            "volatility_lookback_bars": 3,
            "volatility_baseline_lookback_bars": 3,
            "trend_strength_threshold": 0.5,
            "high_vol_ratio_threshold": 1.5,
        },
    )

    assert first == second
    assert first["version"] == "v1"
    assert first["lineage"]["config_hash"] == "abc123"
    assert first["regime_definitions"]["trend_regime"]["labels"] == ["trending", "non_trending", "unknown"]

    asset_entry = first["assets"][0]
    assert asset_entry["oos_bar_count"] == 3
    assert asset_entry["reconciliation"]["combined_coverage_matches_total"] is True

    strategy_entry = first["strategies"][0]
    assert strategy_entry["totals"]["oos_bar_count"] == 3
    assert strategy_entry["totals"]["oos_trade_count"] == 2
    assert strategy_entry["reconciliation"]["combined_coverage_matches_total"] is True
    assert strategy_entry["reconciliation"]["combined_trade_counts_match_total"] is True
    assert strategy_entry["reconciliation"]["combined_return_contribution_matches_total"] is True
    high_vol_entry = next(
        item for item in strategy_entry["regime_breakdown"]["combined"] if item["label"] == "trending|high_vol"
    )
    assert high_vol_entry["coverage_count"] == 1
    assert high_vol_entry["return_metrics"]["sharpe"] is None
    assert high_vol_entry["return_metrics"]["validity"]["sharpe_valid"] is False


class _RegimeEngine:
    def __init__(self, start_datum, eind_datum, evaluation_config=None, regime_config=None):
        self.start = start_datum
        self.end = eind_datum
        self._provenance_events = []
        self.last_evaluation_report = None

    def grid_search(self, strategie_factory, param_grid, assets, interval="1d"):
        self.last_evaluation_report = _evaluation()["evaluation_report"]
        return {
            "beste_params": {"fast": 10},
            "win_rate": 0.6,
            "sharpe": 0.5,
            "deflated_sharpe": 0.4,
            "max_drawdown": 0.1,
            "trades_per_maand": 3.0,
            "consistentie": 0.7,
            "totaal_trades": 2,
            "goedgekeurd": True,
            "criteria_checks": {},
            "reden": "",
        }


def test_run_research_writes_regime_sidecar_without_public_schema_changes(monkeypatch, tmp_path: Path):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "research").mkdir()
    monkeypatch.setattr(run_research_module, "BacktestEngine", _RegimeEngine)
    monkeypatch.setattr(
        run_research_module,
        "get_enabled_strategies",
        lambda: [
            {
                "name": "trend_fast",
                "family": "trend",
                "hypothesis": "trend hypothesis",
                "factory": lambda **params: None,
                "params": {"fast": [10]},
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
            AS_OF_UTC,
            {"version": "v1", "resolved_count": 1},
        ),
    )
    monkeypatch.setattr(
        run_research_module,
        "load_research_config",
        lambda config_path="config/config.yaml": {"regime_diagnostics": {"trend_lookback_bars": 3}},
    )
    monkeypatch.setattr(run_research_module, "_git_revision", lambda: "deadbeef")
    monkeypatch.setattr(run_research_module, "_write_provenance_sidecar", lambda **kwargs: None)
    monkeypatch.setattr(run_research_module, "_write_walk_forward_sidecar", lambda **kwargs: None)
    monkeypatch.setattr(run_research_module, "_write_statistical_defensibility_sidecar", lambda **kwargs: None)
    monkeypatch.setattr(run_research_module, "_write_candidate_registry", lambda **kwargs: None)
    monkeypatch.setattr(run_research_module, "_write_portfolio_aggregation_sidecar", lambda **kwargs: None)
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

    run_research_module.run_research()

    public_json = json.loads((tmp_path / "research" / "research_latest.json").read_text(encoding="utf-8"))
    sidecar = json.loads((tmp_path / "research" / "regime_diagnostics_latest.v1.json").read_text(encoding="utf-8"))
    with (tmp_path / "research" / "strategy_matrix.csv").open(encoding="utf-8", newline="") as handle:
        csv_rows = list(csv.DictReader(handle))

    assert list(public_json["results"][0].keys()) == ROW_SCHEMA
    assert list(csv_rows[0].keys()) == ROW_SCHEMA
    assert sidecar["version"] == "v1"
    assert sidecar["strategies"][0]["strategy_name"] == "trend_fast"
    assert sidecar["strategies"][0]["reconciliation"]["combined_trade_counts_match_total"] is True
