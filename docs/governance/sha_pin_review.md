# SHA-Pin Review (Monthly)

GitHub Actions are pinned by 40-character commit SHA in every workflow
file (per ADR-015 §Doctrine 6 — provenance integrity). Tags float;
SHAs do not. The monthly review keeps the pins fresh against upstream
security fixes without giving up immutability.

---

## Cadence

Once per calendar month, on the first Monday or as soon afterwards as
the operator has a quiet window. Logged in
`docs/governance/sha_pin_reviews/<YYYY-MM>.md`.

## Procedure

1. **Enumerate pins** in every workflow:
   ```sh
   grep -RnE 'uses:\s+[A-Za-z0-9_./-]+@[0-9a-f]{40}' .github/workflows/
   ```

2. **Resolve the latest stable tag for each action.** Use the action's
   release page or:
   ```sh
   gh api repos/<owner>/<action>/git/refs/tags | jq '.[] | .ref'
   ```

3. **For each action**, compare current pin vs latest tag's SHA. If a
   newer SHA exists:
   - Read the changelog between the two for breaking changes / security
     fixes.
   - If safe to upgrade, propose the bump in a `governance-bootstrap`
     PR (or accept dependabot's PR if it has already opened one).
   - If breaking, file a backlog item in `docs/backlog/agent_backlog.md`
     and skip this round.

4. **Log the review** at
   `docs/governance/sha_pin_reviews/<YYYY-MM>.md`:
   ```
   | action | current_sha | latest_sha | decision | notes |
   ```

5. **Confirm `actions_pinned=true`** in build provenance for the next
   build after the review.

## Skip rules

A review may declare `no changes` for an action if:

- The current pin is already the latest stable tag.
- A newer tag exists but is `prerelease` or `draft`.
- A newer tag exists but the changelog flags it as breaking and the
  ci-guardian agent has not yet completed an impact assessment.

`no changes` is logged with a one-line reason; the row still appears.

## Authority

The `ci-guardian` agent is the only agent allowed to propose pin bumps,
and only inside a dedicated `ci-hardening` task (per its frontmatter).
Humans may also do this manually.

## What if a pin gets out of date for ≥3 months?

That is a `P1` backlog item. The operator's call is whether to skip a
month for legitimate reasons or whether the review has stalled. Three
consecutive `no changes` rows for the same action without a reason is
a soft regression flag; ci-guardian will surface it in its monthly
report.

## Cross-references

- ADR-015 §Doctrine 6
- [`agent_backlog.md`](../backlog/agent_backlog.md) — backlog item
  AB-0006 covers the first review.
