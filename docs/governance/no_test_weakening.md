# No Test Weakening

A failing test means the system is broken or the assertion is wrong. **Both
of those are real engineering problems** that deserve real engineering fixes,
not workarounds. This policy makes that explicit.

---

## What is forbidden for agents

The hook `deny_test_weakening.py` blocks any Edit/Write under `tests/` that
*introduces* one of:

- `@pytest.mark.skip(...)`
- `@pytest.mark.skipif(...)`
- `@pytest.mark.xfail(...)`
- `pytest.skip(...)` inline
- `pytest.xfail(...)` inline
- `pytest.importorskip(...)`

These are blocked even on otherwise-allowed paths (e.g. inside `tests/unit/`).

Beyond the hook, the policy *also* prohibits these even when the hook would
pass — they are forbidden to humans-via-PR-without-justification too:

- Relaxing an assertion (e.g. changing `assert x == y` to `assert abs(x - y) < 1e-3`)
  to make a previously-failing test pass.
- Regenerating a fixture or golden file because the new code produces different
  output.
- Updating a determinism pin or snapshot digest because the new code produces
  different bytes.

---

## What is *not* forbidden

- Adding a new test that is intentionally skipped on a specific platform (e.g.
  Windows-only API). This is allowed via a `governance-bootstrap` PR with the
  `skip` justified in the PR body and the test file CODEOWNERS-reviewed.
- Marking a brand-new test as `xfail` on day one because the feature is
  in-progress is **also** forbidden — write the test only when the feature
  works.
- Removing a test that genuinely no longer applies (e.g. it tested a removed
  feature). This is an `ask` flow with a clear PR explanation.

---

## Why

This codebase is a deterministic Quant Research Engine with frozen v1 schemas
and byte-stable replay invariants. Determinism pins are *load-bearing* — if a
pin starts failing, that is news, not noise. The temptation to "just regenerate
the pin" turns the entire determinism doctrine into theater.

Similarly, skipping a flaky integration test hides whatever made it flaky.
Either fix the flake (a real engineering problem) or remove the test (an
explicit choice with a paper trail).

---

## When a pin fails

`determinism-guardian` agent reports the failure. It **never** updates the
pin. The operator decides:

1. The new bytes are correct (e.g. a deliberate format change). Human-authored
   ADR amendment + new pin in a CODEOWNERS-reviewed PR.
2. The new bytes are wrong. Find and fix the source of drift; the pin stays.

Either path goes through human review.

---

## When a flake happens

1. Reproduce the flake locally (e.g. `pytest --count 50`).
2. Identify the source of nondeterminism (timestamps, dict ordering, network).
3. Fix it. Tests must be deterministic.
4. If the flake cannot be fixed in the time available, **remove** the test
   (with a PR explanation), do not mark it `xfail`.

---

## Enforcement summary

| Layer | Enforcement | Bypass |
|---|---|---|
| Hook (`deny_test_weakening.py`) | Hard deny at PreToolUse | Hook layer is self-protected |
| Policy (this doc) | Reviewer responsibility | CODEOWNERS-only with PR explanation |
| ADR-015 §test integrity doctrine | Architecture authority | New ADR amendment |

A `governance-bootstrap` PR can bypass the hook *for governance changes*
(e.g. a deliberate one-off skip on Windows). It cannot bypass the policy
itself.
