# Sequestered Hold-Out Discipline — specification

> **Status:** specification (S5 of the Research-Quality Hardening
> Sprint declared by ADR-018 draft).
>
> **Authority:** governance spec. Declares the hold-out window
> manifest, the hook-enforced read-deny, the red-team review
> process, and the per-candidate single-use guarantee. Does not
> implement runtime code; the implementation lands in a later
> scoped PR.
>
> **Cross-refs:**
> [`roadmap_scope_status.md`](roadmap_scope_status.md),
> [`research_quality_sprint_plan.md`](research_quality_sprint_plan.md)
> §7,
> [`paper_readiness_checklist.md`](paper_readiness_checklist.md),
> [`docs/adr/_drafts/ADR-018-roadmap-execution-reset.md`](../adr/_drafts/ADR-018-roadmap-execution-reset.md),
> [`docs/adr/_drafts/ADR-020-paper-shadow-live-separation.md`](../adr/_drafts/ADR-020-paper-shadow-live-separation.md).

## 1. Purpose

The QRE today reads every available historical window during
research. The hold-out discipline names a window that is **not
read** by any v3.15.x research code — preserved for a single
red-team validation pass at paper-readiness time.

Without sequestration:

- Routing, sampling, diagnostics, and discovery contaminate the
  final OOS validation.
- Hold-out validation degenerates into validation-on-the-same-data.
- Paper-readiness loses its meaning.

The discipline turns the hold-out into a one-shot, single-use,
operator-authorised gate.

## 2. Scope

Applies to:

- Every data path read by `research/`, `reporting/`,
  diagnostics, Hypothesis Discovery, routing, sampling, scoring,
  and any future v3.15.x research surface.
- Every asset class within the declared hold-out window.

Does **not** apply to:

- Live / paper / shadow / broker / execution surfaces. Per
  ADR-020 draft they never feed live anyway, and they have
  their own data governance.
- Operator-driven manual analysis outside the autonomous
  surfaces. Operators may inspect the hold-out for their own
  review; the discipline scopes only the autonomous research
  surface.

## 3. Authority

The hold-out manifest is **canonical authority** for "which
windows are sequestered". Per ADR-014 the manifest joins the
canonical authority mapping for the new domain
`research_holdout_window`:

| Truth domain | Canonical authority |
|---|---|
| "this window is sequestered" | `state/holdout_manifest.v1.json` |
| "this candidate was authorised to read the hold-out" | `logs/holdout_reviews/<window_id>/<candidate_id>.v1.json` |

The hook-enforced read-deny derives directly from the manifest.

## 4. Manifest

The manifest lives at `state/holdout_manifest.v1.json` and is
**operator-authored**. Agents do not modify it; the autonomous
PR runner is denied at the file level.

### 4.1 Top-level shape

```json
{
  "schema_version": 1,
  "module_version": "spec-2026-05-21",
  "generated_at_utc": "<iso8601-utc-seconds>",
  "windows": [ /* see §4.2 */ ]
}
```

### 4.2 Per-window record

| field | type | notes |
|---|---|---|
| `window_id` | string | `holdout_<purpose>_<asset_class>_<year_range>`; unique across the manifest |
| `purpose` | enum | `red_team_paper_promotion` / `red_team_shadow_promotion` / `red_team_live_promotion`; v3.15.x uses only `red_team_paper_promotion` |
| `asset_class` | enum | `crypto` / `equities` / `polymarket`; closed |
| `asset_universe` | array | list of canonical instrument IDs (per ADR-014 / future symbology); ≤ 64 entries |
| `start_utc` | string | RFC3339 UTC inclusive |
| `end_utc` | string | RFC3339 UTC inclusive |
| `frequency_caps` | object | `{"min_bar_seconds": int}` — minimum granularity that is sequestered (e.g. 86400 = daily) |
| `created_by` | string | operator handle |
| `created_at_utc` | string | RFC3339 UTC |
| `notes` | string | ≤ 400 chars |
| `read_authorization_required` | bool | always `true` in v1 |
| `last_authorized_read_ts_utc` | string \| null | populated by the red-team review |
| `last_authorized_reader_kind` | enum \| null | `human_operator` / `automated_review`; `automated_review` is disabled in v3.15.x |
| `last_authorized_candidate_id` | string \| null |
| `last_authorized_review_id` | string \| null | pointer to `logs/holdout_reviews/<window_id>/<review_id>.v1.json` |

### 4.3 Invariants

| ID | Invariant | Enforcement |
|---|---|---|
| HD-I1 | Manifest is operator-authored. No agent / hook / runtime writes to it. | `deny_no_touch` + writer-restricted allowlist; tests pin. |
| HD-I2 | Every `window_id` is unique. | Schema test. |
| HD-I3 | `start_utc <= end_utc`. | Schema test. |
| HD-I4 | `read_authorization_required` is always `true` in v1. | Schema test. |
| HD-I5 | `purpose` is in the closed enum. | Schema test. |
| HD-I6 | A window in `red_team_paper_promotion` may be `last_authorized_read` only when a corresponding `holdout_reviews/<window_id>/<review_id>.v1.json` artifact exists. | Cross-file consistency test. |

## 5. Hook-enforced read-deny

A new hook `deny_holdout_read.py` (planned) runs at
`PreToolUse` for `Read`-like tools.

### 5.1 What it denies

- File reads under any data path whose **content** overlaps the
  hold-out window for any sequestered asset.
- Bulk-read tools (`Glob`, `Grep`) whose pattern would scan
  hold-out data.
- `python` invocations whose argv contains paths that resolve
  into the hold-out window. (Mirrors the existing
  `deny_dangerous_bash.py` pattern.)

### 5.2 What it allows

