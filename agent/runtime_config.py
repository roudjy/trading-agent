from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import yaml

POLYMARKET_SECRET_ENV_MAP = {
    "private_key": ("POLYMARKET_PRIVATE_KEY", "POLYMARKET_PRIVATE_KEY_FILE"),
    "alchemy_rpc": ("POLYMARKET_ALCHEMY_RPC_URL", "POLYMARKET_ALCHEMY_RPC_URL_FILE"),
    "proxy_wallet": ("POLYMARKET_PROXY_WALLET", "POLYMARKET_PROXY_WALLET_FILE"),
}
_PLACEHOLDER_VALUES = {"", "INVULLEN", "env", "secret"}
_SENSITIVE_FIELD_NAMES = {"private_key", "alchemy_rpc", "api_key", "api_secret", "secret", "token", "password"}


class RuntimeConfigError(RuntimeError):
    """Raised when runtime configuration is incomplete for an active exchange."""


def _read_secret_value(env_name: str, file_env_name: str) -> str:
    direct = str(os.environ.get(env_name) or "").strip()
    if direct:
        return direct
    file_path = str(os.environ.get(file_env_name) or "").strip()
    if not file_path:
        return ""
    candidate = Path(file_path)
    if not candidate.is_file():
        raise RuntimeConfigError(f"runtime secret file missing for {env_name}: {file_env_name}")
    return candidate.read_text(encoding="utf-8").strip()


def _looks_like_placeholder(value: Any) -> bool:
    text = str(value or "").strip()
    if not text:
        return True
    lowered = text.lower()
    if lowered in {item.lower() for item in _PLACEHOLDER_VALUES}:
        return True
    if lowered.startswith("env:") or lowered.startswith("${"):
        return True
    return False


def load_runtime_config(config_path: str = "config/config.yaml") -> dict[str, Any]:
    path = Path(config_path)
    if not path.exists():
        return {}
    with path.open(encoding="utf-8") as handle:
        payload = yaml.safe_load(handle) or {}
    if not isinstance(payload, dict):
        return {}
    return apply_runtime_secrets(payload)


def apply_runtime_secrets(config: dict[str, Any]) -> dict[str, Any]:
    exchanges = config.get("exchanges")
    if not isinstance(exchanges, dict):
        return config
    polymarket = exchanges.get("polymarket")
    if not isinstance(polymarket, dict):
        return config
    missing: list[str] = []
    for field, (env_name, file_env_name) in POLYMARKET_SECRET_ENV_MAP.items():
        resolved = _read_secret_value(env_name, file_env_name)
        if resolved:
            polymarket[field] = resolved
            continue
        if _looks_like_placeholder(polymarket.get(field)):
            polymarket[field] = ""
        if bool(polymarket.get("actief")) and not str(polymarket.get(field) or "").strip():
            missing.append(env_name)
    if bool(polymarket.get("actief")) and missing:
        joined = ", ".join(missing)
        raise RuntimeConfigError(f"Polymarket actief maar runtime secrets ontbreken: {joined}")
    return config


def redact_sensitive_values(payload: Any, *, config: dict[str, Any] | None = None) -> Any:
    secrets = {
        value
        for env_name, file_env_name in POLYMARKET_SECRET_ENV_MAP.values()
        for value in (
            str(os.environ.get(env_name) or "").strip(),
            str(os.environ.get(file_env_name) or "").strip(),
        )
        if value
    }
    if config:
        exchanges = config.get("exchanges") if isinstance(config, dict) else {}
        polymarket = exchanges.get("polymarket") if isinstance(exchanges, dict) else {}
        if isinstance(polymarket, dict):
            for field in POLYMARKET_SECRET_ENV_MAP:
                value = str(polymarket.get(field) or "").strip()
                if value:
                    secrets.add(value)
    return _redact(payload, secrets=secrets)


def _redact(payload: Any, *, secrets: set[str]) -> Any:
    if isinstance(payload, dict):
        redacted: dict[str, Any] = {}
        for key, value in payload.items():
            if str(key).lower() in _SENSITIVE_FIELD_NAMES:
                redacted[key] = "[REDACTED]"
            else:
                redacted[key] = _redact(value, secrets=secrets)
        return redacted
    if isinstance(payload, list):
        return [_redact(item, secrets=secrets) for item in payload]
    if isinstance(payload, tuple):
        return tuple(_redact(item, secrets=secrets) for item in payload)
    if isinstance(payload, str):
        redacted = payload
        for secret in sorted(secrets, key=len, reverse=True):
            redacted = redacted.replace(secret, "[REDACTED]")
        return redacted
    return payload


__all__ = [
    "POLYMARKET_SECRET_ENV_MAP",
    "RuntimeConfigError",
    "apply_runtime_secrets",
    "load_runtime_config",
    "redact_sensitive_values",
]
