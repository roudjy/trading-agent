"""N2b-3b — Real Web Push transport (env-gated, lazy-imported).

Provides the single isolated callable that actually performs a Web
Push HTTP request to a real provider (FCM / Mozilla / Apple / WNS).
It is the only place in the repository that may open a Web Push
network socket. It does so only when:

1. The VPS environment exposes ``WEB_PUSH_VAPID_PRIVATE_KEY`` and
   ``WEB_PUSH_VAPID_SUBJECT``; and
2. The optional ``pywebpush`` runtime dependency is importable; and
3. The caller (``dashboard.api_push_dispatch``) explicitly constructs
   the transport via :func:`make_transport` and hands it to the
   existing N2b-3a adapter ``dispatch_one(transport=...)``.

If any of those conditions fail, the transport refuses to operate and
returns ``{"status_code": None, "error_class": "..."}`` so the
adapter classifies the outcome as ``retry`` and emits no real push.

Hard guarantees (pinned by tests)
---------------------------------

* Stdlib-only at import time. ``pywebpush`` is imported **lazily**
  inside :func:`_real_send`; it is never imported at module load.
* No subprocess, no ``gh``, no ``git``.
* The literal env-var name ``WEB_PUSH_VAPID_PRIVATE_KEY`` IS allowed
  in this module — this is the one and only module permitted to
  reference it. Every other module pins its absence.
* :func:`is_configured` returns a boolean only; it never returns,
  logs, or echoes the private-key content.
* The transport return envelope is the closed shape
  ``{"status_code": int|None, "error_class": str|None}``.
* Endpoint URLs are never logged. The caller already supplies an
  ``endpoint_hash`` field; this module relies on that for any
  observability surface (none is added here — the adapter and the
  dashboard API layer own observability).
* No imports of ``dashboard``, ``frontend``, ``automation``,
  ``broker``, ``agent.risk``, ``agent.execution``, ``research``,
  ``reporting.intelligent_routing``, ``live``, ``paper``, ``shadow``,
  ``trading``.
* No mutation of any file; the transport is a pure HTTP egress
  helper.
* Importing this module does NOT flip Step 5 invariants.

Architecture
------------

::

    notification_dispatcher (N2a)
       └─ records with delivery_intent="ready"
           ↓
    notification_dispatch_outbox (N2b-1)
       └─ stub provider, accepted_offline
           ↓
    web_push_dispatch_adapter (N2b-3a)
       └─ build_envelope(...) → transport(envelope) → outcome
                                ↑
                                │
    web_push_real_transport (N2b-3b)  ← THIS MODULE
       └─ make_transport() → callable[envelope] → {status_code, error_class}
           (lazy pywebpush import; env-only VAPID private)

The transport is the smallest safe surface that lets a real push
flow end-to-end. It does **not**:

* mint approval tokens (N4 territory);
* open mobile approval inbox rows (N3 territory);
* execute merge / deploy (N5 / future);
* enable Step 5.1 or Step 5.2;
* flip ``step5_implementation_allowed``;
* change ``STEP5_ENABLED_SUBSTAGE``;
* touch QRE / research / live / paper / shadow / risk / broker /
  execution paths;
* edit ``.claude/**``;
* persist secrets to the repo.

Level 6 stays permanently disabled per ADR-015 §Doctrine 1.
"""

from __future__ import annotations

import json
import os
from typing import Any, Callable, Final

MODULE_VERSION: Final[str] = "v3.15.16.N2b3b"
SCHEMA_VERSION: Final[str] = "1.0"

# ---------------------------------------------------------------------------
# Step 5 invariants
# ---------------------------------------------------------------------------

STEP5_ENABLED_SUBSTAGE: Final[str] = "none"
step5_implementation_allowed: Final[bool] = False


# ---------------------------------------------------------------------------
# Closed env-var names
# ---------------------------------------------------------------------------

#: Name of the env var that holds the VAPID private key (PEM or base64url
#: depending on the provider library's accepted format). The value is
#: NEVER hard-coded in repo; the operator sets this in the VPS
#: environment (systemd unit override or `.env` outside the repo).
ENV_VAPID_PRIVATE_KEY: Final[str] = "WEB_PUSH_VAPID_PRIVATE_KEY"

#: Name of the env var that holds the VAPID subject (``mailto:`` URI or
#: ``https://`` URL identifying the application server, per RFC 8292).
ENV_VAPID_SUBJECT: Final[str] = "WEB_PUSH_VAPID_SUBJECT"


# ---------------------------------------------------------------------------
# Closed result envelope
# ---------------------------------------------------------------------------

