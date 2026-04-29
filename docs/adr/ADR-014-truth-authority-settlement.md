# ADR-014 — Truth Authority Settlement

Status: **Accepted** — 2026-04-29
Branch: `feature/v3.15.15-truth-authority-settlement`
Predecessor: `docs/audits/v3.15.15.6_strategy_preset_fundamental_audit.md`

## Context

The v3.15.15.6 fundamental audit established that the dominant
architectural risk in the research engine at v3.15.15.6 is **not** an
entanglement of trading-intelligence with research-intelligence,
**not** strategy proliferation, and **not** broken separation of
concerns. The audit's executive summary (§1) states it directly:

> The dominant *real* problem is not separation-of-concerns. It is
> truth-authority pluralism without a written settlement: at least
> four authorities (the strategy `registry`, the
> `strategy_hypothesis_catalog`, the `ResearchPreset` dataclass, the
> `candidate_lifecycle` enum) carry overlapping but non-identical
> truth surfaces about which strategies/hypotheses/presets/candidates
> exist and what their statuses are, with no single doctrinal sentence
> that says which authority wins on which scope.

The most concrete operational symptom (audit §8.6 / E1): three
strategies — `bollinger_regime`, `trend_pullback_tp_sl`,
`zscore_mean_reversion` — are `enabled=True` in the registry but
bundle-active in zero presets. A reader (operator or LLM agent) seeing
`enabled=True` will plausibly infer "this strategy is being
investigated." Operationally, false. The audit classifies this as
`misleading` and proposes a single doctrinal ADR (this one) as the
migration anchor — settle authority pluralism in writing, then add an
additive derived view (`bundle_active`) and a verification trace, with
no policy or schema changes.

ADR-014 is doctrine, not code. It declares what the codebase already
largely does and makes the registered-but-inert case immediately
legible as a doctrinal mismatch.

## Decision

Adopt the canonical authority mapping in §A as the single doctrinal
settlement of authority pluralism for the v3.15.15.10+ research
engine. Adopt §B (frozen correctness doctrine), §C (transitional
architecture rules), §D (no-touch zones), and §E (derived truth
principles) as binding context for how the authority mapping is to be
read and applied.

**Core principles** (binding):

> `enabled=True` does not imply actively investigated.
> Registry presence does not imply preset participation.
> `bundle_active` is derived from preset bundles.
> `active_discovery` is owned by the hypothesis catalog.
> `live_eligible` remains false through the current no-live
> governance envelope.

This release ships two additive surfaces alongside this ADR:

1. **`research/authority_views.py`** — a pure read-only module
   exposing `bundle_active`, `active_discovery`, `live_eligible`, and
   `render_authority_summary`. Derived from the canonical authorities
   in §A. No IO, no mutation, no decision-path consumers.
2. **Five doctrine sentences** in `research/presets.py`,
   `research/registry.py`, `research/campaign_policy.py`,
   `research/strategy_hypothesis_catalog.py`, and
   `docs/orchestrator_brief.md`, plus four one-line cross-refs in
   `AGENTS.md`, `CLAUDE.md`, `docs/roadmap/qre_prompt_guidelines_v2.md`,
   and `docs/roadmap/qre_roadmap_v4.md`.

The runtime verification trace prescribed by the audit (§19.2) ships
in v3.15.15.11 as a separate, gated micro-release.

## §A — Canonical authority mapping

For each truth domain in the research engine, exactly one authority
wins. Other surfaces may carry the same data for derivability, byte
identity, or migration reasons — but only the canonical authority
defines the truth.

