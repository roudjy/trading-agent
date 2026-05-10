# PR Lifecycle Observer — A22 (read-only projector)

> **Status:** Implemented (read-only). A22 is a strict observer of
> the existing `logs/github_pr_lifecycle/latest.json` digest. A22
> **never** calls `gh`. A22 **never** merges, comments, or mutates
> any PR.
>
> **Module:** [`reporting/development_pr_lifecycle_observer.py`](../../reporting/development_pr_lifecycle_observer.py)
>
> **Authority:** development-governance read-only.
> A22 grants ADE no new authority. Level 6 stays permanently
> disabled per ADR-015 §Doctrine 1. **No approval can happen from a
> notification click alone.**

---

## 1. Purpose

A22 is the read-only counterpart to the existing
[`reporting.github_pr_lifecycle`](../../reporting/github_pr_lifecycle.py)
module. The upstream module produces the digest at
`logs/github_pr_lifecycle/latest.json` by calling `gh`; A22 only
reads that artefact and projects each PR into a closed
`observer_classification`.

A22 surfaces *where each open PR sits in its lifecycle* — clean,
blocked, behind base, draft, unstable, or unknown — without itself
opening any network connection. The artefact is consumed by future
A23 (Merge Recommendation), which combines A22 + N3 inbox state
into a recommendation record.

A22 makes **no recommendation** of its own. It classifies PR
state; the decision to act is downstream.

---

## 2. Hard constraints

A22, in this PR and at runtime, must not:

- call `gh`, `git`, `subprocess`, or any network library;
- merge, comment on, or mutate any PR;
- touch `dashboard/dashboard.py`;
- touch `frontend/**`;
- mint approval tokens (N4 territory);
- recommend a merge (A23 territory);
- enable Step 5.1 or Step 5.2;
- flip `step5_implementation_allowed`;
- change `STEP5_ENABLED_SUBSTAGE`;
- change QRE behaviour;
- mutate research artifacts;
- touch live / paper / shadow / risk / broker / execution paths;
- edit `.claude/**`;
- store secrets in repo;
- edit canonical roadmap status fields;
- mark any roadmap phase complete.

---

## 3. Closed vocabularies

### `pr_state` (5 values)

```
OPEN  CLOSED  MERGED  DRAFT  UNKNOWN
```

### `merge_state_status` (8 values; mirrors gh GraphQL)

```
BEHIND  BLOCKED  CLEAN  DIRTY  DRAFT  HAS_HOOKS  UNKNOWN  UNSTABLE
```

### `observer_classification` (8 values)

| Value                       | Meaning                                                                  |
| --------------------------- | ------------------------------------------------------------------------ |
| `open_clean_mergeable`      | open, not draft, `merge_state_status="CLEAN"` — eligible for A23 lookup |
| `open_blocked_or_dirty`     | open but blocked by reviews/hooks or merge conflict                      |
| `open_behind_base`          | open but base branch advanced; needs `update-branch`                     |
| `open_draft`                | draft (or `state="DRAFT"`)                                                |
| `open_unstable`             | open but checks unstable                                                  |
| `open_unknown`              | open with no resolvable merge_state_status                                |
| `closed_or_merged`          | already terminal                                                          |
| `ineligible_shape`          | upstream record didn't parse (rare; emits a warning)                     |

### Per-row schema (16 keys)

```
pr_number  title  head_ref  head_sha  base_ref
state  is_draft  merge_state_status  mergeable  checks_summary
author_login  is_dependabot
observer_classification  url  created_at  updated_at
```

All scalars bounded; no PR body text, no diff, no commit message,
no review comment.

---

## 4. Discipline invariants (emitted on every artefact)

```
calls_gh_cli                        = false
merges_or_comments_on_prs           = false
uses_subprocess_or_network          = false
operator_promotion_required         = true
step5_implementation_allowed        = false
step5_enabled_substage              = "none"
diagnostics_do_not_trade            = true
```

Every emitted snapshot is additionally routed through
[`reporting.agent_audit_summary.assert_no_secrets`](../../reporting/agent_audit_summary.py)
before write.

---

## 5. CLI

```sh
python -m reporting.development_pr_lifecycle_observer --no-write
python -m reporting.development_pr_lifecycle_observer
```

Pure stdlib + `reporting.github_pr_lifecycle` (imported only for
its `MODULE_VERSION` constant; no callable from that module is
invoked) + `reporting.agent_audit_summary.assert_no_secrets`. No
subprocess, no network, no `gh`, no `git`.

---

## 6. Test coverage

Pinned in [`tests/unit/test_development_pr_lifecycle_observer.py`](../../tests/unit/test_development_pr_lifecycle_observer.py):

- closed `PR_STATES`, `MERGE_STATE_STATUSES`,
  `OBSERVER_CLASSIFICATIONS`, `VALIDATION_WARNINGS`, `PR_ROW_KEYS`
  pinned exactly;
- every `merge_state_status` row of §3 maps to the correct
  classification;
- camelCase upstream fields (`headRefOid`, `mergeStateStatus`,
  `isDraft`, `author.login`) coerce correctly to snake_case row;
- absent / unparseable / provider-not-available digests yield
  bounded warning vocab without crash;
- atomic write refuses any path outside
  `logs/development_pr_lifecycle_observer/`;
- AST-level forbidden-import scan: no `dashboard`, `frontend`,
  `automation`, `broker`, `agent.risk`, `agent.execution`,
  `research`, `reporting.intelligent_routing`, `live`, `paper`,
  `shadow`, `trading`;
- source-text scan: no `subprocess`, `socket`, `urllib`, `requests`,
  `httpx`, `aiohttp`, `gh`, `git`, no calls to upstream gh-using
  functions (`list_open_prs`, `pr_inspect`, `merge_squash`, etc.);
- importing the module does not flip Step 5 invariants.

---

## 7. What A22 does NOT do

- A22 never calls `gh`.
- A22 never merges or comments on a PR.
- A22 never recommends a merge — that's A23.
- A22 never opens a network socket.
- A22 does not change Step 5.0 logic.
- A22 does not flip `step5_implementation_allowed`.
- A22 does not change `STEP5_ENABLED_SUBSTAGE`.
- Step 5.1 / Step 5.2 remain BLOCKED.
- A18 / N2b-3b / N3 (live wiring) / N4 (live wiring) / N5 (merge
  adapter) / deploy adapter all remain unimplemented.
- Level 6 stays permanently disabled.
