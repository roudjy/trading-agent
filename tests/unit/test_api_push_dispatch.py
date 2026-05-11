"""Unit tests for N2b-3b — dashboard.api_push_dispatch (UNWIRED).

Pins:

* the blueprint registers exactly one route, POST /api/push/dispatch;
* the loopback gate refuses non-loopback `request.remote_addr` with 403;
* the env gate refuses (503 `configuration_missing`) when
  :func:`reporting.web_push_real_transport.is_configured` is False;
* the body-size gate refuses payloads > 1 KiB with 413;
* the happy path with a mocked transport factory dispatches each
  (record × subscription) pair and aggregates counts;
* a 410 outcome triggers ``pss.unregister_subscription`` and
  increments ``unregistered_on_410``;
* the response body contains no endpoint URLs, no key material, no
  decision-verb literals;
* the summary file write is atomic and sentinel-restricted;
* `dashboard/dashboard.py` does NOT yet import or register the
  dispatch blueprint (until the operator wires it; skip-or-enforce);
* source-text + AST scans for forbidden imports / literals / verbs;
* Step 5 invariants unchanged by import.

The subscription record used in the Flask-client e2e test is built
with the bland values ``"k1"`` / ``"k2"`` rather than realistic
base64url-shaped strings so the test diff carries no high-entropy
literal pairs that could trip generic-api-key heuristics.
"""

from __future__ import annotations

import ast
import importlib
import json
from pathlib import Path
from typing import Any

import pytest
from flask import Flask

from dashboard import api_push_dispatch as apd
from reporting import push_subscription_store as pss
from reporting import web_push_real_transport as wprt


