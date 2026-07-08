# QRE Next Sequence

The safe sequence stops before validation, paper, shadow, live, broker, risk, order execution, capital allocation, strategy registration, and autonomous market loops.

## Next PR 1

gap: Tiingo data-driven hypotheses are working but orphaned relative to candidate admission and memory.

why now: This is the first break in the functional chain after the trusted-for-the-Tiingo-E2E-slice-only source/profile/hypothesis evidence.

This addresses a contract/lineage break before adding candidate generation, preventing another disconnected runtime surface.

expected files:

- `research/qre_tiingo_hypothesis_generator_e2e.py` only if adding metadata fields to the existing research-only payload.
- A new or existing read-only contract doc under `docs/architecture/` or `docs/research/`.
- Focused unit tests if a schema/contract helper is added.

acceptance criteria:

- Define a research-only Tiingo hypothesis seed artifact contract with stable identity, source snapshot, data profile digest, controls verdict, and explicit `trading_authority=false`.
- Define whether candidate admission consumes it now or remains blocked, without creating candidates or running screening.
- Preserve shuffled/truncated null-control acceptance.
- No mutation of `research/research_latest.json` or `research/strategy_matrix.csv`.

forbidden scope:

- No candidate promotion.
- No strategy registration.
- No `research.run_research`.
- No validation, paper, shadow, live, broker, risk, or execution behavior.

## Next PR 2

gap: Candidate materialization exists as legacy/scaffold surfaces but has no explicit fail-closed decision for Tiingo hypotheses.

why now: The loop cannot reach screening or evidence until it can say whether a data-driven hypothesis is admissible as a research candidate, blocked, or missing prerequisites.

expected files:

- Candidate admission/readiness helper under the appropriate QRE research boundary.
- Tests proving Tiingo hypotheses remain research-only and fail closed when required lineage is absent.
- Docs updating artifact lineage.

acceptance criteria:

- Consume the accepted Tiingo hypothesis seed contract as input.
- Emit a read-only admission decision artifact or summary.
- Produce `blocked_not_materialized` unless all required non-runtime prerequisites exist.
- Do not create executable strategies or modify registry.

forbidden scope:

- No screening execution.
- No validation/promotion.
- No campaign launcher.
- No paper/shadow/live.

## Next PR 3

gap: Feedback memory does not index the Tiingo E2E evidence by default, so later advisory layers cannot learn from this path.

why now: After a stable seed/admission artifact exists, memory can safely index it without implying runtime execution.

expected files:

- `packages/qre_research/research_memory.py` or a package-boundary-compatible adapter.
- Unit tests for missing, malformed, pass, and blocked Tiingo evidence.
- Docs updating feedback-loop closure status.

acceptance criteria:

- Add Tiingo evidence as read-only memory input.
- Preserve fail-closed behavior for missing/malformed artifacts.
- Prove retrieval can surface Tiingo blockers/verdicts.
- Do not make routing or campaign execution consume it automatically.

forbidden scope:

- No next-cycle execution.
- No validation/paper/shadow/live readiness changes.
- No mutation of frozen public research outputs.

## Blocked/Future

- Validation gate: blocked until candidate materialization and screening evidence are proven.
- Paper/shadow/live gates: future-only or hard-disabled per package boundary docs.
- Automated closed-loop execution: blocked until feedback memory is consumed by a later run with tests proving decision change and evidence writeback.
