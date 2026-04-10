"""Regression tests for persisted stop-loss and take-profit trade fields."""

import sqlite3
from pathlib import Path

import pytest

from agent.risk.risk_manager import TradeSignaal


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


def test_trade_table_migrates_stop_loss_take_profit_columns(tmp_path, monkeypatch):
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

    with sqlite3.connect(db_path) as conn:
        columns = {row[1] for row in conn.execute("PRAGMA table_info(trades)").fetchall()}

    assert 'stop_loss_pct' in columns
    assert 'take_profit_pct' in columns


@pytest.mark.asyncio
async def test_executor_trade_persists_stop_loss_take_profit(tmp_path, monkeypatch):
    from agent.execution.order_executor import OrderExecutor
    from agent.learning.memory import AgentMemory

    monkeypatch.chdir(tmp_path)
    cfg = _memory_cfg()
    executor = OrderExecutor(cfg)
    geheugen = AgentMemory(cfg)

    signaal = TradeSignaal(
        symbool='BTC/EUR',
        richting='long',
        strategie_type='rsi_mean_reversion',
        verwacht_rendement=0.02,
        win_kans=0.60,
        stop_loss_pct=0.03,
        take_profit_pct=0.07,
        bron='persist-test',
        zekerheid=0.75,
        regime='trend',
    )

    trade = await executor._paper_trade(
        signaal,
        markt_data={'BTC/EUR': {'prijs': 50000.0}},
        max_bedrag=50.0,
    )
    assert trade is not None

    geheugen.sla_trade_op(trade)

    db_path = Path("logs/agent_geheugen.db")
    with sqlite3.connect(db_path) as conn:
        row = conn.execute(
            "SELECT stop_loss_pct, take_profit_pct FROM trades WHERE id = ?",
            (trade.id,),
        ).fetchone()

    assert row == (0.03, 0.07)
