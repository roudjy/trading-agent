# Tooling Intake Policy

> Owner: repo owner + `ci-guardian`, `architecture-guardian`,
> `observability-guardian` agents.
> Linked module: `reporting.proposal_queue` (v3.15.15.19) classifies
> tooling proposals against this policy.

This is the canonical decision rubric for whether a proposed tool /
library / dependency may be integrated **without** routing through
the approval inbox, and what evidence every proposal must carry.

## TL;DR

| classification | examples | route |
|---|---|---|
| **LOW** | dev-only, free, OSS, no telemetry, no signup, no token, MIT / Apache 2.0 / BSD / similar permissive license | safe to integrate as a normal release after the standard review |
| **MEDIUM** | dev-only or runtime-adjacent, free, but lacking explicit free-tool markers | route via the proposal queue, normal review |
| **HIGH** | hosted service, requires signup / API key / OAuth / paid plan / telemetry / SaaS / data egress | route to the approval inbox; `needs_human` |

The classifier in `reporting.proposal_queue._classify_risk` encodes
this rubric. The negation-aware substring check means "no telemetry"
is a LOW marker, not a HIGH trigger.

## When this policy applies

* Any new entry in `frontend/package.json` `dependencies` or
  `devDependencies`.
* Any new entry in `requirements.txt`, `requirements-dev.txt`, or any
  Python environment manifest.
* Any new GitHub Action `uses:` reference (must remain SHA-pinned —
  see `docs/governance/sha_pin_review.md`).
* Any pre-commit hook addition.
* Any container base-image change (these are governed additionally
  by `docs/governance/no_touch_paths.md` — Dockerfile is no-touch).
* Any external SaaS integration (Datadog, Sentry, Segment.io,
  Google Analytics, Datadog APM, etc.) — all default to HIGH.

## Required evidence per proposal

Every tooling proposal must include the following in its rationale
or runbook before integration:

| field | what to capture |
|---|---|
| **purpose** | What problem does this tool solve? Which existing tool is insufficient? |
| **license** | SPDX identifier (e.g. `MIT`, `Apache-2.0`, `BSD-3-Clause`). Reject anything unknown / non-permissive without an explicit ADR. |
| **cost** | Free / paid / freemium. If freemium: explicit confirmation that the project will stay on the free tier. Anything paid → HIGH. |
| **data egress / telemetry** | Does the tool phone home? What data is sent? To which host? Anything non-zero → HIGH. |
| **secrets / accounts** | Any API key, OAuth token, account creation, or signup required? Anything required → HIGH. |
| **runtime vs dev-only** | Is this a `devDependency` only, or does it run in production? Runtime-critical → ADR required. |
| **files changed** | Exact list of files modified by integration (manifests, configs, workflows, lockfiles). |
| **rollback plan** | Concrete revert steps. For pip: `pip uninstall <pkg> && git revert <sha>`. For workflow actions: pin SHA back. For runtime libs: confirm no schema migration. |
| **tests / validation** | Test file(s) covering the new tool's surface, OR an explicit "operator runs `<command>` to validate" line. |
| **owner / review surface** | Which agent / human is the maintenance owner. Default: repo owner + `architecture-guardian` for runtime-critical changes. |

## Hard "no" — never integrate without approval

* External account creation by the agent.
* API keys / OAuth tokens / bearer tokens stored anywhere in repo or
  CI without a documented secret-rotation plan.
* Telemetry, analytics, error reporting that exfiltrates data to a
  third party (Datadog, Sentry, Google Analytics, Segment.io, etc.).
* Paid plans or subscriptions.
* Hosted services that gate on signup.
* Tools that touch live / paper / shadow / trading / risk behavior.
* Tools that weaken governance (CODEOWNERS, branch protection,
  required status checks, secret scanners, gitleaks, frozen contracts).
* Tools that bypass the no-touch hook layer (`.claude/hooks/**`).

## Allowed examples (LOW)

These are illustrative — each one still goes through the proposal
queue and the standard PR review, but carries no HIGH risk class.

* `vite-plugin-pwa` — MIT, dev-only, no telemetry, no signup.
* `ruff` — MIT, dev-only, OSS, no telemetry.
* `prettier` — MIT, dev-only, OSS.
* `pre-commit` — MIT, dev-only, OSS.
* `mypy` / `pytest` / `vitest` — already present; minor / patch
  bumps land via Dependabot, governed by
  [`dependabot_cleanup_playbook.md`](dependabot_cleanup_playbook.md).
* New `@types/*` packages — TypeScript type definitions, dev-only.

## Approval-required examples (HIGH)

* Any APM / observability SaaS (Datadog, New Relic, Honeycomb, etc.).
* Any error-reporting SaaS (Sentry, Bugsnag, etc.).
* Any analytics / telemetry SDK (Segment.io, Google Analytics,
  Mixpanel, etc.).
* Any auth provider that requires hosted-service signup.
* Any hosted database / queue / cache (Redis Cloud, Supabase,
  Firebase, etc.).
* Any feature-flag SaaS (LaunchDarkly, Unleash Cloud, etc.).
* Any AI / ML provider integration that adds a new credential vector
  beyond what `config/config.yaml` already covers.

## Container base-image changes

Container base-image bumps (e.g. `python:3.11-slim` → `python:3.12-slim`)
are a special case:

* `Dockerfile` and `docker-compose.prod.yml` are on the no-touch
  list — agent cannot author these changes directly.
* Always require an ADR with: motivation, compatibility test plan,
  rollback path (digest of previous image), and confirmation that
  the new base image is reproducible (preferably SHA-digest pinned).
* Even with all of the above, the change must land through a
  human-authored PR with `architecture-guardian` review.

## How `proposal_queue` enforces this

The classifier looks at the proposal's title and body for two
disjoint token sets:

* `TOOLING_HIGH_TOKENS`: api key, signup, oauth, telemetry, datadog,
  sentry, segment.io, google-analytics, googletagmanager, hosted
  service, saas, paid plan, subscription.
* `TOOLING_LOW_TOKENS`: dev-only, devdependency, stdlib-only,
  no telemetry, no signup, open source, MIT license, Apache 2.0,
  BSD license.

LOW signals are checked first — so an explicit "no telemetry" /
"no signup" marker never gets re-classified as HIGH by a substring
match on the negated word.

## Synchronization check

When this policy changes:

1. Update `TOOLING_HIGH_TOKENS` / `TOOLING_LOW_TOKENS` in
   `reporting/proposal_queue.py`.
2. Update the parametrized lists in
   `tests/unit/test_proposal_queue.py`
   (`test_tooling_with_secrets_or_telemetry_is_high` and
   `test_tooling_marked_free_dev_only_is_low`).
3. Update the table in `proposal_queue/schema.v1.md`.
4. Open a PR with `architecture-guardian` review (this file lives in
   `docs/governance/` and changes here are governance-shape).
