"""N5b Phase 3 — Recorded-fixture simulator endpoint (B2.9c).

POST route module that exposes the B2.9b simulator core to the
operator-facing dashboard. The route consumes a closed-shape
operator-provided fixture on disk, replays the canned merge
response into the closed simulation snapshot, and writes the
``latest.json`` + ``history.jsonl`` audit artefacts. It NEVER
touches GitHub, NEVER opens a network socket, NEVER spawns a
subprocess, NEVER mutates a PR.

Phase 3 path selection: **recorded-fixture simulator**. The
sacrificial-GitHub-repository path is rejected per
``docs/governance/n5b_phase3_implementation_plan.md`` §1.4.

What this module does:

* Accepts exactly one POST route at
  ``/api/agent-control/merge-execution/simulate``.
* Validates the closed §2.3 6-field request body (5 fields
  mirroring B2.8e + ``operator_confirmation_marker`` singleton).
* Reads the two Phase 3 env vars
  ``ADE_N5B_SIMULATOR_ENABLED`` and
  ``ADE_N5B_SIMULATOR_FIXTURE_PATH`` (read-only; never a
  mint/verify secret).
* Verifies the operator-supplied N4b dry-run token via
  :func:`reporting.approval_token_runtime.verify_runtime_for_dry_run`
  — reusing the existing N4b/N4a frozen contract. **No new N4b
  intent is added.**
* Reads and validates the fixture via
  :func:`reporting.n5b_merge_execution_simulate.read_fixture`.
* Builds + writes the closed simulation artefacts via the B2.9b
  projector.
* Returns a closed-envelope response per §2.4 / §2.5.

Hard guarantees (pinned by tests):

* POST only; GET / PUT / PATCH / DELETE return 405.
* No subprocess / network / GitHub / gh / git imports.
* No new N4b intent literal added; the existing
  ``mobile_approval_dispatch`` is reused.
* Phase 4 literals (the production-merge target-classification
  literal, the live-execute env flag, the Phase 4
  execution-artefact ``report_kind``) never appear in this
  source — pinned by negative source-text scans in the
  companion test file.
* The blueprint is **NOT** registered in
  ``dashboard/dashboard.py`` by this module. The 2-line
  operator-applied wiring patch is B2.9d (operator manual,
  B2.0c precedent) — Claude is blocked by
  ``.claude/hooks/deny_no_touch.py`` regardless.
* ``step5_implementation_allowed = Final[False]``;
  ``STEP5_ENABLED_SUBSTAGE = Final["none"]``; Level 6
  permanently disabled.
* No raw token / raw nonce persisted in any artefact.
* On full success the response carries ``status="ok"`` with
  ``would_proceed=True``, ``target_classification=
  "recorded_fixture_simulator"``, ``mode="simulate_only"``, and
  the six dry-run invariants nailed. ``ok`` here means *"dry-run
  checks passed and audit artefacts written"* — NEVER *"merge
  executed"*, *"PR mutated"*, *"deploy triggered"*, *"live
  execution authorized"*.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Final

from flask import Flask, Response, jsonify, request

from reporting import approval_token_runtime as atr
from reporting import n5b_merge_execution_simulate as projector
from reporting.agent_audit_summary import assert_no_secrets

MODULE_VERSION: Final[str] = "v3.15.16.N5b.phase3.simulator_route"
SCHEMA_VERSION: Final[int] = 1


# ---------------------------------------------------------------------------
# Step 5 invariants
# ---------------------------------------------------------------------------

STEP5_ENABLED_SUBSTAGE: Final[str] = "none"
step5_implementation_allowed: Final[bool] = False


# ---------------------------------------------------------------------------
# Closed envelope helpers — mirror the B2.8e walker pattern
# ---------------------------------------------------------------------------

_DISCIPLINE_FIELDS: Final[dict[str, bool | str]] = {
    "step5_implementation_allowed": False,
    "step5_enabled_substage": STEP5_ENABLED_SUBSTAGE,
    "level6_enabled": False,
    "dry_run_only": True,
    "live_merge_implemented": False,
    "deploy_coupled": False,
}

#: Closed simulator-specific invariants attached to every
#: response envelope. Pinned by the behavioural co-occurrence
#: test.
_SIMULATOR_RESPONSE_INVARIANTS: Final[dict[str, bool | str]] = {
    "target_classification": "recorded_fixture_simulator",
    "mode": "simulate_only",
}

#: Closed set of required request body fields per §2.3 of the
#: Phase 3 sub-plan.
_REQUIRED_BODY_FIELDS: Final[tuple[str, ...]] = (
    "pr_number",
    "pr_head_sha",
    "token",
    "intent",
    "evidence_hash",
    "operator_confirmation_marker",
)

#: Pinned literal for the request body ``intent`` field — reused
#: from B2.8e (no new N4b intent).
_INTENT_LITERAL: Final[str] = "mobile_approval_dispatch"

#: Pinned literal for the ``operator_confirmation_marker`` field
#: — singleton; the only accepted value.
_OPERATOR_CONFIRMATION_MARKER_LITERAL: Final[str] = "simulator_execute_confirmed"

#: Bounded request-body caps; defense-in-depth against
#: pathological inputs.
_MAX_PR_HEAD_SHA_LEN: Final[int] = 64
_MAX_TOKEN_LEN: Final[int] = 4096
_MAX_INTENT_LEN: Final[int] = 64
_MAX_EVIDENCE_HASH_LEN: Final[int] = 256
_MAX_OPERATOR_CONFIRMATION_MARKER_LEN: Final[int] = 64
_MAX_REASON_LEN: Final[int] = 200

#: Operator-actor literal for the session-protected route.
_OPERATOR_ACTOR_SESSION: Final[str] = "session"

# ---------------------------------------------------------------------------
# Phase 3 env-var names + fixture default path
#
# These two env vars are read by this dashboard module ONLY.
# Neither is a mint/verify secret. The projector module
# (reporting/n5b_merge_execution_simulate.py) reads neither;
# the caller supplies the fixture as a validated dict.
# ---------------------------------------------------------------------------

#: Operator-set boolean toggle on the live VPS. Accepted values:
#: case-insensitive "true" / "1" / "yes" → ENABLED. Anything
#: else (incl. unset) → DISABLED.
ENV_SIMULATOR_ENABLED: Final[str] = "ADE_N5B_SIMULATOR_ENABLED"

#: Operator-set absolute or repo-relative path to the recorded
#: fixture JSON file. When unset, defaults to
#: :data:`_DEFAULT_FIXTURE_RELATIVE_PATH` resolved relative to
#: the repo root.
ENV_SIMULATOR_FIXTURE_PATH: Final[str] = "ADE_N5B_SIMULATOR_FIXTURE_PATH"

#: Default fixture path (repo-relative). The directory `state/`
#: is gitignored.
_DEFAULT_FIXTURE_RELATIVE_PATH: Final[str] = "state/n5b_simulator_fixture.json"

#: Bounded cap on fixture-path string length to prevent
#: pathological env input. Set generously but bounded.
_MAX_FIXTURE_PATH_LEN: Final[int] = 1024

_REPO_ROOT: Final[Path] = Path(__file__).resolve().parent.parent


def _is_truthy_env(value: str | None) -> bool:
    """Closed truthy-string vocab. Accepts only ``"true"``,
    ``"1"``, ``"yes"`` (case-insensitive). Anything else (incl.
    ``None``) is False."""
    if value is None:
        return False
    lower = value.strip().lower()
    return lower in ("true", "1", "yes")


def _resolve_fixture_path() -> Path:
    """Read the fixture-path env var (or default) and return a
    bounded resolved :class:`pathlib.Path`. Read-only; never
    raises."""
    raw = os.environ.get(ENV_SIMULATOR_FIXTURE_PATH)
    if isinstance(raw, str) and raw.strip():
        candidate = raw.strip()[:_MAX_FIXTURE_PATH_LEN]
        path = Path(candidate)
        if not path.is_absolute():
            path = _REPO_ROOT / path
        return path
    return _REPO_ROOT / _DEFAULT_FIXTURE_RELATIVE_PATH


def _with_discipline(envelope: dict[str, Any]) -> dict[str, Any]:
    """Attach the closed six-field discipline invariants + the
    closed simulator response invariants to ``envelope``."""
    out = dict(envelope)
    out.update(_DISCIPLINE_FIELDS)
    out.update(_SIMULATOR_RESPONSE_INVARIANTS)
    return out


def _safe_jsonify(payload: dict[str, Any]) -> Response:
    """``assert_no_secrets`` then ``flask.jsonify``."""
    assert_no_secrets(payload)
    return jsonify(payload)


def _utcnow_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace(
        "+00:00", "Z"
    )


# ---------------------------------------------------------------------------
# Envelope builders
# ---------------------------------------------------------------------------


def _base_envelope(
    *,
    status: str,
    stop_condition: str | None,
    would_proceed: bool,
    pr_number: int,
    pr_head_sha: str,
    reason: str | None = None,
) -> dict[str, Any]:
    """Build the closed envelope per §2.5 of the sub-plan."""
    envelope: dict[str, Any] = {
        "kind": "agent_control_merge_execution_simulate",
        "schema_version": SCHEMA_VERSION,
        "module_version": MODULE_VERSION,
        "status": status,
        "stop_condition": stop_condition,
        "would_proceed": would_proceed,
        "pr_number": pr_number,
        "pr_head_sha": pr_head_sha,
    }
    if reason is not None:
        envelope["reason"] = reason[:_MAX_REASON_LEN]
    return _with_discipline(envelope)


# ---------------------------------------------------------------------------
# Request body validation
# ---------------------------------------------------------------------------


def _validate_body(
    body: Any,
) -> tuple[bool, str | None, int, str]:
    """Validate the closed §2.3 body shape. Returns
    ``(ok, reason, pr_number, pr_head_sha)``."""
    if body is None:
        return (False, "body_missing", 0, "")
    if not isinstance(body, dict):
        return (False, "body_not_object", 0, "")
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
        return (
            False,
            "field_value:evidence_hash_length",
            pr_number,
            pr_head_sha,
        )

    if "operator_confirmation_marker" not in body:
        return (
            False,
            "field_missing:operator_confirmation_marker",
            pr_number,
            pr_head_sha,
        )
    marker_raw = body["operator_confirmation_marker"]
    if not isinstance(marker_raw, str):
        return (
            False,
            "field_type:operator_confirmation_marker",
            pr_number,
            pr_head_sha,
        )
    if len(marker_raw) > _MAX_OPERATOR_CONFIRMATION_MARKER_LEN:
        return (
            False,
            "field_value:operator_confirmation_marker_length",
            pr_number,
            pr_head_sha,
        )
    if marker_raw != _OPERATOR_CONFIRMATION_MARKER_LITERAL:
        return (
            False,
            "field_value:operator_confirmation_marker_not_pinned",
            pr_number,
            pr_head_sha,
        )

    return (True, None, pr_number, pr_head_sha)


# ---------------------------------------------------------------------------
# View function — exactly one route
# ---------------------------------------------------------------------------


def _view_simulate() -> tuple[Response, int]:
    """POST handler for the Phase 3 simulator endpoint.

    Flow:

    1. Validate body shape.
    2. Check ``ADE_N5B_SIMULATOR_ENABLED`` is truthy → otherwise
       ``configuration_missing``.
    3. Resolve fixture path; check file exists → otherwise
       ``configuration_missing``.
    4. Validate ``operator_confirmation_marker`` literal (already
       enforced by :func:`_validate_body`).
    5. Verify the dry-run N4b token via
       :func:`atr.verify_runtime_for_dry_run`. On any failure →
       ``rejected`` with closed stop_condition.
    6. Read + validate the fixture via
       :func:`projector.read_fixture`. On any failure →
       ``configuration_missing`` with a bounded reason.
    7. Write the simulation artefacts via the B2.9b projector. On
       any write failure → ``rejected`` with HTTP 500 and a
       bounded reason.
    8. On full success → ``status="ok"``, ``would_proceed=True``,
       the closed simulator + discipline invariants nailed.
    """
    body: Any = request.get_json(silent=True)
    ok_body, body_reason, pr_number, pr_head_sha = _validate_body(body)
    if not ok_body:
        envelope = _base_envelope(
            status="rejected",
            stop_condition=None,
            would_proceed=False,
            pr_number=pr_number,
            pr_head_sha=pr_head_sha,
            reason=body_reason or "body_invalid",
        )
        return _safe_jsonify(envelope), 400

    # Env-flag check.
    if not _is_truthy_env(os.environ.get(ENV_SIMULATOR_ENABLED)):
        envelope = _base_envelope(
            status="configuration_missing",
            stop_condition=None,
            would_proceed=False,
            pr_number=pr_number,
            pr_head_sha=pr_head_sha,
            reason="simulator_disabled",
        )
        return _safe_jsonify(envelope), 200

    # Fixture file presence.
    fixture_path = _resolve_fixture_path()
    if not fixture_path.is_file():
        envelope = _base_envelope(
            status="configuration_missing",
            stop_condition=None,
            would_proceed=False,
            pr_number=pr_number,
            pr_head_sha=pr_head_sha,
            reason="fixture_file_missing",
        )
        return _safe_jsonify(envelope), 200

    # Token verification — reuses B2.8e's verify_runtime_for_dry_run.
    # No new N4b intent. Returns the closed envelope shape:
    # {status, outcome, reason, [kid, nonce_hash, event_id, intent on ok]}.
    body_dict: dict[str, Any] = body  # type: ignore[assignment]
    verify_env = atr.verify_runtime_for_dry_run(
        token=str(body_dict["token"]),
        expected_pr_number=pr_number,
        expected_pr_head_sha=pr_head_sha,
        expected_evidence_hash=str(body_dict["evidence_hash"]),
        expected_intent=_INTENT_LITERAL,
    )
    v_status = verify_env.get("status")
    if v_status == "configuration_missing":
        envelope = _base_envelope(
            status="configuration_missing",
            stop_condition=None,
            would_proceed=False,
            pr_number=pr_number,
            pr_head_sha=pr_head_sha,
            reason=str(verify_env.get("reason") or "n4b_configuration_missing")[
                :_MAX_REASON_LEN
            ]
            or None,
        )
        return _safe_jsonify(envelope), 200
    if v_status != "ok":
        outcome = verify_env.get("outcome") or ""
        reason = verify_env.get("reason") or ""
        # Map verify outcomes to the closed §7 stop vocab. The
        # closed mapping mirrors B2.8c's body/verify table.
        if outcome == "replay_detected":
            stop = "replay_detected"
        elif outcome == "binding_mismatch":
            if reason == "pr_number_mismatch":
                stop = "pr_number_mismatch"
            else:
                stop = "binding_mismatch"
        elif outcome in {
            "signature_invalid",
            "malformed_envelope",
            "expired",
            "unknown_kid",
        }:
            stop = "token_invalid"
        elif outcome == "intent_unknown":
            stop = "binding_mismatch"
        else:
            stop = "token_invalid"
        envelope = _base_envelope(
            status="rejected",
            stop_condition=stop,
            would_proceed=False,
            pr_number=pr_number,
            pr_head_sha=pr_head_sha,
            reason=str(reason)[:_MAX_REASON_LEN] or None,
        )
        return _safe_jsonify(envelope), 200

    token_kid = str(verify_env.get("kid") or "")
    nonce_hash = str(verify_env.get("nonce_hash") or "")

    # Fixture read + validation.
    try:
        fixture = projector.read_fixture(fixture_path)
    except (FileNotFoundError, ValueError, TypeError):
        envelope = _base_envelope(
            status="configuration_missing",
            stop_condition=None,
            would_proceed=False,
            pr_number=pr_number,
            pr_head_sha=pr_head_sha,
            reason="fixture_invalid",
        )
        return _safe_jsonify(envelope), 200

    # Artefact write — latest.json + history.jsonl.
    generated_at = _utcnow_iso()
    try:
        projector.write_simulate_latest(
            pr_number=pr_number,
            pr_head_sha=pr_head_sha,
            token_kid=token_kid,
            nonce_hash=nonce_hash,
            operator_actor=_OPERATOR_ACTOR_SESSION,
            operator_confirmation_marker=_OPERATOR_CONFIRMATION_MARKER_LITERAL,
            generated_at_utc=generated_at,
            fixture=fixture,
        )
    except Exception:
        envelope = _base_envelope(
            status="rejected",
            stop_condition="audit_write_failure",
            would_proceed=False,
            pr_number=pr_number,
            pr_head_sha=pr_head_sha,
            reason="simulate_latest_write_failed",
        )
        return _safe_jsonify(envelope), 500
    try:
        projector.append_simulate_history(
            pr_number=pr_number,
            pr_head_sha=pr_head_sha,
            token_kid=token_kid,
            nonce_hash=nonce_hash,
            operator_actor=_OPERATOR_ACTOR_SESSION,
            operator_confirmation_marker=_OPERATOR_CONFIRMATION_MARKER_LITERAL,
            generated_at_utc=generated_at,
            fixture=fixture,
        )
    except Exception:
        envelope = _base_envelope(
            status="rejected",
            stop_condition="audit_write_failure",
            would_proceed=False,
            pr_number=pr_number,
            pr_head_sha=pr_head_sha,
            reason="simulate_history_write_failed",
        )
        return _safe_jsonify(envelope), 500

    # All Phase 3 preconditions satisfied; simulator ran end-to-end.
    # status="ok" + would_proceed=True mean "dry-run checks passed
    # and audit artefacts written" — never live merge authority.
    envelope = _base_envelope(
        status="ok",
        stop_condition=None,
        would_proceed=True,
        pr_number=pr_number,
        pr_head_sha=pr_head_sha,
        reason=None,
    )
    return _safe_jsonify(envelope), 200


# ---------------------------------------------------------------------------
# Route table + register helper
# ---------------------------------------------------------------------------

_MERGE_EXECUTION_SIMULATE_ROUTES: Final[
    tuple[tuple[str, str, Any, str], ...]
] = (
    (
        "/api/agent-control/merge-execution/simulate",
        "POST",
        _view_simulate,
        "agent_control_merge_execution_simulate",
    ),
)


def register_merge_execution_simulate_routes(app: Flask) -> None:
    """Register the N5b Phase 3 simulator route.

    **NOT** wired into ``dashboard/dashboard.py`` by this module.
    The 2-line operator-applied wiring patch is B2.9d (operator
    manual, B2.0c precedent); Claude is blocked from editing
    ``dashboard/dashboard.py`` by
    ``.claude/hooks/deny_no_touch.py`` regardless.

    The eventual wiring patch adds, alongside the existing
    ``register_merge_preflight_routes(app)`` /
    ``register_merge_execution_dry_run_routes(app)`` calls:

    ::

        from dashboard.api_merge_execution_simulate import (
            register_merge_execution_simulate_routes,
        )
        register_merge_execution_simulate_routes(app)
    """
    for path, method, handler, endpoint in _MERGE_EXECUTION_SIMULATE_ROUTES:
        app.add_url_rule(
            path,
            endpoint=endpoint,
            view_func=handler,
            methods=[method],
        )


__all__ = [
    "ENV_SIMULATOR_ENABLED",
    "ENV_SIMULATOR_FIXTURE_PATH",
    "MODULE_VERSION",
    "SCHEMA_VERSION",
    "STEP5_ENABLED_SUBSTAGE",
    "register_merge_execution_simulate_routes",
    "step5_implementation_allowed",
]
