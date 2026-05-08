"""N1 — ADE Notification Event Taxonomy (pure data + routing).

Pinned, closed-vocabulary lookup module for the ADE Notification &
Mobile Approval Engine. This is the **smallest safe slice (N1)**:
N2 (push engine), N3 (mobile inbox), N4 (approval-token gate), and
N5 (merge/deploy adapter) are NOT implemented and remain BLOCKED at
the design layer.

Hard guarantees (pinned by tests):

* **Pure stdlib only.** No I/O. No subprocess, no network, no
  ``gh``, no ``git``, no ``requests``, no ``urllib``, no ``socket``,
  no ``httpx``, no ``aiohttp``.
* No imports of ``dashboard``, ``frontend``, ``research``,
  ``automation``, ``broker``, ``agent.risk``, ``agent.execution``,
  ``reporting.intelligent_routing``, or any live / paper / shadow /
  trading path.
* **This module emits no notifications.** It mints no tokens. It
  approves nothing. It opens no inbox row. It is a closed-vocabulary
  lookup table plus one pure routing function. Importing this
  module performs zero side-effects and grants zero authority.
* Step 5 invariants are unaffected: importing this module does NOT
  flip ``reporting.development_step5_loop.step5_implementation_allowed``
  and does NOT change ``STEP5_ENABLED_SUBSTAGE``.
* Level 6 stays permanently disabled per ADR-015 §Doctrine 1.

Design anchor: ``docs/governance/notification_engine.md``.

Public surface
--------------

* :data:`EVENT_KINDS`            — closed tuple of event-kind strings.
* :data:`EVENT_SEVERITIES`       — closed tuple of severity strings,
                                   ordered low → high.
* :data:`DECISION_STATES`        — closed tuple of inbox decision-state
                                   strings (used by future N3).
* :data:`EVENT_KIND_DEFAULT_SEVERITY`
                                 — pinned ``event_kind → severity``
                                   default mapping, the routing table.
* :func:`route_for`              — pure deterministic routing function.

Anything outside this surface is private and may change without a
SemVer-style bump.
"""

from __future__ import annotations

from typing import Final

MODULE_VERSION: Final[str] = "v3.15.16.N1"
SCHEMA_VERSION: Final[str] = "1.0"

# ---------------------------------------------------------------------------
# Closed vocabularies
# ---------------------------------------------------------------------------

#: Closed event-kind vocabulary. Adding a value requires a code
#: change pinned by an updated unit test. Order is significant for
#: byte-stable artefacts.
EVENT_KINDS: Final[tuple[str, ...]] = (
    # Queue (A8)
    "queue_item_proposed",
    "queue_item_blocked",
    "queue_item_human_needed",
    # Delegation (A11)
    "delegation_emitted",
    "delegation_blocked",
    # Bugfix loop (A10)
    "bugfix_candidate_proposed",
    "bugfix_candidate_blocked",
    # Roadmap intake (Step 5.0.1)
    "intake_candidate_proposed",
    "intake_candidate_eligible",
    "intake_candidate_blocked",
    # Step 5 dry-run planner (A14)
    "step5_cycle_planned",
    "step5_cycle_halted",
    "step5_cycle_needs_human",
    # Release gate (A9)
    "release_gate_pass",
    "release_gate_fail",
    "release_gate_needs_human",
    # Operational digest / E2E (A12 / A13)
    "operational_digest_emitted",
    "e2e_proof_pass",
    "e2e_proof_fail",
    # PR / merge (future N5; the kind exists in N1 vocab so emitters
    # can reserve it without code change later)
    "pr_lifecycle_event",
    "pr_merge_approval_required",
    "pr_merge_approved",
    "pr_merge_rejected",
    "pr_merge_executed",
    # Deploy (design-only in N5; vocab-only here)
    "deploy_approval_required",
    "deploy_approved",
    "deploy_rejected",
    "deploy_executed",
    # Cross-cutting
    "governance_violation_detected",
    "secret_or_pii_redaction_event",
    "audit_chain_anomaly",
    "unknown_state",
)

#: Closed severity vocabulary, ordered low → high. ``silent`` is the
#: floor (ledger only); ``critical`` is the ceiling (bypasses Do Not
#: Disturb on operator-opted devices).
EVENT_SEVERITIES: Final[tuple[str, ...]] = (
    "silent",
    "digest",
    "push_info",
    "push_action_required",
    "approval_required",
    "critical",
)

#: Closed inbox decision-state vocabulary. Reserved for the N3 mobile
#: approval inbox; pinned here so producers can reference the closed
#: set without taking a dependency on a not-yet-implemented module.
#: ``approved`` and ``rejected`` are writable ONLY through the future
#: N4 approval-token gate. ``superseded`` allows an emitter to
#: invalidate a prior pending row when a fresher row supersedes it.
DECISION_STATES: Final[tuple[str, ...]] = (
    "pending",
    "acknowledged",
    "approved",
    "rejected",
    "expired",
    "superseded",
)


# ---------------------------------------------------------------------------
# Routing table — pinned, deterministic, byte-stable
# ---------------------------------------------------------------------------

