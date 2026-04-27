# Research Intelligence Layer (v3.15.11)

> **Positioning**: advisory observability, not autonomous control.
> Every artifact in this layer is read-only signal for the operator
> (and, in a future release, for `campaign_policy.decide()`). Nothing
> in this layer freezes a preset, retires a hypothesis, mutates the
> queue, or enforces a recommendation today.

---

## 1. Purpose

After v3.15.8–v3.15.10 closed the funnel (sampling → evidence →
policy), the research engine produces enough information per campaign
to answer questions it could not previously answer:

- *What did we learn this week?*
- *Which hypotheses keep failing the same way?*
- *Where is compute being burned without producing candidates?*
- *Is the project still worth pursuing within the current hypothesis
  space?*

v3.15.11 turns that information into five deterministic, JSON-safe
sidecars under `research/campaigns/evidence/`. Operators read them;
the dashboard renders them; nothing is automatically actioned.

## 2. What this layer does NOT do

- Modify `campaign_policy.decide()` (regression-tested).
- Mutate `campaign_evidence_ledger.jsonl`, the campaign registry,
  the queue, or any frozen contract.
- Promote, retire, freeze, or cooldown anything automatically.
- Use ML, black-box scoring, or hidden heuristics. Every weight,
  threshold, and bucket is a named module-level constant.
- Make a financial recommendation. The viability verdict is *research*
  viability — "are we learning?" not "are we making money?".

## 3. Artifacts

All artifacts share the `_sidecar_io` canonical-write contract:
sorted keys, indent=2, LF newlines, atomic rename. Repeated builds
on identical inputs produce byte-identical files.

| Path | Module | Schema |
|---|---|---|
| `research/campaigns/evidence/evidence_ledger_latest.v1.json` | `research/research_evidence_ledger.py` | 1.0 |
| `research/campaigns/evidence/information_gain_latest.v1.json` | `research/information_gain.py` | 1.0 |
| `research/campaigns/evidence/stop_conditions_latest.v1.json` | `research/stop_condition_engine.py` | 1.0 |
| `research/campaigns/evidence/dead_zones_latest.v1.json` | `research/dead_zone_detection.py` | 1.0 |
| `research/campaigns/evidence/viability_latest.v1.json` | `research/viability_metrics.py` | 1.0 |

The five writes are wrapped in their own try/except inside
`run_research.py`'s finalisation block, so any one failure surfaces
as a `tracker_event` without masking the original research outcome.

## 4. Schema overview

### 4.1 Evidence Ledger

Rolled-up snapshot of `campaign_evidence_ledger.jsonl` joined with
`screening_evidence_latest.v1.json` (for hypothesis enrichment) and
`candidate_registry_latest.v1.json` (for candidate lineage).

Top-level: `schema_version`, `generated_at_utc`, `git_revision`,
`run_id`, `col_campaign_id`, `source_artifacts`, `summary`,
`hypothesis_evidence[]`, `failure_mode_counts[]`,
`candidate_lineage[]`.

`hypothesis_evidence` rows roll per `(preset_name, hypothesis_id,
strategy_family)` and carry `campaign_count`, `exploratory_pass_count`,
`promotion_candidate_count`, `paper_ready_count`, `rejection_count`,
`technical_failure_count`, `degenerate_count`, `dominant_failure_mode`,
`last_outcome`, `last_seen_at_utc`.

Degenerate outcomes (`degenerate_no_survivors`,
`completed_no_survivor`) are routed to `degenerate_count`, NOT
`technical_failure_count` — they remain meaningful research signals.

### 4.2 Information Gain

Per-campaign deterministic score in `[0.0, 1.0]` with a named bucket
(`none` / `low` / `medium` / `high`) and explicit reason list. A
campaign is "meaningful" iff `bucket >= medium`.

Constants (in `research/information_gain.py`):

```
IG_TECHNICAL_FAILURE      = 0.0   # short-circuit
IG_DUPLICATE_REJECTION    = 0.1
IG_NEW_FAILURE_MODE       = 0.5
IG_NEAR_CANDIDATE         = 0.8
IG_EXPLORATORY_PASS       = 0.8
IG_PROMOTION_CANDIDATE    = 0.9
IG_PAPER_READY            = 1.0
IG_COVERAGE_BONUS_MAX     = 0.2   # additive, capped
IG_COVERAGE_BONUS_FLOOR   = 0.80  # below this, no bonus
```

A `technical_failure` is never meaningful regardless of any other
signal. Coverage adds a small additive bonus that cannot push a
duplicate-rejection campaign past the `medium` floor — coverage
enables learning, it does not constitute it.

### 4.3 Stop Conditions (ADVISORY)

Recommends `NONE` / `COOLDOWN` / `FREEZE_PRESET` /
`RETIRE_HYPOTHESIS` / `RETIRE_FAMILY` / `REVIEW_REQUIRED`.

**Field name is `recommended_decision`, not `decision`. Every
artifact carries `enforcement_state="advisory_only"` at top level
and on each decision record.**

