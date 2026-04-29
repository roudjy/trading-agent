# Changelog

All notable changes to the trading-agent research and backtesting
stack are documented here. Live trading / orchestration surfaces
outside the research path are not tracked in this file.

## [v3.15.15.9] — Sprint Progress Freshness Repair

Date: 2026-04-29
Branch: `feat/sprint-progress-launcher-hook-v3-15-15-9`

Fixes the long-standing "sprint progress sidecar is hours stale"
finding that v3.15.15.6 surfaced as the warning
``sprint_progress_stale_relative_to_registry``. Pre-v3.15.15.9 the
``discovery_sprint_progress_latest.v1.json`` artifact was only refreshed
when an operator manually invoked ``python -m research.discovery_sprint
status``; the systemd timer fires
``research.campaign_launcher`` (not the sprint CLI), so live progress
naturally drifted by tens of hours during normal operation.

### What changed

Refactored the side-effect body of ``cmd_status`` into a non-CLI
callable ``research.discovery_sprint.update_sprint_progress(now_utc=None)``
and invoked it from the campaign launcher tick AFTER ``assert_invariants``
succeeds. The hook is wrapped in a defensive try/except so it can never
block the launcher tick.

| File | Change | Lines |
|---|---|---|
| `research/discovery_sprint.py` | extracted `update_sprint_progress()` from `cmd_status`; `cmd_status` becomes a thin shim | +112 / -55 |
| `research/campaign_launcher.py` | imported `update_sprint_progress`; added the post-tick hook | +18 |
| `tests/unit/test_sprint_progress_launcher_hook.py` | new file — 9 unit tests for the contract | +220 |
| `VERSION` | `3.15.15.8` → `3.15.15.9` | 1 |
| `CHANGELOG.md` | this entry | ~115 |

### Files explicitly NOT touched

- `research/campaign_registry.py`, `research/campaign_queue.py`
- `research/diagnostics/*` — unchanged. The aggregator's existing
  `sprint_progress_stale_relative_to_registry` warning is now expected
  to clear naturally on the next tick after deploy.
- `dashboard/`, `frontend/`, `agent/`, `strategies/`, `orchestration/`
- `ops/systemd/*` — no timer install/enable/start
- All frozen contracts

### Contract: `update_sprint_progress(now_utc=None) -> dict | None`

Pure side-effect callable. **Never raises.** Returns the just-written
progress payload as a dict, or `None` for any of:

- no sprint registry artifact (normal "no active sprint" state)
- corrupt sprint registry payload (warning emitted to stderr)
- missing `started_at_utc` / `expected_completion_at_utc` (warning)
- IO failure writing the progress sidecar (warning)
- write failure during state transition (progress sidecar still landed;
  warning surfaces, function returns the partially-completed summary)

Side effects, in order:

1. Always writes a fresh `SPRINT_PROGRESS_PATH` when a sprint exists
   and timestamps parse.
2. Writes `SPRINT_REGISTRY_PATH` only when crossing `target_met` or
   `expired` thresholds (state transition).

The returned dict, when non-`None`, carries every key the legacy
`cmd_status` JSON output emitted — so the CLI shim is byte-equivalent
to the v3.15.15.8 surface.

### Launcher-tick safety analysis

| Concern | Mitigation |
|---|---|
| Sprint sidecar corruption blocks the tick | hook is wrapped in try/except + the function itself never raises |
| Disk-full during sprint write blocks campaign artifact persistence | hook fires AFTER `assert_invariants`, so registry / queue / ledger / digest are ALREADY persisted; sprint write failure is contained |
| Stale registry → confusing observed counts | sprint progress is descriptive, not prescriptive — a stale count just under-reports observations until the next tick |
| Sprint registry transition writes after a tick crash | a tick that crashes mid-state-transition leaves the progress sidecar fresh and the registry unchanged; on the NEXT tick the hook re-evaluates the same transition and (idempotently) re-issues it |
| Hook becomes a hidden coupling between launcher and sprint module | already present from v3.15.14: `load_active_sprint_constraints`, `apply_sprint_routing`, `sprint_extra_for_record`. This release adds **one more** callable from the same module — no new module dependency |

### Cleanup / canonicalization (v3.15.15.9)

| Item | Location | Classification | Action |
|---|---|---|---|
| `cmd_status` body duplicated logic with `cmd_run` | `discovery_sprint.py:1336-1383` and `:1402-1485` | dead-code-ish (acceptable) | KEEP — `cmd_run` is sprint-creation, not sprint-progress; merging would tangle two concerns. The shared `build_progress_payload` already factors out the inner write. |
| `_write_ledger`, `_record_digest` patterns in launcher | `campaign_launcher.py:407-424` | canonical | KEEP — same try/except safety pattern applied to the new sprint hook |
| `sprint_progress_stale_relative_to_registry` warning | `aggregator.py + paths.py` | canonical, transitional | KEEP — still useful as a diagnostic during the soak window; once the hook is proven on live VPS, a future release may drop the warning entirely |
| CLI vs launcher invocation paths | `cmd_status` and `update_sprint_progress` | canonical now | the legacy CLI invocation `python -m research.discovery_sprint status` continues to work; AGENTS / docs keep both paths |

No destructive cleanup performed.

### Tests

- `tests/unit/test_sprint_progress_launcher_hook.py` (+9):
  - `test_update_sprint_progress_returns_none_when_no_sprint`
  - `test_update_sprint_progress_returns_none_on_corrupt_registry`
  - `test_update_sprint_progress_writes_progress_sidecar_on_happy_path`
  - `test_update_sprint_progress_returns_full_summary_dict`
  - `test_update_sprint_progress_does_not_raise_on_io_failure`
  - `test_cmd_status_is_thin_shim_over_update_sprint_progress`
  - `test_cmd_status_emits_full_summary_when_active`
  - `test_update_sprint_progress_state_transition_to_completed_writes_registry`
  - `test_update_sprint_progress_never_raises_on_unparseable_timestamps`
- All 68 pre-existing `test_discovery_sprint*.py` tests remain green
  (no behavior change to `cmd_status` JSON output).

### Validation

```
$ pytest tests/unit/test_sprint_progress_launcher_hook.py -q
                          9 passed in 1.13s            (gate 1)

$ pytest tests/unit/test_discovery_sprint*.py tests/unit/test_sprint_progress_launcher_hook.py -q
                       77 passed                       (gate 2)

$ pytest tests/unit/ -q
                       2276 passed, 3 skipped          (gate 3; +9 from v3.15.15.8)

$ pytest tests/functional --run-functional -q
                       23 passed                       (gate 4 — harness untouched)
```

Frozen contract md5s unchanged (canonical LF):
- `research/research_latest.json`: 1b4bf00b4e58b1f810fd9d2c3914b9f8
- `research/strategy_matrix.csv`: fb879837f358792cfc00a0b821df7279

### Expected live impact post-deploy

| `/api/observability/summary` field | Pre-deploy | Post-first-tick |
|---|---|---|
| `summary.warnings` includes `sprint_progress_stale_relative_to_registry` | yes | **no** (mtime gap drops below 1 hour after first tick) |
| `discovery_sprint_progress_latest.v1.json` mtime | 19h+ stale | within minutes of registry mtime |
| `update_sprint_progress` invocations per tick | 0 | 1 |
| Tick wall-clock duration | unchanged | unchanged (sprint update completes in <100 ms) |

### Roll-back

`git revert -m 1 <merge-commit>` fully reverses. The new sprint
progress sidecar shape is identical to the legacy shape (the same
`build_progress_payload` produces it), so revert leaves on-disk
artifacts intact.

## [v3.15.15.8] — Registry Metadata Enrichment

Date: 2026-04-29
Branch: `feat/registry-metadata-enrichment-v3-15-15-8`

Closes the writer-side gap that v3.15.15.6 surfaced as
``hypothesis_id_missing_from_source_artifact``,
``strategy_family_field_present_but_unpopulated_by_writer``, and
``asset_class_field_present_but_unpopulated_by_writer``. Now that the
diagnostics read path is fully wired (v3.15.15.7), the next bottleneck
is metadata at the registry: the launcher already knew the preset name
at spawn time but never resolved it back to its hypothesis catalog row.

### Schema additions on `CampaignRecord`

| Field | Was | Now | Source at spawn time |
|---|---|---|---|
| `hypothesis_id` | absent | `str \| None = None` | `preset.hypothesis_id` |
| `strategy_family` | `str \| None = None`, always null | populated when hypothesis_id resolves | `STRATEGY_HYPOTHESIS_CATALOG[hypothesis_id].strategy_family` |
| `asset_class` | `str \| None = None`, always null | populated for every preset | `infer_asset_class(preset.universe)` |
| `universe` | absent | `tuple[str, ...] = ()` | `tuple(preset.universe)` |

Boundary rule per the v3.15.15.8 audit: each addition is (a) known at
spawn time, (b) stable for the campaign's lifetime, (c) needed for
failure clustering / dead-zone detection. Per-run / per-candidate /
per-screening detail does NOT live on the registry record — it lives
in evidence sidecars.

Explicit non-additions (deferred to later releases or never):
`timeframe`, `market_regime`, `failure_subreason`, `proposal_fingerprint`,
`causal_chain`, candidate counts, screening reason histograms, policy
decision blobs.

### Files modified

| File | Change | Lines |
|---|---|---|
| `research/campaign_registry.py` | added `hypothesis_id` and `universe` fields with backward-compatible defaults | +13 |
| `research/discovery_sprint.py` | added public alias `infer_asset_class = _infer_asset_class` (canonicalization, non-destructive) | +5 |
| `research/campaign_launcher.py` | new `_resolve_metadata_for_preset()` resolver; `_build_record` populates the four new keys | +44 |
| `tests/unit/test_campaign_registry.py` | six v3.15.15.8 unit tests (defaults, populated, mixed-registry, byte-reproducible writes, transition+outcome preservation) | +95 |
| `tests/unit/test_campaign_launcher_metadata_resolver.py` | new file — nine resolver-purity tests | +95 |
| `tests/unit/test_observability_failure_modes.py` | two v3.15.15.8 diagnostics tests (limitations clear when populated; persist for legacy-only registries) | +75 |
| `VERSION` | `3.15.15.7` → `3.15.15.8` | 1 |
| `CHANGELOG.md` | this entry | ~125 |

### Files explicitly NOT touched

- `research/screening_evidence.py`, `research/run_research.py`
- `research/diagnostics/*` — diagnostics read surface unchanged; the
  same code now sees populated values for new records
- `dashboard/`, `frontend/`, `agent/`, `strategies/`, `orchestration/`,
  `execution/`, `automation/`, `state/`
- `ops/systemd/*` — no timer install/enable/start
- All frozen contracts (`research_latest.json`, `strategy_matrix.csv`)

### Backward compatibility

The 20 live VPS registry records lack `hypothesis_id` and `universe`
entirely and carry `strategy_family=null` / `asset_class=null`. All
consumers of these fields use `dict.get()` with null-tolerance:

- `campaign_digest._compute_by_candidate_family` — `if not family or not asset: continue`
- `campaign_launcher` family-state derivation — `if family and asset: families.append(...)`
- `campaign_policy._guess_family_key` — falls through to `"unknown|unknown"`
- `campaign_queue.queue_entry_from_record` — does NOT pass through the new keys at all
- `dead_zone_detection` — reads ledger events, not the registry
- `research/diagnostics/failure_modes.py` — already reports limitations
  when these are missing; will simply stop reporting them once
  populated records exist

Mixed-registry coexistence is permanent: legacy and new records share
the same registry artifact indefinitely. The two diagnostic limitation
codes survive until every record in the registry carries the new keys.
A new test in `test_observability_failure_modes.py` pins both halves of
this contract (limitations clear with populated record; limitations
persist with legacy-only record).

Deterministic serialization is preserved: `write_sidecar_atomic` uses
`json.dumps(..., sort_keys=True)`, so dataclass field order does not
affect the on-disk output. Adding fields with defaults does not
perturb the serialization of records that don't set them.

### Cleanup / canonicalization (v3.15.15.8 first pass)

Per the AUTO MODE stabilize+canonicalize mandate, audited the affected
surface for stale/dead/duplicate constructs:

| Item | Location | Classification | Action |
|---|---|---|---|
| `_infer_asset_class` private helper | `research/discovery_sprint.py:275` | canonical, but private | added public alias `infer_asset_class` (non-destructive — both names reference the same function object); avoids cross-module dependency on a private symbol |
| `worker_crashed` outcome literal | `research/campaign_registry.py:71-72,85` | compat-shim (DEPRECATED v3.15.5; historical records only) | KEEP — actively documented as backward-compat for legacy ledger entries; removal would invalidate the live ledger |
| `hypothesis_id_missing_from_source_artifact` limitation | `research/diagnostics/paths.py:255` + `failure_modes.py:570` | canonical, transitional | KEEP — drops naturally from emission once populated records exist; mixed-registry safety preserved |
| `strategy_family_field_present_but_unpopulated_by_writer` | `paths.py:256` | canonical, transitional | KEEP — same rationale |
| `asset_class_field_present_but_unpopulated_by_writer` | `paths.py:257` | canonical, transitional | KEEP — same rationale |
| `FUTURE_WRITER_FIELDS` list | `failure_modes.py:70-81` | canonical | KEEP unchanged this release — entries pin diagnostic intent; once the live registry has only post-v3.15.15.8 records, a future release can shrink the list |

No destructive cleanup performed. No file deleted. No constant renamed.
No frozen-contract impact.

### Tests

- `tests/unit/test_campaign_registry.py` (+6 new):
  - `test_v3_15_15_8_record_defaults_for_new_metadata_fields`
  - `test_v3_15_15_8_record_round_trips_with_metadata_populated`
  - `test_v3_15_15_8_legacy_record_without_new_keys_loads_via_dict_get`
  - `test_v3_15_15_8_write_registry_byte_reproducible_with_metadata`
  - `test_v3_15_15_8_transition_state_preserves_metadata`
  - `test_v3_15_15_8_record_outcome_preserves_metadata`
- `tests/unit/test_campaign_launcher_metadata_resolver.py` (+9 new):
  pins resolver behaviour for active-discovery presets (trend_pullback,
  vol_compression_breakout 1h+4h), preset-without-hypothesis_id
  (crypto_diagnostic_1h), equity universe presets, unknown preset
  fallback, empty-tuple invariant, purity.
- `tests/unit/test_observability_failure_modes.py` (+2 new):
  - `test_v3_15_15_8_diagnostic_limitations_clear_when_metadata_populated`
  - `test_v3_15_15_8_diagnostic_limitations_persist_for_legacy_only_registry`

### Validation

```
$ pytest tests/unit/test_campaign_registry.py tests/unit/test_campaign_launcher_metadata_resolver.py -q
                       30 passed in 1.20s          (gate 1)

$ pytest tests/unit/test_observability_*.py tests/unit/test_dashboard_api_observability.py tests/unit/test_campaign_registry.py tests/unit/test_campaign_launcher_metadata_resolver.py -q
                       243 passed in 6.99s         (gate 2)

$ pytest tests/unit/ -q
                       2267 passed, 3 skipped      (gate 3; +17 from v3.15.15.7)

$ pytest tests/functional --run-functional -q
                       23 passed in 4.04s          (gate 4 — harness untouched)

$ pytest tests/unit/test_observability_static_import_surface.py tests/unit/test_observability_no_other_artifacts_mutated.py -q
                       24 passed                    (gate 5 — diagnostics import surface still isolated)
```

Frozen contract md5s unchanged:
- `research/research_latest.json`: 5250ffa10e226b5b52424fb14c86814b
- `research/strategy_matrix.csv`: fb879837f358792cfc00a0b821df7279

### Expected live impact post-deploy

The launcher tick spawns at most a handful of campaigns per cycle.
After the first new spawn:

| `/api/observability/failure-modes` field | Pre-deploy | Post-first-new-spawn |
|---|---|---|
| `diagnostic_context.limitations` includes `hypothesis_id_missing_from_source_artifact` | yes | **no** (mixed registry, but `has_any_*` flips True) |
| `diagnostic_context.limitations` includes `strategy_family_field_present_but_unpopulated_by_writer` | yes | **no** |
| `diagnostic_context.limitations` includes `asset_class_field_present_but_unpopulated_by_writer` | yes | **no** |
| `by_hypothesis_id` | empty | populated for new records |
| `by_strategy_family` | empty | populated for new records |
| `repeated_failure_clusters[*].cluster_key_quality` | mostly `partial`/`weak` | new records can score `full` |

Note: the `hypothesis_id`/`strategy_family`/`asset_class` keys are
populated for new spawns only. The 20 legacy records on the live VPS
remain in their pre-v3.15.15.8 shape (no destructive migration).

### Not changed (intentional, deferred)

- v3.15.15.9 — sprint-progress writer hook (separate audit + release)
- v3.15.16+ — dormant evidence cluster activation (separate audit)
- `timeframe` field on registry — requires preset-side schema work
- `market_regime` field — requires runtime emission
- candidate counts / screening reason histograms / policy decision
  blobs on the registry — wrong layer; belong in evidence sidecars
- per-spawn `proposal_fingerprint`, `causal_chain` — out of scope

### Roll-back

Single commit, additive only. `git revert -m 1 <merge-commit>` fully
reverses with no migration cost. Mixed-registry records survive a
revert because consumers tolerate both shapes; new records carry the
extra keys but those keys decay gracefully when `_build_record`
returns to its pre-v3.15.15.8 signature.

## [v3.15.15.7] — Evidence Path Hotfix + Diagnostics Re-read

Date: 2026-04-29
Branch: `feat/diagnostics-path-hotfix-v3-15-15-7`

Single-file diagnostics path fix. Read-only. Zero behavior change.
**No edits to runtime / launcher / registry / sprint / writer / dashboard /
frontend / agent / strategies / orchestration / execution / automation / state
code.**

### Bug

Pre-v3.15.15.7 ``research/diagnostics/paths.py`` declared:

    CAMPAIGN_EVIDENCE_LEDGER_PATH = RESEARCH_DIR / "campaign_evidence_ledger.jsonl"

But the campaign launcher writes the canonical event ledger to:

    research/campaign_evidence_ledger_latest.v1.jsonl

(see ``research/campaign_launcher.py:139``: ``EVIDENCE_LEDGER_PATH = "research/campaign_evidence_ledger_latest.v1.jsonl"``).
The path mismatch caused ``read_jsonl_tail_safe`` to silently return
``state="absent"`` on every read, even though the launcher had been
appending events to disk on every tick since the project's start.

Live VPS at the time of fix: 80 events on disk in
``campaign_evidence_ledger_latest.v1.jsonl``, all invisible to diagnostics.

The v3.15.15.6 ``diagnostic_context.limitations`` entry
``campaign_evidence_ledger_absent`` was therefore a **false negative**
caused by the diagnostics constant, not by a missing writer.

### Fix

One-line constant value change in ``research/diagnostics/paths.py``:
``CAMPAIGN_EVIDENCE_LEDGER_PATH`` now points at
``campaign_evidence_ledger_latest.v1.jsonl`` (with the ``_latest.v1``
snapshot-current suffix used by every other artifact in the project).

A second matching update in the ``INPUT_ARTIFACTS`` table inside the same
file ensures ``artifact_health`` reads the same canonical filename.

### Tests

- ``tests/unit/test_observability_paths.py``:
  - extended ``DRIFT_CHECKS`` with
    ``("campaign_evidence_ledger_latest.v1.jsonl", "campaign_launcher.py")`` —
    a text-only drift assertion that pins both ``paths.py`` and the writer
    constant in the launcher (no module imports of the launcher; the test
    parses it as plain text).
  - new ``test_no_pre_v3_15_15_7_wrong_ledger_path_anywhere_in_diagnostics``:
    scans every ``.py`` file under ``research/diagnostics/`` AS TEXT and
    fails if the OLD wrong filename ``"campaign_evidence_ledger.jsonl"``
    (no ``_latest.v1`` suffix) reappears as a string literal.
  - new ``test_campaign_evidence_ledger_path_constant_uses_latest_v1_suffix``:
    pins the imported runtime ``Path`` object's filename so a future
    refactor cannot silently regress.
- ``tests/unit/test_observability_failure_modes.py``:
  - new ``test_ledger_available_true_when_file_exists_at_real_writer_path``:
    builds a synthetic ledger at the real writer-path filename, runs
    ``build_failure_modes_artifact``, asserts ``diagnostic_mode = ledger_enriched``
    and ``ledger_available = True`` and the ``campaign_evidence_ledger_absent``
    limitation is dropped.
  - new ``test_ledger_unavailable_when_only_old_wrong_path_exists``:
    plants a file at the OLD wrong filename and verifies diagnostics does
    NOT silently fall back to it. Hard regression guard against a
    well-intentioned future "make it forgive both paths" change that would
    mask the drift test.
  - new ``test_campaign_evidence_ledger_path_constant_has_latest_v1_suffix``:
    belt-and-braces companion to the drift test.

### Validation

```
$ pytest tests/unit/test_observability_paths.py -q
                       17 passed in 0.07s        (gate 1)

$ pytest tests/unit/test_observability_failure_modes.py -q
                       58 passed in 0.21s        (gate 2)

$ pytest tests/unit/test_observability_*.py tests/unit/test_dashboard_api_observability.py -q
                       211 passed in 6.33s       (gate 3)

$ pytest tests/functional --run-functional -q
                       23 passed in 3.62s        (gate 4)

$ pytest tests/unit/ -q
                       2250 passed, 3 skipped    (gate 5; was 2244 pre-patch; +6 from this release)

$ pytest tests/unit/test_observability_static_import_surface.py -q
                       23 passed in 0.21s        (gate 7 — static import surface still green)
```

Frozen contract md5s unchanged (gate 6):
- ``research/research_latest.json``: 5250ffa10e226b5b52424fb14c86814b
- ``research/strategy_matrix.csv``: fb879837f358792cfc00a0b821df7279

### Expected live impact post-deploy

| Field on ``/api/observability/failure-modes`` | Pre-deploy | Post-deploy |
|---|---|---|
| ``diagnostic_context.ledger_available`` | ``false`` | ``true`` |
| ``diagnostic_context.diagnostic_mode`` | ``registry_plus_digest_enriched`` | ``ledger_enriched`` |
| ``diagnostic_context.limitations`` includes ``campaign_evidence_ledger_absent`` | yes | no |
| ``top_failure_reasons`` populated | yes (registry-derived) | at least as populated, ledger may add |
| ``repeated_failure_clusters`` populated | yes (5 entries, partial-quality) | at least as populated |
| ``by_worker_id`` populated | yes (19 entries) | at least as populated; ledger lease events may add |

### Not changed (intentional)

- ``research/campaign_launcher.py`` — read as text only by the path-drift test, never imported, never modified
- ``research/campaign_registry.py``, ``research/discovery_sprint.py``, ``research/run_research.py``, ``research/screening_evidence.py``, ``research/presets.py``, ``research/strategy_hypothesis_catalog.py`` — entirely untouched
- ``dashboard/``, ``frontend/`` — entirely untouched
- ``ops/systemd/`` — no timer install/enable/start
- All other diagnostics modules (``aggregator.py``, ``failure_modes.py``,
  ``throughput.py``, ``system_integrity.py``, ``artifact_health.py``,
  ``cli.py``, ``clock.py``, ``io.py``) — entirely untouched
- All frozen contracts

### Deferred

The wider Phase 1 audit findings remain open and are slated for separate releases:

- **v3.15.15.8** — Registry metadata enrichment (``hypothesis_id`` field;
  populate ``strategy_family``, ``asset_class``; add ``universe`` only after
  backward-compat proven). Requires its own audit + migration plan.
- **v3.15.15.9** — Sprint-progress freshness fix (refactor ``cmd_status``
  body into a callable; invoke from launcher post-tick). Requires its own
  launcher-tick safety analysis.
- **v3.15.16+** — Dormant evidence cluster activation (screening_evidence
  degenerate skeleton, rolled-up evidence ledger, spawn proposals, dead
  zones, information gain, stop conditions).

### Rollback

``git revert -m 1`` of the merge commit reverts the constant value plus the
test additions. Single-line code change; revert is trivial.

## [v3.15.15.6] — Diagnostics Evidence Completeness & Failure-Modes Enrichment

Date: 2026-04-29
Branch: `feat/diagnostics-evidence-completeness-v3-15-15-6`

Diagnostics-only patch. Read-only. Zero behavior change. Aligns the
diagnostics layer with the launcher's actual emitted shape, making
failure analysis honest in registry-only mode and reporting evidence
limitations explicitly. **No edits to runtime / launcher / policy /
sprint / strategy / dashboard / frontend code.**

### Phase 1 — Audit findings

Snapshotted the live VPS artifact set on 2026-04-29T08:54Z and
compared against the diagnostics parser:

* The launcher emits ``reason_code`` (not ``failure_reason``);
  diagnostics looked for ``failure_reason`` only → ``top_failure_reasons``
  was empty for every campaign.
* ``worker_id`` lives nested in ``lease.worker_id`` only;
  diagnostics looked at the top level → ``by_worker_id`` was empty.
