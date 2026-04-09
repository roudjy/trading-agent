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

The system must enforce a clear and modular structure aligned with the defined layers.

### Source of Truth

- `registry.py` is the single source of truth for strategy registration
- Strategy implementations live in `agent/backtesting/strategies.py`
- Research orchestration lives in `research/run_research.py`

### Output Contracts

All research runs must produce:

- `research_latest.json`
- `strategy_matrix.csv`

These outputs must:
- be deterministic
- be reproducible
- follow a stable schema

### Constraints

- Do not duplicate strategy definitions
- Do not bypass the registry
- Do not embed research logic in the runner
- Do not mix orchestration and strategy logic

---

## 4. AI Tooling Roles

Strict separation between reasoning, planning, and execution.

No agent may operate outside its assigned role.

---

### Claude (Architect / Analyst)

Responsible for:

- system architecture decisions
- research reasoning
- hypothesis design
- evaluation of results
- defining refactor scope

Must:

- produce structured plans before any implementation
- enforce AGENTS.md and orchestrator specifications
- identify risks and constraint violations

Not responsible for:

- executing code changes
- performing multi-file edits
- running CLI commands

---

### Codex CLI (Implementation Engine)

Responsible for:

- implementing approved changes
- performing multi-file refactors
- running commands and validations

Must:

- read `AGENTS.md` and `docs/orchestrator_brief.md` before acting
- present a clear diff plan before making changes
- keep changes minimal, scoped, and reversible
- preserve existing behavior unless explicitly instructed otherwise

Not allowed to:

- introduce new strategy logic without explicit approval
- change architecture without a prior plan
- bypass system constraints or layer boundaries

---

### Claude Code (Precision Tool)

Responsible for:

- small targeted edits
- debugging specific issues
- inspecting and explaining code

Must:

- operate within the current architecture
- avoid structural or multi-file changes

---

### Execution Flow (Strict)

All work must follow this sequence:

1. Claude:
   - analyzes problem
   - defines plan
   - identifies risks

2. Human:
   - reviews and approves plan

3. Codex:
   - proposes diff
   - applies changes

4. Human:
   - validates outcome

No step may be skipped.

---

### Core Principle

Separate thinking from execution:

- Claude decides what to build
- Codex implements it
- Human validates correctness

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

## 11. Git Workflow

All work must happen on a non-main branch.

Branch rules:
- never work directly on `main`
- create a new branch before any implementation work
- keep one branch limited to one coherent scope

Branch naming:
- `feature/...` for new capabilities
- `refactor/...` for structural changes
- `fix/...` for bug fixes

Commit rules:
- keep commits small and atomic
- commit only at meaningful checkpoints
- push regularly so remote state stays current

Pull request rules:
- merge to `main` only through a reviewed, intentional PR
- summarize scope, risks, and smoke checks in the PR

Session start rule:
- confirm current branch before doing any work
- if on `main`, create a new branch immediately

Never commit:

* temporary logs
* irrelevant artifacts
* partial experiments

## 12. Enforcement

Any violation of:
- layer boundaries
- registry usage
- configuration rules
- orchestrator specification

must result in:
- rejection of the change
- explicit explanation of the violation
