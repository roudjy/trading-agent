"""Unit tests for N2b-2a — Flask blueprint api_push_subscribe (UNWIRED)."""

from __future__ import annotations

import importlib
import json
import subprocess
from pathlib import Path
from typing import Any

import pytest
from flask import Flask

from reporting import push_subscription_store as pss

from dashboard import api_push_subscribe as aps


REPO_ROOT = Path(__file__).resolve().parents[2]


# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------


def _patch_store_paths(tmp_path: Path, monkeypatch) -> tuple[Path, Path]:
    sub_path = tmp_path / "config" / "web_push_subscriptions.json"
    sub_path.parent.mkdir(parents=True)
    vapid_path = tmp_path / "config" / "web_push_vapid_public.txt"
    monkeypatch.setattr(pss, "SUBSCRIPTIONS_PATH", sub_path)
    monkeypatch.setattr(pss, "VAPID_PUBLIC_PATH", vapid_path)
    return sub_path, vapid_path


def _make_app() -> Flask:
    app = Flask(__name__)
    aps.register_push_subscribe_routes(app)
    return app


def _valid_subscription_payload() -> dict[str, Any]:
    return {
        "endpoint": "https://fcm.googleapis.com/fcm/send/abc123",
        "keys": {
            "p256dh": "BCfV1eK4_p256dh_public_key_base64url_text",
            "auth": "auth_secret_base64url_text",
        },
        "kid": "k1",
        "label": "iPhone PWA",
    }


# ---------------------------------------------------------------------------
# Route registration
# ---------------------------------------------------------------------------


def test_register_routes_registers_all_five_endpoints() -> None:
    app = _make_app()
    rules = {
        (rule.rule, frozenset(rule.methods or set()))
        for rule in app.url_map.iter_rules()
    }
    expected = {
        ("/api/push/subscribe", frozenset({"POST", "OPTIONS"})),
        ("/api/push/unsubscribe", frozenset({"DELETE", "OPTIONS"})),
        ("/api/push/vapid_public", frozenset({"GET", "HEAD", "OPTIONS"})),
        ("/api/push/status", frozenset({"GET", "HEAD", "OPTIONS"})),
        ("/api/push/test", frozenset({"POST", "OPTIONS"})),
    }
    for r in expected:
        assert r in rules, r


def test_blueprint_not_imported_by_dashboard_dashboard() -> None:
    """N2b-2a does NOT wire the blueprint into dashboard/dashboard.py.
    Wiring is N2b-2b territory and lands behind operator approval."""
    text = (
        REPO_ROOT / "dashboard" / "dashboard.py"
    ).read_text(encoding="utf-8")
    assert "api_push_subscribe" not in text
    assert "register_push_subscribe_routes" not in text


# ---------------------------------------------------------------------------
# POST /api/push/subscribe
# ---------------------------------------------------------------------------


def test_subscribe_accepts_valid_payload(
    tmp_path: Path, monkeypatch
) -> None:
    _patch_store_paths(tmp_path, monkeypatch)
    app = _make_app()
    client = app.test_client()
    res = client.post(
        "/api/push/subscribe",
        data=json.dumps(_valid_subscription_payload()),
        content_type="application/json",
    )
    assert res.status_code == 200
    body = res.get_json()
    assert body["status"] == "ok"
    assert "endpoint_hash" in body
    # The full endpoint URL must NOT appear in the response.
    raw = res.data.decode("utf-8")
    assert "fcm.googleapis.com/fcm/send/abc123" not in raw


def test_subscribe_rejects_invalid_payload(
    tmp_path: Path, monkeypatch
) -> None:
    _patch_store_paths(tmp_path, monkeypatch)
    app = _make_app()
    client = app.test_client()
    res = client.post(
        "/api/push/subscribe",
        data=json.dumps({"endpoint": "https://attacker.example.com/x"}),
        content_type="application/json",
    )
    assert res.status_code == 400
    body = res.get_json()
    assert body["status"] == "error"


def test_subscribe_rejects_non_json_body(
    tmp_path: Path, monkeypatch
) -> None:
    _patch_store_paths(tmp_path, monkeypatch)
    app = _make_app()
    client = app.test_client()
    res = client.post(
        "/api/push/subscribe",
        data="not json",
        content_type="application/json",
    )
    assert res.status_code == 400


