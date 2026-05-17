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

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Final

from flask import Flask, Response, jsonify, request

from reporting import approval_token_runtime as atr
from reporting import n5b_merge_execution_dry_run as projector
from reporting.agent_audit_summary import assert_no_secrets

MODULE_VERSION: Final[str] = "v3.15.16.N5b.phase2.implemented"
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

# ---------------------------------------------------------------------------
# B2.8d walker — upstream artefact paths (READ-ONLY).
#
# The walker reads pre-existing artefacts maintained by the
# operator-paced upstream workloop. The walker NEVER calls ``gh``,
# ``git``, subprocess, sockets, urllib, requests, httpx, or aiohttp
# directly. It NEVER imports ``reporting.github_pr_lifecycle`` (the
# module that produces ``logs/github_pr_lifecycle/latest.json``)
# because that module legitimately uses ``subprocess`` — the walker
# reads its on-disk artefact instead.
#
# Missing / malformed / no-matching-row artefacts fail closed with
# the closed §7 ``network_uncertain`` stop_condition.
# ---------------------------------------------------------------------------

_N5A_ARTIFACT_PATH: Final[Path] = (
    _REPO_ROOT / "logs" / "development_merge_recommendation" / "latest.json"
)
_A22_ARTIFACT_PATH: Final[Path] = (
    _REPO_ROOT / "logs" / "development_pr_lifecycle_observer" / "latest.json"
)
_GITHUB_PR_LIFECYCLE_ARTIFACT_PATH: Final[Path] = (
    _REPO_ROOT / "logs" / "github_pr_lifecycle" / "latest.json"
)

#: Closed canonical mergeStateStatus values that count as "merge is
#: safe to attempt right now". Per §6.3 the adapter accepts only
#: ``CLEAN``. The walker upper-cases A22 values before comparing.
_CLEAN_MERGE_STATES: Final[frozenset[str]] = frozenset({"CLEAN"})

#: Closed canonical check-conclusion values that count as "all
#: required checks green". Per §6.3 the adapter accepts only
#: ``success``-equivalents. A22 emits canonical-cased rollups
#: (``SUCCESS``, ``PASSED``, ``PASSING``).
_GREEN_CHECK_STATES: Final[frozenset[str]] = frozenset(
    {"SUCCESS", "PASSING", "PASSED"}
)

#: Closed N5a recommendation that means "human merge is the
#: appropriate next step". Anything else triggers
#: ``stale_recommendation`` (per the operator-approved §7 semantic
#: stretch — N5a's snapshot is not in the eligible state at
#: evaluation time).
_N5A_ELIGIBLE_ACTION: Final[str] = "recommend_human_merge"
_N5A_ELIGIBLE_REASON: Final[str] = "pr_clean_and_no_blocking_inbox"

#: Bounded freshness window for the N5a recommendation snapshot.
#: Per parent doc §3 row 13 — N5a older than this is flagged with
#: ``stale_recommendation``.
_N5A_FRESHNESS_SECONDS: Final[int] = 60 * 60  # 60 minutes

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


# ---------------------------------------------------------------------------
# Upstream-artefact readers (READ-ONLY; never raise; defense-in-depth)
# ---------------------------------------------------------------------------


def _read_json_artifact(path: Path) -> tuple[str, dict[str, Any] | None]:
    """Return ``(status, payload)`` where ``status`` ∈
    {``"ok"``, ``"absent"``, ``"malformed"``}. Never raises."""
    if not path.is_file():
        return "absent", None
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return "malformed", None
    try:
        data = json.loads(text)
    except (ValueError, json.JSONDecodeError):
        return "malformed", None
    if not isinstance(data, dict):
        return "malformed", None
    return "ok", data


def _find_row_for_pr(
    payload: dict[str, Any], rows_key: str, pr_number: int
) -> dict[str, Any] | None:
    """Locate the row in ``payload[rows_key]`` whose ``pr_number``
    matches. Returns the matched dict, or ``None`` if no match."""
    raw = payload.get(rows_key)
    if not isinstance(raw, list):
        return None
    for row in raw:
        if not isinstance(row, dict):
            continue
        candidate = row.get("pr_number") or row.get("number")
        try:
            if int(candidate or 0) == pr_number:
                return row
        except (TypeError, ValueError):
            continue
    return None