REPO_ROOT = Path(__file__).resolve().parents[2]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _isolate_artifacts(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Redirect the artefact write target into ``tmp_path``."""
    target_dir = tmp_path / "logs" / "notification_dispatch_real"
    target_latest = target_dir / "latest.json"
    monkeypatch.setattr(apd, "ARTIFACT_DIR", target_dir)
    monkeypatch.setattr(apd, "ARTIFACT_LATEST", target_latest)
    return target_dir


@pytest.fixture(autouse=True)
def _isolate_subscription_store(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Path:
    sub_path = tmp_path / "config" / "web_push_subscriptions.json"
    sub_path.parent.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(pss, "SUBSCRIPTIONS_PATH", sub_path)
    monkeypatch.setattr(
        pss,
        "VAPID_PUBLIC_PATH",
        tmp_path / "config" / "web_push_vapid_public.txt",
    )
    return sub_path


@pytest.fixture(autouse=True)
def _clear_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(wprt.ENV_VAPID_PRIVATE_KEY, raising=False)
    monkeypatch.delenv(wprt.ENV_VAPID_SUBJECT, raising=False)


def _make_app() -> Flask:
    app = Flask(__name__)
    apd.register_push_dispatch_routes(app)
    return app


def _valid_outbox_snapshot() -> dict[str, Any]:
    return {
        "records": [
            {
                "event_id": "abc12345abc12345",
                "outbound_delivery_intent": "sent",
                "payload": {
                    "event_id": "abc12345abc12345",
                    "event_kind": "intake_candidate_eligible",
                    "event_severity": "push_info",
                    "title": "title",
                    "summary": "summary",
                    "open_at": "/agent-control/inbox?event=abc12345abc12345",
                },
            }
        ]
    }


def _valid_subscription() -> dict[str, Any]:
    return {
        "endpoint": "https://fcm.googleapis.com/fcm/send/abc",
        "keys": {"p256dh": "k1", "auth": "k2"},
        "kid": "k1",
    }


def _register_a_subscription() -> None:
    """Persist one valid subscription via the store API. Uses bland
    short values so the test diff carries no high-entropy literals."""
    rec, _warnings = pss.register_subscription(
        {
            "endpoint": "https://fcm.googleapis.com/fcm/send/abc",
            "keys": {"p256dh": "k1", "auth": "k2"},
            "kid": "k1",
            "label": "test",
        }
    )
    assert rec is not None


# ---------------------------------------------------------------------------
# Route registration
# ---------------------------------------------------------------------------


def test_register_routes_registers_only_dispatch_post() -> None:
    app = _make_app()
    rules = [
        (rule.rule, frozenset(rule.methods or set()))
        for rule in app.url_map.iter_rules()
        if rule.rule.startswith("/api/push/")
    ]
    assert rules == [(
        "/api/push/dispatch",
        frozenset({"POST", "OPTIONS"}),
    )], rules


def test_dispatch_route_not_yet_wired_into_dashboard_dashboard() -> None:
    """Until the operator commits the two-line wiring diff for
    api_push_dispatch, `dashboard/dashboard.py` must not import or
    register this blueprint. Dual mode: if wiring is present the
    other wiring test enforces the exact shape; here we only assert
    consistency (both flags absent or both flags present)."""
    text = (REPO_ROOT / "dashboard" / "dashboard.py").read_text(
        encoding="utf-8"
    )
    wiring_present = (
        "from dashboard.api_push_dispatch import register_push_dispatch_routes"
        in text
    )
    register_present = "register_push_dispatch_routes(app)" in text
    assert wiring_present == register_present, (
        "dashboard.py must contain BOTH import and register call for "
        "api_push_dispatch wiring, or NEITHER. Found import="
        f"{wiring_present}, register={register_present}."
    )


# ---------------------------------------------------------------------------
# Loopback gate
# ---------------------------------------------------------------------------


def test_loopback_gate_refuses_non_loopback() -> None:
    app = _make_app()
    client = app.test_client()
    res = client.post(
        "/api/push/dispatch",
        data="{}",
        content_type="application/json",
        environ_overrides={"REMOTE_ADDR": "203.0.113.42"},
    )
    assert res.status_code == 403
    body = res.get_json()
    assert body == {"status": "error", "error": "remote_not_loopback"}


def test_loopback_gate_accepts_ipv4_loopback() -> None:
    """A loopback request still needs env to proceed; without env we
    expect 503, not 403."""
    app = _make_app()
    client = app.test_client()
    res = client.post(
        "/api/push/dispatch",
        data="{}",
        content_type="application/json",
        environ_overrides={"REMOTE_ADDR": "127.0.0.1"},
    )
    assert res.status_code == 503


def test_loopback_gate_accepts_ipv6_loopback() -> None:
    app = _make_app()
    client = app.test_client()
    res = client.post(
        "/api/push/dispatch",
        data="{}",
        content_type="application/json",
        environ_overrides={"REMOTE_ADDR": "::1"},
    )
    assert res.status_code == 503


# ---------------------------------------------------------------------------
# Env gate
# ---------------------------------------------------------------------------


def test_env_gate_refuses_when_unconfigured() -> None:
    app = _make_app()
    client = app.test_client()
    res = client.post(
        "/api/push/dispatch",
        data="{}",
        content_type="application/json",
        environ_overrides={"REMOTE_ADDR": "127.0.0.1"},
    )
    assert res.status_code == 503
    body = res.get_json()
    assert body == {"status": "error", "error": "configuration_missing"}


# ---------------------------------------------------------------------------
# Body-size gate
# ---------------------------------------------------------------------------


def test_body_size_gate_refuses_oversize_body() -> None:
    app = _make_app()
    client = app.test_client()
    res = client.post(
        "/api/push/dispatch",
        data="x" * (apd._MAX_REQUEST_BYTES + 1),
        content_type="application/json",
        environ_overrides={"REMOTE_ADDR": "127.0.0.1"},
    )
    assert res.status_code == 413
    body = res.get_json()
    assert body == {"status": "error", "error": "payload_too_large"}


# ---------------------------------------------------------------------------
# Happy path with injected mock transport
# ---------------------------------------------------------------------------


def test_dispatch_ready_events_happy_path_with_mock_transport() -> None:
    """End-to-end (record × subscription) dispatch via an injected
    transport factory that returns 2xx."""

    def fake_factory(*, subscription: dict[str, Any]) -> Any:
        def _t(envelope: dict[str, Any]) -> dict[str, Any]:
            return {"status_code": 201, "error_class": "ok"}

        return _t

    snap = _valid_outbox_snapshot()
    summary = apd.dispatch_ready_events(
        transport_factory=fake_factory,
        outbox_snapshot=snap,
        subscriptions=[_valid_subscription()],
        unregister_callable=lambda _e: False,
    )
    counts = summary["counts"]
    assert counts["ready_records"] == 1
    assert counts["subscriptions"] == 1
    assert counts["attempted"] == 1
    assert counts["sent"] == 1
    assert summary["note"] == "dispatch_summary"
    # Per-attempt rows are redacted.
    assert len(summary["attempts"]) == 1
    row = summary["attempts"][0]
    for k in ("event_id", "endpoint_hash", "outcome", "provider_status_class"):
        assert k in row
    # Endpoint URL and keys never appear.
    raw = json.dumps(summary)
    assert "fcm.googleapis.com" not in raw


def test_dispatch_ready_events_410_triggers_unregister() -> None:
    """A 410 from the transport must classify as `drop_subscription`
    AND call the unregister callable AND increment the counter."""
    unreg_calls: list[str] = []

    def fake_factory(*, subscription: dict[str, Any]) -> Any:
        def _t(envelope: dict[str, Any]) -> dict[str, Any]:
            return {"status_code": 410, "error_class": "ok"}

        return _t

    def fake_unreg(endpoint: str) -> bool:
        unreg_calls.append(endpoint)
        return True

    snap = _valid_outbox_snapshot()
    summary = apd.dispatch_ready_events(
        transport_factory=fake_factory,
        outbox_snapshot=snap,
        subscriptions=[_valid_subscription()],
        unregister_callable=fake_unreg,
    )
    counts = summary["counts"]
    assert counts["drop_subscription"] == 1
    assert counts["unregistered_on_410"] == 1
    assert unreg_calls == ["https://fcm.googleapis.com/fcm/send/abc"]


def test_dispatch_ready_events_no_records_returns_no_ready_records() -> None:
    summary = apd.dispatch_ready_events(
        transport_factory=lambda *, subscription: (lambda e: {}),
        outbox_snapshot={"records": []},
        subscriptions=[_valid_subscription()],
        unregister_callable=lambda _e: False,
    )
    assert summary["note"] == "no_ready_records"
    assert summary["counts"]["attempted"] == 0


def test_dispatch_ready_events_no_subscriptions_returns_no_subscriptions() -> None:
    summary = apd.dispatch_ready_events(
        transport_factory=lambda *, subscription: (lambda e: {}),
        outbox_snapshot=_valid_outbox_snapshot(),
        subscriptions=[],
        unregister_callable=lambda _e: False,
    )
    assert summary["note"] == "no_subscriptions"
    assert summary["counts"]["attempted"] == 0


def test_dispatch_ready_events_skips_non_sent_outbox_records() -> None:
    """A `duplicate` or `failed_*` outbox record must not be promoted
    to real delivery."""
    snap = {
        "records": [
            {
                "event_id": "x",
                "outbound_delivery_intent": "duplicate",
                "payload": {"event_id": "x"},
            }
        ]
    }
    summary = apd.dispatch_ready_events(
        transport_factory=lambda *, subscription: (lambda e: {}),
        outbox_snapshot=snap,
        subscriptions=[_valid_subscription()],
        unregister_callable=lambda _e: False,
    )
    assert summary["counts"]["ready_records"] == 0
    assert summary["counts"]["attempted"] == 0


# ---------------------------------------------------------------------------
# End-to-end via Flask client (env set, mocked transport)
# ---------------------------------------------------------------------------


def test_post_dispatch_happy_path_writes_summary(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv(wprt.ENV_VAPID_PRIVATE_KEY, "v")
    monkeypatch.setenv(wprt.ENV_VAPID_SUBJECT, "mailto:x@y.z")

    # Replace _read_outbox_snapshot with our in-test snapshot.
    monkeypatch.setattr(
        apd, "_read_outbox_snapshot", lambda: _valid_outbox_snapshot()
    )
    _register_a_subscription()

    # Inject a successful mock factory.
    def fake_factory(*, subscription: dict[str, Any]) -> Any:
        def _t(envelope: dict[str, Any]) -> dict[str, Any]:
            return {"status_code": 201, "error_class": "ok"}

        return _t

    monkeypatch.setattr(
        wprt, "make_transport_for_subscription", fake_factory
    )

    app = _make_app()
    client = app.test_client()
    res = client.post(
        "/api/push/dispatch",
        data="{}",
        content_type="application/json",
        environ_overrides={"REMOTE_ADDR": "127.0.0.1"},
    )
    assert res.status_code == 200, res.data
    body = res.get_json()
    assert body["status"] == "ok"
    assert body["summary"]["counts"]["sent"] == 1
    # Summary written to ARTIFACT_LATEST.
    assert apd.ARTIFACT_LATEST.is_file()


def test_post_dispatch_response_never_contains_endpoint_or_keys(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(wprt.ENV_VAPID_PRIVATE_KEY, "v")
    monkeypatch.setenv(wprt.ENV_VAPID_SUBJECT, "mailto:x@y.z")
    monkeypatch.setattr(
        apd, "_read_outbox_snapshot", lambda: _valid_outbox_snapshot()
    )
    _register_a_subscription()

    def fake_factory(*, subscription: dict[str, Any]) -> Any:
        return lambda envelope: {"status_code": 201, "error_class": "ok"}

    monkeypatch.setattr(
        wprt, "make_transport_for_subscription", fake_factory
    )

    app = _make_app()
    client = app.test_client()
    res = client.post(
        "/api/push/dispatch",
        data="{}",
        content_type="application/json",
        environ_overrides={"REMOTE_ADDR": "127.0.0.1"},
    )
    body_raw = res.data.decode("utf-8")
    assert "fcm.googleapis.com/fcm/send/abc" not in body_raw
    assert "p256dh" not in body_raw


# ---------------------------------------------------------------------------
# Atomic write sentinel
# ---------------------------------------------------------------------------


def test_atomic_write_summary_refuses_non_sentinel_path(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(
        apd,
        "ARTIFACT_LATEST",
        tmp_path / "logs" / "elsewhere" / "latest.json",
    )
    with pytest.raises(ValueError):
        apd._atomic_write_summary({"x": 1})


# ---------------------------------------------------------------------------
# Source-text + AST scans
# ---------------------------------------------------------------------------


def _module_source() -> str:
    return Path(apd.__file__).read_text(encoding="utf-8")


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
    forbidden = ("subprocess.run", "subprocess.call", " gh ", " git ")
    for needle in forbidden:
        assert needle not in src, needle


def test_no_web_push_library_import_in_module() -> None:
    """The dispatch blueprint must never import a real Web Push
    library directly; the lazy import lives only in
    `reporting/web_push_real_transport`. We check via AST so the
    benign `from reporting import web_push_*` imports of our own
    modules are not flagged."""
    names = _imported_module_names()
    for n in names:
        assert n not in {"pywebpush", "webpush", "web_push"}, n
        assert not n.startswith("pywebpush."), n
        assert not n.startswith("webpush."), n
        assert not n.startswith("web_push."), n


def test_no_vapid_private_key_literal_in_module() -> None:
    """The literal env-var name must NOT appear in the blueprint; the
    transport module is the only allowed reference site."""
    src = _module_source()
    assert "WEB_PUSH_VAPID_PRIVATE_KEY" not in src


def test_no_decision_verb_in_module() -> None:
    """The blueprint must contain no decision-verb call patterns. The
    dispatch endpoint delivers notifications only."""
    src = _module_source().lower()
    for verb in ("approve(", "reject(", "merge(", "deploy("):
        assert verb not in src, verb


def test_no_seed_jsonl_writes_in_module() -> None:
    src = _module_source()
    for forbidden in (
        "seed.jsonl",
        "delegation_seed.jsonl",
        "generated_seed.jsonl",
    ):
        assert forbidden not in src, forbidden


def test_no_step5_invariant_writes_in_module() -> None:
    src = _module_source()
    assert src.count("step5_implementation_allowed: Final[bool] = False") == 1
    assert "step5_implementation_allowed = True" not in src
    assert 'STEP5_ENABLED_SUBSTAGE: Final[str] = "none"' in src


def test_no_forbidden_module_imports() -> None:
    forbidden_prefixes = (
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


def test_imports_only_pss_wpda_wprt_aas_and_stdlib() -> None:
    """The blueprint must import only the existing subscription store,
    the existing N2b-3a adapter, the new transport module, and the
    secret-redactor guard. No other reporting module is allowed."""
    names = _imported_module_names()
    allowed_reporting = {
        "reporting",  # bare package name from `from reporting import ...`
        "reporting.push_subscription_store",
        "reporting.web_push_dispatch_adapter",
        "reporting.web_push_real_transport",
        "reporting.agent_audit_summary",
    }
    for n in names:
        if n == "reporting" or n.startswith("reporting."):
            assert n in allowed_reporting, n


# ---------------------------------------------------------------------------
# Step 5 invariants
# ---------------------------------------------------------------------------


def test_import_does_not_flip_step5_invariants() -> None:
    importlib.reload(apd)
    assert apd.step5_implementation_allowed is False
    assert apd.STEP5_ENABLED_SUBSTAGE == "none"


# ---------------------------------------------------------------------------
# Gitignored config invariants (defense in depth)
# ---------------------------------------------------------------------------


def test_vapid_subscriptions_path_gitignored() -> None:
    gitignore = (REPO_ROOT / ".gitignore").read_text(encoding="utf-8")
    assert "config/web_push_subscriptions.json" in gitignore
    assert "config/web_push_vapid_public.txt" in gitignore


def test_vapid_public_text_path_not_tracked_in_git() -> None:
    """If the file currently exists on disk it must not contain a
    private-key marker (defensive — a misnamed write of the private
    PEM into the public-key path)."""
    pub = REPO_ROOT / "config" / "web_push_vapid_public.txt"
    if not pub.is_file():
        return
    text = pub.read_text(encoding="utf-8")
    forbidden = ("BEGIN PRIVATE KEY", "BEGIN RSA PRIVATE KEY")
    for needle in forbidden:
        assert needle not in text, needle
