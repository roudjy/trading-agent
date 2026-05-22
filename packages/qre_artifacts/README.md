# QRE Artifacts Package

## Purpose

`packages/qre_artifacts` is the target package boundary for research artifact
schemas, deterministic artifact IO contracts, and compatibility definitions.

## Current Status

Status: scaffold-only. Current artifact schemas and generated outputs remain in
their existing repo paths.

## Source of Truth / Authority Boundary

`research/research_latest.json`, `research/strategy_matrix.csv`, tracked schema
fixtures, and existing artifact producers remain authoritative until a bounded
artifact migration pins compatibility.

## Allowed Future Contents

- Artifact schema contracts.
- Deterministic read/write interfaces after compatibility tests exist.
- Artifact validation helpers selected by a named migration unit.

## Forbidden Contents

- Changes to frozen output schemas without explicit artifact-contract intent.
- Strategy, registry, dashboard route, or ADE authority logic.
- Live, paper, shadow, risk, broker, or order-execution behavior.

## Migration Preconditions

- Frozen artifact fixtures and schema-stability tests are passing.
- Producers and consumers are mapped.
- Byte-stability or documented schema compatibility is proven.

## Current Compatibility Policy

Existing artifact paths and schemas remain authoritative. This scaffold exports
no runtime API.

## Activation Status

Activation status: scaffold-only.
