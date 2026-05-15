"""Pin tests for the B2.8b — N5b Phase 2 token-bound dry-run endpoint
skeleton (UNWIRED, fail-closed).

The module under test (``dashboard/api_merge_execution_dry_run.py``)
ships **only** the fail-closed skeleton: every request returns
the closed-envelope ``not_yet_implemented`` status, no token
verification is performed, no GitHub API is called, no audit
artefact is written, no environment variable is read, and the
blueprint is **not wired** into ``dashboard/dashboard.py``.

These pin tests lock the skeleton's invariants. Subsequent
sub-units (B2.8c / B2.8d / B2.8e) inherit the pins; they may
extend the closed status vocabulary (``ok`` / ``rejected`` /
``configuration_missing``) and replace specific skeleton-only
pins (e.g. "every request returns not_yet_implemented") but
must update each pin in the same PR that introduces the new
behaviour.

Defense-in-depth note: the forbidden marker strings the tests
search for are NEVER embedded as literals in this file when
they would also trip the runtime source-text scan; markers are
assembled at runtime from constituent parts.
"""

from __future__ import annotations

import ast
import json
from pathlib import Path
from typing import Any

import pytest
from flask import Flask

from dashboard import api_merge_execution_dry_run as mod

REPO_ROOT = Path(__file__).resolve().parents[2]
MODULE_PATH = REPO_ROOT / "dashboard" / "api_merge_execution_dry_run.py"
DASHBOARD_PY = REPO_ROOT / "dashboard" / "dashboard.py"

ROUTE_URL = "/api/agent-control/merge-execution/dry-run"


# ---------------------------------------------------------------------------
# Module surface
# ---------------------------------------------------------------------------


def test_module_imports_successfully() -> None:
    """Smoke pin: importing the module does not raise."""
    assert mod is not None


def test_module_version_is_pinned_string() -> None:
    assert mod.MODULE_VERSION == "v3.15.16.N5b.phase2.skeleton"


def test_schema_version_is_pinned_integer_1() -> None:
    assert mod.SCHEMA_VERSION == 1


def test_step5_enabled_substage_is_pinned_none() -> None:
    assert mod.STEP5_ENABLED_SUBSTAGE == "none"


def test_step5_implementation_allowed_is_pinned_false() -> None:
    assert mod.step5_implementation_allowed is False


def test_all_exports_are_closed() -> None:
    expected = {
        "MODULE_VERSION",
        "SCHEMA_VERSION",
        "STEP5_ENABLED_SUBSTAGE",
        "register_merge_execution_dry_run_routes",
        "step5_implementation_allowed",
    }
    assert set(mod.__all__) == expected


def test_register_helper_callable_exists() -> None:
    assert callable(mod.register_merge_execution_dry_run_routes)


# ---------------------------------------------------------------------------
# AST guards — forbidden imports
# ---------------------------------------------------------------------------


_FORBIDDEN_IMPORT_TOPS = (
    "subprocess",
    "socket",
    "urllib",
    "requests",
    "httpx",
    "aiohttp",
    "asyncio",
    # B2.8b must NOT import the token runtime — that wiring is
    # reserved for B2.8c. Adding this import here without
    # narrowing this pin is the contract violation we want to
    # catch.
    "reporting.approval_token_runtime",
    # B2.8b must NOT import the reporting-side audit projector
    # — that module does not exist yet and lands in B2.8c.
    "reporting.n5b_merge_execution_dry_run",
)


def _module_imports() -> list[str]:
    """Return the list of top-level module names imported by
    the module under test (both ``import X`` and ``from X
    import ...``)."""
    src = MODULE_PATH.read_text(encoding="utf-8")
    tree = ast.parse(src)
    names: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                names.append(alias.name)
        if isinstance(node, ast.ImportFrom) and node.module is not None:
            names.append(node.module)
    return names


