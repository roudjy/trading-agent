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

    # Re-bind the projector's FAILURE_DIR to tmp_path so the walker
    # writes B2.8d failure artefacts into the test sandbox.
    failure_dir = (
        tmp_path / "logs" / "n5b_merge_execution" / "failure"
    )
    failure_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(projector, "FAILURE_DIR", failure_dir)

    # Re-bind the B2.8e dry-run + history artefact paths to
    # tmp_path so the walker writes both into the test sandbox.
    dry_run_dir = tmp_path / "logs" / "n5b_merge_execution" / "dry_run"
    dry_run_dir.mkdir(parents=True, exist_ok=True)
    dry_run_latest = dry_run_dir / "latest.json"
    dry_run_history = dry_run_dir / "history.jsonl"
    monkeypatch.setattr(projector, "DRY_RUN_LATEST", dry_run_latest)
    monkeypatch.setattr(projector, "DRY_RUN_HISTORY", dry_run_history)

    # Re-bind the walker's three upstream-artefact paths to tmp_path
    # so tests can inject synthetic N5a / A22 / github_pr_lifecycle
    # artefacts to exercise the B2.8d walker.
    for attr, rel in (
        ("_N5A_ARTIFACT_PATH",
         "logs/development_merge_recommendation/latest.json"),
        ("_A22_ARTIFACT_PATH",
         "logs/development_pr_lifecycle_observer/latest.json"),
        ("_GITHUB_PR_LIFECYCLE_ARTIFACT_PATH",
         "logs/github_pr_lifecycle/latest.json"),
    ):
        target = tmp_path / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        monkeypatch.setattr(mod, attr, target)

    monkeypatch.delenv(atr.ENV_APPROVAL_TOKEN_HMAC_SECRET, raising=False)
    yield preflight_target


# ---------------------------------------------------------------------------
# Synthetic upstream-artefact helpers for B2.8d walker exercises
# ---------------------------------------------------------------------------


def _write_synthetic_n5a(
    *,
    pr_number: int,
    head_sha: str,
    action: str = "recommend_human_merge",
    reason: str = "pr_clean_and_no_blocking_inbox",
    inbox_critical_count: int = 0,
    evaluated_at: str | None = None,
) -> None:
    """Write a synthetic N5a artefact at the tmp-redirected path."""
    if evaluated_at is None:
        from datetime import UTC, datetime

        evaluated_at = (
            datetime.now(UTC).replace(microsecond=0).isoformat().replace(
                "+00:00", "Z"
            )
        )
    payload = {
        "rows": [
            {
                "recommendation_id": "rec_synth",
                "pr_number": pr_number,
                "head_sha": head_sha,
                "head_ref": "feature/synth",
                "base_ref": "main",
                "observer_classification": "open",
                "inbox_blocked_count": 0,
                "inbox_critical_count": inbox_critical_count,
                "inbox_needs_review_count": 0,
                "recommendation_action": action,
                "recommendation_reason": reason,
                "evaluated_at": evaluated_at,
            }
        ]
    }
    mod._N5A_ARTIFACT_PATH.write_text(json.dumps(payload), encoding="utf-8")


def _write_synthetic_a22(
    *,
    pr_number: int,
    head_sha: str,
    merge_state_status: str = "CLEAN",
    checks_summary: str = "SUCCESS",
    base_ref: str = "main",
) -> None:
    """Write a synthetic A22 artefact at the tmp-redirected path."""
    payload = {
        "rows": [
            {
                "pr_number": pr_number,
                "title": "synth",
                "head_ref": "feature/synth",
                "head_sha": head_sha,
                "base_ref": base_ref,
                "state": "open",
                "is_draft": False,
                "merge_state_status": merge_state_status,
                "mergeable": True,
                "checks_summary": checks_summary,
                "author_login": "synth-author",
                "is_dependabot": False,
                "observer_classification": "open",
                "url": "https://example/pr",
                "created_at": "2026-05-16T00:00:00Z",
                "updated_at": "2026-05-16T00:00:00Z",
            }
        ]
    }
    mod._A22_ARTIFACT_PATH.write_text(json.dumps(payload), encoding="utf-8")


def _write_synthetic_gh_pr_lifecycle(
    *,
    pr_number: int,
    protected_paths_touched: bool = False,
    no_touch_path_violation: bool = False,
    deploy_coupling_detected: bool = False,
    step5_flag_changed: bool = False,
    level_6_attempted: bool = False,
    branch_protection_satisfied: bool = True,
) -> None:
    """Write a synthetic github_pr_lifecycle artefact at the
    tmp-redirected path. Includes the B2.8d extended optional fields
    that production today does not yet emit — by design, until those
    fields are added upstream the walker fails closed with
    ``network_uncertain``."""
    payload = {
        "prs": [
            {
                "number": pr_number,
                "title": "synth",
                "branch": "feature/synth",
                "base": "main",
                "author": "synth-author",
                "package": "synth",
                "merge_state": "clean",
                "checks_state": "passed",
                "additions": 1,
                "deletions": 0,
                "files_count": 1,
                "protected_paths_touched": protected_paths_touched,
                "no_touch_path_violation": no_touch_path_violation,
                "deploy_coupling_detected": deploy_coupling_detected,
                "step5_flag_changed": step5_flag_changed,
                "level_6_attempted": level_6_attempted,
                "branch_protection_satisfied": branch_protection_satisfied,
                "risk_class": "LOW",
                "risk_reason": "synth",
                "decision": "merge_allowed",
                "reason": "synth",
                "actions_taken": [],
                "url": "https://example/pr",
            }
        ]
    }
    mod._GITHUB_PR_LIFECYCLE_ARTIFACT_PATH.write_text(
        json.dumps(payload), encoding="utf-8"
    )


def _seed_all_clean_upstream_artefacts(
    *,
    pr_number: int = 123,
    head_sha: str = "abc1234567890def1234567890abcdef12345678",
) -> None:
    """Write all three synthetic upstream artefacts in the
    all-pass / all-clean configuration. Used by the happy-walker
    test to drive preconditions 8–17 to success."""
    _write_synthetic_n5a(pr_number=pr_number, head_sha=head_sha)
    _write_synthetic_a22(pr_number=pr_number, head_sha=head_sha)
    _write_synthetic_gh_pr_lifecycle(pr_number=pr_number)


