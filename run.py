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

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(levelname)s | %(name)s | %(message)s',
    handlers=[
        logging.FileHandler('logs/agent.log'),
        logging.StreamHandler()
    ]
)

log = logging.getLogger(__name__)


async def main():
    log.info("=" * 60)
    log.info("JvR TRADING AGENT - GESTART (multi-agent orchestrator)")
    log.info("=" * 60)

    import yaml
    with open('config/config.yaml') as f:
        config = yaml.safe_load(f)

    log.info("Paper trading modus actief — geen echt geld in gebruik")
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
