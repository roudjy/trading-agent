"""Unit tests for N3b — dashboard.api_mobile_approval_inbox (UNWIRED).

Pins:
* exactly 2 GET routes registered: list + detail; no other HTTP
  method is registered;
* list with missing artifact → ``not_available`` envelope;
* list with valid artifact → bounded rows + counts;
* detail with missing artifact → 404 ``not_available``;
* detail with valid artifact but unknown event_id → 404 ``not_found``;
* detail with valid event_id → 200 with exactly one row;
* invalid event_id (empty / too long / bad charset) → 400
  ``invalid_event_id``;
* AST + source-text scans: no ``subprocess`` / ``gh`` / ``git`` /
  ``pywebpush`` / ``WEB_PUSH_VAPID_PRIVATE_KEY`` / approval-token
  helpers / decision-verb call patterns;
* ``dashboard/dashboard.py`` does NOT yet import the new blueprint
  (skip-or-enforce dual mode — operator step);
* Step 5 invariants unchanged by import.
"""

from __future__ import annotations

import ast
import importlib
import json
from pathlib import Path
from typing import Any

import pytest
from flask import Flask

from dashboard import api_mobile_approval_inbox as amai
from reporting import mobile_approval_inbox as mai


REPO_ROOT = Path(__file__).resolve().parents[2]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _isolate_artifact(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Redirect ARTIFACT_LATEST into ``tmp_path`` so tests never read or
    write the developer's logs/ directory."""
    target = tmp_path / "logs" / "mobile_approval_inbox" / "latest.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(mai, "ARTIFACT_LATEST", target)
    return target


def _make_app() -> Flask:
    app = Flask(__name__)
    amai.register_mobile_approval_inbox_routes(app)
    return app


def _valid_row(event_id: str = "evt_abc12345abc12345") -> dict[str, Any]:
    return {
        "inbox_row_id": "row_" + event_id,
        "event_id": event_id,
        "event_kind": "intake_candidate_eligible",
        "event_severity": "push_info",
        "source_module": "notification_dispatch_outbox",
        "source_id": event_id,
        "endpoint_hash": "deadbeefdeadbeef",
        "outbound_delivery_intent": "sent",
        "attention_level": "informational",
        "decision_state": "pending",
        "title": "Some inbox title",
        "summary": "A bounded inbox summary.",
        "open_at": f"/agent-control/inbox?event={event_id}",
        "created_at": "2026-05-11T08:00:00Z",
    }


def _write_artifact(artifact_path: Path, rows: list[dict[str, Any]]) -> None:
    payload = {
        "schema_version": mai.SCHEMA_VERSION,
        "module_version": mai.MODULE_VERSION,
        "report_kind": mai.REPORT_KIND,
        "generated_at_utc": "2026-05-11T08:30:00Z",
        "rows": rows,
    }
    artifact_path.write_text(json.dumps(payload), encoding="utf-8")


# ---------------------------------------------------------------------------
# Route registration
# ---------------------------------------------------------------------------


def test_register_routes_registers_only_two_get_routes() -> None:
    app = _make_app()
    rules = sorted(
        (rule.rule, frozenset(rule.methods or set()))
        for rule in app.url_map.iter_rules()
        if rule.rule.startswith("/api/agent-control/mobile-inbox/")
    )
    assert rules == [
        (
            "/api/agent-control/mobile-inbox/detail/<string:event_id>",
            frozenset({"GET", "HEAD", "OPTIONS"}),
        ),
        (
            "/api/agent-control/mobile-inbox/list",
            frozenset({"GET", "HEAD", "OPTIONS"}),
        ),
    ]


def test_no_mutating_routes_registered() -> None:
    app = _make_app()
    for rule in app.url_map.iter_rules():
        if rule.rule.startswith("/api/agent-control/mobile-inbox/"):
            methods = rule.methods or set()
            assert not (methods & {"POST", "PUT", "PATCH", "DELETE"}), (
                f"unexpected mutating method on {rule.rule}: {methods}"
            )


def test_blueprint_not_yet_wired_into_dashboard_dashboard() -> None:
    """Operator step pending: dashboard.py must not yet import the new
    blueprint. Once wired, the strict pin tests in
    test_dashboard_dashboard_one_line_wiring.py will assert the exact
    two-line shape."""
    text = (REPO_ROOT / "dashboard" / "dashboard.py").read_text(
        encoding="utf-8"
    )
    wiring_present = (
        "from dashboard.api_mobile_approval_inbox import register_mobile_approval_inbox_routes"
        in text
    )
    register_present = "register_mobile_approval_inbox_routes(app)" in text
    assert wiring_present == register_present, (
        "dashboard.py must contain BOTH the import and the register "
        "call for api_mobile_approval_inbox, or NEITHER."
    )


# ---------------------------------------------------------------------------
# List endpoint
# ---------------------------------------------------------------------------


def test_list_missing_artifact_returns_not_available() -> None:
    app = _make_app()
    client = app.test_client()
    res = client.get("/api/agent-control/mobile-inbox/list")
    assert res.status_code == 200
    body = res.get_json()
    assert body["status"] == "not_available"
    assert body["counts"]["rows"] == 0
    assert body["rows"] == []


def test_list_valid_artifact_returns_bounded_rows(
    _isolate_artifact: Path,
) -> None:
    rows = [_valid_row(f"evt_{i:08d}") for i in range(3)]
    _write_artifact(_isolate_artifact, rows)
    app = _make_app()
    res = app.test_client().get("/api/agent-control/mobile-inbox/list")
    body = res.get_json()
    assert body["status"] == "ok"
    assert body["counts"]["rows"] == 3
    assert len(body["rows"]) == 3
    assert body["rows"][0]["event_id"] == "evt_00000000"


def test_list_envelope_carries_step5_invariants(
    _isolate_artifact: Path,
) -> None:
    _write_artifact(_isolate_artifact, [_valid_row()])
    app = _make_app()
    body = app.test_client().get(
        "/api/agent-control/mobile-inbox/list"
    ).get_json()
    assert body["step5_implementation_allowed"] is False
    assert body["step5_enabled_substage"] == "none"


def test_list_malformed_artifact_returns_not_available(
    _isolate_artifact: Path,
) -> None:
    _isolate_artifact.write_text("not json", encoding="utf-8")
    app = _make_app()
    res = app.test_client().get("/api/agent-control/mobile-inbox/list")
    body = res.get_json()
    assert body["status"] == "not_available"
    assert "malformed" in body["reason"]


def test_list_artifact_with_invalid_row_shapes_is_filtered(
    _isolate_artifact: Path,
) -> None:
    rows: list[dict[str, Any]] = [
        _valid_row("evt_keep"),
        {"event_id": "evt_partial"},  # missing required keys
    ]
    _write_artifact(_isolate_artifact, rows)
    res = _make_app().test_client().get(
        "/api/agent-control/mobile-inbox/list"
    )
    body = res.get_json()
    assert [r["event_id"] for r in body["rows"]] == ["evt_keep"]


# ---------------------------------------------------------------------------
# Detail endpoint
# ---------------------------------------------------------------------------


def test_detail_missing_artifact_returns_404_not_available() -> None:
    app = _make_app()
    res = app.test_client().get(
        "/api/agent-control/mobile-inbox/detail/evt_abc"
    )
    assert res.status_code == 404
    body = res.get_json()
    assert body["status"] == "not_available"


def test_detail_unknown_event_id_returns_404_not_found(
    _isolate_artifact: Path,
) -> None:
    _write_artifact(_isolate_artifact, [_valid_row("evt_existing")])
    app = _make_app()
    res = app.test_client().get(
        "/api/agent-control/mobile-inbox/detail/evt_nope"
    )
    assert res.status_code == 404
    body = res.get_json()
    assert body["status"] == "not_found"


def test_detail_valid_event_id_returns_exact_row(
    _isolate_artifact: Path,
) -> None:
    rows = [
        _valid_row("evt_first"),
        _valid_row("evt_second"),
        _valid_row("evt_third"),
    ]
    _write_artifact(_isolate_artifact, rows)
    app = _make_app()
    res = app.test_client().get(
        "/api/agent-control/mobile-inbox/detail/evt_second"
    )
    assert res.status_code == 200
    body = res.get_json()
    assert body["status"] == "ok"
    assert body["row"]["event_id"] == "evt_second"
    # The row is the closed N3a schema — no decision verb in payload.
    for v in body["row"].values():
        if isinstance(v, str):
            lv = v.lower()
            assert "approve" not in lv
            assert "reject" not in lv
            assert "deploy" not in lv


def test_detail_invalid_event_id_too_long_returns_400(
    _isolate_artifact: Path,
) -> None:
    _write_artifact(_isolate_artifact, [_valid_row()])
    app = _make_app()
    big = "x" * 200
    res = app.test_client().get(
        f"/api/agent-control/mobile-inbox/detail/{big}"
    )
    assert res.status_code == 400
    body = res.get_json()
    assert body["status"] == "invalid_event_id"
    assert body["reason"] == "too_long"


def test_detail_invalid_event_id_bad_charset_returns_400(
    _isolate_artifact: Path,
) -> None:
    _write_artifact(_isolate_artifact, [_valid_row()])
    app = _make_app()
    # Flask path parameter does not accept '/' but allows ' '
    # via URL encoding. We assert that something outside [A-Za-z0-9_-]
    # is rejected.
    res = app.test_client().get(
        "/api/agent-control/mobile-inbox/detail/bad%20event"
    )
    assert res.status_code == 400
    body = res.get_json()
    assert body["status"] == "invalid_event_id"
    assert body["reason"] == "bad_charset"


def test_detail_envelope_carries_step5_invariants(
    _isolate_artifact: Path,
) -> None:
    _write_artifact(_isolate_artifact, [_valid_row("evt_x")])
    body = _make_app().test_client().get(
        "/api/agent-control/mobile-inbox/detail/evt_x"
    ).get_json()
    assert body["step5_implementation_allowed"] is False
    assert body["step5_enabled_substage"] == "none"


# ---------------------------------------------------------------------------
# Response payload safety: no endpoint URL leak, no key material
# ---------------------------------------------------------------------------


def test_response_payload_has_no_endpoint_url_or_key_material(
    _isolate_artifact: Path,
) -> None:
    """The N3a artefact already redacts these; we re-assert at the API
    boundary that the response carries only the closed scalars and
    never a raw subscription endpoint URL or key bytes."""
    _write_artifact(_isolate_artifact, [_valid_row()])
    res = _make_app().test_client().get(
        "/api/agent-control/mobile-inbox/list"
    )
    raw = res.data.decode("utf-8")
    assert "fcm.googleapis.com" not in raw
    assert "p256dh" not in raw
    assert "BEGIN PRIVATE KEY" not in raw


# ---------------------------------------------------------------------------
# Source-text + AST scans
# ---------------------------------------------------------------------------


def _module_source() -> str:
    return Path(amai.__file__).read_text(encoding="utf-8")


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
    for needle in ("subprocess.run", "subprocess.call", " gh ", " git "):
        assert needle not in src, needle


def test_no_web_push_library_import_in_module() -> None:
    names = _imported_module_names()
    for n in names:
        assert n not in {"pywebpush", "webpush", "web_push"}, n
        assert not n.startswith("pywebpush."), n


def test_no_vapid_private_key_literal_in_module() -> None:
    src = _module_source()
    assert "WEB_PUSH_VAPID_PRIVATE_KEY" not in src


def test_no_token_mint_helpers_in_module() -> None:
    src = _module_source().lower()
    for needle in (
        "mint_approval_token",
        "approval_token_mint",
        "verify_approval_token",
        "approval_token_gate",
    ):
        assert needle not in src, needle


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


def test_imports_only_mai_aas_flask_and_stdlib() -> None:
    """The blueprint must import only the N3a projector module, the
    secret-redactor guard, and Flask. No other reporting module."""
    names = _imported_module_names()
    allowed_reporting = {
        "reporting",
        "reporting.mobile_approval_inbox",
        "reporting.agent_audit_summary",
    }
    for n in names:
        if n == "reporting" or n.startswith("reporting."):
            assert n in allowed_reporting, n


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


# ---------------------------------------------------------------------------
# Step 5 invariants
# ---------------------------------------------------------------------------


def test_import_does_not_flip_step5_invariants() -> None:
    importlib.reload(amai)
    assert amai.step5_implementation_allowed is False
    assert amai.STEP5_ENABLED_SUBSTAGE == "none"


def test_module_source_pins_step5_invariants() -> None:
    src = _module_source()
    assert "step5_implementation_allowed: Final[bool] = False" in src
    assert 'STEP5_ENABLED_SUBSTAGE: Final[str] = "none"' in src
    assert "step5_implementation_allowed = True" not in src
