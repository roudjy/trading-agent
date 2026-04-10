"""
START SCRIPT
============
Start de trading agent (Orchestrator + sub-agents).
Dashboard draait als aparte container via docker compose.
Gebruik: python run.py
"""

import asyncio
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from agent.brain.orchestrator import Orchestrator
from automation import live_gate

Path('logs').mkdir(exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)s | %(name)s | %(message)s',
    handlers=[
        logging.FileHandler('logs/agent.log'),
        logging.StreamHandler()
    ]
)

log = logging.getLogger(__name__)


def _live_requested(config: dict) -> bool:
    """Return True when any exchange is explicitly configured for live trading."""
    exchanges = config.get('exchanges', {})
    for exchange_config in exchanges.values():
        if isinstance(exchange_config, dict) and exchange_config.get('paper_trading') is False:
            return True
    return False


def _force_paper_mode(config: dict) -> None:
    """Flip all configured exchange paper/live flags back to paper mode."""
    for exchange_config in config.get('exchanges', {}).values():
        if isinstance(exchange_config, dict) and 'paper_trading' in exchange_config:
            exchange_config['paper_trading'] = True


def _enforce_live_gate(config: dict) -> None:
    """Prevent config-only live trading unless the out-of-config gate is armed."""
    if not _live_requested(config):
        log.info("Paper trading modus actief - geen echt geld in gebruik")
        return

    if live_gate.is_live_armed():
        log.warning("Live trading aangevraagd en live gate is gewapend.")
        return

    log.critical(
        "LIVE TRADING GEWEIGERD: config vraagt live modus, maar live gate is niet gewapend. "
        "Valt terug naar paper trading."
    )
    _force_paper_mode(config)
    log.info("Paper trading modus actief - geen echt geld in gebruik")


async def main():
    log.info("=" * 60)
    log.info("JvR TRADING AGENT - GESTART (multi-agent orchestrator)")
    log.info("=" * 60)

    import yaml
    with open('config/config.yaml') as f:
        config = yaml.safe_load(f)

    _enforce_live_gate(config)
    log.info("-" * 60)

    orchestrator = Orchestrator(config)
    await orchestrator.start()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        log.info("Agent gestopt door gebruiker")
    except Exception as e:
        log.critical(f"Agent gecrasht: {e}", exc_info=True)
        sys.exit(1)
