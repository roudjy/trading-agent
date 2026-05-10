"""N2b-3a — Web Push dispatch adapter (mocked transport, no socket).

Pure stdlib-only callable that **constructs** the HTTP request envelope
a real Web Push provider would receive (URL, headers, encrypted-body
placeholder, VAPID JWT placeholder) for a `delivery_intent="ready"`
notification record, and dispatches it through a **caller-supplied
transport function**.

This module **never opens a network socket**. It never imports a
Web Push library. It never reads a VAPID private key. The transport
parameter is mandatory and must be supplied by the caller; tests
supply a synthetic transport that records the call. Production
N2b-3b (deferred, separate operator-authorised PR) will supply a
real HTTP client.

Hard guarantees (pinned by tests)
---------------------------------

* Stdlib + ``reporting.notification_event`` (read-only) +
  ``reporting.notification_dispatcher`` (read-only) +
  ``reporting.push_subscription_store`` (read-only API) +
  ``reporting.agent_audit_summary.assert_no_secrets`` (read-only
  redactor guard).
* No subprocess, no network, no ``gh``, no ``git``, no ``socket``,
  no ``urllib``, no ``requests``, no ``httpx``, no ``aiohttp``, no
  Web Push library.
* No imports of ``dashboard``, ``frontend``, ``automation``,
  ``broker``, ``agent.risk``, ``agent.execution``, ``research``,
  ``reporting.intelligent_routing``, ``live``, ``paper``, ``shadow``,
  ``trading``.
* The literal env-var name for the VAPID private key does NOT
  appear in this module. The private key is **N2b-3b only** and is
  read from the VPS environment, never from the repo.
* `dispatch_one(...)` accepts ``transport`` only as a callable
  argument — there is no module-level default that would let a
  real HTTP client sneak in. A missing ``transport`` raises
  ``TypeError`` immediately.
* Closed `dispatch_outcome` vocabulary; closed `provider_status_class`
  vocabulary; closed payload schema (the same six-key payload N2b-1
  already produces).
* ``assert_no_secrets`` is run on every emitted record and on every
  outbound envelope.

Architecture
------------

::

    notification_dispatcher (N2a)
       └─ records with delivery_intent="ready"
           ↓
    notification_dispatch_outbox (N2b-1)
       └─ stub provider, accepted_offline
           ↓
    web_push_dispatch_adapter (N2b-3a)        ← THIS MODULE
       └─ transport(envelope) → outcome
           ↓
    [N2b-3b: real HTTP client; deferred and operator-authorised]

The adapter exists to **decouple** envelope construction from real
network I/O. By passing a synthetic transport in tests, we get
end-to-end coverage of:

* URL derivation from subscription endpoint;
* header set (`TTL`, `Content-Encoding`, `Content-Type`,
  `Authorization`-placeholder, `Crypto-Key`-placeholder);
* outcome classification (2xx → sent, 410 → drop_subscription,
  4xx-other → failed_provider, 5xx → retry);
* dedupe / rate-limit / failure mapping;
* `assert_no_secrets` is called on every envelope and every
  outcome record;

…all without ever opening a socket.

CLI
---

There is no CLI in N2b-3a. The adapter is a Python callable;
production wiring lives in N2b-3b's `dashboard/api_push_dispatch.py`.
"""

from __future__ import annotations

import datetime as _dt
import hashlib
import json
from typing import Any, Callable, Final

from reporting import notification_dispatcher as nd
from reporting import notification_event as ne
from reporting import push_subscription_store as pss
from reporting.agent_audit_summary import assert_no_secrets

MODULE_VERSION: Final[str] = "v3.15.16.N2b3a"
SCHEMA_VERSION: Final[str] = "1.0"

# ---------------------------------------------------------------------------
# Step 5 invariants
# ---------------------------------------------------------------------------

STEP5_ENABLED_SUBSTAGE: Final[str] = "none"
step5_implementation_allowed: Final[bool] = False


# ---------------------------------------------------------------------------
# Closed vocabularies
# ---------------------------------------------------------------------------

#: Closed dispatch-outcome vocabulary. Adding a value requires a
#: code change pinned by an updated unit test.
DISPATCH_OUTCOMES: Final[tuple[str, ...]] = (
    "sent",
    "drop_subscription",
    "failed_provider",
    "retry",
    "skipped_no_subscription",
    "skipped_invalid_record",
)

#: Closed provider-status classification. Mirrors HTTP semantics.
PROVIDER_STATUS_CLASSES: Final[tuple[str, ...]] = (
    "2xx",
    "410",
    "4xx_other",
    "5xx",
    "transport_error",
    "unknown",
)

