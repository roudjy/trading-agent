# ADE-QRE-019 Governed Automated Research Strategy Generation Program

## Purpose

ADE-QRE-019 admits the first bounded, deterministic, research-only automated
strategy generation pipeline for QRE.

It authorizes the following research-only chain:

approved behavior thesis
-> deterministic typed strategy specification
-> deterministic executable strategy code generation
-> deterministic test generation
-> static safety validation
-> isolated sandbox validation
-> automatic generated-registry admission
-> canonical resolved research-only catalog inclusion
-> automatic bounded preset generation
-> automatic null-control specification generation
-> automatic campaign-lineage materialization
-> automatic portfolio readiness evaluation
-> automatic preregistration readiness

## Permanent restrictions preserved

- no paper trading
- no shadow activation
- no live trading
- no broker orders
- no capital allocation
- no risk-policy mutation
- no execution-engine mutation
- no automatic candidate-quality promotion
- no automatic promotion to shadow, paper, or live
- no bypass of OOS, null controls, or campaign preregistration
- no unconstrained LLM generation
- no stochastic strategy mutation
- no arbitrary source-code execution
- no `.claude/**` modification requirement
- no `research/**` carveout requirement

## Program items

### ADE-QRE-019A - Governance and Research-Only Generation Authority

- admit bounded deterministic executable strategy generation for research use
- keep trading and deployment authority denied

### ADE-QRE-019B - Typed Strategy Specification Contract

- closed, versioned, typed strategy specification
- approved primitives only

### ADE-QRE-019C - Thesis-to-Specification Compiler

- deterministic compilation from approved theses
- fail-closed blocking outcomes

### ADE-QRE-019D - Deterministic Executable Strategy Generator

- template-based repository-native executable strategy generation
- byte-identical regeneration for identical canonical input

### ADE-QRE-019E - Automated Test Generator

- deterministic repository-native generated tests from typed contracts

### ADE-QRE-019F - Static Safety and Architecture Gate

- AST, import, call, boundary, and integrity validation

### ADE-QRE-019G - Isolated Sandbox Validation

- isolated import, generated-test execution, standard contract tests, and
  deterministic smoke validation

### ADE-QRE-019H - Automatic Research-Only Registration

- atomic generated-registry admission after all automated gates pass
- no manual registration gate

### ADE-QRE-019I - Automatic Bounded Preset Generation

- bounded preset generation inside specification domains

### ADE-QRE-019J - Automatic Null-Control Specification

- mechanism-appropriate null-control specification generation only

### ADE-QRE-019K - Campaign Lineage and Portfolio Integration

- materialize thesis-to-strategy-to-preset-to-portfolio lineage
- determine preregistration readiness only

## Architecture guardrails

- `research/**` remains protected and is not the write target for generated
  ADE-QRE-019 artifacts.
- Generated specifications, manifests, validation artifacts, presets, lineage,
  and registry inputs must live on isolated generated-research surfaces outside
  `research/**`.
- Manual strategy authority remains protected in `research/registry.py`.
- Generated strategy entries are a controlled input only; they do not become a
  second independent authority.
- A single canonical resolver must compose protected manual authority with
  validated generated entries into one research-only resolved strategy catalog.
- Automatic deployment, promotion to candidate-quality, paper, shadow, and
  live remain forbidden.

### ADE-QRE-019L - Apply Pipeline to Blocked Theses

- run the ADE-QRE-019 pipeline against the currently blocked theses
- preserve fail-closed outcomes where eligibility or primitives are missing

### ADE-QRE-019M - Automated Generation Closeout

- deterministic integrated outcome and blocker report
- exact next action only

## Definition of done

ADE-QRE-019 is complete only when:

- governance, queue, roadmap, and authority surfaces consistently admit the
  bounded research-only generation lane without requiring `.claude/**` changes
  or `research/**` write carveouts;
- the deterministic pipeline is implemented and tested;
- successful strategies are automatically admitted to the generated registry
  and become visible through the canonical resolved research-only catalog;
- unsuccessful theses fail closed with explicit reasons;
- portfolio readiness is recomputed from generated outputs;
- campaign execution remains blocked unless preregistration gates are truly met.
