# QRE Governed Research Throughput

This document describes the PR10 throughput control surface. It is a
governance and planning capability only: it does not run research, create
production candidates, create strategies, create campaigns, run screening, or
grant synthesis/shadow/paper/live/broker/risk/order/capital authority.

## Purpose

The throughput control accepts already-governed hypothesis proposals and plans
which synthetic research items may enter a bounded review queue. Admission is
allowed only when the relevant budgets and gates are satisfied.

## Controls

- candidate budget
- campaign budget
- per-source budget
- per-behavior-family budget
- per-timeframe budget
- duplicate active path suppression
- repeated failure-mode suppression
- data-quality admission
- operator-decision blocking
- architecture gate blocking
- maturity gate blocking
- explainable next-action queue for blocked items

## Boundaries

The output is a read-only report and admission record set. Blocked items carry
canonical, provider-agnostic reason codes from the rejection reason taxonomy.
Missing data, unresolved identity, duplicate paths, operator decisions, and
architecture or maturity gate failures remain explicit next actions.

This module is not a research runner and does not mutate frozen outputs:

- `research/research_latest.json`
- `research/strategy_matrix.csv`
