"""Tests for candidate promotion decision logic and sidecar assembly."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

from research import run_research as run_research_module
from research.promotion import (
    STATUS_CANDIDATE,
    STATUS_NEEDS_INVESTIGATION,
    STATUS_REJECTED,
    build_strategy_id,
    classify_candidate,
    normalize_promotion_config,
)
from research.promotion_reporting import (
    ArtifactJoinError,
    build_candidate_registry_payload,
)
from research.results import write_latest_json, write_results_to_csv


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _good_oos() -> dict:
    return {
        "sharpe": 0.8,
        "max_drawdown": 0.15,
        "totaal_trades": 30,
        "goedgekeurd": True,
    }


def _good_defensibility() -> dict:
    return {
        "psr": 0.95,
        "dsr_canonical": 0.5,
        "noise_warning": {"is_likely_noise": False, "reason": "clear"},
        "bootstrap_ci": {"sharpe": {"low": 0.1, "high": 1.2}},
    }


def _research_latest(results: list[dict] | None = None) -> dict:
    if results is None:
        results = [
            {
                "strategy_name": "trend_fast",
                "asset": "BTC-USD",
                "interval": "1d",
                "params_json": '{"fast": 20, "slow": 50}',
                "success": True,
            }
        ]
    return {"generated_at_utc": "2026-04-12T00:00:00+00:00", "results": results}


def _walk_forward(strategies: list[dict] | None = None) -> dict:
    if strategies is None:
        strategies = [
            {
                "strategy_name": "trend_fast",
                "asset": "BTC-USD",
                "interval": "1d",
                "oos_summary": _good_oos(),
                "leakage_checks_ok": True,
            }
        ]
    return {"strategies": strategies}


def _stat_defensibility(members: list[dict] | None = None) -> dict:
    if members is None:
        members = [
            {
                "strategy_name": "trend_fast",
                "asset": "BTC-USD",
                "selected_params": {"fast": 20, "slow": 50},
                **_good_defensibility(),
            }
        ]
    return {
        "families": [
            {"family": "trend", "interval": "1d", "members": members},
        ]
    }


# ---------------------------------------------------------------------------
# normalize_promotion_config
# ---------------------------------------------------------------------------

class TestNormalizeConfig:
    def test_defaults_returned_when_none(self):
        config = normalize_promotion_config(None)
        assert config["min_oos_sharpe"] == 0.3
        assert config["require_goedgekeurd"] is False

    def test_overrides_applied(self):
        config = normalize_promotion_config({"min_oos_sharpe": 0.5})
        assert config["min_oos_sharpe"] == 0.5
        assert config["max_oos_drawdown"] == 0.35  # default preserved

    def test_unknown_keys_ignored(self):
        config = normalize_promotion_config({"unknown_key": 999})
        assert "unknown_key" not in config


# ---------------------------------------------------------------------------
# build_strategy_id
# ---------------------------------------------------------------------------

class TestBuildStrategyId:
    def test_deterministic(self):
        sid1 = build_strategy_id("trend_fast", "BTC-USD", "1d", {"fast": 20, "slow": 50})
        sid2 = build_strategy_id("trend_fast", "BTC-USD", "1d", {"slow": 50, "fast": 20})
        assert sid1 == sid2  # sort_keys=True

    def test_different_params_different_id(self):
        sid1 = build_strategy_id("trend_fast", "BTC-USD", "1d", {"fast": 20})
        sid2 = build_strategy_id("trend_fast", "BTC-USD", "1d", {"fast": 10})
        assert sid1 != sid2


# ---------------------------------------------------------------------------
# classify_candidate — rejection paths
# ---------------------------------------------------------------------------

class TestClassifyRejection:
    def test_low_sharpe_rejected(self):
        oos = _good_oos()
        oos["sharpe"] = 0.1
        status, reasoning = classify_candidate(oos, True, _good_defensibility(), normalize_promotion_config(None))
        assert status == STATUS_REJECTED
        assert "oos_sharpe_below_threshold" in reasoning["failed"]

    def test_high_drawdown_rejected(self):
        oos = _good_oos()
        oos["max_drawdown"] = 0.5
        status, reasoning = classify_candidate(oos, True, _good_defensibility(), normalize_promotion_config(None))
        assert status == STATUS_REJECTED
        assert "drawdown_above_limit" in reasoning["failed"]

    def test_leakage_rejected(self):
        status, reasoning = classify_candidate(_good_oos(), False, _good_defensibility(), normalize_promotion_config(None))
        assert status == STATUS_REJECTED
        assert "leakage_detected" in reasoning["failed"]

    def test_insufficient_trades_rejected(self):
        oos = _good_oos()
        oos["totaal_trades"] = 3
        status, reasoning = classify_candidate(oos, True, _good_defensibility(), normalize_promotion_config(None))
        assert status == STATUS_REJECTED
        assert "insufficient_trades" in reasoning["failed"]

    def test_goedgekeurd_required_but_false(self):
        oos = _good_oos()
        oos["goedgekeurd"] = False
        config = normalize_promotion_config({"require_goedgekeurd": True})
        status, reasoning = classify_candidate(oos, True, _good_defensibility(), config)
        assert status == STATUS_REJECTED
        assert "goedgekeurd_required_but_false" in reasoning["failed"]

    def test_multiple_failures_all_recorded(self):
        oos = {"sharpe": 0.0, "max_drawdown": 0.9, "totaal_trades": 0}
        status, reasoning = classify_candidate(oos, False, None, normalize_promotion_config(None))
        assert status == STATUS_REJECTED
        assert len(reasoning["failed"]) >= 3


# ---------------------------------------------------------------------------
# classify_candidate — escalation paths
# ---------------------------------------------------------------------------

class TestClassifyEscalation:
    def test_defensibility_missing_escalates(self):
        status, reasoning = classify_candidate(_good_oos(), True, None, normalize_promotion_config(None))
        assert status == STATUS_NEEDS_INVESTIGATION
        assert "defensibility_data_missing" in reasoning["escalated"]

    def test_noise_warning_escalates(self):
        defensibility = _good_defensibility()
        defensibility["noise_warning"]["is_likely_noise"] = True
        status, reasoning = classify_candidate(_good_oos(), True, defensibility, normalize_promotion_config(None))
        assert status == STATUS_NEEDS_INVESTIGATION
        assert "noise_warning_fired" in reasoning["escalated"]

    def test_psr_below_threshold_escalates(self):
        defensibility = _good_defensibility()
        defensibility["psr"] = 0.5
        status, reasoning = classify_candidate(_good_oos(), True, defensibility, normalize_promotion_config(None))
        assert status == STATUS_NEEDS_INVESTIGATION
        assert "psr_below_threshold" in reasoning["escalated"]

    def test_psr_none_escalates(self):
        defensibility = _good_defensibility()
        defensibility["psr"] = None
        status, reasoning = classify_candidate(_good_oos(), True, defensibility, normalize_promotion_config(None))
        assert status == STATUS_NEEDS_INVESTIGATION
        assert "psr_unavailable" in reasoning["escalated"]

    def test_dsr_none_escalates(self):
        defensibility = _good_defensibility()
        defensibility["dsr_canonical"] = None
        status, reasoning = classify_candidate(_good_oos(), True, defensibility, normalize_promotion_config(None))
        assert status == STATUS_NEEDS_INVESTIGATION
        assert "dsr_unavailable" in reasoning["escalated"]

    def test_dsr_below_threshold_escalates(self):
        defensibility = _good_defensibility()
        defensibility["dsr_canonical"] = -0.5
        status, reasoning = classify_candidate(_good_oos(), True, defensibility, normalize_promotion_config(None))
        assert status == STATUS_NEEDS_INVESTIGATION
        assert "dsr_canonical_below_threshold" in reasoning["escalated"]

    def test_bootstrap_ci_includes_zero_escalates(self):
        defensibility = _good_defensibility()
        defensibility["bootstrap_ci"]["sharpe"]["low"] = -0.1
        status, reasoning = classify_candidate(_good_oos(), True, defensibility, normalize_promotion_config(None))
        assert status == STATUS_NEEDS_INVESTIGATION
        assert "bootstrap_sharpe_ci_includes_zero" in reasoning["escalated"]

    def test_bootstrap_ci_unavailable_escalates(self):
        defensibility = _good_defensibility()
        defensibility["bootstrap_ci"] = {}
        status, reasoning = classify_candidate(_good_oos(), True, defensibility, normalize_promotion_config(None))
        assert status == STATUS_NEEDS_INVESTIGATION
        assert "bootstrap_sharpe_ci_unavailable" in reasoning["escalated"]


# ---------------------------------------------------------------------------
# classify_candidate — candidate (happy path)
# ---------------------------------------------------------------------------

class TestClassifyCandidate:
    def test_all_checks_pass(self):
        status, reasoning = classify_candidate(
            _good_oos(), True, _good_defensibility(), normalize_promotion_config(None)
        )
        assert status == STATUS_CANDIDATE
        assert reasoning["failed"] == []
        assert reasoning["escalated"] == []
        assert len(reasoning["passed"]) > 0

    def test_deterministic(self):
        args = (_good_oos(), True, _good_defensibility(), normalize_promotion_config(None))
        r1 = classify_candidate(*args)
        r2 = classify_candidate(*args)
        assert r1 == r2


# ---------------------------------------------------------------------------
# build_candidate_registry_payload — integration
# ---------------------------------------------------------------------------

class TestBuildPayload:
    def test_happy_path_produces_v1_schema(self):
        payload = build_candidate_registry_payload(
            research_latest=_research_latest(),
            walk_forward=_walk_forward(),
            statistical_defensibility=_stat_defensibility(),
            promotion_config=None,
            git_revision="abc123",
        )
        assert payload["version"] == "v1"
        assert payload["git_revision"] == "abc123"
        assert len(payload["candidates"]) == 1
        assert payload["candidates"][0]["status"] == STATUS_CANDIDATE
        assert payload["summary"]["total"] == 1

    def test_missing_walk_forward_entry_raises(self):
        with pytest.raises(ArtifactJoinError, match="walk-forward entry missing"):
            build_candidate_registry_payload(
                research_latest=_research_latest(),
                walk_forward=_walk_forward(strategies=[]),
                statistical_defensibility=None,
                promotion_config=None,
                git_revision="abc123",
            )

    def test_malformed_research_latest_raises(self):
        with pytest.raises(ArtifactJoinError, match="research_latest.results"):
            build_candidate_registry_payload(
                research_latest={"bad": True},
                walk_forward=_walk_forward(),
                statistical_defensibility=None,
                promotion_config=None,
                git_revision="abc123",
            )

    def test_malformed_walk_forward_raises(self):
        with pytest.raises(ArtifactJoinError, match="walk_forward.strategies"):
            build_candidate_registry_payload(
                research_latest=_research_latest(),
                walk_forward={"bad": True},
                statistical_defensibility=None,
                promotion_config=None,
                git_revision="abc123",
            )

    def test_none_defensibility_still_classifies(self):
        payload = build_candidate_registry_payload(
            research_latest=_research_latest(),
            walk_forward=_walk_forward(),
            statistical_defensibility=None,
            promotion_config=None,
            git_revision="abc123",
        )
        assert payload["candidates"][0]["status"] == STATUS_NEEDS_INVESTIGATION

    def test_failed_rows_excluded(self):
        results = [
            {"strategy_name": "a", "asset": "X", "interval": "1d", "params_json": "{}", "success": False},
            {"strategy_name": "trend_fast", "asset": "BTC-USD", "interval": "1d", "params_json": '{"fast": 20, "slow": 50}', "success": True},
        ]
        payload = build_candidate_registry_payload(
            research_latest=_research_latest(results),
            walk_forward=_walk_forward(),
            statistical_defensibility=_stat_defensibility(),
            promotion_config=None,
            git_revision="abc123",
        )
        assert payload["summary"]["total"] == 1

    def test_candidates_sorted_by_strategy_id(self):
        results = [
            {"strategy_name": "z_strat", "asset": "BTC-USD", "interval": "1d", "params_json": "{}", "success": True},
            {"strategy_name": "a_strat", "asset": "BTC-USD", "interval": "1d", "params_json": "{}", "success": True},
        ]
        wf = _walk_forward([
            {"strategy_name": "z_strat", "asset": "BTC-USD", "interval": "1d", "oos_summary": _good_oos(), "leakage_checks_ok": True},
            {"strategy_name": "a_strat", "asset": "BTC-USD", "interval": "1d", "oos_summary": _good_oos(), "leakage_checks_ok": True},
        ])
        payload = build_candidate_registry_payload(
            research_latest=_research_latest(results),
            walk_forward=wf,
            statistical_defensibility=None,
            promotion_config=None,
            git_revision="abc123",
        )
        ids = [c["strategy_id"] for c in payload["candidates"]]
        assert ids == sorted(ids)

    def test_promotion_config_forwarded(self):
        payload = build_candidate_registry_payload(
            research_latest=_research_latest(),
            walk_forward=_walk_forward(),
            statistical_defensibility=_stat_defensibility(),
            promotion_config={"min_oos_sharpe": 2.0},
            git_revision="abc123",
        )
        assert payload["promotion_config"]["min_oos_sharpe"] == 2.0
        assert payload["candidates"][0]["status"] == STATUS_REJECTED


# ---------------------------------------------------------------------------
# Wiring test — proves run_research() writes the sidecar file
# ---------------------------------------------------------------------------

AS_OF_UTC = datetime(2026, 4, 8, 10, 59, 31, 381566, tzinfo=UTC)


class _WiringEngine:
    """Minimal fake engine that returns walk-forward evaluation data."""

    def __init__(self, start_datum, eind_datum, evaluation_config=None):
        self._provenance_events = []
        self.last_evaluation_report = None

    def grid_search(self, strategie_factory, param_grid, assets, interval="1d"):
        self.last_evaluation_report = {
            "evaluation_config": {},
            "selection_metric": "sharpe",
            "selected_params": {"periode": 14},
            "is_summary": {},
            "oos_summary": _good_oos(),
            "folds": [{"train": [0, 69], "test": [70, 99], "leakage_ok": True}],
            "leakage_checks_ok": True,
            "evaluation_samples": {
                "daily_returns": [0.01, -0.005, 0.003],
                "trade_pnls": [0.02, -0.01],
                "monthly_returns": [0.008],
            },
            "sample_statistics": {
                "daily_returns": {"count": 3, "mean": 0.003, "std": 0.006, "skew": 0.0, "kurt": 3.0},
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


class TestCandidateRegistryWiring:
    def test_run_research_writes_candidate_registry(self, monkeypatch, tmp_path):
        monkeypatch.chdir(tmp_path)
        (tmp_path / "research").mkdir()
        monkeypatch.setattr(run_research_module, "BacktestEngine", _WiringEngine)
        monkeypatch.setattr(
            run_research_module,
            "get_enabled_strategies",
            lambda: [
                {
                    "name": "fake_strategy",
                    "family": "trend",
                    "hypothesis": "Test",
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
        monkeypatch.setattr(run_research_module, "load_research_config", lambda config_path="config/config.yaml": {})
        monkeypatch.setattr(run_research_module, "_git_revision", lambda: "abc123")
        monkeypatch.setattr(run_research_module, "_write_provenance_sidecar", lambda **kwargs: None)
        monkeypatch.setattr(run_research_module, "_write_statistical_defensibility_sidecar", lambda **kwargs: None)
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

        registry_path = tmp_path / "research" / "candidate_registry_latest.v1.json"
        assert registry_path.exists(), "candidate_registry_latest.v1.json was not written"
        payload = json.loads(registry_path.read_text(encoding="utf-8"))
        assert payload["version"] == "v1"
        assert payload["git_revision"] == "abc123"
        assert len(payload["candidates"]) > 0
        assert "promotion_config" in payload
        assert "summary" in payload
