"""Unit tests for N2b-3b — Real Web Push transport (env-gated, lazy import).

These tests pin:

* the closed env-var names and the closed result envelope shape;
* :func:`is_configured` is env-only and never echoes values;
* :func:`make_transport` refuses (returns ``invalid_envelope``) even
  on a structurally valid envelope because the adapter envelope does
  not carry subscription keys — the bare transport is for env/library
  gate tests only;
* :func:`make_transport_for_subscription` returns a closure that
  classifies every failure mode into the closed
  ``error_class`` vocabulary;
* the closure refuses without env, without subscription keys, with a
  mismatched envelope url vs subscription endpoint, and when
  ``pywebpush`` is unimportable;
* the closure invokes ``pywebpush.webpush`` exactly once on the happy
  path, with no endpoint URL or VAPID private key in the surfaced
  result;
* the module never imports ``pywebpush`` at module load;
* source-text + AST scans for forbidden imports and forbidden
  literals;
* Step 5 invariants are not flipped by import.
"""

from __future__ import annotations

import ast
import importlib
import os
import sys
from pathlib import Path
from typing import Any

import pytest

from reporting import web_push_real_transport as wprt


REPO_ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = Path(wprt.__file__).resolve()


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _valid_envelope() -> dict[str, Any]:
    return {
        "url": "https://fcm.googleapis.com/fcm/send/abc",
        "method": "POST",
        "headers": {
            "TTL": "60",
            "Content-Encoding": "aes128gcm",
            "Content-Type": "application/octet-stream",
            "Authorization-Mode": "vapid_jwt_pending_n2b3b",
            "Crypto-Key-Mode": "ecdh_p256_pending_n2b3b",
        },
        "body_meta": {
            "event_id": "abc12345abc12345",
            "event_kind": "intake_candidate_eligible",
            "event_severity": "push_info",
            "title": "title",
            "summary": "summary",
            "open_at": "/agent-control/inbox?event=abc12345abc12345",
        },
        "kid": "k1",
        "endpoint_hash": "deadbeefdeadbeef",
        "event_id": "abc12345abc12345",
    }


def _valid_subscription() -> dict[str, Any]:
    return {
        "endpoint": "https://fcm.googleapis.com/fcm/send/abc",
        "keys": {"p256dh": "BCfV1eK4_publickeybase64url", "auth": "auth_secret"},
        "kid": "k1",
    }


@pytest.fixture(autouse=True)
def _clear_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(wprt.ENV_VAPID_PRIVATE_KEY, raising=False)
    monkeypatch.delenv(wprt.ENV_VAPID_SUBJECT, raising=False)


# ---------------------------------------------------------------------------
# Closed vocabularies + Step 5
# ---------------------------------------------------------------------------


def test_env_names_pinned_exactly() -> None:
    assert wprt.ENV_VAPID_PRIVATE_KEY == "WEB_PUSH_VAPID_PRIVATE_KEY"
    assert wprt.ENV_VAPID_SUBJECT == "WEB_PUSH_VAPID_SUBJECT"


def test_transport_result_keys_pinned() -> None:
    assert wprt.TRANSPORT_RESULT_KEYS == ("status_code", "error_class")


def test_error_classes_pinned_exactly() -> None:
    assert wprt.ERROR_CLASSES == (
        "ok",
        "config_missing",
        "library_missing",
        "invalid_envelope",
        "transport_exception",
    )


def test_step5_invariants_unchanged() -> None:
    assert wprt.STEP5_ENABLED_SUBSTAGE == "none"
    assert wprt.step5_implementation_allowed is False


# ---------------------------------------------------------------------------
# is_configured()
# ---------------------------------------------------------------------------


def test_is_configured_false_when_both_unset() -> None:
    assert wprt.is_configured() is False


