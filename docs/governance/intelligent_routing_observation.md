# Intelligent Routing Observation Workflow — Operator Runbook

> Workflow: `.github/workflows/observe-intelligent-routing.yml`
> Modules:  `reporting/intelligent_routing.py`,
>           `reporting/intelligent_routing_status.py`
> Release:  v3.15.16 (advisory)
> Companion: [`scripts/deploy_vps_dashboard.sh`](../../scripts/deploy_vps_dashboard.sh) (sibling deploy posture, mirrored secrets/SSH pattern)

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
artifacts/logs/intelligent_routing_status/latest.json
artifacts/remote_stdout.txt
```

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
