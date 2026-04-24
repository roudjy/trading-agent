"""v3.15 regression tests.

Pins:

- byte-identity of every v3.15 sidecar on a controlled fixture
  across reruns,
- schema_version + layer_version fields on every sidecar,
- authoritative / diagnostic_only / live_eligible invariants,
- v3.12 / v3.13 / v3.14 frozen artifact paths are **never**
  written to by the v3.15 façade.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import pytest

from research.paper_divergence import PAPER_DIVERGENCE_VERSION
from research.paper_ledger import PAPER_LEDGER_VERSION
from research.paper_readiness import PAPER_READINESS_VERSION
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


def _full_fill(sequence: int, day: int) -> _FakeExecutionEvent:
    ts = f"2024-05-{day:02d}T00:00:00+00:00"
    return _FakeExecutionEvent(
        event_id=f"{sequence}|BTC/EUR|{ts}|full_fill",
        kind="full_fill",
        asset="BTC/EUR",
        side="long",
        timestamp_utc=ts,
        sequence=sequence,
        fold_index=0,
        intended_price=50000.0,
        requested_size=1.0,
        fill_price=50010.0,
        filled_size=1.0,
        fee_amount=125.0,
        slippage_bps=2.0,
        reason_code=None,
        reason_detail=None,
    )


def _fixture_evaluation() -> dict:
    return {
        "row": {
            "strategy_name": "ema_trend",
            "asset": "BTC/EUR",
            "interval": "1d",
            "asset_type": "crypto",
        },
        "selected_params": {"ema_fast": 10, "ema_slow": 50},
        "evaluation_report": {
            "kosten_per_kant": 0.0025,
            "oos_summary": {
                "eindkapitaal": 1.15,
                "sharpe": 1.1,
                "max_drawdown": 0.08,
            },
            "evaluation_streams": {
                "oos_daily_returns": [
                    {"timestamp_utc": f"2024-05-{i+1:02d}T00:00:00+00:00", "return": 0.001 * ((i % 5) - 2)}
                    for i in range(90)
                ],
                "oos_execution_events": [_full_fill(i, (i % 28) + 1) for i in range(5)],
            },
        },
    }


def _paths_for(tmp_path: Path) -> dict[str, Path]:
    return {
        "timestamped_returns_path": tmp_path / TIMESTAMPED_RETURNS_PATH.name,
        "paper_ledger_path": tmp_path / PAPER_LEDGER_PATH.name,
        "paper_divergence_path": tmp_path / PAPER_DIVERGENCE_PATH.name,
        "paper_readiness_path": tmp_path / PAPER_READINESS_PATH.name,
    }


def _make_ctx() -> PaperValidationBuildContext:
    return PaperValidationBuildContext(
        run_id="regression-run",
        generated_at_utc="2026-04-24T10:00:00+00:00",
        git_revision="0123456789abcdef",
        registry_v2={"entries": []},
        sleeve_registry=None,
        evaluations=[_fixture_evaluation()],
    )


def test_byte_identity_on_fixture(tmp_path):
    ctx = _make_ctx()
    dir_a = tmp_path / "a"
    dir_b = tmp_path / "b"
    dir_a.mkdir()
    dir_b.mkdir()
    build_and_write_paper_validation_sidecars(ctx, **_paths_for(dir_a))
    build_and_write_paper_validation_sidecars(ctx, **_paths_for(dir_b))
    for name in (
        TIMESTAMPED_RETURNS_PATH.name,
        PAPER_LEDGER_PATH.name,
        PAPER_DIVERGENCE_PATH.name,
        PAPER_READINESS_PATH.name,
    ):
        assert (dir_a / name).read_text() == (dir_b / name).read_text()


def test_schema_and_layer_versions_pinned(tmp_path):
    ctx = _make_ctx()
    paths = _paths_for(tmp_path)
    build_and_write_paper_validation_sidecars(ctx, **paths)
    ts = json.loads(paths["timestamped_returns_path"].read_text())
    assert ts["schema_version"] == "1.0"
    ledger = json.loads(paths["paper_ledger_path"].read_text())
    assert ledger["schema_version"] == "1.0"
    assert ledger["paper_ledger_version"] == PAPER_LEDGER_VERSION == "v0.1"
    divergence = json.loads(paths["paper_divergence_path"].read_text())
    assert divergence["schema_version"] == "1.0"
    assert divergence["paper_divergence_version"] == PAPER_DIVERGENCE_VERSION == "v0.1"
    readiness = json.loads(paths["paper_readiness_path"].read_text())
    assert readiness["schema_version"] == "1.0"
    assert readiness["paper_readiness_version"] == PAPER_READINESS_VERSION == "v0.1"


def test_diagnostic_and_live_eligibility_invariants(tmp_path):
    ctx = _make_ctx()
    paths = _paths_for(tmp_path)
    build_and_write_paper_validation_sidecars(ctx, **paths)
    for key in ("paper_ledger_path", "paper_divergence_path", "paper_readiness_path"):
        data = json.loads(paths[key].read_text())
        assert data["authoritative"] is False
        assert data["diagnostic_only"] is True
        assert data["live_eligible"] is False
    # timestamped-returns is precision data but we still pin live_eligible=False
    ts = json.loads(paths["timestamped_returns_path"].read_text())
    assert ts["live_eligible"] is False


def test_facade_never_writes_v3_12_v3_13_v3_14_frozen_paths(tmp_path):
    ctx = _make_ctx()
    # Use tmp_path for v3.15 outputs. If the façade accidentally
    # targeted any of the v3.12–v3.14 paths they would also land
    # here (same dir) and be detectable.
    paths = _paths_for(tmp_path)
    build_and_write_paper_validation_sidecars(ctx, **paths)
    forbidden = [
        "candidate_registry_latest.v1.json",
        "candidate_registry_latest.v2.json",
        "candidate_status_history_latest.v1.json",
        "agent_definitions_latest.v1.json",
        "regime_intelligence_latest.v1.json",
        "candidate_registry_regime_overlay_latest.v1.json",
        "sleeve_registry_latest.v1.json",
        "candidate_returns_latest.v1.json",
        "portfolio_diagnostics_latest.v1.json",
        "regime_width_distributions_latest.v1.json",
    ]
    created = {p.name for p in tmp_path.iterdir()}
    for name in forbidden:
        assert name not in created, (
            f"v3.15 façade wrote forbidden v3.12-v3.14 path {name!r}"
        )
