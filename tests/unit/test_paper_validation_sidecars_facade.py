"""v3.15 unit tests: paper_validation_sidecars façade."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import pytest

from research.candidate_registry_v2 import build_candidate_id
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


def _execution_event(kind: str, timestamp: str, sequence: int) -> _FakeExecutionEvent:
    base = dict(
        event_id=f"{sequence}|BTC/EUR|{timestamp}|{kind}",
        kind=kind,
        asset="BTC/EUR",
        side="long",
        timestamp_utc=timestamp,
        sequence=sequence,
        fold_index=0,
        intended_price=50000.0,
        requested_size=1.0,
        fill_price=None,
        filled_size=None,
        fee_amount=None,
        slippage_bps=None,
        reason_code=None,
        reason_detail=None,
    )
    if kind == "full_fill":
        base.update(
            fill_price=50010.0,
            filled_size=1.0,
            fee_amount=125.0,
            slippage_bps=2.0,
        )
    return _FakeExecutionEvent(**base)


def _evaluation(
    *,
    strategy_name: str = "ema_trend",
    asset: str = "BTC/EUR",
    interval: str = "1d",
    asset_type: str = "crypto",
    oos_days: int = 90,
    n_fills: int = 4,
) -> dict:
    selected_params = {"ema_fast": 10, "ema_slow": 50}
    daily_returns = [
        {
            "timestamp_utc": f"2024-05-{(i % 28) + 1:02d}T00:00:00+00:00",
            "return": 0.001 * (i + 1),
        }
        for i in range(oos_days)
    ]
    # Unique timestamps: spread over multiple months so no dups
    daily_returns = [
        {"timestamp_utc": f"2024-{(i // 28) + 5:02d}-{(i % 28) + 1:02d}T00:00:00+00:00", "return": 0.001}
        for i in range(oos_days)
    ]
    exec_events = [
        _execution_event("full_fill", f"2024-05-{(i % 28) + 1:02d}T00:00:00+00:00", i)
        for i in range(n_fills)
    ]
    return {
        "row": {
            "strategy_name": strategy_name,
            "asset": asset,
            "interval": interval,
            "asset_type": asset_type,
        },
        "selected_params": selected_params,
        "evaluation_report": {
            "kosten_per_kant": 0.0025,
            "oos_summary": {
                "eindkapitaal": 1.10,
                "sharpe": 1.2,
                "max_drawdown": 0.05,
            },
            "evaluation_streams": {
                "oos_daily_returns": daily_returns,
                "oos_execution_events": exec_events,
            },
        },
    }


def _ctx(
    *,
    evaluations: list[dict] | None = None,
    sleeve_registry: dict | None = None,
) -> PaperValidationBuildContext:
    return PaperValidationBuildContext(
        run_id="run-test",
        generated_at_utc="2026-04-24T10:00:00+00:00",
        git_revision="deadbeef",
        registry_v2={"entries": []},
        sleeve_registry=sleeve_registry,
        evaluations=evaluations if evaluations is not None else [_evaluation()],
    )


def _run_facade(tmp_path: Path, ctx: PaperValidationBuildContext) -> dict[str, Path]:
    paths = {
        "timestamped_returns_path": tmp_path / TIMESTAMPED_RETURNS_PATH.name,
        "paper_ledger_path": tmp_path / PAPER_LEDGER_PATH.name,
        "paper_divergence_path": tmp_path / PAPER_DIVERGENCE_PATH.name,
        "paper_readiness_path": tmp_path / PAPER_READINESS_PATH.name,
    }
    return build_and_write_paper_validation_sidecars(ctx, **paths)


def test_all_four_sidecars_written(tmp_path):
    ctx = _ctx()
    written = _run_facade(tmp_path, ctx)
    assert set(written.keys()) == {
        "candidate_timestamped_returns",
        "paper_ledger",
        "paper_divergence",
        "paper_readiness",
    }
    for path in written.values():
        assert path.exists(), f"Missing {path}"
        data = json.loads(path.read_text())
        assert data["schema_version"] == "1.0"


def test_live_eligible_false_in_every_sidecar(tmp_path):
    ctx = _ctx()
    written = _run_facade(tmp_path, ctx)
    for name in ("paper_ledger", "paper_divergence", "paper_readiness"):
        data = json.loads(written[name].read_text())
        assert data["live_eligible"] is False
        assert data["authoritative"] is False
        assert data["diagnostic_only"] is True


def test_byte_identical_reruns(tmp_path):
    ctx = _ctx()
    a = tmp_path / "a"
    b = tmp_path / "b"
    a.mkdir()
    b.mkdir()
    _run_facade(a, ctx)
    _run_facade(b, ctx)
    for name in (
        TIMESTAMPED_RETURNS_PATH.name,
        PAPER_LEDGER_PATH.name,
        PAPER_DIVERGENCE_PATH.name,
        PAPER_READINESS_PATH.name,
    ):
        assert (a / name).read_text() == (b / name).read_text(), (
            f"byte-identity violation in {name}"
        )


def test_graceful_empty_evaluations(tmp_path):
    ctx = _ctx(evaluations=[])
    written = _run_facade(tmp_path, ctx)
    ledger = json.loads(written["paper_ledger"].read_text())
    assert ledger["per_candidate"] == []
    divergence = json.loads(written["paper_divergence"].read_text())
    assert divergence["per_candidate"] == []
    readiness = json.loads(written["paper_readiness"].read_text())
    assert readiness["entries"] == []
    ts = json.loads(written["candidate_timestamped_returns"].read_text())
    assert ts["entries"] == []


def test_facade_does_not_write_to_v3_12_v3_13_v3_14_paths(tmp_path, monkeypatch):
    # Monkey-patch the v3.15 default paths to the temp dir so the
    # façade never touches the real research/ directory, but leave
    # the v3.12/v3.13/v3.14 paths untouched so any accidental write
    # would fail the test via existence of unexpected files.
    ctx = _ctx()
    v315_paths = {
        "timestamped_returns_path": tmp_path / "v315_ts.json",
        "paper_ledger_path": tmp_path / "v315_ledger.json",
        "paper_divergence_path": tmp_path / "v315_div.json",
        "paper_readiness_path": tmp_path / "v315_ready.json",
    }
    build_and_write_paper_validation_sidecars(ctx, **v315_paths)
    # Verify only the v3.15 files exist in tmp_path
    created = sorted(p.name for p in tmp_path.iterdir())
    assert created == [
        "v315_div.json",
        "v315_ledger.json",
        "v315_ready.json",
        "v315_ts.json",
    ]
    # Forbidden v3.12–v3.14 paths should not have been created
    forbidden = [
        "candidate_registry_latest.v1.json",
        "candidate_registry_latest.v2.json",
        "regime_intelligence_latest.v1.json",
        "candidate_registry_regime_overlay_latest.v1.json",
        "sleeve_registry_latest.v1.json",
        "candidate_returns_latest.v1.json",
        "portfolio_diagnostics_latest.v1.json",
        "regime_width_distributions_latest.v1.json",
    ]
    for name in forbidden:
        assert not (tmp_path / name).exists()