- All reads outside any declared hold-out window.
- Reads of the manifest itself (the manifest is metadata, not
  data).
- Reads of the review artifacts (operators may inspect prior
  reviews).
- A **single-use, scoped read** during a red-team review, gated
  by an ephemeral authorisation flag (`state/holdout_review.lock`
  or equivalent; the implementation PR pins the path).

### 5.3 Allowed-roots interaction

The hook coexists with the existing
[`deny_outside_agent_allowlist.py`](../../.claude/hooks/deny_outside_agent_allowlist.py).
The hold-out hook is a *subtractive* layer: it can deny what the
allowlist permits; it cannot allow what the no-touch list denies.

### 5.4 Fail-closed

The hook fails closed: any error in manifest parsing, hash
computation, or authorisation-flag inspection denies the read.
This mirrors the existing hook discipline.

## 6. Red-team review process

### 6.1 Pre-conditions

A candidate may enter the hold-out review only when **all** of
the following hold:

- Validation gate chain
  ([`research_quality_kpis.md`](research_quality_kpis.md) §5)
  gates 1-5 passed.
- A `paper_readiness_checklist.v1.json` artifact exists for the
  candidate with every check `yes|n/a` except
  `holdout_redteam_review_pass` (which is still `n/a` because
  the review has not happened).
- Operator authorisation is recorded as an ephemeral
  `state/holdout_review.lock` (or equivalent) naming the
  `candidate_id`, the `window_id`, and a single-use token.

### 6.2 During the review

- The hook reads the authorisation flag and allows scoped reads
  on the named window for the named candidate.
- The review writes a single `holdout_reviews/<window_id>/<review_id>.v1.json`
  artifact recording:
  - candidate_id, window_id, review_id;
  - operator handle;
  - start_ts_utc, end_ts_utc;
  - the candidate's multiplicity-adjusted score on the hold-out;
  - the candidate's cost-adjusted edge on the hold-out;
  - decision: `pass` / `fail` / `inconclusive`;
  - notes (≤ 1000 chars).
- The manifest's `last_authorized_*` fields are updated by the
  operator in the same review PR.

### 6.3 Post-conditions

- The authorisation flag is removed.
- The hook resumes denying reads on the window.
- The `paper_readiness_checklist.v1.json` is regenerated with
  `holdout_redteam_review_pass: yes|no`.
- The candidate proceeds to paper-readiness assessment or is
  rejected, per
  [`paper_readiness_checklist.md`](paper_readiness_checklist.md).

### 6.4 Single-use guarantee

A window may be reviewed for a candidate **at most once**. A
second review of the same `candidate_id` × `window_id` pair
requires an explicit operator-approved exception PR. The hook
denies repeated reads even with a fresh authorisation flag if
the previous review's pass/fail has been recorded.

## 7. What the discipline is NOT

- Not a data licence. Hold-out data licence terms are governed
  by the source manifests, not by this discipline.
- Not a paper-readiness gate by itself. It is **one** gate in
  the chain
  ([`research_quality_kpis.md`](research_quality_kpis.md) §5,
  gate 6).
- Not a deletion mechanism. The hold-out window's data is not
  deleted or quarantined; it is only sequestered from
  autonomous reads.
- Not a substitute for OOS. OOS gates run before the hold-out
  review; the hold-out is the *final* OOS, not the only one.

## 8. Storage layout

| Path | Owner | Content |
|---|---|---|
| `state/holdout_manifest.v1.json` | operator | the manifest (operator-authored) |
| `state/holdout_review.lock` | operator (ephemeral) | active-review authorisation flag |
| `logs/holdout_reviews/<window_id>/<review_id>.v1.json` | review-writing module | per-review record |
| `logs/holdout_reviews/manifest.v1.json` | review-writing module | rolled-up index, regenerated on every review |

## 9. Test plan (for the implementation PR)

- Manifest schema tests (HD-I1 through HD-I6).
- Hook-deny tests covering:
  - data-file reads within a hold-out window;
  - bulk-read tool patterns that include hold-out data;
  - `python` invocations whose argv resolves into the hold-out;
  - reads outside the window (must succeed).
- Authorisation-window lifecycle test: authorisation is
  single-use; second read attempt is denied even with a fresh
  flag if a review is on file.
- Review-artifact schema test.
- Manifest-consistency test (HD-I6: a `last_authorized_*` set
  matches an existing review artifact).
- Hook fail-closed test (corrupted manifest → deny all hold-out
  reads).

## 10. Operator workflow (planned)

1. Operator declares a new hold-out window via a manifest PR.
   The PR is operator-authored; the autonomous runner cannot
   open it.
2. A candidate clears gates 1-5 of the validation chain
   (per [`research_quality_kpis.md`](research_quality_kpis.md)).
3. Operator initiates a red-team review by writing the
   ephemeral authorisation flag.
4. The review module runs scoped reads, writes the review
   artifact, and removes the flag.
5. Operator updates the manifest's `last_authorized_*` fields
   in a follow-up PR.
6. The candidate's paper-readiness checklist regenerates with
   the hold-out gate result.

## 11. Out of scope (for the spec)

- Cryptographic sealing of the hold-out window (a future
  enhancement; v1 relies on hook-deny + manifest authority).
- Multi-operator joint review. v1 supports one operator per
  review.
- Hold-outs for shadow / live (deferred; ADR-022 / ADR-023 will
  add `purpose` enum values).
- Automated review (`last_authorized_reader_kind:
  automated_review` is reserved; not active in v3.15.x).

## 12. Update history

- 2026-05-21: initial version (Research-Quality Hardening Sprint,
  S5 detail spec). Expands
  [`research_quality_sprint_plan.md`](research_quality_sprint_plan.md)
  §7.
