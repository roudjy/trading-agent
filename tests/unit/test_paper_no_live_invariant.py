"""v3.15 no-live invariant tests.

v3.15 must not import, call, or otherwise depend on any live /
broker / order-execution surface. These tests pin three layers of
the invariant:

1. **Import scan** — no v3.15 module imports from
   ``agent.execution``, ``agent.brain.*``, ``execution.paper``,
   ``execution.protocols``, or anything that looks like a broker
   surface.
2. **Payload invariant** — every v3.15 artifact payload has
   ``live_eligible`` pinned to ``False`` at every level where the
   field exists.
3. **No network** — a façade run under a socket monkey-patch that
   raises on any network attempt must complete successfully, i.e.
   v3.15 never talks to a remote service.
"""

from __future__ import annotations

import importlib
import io
import json
import pkgutil
import socket
import sys
from dataclasses import dataclass
from pathlib import Path

import pytest

import research
from research.paper_validation_sidecars import (
    PAPER_DIVERGENCE_PATH,
    PAPER_LEDGER_PATH,
    PAPER_READINESS_PATH,
    TIMESTAMPED_RETURNS_PATH,
    PaperValidationBuildContext,
    build_and_write_paper_validation_sidecars,
)


V3_15_MODULE_NAMES: tuple[str, ...] = (
    "research.paper_venues",
    "research.candidate_timestamped_returns_feed",
    "research.paper_ledger",
    "research.paper_divergence",
    "research.paper_readiness",
    "research.paper_validation_sidecars",
    "research._oos_stream",
)

# Forbidden import prefixes. These represent the live / broker /
# order-execution surface. v3.15 may depend on
# ``agent.backtesting`` (the backtest engine) but NOT on
# ``agent.execution`` (the live order executor) or the paper
# broker simulator under ``execution.paper`` (Polymarket).
FORBIDDEN_IMPORT_PREFIXES: tuple[str, ...] = (
    "agent.execution",
    "agent.brain",
    "agent.agents",
    "execution.paper",
    "execution.protocols",
    "agent.risk",
)


def _module_source(module_name: str) -> str:
    module = importlib.import_module(module_name)
    path = getattr(module, "__file__", None)
    if not path:
        return ""
    return Path(path).read_text(encoding="utf-8")


def test_no_forbidden_imports_in_v3_15_modules():
    for module_name in V3_15_MODULE_NAMES:
        source = _module_source(module_name)
        for prefix in FORBIDDEN_IMPORT_PREFIXES:
            # Match both `import <prefix>` and `from <prefix>` forms
            assert f"import {prefix}" not in source, (
                f"v3.15 module {module_name!r} imports forbidden "
                f"prefix {prefix!r}"
            )
            assert f"from {prefix}" not in source, (
                f"v3.15 module {module_name!r} imports from forbidden "
                f"prefix {prefix!r}"
            )


def test_no_live_eligible_true_anywhere_in_v3_15_source():
    # Defensive: sweep the v3.15 source for any literal that could
    # set live_eligible=True. The only accepted pattern is
    # ``live_eligible": False`` or ``live_eligible=False`` (and
    # ``live_eligible is False`` in assertions).
    forbidden_substrings = (
        "live_eligible=True",
        "live_eligible = True",
        '"live_eligible": True',
    )
    for module_name in V3_15_MODULE_NAMES:
        source = _module_source(module_name)
        for forbidden in forbidden_substrings:
            assert forbidden not in source, (
                f"v3.15 module {module_name!r} contains forbidden "
                f"literal {forbidden!r}"
            )


@dataclass
class _FakeEvent:
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


def _make_eval() -> dict:
    events = [
        _FakeEvent(
            event_id=f"{i}|BTC/EUR|2024-05-{i+1:02d}T00:00:00+00:00|full_fill",
            kind="full_fill",
            asset="BTC/EUR",
            side="long",
            timestamp_utc=f"2024-05-{i+1:02d}T00:00:00+00:00",
            sequence=i,
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
        for i in range(3)
    ]
    daily = [
        {"timestamp_utc": f"2024-05-{i+1:02d}T00:00:00+00:00", "return": 0.001}
        for i in range(65)
    ]
    return {
        "row": {
            "strategy_name": "x",
            "asset": "BTC/EUR",
            "interval": "1d",
            "asset_type": "crypto",
        },
        "selected_params": {"a": 1},
        "evaluation_report": {
            "kosten_per_kant": 0.0025,
            "oos_summary": {
                "eindkapitaal": 1.1,
                "sharpe": 1.0,
                "max_drawdown": 0.05,
            },
            "evaluation_streams": {
                "oos_daily_returns": daily,
                "oos_execution_events": events,
            },
        },
    }


def test_facade_runs_without_any_network_calls(tmp_path, monkeypatch):
    def _no_network(*args, **kwargs):
        raise AssertionError(
            "v3.15 made a socket connection; this violates the "
            "no-live invariant"
        )

    monkeypatch.setattr(socket.socket, "connect", _no_network)
    monkeypatch.setattr(socket.socket, "connect_ex", _no_network)

    ctx = PaperValidationBuildContext(
        run_id="no-live",
        generated_at_utc="2026-04-24T10:00:00+00:00",
        git_revision="cafe",
        registry_v2={"entries": []},
        sleeve_registry=None,
        evaluations=[_make_eval()],
    )
    written = build_and_write_paper_validation_sidecars(
        ctx,
        timestamped_returns_path=tmp_path / TIMESTAMPED_RETURNS_PATH.name,
        paper_ledger_path=tmp_path / PAPER_LEDGER_PATH.name,
        paper_divergence_path=tmp_path / PAPER_DIVERGENCE_PATH.name,
        paper_readiness_path=tmp_path / PAPER_READINESS_PATH.name,
    )
    # All four sidecars written, every one has live_eligible=False
    for path in written.values():
        data = json.loads(path.read_text())
        assert data["live_eligible"] is False
