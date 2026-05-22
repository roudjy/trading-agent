# QRE Policy Package

## Purpose

`packages/qre_policy` is the target package boundary for QRE research policy,
campaign lifecycle policy, candidate lifecycle rules, and readiness policy
contracts.

## Current Status

Status: scaffold-only. Current policy modules remain under `research/`.

## Source of Truth / Authority Boundary

ADR-014 authority surfaces, presets, candidate lifecycle, campaign registry,
and paper readiness policy remain in their existing modules until each surface
is migrated by a bounded unit.

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

Existing `research/` policy imports remain authoritative. This scaffold exports
no runtime API.

## Activation Status

Activation status: scaffold-only.
