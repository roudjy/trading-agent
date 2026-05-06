# Quant Research Engine — Roadmap v4 (Ultimate, Claude-Autopilot Ready)

---

# 0. PURPOSE OF THIS DOCUMENT

This document is the **single source of truth** for all development from v3.12 → v3.17.

It is designed so that:
- Claude can execute phases **without ambiguity**
- Development remains **deterministic and aligned**
- No architectural drift occurs
- No time is wasted on interpretation

---

# 1. CURRENT STATE (POST v3.11)

## System Characteristics

- Preset-driven research engine
- Artifact-driven architecture
- Deterministic execution
- React frontend (port 8050)
- Flask backend API
- systemd scheduler (06:00 UTC)
- Docker deployment
- Nginx anti-indexing enforced

## Frozen Contracts (STRICT)

These MUST NEVER change:

- research_latest.json
- strategy_matrix.csv
- ROW_SCHEMA (results.py)

## Authority Doctrine

- ADR-014 (`docs/adr/ADR-014-truth-authority-settlement.md`, v3.15.15.10) — canonical authority map across registry, presets, hypothesis catalog, candidate lifecycle, campaign registry, paper readiness, and live governance. Required reading for any change touching authority surfaces. Defines `executable | enabled | bundle_active | active_discovery | live_eligible` as formally distinct concepts.

---

# 2. CORE ARCHITECTURE RULES

1. registry.py = ONLY source of strategy logic
2. run_research.py = ONLY orchestration entrypoint
3. Artifacts = source of truth
4. No business logic in frontend
5. No pipeline bypass allowed
6. No new strategies outside approved presets
7. Engine = FILTER, not generator

---

# 3. GLOBAL BUILD PROTOCOL (MANDATORY)

For EVERY version:

1. Create branch:
   feature/v3.X-<name>

2. Implement:
   - smallest correct solution
   - no scope creep

3. Commit:
   - small atomic commits
   - logical grouping

4. Test:
   - full suite must pass
   - add new tests

5. Merge:
   - into main
   - no squash

6. Deploy:
   - docker compose
   - verify /api/health

---

# 4. v3.12 — Candidate Promotion Framework

## OBJECTIVE

Convert execution-ready candidates into **ranked, promotable outputs**

---

## MODULES

research/
  promotion_engine.py
  scoring.py
  rejection_layers.py

---

## IMPLEMENTATION STEPS (COMMIT LEVEL)

1. Add scoring.py
   - pure deterministic functions
   - no randomness

2. Add promotion_engine.py
   - consumes candidates + execution_preview
   - produces ranking

3. Integrate into run_research
   - post-execution bridge step

4. Add artifact:
   promoted_candidates.json

5. Add CLI exposure

---

## TESTS

- deterministic scoring
- ranking stability
- reproducibility
- no randomness

---

## FAILURE MODES

- overfitting
- too few trades
- unstable metrics

---

## DoD

- artifact generated
- ranking consistent
- all tests pass
- contracts unchanged

---

# 5. v3.13 — Regime Intelligence

## OBJECTIVE

Add market context to candidate evaluation

---

## MODULES

research/regime/
  detection.py
  tagging.py

---

## IMPLEMENTATION

1. Define regimes:
   - trending
   - ranging
   - high vol
   - low vol

2. Tag candidates

3. Integrate into reporting

---

## TESTS

- deterministic classification
- stable outputs

---

## FAILURE MODES

- misclassification
- unstable tagging

---

## DoD

- regime present in reports
- no contract changes
- deterministic

---

# 6. v3.14 — Portfolio Research

## OBJECTIVE

Evaluate combinations of strategies

---

## MODULES

portfolio/
  correlation.py
  allocator.py

---

## IMPLEMENTATION

1. Compute correlation matrix
2. Evaluate diversification
3. Simulate portfolio performance

---

## TESTS

- reproducibility
- deterministic allocation

---

## FAILURE MODES

- unstable correlation
- overfitting

---

## DoD

- portfolio outputs correct
- deterministic

---

# 7. v3.15 — Paper Validation

## OBJECTIVE

Simulate real-world execution

---

## MODULES

execution/
  paper_engine.py
  latency.py

---

## IMPLEMENTATION

1. Event-driven simulation
2. Slippage modeling
3. Latency handling

---

## TESTS

- no lookahead
- deterministic replay

---

## FAILURE MODES

- unrealistic fills
- latency mismatch

---

## DoD

- realistic behavior
- stable output

---

# 8. v3.16 — Shadow Deployment

## OBJECTIVE

Run strategies live without capital risk

---

## IMPLEMENTATION

1. Connect live data
2. Execute paper trades
3. Monitor behavior

---

## TESTS

- runtime stability
- no crashes

---

## FAILURE MODES

- data feed issues
- crashes

---

## DoD

- stable runtime
- logs clean

---

# 9. v3.17 — Controlled Live Trading

## OBJECTIVE

Enable limited real trading

---

## IMPLEMENTATION

1. Capital limits
2. Kill switches
3. Monitoring

---

## TESTS

- safety triggers
- rollback

---

## FAILURE MODES

- risk exposure
- execution drift

---

## DoD

- fully controlled
- rollback possible

---

# 10. TEST STRATEGY (GLOBAL)

Each phase must include:

- unit tests
- regression tests
- artifact validation
- integration tests

---

# 11. KEY RISKS

- non-determinism
- contract drift
- test pollution (sidecars)
- overfitting
- execution mismatch

---

# 12. CLAUDE EXECUTION TEMPLATE

Claude MUST follow:

- create branch
- implement phase
- commit
- test
- push
- merge
- deploy
- verify

---

# 13. FINAL INSIGHT

This system is:

NOT:
- a trading bot
- a strategy generator

IS:
- a filtering engine
- a validation pipeline
- a risk control layer

---

# 14. NEXT ACTION

Start with:

👉 v3.12 — Candidate Promotion Framework

