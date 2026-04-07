# AGENTS.md

## Project doel
Trading research platform dat bepaalt:
welke strategie werkt op welke asset + timeframe + regime.

## Workflow regels
- Werk ALTIJD op feature branches
- Run tests na elke wijziging
- Commit alleen relevante files
- Toon diffs tenzij anders gevraagd

## Architectuur regels
- Backtest engine = generiek
- Strategieën = signal generators
- Regime detector = context filter

## Backtesting regels
Elke strategie moet output geven:
- win_rate
- sharpe
- max_drawdown
- trades_per_maand
- consistentie

## Verboden
- Geen blind parameter tunen
- Geen strategie zonder hypothese
- Geen data/logs committen

## Evaluatie
Alle strategieën worden beoordeeld via:
strategy_family × asset_type × timeframe × regime