#: Closed envelope-key set. The envelope passed to the transport
#: contains EXACTLY these keys. Catches accidental field bloat.
ENVELOPE_KEYS: Final[tuple[str, ...]] = (
    "url",
    "method",
    "headers",
    "body_meta",
    "kid",
    "endpoint_hash",
    "event_id",
)

#: Closed envelope-headers key set.
ENVELOPE_HEADERS_KEYS: Final[tuple[str, ...]] = (
    "TTL",
    "Content-Encoding",
    "Content-Type",
    "Authorization-Mode",
    "Crypto-Key-Mode",
)

#: Closed dispatch-record schema (one row per record dispatched).
DISPATCH_RECORD_KEYS: Final[tuple[str, ...]] = (
    "event_id",
    "event_kind",
    "event_severity",
    "endpoint_hash",
    "kid",
    "outcome",
    "provider_status_class",
    "provider_status_code",
    "envelope_url",
    "attempted_at",
)

#: Default Web Push TTL (seconds). Bounded; the value is a string in
#: HTTP headers but pinned at the module layer for tests.
DEFAULT_TTL_SECONDS: Final[int] = 60

#: Default `Content-Encoding` for Web Push payloads. The placeholder
#: name is what the real provider would expect; N2b-3a does not
#: actually encrypt.
CONTENT_ENCODING: Final[str] = "aes128gcm"

#: Default `Content-Type` for Web Push payloads.
CONTENT_TYPE: Final[str] = "application/octet-stream"

#: Authorization header placeholder mode. The real value is computed
#: in N2b-3b from the VAPID private key in the env. N2b-3a stamps
#: only the *mode* into the envelope.
AUTHORIZATION_MODE_PLACEHOLDER: Final[str] = "vapid_jwt_pending_n2b3b"

#: Crypto-Key header placeholder mode.
CRYPTO_KEY_MODE_PLACEHOLDER: Final[str] = "ecdh_p256_pending_n2b3b"


# ---------------------------------------------------------------------------
# Type aliases
# ---------------------------------------------------------------------------

#: A transport callable: takes an envelope dict, returns a dict with
#: at least ``status_code`` (int) and ``error_class`` (str | None).
#: The transport MUST NOT raise for HTTP-level failures — it must
#: classify them. Network exceptions raised by the transport are
#: classified by :func:`_classify_outcome` as ``transport_error``.
Transport = Callable[[dict[str, Any]], dict[str, Any]]


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


def _classify_status(status_code: int | None) -> str:
    if status_code is None:
        return "transport_error"
    if 200 <= status_code < 300:
        return "2xx"
    if status_code == 410:
        return "410"
    if 400 <= status_code < 500:
        return "4xx_other"
    if 500 <= status_code < 600:
        return "5xx"
    return "unknown"


def _classify_outcome(status_class: str) -> str:
    if status_class == "2xx":
        return "sent"
    if status_class == "410":
        return "drop_subscription"
    if status_class == "4xx_other":
        return "failed_provider"
    if status_class == "5xx":
        return "retry"
    if status_class == "transport_error":
        return "retry"
    return "failed_provider"


# ---------------------------------------------------------------------------
# Envelope construction
# ---------------------------------------------------------------------------


def build_envelope(
    *,
    record: dict[str, Any],
    subscription: dict[str, Any],
) -> dict[str, Any]:
    """Build the closed-schema HTTP envelope for one record + one
    subscription. Pure: no network, no socket, no key signing.

    The body is **not encrypted** in N2b-3a. We carry only a
    bounded ``body_meta`` block describing the future encrypted
    payload — the same six-key push payload N2b-1 already produces.
    N2b-3b will replace ``body_meta`` with the real encrypted body.
    """
    if not isinstance(record, dict):
        raise TypeError("record must be a dict")
    if not isinstance(subscription, dict):
        raise TypeError("subscription must be a dict")

    endpoint = subscription.get("endpoint")
    if not isinstance(endpoint, str) or not endpoint:
        raise ValueError("subscription.endpoint must be a non-empty string")
    kid = subscription.get("kid") or ""

    # Closed body-meta projection — mirrors the N2b-1 push payload.
    body_meta = {
        "event_id": str(record.get("event_id") or ""),
        "event_kind": str(record.get("event_kind") or ""),
        "event_severity": str(record.get("event_severity") or ""),
        "title": str(record.get("title") or ""),
        "summary": str(record.get("summary") or ""),
        "open_at": str(record.get("open_at") or ""),
    }

    headers: dict[str, Any] = {
        "TTL": str(DEFAULT_TTL_SECONDS),
        "Content-Encoding": CONTENT_ENCODING,
        "Content-Type": CONTENT_TYPE,
        "Authorization-Mode": AUTHORIZATION_MODE_PLACEHOLDER,
        "Crypto-Key-Mode": CRYPTO_KEY_MODE_PLACEHOLDER,
    }

    envelope: dict[str, Any] = {
        "url": endpoint,
        "method": "POST",
        "headers": headers,
        "body_meta": body_meta,
        "kid": str(kid),
        "endpoint_hash": pss.endpoint_hash(endpoint),
        "event_id": body_meta["event_id"],
    }

    # Closed shape check — pin both top-level and headers keys.
    assert set(envelope.keys()) == set(ENVELOPE_KEYS)
    assert set(envelope["headers"].keys()) == set(ENVELOPE_HEADERS_KEYS)

    # Defense-in-depth: no credential pattern allowed anywhere.
    assert_no_secrets(envelope)

    return envelope