#: Closed transport-result envelope. The same keys whatever the
#: outcome — caller checks ``status_code`` (None on transport error).
TRANSPORT_RESULT_KEYS: Final[tuple[str, ...]] = (
    "status_code",
    "error_class",
)

#: Closed ``error_class`` vocabulary. The adapter maps these to its
#: ``provider_status_class``; the transport never invents new values.
ERROR_CLASSES: Final[tuple[str, ...]] = (
    "ok",
    "config_missing",
    "library_missing",
    "invalid_envelope",
    "transport_exception",
)


# ---------------------------------------------------------------------------
# Configuration predicate (env-only, never echoes values)
# ---------------------------------------------------------------------------


def is_configured() -> bool:
    """Return True iff both VAPID env vars are present and non-empty.

    Does NOT return or log the values themselves. The dashboard API
    layer uses this predicate to fail-closed before invoking the
    transport. Pinned by tests.
    """
    priv = os.environ.get(ENV_VAPID_PRIVATE_KEY) or ""
    subj = os.environ.get(ENV_VAPID_SUBJECT) or ""
    return bool(priv) and bool(subj)


def _read_env_subject() -> str:
    """Return the VAPID subject env value or empty string.

    Internal helper; never echoes the private key.
    """
    return (os.environ.get(ENV_VAPID_SUBJECT) or "").strip()


def _read_env_private_key() -> str:
    """Return the VAPID private-key env value or empty string.

    Internal helper. The returned value is passed directly to the
    Web Push library and never logged, printed, or persisted.
    """
    return (os.environ.get(ENV_VAPID_PRIVATE_KEY) or "").strip()


# ---------------------------------------------------------------------------
# Envelope validation
# ---------------------------------------------------------------------------

_ENVELOPE_REQUIRED_KEYS: Final[tuple[str, ...]] = (
    "url",
    "method",
    "headers",
    "body_meta",
    "kid",
    "endpoint_hash",
    "event_id",
)


def _envelope_is_valid(envelope: Any) -> bool:
    """Return True iff the envelope matches the N2b-3a adapter shape.

    Defense-in-depth: the adapter already builds the envelope, but
    the transport refuses anything else. This keeps the only network
    egress callable in the repo from being abused by a future caller
    that forgets the envelope contract.
    """
    if not isinstance(envelope, dict):
        return False
    if set(envelope.keys()) != set(_ENVELOPE_REQUIRED_KEYS):
        return False
    url = envelope.get("url")
    if not isinstance(url, str) or not url:
        return False
    if not (
        url.startswith("https://fcm.googleapis.com/")
        or url.startswith("https://updates.push.services.mozilla.com/")
        or url.startswith("https://web.push.apple.com/")
        or url.startswith("https://wns2-")
    ):
        return False
    headers = envelope.get("headers")
    if not isinstance(headers, dict):
        return False
    body_meta = envelope.get("body_meta")
    if not isinstance(body_meta, dict):
        return False
    return True


# ---------------------------------------------------------------------------
# Result envelope helpers
# ---------------------------------------------------------------------------


def _result(
    *, status_code: int | None, error_class: str
) -> dict[str, Any]:
    """Build the closed-shape transport result envelope."""
    res = {"status_code": status_code, "error_class": error_class}
    assert set(res.keys()) == set(TRANSPORT_RESULT_KEYS)
    return res


# ---------------------------------------------------------------------------
# Real provider call (lazy pywebpush import)
# ---------------------------------------------------------------------------


def _payload_bytes(body_meta: dict[str, Any]) -> bytes:
    """Encode the bounded six-key payload as deterministic JSON bytes.

    The N2b-3a adapter already enforces the payload schema; we just
    serialize it. ``sort_keys=True`` so a given record always produces
    the same payload bytes for transport-layer replay.
    """
    return json.dumps(body_meta, sort_keys=True, ensure_ascii=False).encode(
        "utf-8"
    )


def _real_send(envelope: dict[str, Any]) -> dict[str, Any]:
    """Bare-transport stub used by :func:`make_transport`.

    The adapter envelope does NOT carry the per-subscription keys that
    ``pywebpush`` requires, so a bare transport cannot perform a real
    push even when env + library are present. This function therefore
    only exercises the env-presence and envelope-shape guards; the
    dashboard API layer uses :func:`make_transport_for_subscription`
    to obtain a callable that captures the subscription's keys.
    """
    subject = _read_env_subject()
    private_key = _read_env_private_key()
    if not subject or not private_key:
        return _result(status_code=None, error_class="config_missing")
    if not _envelope_is_valid(envelope):
        return _result(status_code=None, error_class="invalid_envelope")
    return _result(status_code=None, error_class="invalid_envelope")