def test_module_has_no_forbidden_top_level_imports() -> None:
    imported = _module_imports()
    offending: list[str] = []
    for name in imported:
        for forbidden in _FORBIDDEN_IMPORT_TOPS:
            # Match exact name OR dotted-prefix match (e.g.
            # `socket.socket` matches `socket`; `subprocess.run`
            # matches `subprocess`).
            if name == forbidden or name.startswith(forbidden + "."):
                offending.append(name)
    assert offending == [], (
        "skeleton imports forbidden modules: "
        f"{offending!r}. B2.8b must not import any subprocess / "
        "network / token-runtime / audit-projector module."
    )


def test_module_does_not_import_os_system_or_popen() -> None:
    """``os.system`` and ``os.popen`` are shell-spawning primitives.
    The skeleton must use neither."""
    src = MODULE_PATH.read_text(encoding="utf-8")
    # Assemble forbidden attributes from parts so this test source
    # remains inert to greppers.
    forbidden = ("o" + "s.system", "o" + "s.popen")
    for marker in forbidden:
        assert marker not in src, (
            f"skeleton contains forbidden attribute reference: {marker!r}"
        )


def test_module_does_not_invoke_subprocess_attrs() -> None:
    """Source-text scan for any subprocess-attribute reference."""
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
            f"skeleton contains forbidden attribute reference: {marker!r}"
        )


# ---------------------------------------------------------------------------
# Source-text guards — forbidden shell-out literals
# ---------------------------------------------------------------------------


def test_module_contains_no_gh_shellout_literal() -> None:
    """No GitHub CLI shell-out literal in the skeleton."""
    src = MODULE_PATH.read_text(encoding="utf-8")
    forbidden_literal = "g" + "h " + "pr " + "merge"
    assert forbidden_literal not in src, (
        f"skeleton contains forbidden shell-out literal: "
        f"{forbidden_literal!r}"
    )


def test_module_contains_no_git_merge_literal() -> None:
    """No version-control CLI merge literal in the skeleton."""
    src = MODULE_PATH.read_text(encoding="utf-8")
    forbidden_literal = "g" + "it " + "merge"
    assert forbidden_literal not in src, (
        f"skeleton contains forbidden shell-out literal: "
        f"{forbidden_literal!r}"
    )


def test_module_contains_no_admin_flag_literal() -> None:
    """No ``--admin`` flag literal — branch-protection bypass
    is permanently denied per n5b_merge_execution_plan.md §8.4."""
    src = MODULE_PATH.read_text(encoding="utf-8")
    forbidden_literal = "--" + "admin"
    assert forbidden_literal not in src, (
        f"skeleton contains forbidden flag literal: {forbidden_literal!r}"
    )


def test_module_contains_no_merge_pr_attribute_literals() -> None:
    """No PR-mutation attribute name appears in the skeleton."""
    src = MODULE_PATH.read_text(encoding="utf-8")
    forbidden_tokens = (
        "p" + "r_merge_approved",
        "m" + "erge" + "Pull" + "Request",
    )
    for marker in forbidden_tokens:
        assert marker not in src, (
            f"skeleton contains forbidden PR-mutation literal: {marker!r}"
        )


def test_module_reads_no_env_var() -> None:
    """The skeleton must read no environment variable. Source-text
    scan for the common env-read attributes."""
    src = MODULE_PATH.read_text(encoding="utf-8")
    forbidden_env_reads = (
        "o" + "s.environ",
        "o" + "s.getenv",
        "g" + "etenv(",
    )
    for marker in forbidden_env_reads:
        assert marker not in src, (
            f"skeleton reads an environment variable: {marker!r}"
        )


# ---------------------------------------------------------------------------
# Route table — exactly one POST route
# ---------------------------------------------------------------------------


def _build_app() -> Flask:
    app = Flask(__name__)
    app.config["TESTING"] = True
    mod.register_merge_execution_dry_run_routes(app)
    return app


def test_route_table_carries_exactly_one_route() -> None:
    table = mod._MERGE_EXECUTION_DRY_RUN_ROUTES
    assert len(table) == 1, (
        f"route table must contain exactly one route, got {len(table)}: "
        f"{table!r}"
    )


def test_route_url_is_pinned_dry_run_path() -> None:
    (path, method, _handler, _endpoint) = mod._MERGE_EXECUTION_DRY_RUN_ROUTES[0]
    assert path == ROUTE_URL, (
        f"route URL must be exactly {ROUTE_URL!r}, got {path!r}"
    )
    assert method == "POST"


