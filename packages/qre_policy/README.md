# QRE Policy Package

## Purpose

`packages/qre_policy` is the target package boundary for QRE research policy,
campaign lifecycle policy, candidate lifecycle rules, and readiness policy
contracts.

## Current Status

Status: active read-only seed. The package owns the ADR-014 derived
read-only authority view predicates in `packages.qre_policy.authority_views`.
Current campaign, candidate, funnel, readiness, and runtime policy modules
remain under `research/`.

## Source of Truth / Authority Boundary

`packages.qre_policy.authority_views` is the canonical namespace for the
read-only ADR-014 derived predicates historically exposed by
`research.authority_views`.

The underlying authority sources remain unchanged: registry truth remains in
`research.registry`, preset bundle truth remains in `research.presets`,
hypothesis status truth remains in `research.strategy_hypothesis_catalog`, and
paper/live eligibility invariants remain governed by the existing no-live
policy envelope.

Campaign policy, candidate lifecycle, campaign registry, and paper readiness
policy remain in their existing modules until each surface is migrated by a
bounded unit.

## Allowed Future Contents

- Read-only policy contracts and immutable policy vocabulary.
- Campaign and candidate policy modules after authority compatibility tests.
- Compatibility shims for migrated QRE policy surfaces.

## Forbidden Contents

- Strategy implementation or registry duplication.
- Dashboard route handlers or ADE governance authority.
- Live broker mutation, capital allocation, live risk, paper order execution,
  or shadow execution behavior.

## Migration Preconditions

- Authority source-of-truth mappings remain singular.
- Frozen contracts and policy fixtures are unchanged.
- Scanner output has zero hard forbidden-edge failures.

## Current Compatibility Policy

Existing imports from `research.authority_views` remain compatible for the
derived ADR-014 policy predicates. The compatibility module imports and
re-exports the canonical package functions.

Other existing `research/` policy imports remain authoritative until migrated
by a separate bounded unit.

## Activation Status

Activation status: read-only ADR-014 authority view seed only.