| Truth domain                                            | Canonical authority                                                              | Subordinate / consumer surfaces                                                                                                                                          |
| ------------------------------------------------------- | -------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| "this strategy exists as code"                          | `research/registry.py:STRATEGIES`                                                | None.                                                                                                                                                                   |
| "this strategy is bundled in some enabled preset"       | `research/presets.py:PRESETS` (across all `bundle` and `optional_bundle` fields) | The derived view `research.authority_views.bundle_active(name)` consumes this. **No** authority writes back to the preset catalog from a derived view.                  |
| "this hypothesis is canonical TI doctrine"              | `research/strategy_hypothesis_catalog.py:STRATEGY_HYPOTHESIS_CATALOG`            | Registry `hypothesis` free-text strings are legacy / byte-identity-binding documentation only — they do **not** participate in canonical hypothesis authority.          |
| "this hypothesis is eligible for autonomous spawning"   | Catalog `status == "active_discovery"` (filtered via `ALPHA_ELIGIBLE_STATUSES`)  | Preset's `hypothesis_id` is a foreign-key reference into this; campaign-template `require_hypothesis_status` consumes it via `EligibilityPredicate`.                    |
| "this preset is executable today"                       | `ResearchPreset.enabled`                                                         | `screening_phase` governs gate strictness; `diagnostic_only`, `excluded_from_daily_scheduler`, `excluded_from_candidate_promotion`, `preset_class` govern OI behavior.   |
| "this campaign is in-progress / completed / failed"    | `campaign_registry_latest.v1.json` (current state) **and** `campaign_evidence_ledger.jsonl` (history) — both canonical for their respective scopes | Two-axis truth (audit §7.4): registry holds the current snapshot; ledger is append-only event history. Funnel-policy decisions trust the ledger; technical-failure detection trusts the registry. |
| "this candidate's lifecycle status"                     | `CandidateLifecycleStatus` enum value as written to `candidate_registry_latest.v1.json` | Runtime `current_status` on the in-memory candidate dict is transient — canonical only during a run, not across runs.                                                   |
| "this candidate is paper-ready"                         | `paper_readiness_latest.v1.json` `readiness_status` field                        | `screening_evidence.promotion_guard` is the upstream input; the campaign funnel policy AND-combines paper readiness with funnel decisions.                              |
| "this funnel-policy decision was emitted"               | `campaign_evidence_ledger.jsonl` `funnel_decision_emitted` event                 | The pure `campaign_funnel_policy.FunnelDecision` is the in-memory representation of the same fact — canonical at the event level once emitted.                          |

Where two surfaces appear to disagree, the canonical column wins.
Where the disagreement is intentional (e.g., the runtime `current_status`
diverging from `lifecycle_status` mid-run), see §C — the divergence is
a transitional / load-bearing seam, not a bug.

## §B — Frozen correctness doctrine

> Frozen correctness > aesthetic normalization.

The research engine carries deliberate duplication and legacy surfaces
that **must not** be cleaned up purely for tidiness. Each one
preserves a load-bearing property.

**Replay guarantees.** A research run from v3.5+ artifacts must
produce byte-identical results today. This is enforced by the
`test_v3_15_*_pin*` test family and by the `ROW_SCHEMA` /
`JSON_*_SCHEMA` tuples in `research/results.py`. Schema additions to
frozen artifacts break replay; therefore none are added by this
release.

**Artifact immutability.** The frozen v1 sidecars
(`candidate_registry_latest.v1.json`,
`strategy_hypothesis_catalog_latest.v1.json`,
`campaign_templates_latest.v1.json`) are byte-identity-pinned for the
fields they currently carry. New observability data lands in
**adjacent** sidecars (e.g., the v3.15.11 evidence ledger,
the v3.15.15.11 authority trace), never spliced into a frozen
schema.

**Reproducibility constraints.** Pure functions
(`promotion.classify_candidate`, `campaign_policy.decide`,
`campaign_funnel_policy.FunnelDecision`,
`campaign_registry.transition_state`) carry the I6 invariant: same
inputs → byte-identical outputs. Trace emission, sink construction,
or any other side-effect injection inside these pure modules would
violate I6. ADR-014's runtime verification layer (v3.15.15.11) is
emitted at *callers*, never inside the pure modules.

**Migration safety.** The `family` field on registry entries (older
ontology) coexists with `strategy_family` (newer); the registry
`hypothesis` free-text string coexists with the catalog `hypothesis_id`
bridge; legacy `trend_pullback` / `trend_pullback_tp_sl` coexist with
`trend_pullback_v1`. Removing the older surface would break archived
audit trails and byte-identity tests.

