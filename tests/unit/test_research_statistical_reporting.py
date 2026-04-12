import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pytest

from research import run_research as run_research_module
from research import statistical_reporting as statistical_reporting_module
from research.results import write_latest_json, write_results_to_csv

AS_OF_UTC = datetime(2026, 4, 11, 10, 0, 0, tzinfo=UTC)
INTERVALS = ["1d", "4h"]
ASSETS = ["BTC-USD", "ETH-USD"]
LEGACY_DEFLATED_SHARPE = 0.812
LEGACY_TRUE_CHECKS = {
    "consistentie": True,
    "deflated_sharpe": True,
    "max_drawdown": True,
    "trades_per_maand": True,
    "win_rate": True,
}
LEGACY_FALSE_CHECKS = {
    "consistentie": False,
    "deflated_sharpe": False,
    "max_drawdown": True,
    "trades_per_maand": True,
    "win_rate": False,
}


def trend_fast_factory(**params):
    return lambda frame: frame


def trend_slow_factory(**params):
    return lambda frame: frame


def mean_basic_factory(**params):
    return lambda frame: frame


STRATEGIES = [
    {
        "name": "trend_fast",
        "family": "trend",
        "hypothesis": "Fast trend hypothesis",
        "factory": trend_fast_factory,
        "params": {"fast": [10, 20], "slow": [50]},
    },
    {
        "name": "trend_slow",
        "family": "trend",
        "hypothesis": "Slow trend hypothesis",
        "factory": trend_slow_factory,
        "params": {"window": [5, 10, 15]},
    },
    {
        "name": "mean_basic",
        "family": "mean_reversion",
        "hypothesis": "Mean reversion hypothesis",
        "factory": mean_basic_factory,
        "params": {"period": [14]},
    },
]

DAILY_RETURNS = {
    "trend_fast_factory": [0.01, -0.01, 0.008, -0.008, 0.006, -0.006],
    "trend_slow_factory": [0.004, -0.012, 0.002, -0.01, 0.001, -0.007],
    "mean_basic_factory": [-0.008, 0.006, -0.007, 0.004, -0.006, 0.003],
}


def _sample_stats(values):
    array = np.asarray(values, dtype=float)
    mean = float(array.mean())
    std = float(array.std())
    if std == 0.0:
        skew = 0.0
        kurt = 3.0
    else:
        centered = (array - mean) / std
        skew = float(np.mean(centered ** 3))
        kurt = float(np.mean(centered ** 4))
    return {"count": int(array.size), "mean": mean, "std": std, "skew": skew, "kurt": kurt}


def _strategies_by_family():
    families = {}
    for strategy in STRATEGIES:
        families.setdefault(strategy["family"], []).append(strategy)
    for family in sorted(families):
        yield family, sorted(families[family], key=lambda strategy: strategy["name"])


class ReportingEngine:
    def __init__(self, start_datum, eind_datum, **kwargs):
        self.start = start_datum
        self.eind = eind_datum
        self._provenance_events = []
        self.last_evaluation_report = {}

    def grid_search(self, strategie_factory, param_grid, assets, interval="1d"):
        strategy_key = strategie_factory.__name__
        daily_returns = DAILY_RETURNS[strategy_key]
        trade_pnls = [value * 2.0 for value in daily_returns]
        monthly_returns = [sum(daily_returns[:3]), sum(daily_returns[3:])]
        selected_params = {name: values[-1] for name, values in param_grid.items()}
        is_approved = strategy_key == "trend_fast_factory"

        self.last_evaluation_report = {
            "evaluation_samples": {
                "daily_returns": list(daily_returns),
                "trade_pnls": trade_pnls,
                "monthly_returns": monthly_returns,
            },
            "sample_statistics": {
                "daily_returns": _sample_stats(daily_returns),
                "trade_pnls": _sample_stats(trade_pnls),
                "monthly_returns": _sample_stats(monthly_returns),
            },
            "selected_params": selected_params,
            "selection_metric": "sharpe",
            "is_summary": {},
            "oos_summary": {},
            "folds": [],
            "leakage_checks_ok": True,
        }
        return {
            "beste_params": selected_params,
            "win_rate": 0.6 if is_approved else 0.35,
            "sharpe": 0.2 if is_approved else -0.15,
            "deflated_sharpe": LEGACY_DEFLATED_SHARPE if is_approved else -0.2,
            "max_drawdown": 0.2 if is_approved else 0.25,
            "trades_per_maand": 4.0 if is_approved else 3.0,
            "consistentie": 0.7 if is_approved else 0.2,
            "totaal_trades": 24,
            "goedgekeurd": is_approved,
            "criteria_checks": LEGACY_TRUE_CHECKS if is_approved else LEGACY_FALSE_CHECKS,
            "reden": "",
        }


