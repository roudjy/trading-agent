"""Unit tests for N4b — dashboard.api_approval_token_gate (UNWIRED).

Pins:
* exactly 3 routes registered: GET status, POST mint, POST verify;
  no other HTTP method appears on any of those paths;
* every route refuses without an operator session (401);
* mint/verify refuse without env (503 ``configuration_missing``);
* oversize body → 413 ``payload_too_large``;
* happy mint + happy verify round-trip with synthetic env secret;
* replay rejected on second verify of the same nonce;
* malformed/binding-mismatched token rejected with closed outcome;
* no secret material leaks into any response body;
* AST + source-text scans: no subprocess / gh / git / pywebpush /
  approve(/reject(/merge(/deploy( call patterns / seed.jsonl writes;
* ``dashboard/dashboard.py`` does NOT yet import the new blueprint
  (skip-or-enforce consistency);
* Step 5 invariants intact by import.
"""

from __future__ import annotations

import ast
import importlib
import secrets as _secrets
from pathlib import Path
from typing import Any

import pytest
from flask import Flask

from dashboard import api_approval_token_gate as atg_api
from reporting import approval_token_runtime as atr


REPO_ROOT = Path(__file__).resolve().parents[2]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _isolate_state(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    target = tmp_path / "state" / "approval_token_seen_nonces.jsonl"
    target.parent.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(atr, "SEEN_NONCES_PATH", target)
    return target


@pytest.fixture(autouse=True)
def _clear_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(atr.ENV_APPROVAL_TOKEN_HMAC_SECRET, raising=False)


def _synthetic_secret_hex() -> str:
    return _secrets.token_hex(32)


def _make_app() -> Flask:
    app = Flask(__name__)
    # Set a session secret_key so test_client can sign cookies and
    # session_transaction works.
    app.secret_key = "test-secret-key-for-flask-session"
    atg_api.register_approval_token_gate_routes(app)
    return app


def _authed_client(app: Flask):
    client = app.test_client()
    with client.session_transaction() as sess:
        sess["operator_authenticated"] = True
        sess["operator_actor"] = "test"
    return client


# ---------------------------------------------------------------------------
# Route registration
# ---------------------------------------------------------------------------


def test_register_routes_registers_exactly_three_routes() -> None:
    app = _make_app()
    rules = sorted(
        (rule.rule, frozenset(rule.methods or set()))
        for rule in app.url_map.iter_rules()
        if rule.rule.startswith("/api/agent-control/approval-token/")
    )
    assert rules == [
        (
            "/api/agent-control/approval-token/mint",
            frozenset({"POST", "OPTIONS"}),
        ),
        (
            "/api/agent-control/approval-token/status",
            frozenset({"GET", "HEAD", "OPTIONS"}),
        ),
        (
            "/api/agent-control/approval-token/verify",
            frozenset({"POST", "OPTIONS"}),
        ),
    ]


def test_no_unexpected_methods_on_token_paths() -> None:
    app = _make_app()
    for rule in app.url_map.iter_rules():
        if not rule.rule.startswith("/api/agent-control/approval-token/"):
            continue
        methods = rule.methods or set()
        if rule.rule.endswith("/status"):
            assert "POST" not in methods
            assert "PUT" not in methods
            assert "DELETE" not in methods
        else:
            assert "GET" not in methods
            assert "PUT" not in methods
            assert "DELETE" not in methods


def test_blueprint_not_yet_wired_into_dashboard_dashboard() -> None:
    text = (REPO_ROOT / "dashboard" / "dashboard.py").read_text(
        encoding="utf-8"
    )
    wiring_present = (
        "from dashboard.api_approval_token_gate "
        "import register_approval_token_gate_routes"
        in text
    )
    register_present = (
        "register_approval_token_gate_routes(app)" in text
    )
    assert wiring_present == register_present, (
        "dashboard.py must contain BOTH the import and the register "
        "call for api_approval_token_gate, or NEITHER."
    )


# ---------------------------------------------------------------------------
# Auth — every route requires an operator session
# ---------------------------------------------------------------------------


def test_status_requires_operator_session() -> None:
    app = _make_app()
    res = app.test_client().get("/api/agent-control/approval-token/status")
    assert res.status_code == 401
    body = res.get_json()
    assert body["error"] == "operator_session_required"


def test_mint_requires_operator_session() -> None:
    app = _make_app()
    res = app.test_client().post(
        "/api/agent-control/approval-token/mint",
        data="{}",
        content_type="application/json",
    )
    assert res.status_code == 401


def test_verify_requires_operator_session() -> None:
    app = _make_app()
    res = app.test_client().post(
        "/api/agent-control/approval-token/verify",
        data="{}",
        content_type="application/json",
    )
    assert res.status_code == 401


# ---------------------------------------------------------------------------
# Env gate
# ---------------------------------------------------------------------------


def test_mint_returns_503_when_env_unset() -> None:
    app = _make_app()
    client = _authed_client(app)
    res = client.post(
        "/api/agent-control/approval-token/mint",
        json={
            "intent": "mobile_approval_dispatch",
            "event_id": "evt_x",
            "evidence_hash": "h_x",
        },
    )
    assert res.status_code == 503
    assert res.get_json()["error"] == "configuration_missing"


def test_verify_returns_503_when_env_unset() -> None:
    app = _make_app()
    client = _authed_client(app)
    res = client.post(
        "/api/agent-control/approval-token/verify",
        json={
            "token": "a.b",
            "expected_event_id": "evt_x",
            "expected_evidence_hash": "h_x",
        },
    )
    assert res.status_code == 503
    assert res.get_json()["error"] == "configuration_missing"


def test_status_reports_unconfigured() -> None:
    app = _make_app()
    client = _authed_client(app)
    res = client.get("/api/agent-control/approval-token/status")
    assert res.status_code == 200
    body = res.get_json()
    assert body["status"] == "ok"
    assert body["is_configured"] is False
    assert body["current_kid"] == atr.CURRENT_KID
    assert body["step5_implementation_allowed"] is False
    assert body["step5_enabled_substage"] == "none"


def test_status_reports_configured_when_env_set(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(
        atr.ENV_APPROVAL_TOKEN_HMAC_SECRET, _synthetic_secret_hex()
    )
    client = _authed_client(_make_app())
    body = client.get(
        "/api/agent-control/approval-token/status"
    ).get_json()
    assert body["is_configured"] is True


# ---------------------------------------------------------------------------
# Body-size gate
# ---------------------------------------------------------------------------


def test_mint_oversize_body_returns_413(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(
        atr.ENV_APPROVAL_TOKEN_HMAC_SECRET, _synthetic_secret_hex()
    )
    app = _make_app()
    client = _authed_client(app)
    res = client.post(
        "/api/agent-control/approval-token/mint",
        data="x" * (atg_api._MAX_REQUEST_BYTES + 1),
        content_type="application/json",
    )
    assert res.status_code == 413


def test_verify_oversize_body_returns_413(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(
        atr.ENV_APPROVAL_TOKEN_HMAC_SECRET, _synthetic_secret_hex()
    )
    client = _authed_client(_make_app())
    res = client.post(
        "/api/agent-control/approval-token/verify",
        data="x" * (atg_api._MAX_REQUEST_BYTES + 1),
        content_type="application/json",
    )
    assert res.status_code == 413


# ---------------------------------------------------------------------------
# Happy mint + verify round-trip
# ---------------------------------------------------------------------------


def test_mint_happy_path_returns_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(
        atr.ENV_APPROVAL_TOKEN_HMAC_SECRET, _synthetic_secret_hex()
    )
    client = _authed_client(_make_app())
    res = client.post(
        "/api/agent-control/approval-token/mint",
        json={
            "intent": "mobile_approval_dispatch",
            "event_id": "evt_happy",
            "pr_number": 42,
            "pr_head_sha": "deadbeef00000001",
            "evidence_hash": "h_happy",
            "release_tag": None,
        },
    )
    assert res.status_code == 200
    body = res.get_json()
    assert body["status"] == "ok"
    assert isinstance(body["token"], str) and "." in body["token"]
    assert body["kid"] == atr.CURRENT_KID
    assert body["intent"] == "mobile_approval_dispatch"
    assert body["event_id"] == "evt_happy"


def test_mint_then_verify_round_trip(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(
        atr.ENV_APPROVAL_TOKEN_HMAC_SECRET, _synthetic_secret_hex()
    )
    client = _authed_client(_make_app())
    mint = client.post(
        "/api/agent-control/approval-token/mint",
        json={
            "intent": "mobile_approval_dispatch",
            "event_id": "evt_rt",
            "pr_number": 7,
            "pr_head_sha": "abc1230000000001",
            "evidence_hash": "h_rt",
            "release_tag": None,
        },
    )
    token = mint.get_json()["token"]
    verify = client.post(
        "/api/agent-control/approval-token/verify",
        json={
            "token": token,
            "expected_event_id": "evt_rt",
            "expected_pr_number": 7,
            "expected_pr_head_sha": "abc1230000000001",
            "expected_evidence_hash": "h_rt",
            "expected_release_tag": None,
        },
    )
    assert verify.status_code == 200
    body = verify.get_json()
    assert body == {"status": "ok", "outcome": "ok", "reason": "verified"}


def test_verify_rejects_replay_with_replay_detected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(
        atr.ENV_APPROVAL_TOKEN_HMAC_SECRET, _synthetic_secret_hex()
    )
    client = _authed_client(_make_app())
    mint = client.post(
        "/api/agent-control/approval-token/mint",
        json={
            "intent": "mobile_approval_dispatch",
            "event_id": "evt_replay",
            "evidence_hash": "h_replay",
        },
    )
    token = mint.get_json()["token"]
    first = client.post(
        "/api/agent-control/approval-token/verify",
        json={
            "token": token,
            "expected_event_id": "evt_replay",
            "expected_evidence_hash": "h_replay",
        },
    )
    assert first.get_json()["outcome"] == "ok"
    second = client.post(
        "/api/agent-control/approval-token/verify",
        json={
            "token": token,
            "expected_event_id": "evt_replay",
            "expected_evidence_hash": "h_replay",
        },
    )
    assert second.status_code == 400
    body = second.get_json()
    assert body["status"] == "rejected"
    assert body["outcome"] == "replay_detected"


def test_verify_rejects_binding_mismatch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(
        atr.ENV_APPROVAL_TOKEN_HMAC_SECRET, _synthetic_secret_hex()
    )
    client = _authed_client(_make_app())
    mint = client.post(
        "/api/agent-control/approval-token/mint",
        json={
            "intent": "mobile_approval_dispatch",
            "event_id": "evt_bind",
            "evidence_hash": "h_bind",
        },
    )
    token = mint.get_json()["token"]
    bad = client.post(
        "/api/agent-control/approval-token/verify",
        json={
            "token": token,
            "expected_event_id": "evt_OTHER",
            "expected_evidence_hash": "h_bind",
        },
    )
    body = bad.get_json()
    assert body["outcome"] == "binding_mismatch"


def test_verify_rejects_malformed_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(
        atr.ENV_APPROVAL_TOKEN_HMAC_SECRET, _synthetic_secret_hex()
    )
    client = _authed_client(_make_app())
    res = client.post(
        "/api/agent-control/approval-token/verify",
        json={
            "token": "not-a-valid-token",
            "expected_event_id": "evt",
            "expected_evidence_hash": "h",
        },
    )
    body = res.get_json()
    assert body["outcome"] == "malformed_envelope"


# ---------------------------------------------------------------------------
# Body validation
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "body,err",
    [
        ({}, "intent_must_be_string"),
        ({"intent": 42}, "intent_must_be_string"),
        (
            {"intent": "mobile_approval_dispatch"},
            "event_id_must_be_string",
        ),
        (
            {
                "intent": "mobile_approval_dispatch",
                "event_id": "evt_x",
            },
            "evidence_hash_must_be_string",
        ),
        (
            {
                "intent": "mobile_approval_dispatch",
                "event_id": "evt_x",
                "evidence_hash": "h",
                "pr_number": "not_int",
            },
            "pr_number_must_be_int_or_null",
        ),
    ],
)
def test_mint_rejects_malformed_body(
    body: dict[str, Any],
    err: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(
        atr.ENV_APPROVAL_TOKEN_HMAC_SECRET, _synthetic_secret_hex()
    )
    client = _authed_client(_make_app())
    res = client.post(
        "/api/agent-control/approval-token/mint",
        json=body,
    )
    assert res.status_code == 400
    assert res.get_json()["error"] == err


# ---------------------------------------------------------------------------
# Secret leakage / response body safety
# ---------------------------------------------------------------------------


def test_response_never_leaks_env_secret(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    raw = _synthetic_secret_hex()
    monkeypatch.setenv(atr.ENV_APPROVAL_TOKEN_HMAC_SECRET, raw)
    client = _authed_client(_make_app())
    res = client.post(
        "/api/agent-control/approval-token/mint",
        json={
            "intent": "mobile_approval_dispatch",
            "event_id": "evt_leak",
            "evidence_hash": "h_leak",
        },
    )
    body_raw = res.data.decode("utf-8")
    assert raw not in body_raw


# ---------------------------------------------------------------------------
# Source-text + AST scans
# ---------------------------------------------------------------------------


def _module_source() -> str:
    return Path(atg_api.__file__).read_text(encoding="utf-8")


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
    for needle in ("subprocess.run", " gh ", " git "):
        assert needle not in src, needle


def test_no_web_push_library_import_in_module() -> None:
    names = _imported_module_names()
    for n in names:
        assert n not in {"pywebpush", "webpush", "web_push"}, n


def test_no_vapid_private_key_literal_in_module() -> None:
    src = _module_source()
    assert "WEB_PUSH_VAPID_PRIVATE_KEY" not in src


def test_no_decision_verb_call_in_module() -> None:
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


def test_imports_only_atr_aas_flask_and_stdlib() -> None:
    names = _imported_module_names()
    allowed_reporting = {
        "reporting",
        "reporting.approval_token_runtime",
        "reporting.agent_audit_summary",
    }
    for n in names:
        if n == "reporting" or n.startswith("reporting."):
            assert n in allowed_reporting, n


# ---------------------------------------------------------------------------
# Step 5 invariants
# ---------------------------------------------------------------------------


def test_import_does_not_flip_step5_invariants() -> None:
    importlib.reload(atg_api)
    assert atg_api.step5_implementation_allowed is False
    assert atg_api.STEP5_ENABLED_SUBSTAGE == "none"


def test_module_source_pins_step5_invariants() -> None:
    src = _module_source()
    assert "step5_implementation_allowed: Final[bool] = False" in src
    assert 'STEP5_ENABLED_SUBSTAGE: Final[str] = "none"' in src
    assert "step5_implementation_allowed = True" not in src