**Historical compatibility.** The v3.15.2 / v3.15.3 / v3.15.4 strict
invariants (≥1 active_discovery hypothesis; explicit hypothesis
bridge in presets; closed status enum) are doctrinally load-bearing.
This ADR does not relax any of them; it codifies the *authority* that
owns each one.

## §C — Transitional architecture rules

The following are **acceptable** during the v3.15.x → v3.17 migration
envelope. Each is documented as transitional in code or in audit §6 /
§21.4. None should be removed before its sunset condition is met.

**Acceptable duplication:**
- The registry `family` field alongside `strategy_family` (older + newer ontology coexisting; audit §3.4 X3.4).
- The registry `hypothesis` free-form string alongside the catalog `hypothesis_id` (legacy TI prose in RI surface; audit §21.4).
- Two policy modules: `research/campaign_policy.py` (older, thicker) and `research/campaign_funnel_policy.py` (newer, pure, v3.15.10). New policy logic targets `campaign_funnel_policy.py`; the older module is retained until Phase-2 trace evidence (audit §19.3 step 2) confirms no conflicting decisions in production.

**Acceptable compatibility shims:**
- The `_METADATA_ONLY_FAMILIES` set in `strategy_hypothesis_catalog.py`. Sunset condition: empty at v3.17+ as planned families become executable.
- The legacy `trend_pullback` and `trend_pullback_tp_sl` registry entries with `strategy_family="trend_following"`. Sunset condition: post-v3.17, conditional on byte-identity verification of any sidecar that serializes the registry surface.
- The `fb_<sha1prefix>` evidence-fingerprint fallback in `screening_evidence.py`. Counted in `summary.identity_fallbacks`; not silent. Sunset condition: zero fallbacks observed across multiple production releases.
- The brute-force Cartesian sweep in `research/registry.py`. Self-documented as a Phase 2 migration target (registry.py:6–8). Sunset condition: Phase 2 brute-force replacement lands.

**Temporary authority mirrors:**
- The runtime `current_status` field on the in-memory candidate dict mirrors `lifecycle_status` from `candidate_registry_latest.v1.json` for the duration of a run. Canonical: artifact post-run; runtime mirror is transient.
- The screening evidence sidecar (`screening_evidence_latest.v1.json`, schema-versioned non-frozen) carries per-candidate stage results that overlap with the `candidate_registry_latest.v1.json` post-promotion verdict. Canonical: registry post-run; screening evidence is canonical only for per-candidate stage results.

**Migration-safe coexistence patterns:**
- New observability data lives in *adjacent* sidecars, never spliced into a frozen v1 schema. Examples: `falsification_gates_latest.v1.json` (v3.15.4), `research_evidence_ledger.v1.json` (v3.15.11), and the upcoming `authority_trace_latest.v1.jsonl` (v3.15.15.11).
- New authority surfaces are **derived** before they are **stored**. The `authority_views.bundle_active` predicate is derived; it is not stored on a strategy row. Storing it would inflate the registry surface and force a byte-identity migration.

**What MAY be cleaned later** (post-v3.17, post-live evidence; audit §19.4):
- The four dead unregistered factories (`fear_greed_strategie`, `earnings_strategie`, `orb_strategie`, `polymarket_expiry_strategie` in `agent/backtesting/strategies.py`).
- The three registered-but-bundle-inert strategies: `bollinger_regime`, `trend_pullback_tp_sl`, `zscore_mean_reversion`. Flipping `enabled=True → False` is gated on byte-identity tolerance; deferred indefinitely if any sidecar serializes the `enabled` field.
- The `_METADATA_ONLY_FAMILIES` entries as their planned strategies become executable.

