"""Regression tests for additive slippage persistence on trades."""

from __future__ import annotations

import sqlite3
from datetime import datetime

from agent.learning.memory import Trade


def _memory_cfg():
    return {
        'kapitaal': {'start': 1000.0, 'max_positie_grootte': 0.10, 'drawdown_limiet': 0.75},
        'strategie': {'momentum': {'stop_loss': 0.03, 'take_profit': 0.06}},
        'database': {'pad': ':memory:'},
        'exchanges': {
            'bitvavo': {'actief': False, 'paper_trading': True, 'api_key': '', 'api_secret': ''},
            'kraken': {'actief': False, 'paper_trading': True, 'api_key': '', 'api_secret': ''},
            'ibkr': {'actief': False, 'paper_trading': True},
        },
    }


def test_trade_table_migrates_slippage_column_idempotently(tmp_path, monkeypatch):
    from agent.learning.memory import AgentMemory

    monkeypatch.chdir(tmp_path)
    logs_dir = tmp_path / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    db_path = logs_dir / "agent_geheugen.db"

    with sqlite3.connect(db_path) as conn:
        conn.execute("""
            CREATE TABLE trades (
                id TEXT PRIMARY KEY,
                symbool TEXT,
                richting TEXT,
                strategie_type TEXT,
                entry_prijs REAL,
                exit_prijs REAL,
                hoeveelheid REAL,
                euro_bedrag REAL,
                pnl REAL,
                pnl_pct REAL,
                entry_tijdstip TEXT,
                exit_tijdstip TEXT,
                reden_entry TEXT,
                reden_exit TEXT,
                geleerd TEXT,
                regime TEXT,
                sentiment_score REAL,
                exchange TEXT
            )
        """)
        conn.commit()

    AgentMemory(_memory_cfg())
    AgentMemory(_memory_cfg())

    with sqlite3.connect(db_path) as conn:
        columns = [row[1] for row in conn.execute("PRAGMA table_info(trades)").fetchall()]

    assert columns.count("slippage_bps") == 1


def test_legacy_rows_with_null_slippage_load_correctly(tmp_path, monkeypatch):
    from agent.learning.memory import AgentMemory

    monkeypatch.chdir(tmp_path)
    geheugen = AgentMemory(_memory_cfg())

    with sqlite3.connect(geheugen.db_pad) as conn:
        conn.execute("""
            INSERT INTO trades (
                id, symbool, richting, strategie_type, entry_prijs, exit_prijs,
                hoeveelheid, euro_bedrag, pnl, pnl_pct, entry_tijdstip,
                exit_tijdstip, reden_entry, reden_exit, geleerd, regime,
                sentiment_score, exchange, stop_loss_pct, take_profit_pct, slippage_bps
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            "legacy-trade",
            "BTC/EUR",
            "long",
            "rsi",
            50000.0,
            None,
            0.01,
            500.0,
            None,
            None,
            "2026-04-10 12:00:00.000000",
            None,
            "legacy-entry",
            "",
            "",
            "trend",
            0.0,
            "paper",
            0.03,
            0.07,
            None,
        ))
        conn.commit()

    trade = geheugen.laad_trade("legacy-trade")

    assert trade is not None
    assert trade.slippage_bps is None
    assert trade.stop_loss_pct == 0.03
    assert trade.take_profit_pct == 0.07


def test_new_rows_round_trip_with_slippage(tmp_path, monkeypatch):
    from agent.learning.memory import AgentMemory

    monkeypatch.chdir(tmp_path)
    geheugen = AgentMemory(_memory_cfg())
    trade = Trade(
        id="roundtrip-trade",
        symbool="BTC/EUR",
        richting="long",
        strategie_type="rsi",
        entry_prijs=50000.0,
        exit_prijs=None,
        hoeveelheid=0.01,
        euro_bedrag=500.0,
        pnl=None,
        pnl_pct=None,
        entry_tijdstip=datetime(2026, 4, 10, 12, 0, 0),
        exit_tijdstip=None,
        reden_entry="unit-test",
        reden_exit="",
        geleerd="",
        regime="trend",
        sentiment_score=0.0,
        exchange="paper",
        stop_loss_pct=0.03,
        take_profit_pct=0.07,
        slippage_bps=12.3456,
    )

    geheugen.sla_trade_op(trade)
    loaded = geheugen.laad_trade("roundtrip-trade")

    assert loaded is not None
    assert loaded.slippage_bps == 12.3456
    assert loaded.entry_prijs == trade.entry_prijs
    assert loaded.entry_tijdstip == trade.entry_tijdstip