def _parse_iso_utc(value: Any) -> datetime | None:
    """Best-effort ISO-8601 parser. Returns ``None`` on any failure."""
    if not isinstance(value, str) or not value:
        return None
    candidate = value.strip()
    if candidate.endswith("Z"):
        candidate = candidate[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(candidate)
    except ValueError:
        return None


# ---------------------------------------------------------------------------
# B2.8d walker (preconditions 8–17)
# ---------------------------------------------------------------------------


#: Closed seen-fields envelope returned by
#: :func:`_walk_preconditions_8_through_17` so the dry-run artefact
#: can record what the walker observed in the upstream artefacts.
#: Fields default to empty strings / empty dicts when the walker
#: short-circuits before reading them.
_EMPTY_SEEN: Final[dict[str, Any]] = {
    "recommendation_action_seen": "",
    "recommendation_reason_seen": "",
    "merge_state_status_seen": "",
    "required_checks_summary": {"_rollup": ""},
}


def _walk_preconditions_8_through_17(
    *,
    pr_number: int,
    pr_head_sha: str,
) -> tuple[str | None, str | None, int, dict[str, Any]]:
    """Walk parent-doc §3 preconditions 8–17 from the on-disk
    upstream artefacts.

    Returns ``(stop_condition, stop_reason, preconditions_evaluated, seen)``
    where:

    * ``stop_condition`` is ``None`` on full success, or one of the
      closed §6.3 / §7 vocabulary strings on the first failure.
    * ``stop_reason`` is ``None`` on full success, or a bounded
      redacted closed-string describing the failure dimension.
    * ``preconditions_evaluated`` is the number of §3 rows the walker
      reached. On full success this is 17 (rows 8–17 plus the
      auto-pass row 17, added to the 7 rows already evaluated by
      the B2.8c walker outside this function).
    * ``seen`` is a closed dict capturing the upstream-observed
      fields the dry-run artefact records: ``recommendation_action_seen``,
      ``recommendation_reason_seen``, ``merge_state_status_seen``,
      ``required_checks_summary`` (always ``{"_rollup": <A22 summary>}``;
      per-check granularity is a future upstream extension).
      Defaults to :data:`_EMPTY_SEEN` when the walker short-circuits
      before reading the relevant artefact.

    The walker NEVER calls ``gh`` / ``git`` / subprocess / network.
    Every check reads from existing on-disk artefacts via
    :func:`_read_json_artifact`. Missing / malformed / no-matching-row
    artefacts fail closed with ``network_uncertain``.

    For optional B2.8d extended fields on the
    ``logs/github_pr_lifecycle/latest.json`` row
    (``step5_flag_changed``, ``level_6_attempted``,
    ``deploy_coupling_detected``, ``branch_protection_satisfied``,
    ``no_touch_path_violation``), missing fields fail closed with
    ``network_uncertain`` rather than silently auto-passing.
    """
    seen: dict[str, Any] = dict(_EMPTY_SEEN)
    # ---- Read upstream artefacts. Missing / malformed → network_uncertain.
    n5a_status, n5a_payload = _read_json_artifact(_N5A_ARTIFACT_PATH)
    if n5a_status != "ok" or n5a_payload is None:
        return ("network_uncertain", "n5a_artifact_unavailable", 7, seen)
    a22_status, a22_payload = _read_json_artifact(_A22_ARTIFACT_PATH)
    if a22_status != "ok" or a22_payload is None:
        return ("network_uncertain", "a22_artifact_unavailable", 7, seen)
    gh_status, gh_payload = _read_json_artifact(_GITHUB_PR_LIFECYCLE_ARTIFACT_PATH)
    if gh_status != "ok" or gh_payload is None:
        return (
            "network_uncertain",
            "gh_pr_lifecycle_artifact_unavailable",
            7,
            seen,
        )

    n5a_row = _find_row_for_pr(n5a_payload, "rows", pr_number)
    if n5a_row is None:
        return ("network_uncertain", "n5a_row_missing_for_pr", 7, seen)
    a22_row = _find_row_for_pr(a22_payload, "rows", pr_number)
    if a22_row is None:
        return ("network_uncertain", "a22_row_missing_for_pr", 7, seen)
    gh_row = _find_row_for_pr(gh_payload, "prs", pr_number)
    if gh_row is None:
        return (
            "network_uncertain",
            "gh_pr_lifecycle_row_missing_for_pr",
            7,
            seen,
        )

    # Record N5a + A22 seen fields up-front; they're set whether the
    # walker accepts or rejects the row.
    seen["recommendation_action_seen"] = str(
        n5a_row.get("recommendation_action") or ""
    )
    seen["recommendation_reason_seen"] = str(
        n5a_row.get("recommendation_reason") or ""
    )
    seen["merge_state_status_seen"] = str(
        a22_row.get("merge_state_status") or ""
    ).upper()
    seen["required_checks_summary"] = {
        "_rollup": str(a22_row.get("checks_summary") or "").upper()
    }

    # ---- Precondition 8: N5a says eligible.
    rec_action = n5a_row.get("recommendation_action")
    rec_reason = n5a_row.get("recommendation_reason")
    if rec_action != _N5A_ELIGIBLE_ACTION:
        return ("stale_recommendation", "n5a_action_not_eligible", 8, seen)
    if rec_reason != _N5A_ELIGIBLE_REASON:
        return ("stale_recommendation", "n5a_reason_not_eligible", 8, seen)

    # ---- Precondition 9: mergeStateStatus = CLEAN (+ branch protection).
    mss = a22_row.get("merge_state_status")
    if not isinstance(mss, str):
        return ("network_uncertain", "merge_state_status_missing", 9, seen)
    if mss.upper() not in _CLEAN_MERGE_STATES:
        return ("merge_state_not_clean", "merge_state_status_not_clean", 9, seen)
    bp_satisfied = gh_row.get("branch_protection_satisfied")
    if not isinstance(bp_satisfied, bool):
        return ("network_uncertain", "branch_protection_field_missing", 9, seen)
    if not bp_satisfied:
        return (
            "branch_protection_not_satisfied",
            "branch_protection_unsatisfied",
            9,
            seen,
        )

    # ---- Precondition 10: all required checks green.
    checks = a22_row.get("checks_summary")
    if not isinstance(checks, str):
        return ("network_uncertain", "checks_summary_missing", 10, seen)
    if checks.upper() not in _GREEN_CHECK_STATES:
        return ("checks_not_green", "checks_summary_not_green", 10, seen)

    # ---- Precondition 11: current head SHA equals token-bound head SHA.
    observed_head = a22_row.get("head_sha")
    if not isinstance(observed_head, str) or not observed_head:
        return ("network_uncertain", "head_sha_missing_in_a22", 11, seen)
    if observed_head != pr_head_sha:
        return ("head_sha_mismatch", "a22_head_sha_differs_from_bound", 11, seen)

    # ---- Precondition 12: base ref = main.
    base_ref = a22_row.get("base_ref")
    if not isinstance(base_ref, str):
        return ("network_uncertain", "base_ref_missing", 12, seen)
    if base_ref.lower() != "main":
        return ("merge_state_not_clean", "base_ref_not_main", 12, seen)

    # ---- Precondition 13: N5a freshness within bounded window.
    evaluated_at = _parse_iso_utc(n5a_row.get("evaluated_at"))
    if evaluated_at is None:
        return ("network_uncertain", "n5a_evaluated_at_unparseable", 13, seen)
    age = datetime.now(UTC) - evaluated_at
    if age.total_seconds() > _N5A_FRESHNESS_SECONDS:
        return (
            "stale_recommendation",
            "n5a_age_exceeds_freshness_window",
            13,
            seen,
        )

    # ---- Precondition 14: no critical inbox rows.
    try:
        crit = int(n5a_row.get("inbox_critical_count") or 0)
    except (TypeError, ValueError):
        return ("network_uncertain", "inbox_critical_count_unparseable", 14, seen)
    if crit > 0:
        return (
            "stale_recommendation",
            "n5a_reports_inbox_criticals_inconsistency",
            14,
            seen,
        )

    # ---- Precondition 15: no protected-path violations
    # (covers unexpected_files_touched + protected_path_violation +
    # deploy_coupling_detected sub-checks).
    pp_touched = gh_row.get("protected_paths_touched")
    if not isinstance(pp_touched, bool):
        return ("network_uncertain", "protected_paths_field_missing", 15, seen)
    if pp_touched:
        return (
            "unexpected_files_touched",
            "gh_pr_lifecycle_flags_protected_path",
            15,
            seen,
        )
    no_touch_violation = gh_row.get("no_touch_path_violation")
    if not isinstance(no_touch_violation, bool):
        return (
            "network_uncertain",
            "no_touch_path_violation_field_missing",
            15,
            seen,
        )
    if no_touch_violation:
        return (
            "protected_path_violation",
            "gh_pr_lifecycle_flags_no_touch_path",
            15,
            seen,
        )
    deploy_coupling = gh_row.get("deploy_coupling_detected")
    if not isinstance(deploy_coupling, bool):
        return ("network_uncertain", "deploy_coupling_field_missing", 15, seen)
    if deploy_coupling:
        return (
            "deploy_coupling_detected",
            "gh_pr_lifecycle_flags_deploy_coupling",
            15,
            seen,
        )

    # ---- Precondition 16: no Step 5 / Level 6 bypass.
    step5_changed = gh_row.get("step5_flag_changed")
    if not isinstance(step5_changed, bool):
        return ("network_uncertain", "step5_flag_field_missing", 16, seen)
    if step5_changed:
        return (
            "step5_flag_changed",
            "gh_pr_lifecycle_flags_step5_change",
            16,
            seen,
        )
    level_6_attempted = gh_row.get("level_6_attempted")
    if not isinstance(level_6_attempted, bool):
        return ("network_uncertain", "level_6_field_missing", 16, seen)
    if level_6_attempted:
        return ("level_6_attempted", "gh_pr_lifecycle_flags_level_6", 16, seen)

    # ---- Precondition 17: auto-pass (dry-run has no execution boundary).
    # Per operator authority: this is the ONLY precondition auto-passed
    # in B2.8d.

    return (None, None, 17, seen)


# ---------------------------------------------------------------------------
# Failure-artefact write helper
# ---------------------------------------------------------------------------


def _make_cycle_id(*, pr_number: int, generated_at_utc: str) -> str:
    """Derive a cycle_id from pr_number + UTC timestamp. The projector
    additionally charset-validates the result."""
    compact_ts = (
        generated_at_utc.replace("-", "").replace(":", "").replace(".", "")
    )
    return f"pr{pr_number}_{compact_ts}"


def _write_failure_after_walker(
    *,
    pr_number: int,
    pr_head_sha: str,
    stop_condition: str,
    stop_reason: str,
    preconditions_evaluated: int,
    preconditions_passed: int,
    generated_at_utc: str,
) -> tuple[bool, str | None]:
    """Persist the closed-schema failure artefact. Returns
    ``(True, None)`` on success or ``(False, "<bounded reason>")``
    on a write failure."""
    cycle_id = _make_cycle_id(
        pr_number=pr_number, generated_at_utc=generated_at_utc
    )
    try:
        projector.write_failure(
            cycle_id=cycle_id,
            pr_number=pr_number,
            pr_head_sha=pr_head_sha,
            stop_condition=stop_condition,
            stop_reason=stop_reason,
            preconditions_evaluated=preconditions_evaluated,
            preconditions_passed=preconditions_passed,
            operator_actor=_OPERATOR_ACTOR_SESSION,
            generated_at_utc=generated_at_utc,
        )
    except Exception:
        return (False, "failure_write_failed")
    return (True, None)


# ---------------------------------------------------------------------------
# B2.8e dry-run + history writer helpers
# ---------------------------------------------------------------------------


def _build_preconditions_dict(
    *, preconditions_passed: int
) -> dict[str, bool]:
    """Build the closed-shape preconditions dict for the dry-run
    artefact. Each of the 17 entries is True iff that row was
    reached and passed."""
    return {
        f"precondition_{i}": i <= preconditions_passed
        for i in range(1, projector.DRY_RUN_PRECONDITION_COUNT + 1)
    }


def _write_dry_run_artefacts(
    *,
    pr_number: int,
    pr_head_sha: str,
    token_kid: str,
    nonce_hash: str,
    generated_at_utc: str,
    preconditions_passed: int,
    seen: dict[str, Any],
    would_proceed: bool,
    stop_condition: str | None,
) -> tuple[bool, str | None]:
    """Persist the closed-schema ``dry_run/latest.json`` snapshot
    AND append the same row to ``dry_run/history.jsonl``. Called
    only after the walker reaches a decision (``ok`` or ``rejected``).

    Returns ``(True, None)`` on success or ``(False, "<bounded reason>")``
    when either write raises. On any write failure the walker emits
    the closed §7 ``audit_write_failure`` stop_condition; no new
    literal is introduced.
    """
    common_kwargs: dict[str, Any] = {
        "pr_number": pr_number,
        "pr_head_sha": pr_head_sha,
        "token_kid": token_kid,
        "nonce_hash": nonce_hash,
        "operator_actor": _OPERATOR_ACTOR_SESSION,
        "generated_at_utc": generated_at_utc,
        "preconditions": _build_preconditions_dict(
            preconditions_passed=preconditions_passed
        ),
        "recommendation_action_seen": str(
            seen.get("recommendation_action_seen") or ""
        ),
        "recommendation_reason_seen": str(
            seen.get("recommendation_reason_seen") or ""
        ),
        "merge_state_status_seen": str(
            seen.get("merge_state_status_seen") or ""
        ),
        "required_checks_summary": dict(
            seen.get("required_checks_summary") or {"_rollup": ""}
        ),
        "required_checks_granularity": "rollup_only",
        "protected_path_violations": [],
        "protected_path_granularity": "boolean_only",
        "would_proceed": would_proceed,
        "stop_condition": stop_condition,
    }
    try:
        projector.write_dry_run_latest(**common_kwargs)
    except Exception:
        return (False, "dry_run_latest_write_failed")
    try:
        projector.append_dry_run_history(**common_kwargs)
    except Exception:
        return (False, "dry_run_history_append_failed")
    return (True, None)


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

    # ---- All 7 preconditions passed. Write preflight artefact, THEN
    # walk preconditions 8–17 (B2.8d). ----
    token_kid = str(verify_env.get("kid") or "")
    nonce_hash = str(verify_env.get("nonce_hash") or "")
    ok_write, write_reason = _write_preflight_after_verification(
        pr_number=pr_number,
        pr_head_sha=pr_head_sha,
        token_kid=token_kid,
        nonce_hash=nonce_hash,
    )
    if not ok_write:
        # Post-verification preflight-write failure: surface as
        # rejected with stop_condition=None and
        # reason=preflight_write_failed. No new §7 stop-condition
        # literal is introduced; the operator inspects the bounded
        # reason field.
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

    # ---- B2.8d/B2.8e walker for preconditions 8–17 ----
    walker_stop, walker_reason, walker_evaluated, walker_seen = (
        _walk_preconditions_8_through_17(
            pr_number=pr_number,
            pr_head_sha=pr_head_sha,
        )
    )
    walker_now = _utcnow_iso()
    if walker_stop is not None:
        # §7 stop hit. Write the failure artefact (B2.8d) AND
        # the dry_run/latest + history artefacts (B2.8e — per
        # parent-doc §2.6 "every dry-run invocation that produced
        # a decision (ok or rejected)").
        passed_count = walker_evaluated - 1
        write_ok, _write_err = _write_failure_after_walker(
            pr_number=pr_number,
            pr_head_sha=pr_head_sha,
            stop_condition=walker_stop,
            stop_reason=walker_reason or "",
            preconditions_evaluated=walker_evaluated,
            preconditions_passed=passed_count,
            generated_at_utc=walker_now,
        )
        if not write_ok:
            # Failure-artefact write itself failed. Per §7
            # vocabulary, emit audit_write_failure.
            envelope = _base_envelope(
                status="rejected",
                stop_condition="audit_write_failure",
                preconditions_evaluated=walker_evaluated,
                preconditions_passed=passed_count,
                would_proceed=False,
                pr_number=pr_number,
                pr_head_sha=pr_head_sha,
                reason="failure_artefact_write_failed",
            )
            return _safe_jsonify(envelope), 500
        dry_ok, _dry_err = _write_dry_run_artefacts(
            pr_number=pr_number,
            pr_head_sha=pr_head_sha,
            token_kid=token_kid,
            nonce_hash=nonce_hash,
            generated_at_utc=walker_now,
            preconditions_passed=passed_count,
            seen=walker_seen,
            would_proceed=False,
            stop_condition=walker_stop,
        )
        if not dry_ok:
            envelope = _base_envelope(
                status="rejected",
                stop_condition="audit_write_failure",
                preconditions_evaluated=walker_evaluated,
                preconditions_passed=passed_count,
                would_proceed=False,
                pr_number=pr_number,
                pr_head_sha=pr_head_sha,
                reason="dry_run_artefact_write_failed",
            )
            return _safe_jsonify(envelope), 500
        envelope = _base_envelope(
            status="rejected",
            stop_condition=walker_stop,
            preconditions_evaluated=walker_evaluated,
            preconditions_passed=passed_count,
            would_proceed=False,
            pr_number=pr_number,
            pr_head_sha=pr_head_sha,
            reason=walker_reason,
        )
        return _safe_jsonify(envelope), 200

    # ---- All 17 preconditions passed.
    # B2.8e flips the B2.8d deferral: status="ok" + would_proceed=True
    # mean "dry-run checks passed and audit artefacts written".
    # This is a dry-run-only proceed signal — not live merge
    # authority of any kind. Per operator authority on B2.8e §1,
    # the response carries no capability to mutate a PR, execute
    # a merge, trigger a deploy, or authorise live execution.
    #
    # The six discipline invariants on the response envelope stay
    # nailed: dry_run_only=True, live_merge_implemented=False,
    # deploy_coupled=False, level6_enabled=False,
    # step5_implementation_allowed=False, step5_enabled_substage="none".
    # The pinned co-occurrence test
    # (test_b2_8e_would_proceed_true_always_co_occurs_with_dry_run_invariants)
    # enforces these on every "ok" / would_proceed=True response.
    dry_ok, _dry_err = _write_dry_run_artefacts(
        pr_number=pr_number,
        pr_head_sha=pr_head_sha,
        token_kid=token_kid,
        nonce_hash=nonce_hash,
        generated_at_utc=walker_now,
        preconditions_passed=17,
        seen=walker_seen,
        would_proceed=True,
        stop_condition=None,
    )
    if not dry_ok:
        envelope = _base_envelope(
            status="rejected",
            stop_condition="audit_write_failure",
            preconditions_evaluated=17,
            preconditions_passed=17,
            would_proceed=False,
            pr_number=pr_number,
            pr_head_sha=pr_head_sha,
            reason="dry_run_artefact_write_failed",
        )
        return _safe_jsonify(envelope), 500
    envelope = _base_envelope(
        status="ok",
        stop_condition=None,
        preconditions_evaluated=17,
        preconditions_passed=17,
        would_proceed=True,
        pr_number=pr_number,
        pr_head_sha=pr_head_sha,
        reason=None,
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