def test_subscribe_rejects_oversize_body(
    tmp_path: Path, monkeypatch
) -> None:
    _patch_store_paths(tmp_path, monkeypatch)
    app = _make_app()
    client = app.test_client()
    huge = "x" * (16 * 1024)
    res = client.post(
        "/api/push/subscribe",
        data=huge,
        content_type="application/json",
    )
    assert res.status_code == 413


# ---------------------------------------------------------------------------
# DELETE /api/push/unsubscribe
# ---------------------------------------------------------------------------


def test_unsubscribe_removes_existing(tmp_path: Path, monkeypatch) -> None:
    _patch_store_paths(tmp_path, monkeypatch)
    pss.register_subscription(_valid_subscription_payload())
    app = _make_app()
    client = app.test_client()
    res = client.delete(
        "/api/push/unsubscribe",
        data=json.dumps({"endpoint": _valid_subscription_payload()["endpoint"]}),
        content_type="application/json",
    )
    assert res.status_code == 200
    body = res.get_json()
    assert body["status"] == "ok"
    assert body["removed"] is True


def test_unsubscribe_idempotent_on_absent_endpoint(
    tmp_path: Path, monkeypatch
) -> None:
    _patch_store_paths(tmp_path, monkeypatch)
    app = _make_app()
    client = app.test_client()
    res = client.delete(
        "/api/push/unsubscribe",
        data=json.dumps({"endpoint": "https://fcm.googleapis.com/fcm/send/missing"}),
        content_type="application/json",
    )
    assert res.status_code == 200
    body = res.get_json()
    assert body["status"] == "ok"
    assert body["removed"] is False


def test_unsubscribe_rejects_missing_endpoint(
    tmp_path: Path, monkeypatch
) -> None:
    _patch_store_paths(tmp_path, monkeypatch)
    app = _make_app()
    client = app.test_client()
    res = client.delete(
        "/api/push/unsubscribe",
        data=json.dumps({}),
        content_type="application/json",
    )
    assert res.status_code == 400


# ---------------------------------------------------------------------------
# GET /api/push/vapid_public
# ---------------------------------------------------------------------------


def test_vapid_public_404_when_missing(tmp_path: Path, monkeypatch) -> None:
    _patch_store_paths(tmp_path, monkeypatch)
    app = _make_app()
    client = app.test_client()
    res = client.get("/api/push/vapid_public")
    assert res.status_code == 404
    body = res.get_json()
    assert body["status"] == "not_available"
    assert body["error"] == "vapid_public_not_configured"


def test_vapid_public_returns_text_when_present(
    tmp_path: Path, monkeypatch
) -> None:
    _, vapid_path = _patch_store_paths(tmp_path, monkeypatch)
    vapid_path.write_text("BPublicKeyBase64UrlText", encoding="utf-8")
    app = _make_app()
    client = app.test_client()
    res = client.get("/api/push/vapid_public")
    assert res.status_code == 200
    assert res.mimetype == "text/plain"
    assert res.data.decode("utf-8") == "BPublicKeyBase64UrlText"


# ---------------------------------------------------------------------------
# GET /api/push/status
# ---------------------------------------------------------------------------


def test_status_returns_only_count_and_flags(
    tmp_path: Path, monkeypatch
) -> None:
    _patch_store_paths(tmp_path, monkeypatch)
    pss.register_subscription(
        _valid_subscription_payload(), now_utc="2026-05-09T00:00:00Z"
    )
    app = _make_app()
    client = app.test_client()
    res = client.get("/api/push/status")
    assert res.status_code == 200
    body = res.get_json()
    assert body["status"] == "ok"
    assert body["count"] == 1
    assert body["last_subscribed_at"] == "2026-05-09T00:00:00Z"
    assert body["vapid_public_present"] is False
    assert body["max_active_subscriptions"] == pss.MAX_ACTIVE_SUBSCRIPTIONS