# ---------------------------------------------------------------------------
# Module surface
# ---------------------------------------------------------------------------


def test_module_imports_successfully() -> None:
    assert mod is not None


def test_module_version_is_pinned_string() -> None:
    assert mod.MODULE_VERSION == "v3.15.16.N5b.phase2.implemented"


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
    """First request: all 1–7 pass + all 1–17 pass → preflight
    artefact written → not_yet_implemented. Second request with
    the same token: replay_detected → rejected → preflight
    artefact NOT overwritten by the rejected branch (we delete
    the artefact between the two calls to make the negative
    assertion strict)."""
    token = _mint_dry_run_token(monkeypatch)
    _seed_all_clean_upstream_artefacts()
    body = _body_with_token(token)
    app = _build_app()
    with app.test_client() as client:
        code1, payload1 = _envelope_after(client, body)
    assert code1 == 200
    assert payload1["status"] == "ok"
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


def test_happy_walker_returns_ok_after_all_17_pass(
    _isolate_state: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """B2.8e happy path: all 17 preconditions pass.

    Per the operator-authorised B2.8e flip, the walker returns
    ``ok`` with ``would_proceed=True``,
    ``preconditions_evaluated=17``, ``preconditions_passed=17``.
    The six discipline invariants stay nailed; ``ok`` means
    'dry-run checks passed and audit artefacts written' — NOT
    'merge executed' / 'PR mutated' / 'deploy triggered'."""
    token = _mint_dry_run_token(monkeypatch)
    _seed_all_clean_upstream_artefacts()
    body = _body_with_token(token)
    app = _build_app()
    with app.test_client() as client:
        code, payload = _envelope_after(client, body)
    assert code == 200
    assert payload["status"] == "ok"
    assert payload["stop_condition"] is None
    assert payload["would_proceed"] is True
    assert payload["preconditions_evaluated"] == 17
    assert payload["preconditions_passed"] == 17
    assert payload["pr_number"] == 123
    assert payload["pr_head_sha"] == "abc1234567890def1234567890abcdef12345678"
    # Discipline invariants nailed even on ok.
    assert payload["dry_run_only"] is True
    assert payload["live_merge_implemented"] is False
    assert payload["deploy_coupled"] is False
    assert payload["level6_enabled"] is False
    assert payload["step5_implementation_allowed"] is False
    assert payload["step5_enabled_substage"] == "none"
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
    _seed_all_clean_upstream_artefacts()
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


def test_b2_8e_emits_ok_on_all_17_pass(
    _isolate_state: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """B2.8e flips the B2.8d deferral. On the fully-clean happy
    path (1–17 all pass), the walker emits ``ok`` with
    ``would_proceed=True``. ``ok`` means 'dry-run checks passed
    and audit artefacts written' — NOT live merge authority."""
    token = _mint_dry_run_token(monkeypatch)
    _seed_all_clean_upstream_artefacts()
    body = _body_with_token(token)
    app = _build_app()
    with app.test_client() as client:
        _code, payload = _envelope_after(client, body)
    assert payload["status"] == "ok"
    assert payload["would_proceed"] is True
    # Critical: would_proceed=True is a dry-run verdict; the six
    # discipline invariants on the envelope must stay nailed.
    assert payload["dry_run_only"] is True
    assert payload["live_merge_implemented"] is False
    assert payload["deploy_coupled"] is False


# ---------------------------------------------------------------------------
# Preflight-write failure — rejected + reason=preflight_write_failed
# ---------------------------------------------------------------------------


def test_preflight_write_failure_emits_rejected_500_no_new_stop_condition(
    _isolate_state: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Post-verification preflight-write failure: status=rejected,
    HTTP 500, stop_condition=None,
    reason='preflight_write_failed'. No new §7 stop-condition
    literal is introduced. This boundary is between B2.8c
    verification + B2.8d walker."""
    token = _mint_dry_run_token(monkeypatch)
    # Seed upstream so the walker would otherwise proceed past 1–7.
    _seed_all_clean_upstream_artefacts()
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
    """The B2.8c body / verify translation tables must emit only
    the closed §7 vocabulary subset documented for §6.2 (B2.8c).
    The B2.8d walker for preconditions 8–17 emits additional
    closed §6.3 stops; those are NOT in the body/verify tables and
    are pinned separately."""
    allowed_in_b2_8c_tables = {
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
    illegal = (body_stops | verify_stops) - allowed_in_b2_8c_tables
    assert illegal == set(), (
        f"B2.8c translation tables emit stop_condition literals "
        f"outside the §6.2 closed vocabulary: {illegal!r}"
    )


def test_walker_does_not_mention_b2_8e_or_later_stop_conditions() -> None:
    """B2.8d walker source must NOT mention the §7 stop conditions
    reserved for B2.8e and later phases. The B2.8d-permitted §6.3
    vocabulary is documented in
    ``reporting.n5b_merge_execution_dry_run.B2_8D_STOP_CONDITIONS``."""
    src = MODULE_PATH.read_text(encoding="utf-8")
    deferred = (
        # §7 stops reserved for Phase 3+ / live execute paths.
        "operator_confirmation_missing",
        "live_execute_disabled",
        "dry_run_required_first",
    )
    for literal in deferred:
        assert literal not in src, (
            f"B2.8d walker source mentions deferred stop_condition literal "
            f"{literal!r}; that scope belongs to B2.8e or later phases"
        )


# ---------------------------------------------------------------------------
# B2.8d walker — preconditions 8–17
# ---------------------------------------------------------------------------


def _failure_files(_isolate_state: Path) -> list[Path]:
    """Return any failure artefacts written under the tmp failure
    dir. The fixture redirected projector.FAILURE_DIR to
    tmp_path/.../failure."""
    failure_dir = _isolate_state.parent.parent / "failure"
    if not failure_dir.is_dir():
        return []
    return sorted(failure_dir.glob("*.json"))


def _exercise_walker(
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[int, dict[str, Any]]:
    """Mint a valid token + run the walker against the currently
    seeded upstream artefacts. Returns ``(status_code, payload)``."""
    token = _mint_dry_run_token(monkeypatch)
    body = _body_with_token(token)
    app = _build_app()
    with app.test_client() as client:
        return _envelope_after(client, body)


def test_walker_8_17_n5a_artifact_absent_emits_network_uncertain(
    _isolate_state: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """N5a artefact missing → status=rejected,
    stop_condition=network_uncertain. Preflight is written (after
    1–7 pass), but the walker fails on the FIRST upstream read.
    A failure artefact is written; no dry_run/latest.json."""
    # Seed A22 + gh_pr_lifecycle, but NOT N5a.
    _write_synthetic_a22(
        pr_number=123,
        head_sha="abc1234567890def1234567890abcdef12345678",
    )
    _write_synthetic_gh_pr_lifecycle(pr_number=123)
    code, payload = _exercise_walker(monkeypatch)
    assert code == 200
    assert payload["status"] == "rejected"
    assert payload["stop_condition"] == "network_uncertain"
    assert payload["preconditions_evaluated"] == 7
    # Preflight was written (after 1–7).
    assert _isolate_state.is_file()
    # One failure artefact written.
    files = _failure_files(_isolate_state)
    assert len(files) == 1
    snapshot = json.loads(files[0].read_text(encoding="utf-8"))
    assert snapshot["report_kind"] == "n5b_failure"
    assert snapshot["stop_condition"] == "network_uncertain"


def test_walker_8_17_a22_artifact_absent_emits_network_uncertain(
    _isolate_state: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _write_synthetic_n5a(
        pr_number=123,
        head_sha="abc1234567890def1234567890abcdef12345678",
    )
    _write_synthetic_gh_pr_lifecycle(pr_number=123)
    code, payload = _exercise_walker(monkeypatch)
    assert code == 200
    assert payload["status"] == "rejected"
    assert payload["stop_condition"] == "network_uncertain"
    assert len(_failure_files(_isolate_state)) == 1


def test_walker_8_17_gh_artifact_absent_emits_network_uncertain(
    _isolate_state: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _write_synthetic_n5a(
        pr_number=123,
        head_sha="abc1234567890def1234567890abcdef12345678",
    )
    _write_synthetic_a22(
        pr_number=123,
        head_sha="abc1234567890def1234567890abcdef12345678",
    )
    code, payload = _exercise_walker(monkeypatch)
    assert code == 200
    assert payload["status"] == "rejected"
    assert payload["stop_condition"] == "network_uncertain"


def test_walker_8_17_n5a_no_matching_row_emits_network_uncertain(
    _isolate_state: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _write_synthetic_n5a(
        pr_number=999,  # different PR
        head_sha="abc1234567890def1234567890abcdef12345678",
    )
    _write_synthetic_a22(
        pr_number=123,
        head_sha="abc1234567890def1234567890abcdef12345678",
    )
    _write_synthetic_gh_pr_lifecycle(pr_number=123)
    code, payload = _exercise_walker(monkeypatch)
    assert code == 200
    assert payload["status"] == "rejected"
    assert payload["stop_condition"] == "network_uncertain"


def test_walker_8_n5a_action_not_eligible_emits_stale_recommendation(
    _isolate_state: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _seed_all_clean_upstream_artefacts()
    # Override N5a with non-eligible action.
    _write_synthetic_n5a(
        pr_number=123,
        head_sha="abc1234567890def1234567890abcdef12345678",
        action="recommend_hold",
    )
    code, payload = _exercise_walker(monkeypatch)
    assert code == 200
    assert payload["status"] == "rejected"
    assert payload["stop_condition"] == "stale_recommendation"
    assert payload["preconditions_evaluated"] == 8


def test_walker_8_n5a_reason_not_eligible_emits_stale_recommendation(
    _isolate_state: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _seed_all_clean_upstream_artefacts()
    _write_synthetic_n5a(
        pr_number=123,
        head_sha="abc1234567890def1234567890abcdef12345678",
        reason="pr_clean_but_inbox_has_critical_attention",
    )
    code, payload = _exercise_walker(monkeypatch)
    assert payload["stop_condition"] == "stale_recommendation"
    assert payload["preconditions_evaluated"] == 8


@pytest.mark.parametrize(
    "merge_state",
    ["DIRTY", "BLOCKED", "BEHIND", "UNSTABLE", "HAS_HOOKS", "UNKNOWN"],
)
def test_walker_9_non_clean_merge_state_emits_merge_state_not_clean(
    _isolate_state: Path,
    monkeypatch: pytest.MonkeyPatch,
    merge_state: str,
) -> None:
    """Per §6.3: adapter accepts ONLY ``CLEAN`` for mergeStateStatus."""
    _seed_all_clean_upstream_artefacts()
    _write_synthetic_a22(
        pr_number=123,
        head_sha="abc1234567890def1234567890abcdef12345678",
        merge_state_status=merge_state,
    )
    code, payload = _exercise_walker(monkeypatch)
    assert payload["status"] == "rejected"
    assert payload["stop_condition"] == "merge_state_not_clean"
    assert payload["preconditions_evaluated"] == 9


def test_walker_9_clean_merge_state_accepted(
    _isolate_state: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Per §6.3: ``CLEAN`` is the only accepted mergeStateStatus.
    Companion to the negative parametrization above. B2.8e emits
    ``ok`` on the all-clean happy path."""
    _seed_all_clean_upstream_artefacts()
    code, payload = _exercise_walker(monkeypatch)
    assert payload["status"] == "ok"
    assert payload["preconditions_passed"] == 17


def test_walker_9_branch_protection_unsatisfied_emits_stop(
    _isolate_state: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _seed_all_clean_upstream_artefacts()
    _write_synthetic_gh_pr_lifecycle(
        pr_number=123,
        branch_protection_satisfied=False,
    )
    code, payload = _exercise_walker(monkeypatch)
    assert payload["status"] == "rejected"
    assert payload["stop_condition"] == "branch_protection_not_satisfied"
    assert payload["preconditions_evaluated"] == 9


@pytest.mark.parametrize(
    "checks_state",
    ["FAILURE", "CANCELLED", "SKIPPED", "IN_PROGRESS", "NULL"],
)
def test_walker_10_non_success_checks_emit_checks_not_green(
    _isolate_state: Path,
    monkeypatch: pytest.MonkeyPatch,
    checks_state: str,
) -> None:
    """Per §6.3: adapter accepts only success-equivalents for required checks."""
    _seed_all_clean_upstream_artefacts()
    _write_synthetic_a22(
        pr_number=123,
        head_sha="abc1234567890def1234567890abcdef12345678",
        checks_summary=checks_state,
    )
    code, payload = _exercise_walker(monkeypatch)
    assert payload["status"] == "rejected"
    assert payload["stop_condition"] == "checks_not_green"
    assert payload["preconditions_evaluated"] == 10


def test_walker_11_head_sha_mismatch_emits_head_sha_mismatch(
    _isolate_state: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A22 head_sha differs from token-bound head_sha → head_sha_mismatch."""
    _seed_all_clean_upstream_artefacts()
    _write_synthetic_a22(
        pr_number=123,
        head_sha="cafe" * 10,  # different SHA
    )
    code, payload = _exercise_walker(monkeypatch)
    assert payload["status"] == "rejected"
    assert payload["stop_condition"] == "head_sha_mismatch"
    assert payload["preconditions_evaluated"] == 11


def test_walker_12_base_ref_not_main_emits_merge_state_not_clean(
    _isolate_state: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """base_ref != main → operator-approved semantic stretch:
    merge_state_not_clean."""
    _seed_all_clean_upstream_artefacts()
    _write_synthetic_a22(
        pr_number=123,
        head_sha="abc1234567890def1234567890abcdef12345678",
        base_ref="develop",
    )
    code, payload = _exercise_walker(monkeypatch)
    assert payload["status"] == "rejected"
    assert payload["stop_condition"] == "merge_state_not_clean"
    assert payload["preconditions_evaluated"] == 12


def test_walker_13_stale_n5a_emits_stale_recommendation(
    _isolate_state: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """N5a evaluated_at older than 60 minutes → stale_recommendation."""
    from datetime import UTC, datetime, timedelta

    old = (datetime.now(UTC) - timedelta(hours=2)).replace(
        microsecond=0
    ).isoformat().replace("+00:00", "Z")
    _seed_all_clean_upstream_artefacts()
    _write_synthetic_n5a(
        pr_number=123,
        head_sha="abc1234567890def1234567890abcdef12345678",
        evaluated_at=old,
    )
    code, payload = _exercise_walker(monkeypatch)
    assert payload["status"] == "rejected"
    assert payload["stop_condition"] == "stale_recommendation"
    assert payload["preconditions_evaluated"] == 13


def test_walker_14_inbox_criticals_emits_stale_recommendation(
    _isolate_state: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """N5a inbox_critical_count > 0 (with N5a still saying merge) →
    operator-approved semantic stretch: stale_recommendation."""
    _seed_all_clean_upstream_artefacts()
    _write_synthetic_n5a(
        pr_number=123,
        head_sha="abc1234567890def1234567890abcdef12345678",
        inbox_critical_count=2,
    )
    code, payload = _exercise_walker(monkeypatch)
    assert payload["status"] == "rejected"
    assert payload["stop_condition"] == "stale_recommendation"
    assert payload["preconditions_evaluated"] == 14


def test_walker_15_protected_paths_emits_unexpected_files_touched(
    _isolate_state: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _seed_all_clean_upstream_artefacts()
    _write_synthetic_gh_pr_lifecycle(
        pr_number=123,
        protected_paths_touched=True,
    )
    code, payload = _exercise_walker(monkeypatch)
    assert payload["status"] == "rejected"
    assert payload["stop_condition"] == "unexpected_files_touched"
    assert payload["preconditions_evaluated"] == 15


def test_walker_15_no_touch_violation_emits_protected_path_violation(
    _isolate_state: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _seed_all_clean_upstream_artefacts()
    _write_synthetic_gh_pr_lifecycle(
        pr_number=123,
        no_touch_path_violation=True,
    )
    code, payload = _exercise_walker(monkeypatch)
    assert payload["status"] == "rejected"
    assert payload["stop_condition"] == "protected_path_violation"
    assert payload["preconditions_evaluated"] == 15


def test_walker_15_deploy_coupling_emits_deploy_coupling_detected(
    _isolate_state: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _seed_all_clean_upstream_artefacts()
    _write_synthetic_gh_pr_lifecycle(
        pr_number=123,
        deploy_coupling_detected=True,
    )
    code, payload = _exercise_walker(monkeypatch)
    assert payload["status"] == "rejected"
    assert payload["stop_condition"] == "deploy_coupling_detected"
    assert payload["preconditions_evaluated"] == 15


def test_walker_16_step5_change_emits_step5_flag_changed(
    _isolate_state: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _seed_all_clean_upstream_artefacts()
    _write_synthetic_gh_pr_lifecycle(
        pr_number=123,
        step5_flag_changed=True,
    )
    code, payload = _exercise_walker(monkeypatch)
    assert payload["status"] == "rejected"
    assert payload["stop_condition"] == "step5_flag_changed"
    assert payload["preconditions_evaluated"] == 16


def test_walker_16_level_6_attempt_emits_level_6_attempted(
    _isolate_state: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _seed_all_clean_upstream_artefacts()
    _write_synthetic_gh_pr_lifecycle(
        pr_number=123,
        level_6_attempted=True,
    )
    code, payload = _exercise_walker(monkeypatch)
    assert payload["status"] == "rejected"
    assert payload["stop_condition"] == "level_6_attempted"
    assert payload["preconditions_evaluated"] == 16


def test_walker_8_17_missing_optional_field_fails_closed_network_uncertain(
    _isolate_state: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Critical operator-mandated pin: missing optional B2.8d
    extended field (no silent auto-pass). When gh_pr_lifecycle row
    lacks ``step5_flag_changed`` (and other B2.8d fields), walker
    rejects with network_uncertain. This is what makes B2.8d
    safe in production today, where these fields don't exist yet."""
    _write_synthetic_n5a(
        pr_number=123,
        head_sha="abc1234567890def1234567890abcdef12345678",
    )
    _write_synthetic_a22(
        pr_number=123,
        head_sha="abc1234567890def1234567890abcdef12345678",
    )
    # gh_pr_lifecycle row without the B2.8d extended fields (mimics
    # current production state).
    bare_payload = {
        "prs": [
            {
                "number": 123,
                "title": "synth",
                "branch": "feature/synth",
                "base": "main",
                "author": "synth-author",
                "package": "synth",
                "merge_state": "clean",
                "checks_state": "passed",
                "additions": 1,
                "deletions": 0,
                "files_count": 1,
                # NO protected_paths_touched, NO step5_flag_changed, etc.
                "risk_class": "LOW",
                "risk_reason": "synth",
                "decision": "merge_allowed",
                "reason": "synth",
                "actions_taken": [],
                "url": "https://example/pr",
            }
        ]
    }
    mod._GITHUB_PR_LIFECYCLE_ARTIFACT_PATH.write_text(
        json.dumps(bare_payload), encoding="utf-8"
    )
    code, payload = _exercise_walker(monkeypatch)
    assert payload["status"] == "rejected"
    assert payload["stop_condition"] == "network_uncertain"
    # The walker rejects on the FIRST missing optional field.
    # ``branch_protection_satisfied`` is checked inside precondition
    # 9 (mergeStateStatus + branch protection block), so the walker
    # stops at preconditions_evaluated=9 before even reaching the
    # precondition-15 protected-paths fields.
    assert payload["preconditions_evaluated"] == 9


def test_walker_8_17_failure_write_failure_emits_audit_write_failure(
    _isolate_state: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When the failure-artefact write itself raises, the walker
    emits ``audit_write_failure``, HTTP 500."""
    _seed_all_clean_upstream_artefacts()
    # Force a §7 stop in the walker (use stale_recommendation via
    # non-eligible action).
    _write_synthetic_n5a(
        pr_number=123,
        head_sha="abc1234567890def1234567890abcdef12345678",
        action="recommend_hold",
    )
    from reporting import n5b_merge_execution_dry_run as projector

    def _boom(**_kwargs: Any) -> Any:
        raise OSError("simulated failure-artefact disk failure")

    monkeypatch.setattr(projector, "write_failure", _boom)
    code, payload = _exercise_walker(monkeypatch)
    assert code == 500
    assert payload["status"] == "rejected"
    assert payload["stop_condition"] == "audit_write_failure"
    assert payload["reason"] == "failure_artefact_write_failed"


def test_walker_writes_dry_run_latest_and_history_on_all_pass(
    _isolate_state: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """B2.8e MUST write both ``dry_run/latest.json`` and
    ``dry_run/history.jsonl`` on the ok-decision path."""
    from reporting import n5b_merge_execution_dry_run as projector

    _seed_all_clean_upstream_artefacts()
    code, payload = _exercise_walker(monkeypatch)
    assert payload["status"] == "ok"
    assert projector.DRY_RUN_LATEST.is_file()
    assert projector.DRY_RUN_HISTORY.is_file()
    latest = json.loads(projector.DRY_RUN_LATEST.read_text(encoding="utf-8"))
    assert latest["report_kind"] == "n5b_dry_run"
    assert latest["would_proceed"] is True
    assert latest["stop_condition"] is None
    # Discipline invariants nailed on the dry_run artefact.
    assert latest["dry_run_only"] is True
    assert latest["live_merge_implemented"] is False
    assert latest["deploy_coupled"] is False
    # Granularity sentinels present.
    assert latest["required_checks_granularity"] == "rollup_only"
    assert latest["protected_path_granularity"] == "boolean_only"
    # History contains exactly one line.
    history_lines = [
        line
        for line in projector.DRY_RUN_HISTORY.read_text(encoding="utf-8").splitlines()
        if line
    ]
    assert len(history_lines) == 1
    row = json.loads(history_lines[0])
    assert row["report_kind"] == "n5b_dry_run"
    assert row["would_proceed"] is True


def test_walker_failure_artefact_carries_closed_schema(
    _isolate_state: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Verify the failure artefact closed schema includes pinned
    fields and excludes raw token / nonce."""
    from reporting import n5b_merge_execution_dry_run as projector

    _seed_all_clean_upstream_artefacts()
    _write_synthetic_a22(
        pr_number=123,
        head_sha="abc1234567890def1234567890abcdef12345678",
        merge_state_status="BLOCKED",
    )
    token = _mint_dry_run_token(monkeypatch)
    body = _body_with_token(token)
    app = _build_app()
    with app.test_client() as client:
        _envelope_after(client, body)
    files = _failure_files(_isolate_state)
    assert len(files) == 1
    snapshot = json.loads(files[0].read_text(encoding="utf-8"))
    assert set(snapshot.keys()) == set(projector.FAILURE_SNAPSHOT_KEYS)
    assert snapshot["stop_condition"] == "merge_state_not_clean"
    assert snapshot["report_kind"] == "n5b_failure"
    # No raw token / nonce / secret in failure artefact.
    blob = json.dumps(snapshot, default=str)
    assert token not in blob


# ---------------------------------------------------------------------------
# B2.8d source-text guards
# ---------------------------------------------------------------------------


def test_walker_does_not_import_github_pr_lifecycle_module() -> None:
    """The github_pr_lifecycle module legitimately uses subprocess
    to call ``gh``. The walker reads its on-disk artefact instead
    and MUST NOT import it directly."""
    imported = set(_module_imports())
    forbidden = (
        "reporting.github_pr_lifecycle",
    )
    for name in forbidden:
        assert name not in imported, (
            f"walker imports {name!r}; it must read its on-disk "
            "artefact instead"
        )


def test_walker_emits_only_closed_b2_8d_stop_vocab() -> None:
    """Every literal the B2.8d walker passes to ``write_failure`` or
    sets on the envelope's ``stop_condition`` field must come from
    ``projector.B2_8D_STOP_CONDITIONS``. Source-text scan finds
    the literals used in the walker and asserts none are outside
    the closed list (modulo the deferred literals pinned above)."""
    from reporting import n5b_merge_execution_dry_run as projector

    src = MODULE_PATH.read_text(encoding="utf-8")
    # Closed list of §6.3 stops B2.8d may emit.
    closed = set(projector.B2_8D_STOP_CONDITIONS)
    # Any literal the walker quotes that LOOKS like a stop must be
    # in the closed list. We scan only inside the walker body for
    # quoted strings that map to §7 vocabulary.
    candidates = [
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
    ]
    for literal in candidates:
        if f'"{literal}"' in src:
            assert literal in closed, (
                f"walker source uses stop_condition literal "
                f"{literal!r} but it's outside the closed "
                f"B2.8d vocabulary {sorted(closed)!r}"
            )


# ---------------------------------------------------------------------------
# B2.8e — integration tests against the mocked-upstream fixture
# (§6.4: happy path produces ok + dry-run artefact;
# every §7 stop produces a failure artefact + dry_run artefact)
# ---------------------------------------------------------------------------


def _dry_run_history_lines() -> list[str]:
    from reporting import n5b_merge_execution_dry_run as projector

    if not projector.DRY_RUN_HISTORY.is_file():
        return []
    return [
        line
        for line in projector.DRY_RUN_HISTORY.read_text(encoding="utf-8").splitlines()
        if line
    ]


def test_b2_8e_happy_path_writes_preflight_dry_run_history_no_failure(
    _isolate_state: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """End-to-end: ok envelope + preflight + dry_run/latest +
    history.jsonl; no failure artefact."""
    from reporting import n5b_merge_execution_dry_run as projector

    _seed_all_clean_upstream_artefacts()
    code, payload = _exercise_walker(monkeypatch)
    assert payload["status"] == "ok"
    assert _isolate_state.is_file()  # preflight
    assert projector.DRY_RUN_LATEST.is_file()
    assert projector.DRY_RUN_HISTORY.is_file()
    # No failure artefact on the happy path.
    assert _failure_files(_isolate_state) == []
    # History row matches latest.
    latest = json.loads(projector.DRY_RUN_LATEST.read_text(encoding="utf-8"))
    history_rows = [json.loads(line) for line in _dry_run_history_lines()]
    assert len(history_rows) == 1
    assert history_rows[0]["report_kind"] == latest["report_kind"]
    assert history_rows[0]["would_proceed"] is True


@pytest.mark.parametrize(
    "fixture_setup,expected_stop",
    [
        (
            "n5a_not_eligible",
            "stale_recommendation",
        ),
        (
            "merge_state_blocked",
            "merge_state_not_clean",
        ),
        (
            "checks_failure",
            "checks_not_green",
        ),
        (
            "head_sha_drift",
            "head_sha_mismatch",
        ),
        (
            "protected_paths",
            "unexpected_files_touched",
        ),
        (
            "step5_change",
            "step5_flag_changed",
        ),
        (
            "level_6_attempt",
            "level_6_attempted",
        ),
    ],
)
def test_b2_8e_each_stop_writes_failure_and_dry_run_artefacts(
    _isolate_state: Path,
    monkeypatch: pytest.MonkeyPatch,
    fixture_setup: str,
    expected_stop: str,
) -> None:
    """For each §7 stop in B2.8d scope, the walker writes BOTH the
    failure artefact (B2.8d behaviour preserved) AND the
    dry_run/latest + history artefacts (B2.8e additions)."""
    from reporting import n5b_merge_execution_dry_run as projector

    _seed_all_clean_upstream_artefacts()
    if fixture_setup == "n5a_not_eligible":
        _write_synthetic_n5a(
            pr_number=123,
            head_sha="abc1234567890def1234567890abcdef12345678",
            action="recommend_hold",
        )
    elif fixture_setup == "merge_state_blocked":
        _write_synthetic_a22(
            pr_number=123,
            head_sha="abc1234567890def1234567890abcdef12345678",
            merge_state_status="BLOCKED",
        )
    elif fixture_setup == "checks_failure":
        _write_synthetic_a22(
            pr_number=123,
            head_sha="abc1234567890def1234567890abcdef12345678",
            checks_summary="FAILURE",
        )
    elif fixture_setup == "head_sha_drift":
        _write_synthetic_a22(
            pr_number=123,
            head_sha="cafe" * 10,
        )
    elif fixture_setup == "protected_paths":
        _write_synthetic_gh_pr_lifecycle(
            pr_number=123,
            protected_paths_touched=True,
        )
    elif fixture_setup == "step5_change":
        _write_synthetic_gh_pr_lifecycle(
            pr_number=123,
            step5_flag_changed=True,
        )
    elif fixture_setup == "level_6_attempt":
        _write_synthetic_gh_pr_lifecycle(
            pr_number=123,
            level_6_attempted=True,
        )
    code, payload = _exercise_walker(monkeypatch)
    assert payload["status"] == "rejected"
    assert payload["stop_condition"] == expected_stop
    # Failure artefact (B2.8d).
    failures = _failure_files(_isolate_state)
    assert len(failures) == 1
    # Dry_run/latest.json (B2.8e).
    assert projector.DRY_RUN_LATEST.is_file()
    latest = json.loads(projector.DRY_RUN_LATEST.read_text(encoding="utf-8"))
    assert latest["report_kind"] == "n5b_dry_run"
    assert latest["would_proceed"] is False
    assert latest["stop_condition"] == expected_stop
    # History appended.
    assert len(_dry_run_history_lines()) == 1


def test_b2_8e_dry_run_artefact_carries_preconditions_dict(
    _isolate_state: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """§6.2: the dry_run artefact must carry the preconditions
    boolean dict with exactly 17 keys."""
    from reporting import n5b_merge_execution_dry_run as projector

    _seed_all_clean_upstream_artefacts()
    _exercise_walker(monkeypatch)
    latest = json.loads(projector.DRY_RUN_LATEST.read_text(encoding="utf-8"))
    preconditions = latest["preconditions"]
    assert isinstance(preconditions, dict)
    assert len(preconditions) == 17
    assert all(
        f"precondition_{i}" in preconditions for i in range(1, 18)
    )
    # All 17 True on the happy path.
    assert all(preconditions.values())


def test_b2_8e_dry_run_artefact_carries_seen_upstream_fields(
    _isolate_state: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from reporting import n5b_merge_execution_dry_run as projector

    _seed_all_clean_upstream_artefacts()
    _exercise_walker(monkeypatch)
    latest = json.loads(projector.DRY_RUN_LATEST.read_text(encoding="utf-8"))
    assert latest["recommendation_action_seen"] == "recommend_human_merge"
    assert latest["recommendation_reason_seen"] == "pr_clean_and_no_blocking_inbox"
    assert latest["merge_state_status_seen"] == "CLEAN"
    assert latest["required_checks_summary"] == {"_rollup": "SUCCESS"}


def test_b2_8e_dry_run_artefact_granularity_sentinels_explicit(
    _isolate_state: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Operator-mandated B2.8e contract: the dry_run artefact MUST
    explicitly carry ``required_checks_granularity="rollup_only"``
    and ``protected_path_granularity="boolean_only"`` so the
    operator-facing surface never silently implies per-check or
    per-file granularity exists."""
    from reporting import n5b_merge_execution_dry_run as projector

    _seed_all_clean_upstream_artefacts()
    _exercise_walker(monkeypatch)
    latest = json.loads(projector.DRY_RUN_LATEST.read_text(encoding="utf-8"))
    assert latest["required_checks_granularity"] == "rollup_only"
    assert latest["protected_path_granularity"] == "boolean_only"
    assert latest["protected_path_violations"] == []


def test_b2_8e_dry_run_artefact_carries_no_raw_token_or_nonce(
    _isolate_state: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Critical B2.8e safety pin: the dry_run artefact carries
    ``token_kid`` + ``nonce_hash`` only — never the raw token,
    never the raw nonce."""
    from reporting import n5b_merge_execution_dry_run as projector

    token = _mint_dry_run_token(monkeypatch)
    _seed_all_clean_upstream_artefacts()
    body = _body_with_token(token)
    app = _build_app()
    with app.test_client() as client:
        _envelope_after(client, body)
    latest = json.loads(projector.DRY_RUN_LATEST.read_text(encoding="utf-8"))
    blob = json.dumps(latest, default=str)
    assert token not in blob
    assert "nonce" not in set(latest.keys())
    assert "token" not in set(latest.keys())
    assert latest["token_kid"] == atr.CURRENT_KID
    assert isinstance(latest["nonce_hash"], str)
    assert len(latest["nonce_hash"]) == 64


# ---------------------------------------------------------------------------
# B2.8e — audit-redaction integration tests (§6.4)
# ---------------------------------------------------------------------------


def test_b2_8e_audit_redaction_aborts_dry_run_write_on_credential_shape(
    _isolate_state: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """§6.4: a tampered payload that trips the redactor at
    ``write_dry_run_latest`` time aborts the write. The walker
    emits ``audit_write_failure`` and no dry_run artefact is
    persisted.

    The B2.8c preflight-write-failure path uses
    ``stop_condition=None, reason="preflight_write_failed"`` by
    pre-B2.8e design; this test specifically targets the
    ``write_dry_run_latest`` writer to exercise the B2.8e §7
    audit_write_failure path."""
    from reporting import n5b_merge_execution_dry_run as projector

    _seed_all_clean_upstream_artefacts()

    def _boom(**_kwargs: Any) -> Any:
        raise AssertionError("simulated credential leak in dry_run snapshot")

    monkeypatch.setattr(projector, "write_dry_run_latest", _boom)
    code, payload = _exercise_walker(monkeypatch)
    # Walker rejected by the redaction guard.
    assert code == 500
    assert payload["status"] == "rejected"
    assert payload["stop_condition"] == "audit_write_failure"
    # No dry_run/latest.json or history.jsonl created (write aborted
    # before persistence).
    assert not projector.DRY_RUN_LATEST.is_file()
    assert not projector.DRY_RUN_HISTORY.is_file()


def test_b2_8e_audit_redaction_via_real_credential_pattern_in_seen_field(
    _isolate_state: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """End-to-end §6.4 redaction: inject a real
    credential-shaped string into the N5a row's recommendation_reason
    field. The walker reads it, passes it to the dry_run snapshot
    builder which then runs assert_no_secrets — which raises on
    the credential pattern. The walker translates to
    audit_write_failure."""
    from reporting import n5b_merge_execution_dry_run as projector

    # Seed N5a with a credential-shaped recommendation_reason. The
    # ``recommendation_reason`` value would normally be a closed
    # N5a vocab string; here we inject a github_pat_-shaped value.
    head_sha = "abc1234567890def1234567890abcdef12345678"
    # Build the marker at runtime so this test source itself is
    # inert to gitleaks-style scanners.
    pat_prefix = "g" + "i" + "thub_pat_"
    tampered_reason = pat_prefix + ("A" * 50)
    _write_synthetic_n5a(
        pr_number=123,
        head_sha=head_sha,
        reason=tampered_reason,
    )
    _write_synthetic_a22(pr_number=123, head_sha=head_sha)
    _write_synthetic_gh_pr_lifecycle(pr_number=123)

    token = _mint_dry_run_token(monkeypatch, pr_number=123, pr_head_sha=head_sha)
    body = _body_with_token(token, pr_number=123, pr_head_sha=head_sha)
    app = _build_app()
    with app.test_client() as client:
        code, payload = _envelope_after(client, body)
    # The walker reaches the §6.2 N5a-reason mismatch check FIRST
    # (precondition 8) and rejects with stale_recommendation
    # because the tampered reason != _N5A_ELIGIBLE_REASON. The
    # rejected branch then tries to write the failure artefact,
    # which runs assert_no_secrets — that AssertionError surfaces
    # as audit_write_failure.
    #
    # Either outcome is acceptable for this test: the credential
    # never reaches a persisted artefact.
    assert payload["status"] == "rejected"
    assert payload["stop_condition"] in {"stale_recommendation", "audit_write_failure"}
    # No on-disk artefact contains the tampered credential pattern.
    for path in (
        _isolate_state,
        projector.DRY_RUN_LATEST,
        projector.DRY_RUN_HISTORY,
    ):
        if path.is_file():
            text = path.read_text(encoding="utf-8")
            assert tampered_reason not in text, (
                f"tampered credential pattern leaked into {path}"
            )
    for failure in _failure_files(_isolate_state):
        text = failure.read_text(encoding="utf-8")
        assert tampered_reason not in text


def test_b2_8e_history_append_failure_emits_audit_write_failure(
    _isolate_state: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """If history.jsonl append raises mid-write, the walker emits
    audit_write_failure. No new stop_condition literal introduced."""
    from reporting import n5b_merge_execution_dry_run as projector

    _seed_all_clean_upstream_artefacts()

    real_append = projector.append_dry_run_history

    def _boom(**_kwargs: Any) -> Any:
        raise OSError("simulated history disk failure")

    monkeypatch.setattr(projector, "append_dry_run_history", _boom)
    code, payload = _exercise_walker(monkeypatch)
    assert code == 500
    assert payload["status"] == "rejected"
    assert payload["stop_condition"] == "audit_write_failure"
    # Restore (defense-in-depth for this test session).
    monkeypatch.setattr(projector, "append_dry_run_history", real_append)


# ---------------------------------------------------------------------------
# B2.8e — would_proceed semantic pins
# ---------------------------------------------------------------------------


def test_b2_8e_would_proceed_true_always_co_occurs_with_dry_run_invariants(
    _isolate_state: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """**Operator-mandated semantic pin**:
    ``would_proceed=true`` is a dry-run-only proceed signal. It
    MUST NOT be readable as merge-proceed / live-merge / deploy
    authority. The pin asserts that whenever ``would_proceed=true``
    appears in the response envelope, **every** discipline
    invariant that nails the dry-run posture also holds:

    * ``dry_run_only=True``
    * ``live_merge_implemented=False``
    * ``deploy_coupled=False``
    * ``level6_enabled=False``
    * ``step5_implementation_allowed=False``
    * ``step5_enabled_substage="none"``

    Same pin applies to the persisted ``dry_run/latest.json``
    snapshot — the artefact carries the same six invariants and
    NEVER ships ``would_proceed=true`` without them."""
    from reporting import n5b_merge_execution_dry_run as projector

    _seed_all_clean_upstream_artefacts()
    code, payload = _exercise_walker(monkeypatch)
    # Envelope side.
    assert payload["would_proceed"] is True
    assert payload["dry_run_only"] is True
    assert payload["live_merge_implemented"] is False
    assert payload["deploy_coupled"] is False
    assert payload["level6_enabled"] is False
    assert payload["step5_implementation_allowed"] is False
    assert payload["step5_enabled_substage"] == "none"
    # Persisted dry_run/latest.json side — same co-occurrence.
    latest = json.loads(projector.DRY_RUN_LATEST.read_text(encoding="utf-8"))
    assert latest["would_proceed"] is True
    assert latest["dry_run_only"] is True
    assert latest["live_merge_implemented"] is False
    assert latest["deploy_coupled"] is False
    assert latest["level6_enabled"] is False
    assert latest["step5_implementation_allowed"] is False
    assert latest["step5_enabled_substage"] == "none"


def test_b2_8e_would_proceed_field_documented_as_dry_run_only_in_source() -> None:
    """Source-text pin: the walker module's source must explicitly
    document ``would_proceed`` as a dry-run-only signal so a future
    reader cannot mistake it for live merge authority. The doc
    string adjacent to the ok-emit branch carries that wording.

    Negative pin: the walker source must NOT describe
    ``would_proceed`` as live-merge / merge-execution / deploy
    authority."""
    src = MODULE_PATH.read_text(encoding="utf-8")
    # Required wording — the comment adjacent to the
    # status="ok" emit branch must explicitly state this is a
    # dry-run-only proceed signal, not live merge authority.
    assert "dry-run-only proceed" in src.lower() or (
        "dry-run only proceed" in src.lower()
    ) or "not live merge authority" in src.lower(), (
        "walker source must document would_proceed=true as a "
        "dry-run-only proceed signal (not live merge authority) "
        "next to the status=ok emit branch"
    )
    # Negative pin: the source must NOT describe would_proceed
    # as live-merge / merge-execution / deploy authority.
    for forbidden_misframing in (
        "would proceed to merge",
        "will merge the pr",
        "executes the merge",
        "live merge authorized",
        "live merge authorised",
        "automatic future merge allowed",
    ):
        assert forbidden_misframing not in src.lower(), (
            f"walker source uses live-merge misframing for "
            f"would_proceed: {forbidden_misframing!r}"
        )


# ---------------------------------------------------------------------------
# B2.8e UNWIRED-state pin — operator-applied wiring is a separate commit
# ---------------------------------------------------------------------------


def test_b2_8e_blueprint_still_unwired_in_dashboard_py() -> None:
    """B2.8e MUST NOT wire the blueprint into ``dashboard/dashboard.py``.
    The operator-applied wiring patch + corresponding test-pin
    retirement is a separate follow-up commit (B2.0c precedent).
    This pin is identical to ``test_blueprint_not_registered_in_dashboard_py``;
    re-asserted explicitly so the B2.8e contract surface is
    self-documenting."""
    src = DASHBOARD_PY.read_text(encoding="utf-8")
    forbidden_substrings = (
        "from dashboard.api_merge_execution_dry_run",
        "import api_merge_execution_dry_run",
        "register_merge_execution_dry_run_routes",
    )
    hits = [s for s in forbidden_substrings if s in src]
    assert not hits, (
        "B2.8e walker must remain UNWIRED. dashboard.py contains "
        f"wiring substrings: {hits!r}. Wiring is operator-applied "
        "in a separate follow-up commit."
    )