# ---------------------------------------------------------------------------
# Single-record dispatch
# ---------------------------------------------------------------------------


def dispatch_one(
    *,
    record: dict[str, Any],
    subscription: dict[str, Any],
    transport: Transport,
    attempted_at: str | None = None,
) -> dict[str, Any]:
    """Build the envelope, hand it to ``transport``, classify the
    response, and return a closed-schema dispatch record.

    ``transport`` is a mandatory keyword argument. There is no
    module-level default. Production wiring (N2b-3b) supplies the
    real HTTP client; tests supply a synthetic.
    """
    if transport is None or not callable(transport):
        raise TypeError("transport must be a callable")

    ts = attempted_at if attempted_at is not None else _utcnow()
    event_id = str(record.get("event_id") or "")
    event_kind = str(record.get("event_kind") or "")
    event_severity = str(record.get("event_severity") or "")

    if not event_id:
        return _record(
            event_id=event_id,
            event_kind=event_kind,
            event_severity=event_severity,
            endpoint_hash="",
            kid="",
            outcome="skipped_invalid_record",
            provider_status_class="unknown",
            provider_status_code=None,
            envelope_url="",
            attempted_at=ts,
        )

    if not isinstance(subscription, dict) or not subscription.get("endpoint"):
        return _record(
            event_id=event_id,
            event_kind=event_kind,
            event_severity=event_severity,
            endpoint_hash="",
            kid="",
            outcome="skipped_no_subscription",
            provider_status_class="unknown",
            provider_status_code=None,
            envelope_url="",
            attempted_at=ts,
        )

    envelope = build_envelope(record=record, subscription=subscription)

    # Call the transport. Any exception from the transport classifies
    # to ``transport_error`` → ``retry``. The transport itself MUST
    # NOT raise for HTTP-level failures (it should return a status
    # code).
    try:
        result = transport(envelope)
        if not isinstance(result, dict):
            status_code: int | None = None
        else:
            raw = result.get("status_code")
            status_code = raw if isinstance(raw, int) else None
    except Exception:
        status_code = None

    status_class = _classify_status(status_code)
    outcome = _classify_outcome(status_class)

    return _record(
        event_id=event_id,
        event_kind=event_kind,
        event_severity=event_severity,
        endpoint_hash=envelope["endpoint_hash"],
        kid=envelope["kid"],
        outcome=outcome,
        provider_status_class=status_class,
        provider_status_code=status_code,
        envelope_url=envelope["url"],
        attempted_at=ts,
    )


def _record(
    *,
    event_id: str,
    event_kind: str,
    event_severity: str,
    endpoint_hash: str,
    kid: str,
    outcome: str,
    provider_status_class: str,
    provider_status_code: int | None,
    envelope_url: str,
    attempted_at: str,
) -> dict[str, Any]:
    rec: dict[str, Any] = {
        "event_id": event_id,
        "event_kind": event_kind,
        "event_severity": event_severity,
        "endpoint_hash": endpoint_hash,
        "kid": kid,
        "outcome": outcome,
        "provider_status_class": provider_status_class,
        "provider_status_code": provider_status_code,
        "envelope_url": envelope_url,
        "attempted_at": attempted_at,
    }
    assert set(rec.keys()) == set(DISPATCH_RECORD_KEYS)
    assert_no_secrets(rec)
    return rec


__all__ = [
    "AUTHORIZATION_MODE_PLACEHOLDER",
    "CONTENT_ENCODING",
    "CONTENT_TYPE",
    "CRYPTO_KEY_MODE_PLACEHOLDER",
    "DEFAULT_TTL_SECONDS",
    "DISPATCH_OUTCOMES",
    "DISPATCH_RECORD_KEYS",
    "ENVELOPE_HEADERS_KEYS",
    "ENVELOPE_KEYS",
    "MODULE_VERSION",
    "PROVIDER_STATUS_CLASSES",
    "SCHEMA_VERSION",
    "STEP5_ENABLED_SUBSTAGE",
    "Transport",
    "build_envelope",
    "dispatch_one",
    "step5_implementation_allowed",
]
