# Funnel Spawn Proposer — Design (post-v3.15.11)

> Status: design locked for v3.15.12 implementation. Six hardenings
> from operator review (2026-04-27) folded in: stronger fingerprint +
> per-fingerprint cooldown, scope-spread exploration coverage,
> dead-zone decay before suppression, viability `stop_or_pivot` →
> `proposal_mode = "diagnostic_only"`, deterministic priority enum
> (HIGH / MEDIUM / LOW / SUPPRESSED), and a `reason_trace` on every
> proposal.
>
> Positioning: **advisory-only forward-looking layer**. Reads
> v3.15.11 intelligence artifacts + v3.15.10 funnel policy + COL
> registry, emits proposed-but-not-spawned campaigns. Never
> mutates the queue, the registry, or `campaign_policy.decide()`.
> Mode flag in artifact: `"shadow"`. Future modes (`"evaluation"`,
> `"gated_consumption"`) deferred to later releases.

---

## 1. Architecture placement

```
                     ┌─────────────────────────────────────────────┐
                     │              run_research lifecycle         │
                     └───────────────────────┬─────────────────────┘
                                             │ writes (in order)
            ┌────────────────────────────────┴────────────────────────────────┐
            │                                                                 │
   v3.15.9 screening_evidence            v3.15.11 evidence_ledger,
                                          information_gain, stop_conditions,
                                          dead_zones, viability
            │                                                                 │
            └───────────────┬─────────────────────────────────┬───────────────┘
                            │                                 │
                            ▼                                 ▼
             v3.15.10 campaign_funnel_policy        ┌─────────────────────────┐
              (per-outcome funnel decisions)        │  NEW: funnel_spawn      │
                            │                       │  proposer (this doc)    │
                            │                       │                         │
                            │                       │  cross-campaign,        │
                            │                       │  forward-looking        │
                            │                       │  proposals + suppress   │
                            │                       └────────────┬────────────┘
                            │                                    │
                            ▼                                    ▼
              campaign_evidence_ledger.jsonl       spawn_proposals_latest.v1.json
              (existing, append-only)              (NEW, advisory)
                            │                       spawn_proposal_history.jsonl
                            ▼                       (NEW, append-only, fingerprint
                COL: registry / queue / launcher    cooldown)
                campaign_policy.decide() (UNCHANGED)             │
                            │                                    ▼
                            ▼                       dashboard card + operator review
                      spawns campaigns              (Phase 1 = read-only)
```

**Decision: NEW module `research/funnel_spawn_proposer.py`**, not an
extension of `campaign_funnel_policy`.

Why not extend `campaign_funnel_policy`:

- `campaign_funnel_policy` interprets ONE campaign's outcome (per-event,
  fits the existing per-outcome funnel decisions added in v3.15.10).
- The proposer aggregates ACROSS many campaigns plus viability and
  dead zones to look forward. Different concern, different cadence.

Why NOT an extension of `campaign_policy.decide()`:

- v3.15.11 explicitly pinned `campaign_policy.decide()` as unchanged.
- Phase 3 (gated consumption) will eventually touch policy; Phase 1
  (this design) must not.

Why NOT a parallel orchestrator:

- The proposer never writes to queue/registry. It only emits sidecars
  the operator (and a future Phase 3 release) consumes.

---

## 2. Module structure

`research/funnel_spawn_proposer.py`:

