"""N2b-2a — Push Subscription Store (backend, unwired).

Pure-stdlib subscription storage for the future PWA Web Push surface.
Manages the gitignored runtime config at
``config/web_push_subscriptions.json`` with strict closed-vocabulary
records, idempotent register/unregister semantics, atomic writes, and
a hard cap on active subscriptions.

This is the backend half of the smallest safe N2b-2 slice: it adds
the storage primitive **without** wiring the future API blueprint
into the running dashboard. ``dashboard/dashboard.py`` is unchanged.
``frontend/**`` is unchanged. **No real push is sent.** No network
socket is opened. No Web Push library is imported. **No VAPID
private key is read or stored.**

N2b-2b (PWA UI + service worker + 1-line dashboard.py wiring) and
N2b-3 (real Web Push delivery using env-only VAPID private) remain
unimplemented and require their own separate operator go-signals.
N3 (mobile approval inbox), N4 (approval-token gate), and N5
(merge/deploy adapter) remain unimplemented. Step 5.1 / 5.2 remain
BLOCKED. Level 6 stays permanently disabled per ADR-015 §Doctrine 1.

Hard guarantees (pinned by tests)
---------------------------------

* Stdlib + ``reporting.agent_audit_summary.assert_no_secrets``
  (read-only redactor guard).
* No subprocess, no network, no ``gh``, no ``git``, no ``socket``,
  no ``urllib``, no ``requests``, no ``httpx``, no ``aiohttp``, no
  Web Push library (``pywebpush``, ``web_push``, ``webpush``).
* No imports of ``dashboard``, ``frontend``, ``automation``,
  ``broker``, ``agent.risk``, ``agent.execution``, ``research``,
  ``reporting.intelligent_routing``, ``live``, ``paper``, ``shadow``,
  or ``trading``.
* The VAPID private-key environment variable name does not appear
  in this module. The private key is **N2b-3 only** and is read
  from the VPS environment, never from the repo.
* Atomic write only to the closed sentinel path
  ``config/web_push_subscriptions.json``. Refused for any other
  target.
* Active subscriptions capped at :data:`MAX_ACTIVE_SUBSCRIPTIONS`.
* Endpoint-based register / unregister are idempotent.
"""

from __future__ import annotations

import datetime as _dt
import hashlib
import json
import os
import tempfile
from pathlib import Path
from typing import Any, Final

REPO_ROOT: Final[Path] = Path(__file__).resolve().parent.parent

MODULE_VERSION: Final[str] = "v3.15.16.N2b2a"
SCHEMA_VERSION: Final[int] = 1


# ---------------------------------------------------------------------------
# Closed sentinel paths
# ---------------------------------------------------------------------------

#: Single sentinel path for the active-subscriptions store. Atomic
#: writes refuse any other target. The file is gitignored.
SUBSCRIPTIONS_PATH: Final[Path] = (
    REPO_ROOT / "config" / "web_push_subscriptions.json"
)
SUBSCRIPTIONS_RELATIVE_PATH: Final[str] = "config/web_push_subscriptions.json"

#: Public key path. The store knows about it but does not require it
#: to exist; the API layer (N2b-2b) reads it on demand.
VAPID_PUBLIC_PATH: Final[Path] = (
    REPO_ROOT / "config" / "web_push_vapid_public.txt"
)
VAPID_PUBLIC_RELATIVE_PATH: Final[str] = "config/web_push_vapid_public.txt"


# ---------------------------------------------------------------------------
# Closed vocabularies and bounds
# ---------------------------------------------------------------------------

#: Per-record schema, exact and ordered.
SUBSCRIPTION_RECORD_KEYS: Final[tuple[str, ...]] = (
    "endpoint",
    "keys",
    "kid",
    "created_at",
    "last_seen_at",
    "label",
)

#: Sub-keys for the ``keys`` field, exact and ordered.
SUBSCRIPTION_KEYS_FIELD_KEYS: Final[tuple[str, ...]] = ("p256dh", "auth")

#: Hard cap on active subscriptions (single-operator system; runaway
#: guard).
MAX_ACTIVE_SUBSCRIPTIONS: Final[int] = 16

#: Bounded length for free-text scalars on a single record.
MAX_ENDPOINT_LEN: Final[int] = 1024
MAX_P256DH_LEN: Final[int] = 200
MAX_AUTH_LEN: Final[int] = 200
MAX_KID_LEN: Final[int] = 64
MAX_LABEL_LEN: Final[int] = 80

#: Allowed origins for the push provider endpoint URLs. Anything else
#: is refused at register time. Pinned by tests; expansion requires a
#: code change.
ALLOWED_ENDPOINT_PREFIXES: Final[tuple[str, ...]] = (
    "https://fcm.googleapis.com/",
    "https://updates.push.services.mozilla.com/",
    "https://web.push.apple.com/",
    "https://wns2-",  # Microsoft WNS hosts (wns2-*.notify.windows.com)
)


