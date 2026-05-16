"""N5b Phase 2 — Token-bound dry-run endpoint (B2.8c walker for preconditions 1–7).

This module is the **B2.8c walker** layered on top of the B2.8b
fail-closed skeleton. It implements the closed precondition walker
for parent-doc §3 preconditions 1–7 (N4b activation, N4c operator
UI presence, token bindings, intent, nonce) using
``reporting.approval_token_runtime.verify_runtime_for_dry_run``
and writes the preflight audit artefact via
``reporting.n5b_merge_execution_dry_run.write_preflight``.

What B2.8c implements (per
``docs/governance/n5b_phase2_implementation_plan.md`` §3 and §6.2):

* POST only — exactly one route at
  ``/api/agent-control/merge-execution/dry-run``. GET / PUT /
  PATCH / DELETE return 405. UNCHANGED from B2.8b.
* Closed response envelope shape from §2.5. UNCHANGED from B2.8b.
* Token verification routes through
  :func:`reporting.approval_token_runtime.verify_runtime_for_dry_run`
  only. The HMAC secret is read by that module exclusively;
  this dashboard module reads NO environment variable.
* Audit preflight artefact at
  ``logs/n5b_merge_execution/preflight/latest.json`` is written
  ONLY AFTER all of body validation + N4b configuration + N4c
  component presence + token verification + binding checks
  succeed. Invalid / malformed / expired / replayed / binding-
  mismatched / mis-configured requests NEVER produce a preflight
  artefact. (Operator-mandated B2.8c correction.)
* Returns ``not_yet_implemented`` on success — never ``ok``. The
  ``ok`` status is reserved for B2.8e when preconditions 8–17
  also walk.
* Stop conditions emitted by this slice are the closed §7 set
  enumerated by the implementation plan §6.2: ``token_missing``,
  ``token_invalid``, ``replay_detected``, ``binding_mismatch``
  (drilled across pr_number / pr_head_sha / evidence_hash /
  intent / nonce), ``pr_number_mismatch``. The status
  ``configuration_missing`` is used for §3 preconditions 1 / 2.
* No new stop-condition literal is introduced. The
  post-verification preflight-write failure is surfaced as
  ``status="rejected"``, ``stop_condition=None``,
  ``reason="preflight_write_failed"`` (a reason, NOT a stop
  condition) so the closed §7 vocabulary stays untouched.

What B2.8c does NOT do:

* No GitHub-API-dependent preconditions (8–17). Those land in
  B2.8d under their own operator-go.
* No dry-run-decision artefact, no failure artefact, no history
  artefact. Those writers land in B2.8d / B2.8e per §2.6.
* No wiring into ``dashboard/dashboard.py``. The blueprint
  remains UNWIRED; the two-line wiring patch is operator-only
  per ``docs/governance/execution_authority.md`` and the
  no-touch hook at ``.claude/hooks/deny_no_touch.py``. Wiring is
  B2.8e scope.
* No subprocess / shell-out / network primitive of any kind.
* No environment-variable read in this module (the token runtime
  reads the HMAC secret on this module's behalf).
* No raw token persisted, no raw nonce surfaced.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Final

from flask import Flask, Response, jsonify, request

from reporting import approval_token_runtime as atr
from reporting import n5b_merge_execution_dry_run as projector
from reporting.agent_audit_summary import assert_no_secrets

MODULE_VERSION: Final[str] = "v3.15.16.N5b.phase2.walker_1_7"
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

#: Repo-rooted path to the N4c PWA mint/verify component. Walker
#: precondition 2 checks this file exists at request time. The
#: path is identical to the one the B2.8c-pre readiness pin test
#: asserts.
_REPO_ROOT: Final[Path] = Path(__file__).resolve().parent.parent
_N4C_COMPONENT_PATH: Final[Path] = (
    _REPO_ROOT
    / "frontend"
    / "src"
    / "routes"
    / "AgentControl"
    / "ApprovalTokenDiagnostics.tsx"
)

#: Operator-actor literal for the session-protected dry-run route.
_OPERATOR_ACTOR_SESSION: Final[str] = "session"

#: Closed mapping from body-shape validation reason → §7 stop
#: condition. Body-shape failures translate to the §7 vocabulary
#: where the failure unambiguously matches a stop condition.
#: Unmatched reasons get ``None`` (envelope still says rejected;
#: stop_condition stays null, reason carries the closed string).
_BODY_REASON_TO_STOP_CONDITION: Final[dict[str, str]] = {
    # token field problems → token_missing
    "field_missing:token": "token_missing",
    "field_value:token_length": "token_missing",
    "field_type:token": "token_missing",
    # pr_number problems → pr_number_mismatch (body lacks a valid pr_number
    # to bind against, so the binding is unprovable)
    "field_missing:pr_number": "pr_number_mismatch",
    "field_type:pr_number": "pr_number_mismatch",
    "field_value:pr_number_non_positive": "pr_number_mismatch",
    # intent problems → binding_mismatch (intent dimension)
    "field_missing:intent": "binding_mismatch",
    "field_type:intent": "binding_mismatch",
    "field_value:intent_length": "binding_mismatch",
    "field_value:intent_not_pinned": "binding_mismatch",
    # pr_head_sha problems → binding_mismatch (pr_head_sha dimension)
    "field_missing:pr_head_sha": "binding_mismatch",
    "field_type:pr_head_sha": "binding_mismatch",
    "field_value:pr_head_sha_length": "binding_mismatch",
    # evidence_hash problems → binding_mismatch (evidence_hash dimension)
    "field_missing:evidence_hash": "binding_mismatch",
    "field_type:evidence_hash": "binding_mismatch",
    "field_value:evidence_hash_length": "binding_mismatch",
    # body_missing / body_not_object: no §7 mapping; stop_condition stays null.
}


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


def _utcnow_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


# ---------------------------------------------------------------------------
# Envelope builders
# ---------------------------------------------------------------------------


def _base_envelope(
    *,
    status: str,
    stop_condition: str | None,
    preconditions_evaluated: int,
    preconditions_passed: int,
    would_proceed: bool,
    pr_number: int,
    pr_head_sha: str,
    reason: str | None = None,
) -> dict[str, Any]:
    """Build the closed envelope per implementation-plan §2.5.

    ``status`` is one of the four closed-vocab values
    (``ok`` / ``rejected`` / ``configuration_missing`` /
    ``not_yet_implemented``). ``stop_condition`` is from the closed
    §7 vocabulary OR ``None``. The six discipline invariants are
    attached unconditionally via :func:`_with_discipline`.

    ``reason`` is optional and bounded to :data:`_MAX_REASON_LEN`
    chars. It carries closed strings only (body-validation reason
    codes, ``preconditions_8_through_17_pending``,
    ``preflight_write_failed``); it never contains user-supplied
    free text.
    """
    envelope: dict[str, Any] = {
        "kind": "agent_control_merge_execution_dry_run",
        "schema_version": SCHEMA_VERSION,
        "module_version": MODULE_VERSION,
        "status": status,
        "stop_condition": stop_condition,
        "preconditions_evaluated": preconditions_evaluated,
        "preconditions_passed": preconditions_passed,
        "would_proceed": would_proceed,
        "pr_number": pr_number,
        "pr_head_sha": pr_head_sha,
    }
    if reason is not None:
        envelope["reason"] = reason[:_MAX_REASON_LEN]
    return _with_discipline(envelope)


# ---------------------------------------------------------------------------
# Request body validation (B2.8b shape — unchanged)
# ---------------------------------------------------------------------------


def _validate_body(
    body: Any,
) -> tuple[bool, str | None, int, str]:
    """Validate the request body shape. UNCHANGED from B2.8b.

    Returns ``(ok, reason, pr_number, pr_head_sha)`` where:

    * ``ok`` is True iff the body is a JSON object with all five
      required fields, each of the correct type, with bounded
      sizes, and ``intent == _INTENT_LITERAL``.
    * ``reason`` is None when ``ok`` is True; otherwise a closed
      reason string from a bounded vocabulary describing the
      first validation failure encountered.
    * ``pr_number`` and ``pr_head_sha`` are extracted from the
      body when present and well-typed; they default to ``0`` and
      ``""`` otherwise.
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
# Verify-outcome → §7 stop-condition translation
# ---------------------------------------------------------------------------