```
constants  ─── EXPLORATION_RESERVATION_PCT = 0.20
              EXPLORATION_MIN_DISTINCT_FAMILIES = 3
              EXPLORATION_MIN_DISTINCT_ASSETS = 3
              EXPLORATION_MIN_DISTINCT_TIMEFRAMES = 2
              MAX_PROPOSALS_PER_RUN_NORMAL = 10
              MAX_PROPOSALS_PER_RUN_DIAGNOSTIC = 3
              FINGERPRINT_COOLDOWN_DAYS = 7
              DEAD_ZONE_DECAY_DAYS = 14
              SPAWN_PROPOSALS_PATH         = research/campaigns/evidence/spawn_proposals_latest.v1.json
              SPAWN_PROPOSAL_HISTORY_PATH  = research/campaigns/evidence/spawn_proposal_history.jsonl
              SPAWN_PROPOSALS_SCHEMA_VERSION = "1.0"
              MODE_SHADOW                = "shadow"
              MODE_DIAGNOSTIC_ONLY       = "diagnostic_only"
              ENFORCEMENT_STATE_ADVISORY = "advisory_only"

priority enum ─ PRIORITY_TIER = Literal[
                  "HIGH",        # confirmation, promotion follow-up
                  "MEDIUM",      # near-pass retry, weak-zone adjacent
                  "LOW",         # exploration, diversification
                  "SUPPRESSED",  # would-have-been-proposed but blocked
                ]

dataclasses ── ProposedCampaign(
                preset_name, hypothesis_id, asset, timeframe,
                strategy_family, parameter_grid_signature,
                proposal_type, spawn_reason,
                priority_tier, lineage,
                rationale_codes, reason_trace,
                expected_information_gain_bucket,
                source_signal, proposal_fingerprint
              )
              SuppressedZone(asset, strategy_family,
                             reason_codes, suppression_until_utc,
                             time_since_last_attempt_days)
              ExplorationCoverage(
                pct_target, pct_actual,
                distinct_families, distinct_assets,
                distinct_timeframes, candidate_zones[]
              )

pure rules ─── _propose_from_screening_evidence(...)
              _propose_from_dead_zones(...)
              _propose_from_viability(...)        # toggles proposal_mode
              _propose_from_high_information_gain(...)
              _suppress_from_stop_conditions(...)
              _decay_dead_zone_suppression(...)   # softens R4
              _enforce_exploration_reservation(...)  # %, family, asset, timeframe
              _filter_by_fingerprint_cooldown(...)
              _filter_by_active_registry(...)
              _assign_priority_tier(...)          # deterministic enum
              _build_reason_trace(...)            # ordered evaluation log

builder ────── build_spawn_proposals_payload(*, ...)
io wrappers ── write_spawn_proposals_artifact(*, ...)
              append_proposal_history(...)        # JSONL, append-only
              load_recent_proposal_fingerprints(*, days)
```

Same canonical sidecar contract as the rest of v3.15.11
(`_sidecar_io.write_sidecar_atomic`, sorted keys, byte-identical
on identical inputs).

The history JSONL uses the same append-only pattern as
`campaign_evidence_ledger.jsonl`.

---

## 3. Input → processing → output flow

| Input artifact | Used for | Drives |
|---|---|---|
| `screening_evidence_latest.v1.json` | per-candidate `stage_result`, `pass_kind`, `near_pass.nearest_failed_criterion` | R1, R2 |
| `evidence_ledger_latest.v1.json` | hypothesis-level `promotion_candidate_count` / `paper_ready_count` (protection); `dominant_failure_mode`; per-zone `last_seen_at_utc` | R3 protection, R4-decay |
| `information_gain_latest.v1.json` | bucket annotated on each proposal; high-IG drives R6 expansion | R6 |
| `stop_conditions_latest.v1.json` | `recommended_decision in {RETIRE_*, FREEZE_PRESET}` blocks proposals | R3 |
| `dead_zones_latest.v1.json` | zone status `dead`/`weak`/`unknown`/`insufficient_data`; `time_since_last_attempt` derived | R4, R5, R7 |
| `viability_latest.v1.json` | `verdict.status` toggles `proposal_mode` | R8 |
| `campaign_registry_latest.v1.json` | active/queued lookup for idempotency | R9-active |
| `spawn_proposal_history.jsonl` | recent fingerprints for cooldown lookup | R9-cooldown |

Output: TWO sidecars.

1. `research/campaigns/evidence/spawn_proposals_latest.v1.json` — the
   current proposal snapshot.
2. `research/campaigns/evidence/spawn_proposal_history.jsonl` —
   append-only fingerprint log for cooldown enforcement.

