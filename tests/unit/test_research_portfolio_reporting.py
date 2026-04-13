import csv
import json
from datetime import UTC, datetime
from pathlib import Path

from research import run_research as run_research_module
from research.portfolio_reporting import build_portfolio_aggregation_payload
from research.results import make_result_row, write_latest_json, write_results_to_csv

AS_OF_UTC = datetime(2026, 4, 13, 8, 0, 0, tzinfo=UTC)
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


def _stream(points):
    return [
        {"timestamp_utc": timestamp, "return": value}
        for timestamp, value in points
    ]


def _evaluation(strategy_name, family, asset, params, stream_points):
    row = make_result_row(
        strategy={"name": strategy_name, "family": family, "hypothesis": f"{strategy_name} hypothesis"},
        asset=asset,
        interval="1d",
        params=params,
        as_of_utc=AS_OF_UTC,
        metrics={
            "win_rate": 0.6,
            "sharpe": 0.5,
            "deflated_sharpe": 0.4,
            "max_drawdown": 0.1,
            "trades_per_maand": 3.0,
            "consistentie": 0.7,
            "totaal_trades": 12,
            "goedgekeurd": True,
            "criteria_checks": {},
            "reden": "",
        },
    )
    return {
        "family": family,
        "interval": "1d",
        "selected_params": params,
        "row": row,
        "evaluation_report": {
            "evaluation_streams": {
                "oos_daily_returns": _stream(stream_points),
            }
        },
    }


def test_build_portfolio_payload_creates_deterministic_views_and_alignment_metadata():
    evaluations = [
        _evaluation(
            "trend_fast",
            "trend",
            "BTC-USD",
            {"fast": 10},
            [
                ("2026-01-02T00:00:00+00:00", 0.01),
                ("2026-01-03T00:00:00+00:00", 0.0),
                ("2026-01-04T00:00:00+00:00", 0.02),
            ],
        ),
        _evaluation(
            "mean_basic",
            "mean_reversion",
            "BTC-USD",
            {"period": 14},
            [
                ("2026-01-03T00:00:00+00:00", -0.01),
                ("2026-01-04T00:00:00+00:00", 0.01),
                ("2026-01-05T00:00:00+00:00", 0.0),
            ],
        ),
        _evaluation(
            "trend_slow",
            "trend",
            "ETH-USD",
            {"window": 20},
            [
                ("2026-01-03T00:00:00+00:00", 0.02),
                ("2026-01-04T00:00:00+00:00", -0.01),
                ("2026-01-05T00:00:00+00:00", 0.01),
            ],
        ),
        _evaluation(
            "mean_regime",
            "mean_reversion",
            "ETH-USD",
            {"period": 20},
            [
                ("2026-01-03T00:00:00+00:00", 0.0),
                ("2026-01-04T00:00:00+00:00", 0.01),
                ("2026-01-05T00:00:00+00:00", -0.02),
            ],
        ),
    ]

    first = build_portfolio_aggregation_payload(evaluations, AS_OF_UTC, git_revision="abc123")
    second = build_portfolio_aggregation_payload(evaluations, AS_OF_UTC, git_revision="abc123")

    assert first == second
    assert first["alignment_policy"]["basis"] == "timestamped_oos_daily_returns"
    assert first["summary"]["view_count"] == 3

    all_included = next(view for view in first["views"] if view["view_name"] == "all_included")
    assert all_included["status"] == "ok"
    assert all_included["alignment"]["common_window"] == {
        "start_utc": "2026-01-03T00:00:00+00:00",
        "end_utc": "2026-01-04T00:00:00+00:00",
        "observation_count": 2,
    }
    assert all_included["summary"]["observation_count"] == 2
    assert len(all_included["portfolio_stream"]) == 2
    assert round(all_included["portfolio_stream"][0]["return"], 6) == 0.0025
    assert all_included["sleeves"][0]["contribution"]["contribution_stream"][0]["timestamp_utc"] == "2026-01-03T00:00:00+00:00"
    assert all_included["alignment"]["dropped_observations_total"] == 4

    by_asset = next(view for view in first["views"] if view["view_name"] == "by_asset")
    assert [sleeve["sleeve_key"] for sleeve in by_asset["sleeves"]] == ["BTC-USD", "ETH-USD"]
    assert by_asset["sleeves"][0]["alignment"]["common_window"]["observation_count"] == 2
    assert by_asset["diversification"]["sleeve_keys"] == ["BTC-USD", "ETH-USD"]

    by_family = next(view for view in first["views"] if view["view_name"] == "by_family")
    assert [sleeve["sleeve_key"] for sleeve in by_family["sleeves"]] == ["mean_reversion", "trend"]
    assert by_family["sleeves"][1]["alignment"]["common_window"]["observation_count"] == 2


