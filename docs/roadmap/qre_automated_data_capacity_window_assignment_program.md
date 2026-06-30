# ADE-QRE-024 Automated Data Capacity and Authoritative Window Assignment

## Status

Active governed follow-on program after ADE-QRE-023.

ADE-QRE-024 admits a bounded deterministic loop that can diagnose the exact
data-capacity and authoritative-window blocker for each campaign cell, repair
the smallest upstream governed cause, replay downstream readiness, and continue
until at least one cell becomes genuinely `READY_FOR_PREREGISTRATION` or an
irreducible terminal blocker is proven from authoritative repository evidence.

## Authority

ADE-QRE-024 may:

- diagnose cache, snapshot, coverage, point-in-time membership, signal-density,
  and authoritative window-assignment blockers for governed campaign cells;
- read existing authoritative local cache, coverage, instrument, universe, and
  readiness artifacts;
- materialize missing cache rows only from repository-supported local inputs and
  governed cache adapters;
- create immutable or content-addressed snapshots outside protected
  `research/**` surfaces;
- assign train, validation, and unseen OOS windows deterministically without
  inspecting strategy results;
- reserve windows in a canonical ledger and prove independence or fail closed;
- replay downstream readiness, portfolio reconstruction, and preregistration
  evaluation automatically;
- create a second-campaign preregistration manifest only when at least one cell
  is genuinely `READY_FOR_PREREGISTRATION`.

ADE-QRE-024 may not:

- invent bars, datasets, snapshots, windows, costs, slippage, signal density,
  or empirical evidence;
- fetch arbitrary external data, use credentials outside governed local data
  adapters, or silently substitute another instrument, source, or timeframe;
- reuse consumed OOS windows, relabel shifted or overlapping windows as
  independent, or inspect OOS performance before assignment;
- execute campaigns;
- grant paper, shadow, live, broker, risk, execution, capital, or deployment
  authority;
- write to protected `research/**` surfaces;
- modify `.claude/**`.

## Program Units

### ADE-QRE-024A - Governance and Data/Window Authority
### ADE-QRE-024B - Data Capacity Diagnosis
### ADE-QRE-024C - Canonical Data Binding and Cache Authority
### ADE-QRE-024D - Missing Cache Row Materialization
### ADE-QRE-024E - Data Quality and Coverage Validation
### ADE-QRE-024F - Immutable Snapshot Materialization
### ADE-QRE-024G - Authoritative Window Policy
### ADE-QRE-024H - Window Ledger and Consumption Registry
### ADE-QRE-024I - Train/Validation/OOS Assignment
### ADE-QRE-024J - OOS Independence and Leakage Proof
### ADE-QRE-024K - Point-in-Time Universe and Breadth Validation
### ADE-QRE-024L - Signal-Density Capacity Validation
### ADE-QRE-024M - Iterative Data/Window Closure Loop
### ADE-QRE-024N - Downstream Readiness Replay
### ADE-QRE-024O - Second-Campaign Preregistration
### ADE-QRE-024P - Integrated Closeout

## Definition of Done

ADE-QRE-024 is complete only when:

- deterministic data-capacity diagnosis, canonical data/cache authority,
  snapshot materialization, authoritative window policy, window ledger,
  independence proof, point-in-time validation, and signal-capacity validation
  exist outside `research/**`;
- the bounded loop has executed against all four A23 campaign cells and
  continued past the first repaired blocker;
- every iteration records before-state, selected blocker, remediation,
  generated artifacts, validation, after-state, and progress classification;
- window assignment occurs without inspecting strategy returns or campaign
  outcomes;
- consumed OOS windows are never reused or relabeled as independent;
- at least one cell is either genuinely `READY_FOR_PREREGISTRATION` or is
  irreducibly fail-closed with an exact blocker and next machine action;
- any second-campaign manifest remains fail-closed unless every mandatory
  preregistration gate is satisfied;
- tests, governance lint, architecture tests, and architecture import scan are
  green;
- frozen contracts and protected execution surfaces remain unchanged.

## Permanent Restrictions

- no `.claude/**` edits;
- no `research/**` empirical writes;
- no edits to `research/research_latest.json`;
- no edits to `research/strategy_matrix.csv`;
- no invented cache rows, bars, windows, independence proofs, or empirical null
  outcomes;
- no OOS-aware window assignment;
- no automatic threshold relaxation;
- no campaign execution;
- no paper, shadow, live, broker, risk, execution, capital-allocation, or
  deployment authority.