**What MUST remain stable indefinitely:**
- The `screening_mode` × `screening_phase` orthogonality. Doctrine forbids collapse.
- The `live_eligible=False` hard pin until v3.17 governance changes.
- The `reference_asset="ETH-EUR"` v3.6 scope lock on `pairs_zscore`.
- The `pairs_equities_daily_baseline.enabled=False` shape — the doctrinal example of "planned-but-disabled."
- The 30-template auto-generated catalog. Manual template additions are forbidden.

## §D — No-touch zones

These are protected by ADR-014. Any change must propose a successor
ADR.

**Frozen artifacts (schemas):**
- `research_latest.json` (`ROW_SCHEMA` in `research/results.py`).
- `strategy_matrix.csv`.
- `candidate_registry_latest.v1.json`.
- `strategy_hypothesis_catalog_latest.v1.json`.
- `campaign_templates_latest.v1.json`.

**Pinned tests (must continue to pass byte-for-byte):**
- `tests/unit/test_paper_no_live_invariant.py`.
- `tests/unit/test_orchestration_boundary.py`.
- `tests/unit/test_orchestration_artifact_truth.py`.
- `tests/unit/test_v3_15_6_preset_phase_explicitness.py`.
- `tests/unit/test_v3_15_6_preset_to_card_unchanged.py`.
- `tests/unit/test_v3_15_6_behavior_equivalent.py`.
- `tests/unit/test_active_discovery_preset_bridge.py`.
- `tests/unit/test_strategy_hypothesis_catalog.py`.
- `tests/unit/test_campaign_invariants.py`.
- `tests/functional/test_static_import_surface.py`.

**Identifiers and templates:**
- Strategy identifiers in `research/registry.py:STRATEGIES`. No renames.
- Preset names in `research/presets.py:PRESETS`. No renames.
- Hypothesis ids in `research/strategy_hypothesis_catalog.py`. No renames.
- The 30 byte-pinned campaign templates.
- Campaign templates layer (the COL "frozen catalog" — picking outside catalog is a bug, not a configuration mistake).

**Doctrine-load-bearing patterns:**
- `screening_mode` ↔ `screening_phase` orthogonality (`research/presets.py:38–53`).
- `live_eligible=False` hard pin on every v3.15+ artifact.
- `_METADATA_ONLY_FAMILIES` as the explicit reconciliation seam between catalog and registry.
- Default `screening_phase="promotion_grade"` as the AST-test-enforced safety floor.
- The four v3.15.x active_discovery thin-strategies and their `contract_version="1.0"` pinning.

**Migration bridges (preserve through their lifetimes):**
- Legacy `trend_pullback` and `trend_pullback_tp_sl` registry entries with `strategy_family="trend_following"`.
- Registry `family` field alongside `strategy_family`.
- Registry `hypothesis` free-form strings.
- The `fb_<sha1prefix>` evidence-fingerprint fallback.
- The validation in-place mutation pattern at `run_research.py:3019`.
- The six-flag diagnostic encoding on `crypto_diagnostic_1h`.
- The brute-force Cartesian sweep in `research/registry.py`.

## §E — Derived truth principles

Five concepts that are commonly conflated must be kept formally
distinct.

| Concept              | Definition                                                                                              | Authority                                                          | How to read                                                                                                       |
| -------------------- | ------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------ | ----------------------------------------------------------------------------------------------------------------- |
| `executable`         | A registered factory exists for the strategy and produces a position series.                            | `agent/backtesting/strategies.py` + `research/registry.py:STRATEGIES` factory wiring | The strategy can technically be invoked. Says nothing about whether it is being investigated.                     |
| `enabled`            | The registry row's `enabled` flag is `True`. The runner / scheduler may consider the strategy.          | `research/registry.py` row                                         | The strategy is registerable — *not* a claim that any preset bundles it.                                          |
| `bundle_active`      | The strategy name appears in `bundle` or `optional_bundle` of at least one `enabled=True` preset.       | Derived view: `research.authority_views.bundle_active(name)`       | Some live preset is currently configured to investigate this strategy.                                            |
| `active_discovery`   | The strategy's `strategy_family` matches a hypothesis with `status="active_discovery"` in the catalog.  | `research/strategy_hypothesis_catalog.py:STRATEGY_HYPOTHESIS_CATALOG` | The strategy backs an active research hypothesis. Legacy / non-bridged strategies (e.g., legacy `trend_pullback`) MUST return `False`. |
| `live_eligible`      | The strategy is allowed to participate in live trading.                                                 | `research/paper_readiness.py` invariant                            | Always `False` through the current no-live governance envelope. Hard-pinned.                                       |

