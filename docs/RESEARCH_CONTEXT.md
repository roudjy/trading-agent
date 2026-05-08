# RESEARCH CONTEXT (historical pre-v3.15 note)

> **Status: historical / superseded.** This file is an early research
> context note from the pre-v3.15 phase. The mismatched header
> (`# CLAUDE.md`) was a leftover; the file has now been retitled but
> kept in place so existing inbound links do not 404. The strategy-
> family verdicts below are historical and have been **superseded**
> by the strategy registry, the strategy hypothesis catalog, and
> ADR-014 (truth-authority settlement).
>
> Current canonical sources of truth:
>
> - Strategy registration: `research/registry.py`
> - Strategy implementations: `agent/backtesting/strategies.py`
> - Hypothesis catalog: `research/strategy_hypothesis_catalog.py`
> - Authority mapping: [`docs/adr/ADR-014-truth-authority-settlement.md`](adr/ADR-014-truth-authority-settlement.md)
> - Authority views (read-only API): `research/authority_views.py`
> - QRE roadmap: [`docs/roadmap/Roadmap v6.md`](<roadmap/Roadmap v6.md>)
>
> Do not treat the verdicts below as live evidence. The runtime
> registry, preset catalog, and `bundle_active` derivation in
> `research.authority_views` are authoritative. This note is kept
> for historical traceability only.

## Historical content (pre-v3.15)

### Architectuur

- Engine: generiek
- Strategieën: signal generators
- Regime: filter
- Output: metrics + verdict

### Strategy families (historical verdicts; not authoritative)

- mean_reversion ❌ (crypto faalt)
- bollinger_mr ❌
- bollinger_mr_regime ❌
- trend_pullback (NEXT)
- breakout (later)
- event_drift (equities)

### Belangrijk principe

Strategieën worden niet globaal beoordeeld,
maar per:
- asset type
- timeframe
- regime

### Huidige status (historical, pre-v3.15)

- Backtest engine: stabiel
- Tests: groen
- Mean reversion: gefaald op crypto

### Volgende focus (historical)

Trend-based strategieën (crypto)
