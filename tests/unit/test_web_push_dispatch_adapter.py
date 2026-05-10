"""Unit tests for N2b-3a — Web Push dispatch adapter (mocked transport)."""

from __future__ import annotations

import importlib
import re
from pathlib import Path
from typing import Any

import pytest

from reporting import push_subscription_store as pss
from reporting import web_push_dispatch_adapter as wpda


REPO_ROOT = Path(__file__).resolve().parents[2]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _ready_record(*, event_id: str = "abc12345abc12345") -> dict[str, Any]:
    return {
        "event_id": event_id,
        "event_kind": "intake_candidate_eligible",
        "event_severity": "push_info",
        "title": "Synthetic eligible candidate",
        "summary": "decision_state=eligible; risk=LOW; target=docs/x.md",
        "open_at": f"/agent-control/inbox?event={event_id}",
    }


def _subscription() -> dict[str, Any]:
    return {
        "endpoint": "https://fcm.googleapis.com/fcm/send/abc",
        "keys": {"p256dh": "BCfV1eK4...", "auth": "auth_secret"},
        "kid": "k1",
    }


# ---------------------------------------------------------------------------
# Closed vocabularies
# ---------------------------------------------------------------------------


def test_dispatch_outcomes_pinned_exactly() -> None:
    assert wpda.DISPATCH_OUTCOMES == (
        "sent",
        "drop_subscription",
        "failed_provider",
        "retry",
        "skipped_no_subscription",
        "skipped_invalid_record",
    )


def test_provider_status_classes_pinned_exactly() -> None:
    assert wpda.PROVIDER_STATUS_CLASSES == (
        "2xx",
        "410",
        "4xx_other",
        "5xx",
        "transport_error",
        "unknown",
    )


def test_envelope_keys_pinned_exactly_and_ordered() -> None:
    assert wpda.ENVELOPE_KEYS == (
        "url",
        "method",
        "headers",
        "body_meta",
        "kid",
        "endpoint_hash",
        "event_id",
    )


def test_envelope_headers_keys_pinned_exactly() -> None:
    assert wpda.ENVELOPE_HEADERS_KEYS == (
        "TTL",
        "Content-Encoding",
        "Content-Type",
        "Authorization-Mode",
        "Crypto-Key-Mode",
    )


