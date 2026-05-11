"""Unit tests for N5a — dashboard.api_merge_recommendation (UNWIRED).

Pins:
* exactly 2 GET routes: list + detail; no other HTTP method;
* list with missing artifact → ``not_available`` envelope;
* list with valid artifact → bounded rows + counts;
* detail with missing artifact → 404 ``not_available``;
* detail with valid artifact but unknown id → 404 ``not_found``;
* detail with valid id → 200 with exactly one row;
* invalid recommendation_id (empty / too_long / bad_charset) →
  400 ``invalid_recommendation_id``;
* AST + source-text scans: no subprocess / gh / git / pywebpush /
  approval-token / approve(/reject(/merge(/deploy( call patterns /
  seed.jsonl writes;
* dashboard/dashboard.py does NOT yet import the blueprint
  (skip-or-enforce consistency);
* Step 5 invariants intact by import.
"""

from __future__ import annotations

import ast
import importlib
import json
from pathlib import Path
from typing import Any

import pytest
from flask import Flask

from dashboard import api_merge_recommendation as amr
from reporting import development_merge_recommendation as dmr


REPO_ROOT = Path(__file__).resolve().parents[2]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _isolate_artifact(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    target = (
        tmp_path
        / "logs"
        / "development_merge_recommendation"
        / "latest.json"
    )
    target.parent.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(dmr, "ARTIFACT_LATEST", target)
    return target


def _make_app() -> Flask:
    app = Flask(__name__)
    amr.register_merge_recommendation_routes(app)
    return app


def _valid_row(rid: str = "rec_pr_42") -> dict[str, Any]:
    return {
        "recommendation_id": rid,
        "pr_number": 42,
        "head_sha": "deadbeefdeadbeef0000000000000001",
        "head_ref": "feature/branch",
        "base_ref": "main",
        "observer_classification": "clean_open",
        "inbox_blocked_count": 0,
        "inbox_critical_count": 0,
        "inbox_needs_review_count": 0,
        "recommendation_action": "recommend_human_merge",
        "recommendation_reason": "pr_clean_and_no_blocking_inbox",
        "evaluated_at": "2026-05-11T20:00:00Z",
    }


def _write_artifact(
    artifact_path: Path, rows: list[dict[str, Any]]
) -> None:
    payload = {
        "schema_version": dmr.SCHEMA_VERSION,
        "module_version": dmr.MODULE_VERSION,
        "report_kind": dmr.REPORT_KIND,
        "generated_at_utc": "2026-05-11T20:30:00Z",
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
        if rule.rule.startswith("/api/agent-control/merge-recommendation/")
    )
    assert rules == [
        (
            "/api/agent-control/merge-recommendation/detail/<string:recommendation_id>",
            frozenset({"GET", "HEAD", "OPTIONS"}),
        ),
        (
            "/api/agent-control/merge-recommendation/list",
            frozenset({"GET", "HEAD", "OPTIONS"}),
        ),
    ]


def test_no_mutating_routes_registered() -> None:
    app = _make_app()
    for rule in app.url_map.iter_rules():
        if rule.rule.startswith(
            "/api/agent-control/merge-recommendation/"
        ):
            methods = rule.methods or set()
            assert not (
                methods & {"POST", "PUT", "PATCH", "DELETE"}
            ), f"unexpected mutating method on {rule.rule}: {methods}"


def test_blueprint_not_yet_wired_into_dashboard_dashboard() -> None:
    """Operator step pending: dashboard.py must not yet import the new
    blueprint. Once wired, the strict pin tests in
    test_dashboard_dashboard_one_line_wiring.py will assert the exact
    two-line shape."""
    text = (REPO_ROOT / "dashboard" / "dashboard.py").read_text(
        encoding="utf-8"
    )
    wiring_present = (
        "from dashboard.api_merge_recommendation "
        "import register_merge_recommendation_routes"
        in text
    )
    register_present = (
        "register_merge_recommendation_routes(app)" in text
    )
    assert wiring_present == register_present, (
        "dashboard.py must contain BOTH the import and the register "
        "call for api_merge_recommendation, or NEITHER."
    )


# ---------------------------------------------------------------------------
# List endpoint
# ---------------------------------------------------------------------------


def test_list_missing_artifact_returns_not_available() -> None:
    res = _make_app().test_client().get(
        "/api/agent-control/merge-recommendation/list"
    )
    assert res.status_code == 200
    body = res.get_json()
    assert body["status"] == "not_available"
    assert body["counts"]["rows"] == 0
    assert body["rows"] == []


def test_list_valid_artifact_returns_bounded_rows(
    _isolate_artifact: Path,
) -> None:
    rows = [_valid_row(f"rec_pr_{i:04d}") for i in range(3)]
    _write_artifact(_isolate_artifact, rows)
    res = _make_app().test_client().get(
        "/api/agent-control/merge-recommendation/list"
    )
    body = res.get_json()
    assert body["status"] == "ok"
    assert body["counts"]["rows"] == 3
    assert len(body["rows"]) == 3
    assert body["rows"][0]["recommendation_id"] == "rec_pr_0000"


def test_list_envelope_carries_step5_invariants(
    _isolate_artifact: Path,
) -> None:
    _write_artifact(_isolate_artifact, [_valid_row()])
    body = _make_app().test_client().get(
        "/api/agent-control/merge-recommendation/list"
    ).get_json()
    assert body["step5_implementation_allowed"] is False
    assert body["step5_enabled_substage"] == "none"


def test_list_malformed_artifact_returns_not_available(
    _isolate_artifact: Path,
) -> None:
    _isolate_artifact.write_text("not json", encoding="utf-8")
    body = _make_app().test_client().get(
        "/api/agent-control/merge-recommendation/list"
    ).get_json()
    assert body["status"] == "not_available"
    assert "malformed" in body["reason"]


def test_list_artifact_with_invalid_row_shapes_is_filtered(
    _isolate_artifact: Path,
) -> None:
    rows: list[dict[str, Any]] = [
        _valid_row("rec_keep"),
        {"recommendation_id": "rec_partial"},  # missing required keys
    ]
    _write_artifact(_isolate_artifact, rows)
    body = _make_app().test_client().get(
        "/api/agent-control/merge-recommendation/list"
    ).get_json()
    assert [r["recommendation_id"] for r in body["rows"]] == ["rec_keep"]


# ---------------------------------------------------------------------------
# Detail endpoint
# ---------------------------------------------------------------------------


def test_detail_missing_artifact_returns_404_not_available() -> None:
    res = _make_app().test_client().get(
        "/api/agent-control/merge-recommendation/detail/rec_x"
    )
    assert res.status_code == 404
    body = res.get_json()
    assert body["status"] == "not_available"


def test_detail_unknown_id_returns_404_not_found(
    _isolate_artifact: Path,
) -> None:
    _write_artifact(_isolate_artifact, [_valid_row("rec_existing")])
    res = _make_app().test_client().get(
        "/api/agent-control/merge-recommendation/detail/rec_nope"
    )
    assert res.status_code == 404
    body = res.get_json()
    assert body["status"] == "not_found"


def test_detail_valid_id_returns_exact_row(
    _isolate_artifact: Path,
) -> None:
    rows = [
        _valid_row("rec_first"),
        _valid_row("rec_second"),
        _valid_row("rec_third"),
    ]
    _write_artifact(_isolate_artifact, rows)
    res = _make_app().test_client().get(
        "/api/agent-control/merge-recommendation/detail/rec_second"
    )
    assert res.status_code == 200
    body = res.get_json()
    assert body["status"] == "ok"
    assert body["row"]["recommendation_id"] == "rec_second"
    # Closed-schema A23 row → no decision verb in any scalar value.
    for v in body["row"].values():
        if isinstance(v, str):
            lv = v.lower()
            # The A23 recommendation_action uses recommend_human_* —
            # explicitly NOT the verbs themselves.
            assert "approve_" not in lv or "recommend" in lv
            assert "deploy" not in lv
            assert "reject" not in lv


def test_detail_invalid_id_too_long_returns_400(
    _isolate_artifact: Path,
) -> None:
    _write_artifact(_isolate_artifact, [_valid_row()])
    big = "x" * 200
    res = _make_app().test_client().get(
        f"/api/agent-control/merge-recommendation/detail/{big}"
    )
    assert res.status_code == 400
    body = res.get_json()
    assert body["status"] == "invalid_recommendation_id"
    assert body["reason"] == "too_long"


def test_detail_invalid_id_bad_charset_returns_400(
    _isolate_artifact: Path,
) -> None:
    _write_artifact(_isolate_artifact, [_valid_row()])
    res = _make_app().test_client().get(
        "/api/agent-control/merge-recommendation/detail/bad%20id"
    )
    assert res.status_code == 400
    body = res.get_json()
    assert body["status"] == "invalid_recommendation_id"
    assert body["reason"] == "bad_charset"


def test_detail_envelope_carries_step5_invariants(
    _isolate_artifact: Path,
) -> None:
    _write_artifact(_isolate_artifact, [_valid_row("rec_x")])
    body = _make_app().test_client().get(
        "/api/agent-control/merge-recommendation/detail/rec_x"
    ).get_json()
    assert body["step5_implementation_allowed"] is False
    assert body["step5_enabled_substage"] == "none"


# ---------------------------------------------------------------------------
# Response payload safety
# ---------------------------------------------------------------------------


def test_response_payload_has_no_unexpected_secret_markers(
    _isolate_artifact: Path,
) -> None:
    _write_artifact(_isolate_artifact, [_valid_row()])
    res = _make_app().test_client().get(
        "/api/agent-control/merge-recommendation/list"
    )
    raw = res.data.decode("utf-8")
    # No VAPID / push / token-secret material should ever land here.
    assert "BEGIN PRIVATE KEY" not in raw
    assert "p256dh" not in raw
    assert "ADE_APPROVAL_TOKEN_HMAC_SECRET" not in raw


# ---------------------------------------------------------------------------
# Source-text + AST scans
# ---------------------------------------------------------------------------


def _module_source() -> str:
    return Path(amr.__file__).read_text(encoding="utf-8")


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


def test_no_approval_token_secret_literal_in_module() -> None:
    """N5a is a read-only inspector — it must not reference the
    approval-token env secret. Token issuance/verification is N4b
    territory."""
    src = _module_source()
    assert "ADE_APPROVAL_TOKEN_HMAC_SECRET" not in src


def test_no_token_mint_helpers_imported() -> None:
    """N5a must not import the approval-token mint/verify helpers.
    Acting on a recommendation is N5b territory and requires
    explicit operator authorisation."""
    names = _imported_module_names()
    for forbidden in (
        "reporting.approval_token_gate",
        "reporting.approval_token_runtime",
    ):
        assert forbidden not in names, forbidden


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


def test_imports_only_dmr_aas_flask_and_stdlib() -> None:
    """The blueprint must import only the A23 projector module, the
    secret-redactor guard, and Flask."""
    names = _imported_module_names()
    allowed_reporting = {
        "reporting",
        "reporting.development_merge_recommendation",
        "reporting.agent_audit_summary",
    }
    for n in names:
        if n == "reporting" or n.startswith("reporting."):
            assert n in allowed_reporting, n


# ---------------------------------------------------------------------------
# Step 5 invariants
# ---------------------------------------------------------------------------


def test_import_does_not_flip_step5_invariants() -> None:
    importlib.reload(amr)
    assert amr.step5_implementation_allowed is False
    assert amr.STEP5_ENABLED_SUBSTAGE == "none"


def test_module_source_pins_step5_invariants() -> None:
    src = _module_source()
    assert "step5_implementation_allowed: Final[bool] = False" in src
    assert 'STEP5_ENABLED_SUBSTAGE: Final[str] = "none"' in src
    assert "step5_implementation_allowed = True" not in src
