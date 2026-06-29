# ADE-QRE-020 Automated Hypothesis Generation Program

## Status

Active governed follow-on program after ADE-QRE-019.

ADE-QRE-020 admits bounded, deterministic, research-only automated hypothesis
generation through isolated generated-hypothesis surfaces outside
`research/**`.

## Authority

ADE-QRE-020 may:

- ingest authoritative repository evidence and generated-research artifacts;
- detect bounded research opportunities;
- build deterministic market observations;
- propose mechanisms from a closed vocabulary;
- compile falsifiable Behavior Thesis candidates;
- evaluate scientific quality, novelty, contradiction, testability, and
  primitive compatibility;
- automatically admit generated theses into an isolated generated thesis
  registry;
- compose manual and generated theses into one resolved research-only thesis
  catalog;
- prioritize admitted theses;
- submit only `COMPILABLE_WITH_CURRENT_PRIMITIVES` generated theses into the
  ADE-QRE-019 strategy-generation pipeline.

ADE-QRE-020 may not:

- generate executable strategy code directly;
- bypass ADE-QRE-019 strategy-specification and validation gates;
- execute campaigns;
- treat sandbox validation as empirical evidence;
- bypass OOS, null controls, preregistration, or campaign readiness;
- grant paper, shadow, live, broker, risk, execution, or capital authority;
- write to protected `research/**` surfaces;
- modify `.claude/**`.

## Canonical Flow

`authoritative evidence`
`-> opportunity`
`-> observation`
`-> mechanism`
`-> candidate thesis`
`-> scientific and novelty gates`
`-> automated research-only thesis admission`
`-> resolved thesis catalog`
`-> optional ADE-QRE-019 submission`

## Program Units

### ADE-QRE-020A - Governance and Hypothesis Authority

- authorize bounded deterministic hypothesis generation and automatic
  research-only thesis admission;
- preserve protected `.claude/**` and `research/**` boundaries;
- preserve prohibition on strategy generation inside ADE-QRE-020.

### ADE-QRE-020B - Evidence Snapshot and Opportunity Inputs

- freeze deterministic input identities for every hypothesis-generation run;
- capture thesis, strategy, contradiction, freshness, failure-memory, and
  portfolio inputs.

### ADE-QRE-020C - Research Opportunity Detector

- detect only closed-vocabulary opportunities from authoritative evidence;
- preserve exact blockers and next actions.

### ADE-QRE-020D - Market Observation Builder

- separate descriptive observations from hypotheses;
- record uncertainty, possible biases, and provenance.

### ADE-QRE-020E - Mechanism Proposal Engine

- emit closed-vocabulary causal mechanisms only;
- distinguish mechanisms from observations and executable code.

### ADE-QRE-020F - Behavior Thesis Compiler

- compile typed candidate theses with falsification, screening, validation,
  OOS, and null-control plans.

### ADE-QRE-020G - Scientific Quality and Falsifiability Gate

- reject or block unfalsifiable, leakage-prone, vague, or non-measurable
  theses.

### ADE-QRE-020H - Novelty and Rejected-Lineage Gate

- reject duplicates, parameter clones, threshold clones, and rejected-lineage
  matches;
- preserve `trend_pullback_v1` rejection lineage.

### ADE-QRE-020I - Contradiction and Alternative-Explanation Engine

- rank supporting, contradicting, and alternative explanations without
  promoting any surface to evidence authority.

### ADE-QRE-020J - Testability and Signal-Density Estimator

- estimate testability, sample adequacy, OOS capacity, and compute cost as
  estimates only.

### ADE-QRE-020K - Primitive Compatibility Classifier

- classify thesis compatibility as:
  - `COMPILABLE_WITH_CURRENT_PRIMITIVES`
  - `COMPILABLE_AFTER_BOUNDED_PRIMITIVE_EXTENSION`
  - `REQUIRES_UNSUPPORTED_STRATEGY_CLASS`
  - `REQUIRES_UNAVAILABLE_DATA`
  - `REQUIRES_UNRESOLVED_IDENTITY`
  - `NOT_SCIENTIFICALLY_ADMISSIBLE`
- create bounded primitive-extension requests where appropriate.

### ADE-QRE-020L - Automatic Thesis Admission and Resolver

- admit only scientifically valid, novel, provenance-complete generated theses;
- compose protected manual theses with generated theses in one resolved
  research-only catalog.

### ADE-QRE-020M - Hypothesis Prioritization

- score admitted theses transparently on information gain, readiness, novelty,
  contradiction value, and portfolio diversity rather than profit claims.

### ADE-QRE-020N - ADE-QRE-019 Integration

- submit only `COMPILABLE_WITH_CURRENT_PRIMITIVES` admitted theses into
  ADE-QRE-019;
- preserve exact downstream blocked or rejected outcomes.

### ADE-QRE-020O - Autonomous Feedback Loop

- ingest ADE-QRE-019 outcomes and later campaign outcomes as bounded feedback;
- do not lower safety or scientific gates automatically.

### ADE-QRE-020P - Apply to Current Research State

- run ADE-QRE-020 against the current authoritative repository state;
- preserve valid zero-admission or generation-blocked outcomes.

### ADE-QRE-020Q - Integrated Closeout

- produce the machine-readable and operator-readable closeout, primitive
  extension requests, prioritized queue, and exact next action.

## Definition of Done

ADE-QRE-020 is complete only when:

- the isolated generated-hypothesis surfaces exist outside `research/**`;
- deterministic evidence snapshot, opportunities, observations, mechanisms,
  candidates, registry, resolved catalog, priorities, feedback, and closeout
  artifacts are persisted;
- automatic admission is atomic and fail-closed;
- the resolved thesis catalog remains the sole resolved research-only thesis
  authority;
- ADE-QRE-019 integration preserves its own gates and can accept only admitted,
  compilable theses;
- tests, governance lint, architecture tests, and architecture import scan are
  green;
- frozen contracts and protected execution surfaces remain unchanged.

## Permanent Restrictions

- no `.claude/**` edits;
- no `research/**` empirical writes;
- no edits to `research/research_latest.json`;
- no edits to `research/strategy_matrix.csv`;
- no strategy generation inside ADE-QRE-020;
- no campaign execution;
- no paper, shadow, live, broker, risk, execution, or capital-allocation
  authority;
- no unconstrained LLM generation;
- no fabricated evidence, identities, OOS windows, or null-control outcomes.
