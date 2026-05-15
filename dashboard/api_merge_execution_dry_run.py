"""N5b Phase 2 — Token-bound dry-run endpoint skeleton (UNWIRED, fail-closed).

This module is the **B2.8b skeleton** of the future Phase 2
token-bound dry-run endpoint described in
``docs/governance/n5b_phase2_implementation_plan.md`` (§2.1/§2.2)
and ``docs/governance/n5b_merge_execution_plan.md`` (§4.2/§10
"Phase 2 — Token-bound dry-run").

**This is NOT a Phase 2 activation.** B2.8b ships ONLY the
fail-closed skeleton: every request returns the closed-envelope
``not_yet_implemented`` status. No token verification is
performed, no GitHub API is called, no audit artefact is
written, no environment variable is read, and the blueprint is
**not wired** into ``dashboard/dashboard.py``. The §4.2 N4b
Phase B activation and §4.3 N4c (or equivalent) mint/verify UI
preconditions of the implementation plan remain unsatisfied
and block any subsequent code-bearing sub-unit (B2.8c / B2.8d /
B2.8e) until the operator explicitly confirms them.

Hard guarantees (pinned by tests in
``tests/unit/test_api_merge_execution_dry_run.py``)
-----------------------------------------------------------

* POST only — exactly one route at
  ``/api/agent-control/merge-execution/dry-run``. GET / PUT /
  PATCH / DELETE return 405.
* Every request returns the closed-envelope status
  ``not_yet_implemented`` regardless of body validity. Malformed
  bodies attach a bounded ``reason`` field and return HTTP 400;
  well-formed bodies return HTTP 200. The envelope ``status``
  field never deviates from ``not_yet_implemented`` in this
  skeleton.
* No token verification — this module does not import
  ``reporting.approval_token_runtime``. Token verification
  wiring is **B2.8c** scope.
* No audit artefact write — this module does not import or
  reference ``reporting.n5b_merge_execution_dry_run`` (which
  does not exist yet). Audit projector is **B2.8c** scope.
* No GitHub API call — this module does not import any
  network primitive (``socket``, ``urllib``, ``requests``,
  ``httpx``, ``aiohttp``) and performs no outbound HTTP call.
  GitHub-API-dependent preconditions 8-17 are **B2.8d** scope.
* No subprocess / shell-out — this module imports no child-process
  primitive and uses no shell-spawning attribute of the os module.
* No env var read — this module reads no environment variable
  whatsoever.
* No write outside ``logs/n5b_merge_execution/`` — this module
  performs no filesystem write of any kind. The audit
  artefact write path is reserved for B2.8c.
* Every response envelope passes
  ``reporting.agent_audit_summary.assert_no_secrets`` before
  being returned to the client.
* Every response envelope carries the closed six-field
  discipline invariants verbatim
  (``step5_implementation_allowed=False``,
  ``step5_enabled_substage="none"``, ``level6_enabled=False``,
  ``dry_run_only=True``, ``live_merge_implemented=False``,
  ``deploy_coupled=False``) so the consumer always sees them.
* Blueprint is **NOT** registered into
  ``dashboard/dashboard.py`` by this PR. The two-line wiring
  change is operator-only per
  ``docs/governance/execution_authority.md`` and the no-touch
  hook at ``.claude/hooks/deny_no_touch.py``. Wiring is
  **B2.8e** scope.

Status envelope contract
------------------------

The response envelope follows the closed schema declared in
``docs/governance/n5b_phase2_implementation_plan.md`` §2.5.
Every field is present in every response. The ``status`` value
is always the literal ``not_yet_implemented`` for this
skeleton sub-unit.

Future sub-units (B2.8c onward) will emit additional closed
status values (``ok``, ``rejected``, ``configuration_missing``)
once the precondition walkers land. B2.8b never emits any of
those values.
"""

from __future__ import annotations

from typing import Any, Final

from flask import Flask, Response, jsonify, request

from reporting.agent_audit_summary import assert_no_secrets

MODULE_VERSION: Final[str] = "v3.15.16.N5b.phase2.skeleton"
SCHEMA_VERSION: Final[int] = 1


# ---------------------------------------------------------------------------
# Step 5 invariants
# ---------------------------------------------------------------------------

STEP5_ENABLED_SUBSTAGE: Final[str] = "none"
step5_implementation_allowed: Final[bool] = False


# ---------------------------------------------------------------------------
# Closed envelope helpers
# ---------------------------------------------------------------------------

#: Closed six-field discipline invariants attached to every
#: response envelope. The dict is read-only; callers never
#: overwrite individual values.
_DISCIPLINE_FIELDS: Final[dict[str, bool | str]] = {
    "step5_implementation_allowed": False,
    "step5_enabled_substage": STEP5_ENABLED_SUBSTAGE,
    "level6_enabled": False,
    "dry_run_only": True,
    "live_merge_implemented": False,
    "deploy_coupled": False,
}

