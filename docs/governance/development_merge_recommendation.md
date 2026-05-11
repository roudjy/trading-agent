# Merge Recommendation — A23 (read-only projector)

> **Status:** Implemented (read-only, projector-only).
>
> **Module:** [`reporting/development_merge_recommendation.py`](../../reporting/development_merge_recommendation.py)
> **Output artefact:** `logs/development_merge_recommendation/latest.json`
>
> **Authority:** development-governance read-only.
> A23 NEVER merges. A23 NEVER calls `gh`. A23 NEVER mints an
> approval token. A23 NEVER executes any approve/reject decision.
> Mobile approval is human approval, not autonomous merge or deploy.
> Level 6 stays permanently disabled per ADR-015 §Doctrine 1.
> **No approval can happen from a notification click alone.**

---

## 1. Purpose

A23 is the **recommendation surface** of the merge-flow stack. It
joins:

- **A22** PR-lifecycle observer at
  `logs/development_pr_lifecycle_observer/latest.json` — provides
  the closed `observer_classification` per open PR;
- **N3a** mobile-approval-inbox at
  `logs/mobile_approval_inbox/latest.json` — provides aggregate
  attention counts;

…and emits a per-PR recommendation record with a closed
`recommendation_action` and `recommendation_reason`. The record
is consumed by:

- the operator, manually;
- the future N5 merge adapter (operator-action-only, deferred);

…to *inform* whether a human should now merge a PR. A23 makes a
**suggestion**, never a decision.

---

## 2. Hard constraints

A23, in this PR and at runtime, must not:

- merge any PR;
- call `gh`, `git`, `subprocess`, or any network library;
- mint or verify approval tokens (N4 territory);
- execute an approve / reject decision (N4 + N5 territory);
- deploy anything;
- send any real push (N2b-3b territory);
- register a Flask blueprint or wire into `dashboard/dashboard.py`;
- touch `frontend/**`;
- mutate any upstream artefact;
- edit canonical roadmap status fields;
- mark any roadmap phase complete;
- enable Step 5.1 or Step 5.2;
- flip `step5_implementation_allowed`;
- change `STEP5_ENABLED_SUBSTAGE`;
- change QRE behaviour;
- mutate research artifacts;
- touch live / paper / shadow / risk / broker / execution paths;
- edit `.claude/**`;
- store secrets in repo.

A23 ships its own AST-level forbidden-import scan and source-text
scans to enforce the relevant bullets.

---

## 3. Closed vocabularies

### `recommendation_action` (5 values)

| Value                       | Meaning                                                                             |
| --------------------------- | ----------------------------------------------------------------------------------- |
| `recommend_human_merge`     | open + clean + no blocking inbox attention — operator can squash-merge if they want |
| `recommend_human_review`    | open + clean but the inbox surfaces attention (critical/blocked/needs_review)       |
| `recommend_no_action`       | closed/merged or draft — there is nothing to do here                                |
| `recommend_update_branch`   | open + behind base — operator should run `gh pr update-branch`                      |
| `recommend_hold`            | open but blocked/dirty/unstable/unknown — hold until upstream resolves              |

**Critical design choice:** none of these values uses the literal
token `approve` or `merge` or `deploy` as a *verb*. A23's
recommendation language is consistently "recommend the human to do
X" — never "approve / merge / deploy this PR". Pinned by source-text
test (`test_recommendation_actions_avoid_decision_verb_in_value`).

### `recommendation_reason` (12 values, closed)

```
pr_clean_and_no_blocking_inbox
pr_clean_but_inbox_has_blocked_attention
pr_clean_but_inbox_has_critical_attention
pr_clean_but_inbox_has_needs_review
pr_closed_or_merged
pr_open_but_draft
pr_behind_base_branch
pr_blocked_or_dirty
pr_unstable_checks
pr_unknown_state
no_upstream_signal
ineligible_pr_shape
```

### Per-row schema (12 keys, exact and ordered)

```
recommendation_id  pr_number  head_sha  head_ref  base_ref
observer_classification
inbox_blocked_count  inbox_critical_count  inbox_needs_review_count
recommendation_action  recommendation_reason  evaluated_at
```

`recommendation_id = "mr_<pr_number>_<head_sha_prefix_12>"` — id
changes when the head advances, which is the right semantics: a new
head means the recommendation needs re-evaluation against the
updated branch.

---

## 4. Decision rules (closed table; first match wins)

| # | Condition (observer_classification)                              | Outcome                                                       |
| - | ---------------------------------------------------------------- | ------------------------------------------------------------- |
| 1 | `closed_or_merged`                                               | `recommend_no_action` / `pr_closed_or_merged`                 |
| 2 | `open_draft`                                                      | `recommend_no_action` / `pr_open_but_draft`                   |
| 3 | `open_blocked_or_dirty`                                           | `recommend_hold` / `pr_blocked_or_dirty`                      |
| 4 | `open_unstable`                                                   | `recommend_hold` / `pr_unstable_checks`                       |
| 5 | `open_behind_base`                                                | `recommend_update_branch` / `pr_behind_base_branch`           |
| 6 | `open_unknown` or `ineligible_shape`                              | `recommend_hold` / `pr_unknown_state`                         |
| 7 | `open_clean_mergeable` AND `inbox_critical_count > 0`             | `recommend_human_review` / `pr_clean_but_inbox_has_critical_attention` |
| 8 | `open_clean_mergeable` AND `inbox_blocked_count > 0`              | `recommend_human_review` / `pr_clean_but_inbox_has_blocked_attention` |
| 9 | `open_clean_mergeable` AND `inbox_needs_review_count > 0`         | `recommend_human_review` / `pr_clean_but_inbox_has_needs_review` |
| 10 | `open_clean_mergeable` AND inbox clean                           | **`recommend_human_merge`** / `pr_clean_and_no_blocking_inbox` |
| 11 | default-deny                                                     | `recommend_hold` / `no_upstream_signal`                       |