def _run_reporting(monkeypatch, tmp_path, research_config=None):
    monkeypatch.setattr(run_research_module, "BacktestEngine", ReportingEngine)
    monkeypatch.setattr(run_research_module, "get_enabled_strategies", lambda: STRATEGIES)
    monkeypatch.setattr(statistical_reporting_module, "iter_strategy_families", _strategies_by_family)
    monkeypatch.setattr(
        run_research_module,
        "build_research_universe",
        lambda config: (
            [type("Asset", (), {"symbol": symbol})() for symbol in ASSETS],
            INTERVALS,
            lambda interval: ("2024-01-01", "2024-12-31"),
            AS_OF_UTC,
        ),
    )
    monkeypatch.setattr(run_research_module, "load_research_config", lambda config_path="config/config.yaml": research_config or {})
    monkeypatch.setattr(run_research_module, "_write_provenance_sidecar", lambda **kwargs: None)
    monkeypatch.setattr(run_research_module, "_write_walk_forward_sidecar", lambda **kwargs: None)

    tmp_path.mkdir(parents=True, exist_ok=True)
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
    public_payload = json.loads((tmp_path / "research" / "research_latest.json").read_text(encoding="utf-8"))
    sidecar_path = tmp_path / "research" / "statistical_defensibility_latest.v1.json"
    sidecar_payload = json.loads(sidecar_path.read_text(encoding="utf-8"))
    return public_payload, sidecar_payload, sidecar_path


def _find_family_entry(sidecar_payload, family, interval):
    return next(item for item in sidecar_payload["families"] if item["family"] == family and item["interval"] == interval)


def _find_public_row(public_payload, strategy_name, asset, interval):
    return next(
        row
        for row in public_payload["results"]
        if row["strategy_name"] == strategy_name and row["asset"] == asset and row["interval"] == interval
    )


def test_sidecar_written_with_v1_schema_and_version_field(monkeypatch, tmp_path):
    _, sidecar_payload, sidecar_path = _run_reporting(monkeypatch, tmp_path)

    assert sidecar_path.exists()
    assert sidecar_payload["version"] == "v1"
    assert sidecar_payload["ranking_metric"] == "sharpe"


def test_sidecar_uses_family_interval_scope(monkeypatch, tmp_path):
    _, sidecar_payload, _ = _run_reporting(monkeypatch, tmp_path)

    assert sidecar_payload["experiment_family_scope"] == ["family", "interval"]
    assert {
        (item["family"], item["interval"])
        for item in sidecar_payload["families"]
    } == {
        ("trend", "1d"),
        ("trend", "4h"),
        ("mean_reversion", "1d"),
        ("mean_reversion", "4h"),
    }


def test_sidecar_includes_param_combinations_market_count_strategy_variants(monkeypatch, tmp_path):
    _, sidecar_payload, _ = _run_reporting(monkeypatch, tmp_path)
    family_entry = _find_family_entry(sidecar_payload, "trend", "1d")

    assert family_entry["strategy_variant_count"] == 2
    assert family_entry["param_combinations_total"] == 5
    assert family_entry["market_count"] == 2
    assert family_entry["trial_count_total"] == 10


def test_canonical_dsr_unavailable_without_regime_count(monkeypatch, tmp_path):
    _, sidecar_payload, _ = _run_reporting(monkeypatch, tmp_path)
    member = _find_family_entry(sidecar_payload, "trend", "1d")["members"][0]

    assert member["dsr_canonical"] is None
    assert member["dsr_unavailable_reason"].startswith("regime_count_not_supplied")


def test_canonical_dsr_available_when_regime_count_supplied(monkeypatch, tmp_path):
    _, sidecar_payload, _ = _run_reporting(monkeypatch, tmp_path, {"evaluation": {"regime_count": 3}})
    family_entry = _find_family_entry(sidecar_payload, "trend", "1d")
    member = family_entry["members"][0]

    assert family_entry["regime_count"] == 3
    assert family_entry["regime_count_source"] == "explicit"
    assert isinstance(member["dsr_canonical"], float)
    assert member["dsr_unavailable_reason"] is None


