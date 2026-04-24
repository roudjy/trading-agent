"""v3.15 integration tests: end-to-end façade wiring.

These tests drive the façade directly against synthetic
``evaluations`` payloads that match the shape the runner
accumulates. They do NOT invoke the full research pipeline — the
v3.14 tests already lock down that outer wiring. v3.15's
integration layer is the façade call plus the paper-validation
composition.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import pytest

from research.paper_validation_sidecars import (
    PAPER_DIVERGENCE_PATH,
    PAPER_LEDGER_PATH,
    PAPER_READINESS_PATH,
    TIMESTAMPED_RETURNS_PATH,
    PaperValidationBuildContext,
    build_and_write_paper_validation_sidecars,
)


@dataclass
class _FakeExecutionEvent:
    event_id: str
    kind: str
    asset: str
    side: str
    timestamp_utc: str
    sequence: int
    fold_index: int | None
    intended_price: float
    requested_size: float
    fill_price: float | None
    filled_size: float | None
    fee_amount: float | None
    slippage_bps: float | None
    reason_code: str | None
    reason_detail: str | None


def _full_fill(asset: str, sequence: int, timestamp: str) -> _FakeExecutionEvent:
    return _FakeExecutionEvent(
        event_id=f"{sequence}|{asset}|{timestamp}|full_fill",
        kind="full_fill",
        asset=asset,
        side="long",
        timestamp_utc=timestamp,
        sequence=sequence,
        fold_index=0,
        intended_price=100.0,
        requested_size=1.0,
        fill_price=100.05,
        filled_size=1.0,
        fee_amount=0.25,
        slippage_bps=2.0,
        reason_code=None,
        reason_detail=None,
    )


def _daily_returns(n_days: int, start_day: int = 1) -> list[dict]:
    stream: list[dict] = []
    for i in range(n_days):
        day = start_day + i
        month = 5 + (day - 1) // 28
        within = ((day - 1) % 28) + 1
        stream.append({
            "timestamp_utc": f"2024-{month:02d}-{within:02d}T00:00:00+00:00",
            "return": 0.001 * ((i % 7) - 3),
        })
    return stream


def _evaluation_crypto(strategy_name: str = "ema_trend", n_fills: int = 5) -> dict:
    asset = "BTC/EUR"
    events = [
        _full_fill(asset, sequence=i, timestamp=f"2024-05-{i+1:02d}T00:00:00+00:00")
        for i in range(n_fills)
    ]
    return {
        "row": {
            "strategy_name": strategy_name,
            "asset": asset,
            "interval": "1d",
            "asset_type": "crypto",
        },
        "selected_params": {"fast": 10, "slow": 50},
        "evaluation_report": {
            "kosten_per_kant": 0.0025,
            "oos_summary": {
                "eindkapitaal": 1.15,
                "sharpe": 1.1,
                "max_drawdown": 0.08,
            },
            "evaluation_streams": {
                "oos_daily_returns": _daily_returns(90),
                "oos_execution_events": events,
            },
        },
    }


def _evaluation_equity() -> dict:
    events = [
        _full_fill("AAPL", sequence=i, timestamp=f"2024-05-{i+1:02d}T15:30:00+00:00")
        for i in range(3)
    ]
    return {
        "row": {
            "strategy_name": "sma_breakout",
            "asset": "AAPL",
            "interval": "1d",
            "asset_type": "equity",
        },
        "selected_params": {"length": 30},
        "evaluation_report": {
            "kosten_per_kant": 0.001,
            "oos_summary": {
                "eindkapitaal": 1.08,
                "sharpe": 0.9,
                "max_drawdown": 0.06,
            },
            "evaluation_streams": {
                "oos_daily_returns": _daily_returns(90, start_day=32),
                "oos_execution_events": events,
            },
        },
    }


def _evaluation_unknown_asset() -> dict:
    events = [
        _full_fill("???", sequence=i, timestamp=f"2024-05-{i+1:02d}T00:00:00+00:00")
        for i in range(2)
    ]
    return {
        "row": {
            "strategy_name": "anomaly",
            "asset": "???",
            "interval": "1d",
            "asset_type": "futures",  # no venue in v3.15
        },
        "selected_params": {"x": 1},
        "evaluation_report": {
            "kosten_per_kant": 0.002,
            "oos_summary": {
                "eindkapitaal": 1.02,
                "sharpe": 0.2,
                "max_drawdown": 0.05,
            },
            "evaluation_streams": {
                "oos_daily_returns": _daily_returns(90, start_day=1),
                "oos_execution_events": events,
            },
        },
    }


def _make_ctx(
    tmp_path: Path,
    evaluations: list[dict],
) -> tuple[PaperValidationBuildContext, dict[str, Path]]:
    ctx = PaperValidationBuildContext(
        run_id="run-int-test",
        generated_at_utc="2026-04-24T10:00:00+00:00",
        git_revision="beefcafe",
        registry_v2={"entries": []},
        sleeve_registry=None,
        evaluations=evaluations,
    )
    paths = {
        "timestamped_returns_path": tmp_path / TIMESTAMPED_RETURNS_PATH.name,
        "paper_ledger_path": tmp_path / PAPER_LEDGER_PATH.name,
        "paper_divergence_path": tmp_path / PAPER_DIVERGENCE_PATH.name,
        "paper_readiness_path": tmp_path / PAPER_READINESS_PATH.name,
    }
    return ctx, paths


def test_end_to_end_multi_venue_happy_path(tmp_path):
    ctx, paths = _make_ctx(
        tmp_path,
        [_evaluation_crypto(), _evaluation_equity()],
    )
    written = build_and_write_paper_validation_sidecars(ctx, **paths)
    # Every sidecar exists and parses
    for name in ("candidate_timestamped_returns", "paper_ledger",
                 "paper_divergence", "paper_readiness"):
        data = json.loads(written[name].read_text())
        assert data["live_eligible"] is False
    # Both candidates appear in divergence and readiness
    divergence = json.loads(written["paper_divergence"].read_text())
    assert len(divergence["per_candidate"]) == 2
    included = [e for e in divergence["per_candidate"] if e["included_in_portfolio"]]
    assert len(included) == 2
    venues = {e["venue"] for e in divergence["per_candidate"]}
    assert venues == {"crypto_bitvavo", "equity_ibkr"}
    readiness = json.loads(written["paper_readiness"].read_text())
    assert len(readiness["entries"]) == 2


def test_unknown_venue_blocked_path(tmp_path):
    ctx, paths = _make_ctx(
        tmp_path,
        [_evaluation_crypto(), _evaluation_unknown_asset()],
    )
    written = build_and_write_paper_validation_sidecars(ctx, **paths)
    readiness = json.loads(written["paper_readiness"].read_text())
    # Unknown-asset candidate must be blocked with insufficient_venue_mapping
    blocked = [
        e for e in readiness["entries"]
        if e["asset_type"] in ("futures", "unknown")
    ]
    assert blocked, "unknown-asset candidate missing from readiness"
    assert any(
        "insufficient_venue_mapping" in e["blocking_reasons"]
        for e in blocked
    )
    # The crypto candidate should still be able to be ready
    crypto = [
        e for e in readiness["entries"] if e["asset_type"] == "crypto"
    ]
    assert crypto and crypto[0]["readiness_status"] in (
        "ready_for_paper_promotion",
        "insufficient_evidence",
    )


def test_byte_identical_across_reruns(tmp_path):
    evaluations = [_evaluation_crypto(), _evaluation_equity(),
                   _evaluation_unknown_asset()]
    ctx_a, paths_a = _make_ctx(tmp_path / "a", evaluations)
    ctx_b, paths_b = _make_ctx(tmp_path / "b", evaluations)
    (tmp_path / "a").mkdir()
    (tmp_path / "b").mkdir()
    build_and_write_paper_validation_sidecars(ctx_a, **paths_a)
    build_and_write_paper_validation_sidecars(ctx_b, **paths_b)
    for name in (
        TIMESTAMPED_RETURNS_PATH.name,
        PAPER_LEDGER_PATH.name,
        PAPER_DIVERGENCE_PATH.name,
        PAPER_READINESS_PATH.name,
    ):
        assert (tmp_path / "a" / name).read_text() == (
            tmp_path / "b" / name
        ).read_text(), f"byte-identity violation in {name}"
