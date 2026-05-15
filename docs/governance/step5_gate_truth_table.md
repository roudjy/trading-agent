# Step 5 Gate Truth Table

> **Status: canonical_policy_doc / inspection only.** Precondition
> to any future Step 5.2 runtime activation (B2.4b / B2.3 / B2.5 in
> Revised Batch 2). This document **proves the current
> architectural state** of Step 5.2 runtime reachability by direct
> file/line citation. It does **not** propose a flip, does **not**
> authorise any runtime change, does **not** remove any `Final`
> annotation, and does **not** introduce any env flag.
>
> Written 2026-05-15 against `main @ b19197b` (post-B2.0e). The
> companion additive pin tests live in
> `tests/unit/test_development_step5_loop.py` (B2.4a tests).

---

## §1 Purpose

This document delivers the audit the operator brief required for
B2.4a:

1. Document the closed truth table over the five gating dimensions
   `(step5_implementation_allowed, STEP5_ENABLED_SUBSTAGE,
   ADE_STEP5_5_2_ENABLED, target_repo_pin, operator_invocation)`.
2. Prove the current architectural state of Step 5.2 runtime
   reachability by direct file/line citation.
3. Identify exactly what source-level changes (if any) would make
   Step 5.2 runtime architecturally reachable.
4. Provide the audit that any future B2.4b activation PR must
   reference.

**This document does not decide between the two possible operator
outcomes.** The operator reads the truth table, then chooses
out-of-band whether to keep
`step5_implementation_allowed` permanently `Final[False]` or to
authorise a future governance-amendment sequence.

---

## §2 Anchoring documents

- [`docs/adr/ADR-015-claude-agent-governance.md`](../adr/ADR-015-claude-agent-governance.md) §Doctrine 1 (Level 6 permanently disabled) and §Doctrine 7 (self-protected layer).
- [`docs/adr/ADR-017-step5-autonomous-implementation-loop.md`](../adr/ADR-017-step5-autonomous-implementation-loop.md) (Accepted).
- [`docs/governance/step5_design.md`](step5_design.md) §1 (definition), §5 (allowed surfaces), §8.3 (artefact schema), §12 (G1–G12 readiness gates), §13 (first slice proposal).
- [`docs/governance/autonomy_ladder.md`](autonomy_ladder.md) (L0–L6 ceiling).
- [`docs/governance/no_touch_paths.md`](no_touch_paths.md).
- [`docs/governance/execution_authority.md`](execution_authority.md).
- [`docs/governance/development_step5_loop.md`](development_step5_loop.md) (A14 Step 5.0 dry-run canonical doc).
- [`docs/roadmap/autonomous_development.txt`](../roadmap/autonomous_development.txt) §A14 (Step 5.0 tests-first preparation), §A15 (Agent Activity Center anchor).

---

## §3 Inspected ground truth (file/line citations)

Every claim in this section was verified by direct file read on `main @ b19197b`. The companion B2.4a pin tests in `tests/unit/test_development_step5_loop.py` enforce these properties so future PRs cannot silently drift.

### 3.1 `STEP5_ENABLED_SUBSTAGE` — module-level `Final[str]` constant

- **File**: `reporting/development_step5_loop.py`
- **Line**: 102
- **Source**: `STEP5_ENABLED_SUBSTAGE: Final[str] = "none"`
- **Annotation**: `Final[str]` — load-bearing.
- **Default value**: `"none"` — default-deny.
- **All reference sites in the module**: lines 350, 382, 426. Every site is **emit-context only** — the constant is written into the snapshot payload as metadata.
- **Branch sites in the module**: **zero**. The constant is never the test-expression of an `if`, `while`, or `assert`. Pinned by the new B2.4a AST test.

### 3.2 `step5_implementation_allowed` — module-level `Final[bool]` constant

- **File**: `reporting/development_step5_loop.py`
- **Line**: 138
- **Source**: `step5_implementation_allowed: Final[bool] = False`
- **Annotation**: `Final[bool]` — load-bearing.
- **Default value**: `False` — hard global deny.
- **All reference sites in the module**: lines 351, 383, 427. Every site is **emit-context only**.
- **Branch sites in the module**: **zero**. Pinned by the new B2.4a AST test.

### 3.3 Operational digest's independent hard pin

