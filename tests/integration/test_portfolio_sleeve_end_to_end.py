"""End-to-end test for the v3.14 portfolio/sleeve layer.

Emulates the wiring inside ``research.run_research.run_research``:
the width feed runs first, its output feeds the v3.13 façade, and
the v3.14 façade then consumes registry v2, the regime overlay, and
the in-memory evaluations to produce four sidecars.
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import numpy as np
import pandas as pd

from research.candidate_returns_feed import build_records_from_evaluations
from research.portfolio_sleeve_sidecars import (
    PortfolioSleeveBuildContext,
    build_and_write_portfolio_sleeve_sidecars,
)
from research.regime_width_feed import build_width_distributions


class _StubRepo:
    def __init__(self, frame: pd.DataFrame):
        self._frame = frame

    def get_bars(self, *, instrument, interval, start_utc, end_utc):
        return SimpleNamespace(
            frame=self._frame,
            provenance=SimpleNamespace(adapter="stub", cache_hit=True),
        )


def _synthetic_frame(n: int = 400, seed: int = 1) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    noise = rng.normal(size=n) * 0.01
    noise[150:250] *= 4.0
    close = 100.0 + np.cumsum(noise)
    return pd.DataFrame({"close": close, "high": close, "low": close, "volume": 1.0})


def _evaluation(strategy: str, asset: str, interval: str, params: dict, daily_returns) -> dict:
    return {
        "row": {"strategy_name": strategy, "asset": asset, "interval": interval},
        "selected_params": params,
        "evaluation_report": {
            "evaluation_samples": {"daily_returns": list(daily_returns)},
            "folds_by_asset": {asset: [{"train": ("2024-01-01", "2024-06-30"), "test": ("2024-07-01", "2024-12-31")}]},
        },
    }


def _registry_v2(candidate_ids: list[str]) -> dict[str, Any]:
    entries = []
    for cid in candidate_ids:
        _, asset, interval, _ = cid.split("|", 3)
        entries.append(
            {
                "candidate_id": cid,
                "experiment_family": "trend|equities",
                "interval": interval,
                "asset": asset,
                "lifecycle_status": "candidate",
            }
        )
    return {"entries": entries}


def _overlay(candidate_ids: list[str]) -> dict[str, Any]:
    return {
        "entries": [
            {
                "candidate_id": cid,
                "regime_assessment_status": "sufficient",
                "regime_dependency_scores": {"trend": 0.4, "vol": 0.3, "width": 0.2},
            }
            for cid in candidate_ids
        ]
    }


def test_end_to_end_produces_all_v3_14_sidecars(tmp_path: Path):
    from research.candidate_registry_v2 import build_candidate_id

    n_obs = 200
    rng = np.random.default_rng(seed=42)
    returns_nvda = rng.normal(size=n_obs) * 0.01
    returns_aapl = rng.normal(size=n_obs) * 0.01

    evaluations = [
        _evaluation("trend_ma", "NVDA", "4h", {"lookback": 20}, returns_nvda),
        _evaluation("trend_ma", "AAPL", "4h", {"lookback": 20}, returns_aapl),
    ]
    records = build_records_from_evaluations(evaluations)
    candidate_ids = [r.candidate_id for r in records]

    registry_v2 = _registry_v2(candidate_ids)
    overlay = _overlay(candidate_ids)

    # Width feed drives both v3.13 (distributions dict) and v3.14
    # (feed result) outputs.
    feed = build_width_distributions(
        registry_v2=registry_v2,
        date_range_by_interval={"4h": ("2024-01-01", "2025-01-01")},
        market_repository=_StubRepo(frame=_synthetic_frame()),
    )

    ctx = PortfolioSleeveBuildContext(
        run_id="e2e_test_run",
        generated_at_utc="2026-04-23T20:00:00+00:00",
        git_revision="deadbeef",
        registry_v2=registry_v2,
        regime_overlay=overlay,
        candidate_returns=records,
        width_feed_result=feed,
    )

    paths = build_and_write_portfolio_sleeve_sidecars(
        ctx,
        sleeve_registry_path=tmp_path / "sleeve.json",
        candidate_returns_path=tmp_path / "returns.json",
        portfolio_diagnostics_path=tmp_path / "diagnostics.json",
        width_distributions_path=tmp_path / "width.json",
    )
    assert set(paths.keys()) == {
        "sleeve_registry",
        "candidate_returns",
        "portfolio_diagnostics",
        "regime_width_distributions",
    }

    sleeve = json.loads((tmp_path / "sleeve.json").read_text(encoding="utf-8"))
    returns = json.loads((tmp_path / "returns.json").read_text(encoding="utf-8"))
    diagnostics = json.loads((tmp_path / "diagnostics.json").read_text(encoding="utf-8"))
    width = json.loads((tmp_path / "width.json").read_text(encoding="utf-8"))

    # Sleeve registry populated with at least one base sleeve + one
    # regime-filtered variant (because every candidate has
    # assessment_status == "sufficient").
    assert any(s["is_regime_filtered"] for s in sleeve["sleeves"])
    assert any(not s["is_regime_filtered"] for s in sleeve["sleeves"])

    # Candidate-returns entries aligned on candidate_id.
    returns_ids = [e["candidate_id"] for e in returns["entries"]]
    assert returns_ids == sorted(candidate_ids)

    # Portfolio diagnostics has non-trivial correlation block and a
    # populated equal-weight portfolio block.
    assert diagnostics["universe_candidate_count"] == 2
    assert diagnostics["equal_weight_portfolio"]["candidate_count"] == 2
    assert diagnostics["correlation"]["candidate"]["labels"] == sorted(candidate_ids)
    # regime-conditioned block produces an entry per sleeve.
    assert diagnostics["regime_conditioned"]

    # Width-axis is no longer structurally empty — at least one bucket
    # is populated.
    first = width["entries"][0]["buckets"]
    assert first["expansion"] + first["compression"] + first["insufficient"] > 0


def test_end_to_end_reruns_byte_identically(tmp_path: Path):
    from research.candidate_registry_v2 import build_candidate_id  # noqa: F401 (imported for parity)

    evaluations = [
        _evaluation("trend_ma", "NVDA", "4h", {"lookback": 20}, [0.01, -0.005, 0.002] * 40),
        _evaluation("trend_ma", "AAPL", "4h", {"lookback": 20}, [0.005, -0.002, 0.001] * 40),
    ]
    records = build_records_from_evaluations(evaluations)
    candidate_ids = [r.candidate_id for r in records]
    registry_v2 = _registry_v2(candidate_ids)
    overlay = _overlay(candidate_ids)

    def _run(dir_: Path):
        feed = build_width_distributions(
            registry_v2=registry_v2,
            date_range_by_interval={"4h": ("2024-01-01", "2025-01-01")},
            market_repository=_StubRepo(frame=_synthetic_frame()),
        )
        ctx = PortfolioSleeveBuildContext(
            run_id="byte_identity_run",
            generated_at_utc="2026-04-23T20:00:00+00:00",
            git_revision="deadbeef",
            registry_v2=registry_v2,
            regime_overlay=overlay,
            candidate_returns=records,
            width_feed_result=feed,
        )
        paths = build_and_write_portfolio_sleeve_sidecars(
            ctx,
            sleeve_registry_path=dir_ / "sleeve.json",
            candidate_returns_path=dir_ / "returns.json",
            portfolio_diagnostics_path=dir_ / "diagnostics.json",
            width_distributions_path=dir_ / "width.json",
        )
        return {name: path.read_text(encoding="utf-8") for name, path in paths.items()}

    a = tmp_path / "a"
    b = tmp_path / "b"
    a.mkdir()
    b.mkdir()
    assert _run(a) == _run(b)