def test_legacy_public_deflated_sharpe_field_unchanged(monkeypatch, tmp_path):
    public_payload, sidecar_payload, _ = _run_reporting(monkeypatch, tmp_path, {"evaluation": {"regime_count": 3}})

    assert all("deflated_sharpe" in row for row in public_payload["results"])
    assert all(row["deflated_sharpe"] in {LEGACY_DEFLATED_SHARPE, -0.2} for row in public_payload["results"])
    member = _find_family_entry(sidecar_payload, "trend", "1d")["members"][0]
    assert member["dsr_legacy_field_in_public_row"] == LEGACY_DEFLATED_SHARPE
    assert member["dsr_canonical"] != LEGACY_DEFLATED_SHARPE


def test_no_corrected_metric_writes_to_public_row(monkeypatch, tmp_path):
    public_payload, _, _ = _run_reporting(monkeypatch, tmp_path)
    public_keys = set(public_payload["results"][0])

    assert "psr" not in public_keys
    assert "dsr_canonical" not in public_keys
    assert "bootstrap_ci" not in public_keys
    assert "noise_warning" not in public_keys


def test_noise_warning_is_explicit_and_deterministic(monkeypatch, tmp_path):
    _, first_sidecar, _ = _run_reporting(monkeypatch, tmp_path / "run1")
    _, second_sidecar, _ = _run_reporting(monkeypatch, tmp_path / "run2")
    first_member = _find_family_entry(first_sidecar, "trend", "1d")["members"][0]
    second_member = _find_family_entry(second_sidecar, "trend", "1d")["members"][0]

    assert first_member["noise_warning"] == second_member["noise_warning"]
    assert first_member["noise_warning"]["is_likely_noise"] is True
    assert "psr_below_0_95" in first_member["noise_warning"]["reason"]
    assert "bootstrap_sharpe_ci_low_nonpositive" in first_member["noise_warning"]["reason"]


def test_no_corrected_metric_drives_gating_or_status(monkeypatch, tmp_path):
    public_payload, sidecar_payload, _ = _run_reporting(monkeypatch, tmp_path)
    public_row = _find_public_row(public_payload, "trend_fast", "BTC-USD", "1d")
    member = _find_family_entry(sidecar_payload, "trend", "1d")["members"][0]

    assert public_row["goedgekeurd"] is True
    assert json.loads(public_row["criteria_checks_json"]) == LEGACY_TRUE_CHECKS
    assert member["noise_warning"]["is_likely_noise"] is True


def test_sidecar_atomic_write_no_partial_on_failure(monkeypatch, tmp_path):
    monkeypatch.setattr(run_research_module, "build_statistical_defensibility_payload", lambda **kwargs: (_ for _ in ()).throw(RuntimeError("boom")))
    monkeypatch.setattr(run_research_module, "BacktestEngine", ReportingEngine)
    monkeypatch.setattr(run_research_module, "get_enabled_strategies", lambda: STRATEGIES)
    monkeypatch.setattr(statistical_reporting_module, "iter_strategy_families", _strategies_by_family)
    monkeypatch.setattr(
        run_research_module,
        "build_research_universe",
        lambda config: (
            [type("Asset", (), {"symbol": symbol})() for symbol in ASSETS],
            INTERVALS,
            lambda interval: ("2024-01-01", "2024-12-31"),
            AS_OF_UTC,
        ),
    )
    monkeypatch.setattr(run_research_module, "load_research_config", lambda config_path="config/config.yaml": {})
    monkeypatch.setattr(run_research_module, "_write_provenance_sidecar", lambda **kwargs: None)
    monkeypatch.setattr(run_research_module, "_write_walk_forward_sidecar", lambda **kwargs: None)
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

    with pytest.raises(RuntimeError, match="boom"):
        run_research_module.run_research()

    assert not (tmp_path / "research" / "statistical_defensibility_latest.v1.json").exists()


def test_canonical_file_bytes_unchanged(monkeypatch, tmp_path):
    repo_root = Path(__file__).resolve().parents[2]
    canonical_json = repo_root / "research" / "research_latest.json"
    canonical_csv = repo_root / "research" / "strategy_matrix.csv"
    before_json = hashlib.sha256(canonical_json.read_bytes()).hexdigest()
    before_csv = hashlib.sha256(canonical_csv.read_bytes()).hexdigest()

    _run_reporting(monkeypatch, tmp_path)

    after_json = hashlib.sha256(canonical_json.read_bytes()).hexdigest()
    after_csv = hashlib.sha256(canonical_csv.read_bytes()).hexdigest()
    assert before_json == after_json
    assert before_csv == after_csv