def test_status_redacts_endpoints_and_keys(
    tmp_path: Path, monkeypatch
) -> None:
    _patch_store_paths(tmp_path, monkeypatch)
    pss.register_subscription(_valid_subscription_payload())
    app = _make_app()
    client = app.test_client()
    res = client.get("/api/push/status")
    raw = res.data.decode("utf-8")
    # Full endpoint URL, p256dh, auth must NOT appear.
    assert "fcm.googleapis.com/fcm/send/abc123" not in raw
    assert "BCfV1eK4_p256dh_public_key_base64url_text" not in raw
    assert "auth_secret_base64url_text" not in raw
    # Should not even contain key-sub-key names.
    body = res.get_json()
    assert "endpoint" not in body
    assert "keys" not in body


# ---------------------------------------------------------------------------
# POST /api/push/test
# ---------------------------------------------------------------------------


def test_test_endpoint_returns_synthetic_event_no_real_push(
    tmp_path: Path, monkeypatch
) -> None:
    _patch_store_paths(tmp_path, monkeypatch)
    app = _make_app()
    client = app.test_client()
    res = client.post("/api/push/test")
    assert res.status_code == 200
    body = res.get_json()
    assert body["status"] == "ok"
    assert body["real_push_sent"] is False
    assert body["would_dispatch_via"] == "n2b1_outbox_stub_provider"
    ev = body["test_event"]
    assert ev["event_kind"] == "intake_candidate_eligible"
    assert ev["event_severity"] == "push_info"
    assert ev["open_at"].startswith("/agent-control/inbox?event=")
    assert ev["event_id"].startswith("ade_test_")


def test_test_endpoint_payload_has_no_decision_verb(
    tmp_path: Path, monkeypatch
) -> None:
    _patch_store_paths(tmp_path, monkeypatch)
    app = _make_app()
    client = app.test_client()
    res = client.post("/api/push/test")
    raw = res.data.decode("utf-8").lower()
    for verb in ("approve", "reject", "merge ", " merge", "deploy"):
        assert verb not in raw, verb


# ---------------------------------------------------------------------------
# Source-text + AST scans
# ---------------------------------------------------------------------------


def _module_source() -> str:
    return Path(aps.__file__).read_text(encoding="utf-8")


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
    src = _module_source()
    assert "WEB_PUSH_VAPID_PRIVATE_KEY" not in src


def test_no_dashboard_dashboard_import() -> None:
    """The blueprint module must NOT import dashboard.dashboard."""
    for module in _imported_module_names():
        assert module != "dashboard.dashboard"
        assert not module.startswith("dashboard.dashboard.")


def test_no_frontend_or_research_imports() -> None:
    forbidden_prefixes = (
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


def test_module_imports_cleanly() -> None:
    importlib.reload(aps)
    assert callable(aps.register_push_subscribe_routes)


def test_importing_module_does_not_flip_step5_invariants() -> None:
    from reporting import development_step5_loop as dsl

    importlib.reload(aps)
    assert dsl.step5_implementation_allowed is False
    assert dsl.STEP5_ENABLED_SUBSTAGE == "none"


# ---------------------------------------------------------------------------
# dashboard/dashboard.py untouched
# ---------------------------------------------------------------------------


def test_dashboard_dashboard_does_not_register_push_routes() -> None:
    """Hard guarantee: the wiring to register_push_subscribe_routes
    has NOT landed yet. N2b-2a is unwired by design."""
    text = (
        REPO_ROOT / "dashboard" / "dashboard.py"
    ).read_text(encoding="utf-8")
    assert "register_push_subscribe_routes" not in text


def test_dashboard_dashboard_unchanged_in_pr_diff() -> None:
    """The current branch must not have modified dashboard/dashboard.py
    relative to origin/main. This is a defense-in-depth check; CI
    enforces the same via PR file-list assertions."""
    out = subprocess.run(
        ["git", "diff", "--name-only", "origin/main...HEAD"],
        check=False,
        capture_output=True,
        text=True,
        cwd=str(REPO_ROOT),
    )
    changed = set(out.stdout.split())
    if changed:
        # Not all CI runners have origin/main; if this fails for env
        # reasons, the PR-scope check still holds via the gh CLI.
        assert "dashboard/dashboard.py" not in changed