#: Closed translation table from :data:`approval_token_runtime`'s
#: verify envelope onto the §7 closed stop-condition vocabulary.
#: The walker reads the verify envelope's ``outcome`` (and the
#: companion ``reason`` for the binding-drift drill) and emits the
#: corresponding §7 stop_condition. The status component of the
#: walker envelope is always ``rejected`` for any non-``ok``
#: outcome that reaches this map.
_VERIFY_OUTCOME_TO_STOP_CONDITION: Final[dict[str, str]] = {
    "replay_detected": "replay_detected",
    "signature_invalid": "token_invalid",
    "malformed_envelope": "token_invalid",
    "expired": "token_invalid",
    "unknown_kid": "token_invalid",
    "intent_unknown": "binding_mismatch",
    # binding_mismatch is handled separately because its specific
    # reason determines whether the walker emits pr_number_mismatch
    # (a stand-alone §7 stop condition) vs the generic
    # binding_mismatch.
}


def _translate_verify_envelope(
    verify_env: dict[str, Any],
) -> tuple[str, str | None]:
    """Translate a verify envelope from
    :func:`reporting.approval_token_runtime.verify_runtime_for_dry_run`
    onto the walker's ``(status, stop_condition)`` pair.

    Only the closed §7 vocabulary plus the two skeleton statuses
    are emitted. New literals are not introduced.
    """
    status = verify_env.get("status")
    if status == "configuration_missing":
        return ("configuration_missing", None)
    if status == "ok":
        return ("ok", None)
    # Any other status from the runtime is a rejection.
    outcome = verify_env.get("outcome")
    if outcome == "binding_mismatch":
        reason = verify_env.get("reason")
        if reason == "pr_number_mismatch":
            return ("rejected", "pr_number_mismatch")
        # All other binding drift dimensions (pr_head_sha,
        # evidence_hash, event_id, release_tag, intent_drift) →
        # generic binding_mismatch.
        return ("rejected", "binding_mismatch")
    mapped = _VERIFY_OUTCOME_TO_STOP_CONDITION.get(outcome or "")
    if mapped is not None:
        return ("rejected", mapped)
    # Unknown outcome — the runtime contract bounds outcome to the
    # closed N4a vocabulary, but defense-in-depth: rejected with
    # token_invalid (the broadest closed §7 token-side stop).
    return ("rejected", "token_invalid")


