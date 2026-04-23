"""Unit tests for research.portfolio_sleeve_sidecars façade."""

from __future__ import annotations

import json
from pathlib import Path

from research.candidate_returns_feed import CandidateReturnsRecord
from research.portfolio_sleeve_sidecars import (
    PortfolioSleeveBuildContext,
    build_and_write_portfolio_sleeve_sidecars,
)
from research.regime_width_feed import WidthFeedResult


def _v2_registry() -> dict:
    return {
        "entries": [
            {
                "candidate_id": "trend_ma|NVDA|4h|{}",
                "experiment_family": "trend|equities",
                "interval": "4h",
                "asset": "NVDA",
                "lifecycle_status": "candidate",
            },
            {
                "candidate_id": "trend_ma|AAPL|4h|{}",
                "experiment_family": "trend|equities",
                "interval": "4h",
                "asset": "AAPL",
                "lifecycle_status": "candidate",
            },
        ],
    }


def _records() -> list[CandidateReturnsRecord]:
    return [
        CandidateReturnsRecord(
            candidate_id="trend_ma|AAPL|4h|{}",
            daily_returns=(0.01, -0.005, 0.002),
            n_obs=3,
            start_date=None,
            end_date=None,
        ),
        CandidateReturnsRecord(
            candidate_id="trend_ma|NVDA|4h|{}",
            daily_returns=(0.02, -0.01, 0.005),
            n_obs=3,
            start_date=None,
            end_date=None,
        ),
    ]


def _ctx(**overrides) -> PortfolioSleeveBuildContext:
    base = dict(
        run_id="run_test",
        generated_at_utc="2026-04-23T20:00:00+00:00",
        git_revision="feedbeef",
        registry_v2=_v2_registry(),
        regime_overlay=None,
        candidate_returns=_records(),
        width_feed_result=None,
    )
    base.update(overrides)
    return PortfolioSleeveBuildContext(**base)


def test_build_and_write_writes_all_core_sidecars(tmp_path: Path):
    sleeve = tmp_path / "sleeve.json"
    returns = tmp_path / "returns.json"
    diagnostics = tmp_path / "diagnostics.json"
    width = tmp_path / "width.json"

    paths = build_and_write_portfolio_sleeve_sidecars(
        _ctx(),
        sleeve_registry_path=sleeve,
        candidate_returns_path=returns,
        portfolio_diagnostics_path=diagnostics,
        width_distributions_path=width,
    )
    assert sleeve.exists()
    assert returns.exists()
    assert diagnostics.exists()
    # Width sidecar is only written when feed is attached.
    assert not width.exists()
    assert set(paths.keys()) == {
        "sleeve_registry",
        "candidate_returns",
        "portfolio_diagnostics",
    }


def test_build_and_write_includes_width_sidecar_when_feed_present(tmp_path: Path):
    feed = WidthFeedResult(
        distributions={"trend_ma|NVDA|4h|{}": {"expansion": 10, "compression": 5, "insufficient": 2}},
        lineage=[{"asset": "NVDA", "interval": "4h", "n_bars": 17}],
    )
    paths = build_and_write_portfolio_sleeve_sidecars(
        _ctx(width_feed_result=feed),
        sleeve_registry_path=tmp_path / "sleeve.json",
        candidate_returns_path=tmp_path / "returns.json",
        portfolio_diagnostics_path=tmp_path / "diagnostics.json",
        width_distributions_path=tmp_path / "width.json",
    )
    width_payload = json.loads((tmp_path / "width.json").read_text(encoding="utf-8"))
    assert "regime_width_distributions" in paths
    assert width_payload["schema_version"] == "1.0"
    assert width_payload["entries"][0]["candidate_id"] == "trend_ma|NVDA|4h|{}"
    assert width_payload["entries"][0]["buckets"]["expansion"] == 10


def test_artifacts_reproduce_byte_identically_on_rerun(tmp_path: Path):
    def _run(dir_path: Path):
        paths = build_and_write_portfolio_sleeve_sidecars(
            _ctx(),
            sleeve_registry_path=dir_path / "sleeve.json",
            candidate_returns_path=dir_path / "returns.json",
            portfolio_diagnostics_path=dir_path / "diagnostics.json",
            width_distributions_path=dir_path / "width.json",
        )
        return {
            name: path.read_text(encoding="utf-8") for name, path in paths.items()
        }

    run_a_dir = tmp_path / "run_a"
    run_b_dir = tmp_path / "run_b"
    run_a_dir.mkdir()
    run_b_dir.mkdir()
    outputs_a = _run(run_a_dir)
    outputs_b = _run(run_b_dir)
    assert outputs_a == outputs_b, "v3.14 sidecars must reproduce byte-identically on rerun"


def test_facade_handles_missing_registry_gracefully(tmp_path: Path):
    paths = build_and_write_portfolio_sleeve_sidecars(
        _ctx(registry_v2={"entries": []}, candidate_returns=[]),
        sleeve_registry_path=tmp_path / "sleeve.json",
        candidate_returns_path=tmp_path / "returns.json",
        portfolio_diagnostics_path=tmp_path / "diagnostics.json",
        width_distributions_path=tmp_path / "width.json",
    )
    payload = json.loads((tmp_path / "sleeve.json").read_text(encoding="utf-8"))
    assert payload["sleeves"] == []
    assert payload["memberships"] == []
    assert "sleeve_registry" in paths