# ---------------------------------------------------------------------------
# Utility helpers
# ---------------------------------------------------------------------------


def _utcnow() -> str:
    return (
        _dt.datetime.now(_dt.UTC)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def _bounded_str(value: Any, max_len: int) -> str:
    if not isinstance(value, str):
        return ""
    if len(value) <= max_len:
        return value
    return value[:max_len]


def endpoint_hash(endpoint: str) -> str:
    """Return a sha256-truncated identifier for an endpoint URL.

    Used in audit / log surfaces where the full endpoint must NOT
    appear. Pinned by tests; the API layer uses this helper to keep
    endpoint URLs out of any operator-visible status surface.
    """
    if not isinstance(endpoint, str):
        return ""
    return hashlib.sha256(endpoint.encode("utf-8")).hexdigest()[:16]


# ---------------------------------------------------------------------------
# Store I/O
# ---------------------------------------------------------------------------


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    """Atomic write. Refuses any path other than
    :data:`SUBSCRIPTIONS_PATH`. The closed sentinel keeps the
    write-side surface tiny; tests pin the refusal."""
    if path.resolve() != SUBSCRIPTIONS_PATH.resolve():
        raise ValueError(
            "push_subscription_store._atomic_write_json refuses "
            f"non-subscriptions path: {path}"
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    fd, tmp_name = tempfile.mkstemp(
        prefix=".push_subscription_store.",
        suffix=".tmp",
        dir=str(path.parent),
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(text)
        os.replace(tmp_name, path)
    except Exception:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise


def load_store(*, path: Path | None = None) -> dict[str, Any]:
    """Load the on-disk store. Returns an empty store envelope on
    first read or on any malformed-file condition.

    The envelope shape is:

    ``{"schema_version": 1, "subscriptions": [<record>, ...]}``

    Tests pin both behaviours.
    """
    p = path if path is not None else SUBSCRIPTIONS_PATH
    if not p.is_file():
        return {"schema_version": SCHEMA_VERSION, "subscriptions": []}
    try:
        text = p.read_text(encoding="utf-8")
    except OSError:
        return {"schema_version": SCHEMA_VERSION, "subscriptions": []}
    try:
        payload = json.loads(text)
    except ValueError:
        return {"schema_version": SCHEMA_VERSION, "subscriptions": []}
    if not isinstance(payload, dict):
        return {"schema_version": SCHEMA_VERSION, "subscriptions": []}
    subs = payload.get("subscriptions")
    if not isinstance(subs, list):
        return {"schema_version": SCHEMA_VERSION, "subscriptions": []}
    cleaned: list[dict[str, Any]] = []
    for s in subs:
        if isinstance(s, dict) and set(s.keys()) >= set(SUBSCRIPTION_RECORD_KEYS):
            cleaned.append(s)
    return {
        "schema_version": int(payload.get("schema_version") or SCHEMA_VERSION),
        "subscriptions": cleaned,
    }


def save_store(store: dict[str, Any], *, path: Path | None = None) -> Path:
    """Persist the store atomically. Refuses any non-sentinel path."""
    p = path if path is not None else SUBSCRIPTIONS_PATH
    payload = {
        "schema_version": int(store.get("schema_version") or SCHEMA_VERSION),
        "subscriptions": list(store.get("subscriptions") or []),
    }
    _atomic_write_json(p, payload)
    return p


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def _validate_record(raw: Any) -> tuple[dict[str, Any] | None, list[str]]:
    """Validate and normalize a register payload. Returns
    ``(record, warnings)`` where ``record`` is None on any failure."""
    warnings: list[str] = []
    if not isinstance(raw, dict):
        warnings.append("not_an_object")
        return None, warnings

    endpoint = _bounded_str(raw.get("endpoint"), MAX_ENDPOINT_LEN)
    if not endpoint:
        warnings.append("missing_endpoint")
        return None, warnings

    if not any(endpoint.startswith(p) for p in ALLOWED_ENDPOINT_PREFIXES):
        warnings.append("endpoint_origin_not_allowed")
        return None, warnings

    raw_keys = raw.get("keys")
    if not isinstance(raw_keys, dict):
        warnings.append("missing_keys")
        return None, warnings
    if set(raw_keys.keys()) != set(SUBSCRIPTION_KEYS_FIELD_KEYS):
        warnings.append("invalid_keys_shape")
        return None, warnings

    p256dh = _bounded_str(raw_keys.get("p256dh"), MAX_P256DH_LEN)
    auth = _bounded_str(raw_keys.get("auth"), MAX_AUTH_LEN)
    if not p256dh or not auth:
        warnings.append("empty_keys")
        return None, warnings

    kid = _bounded_str(raw.get("kid"), MAX_KID_LEN)
    if not kid:
        warnings.append("missing_kid")
        return None, warnings

    label = _bounded_str(raw.get("label"), MAX_LABEL_LEN)
    return (
        {
            "endpoint": endpoint,
            "keys": {"p256dh": p256dh, "auth": auth},
            "kid": kid,
            "created_at": "",  # filled at register time
            "last_seen_at": "",  # filled at register time
            "label": label,
        },
        warnings,
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def list_subscriptions(*, path: Path | None = None) -> list[dict[str, Any]]:
    """Return the active subscriptions list. Pure read."""
    return list(load_store(path=path).get("subscriptions") or [])


def get_by_endpoint(
    endpoint: str, *, path: Path | None = None
) -> dict[str, Any] | None:
    if not isinstance(endpoint, str) or not endpoint:
        return None
    for s in list_subscriptions(path=path):
        if s.get("endpoint") == endpoint:
            return s
    return None


def register_subscription(
    record: dict[str, Any],
    *,
    path: Path | None = None,
    now_utc: str | None = None,
) -> tuple[dict[str, Any] | None, list[str]]:
    """Register or refresh a subscription. Idempotent on ``endpoint``.

    Returns ``(record_or_None, warnings)``. ``None`` on any
    validation failure.
    """
    validated, warnings = _validate_record(record)
    if validated is None:
        return None, warnings

    ts = now_utc if now_utc is not None else _utcnow()
    store = load_store(path=path)
    subs: list[dict[str, Any]] = list(store.get("subscriptions") or [])

    # Idempotent refresh on existing endpoint.
    for i, s in enumerate(subs):
        if s.get("endpoint") == validated["endpoint"]:
            refreshed = {
                "endpoint": validated["endpoint"],
                "keys": dict(validated["keys"]),
                "kid": validated["kid"],
                "created_at": s.get("created_at") or ts,
                "last_seen_at": ts,
                "label": validated["label"] or s.get("label", ""),
            }
            subs[i] = refreshed
            store["subscriptions"] = subs
            save_store(store, path=path)
            return refreshed, warnings

    # Cap reached → refuse.
    if len(subs) >= MAX_ACTIVE_SUBSCRIPTIONS:
        warnings.append("subscription_cap_reached")
        return None, warnings

    new_record = {
        "endpoint": validated["endpoint"],
        "keys": dict(validated["keys"]),
        "kid": validated["kid"],
        "created_at": ts,
        "last_seen_at": ts,
        "label": validated["label"],
    }
    subs.append(new_record)
    store["subscriptions"] = subs
    save_store(store, path=path)
    return new_record, warnings


def unregister_subscription(
    endpoint: str, *, path: Path | None = None
) -> bool:
    """Remove a subscription by endpoint. Idempotent — returns
    ``True`` if a record was removed; ``False`` if absent."""
    if not isinstance(endpoint, str) or not endpoint:
        return False
    store = load_store(path=path)
    subs: list[dict[str, Any]] = list(store.get("subscriptions") or [])
    new_subs = [s for s in subs if s.get("endpoint") != endpoint]
    if len(new_subs) == len(subs):
        return False
    store["subscriptions"] = new_subs
    save_store(store, path=path)
    return True


# ---------------------------------------------------------------------------
# VAPID public-key helper (read-only, no network)
# ---------------------------------------------------------------------------


def vapid_public_present(*, path: Path | None = None) -> bool:
    """Return True iff ``config/web_push_vapid_public.txt`` exists.

    Does not read the file content. The API layer (N2b-2b) reads the
    content on demand.
    """
    p = path if path is not None else VAPID_PUBLIC_PATH
    return p.is_file()


def vapid_public_text(*, path: Path | None = None) -> str | None:
    """Return the public key text or ``None`` if absent / unreadable.

    Best-effort; never raises. Pinned by tests."""
    p = path if path is not None else VAPID_PUBLIC_PATH
    if not p.is_file():
        return None
    try:
        return p.read_text(encoding="utf-8").strip()
    except OSError:
        return None


__all__ = [
    "ALLOWED_ENDPOINT_PREFIXES",
    "MAX_ACTIVE_SUBSCRIPTIONS",
    "MODULE_VERSION",
    "SCHEMA_VERSION",
    "SUBSCRIPTIONS_PATH",
    "SUBSCRIPTIONS_RELATIVE_PATH",
    "SUBSCRIPTION_KEYS_FIELD_KEYS",
    "SUBSCRIPTION_RECORD_KEYS",
    "VAPID_PUBLIC_PATH",
    "VAPID_PUBLIC_RELATIVE_PATH",
    "endpoint_hash",
    "get_by_endpoint",
    "list_subscriptions",
    "load_store",
    "register_subscription",
    "save_store",
    "unregister_subscription",
    "vapid_public_present",
    "vapid_public_text",
]