def test_is_configured_false_when_only_private_set(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(wprt.ENV_VAPID_PRIVATE_KEY, "x")
    assert wprt.is_configured() is False


def test_is_configured_false_when_only_subject_set(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(wprt.ENV_VAPID_SUBJECT, "mailto:x@y.z")
    assert wprt.is_configured() is False


def test_is_configured_true_when_both_set(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(wprt.ENV_VAPID_PRIVATE_KEY, "x")
    monkeypatch.setenv(wprt.ENV_VAPID_SUBJECT, "mailto:x@y.z")
    assert wprt.is_configured() is True


def test_is_configured_false_for_empty_string(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(wprt.ENV_VAPID_PRIVATE_KEY, "")
    monkeypatch.setenv(wprt.ENV_VAPID_SUBJECT, "")
    assert wprt.is_configured() is False


def test_is_configured_returns_boolean_only(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(wprt.ENV_VAPID_PRIVATE_KEY, "super-secret-value")
    monkeypatch.setenv(wprt.ENV_VAPID_SUBJECT, "mailto:x@y.z")
    result = wprt.is_configured()
    assert isinstance(result, bool)
    # Should never include the secret in any representation.
    assert "super-secret-value" not in repr(result)


# ---------------------------------------------------------------------------
# make_transport() bare callable — env / library / envelope gates
# ---------------------------------------------------------------------------


def test_make_transport_returns_callable() -> None:
    t = wprt.make_transport()
    assert callable(t)


def test_make_transport_config_missing_when_no_env() -> None:
    t = wprt.make_transport()
    out = t(_valid_envelope())
    assert out == {"status_code": None, "error_class": "config_missing"}


def test_make_transport_invalid_envelope_when_env_set_but_no_keys(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(wprt.ENV_VAPID_PRIVATE_KEY, "x")
    monkeypatch.setenv(wprt.ENV_VAPID_SUBJECT, "mailto:x@y.z")
    # The bare transport always returns invalid_envelope on a valid
    # envelope because the adapter envelope does not carry keys.
    t = wprt.make_transport()
    out = t(_valid_envelope())
    assert out["status_code"] is None
    assert out["error_class"] == "invalid_envelope"


def test_make_transport_rejects_unknown_origin(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(wprt.ENV_VAPID_PRIVATE_KEY, "x")
    monkeypatch.setenv(wprt.ENV_VAPID_SUBJECT, "mailto:x@y.z")
    env = _valid_envelope()
    env["url"] = "https://evil.example.com/send/abc"
    t = wprt.make_transport()
    out = t(env)
    assert out == {"status_code": None, "error_class": "invalid_envelope"}


def test_make_transport_rejects_extra_keys(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(wprt.ENV_VAPID_PRIVATE_KEY, "x")
    monkeypatch.setenv(wprt.ENV_VAPID_SUBJECT, "mailto:x@y.z")
    env = _valid_envelope()
    env["unexpected"] = "value"
    t = wprt.make_transport()
    out = t(env)
    assert out["error_class"] == "invalid_envelope"


def test_make_transport_returns_closed_shape_only(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    t = wprt.make_transport()
    out = t(_valid_envelope())
    assert set(out.keys()) == set(wprt.TRANSPORT_RESULT_KEYS)


# ---------------------------------------------------------------------------
# make_transport_for_subscription() — full closure behaviour
# ---------------------------------------------------------------------------


def test_subscription_transport_config_missing_when_no_env() -> None:
    closure = wprt.make_transport_for_subscription(
        subscription=_valid_subscription()
    )
    out = closure(_valid_envelope())
    assert out == {"status_code": None, "error_class": "config_missing"}


def test_subscription_transport_mismatched_endpoint(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(wprt.ENV_VAPID_PRIVATE_KEY, "x")
    monkeypatch.setenv(wprt.ENV_VAPID_SUBJECT, "mailto:x@y.z")
    sub = _valid_subscription()
    sub["endpoint"] = "https://fcm.googleapis.com/fcm/send/different"
    closure = wprt.make_transport_for_subscription(subscription=sub)
    out = closure(_valid_envelope())
    assert out == {"status_code": None, "error_class": "invalid_envelope"}


def test_subscription_transport_missing_keys(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(wprt.ENV_VAPID_PRIVATE_KEY, "x")
    monkeypatch.setenv(wprt.ENV_VAPID_SUBJECT, "mailto:x@y.z")
    sub = _valid_subscription()
    sub["keys"] = {}
    closure = wprt.make_transport_for_subscription(subscription=sub)
    out = closure(_valid_envelope())
    assert out == {"status_code": None, "error_class": "invalid_envelope"}


def test_subscription_transport_library_missing_when_pywebpush_absent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """If `pywebpush` is not importable, the closure must classify
    as `library_missing` and return None status_code."""
    monkeypatch.setenv(wprt.ENV_VAPID_PRIVATE_KEY, "x")
    monkeypatch.setenv(wprt.ENV_VAPID_SUBJECT, "mailto:x@y.z")

    # Simulate the import failing by intercepting sys.modules.
    sentinel = object()
    monkeypatch.setitem(sys.modules, "pywebpush", None)  # type: ignore[arg-type]
    try:
        closure = wprt.make_transport_for_subscription(
            subscription=_valid_subscription()
        )
        out = closure(_valid_envelope())
        assert out["status_code"] is None
        assert out["error_class"] == "library_missing"
    finally:
        # Best-effort restore; pytest monkeypatch reverts at teardown.
        pass


def test_subscription_transport_happy_path_calls_pywebpush(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """On a fully valid input + env + (mocked) pywebpush, the closure
    returns ``ok`` with the mocked status_code."""
    monkeypatch.setenv(wprt.ENV_VAPID_PRIVATE_KEY, "private-key-value")
    monkeypatch.setenv(wprt.ENV_VAPID_SUBJECT, "mailto:x@y.z")

    calls: list[dict[str, Any]] = []

    class FakeResponse:
        status_code = 201

    class FakeWebPushException(Exception):
        pass

    def fake_webpush(**kwargs: Any) -> FakeResponse:
        calls.append(kwargs)
        return FakeResponse()

    fake_module = type(sys)("pywebpush")
    fake_module.webpush = fake_webpush  # type: ignore[attr-defined]
    fake_module.WebPushException = FakeWebPushException  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "pywebpush", fake_module)

    closure = wprt.make_transport_for_subscription(
        subscription=_valid_subscription()
    )
    out = closure(_valid_envelope())

    assert out == {"status_code": 201, "error_class": "ok"}
    assert len(calls) == 1
    kw = calls[0]
    assert kw["subscription_info"]["endpoint"] == (
        "https://fcm.googleapis.com/fcm/send/abc"
    )
    assert kw["vapid_claims"] == {"sub": "mailto:x@y.z"}
    assert kw["ttl"] == 60
    # Defense-in-depth: result must not embed the private key or
    # the endpoint URL.
    repr_out = repr(out)
    assert "private-key-value" not in repr_out
    assert "/fcm/send/abc" not in repr_out


def test_subscription_transport_410_classifies_via_pywebpush_exception(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(wprt.ENV_VAPID_PRIVATE_KEY, "x")
    monkeypatch.setenv(wprt.ENV_VAPID_SUBJECT, "mailto:x@y.z")

    class FakeInner:
        status_code = 410

    class FakeWebPushException(Exception):
        def __init__(self) -> None:
            super().__init__("gone")
            self.response = FakeInner()

    def fake_webpush(**kwargs: Any) -> Any:
        raise FakeWebPushException()

    fake_module = type(sys)("pywebpush")
    fake_module.webpush = fake_webpush  # type: ignore[attr-defined]
    fake_module.WebPushException = FakeWebPushException  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "pywebpush", fake_module)

    closure = wprt.make_transport_for_subscription(
        subscription=_valid_subscription()
    )
    out = closure(_valid_envelope())
    assert out == {"status_code": 410, "error_class": "ok"}


def test_subscription_transport_unknown_exception_classified_as_transport_exception(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(wprt.ENV_VAPID_PRIVATE_KEY, "x")
    monkeypatch.setenv(wprt.ENV_VAPID_SUBJECT, "mailto:x@y.z")

    def fake_webpush(**kwargs: Any) -> Any:
        raise RuntimeError("boom")

    class FakeWebPushException(Exception):
        pass

    fake_module = type(sys)("pywebpush")
    fake_module.webpush = fake_webpush  # type: ignore[attr-defined]
    fake_module.WebPushException = FakeWebPushException  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "pywebpush", fake_module)

    closure = wprt.make_transport_for_subscription(
        subscription=_valid_subscription()
    )
    out = closure(_valid_envelope())
    assert out == {"status_code": None, "error_class": "transport_exception"}


def test_subscription_transport_never_raises(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(wprt.ENV_VAPID_PRIVATE_KEY, "x")
    monkeypatch.setenv(wprt.ENV_VAPID_SUBJECT, "mailto:x@y.z")
    closure = wprt.make_transport_for_subscription(
        subscription="not-a-dict",  # type: ignore[arg-type]
    )
    out = closure(_valid_envelope())
    assert out["status_code"] is None
    assert out["error_class"] == "invalid_envelope"


# ---------------------------------------------------------------------------
# Source-text + AST scans
# ---------------------------------------------------------------------------


def _module_source() -> str:
    return MODULE_PATH.read_text(encoding="utf-8")


def _imported_module_names() -> set[str]:
    tree = ast.parse(_module_source())
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


def test_no_gh_or_git_in_module() -> None:
    src = _module_source()
    forbidden = (" gh ", " git ", "subprocess.call", "subprocess.run")
    for needle in forbidden:
        assert needle not in src, needle


def test_pywebpush_imported_only_lazily() -> None:
    """The module must not contain a top-level `import pywebpush` or
    `from pywebpush import ...`. The lazy import lives inside
    function bodies."""
    tree = ast.parse(_module_source())
    for node in tree.body:
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert alias.name != "pywebpush", (
                    "pywebpush must be lazy-imported, not top-level"
                )
        if isinstance(node, ast.ImportFrom):
            assert node.module != "pywebpush", (
                "pywebpush must be lazy-imported, not top-level"
            )


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
            assert module != prefix, module
            assert not module.startswith(prefix + "."), module


def test_no_decision_verb_call_in_module() -> None:
    """The transport must not invoke any approve/reject/merge/deploy
    callable. The transport is delivery-only. We look for the
    function-call pattern (``verb(``) so the docstring's prose
    describing what the transport *does not* do is allowed to mention
    the verbs."""
    src = _module_source().lower()
    for verb in ("approve(", "reject(", "merge(", "deploy("):
        assert verb not in src, verb


def test_env_var_name_is_the_only_one_referenced() -> None:
    """This module is the ONLY place the literal env-var name appears.
    Other modules pin its absence. We also check that no other secret
    env name leaks in."""
    src = _module_source()
    assert "WEB_PUSH_VAPID_PRIVATE_KEY" in src
    forbidden = (
        "ADE_APPROVAL_TOKEN_HMAC_SECRET",
        "ANTHROPIC_API_KEY",
        "BITVAVO_SECRET",
        "POLYMARKET_PRIVATE_KEY",
    )
    for needle in forbidden:
        assert needle not in src, needle


# ---------------------------------------------------------------------------
# Step 5 invariants — import-time
# ---------------------------------------------------------------------------


def test_import_does_not_flip_step5_invariants() -> None:
    """A fresh import must not flip any Step 5 invariant."""
    importlib.reload(wprt)
    assert wprt.step5_implementation_allowed is False
    assert wprt.STEP5_ENABLED_SUBSTAGE == "none"


# ---------------------------------------------------------------------------
# Doc invariants
# ---------------------------------------------------------------------------


def _doc_text() -> str:
    return (
        REPO_ROOT
        / "docs"
        / "governance"
        / "notification_dispatch_real.md"
    ).read_text(encoding="utf-8")


def test_doc_states_level_6_permanently_disabled() -> None:
    text = _doc_text().lower()
    assert "level 6" in text
    assert "permanently disabled" in text


def test_doc_states_no_approval_from_click_alone() -> None:
    import re

    text = re.sub(r"\s+", " ", _doc_text().lower())
    assert (
        "no approval can happen from notification click alone" in text
        or "no approval from notification click alone" in text
        or "no approval can happen from a notification click alone" in text
    )


def test_doc_lists_n3_n4_n5_as_future() -> None:
    text = _doc_text().lower()
    for marker in ("n3", "n4", "n5"):
        assert marker in text, marker
    assert (
        "unimplemented" in text
        or "out of scope" in text
        or "future" in text
    )