* ``campaign_type`` was extracted only from the narrow failed-records
  filter (which excluded degenerate runs) → ``by_campaign_type`` was
  empty.
* ``hypothesis_id``, ``timeframe``, ``asset``, ``universe`` are not
  emitted by the writer at all today → diagnostics had no way to
  populate those breakdowns. Reported as
  ``future_writer_enrichment_required`` rather than guessed.
* ``strategy_family`` and ``asset_class`` keys are present in the
  record but always null in production → reported as
  ``field_present_but_unpopulated_by_writer``.
* The campaign digest exposes ``top_failure_reasons``,
  ``meaningful_by_classification``, and ``campaigns_by_type`` — none
  consumed by diagnostics → became fallback inputs in this release.
* Sprint progress sidecar runs ~18 hours stale relative to the
  registry on the live VPS — never surfaced as a warning.

### Phase 2 — Patch (additive, behavior-pure)

Files modified:

* ``research/diagnostics/paths.py``: new constants
  ``SPRINT_PROGRESS_STALE_VS_REGISTRY_SECONDS`` (default 1 hour),
  ``DIAGNOSTIC_MODES``, ``DIAGNOSTIC_EVIDENCE_STATUSES``,
  ``DIAGNOSTIC_LIMITATION_CODES`` — single source of truth for the
  vocabulary used by failure_modes / aggregator / tests.
* ``research/diagnostics/failure_modes.py``:
  - ``_enrich_record(...)`` extracts ``reason_code → failure_reason``
    alias, ``preset_name → preset`` alias, ``lease.worker_id →
    worker_id`` alias, ``strategy_family → family`` alias. Original
    record is not mutated.
  - ``_effective_failure_reason(...)`` resolves the effective
    failure-reason and reports a conflict when ``failure_reason`` and
    ``reason_code`` are both present and disagree (``failure_reason``
    wins; ``conflicting_failure_reason_fields`` limitation emitted).
  - ``_ledger_failure_events`` widened to recognise launcher-literal
    outcomes (``degenerate_no_survivors``, ``technical_failure``,
    ``worker_crashed``, ``research_rejection``, ``no_signal``,
    ``near_pass``, ``integrity_failed``, ``paper_blocked``).
  - ``_repeated_failure_clusters`` rewritten with full / partial / weak
    fallback-key strategy + ``cluster_key_quality`` reporting +
    threshold lowered to ``count >= 2``. Cluster row shape:
    ``{count, outcome_class, preset_name, hypothesis_id,
    strategy_family, timeframe, asset, cluster_key_quality, source}``.
  - ``by_campaign_type`` and ``by_meaningful_classification`` now
    aggregate across ALL campaigns (not the narrow failed-records
    subset) — populated in registry-only mode.
  - ``technical_vs_research_failure_counts`` ranges over ALL campaigns
    and adds ``degenerate_no_survivors`` + ``paper_blocked`` as
    first-class buckets.
  - ``top_failure_reasons`` falls back to digest's pre-computed
    counts when registry-derived reasons are empty (rows tagged
    ``source="digest"``).
  - New ``diagnostic_context`` block reports diagnostic_mode,
    evidence_available booleans, missing_evidence_artifacts,
    limitations (10 documented codes), and
    ``future_writer_enrichment_required`` (10 entries).
  - ``build_failure_modes_artifact`` now also reads digest +
    screening + rolled-up ledger + spawn-proposals to drive the
    diagnostic_context flags. Path defaults resolve at call time
    (monkeypatch-friendly).
* ``research/diagnostics/throughput.py``: added
  ``meaningful_by_classification_from_digest`` and
  ``campaigns_by_type_from_digest`` passthroughs (None when digest
  absent). Names explicitly tagged ``_from_digest`` so they cannot be
  confused with recomputed truth.
* ``research/diagnostics/aggregator.py``:
  - New ``infrastructure_status`` field — same enum semantics as
    ``overall_status`` (legacy field kept identical for backward-compat).
  - New ``diagnostic_evidence_status`` field — sourced from
    ``failure_modes.diagnostic_context.diagnostic_evidence_status``.
  - New ``diagnostic_mode`` field — sourced likewise.
  - Limitation strings from failure_modes propagated into
    ``warnings`` so an operator on ``/observability`` sees them.
  - Aggregate-level "diagnostic evidence partial/insufficient"
    warning fires when infrastructure is healthy but evidence is
    incomplete.
  - New ``sprint_progress_freshness`` block compares sprint-progress
    mtime against campaign-registry mtime; emits a WARNING ONLY
    when the delta exceeds
    ``SPRINT_PROGRESS_STALE_VS_REGISTRY_SECONDS`` (default 1h) —
    NEVER flips ``infrastructure_status`` to degraded.
* ``research/diagnostics/artifact_health.py``: minimal — added
  ``failure_stage`` to ``LINKED_ID_KEYS`` so
  ``public_artifact_status_latest.v1.json``'s
  ``last_attempted_run.failure_stage`` ("screening_no_survivors") is
  surfaced. No broader artifact_health redesign.

Tests added (107 new cases, 168 total in observability suites):

* 14 new failure_modes cases covering reason_code alias,
  lease.worker_id, by_campaign_type for ALL, by_meaningful_classification,
  conflicting fields, digest fallback, fallback-key cluster qualities,
  diagnostic_context shape per mode, no-over-inference of timeframe.
* 4 new throughput cases covering the digest passthroughs.
* 6 new aggregator cases covering split status fields, evidence-warning
  propagation, sprint-progress freshness (warning only).
* Functional harness extended: scenario A and scenario B now assert
  the new ``top_failure_reasons``, ``repeated_failure_clusters``,
  ``by_worker_id``, ``by_meaningful_classification``,
  ``diagnostic_context`` shape, ``technical_vs_research_failure_counts``
  with degenerate + paper_blocked first-class buckets, and the split
  status fields. **Zero xfails**.

### Live before/after on production VPS-shape data (20 campaigns)

| Field | Pre-v3.15.15.6 | Post-v3.15.15.6 |
|---|---|---|
| ``top_failure_reasons`` | ``[]`` | ``[degenerate_no_evaluable_pairs: 15, worker_crash: 4]`` |
| ``repeated_failure_clusters`` | ``[]`` | 5 entries (all partial-quality), e.g. ``trend_pullback_crypto_1h × 4 degenerate`` |
| ``by_worker_id`` | ``[]`` | 19 entries (extracted from ``lease.worker_id``) |
| ``by_campaign_type`` | ``[]`` | ``[daily_primary: 15, daily_control: 5]`` |
| ``by_meaningful_classification`` | not present | ``[meaningful_failure_confirmed: 15, uninformative_technical_failure: 4]`` |
| ``diagnostic_context`` | not present | mode=``registry_plus_digest_enriched``, evidence=``partial``, 10 limitations |
| ``technical_vs_research_failure_counts`` (degenerate / paper_blocked) | absent / absent | ``15`` / ``0`` |
| ``summary.infrastructure_status`` | not present | ``healthy`` |
| ``summary.diagnostic_evidence_status`` | not present | ``partial`` |
| ``summary.warnings`` (evidence) | not present | 10 ``diagnostic_evidence_limitation: …`` warnings + sprint-stale warning |
| ``summary.sprint_progress_freshness`` | not present | block populated, ``stale_relative_to_campaign_registry=true``, ``age_delta_seconds≈66752`` |

### Hard guarantees verified

* **Frozen contracts unchanged** — md5 ``5250ffa1…`` /
  ``fb879837…`` identical pre/post.
* **No edits to runtime files** — ``git status`` filter covers
  ``research/`` (other than ``research/diagnostics/``),
  ``agent/``, ``strategies/``, ``orchestration/``, ``execution/``,
  ``automation/``, ``state/``, ``dashboard/``, ``frontend/``: all
  untouched.
* **Backward compat** — ``overall_status`` retains legacy enum values
  + semantics; pre-v3.15.15.6 consumers continue to work without change.
* **All existing tests pass** — 2244 unit + 23 functional all green.

### Not done in this release (intentional)

* **No frontend / dashboard changes.** The new fields appear in the
  existing ``/api/observability/failure-modes`` and
  ``/api/observability/summary`` JSON automatically. Whether to
  surface them visually is a separate UX decision.
* **No writer / launcher changes.** Fields the writer doesn't emit
  today (``hypothesis_id``, ``timeframe``, ``asset``, ``universe``)
  are reported as ``future_writer_enrichment_required`` but not
  inferred or back-filled.
* **No systemd timer install** — unit files remain shipped-but-not-installed.

### Rollback

``git revert -m 1 <merge-commit>`` removes the patch. The patch is
purely additive — pre-v3.15.15.6 consumers don't depend on the new
fields, so the revert is clean.

## [v3.15.15.5] — Synthetic Artifact Contract Harness (functional, opt-in)

Date: 2026-04-28
Branch: `feat/synthetic-artifact-contract-harness`

A read-only functional test suite that produces launcher-shaped
synthetic JSON/JSONL on disk under a sandboxed ``research/`` tree,
runs the v3.15.15.2 diagnostics layer over those artifacts, and
asserts the v3.15.15.4 classifier output. **Zero xfails** because
Release A (v3.15.15.4) shipped first.

### Added

- ``tests/functional/`` — new test suite, opt-in via
  ``--run-functional``. Default ``pytest -q`` invocations
  collect-and-skip the suite (23 tests skipped instantly) so VPS
  smoke / CI default behavior is unaffected.
- ``tests/functional/conftest.py``:
  - ``--run-functional`` flag + `pytest_collection_modifyitems`
    skip-by-default mechanism.
  - Package-scope autouse ``frozen_contract_sentinel`` that
    md5-checks ``research/research_latest.json`` and
    ``research/strategy_matrix.csv`` at session boundaries.
  - ``sandbox`` fixture that builds a synthetic ``research/`` tree
    under ``workspace_tmp_path`` and re-binds every diagnostics
    PATH constant — mirrors the canonical pattern from
    ``tests/unit/test_observability_no_other_artifacts_mutated.py``.
  - ``run_diagnostics_build`` helper: orchestrates the diagnostics
    artifact build via the pure ``compute_*`` / ``inspect_*`` /
    ``build_*_snapshot`` APIs with explicit sandbox paths. cmd_build
    itself is unit-tested separately.
- ``tests/functional/_funnel_artifact_builders.py`` — pure
  synthetic-shape builders for launcher-emitted artifacts:
  - ``make_campaign_record(...)``, ``make_ledger_event(...)``,
    ``write_registry(...)``, ``write_ledger_jsonl(...)``,
    ``write_frozen_contracts(...)``.
  - Schema fields are inlined as documented constants. The builders
    do NOT import any funnel/runtime module; they reproduce the
    launcher's on-disk shape from the v3.15.5+ schema documentation.
- Scenarios:
  - ``test_a_degenerate_no_survivor.py`` — Scenario A
    (``outcome="degenerate_no_survivors"``, 2 cases).
  - ``test_b_technical_failure.py`` — Scenarios B + B2
    (``outcome="technical_failure"`` with reason worker_crash and
    timeout, plus the legacy ``outcome="worker_crashed"`` literal —
    3 cases total).
  - ``test_f_observability_lite.py`` — Scenario F-lite
    (parametrised diagnostics build over the three scenarios + the
    aggregator healthy→degraded transition under deliberate
    artifact corruption + the paper_blocked taxonomy presence
    check — 5 cases).
- ``tests/functional/test_static_import_surface.py`` — mandatory
  contractual guard: parses every ``.py`` file under
  ``tests/functional/`` AS TEXT (no import) and rejects any
  forbidden import (campaign / sprint / strategy / runtime / agent
  / execution / orchestration / automation / state / dashboard, plus
  ``yfinance``, ``ccxt``, ``requests``, ``urllib*``, ``httpx``).
  Allowlist: stdlib + pytest + ``research._sidecar_io`` +
  ``research.diagnostics.*`` + relative imports inside the package.

### Changed

- ``pytest.ini``: registered ``functional`` marker so a follow-up
  release can mark individual tests with ``@pytest.mark.functional``
  if needed (the directory-based skip is the primary opt-in
  mechanism today).

### Hard guarantees verified

- **Zero xfails** — all 23 functional tests pass cleanly with
  ``--run-functional`` because the v3.15.15.4 taxonomy patch shipped
  first.
- **Default pytest skips** — `pytest tests/functional -q` (no flag)
  reports `23 skipped in 0.06s`. The flag is the sole opt-in.
- **Frozen contracts unchanged** — md5 sentinel verifies
  ``research_latest.json`` and ``strategy_matrix.csv`` are
  byte-identical at session start and end.
- **Static import surface clean** — 13/13 cases pass; no forbidden
  imports anywhere in the harness.