def test_build_portfolio_payload_makes_missing_streams_and_no_overlap_explicit():
    evaluations = [
        _evaluation(
            "trend_fast",
            "trend",
            "BTC-USD",
            {"fast": 10},
            [("2026-01-02T00:00:00+00:00", 0.01), ("2026-01-03T00:00:00+00:00", 0.02)],
        ),
        _evaluation(
            "trend_slow",
            "trend",
            "ETH-USD",
            {"window": 20},
            [("2026-02-02T00:00:00+00:00", 0.03), ("2026-02-03T00:00:00+00:00", -0.01)],
        ),
        {
            "family": "mean_reversion",
            "interval": "1d",
            "selected_params": {"period": 14},
            "row": make_result_row(
                strategy={"name": "missing_stream", "family": "mean_reversion", "hypothesis": "missing"},
                asset="SOL-USD",
                interval="1d",
                params={"period": 14},
                as_of_utc=AS_OF_UTC,
                metrics={"goedgekeurd": False, "criteria_checks": {}},
            ),
            "evaluation_report": {},
        },
    ]

    payload = build_portfolio_aggregation_payload(evaluations, AS_OF_UTC, git_revision="abc123")
    view = next(item for item in payload["views"] if item["view_name"] == "all_included")

    assert view["status"] == "insufficient_common_support_across_sleeves"
    assert view["summary"]["observation_count"] == 0
    assert view["alignment"]["consequence"].startswith("no portfolio stream available")
    assert any(item["reason"] == "missing_oos_daily_return_stream" for item in view["excluded_runs"])


def test_build_portfolio_payload_excludes_duplicate_oos_daily_return_timestamps():
    evaluations = [
        _evaluation(
            "trend_fast",
            "trend",
            "BTC-USD",
            {"fast": 10},
            [
                ("2026-01-02T00:00:00+00:00", 0.01),
                ("2026-01-02T00:00:00+00:00", 0.02),
            ],
        ),
        _evaluation(
            "trend_slow",
            "trend",
            "ETH-USD",
            {"window": 20},
            [
                ("2026-01-02T00:00:00+00:00", 0.03),
                ("2026-01-03T00:00:00+00:00", -0.01),
            ],
        ),
    ]

    payload = build_portfolio_aggregation_payload(evaluations, AS_OF_UTC, git_revision="abc123")
    view = next(item for item in payload["views"] if item["view_name"] == "all_included")

    assert any(item["reason"] == "duplicate_timestamp_in_oos_daily_return_stream" for item in view["excluded_runs"])
    assert view["included_runs"][0]["asset"] == "ETH-USD"
    assert view["summary"]["observation_count"] == 2


class _PortfolioEngine:
    def __init__(self, start_datum, eind_datum, evaluation_config=None):
        self.start = start_datum
        self.end = eind_datum
        self.evaluation_config = evaluation_config or {}
        self._provenance_events = []
        self.last_evaluation_report = None

    def grid_search(self, strategie_factory, param_grid, assets, interval="1d"):
        self.last_evaluation_report = {
            "selected_params": {"periode": 14},
            "selection_metric": "sharpe",
            "is_summary": {},
            "oos_summary": {},
            "folds": [],
            "leakage_checks_ok": True,
            "evaluation_samples": {
                "daily_returns": [0.01, -0.005, 0.003],
                "trade_pnls": [0.02, -0.01],
                "monthly_returns": [0.01],
            },
            "evaluation_streams": {
                "oos_daily_returns": _stream(
                    [
                        ("2026-01-02T00:00:00+00:00", 0.01),
                        ("2026-01-03T00:00:00+00:00", -0.005),
                        ("2026-01-04T00:00:00+00:00", 0.003),
                    ]
                )
            },
        }
        return {
            "beste_params": {"periode": 14},
            "win_rate": 0.55,
            "sharpe": 1.2,
            "deflated_sharpe": 1.1,
            "max_drawdown": 0.12,
            "trades_per_maand": 2.5,
            "consistentie": 0.75,
            "totaal_trades": 30,
            "goedgekeurd": True,
            "criteria_checks": {},
            "reden": "",
        }


def test_run_research_writes_additive_portfolio_sidecar_without_public_schema_changes(monkeypatch, tmp_path: Path):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "research").mkdir()
    monkeypatch.setattr(run_research_module, "BacktestEngine", _PortfolioEngine)
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
            AS_OF_UTC,
            {"version": "v1", "resolved_count": 1},
        ),
    )
    monkeypatch.setattr(run_research_module, "load_research_config", lambda config_path="config/config.yaml": {})
    monkeypatch.setattr(run_research_module, "_git_revision", lambda: "deadbeef")
    monkeypatch.setattr(run_research_module, "_write_provenance_sidecar", lambda **kwargs: None)
    monkeypatch.setattr(run_research_module, "_write_walk_forward_sidecar", lambda **kwargs: None)
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

    run_research_module.run_research()

    public_json = json.loads((tmp_path / "research" / "research_latest.json").read_text(encoding="utf-8"))
    sidecar = json.loads((tmp_path / "research" / "portfolio_aggregation_latest.v1.json").read_text(encoding="utf-8"))
    with (tmp_path / "research" / "strategy_matrix.csv").open(encoding="utf-8", newline="") as handle:
        csv_rows = list(csv.DictReader(handle))

    assert list(public_json["results"][0].keys()) == ROW_SCHEMA
    assert list(csv_rows[0].keys()) == ROW_SCHEMA
    assert sidecar["version"] == "v1"
    assert sidecar["alignment_policy"]["policy"] == "exact_timestamp_intersection"
    assert sidecar["views"][0]["view_name"] == "all_included"