def test_route_registers_with_post_method_only() -> None:
    app = _build_app()
    matches = [r for r in app.url_map.iter_rules() if r.rule == ROUTE_URL]
    assert len(matches) == 1, (
        f"expected exactly one route registered for {ROUTE_URL!r}, "
        f"got {len(matches)}: {matches!r}"
    )
    rule = matches[0]
    methods = rule.methods or set()
    # Flask always adds HEAD + OPTIONS automatically; the POST
    # method must be present and no other domain method (GET /
    # PUT / PATCH / DELETE) may be.
    assert "POST" in methods, f"POST not in registered methods: {methods!r}"
    forbidden = {"GET", "PUT", "PATCH", "DELETE"}
    assert methods.isdisjoint(forbidden), (
        f"route must not accept {forbidden!r}, accepted: {methods!r}"
    )


# ---------------------------------------------------------------------------
# Method dispatch — 405 for non-POST
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("method", ["GET", "PUT", "PATCH", "DELETE"])
def test_non_post_methods_return_405(method: str) -> None:
    app = _build_app()
    with app.test_client() as client:
        resp = client.open(ROUTE_URL, method=method)
    assert resp.status_code == 405, (
        f"{method} {ROUTE_URL} must return 405, got {resp.status_code}"
    )


# ---------------------------------------------------------------------------
# Envelope shape — every response has the closed schema
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
    """Return a syntactically valid request body matching the
    closed §2.3 schema."""
    return {
        "pr_number": 123,
        "pr_head_sha": "abc1234567890def1234567890abcdef12345678",
        "token": "synthetic-token-for-skeleton-tests",
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


def test_well_formed_request_returns_not_yet_implemented_200() -> None:
    app = _build_app()
    with app.test_client() as client:
        resp = _post_json(client, _well_formed_body())
    assert resp.status_code == 200
    payload = resp.get_json()
    assert payload["status"] == "not_yet_implemented"
    assert payload["would_proceed"] is False
    assert payload["stop_condition"] is None


def test_envelope_contains_all_closed_fields() -> None:
    app = _build_app()
    with app.test_client() as client:
        resp = _post_json(client, _well_formed_body())
    payload = resp.get_json()
    missing = _REQUIRED_ENVELOPE_FIELDS - set(payload.keys())
    assert not missing, f"envelope missing required fields: {missing!r}"


def test_envelope_pins_six_discipline_invariants() -> None:
    app = _build_app()
    with app.test_client() as client:
        resp = _post_json(client, _well_formed_body())
    payload = resp.get_json()
    assert payload["step5_implementation_allowed"] is False
    assert payload["step5_enabled_substage"] == "none"
    assert payload["level6_enabled"] is False
    assert payload["dry_run_only"] is True
    assert payload["live_merge_implemented"] is False
    assert payload["deploy_coupled"] is False


def test_envelope_echoes_body_pr_number_and_head_sha() -> None:
    app = _build_app()
    body = _well_formed_body()
    with app.test_client() as client:
        resp = _post_json(client, body)
    payload = resp.get_json()
    assert payload["pr_number"] == body["pr_number"]
    assert payload["pr_head_sha"] == body["pr_head_sha"]


def test_envelope_module_and_schema_versions_match_constants() -> None:
    app = _build_app()
    with app.test_client() as client:
        resp = _post_json(client, _well_formed_body())
    payload = resp.get_json()
    assert payload["module_version"] == mod.MODULE_VERSION
    assert payload["schema_version"] == mod.SCHEMA_VERSION


# ---------------------------------------------------------------------------
# Malformed body — HTTP 400 with not_yet_implemented + reason
# ---------------------------------------------------------------------------


def test_missing_body_returns_400_not_yet_implemented() -> None:
    app = _build_app()
    with app.test_client() as client:
        resp = _post_json(client, None)
    assert resp.status_code == 400
    payload = resp.get_json()
    assert payload["status"] == "not_yet_implemented"
    assert payload["would_proceed"] is False
    assert payload["reason"] == "body_missing"
    assert payload["pr_number"] == 0
    assert payload["pr_head_sha"] == ""


def test_non_object_body_returns_400_with_reason() -> None:
    app = _build_app()
    with app.test_client() as client:
        resp = _post_json(client, [1, 2, 3])
    assert resp.status_code == 400
    payload = resp.get_json()
    assert payload["status"] == "not_yet_implemented"
    assert payload["reason"] == "body_not_object"


@pytest.mark.parametrize(
    "drop_field,expected_reason",
    [
        ("pr_number", "field_missing:pr_number"),
        ("pr_head_sha", "field_missing:pr_head_sha"),
        ("token", "field_missing:token"),
        ("intent", "field_missing:intent"),
        ("evidence_hash", "field_missing:evidence_hash"),
    ],
)
def test_missing_required_field_returns_400_with_closed_reason(
    drop_field: str, expected_reason: str
) -> None:
    app = _build_app()
    body = _well_formed_body()
    del body[drop_field]
    with app.test_client() as client:
        resp = _post_json(client, body)
    assert resp.status_code == 400
    payload = resp.get_json()
    assert payload["status"] == "not_yet_implemented"
    assert payload["reason"] == expected_reason


@pytest.mark.parametrize(
    "field,bad_value,expected_reason",
    [
        ("pr_number", "123", "field_type:pr_number"),
        ("pr_number", True, "field_type:pr_number"),
        ("pr_head_sha", 123, "field_type:pr_head_sha"),
        ("token", 123, "field_type:token"),
        ("intent", 123, "field_type:intent"),
        ("evidence_hash", 123, "field_type:evidence_hash"),
    ],
)
def test_wrong_field_type_returns_400_with_closed_reason(
    field: str, bad_value: Any, expected_reason: str
) -> None:
    app = _build_app()
    body = _well_formed_body()
    body[field] = bad_value
    with app.test_client() as client:
        resp = _post_json(client, body)
    assert resp.status_code == 400
    payload = resp.get_json()
    assert payload["status"] == "not_yet_implemented"
    assert payload["reason"] == expected_reason


def test_intent_must_be_pinned_literal() -> None:
    app = _build_app()
    body = _well_formed_body()
    body["intent"] = "something_else"
    with app.test_client() as client:
        resp = _post_json(client, body)
    assert resp.status_code == 400
    payload = resp.get_json()
    assert payload["reason"] == "field_value:intent_not_pinned"


def test_negative_pr_number_is_rejected() -> None:
    app = _build_app()
    body = _well_formed_body()
    body["pr_number"] = -1
    with app.test_client() as client:
        resp = _post_json(client, body)
    assert resp.status_code == 400
    payload = resp.get_json()
    assert payload["reason"] == "field_value:pr_number_non_positive"


def test_zero_pr_number_is_rejected() -> None:
    app = _build_app()
    body = _well_formed_body()
    body["pr_number"] = 0
    with app.test_client() as client:
        resp = _post_json(client, body)
    assert resp.status_code == 400
    payload = resp.get_json()
    assert payload["reason"] == "field_value:pr_number_non_positive"


def test_oversized_token_is_rejected() -> None:
    app = _build_app()
    body = _well_formed_body()
    body["token"] = "x" * 5000  # exceeds _MAX_TOKEN_LEN = 4096
    with app.test_client() as client:
        resp = _post_json(client, body)
    assert resp.status_code == 400
    payload = resp.get_json()
    assert payload["reason"] == "field_value:token_length"


def test_empty_pr_head_sha_is_rejected() -> None:
    app = _build_app()
    body = _well_formed_body()
    body["pr_head_sha"] = ""
    with app.test_client() as client:
        resp = _post_json(client, body)
    assert resp.status_code == 400
    payload = resp.get_json()
    assert payload["reason"] == "field_value:pr_head_sha_length"


# ---------------------------------------------------------------------------
# Status vocabulary — skeleton emits only not_yet_implemented
# ---------------------------------------------------------------------------


_FORBIDDEN_SKELETON_STATUSES = frozenset({"ok", "rejected", "configuration_missing"})


@pytest.mark.parametrize(
    "body",
    [
        # Well-formed body → 200.
        {
            "pr_number": 1,
            "pr_head_sha": "a" * 40,
            "token": "t",
            "intent": "mobile_approval_dispatch",
            "evidence_hash": "e" * 64,
        },
        # Various malformed bodies → 400. All must still emit
        # status = "not_yet_implemented".
        {},
        {"pr_number": 1},
        {"pr_number": "not-an-int", "pr_head_sha": "x"},
    ],
)
def test_skeleton_status_is_always_not_yet_implemented(body: Any) -> None:
    """B2.8b never emits ok / rejected / configuration_missing.
    Those values are reserved for B2.8c (token verification),
    B2.8c onwards (rejected on stop_condition), and the
    configuration-readiness check (B2.8c also)."""
    app = _build_app()
    with app.test_client() as client:
        resp = _post_json(client, body)
    payload = resp.get_json()
    assert payload["status"] == "not_yet_implemented"
    assert payload["status"] not in _FORBIDDEN_SKELETON_STATUSES


# ---------------------------------------------------------------------------
# UNWIRED contract — blueprint not registered in dashboard.py
# ---------------------------------------------------------------------------


def test_dashboard_py_present_for_unwired_pin() -> None:
    """Existence pin for the UNWIRED scan below: the dashboard
    wiring file must be on disk so the scan is meaningful."""
    assert DASHBOARD_PY.is_file(), (
        f"dashboard wiring file missing: {DASHBOARD_PY}"
    )


def test_blueprint_not_registered_in_dashboard_py() -> None:
    """B2.8b ships the skeleton UNWIRED. The wiring patch into
    ``dashboard/dashboard.py`` is operator-only and reserved for
    B2.8e. Source-text scan of dashboard.py asserts the import
    + register-call are absent."""
    src = DASHBOARD_PY.read_text(encoding="utf-8")
    forbidden_substrings = (
        "from dashboard.api_merge_execution_dry_run",
        "import api_merge_execution_dry_run",
        "register_merge_execution_dry_run_routes",
    )
    hits = [s for s in forbidden_substrings if s in src]
    assert not hits, (
        "B2.8b skeleton must remain UNWIRED. dashboard.py contains "
        f"wiring substrings: {hits!r}. Wiring is B2.8e scope."
    )


# ---------------------------------------------------------------------------
# Audit redaction — every envelope passes assert_no_secrets
# ---------------------------------------------------------------------------


def test_well_formed_envelope_passes_assert_no_secrets() -> None:
    """The handler runs assert_no_secrets on every envelope; this
    pin re-asserts the contract by re-running it on the response
    payload independently."""
    from reporting.agent_audit_summary import assert_no_secrets

    app = _build_app()
    with app.test_client() as client:
        resp = _post_json(client, _well_formed_body())
    payload = resp.get_json()
    # Re-running assert_no_secrets must not raise.
    assert_no_secrets(payload)


def test_malformed_body_envelope_passes_assert_no_secrets() -> None:
    from reporting.agent_audit_summary import assert_no_secrets

    app = _build_app()
    with app.test_client() as client:
        resp = _post_json(client, None)
    payload = resp.get_json()
    assert_no_secrets(payload)


# ---------------------------------------------------------------------------
# No filesystem write — skeleton writes nothing
# ---------------------------------------------------------------------------


def test_skeleton_source_has_no_filesystem_write_attrs() -> None:
    """The skeleton must not call any filesystem write primitive.
    B2.8c reserves the right to write under
    ``logs/n5b_merge_execution/`` — but B2.8b does not."""
    src = MODULE_PATH.read_text(encoding="utf-8")
    # Assemble forbidden write attributes from parts.
    forbidden = (
        ".write(",
        ".write_text(",
        ".write_bytes(",
        "open(",
        "o" + "s.replace(",
        "json.dump(",
        "json.dumps(",  # the skeleton uses no JSON serialisation
    )
    hits = [m for m in forbidden if m in src]
    assert hits == [], (
        f"skeleton contains forbidden filesystem-write attributes: {hits!r}. "
        "B2.8b writes nothing; audit projector lands in B2.8c."
    )


# ---------------------------------------------------------------------------
# Bounded caps — defense-in-depth against pathological inputs
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