#: Closed set of required request body fields per
#: ``n5b_phase2_implementation_plan.md`` §2.3.
_REQUIRED_BODY_FIELDS: Final[tuple[str, ...]] = (
    "pr_number",
    "pr_head_sha",
    "token",
    "intent",
    "evidence_hash",
)

#: Pinned literal value for the request body ``intent`` field
#: per the implementation plan §2.3.
_INTENT_LITERAL: Final[str] = "mobile_approval_dispatch"

#: Bounded caps on body field sizes. Defense-in-depth against
#: pathological inputs.
_MAX_PR_HEAD_SHA_LEN: Final[int] = 64
_MAX_TOKEN_LEN: Final[int] = 4096
_MAX_INTENT_LEN: Final[int] = 64
_MAX_EVIDENCE_HASH_LEN: Final[int] = 256
_MAX_REASON_LEN: Final[int] = 200


def _with_discipline(envelope: dict[str, Any]) -> dict[str, Any]:
    """Attach the closed discipline-invariant fields to ``envelope``.
    Callers never overwrite these values; this helper is the
    single source of truth for the six invariants."""
    out = dict(envelope)
    out.update(_DISCIPLINE_FIELDS)
    return out


def _safe_jsonify(payload: dict[str, Any]) -> Response:
    """Run the payload through ``assert_no_secrets`` then
    ``flask.jsonify``. Matches the ``api_merge_preflight`` pattern."""
    assert_no_secrets(payload)
    return jsonify(payload)


# ---------------------------------------------------------------------------
# Envelope builders
# ---------------------------------------------------------------------------


def _not_yet_implemented_envelope(
    *,
    pr_number: int,
    pr_head_sha: str,
    reason: str | None = None,
) -> dict[str, Any]:
    """Build the closed ``not_yet_implemented`` envelope per
    implementation-plan §2.5.

    The envelope's ``status`` is always the literal
    ``not_yet_implemented``. ``would_proceed`` is always False.
    ``stop_condition`` is always None — stop conditions are emitted
    by the precondition walker in B2.8c onward.
    """
    envelope: dict[str, Any] = {
        "kind": "agent_control_merge_execution_dry_run",
        "schema_version": SCHEMA_VERSION,
        "module_version": MODULE_VERSION,
        "status": "not_yet_implemented",
        "stop_condition": None,
        "preconditions_evaluated": 0,
        "preconditions_passed": 0,
        "would_proceed": False,
        "pr_number": pr_number,
        "pr_head_sha": pr_head_sha,
    }
    if reason is not None:
        envelope["reason"] = reason[:_MAX_REASON_LEN]
    return _with_discipline(envelope)


def _bad_body_envelope(reason: str) -> dict[str, Any]:
    """Build the ``not_yet_implemented`` envelope with a sentinel
    ``pr_number=0`` and empty ``pr_head_sha`` for the malformed-body
    case. The HTTP layer pairs this envelope with status 400.

    The envelope status remains the closed-vocab
    ``not_yet_implemented`` per implementation-plan §2.4 ("No
    other status value is permitted"); the ``reason`` field carries
    the body-validation outcome (e.g. ``"body_missing"``,
    ``"field_missing:token"``)."""
    return _not_yet_implemented_envelope(
        pr_number=0,
        pr_head_sha="",
        reason=reason,
    )


# ---------------------------------------------------------------------------
# Request body validation
# ---------------------------------------------------------------------------


