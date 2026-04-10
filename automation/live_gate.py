"""Out-of-config live-trading gate with signed TTL state."""

from __future__ import annotations

import hashlib
import hmac
import json
import secrets
from datetime import datetime, timedelta, timezone
from pathlib import Path

from reporting import audit_log

STATE_PATH = Path("state/live_armed.json")
SECRET_PATH = Path("state/live_gate.secret")
MAX_TTL_HOURS = 24


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _isoformat_utc(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat()


def _parse_utc(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _ensure_secret() -> str:
    SECRET_PATH.parent.mkdir(parents=True, exist_ok=True)
    if SECRET_PATH.exists():
        return SECRET_PATH.read_text(encoding="utf-8").strip()

    secret = secrets.token_hex(32)
    SECRET_PATH.write_text(secret, encoding="utf-8")
    return secret


def _payload_signature(operator_id: str, armed_at_utc: str, expires_at_utc: str, candidate_id: str) -> str:
    secret = _ensure_secret().encode("utf-8")
    message = "|".join([operator_id, armed_at_utc, expires_at_utc, candidate_id]).encode("utf-8")
    return hmac.new(secret, message, hashlib.sha256).hexdigest()


def _load_state() -> dict | None:
    if not STATE_PATH.exists():
        return None
    with open(STATE_PATH, encoding="utf-8") as handle:
        return json.load(handle)


def is_live_armed() -> bool:
    """Return True only when the signed live gate exists and has not expired."""
    try:
        state = _load_state()
        if not state:
            return False

        required = {"operator_id", "armed_at_utc", "expires_at_utc", "candidate_id", "signature"}
        if required - set(state):
            return False

        armed_at = _parse_utc(state["armed_at_utc"])
        expires_at = _parse_utc(state["expires_at_utc"])
        now = _utc_now()
        if expires_at <= now or expires_at <= armed_at:
            return False
        if expires_at - armed_at > timedelta(hours=MAX_TTL_HOURS):
            return False

        expected = _payload_signature(
            operator_id=state["operator_id"],
            armed_at_utc=state["armed_at_utc"],
            expires_at_utc=state["expires_at_utc"],
            candidate_id=state["candidate_id"],
        )
        return hmac.compare_digest(state["signature"], expected)
    except (OSError, ValueError, json.JSONDecodeError, TypeError):
        return False


def arm(operator_id: str, candidate_id: str, ttl_hours: int) -> None:
    """Arm live trading for a bounded period and append an audit entry."""
    if ttl_hours <= 0 or ttl_hours > MAX_TTL_HOURS:
        raise ValueError(f"ttl_hours must be between 1 and {MAX_TTL_HOURS}")

    armed_at = _utc_now()
    expires_at = armed_at + timedelta(hours=ttl_hours)
    state = {
        "operator_id": operator_id,
        "armed_at_utc": _isoformat_utc(armed_at),
        "expires_at_utc": _isoformat_utc(expires_at),
        "candidate_id": candidate_id,
    }
    state["signature"] = _payload_signature(
        operator_id=state["operator_id"],
        armed_at_utc=state["armed_at_utc"],
        expires_at_utc=state["expires_at_utc"],
        candidate_id=state["candidate_id"],
    )

    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(STATE_PATH, "w", encoding="utf-8") as handle:
        json.dump(state, handle, ensure_ascii=False, indent=2)

    audit_log.append(
        event="live_gate_armed",
        actor=operator_id,
        payload={
            "candidate_id": candidate_id,
            "expires_at_utc": state["expires_at_utc"],
            "ttl_hours": ttl_hours,
        },
    )


def disarm(reason: str) -> None:
    """Disarm live trading and append an audit entry."""
    state = _load_state() or {}
    actor = state.get("operator_id", "system")
    if STATE_PATH.exists():
        STATE_PATH.unlink()

    audit_log.append(
        event="live_gate_disarmed",
        actor=actor,
        payload={
            "reason": reason,
            "candidate_id": state.get("candidate_id", ""),
        },
    )
