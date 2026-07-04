from __future__ import annotations

from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[2]


def _compose() -> dict:
    return yaml.safe_load((REPO_ROOT / "docker-compose.yml").read_text(encoding="utf-8"))


def test_supervisor_service_is_isolated_from_agent_dependency() -> None:
    supervisor = _compose()["services"]["qre-research-supervisor"]

    assert "depends_on" not in supervisor
    assert supervisor["command"] == [
        "python",
        "-m",
        "reporting.qre_research_supervisor",
        "--loop",
        "--interval-seconds",
        "300",
        "--max-iterations",
        "24",
    ]
    assert supervisor["restart"] == "unless-stopped"


def test_supervisor_service_declares_required_volumes_and_healthcheck() -> None:
    supervisor = _compose()["services"]["qre-research-supervisor"]
    mounts = set(supervisor["volumes"])

    assert "./generated_research:/app/generated_research" in mounts
    assert "./logs:/app/logs" in mounts
    assert "./data/cache:/app/data/cache" in mounts
    assert supervisor["healthcheck"]["test"] == [
        "CMD",
        "python",
        "-m",
        "reporting.qre_research_supervisor",
        "--healthcheck",
    ]
    assert supervisor["healthcheck"]["interval"] == "30s"
    assert supervisor["healthcheck"]["timeout"] == "10s"
    assert supervisor["healthcheck"]["retries"] == 3
    assert supervisor["healthcheck"]["start_period"] == "20s"


def test_agent_service_uses_runtime_secret_placeholders_only() -> None:
    agent = _compose()["services"]["agent"]
    environment = set(agent["environment"])

    assert "POLYMARKET_PRIVATE_KEY" in environment
    assert "POLYMARKET_ALCHEMY_RPC_URL" in environment
    assert "POLYMARKET_PROXY_WALLET" in environment
    assert all("0x" not in item for item in environment)
    assert all("alchemy.example" not in item for item in environment)
