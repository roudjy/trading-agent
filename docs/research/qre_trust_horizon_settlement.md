# QRE Trust Horizon Settlement

This note defines the canonical split between `latest_run` trust artifacts and the cumulative trust horizon.

## Core rule

Latest-run counters and cumulative trust-horizon counters are different measurements and must never overwrite each other.

## Latest-run scope

`trust_horizon_latest_run.v1.json` records only what changed in the most recent invocation:

- `latest_run_new_campaign_count`
- `latest_run_new_evidence_cycle_count`
- `latest_run_replay_count`
- `latest_run_id`

An empty rerun is allowed to report:

- `latest_run_new_campaign_count = 0`
- `latest_run_new_evidence_cycle_count = 0`

## Cumulative scope

`trust_horizon.v1.json` preserves the full cumulative certification horizon:

- cumulative real campaign count
- cumulative distinct hypotheses
- cumulative mechanism families
- cumulative evidence-changing cycles
- cumulative deterministic replays

An empty rerun must not remove historical campaigns, evidence-changing cycles, hypotheses, or families from this horizon.

## Replay semantics

A deterministic replay reuses the same empirical evidence fingerprint.

It may increase replay coverage, but it is not an evidence-changing cycle.

## Certification consequence

`operator_trust_readiness` is computed from the cumulative trust horizon under `qre_operator_trust_policy_v1_1`.

`shadow_readiness` remains separate and still requires a real shadow-eligible candidate.