# ---------------------------------------------------------------------------
# Preflight artefact write (post-verification only)
# ---------------------------------------------------------------------------


def _write_preflight_after_verification(
    *,
    pr_number: int,
    pr_head_sha: str,
    token_kid: str,
    nonce_hash: str,
) -> tuple[bool, str | None]:
    """Persist the closed-schema preflight artefact.

    Called ONLY after all of body validation + N4b configuration +
    N4c component presence + token verification + binding checks
    have passed. The projector is sentinel-restricted to
    ``logs/n5b_merge_execution/`` and raises ``ValueError`` /
    ``AssertionError`` / ``OSError`` on any unsafe write or
    credential-shaped string.

    Returns ``(True, None)`` on success or ``(False, "<bounded reason>")``
    on a write failure. The bounded reason is one of
    ``"preflight_write_failed"``; no underlying exception details
    leak.
    """
    try:
        projector.write_preflight(
            pr_number=pr_number,
            pr_head_sha=pr_head_sha,
            token_kid=token_kid,
            nonce_hash=nonce_hash,
            operator_actor=_OPERATOR_ACTOR_SESSION,
            generated_at_utc=_utcnow_iso(),
        )
    except Exception:
        return (False, "preflight_write_failed")
    return (True, None)


# ---------------------------------------------------------------------------
# View function — exactly one route
# ---------------------------------------------------------------------------


