# Intelligent Routing Observation Workflow — Operator Runbook

> Workflow: `.github/workflows/observe-intelligent-routing.yml`
> Modules:  `reporting/intelligent_routing.py`,
>           `reporting/intelligent_routing_status.py`
> Release:  v3.15.16 (advisory) + v3.15.16.1 (dead-zone coarse-lookup
>           annotation)
> Companion: [`scripts/deploy_vps_dashboard.sh`](../../scripts/deploy_vps_dashboard.sh) (sibling deploy posture, mirrored secrets/SSH pattern)

## v3.15.16.1 — dead-zone coarse-lookup annotation only

The first real-input observations of the v3.15.16 advisory artifact
showed `dead_zone_status: "unknown"` for every campaign. Root cause:
the upstream `dead_zones_latest.v1.json` artifact currently keys
zones on `(asset, "unknown", family)` (per
[`research/dead_zone_detection.py:21-24`](../../research/dead_zone_detection.py:21):
*"Timeframe is currently 'unknown' for every zone because the
upstream ledger event does not carry interval. v4 will enrich
ledger events with timeframe."*). The routing layer's coordinates
now carry real timeframes (`4h` / `1h` / `1d` etc.), so the exact
key never matches.

**v3.15.16.1 adds a coarse-lookup observability annotation only.**

* If the artifact has an exact `(asset_class, timeframe, family)`
  key, that wins → `dead_zone_lookup_precision = "exact_timeframe_match"`.
  Existing advisory dead-zone behaviour applies (a `dead` exact
  match may set `advisory_suppression_reason = "dead_zone"`).
* If the artifact has only `(asset_class, "unknown", family)`,
  the coarse fallback fires → `dead_zone_lookup_precision =
  "coarse_unknown_timeframe_match"`. The decision row carries the
  upstream `dead_zone_status` for operator visibility, **but**:
  - It MUST NOT set `advisory_suppression_reason`.
  - It MUST NOT alter `advisory_priority_score`.
  - It MUST NOT alter `advisory_rank`.
  - It MUST NOT be classified as exact timeframe-aware evidence.
* If neither key is present →
  `dead_zone_lookup_precision = "no_match"`,
  `dead_zone_status = "unknown"`, no suppression / priority /
  rank effect.

These invariants are pinned by 14 dedicated tests in
[`tests/unit/test_intelligent_routing_dead_zone_coarse_lookup.py`](../../tests/unit/test_intelligent_routing_dead_zone_coarse_lookup.py)
plus updates to `test_intelligent_routing_advisory_suppression.py`
and `test_intelligent_routing_pure.py`. No test was weakened,
skipped, deleted, or marked `xfail`.

## Current upstream-signal limits (operator-facing summary)

These three limits sit upstream of the routing layer; the routing
layer surfaces them honestly but does **not** infer them away.

1. **Dead-zone artifact carries `timeframe="unknown"` for every zone
   today.** v3.15.16.1 reads them via the coarse fallback (above)
   so operators can see them at all. The canonical fix is the
   upstream v4 ledger enrichment named in
   [`research/dead_zone_detection.py:21-24`](../../research/dead_zone_detection.py:21).
   That work is in `research/**`, which is no-touch for the
   reporting layer; addressing it requires a separate
   research-side product task.

2. **Information-gain artifact is single-campaign.** The producer
   in [`research/information_gain.py`](../../research/information_gain.py)
   emits one `col_campaign_id` per file (the most recent
   meaningful campaign). The routing layer's IG lookup is sparse
   by construction: most campaigns will have `info_gain_score = 0
   / bucket = "none"`. A multi-campaign IG roll-up via the
   evidence ledger reader is **deferred to a separate, operator-
   reviewed task** with a tight event-type allowlist; no scoping
   nor implementation in this v3.15.16.1 phase.

3. **`strategy_family` partial population.** Per
   [`research/campaign_launcher.py:240-251`](../../research/campaign_launcher.py:240),
   `strategy_family` is populated only when a preset has
   `hypothesis_id` AND that hypothesis exists in the catalog.
   Records whose preset lacks a `hypothesis_id` (or references a
   missing one) carry `strategy_family: null`, surfaced as
   `family: "unknown"` in the routing artifact. The fix is
   producer-side (in `research/presets.py` or
   `research/strategy_hypothesis_catalog.py`) and is therefore not
   addressable from the routing layer.

## Queue integration remains deferred

`queue_ordering_effect: "none"` and `routing_effect: "advisory_only"`
are unchanged in v3.15.16.1. Queue integration MUST NOT be
considered until **all** of the following are met:

- Per-campaign IG history is reliable across substantially more
  than `1/N` campaigns (today's observed sparsity).
- Dead-zone matching uses an exact, timeframe-aware key path
  (i.e. the upstream v4 ledger enrichment has landed; coarse
  matches alone are not sufficient).
- `strategy_family` is populated for the strong majority of
  active campaigns.
- Behavior coordinates have meaningful diversity in the active
  queue (today: 3 unique triples across 25 campaigns →
  `orthogonality_bucket: "saturated"` for every row).
- Top-ranked rows are explainable on signal beyond a single
  campaign's IG.

v3.15.17 Sampling Intelligence remains deferred until the same
upstream-signal readiness gate clears (see Roadmap v6 lines
297-340; *"low-information-region suppression"* and *"signal-
density-aware sampling"* depend on per-campaign IG, *"stratified
sampling"* depends on coordinate diversity, *"lower dead-zone
compute burn"* depends on an exact dead-zone match path).

This is the operator-facing runbook for the v3.15.16 advisory
Intelligent Routing **observation** workflow. It is the only governed
path that runs `python -m reporting.intelligent_routing --write` (and
its `_status` sibling) on the VPS where the upstream research
artifacts live, then uploads the resulting JSON files as a workflow
artifact for inspection.

The workflow is **observation-only**. It never alters the trading
agent, never restarts the dashboard, never deploys anything, and
never touches research/** beyond the two log files written by the
already-merged advisory CLIs.

## Core design principle

> The advisory Intelligent Routing artifact is observed against real
> input only via a parameter-free, fixed-allowlist `workflow_dispatch`
> entry point. Frozen contracts are sha256-pinned before AND after
> every run. Any drift fails the job.
>
> The CLIs the workflow runs were merged in PRs [#117–#120](https://github.com/roudjy/trading-agent/pulls?q=v3.15.16+is%3Amerged) and
> already carry their own no-write / `--write` invariants pinned by
> 136 tests in the v3.15.16 suite.

## TL;DR

```sh
# Trigger the observation from your local shell:
gh workflow run observe-intelligent-routing.yml --ref main

# Watch:
gh run list --workflow=observe-intelligent-routing.yml --limit 1
gh run watch <run-id>

# Download the artifact (zip with both JSONs + remote_stdout.txt):
gh run download <run-id> \
    --name v3-15-16-intelligent-routing-observation \
    -D ./observation-out
```

## What the workflow runs on the VPS

A single fixed bash script delivered via SSH. The script accepts no
arguments. The workflow has no inputs. The remote command list is:

```sh
cd /root/trading-agent
git fetch origin main
git reset --hard origin/main

# pre-snapshot frozen contracts (research_latest.json, strategy_matrix.csv)
# (sha256, printed to stdout under FROZEN_BEFORE_BEGIN/_END markers)

python3 -m reporting.intelligent_routing --write
python3 -m reporting.intelligent_routing_status --write

# post-snapshot frozen contracts → must equal pre-snapshot
# (printed under FROZEN_AFTER_BEGIN/_END)

# git diff --quiet HEAD must succeed (no tracked-file mutation)
# git status --short must list ONLY untracked entries under
# logs/intelligent_routing/ or logs/intelligent_routing_status/

# Stream both artifact files back via stdout (ARTIFACT_BEGIN/_END
# markers) so the runner can re-write them and upload as a workflow
# artifact.
```

Anything else is forbidden. The workflow is rejected by review if it
ever invokes campaign launchers, research generation, `run_research`,
docker compose, the deploy script, broker / live / paper / shadow /
trading / risk / execution code, dashboard or nginx restart, or any
arbitrary command from a workflow input.

## Hard guarantees (enforced by code AND review)

| guarantee | enforcement |
|---|---|
| `workflow_dispatch` only — no push / pull_request / schedule | source-text review of the `on:` block |
| Zero workflow inputs — no operator-supplied tokens / branches / paths / commands | source-text review of the `workflow_dispatch:` block |
| Remote script is a quoted heredoc — no shell expansion on the runner | `<<'REMOTE_EOF'` (single-quoted terminator) |
| `python3 -m` only — no `bash -c`, no `eval`, no `os.system`, no `subprocess.run` from input | source-text review |
| Frozen-contract drift detection (`research_latest.json`, `strategy_matrix.csv`) | sha256 captured before AND after the CLI; mismatch raises `SystemExit` on the runner |
| Tracked-file mutation detection | `git diff --quiet HEAD` after CLI; non-zero fails job |
| Untracked-path allowlist | `git status --short` filtered to `logs/intelligent_routing(/|_status/)` only; anything else fails job |
| SHA-pinned third-party actions | `actions/checkout@b4ffde65…` and `actions/upload-artifact@65462800…` (verified by `scripts/governance_lint.py`) |
| Secrets never echoed | `${{ secrets.* }}` only; `set -x` not used; `ssh-keyscan` stderr is silenced |
| Ephemeral SSH key | written with chmod 600 via `umask 077`; wiped in an `if: always()` step |
| Idempotent | re-running the workflow re-runs the CLIs; the only mutation is to the two `logs/` files, which are gitignored on the VPS too |

## Trigger frequency

Manual only. Use it when you want to take a fresh observation snapshot
of the advisory artifact against real input. There is no schedule and
no automatic trigger.

Two consecutive runs against an unchanged upstream input set should
produce the two artifact JSONs byte-identical modulo `generated_at_utc`
(stability invariant pinned by the v3.15.16 unit tests).

## Failure modes

| Symptom | Likely cause |
|---|---|
| Job fails at "Configure SSH client" with `missing one or more required secrets` | One of `VPS_HOST`, `VPS_USER`, `VPS_SSH_KEY` is unset or empty in repo settings. |
| Job fails at "Run observation on VPS" with `FAIL: tracked files modified during observation` | A CLI write escaped its expected target path; investigate before re-running. **Do not** rerun until the cause is identified. |
| Job fails at "Run observation on VPS" with `FAIL: unexpected untracked files during observation` | Some file other than `logs/intelligent_routing[_status]/*` was created on the VPS during the run. **Do not** rerun until the cause is identified. |
| Job fails at "Verify frozen-contract drift on remote" with `FROZEN-CONTRACT DRIFT` | A frozen contract sha256 changed between the pre- and post-snapshots. **Critical.** Investigate immediately. |
| `python3` not found on the VPS | The CLIs are stdlib-only and require Python 3.11+. Ubuntu 24.04 ships 3.12 by default; if the VPS lacks `python3`, install before re-running. |

In every failure mode, the runner uploads `artifacts/remote_stdout.txt`
inside the workflow artifact — that's the canonical post-mortem
record.

## Where the artifact lands

Workflow artifact name: `v3-15-16-intelligent-routing-observation`
(retention 14 days). Contents:

```
artifacts/logs/intelligent_routing/latest.json
artifacts/logs/intelligent_routing/metadata_shape_diagnostic.json     # optional
artifacts/logs/intelligent_routing/ig_ledger_shape_diagnostic.json    # optional
artifacts/logs/intelligent_routing_status/latest.json
artifacts/remote_stdout.txt
```

The optional `metadata_shape_diagnostic.json` is a **sanitized**
preview of the shape of the upstream registry + queue artifacts. It
lists top-level keys, the value-type of `campaigns` (`dict` vs
`list`), the record count, and the **key sets** of the first three
records along with **scalar previews** (≤ 80 chars; no full payload;
no secrets). It is purely diagnostic — used to confirm what fields
the routing layer can safely index without inferring metadata from
`campaign_id`.

The optional `ig_ledger_shape_diagnostic.json` (v3.15.16.2.diag) is
a **sanitized** preview of the append-only
`research/campaign_evidence_ledger.jsonl` ledger. It exists to help
calibrate a future reporting-only multi-campaign Information Gain
ledger reader (proposed v3.15.16.2). The diagnostic emits **counts,
key sets, and bounded scalar values only** — never full event
bodies, never raw nested payloads, never secrets. Specifically:

* Ledger presence + size + line counts (`line_count`,
  `parsed_line_count`, `malformed_line_count`, `truncated`,
  `max_lines_scanned = 1_000_000`).
* Distributions over `event_type`, `meaningful_classification`,
  `outcome`, top-20 `reason_code`.
* Per-campaign histogram (`1`, `2`, `3-5`, `6-10`, `11+` event
  buckets) and unique campaign count.
* Timestamp diagnostics (oldest / newest `at_utc`,
  ascending-order check, missing/malformed `at_utc` counts).
* Field-shape probes: first-three event key-sets (names only),
  candidate `campaign_id`/`score`/`bucket`/`timestamp` field
  names seen.
* Mapping-evidence counts for the candidate signals named in the
  v3.15.16.2 plan (`paper_ready`, `exploratory_pass`,
  `completed_with_candidates`, `duplicate_detected`,
  `duplicate_spawn_rejected`, `campaign_failed`,
  `reason_code_present_non_none`,
  `any_score_like_scalar_field_present`).

The diagnostic JSON is **calibration evidence only**. It does NOT
encode a final reader contract. The eventual v3.15.16.2 reader's
event-type allowlist + score mapping must be operator-blessed in a
separate PR after reviewing this diagnostic.

The diagnostic step is parameter-free, stdlib-only, and consumes
the ledger read-only. The same pre/post sha256 frozen-contract pin
+ tracked-file-mutation check + untracked-delta allowlist that
gate the rest of the observation workflow continue to gate the
diagnostic. The diagnostic writes only to
`logs/intelligent_routing/ig_ledger_shape_diagnostic.json`.

The runtime artifact on the VPS itself is at
`/root/trading-agent/logs/intelligent_routing/latest.json` and
`/root/trading-agent/logs/intelligent_routing_status/latest.json`.
Both are gitignored (`logs/`). The workflow does not commit them.

## Authorization trail

The introduction of this workflow widened `.github/workflows/**`
beyond the existing seed (deploy + tests + nightly + docker-build).
The widening is scoped to **exactly** this single observation
workflow. The operator authorisation that produced this PR is
recorded in the originating session's chat transcript and in the PR
description that landed it. Any future addition to
`.github/workflows/**` requires a new operator authorisation in the
same form — this doc is not a blanket precedent.

## Relationship to v3.15.16 release framing

The artifact this workflow uploads carries the unchanged v3.15.16
release framing pinned by the merged code:

- `routing_effect = "advisory_only"`
- `queue_ordering_effect = "none"`

Observing the artifact against real input is the mandatory
prerequisite for any future queue-integration discussion. Until this
workflow has been run on a checkout where the four upstream inputs
(`research/campaign_queue_latest.v1.json`,
`research/campaign_registry_latest.v1.json`,
`research/campaigns/evidence/information_gain_latest.v1.json`,
`research/campaigns/evidence/dead_zones_latest.v1.json`) are
present, queue integration MUST NOT be proposed.