def _validate_body(
    body: Any,
) -> tuple[bool, str | None, int, str]:
    """Validate the request body shape.

    Returns ``(ok, reason, pr_number, pr_head_sha)`` where:

    * ``ok`` is True iff the body is a JSON object with all five
      required fields, each of the correct type, with bounded
      sizes, and ``intent == _INTENT_LITERAL``.
    * ``reason`` is None when ``ok`` is True; otherwise a closed
      reason string from a bounded vocabulary describing the
      first validation failure encountered.
    * ``pr_number`` and ``pr_head_sha`` are extracted from the
      body when present and well-typed; they default to ``0`` and
      ``""`` otherwise. The skeleton echoes them back so the
      future implementation has body-context in the envelope
      regardless of validity.
    """
    if body is None:
        return (False, "body_missing", 0, "")
    if not isinstance(body, dict):
        return (False, "body_not_object", 0, "")
    # Field-presence + type checks in the documented order.
    if "pr_number" not in body:
        return (False, "field_missing:pr_number", 0, "")
    pr_number_raw = body["pr_number"]
    if not isinstance(pr_number_raw, int) or isinstance(pr_number_raw, bool):
        return (False, "field_type:pr_number", 0, "")
    if pr_number_raw <= 0:
        return (False, "field_value:pr_number_non_positive", 0, "")
    pr_number: int = pr_number_raw

    if "pr_head_sha" not in body:
        return (False, "field_missing:pr_head_sha", pr_number, "")
    pr_head_sha_raw = body["pr_head_sha"]
    if not isinstance(pr_head_sha_raw, str):
        return (False, "field_type:pr_head_sha", pr_number, "")
    if not pr_head_sha_raw or len(pr_head_sha_raw) > _MAX_PR_HEAD_SHA_LEN:
        return (False, "field_value:pr_head_sha_length", pr_number, "")
    pr_head_sha: str = pr_head_sha_raw

    if "token" not in body:
        return (False, "field_missing:token", pr_number, pr_head_sha)
    token_raw = body["token"]
    if not isinstance(token_raw, str):
        return (False, "field_type:token", pr_number, pr_head_sha)
    if not token_raw or len(token_raw) > _MAX_TOKEN_LEN:
        return (False, "field_value:token_length", pr_number, pr_head_sha)

    if "intent" not in body:
        return (False, "field_missing:intent", pr_number, pr_head_sha)
    intent_raw = body["intent"]
    if not isinstance(intent_raw, str):
        return (False, "field_type:intent", pr_number, pr_head_sha)
    if len(intent_raw) > _MAX_INTENT_LEN:
        return (False, "field_value:intent_length", pr_number, pr_head_sha)
    if intent_raw != _INTENT_LITERAL:
        return (False, "field_value:intent_not_pinned", pr_number, pr_head_sha)

    if "evidence_hash" not in body:
        return (False, "field_missing:evidence_hash", pr_number, pr_head_sha)
    evidence_hash_raw = body["evidence_hash"]
    if not isinstance(evidence_hash_raw, str):
        return (False, "field_type:evidence_hash", pr_number, pr_head_sha)
    if (
        not evidence_hash_raw
        or len(evidence_hash_raw) > _MAX_EVIDENCE_HASH_LEN
    ):
        return (False, "field_value:evidence_hash_length", pr_number, pr_head_sha)

    return (True, None, pr_number, pr_head_sha)


# ---------------------------------------------------------------------------
# View function — exactly one route
# ---------------------------------------------------------------------------


def _view_dry_run() -> tuple[Response, int]:
    """POST handler for the token-bound dry-run endpoint skeleton.

    B2.8b behaviour:

    * Parses request body. If the body is non-JSON / missing /
      malformed, returns ``not_yet_implemented`` with a bounded
      ``reason`` field at HTTP 400.
    * If the body is well-formed, returns ``not_yet_implemented``
      at HTTP 200.
    * Never verifies a token. Never calls GitHub. Never writes
      an audit artefact. Never reads an environment variable.
    """
    # Parse body permissively — silent=True ensures malformed
    # JSON returns None rather than raising 400 with the default
    # Flask handler.
    body: Any = request.get_json(silent=True)
    ok, reason, pr_number, pr_head_sha = _validate_body(body)
    if not ok:
        return _safe_jsonify(_bad_body_envelope(reason or "body_invalid")), 400
    return (
        _safe_jsonify(
            _not_yet_implemented_envelope(
                pr_number=pr_number,
                pr_head_sha=pr_head_sha,
            )
        ),
        200,
    )


# ---------------------------------------------------------------------------
# Route table + register helper
# ---------------------------------------------------------------------------

#: The closed route table. Exactly one POST route per
#: implementation-plan §2.2. GET / PUT / PATCH / DELETE on the
#: same URL return 405 via Flask's default method-not-allowed
#: handler.
_MERGE_EXECUTION_DRY_RUN_ROUTES: Final[
    tuple[tuple[str, str, Any, str], ...]
] = (
    (
        "/api/agent-control/merge-execution/dry-run",
        "POST",
        _view_dry_run,
        "agent_control_merge_execution_dry_run",
    ),
)


def register_merge_execution_dry_run_routes(app: Flask) -> None:
    """Register the N5b Phase 2 token-bound dry-run skeleton route.

    **NOT** wired into ``dashboard/dashboard.py`` in the PR that
    introduces this blueprint. The two-line wiring change

    ::

        from dashboard.api_merge_execution_dry_run import (
            register_merge_execution_dry_run_routes,
        )
        register_merge_execution_dry_run_routes(app)

    is operator-only per ``docs/governance/execution_authority.md``
    (``dashboard_wiring`` = NEEDS_HUMAN) and the no-touch hook at
    ``.claude/hooks/deny_no_touch.py`` (which protects
    ``dashboard/dashboard.py``). Wiring is **B2.8e** scope.
    """
    for path, method, handler, endpoint in _MERGE_EXECUTION_DRY_RUN_ROUTES:
        app.add_url_rule(
            path,
            endpoint=endpoint,
            view_func=handler,
            methods=[method],
        )


__all__ = [
    "MODULE_VERSION",
    "SCHEMA_VERSION",
    "STEP5_ENABLED_SUBSTAGE",
    "register_merge_execution_dry_run_routes",
    "step5_implementation_allowed",
]
