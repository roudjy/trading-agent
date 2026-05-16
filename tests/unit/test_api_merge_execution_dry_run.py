"""Pin tests for the B2.8c N5b Phase 2 token-bound dry-run walker
(``dashboard/api_merge_execution_dry_run.py``).

The module under test ships the walker for parent-doc §3
preconditions 1–7 layered on top of the B2.8b skeleton. The
closed contracts (route, envelope, method, UNWIRED state) are
preserved verbatim; the walker adds the rejected /
configuration_missing / not_yet_implemented branches and the
preflight artefact write that must occur ONLY after all 1–7
clear.

The preconditions 8–17 (GitHub-API-dependent) remain in B2.8d
scope and are not exercised here. The dry-run-decision / failure
/ history artefact writers remain in B2.8d / B2.8e scope.

Defense-in-depth note: forbidden marker strings the tests search
for are NEVER embedded as literals in this file when they would
also trip the runtime source-text scan; markers are assembled at
runtime from constituent parts.
"""

from __future__ import annotations

import ast
import json
import secrets as _secrets
from pathlib import Path
from typing import Any

import pytest
from flask import Flask

from dashboard import api_merge_execution_dry_run as mod
from reporting import approval_token_runtime as atr

REPO_ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = REPO_ROOT / "dashboard" / "api_merge_execution_dry_run.py"
DASHBOARD_PY = REPO_ROOT / "dashboard" / "dashboard.py"
N4C_COMPONENT_PATH = (
    REPO_ROOT
    / "frontend"
    / "src"
    / "routes"
    / "AgentControl"
    / "ApprovalTokenDiagnostics.tsx"
)

ROUTE_URL = "/api/agent-control/merge-execution/dry-run"