---

## 4. Output schema

```json
{
  "schema_version": "1.0",
  "generated_at_utc": "...",
  "git_revision": "...",
  "run_id": "...",
  "enforcement_state": "advisory_only",
  "mode": "shadow",
  "proposal_mode": "normal",
  "summary": {
    "proposed_count": 0,
    "suppressed_zone_count": 0,
    "human_review_required": false,
    "exploration_coverage": {
      "pct_target": 0.20,
      "pct_actual": 0.0,
      "distinct_families_target": 3,
      "distinct_families_actual": 0,
      "distinct_assets_target": 3,
      "distinct_assets_actual": 0,
      "distinct_timeframes_target": 2,
      "distinct_timeframes_actual": 0,
      "shortfall_reason_codes": []
    },
    "fingerprint_cooldown_blocks": 0
  },
  "proposed_campaigns": [
    {
      "preset_name": "trend_pullback_crypto_1h",
      "hypothesis_id": "hyp_42",
      "asset": "crypto",
      "timeframe": "1h",
      "strategy_family": "trend_pullback",
      "parameter_grid_signature": "sha1:...",
      "proposal_type": "confirmation_campaign",
      "spawn_reason": "confirmation_from_exploratory_pass",
      "priority_tier": "HIGH",
      "lineage": {
        "parent_campaign_id": "...",
        "parent_run_id": "..."
      },
      "rationale_codes": [
        "exploratory_pass_observed",
        "no_confirmation_run_in_recent_window"
      ],
      "reason_trace": [
        "exploratory_pass_detected",
        "stop_conditions_clear_for_scope",
        "not_in_dead_zone",
        "fingerprint_not_in_cooldown",
        "no_active_or_queued_duplicate",
        "priority_tier_assigned=HIGH"
      ],
      "expected_information_gain_bucket": "high",
      "source_signal": "screening_evidence",
      "proposal_fingerprint": "sha1:..."
    }
  ],
  "suppressed_zones": [
    {
      "asset": "crypto",
      "strategy_family": "momentum",
      "reason_codes": ["dead_zone_detected"],
      "suppression_until_utc": "2026-05-11T12:00:00+00:00",
      "time_since_last_attempt_days": 2
    }
  ],
  "exploration_reservation": {
    "pct_target": 0.20,
    "candidate_zones": [
      {
        "asset": "stocks",
        "strategy_family": "mean_reversion",
        "current_status": "insufficient_data"
      }
    ]
  },
  "human_review_required": {
    "active": false,
    "reason_codes": []
  }
}
```