- **No edits to research/, agent/, strategies/, orchestration/,
  execution/, automation/, state/, dashboard/, frontend/**.

### Not changed

- All runtime / funnel / dashboard / frontend code. The harness is
  pure additive: a new ``tests/functional/`` directory plus a
  pytest.ini marker registration plus VERSION + CHANGELOG.
- The v3.15.15.4 ``research/diagnostics/`` modules are
  unchanged. Two pre-existing implementation details surfaced
  during development and are documented inline in the tests as
  scope-deferred enhancements:
  1. ``failure_modes._ledger_failure_events`` filters ledger events
     on ``outcome=="failed"`` or event_type containing "fail" — it
     does not yet recognise launcher-literal outcome literals
     (``technical_failure``, ``degenerate_no_survivors``, etc.) as
     failure events. The harness asserts current behavior; the
     widening is a future research/diagnostics enhancement.
  2. ``failure_modes._repeated_failure_clusters`` only feeds off
     records that classify as ``technical_failure`` or have
     ``outcome=="failed"``. Same future enhancement scope.

### Rollback

``git revert -m 1 <merge-commit>`` removes the entire
``tests/functional/`` directory plus the pytest.ini marker entry,
the VERSION bump, and the CHANGELOG entry. No other module is
touched.

## [v3.15.15.4] — Diagnostics Taxonomy Patch (additive, behavior-pure)

Date: 2026-04-28
Branch: `feat/diagnostics-taxonomy-v3-15-15-4`

Aligns the observability classifier with the launcher's actual emitted
outcome vocabulary. The launcher (research/campaign_launcher.py
v3.15.5+) writes literals like ``technical_failure``,
``degenerate_no_survivors``, ``completed_with_candidates``,
``paper_blocked``, ``research_rejection``, ``completed_no_survivor``
that the diagnostics layer used to classify as ``unknown``. Existing
mappings are preserved byte-for-byte; the patch is additive only.

### Changed

- `research/diagnostics/failure_modes.py`:
  - ``OUTCOME_CLASSES`` extended from 8 to 9 entries — adds
    ``"paper_blocked"`` as a dedicated class. Folding paper_blocked
    into ``completed_no_survivor`` would have been misleading because
    a candidate was found (paper-readiness blocked promotion, not the
    research stage).
  - ``_OUTCOME_TO_CLASS`` extended with the launcher's v3.15.5+ outcome
    literals: ``completed_with_candidates``,
    ``completed_no_survivor``, ``degenerate_no_survivors``,
    ``technical_failure``, ``research_rejection``, ``paper_blocked``,
    ``integrity_failed``, ``aborted``, ``canceled_duplicate``,
    ``canceled_upstream_stale``, plus pre-v3.15.5 backward-compat
    ``worker_crashed``.
  - All pre-existing entries preserved verbatim — pinned by a new
    parametrised regression test
    ``test_pre_patch_classification_unchanged``.
- `research/diagnostics/throughput.py`:
  - ``_is_meaningful`` extended to recognise launcher-literal outcomes.
    ``completed_with_candidates``, ``completed_no_survivor``,
    ``research_rejection``, ``degenerate_no_survivors``, and
    ``paper_blocked`` are meaningful. ``technical_failure``,
    ``worker_crashed``, ``integrity_failed`` and the four cancellation
    literals are not. Pre-existing semantics for ``no_signal`` /
    ``near_pass`` / ``completed`` / ``failed`` are unchanged — pinned
    by ``test_pre_patch_meaningful_unchanged``.

### Added (tests only)

- `tests/unit/test_observability_failure_modes.py`:
  - ``test_pre_patch_classification_unchanged`` — pins every
    historical (outcome, failure_reason) pair (14 cases).
  - ``test_launcher_literal_outcome_classifies_correctly`` — verifies
    each launcher literal lands in its dedicated class (13 cases).
  - ``test_paper_blocked_is_a_dedicated_outcome_class`` — verifies the
    ``paper_blocked`` literal does NOT collapse into
    ``completed_no_survivor``.
  - ``test_known_launcher_outcomes_never_land_in_unknown`` —
    comprehensive guarantee that every recognised literal classifies
    cleanly.
  - ``test_unknown_outcome_still_lands_in_unknown`` — pins the
    catch-all behavior for genuinely unrecognised values.
  - ``test_outcome_classes_taxonomy_includes_paper_blocked_v3_15_15_4`` —
    pins the new taxonomy size (9 entries) and ``paper_blocked``
    membership.
- `tests/unit/test_observability_throughput.py`:
  - ``test_pre_patch_meaningful_unchanged`` — pins every historical
    meaningful classification (13 cases).
  - ``test_launcher_literal_meaningful_classification`` — covers each
    launcher literal (11 cases).
  - ``test_meaningful_per_day_counts_launcher_literals`` — end-to-end
    via ``compute_throughput_metrics``.
  - ``test_paper_blocked_is_meaningful`` — pins the meaningful
    classification of paper_blocked.

### Not changed

- `research/campaign_launcher.py` — launcher emits the same outcome
  literals as before; this patch only teaches the diagnostics layer
  to read them.
- `research/diagnostics/aggregator.py` — taxonomy-agnostic; operates
  over component status, not outcome strings.
- `research/diagnostics/artifact_health.py` — does not classify
  outcomes.
- `research/diagnostics/paths.py`, `system_integrity.py`, `cli.py` —
  unaffected.
- All frozen contracts (`research_latest.json`,
  `strategy_matrix.csv`).
- Frontend, dashboard, and any module outside `research/diagnostics/`.

### Validation

- 74/74 tests pass in
  ``test_observability_failure_modes.py`` + ``test_observability_throughput.py``
  (was ~17 before; +57 new cases).
- 192/192 tests pass across the full diagnostics + dashboard
  observability suite.
- Frozen contracts md5 unchanged.

### Rollback

``git revert -m 1 <merge-commit>`` removes the taxonomy entries and
the new tests. Existing v3.15.15.2/3 unit tests continue to pass on
the reverted code (the taxonomy patch is purely additive).

## [v3.15.15.3] — Observability Frontend Integration (thin surface)

Date: 2026-04-28
Branch: `feat/observability-frontend-v3-15-15-3`

UI-only release: surface the v3.15.15.2 observability artifacts in
the QRE Control Room without changing any runtime behavior.

### Added

- ``dashboard/api_observability.py`` (NEW, isolated read-only module).
  Twelve GET-only endpoints exposing the observability artifact set:
  - ``/api/observability/summary``
  - ``/api/observability/artifact-health``
  - ``/api/observability/failure-modes``
  - ``/api/observability/throughput``
  - ``/api/observability/system-integrity``
  - ``/api/observability/funnel`` (deferred, returns ``available=false``)
  - ``/api/observability/campaign-timeline`` (deferred)
  - ``/api/observability/parameter-coverage`` (deferred)
  - ``/api/observability/data-freshness`` (deferred)
  - ``/api/observability/policy-trace`` (deferred)
  - ``/api/observability/no-touch-health`` (deferred)
  - ``/api/observability/index`` (component listing)
  Each endpoint returns the same envelope ``{available, component,
  artifact_name, artifact_path, state, modified_at_unix, size_bytes,
  payload, error}``. Imports only stdlib + flask +
  ``research.diagnostics.paths`` (the stdlib-only path constants
  module). Verified by ``test_dashboard_api_observability.py`` static
  import-surface check.
- ``frontend/src/api/observability.ts`` (NEW): typed shapes for every
  observability artifact payload + the shared envelope.
- ``frontend/src/api/client.ts``: 11 typed observability GET methods
  + 1 index method. Zero new mutators.
- ``frontend/src/routes/Observability.tsx`` (NEW route at
  ``/observability``): single read-only overview with the aggregator
  summary card up top + a component table sourced from the index
  endpoint. Renders gracefully when the aggregator artifact is
  missing (falls back to the index listing).
- ``frontend/src/components/pixel/ComponentStatusPill.tsx`` (NEW):
  small pixel-art badge for component status taxonomy.
- Sidebar: one new nav item "Observability" between Artifacts and
  System Health. Read-only legend preserved.
- Light enhancements (single card or column each):
  - Overview gets an observability summary card (overall_status,
    last update, critical-findings count, link to /observability).
  - Artifacts gains a "Contract" column sourced from
    ``artifact_health`` when present.
  - Failures appends a single observability summary card from
    ``failure_modes`` (technical / research / degenerate / unknown
    counts) — does NOT replace the existing evidence-derived table.
  - Health appends a single ``system_integrity`` card.
  - Version appends a single ``system_integrity`` sidecar card.
- ``frontend/src/test/Observability.test.tsx`` (NEW, 5 tests):
  page renders summary, falls back to index when summary absent,
  graceful corrupt handling, network error handling, mutation-surface
  guard.
- SPA fallback ``/observability`` registered in ``dashboard.py``
  alongside the existing v3.15.15.1 routes.

### Hard guarantees verified by tests

- ``test_dashboard_api_observability.py`` (37 tests):
  - 200 + ``available=true`` for valid artifact (per active endpoint).
  - 200 + ``available=false`` for missing/corrupt artifact (per active
    endpoint).
  - All deferred endpoints return ``available=false, deferred=true``.
  - All GET-only (POST/PUT/DELETE/PATCH rejected per endpoint).
  - Read-only across passes (snapshot mtime+size of artifact dir
    unchanged after multiple GETs).
  - Static import-surface check rejects any
    campaign/sprint/strategy/runtime import. Allowed project imports
    limited to ``research.diagnostics.paths``.
  - ``research.diagnostics.paths`` itself stdlib-only check.
- Frontend tests (``Observability.test.tsx``): page renders summary,
  falls back to index, handles absent/corrupt/network-error, asserts
  mutation surface still contains only ``login``, ``logout``,
  ``runPreset``.

### Not changed (explicit no-ops)

- frozen contracts (``research_latest.json``, ``strategy_matrix.csv``)
- campaign launcher, policy, queue, lease, registry, digest,
  templates, budget, family / preset policy
- sprint orchestrator, screening runtime, screening evidence,
  candidate pipeline, strategy code, agent / orchestration / execution
  / automation / state subsystems
- existing dashboard auth surface; ``/api/presets/{name}/run`` is
  still the only mutating preset endpoint
- existing read-only endpoints (``/api/system/version``,
  ``/api/research/artifact-index``, ``/api/research/sprint-status``)
  are unchanged

### Rollback

``git revert -m 1 <merge-commit>`` removes the API blueprint, the
``/observability`` route, the sidebar item, all ``Observability*``
React code, all card additions to existing pages, the tests, the
SPA fallback, the VERSION bump, and the CHANGELOG entry. The
v3.15.15.2 observability artifacts under ``research/observability/``
are untouched and continue to be produced by manual CLI runs.

## [v3.15.15.2] — Discovery Observability & Instrumentation (MVP)

Date: 2026-04-28
Branch: `feat/observability-v3-15-15-2`

Read-only observability layer. Generates five sidecar artifacts under
``research/observability/`` describing artifact health, failure-mode
distribution, throughput metrics, system integrity, and an aggregator
summary. Zero behavior change: no campaign, sprint, policy, queue,
sampling, screening, or strategy code is modified or imported.

### Added

- ``research/diagnostics/`` package (Python module path) with five
  active modules (artifact_health, failure_modes, throughput,
  system_integrity, aggregator), one centralized ``paths.py``
  (single source of truth for artifact paths), a passive ``io.py``
  (read_json_safe + bounded read_jsonl_tail_safe), an injectable
  ``clock.py``, a ``cli.py`` exposing ``python -m research.diagnostics
  {build, status}``, and ``__main__.py`` delegating to the CLI. The
  Python module name diverges from the v3.15.15.2 brief (which
  proposed ``research.observability``) because that name is already
  taken by a runtime module exposing ``ProgressTracker`` to
  ``research.run_research``. Output artifact paths are unchanged
  and still land under ``research/observability/`` (a pure data
  directory, no ``__init__.py``) per the brief.
- New observability artifacts (every output is byte-deterministic
  given fixed inputs + ``now_utc``):
  - ``research/observability/artifact_health_latest.v1.json``
  - ``research/observability/failure_modes_latest.v1.json``
  - ``research/observability/throughput_metrics_latest.v1.json``
  - ``research/observability/system_integrity_latest.v1.json``
  - ``research/observability/observability_summary_latest.v1.json``
- ``ops/systemd/trading-agent-observability.service`` +
  ``.timer`` (15-min cadence). **Shipped but NOT auto-installed**;
  operator decides when to enable per ``ops/systemd/README.md``.
- ``docs/qre_observability_runbook.md`` — install / disable /
  rollback procedure.
- ``tests/unit/test_observability_*`` — 38 unit tests covering the
  modules, CLI, path drift, static import surface, and the end-to-end
  "no other artifacts mutated" guarantee.

### Hard guarantees verified by tests

- ``test_observability_static_import_surface.py`` — every module under
  ``research/diagnostics/`` is parsed AS TEXT (no import) and
  rejected if it imports any campaign / sprint / strategy / runtime
  module. Allowed project imports are limited to
  ``research._sidecar_io`` (verified pure). Forbidden list
  explicitly includes the legacy ``research.observability`` runtime
  module so we cannot accidentally pull in its
  ``research.run_state`` dependency.
- ``test_observability_no_other_artifacts_mutated.py`` — snapshots
  mtime+size of every file under a synthetic ``research/`` tree
  before/after a CLI build, asserts that ONLY files under
  ``research/observability/`` were created or modified.
- ``test_observability_paths.py`` — drift test parses writer modules
  AS TEXT and verifies they still produce the filenames the
  observability layer reads.
- Determinism: every aggregation module accepts ``now_utc=`` for
  injection; tests assert byte-identical output across two runs with
  the same inputs.

### Not changed (explicit no-ops)

- frozen contracts (``research_latest.json``, ``strategy_matrix.csv``)
- campaign launcher, policy, queue, lease, registry, digest,
  templates, budget, family / preset policy
- sprint orchestrator, screening runtime, screening evidence,
  candidate pipeline, strategy code
- existing dashboard endpoints + auth surface
- VERSION schema (the bump from ``3.15.15`` → ``3.15.15.2`` follows
  PEP 440 sub-patch ordering)

### Bounded reads

- ``MAX_LEDGER_LINES = 10_000`` and ``MAX_LEDGER_TAIL_BYTES = 25 MB``
  cap ledger ingestion. Partial trailing JSONL line is dropped to
  defend against in-flight appender writes; reported via
  ``source.ledger_partial_trailing_dropped``.

### Rollback

``git revert -m 1 <merge-commit>`` removes every observability file
plus the systemd unit files. The systemd unit being absent does not
break anything because v3.15.15.2 does not auto-install it.

## [v3.15.15] — Vol Compression Breakout: 4h preset + template wiring + observability safeguards

Date: 2026-04-27
Branch: `feature/v3.15.15-vol-compression-templates`

Closes the v3.15.14 known limitation: the
`crypto_exploratory_v1` sprint profile's plan now contains **three**
entries instead of one routable. Adds the 4h timeframe variant of
`vol_compression_breakout` (no new strategy, no new hypothesis), wires
both `vol_compression_breakout_crypto_*h` presets into
`CAMPAIGN_TEMPLATES`, and ships four observability-only safeguards
that run every launcher tick. None of the safeguards filter
candidates; `campaign_policy.decide()` is unchanged.

### Added

- `research/presets.py`: new `ResearchPreset`
  `vol_compression_breakout_crypto_4h`. Mirrors the 1h variant
  field-for-field except `name`, `timeframe="4h"`, and rationale
  pointing at the 4h sprint slot. Binds to existing
  `volatility_compression_breakout_v0` hypothesis (no catalog or
  registry change).
- `research/campaign_templates.py`: extends `_HYPOTHESIS_AWARE_PRESETS`
  from one entry to three. `CAMPAIGN_TEMPLATES` grows from 20 to 30
  (6 presets × 5 template types). Existing v3.15.2 baseline 15 rows
  remain byte-identical (covered by existing regression).
- `research/discovery_sprint.py`: observability-only safeguard
  helpers + sidecar emission surface.
  - `compute_4h_insufficient_trades_observations(...)` — read-only
    rate calculation per 4h candidate preset; emits tags
    (`4h_insufficient_trades_high`, `..._ok`, `..._cold_start`).
    **Never filters.**
  - `compute_parameter_coverage(...)` — static
    `parameter_sample_count / total_grid_size / coverage_ratio` per
    plan preset. Sampling behavior unchanged.
  - `compute_throughput_snapshot(...)` + `ensure_throughput_baseline(...)`
    + `detect_throughput_regressions(...)` — rolling-window per-preset
    spawn-count check with a `THROUGHPUT_MIN_BASELINE_RATE = 0.1`
    floor that prevents divide-by-zero / false-positive warnings on
    presets that were idle pre-deploy. Baseline auto-captured on
    first launcher tick post-deploy and never overwritten.
  - `check_preset_orthogonality(...)` — pure helper; warns when two
    presets share both `hypothesis_id` AND `timeframe`. The 4h variant
    passes (different timeframe from the 1h variant).
  - `build_safeguards_decision_payload(...)` +
    `write_safeguards_decision_artifact(...)` — single aggregate sidecar
    `research/discovery_sprints/sprint_safeguards_decision_latest.v1.json`
    carrying all four signals plus baseline + current snapshots, with
    `observability_only: true` stamped at the top.
  - New constants: `SAFEGUARDS_DECISION_PATH`, `THROUGHPUT_BASELINE_PATH`,
    `SCREENING_PARAM_SAMPLE_LIMIT`, `THROUGHPUT_WINDOW_DAYS`,
    `THROUGHPUT_DROP_THRESHOLD`, `THROUGHPUT_MIN_BASELINE_RATE`,
    `INSUFFICIENT_TRADES_REASON_CODE`,
    `INSUFFICIENT_TRADES_RATE_THRESHOLD`,
    `INSUFFICIENT_TRADES_MIN_HISTORY`.
- `research/campaign_launcher.py`: new private helper
  `_emit_safeguards_sidecar()` invoked once per non-dry-run tick,
  immediately after the v3.15.14 sprint-routing sidecar. Wrapped in
  `try/except` (with `# nosec B110`) so the safeguards path can
  never fail a tick.
- `tests/unit/test_discovery_sprint_safeguards.py` — new file,
  covers plan determinism, observation tags, parameter coverage
  ratios, baseline auto-capture + idempotency, throughput-regression
  floor (zero-baseline + non-zero-baseline cases), orthogonality on
  the live `PRESETS` tuple + collision detection on a synthetic
  collision, sidecar payload shape + atomic write, and frozen-contract
  integrity across the helper surface.

### Changed

- `VERSION`: `3.15.14 → 3.15.15`.
- `tests/regression/test_v3_15_2_campaign_templates_byte_identity.py`:
  count assertion `20 → 30`; comment lineage updated to
  `15 baseline + 5 v3.15.3 + 10 v3.15.15`.
- `tests/unit/test_discovery_sprint_routing.py`: routing assertion
  for `templates_filtered` shifts `5 → 15` (5 standard template types
  × 3 wired sprint presets); comment updated to reflect v3.15.15
  closing the v3.15.4 wiring gap.
- `tests/unit/test_campaign_policy_hypothesis_status.py:134`: pin
  comment softens "the only v3.15.3 active_discovery preset" to
  "v3.15.3+ active_discovery presets".

### Not changed (verified)

- `research/campaign_policy.py` — `decide()` signature, body, and
  byte-identity invariant unchanged (v3.15.11 regression pin intact).
- `research/research_latest.json`, `research/strategy_matrix.csv` —
  frozen contracts, untouched.
- `research/strategy_hypothesis_catalog.py` — no new catalog rows;
  `validate_active_discovery_preset_bridges()` already accepts
  multiple presets per hypothesis_id.
- `research/registry.py` — no new strategy code.
- COL queue / lease / admission / cooldown / per-template daily cap /
  budget enforcement — all unchanged.
- v3.15.14 sprint-routing path — only its candidate set widens.

### Migration / deploy notes

- Rebuild `agent` and `dashboard` images so both pick up the new
  preset + helpers.
- The `campaign_templates_latest.v1.json` sidecar is regenerated on
  the first post-deploy tick and grows by 10 rows. Not a frozen
  contract.
- The `throughput_baseline_v3_15_15.json` sidecar is captured exactly
  once on the first post-deploy tick from current registry state.
  Subsequent ticks re-use it without overwriting.

## [v3.15.14] — Sprint-aware COL Routing

Date: 2026-04-27
Branch: `feature/v3.15.14-sprint-aware-col-routing`

Closes the v3.15.13 observer/router split: when a discovery sprint is
active, the v3.15.2 Campaign Operating Layer (COL) now filters its
candidate set to the sprint's plan presets BEFORE
`campaign_policy.decide()` runs. `decide()` itself is unchanged
(v3.15.11 regression pin intact); the routing happens by shrinking
the launcher's input.

When no sprint is active — including when state is `completed`,
`expired`, or `canceled` — COL behavior is identical to v3.15.13
(passthrough).

### Added

- `research/discovery_sprint.py`:
  - `ActiveSprintConstraints` (frozen dataclass) — read-only summary of
    plan_preset_names / plan_hypothesis_ids / target / window.
  - `load_active_sprint_constraints()` — reads sprint registry, returns
    `None` when state ≠ active OR window expired OR (registry given AND
    target met). Recognises `canceled` as a non-active terminal state
    (`INACTIVE_SPRINT_STATES`).
  - `apply_sprint_routing()` — pure filter over `(templates,
    follow_up_specs, weekly_control_specs)` to plan preset names.
  - `build_routing_decision_payload()` + `write_routing_decision_artifact()`
    — read-only audit sidecar at
    `research/discovery_sprints/sprint_routing_decision_latest.v1.json`
    capturing `(routing_active, sprint_id, profile_name, counts,
    decision)` per launcher tick.
  - `sprint_extra_for_record()` — returns the extra-keys to stamp on
    spawned campaigns: `sprint_id`, `sprint_profile_name`,
    `sprint_routing="v3.15.14"`.
- `research/campaign_launcher.py`:
  - `_tick()` now calls `load_active_sprint_constraints()` and
    `apply_sprint_routing()` between `_build_*_specs` and `decide()`,
    then writes the routing sidecar when a sprint is active.
  - `_apply_decision()` accepts `sprint_constraints` and stamps the
    new `CampaignRecord.extra` with sprint metadata at spawn time
    (additive nullable fields under existing `extra: dict[str, Any]`).
- `tests/unit/test_discovery_sprint_routing.py` — 23 tests covering
  loader matrix (no-registry / canceled / completed / expired /
  target-met / happy-path), routing-helper behavior (passthrough /
  templates filter / equities exclusion / promotion_grade exclusion /
  followup+control filter), routing-decision payload + atomic write,
  sprint extra stamping, launcher tick integration (passthrough
  vs filtering vs sidecar absence vs disengagement-on-cancel),
  v3.15.13 status regression, and frozen-contract integrity.
- `docker-compose.yml`: added `./research:/app/research` bind mount to
  the `agent` service. Required so the campaign launcher (running in
  the agent container) can read the sprint registry written by the
  dashboard container — without this, sprint routing silently
  remains inactive on the VPS.

### Changed

- `VERSION`: `3.15.13` → `3.15.14`.

### Not changed (verified)

- `research/campaign_policy.decide()` — signature, body, and
  byte-identity invariant (I6) all preserved. v3.15.11 regression pin
  intact.
- `research/research_latest.json`, `research/strategy_matrix.csv` —
  frozen contracts, untouched.
- No new strategies, presets, or hypothesis catalog rows.
- COL queue / lease / admission control / cooldown / per-template
  daily cap / budget enforcement — unchanged. v3.15.14 routes by
  shrinking the candidate set; every other gate fires verbatim.

### Known limitations (not blocking the release)

- The crypto sprint plan includes `vol_compression_breakout_crypto_1h`,
  but `research/campaign_templates.py` currently wires the standard
  five-template set only for `trend_pullback_crypto_1h` (v3.15.3
  hypothesis-aware presets). Until the second preset is wired into
  CAMPAIGN_TEMPLATES (a separate v3.15.4-style mechanical fix),
  sprint routing will only spawn `trend_pullback_crypto_1h`
  campaigns. The launcher correctly filters by plan ∩ catalog, so
  no spurious campaigns fire — the sprint just makes partial
  progress against its target.

## [v3.15.13] — Discovery Sprint Orchestrator (artifact-only)

Date: 2026-04-27
Branch: `feature/v3.15.13-discovery-sprint-orchestrator`

Adds a **bounded observation-window controller** on top of the v3.15.2
Campaign Operating Layer. A discovery sprint snapshots a closed
profile, derives a deterministic plan from the existing
`research.strategy_hypothesis_catalog` × `research.presets` binding,
and tracks how many COL-completed campaigns matching the plan land
inside `[started_at, started_at + max_days]`.

Hard positioning:

- **Artifact-only.** No queue, registry, lease, ledger, or frozen
  contract is ever mutated. The orchestrator exposes no spawn surface
  and cannot bypass COL.
- **Idempotent `run`.** Refuses to start a second sprint while another
  is `state="active"` and within its window.
- **Deterministic `plan`.** Same inputs → byte-identical plan output.
- **One built-in profile this release:** `crypto_exploratory_v1`
  (target 50 campaigns / 5 days, asset_class=crypto, timeframes=1h/4h,
  screening_phase=exploratory, hypotheses=trend_pullback_v1 +
  volatility_compression_breakout_v0, exclude equities, exclude
  promotion_grade).

### Added

- `research/discovery_sprint.py` — pure profile/plan/payload builders
  + thin IO wrappers + CLI dispatcher.
  - `BUILTIN_PROFILES` closed dict (only `crypto_exploratory_v1`).
  - `derive_plan()` filters on hypothesis_id / timeframe /
    screening_phase / preset.enabled / preset.status / inferred
    asset_class.
  - `count_observations()` over `campaign_registry_latest.v1.json`
    (read-only).
  - `compute_sprint_id()` — deterministic
    `sprt-<utc_compact>-<sha256[:10]>`.
  - CLI subcommands: `plan`, `run`, `status`, `report`.
- `research/discovery_sprints/` artifact directory:
  - `sprint_registry_latest.v1.json`
  - `discovery_sprint_progress_latest.v1.json`
  - `discovery_sprint_report_latest.v1.json`
- `tests/unit/test_discovery_sprint.py` — 27 tests covering profile
  validation, plan determinism, equities/promotion_grade exclusion,
  hypothesis allowlist, sprint id determinism, active-sprint guard,
  artifact writes, status transitions to `completed` (target met) and
  `expired` (window passed), report gating, frozen-contract integrity,
  and source-level guard against COL mutator imports.

### Changed

- `VERSION`: bump `3.15.12` → `3.15.13`.

### Not changed (verified)

- `research/research_latest.json` — frozen contract, untouched.
- `research/strategy_matrix.csv` — frozen contract, untouched.
- `research/campaign_registry_latest.v1.json`,
  `research/campaign_queue_latest.v1.json`,
  `research/campaign_evidence_ledger_latest.v1.jsonl` — read-only by
  the orchestrator.
- `research.campaign_policy.decide()` — still pinned by v3.15.11
  regression.
- No new strategies, presets, or campaign templates.

## [v3.15.12] — Funnel Spawn Proposer (advisory shadow mode)

Date: 2026-04-27
Branch: `feature/v3.15.12-funnel-spawn-proposer`

Adds the first **forward-looking** module in the research intelligence
layer. Reads v3.15.9 screening_evidence + v3.15.11 advisory artifacts +
v3.15.2 campaign_registry, emits proposed-but-not-spawned campaigns at
`research/campaigns/evidence/spawn_proposals_latest.v1.json` plus an
append-only `spawn_proposal_history.jsonl` for fingerprint cooldown.

Hard positioning: advisory shadow mode only. Top-level
`enforcement_state="advisory_only"` + `mode="shadow"`. Per-build
`proposal_mode in {"normal", "diagnostic_only"}` switches behavior
based on viability verdict. `campaign_policy.decide()` remains
unchanged — pinned by extended regression test that re-asserts the
boundary now that another advisory sidecar exists.

Six operator-review hardenings vs the original sketch:

1. proposal_fingerprint covers 6 fields (hypothesis, preset,
   parameter_grid_signature from v3.15.8, timeframe, asset,
   proposal_type).
2. Per-fingerprint cooldown (`FINGERPRINT_COOLDOWN_DAYS = 7`) via
   append-only `spawn_proposal_history.jsonl`.
3. Exploration coverage enforced over BOTH percentage AND scope spread
   (≥3 families, ≥3 assets, ≥2 timeframes; shortfalls reported in
   `summary.exploration_coverage.shortfall_reason_codes`).
4. Dead-zone suppression decays after `DEAD_ZONE_DECAY_DAYS = 14` —
   never permanent on low data.
5. `viability == "stop_or_pivot"` toggles `proposal_mode =
   "diagnostic_only"`, drops HIGH-tier proposals, caps total at
   `MAX_PROPOSALS_PER_RUN_DIAGNOSTIC = 3`.
6. Deterministic `priority_tier` enum (HIGH/MEDIUM/LOW/SUPPRESSED)
   plus `reason_trace[]` on every proposal AND every suppressed zone.

### Added

- `research/funnel_spawn_proposer.py` — pure builder + thin IO wrapper
  with eleven deterministic rules (R1–R11), per-fingerprint cooldown
  via append-only history JSONL, and constants
  `EXPLORATION_RESERVATION_PCT = 0.20`,
  `EXPLORATION_MIN_DISTINCT_FAMILIES = 3`,
  `EXPLORATION_MIN_DISTINCT_ASSETS = 3`,
  `EXPLORATION_MIN_DISTINCT_TIMEFRAMES = 2`,
  `MAX_PROPOSALS_PER_RUN_NORMAL = 10`,
  `MAX_PROPOSALS_PER_RUN_DIAGNOSTIC = 3`,
  `FINGERPRINT_COOLDOWN_DAYS = 7`,
  `DEAD_ZONE_DECAY_DAYS = 14`.
- `dashboard/api_research_intelligence.py` — new endpoint
  `GET /api/research/spawn-proposals` (passthrough) and a new
  `spawn_proposals` block in `/api/research/intelligence-summary`
  (combined card-friendly view).
- `frontend/src/components/ResearchIntelligenceCard.tsx` — extended
  with proposal mode row (warn-tinted in diagnostic_only),
  spawn proposal count, suppressed zone count, optional review-required
  row, and top-3 proposals.
- `docs/funnel_spawn_proposer_design.md` — design doc with all six
  hardenings and the 10-item MUST HAVE checklist.
- `docs/handoffs/v3.15.12.md` — handoff.

### Changed

- `research/run_research.py` — finalisation block now calls
  `write_spawn_proposals_artifact(...)` after `write_viability_artifact`.
  Wrapped in its own try/except + `tracker_event`. Promoted four
  payload variables (`ig_payload`, `stop_payload`, `dz_payload`,
  `via_payload`) to defaulted Optional locals so the proposer can
  read them safely or degrade to `None` when their owning try block
  failed.
- `frontend/src/api/client.ts` — `ResearchIntelligenceSummary` type
  extended with optional `spawn_proposals` field.

### Tests

53 new tests across 1 unit + 1 integration + 3 endpoint + 2 frontend.
All v3.15.5–v3.15.12 regression tests remain green. The regression
test `test_campaign_policy_decide_signature_still_pinned_after_v3_15_12`
re-pins the policy boundary now that another consumable advisory
sidecar exists.

## [v3.15.11] — Research Intelligence Layer (advisory observability)

Date: 2026-04-27
Branch: `feature/v3.15.x-research-intelligence-layer`

Adds five deterministic, advisory-only sidecars under
`research/campaigns/evidence/` plus six read-only `/api/research/*`
endpoints and a render-only `ResearchIntelligenceCard`. The layer
turns the v3.15.5–v3.15.10 funnel evidence into operator-facing
signal — what was learned, where compute is being burned, whether
the project remains viable within the current hypothesis space.

Hard positioning: advisory observability, NOT autonomous control.

- Stop-condition output uses `recommended_decision` (not `decision`)
  and carries `enforcement_state="advisory_only"` at top level and on
  every record.
- `campaign_policy.decide()` is unchanged. A regression test pins
  the policy boundary so a future autonomous-consumption release must
  update that test alongside it.
- No queue / registry / frozen-contract mutations.
- No new strategies, no ML, no black-box scoring.

Operator guide: `docs/research_intelligence_layer.md`.
Handoff: `docs/handoffs/v3.15.11.md`.

### Added

- `research/research_evidence_ledger.py` — pure builder + thin IO
  wrapper for `research/campaigns/evidence/evidence_ledger_latest.v1.json`.
  Aggregates `campaign_evidence_ledger.jsonl` joined with
  `screening_evidence_latest.v1.json` and
  `candidate_registry_latest.v1.json`. Degenerate outcomes route to
  `degenerate_count`, never `technical_failure_count`.
- `research/information_gain.py` — deterministic per-campaign score
  in `[0.0, 1.0]` with named buckets (`none`/`low`/`medium`/`high`).
  Constants: `IG_TECHNICAL_FAILURE`, `IG_DUPLICATE_REJECTION`,
  `IG_NEW_FAILURE_MODE`, `IG_NEAR_CANDIDATE`, `IG_EXPLORATORY_PASS`,
  `IG_PROMOTION_CANDIDATE`, `IG_PAPER_READY`, `IG_COVERAGE_BONUS_MAX`,
  `IG_COVERAGE_BONUS_FLOOR`. Coverage bonus is additive and capped
  so coverage alone cannot push a duplicate-rejection campaign past
  the medium floor.
- `research/stop_condition_engine.py` — advisory recommender. Constants:
  `STOP_INSUFFICIENT_TRADES_COOLDOWN=3`, `STOP_REPEAT_REJECTION_FREEZE=5`,
  `STOP_REPEAT_REJECTION_RETIRE=10`, `STOP_TECHNICAL_FAILURE_REVIEW=3`,
  `STOP_NO_INFO_REVIEW=10`. Technical failures route to
  `REVIEW_REQUIRED`, never `RETIRE_*`. Existing candidate evidence
  protects scopes from `FREEZE_PRESET` and `RETIRE_*`.
- `research/dead_zone_detection.py` — `(asset × timeframe × family)`
  zone classifier with status `insufficient_data`/`unknown`/`alive`/
  `weak`/`dead`. Conservative thresholds. Timeframe is currently
  `"unknown"` until v4 ledger-event enrichment fills it in.
- `research/viability_metrics.py` — verdict `insufficient_data`/
  `promising`/`weak`/`commercially_questionable`/`stop_or_pivot` plus
  cost-per-X metrics with `_safe_div` (zero denominators → null).
- `dashboard/api_research_intelligence.py` — five `/api/research/*`
  passthrough endpoints + `/api/research/intelligence-summary`
  combined view.
- `frontend/src/components/ResearchIntelligenceCard.tsx` — render-only
  dashboard card.
- `docs/research_intelligence_layer.md` — operator guide.
- `docs/handoffs/v3.15.11.md` — handoff.

### Changed

- `research/run_research.py` — finalisation block now writes the
  five v3.15.11 sidecars in deterministic order
  (`evidence_ledger → information_gain → stop_conditions →
  dead_zones → viability`) after the v3.15.9 `screening_evidence`
  write. Each is wrapped in its own try/except + `tracker_event`.
  `screening_evidence_payload` is captured into a defaulted local
  in the v3.15.9 block so the v3.15.11 block can read it safely or
  degrade to empty inputs when v3.15.9 itself failed.
- `frontend/src/api/client.ts` — adds `ResearchIntelligenceSummary`
  type and `api.researchIntelligenceSummary()` fetcher.
- `dashboard/dashboard.py` — registers the new API blueprint via
  `register_research_intelligence_routes(app)`.

### Tests

89 new tests across 7 unit + 1 integration + 1 frontend file. All
v3.15.5–v3.15.11 regression tests remain green. The
`test_campaign_policy_decide_signature_unchanged` regression pins
that this release does not consume advisory output in policy.

## [v3.15.10] — Funnel Completion (combined: v3.15.8 + v3.15.9 + v3.15.10)

Date: 2026-04-26
Branch: `feature/v3.15.8-15.10-funnel-completion`

Single VERSION bump. No intermediate `3.15.8` / `3.15.9`
releases were tagged; their work ships as part of this combined
release.

Closes the three remaining funnel layers after v3.15.7:

  Sampling   — coverage calibration for small grids.
  Evidence   — non-frozen ``screening_evidence_latest.v1.json``.
  Policy     — campaign funnel policy reacts to evidence.

No threshold changes, no new strategies, no taxonomy changes,
no frozen-contract mutation. Operator guide and limitations
documented in ``docs/handoffs/v3.15.8-15.10.md``.

### v3.15.8 — Parameter Sampling Calibration

#### Added

- ``research/candidate_pipeline.py``: ``SamplingPlan``
  dataclass + ``sampling_plan_for_param_grid()`` helper. New
  constants ``MAX_FULL_COVERAGE_GRID_SIZE = 8``,
  ``MAX_STRATIFIED_GRID_SIZE = 16``,
  ``MIN_STRATIFIED_COVERAGE_PCT = 0.80``,
  ``LEGACY_LARGE_GRID_SAMPLE_COUNT = 3``. New policy /
  warning string codes. Deterministic helpers
  ``_json_safe_param_value`` (NaN/inf -> None),
  ``_canonical_param_dump`` (``allow_nan=False``),
  ``_compute_sampled_parameter_digest``,
  ``_stratified_indices``.
- ``research/screening_runtime.py``: ``sampling_metadata``
  kwarg on ``execute_screening_candidate_samples`` and a
  ``"sampling"`` block on every return path (success, error,
  timeout, no-engine fast path).
- ``research/screening_process.py``: ``sampling_metadata`` is
  threaded through ``_build_child_payload`` into the
  subprocess. ``_failed_outcome`` and ``_timed_out_outcome``
  carry the block on synthetic outcomes too.

#### Changed

- ``screening_param_samples()`` is preserved as a backward-
  compatible thin shim. **Intentional behavioural shift**:
  the shim now ignores ``max_samples`` for grid_size in
  ``[1..MAX_STRATIFIED_GRID_SIZE]`` — this is the deliberate
  fix for the v3.15.7 under-sampling defect. ``max_samples``
  is still honoured for grid_size > 16 (legacy
  first/middle/last cap).
- All 5 internal callers (``batch_execution``,
  ``run_research`` at line ~2352, ``screening_process`` at
  lines 110/148, ``screening_runtime`` at line 379) migrated
  to ``sampling_plan_for_param_grid()``.
- ``run_research``'s v3.14.1 timeout-transform and wrapper-
  level exception block now carry the plan-derived sampling
  block on their synthetic outcome dicts.

### v3.15.9 — Funnel Evidence Artifacts

#### Added

- ``research/screening_evidence.py`` (new): pure builder
  module. Exports ``SCREENING_EVIDENCE_PATH``,
  ``SCREENING_EVIDENCE_SCHEMA_VERSION = "1.0"``,
  ``TOP_LEVEL_KEYS``, ``PER_CANDIDATE_KEYS``,
  ``to_json_safe_float``, ``artifact_fingerprint``,
  ``candidate_evidence_fingerprint``, ``is_near_pass``,
  ``dominant_failure_reasons``, ``resolve_stage_result``,
  ``build_screening_evidence_payload``. Near-pass band
  constants: ``EXPLORATORY_EXPECTANCY_NEAR_BAND = 0.0005``,
  ``EXPLORATORY_PROFIT_FACTOR_NEAR_REL_BAND = 0.05``,
  ``EXPLORATORY_DRAWDOWN_NEAR_REL_BAND = 0.05``.
- ``research/run_research.py``: ``_read_paper_blocked_index()``
  helper plus an emit hook adjacent to the v3.15.3 catalog
  block (after ``build_and_write_paper_validation_sidecars``).
  Tracker emits ``v3_15_9_screening_evidence_written`` /
  ``v3_15_9_screening_evidence_failed``.

#### Behaviour

- Top-level + per-candidate keys are closed sets pinned by
  unit and regression tests. Per-candidate record carries
  ``identity_fallback_used`` + ``evidence_fingerprint``.
- **Identity-fallback resilience**: missing/empty/whitespace
  ``candidate_id`` triggers a deterministic
  ``fb_<sha1prefix>`` id. The builder NEVER asserts.
  ``summary.identity_fallbacks`` counts the fallback path.
- **Stage-result two-step resolution**: base state (pass /
  near_pass / screening_reject / unknown) determined first
  from screening promotion + near-pass; downstream override
  (paper_blocked > promotion_candidate >
  needs_investigation > screening_pass) applies ONLY to a
  screening pass. A rejected near-pass remains ``near_pass``.
- **NaN safety**: every metric float passes through
  ``to_json_safe_float`` upstream of the canonical dump,
  which uses ``allow_nan=False``. Direct unsanitised NaN
  raises ``ValueError`` (proves the guard).
- **Paper-blocked graceful degradation**: missing/malformed
  ``paper_readiness_latest.v1.json`` yields ``{}``; the
  evidence artifact still writes.

### v3.15.10 — Campaign Policy Alignment

#### Added

- ``research/campaign_funnel_policy.py`` (new): pure module.
  6 decision-code constants
  (``confirmation_from_exploratory_pass``,
  ``follow_up_from_near_pass``,
  ``alternate_timeframe_from_insufficient_trades``,
  ``coverage_followup_from_low_sampling_coverage``,
  ``cooldown_from_repeat_rejection``,
  ``no_action_technical_failure``).
  ``DECISION_PRIORITY`` (10..60).
  ``REPEAT_REJECTION_STREAK_THRESHOLD = 3``.
  ``LOW_COVERAGE_TRIGGER_PCT = 0.80``.
  ``TERMINAL_CAMPAIGN_STATES`` /
  ``ACTIVE_CAMPAIGN_STATES`` exactly cover the real
  ``CAMPAIGN_STATES`` tuple. ``FunnelDecision`` dataclass.
  ``evidence_owns_campaign``, ``_dominant_reason``,
  ``repeat_rejection_streak``,
  ``has_alternate_timeframe_support`` (always False),
  ``has_funnel_spawn_for``, ``derive_funnel_decisions``,
  ``sort_funnel_decisions``.
- ``research/campaign_launcher.py``: error-isolated
  ``_apply_funnel_decisions(...)`` helper wired between
  ``_apply_decision`` and ``_write_ledger`` in the per-tick
  critical section.
- ``research/campaign_evidence_ledger.py``: 4 additive
  EventType Literal members
  (``funnel_decision_emitted``,
  ``funnel_evidence_stale_or_mismatched``,
  ``funnel_technical_no_freeze``,
  ``funnel_policy_error``). ``LEDGER_SCHEMA_VERSION`` stays
  at ``"1.0"`` (on-disk JSONL row schema unchanged).
- ``research/campaign_digest.py``:
  ``DIGEST_SCHEMA_VERSION`` bumped from ``"1.0"`` to
  ``"1.1"``. New top-level
  ``funnel_decisions: dict[decision_code -> count]`` block.
  Backward-compat verified for both readers
  (``campaign_launcher.load_previous_digest`` and
  ``dashboard/api_campaigns.py``).

#### Behaviour

- **Decision-only metadata** (MF-15):
  ``extra.requested_screening_phase = "promotion_grade"`` is
  recorded as forensic metadata in the
  ``confirmation_from_exploratory_pass`` decision. There is
  currently no executor reader of this field anywhere in the
  ``research/`` subtree (pinned by static-grep test). The
  spawned campaign would run at the parent preset's natural
  ``screening_phase`` (i.e. ``exploratory``), NOT at
  ``promotion_grade``. Vocabulary is "confirmation request /
  queued confirmation decision", NOT "promotion-grade
  execution". v3.15.11+ may wire the executor override.
- **Alternate timeframe absent** (MF-18):
  ``has_alternate_timeframe_support()`` always returns
  ``False`` because no preset-catalog mechanism exists today.
  ``insufficient_trades`` failures fall back to
  ``cooldown_from_repeat_rejection`` with rationale
  ``alternate_timeframe_unavailable=True``.
- **Ledger events only** in v3.15.10: the launcher hook
  records ``funnel_decision_emitted`` /
  ``funnel_technical_no_freeze`` /
  ``funnel_evidence_stale_or_mismatched`` /
  ``funnel_policy_error`` events. No ``CampaignRecord``
  upserts and no queue mutations from the funnel hook itself.
  The ``spawn_request`` payload is carried in the event's
  ``extra`` so v3.15.11+ executor work can act on it.
- **Error isolation** (MF-9): the entire funnel-policy block
  is wrapped in ``try/except``. Failures emit a single
  ``funnel_policy_error`` event but NEVER mutate the parent
  campaign's outcome.
- **Repeat-rejection streak** (MF-12): walks
  ``campaign_completed`` events for the preset; increments on
  ``research_rejection`` with matching dominant reason;
  ``technical_failure`` and ``degenerate_no_survivors`` are
  NEUTRAL (skip without breaking); any other outcome BREAKS.
  Threshold is 3.
- **Dedupe**: ledger-based
  ``_funnel_decision_already_in_ledger`` checks
  ``(parent_id, decision_code, candidate_id, fingerprint)``
  against existing ``funnel_decision_emitted`` events.
  Registry-based ``has_funnel_spawn_for`` is exported for
  v3.15.11+ when actual records will be spawned.

### Tests

- 64 v3.15.8 cases.
- 71 v3.15.9 cases (incl. regression schema pin).
- 43 v3.15.10 cases (incl. ledger closure pin, digest 1.1
  pin, digest v1.0 backward load, launcher integration).

Full pytest suite: 2092 passed, 1 skipped.

### Deliberately not changed

- Frozen contracts:
  ``research/research_latest.json``,
  ``research/strategy_matrix.csv``,
  ``research/candidate_registry_latest.v1.json`` schema.
- Campaign launcher outcome taxonomy (no new
  ``CampaignOutcome`` values; ``worker_crashed`` invariant
  preserved).
- v3.15.7 exploratory thresholds.
- Strategy logic / strategies / presets.
- Execution-side override of
  ``extra.requested_screening_phase`` (v3.15.11 scope).
- Frontend (existing dashboard digest endpoint continues to
  serve the dict via ``.get(...)`` — no schema-aware code
  change needed).
- ``run_meta_latest.v1.json`` schema_version stays ``"1.2"``.
- ``CampaignType`` Literal (``daily_primary``,
  ``daily_control``, ``survivor_confirmation``,
  ``paper_followup``, ``weekly_retest``) — funnel
  confirmation requests reuse ``survivor_confirmation`` with
  funnel-specific subtype + extra metadata.

## [v3.15.7] — Exploratory Screening Criteria

Date: 2026-04-26
Branch: `fix/v3.15.7-exploratory-screening-criteria`

Activates phase-aware screening criteria for the
``exploratory`` funnel stage introduced in v3.15.6.
``promotion_grade`` / ``standard`` / ``None`` retain the legacy
``goedgekeurd`` AND-gate byte-identically. ``win_rate`` becomes
diagnostic-only for ``exploratory`` so trend / momentum
strategies with positive expectancy but low win_rate can be
shortlisted without lowering the eventual promotion bar.

Funnel discipline:

  Screening zoekt.   Promotion bewijst.   Paper valideert.

### Added

- ``agent/backtesting/engine.py``: additive metrics
  ``expectancy`` and ``profit_factor`` (pure derivations from
  ``trade_pnls``; no impact on ``goedgekeurd``).
  ``PROFIT_FACTOR_NO_LOSS_CAP = 999.0`` is the JSON-safe finite
  proxy for "no losses observed".
- ``research/screening_criteria.py`` (new): pure helper
  ``apply_phase_aware_criteria(metrics, screening_phase) ->
  (passed, reason)`` with three exploratory thresholds
  (``EXPLORATORY_MIN_EXPECTANCY = 0.0`` strict,
  ``EXPLORATORY_MIN_PROFIT_FACTOR = 1.05``,
  ``EXPLORATORY_MAX_DRAWDOWN = 0.45``).
- ``SCREENING_REASON_CODES`` extended with three exploratory
  codes: ``expectancy_not_positive``,
  ``profit_factor_below_floor``,
  ``drawdown_above_exploratory_limit``. v3.15.5
  ``_classify_research_rejection`` accepts these so a fully-
  exploratory-rejected run still classifies as
  ``research_rejection``.
- Outcome dict (non-frozen screening sidecar surface) gains:
  ``pass_kind`` (None / "standard" / "promotion_grade" /
  "exploratory"; set ONLY on screening pass — rejections carry
  ``None``), ``screening_criteria_set`` ("legacy" or
  "exploratory"), ``diagnostic_metrics`` (JSON-safe finite
  floats: expectancy, profit_factor, win_rate, max_drawdown).
  No ``screening_phase`` key (v3.15.6 invariant preserved).
- ``promotion.classify_candidate`` accepts ``pass_kind``
  (default ``None``); ``"exploratory"`` short-circuits to
  ``STATUS_NEEDS_INVESTIGATION`` with a single escalated reason
  ``exploratory_pass_requires_promotion_grade_confirmation``.
- ``promotion_reporting.build_candidate_registry_payload``
  accepts ``screening_pass_kinds: dict[str, str | None] | None
  = None``. Default is byte-identical to pre-v3.15.7;
  ``pass_kind`` is consumed but NEVER serialised into the v1
  candidate registry row.
- ``research/run_research.py``: builds the
  ``{strategy_id → pass_kind}`` index from candidate runtime
  records and forwards it to promotion reporting. Emits
  ``exploratory_screening_pass`` tracker event when
  ``outcome["pass_kind"] == "exploratory"`` — emit-site lives
  exclusively in run_research.

### Changed

- ``screening_runtime.execute_screening_candidate_samples`` now
  accepts ``screening_phase`` and replaces the static
  ``goedgekeurd`` check with the phase-aware dispatch via
  ``apply_phase_aware_criteria``. Pre-checks
  (``no_oos_samples`` / ``insufficient_trades``) stay upstream
  to avoid double-gate drift.
- ``screening_process.execute_screening_candidate_isolated``
  no longer discards the v3.15.6 kwarg; it threads
  ``screening_phase`` through ``_build_child_payload`` into the
  subprocess and into both inner runners.
- ``batch_execution`` candidate-update's ``screening`` sub-dict
  carries ``pass_kind`` from the outcome dict (no preset / no
  tracker — same v3.15.6 discipline; pass_kind comes straight
  from the runtime record).
- Two v3.15.6 tests reformulated (NOT deleted) with explicit
  supersession docstrings — the v3.15.6 no-branching invariants
  are intentionally superseded by v3.15.7. Signature-binding
  test preserved verbatim.

### Deliberately not changed

- ``engine.CRITERIA`` and ``_goedkeuren()`` — promotion-grade
  gates byte-identical.
- Strategy logic (``agent/backtesting/strategies.py``, registry,
  bundles, parameters).
- Parameter sampling (v3.15.8 scope).
- Campaign launcher / v3.15.5 outcome semantics —
  ``worker_crashed`` still never emitted; the v3.15.5
  invariant tests stay green.
- Frozen contracts: ``research_latest.json``,
  ``strategy_matrix.csv``,
  ``candidate_registry_latest.v1.json`` schema — bytewise
  unchanged.
- ``run_meta_latest.v1.json`` schema_version stays "1.2" (no
  v3.15.7 fields at run level).
- ``preset_to_card`` / dashboard API / frontend.
- v3.15.6 preset assignments.
- ``screening_phase`` annotation remains ``str | None`` (not
  Literal) — v3.15.6 seam contract.
- v3.15.6 ``screening_phase`` key forbidden in outcome dict.
- ``screening_runtime.py`` and ``screening_process.py`` do not
  contain phase-specific threshold constants; those live
  exclusively in ``research/screening_criteria.py``.

### Behavioral shift (intentional)

- ``crypto_diagnostic_1h``, ``trend_pullback_crypto_1h``, and
  ``vol_compression_breakout_crypto_1h`` (the three v3.15.6
  exploratory presets) can now produce screening passes on
  positive expectancy + healthy profit_factor + bounded drawdown
  even when the engine ``goedgekeurd`` AND-gate (which includes
  ``win_rate > 0.50``) fails. Those passes downgrade to
  ``needs_investigation`` in promotion — they are NOT
  auto-promoted to candidate / paper.
- Operators who previously expected
  ``screening_criteria_not_met`` as the dominant exploratory
  failure reason should also see
  ``expectancy_not_positive`` / ``profit_factor_below_floor`` /
  ``drawdown_above_exploratory_limit`` in the digest.

### v3.15.8 sampling dependency

If exploratory pass count remains zero after v3.15.7 deploy,
**inspect sampling coverage in v3.15.8 before further loosening
criteria**. Lowering exploratory thresholds without first
addressing a sampling bottleneck would mask the actual problem.
See ``docs/handoffs/v3.15.7.md`` §10 for indicators.

### Tests

11 new v3.15.7 test files (~85 individual cases). 3 v3.15.5 /
v3.15.6 test files updated (not deleted) with explicit
supersession comments. Verifies every emitted screening reason
lives in ``SCREENING_REASON_CODES``, the registry row schema is
unchanged, paper readiness filters ``needs_investigation``, the
tracker event lives only in run_research, and the trend-case
fixture passes exploratory + fails promotion_grade.

## [v3.15.6] — Screening Mode Activation

Date: 2026-04-26
Branch: `fix/v3.15.6-screening-mode-activation`

Activates the funnel-stage classification (``screening_phase``)
end-to-end as plumbing. No threshold or screening-criteria change
ships in v3.15.6 — the seam is laid for v3.15.7 to dispatch
phase-aware criteria. ``screening_phase`` and the legacy
``screening_mode`` coexist: distinct concepts, distinct
vocabularies, no rename, no vocab replacement.

### Comparison: screening_mode vs screening_phase

| Concept | Values | Meaning | Runtime effect in v3.15.6 |
|---|---|---|---|
| `screening_mode` (legacy, v3.10) | `strict` / `lenient` / `diagnostic` | gate-strictness metadata | unchanged; runtime-inert |
| `screening_phase` (NEW, v3.15.6) | `exploratory` / `standard` / `promotion_grade` | funnel-stage metadata | propagated to screening boundary; **no behavior change** |

### Added

- ``research/presets.ScreeningPhase = Literal["exploratory",
  "standard", "promotion_grade"]`` with a docstring linking it to
  the legacy ``ScreeningMode`` for clarity.
- ``ResearchPreset.screening_phase`` field with default
  ``"promotion_grade"`` (safety-net only). All 6 production
  presets receive the field explicitly; an AST test pins the
  explicitness contract.
- ``research/screening_process.execute_screening_candidate_isolated``
  accepts a new ``screening_phase: str | None = None`` keyword-
  only parameter. The function discards the kwarg via
  ``del screening_phase`` — no branching, no result-dict
  expansion. The annotation is intentionally ``str | None`` (not
  Literal) so v3.15.7 may extend the vocabulary in-place without
  an API break.
- ``research/run_research``: tracker events
  ``screening_phase_active`` (run-level) and
  ``screening_phase_observed`` (per-candidate, run_research only).
- ``research/run_meta_latest.v1.json`` schema bump 1.1 → 1.2 with
  additive nullable ``screening_phase`` field. File path unchanged.
- ``researchctl run --dry-run`` listing surfaces ``screening_phase``
  next to the legacy ``screening_mode``. Operator visibility
  without a frontend change.
- 14 new test files pinning the v3.15.6 contract end-to-end:
  type, preset assignments, AST explicitness, legacy
  ``screening_mode`` unchanged, default+strict validation paths,
  invalid-phase end-to-end → technical_failure (no catalog
  pollution), run_research / screening_process / batch_execution
  propagation, v3.15.7 compatibility seam, behavior equivalence,
  run_meta schema, ``preset_to_card`` unchanged, researchctl
  listing.

### Changed

- ``research/run_research._enforce_preset_validation`` now
  surfaces ``screening_phase_invalid`` issues alongside the v3.11
  hypothesis-metadata path. Default mode emits a
  ``preset_validation_warning`` tracker event without raising;
  strict mode (``QRE_STRICT_PRESET_VALIDATION=1``) raises
  ``PresetValidationError``.
- Preset assignments (classification change only — same screening
  criteria as today until v3.15.7):
  - `trend_pullback_crypto_1h`           → `exploratory`
  - `vol_compression_breakout_crypto_1h` → `exploratory`
  - `crypto_diagnostic_1h`               → `exploratory`
  - all other presets                    → `promotion_grade`

### Deliberately not changed

- Bestaand ``screening_mode`` field — every preset's value is
  byte-identical pre-v3.15.6 (test pinned). The legacy Literal
  remains exactly ``("strict", "lenient", "diagnostic")``.
- ``preset_to_card`` (frontend / dashboard API) — byte-identical
  pre-v3.15.6. Visibility for v3.15.6 lives in tracker events,
  run_meta, and the CLI listing.
- ``research/screening_runtime.py``, ``candidate_pipeline.py``,
  ``rejection_taxonomy.py``, ``campaign_launcher.py``,
  ``dashboard/dashboard.py``, ``frontend/`` — unchanged.
- ``execute_screening_candidate_isolated`` returned outcome dict
  — NOT extended. The function discards the kwarg via
  ``del screening_phase`` to prevent stealth schema drift via
  ``runtime_record.update(outcome)`` on
  ``research/batch_execution.py:191``.
- ``research/batch_execution.py`` — no preset/tracker context;
  passes ``screening_phase=None`` literally; no inference from
  ``screening_mode`` / ``preset_class`` / ``hypothesis_id`` /
  diagnostic flags.
- Frozen contracts: ``research_latest.json``,
  ``strategy_matrix.csv``,
  ``candidate_registry_latest.v1.json`` schema — byte-identical.
- v3.15.5 outcome semantics — fully preserved. All `v3_15_5`
  pattern tests remain green.

### Behavioral shift (intentional)

- Three production presets are now classified as ``exploratory``
  (`trend_pullback_crypto_1h`, `vol_compression_breakout_crypto_1h`,
  `crypto_diagnostic_1h`). This is a **classification change
  only** — same screening criteria as today. v3.15.7 may
  introduce phase-aware thresholds, at which point the
  exploratory presets will see different gating from the
  promotion_grade presets.
- Operators who filter or aggregate on ``screening_mode`` should
  also surface ``screening_phase`` for v3.15.6+ runs. The CLI
  listing now exposes both.

### Tests

Full suite: 1755 + ~57 new tests = ~1812 expected.

## [v3.15.5] — Outcome Semantics Fix

Date: 2026-04-26
Branch: `fix/v3.15.5-outcome-semantics`

Closes the v3.15.3 carry-over **C1**
(*"degenerate research run misclassified as `worker_crashed`"*) and
makes the launcher's outcome assignment semantically correct,
deterministic, and policy-safe ahead of the v3.15.2 Autonomous
Campaign Operations Layer. No strategy logic, no screening threshold
changes, no promotion logic changes, no frozen-contract mutation,
no v3.15.2 build.

### Added

- ``research/empty_run_reporting.EXIT_CODE_DEGENERATE_NO_SURVIVORS``
  (= 2). Reserved CLI exit code for a controlled
  ``DegenerateResearchRunError`` raise. Only the ``__main__``
  wrapper of ``research/run_research.py`` produces this code.
- Three semantically correct outcomes added to
  ``research/campaign_registry.CampaignOutcome`` (Literal) and
  ``CAMPAIGN_OUTCOMES`` (tuple):
  - ``degenerate_no_survivors``
  - ``research_rejection``
  - ``technical_failure``
- ``research/campaign_registry.LAUNCHER_EMITTABLE_OUTCOMES`` —
  frozenset enumerating the post-v3.15.5 launcher emission set.
  ``worker_crashed`` is deliberately absent. The launcher's
  runtime invariant asserts ``outcome ∈
  LAUNCHER_EMITTABLE_OUTCOMES`` and ``outcome != "worker_crashed"``
  before ``record_outcome``.
- ``research/rejection_taxonomy.SCREENING_REASON_CODES`` —
  frozenset of the per-candidate rejection codes that classify a
  rejection as a screening-layer failure (vs. promotion / paper).
  Pinned by a unit test that asserts every code appears in the
  screening layer source.
- ``empty_run_diagnostics_latest.v1.json`` carries an additive
  nullable top-level ``col_campaign_id`` field. Producer:
  ``research.run_research._raise_degenerate_run`` (mirrors the
  v3.15.4 pattern on ``paper_readiness_latest.v1.json``). Consumer:
  the launcher's ``_check_rc2_origin`` diagnostic helper. Schema
  version unchanged (``"1.0"``); the field is additive and
  nullable.
- New tests:
  - ``tests/unit/test_v3_15_5_outcome_classification.py`` — pure
    helpers for paper / candidate-registry / rc=2 classification.
  - ``tests/unit/test_v3_15_5_outcome_invariant.py`` — static AST
    guard: launcher production path never assigns ``outcome =
    "worker_crashed"``; the runtime invariant + the
    ``LAUNCHER_EMITTABLE_OUTCOMES`` import are present.
  - ``tests/unit/test_v3_15_5_run_research_exit_code.py`` —
    ``__main__`` exits rc=2 on ``DegenerateResearchRunError``;
    other exceptions fall through (rc=1); callable
    ``run_research(...)`` still raises the exception so the
    library contract is byte-identical.
  - ``tests/unit/test_v3_15_5_screening_reason_codes.py`` —
    frozenset shape + repo-presence pin.
  - ``tests/unit/test_v3_15_5_policy_regression.py`` — 5×
    consecutive ``degenerate_no_survivors`` or
    ``research_rejection`` triggers preset freeze; 5×
    ``technical_failure`` does **not**; mixed streaks reset
    correctly.

### Changed

- ``research/campaign_launcher.py`` outcome dispatch is now strict
  and hierarchical (rc=2 → degenerate; rc≠0 → technical; rc=0 →
  paper-ready / paper-blocked / research_rejection /
  completed_no_survivor — exhaustive mutually exclusive paths).
  Ownership for ``research_rejection`` is hard-anchored on
  ``paper_readiness.col_campaign_id`` (v3.15.4 stamp); mtime is
  not used as ownership.
- ``research/campaign_launcher.py`` lifecycle state for
  ``degenerate_no_survivors`` is now ``completed`` (not
  ``failed``). A degenerate run is a structured completion with a
  meaningful verdict; ``failed`` is reserved for true technical
  failures. The terminal event becomes ``campaign_completed`` so
  the policy streak counter (which inspects only
  ``campaign_completed``) observes the new outcome.
- ``research/campaign_preset_policy._NON_TECHNICAL_REJECT_OUTCOMES``
  extended with ``degenerate_no_survivors`` and
  ``research_rejection``. ``technical_failure`` deliberately
  excluded — technical failures must not freeze a preset.

### Deprecated

- ``"worker_crashed"`` in ``CampaignOutcome`` /
  ``CAMPAIGN_OUTCOMES``. The literal stays in the tuple/Literal so
  historical ``campaign_registry_latest.v1.json`` records still
  validate, but post-v3.15.5 launcher emissions never produce it.
  See *Behavioral shift* below.

### Behavioral shift (intentional)

- **Reading historical records.** Campaigns recorded pre-v3.15.5
  with ``outcome == "worker_crashed"`` should be read as
  *technical_failure* by downstream consumers. Records are not
  rewritten in place; consumers that filter on outcome should
  treat ``("worker_crashed", "technical_failure")`` as the union
  for migration-spanning queries.
- **Throughput may dip initially.** Pre-v3.15.5,
  ``DegenerateResearchRunError`` runs were classified as technical
  and therefore excluded from the
  ``_non_technical_reject_streak`` counter. Post-v3.15.5 they
  count toward freeze (5+ in a row → preset freeze). Presets with
  repeated degenerate runs may now freeze / cooldown earlier than
  before. This is the intended correction — repeated degenerate
  runs are a real family-falsification signal.
- **Digest / dashboards.** ``top_failure_reasons`` will surface
  ``degenerate_no_evaluable_pairs`` where pre-v3.15.5 it surfaced
  ``worker_crash``. Consumers hardcoded on ``worker_crash`` should
  accept both during the migration window.

### Deliberately not changed

- ``research/research_latest.json`` — frozen. Byte-identical.
- ``research/strategy_matrix.csv`` — frozen. Byte-identical.
- ``research/candidate_registry_latest.v1.json`` schema — frozen.
  Schema unchanged. Ownership is anchored via
  ``paper_readiness.col_campaign_id``, not via a new
  ``run_id``/``campaign_id`` field on the v1 registry.
- Strategy logic, screening thresholds, promotion logic.
- Campaign policy redesign (only the
  ``_NON_TECHNICAL_REJECT_OUTCOMES`` set was extended; ladder
  semantics for ``completed_no_survivor`` cooldown remain
  unchanged).
- Frontend.

### Carry-over backlog (out of scope for v3.15.5)

- C1 from v3.15.3: **closed** by this release.
- C2: ``build_campaign_id`` uses local TZ but suffixes ``Z``.
- C3: pending entries from R0 reclaim not re-picked.
- C4: GHA ``docker-build`` workflow lag for ``:latest`` tag.

### Tests

Full suite: 1755 passed, 1 skipped after this release. Forty-plus
new tests pin the v3.15.5 contract.

## [v3.15.4] — Second controlled candidate + finalization patch

Date: 2026-04-26
Branch: `chore/v3.15.4-finalize` (after the v3.15.4 working set on
`main` merged via commits `5c5f442`..`3aa559d`).

Closes the v3.15.x line. Adds the second controlled
``active_discovery`` candidate
(``volatility_compression_breakout_v0``), tightens the
catalog ↔ preset ↔ registry bridge into a startup gate, and applies
a narrow finalization patch (release-integrity + campaign ownership
auditability) before v3.16 work begins. No strategy logic, no
campaign policy redesign, no shadow / live work, no frozen-contract
changes.

### Added (v3.15.4 working set, commits `5c5f442`..`3aa559d`)

- ``volatility_compression_breakout`` strategy module + registry
  entry (``research/registry.py``); ``compression_ratio`` /
  rolling-high / rolling-low previous primitives in
  ``agent/backtesting/features.py``; matching strategy in
  ``agent/backtesting/strategies.py``.
- Strategy hypothesis catalog: promote ``vol_breakout_v0`` to
  ``active_discovery`` and add planned rows for sleeve and
  cross-sectional momentum families
  (``research/strategy_hypothesis_catalog.py``).
- Preset ``vol_compression_breakout_crypto_1h`` bound to
  ``hypothesis_id="volatility_compression_breakout_v0"``
  (``research/presets.py``).
- Canonical failure-code aliases for the new strategy
  (``research/strategy_failure_taxonomy.py``).
- Strict ``active_discovery`` validator + cross-module preset
  bridge ``validate_active_discovery_preset_bridges()`` wired into
  ``run_research`` startup before any preset / config work
  (``research/strategy_hypothesis_catalog.py``,
  ``research/run_research.py``).
- Test coverage:
  ``tests/unit/test_active_discovery_preset_bridge.py``,
  ``tests/unit/test_v3_15_4_feature_primitives.py``,
  ``tests/unit/test_volatility_compression_breakout_strategy.py``,
  preset-count + bridge lazy-import follow-ups.

### Added (finalization patch)

- ``research/paper_readiness.py``: nullable ``col_campaign_id``
  field on ``build_paper_readiness_payload`` and on the written
  sidecar. Stamped by ``run_research`` from the v3.15.2 COL
  breadcrumb. Null for direct-CLI invocations; pre-v3.15.4 readers
  ignore unknown keys.
- ``research/paper_validation_sidecars.py``:
  ``PaperValidationBuildContext.col_campaign_id`` (default
  ``None``) plumbs the breadcrumb into the readiness sidecar
  through the existing façade.
- ``research/campaign_launcher.py``: ``_classify_outcome_from_paper``
  takes ``expected_campaign_id`` and rejects mismatched / missing
  ownership stamps. Caller passes ``cid`` so a stale sidecar from a
  prior campaign cannot misclassify the current run; mismatch falls
  through to the conservative ``completed_no_survivor`` branch.
- ``research/strategy_hypothesis_catalog.py``: bridge-validator
  errors now include ``strategy_family`` and the list of
  bound-but-disqualified presets (with their actual ``status`` /
  ``enabled`` flags) so an on-call operator can tell at a glance
  whether the binding is missing entirely or merely flipped to
  ``enabled=False``.
- ``docs/handoffs/v3.15.4.md``: documents the
  ``max_concurrent_campaigns=1`` ↔ launcher-holds-lock-across-
  subprocess coupling so a future operator who raises the limit
  understands why hourly ticks would suddenly serialise.
- Tests:
  ``tests/unit/test_paper_readiness_col_ownership.py`` (5 tests:
  payload + façade ownership stamp on success and default-null
  paths); ``tests/unit/test_campaign_launcher_paper_ownership.py``
  (7 tests: missing sidecar, owner-match, owner-mismatch (the
  defining stale-sidecar case), missing-owner-when-expected,
  blocked-with-owner, no-expected-id back-compat, corrupt sidecar);
  added one assertion in
  ``tests/unit/test_active_discovery_preset_bridge.py`` covering
  the improved error message.

### Changed

- ``VERSION``: ``3.15.3.1`` → ``3.15.4``. Catches up the release
  identity to the working set on ``main`` (gap acknowledged in the
  v3.15.3 CHANGELOG entry).

### Deliberately not changed

- No strategy or feature logic was modified. The two new strategies
  added in the v3.15.4 working set (``trend_pullback_v1`` shipped in
  v3.15.3, ``volatility_compression_breakout`` shipped in v3.15.4)
  were already present on ``main``; the finalization patch does not
  touch them.
- No campaign policy redesign. Eligibility predicate + bridge gating
  remain as merged in v3.15.2 / v3.15.3.
- No shadow / live work; no broker connectivity changes; no
  ``live_eligible`` flips (still hard-pinned ``False``).
- Frozen contracts preserved: ``research/research_latest.json`` and
  ``research/strategy_matrix.csv`` are byte-identical to v3.15. The
  v3.15.2 ``campaign_templates_latest.v1.json`` byte-identity for
  the 3 baseline preset templates is preserved.
- Paper-readiness sidecar schema version stays at
  ``PAPER_READINESS_SCHEMA_VERSION="1.0"`` — ``col_campaign_id``
  is an additive nullable field, not a schema-breaking change.

### Tests

- 12 new finalization-patch tests across two new files plus one
  added assertion in the existing bridge-validator suite. Full
  pytest suite runs with the v3.15.4 contract (>=1
  ``active_discovery``, both controlled candidates active).

### Known limitations

- The launcher still holds the campaign queue lock across the
  ``run_research`` subprocess. This is correct only while
  ``max_concurrent_campaigns=1``; raising the cap requires
  releasing the lock at the spawn boundary. See
  ``docs/handoffs/v3.15.4.md``.

## [v3.15.3.1] — Audit-sidecar hotfix on degenerate runs

Date: 2026-04-25
Branch: `fix/v3.15.3.1-audit-sidecar-on-degenerate`

Hotfix on top of v3.15.3. The two new audit sidecars
(``strategy_hypothesis_catalog_latest.v1.json`` and
``strategy_campaign_metadata_latest.v1.json``) are now written even
when a research run terminates as degenerate / no-survivor, so the
COL audit trail is never missing the catalog snapshot at the moment
of the rejection.

### Changed

- ``research/run_research.py``: ``_raise_degenerate_run`` writes
  both v3.15.3 sidecars before re-raising
  ``DegenerateResearchRunError``. Mirrors the existing
  ``_write_public_artifact_status_sidecar`` pattern in the same
  function — best-effort with ``tracker.emit_event(
  "v3_15_3_hypothesis_catalog_sidecars_failed", ...)`` on failure,
  never blocks the original degenerate-run exception.

### Deliberately not changed

- No policy changes. ``campaign_policy._check_template_eligibility``
  still reads the in-memory catalog tuple, not the sidecar file —
  the hotfix only fills an audit-trail gap, never alters a
  selection decision.
- No strategy changes. ``trend_pullback_v1`` and the legacy
  trend_pullback / trend_pullback_tp_sl entries are untouched.
- No artifact schema changes. The sidecar schemas
  (``CATALOG_SCHEMA_VERSION="1.0"``,
  ``CAMPAIGN_METADATA_SCHEMA_VERSION="1.0"``) are unchanged; this
  release only adjusts WHEN they are written.
- Frozen contracts preserved: ``research_latest.json``,
  ``strategy_matrix.csv``, the v3.15.2
  ``campaign_templates_latest.v1.json`` byte-identity for the 3
  baseline preset templates.

### Tests

- 6 new regression tests in
  ``tests/regression/test_v3_15_3_1_audit_sidecars_on_degenerate.py``:
  catalog sidecar written on degenerate, metadata sidecar written
  on degenerate, sidecar-failure does not mask the original
  ``DegenerateResearchRunError``, sidecar-failure emits the typed
  tracker event, sidecar carries the v3.15.3 pin block invariants
  on the degenerate path, sidecar records run_id.

## [v3.15.3] — Strategy Hypothesis Catalog + First Controlled Strategy Candidate

Date: 2026-04-25
Branch: `feature/v3.15.3-hypothesis-catalog`

v3.15.3 introduces strategy hypotheses as first-class artifact-backed
objects so the v3.15.2 Campaign Operating Layer can autonomously
**select / negate / falsify / cooldown / escalate / deprioritize**
them. This release is **not alpha-expansion**: exactly **one**
hypothesis (`trend_pullback_v1`) carries `status="active_discovery"`;
all other catalog rows are visible-but-not-spawned (`planned`),
explicitly blocked (`disabled`), or enrichment-only (`diagnostic`).

### Added

- **Strategy Hypothesis Catalog** (`research/strategy_hypothesis_catalog.py`,
  `CATALOG_SCHEMA_VERSION="1.0"`,
  `HYPOTHESIS_CATALOG_VERSION="v0.1"`). Closed status enum
  `(active_discovery, planned, disabled, diagnostic)`. Five rows:
  `trend_pullback_v1` (active_discovery), `regime_diagnostics_v1`
  (diagnostic), `atr_adaptive_trend_v0` (planned),
  `volatility_compression_breakout_v0` (planned), `dynamic_pairs_v0`
  (disabled). Hard invariant: exactly one `active_discovery`,
  enforced at import via `_validate_catalog`.
- **Adjacent artifact `research/strategy_hypothesis_catalog_latest.v1.json`**
  written every research run via the canonical `_sidecar_io.write_sidecar_atomic`
  helper. Carries the v3.15.2 campaign-os pin block
  (`schema_version=1.0, authoritative=False, diagnostic_only=True,
  live_eligible=False`).
- **Per-hypothesis Campaign Metadata sidecar**
  (`research/strategy_campaign_metadata.py`,
  `CAMPAIGN_METADATA_SCHEMA_VERSION="1.0"`,
  `STRATEGY_CAMPAIGN_METADATA_VERSION="v0.1"`). Carries
  `eligible_campaign_types`, `cooldown_policy`, `followup_policy`,
  `priority_profile`, `failure_mode_mapping` per hypothesis.
  Adjacent artifact `research/strategy_campaign_metadata_latest.v1.json`.
- **Strategy Failure Taxonomy** (`research/strategy_failure_taxonomy.py`).
  Closed canonical codes
  `(insufficient_trades, cost_fragile, parameter_fragile,
  asset_singleton, oos_collapse, no_baseline_edge, overtrading,
  drawdown_unacceptable, liquidity_sensitive, baseline_underperform)`
  + strategy-specific `STRATEGY_SPECIFIC_ALIASES` mapping (e.g.
  `trend_pullback_cost_fragile -> cost_fragile`). Lives outside
  `research/rejection_taxonomy.py` to protect the v3.11 contract.
- **`pullback_distance` feature primitive** (`agent/backtesting/features.py`)
  registered in `FEATURE_REGISTRY`. Composite of `ema(close, span)` +
  `rolling_volatility(log_returns(close), window)`. Explicit
  zero-volatility guard returns NaN rather than ±inf.
- **`trend_pullback_v1_strategie`** (`agent/backtesting/strategies.py`)
  thin-contract long-only strategy. Max 3 parameters
  (`ema_fast_window, ema_slow_window, entry_k`); declares four
  `FeatureRequirement`s. Bridges to the active_discovery catalog row.
- **`trend_pullback_crypto_1h` preset** (`research/presets.py`)
  bundle=`("trend_pullback_v1",)`, `status="stable"`,
  `preset_class="experimental"`, full hypothesis metadata
  (rationale / expected_behavior / falsification / enablement_criteria).
- **Hypothesis-status filter in campaign policy**
  (`research/campaign_policy._check_template_eligibility`). Bridges
  `preset.bundle[0] -> registry.strategy_family -> catalog.status`,
  rejecting with canonical reasons `hypothesis_not_in_catalog`,
  `hypothesis_status_<status>_not_in_required`,
  `strategy_not_in_registry`, or `preset_bundle_empty`.
- **Eligibility-predicate extension**
  (`research/campaign_templates.py`). New field
  `EligibilityPredicate.require_hypothesis_status: tuple[str, ...]`
  with default `()`. `to_payload()` **omits** the field when empty
  so the existing 3 baseline preset templates remain
  byte-identical in `campaign_templates_latest.v1.json`.
- **Tests:** 86 new tests across:
  - `tests/unit/test_strategy_failure_taxonomy.py` (9)
  - `tests/unit/test_strategy_hypothesis_catalog.py` (18)
  - `tests/unit/test_strategy_campaign_metadata.py` (10)
  - `tests/unit/test_trend_pullback_v1_feature.py` (8)
  - `tests/unit/test_trend_pullback_v1_strategy.py` (10)
  - `tests/unit/test_campaign_policy_hypothesis_status.py` (10)
  - `tests/regression/test_v3_15_2_campaign_templates_byte_identity.py` (6)
  - Plus updated `tests/unit/test_presets.py` count assertion
    (4 -> 5 presets).

### Changed

- `research/run_research.py`: post-run sidecar block (after the v3.15
  paper-validation hook, before `report_agent`) now also writes the
  hypothesis-catalog + campaign-metadata sidecars. Try/except wrapped
  with `tracker.emit_event("v3_15_3_hypothesis_catalog_sidecars_written"
  / "_failed")`.
- `research/registry.py`: appended `trend_pullback_v1` (3 params,
  thin contract, `strategy_family="trend_pullback"`). Legacy
  `trend_pullback` (6 params, `strategy_family="trend_following"`)
  and `trend_pullback_tp_sl` (8 params) are unchanged.
- `research/presets.py`: appended `trend_pullback_crypto_1h` between
  `trend_regime_filtered_equities_4h` and `crypto_diagnostic_1h`.
- `VERSION`: `3.15.1` → `3.15.3`. (v3.15.2 was deployed via the
  campaign operating layer cutover but did not bump the file in
  the local repo.)

### Deliberately not changed (frozen contracts)

- `research/research_latest.json` row + top-level schema.
- 19-column `research/strategy_matrix.csv` row schema.
- `research/candidate_registry_latest.v1.json` schema + writer.
- `research/candidate_registry_latest.v2.json` schema + writer.
- `research/rejection_taxonomy.py` v3.11 canonical codes (the new
  `strategy_failure_taxonomy` is an adjacent module).
- `research/regime_diagnostics.py` behavior — never gates trade
  signals, only registered in catalog as `diagnostic`.
- All v3.12 / v3.13 / v3.14 / v3.15 / v3.15.1 / v3.15.2 sidecar
  schemas + writers.
- Legacy `trend_pullback` and `trend_pullback_tp_sl` registry
  entries (pinned by `test_legacy_trend_pullback_unchanged`).
- v3.15.2 `campaign_templates_latest.v1.json` byte-identity for
  the existing 3 baseline preset templates (pinned by
  `test_v3_15_2_campaign_templates_byte_identity.py`).
- v3.15.2 fb02c2f eligibility hotfix tests still pass unchanged.

### Known limitations

- Auto-status transitions (`active_discovery → cooldown / negated /
  deprioritized`) are not implemented. The catalog ships with
  hand-curated initial statuses; future versions will let the
  campaign launcher mutate status based on accumulated evidence.
- The hypothesis bridge uses `preset.bundle[0]` — multi-strategy
  bundles (e.g. `trend_equities_4h_baseline` with sma_crossover +
  breakout_momentum) are intentionally NOT hypothesis-aware in
  v3.15.3; their templates carry `require_hypothesis_status=()`
  and are gated only by the v3.15.2 preset filters.
- `regime_diagnostics_latest.v1.json` was NOT introduced in
  v3.15.3 (the existing `regime_diagnostics_latest.v1.json`
  already exists from earlier versions; v3.15.3 only registers
  the diagnostic hypothesis row in the catalog).
- The five v3.15.2 verification carry-overs (C1–C5) recorded in
  the v3.15.2 closeout remain explicitly out of scope.

## [v3.15.2] — Autonomous Campaign Operating Layer

Date: 2026-04-25 (production cutover; merged via
`feat/v3.15.2-campaign-operating-layer` + hotfix
`fix/v3.15.2-eligibility-enforcement`)
Branches: `feat/v3.15.2-campaign-operating-layer`,
`fix/v3.15.2-eligibility-enforcement`

Retroactive entry: v3.15.2 shipped via the campaign-operating-layer
cutover commits (`c1c4fd6`, `b6f6ca1`, `798d880`, `fb02c2f`,
`a1dfc88`) but the local `VERSION` and `CHANGELOG.md` were not
bumped at the time. This entry records the shipped scope so
v3.15.3 has a clean continuation.

### Added

- **Autonomous Campaign Operating Layer** (the COL): hourly
  `campaign_launcher` tick decides spawn / skip / reclaim / cancel
  per-tick across 9 closed taxonomies (registry, queue, lease,
  budget, evidence ledger, preset policy, family policy,
  templates, decision).
- **Closed campaign taxonomies** + per-artifact pin-block
  (`research/campaign_os_artifacts.py`, `CAMPAIGN_OS_VERSION="v0.1"`).
- **Modules**: `campaigns.py`, `campaign_policy.py`,
  `campaign_preset_policy.py`, `campaign_family_policy.py`,
  `campaign_templates.py`, `campaign_launcher.py`,
  `campaign_queue.py`, `campaign_registry.py`,
  `campaign_invariants.py`, `campaign_followup.py`,
  `campaign_lease.py`, `campaign_budget.py`,
  `campaign_digest.py`, `campaign_evidence_ledger.py`,
  `campaign_os_artifacts.py`.
- **Sidecars** (10): `campaign_registry_latest.v1.json`,
  `campaign_queue_latest.v1.json`,
  `campaign_policy_decision_latest.v1.json`,
  `preset_policy_state_latest.v1.json`,
  `candidate_family_policy_state_latest.v1.json`,
  `campaign_budget_latest.v1.json`,
  `campaign_digest_latest.v1.json`,
  `campaign_evidence_ledger_latest.v1.jsonl` (+ `.meta.json`),
  `campaign_templates_latest.v1.json`.
- **fb02c2f hotfix**: `_check_template_eligibility` (Filter 0)
  centralised to honour `EligibilityPredicate` against live preset
  attributes before any campaign candidate can be selected. Closes
  the gap that allowed `crypto_diagnostic_1h` (diagnostic_only +
  excluded_from_daily_scheduler) to be picked for `daily_primary`.

### Production-cutover verification (2026-04-25)

- 08:00 UTC tick — R0 reclaimed stale lease.
- 09:00 UTC tick — R1 cancelled upstream-stale candidate.
- 10:00 UTC tick — autonomous spawn of
  `trend_regime_filtered_equities_4h`; eligibility filter blocked
  `crypto_diagnostic_1h` correctly; subprocess ran the trend-equities
  research subprocess. All 7 campaign API endpoints HTTP 200; pin
  blocks intact across all 9 COL artifacts.

### Carry-over backlog (out of scope for v3.15.3)

- C1: degenerate research run misclassified as `worker_crashed`.
- C2: `build_campaign_id` uses local TZ but suffixes `Z`.
- C3: pending entries from R0 reclaim not re-picked.
- C4: GHA `docker-build` workflow lag for `:latest` tag.
- C5: lock-contention error visibility.

## [v3.15.1] — Stale Artifact Banner + Pairs Decision Surface

Date: 2026-04-24
Branch: `fix/v3.15.1-stale-artifact-banner-and-pairs-decision`

Kleine operationele / product-verduidelijking bovenop v3.15. Geen
alpha-uitbreiding, geen nieuwe strategieën, geen engine-contract
wijziging. Twee gaten gesloten:

1. Stale public artifacts bij degenerate / no-survivor runs zijn nu
   zichtbaar in API + UI; `research_latest.json` en
   `strategy_matrix.csv` blijven frozen en onaangeraakt.
2. `pairs_equities_daily_baseline` is expliciet als
   product-/roadmapbeslissing gevisualiseerd — geen kapotte
   placeholder, maar een gedocumenteerde disabled/planned preset met
   rationale, verwacht gedrag, falsificatiecriteria en
   enablement-criteria.

### Added

- **Public artifact status sidecar** (`research/public_artifact_status.py`,
  schema v1.0, `PUBLIC_ARTIFACT_STATUS_VERSION="v0.1"`). Adjacent
  artifact `research/public_artifact_status_latest.v1.json` geschreven
  na **elke** run-poging (success én degenerate). Velden:
  `last_attempted_run` (run_id, attempted_at_utc, preset, outcome,
  failure_stage), `last_public_artifact_write` (run_id, written_at_utc,
  preset), `last_public_write_age_seconds`, `public_artifacts_stale`,
  `stale_reason` (gesloten vocabulary:
  `degenerate_run_no_public_write`, `error_no_public_write`,
  `public_write_never_occurred`), `stale_since_utc`. Missing file is
  **expliciet unknown** (niet impliciet fresh). `stale_since_utc`
  wordt bewaard over opeenvolgende stale runs; een succesvolle run
  reset naar fresh.
- **Dashboard endpoint** `GET /api/research/public-artifact-status`
  (`@requires_auth`, missing-state-safe). Absent-state payload draagt
  `state="absent"` + `public_artifacts_stale=null` zodat consumers
  "confirmed fresh" kunnen onderscheiden van "no signal yet".
- **Frontend banner** `frontend/src/components/StaleArtifactBanner.tsx`.
  Rendert alleen bij `state="valid"` + `public_artifacts_stale=true`.
  Getoond op `/` (Dashboard), `/reports`, `/candidates`. Absent-state
  rendert niets — onbekend is niet onveilig, maar het is ook geen
  impliciete fresh.
- **Preset `enablement_criteria`**: nieuw veld op `ResearchPreset`
  (`tuple[str, ...] = ()`, backward-compatible).
- **Gevulde hypothesis-metadata voor `pairs_equities_daily_baseline`**:
  `rationale`, `expected_behavior`, `falsification`,
  `enablement_criteria` zijn nu gedocumenteerd — van lege placeholder
  naar first-class productbeslissing.
- **Backend-side preset decision inference**: `preset_to_card()`
  exposeert een `decision` dict met gesloten `kind` vocabulary
  (`disabled_planned`, `diagnostic_only`, `scheduler_excluded`, null)
  + `is_product_decision` + `summary` + `requires_enablement`.
  Frontend rendert op basis hiervan — geen business-logic in de UI.
- **Frontend preset decision surface**: `Presets.tsx` toont
  `preset_class` badge + rationale/expected_behavior/falsification
  secties + een dedicated decision-block met backlog_reason en
  genummerde `enablement_criteria` wanneer
  `decision.is_product_decision=true`.

### Changed

- `research/run_research.py`: success-path schrijft nu altijd
  `public_artifact_status` na `write_latest_json`. Elk van de vier
  degenerate-paths (`eligibility_no_candidates`,
  `screening_no_survivors`, `validation_no_survivors`,
  `postrun_no_oos_daily_returns`) schrijft de stale-versie. Fouten
  op de sidecar-write worden gemeld via
  `public_artifact_status_sidecar_failed` tracker-event maar blokkeren
  nooit de run — dit is een observability artifact.
- `research/presets.py`: `ResearchPreset.enablement_criteria` toegevoegd,
  `preset_to_card()` exposeert `enablement_criteria` + `decision`.
- `dashboard/research_artifacts.py`: `load_public_artifact_status()`
  + `PUBLIC_ARTIFACT_STATUS_PATH` constant.
- `frontend/src/api/client.ts`: `PresetCard` interface uitgebreid met
  v3.11 velden (`preset_class`, `rationale`, `expected_behavior`,
  `falsification`) + v3.15.1 velden (`enablement_criteria`,
  `decision`). Nieuwe `PublicArtifactStatus` type +
  `api.publicArtifactStatus()`.
- `frontend/src/routes/Dashboard.tsx`, `Reports.tsx`, `Candidates.tsx`:
  mount `<StaleArtifactBanner />` bovenaan.
- `frontend/src/routes/Presets.tsx`: gesplitst in `PresetCardView`
  met expliciete rendering van hypothesis-metadata + decision-block.
- `frontend/package.json` + `vitest.config.ts`: vitest +
  @testing-library opzet voor frontend-tests.

### Deliberately not changed

- `research_latest.json`: frozen, schema onveranderd.
- `strategy_matrix.csv`: frozen, schema onveranderd.
- `empty_run_diagnostics_latest.v1.json`: onveranderd (blijft
  authoritative source voor degenerate-run detail); de nieuwe sidecar
  is een aparte freshness-surface, geen replacement.
- `run_meta_latest.v1.json`: onveranderd.
- v3.12 / v3.13 / v3.14 / v3.15 sidecars: onveranderd.
- `candidate_registry_latest.v1.json` / `.v2.json`: onveranderd.
- Engine / strategy registry / orchestration layer: onveranderd.
- `pairs_equities_daily_baseline`: blijft `enabled=False`,
  `status="planned"`. Deze release activeert géén pairs-logic —
  documenteert alleen de bestaande beslissing als first-class surface.
- `SCORING_FORMULA_VERSION`: blijft `v0.1-experimental`.

### Tests

- `tests/unit/test_public_artifact_status.py` (16): version pins,
  outcome handling (success / degenerate / error), stale_reason
  vocabulary, stale_since_utc preservation, stale→fresh transition,
  atomic write round-trip, schema validation.
- `tests/unit/test_dashboard_api_public_artifact_status.py` (5): auth
  gate, explicit absent-state (`public_artifacts_stale=null`),
  success pass-through, stale pass-through with
  `last_public_write_age_seconds`, invalid-json fallback.
- `tests/unit/test_presets.py` (+6): `enablement_criteria` default,
  pairs preset carries full research metadata + enablement criteria,
  card exposes new fields, decision inference on pairs / baseline /
  diagnostic presets, JSON safety.
- `tests/integration/test_public_artifact_status_end_to_end.py` (5):
  success → fresh, degenerate-without-prior →
  `public_write_never_occurred`, degenerate-after-success preserves
  write block, stale → fresh transition after later success, sidecar
  write failure still emits tracker event + raises degenerate error.
- `frontend/src/components/__tests__/StaleArtifactBanner.test.tsx` (4):
  absent / fresh / stale / api-error rendering behavior.
- `frontend/src/routes/__tests__/Presets.test.tsx` (3): decision block
  visible on disabled_planned, hidden on enabled stable, no
  cross-contamination in mixed preset lists.

### Known limitations

- Geen bar-level freshness — de sidecar is run-granulariteit.
- Geen per-sidecar freshness (elk v3.12+ sidecar apart). v3.15.1
  dekt alleen de twee publieke frozen contracts.
- `enablement_criteria` voor pairs zijn indicatief — de formele
  v3.11 equity-pairs ADR blijft de gate voor een latere enablement.
- Error-outcome (`STALE_REASON_ERROR`) is geschikt voor toekomstige
  outer try/except wrapper rond `run_research`; wordt in v3.15.1 niet
  automatisch geschreven bij onverwachte exceptions buiten de
  degenerate / success paden.

## [v3.15] — Paper Validation Engine

Date: 2026-04-24
Branch: `feature/v3.15-paper-validation-engine`

Strictly additive **paper validation engine** on top of the v3.14
portfolio / sleeve layer. Geen live trading, geen broker-integratie,
geen shadow deployment, geen allocator. Elke wijziging is additief;
de v3.12 / v3.13 / v3.14 frozen artifacts blijven onaangetast en
v3.15 schrijft nooit naar hun paths.

v3.15 beantwoordt drie vragen per kandidaat:

1. **Ledger** — welke signal/order/fill/reject/skip/position events
   genereert deze kandidaat onder paper-semantiek?
2. **Divergence** — hoe wijkt paper af van de engine baseline
   (metrics delta, venue-cost delta, timestamp-aligned coverage)?
3. **Readiness** — is deze kandidaat klaar voor een eventuele v3.16+
   paper-promotion, of is er een blocking reason? `live_eligible`
   is in v3.15 altijd `False`, hard gepind.

### Added

- **Venue mapping** (`research/paper_venues.py`). `asset_type →
  ScenarioSpec` mapping voor `crypto` (Bitvavo: 0.25% per kant +
  10 bps slippage), `equity` (IBKR: €1/€2000 notional = 5 bps per
  kant + 10 bps slippage; `VENUE_IBKR_EQUITY_ASSUMED_NOTIONAL_EUR`
  geëxposeerd in elk artifact dat IBKR gebruikt), en
  `polymarket_binary` (2% spread + 10 bps — **gedefinieerd, niet
  toegepast** in v3.15). `unknown` / `futures` / `index_like`
  krijgen geen fallback — `venue_name_for_asset_type` returnt
  `None` en readiness vertaalt dat naar een
  `insufficient_venue_mapping` blocking reason.
  `PAPER_VENUES_VERSION = "v0.1"`.
- **Timestamped returns bridge**
  (`research/candidate_timestamped_returns_feed.py`). Closes v3.14
  handoff §8.1. Consumeert de al-bestaande
  `evaluation_report.evaluation_streams.oos_daily_returns` typed
  stream van de engine zonder engine-contract uitbreiding. Nieuwe
  `TimestampedCandidateReturnsRecord` dataclass draagt parallel
  `timestamps` en `daily_returns` arrays plus een expliciete
  `stream_error` code wanneer de engine stream missing / malformed
  / duplicate was. v3.14 `CandidateReturnsRecord` blijft frozen.
- **Shared OOS-stream validator** (`research/_oos_stream.py`).
  Extracted uit `portfolio_reporting._normalize_stream` zodat
  `candidate_timestamped_returns_feed` en `paper_divergence`
  dezelfde implementatie hergebruiken. Gedrag byte-identical met
  pre-extraction — v3.12+ artifacts blijven byte-identical.
- **Paper ledger** (`research/paper_ledger.py`). First-class
  lifecycle projectie. Gesloten event-taxonomy (`signal`, `order`,
  `fill`, `reject`, `skip`, `position`) en gesloten
  evidence-status taxonomy (`reconstructed`, `projected_minimal`,
  `projected_insufficient`). Elk event draagt expliciete `lineage`
  pointers naar `oos_execution_events`. Signal + position events
  zijn `projected_minimal` omdat de engine ze niet apart
  serialiseert — v3.15 vindt nooit bron-evidence uit. Unmapped
  venues krijgen alleen `signal` + `reject(reason=
  insufficient_venue_mapping)`. Deterministic ordering via
  `(timestamp_utc, lifecycle_index, event_id)`.
  `PAPER_LEDGER_VERSION = "v0.1"`.
- **Paper divergence** (`research/paper_divergence.py`). Per
  candidate / per sleeve / portfolio-level divergence. Math is het
  per-fill multiplicatieve model uit
  `agent.backtesting.cost_sensitivity` (analytisch equivalent voor
  scalar metrics; bar-level timestamped paper-returns stream
  deferred naar v3.16). Rapporteert: `metrics_delta` (final
  equity, cumulative adjustment, sharpe proxy), `venue_cost_delta`
  (per-fill adjustment, fee drag delta vs baseline, slippage drag),
  `timestamp_aligned_return_diff` (coverage window), en
  `divergence_severity` via named drempels
  (`DIVERGENCE_SEVERITY_MEDIUM_BPS=25`,
  `DIVERGENCE_SEVERITY_HIGH_BPS=75`). Portfolio-level gebruikt
  `exact_timestamp_intersection` (mirror van
  `portfolio_reporting.ALIGNMENT_POLICY`).
  `PAPER_DIVERGENCE_VERSION = "v0.1"`.
- **Paper readiness** (`research/paper_readiness.py`). First-class
  gate. Gesloten blocking-reason taxonomy:
  `insufficient_venue_mapping`, `insufficient_oos_days`,
  `missing_execution_events`, `excessive_divergence`,
  `malformed_return_stream`, `no_candidate_returns`. Gesloten
  warning taxonomy: `negative_paper_sharpe` (warning by default,
  niet blocking), `projected_insufficient_events_ratio_high`,
  `medium_divergence`. Status ∈ `{ready_for_paper_promotion,
  blocked, insufficient_evidence}`. Thresholds named:
  `MIN_PAPER_OOS_DAYS=60`, `MIN_PAPER_SHARPE_FOR_READY=0.3`,
  `WARN_PROJECTED_INSUFFICIENT_RATIO=0.20`. `live_eligible=False`
  is top-level hard-pinned in de payload — geen enkel codepath
  zet het op `True`. `PAPER_READINESS_VERSION = "v0.1"`.
- **Parallel façade** (`research/paper_validation_sidecars.py`).
  Mirrors v3.14 façade exactly. Frozen
  `PaperValidationBuildContext` + single
  `build_and_write_paper_validation_sidecars(ctx)` entry. All
  writes gaan door `_sidecar_io.write_sidecar_atomic` zodat elke
  artifact canonical en byte-reproducible is.
- **Runner hook** (`research/run_research.py`). Één additieve block
  na de v3.14 portfolio-sleeve hook. Leest
  `sleeve_registry_latest.v1.json` voor sleeve membership lookup,
  construeert `PaperValidationBuildContext` uit de al-bestaande
  `evaluations` accumulator + registry_v2 payload, en roept de
  façade aan. Try/except zodat v3.15 falen nooit de v3.14 run
  maskeert.
- **Report extension** (`research/report_agent.py`).
  `_paper_layer_summary()` helper + optionele top-level
  `paper_layer_summary` key + `_append_paper_layer_section()`
  markdown renderer. Aggregeert ledger event counts, divergence
  severity distribution, readiness counts, candidate count. Report
  `schema_version` blijft `"1.1"`.
- **Dashboard endpoints** (`dashboard/dashboard.py`). Vier read-only
  `@requires_auth` endpoints:
  - `GET /api/registry/paper` — summary (readiness counts +
    divergence severity distribution + ledger event counts +
    artifact states)
  - `GET /api/registry/paper/ledger`
  - `GET /api/registry/paper/divergence`
  - `GET /api/registry/paper/readiness`
  Alle vier pinnen `live_eligible=false` in zowel missing-state
  als happy-path schemas.
- **Vier nieuwe sidecars** (alle `schema_version="1.0"`,
  `authoritative=false`, `diagnostic_only=true`,
  `live_eligible=false`):
  - `research/candidate_timestamped_returns_latest.v1.json`
  - `research/paper_ledger_latest.v1.json`
  - `research/paper_divergence_latest.v1.json`
  - `research/paper_readiness_latest.v1.json`

### Changed

- `research/portfolio_reporting.py`: `_normalize_stream` is nu een
  thin delegate naar `research._oos_stream.normalize_oos_daily_return_stream`.
  Gedrag byte-identical; v3.12 artifacts blijven byte-identical.
- `research/run_research.py`: één nieuwe try/except block met
  `build_and_write_paper_validation_sidecars` direct na de v3.14
  hook. Runner blijft dun.
- `research/report_agent.py`: additief — `paper_layer_summary` top-
  level key + markdown sectie. `schema_version` blijft `"1.1"`.
- `dashboard/dashboard.py`: vier nieuwe routes; bestaande routes
  onveranderd.
- `VERSION`: `3.14.1` → `3.15.0`.

### Deliberately NOT changed

- `research/candidate_returns_feed.py` (v3.14 frozen). De v3.15
  precision-upgrade is een *nieuwe* sidecar — v3.14's shape en
  bytes blijven onaangetast.
- `research/candidate_scoring.py`. `SCORING_FORMULA_VERSION` blijft
  `"v0.1-experimental"`, `composite_status` blijft `"provisional"`,
  `authoritative` blijft `False`. Scoring-bump naar
  `v0.2-experimental` is uitgesteld naar v3.16 (vereist
  evidence-gedreven goldens-update).
- `agent/backtesting/engine.py` + `agent/backtesting/cost_sensitivity.py`.
  v3.15 hergebruikt beide zonder wijziging.
- Geen forced-sleeves, geen allocator, geen Kelly, geen
  vol-targeting, geen frontend UI-tab.

### Tests

- **Unit**: 63 nieuw
  - `tests/unit/test_paper_venues.py` (16)
  - `tests/unit/test_oos_stream.py` (9)
  - `tests/unit/test_candidate_timestamped_returns_feed.py` (6)
  - `tests/unit/test_paper_ledger.py` (8)
  - `tests/unit/test_paper_divergence.py` (7)
  - `tests/unit/test_paper_readiness.py` (11)
  - `tests/unit/test_paper_validation_sidecars_facade.py` (5)
  - `tests/unit/test_dashboard_api_v315.py` (8)
  - `tests/unit/test_paper_no_live_invariant.py` (3)
  - `tests/unit/test_report_agent_paper_layer.py` (5)
- **Integration**: 3 nieuw
  - `tests/integration/test_paper_validation_end_to_end.py` (3)
- **Regression**: 4 nieuw
  - `tests/regression/test_v3_15_artifacts_deterministic.py` (4)

Totaal **70 nieuwe tests**, alle green. Static analysis (mypy,
flake8, bandit) schoon op alle v3.15 modules.

### Known limitations (voor v3.16)

- **Bar-level timestamped paper-returns stream** deferred. v3.15
  gebruikt het analytische per-fill multiplicatieve model
  (scalar-equivalent aan `cost_sensitivity`). v3.16 kan bar-exact
  replay inschakelen via `build_cost_sensitivity_report` met
  `oos_bar_returns` + `fill_positions` plumbing.
- **Polymarket venue** gedefinieerd, niet toegepast. Wacht op
  Polymarket candidates in de research pipeline via Bot /
  DataArbitrage agent integratie.
- **Scoring bump** `v0.1-experimental → v0.2-experimental` blijft
  uitgesteld. `regime_breadth_signal` als composite-component is
  pas gerechtvaardigd na meerdere runs met consistent bewijs.
- **Allocator / Kelly / vol-targeting** expliciet buiten scope.
  v3.15 blijft equal-weight paper-portfolio (mirror v3.14).
- **Frontend UI**: geen paper-tab; consumptie via 4 endpoints +
  markdown report. v3.16+ kan een read-only paper-tab toevoegen
  wanneer operationele behoefte bevestigd is.
- **Paper-to-live promotion** niet geïmplementeerd.
  `live_eligible=False` is hard gepind en v3.15 levert geen
  codepath die dit verandert.

---

## [v3.14.1] — Runtime budget + preset universe hotfix

Date: 2026-04-24
Branch: `fix/v3.14.1-runtime-budget-and-preset-universe`

Targeted hotfix on top of v3.14 for the two blocking bugs that
prevented daily / canary runs from completing on the VPS. No new
features, no v3.15 work, no new strategies, no output contract
changes. `research/research_latest.json` and
`research/strategy_matrix.csv` schemas are untouched.

### Fixed

- **Screening candidate budget default** — raised from 60s to
  300s (`research/run_research.py::DEFAULT_SCREENING_CANDIDATE_BUDGET_SECONDS`).
  The 60s default was too aggressive for warm-start screening on
  Hetzner CX22 and caused frequent unwanted candidate interrupts.
  Config override via `research.screening.candidate_budget_seconds`
  remains authoritative — explicit values (including `0` =
  no budget) are respected verbatim.
- **Candidate-level timeout on screening interrupt** —
  `execute_screening_candidate_isolated` returning
  `execution_state="interrupted"` no longer raises
  `KeyboardInterrupt`. That `BaseException` bypassed the enclosing
  `except Exception` and killed the entire daily / canary run on
  a single candidate timeout, leaving `running` artifacts behind.
  The branch now emits a candidate-level outcome:
  - `final_status = FINAL_STATUS_TIMED_OUT`
  - `reason_code = "candidate_budget_exceeded"` (already a
    documented v3.12 taxonomy code; no new strings)
  - `legacy_decision.status = "rejected_in_screening"`
  - `legacy_decision.reason = "candidate_budget_exceeded"`
  - preserves isolated_result `elapsed_seconds`, `samples_total`,
    `samples_completed`
  - emits a `screening_candidate_budget_exceeded` tracker event
  Control falls through into the regular post-candidate loop; the
  existing `FINAL_STATUS_TIMED_OUT` branch at
  `run_research.py:2313` continues to tally
  `batch["timed_out_count"]`. The run proceeds to the next
  candidate. A real user `Ctrl-C` from outside still raises
  `BaseException` and propagates unchanged — the enclosing handler
  was never widened.
- **Preset universe is load-bearing for preset-runs** — new helper
  `research.universe.build_research_universe_from_preset`. Before
  v3.14.1, preset-runs first resolved assets via
  `build_research_universe(research_config)`, which reads
  `research.universe.source` (default `crypto_major`). The
  preset's `universe` field was effectively ignored. That meant
  `trend_equities_4h_baseline` silently ran on crypto assets
  instead of NVDA/AMD/ASML/MSFT/META/AMZN/TSM.
  The runner at `run_research.py:1843-1853` now branches: if a
  preset is active, route through the preset helper; otherwise
  use the config-driven path. `preset.universe` is authoritative,
  `intervals` defaults to `[preset.timeframe]`,
  `interval_lookbacks` / `default_lookback_days` still come from
  `research_config`. Empty `preset.universe` raises `ValueError`.
  Snapshot provenance uses `source="preset:<name>"` and
  `resolver="preset"` so lineage is unambiguous.

### Changed (additive only)

- `research/run_research.py`: three edits (budget default,
  interrupted branch rewrite, preset-aware universe wiring).
- `research/universe.py`: new public function
  `build_research_universe_from_preset` +
  `_infer_asset_type_from_symbol` helper.
- `VERSION`: `3.14.0` → `3.14.1`.

### Deliberately **not** changed

- No new config keys.
- No taxonomy extensions (`candidate_budget_exceeded` is a v3.12
  code).
- No engine / cost_sensitivity / backtesting surface change.
- No sidecar schema or byte-identity change.
- No frontend work, no dashboard endpoints, no execution-bridge
  surface.
- No v3.15 paper-validation changes on this branch.

### Tests (19 new)

- `tests/unit/test_run_research_screening_budget_v3_14_1.py` (9):
  default = 300, config override authoritative, zero = no-budget
  sentinel, negative clamped to zero, interrupted branch projects
  to candidate-level timeout with correct shape, no legacy
  `KeyboardInterrupt` raise, taxonomy membership, except-scope
  invariant (`except Exception`, not `BaseException`).
- `tests/unit/test_run_research_preset_universe_v3_14_1.py` (10):
  trend_equities_4h_baseline resolves to its preset universe (not
  crypto_major), crypto preset resolves to crypto asset_type,
  intervals = [preset.timeframe], empty preset.universe → clear
  ValueError, None preset rejected, preset path ignores config
  `research.universe.source`, lookback config still honoured,
  non-preset runs still use `build_research_universe`, default
  still `crypto_major` for empty config, runner source actually
  calls the preset helper.

All 19 green. Full suite: green (delta documented in handoff).

---

## [v3.14] — Portfolio / Sleeve Research

Date: 2026-04-23
Branch: `feature/v3.14-portfolio-sleeve-research`

Strictly additive portfolio / sleeve research layer on top of the
v3.12 candidate and v3.13 regime infrastructure. No paper / live /
broker surfaces, no allocator, no Kelly overlay, no optimizer. Every
change is additive; `research/research_latest.json`,
`research/strategy_matrix.csv`, `research/candidate_registry_latest.v1.json`,
and the shape / values of every v3.12 field on
`research/candidate_registry_latest.v2.json` remain byte-identical.
All v3.14 data lands in four new adjacent sidecars joined on
`candidate_id` / `sleeve_id` — no in-place v2/v3.13 mutation.

The v3.14 layer answers "how do these candidates *compose*?" rather
than "is this candidate good?". It is diagnostic-first and explicitly
non-authoritative (`authoritative=false`, `diagnostic_only=true` in
every payload).

### Added

- **Sleeve registry** (`research/sleeve_registry.py`). Deterministic
  grouping of v3.12 candidates by `(strategy_family, asset_class,
  interval)` triples, derived from the existing `experiment_family`
  and `interval` fields on the v2 registry. Only lifecycle
  `candidate` entries are members; `rejected` / `exploratory` are
  excluded. Optional research-variant sleeves with a
  `__regime_filtered` suffix exist for every candidate whose v3.13
  overlay reports `regime_assessment_status == "sufficient"`.
  `ASSIGNMENT_RULE_VERSION = "v0.1"`.
- **Per-candidate returns bridge** (`research/candidate_returns_feed.py`).
  Typed extraction of per-candidate daily-return series from the
  in-memory `evaluations` list populated in
  `research.run_research.run_research`. Returns are read from the
  engine's public `last_evaluation_report.evaluation_samples.daily_returns`
  accessor — no engine contract widening. Every record carries an
  explicit `alignment = "utc_daily_close"` and
  `timestamp_semantics = "engine_window_close_utc"` so consumers can
  reason about the data lineage.
- **Width-axis feed** (`research/regime_width_feed.py`). Closes the
  v3.13 §8.1 gap. For every `(asset, interval)` pair in the v2
  registry the feed reuses the cached OHLCV response produced by the
  backtest's own `data.repository.MarketRepository.get_bars` call,
  runs `research.regime_classifier.classify_bars`, and produces a
  per-candidate `width_distributions` dict. The v3.13 façade now
  consumes this dict so `regime_dependency_score_width`,
  `regime_tags_summary.width`, and the `trend_expansion` gate can
  emit real evidence-backed values. Per-source lineage (asset,
  interval, bar count, adapter, `cache_hit`) is persisted alongside
  the raw distributions. `WIDTH_FEED_VERSION = "v0.1"`.
- **Portfolio / sleeve diagnostics**
  (`research/portfolio_diagnostics.py`). Diagnostic-only correlation
  matrix (aligned-suffix) across the candidate universe, an
  equal-weight research portfolio (Sharpe / Sortino / annualised
  return / max drawdown / Calmar), drawdown attribution over the
  worst-window of the equal-weight portfolio, HHI-based concentration
  warnings on asset and sleeve dimensions, intra-sleeve correlation
  warnings, turnover-activity-ratio per sleeve, and a
  regime-conditioned `regime_breadth_diagnostic` per sleeve derived
  from v3.13 per-axis dependency scores. Every threshold is a named,
  warning-only constant exposed in the artifact `thresholds` block:
  `MIN_OVERLAP_DAYS=90`, `HHI_WARN_THRESHOLD=0.4`,
  `INTRA_SLEEVE_CORR_WARN_THRESHOLD=0.7`,
  `MAX_DRAWDOWN_CONTRIBUTION_WARN_THRESHOLD=0.5`,
  `MIN_SAMPLES_FOR_STATS=5`. `DIAGNOSTICS_LAYER_VERSION = "v0.1"`.
- **Parallel façade** (`research/portfolio_sleeve_sidecars.py`).
  Mirrors the v3.12 and v3.13 façade pattern exactly. One
  `PortfolioSleeveBuildContext` dataclass + single
  `build_and_write_portfolio_sleeve_sidecars(ctx)` entry point
  invoked once from `run_research.py` after the v3.13 façade.
  Canonical atomic writes reuse `_sidecar_io.write_sidecar_atomic`.
- **New sidecars** (overlay-first, all `schema_version="1.0"`):
  - `research/sleeve_registry_latest.v1.json`
  - `research/candidate_returns_latest.v1.json`
  - `research/portfolio_diagnostics_latest.v1.json`
  - `research/regime_width_distributions_latest.v1.json`
- **API endpoint** — `GET /api/registry/portfolio`. Read-only,
  `@requires_auth`, mirrors `/api/registry/regime` verbatim. Stable
  missing-state payload with
  `artifact_state="missing"`, `authoritative=false`,
  `diagnostic_only=true`, and empty collection fields so consumers
  can differentiate "fresh environment" from "corrupted sidecar".

### Changed (additive only)

- `research/run_research.py`: three new thin additions after the
  v3.12/v3.13 façade block — (1) width feed driver, (2) in-place
  wiring of `width_distributions=...` into the existing v3.13
  context, (3) single call to the v3.14 façade with registry v2 +
  regime overlay + in-memory evaluations. No engine-contract change.
- `research/report_agent.py`: new `_portfolio_layer_summary()` helper
  + new optional top-level key `portfolio_layer_summary` + one
  additive markdown section. Report `schema_version` stays `"1.1"`.
- `dashboard/dashboard.py`: `/api/registry/portfolio` added.

### Deliberately **not** changed in v3.14

- `research/candidate_scoring.py` — untouched. `regime_breadth` is
  exposed only as a diagnostic in the portfolio artifacts and the
  sleeve registry. No scoring-formula bump in v3.14;
  `SCORING_FORMULA_VERSION = "v0.1-experimental"`,
  `composite_status = "provisional"`, `authoritative = False` are all
  preserved.
- `research/candidate_registry_v2.py` — untouched. Overlay join is
  preserved as the canonical pattern.
- `research/regime_sidecars.py` — signature untouched.
  `width_distributions` is now populated via the new feed instead of
  `None`; no API change.
- `agent/backtesting/*` — untouched. No engine-contract widening.
- No new strategies, no new presets, no frontend work, no
  execution / paper / live surfaces, no allocator, no optimizer, no
  Kelly overlay.

### Tests (34 new)

- `tests/unit/test_regime_width_feed.py` (5): cache-hit determinism,
  graceful fetch-failure, bucket-count correctness, per-pair
  deduplication, missing-date-range skip.
- `tests/unit/test_candidate_returns_feed.py` (5): record schema,
  insufficient-returns path, alignment field, canonical ordering,
  deduplication rule.
- `tests/unit/test_sleeve_registry.py` (6): empty-registry
  behaviour, lifecycle filter, family/interval grouping,
  regime-filtered variant emission only on `sufficient`, determinism
  under input reordering, canonical payload shape.
- `tests/unit/test_portfolio_diagnostics.py` (6): empty-input
  payload shape, correlation+portfolio happy path, concentration
  warning threshold trip, intra-sleeve correlation warning for
  duplicated series, `MIN_OVERLAP_DAYS` flag semantics, envelope
  shape.
- `tests/unit/test_portfolio_sleeve_sidecars_facade.py` (4):
  all-core sidecars written, width sidecar present only when feed
  attached, byte-identical across reruns, graceful empty-registry
  fallback.
- `tests/unit/test_dashboard_api_v314.py` (3): auth, missing-state
  schema, happy-path payload.
- `tests/regression/test_v3_14_artifacts_deterministic.py` (3):
  byte-identical reruns, pinned `schema_version` everywhere, frozen
  v1 registry never touched.
- `tests/integration/test_portfolio_sleeve_end_to_end.py` (2):
  end-to-end wiring produces all four sidecars, rerun byte-identity.

Full suite: **1322 passed, 1 skipped, 0 failed** in 11m12s.
mypy / flake8 / bandit clean on every new and modified v3.14 module.

### Known v3.14 limitations (v3.15 pickup)

- Correlation matrix uses suffix-alignment on aggregated daily
  returns rather than timestamp alignment — honest for the current
  engine output shape, but loses precision when candidates run on
  non-overlapping windows. A typed timestamped returns stream in
  v3.15 would upgrade this.
- Joint `(trend, vol)` bar tagging is still not available;
  `trend_low_vol` continues to use the conservative intersection
  documented in v3.13.
- `regime_breadth_signal` is a diagnostic on portfolio artifacts
  only — `candidate_scoring.py` remains at `v0.1-experimental` and
  non-authoritative. Promoting breadth into the composite is v3.15+.
- No frontend surface. Consumption via `/api/registry/portfolio` and
  the markdown report.
- Equal-weight only. Volatility-targeted and capped-concentration
  research portfolios deferred.

## [v3.13] — Regime Intelligence & Gating

Date: 2026-04-23
Branch: `feature/v3.13-regime-intelligence`

Diagnostic-first regime layer on top of the realized v3.12 candidate
infrastructure. No new strategies, no new presets, no new base
metrics, no allocation logic. Every change is additive; the
v3.11/v3.12 public contracts (`research_latest.json`,
`strategy_matrix.csv`, `candidate_registry_latest.v1.json`, and the
shape/values of every v3.12 field on
`candidate_registry_latest.v2.json`) remain byte-identical. All v3.13
data lands in two new adjacent sidecars joined on `candidate_id` —
no in-place v2-registry enrichment.

### Added

- **Regime classifier** (`research/regime_classifier.py`).
  Axis-separable, deterministic, `shift(1)` no-lookahead. Three
  independent axes: `trend` (trending / non_trending / insufficient),
  `vol` (low_vol / high_vol / insufficient), `width` (expansion /
  compression / insufficient). Trend and volatility normalizers
  consume the labels already produced by
  `agent/backtesting/regime.py`; the width axis is a new Bollinger
  bandwidth vs rolling-median comparator. Explicit named constants
  for every threshold; no tuning loop.
  `REGIME_CLASSIFIER_VERSION = "v0.1"`.
- **Per-candidate regime diagnostics**
  (`research/regime_diagnostics.py`). HHI-style per-axis dependency
  scores (`regime_dependency_score_trend|vol|width`) plus an
  explicit aggregate (`overall`). Hard sufficiency gates
  (`MIN_TRADES_PER_AXIS=10`, `MIN_REGIMES_WITH_EVIDENCE=2`) produce
  `regime_assessment_status ∈ {sufficient,
  insufficient_regime_evidence}`. Silence is preferred over
  fabricated precision — missing or thin axes emit `null` metrics,
  never crash. `REGIME_CONCENTRATED_THRESHOLD = 0.7`.
- **Multi-rule gating framework** (`research/regime_gating.py`).
  Three fixed predefined rules — `trend_only`, `trend_low_vol`,
  `trend_expansion` — each reported with baseline / filtered /
  delta for every sufficient candidate. No gate search, no
  optimization loop, no winner-picking (no `best_rule` field — it
  is always `null` in v3.13). Width-dependent rules mark
  `insufficient_axis_evidence` rather than fabricate a filter.
  Conjunctions with vol use an explicitly documented conservative
  intersection (joint bar tagging is deferred to v3.14).
- **Parallel façade** (`research/regime_sidecars.py`). One
  `RegimeSidecarBuildContext` + `build_and_write_regime_sidecars()`
  call is the sole new hook in `run_research.py`. Canonical atomic
  writes reuse `_sidecar_io.write_sidecar_atomic`. v3.12 façade
  stays untouched.
- **New sidecars** (overlay-first):
  - `research/regime_intelligence_latest.v1.json`
    (`schema_version="1.0"`, `classifier_version="v0.1"`,
    `regime_layer_version="v0.1"`).
  - `research/candidate_registry_regime_overlay_latest.v1.json`
    (`schema_version="1.0"`). Registry-shaped overlay; consumers
    join on `candidate_id` against `candidate_registry_latest.v2.json`.
    Fields: `regime_assessment_status`,
    `regime_dependency_scores`, `regime_concentrated_status`
    (`emitted | below_threshold | insufficient_evidence |
    absent_sidecar`), `regime_gating_summary.best_rule = null`.
- **API endpoint** — `GET /api/registry/regime`. Read-only,
  `@requires_auth`, mirrors the v3.12 endpoint pattern. Stable
  missing-state payload with `schema_version="1.0"`,
  `classifier_version=null`, `generated_at_utc=null`,
  `artifact_state="missing"`, `entries=[]`.

### Changed (additive only)

- `research/rejection_taxonomy.py`: `derive_taxonomy()` accepts
  optional `regime_intelligence=` and
  `regime_concentrated_threshold=` kwargs. When the intelligence
  sidecar carries a matching entry with sufficient evidence and any
  per-axis score ≥ threshold, `regime_concentrated` is emitted with
  `derivation_method="classifier_output"` and
  `observed_sources` lists the triggering axis
  (e.g. `regime_dependency_score_trend`). Sidecar absent for the
  candidate → legacy `flag_source` path unchanged. Sidecar present
  but evidence insufficient → silence (no overclaiming). Positional
  v3.12 signature stays byte-compatible.
- `research/report_agent.py`: new `_enrich_with_regime_fields()`
  additive helper and new optional top-level key
  `regime_layer_summary`. Report `schema_version` stays `"1.1"`.
- `research/run_research.py`: one new thin call after the v3.12
  façade. In v3.13 `width_distributions=None` so the width axis is
  marked insufficient until v3.14 wires a per-asset OHLCV feed.
- `dashboard/dashboard.py`: `/api/registry/regime` added.

### Deliberately **not** changed in v3.13

- `research/candidate_scoring.py` — untouched to keep every v3.12
  field on the v2 registry byte-identical in shape and value.
  Regime-breadth integration into the composite is deferred to
  v3.14 with a proper `SCORING_FORMULA_VERSION` bump and regression
  golden update.
- `research/candidate_registry_v2.py` — untouched. Overlay join
  replaces in-place enrichment.
- `agent/backtesting/*` — untouched. No engine-contract widening.
- No new strategies, no new presets, no frontend refactor, no
  execution/paper/live surfaces, no dynamic allocation.

### Tests (44 new)

- `tests/unit/test_regime_classifier.py` (15): determinism,
  no-lookahead invariant, expansion/compression synthetic fixtures,
  insufficient lookback handling.
- `tests/unit/test_research_regime_diagnostics.py` (8): per-axis
  HHI scores, sufficiency gates, width plumbing, upstream
  unknown-label collapse, overall aggregate semantics.
- `tests/unit/test_regime_gating.py` (7): three fixed rules,
  width-dependent rules marked insufficient, conservative
  intersection on `trend_low_vol`, no winner-picking API surface.
- `tests/unit/test_rejection_taxonomy_v3_13.py` (5):
  classifier-output derivation above threshold, silence below and
  on insufficient evidence, legacy fallback when the sidecar is
  absent.
- `tests/unit/test_dashboard_api_v313.py` (3): auth, missing-state
  schema, happy-path payload.
- `tests/integration/test_regime_sidecars_end_to_end.py` (6):
  both sidecars written, overlay join on every `candidate_id`,
  missing-state graceful, byte-identical reruns, `best_rule=null`.
- `tests/regression/test_v12_contracts_preserved.py` (4):
  `derive_taxonomy` v3.12 signature and semantics preserved when
  the new v3.13 optional params are unused.

Full suite: **1221 passed, 1 skipped, 0 failed**.
mypy / flake8 / bandit clean on every new and modified v3.13 module.

### Known v3.13 limitations (v3.14 pickup)

- Width axis runs empty in production (width_distributions=None);
  classifier is complete and tested, only the feed is deferred.
- Joint (trend, vol) bar tagging is not available in
  `regime_diagnostics_latest.v1.json`; `trend_low_vol` uses a
  conservative intersection.
- Sharpe / max-drawdown on filtered subsets are reported as `null`
  because bar-level streams are not serialized.
- Composite scoring is unchanged; regime-breadth integration is
  v3.14 work.

## [v3.12] — Candidate Promotion Framework 2.0

Date: 2026-04-23
Branch: `feature/v3.12-candidate-promotion-framework`

First-class candidate lifecycle and lineage. No new strategies, no
new metrics, no new promotion thresholds. Every change is additive;
the v3.11 public contracts (`research_latest.json`,
`strategy_matrix.csv`, `candidate_registry_latest.v1.json`) remain
byte-identical. All v3.12 data lands in new adjacent sidecars with
their own `schema_version` pins.

### Added

- **Candidate lifecycle status model** (`research/candidate_lifecycle.py`).
  Durable 8-status enum spanning v3.12–v3.17:
  `rejected | exploratory | candidate | paper_ready | paper_validated
  | live_shadow_ready | live_enabled | retired`. Two-layer validation:
  - `FULL_LIFECYCLE_GRAPH` — the complete reference graph for
    downstream phases.
  - `ACTIVE_TRANSITIONS_V3_12` — strict runtime subset
    (`exploratory → candidate | rejected`, `candidate → rejected`).
    Transitions into reserved statuses raise `ReservedStatusError`
    so later-phase slots cannot be entered accidentally.
  - `map_legacy_verdict()` returns `(lifecycle_status, mapping_reason)`,
    preserving `needs_investigation → exploratory` as
    `legacy_needs_investigation_mapped_to_exploratory`.
  - `STATUS_MODEL_VERSION = "v3.12.0"`.
- **Unified rejection taxonomy** (`research/rejection_taxonomy.py`).
  Eight codes from the spec: `insufficient_trades`, `no_oos_samples`,
  `oos_collapse`, `cost_sensitive`,
  `unstable_parameter_neighborhood`, `regime_concentrated`,
  `single_asset_dependency`, `low_statistical_defensibility`.
  Observed vs derived split:
  - `collect_observed_reason_codes()` — raw v3.11 reasoning codes,
    unchanged.
  - `derive_taxonomy()` — only emits codes with defensible
    derivation (direct mapping from promotion codes,
    flag_source from regime/cost sidecars).
  - `DEFERRED_TAXONOMY_CODES`: `unstable_parameter_neighborhood`,
    `single_asset_dependency`, `no_oos_samples` — deliberately not
    derived in v3.12.
  - No per-entry timestamps — per-entry byte-reproducibility.
- **Deterministic candidate scoring** (`research/candidate_scoring.py`).
  Components (each 0..1, `None` when source missing): `dsr_signal`,
  `psr_signal`, `drawdown_signal`, `stability_signal`,
  `trade_density_signal`, `breadth_signal`. Composite is
  equal-weighted mean of available components, emitted with
  `composite_status="provisional"` and `authoritative=False`
  (double signal so no downstream consumer mistakes it for a
  promotion authority). `SCORING_FORMULA_VERSION = "v0.1-experimental"`.
- **Candidate status history** (`research/candidate_status_history.py`).
  Append-only sidecar with deterministic
  `event_id = sha256(candidate_id|from|to|run_id|reason_code)`.
  Merge is idempotent (rerun on identical input yields zero new
  events), stable-sorted per candidate on `(at_utc, event_id)`,
  with sorted top-level candidate_id keys. Writes via atomic
  tempfile+rename through `_sidecar_io`.
- **Candidate registry v2** (`research/candidate_registry_v2.py`).
  Additive first-class view alongside the frozen v1 sidecar.
  Entries carry `candidate_id`, `experiment_family`, `preset_origin`,
  strict separation of `processing_state` (v3.11) and
  `lifecycle_status` (v3.12), `legacy_verdict + mapping_reason`,
  `observed_reason_codes + taxonomy_rejection_codes +
  taxonomy_derivations`, `scores`, `paper_readiness_flags = null`
  with `paper_readiness_assessment_status =
  "reserved_for_future_phase"`, `deployment_eligibility =
  "reserved_for_future_phase"`, full `lineage_metadata`, and
  `source_artifact_references`. Schema pinned at `"2.0"`.
- **Advisory-only agent_definition bridge** (`research/execution_bridge/`).
  Single artifact (`research/agent_definitions_latest.v1.json`).
  Every entry carries `runnable=false` +
  `execution_scope="future_paper_phase_only"`; payload
  `runnable_entries` is pinned to 0 as a structural invariant.
  Scope-locked to `trend_equities_4h_baseline` and
  `regime_filter_equities_4h_experimental` presets with
  `lifecycle_status in {exploratory, candidate}`. AST test asserts
  no imports from `agent.execution`, `execution.paper`, `ccxt`,
  `yfinance`, `polymarket`, or `alchemy`.
- **Single candidate-sidecars façade** (`research/candidate_sidecars.py`).
  `build_and_write_all(ctx)` is the only new call-site in
  `run_research.py`, orchestrating registry-v2 → status-history →
  agent-definitions through the shared
  `_sidecar_io.write_sidecar_atomic` helper.
- **Canonical sidecar IO helper** (`research/_sidecar_io.py`).
  `sort_keys=True, indent=2, LF line endings, trailing newline,
  tempfile+rename`. Used by every v3.12 sidecar writer for uniform
  determinism and atomicity.
- **Report additive enrichment** (`research/report_agent.py`).
  `per_candidate_diagnostics[]` gains optional `lifecycle_status`,
  `legacy_verdict`, `observed_reason_codes`,
  `taxonomy_rejection_codes`, and `scores` fields pulled from the
  v2 sidecar. Top-level `lifecycle_breakdown` counter and optional
  "Candidate Lifecycle Breakdown (v3.12)" markdown section.
  Report `schema_version` unchanged ("1.1") — consumers read with
  `.get()`; no breaking change.
- **Read-only API endpoints** (`dashboard/dashboard.py`).
  `GET /api/registry/v2` and `GET /api/registry/status-history`
  follow the existing `/api/candidates/latest` auth + error pattern.
  Graceful `{ artifact_state: "missing" }` response when sidecars
  are absent.

### Preserved / frozen

- `research/research_latest.json` — 19-column schema, byte-identical.
- `research/strategy_matrix.csv` — column order, byte-identical.
- `research/candidate_registry_latest.v1.json` — structure + summary
  keys byte-identical (regression test
  `tests/regression/test_candidate_registry_v1_immutable.py` pins
  this).
- `research/run_meta_latest.v1.json` — v1.1 unchanged.
- `research/report_latest.{md,json}` — v1.1 schema_version unchanged.
- Frontend components — untouched. React Reports.tsx primitive
  filter already tolerates new nested v3.12 keys.

### Tests added (v3.12)

- `tests/unit/test_sidecar_io.py` — 12 tests, canonical serialization.
- `tests/unit/test_candidate_lifecycle.py` — 21 tests, graph +
  transitions + legacy mapping.
- `tests/unit/test_rejection_taxonomy.py` — 16 tests, observed vs
  derived split, no per-entry timestamps.
- `tests/unit/test_candidate_scoring.py` — 14 tests, deterministic
  unit signals + provisional composite.
- `tests/unit/test_candidate_status_history.py` — 16 tests,
  event_id determinism, idempotent merge, stable sort.
- `tests/unit/test_candidate_registry_v2.py` — 14 tests.
- `tests/unit/test_agent_definition_bridge.py` — 13 tests incl.
  AST-based import isolation.
- `tests/unit/test_candidate_sidecars_facade.py` — 7 tests.
- `tests/unit/test_report_agent_v312_enrichment.py` — 7 tests.
- `tests/unit/test_dashboard_api_v312.py` — 7 tests.
- `tests/integration/test_v312_sidecars_e2e.py` — 5 end-to-end
  scenarios incl. rerun byte-identity.
- `tests/regression/test_candidate_registry_v1_immutable.py` — 6
  tests pinning v1 contract.
- `tests/regression/test_v312_sidecar_schema_stability.py` — 14
  tests pinning key sets and schema_version values for all three
  v3.12 artifacts.

### Explicitly out of scope (deferred)

- Execution preview with replay / fees / slippage / synthetic PnL
  → **v3.15 Paper Validation Engine**.
- Runnable paper path → **v3.15**.
- Regime classifier and gating → **v3.13 Regime Intelligence**.
- Portfolio / sleeves → **v3.14**.
- Kill switches, shadow mode, monitoring → **v3.16**.
- Controlled live enablement → **v3.17**.
- ML or optimizer-heavy scoring — permanently out of roadmap scope.
- Frontend component changes — deferred; additive report schema
  is enough for v3.12.
- `unstable_parameter_neighborhood` and `single_asset_dependency`
  taxonomy derivation — both remain `DEFERRED_TAXONOMY_CODES` in
  v3.12, scheduled for v3.13+ when breadth and neighborhood context
  become first-class.

## [v3.11] — Research Quality Engine

Date: 2026-04-22
Branch: `feature/v3.11-research-quality-engine`

Quality-hardening release. Zero new infra, zero new strategy
families, zero new metrics. Every change is additive and consumer-only
against the existing v3.10 artifact landscape. Public output contracts
(`research_latest.json`, `strategy_matrix.csv`) remain **byte-identical
to v3.10**; new data lands exclusively in schema-bumped adjacent
sidecars (`run_meta_latest.v1.json` v1.1, `report_latest.{md,json}`
v1.1) and a new consumer-only join module.

The bottleneck after v3.10 was input + interpretation quality, not
throughput. v3.11 formalises hypothesis metadata per preset, separates
screening (mild, observability) from promotion (strict, DSR/PSR/
stability) in report output, and wires per-candidate diagnostics that
explain **why** each row survived, stalled, or failed — without the
engine growing a single new threshold or metric.

### Added

- **Preset Quality Layer.** `ResearchPreset` dataclass extended with
  four fields:
  - `preset_class: Literal["baseline", "diagnostic", "experimental"]`
    — orthogonal to the existing `status` lifecycle label.
  - `rationale`, `expected_behavior`, `falsification` — structured
    hypothesis metadata. All three enabled presets
    (`trend_equities_4h_baseline`, `trend_regime_filtered_equities_4h`,
    `crypto_diagnostic_1h`) ship with the fields filled. Planned
    `pairs_equities_daily_baseline` stays empty (backlog_reason still
    load-bearing).
  - `hypothesis_metadata_issues()` helper returns only the v3.11
    soft-issue codes so the runner can emit dedicated warnings.
- **Soft preset validation + opt-in strict mode.** `validate_preset`
  returns soft issues on empty rationale / expected_behavior /
  falsification for enabled presets. The runner emits
  `preset_validation_warning` tracker events. Setting
  `QRE_STRICT_PRESET_VALIDATION=1` elevates to hard failure via a
  new `PresetValidationError`. Default is soft — v3.11 never
  self-blocks.
- **run_meta schema v1.1** (additive). New fields on
  `research/run_meta_latest.v1.json`: `preset_class`,
  `preset_rationale`, `preset_expected_behavior`, `preset_falsification`,
  `preset_bundle_hypotheses` (resolved read-only from `STRATEGIES`).
  `is_run_excluded_from_promotion` and all v1.0 keys are unchanged.
  v1.0-shaped sidecars remain readable bytewise.
- **`research/report_candidate_diagnostics.py`** (new module). Pure
  join functions — no IO, no new metrics, no threshold derivation.
  Returns `(per_candidate_diagnostics, join_stats)`.
  - Verdict enum pinned at four values:
    `promoted | needs_investigation | rejected_promotion | rejected_screening`.
  - Rejection_layer enum: `fit_prior | eligibility | screening |
    promotion | null`.
  - Stability flags (`noise_warning`, `psr_below_threshold`,
    `dsr_canonical_below_threshold`, `bootstrap_sharpe_ci_includes_zero`)
    sourced read-only from
    `candidate_registry.candidates[].reasoning.failed/.escalated/.passed`.
  - `cost_sensitivity_flag` and `regime_suspicion_flag` consume
    pre-computed booleans only; null when the source sidecar is
    absent or exposes only numeric fields.
  - Join discipline: primary key `build_strategy_id(name, asset,
    interval, params)`; defensibility triple `(name, asset, interval)`;
    unmatched counts surface in `join_stats`.
  - Soft warning sentinel `join_stats.warning = "large_candidate_count"`
    at > 1000 rows; no hard cap.
- **Report agent v1.1.** `research/report_agent.py`:
  - `REPORT_SCHEMA_VERSION = "1.1"`.
  - `summary` carries additive `screening` and `promotion` sub-dicts
    (legacy v3.10 keys preserved for dashboard consumers).
  - `top_rejection_reasons_by_layer` splits screening-layer codes
    (from `run_filter_summary_latest.v1.json`) and promotion-layer
    codes (from `candidate_registry_latest.v1.json`). Flat
    `top_rejection_reasons` list remains for legacy consumers.
  - `per_candidate_diagnostics` and `join_stats` payload keys.
  - Markdown sections: **Hypothese**, **Samenvatting** (with
    Screening-laag + Promotion-laag + Join stats sub-blocks), **Wat
    werkte**, **Wat werkte niet** (split), **Waarom (per candidate)**,
    **Volgende stap**.
  - `suggest_next_experiment` extended with layer-aware + failure-type
    logic (statistical / risk / trades / noise) driven by existing
    promotion-reason codes only. Signature adds keyword-only
    `rejection_reasons_by_layer` (backwards compatible).
- **Test coverage.** 43 new unit tests pinning the v3.11 contract:
  - `tests/unit/test_presets.py` +9 tests.
  - `tests/unit/test_run_meta.py` +6 tests.
  - `tests/unit/test_report_agent.py` +8 tests.
  - `tests/unit/test_report_candidate_diagnostics.py` (new) 20 tests
    covering verdict mapping, stability flag sourcing, cost/regime
    flag null-safety, join mismatches, malformed rows, soft warning.

### Changed

- `render_markdown` section titles updated from v3.10 English labels
  to v3.11 Dutch narrative labels (Samenvatting / Wat werkte / Wat
  werkte niet / Waarom / Volgende stap). Corresponding test assertions
  updated in the same commit as the rename.
- `build_run_meta_payload` now resolves `preset_bundle_hypotheses`
  via a read-only local import of `STRATEGIES`; avoids a module-level
  circular import with the registry.

### Preserved bytewise

- `ROW_SCHEMA` (19 columns) and `JSON_TOP_LEVEL_SCHEMA`.
- `candidate_registry_latest.v1.json` schema + writer.
- All other sidecar schemas and writers (statistical defensibility,
  regime diagnostics, falsification gates, integrity report,
  portfolio aggregation, empty run diagnostics).
- Tier 1 digest pins, walk-forward `FoldLeakageError` semantics,
  resume-integrity gate.
- `run_meta` v1.0-shaped sidecars still parse via
  `read_run_meta_sidecar`.

### Deferred (explicit)

- Portfolio layer (v3.12).
- Candidate registry schema extensions (v3.12).
- Regime classification engine (v3.13).
- Paper trading, new strategy families, ML/ranking, UI expansion
  beyond the preset-card additive fields.
- Hard-fail default for preset validation (remains opt-in via env
  flag in v3.11).

### Known risks

- Dashboard report-viewer must tolerate the new v1.1 schema fields;
  they are additive and null-safe but any tight JSON-Schema consumer
  will need an update.
- `cost_sensitivity_flag` and `regime_suspicion_flag` stay `null` in
  the current pipeline because no upstream sidecar writer emits a
  pre-computed boolean. They go live the moment the writers choose
  to expose one — no v3.11 code change needed.
- Falsification criteria quality is subjective on the initial fill
  of the 3 enabled presets. Iteration happens via runs + feedback
  loop, not via engine changes.
- Per-candidate diagnostics can grow with universe size; the soft
  warning at >1000 rows is a visibility aid, not a guard. Retention
  discipline arrives with v3.12's candidate registry.

## [v3.10] — Research Ops & Frontend Migration

Date: 2026-04-22
Branch: `feature/v3.10-research-ops-react`

Operations release. Preset catalog, single-command `researchctl`
CLI, post-run analysis/report agent, Flask control-surface API
extension, React + TypeScript SPA on `:8050`, nginx anti-indexing
reverse proxy, host-level systemd-timer for the daily default run,
and explicit `scripts/deploy.sh` deploy channel from GHCR to the
VPS. No strategy-logic changes. Public output contracts
(`research_latest.json`, `strategy_matrix.csv`) are byte-identical
to pre-v3.10; new fields land in adjacent artifacts
(`research/run_meta_latest.v1.json`, `research/report_latest.md`,
`research/report_latest.json`). See
[ADR-011](docs/adr/ADR-011-v3.10-architecture.md) for the full
design record and
[ADR-012](docs/adr/ADR-012-v3.10-approval-override-audit.md) for
the engine approval-override audit outcome.

### Added

- `research/presets.py`: frozen `ResearchPreset` dataclass + four
  registered presets (`trend_equities_4h_baseline` default,
  `pairs_equities_daily_baseline` planned/disabled,
  `trend_regime_filtered_equities_4h`, `crypto_diagnostic_1h` with
  diagnostic/exclusion flags). Public API: `list_presets`,
  `get_preset`, `resolve_preset_bundle`, `validate_preset`,
  `default_daily_preset`, `daily_schedulable_presets`, `preset_to_card`.
- `research/run_meta.py`: new adjacent sidecar
  `research/run_meta_latest.v1.json` (schema v1.0) carrying preset
  metadata, candidate summary, top rejection reasons, and artifact
  paths. Safe-default promotion-exclusion when the sidecar is missing
  or diagnostic (ADR-011 §9).
- `research/report_agent.py`: post-run analysis that composes
  `research/report_latest.md` + `research/report_latest.json` from
  the existing reporting modules. Verdicts:
  `promoted | candidates_no_promotion | niets_bruikbaars_vandaag`.
- `research/run_research.py --preset <name>`: threads a preset through
  candidate planning, writes the run_meta sidecar, and invokes the
  report agent at the end of each run (best-effort, never fails the run).
- `researchctl.py` CLI at the repo root with subcommands
  `run / report / history / doctor` (no `deploy` — ADR-011 §4).
- Dashboard endpoints: `/api/presets`, `/api/presets/<name>/run`,
  `/api/report/latest`, `/api/report/history`, `/api/candidates/latest`,
  `/api/health`, `/api/session/login`, `/api/session/logout`.
- React + TypeScript SPA under `frontend/` with Login, Dashboard,
  Presets, History, Reports, Candidate Inspector screens. Multi-stage
  Dockerfile builds the bundle on `node:20-alpine` and ships it in the
  Python runtime image.
- `ops/nginx/nginx.conf` + `robots.txt`: reverse proxy with
  `X-Robots-Tag: noindex, nofollow, noarchive, nosnippet`, AI/crawler
  UA block (20+ agents → 403), cookie/auth pass-through to Flask.
- `ops/systemd/trading-agent-daily-research.{service,timer}` + README:
  host-level systemd-timer that calls
  `docker exec jvr_dashboard python /app/researchctl.py run
  trend_equities_4h_baseline` at 06:00 UTC daily. Crypto diagnostic
  preset is never auto-scheduled.
- `scripts/deploy.sh`: explicit GHCR pull + compose up + health-check
  deploy with retry, rollback via `IMAGE_TAG=<prev-tag>`.
- `docker-compose.prod.yml`: GHCR-image override for VPS deploys.
- `docs/adr/ADR-011-v3.10-architecture.md`: architecture record for the
  whole v3.10 shape.
- `docs/adr/ADR-012-v3.10-approval-override-audit.md`: audit of
  engine.py / promotion.py / run_research.py for gate-bypass logic —
  outcome A, no production bypass exists.
- Regression / smoke coverage: `test_make_result_row_strategy_name.py`,
  `test_execution_event_roundtrip.py`,
  `test_screening_interrupt_reason_detail.py`,
  `test_daily_preset_smoke.py`, `test_presets.py`,
  `test_run_meta.py`, `test_report_agent.py`,
  `test_dashboard_api_v310.py`.

### Changed

- `VERSION`: `0.1.0` → `3.10.0`.
- `Dockerfile` is now multi-stage (node builder → python runtime copies
  `frontend/dist`).
- `docker-compose.yml`: dashboard no longer binds the host port; nginx
  binds `8050:80` and proxies to `dashboard:8050` internally. New
  `./state:/app/state` bind-mount preserves session/operator secrets
  across deploys.
- `dashboard/dashboard.py`: SPA index served at `/`; legacy Jinja
  dashboards kept reachable at `/legacy/dashboard` and
  `/legacy/research-control` for one release.
- `dashboard/research_runner.launch_research_run` accepts an optional
  `preset` kwarg and threads `--preset <name>` into the subprocess
  command.

### Fixed

- `research/results.py::make_result_row` now raises `ValueError` when
  `strategy["name"]` is None or empty, closing the strategy-None leak
  in `strategy_matrix.csv` / `research_latest.json`. The frozen
  ROW_SCHEMA tuple is untouched — only a precondition was added.
- `researchctl doctor` detects stale `strategy_matrix.csv` headers
  (the v3.x legacy `strategy_family,asset_type,…` header class) and
  fails the check instead of letting it slide.

### Security

- Anti-indexing enforced at three layers: nginx `X-Robots-Tag`
  response header + AI-crawler UA 403 block, Flask `X-Robots-Tag`
  injection on the SPA index, and React `<meta name="robots">` tag.
  `/robots.txt` served by both nginx and Flask.
- New `/api/session/login` validates via the existing SHA256+SALT hash
  and `hmac.compare_digest`; no new credential store. Session cookie
  `SameSite=Lax` (no TLS in v3.10, `Secure` flag deferred to v3.11).

### Contracts

- No mutations to `ROW_SCHEMA`, `JSON_TOP_LEVEL_SCHEMA`, or
  `JSON_SUMMARY_SCHEMA` in `research/results.py`. All new v3.10
  fields are recorded in adjacent sidecar artifacts
  (`research/run_meta_latest.v1.json`, `research/report_latest.md`,
  `research/report_latest.json`).
- Existing `/api/research/run-status` remains the canonical run-status
  endpoint (ADR-011 §12). No `/api/run-status` introduced.

## [v3.8] — Execution Realism & Evaluation Hardening

Date: 2026-04-21
Branch: `feature/v3.7-fitted-feature-abstraction`

Evaluation-hardening phase. Additive abstractions and opt-in
evaluation hooks only. No change to strategy logic, feature logic,
fitted-feature semantics, baseline equity / trade booking, public
JSON / CSV schemas, `candidate_id` hashing, or Tier 1 bytewise
pins. See
[ADR-008](docs/adr/ADR-008-execution-realism-and-evaluation-hardening.md)
for the full design record, rejected alternatives, pinned
semantics, and deferred items.

### Added

- `agent/backtesting/execution.py` (v3.8 step 1). Canonical
  execution event scaffold. `EXECUTION_EVENT_VERSION = "1.0"`,
  frozen `ExecutionEvent` with five pinned kinds (`accepted`,
  `partial_fill`, `full_fill`, `rejected`, `canceled`), typed
  `ALLOWED_REASON_CODES`, factory builders (`.accepted`,
  `.full_fill`, `.partial_fill`, `.rejected`, `.canceled`),
  pandas / numpy sentinel rejection, dict round-trip helpers
  (`execution_event_to_dict`, `execution_event_from_dict`),
  structural `fingerprint` placeholder (unset in v1.0).
  Deliberately disjoint from `execution/protocols.py::Fill`
  (live / paper-broker success record).
- `agent/backtesting/engine.py::_simuleer_detailed` (v3.8 step 2).
  Deterministic emission of `ExecutionEvent.accepted` +
  `ExecutionEvent.full_fill` pairs at each booked entry and exit.
  Monotone `sequence` within `(run_id, asset, fold_index)`; every
  event carries `fold_index`. Gated behind
  `include_execution_events` keyword flag; enabled only on OOS
  folds. Events land in
  `_last_window_streams["oos_execution_events"]` and surface on
  the research result dict as `evaluation_streams`. Baseline
  equity math, fee application, and trade PnL bytewise unchanged.
- `agent/backtesting/cost_sensitivity.py` (v3.8 step 3).
  `COST_SENSITIVITY_VERSION = "1.0"`, frozen `ScenarioSpec`,
  `DEFAULT_SCENARIOS`, `run_cost_sensitivity`,
  `derive_fill_positions`, `build_cost_sensitivity_report`. Pure
  evaluation-layer replay applying per-fill multiplicative
  adjustment `(1 - m*k) * (1 - s_bps/1e4) / (1 - k)`. Baseline
  scenario reproduces the engine's `dag_returns` bytewise;
  alternative scenarios apply stress without mutating the
  baseline. Opt-in hook `BacktestEngine.build_cost_sensitivity`
  (not called from `run()`).
- `agent/backtesting/exit_diagnostics.py` (v3.8 step 4).
  `EXIT_DIAGNOSTICS_VERSION = "1.0"`, frozen `TradeDiagnostic`,
  `compute_trade_diagnostic`, `extract_interior_bar_returns`,
  `build_exit_diagnostics_report`. Pure evaluation-layer path
  analysis consuming `oos_trade_events` + `oos_bar_returns` +
  `kosten_per_kant`. Pinned per-trade definitions: MFE, MAE,
  realized return, capture ratio (with `None` on zero MFE),
  winner giveback (with `None` on losers), exit lag, holding
  bars. Pinned aggregate: turnover-adjusted exit quality
  (`avg_capture * (1 - density)`, zero on zero-trade). Exit-bar
  pollution by `(1 - k)` fee factor is handled by anchoring the
  exit path point at `pnl + k`. Opt-in hook
  `BacktestEngine.build_exit_diagnostics` (not called from
  `run()`).
- `tests/unit/test_execution_event_scaffold.py` (v3.8 step 1,
  ~23 tests).
- `tests/unit/test_execution_event_emission.py` (v3.8 step 2).
- `tests/unit/test_cost_sensitivity.py` (v3.8 step 3, 30 tests).
- `tests/unit/test_exit_diagnostics.py` (v3.8 step 4, 26 tests).
- `docs/adr/ADR-008-execution-realism-and-evaluation-hardening.md`
  (v3.8 step 5).
- `docs/orchestrator_brief.md` §Addendum: v3.8 scope, layer
  placement, execution-event / cost-sensitivity / exit-quality
  semantics, deferred items, preserved bytewise invariants, phase
  character.

### Unchanged — explicitly pinned

- `research_latest.json` row schema and top-level schema
  (bytewise).
- 19-column CSV row schema (bytewise).
- Integrity (`integrity_report_latest.v1.json`) and falsification
  (`falsification_gates_latest.v1.json`) sidecar schemas.
- Integrity D4 boundary.
- Tier 1 bytewise digests (`sma_crossover`,
  `zscore_mean_reversion`, `pairs_zscore`).
- Walk-forward `FoldLeakageError` semantics.
- Resume-integrity gate.
- `candidate_id` hashing inputs (`research/candidate_pipeline.py
  ::_hash_payload`). Execution shape is explicitly out of the
  hash.
- `FEATURE_REGISTRY`, `FEATURE_VERSION = "1.0"`,
  `build_features_for`, `build_features_for_multi`.
- `FITTED_FEATURE_REGISTRY`, `FITTED_FEATURE_VERSION = "1.0"`,
  fold-aware builders.
- Strategy logic (`strategies.py`, `thin_strategy.py`).
- Baseline equity math, fee application, trade PnL formula in
  `_simuleer_detailed`.
- Live / paper broker path (`execution/protocols.py`,
  `execution/paper/polymarket_sim.py`).

### Deferred

- Paper validation as a formal gate.
- Live / paper divergence reporting between live `Fill` outcomes
  and backtest `ExecutionEvent` projections.
- Full execution shortfall framework (quote midpoint, bid/ask,
  impact curves). Current backtest slippage is `0.0 bps`
  (next-bar close).
- Richer rejection / partial-fill semantics in the engine. The
  scaffold exists; current emission is entry + exit fills only.
- Broader promotion framework integration of cost-sensitivity and
  exit-quality reports. Both remain opt-in side-channels and are
  not gates in v3.8.
- Regime / portfolio research.
- Broader orchestration / platform automation.
- Thin contract v2.0 unification. See
  [ADR-006](docs/adr/ADR-006-v2-contract-deferred.md). v3.8 does
  not introduce new ADR-006 triggers and does not resolve any of
  its conditions.
- Broader strategy migration to the fitted path (ADR-007). v3.8
  neither widens nor narrows the v3.7 opt-in surface.
- `ExecutionEvent.fingerprint` computation. v1.0 reserves the
  field as a structural placeholder.
- Config-level surfacing of `build_cost_sensitivity` and
  `build_exit_diagnostics` on the research pipeline. Both remain
  callable on `BacktestEngine` instances only.

### Phase character

v3.8 is an evaluation-hardening phase, not a strategy-expansion
phase. Every change is additive, deterministic, non-mutating with
respect to baseline results, and gated behind opt-in hooks or
flags that default off. Tier 1 digests, public artifacts, and
promotion inputs are pinned at their v3.7 values.

## [v3.7] — Fitted Feature Abstraction

Date: 2026-04-21
Branch: `feature/v3.7-fitted-feature-abstraction`

### Added

- `agent/backtesting/fitted_features.py`: parallel feature
  abstraction for features that require a fit/transform lifecycle.
  `FittedFeatureSpec`, `FittedParams` (frozen dataclass with
  `MappingProxyType` values, deep-copy + `flags.writeable=False` on
  arrays, pandas-sentinel rejection, hard caps on entries / array
  elements / sequence length), `FITTED_FEATURE_REGISTRY`,
  `validate_fitted_params`, `FITTED_FEATURE_VERSION = "1.0"`.
  Registered entries: `hedge_ratio_ols` (OLS beta on close vs
  close_ref, ddof=0) and `spread_zscore_ols` (shares the OLS fit
  via a private helper; transform returns
  `zscore(spread(close, close_ref, beta), lookback)`).
- `agent/backtesting/thin_strategy.py`:
  `FeatureRequirement.feature_kind: Literal["plain", "fitted"]`
  (default `"plain"`, byte-identical to v3.6). Fold-aware builders
  `build_features_train`, `build_features_test`,
  `build_features_train_multi`, `build_features_test_multi`. The
  single-frame `build_features_for` and multi-frame
  `build_features_for_multi` paths are unchanged and remain the
  owners of the v3.5 / v3.6 bytewise pins.
- `agent/backtesting/engine.py`:
  `BacktestEngine._evaluate_windows` materializes each fold's
  training slice (and `train_reference_frame` when multi-asset)
  and forwards them through `_simuleer_detailed → _invoke_strategy`.
  New `_resolve_fitted_features` helper routes fitted requirements
  through the train/test helpers; loud-fails when `train_frame` /
  `train_reference_frame` is missing. Non-fitted strategies ignore
  the new kwargs.
- `agent/backtesting/strategies.py::pairs_zscore_strategie`:
  explicit `use_fitted_hedge_ratio: bool = False` opt-in. Default
  emits the v3.6 `spread_zscore` requirement byte-identically;
  `True` swaps to `spread_zscore_ols` (fitted).
- `tests/unit/test_fitted_features.py` (33 tests — v3.7 step 1),
  `tests/unit/test_fitted_hedge_ratio_ols.py` (v3.7 step 2),
  `tests/unit/test_feature_kind_discriminator.py` and
  `tests/unit/test_fold_aware_builders.py` (v3.7 step 3),
  `tests/unit/test_fitted_pairs_engine.py` (19 tests — v3.7 step 4).
- `docs/adr/ADR-007-fitted-feature-abstraction.md`.
- `docs/orchestrator_brief.md` §Addendum: v3.7 fitted feature
  scope, layer placement, walk-forward semantics, param safety,
  pairs strategy behavior, explicit deferrals, roadmap relationship,
  thin contract maturity statement.

### Unchanged — explicitly pinned

- `research_latest.json` row schema and top-level schema (bytewise).
- 19-column CSV row schema (bytewise).
- Integrity (`integrity_report_latest.v1.json`) and falsification
  (`falsification_gates_latest.v1.json`) sidecar schemas.
- Integrity D4 boundary.
- Tier 1 bytewise digests (`sma_crossover`,
  `zscore_mean_reversion`, `pairs_zscore`). Pairs digest continues
  to resolve through the v3.6 multi-asset engine path with
  `use_fitted_hedge_ratio=False` (the default).
- Walk-forward `FoldLeakageError` semantics.
- Resume-integrity gate.
- `FEATURE_REGISTRY`, `FEATURE_VERSION = "1.0"`,
  `build_features_for`, `build_features_for_multi` — the plain
  feature path is unchanged.

### Deferred

- Thin contract v2.0 (`func(features)` purity). v3.7 introduces
  one of the ADR-006 triggers (fit/transform abstraction) but does
  not migrate any strategy. See
  [ADR-006](docs/adr/ADR-006-v2-contract-deferred.md) and
  [ADR-007](docs/adr/ADR-007-fitted-feature-abstraction.md).
- Broader strategy migration to the fitted path. Only
  `pairs_zscore` gains an opt-in flag; SMA crossover and z-score
  mean reversion are plain-only.
- Generalized lineage / persistence for fitted params. The
  `FittedParams.fingerprint` placeholder reserves the surface;
  computation and persistence are future work.
- Rolling / time-varying fitted parameters. v3.7 is static fit per
  fold.
- Config-level exposure of the fitted path at the research
  pipeline. Opt-in lives at the strategy factory call site today.
- Evaluation hardening, exit diagnostics, regime / portfolio work.
- Promotion of `use_fitted_hedge_ratio=True` to the pairs default —
  requires evidence and would drift the Tier 1 bytewise pin; a
  separate single-purpose change.

### Thin contract maturity

- v1.0 is production for all Tier 1 strategies, including pairs.
- v2.0 is still deferred (ADR-006). v3.7 introduces one of its
  triggers without performing the migration.
- Fitted feature abstraction is production for opt-in callers.

## [v3.6] — Multi-Asset Loader & Feature-Purity Progression

Date: 2026-04-21
Branch: `feature/v3.6-multi-asset-loader-and-feature-purity`

### Added

- `agent/backtesting/multi_asset_loader.py`: `load_aligned_pair`,
  `AlignedPairFrame`, typed errors
  (`EmptyIntersectionError`, `MixedAssetClassError`,
  `LegUnavailableError`). Inner-join alignment with truncation
  idempotence as the fold-safety invariant.
- `agent/backtesting/thin_strategy.py`:
  `FeatureRequirement.source_role` (default `None`, byte-identical to
  v3.5) and `build_features_for_multi(requirements, frames)`. The
  single-frame `build_features_for` path is unchanged.
- `agent/backtesting/engine.py`: optional
  `AssetContext.reference_frame`, `_invoke_strategy` multi-asset
  routing, keyword-only `grid_search(reference_asset=...)`.
- `research/candidate_pipeline.py`: `reference_asset` plumbing from
  registry → candidate metadata → engine. Included in
  `candidate_id` hashing **only when non-None** so SMA / z-score
  hashes stay byte-identical to v3.5.
- `research/registry.py`: `pairs_zscore.enabled = True` with
  `reference_asset = "ETH-EUR"` alongside `asset = "BTC-EUR"`.
- `tests/unit/test_aligned_pair_loader.py` (10 tests),
  `tests/integration/test_pairs_end_to_end.py` (9 tests),
  `tests/unit/test_multi_asset_feature_resolution.py` (10 tests),
  `tests/regression/test_multi_asset_feature_parity.py` (3 tests),
  `tests/regression/test_tier1_bytewise_pin.py::
  test_pairs_bytewise_pin_through_multi_asset_engine`,
  `tests/unit/test_walk_forward_framework.py::
  test_multi_asset_fold_slices_match_direct_alignment_per_fold`.
- `docs/adr/ADR-006-v2-contract-deferred.md`.
- `docs/orchestrator_brief.md` §Addendum: v3.6 multi-asset scope,
  loader contract, feature contract extension, engine routing,
  candidate pipeline plumbing, public output contract invariant,
  thin contract maturity statement.
- `CHANGELOG.md` (this file).

### Unchanged — explicitly pinned

- `research_latest.json` row schema and top-level schema (bytewise).
- 19-column CSV row schema (bytewise).
- Integrity (`integrity_report_latest.v1.json`) and falsification
  (`falsification_gates_latest.v1.json`) sidecar schemas.
- Integrity D4 boundary — no `status` field added to sidecars.
- Public `asset` column semantics — single symbol string, never
  concatenated, never reinterpreted. `reference_asset` lives only on
  internal surfaces.
- Tier 1 bytewise digests (`sma_crossover`,
  `zscore_mean_reversion`, `pairs_zscore`) — including pairs, whose
  digest through the multi-asset engine path equals the single-frame
  v3.5 pin exactly.
- Walk-forward `FoldLeakageError` semantics.
- Resume-integrity gate.

### Deferred

- Static / full-series OLS hedge ratio — requires fit/transform
  abstraction; tracked for v3.7
  (`feature/v3.7-fitted-feature-abstraction`).
- N > 2 multi-asset (triplets, portfolios).
- Mixed asset-class pairs (crypto × equity).
- Intraday multi-asset alignment (DST / session boundary policy).
- Thin contract v2.0 (`func(features)` purity). See
  `docs/adr/ADR-006-v2-contract-deferred.md` for trigger conditions
  and migration approach.
- Generalized pair-selection: pair universe, cointegration
  discovery, dynamic pair rotation.

### Thin contract maturity

v1.0 is production for all Tier 1 strategies, including pairs.
v2.0 is deferred to v3.7+ pending a concrete triggering use case.

## [v3.5] — Canonical Feature Primitives & Thin Strategy Contract v1.0

Date: earlier in 2026, pre-v3.6.
Branch: merged to `main` at `72e70aa`.

- Canonical feature primitives and registry.
- Thin strategy contract v1.0 (`func(df, features)`) with AST-level
  body enforcement (strategies may read `df.index` only).
- Engine-side thin routing through `build_features_for`.
- Integrity / falsification sidecars with typed reason codes and the
  D4 boundary invariant.
- Artifact-integrity resume gate.
- Tier 1 bytewise pins for `sma_crossover` and
  `zscore_mean_reversion`. Pairs scaffolded under the thin contract
  but registry-disabled pending multi-asset support (landed in v3.6).
