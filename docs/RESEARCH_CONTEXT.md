# CLAUDE.md

## Architectuur

- Engine: generiek
- Strategieën: signal generators
- Regime: filter
- Output: metrics + verdict

## Strategy families

- mean_reversion ❌ (crypto faalt)
- bollinger_mr ❌
- bollinger_mr_regime ❌
- trend_pullback (NEXT)
- breakout (later)
- event_drift (equities)

## Belangrijk principe

Strategieën worden niet globaal beoordeeld,
maar per:
- asset type
- timeframe
- regime

## Huidige status

- Backtest engine: stabiel
- Tests: groen
- Mean reversion: gefaald op crypto

## Volgende focus

Trend-based strategieën (crypto)