The *only* path to a `recommend_human_merge` outcome is rule 10:
PR is clean AND inbox has zero blocking/critical/review-warranting
attention. Even then, the recommendation is to a **human** — A23
does not invoke the merge adapter (which doesn't exist yet) and is
forbidden from touching `gh`.

---

## 5. Discipline invariants (emitted on every artefact)

```
calls_gh_cli                                  = false
merges_or_deploys                             = false
mints_approval_token                          = false
verifies_approval_token                       = false
executes_approve_or_reject                    = false
sends_real_push                               = false
registers_flask_blueprint                     = false
uses_subprocess_or_network                    = false
operator_promotion_required                   = true
step5_implementation_allowed                  = false
step5_enabled_substage                        = "none"
diagnostics_do_not_trade                      = true
no_approval_from_notification_click_alone     = true
```

Every emitted snapshot is additionally routed through
[`reporting.agent_audit_summary.assert_no_secrets`](../../reporting/agent_audit_summary.py)
before write.

---

## 6. CLI

```sh
python -m reporting.development_merge_recommendation --no-write
python -m reporting.development_merge_recommendation
```

Pure stdlib + read-only ADE deps. No subprocess, no network,
no `gh`, no `git`.

---

## 7. Authority chain summary

| Capability                                              | Today (post-N3a) | After A23                                | After N4b (future, operator-authored) | After N5 (future, operator-authored) |
| ------------------------------------------------------- | ---------------- | ---------------------------------------- | --------------------------------------- | ------------------------------------- |
| Read A22 PR observer                                    | yes              | unchanged                                | unchanged                               | unchanged                             |
| Read N3a inbox                                          | yes              | unchanged                                | unchanged                               | unchanged                             |
| Emit recommendation record                               | does not exist   | yes — A23 read-only                      | unchanged                               | unchanged                             |
| Mint approval token                                      | does not exist   | does not exist                           | yes — operator-env-only                 | unchanged                             |
| Execute approve / reject                                 | does not exist   | does not exist                           | does not exist                          | yes — bounded merge adapter, operator-token-gated |
| Autonomous merge / deploy                                | forbidden, Level 6 | unchanged — Level 6 permanently disabled | unchanged                               | unchanged                             |

A23 grants ADE **zero** new authority. The recommendation is
information, not authority.

---

## 8. Test coverage

Pinned in [`tests/unit/test_development_merge_recommendation.py`](../../tests/unit/test_development_merge_recommendation.py):

- closed `RECOMMENDATION_ACTIONS` (5), `RECOMMENDATION_REASONS` (12),
  `VALIDATION_WARNINGS` (5), `RECOMMENDATION_ROW_KEYS` (12) pinned
  exactly;
- **no recommendation action contains the literal verb `approve` /
  `merge` (as a standalone verb) / `deploy`** — pinned by
  `test_recommendation_actions_avoid_decision_verb_in_value`;
- every rule row of §4 evaluates correctly;
- `recommendation_id` is stable for the same (pr_number, head_sha)
  and changes when the head advances;
- atomic write refuses any path outside
  `logs/development_merge_recommendation/`;
- AST-level forbidden-import scan: no `dashboard`, `frontend`,
  `automation`, `broker`, `agent.risk`, `agent.execution`,
  `research`, `reporting.intelligent_routing`, `live`, `paper`,
  `shadow`, `trading`;
- source-text scan: no `subprocess`, `socket`, `urllib`,
  `requests`, `httpx`, `aiohttp`, `gh`, `git`;
- source-text scan: no Flask blueprint registration
  (`add_url_rule` / `register_blueprint` absent);
- importing the module does not flip Step 5 invariants;
- this doc states "no approval from notification click alone" and
  "Level 6 stays permanently disabled".

---

## 9. What A23 does NOT do

- A23 never merges any PR.
- A23 never calls `gh`.
- A23 never mints or verifies an approval token.
- A23 never approves or rejects anything.
- A23 never deploys.
- A23 never sends a real push.
- A23 never registers a Flask blueprint.
- A23 never writes to `dashboard/dashboard.py` or `frontend/**`.
- A23 never writes to any seed file.
- A23 never edits canonical roadmap status fields.
- A23 does not flip `step5_implementation_allowed`.
- A23 does not change `STEP5_ENABLED_SUBSTAGE`.
- Step 5.1 / Step 5.2 remain BLOCKED.
- N3b / N3c / N4 (live) / N5 / deploy adapter remain
  unimplemented.
- Level 6 stays permanently disabled.