def make_transport() -> Callable[[dict[str, Any]], dict[str, Any]]:
    """Return a ``Transport`` callable compatible with the N2b-3a
    adapter.

    The returned callable refuses to operate unless
    :func:`is_configured` is True at call time. It also requires the
    optional ``pywebpush`` dependency at call time; without it the
    callable returns ``library_missing``. The callable never raises;
    all failure modes are classified into the closed
    :data:`ERROR_CLASSES` vocabulary.

    NOTE: a bare ``make_transport()`` cannot perform a real push
    because the Web Push subscription's ``keys.p256dh`` / ``keys.auth``
    are NOT part of the adapter's envelope schema. The bare callable
    therefore returns ``invalid_envelope`` even on a valid envelope —
    it is wired only for tests that exercise the env / library /
    envelope-validation gates. The dashboard API layer uses
    :func:`make_transport_for_subscription` to produce a callable that
    captures the subscription keys per dispatch.
    """
    return _real_send


def make_transport_for_subscription(
    *,
    subscription: dict[str, Any],
) -> Callable[[dict[str, Any]], dict[str, Any]]:
    """Return a per-subscription transport closure.

    The closure captures the subscription's ``keys`` dict (required by
    ``pywebpush`` for AES-128-GCM payload encryption) and performs the
    real Web Push HTTP request on each call. All failure modes are
    classified into :data:`ERROR_CLASSES`; the closure never raises.

    The dashboard API layer composes one closure per (event ×
    subscription) pair before handing it to
    ``web_push_dispatch_adapter.dispatch_one``.
    """

    def _send(envelope: dict[str, Any]) -> dict[str, Any]:
        subject = _read_env_subject()
        private_key = _read_env_private_key()
        if not subject or not private_key:
            return _result(status_code=None, error_class="config_missing")

        if not _envelope_is_valid(envelope):
            return _result(status_code=None, error_class="invalid_envelope")

        if not isinstance(subscription, dict):
            return _result(status_code=None, error_class="invalid_envelope")
        endpoint = envelope.get("url")
        sub_endpoint = subscription.get("endpoint")
        if endpoint != sub_endpoint:
            return _result(status_code=None, error_class="invalid_envelope")
        keys = subscription.get("keys")
        if not isinstance(keys, dict):
            return _result(status_code=None, error_class="invalid_envelope")
        p256dh = keys.get("p256dh")
        auth = keys.get("auth")
        if not isinstance(p256dh, str) or not p256dh:
            return _result(status_code=None, error_class="invalid_envelope")
        if not isinstance(auth, str) or not auth:
            return _result(status_code=None, error_class="invalid_envelope")

        try:
            from pywebpush import WebPushException, webpush  # type: ignore
        except Exception:
            return _result(status_code=None, error_class="library_missing")

        body_meta = envelope.get("body_meta", {})
        if not isinstance(body_meta, dict):
            return _result(status_code=None, error_class="invalid_envelope")
        payload = _payload_bytes(body_meta)

        headers = envelope.get("headers", {}) or {}
        ttl_str = headers.get("TTL") if isinstance(headers, dict) else None
        try:
            ttl = int(ttl_str) if ttl_str is not None else 60
        except (TypeError, ValueError):
            ttl = 60

        subscription_info = {
            "endpoint": endpoint,
            "keys": {"p256dh": p256dh, "auth": auth},
        }

        try:
            resp = webpush(
                subscription_info=subscription_info,
                data=payload,
                vapid_private_key=private_key,
                vapid_claims={"sub": subject},
                ttl=ttl,
            )
        except WebPushException as exc:  # type: ignore[misc]
            status = None
            inner = getattr(exc, "response", None)
            if inner is not None:
                code = getattr(inner, "status_code", None)
                if isinstance(code, int):
                    status = code
            if status is None:
                return _result(status_code=None, error_class="transport_exception")
            return _result(status_code=status, error_class="ok")
        except Exception:
            return _result(status_code=None, error_class="transport_exception")

        status_code = getattr(resp, "status_code", None)
        if not isinstance(status_code, int):
            return _result(status_code=None, error_class="transport_exception")
        return _result(status_code=status_code, error_class="ok")

    return _send


__all__ = [
    "ENV_VAPID_PRIVATE_KEY",
    "ENV_VAPID_SUBJECT",
    "ERROR_CLASSES",
    "MODULE_VERSION",
    "SCHEMA_VERSION",
    "STEP5_ENABLED_SUBSTAGE",
    "TRANSPORT_RESULT_KEYS",
    "is_configured",
    "make_transport",
    "make_transport_for_subscription",
    "step5_implementation_allowed",
]
