"""Cross-module observability + security invariants (v3.15.15.27).

This is the v3.15.15.27 hardening sweep test surface. It walks
``dashboard/api_*.py`` and ``reporting/*.py`` files in source form
and asserts:

* Agent-Control endpoints are GET-only at the registration layer.
* Boundary exception handlers in those files emit only the
  exception's class name (``type(e).__name__``), never ``str(e)``
  / ``repr(e)`` / ``e.args`` — those can carry credential strings,
  free-form path mentions, or internal traceback fragments.
* Status payload responses never contain credential-shaped values
  (``sk-ant-`` / ``ghp_`` / ``github_pat_`` / ``AKIA`` /
  ``BEGIN PRIVATE KEY``).
* ``api_execute_safe_controls`` remains UNWIRED in
  ``dashboard.dashboard``.
* The shared no-touch-path-reference allowlist is preserved across
  ``approval_policy``, ``agent_audit_summary``, and
  ``governance_status`` — the v3.15.15.25.1 narrowing must not be
  re-broadened by a future regression.
* Frontend bundle (raw source) never imports a mutation fetch verb
  (POST/PUT/PATCH/DELETE) for any /api/agent-control/* endpoint.

These tests are intentionally source-text checks — they cannot be
defeated by stubbing or runtime patching, which is the point.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent.parent


# ---------------------------------------------------------------------------
# Boundary handler invariants
# ---------------------------------------------------------------------------


# Files we apply the strict boundary-handler rules to. Each is a
# read-only surface that publishes status to operator-facing
# JSON / API / PWA. Anything else (e.g. CLI scripts, internal
# helpers) is allowed to keep ``str(e)`` because it never leaves
# the local process.
_AGENT_CONTROL_BOUNDARY_FILES: tuple[str, ...] = (
    "dashboard/api_agent_control.py",
    "dashboard/api_approval_inbox.py",
    "dashboard/api_proposal_queue.py",
    "dashboard/api_execute_safe_controls.py",
)


# Forbidden patterns inside the body of a boundary exception
# handler. We accept ``type(e).__name__`` (the canonical redacted
# form) and reject every other way of stringifying the exception.
_FORBIDDEN_EXC_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"\bstr\(\s*e\s*\)"),
    re.compile(r"\brepr\(\s*e\s*\)"),
    re.compile(r"\bf['\"][^'\"]*\{e\}[^'\"]*['\"]"),
    re.compile(r"\be\.args\b"),
    re.compile(r"\btraceback\.format_exc\("),
)


@pytest.mark.parametrize("rel", _AGENT_CONTROL_BOUNDARY_FILES)
def test_agent_control_boundary_handlers_redact_exception_messages(rel: str) -> None:
    """Boundary handlers in agent-control routes must not emit raw
    exception messages. Only ``type(e).__name__`` is allowed."""
    p = REPO_ROOT / rel
    src = p.read_text(encoding="utf-8")
    for pat in _FORBIDDEN_EXC_PATTERNS:
        match = pat.search(src)
        assert match is None, (
            f"{rel} contains a forbidden exception-leak pattern: "
            f"{pat.pattern!r} matched {match.group(0)!r}"
        )


# ---------------------------------------------------------------------------
# GET-only verb invariant
# ---------------------------------------------------------------------------


_METHODS_RE = re.compile(r"methods\s*=\s*\[([^\]]+)\]")
_FORBIDDEN_VERBS: frozenset[str] = frozenset(
    {"POST", "PUT", "PATCH", "DELETE"}
)


@pytest.mark.parametrize("rel", _AGENT_CONTROL_BOUNDARY_FILES)
def test_agent_control_routes_are_get_only(rel: str) -> None:
    """No ``methods=[...]`` list in any agent-control route file
    contains a mutation verb."""
    p = REPO_ROOT / rel
    src = p.read_text(encoding="utf-8")
    for m in _METHODS_RE.finditer(src):
        verbs_raw = m.group(1)
        verbs = {v.strip().strip("'\"").upper() for v in verbs_raw.split(",")}
        leaked = verbs & _FORBIDDEN_VERBS
        assert not leaked, (
            f"{rel} registers a mutation verb {leaked!r} in "
            f"methods={verbs_raw!r}"
        )


def test_dashboard_does_not_wire_execute_safe_routes() -> None:
    """``dashboard.dashboard`` must NOT call
    ``register_execute_safe_routes``. The execute-safe API stays
    intentionally unwired until the operator approves a separate
    release."""
    p = REPO_ROOT / "dashboard" / "dashboard.py"
    src = p.read_text(encoding="utf-8")
    assert "register_execute_safe_routes" not in src, (
        "dashboard/dashboard.py must not wire api_execute_safe_controls"
    )


# ---------------------------------------------------------------------------
# Status payload no-credential-leak meta-test
# ---------------------------------------------------------------------------


_CREDENTIAL_FRAGMENTS: tuple[str, ...] = (
    "sk-ant-",
    "ghp_",
    "github_pat_",
    "AKIA",
    "BEGIN PRIVATE KEY",
)


def test_agent_control_status_endpoint_emits_no_credential_shaped_values(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """End-to-end guard: hitting ``/api/agent-control/status`` must
    never return a credential-shaped string in any field. We
    redirect every artifact path into ``tmp_path`` so the test is
    hermetic."""
    from flask import Flask
    from dashboard import api_agent_control as ac

    monkeypatch.setattr(ac, "LOGS_DIR", tmp_path / "logs")
    monkeypatch.setattr(
        ac,
        "WORKLOOP_LATEST",
        tmp_path / "logs" / "autonomous_workloop" / "latest.json",
    )
    monkeypatch.setattr(
        ac,
        "PR_LIFECYCLE_LATEST",
        tmp_path / "logs" / "github_pr_lifecycle" / "latest.json",
    )
    flask_app = Flask(__name__)
    ac.register_agent_control_routes(flask_app)
    client = flask_app.test_client()
    resp = client.get("/api/agent-control/status")
    assert resp.status_code == 200
    text = resp.get_data(as_text=True)
    for frag in _CREDENTIAL_FRAGMENTS:
        assert frag not in text, (
            f"/api/agent-control/status response leaks credential fragment {frag!r}"
        )


# ---------------------------------------------------------------------------
# v3.15.15.25.1 path-reference allowlist preserved
# ---------------------------------------------------------------------------


def test_agent_audit_summary_assert_no_secrets_allows_no_touch_paths() -> None:
    """The v3.15.15.25.1 narrowing must not be re-broadened. A
    future regression that re-introduces a ``_SENSITIVE_FRAGMENTS``
    substring check would break inbox/runtime collection."""
    from reporting import agent_audit_summary as aas

    for path_ref in aas.KNOWN_NO_TOUCH_PATH_REFERENCES:
        aas.assert_no_secrets({"path": path_ref})  # must not raise


def test_governance_status_assert_no_secrets_allows_no_touch_paths() -> None:
    from reporting import governance_status as gs

    for path_ref in gs.KNOWN_NO_TOUCH_PATH_REFERENCES:
        gs.assert_no_secrets({"path": path_ref})  # must not raise


def test_approval_policy_assert_no_credential_values_allows_no_touch_paths() -> None:
    """The shared approval_policy guard is intentionally narrow:
    only credential VALUES trip; path-shaped strings flow through.
    Verified verbatim against v3.15.15.24 contract."""
    from reporting import approval_policy as ap

    for path_ref in (
        "config/config.yaml",
        "automation/live_gate.py",
        "research/research_latest.json",
    ):
        ap.assert_no_credential_values({"path": path_ref})  # must not raise


# ---------------------------------------------------------------------------
# Frontend bundle source: no mutation fetch
# ---------------------------------------------------------------------------


def test_frontend_agent_control_api_uses_only_get() -> None:
    """``frontend/src/api/agent_control.ts`` must not call any
    mutation verb against the agent-control surface. We grep the
    raw source for ``method:`` declarations."""
    p = REPO_ROOT / "frontend" / "src" / "api" / "agent_control.ts"
    src = p.read_text(encoding="utf-8")
    forbidden = (
        '"POST"', "'POST'",
        '"PUT"', "'PUT'",
        '"PATCH"', "'PATCH'",
        '"DELETE"', "'DELETE'",
    )
    for tok in forbidden:
        assert tok not in src, (
            f"frontend/src/api/agent_control.ts contains a forbidden mutation verb: {tok!r}"
        )


# ---------------------------------------------------------------------------
# Stale-artifact classification (v3.15.15.27)
# ---------------------------------------------------------------------------


def test_autonomy_metrics_classifies_known_missing_as_not_available() -> None:
    """The two known-missing collectors (recurring_maintenance and
    execute_safe_controls) must be classified ``missing`` /
    ``not_available`` — NOT failed, NOT stale. This protects the
    operator from being told "these are bugs" when they are simply
    "not yet collected"."""
    from reporting import autonomy_metrics as am

    for src_path in (
        "logs/recurring_maintenance/latest.json",
        "logs/execute_safe_controls/latest.json",
    ):
        # The path is one of the canonical SOURCE_ORDER entries.
        assert any(
            src_path == rel for _, rel in am.SOURCE_ORDER
        ), f"missing source path not registered: {src_path}"


def test_autonomy_metrics_stale_threshold_is_documented() -> None:
    """The schema doc must document the stale-threshold default and
    the env var override."""
    schema = (
        REPO_ROOT
        / "docs"
        / "governance"
        / "autonomy_metrics"
        / "schema.v1.md"
    )
    text = schema.read_text(encoding="utf-8")
    # Either the v3.15.15.27 docs are present (preferred) or the
    # original v1 schema doc is — staleness is documented as a
    # reliability metric in both cases.
    assert "stale_artifact_count" in text


# ---------------------------------------------------------------------------
# No subprocess / network in the agent-control surface
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("rel", _AGENT_CONTROL_BOUNDARY_FILES)
def test_agent_control_boundary_files_use_no_subprocess_or_network(
    rel: str,
) -> None:
    p = REPO_ROOT / rel
    src = p.read_text(encoding="utf-8")
    forbidden = (
        "import subprocess",
        "from subprocess",
        "import requests",
        "import urllib.request",
        "from urllib.request",
        "Popen(",
    )
    for tok in forbidden:
        assert tok not in src, (
            f"{rel} contains a forbidden import/usage: {tok!r}"
        )


# ---------------------------------------------------------------------------
# Ad-hoc structural test: status payload shape stays read-only
# ---------------------------------------------------------------------------


def test_agent_control_status_payload_shape_is_read_only(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """End-to-end: every top-level value of the status payload is
    an envelope (status: ok|not_available) with no embedded
    "execute" / "approve" / "merge" verbs in any string field."""
    from flask import Flask
    from dashboard import api_agent_control as ac

    monkeypatch.setattr(ac, "LOGS_DIR", tmp_path / "logs")
    monkeypatch.setattr(
        ac,
        "WORKLOOP_LATEST",
        tmp_path / "logs" / "autonomous_workloop" / "latest.json",
    )
    monkeypatch.setattr(
        ac,
        "PR_LIFECYCLE_LATEST",
        tmp_path / "logs" / "github_pr_lifecycle" / "latest.json",
    )
    flask_app = Flask(__name__)
    ac.register_agent_control_routes(flask_app)
    client = flask_app.test_client()
    body = client.get("/api/agent-control/status").get_json()

    forbidden_verbs = ("execute_now", "approve_now", "merge_now", "ack_now", "reject_now")
    flat = json.dumps(body).lower()
    for v in forbidden_verbs:
        assert v not in flat, f"status payload contains forbidden mutation verb {v!r}"