#: Pinned default severity per event_kind. Every member of
#: :data:`EVENT_KINDS` MUST appear as a key here. Test
#: ``test_routing_table_covers_all_event_kinds`` enforces it.
EVENT_KIND_DEFAULT_SEVERITY: Final[dict[str, str]] = {
    # Proposals are non-blocking — digest only.
    "queue_item_proposed": "digest",
    "delegation_emitted": "digest",
    "bugfix_candidate_proposed": "digest",
    "intake_candidate_proposed": "digest",
    "operational_digest_emitted": "digest",
    # "Now actionable" — push_info.
    "intake_candidate_eligible": "push_info",
    "release_gate_pass": "push_info",
    "e2e_proof_pass": "push_info",
    "pr_merge_executed": "push_info",
    "deploy_executed": "push_info",
    "pr_merge_approved": "push_info",
    "pr_merge_rejected": "push_info",
    "deploy_approved": "push_info",
    "deploy_rejected": "push_info",
    # Generic PR lifecycle (opened / labelled / ready) — push_info.
    "pr_lifecycle_event": "push_info",
    # Blocks / fails — visible but not gated.
    "queue_item_blocked": "push_info",
    "delegation_blocked": "push_info",
    "bugfix_candidate_blocked": "push_info",
    "intake_candidate_blocked": "push_info",
    # Loop is waiting on the operator — push_action_required.
    "queue_item_human_needed": "push_action_required",
    "step5_cycle_halted": "push_action_required",
    "step5_cycle_needs_human": "push_action_required",
    "release_gate_fail": "push_action_required",
    "e2e_proof_fail": "push_action_required",
    # The fail-safe surface for unknown / malformed upstream state.
    "unknown_state": "push_action_required",
    # Approval-required — gated by future N4 token.
    "release_gate_needs_human": "approval_required",
    "pr_merge_approval_required": "approval_required",
    "deploy_approval_required": "approval_required",
    # Silent (ledger only). step5_cycle_planned is high-volume and
    # boring — operator can pull the digest if interested.
    "step5_cycle_planned": "silent",
    # Critical — bypass DND for operator-opted devices.
    "governance_violation_detected": "critical",
    "secret_or_pii_redaction_event": "critical",
    "audit_chain_anomaly": "critical",
}


#: Severity used when an emitter passes an event_kind that is not in
#: :data:`EVENT_KINDS`. Default-deny: an unknown kind is treated as a
#: gap that the operator must inspect. NEVER ``silent``.
UNKNOWN_EVENT_KIND_FALLBACK_SEVERITY: Final[str] = "push_action_required"


# ---------------------------------------------------------------------------
# Pure routing function
# ---------------------------------------------------------------------------


def route_for(
    event_kind: str,
    *,
    risk_class: str | None = None,
    execution_authority_decision: str | None = None,
) -> str:
    """Return the pinned severity for ``event_kind``.

    Pure, deterministic, side-effect-free. Does not read from disk,
    does not write to disk, does not call the network, does not
    consult any external state.

    Parameters
    ----------
    event_kind:
        One of :data:`EVENT_KINDS`. Anything else is treated as
        unknown and routes to
        :data:`UNKNOWN_EVENT_KIND_FALLBACK_SEVERITY`.
    risk_class:
        Optional risk-class hint (mirrors
        ``reporting.approval_policy.RISK_CLASSES``). When provided as
        ``"HIGH"`` or ``"UNKNOWN"`` it can ESCALATE a non-critical,
        non-approval severity by one step (e.g. ``digest`` →
        ``push_info`` → ``push_action_required``). It can never
        DOWNGRADE a severity below the routing-table default.
    execution_authority_decision:
        Optional upstream-recorded authority decision (mirrors
        ``reporting.execution_authority`` decisions). When the
        decision is ``"NEEDS_HUMAN"`` and the routing-table default is
        below ``approval_required``, the result is escalated to
        ``approval_required``. ``"PERMANENTLY_DENIED"`` escalates to
        ``critical`` if the default is below ``critical``. The
        default is never downgraded.

    Returns
    -------
    str
        A member of :data:`EVENT_SEVERITIES`.

    Notes
    -----
    The escalation rules are intentionally minimal in N1 and pinned
    by ``test_route_for_escalations``. Future tracks (N2–N5) MAY add
    further escalations only via a code change pinned by an updated
    test.
    """
    base = EVENT_KIND_DEFAULT_SEVERITY.get(
        event_kind, UNKNOWN_EVENT_KIND_FALLBACK_SEVERITY
    )

    # Look up severity ordering for the (very small) escalation
    # logic. ``EVENT_SEVERITIES`` is ordered low → high, so a higher
    # tuple index is a stricter severity.
    rank = EVENT_SEVERITIES.index(base)

    def _at_least(idx: int) -> str:
        return EVENT_SEVERITIES[max(rank, idx)]

    push_info_idx = EVENT_SEVERITIES.index("push_info")
    push_action_idx = EVENT_SEVERITIES.index("push_action_required")
    approval_idx = EVENT_SEVERITIES.index("approval_required")
    critical_idx = EVENT_SEVERITIES.index("critical")

    # Risk-class escalations.
    if risk_class == "HIGH":
        # HIGH risk lifts a digest to push_info, otherwise no-op.
        rank = EVENT_SEVERITIES.index(_at_least(push_info_idx))
    elif risk_class == "UNKNOWN":
        # Unknown is never silently OK — push_action_required floor.
        rank = EVENT_SEVERITIES.index(_at_least(push_action_idx))

    # Authority-decision escalations.
    if execution_authority_decision == "NEEDS_HUMAN":
        rank = EVENT_SEVERITIES.index(_at_least(approval_idx))
    elif execution_authority_decision == "PERMANENTLY_DENIED":
        rank = EVENT_SEVERITIES.index(_at_least(critical_idx))

    return EVENT_SEVERITIES[rank]


__all__ = [
    "DECISION_STATES",
    "EVENT_KIND_DEFAULT_SEVERITY",
    "EVENT_KINDS",
    "EVENT_SEVERITIES",
    "MODULE_VERSION",
    "SCHEMA_VERSION",
    "UNKNOWN_EVENT_KIND_FALLBACK_SEVERITY",
    "route_for",
]