# ---------------------------------------------------------------------------
# Test isolation — env + seen-nonce store + preflight artefact target
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _isolate_state(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Redirect the approval-token-runtime seen-nonce store and the
    preflight artefact write target into ``tmp_path/...``. The repo's
    real artefact paths are never touched by these tests."""
    seen_target = tmp_path / "state" / "approval_token_seen_nonces.jsonl"
    seen_target.parent.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(atr, "SEEN_NONCES_PATH", seen_target)

    preflight_target = (
        tmp_path
        / "logs"
        / "n5b_merge_execution"
        / "preflight"
        / "latest.json"
    )
    preflight_target.parent.mkdir(parents=True, exist_ok=True)
    # Re-bind the projector's PREFLIGHT_LATEST to the tmp path so the
    # walker writes into the test sandbox. The sentinel substring
    # ``logs/n5b_merge_execution/`` is preserved by the redirection.
    from reporting import n5b_merge_execution_dry_run as projector

    monkeypatch.setattr(projector, "PREFLIGHT_LATEST", preflight_target)
    monkeypatch.delenv(atr.ENV_APPROVAL_TOKEN_HMAC_SECRET, raising=False)
    yield preflight_target


# ---------------------------------------------------------------------------
# Module surface
# ---------------------------------------------------------------------------


def test_module_imports_successfully() -> None:
    assert mod is not None


def test_module_version_is_pinned_string() -> None:
    assert mod.MODULE_VERSION == "v3.15.16.N5b.phase2.walker_1_7"


def test_schema_version_is_pinned_integer_1() -> None:
    assert mod.SCHEMA_VERSION == 1


def test_step5_enabled_substage_is_pinned_none() -> None:
    assert mod.STEP5_ENABLED_SUBSTAGE == "none"


def test_step5_implementation_allowed_is_pinned_false() -> None:
    assert mod.step5_implementation_allowed is False


def test_all_exports_are_closed() -> None:
    assert set(mod.__all__) == {
        "MODULE_VERSION",
        "SCHEMA_VERSION",
        "STEP5_ENABLED_SUBSTAGE",
        "register_merge_execution_dry_run_routes",
        "step5_implementation_allowed",
    }


def test_register_helper_callable_exists() -> None:
    assert callable(mod.register_merge_execution_dry_run_routes)


# ---------------------------------------------------------------------------
# AST guards — forbidden imports; required imports
# ---------------------------------------------------------------------------


_FORBIDDEN_IMPORT_TOPS = (
    "subprocess",
    "socket",
    "urllib",
    "requests",
    "httpx",
    "aiohttp",
    "asyncio",
    # B2.8c is allowed to import the token runtime + the projector.
    # No GitHub API client of any flavour.
    "github",
    "ghapi",
    "PyGithub",
)

_REQUIRED_IMPORTS = (
    "reporting.approval_token_runtime",
    "reporting.n5b_merge_execution_dry_run",
)


def _module_imports() -> list[str]:
    """Return the set of importable names referenced by the module's
    imports. For ``from PKG import NAME`` we emit both ``PKG`` and
    ``PKG.NAME`` so positive pins on dotted-form imports work."""
    src = MODULE_PATH.read_text(encoding="utf-8")
    tree = ast.parse(src)
    names: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                names.append(alias.name)
        if isinstance(node, ast.ImportFrom) and node.module is not None:
            names.append(node.module)
            for alias in node.names:
                names.append(f"{node.module}.{alias.name}")
    return names


def test_module_has_no_forbidden_top_level_imports() -> None:
    imported = _module_imports()
    offending: list[str] = []
    for name in imported:
        for forbidden in _FORBIDDEN_IMPORT_TOPS:
            if name == forbidden or name.startswith(forbidden + "."):
                offending.append(name)
    assert offending == [], (
        f"walker imports forbidden modules: {offending!r}."
    )


def test_module_imports_token_runtime_and_projector() -> None:
    """Positive pin: B2.8c is required to import the two B2.8c-scope
    modules. Removing either import indicates the walker was reverted
    to the B2.8b skeleton without a corresponding pin-test update."""
    imported = set(_module_imports())
    for required in _REQUIRED_IMPORTS:
        assert required in imported, (
            f"walker must import {required!r} (B2.8c scope)"
        )


def test_module_does_not_import_os_system_or_popen() -> None:
    src = MODULE_PATH.read_text(encoding="utf-8")
    forbidden = ("o" + "s.system", "o" + "s.popen")
    for marker in forbidden:
        assert marker not in src, (
            f"walker contains forbidden attribute reference: {marker!r}"
        )


def test_module_does_not_invoke_subprocess_attrs() -> None:
    src = MODULE_PATH.read_text(encoding="utf-8")
    forbidden_attrs = (
        "s" + "ubprocess.run",
        "s" + "ubprocess.Popen",
        "s" + "ubprocess.call",
        "s" + "ubprocess.check_call",
        "s" + "ubprocess.check_output",
    )
    for marker in forbidden_attrs:
        assert marker not in src, (
            f"walker contains forbidden attribute reference: {marker!r}"
        )


# ---------------------------------------------------------------------------
# Source-text guards — forbidden shell-out + mutation literals
# ---------------------------------------------------------------------------


def test_module_contains_no_gh_shellout_literal() -> None:
    src = MODULE_PATH.read_text(encoding="utf-8")
    forbidden_literal = "g" + "h " + "pr " + "merge"
    assert forbidden_literal not in src, (
        f"walker contains forbidden shell-out literal: {forbidden_literal!r}"
    )


def test_module_contains_no_git_merge_literal() -> None:
    src = MODULE_PATH.read_text(encoding="utf-8")
    forbidden_literal = "g" + "it " + "merge"
    assert forbidden_literal not in src, (
        f"walker contains forbidden shell-out literal: {forbidden_literal!r}"
    )


def test_module_contains_no_admin_flag_literal() -> None:
    src = MODULE_PATH.read_text(encoding="utf-8")
    forbidden_literal = "--" + "admin"
    assert forbidden_literal not in src, (
        f"walker contains forbidden flag literal: {forbidden_literal!r}"
    )


def test_module_contains_no_no_verify_flag_literal() -> None:
    src = MODULE_PATH.read_text(encoding="utf-8")
    forbidden_literal = "--" + "no-verify"
    assert forbidden_literal not in src, (
        f"walker contains forbidden flag literal: {forbidden_literal!r}"
    )


def test_module_contains_no_force_push_literal() -> None:
    src = MODULE_PATH.read_text(encoding="utf-8")
    forbidden_literal = "p" + "ush --force"
    assert forbidden_literal not in src, (
        f"walker contains forbidden flag literal: {forbidden_literal!r}"
    )


def test_module_contains_no_merge_pr_attribute_literals() -> None:
    src = MODULE_PATH.read_text(encoding="utf-8")
    forbidden_tokens = (
        "p" + "r_merge_approved",
        "m" + "erge" + "Pull" + "Request",
    )
    for marker in forbidden_tokens:
        assert marker not in src, (
            f"walker contains forbidden PR-mutation literal: {marker!r}"
        )


def test_module_reads_no_env_var() -> None:
    """The walker must read no environment variable directly; only
    ``reporting.approval_token_runtime`` (called internally) does."""
    src = MODULE_PATH.read_text(encoding="utf-8")
    forbidden_env_reads = (
        "o" + "s.environ",
        "o" + "s.getenv",
        "g" + "etenv(",
    )
    for marker in forbidden_env_reads:
        assert marker not in src, (
            f"walker reads an environment variable: {marker!r}"
        )


def test_module_does_not_reference_env_var_literal() -> None:
    """The HMAC env-var name lives ONLY in approval_token_runtime."""
    src = MODULE_PATH.read_text(encoding="utf-8")
    assert "ADE_APPROVAL_TOKEN_HMAC_SECRET" not in src


def test_step5_invariants_pinned_in_source() -> None:
    src = MODULE_PATH.read_text(encoding="utf-8")
    assert "step5_implementation_allowed: Final[bool] = False" in src
    assert 'STEP5_ENABLED_SUBSTAGE: Final[str] = "none"' in src


# ---------------------------------------------------------------------------
# Route surface — exactly one POST route at the pinned URL
# ---------------------------------------------------------------------------


def _build_app() -> Flask:
    app = Flask(__name__)
    app.config["TESTING"] = True
    mod.register_merge_execution_dry_run_routes(app)
    return app


def test_route_table_carries_exactly_one_route() -> None:
    table = mod._MERGE_EXECUTION_DRY_RUN_ROUTES
    assert len(table) == 1


def test_route_url_is_pinned_dry_run_path() -> None:
    (path, method, _handler, _endpoint) = mod._MERGE_EXECUTION_DRY_RUN_ROUTES[0]
    assert path == ROUTE_URL
    assert method == "POST"


def test_route_registers_with_post_method_only() -> None:
    app = _build_app()
    matches = [r for r in app.url_map.iter_rules() if r.rule == ROUTE_URL]
    assert len(matches) == 1
    rule = matches[0]
    methods = rule.methods or set()
    assert "POST" in methods
    forbidden = {"GET", "PUT", "PATCH", "DELETE"}
    assert methods.isdisjoint(forbidden)


@pytest.mark.parametrize("method", ["GET", "PUT", "PATCH", "DELETE"])
def test_non_post_methods_return_405(method: str) -> None:
    app = _build_app()
    with app.test_client() as client:
        resp = client.open(ROUTE_URL, method=method)
    assert resp.status_code == 405


# ---------------------------------------------------------------------------
# Envelope shape — 16 closed fields preserved verbatim
# ---------------------------------------------------------------------------


_REQUIRED_ENVELOPE_FIELDS = frozenset(
    {
        "kind",
        "schema_version",
        "module_version",
        "status",
        "stop_condition",
        "preconditions_evaluated",
        "preconditions_passed",
        "would_proceed",
        "pr_number",
        "pr_head_sha",
        "step5_implementation_allowed",
        "step5_enabled_substage",
        "level6_enabled",
        "dry_run_only",
        "live_merge_implemented",
        "deploy_coupled",
    }
)


def _well_formed_body() -> dict[str, Any]:
    return {
        "pr_number": 123,
        "pr_head_sha": "abc1234567890def1234567890abcdef12345678",
        "token": "synthetic-token-shape-for-skeleton-paths",
        "intent": "mobile_approval_dispatch",
        "evidence_hash": "deadbeef" * 8,
    }


def _post_json(client: Any, body: Any) -> Any:
    if body is None:
        return client.post(ROUTE_URL)
    if isinstance(body, str):
        return client.post(ROUTE_URL, data=body, content_type="application/json")
    return client.post(
        ROUTE_URL,
        data=json.dumps(body),
        content_type="application/json",
    )


def _envelope_after(client: Any, body: Any) -> tuple[int, dict[str, Any]]:
    resp = _post_json(client, body)
    return resp.status_code, resp.get_json()


def test_envelope_contains_all_closed_fields_after_body_failure() -> None:
    app = _build_app()
    with app.test_client() as client:
        _code, payload = _envelope_after(client, None)
    missing = _REQUIRED_ENVELOPE_FIELDS - set(payload.keys())
    assert not missing, f"envelope missing required fields: {missing!r}"


def test_envelope_pins_six_discipline_invariants() -> None:
    app = _build_app()
    with app.test_client() as client:
        _code, payload = _envelope_after(client, None)
    assert payload["step5_implementation_allowed"] is False
    assert payload["step5_enabled_substage"] == "none"
    assert payload["level6_enabled"] is False
    assert payload["dry_run_only"] is True
    assert payload["live_merge_implemented"] is False
    assert payload["deploy_coupled"] is False


def test_envelope_module_and_schema_versions_match_constants() -> None:
    app = _build_app()
    with app.test_client() as client:
        _code, payload = _envelope_after(client, None)
    assert payload["module_version"] == mod.MODULE_VERSION
    assert payload["schema_version"] == mod.SCHEMA_VERSION


# ---------------------------------------------------------------------------
# Body-shape failures — rejected + §7 stop_condition mapping; NO preflight write
# ---------------------------------------------------------------------------


def test_missing_body_returns_400_rejected_no_preflight(
    _isolate_state: Path,
) -> None:
    app = _build_app()
    with app.test_client() as client:
        code, payload = _envelope_after(client, None)
    assert code == 400
    assert payload["status"] == "rejected"
    assert payload["stop_condition"] is None
    assert payload["would_proceed"] is False
    assert payload["reason"] == "body_missing"
    assert not _isolate_state.is_file()


def test_non_object_body_returns_400_rejected_no_preflight(
    _isolate_state: Path,
) -> None:
    app = _build_app()
    with app.test_client() as client:
        code, payload = _envelope_after(client, [1, 2, 3])
    assert code == 400
    assert payload["status"] == "rejected"
    assert payload["stop_condition"] is None
    assert payload["reason"] == "body_not_object"
    assert not _isolate_state.is_file()


@pytest.mark.parametrize(
    "drop_field,expected_reason,expected_stop",
    [
        ("token", "field_missing:token", "token_missing"),
        ("pr_number", "field_missing:pr_number", "pr_number_mismatch"),
        ("intent", "field_missing:intent", "binding_mismatch"),
        ("pr_head_sha", "field_missing:pr_head_sha", "binding_mismatch"),
        ("evidence_hash", "field_missing:evidence_hash", "binding_mismatch"),
    ],
)
def test_missing_required_field_emits_rejected_with_closed_stop(
    drop_field: str,
    expected_reason: str,
    expected_stop: str,
    _isolate_state: Path,
) -> None:
    app = _build_app()
    body = _well_formed_body()
    del body[drop_field]
    with app.test_client() as client:
        code, payload = _envelope_after(client, body)
    assert code == 400
    assert payload["status"] == "rejected"
    assert payload["reason"] == expected_reason
    assert payload["stop_condition"] == expected_stop
    assert not _isolate_state.is_file()


def test_intent_drift_in_body_emits_binding_mismatch_no_preflight(
    _isolate_state: Path,
) -> None:
    app = _build_app()
    body = _well_formed_body()
    body["intent"] = "something_else"
    with app.test_client() as client:
        code, payload = _envelope_after(client, body)
    assert code == 400
    assert payload["status"] == "rejected"
    assert payload["reason"] == "field_value:intent_not_pinned"
    assert payload["stop_condition"] == "binding_mismatch"
    assert not _isolate_state.is_file()


def test_oversized_token_emits_token_missing_no_preflight(
    _isolate_state: Path,
) -> None:
    app = _build_app()
    body = _well_formed_body()
    body["token"] = "x" * 5000
    with app.test_client() as client:
        code, payload = _envelope_after(client, body)
    assert code == 400
    assert payload["stop_condition"] == "token_missing"
    assert not _isolate_state.is_file()


def test_zero_pr_number_emits_pr_number_mismatch_no_preflight(
    _isolate_state: Path,
) -> None:
    app = _build_app()
    body = _well_formed_body()
    body["pr_number"] = 0
    with app.test_client() as client:
        code, payload = _envelope_after(client, body)
    assert code == 400
    assert payload["stop_condition"] == "pr_number_mismatch"
    assert not _isolate_state.is_file()


# ---------------------------------------------------------------------------
# Precondition 1 — N4b not configured → configuration_missing; no preflight
# ---------------------------------------------------------------------------


def test_n4b_missing_emits_configuration_missing_no_preflight(
    _isolate_state: Path,
) -> None:
    """Env unset → status=configuration_missing, no preflight write."""
    app = _build_app()
    with app.test_client() as client:
        code, payload = _envelope_after(client, _well_formed_body())
    assert code == 200
    assert payload["status"] == "configuration_missing"
    assert payload["stop_condition"] is None
    assert payload["preconditions_evaluated"] == 1
    assert payload["preconditions_passed"] == 0
    assert payload["reason"] == "n4b_not_activated"
    assert payload["would_proceed"] is False
    assert not _isolate_state.is_file()


# ---------------------------------------------------------------------------
# Precondition 2 — N4c component missing → configuration_missing; no preflight
# ---------------------------------------------------------------------------


def test_n4c_missing_emits_configuration_missing_no_preflight(
    _isolate_state: Path,
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    """When the N4c PWA component file is absent, the walker emits
    ``configuration_missing`` with preconditions_evaluated=2 / passed=1,
    and never writes a preflight artefact."""
    # Activate N4b so we get past precondition 1.
    monkeypatch.setenv(
        atr.ENV_APPROVAL_TOKEN_HMAC_SECRET, _secrets.token_hex(32)
    )
    # Point the N4c path at a non-existent file.
    monkeypatch.setattr(
        mod,
        "_N4C_COMPONENT_PATH",
        tmp_path / "no_such_n4c_component.tsx",
    )
    app = _build_app()
    with app.test_client() as client:
        code, payload = _envelope_after(client, _well_formed_body())
    assert code == 200
    assert payload["status"] == "configuration_missing"
    assert payload["stop_condition"] is None
    assert payload["preconditions_evaluated"] == 2
    assert payload["preconditions_passed"] == 1
    assert payload["reason"] == "n4c_component_missing"
    assert not _isolate_state.is_file()


def test_n4c_component_path_constant_points_at_canonical_location() -> None:
    """The walker's N4c path constant must match the canonical
    location asserted by the B2.8c-pre readiness pin test."""
    assert mod._N4C_COMPONENT_PATH == N4C_COMPONENT_PATH


# ---------------------------------------------------------------------------
# Preconditions 3–7 — token verification + bindings
# ---------------------------------------------------------------------------


def _mint_dry_run_token(
    monkeypatch: pytest.MonkeyPatch,
    *,
    pr_number: int = 123,
    pr_head_sha: str = "abc1234567890def1234567890abcdef12345678",
    evidence_hash: str | None = None,
    event_id: str = "evt_walker_test",
    intent: str = "mobile_approval_dispatch",
) -> str:
    if evidence_hash is None:
        evidence_hash = "deadbeef" * 8
    monkeypatch.setenv(
        atr.ENV_APPROVAL_TOKEN_HMAC_SECRET, _secrets.token_hex(32)
    )
    out = atr.mint_runtime(
        intent=intent,
        event_id=event_id,
        pr_number=pr_number,
        pr_head_sha=pr_head_sha,
        evidence_hash=evidence_hash,
    )
    assert out["status"] == "ok", out
    return out["token"]


def _body_with_token(
    token: str,
    *,
    pr_number: int = 123,
    pr_head_sha: str = "abc1234567890def1234567890abcdef12345678",
    evidence_hash: str | None = None,
    intent: str = "mobile_approval_dispatch",
) -> dict[str, Any]:
    if evidence_hash is None:
        evidence_hash = "deadbeef" * 8
    return {
        "pr_number": pr_number,
        "pr_head_sha": pr_head_sha,
        "token": token,
        "intent": intent,
        "evidence_hash": evidence_hash,
    }


def test_invalid_token_emits_token_invalid_no_preflight(
    _isolate_state: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(
        atr.ENV_APPROVAL_TOKEN_HMAC_SECRET, _secrets.token_hex(32)
    )
    body = _well_formed_body()
    body["token"] = "not.a.valid.token.envelope"
    app = _build_app()
    with app.test_client() as client:
        code, payload = _envelope_after(client, body)
    assert code == 200
    assert payload["status"] == "rejected"
    assert payload["stop_condition"] == "token_invalid"
    assert not _isolate_state.is_file()


def test_pr_number_mismatch_emits_pr_number_mismatch_no_preflight(
    _isolate_state: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    token = _mint_dry_run_token(monkeypatch, pr_number=999)
    body = _body_with_token(token, pr_number=123)
    app = _build_app()
    with app.test_client() as client:
        code, payload = _envelope_after(client, body)
    assert code == 200
    assert payload["status"] == "rejected"
    assert payload["stop_condition"] == "pr_number_mismatch"
    assert not _isolate_state.is_file()


def test_pr_head_sha_mismatch_emits_binding_mismatch_no_preflight(
    _isolate_state: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    token = _mint_dry_run_token(monkeypatch, pr_head_sha="cafebabe" * 5)
    body = _body_with_token(token, pr_head_sha="deadbeef" * 5)
    app = _build_app()
    with app.test_client() as client:
        code, payload = _envelope_after(client, body)
    assert code == 200
    assert payload["status"] == "rejected"
    assert payload["stop_condition"] == "binding_mismatch"
    assert not _isolate_state.is_file()


def test_evidence_hash_mismatch_emits_binding_mismatch_no_preflight(
    _isolate_state: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    token = _mint_dry_run_token(monkeypatch, evidence_hash="h_orig")
    body = _body_with_token(token, evidence_hash="h_drift")
    app = _build_app()
    with app.test_client() as client:
        code, payload = _envelope_after(client, body)
    assert code == 200
    assert payload["status"] == "rejected"
    assert payload["stop_condition"] == "binding_mismatch"
    assert not _isolate_state.is_file()


def test_intent_drift_in_token_emits_binding_mismatch_no_preflight(
    _isolate_state: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Token minted with mobile_review_dispatch but body says
    mobile_approval_dispatch. verify_runtime_for_dry_run rejects
    with reason=intent_drift; walker maps to binding_mismatch."""
    token = _mint_dry_run_token(monkeypatch, intent="mobile_review_dispatch")
    body = _body_with_token(token, intent="mobile_approval_dispatch")
    app = _build_app()
    with app.test_client() as client:
        code, payload = _envelope_after(client, body)
    assert code == 200
    assert payload["status"] == "rejected"
    assert payload["stop_condition"] == "binding_mismatch"
    assert not _isolate_state.is_file()


def test_expired_token_emits_token_invalid_no_preflight(
    _isolate_state: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from datetime import UTC, datetime, timedelta

    from reporting import approval_token_gate as atg

    raw = _secrets.token_hex(32)
    secret_bytes = bytes.fromhex(raw)
    monkeypatch.setenv(atr.ENV_APPROVAL_TOKEN_HMAC_SECRET, raw)
    past = datetime.now(UTC).replace(microsecond=0) - timedelta(
        seconds=2 * atg.DEFAULT_TTL_SECONDS
    )
    token = atg.mint_token(
        intent="mobile_approval_dispatch",
        event_id="evt_expired",
        pr_number=123,
        pr_head_sha="abc1234567890def1234567890abcdef12345678",
        evidence_hash="deadbeef" * 8,
        release_tag=None,
        kid=atr.CURRENT_KID,
        secret=secret_bytes,
        ttl_seconds=atg.DEFAULT_TTL_SECONDS,
        now=past,
    )
    body = _body_with_token(token)
    app = _build_app()
    with app.test_client() as client:
        code, payload = _envelope_after(client, body)
    assert code == 200
    assert payload["status"] == "rejected"
    assert payload["stop_condition"] == "token_invalid"
    assert not _isolate_state.is_file()


def test_replay_detected_on_second_request_no_preflight_on_replay(
    _isolate_state: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """First request: all 7 pass → preflight artefact written →
    not_yet_implemented. Second request with the same token:
    replay_detected → rejected → preflight artefact NOT overwritten
    by the rejected branch (we delete the artefact between the two
    calls to make the negative-assertion strict)."""
    token = _mint_dry_run_token(monkeypatch)
    body = _body_with_token(token)
    app = _build_app()
    with app.test_client() as client:
        code1, payload1 = _envelope_after(client, body)
    assert code1 == 200
    assert payload1["status"] == "not_yet_implemented"
    assert _isolate_state.is_file()
    # Remove the artefact so the second call's negative assertion is
    # strict.
    _isolate_state.unlink()
    with app.test_client() as client:
        code2, payload2 = _envelope_after(client, body)
    assert code2 == 200
    assert payload2["status"] == "rejected"
    assert payload2["stop_condition"] == "replay_detected"
    # The rejected branch must not write a preflight artefact.
    assert not _isolate_state.is_file()


# ---------------------------------------------------------------------------
# Happy walker — all 7 pass; preflight written; not_yet_implemented
# ---------------------------------------------------------------------------


def test_happy_walker_returns_not_yet_implemented_with_preflight_written(
    _isolate_state: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    token = _mint_dry_run_token(monkeypatch)
    body = _body_with_token(token)
    app = _build_app()
    with app.test_client() as client:
        code, payload = _envelope_after(client, body)
    assert code == 200
    assert payload["status"] == "not_yet_implemented"
    assert payload["stop_condition"] is None
    assert payload["would_proceed"] is False
    assert payload["preconditions_evaluated"] == 7
    assert payload["preconditions_passed"] == 7
    assert payload["reason"] == "preconditions_8_through_17_pending"
    assert payload["pr_number"] == 123
    assert payload["pr_head_sha"] == "abc1234567890def1234567890abcdef12345678"
    # Preflight artefact exists with the closed schema.
    assert _isolate_state.is_file()
    snapshot = json.loads(_isolate_state.read_text(encoding="utf-8"))
    assert snapshot["report_kind"] == "n5b_preflight"
    assert snapshot["pr_number"] == 123
    assert snapshot["intent"] == "mobile_approval_dispatch"
    assert snapshot["operator_actor"] == "session"
    # Critical: no raw token, no raw nonce.
    blob = json.dumps(snapshot, default=str)
    assert token not in blob


def test_preflight_artefact_carries_kid_and_nonce_hash_only(
    _isolate_state: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    token = _mint_dry_run_token(monkeypatch)
    body = _body_with_token(token)
    app = _build_app()
    with app.test_client() as client:
        _envelope_after(client, body)
    snapshot = json.loads(_isolate_state.read_text(encoding="utf-8"))
    # kid + nonce_hash present and well-shaped.
    assert snapshot["token_kid"] == atr.CURRENT_KID
    assert isinstance(snapshot["nonce_hash"], str)
    assert len(snapshot["nonce_hash"]) == 64
    assert all(c in "0123456789abcdef" for c in snapshot["nonce_hash"])
    # No raw nonce / token field in the closed schema.
    assert "nonce" not in snapshot
    assert "token" not in snapshot


def test_b2_8c_never_emits_ok_status(
    _isolate_state: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Pin: even on the fully-clean happy path, B2.8c emits
    ``not_yet_implemented`` — never ``ok``. The ``ok`` status is
    reserved for B2.8e when preconditions 8–17 also walk."""
    token = _mint_dry_run_token(monkeypatch)
    body = _body_with_token(token)
    app = _build_app()
    with app.test_client() as client:
        _code, payload = _envelope_after(client, body)
    assert payload["status"] != "ok"
    assert payload["status"] == "not_yet_implemented"


# ---------------------------------------------------------------------------
# Preflight-write failure — rejected + reason=preflight_write_failed
# ---------------------------------------------------------------------------


def test_preflight_write_failure_emits_rejected_500_no_new_stop_condition(
    _isolate_state: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Post-verification write failure: status=rejected, HTTP 500,
    stop_condition=None, reason='preflight_write_failed'. No new
    §7 stop-condition literal is introduced."""
    token = _mint_dry_run_token(monkeypatch)
    body = _body_with_token(token)

    from reporting import n5b_merge_execution_dry_run as projector

    def _boom(**_kwargs: Any) -> Any:
        raise OSError("simulated disk failure")

    monkeypatch.setattr(projector, "write_preflight", _boom)
    app = _build_app()
    with app.test_client() as client:
        code, payload = _envelope_after(client, body)
    assert code == 500
    assert payload["status"] == "rejected"
    assert payload["stop_condition"] is None
    assert payload["reason"] == "preflight_write_failed"
    assert payload["preconditions_evaluated"] == 7
    assert payload["preconditions_passed"] == 7
    # Artefact must not exist (write raised before completing).
    assert not _isolate_state.is_file()


# ---------------------------------------------------------------------------
# UNWIRED contract — blueprint not registered in dashboard.py
# ---------------------------------------------------------------------------


def test_dashboard_py_present_for_unwired_pin() -> None:
    assert DASHBOARD_PY.is_file()


def test_blueprint_not_registered_in_dashboard_py() -> None:
    """B2.8c keeps the walker UNWIRED. The wiring patch into
    ``dashboard/dashboard.py`` is operator-only and reserved for
    B2.8e. Source-text scan of dashboard.py asserts the import +
    register-call are absent."""
    src = DASHBOARD_PY.read_text(encoding="utf-8")
    forbidden_substrings = (
        "from dashboard.api_merge_execution_dry_run",
        "import api_merge_execution_dry_run",
        "register_merge_execution_dry_run_routes",
    )
    hits = [s for s in forbidden_substrings if s in src]
    assert not hits, (
        "B2.8c walker must remain UNWIRED. dashboard.py contains "
        f"wiring substrings: {hits!r}. Wiring is B2.8e scope."
    )


# ---------------------------------------------------------------------------
# Audit redaction — every envelope passes assert_no_secrets
# ---------------------------------------------------------------------------


def test_well_formed_envelope_passes_assert_no_secrets(
    _isolate_state: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from reporting.agent_audit_summary import assert_no_secrets

    token = _mint_dry_run_token(monkeypatch)
    body = _body_with_token(token)
    app = _build_app()
    with app.test_client() as client:
        _code, payload = _envelope_after(client, body)
    assert_no_secrets(payload)


def test_malformed_body_envelope_passes_assert_no_secrets() -> None:
    from reporting.agent_audit_summary import assert_no_secrets

    app = _build_app()
    with app.test_client() as client:
        _code, payload = _envelope_after(client, None)
    assert_no_secrets(payload)


# ---------------------------------------------------------------------------
# Bounded caps — defense-in-depth (unchanged from B2.8b)
# ---------------------------------------------------------------------------


def test_token_size_cap_is_pinned() -> None:
    assert mod._MAX_TOKEN_LEN == 4096


def test_pr_head_sha_size_cap_is_pinned() -> None:
    assert mod._MAX_PR_HEAD_SHA_LEN == 64


def test_intent_size_cap_is_pinned() -> None:
    assert mod._MAX_INTENT_LEN == 64


def test_evidence_hash_size_cap_is_pinned() -> None:
    assert mod._MAX_EVIDENCE_HASH_LEN == 256


def test_reason_size_cap_is_pinned() -> None:
    assert mod._MAX_REASON_LEN == 200


def test_intent_literal_is_pinned() -> None:
    assert mod._INTENT_LITERAL == "mobile_approval_dispatch"


def test_required_body_fields_are_closed_five_set() -> None:
    assert mod._REQUIRED_BODY_FIELDS == (
        "pr_number",
        "pr_head_sha",
        "token",
        "intent",
        "evidence_hash",
    )


def test_discipline_fields_dict_is_closed_six_set() -> None:
    assert set(mod._DISCIPLINE_FIELDS.keys()) == {
        "step5_implementation_allowed",
        "step5_enabled_substage",
        "level6_enabled",
        "dry_run_only",
        "live_merge_implemented",
        "deploy_coupled",
    }
    assert mod._DISCIPLINE_FIELDS["step5_implementation_allowed"] is False
    assert mod._DISCIPLINE_FIELDS["step5_enabled_substage"] == "none"
    assert mod._DISCIPLINE_FIELDS["level6_enabled"] is False
    assert mod._DISCIPLINE_FIELDS["dry_run_only"] is True
    assert mod._DISCIPLINE_FIELDS["live_merge_implemented"] is False
    assert mod._DISCIPLINE_FIELDS["deploy_coupled"] is False


# ---------------------------------------------------------------------------
# Stop-condition vocabulary — closed; no new literals introduced
# ---------------------------------------------------------------------------


def test_only_closed_stop_conditions_appear_in_translation_tables() -> None:
    """The walker's translation tables must emit only §7 stop
    conditions enumerated by the B2.8c implementation plan §6.2."""
    allowed_in_b2_8c = {
        "token_missing",
        "token_invalid",
        "replay_detected",
        "binding_mismatch",
        "pr_number_mismatch",
        None,
    }
    body_stops = set(mod._BODY_REASON_TO_STOP_CONDITION.values()) | {None}
    verify_stops = set(mod._VERIFY_OUTCOME_TO_STOP_CONDITION.values()) | {
        None,
        "pr_number_mismatch",
        "binding_mismatch",
    }
    illegal = (body_stops | verify_stops) - allowed_in_b2_8c
    assert illegal == set(), (
        f"walker emits stop_condition literals outside the B2.8c "
        f"closed §7 vocabulary: {illegal!r}"
    )


def test_module_source_does_not_mention_b2_8d_or_later_stop_conditions() -> None:
    """The closed §7 stop conditions reserved for B2.8d / B2.8e
    must NOT appear as quoted literals in the B2.8c walker source.
    This pins the scope boundary."""
    src = MODULE_PATH.read_text(encoding="utf-8")
    deferred = (
        "head_sha_mismatch",
        "merge_state_not_clean",
        "checks_not_green",
        "branch_protection_not_satisfied",
        "unexpected_files_touched",
        "deploy_coupling_detected",
        "step5_flag_changed",
        "level_6_attempted",
        "protected_path_violation",
        "stale_recommendation",
        "network_uncertain",
        "audit_write_failure",
        "operator_confirmation_missing",
        "live_execute_disabled",
        "dry_run_required_first",
    )
    for literal in deferred:
        assert literal not in src, (
            f"walker source mentions deferred stop_condition literal "
            f"{literal!r}; that scope belongs to B2.8d / B2.8e"
        )
