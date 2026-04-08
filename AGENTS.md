# AGENTS.md

## 1. Purpose

This project builds an automated research platform to discover which strategies work across 
asset × timeframe × regime.

The system must remain:

* hypothesis-driven
* reproducible
* extensible across assets and strategy families

---

## 2. Core Principles

* Quality over speed
* No brute-force parameter searches
* Every strategy must have a clear hypothesis
* Preserve negative results (failure memory)
* Keep changes minimal and reviewable
* Maintain reproducibility of research runs

---

## 3. System Architecture Rules

* `registry.py` is the single source of truth for strategies
* Strategy logic lives only in `agent/backtesting/strategies.py`
* Research orchestration lives in `research/run_research.py`
* Results must always be written to:

  * `research_latest.json`
  * `strategy_matrix.csv`

Constraints:

* Do not duplicate strategy definitions
* Do not bypass the registry
* Do not embed research logic in the runner

---

## 4. AI Tooling Roles

Strict separation between reasoning and execution.

### Claude (Architect / Analyst)

Responsible for:

* architecture decisions
* research reasoning
* hypothesis design
* evaluation of results

Not responsible for:

* multi-file refactors
* direct code execution

---

### Codex CLI (Implementation Engine)

Responsible for:

* implementing code changes
* multi-file refactors
* running commands and smoke checks

Constraints:

* must present a diff plan before editing
* must keep changes minimal and scoped
* must not introduce new strategy logic unless explicitly requested

---

### Claude Code (Precision Tool)

Responsible for:

* small targeted edits
* debugging
* inspecting existing code

---

### Core Principle

Separate thinking from execution:

* Claude decides what to build
* Codex implements it
* Human reviews and validates

Never mix roles within a single step.

---

## 5. Execution Workflow

Every change follows this sequence:

1. Define the task (architecture or research goal)
2. Use Claude to design the minimal solution
3. Use Codex to implement the change
4. Run smoke checks
5. Review outputs before committing

Rules:

* no direct coding without a plan
* no strategy changes during architecture work
* prefer the smallest possible change set

---

## 6. Guardrails

* Do not mix reasoning and implementation in one step
* Do not let Codex invent strategies
* Do not let Claude perform large refactors
* Do not introduce changes without a clear hypothesis or goal
* Do not break existing output formats without explicit intent

---

## 7. Research Discipline

* Focus on one hypothesis at a time
* Do not expand strategy families prematurely
* Prefer improving signal quality over adding complexity
* Trade management changes must be justified separately from entry logic

Current direction:

* Trend-based strategies are the primary focus
* Mean reversion is deprioritized for crypto intraday

---

## 8. Engineering Direction (Current Phase)

Focus on architecture, not alpha expansion.

Priorities:

* extract asset universe into `research/universe.py`
* introduce structured asset metadata
* prepare for multi-asset-type support
* keep runner simple and deterministic

Do not:

* add new strategies during architecture work
* refactor beyond the smallest viable change

---

## 9. Session Start Protocol

At the start of every session:

* activate environment
* pull latest changes
* inspect latest results

```
cd ~/trading-agent
source .venv/bin/activate
git pull
cat research/research_latest.json
```

Then continue from the current system state.

---

## 10. Commit Discipline

* Commit only meaningful changes
* Keep commits small and atomic
* Use clear messages:

  * `feat:` new hypothesis or feature
  * `refactor:` structural change
  * `fix:` bug fix

Never commit:

* temporary logs
* irrelevant artifacts
* partial experiments