Top-level `enforcement_state` and `mode` are split from
`proposal_mode` (which describes the proposer's behavior, not the
sidecar's enforcement state).

---

## 5. Deterministic rule set

Constants are module-level (single inspection point), no scattered
magic numbers.

| # | Trigger | Action | Priority Tier |
|---|---|---|---|
| R1 | `screening_evidence.candidates[].stage_result == "needs_investigation"` AND `pass_kind == "exploratory"` | propose `confirmation_campaign(hypothesis_id, screening_phase=promotion_grade)` | **HIGH** |
| R2 | `screening_evidence.candidates[].stage_result == "near_pass"` AND `near_pass.is_near_pass == true` | propose `parameter_adjacent_retry(preset, criterion=near_pass.nearest_failed_criterion)` | **MEDIUM** |
| R3 | `stop_conditions.decisions[].recommended_decision in {RETIRE_HYPOTHESIS, RETIRE_FAMILY, FREEZE_PRESET}` for scope S | NO proposal for S; record in `suppressed_zones[]` if applicable | **SUPPRESSED** |
| R4 | `dead_zones.zones[].zone_status == "dead"` AND `time_since_last_attempt_days <= DEAD_ZONE_DECAY_DAYS (14)` | suppress proposals in zone; add to `suppressed_zones[]` with `suppression_until_utc = last_attempt + DEAD_ZONE_DECAY_DAYS` | **SUPPRESSED** |
| R4-decay | `dead_zones.zones[].zone_status == "dead"` AND `time_since_last_attempt_days > DEAD_ZONE_DECAY_DAYS` | NOT suppressed: zone is eligible for R6 (exploration). Add `reason_code="dead_zone_decayed_eligible_for_revisit"` | **LOW** |
| R5 | `dead_zones.zones[].zone_status == "weak"` AND last campaign in zone had IG bucket >= medium | propose `adjacent_preset_campaign(family, neighbor_asset_or_timeframe)` | **MEDIUM** |
| R6 | `dead_zones.zones[].zone_status in {"unknown", "insufficient_data"}` OR R4-decay-eligible | candidate for exploration reservation (per R7) | **LOW** |
| R6-IG | `information_gain.information_gain.bucket == "high"` AND zone in same scope had no recent spawn (within 3 days) | propose `adjacent_preset_campaign(family, neighbor_asset_or_timeframe)` to expand | **MEDIUM** |
| R7 | After R1–R6 evaluated: enforce that the final proposal set satisfies BOTH (a) `pct_actual >= EXPLORATION_RESERVATION_PCT (0.20)` AND (b) `distinct_families >= 3`, `distinct_assets >= 3`, `distinct_timeframes >= 2` (graceful fallback if catalog can't supply that many — record `shortfall_reason_codes`). If targets unmet, lift the lowest-priority HIGH/MEDIUM proposal and replace with a LOW exploration proposal that improves the most-deficient dimension. | post-processing | rebalance |
| R8 | `viability.verdict.status == "stop_or_pivot"` | set `proposal_mode = "diagnostic_only"`. Drop all HIGH-tier proposals. Cap output at `MAX_PROPOSALS_PER_RUN_DIAGNOSTIC (3)`. Allow only LOW (exploration, diversification). Set `human_review_required.active = true`. | enforced |
| R9-cooldown | Proposal `proposal_fingerprint` appears in `spawn_proposal_history.jsonl` within `FINGERPRINT_COOLDOWN_DAYS (7)` | drop proposal; increment `summary.fingerprint_cooldown_blocks` | filter |
| R9-active | Proposal `proposal_fingerprint` matches an active or queued (within 7 days) entry in `campaign_registry_latest.v1.json` | drop proposal | filter |
| R10 | After all rules, sort by `priority_tier` enum order (HIGH > MEDIUM > LOW > SUPPRESSED) then by `proposal_fingerprint` ascending. Cap total at `MAX_PROPOSALS_PER_RUN_NORMAL (10)` or `MAX_PROPOSALS_PER_RUN_DIAGNOSTIC (3)` per `proposal_mode`. | sort + cap | n/a |
| R11 | For every kept proposal: append to `spawn_proposal_history.jsonl` with `{fingerprint, generated_at_utc, run_id}`. Used by R9-cooldown on the NEXT run. | side-effect (append-only) | n/a |

### 5.1 Fingerprint definition (R9 input)

```
proposal_fingerprint = sha1(canonical_json({
  hypothesis_id,
  preset_name,
  parameter_grid_signature,
  timeframe,
  asset,
  proposal_type,
}))
```

Six fields, not four. `parameter_grid_signature` is the same digest
v3.15.8 already computes per candidate (so it's available, no new
infrastructure). `proposal_type` (e.g. `"confirmation_campaign"` vs
`"parameter_adjacent_retry"`) prevents two different proposal kinds
on the same scope from collapsing.

### 5.2 Reason trace (R-trace)

Every kept proposal carries `reason_trace[]` — the ORDERED list of
checks each rule asked, in evaluation order. Example:

```
[
  "exploratory_pass_detected",            # R1 fired
  "stop_conditions_clear_for_scope",      # R3 passed
  "not_in_dead_zone",                     # R4 passed
  "fingerprint_not_in_cooldown",          # R9-cooldown passed
  "no_active_or_queued_duplicate",        # R9-active passed
  "priority_tier_assigned=HIGH",          # tier
  "exploration_reservation_satisfied"     # R7 passed
]
```

For SUPPRESSED proposals (recorded in `suppressed_zones[]`, not
`proposed_campaigns[]`), the trace includes WHICH rule suppressed
them: `"r4_dead_zone_active_within_decay_window"`.

This is debugging gold. It also ensures that any future Phase 3
autonomous consumer can audit *why* a proposal exists before acting.

### 5.3 Priority tier ordering

```
PRIORITY_TIER_ORDER = ["HIGH", "MEDIUM", "LOW", "SUPPRESSED"]
```

HIGH:
- `confirmation_campaign` (R1)

MEDIUM:
- `parameter_adjacent_retry` (R2)
- `adjacent_preset_campaign` from weak zone (R5)
- `adjacent_preset_campaign` from high IG (R6-IG)

LOW:
- `exploration_reservation_unknown_zone` (R6)
- `hypothesis_diversification` (R7 rebalance)
- `dead_zone_decayed_revisit` (R4-decay → R6)

SUPPRESSED:
- only appears in `suppressed_zones[]`, NOT in `proposed_campaigns[]`,
  but kept in the schema so operator can see what was blocked and
  why.

Sort within tier: by `proposal_fingerprint` ascending. Deterministic.

---

## 6. Example output (illustrative)

After a run where:
- one exploratory pass on `trend_pullback_crypto_1h`,
- one near_pass on `mr_reversion_eth_15m`,
- `(stocks, mean_reversion)` zone is `insufficient_data`,
- `(crypto, momentum)` zone is `dead`, last attempted 2 days ago,
- `(forex, momentum)` zone is `dead`, last attempted 30 days ago →
  decayed, eligible for revisit,
- viability is still `weak` (not `stop_or_pivot`).

```json
{
  "schema_version": "1.0",
  "enforcement_state": "advisory_only",
  "mode": "shadow",
  "proposal_mode": "normal",
  "summary": {
    "proposed_count": 4,
    "suppressed_zone_count": 1,
    "human_review_required": false,
    "exploration_coverage": {
      "pct_target": 0.20,
      "pct_actual": 0.50,
      "distinct_families_target": 3,
      "distinct_families_actual": 3,
      "distinct_assets_target": 3,
      "distinct_assets_actual": 3,
      "distinct_timeframes_target": 2,
      "distinct_timeframes_actual": 2,
      "shortfall_reason_codes": []
    },
    "fingerprint_cooldown_blocks": 0
  },
  "proposed_campaigns": [
    {
      "preset_name": "trend_pullback_crypto_1h",
      "proposal_type": "confirmation_campaign",
      "spawn_reason": "confirmation_from_exploratory_pass",
      "priority_tier": "HIGH",
      "reason_trace": [
        "exploratory_pass_detected",
        "stop_conditions_clear_for_scope",
        "not_in_dead_zone",
        "fingerprint_not_in_cooldown",
        "no_active_or_queued_duplicate",
        "priority_tier_assigned=HIGH"
      ]
    },
    {
      "preset_name": "mr_reversion_eth_15m",
      "proposal_type": "parameter_adjacent_retry",
      "spawn_reason": "parameter_adjacent_retry_from_near_pass",
      "priority_tier": "MEDIUM",
      "reason_trace": [
        "near_pass_detected",
        "nearest_failed_criterion=profit_factor_below_floor",
        "stop_conditions_clear_for_scope",
        "not_in_dead_zone",
        "fingerprint_not_in_cooldown",
        "no_active_or_queued_duplicate",
        "priority_tier_assigned=MEDIUM"
      ]
    },
    {
      "preset_name": "mr_reversion_stocks_1d",
      "proposal_type": "exploration_reservation_unknown_zone",
      "spawn_reason": "exploration_reservation_unknown_zone",
      "priority_tier": "LOW",
      "reason_trace": [
        "zone_status=insufficient_data",
        "exploration_coverage_distinct_assets_below_target",
        "fingerprint_not_in_cooldown",
        "no_active_or_queued_duplicate",
        "priority_tier_assigned=LOW"
      ]
    },
    {
      "preset_name": "momentum_forex_4h",
      "proposal_type": "dead_zone_decayed_revisit",
      "spawn_reason": "dead_zone_decay_passed",
      "priority_tier": "LOW",
      "reason_trace": [
        "dead_zone_status_active",
        "time_since_last_attempt_days=30 > DEAD_ZONE_DECAY_DAYS=14",
        "dead_zone_decay_passed",
        "fingerprint_not_in_cooldown",
        "priority_tier_assigned=LOW"
      ]
    }
  ],
  "suppressed_zones": [
    {
      "asset": "crypto",
      "strategy_family": "momentum",
      "reason_codes": ["dead_zone_active_within_decay_window"],
      "suppression_until_utc": "2026-05-11T12:00:00+00:00",
      "time_since_last_attempt_days": 2
    }
  ]
}
```

---

## 7. Integration plan (phased, throughput-aware)

Throughput is currently <10 runs/week, so each phase needs a real
calendar window — not "after N PRs".

### Phase 1 — Shadow / Simulation (v3.15.12, build now)

- Add `research/funnel_spawn_proposer.py`.
- Lifecycle hook in `run_research.py` calls
  `write_spawn_proposals_artifact(...)` after `write_viability_artifact`
  and `append_proposal_history(...)` for kept proposals.
- Wrap in its own try/except + `tracker_event` (same pattern as
  v3.15.11 modules).
- Add `/api/research/spawn-proposals` read-only passthrough.
- Extend `ResearchIntelligenceCard` to show top 3 proposals (priority
  + spawn_reason), suppressed zone count, and human-review flag.
- No execution change. Operator reads weekly.
- Tests: ≥15 unit + 1 integration test (covers all 6 hardenings).
- Duration: ≥4 calendar weeks AND ≥30 completed campaigns, whichever
  is later.

### Phase 2 — Evaluation (v3.15.13 or v3.16.x)

- Add `research/proposal_evaluation.py` + sidecar
  `proposal_vs_actual_latest.v1.json`.
- For each completed campaign, look up whether it appeared in the
  most-recent `spawn_proposals_latest.v1.json` and compare:
  - did proposals lead to higher meaningful_campaign_rate than
    non-proposed campaigns?
  - did proposals reach paper_ready faster?
  - did exploration reservation hit `EXPLORATION_RESERVATION_PCT`
    AND scope-spread targets?
  - did dead-zone decay re-discover any meaningful campaigns?
- Operator reviews. Adjust constants (only) if needed. Constants
  changes require PR review.
- Continues until proposal-vs-actual delta is statistically credible
  on operator judgement (NOT on a hidden score).

### Phase 3 — Gated consumption (deferred, post-validation)

- `campaign_policy.decide()` optionally consumes
  `spawn_proposals_latest.v1.json` behind a config flag
  (default OFF).
- Per-category caps from operator config (e.g.
  `max_confirmation_proposals_per_day`,
  `min_exploration_proposals`).
- The flag-flip is the only consent gate. Rollback by flipping back.
- The regression test
  `test_campaign_policy_decide_signature_unchanged` MUST be updated
  in the same release that introduces the kwarg, so a future
  reviewer can see the boundary moved deliberately.

---

## 8. Risks and mitigations

| Risk | Likelihood (low data) | Mitigation |
|---|---|---|
| Premature suppression of exploration | medium | R7 reservation budget + scope-spread floor (families/assets/timeframes). R4 dead-zone DECAY (14 days default) — never permanent suppression on low data. |
| Bias reinforcement loop (confirm → propose more confirms) | low | R9-cooldown: 7-day fingerprint cooldown blocks identical re-proposals. R9-active blocks if the campaign is already queued. Idempotent across runs. |
| Over-reliance on early weak signals | high | Rules use BUCKETS (high/medium/low/none), not numeric scores. Phase 1 shadow-only — no consumption until Phase 2 validates. |
| Low data instability | high | Rules use HARD COUNTS (`5+ rejections`, `time_since_last >= 14 days`), not rates. Counts are stable under low data. |
| Feedback loop with `campaign_funnel_policy` | medium | Same fingerprint scheme. COL queue idempotency is the final guarantee — already enforced. |
| Operator paralysis (too many proposals) | medium | R10 cap at MAX_PROPOSALS_PER_RUN_NORMAL=10. Card shows top 3 only. |
| Compute starvation of edge cases | medium | R7 scope-spread enforcement: families/assets/timeframes coverage NOT just %. |
| Schema drift between proposer and a future autonomous consumer | low | `mode` and `proposal_mode` at top-level. Future consumer must check `mode == "shadow"` and refuse to consume; only Phase 3 release flips it. |
| `viability == stop_or_pivot` ignored | medium | R8: `proposal_mode = "diagnostic_only"`, drop HIGH-tier, cap at 3, allow only LOW (exploration / diversification). Behavior changes — not just a flag. |
| Reason trace gets ignored | low | Frontend card surfaces `reason_trace` on hover/click for top proposals. Forces operator to look. |

---

## 9. Final recommendation

**Build it now. Option 1: advisory-only proposer in shadow mode (v3.15.12).**

Reasoning:

- **Shadow mode is risk-free.** No execution change. Just two extra
  sidecars + an extra card section + an extra API endpoint. Same
  try/except discipline as v3.15.11 means any failure cannot mask
  the run's original outcome.
- **Validation needs the artifact to exist.** Phase 2 (evaluation)
  compares proposals to actuals. Without proposals there is nothing
  to compare. Delaying Phase 1 delays Phase 2 by the same amount.
- **Throughput will only grow.** Building the proposer now means by
  the time throughput reaches "interesting" volume, the proposal
  quality is already audited.
- **Build it as if it will be trusted later.** The six hardenings
  (strong fingerprint + cooldown, scope-spread coverage, dead-zone
  decay, `proposal_mode`, priority enum, `reason_trace`) make the
  Phase 3 trust gate technically achievable instead of a leap of
  faith.

What I would NOT do now:

- Don't build evaluation (Phase 2) until Phase 1 has data.
- Don't touch `campaign_policy.decide()`.
- Don't add config flags for autonomous consumption.
- Don't extend `campaign_funnel_policy` — keep concerns separate.
- Don't build a "minimal version". The minimum useful version IS this
  scope — cutting any of the six hardenings cripples Phase 2.

---

## 10. MUST HAVE before implementation (operator checklist)

| # | Requirement | Source rule |
|---|---|---|
| 1 | Strong `proposal_fingerprint` over 6 fields (hypothesis, preset, grid signature, timeframe, asset, proposal_type) | §5.1 |
| 2 | Per-fingerprint cooldown via append-only history JSONL (default 7 days) | R9-cooldown, R11 |
| 3 | Exploration coverage enforced over BOTH percentage AND scope spread (families ≥ 3, assets ≥ 3, timeframes ≥ 2 with graceful fallback) | R7 |
| 4 | Dead-zone suppression decays after `DEAD_ZONE_DECAY_DAYS` (14) — never permanent on low data | R4-decay |
| 5 | `viability == stop_or_pivot` toggles `proposal_mode = "diagnostic_only"`, drops HIGH-tier, caps at 3 | R8 |
| 6 | Deterministic `priority_tier` enum (HIGH / MEDIUM / LOW / SUPPRESSED) — not `+1`/`0` integers | §5.3 |
| 7 | `reason_trace` on every proposal AND every suppressed zone, ordered by rule evaluation | §5.2 |
| 8 | Top-level `enforcement_state="advisory_only"` AND `mode="shadow"` (separate from `proposal_mode`) | §4 |
| 9 | `test_campaign_policy_decide_signature_unchanged` regression still green | §1 |
| 10 | Two sidecars: snapshot (`spawn_proposals_latest.v1.json`) + history (`spawn_proposal_history.jsonl`) | §3 |

All 10 items are MUST HAVE before merging v3.15.12 to main.