- **File**: `reporting/development_operational_digest.py`
- **Line**: 378
- **Source**: `"step5_implementation_allowed": False,` (hard-coded literal in `_evaluate_step5(...)`'s return dict).
- **Effect**: the digest returns `step5_implementation_allowed: False` regardless of upstream artefact state. This is a **second, independent** hard pin — separate from the module-level constant in §3.2.

### 3.4 `ADE_STEP5_5_2_ENABLED` env flag — does not exist

Verified by recursive grep across:
- `reporting/`
- `scripts/`
- `dashboard/`
- `tests/unit/`
- `.claude/`

**Result: zero matches.** No code reads such an env flag today. Pinned by the new B2.4a source-text test.

### 3.5 `git` / `gh` / `subprocess` / network in the Step 5 module

- AST-pinned absence of imports: `subprocess`, `socket`, `urllib`, `urllib.request`, `urllib.parse`, `requests`, `urllib3`, `httpx`, `aiohttp` — see [`tests/unit/test_development_step5_loop.py`](../../tests/unit/test_development_step5_loop.py) `FORBIDDEN_IMPORT_PREFIXES` (line 85).
- Source-text absence of `os.system(`, `os.popen(`, `subprocess.run(`, `subprocess.Popen(`, `gh pr merge`, `git push origin main`.
- `_atomic_write_json` refuses every path outside `logs/step5_*/`.

The module is **architecturally incapable** of opening a network socket, spawning a child process, or invoking `git`/`gh`. No env flag, substage cap flip, or operator phrase can change this without a source-level rewrite.

### 3.6 Operator invocation channel

The operator invocation channel exists today as:

- ADR-015 §Doctrine 7 governance-bootstrap PR body authorisation (signed in writing).
- No automated channel.

The visual control plane (B2.0 / B2.0a–e) surfaces `required_phrase` as **read-only data** from upstream artefacts; it never issues a phrase as an authority token. The push-body safety lint (B2.0e) blocks operator-go-phrase literals from appearing in any push surface.

### 3.7 Target-repo pin

Verified absent. No constant binds Step 5 to any target repository. Any future Step 5.2 runtime would need to introduce a source-pinned target-repo identifier (currently nonexistent). This is intentional — the Step 5.0 dry-run never opens PRs.

---

## §4 Closed truth table

The table below enumerates all dimension combinations relevant to Step 5.2 runtime activation. Rows 1–4 reflect what the source code currently does or could do with cosmetic flips only. Row 5 reflects what would require a source-level rewrite.

| # | `step5_implementation_allowed` (source) | `STEP5_ENABLED_SUBSTAGE` (source) | `ADE_STEP5_5_2_ENABLED` env | target_repo_pin | operator_invocation | Step 5.2 runtime allowed? |
|---|---|---|---|---|---|---|
| 1 | `Final[bool] = False` | `Final[str] = "none"` | unset | absent | absent | **NONE** — current state on `main @ b19197b`. Step 5.0 dry-run only. |
| 2 | `Final[bool] = False` | `Final[str] = "5.2"` (hypothetical) | unset | absent | absent | **NONE** — the substage constant has no runtime consumer (§3.1 branch count = 0). Flipping it changes metadata only. |
| 3 | `Final[bool] = False` | `Final[str] = "5.2"` | `"true"` | absent | absent | **NONE** — `ADE_STEP5_5_2_ENABLED` is not read by any code today (§3.4). Even if introduced, the implementation-allowed constant remains `Final[False]` at the source layer (§3.2). |
| 4 | `Final[bool] = False` | `Final[str] = "5.2"` | `"true"` | sacrificial | required phrase issued | **NONE** — same reason as row 3. The `Final[False]` boolean is a hard global deny that no runtime input can override. |
| 5 | `bool = False` (would require **Final removal** + new value-binding code) | `Final[str] = "5.2"` | `"true"` | sacrificial | required phrase issued | **Open question** — see §6 Path C. Currently the source treats this as architecturally and doctrinally forbidden. |

**Rows 1–4 prove that no combination of cosmetic flips changes Step 5.2 runtime reachability.** The load-bearing gate is the `Final` annotation on `step5_implementation_allowed`, not the substage cap or any env flag.

---

## §5 Conclusion: Step 5.2 runtime is currently architecturally unreachable

The truth table makes the architectural state explicit:

- **Row 1 (current state)**: Step 5.2 runtime is unreachable. The Step 5.0 module writes only to `logs/step5_*/`, never invokes `git`/`gh`/`subprocess`, and never reads either gating constant as a branch.
- **Rows 2–4**: Step 5.2 runtime remains unreachable under any combination of substage cap flip, env flag flip, target-repo pin addition, or operator phrase issuance — because **no runtime gate consumes any of these inputs**. The constants are metadata-only.
- **Row 5**: Step 5.2 runtime would require:
  1. Removing the `Final` annotation from `step5_implementation_allowed`.
  2. Adding new runtime code that consumes the combined gate.
  3. A coordinated ADR-015 / ADR-017 amendment.
  4. Readiness-gate G1–G12 reverification per step5_design.md §12.

This is a **non-trivial source rewrite plus a multi-document governance amendment**, not a cosmetic constant flip.

The architectural state of `step5_implementation_allowed = Final[False]` is the load-bearing gate. **Flipping the substage cap or adding an env flag without removing `Final` would change emitted metadata but not behaviour.**

---

## §6 Three hypothetical activation paths

This section enumerates the three paths a future B2.4b activation PR could take. **This document does not authorise any of them.** It documents them so the operator can choose out-of-band.

### Path A — substage-cap flip only

- **Source change**: `STEP5_ENABLED_SUBSTAGE: Final[str] = "5.2"`.
- **Runtime effect**: **none**. The constant is read only by the `_build_*_payload` helpers to emit metadata. No `if` branch reads it (§3.1 branch count = 0).
- **Conclusion**: Path A is a **NO-OP**. It must **not** be proposed as B2.4b. Any PR that ships only this flip and claims runtime reachability is incorrect.

### Path B — env-flag-driven runtime gate (requires source rewrite)

- **Source changes**:
  1. Add a new helper `_runtime_substage_active() -> str` that returns the lesser of `STEP5_ENABLED_SUBSTAGE` and a new env-derived cap (e.g. `os.environ.get("ADE_STEP5_5_2_ENABLED")` mapped through a closed-vocab parse).
  2. Add conditional branches in `collect_snapshot` / `write_outputs` guarded on this helper.
- **Implication**: the substage cap becomes runtime-effective **only when both** the source constant is flipped to `"5.2"` AND the env flag is set on the runtime host. `step5_implementation_allowed` would remain `Final[False]` — the runtime gate would emit a `would_*` plan shape, not a real PR.
- **Conclusion**: Path B is a **multi-PR sequence**:
  - **B-1**: add the runtime-gate helper (no behaviour change yet; pinned by tests that fire when both gates are off).
  - **B-2**: ship Step 5.1 / Step 5.2 dry-run additive schema (already planned as B2.1 / B2.2 in Revised Batch 2).
  - **B-3**: flip the source constant `STEP5_ENABLED_SUBSTAGE` to `"5.2"` and set the env on the VPS (canonical_policy_doc class).
  - **B-4**: first sacrificial runtime invocation against a test repository (extra-gated; mirror the B2.5 plan).
- **Operator authorisation**: required at each step. **`step5_implementation_allowed` stays `Final[False]` throughout Path B.** The runtime path never opens a production PR; it remains dry-run-extended.

### Path C — remove `Final` and add a governance amendment

- **Source change**: `step5_implementation_allowed: bool = False` (no `Final`), permitting future runtime code to bind it to `True` under an amendment-controlled flow.
- **This path requires**:
  - **(a)** ADR-015 amendment (currently §Doctrine 1 / §Doctrine 7 treat this as hard).
  - **(b)** ADR-017 amendment (currently treats Step 5.2 runtime as a separately gated future phase).
  - **(c)** Readiness-gate G1–G12 reverification per `step5_design.md` §12.
  - **(d)** Explicit operator authorisation in the activation PR body (signed in writing).
  - **(e)** Source-code change pinned by new tests asserting the new closed semantics.
- **Conclusion**: Path C is a **governance-bootstrap sequence**, weeks of work, not a single PR. It crosses an explicit ADR boundary and cannot be initiated by the agent.

---

## §7 What B2.4b would need to do per operator outcome

The operator reads §3, §4, §5, §6 and chooses out-of-band between two outcomes:

### Outcome (a) — `step5_implementation_allowed` stays `Final[False]` permanently

- **B2.4b is dropped from Revised Batch 2.**
- **B2.3** (Step 5.2 PR creation runtime module), **B2.5** (first sacrificial invocation), and **B2.7** (CI bugfix runtime) are also dropped — the runtime path is permanently unreachable by doctrine.
- Revised Batch 2 Step 5 thread terminates at **B2.2** (Step 5.2 PR creation dry-run; additive schema only, no runtime).
- The Step 5.2 runtime question becomes a post-Batch-2 governance topic.

### Outcome (b) — the doctrine permits a future amendment

- **B2.4b becomes a multi-PR sequence** per Path B or Path C above. The current Revised Batch 2 plan (B2.3 → B2.4b → B2.5) remains as the *outline*, but each step expands into multiple PRs.
- Every step in the sequence requires explicit per-PR operator authorisation.
- `step5_implementation_allowed` stays `Final[False]` throughout Path B. Only Path C removes `Final` — and Path C requires the ADR amendments first.

**This document does not decide between (a) and (b).** The agent's role ends at producing the audit.

---

## §8 What this document is NOT

- Not an authorisation for any Step 5.2 runtime activation.
- Not a request to flip `step5_implementation_allowed` from `Final[False]`.
- Not a request to flip `STEP5_ENABLED_SUBSTAGE` from `Final["none"]`.
- Not a request to remove any `Final` annotation.
- Not a request to introduce the `ADE_STEP5_5_2_ENABLED` env flag.
- Not a proposal for any new runtime gate.
- Not an ADR amendment proposal.
- Not a deploy plan.
- Not a QRE deliverable. QRE work resumes under Roadmap v6 and is disjoint from this audit.
- Not a multi-operator review handoff. The reviewed-state stays with the operator.

---

## Appendix A — Cross-reference summary

| Topic | Document |
|---|---|
| Authority chain | [ADR-015](../adr/ADR-015-claude-agent-governance.md) §Doctrine 1 + §Doctrine 7 |
| Step 5 architectural decision | [ADR-017](../adr/ADR-017-step5-autonomous-implementation-loop.md) |
| Step 5 design + readiness gates | [`step5_design.md`](step5_design.md) §1, §5, §8.3, §12, §13 |
| Step 5.0 dry-run canonical doc | [`development_step5_loop.md`](development_step5_loop.md) |
| Autonomy ladder | [`autonomy_ladder.md`](autonomy_ladder.md) |
| No-touch paths | [`no_touch_paths.md`](no_touch_paths.md) |
| Per-action authority | [`execution_authority.md`](execution_authority.md) |
| AAC design (B2.0) | [`agent_activity_center_design.md`](agent_activity_center_design.md) |
| AAC push body safety doctrine (B2.0e backs) | [`agent_activity_center_push_notification_safety.md`](agent_activity_center_push_notification_safety.md) |
| Canonical Step 5 roadmap anchor | [`docs/roadmap/autonomous_development.txt`](../roadmap/autonomous_development.txt) §A14 |
| Step 5.0 module | `reporting/development_step5_loop.py` |
| Step 5.0 tests + B2.4a additive pins | `tests/unit/test_development_step5_loop.py` |
| Operational digest hard pin | `reporting/development_operational_digest.py` line 378 |

---

## Appendix B — File/line citations

| Claim | File | Line | Evidence |
|---|---|---|---|
| `STEP5_ENABLED_SUBSTAGE` is `Final[str] = "none"` | `reporting/development_step5_loop.py` | 102 | source line |
| `STEP5_ENABLED_SUBSTAGE` reference site (emit) | `reporting/development_step5_loop.py` | 350 | inside `_build_plan_payload(...)` |
| `STEP5_ENABLED_SUBSTAGE` reference site (emit) | `reporting/development_step5_loop.py` | 382 | inside `_build_no_op_plan_payload(...)` |
| `STEP5_ENABLED_SUBSTAGE` reference site (emit) | `reporting/development_step5_loop.py` | 426 | inside `_build_loop_snapshot(...)` |
| `step5_implementation_allowed` is `Final[bool] = False` | `reporting/development_step5_loop.py` | 138 | source line |
| `step5_implementation_allowed` reference site (emit) | `reporting/development_step5_loop.py` | 351 | inside `_build_plan_payload(...)` |
| `step5_implementation_allowed` reference site (emit) | `reporting/development_step5_loop.py` | 383 | inside `_build_no_op_plan_payload(...)` |
| `step5_implementation_allowed` reference site (emit) | `reporting/development_step5_loop.py` | 427 | inside `_build_loop_snapshot(...)` |
| Operational digest hard pin | `reporting/development_operational_digest.py` | 378 | hard-coded `"step5_implementation_allowed": False,` |
| `ADE_STEP5_5_2_ENABLED` absence | `reporting/`, `scripts/`, `dashboard/`, `tests/unit/`, `.claude/` | n/a | zero recursive grep matches |
| Forbidden imports pin | `tests/unit/test_development_step5_loop.py` | 85 | `FORBIDDEN_IMPORT_PREFIXES` tuple |
| Atomic-write sentinel | `reporting/development_step5_loop.py` | 451 | `_atomic_write_json(...)` rejects non-`logs/step5_*/` paths |

## End of truth-table document
