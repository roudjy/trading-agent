# QRE Artifacts Package

## Purpose

`packages/qre_artifacts` is the target package boundary for research artifact
schemas, deterministic artifact IO contracts, and compatibility definitions.

## Current Status

Status: active read-only seed. The package owns the read-only public output
schema/path constants in `packages.qre_artifacts.public_outputs`. Current
artifact writers and generated outputs remain in their existing repo paths.

## Source of Truth / Authority Boundary

`packages.qre_artifacts.public_outputs` is the canonical namespace for the
frozen public output schema/path constants used by `research.results`.

`research/research_latest.json`, `research/strategy_matrix.csv`, tracked schema
fixtures, and existing artifact producers remain authoritative and are not
moved by this package seed.

## Allowed Future Contents

- Artifact schema contracts.
- Read-only artifact path contracts.
- Deterministic read/write interfaces after compatibility tests exist.
- Artifact validation helpers selected by a named migration unit.

## Forbidden Contents

- Changes to frozen output schema values without explicit artifact-contract intent.
- Strategy, registry, dashboard route, or ADE authority logic.
- Live, paper, shadow, risk, broker, or order-execution behavior.

## Migration Preconditions

- Frozen artifact fixtures and schema-stability tests are passing.
- Producers and consumers are mapped.
- Byte-stability or documented schema compatibility is proven.

## Current Compatibility Policy

Existing imports from `research.results` remain compatible for the public output
schema/path constants. The canonical package module exports the same immutable
tuple/string contract values.

## Activation Status

Activation status: read-only public output contract seed only.
