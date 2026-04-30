# Branch Protection Checklist (`main`)

Settings to apply in **GitHub UI → Settings → Branches → Add branch
protection rule** for `main`. These cannot be configured from repo files; they
require a human with admin permissions.

This is the human-side counterpart of the repo-side governance layer added in
v3.15.15.12. Without these toggles, CODEOWNERS is advisory and hooks can be
bypassed by anyone with direct push access.

---

## Required toggles

- [ ] **Require a pull request before merging.**
  - [ ] Require approvals: **1**.
  - [ ] **Dismiss stale pull request approvals when new commits are pushed.**
  - [ ] **Require review from Code Owners.**
  - [ ] *Optional but recommended:* Require approval of the most recent
        reviewable push.

- [ ] **Require status checks to pass before merging.**
  - [ ] **Require branches to be up to date before merging.**
  - [ ] Required status checks (search and add — names must match the
        `tests.yml` job IDs):
    - [ ] `lint`
    - [ ] `secret-scan`
    - [ ] `typecheck`
    - [ ] `unit`
    - [ ] `regression-fast`
    - [ ] `frontend`
    - [ ] `hook-tests`

- [ ] **Require conversation resolution before merging.**

- [ ] **Require linear history.**

- [ ] **Do not allow bypassing the above settings** (uncheck "Allow specified
      actors to bypass required pull requests").

- [ ] **Restrict who can push to matching branches** — empty (no direct push;
      everyone goes through PR).

- [ ] **Rules applied to administrators** — **enabled** (admin cannot bypass
      either).

- [ ] **Allow force pushes:** **disabled**.

- [ ] **Allow deletions:** **disabled**.

---

## Repository-level settings

In **Settings → General → Pull Requests**:

- [ ] **Allow merge commits:** disabled (linear history above already covers
      it; explicit toggle for clarity).
- [ ] **Allow squash merging:** enabled.
- [ ] **Allow rebase merging:** enabled.
- [ ] **Always suggest updating pull request branches.**
- [ ] **Automatically delete head branches** — operator preference.

In **Settings → General → Features**:

- [ ] **Wikis:** off.
- [ ] **Issues:** on.
- [ ] **Projects:** operator preference.
- [ ] **Sponsorships:** operator preference.

In **Settings → Code security and analysis**:

- [ ] **Dependabot alerts:** enabled.
- [ ] **Dependabot security updates:** enabled.
- [ ] **Dependabot version updates:** enabled (configured via
      `.github/dependabot.yml`; **no auto-merge** per policy).
- [ ] **Secret scanning:** enabled.
- [ ] **Push protection:** enabled.

---

## After enabling

1. Open a noop test PR from a branch and confirm:
   - All required checks fire.
   - CODEOWNERS review is requested automatically.
   - Force-push to `main` fails with a clear message.
2. Check that direct `git push origin main` from a developer machine fails for
   the operator's own account too (this confirms "Rules applied to
   administrators").
3. Record the activation timestamp at the bottom of this file.

---

## Activation log

| date_utc | operator | notes |
|---|---|---|
| (pending) | (pending) | Branch protection not yet enabled. Scheduled morning after this PR exists. |

---

## Related

- [`manual_blockers.md`](manual_blockers.md) — tracks the open status.
- [`permission_model.md`](permission_model.md) — explains where branch
  protection sits in the layered model.
- [`docs/adr/ADR-015-claude-agent-governance.md`](../adr/ADR-015-claude-agent-governance.md)
  — branch protection is the final backstop in the architectural authority
  chain.