def _view_dry_run() -> tuple[Response, int]:
    """POST handler for the token-bound dry-run endpoint walker.

    Walks closed §3 preconditions 1–7 in the order:

    1. Body shape (existing :func:`_validate_body`).
    2. N4b activated (``atr.is_configured()``).
    3. N4c operator UI present (file presence at
       :data:`_N4C_COMPONENT_PATH`).
    4–7. Token verification + binding checks via
       :func:`reporting.approval_token_runtime.verify_runtime_for_dry_run`.

    Writes the preflight artefact ONLY after steps 1–7 all pass.
    No preflight write on body-shape failure, missing N4b,
    missing N4c, invalid token, expired token, replay, or any
    binding mismatch.

    Returns ``not_yet_implemented`` with
    ``preconditions_evaluated=7``, ``preconditions_passed=7``,
    ``reason="preconditions_8_through_17_pending"`` once all
    seven preconditions clear and the preflight artefact is
    written — never ``ok`` (which is reserved for B2.8e after
    preconditions 8–17 also walk).
    """
    # Parse body permissively — silent=True ensures malformed JSON
    # returns None rather than raising 400 with the default Flask
    # handler.
    body: Any = request.get_json(silent=True)
    ok_body, body_reason, pr_number, pr_head_sha = _validate_body(body)
    if not ok_body:
        stop = _BODY_REASON_TO_STOP_CONDITION.get(body_reason or "")
        envelope = _base_envelope(
            status="rejected",
            stop_condition=stop,
            preconditions_evaluated=0,
            preconditions_passed=0,
            would_proceed=False,
            pr_number=pr_number,
            pr_head_sha=pr_head_sha,
            reason=body_reason or "body_invalid",
        )
        return _safe_jsonify(envelope), 400

    # ---- Precondition 1: N4b activated on VPS ----
    if not atr.is_configured():
        envelope = _base_envelope(
            status="configuration_missing",
            stop_condition=None,
            preconditions_evaluated=1,
            preconditions_passed=0,
            would_proceed=False,
            pr_number=pr_number,
            pr_head_sha=pr_head_sha,
            reason="n4b_not_activated",
        )
        return _safe_jsonify(envelope), 200

    # ---- Precondition 2: N4c (or equivalent) operator UI present ----
    if not _N4C_COMPONENT_PATH.is_file():
        envelope = _base_envelope(
            status="configuration_missing",
            stop_condition=None,
            preconditions_evaluated=2,
            preconditions_passed=1,
            would_proceed=False,
            pr_number=pr_number,
            pr_head_sha=pr_head_sha,
            reason="n4c_component_missing",
        )
        return _safe_jsonify(envelope), 200

    # ---- Preconditions 3–7: token verification + bindings ----
    # The dashboard module never reads the env or parses unverified
    # token payloads for trust decisions — verify_runtime_for_dry_run
    # owns both responsibilities.
    body_dict: dict[str, Any] = body  # type: ignore[assignment]
    verify_env = atr.verify_runtime_for_dry_run(
        token=str(body_dict["token"]),
        expected_pr_number=pr_number,
        expected_pr_head_sha=pr_head_sha,
        expected_evidence_hash=str(body_dict["evidence_hash"]),
        expected_intent=_INTENT_LITERAL,
    )
    status, stop_condition = _translate_verify_envelope(verify_env)
    if status != "ok":
        # No preflight write on any verification failure or runtime
        # configuration-missing reading.
        # The verify envelope's metadata is non-existent on
        # non-ok branches by contract, so the walker only echoes
        # the body's pr_number / pr_head_sha back.
        envelope = _base_envelope(
            status=status,
            stop_condition=stop_condition,
            preconditions_evaluated=7 if status == "rejected" else 2,
            preconditions_passed=2,
            would_proceed=False,
            pr_number=pr_number,
            pr_head_sha=pr_head_sha,
            reason=str(verify_env.get("reason") or "")[:_MAX_REASON_LEN] or None,
        )
        return _safe_jsonify(envelope), 200

    # ---- All 7 preconditions passed. Preflight write THEN
    # not_yet_implemented (preconditions 8–17 are out of scope
    # for B2.8c). ----
    token_kid = str(verify_env.get("kid") or "")
    nonce_hash = str(verify_env.get("nonce_hash") or "")
    ok_write, write_reason = _write_preflight_after_verification(
        pr_number=pr_number,
        pr_head_sha=pr_head_sha,
        token_kid=token_kid,
        nonce_hash=nonce_hash,
    )
    if not ok_write:
        # Post-verification write failure: surface as rejected with
        # stop_condition=None and reason=preflight_write_failed.
        # No new §7 stop-condition literal is introduced; the
        # operator inspects the bounded reason field.
        envelope = _base_envelope(
            status="rejected",
            stop_condition=None,
            preconditions_evaluated=7,
            preconditions_passed=7,
            would_proceed=False,
            pr_number=pr_number,
            pr_head_sha=pr_head_sha,
            reason=write_reason,
        )
        return _safe_jsonify(envelope), 500

    envelope = _base_envelope(
        status="not_yet_implemented",
        stop_condition=None,
        preconditions_evaluated=7,
        preconditions_passed=7,
        would_proceed=False,
        pr_number=pr_number,
        pr_head_sha=pr_head_sha,
        reason="preconditions_8_through_17_pending",
    )
    return _safe_jsonify(envelope), 200


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
    """Register the N5b Phase 2 token-bound dry-run walker route.

    **NOT** wired into ``dashboard/dashboard.py`` by B2.8c. The
    two-line wiring change

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
