from __future__ import annotations

from pathlib import Path

import pytest

from agent.runtime_config import RuntimeConfigError, load_runtime_config, redact_sensitive_values


def _write_config(path: Path, *, polymarket_active: bool) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(
            [
                "agent:",
                '  naam: "test"',
                "kapitaal:",
                "  start: 1000",
                "exchanges:",
                "  polymarket:",
                f"    actief: {'true' if polymarket_active else 'false'}",
                '    private_key: "env:POLYMARKET_PRIVATE_KEY"',
                '    proxy_wallet: "env:POLYMARKET_PROXY_WALLET"',
                '    alchemy_rpc: "env:POLYMARKET_ALCHEMY_RPC_URL"',
            ]
        ),
        encoding="utf-8",
    )


def test_disabled_polymarket_does_not_require_runtime_secrets(monkeypatch, tmp_path: Path) -> None:
    config_path = tmp_path / "config.yaml"
    _write_config(config_path, polymarket_active=False)

    monkeypatch.delenv("POLYMARKET_PRIVATE_KEY", raising=False)
    monkeypatch.delenv("POLYMARKET_ALCHEMY_RPC_URL", raising=False)
    monkeypatch.delenv("POLYMARKET_PROXY_WALLET", raising=False)

    config = load_runtime_config(str(config_path))

    assert config["exchanges"]["polymarket"]["actief"] is False
    assert config["exchanges"]["polymarket"]["private_key"] == ""


def test_active_polymarket_fails_closed_without_runtime_secrets(monkeypatch, tmp_path: Path) -> None:
    config_path = tmp_path / "config.yaml"
    _write_config(config_path, polymarket_active=True)

    monkeypatch.delenv("POLYMARKET_PRIVATE_KEY", raising=False)
    monkeypatch.delenv("POLYMARKET_ALCHEMY_RPC_URL", raising=False)
    monkeypatch.delenv("POLYMARKET_PROXY_WALLET", raising=False)

    with pytest.raises(RuntimeConfigError) as excinfo:
        load_runtime_config(str(config_path))

    message = str(excinfo.value)
    assert "POLYMARKET_PRIVATE_KEY" in message
    assert "POLYMARKET_ALCHEMY_RPC_URL" in message
    assert "POLYMARKET_PROXY_WALLET" in message
    assert "env:" not in message


def test_runtime_config_supports_env_and_file_secret_injection(monkeypatch, tmp_path: Path) -> None:
    config_path = tmp_path / "config.yaml"
    secret_file = tmp_path / "poly_wallet.secret"
    _write_config(config_path, polymarket_active=True)
    secret_file.write_text("0xproxy", encoding="utf-8")

    monkeypatch.setenv("POLYMARKET_PRIVATE_KEY", "pm-test-secret")
    monkeypatch.setenv("POLYMARKET_ALCHEMY_RPC_URL", "https://alchemy.example/rpc")
    monkeypatch.setenv("POLYMARKET_PROXY_WALLET_FILE", str(secret_file))

    config = load_runtime_config(str(config_path))

    assert config["exchanges"]["polymarket"]["private_key"] == "pm-test-secret"
    assert config["exchanges"]["polymarket"]["alchemy_rpc"] == "https://alchemy.example/rpc"
    assert config["exchanges"]["polymarket"]["proxy_wallet"] == "0xproxy"


def test_runtime_secret_redaction_removes_secret_values_from_payload(monkeypatch, tmp_path: Path) -> None:
    config_path = tmp_path / "config.yaml"
    _write_config(config_path, polymarket_active=True)
    sample_secret = "runtime-placeholder-value"

    monkeypatch.setenv("POLYMARKET_PRIVATE_KEY", sample_secret)
    monkeypatch.setenv("POLYMARKET_ALCHEMY_RPC_URL", "https://alchemy.example/rpc")
    monkeypatch.setenv("POLYMARKET_PROXY_WALLET", "0xproxy")

    config = load_runtime_config(str(config_path))
    payload = {
        "status": "FAILED",
        "private_key": sample_secret,
        "detail": f"secret used: {sample_secret}",
        "nested": [{"proxy_wallet": "0xproxy"}],
    }

    redacted = redact_sensitive_values(payload, config=config)
    flat = str(redacted)

    assert sample_secret not in flat
    assert "0xproxy" not in flat
    assert "[REDACTED]" in flat