These are **independent**. A strategy may be `executable` and
`enabled` without being `bundle_active` (the registered-but-inert
case). A strategy may be `bundle_active` without being
`active_discovery` (e.g., `sma_crossover` is bundled in trend
baselines but no `active_discovery` hypothesis carries
`strategy_family="trend"`). No combination implies `live_eligible`
through v3.17.

The `research.authority_views` module exposes the three derived
predicates plus a `render_authority_summary(name)` formatter for
operator diagnostics.

## Out of scope

- **Automatic catalog status mutation on repeated falsification.**
  Audit §19.3 step 1. Deferred to v3.16 — requires operator
  acknowledgement first; automatic only post-v3.17.
- **Retirement of `campaign_policy.py`.** Conditional on Phase-2
  trace evidence (audit §19.3 step 2). v3.15.15.11 ships the trace;
  retirement decision follows separately.
- **Refactor of the `SamplingPlan` ↔ `promotion_guard` coupling.**
  Audit §X2.6 marks this `unverifiable` at line level. Out of scope.
- **Reification of the candidate dict to a dataclass.** Phased rollout
  per `CandidateLifecycleStatus` reserved statuses (v3.16 / v3.17).
  Out of scope here.
- **Flipping `enabled=True → False` on the three registered-but-inert
  strategies.** Audit §19.4 step 2. Gated on byte-identity tolerance;
  deferred indefinitely if any sidecar serializes the field. The
  doctrinal sentence + `bundle_active` derived view is the prescribed
  fallback.
- **Live or shadow enablement.** All artifacts pin `live_eligible=False`.

## Consequences

- The codebase has, for the first time, a **single doctrinal sentence
  per truth domain** declaring which authority wins. Future Claude /
  operator readers can resolve apparent conflicts by reading §A.
- The registered-but-inert case (`bollinger_regime`,
  `trend_pullback_tp_sl`, `zscore_mean_reversion`) is now legible as a
  documented gap (§E) rather than as a code defect. Operators have an
  authoritative API (`bundle_active`) to detect it.
- Frozen v3.5+ public output contracts (`research_latest.json`,
  `strategy_matrix.csv`) are untouched. The new `authority_views.py`
  module is an adjacent derived surface; the upcoming
  `authority_trace_latest.v1.jsonl` (v3.15.15.11) is an adjacent
  observability sidecar.
- The v3.15.4 strict catalog invariant, the COL no-touch invariant,
  the v3.15.7 phase-aware promotion dispatch, and the v3.15.10
  funnel-policy purity invariant are all explicitly preserved.
- The audit's Phase-2 verification (`unverifiable` items in §19.2 /
  §X2.6 / §X2.7) is the natural next step. v3.15.15.11 implements the
  trace layer; the conditional Phase-3 fixes in audit §19.3 follow as
  evidence accumulates.

## References

- `docs/audits/v3.15.15.6_strategy_preset_fundamental_audit.md` — fundamental audit (predecessor).
- Audit §1 — executive summary (truth-authority pluralism finding).
- Audit §7 — ontology & semantic ownership.
- Audit §8 — epistemic integrity & truth ownership; §8.6 disagreement classes.
- Audit §15 — frozen correctness vs architectural correctness.
- Audit §18.2 — proposed truth-authority map (the table in §A above).
- Audit §19.1 — Phase 1 doctrine-only steps.
- Audit §21 — what absolutely NOT to change.
- ADR-011 — v3.10 architecture (platform-layer + research-ops introduction).
- ADR-013 — v3.15.3 hypothesis catalog (closed status enum + active_discovery gating).