Constants (in `research/stop_condition_engine.py`):

```
STOP_INSUFFICIENT_TRADES_COOLDOWN = 3
STOP_REPEAT_REJECTION_FREEZE      = 5
STOP_REPEAT_REJECTION_RETIRE      = 10
STOP_TECHNICAL_FAILURE_REVIEW     = 3
STOP_NO_INFO_REVIEW               = 10
```

Safety invariants enforced by the engine:

- `technical_failure` evidence routes to `REVIEW_REQUIRED`, never
  `RETIRE_*`.
- Any `promotion_candidate_count` or `paper_ready_count > 0`
  protects the scope from `FREEZE_PRESET` and `RETIRE_*`.
- Repeated `degenerate_no_survivors` keeps counting as a
  research-meaningful signal.

### 4.4 Dead-Zone Detection

`(asset × timeframe × strategy_family)` zones with status
`insufficient_data | unknown | alive | weak | dead`.

Timeframe is currently `"unknown"` for every zone — ledger events
do not yet carry interval; v4 enrichment will fill it in. The
`(asset, family)` view is the actionable operator scope.

Dead fires only when ALL of:

- `campaign_count >= DZ_MIN_CAMPAIGNS (5)`
- no candidate or paper-ready evidence
- `failure_density >= DZ_DEAD_FAILURE_DENSITY (0.80)`
- `information_gain_rate <= DZ_DEAD_INFORMATION_GAIN_RATE (0.10)`

Detection signals only — it never removes strategies or presets.

### 4.5 Viability

Conservative verdict `insufficient_data | promising | weak |
commercially_questionable | stop_or_pivot` plus cost-per-X metrics.

Constants (in `research/viability_metrics.py`):

```
VIABILITY_MIN_CAMPAIGNS               = 20
VIABILITY_MEANINGFUL_RATE_PROMISING   = 0.50
VIABILITY_MEANINGFUL_RATE_WEAK        = 0.10
VIABILITY_LARGE_WINDOW                = 100
```

Cost denominators are guarded by `_safe_div`: zero denominators
collapse to `null` rather than NaN/inf. When
`estimated_compute_cost` is omitted, every cost metric is `null`.

This is research viability, not financial advice.

## 5. Reading order for operators

A normal post-deploy check works top-down:

1. **`/api/research/intelligence-summary`** — does `viability.status`
   look right for the current week's campaigns? If `promising` or
   `weak`, you're learning. If `commercially_questionable` or
   `stop_or_pivot`, dig further.
2. **`/api/research/dead-zones`** — any zones marked `dead`? If yes,
   look at the `dominant_failure_mode` to understand the structural
   gap.
3. **`/api/research/stop-conditions`** — any `RETIRE_*` or
   `FREEZE_PRESET` recommendations? Read the `reason_codes` and the
   `evidence` block before doing anything manually.
4. **`/api/research/information-gain`** — last campaign's score and
   reasons.
5. **`/api/research/evidence-ledger`** — the rolled snapshot. Useful
   when investigating a specific preset/hypothesis lineage.

## 6. Cross-version dependencies

This layer assumes:

- **v3.15.5** outcome semantics: distinguishes
  `degenerate_no_survivors` / `research_rejection` /
  `technical_failure` (and never re-emits `worker_crashed`).
- **v3.15.6** `screening_phase` literal propagation
  (`exploratory` / `standard` / `promotion_grade`).
- **v3.15.7** exploratory criteria
  (expectancy/profit_factor/drawdown), `pass_kind` tagging.
- **v3.15.9** `screening_evidence_latest.v1.json` for hypothesis
  enrichment + sampling block. Layer degrades gracefully when this
  artifact is absent on a fresh deploy.
- **v3.15.10** funnel decisions in the campaign policy ledger.

Frozen contracts (`research_latest.json`, `strategy_matrix.csv`,
`candidate_registry_latest.v1.json` schema) are NEVER touched.

## 7. How this supports a future v3.16 gate

A future v3.16 release may consume these advisory recommendations
in `campaign_policy.decide()` to make autonomous decisions. Until
then:

- `enforcement_state="advisory_only"` is the contract that prevents
  that consumption from happening accidentally.
- The `recommended_decision` field name (vs `decision`) is the
  schema-level signal that this is *advice*.
- A regression test
  (`test_campaign_policy_decide_signature_unchanged`) pins the
  policy boundary so a future autonomous-control release must
  update that test alongside the consumption code.

## 8. After deploy — what to look for

If `viability.status` stays at `insufficient_data` after deploy,
that's expected — the layer needs `VIABILITY_MIN_CAMPAIGNS` (20)
historic completed campaigns before it can produce a verdict.

If `viability.status` says `commercially_questionable` or
`stop_or_pivot` AFTER 100+ campaigns and you have not yet
investigated the dominant failure modes per dead zone — investigate
those first. Do NOT immediately retire hypotheses. The advisory
recommendations are inputs to a human decision, not outputs.