def test_dispatch_record_keys_pinned_exactly_and_ordered() -> None:
    assert wpda.DISPATCH_RECORD_KEYS == (
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


def test_step5_invariants_pinned() -> None:
    assert wpda.step5_implementation_allowed is False
    assert wpda.STEP5_ENABLED_SUBSTAGE == "none"


# ---------------------------------------------------------------------------
# build_envelope shape
# ---------------------------------------------------------------------------


def test_build_envelope_returns_closed_top_level_key_set() -> None:
    env = wpda.build_envelope(record=_ready_record(), subscription=_subscription())
    assert set(env.keys()) == set(wpda.ENVELOPE_KEYS)


def test_build_envelope_headers_are_closed_set() -> None:
    env = wpda.build_envelope(record=_ready_record(), subscription=_subscription())
    assert set(env["headers"].keys()) == set(wpda.ENVELOPE_HEADERS_KEYS)


def test_build_envelope_body_meta_is_six_key_payload() -> None:
    env = wpda.build_envelope(record=_ready_record(), subscription=_subscription())
    assert set(env["body_meta"].keys()) == {
        "event_id",
        "event_kind",
        "event_severity",
        "title",
        "summary",
        "open_at",
    }


def test_build_envelope_uses_subscription_endpoint_as_url() -> None:
    env = wpda.build_envelope(record=_ready_record(), subscription=_subscription())
    assert env["url"] == "https://fcm.googleapis.com/fcm/send/abc"


def test_build_envelope_method_is_post() -> None:
    env = wpda.build_envelope(record=_ready_record(), subscription=_subscription())
    assert env["method"] == "POST"


def test_build_envelope_endpoint_hash_is_sha256_truncated() -> None:
    sub = _subscription()
    env = wpda.build_envelope(record=_ready_record(), subscription=sub)
    assert env["endpoint_hash"] == pss.endpoint_hash(sub["endpoint"])
    assert len(env["endpoint_hash"]) == 16


def test_build_envelope_carries_authorization_and_crypto_placeholders() -> None:
    """N2b-3a must NOT carry a real VAPID JWT or real Crypto-Key. The
    headers carry closed placeholder mode strings only."""
    env = wpda.build_envelope(record=_ready_record(), subscription=_subscription())
    assert env["headers"]["Authorization-Mode"] == wpda.AUTHORIZATION_MODE_PLACEHOLDER
    assert env["headers"]["Crypto-Key-Mode"] == wpda.CRYPTO_KEY_MODE_PLACEHOLDER


def test_build_envelope_rejects_non_dict_record() -> None:
    with pytest.raises(TypeError):
        wpda.build_envelope(record="nope", subscription=_subscription())  # type: ignore[arg-type]


def test_build_envelope_rejects_non_dict_subscription() -> None:
    with pytest.raises(TypeError):
        wpda.build_envelope(record=_ready_record(), subscription=None)  # type: ignore[arg-type]


def test_build_envelope_rejects_missing_endpoint() -> None:
    with pytest.raises(ValueError):
        wpda.build_envelope(record=_ready_record(), subscription={"endpoint": ""})


# ---------------------------------------------------------------------------
# dispatch_one — transport requirement
# ---------------------------------------------------------------------------


def test_dispatch_one_requires_transport_callable() -> None:
    with pytest.raises(TypeError):
        wpda.dispatch_one(  # type: ignore[call-arg]
            record=_ready_record(),
            subscription=_subscription(),
        )


def test_dispatch_one_rejects_non_callable_transport() -> None:
    with pytest.raises(TypeError):
        wpda.dispatch_one(
            record=_ready_record(),
            subscription=_subscription(),
            transport="not callable",  # type: ignore[arg-type]
        )


# ---------------------------------------------------------------------------
# dispatch_one — outcome classification
# ---------------------------------------------------------------------------


def _transport_returning(status_code: int | None):
    def _t(envelope: dict[str, Any]) -> dict[str, Any]:
        return {"status_code": status_code, "error_class": None}

    return _t


def _transport_raising(exc: Exception):
    def _t(envelope: dict[str, Any]) -> dict[str, Any]:
        raise exc

    return _t


def test_dispatch_one_2xx_yields_sent() -> None:
    rec = wpda.dispatch_one(
        record=_ready_record(),
        subscription=_subscription(),
        transport=_transport_returning(201),
        attempted_at="2026-05-10T00:00:00Z",
    )
    assert rec["outcome"] == "sent"
    assert rec["provider_status_class"] == "2xx"
    assert rec["provider_status_code"] == 201
    assert rec["envelope_url"] == "https://fcm.googleapis.com/fcm/send/abc"


def test_dispatch_one_410_yields_drop_subscription() -> None:
    rec = wpda.dispatch_one(
        record=_ready_record(),
        subscription=_subscription(),
        transport=_transport_returning(410),
    )
    assert rec["outcome"] == "drop_subscription"
    assert rec["provider_status_class"] == "410"


def test_dispatch_one_4xx_other_yields_failed_provider() -> None:
    rec = wpda.dispatch_one(
        record=_ready_record(),
        subscription=_subscription(),
        transport=_transport_returning(404),
    )
    assert rec["outcome"] == "failed_provider"
    assert rec["provider_status_class"] == "4xx_other"


def test_dispatch_one_5xx_yields_retry() -> None:
    rec = wpda.dispatch_one(
        record=_ready_record(),
        subscription=_subscription(),
        transport=_transport_returning(503),
    )
    assert rec["outcome"] == "retry"
    assert rec["provider_status_class"] == "5xx"


def test_dispatch_one_transport_error_yields_retry() -> None:
    rec = wpda.dispatch_one(
        record=_ready_record(),
        subscription=_subscription(),
        transport=_transport_raising(RuntimeError("boom")),
    )
    assert rec["outcome"] == "retry"
    assert rec["provider_status_class"] == "transport_error"
    assert rec["provider_status_code"] is None


def test_dispatch_one_status_code_none_yields_failed_provider_or_retry() -> None:
    """A transport that returns a non-int status_code lands as
    transport_error (which classifies to retry)."""
    rec = wpda.dispatch_one(
        record=_ready_record(),
        subscription=_subscription(),
        transport=_transport_returning(None),
    )
    assert rec["outcome"] == "retry"
    assert rec["provider_status_class"] == "transport_error"


def test_dispatch_one_unknown_status_class_falls_back_to_failed_provider() -> None:
    """e.g. a 100 informational or 3xx redirect is unexpected for
    Web Push — classify as `unknown` → `failed_provider`."""
    rec = wpda.dispatch_one(
        record=_ready_record(),
        subscription=_subscription(),
        transport=_transport_returning(301),
    )
    assert rec["provider_status_class"] == "unknown"
    assert rec["outcome"] == "failed_provider"


def test_dispatch_one_skips_invalid_record() -> None:
    bad = _ready_record()
    bad["event_id"] = ""
    rec = wpda.dispatch_one(
        record=bad,
        subscription=_subscription(),
        transport=_transport_returning(200),
    )
    assert rec["outcome"] == "skipped_invalid_record"


def test_dispatch_one_skips_missing_subscription() -> None:
    rec = wpda.dispatch_one(
        record=_ready_record(),
        subscription={},
        transport=_transport_returning(200),
    )
    assert rec["outcome"] == "skipped_no_subscription"


def test_dispatch_record_has_no_full_endpoint_url_in_redacted_fields() -> None:
    """The endpoint URL appears only in `envelope_url`. Other
    redacted-friendly fields (`endpoint_hash`) carry a sha256 prefix.
    Pinned to catch a future refactor that copies the endpoint into
    the wrong place."""
    rec = wpda.dispatch_one(
        record=_ready_record(),
        subscription=_subscription(),
        transport=_transport_returning(200),
    )
    assert rec["endpoint_hash"]
    assert "fcm.googleapis.com/fcm/send/abc" not in rec["endpoint_hash"]


def test_dispatch_one_envelope_url_passed_through() -> None:
    rec = wpda.dispatch_one(
        record=_ready_record(),
        subscription=_subscription(),
        transport=_transport_returning(200),
    )
    assert rec["envelope_url"] == "https://fcm.googleapis.com/fcm/send/abc"


# ---------------------------------------------------------------------------
# Source-text scans
# ---------------------------------------------------------------------------


def _module_source() -> str:
    return Path(wpda.__file__).read_text(encoding="utf-8")


def _imported_module_names() -> set[str]:
    import ast

    src = _module_source()
    tree = ast.parse(src)
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                names.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module is not None:
                names.add(node.module)
    return names


def test_no_subprocess_in_module() -> None:
    src = _module_source()
    assert "import subprocess" not in src
    assert "from subprocess" not in src


def test_no_network_in_module() -> None:
    src = _module_source()
    for forbidden in (
        "import socket",
        "import urllib",
        "import http.client",
        "import requests",
        "import httpx",
        "import aiohttp",
    ):
        assert forbidden not in src, forbidden


def test_no_web_push_library_imports() -> None:
    src = _module_source()
    for forbidden in (
        "import pywebpush",
        "from pywebpush",
        "import webpush",
        "from webpush",
        "import web_push",
        "from web_push",
    ):
        assert forbidden not in src, forbidden


def test_no_vapid_private_key_reference() -> None:
    """The literal env-var name must not appear in N2b-3a source.
    Reading the private key is N2b-3b territory."""
    src = _module_source()
    assert "WEB_PUSH_VAPID_PRIVATE_KEY" not in src


def test_no_dashboard_or_frontend_imports() -> None:
    forbidden_prefixes = (
        "dashboard",
        "frontend",
        "automation",
        "broker",
        "agent.risk",
        "agent.execution",
        "research",
        "reporting.intelligent_routing",
        "live",
        "paper",
        "shadow",
        "trading",
    )
    for module in _imported_module_names():
        for prefix in forbidden_prefixes:
            assert not (
                module == prefix or module.startswith(prefix + ".")
            ), f"forbidden import: {module}"


def test_no_real_provider_code_paths_present() -> None:
    """Defense in depth — no hint of a real HTTP call inside the
    module body."""
    src = _module_source()
    forbidden_code_patterns = (
        "subscriptions.json",
        "VAPID_PRIVATE",
        "WEB_PUSH_VAPID",
        "open_socket",
        ".send_web_push",
        "WebPushClient",
        "create_connection",
    )
    for forbidden in forbidden_code_patterns:
        assert forbidden not in src, forbidden


def test_module_imports_cleanly() -> None:
    importlib.reload(wpda)
    assert callable(wpda.dispatch_one)
    assert callable(wpda.build_envelope)


def test_importing_module_does_not_flip_step5_invariants() -> None:
    from reporting import development_step5_loop as dsl

    importlib.reload(wpda)
    assert dsl.step5_implementation_allowed is False
    assert dsl.STEP5_ENABLED_SUBSTAGE == "none"


# ---------------------------------------------------------------------------
# Companion doc invariants
# ---------------------------------------------------------------------------


def _doc_text() -> str:
    return (
        REPO_ROOT
        / "docs"
        / "governance"
        / "notification_dispatch_real.md"
    ).read_text(encoding="utf-8")


def test_doc_states_no_real_push_in_n2b3a() -> None:
    text = _doc_text().lower()
    assert "no real push" in text or "no real web push" in text


def test_doc_states_n2b3b_is_deferred_and_operator_gated() -> None:
    text = _doc_text().lower()
    assert "n2b-3b" in text
    assert "deferred" in text or "operator" in text


def test_doc_pins_step5_invariants_text() -> None:
    text = _doc_text()
    assert "step5_implementation_allowed" in text
    assert "STEP5_ENABLED_SUBSTAGE" in text


def test_doc_mentions_level_6_only_with_qualifier() -> None:
    text = _doc_text()
    pattern = re.compile(r"\bLevel\s*6\b")
    for m in pattern.finditer(text):
        start = max(0, m.start() - 200)
        end = m.start() + 600
        window = text[start:end].lower()
        assert "permanently disabled" in window
