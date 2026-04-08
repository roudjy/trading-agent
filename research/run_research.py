"""
Research runner:
voert alle enabled strategieën uit via de registry
en schrijft resultaten naar CSV + latest JSON.
"""

from agent.backtesting.engine import BacktestEngine
from research.registry import get_enabled_strategies
from research.results import make_result_row, append_results_to_csv, write_latest_json


ASSETS = ["BTC-USD", "ETH-USD"]
INTERVALS = ["1h", "4h"]


def run_research():
    engine = BacktestEngine(
        start_datum="2022-01-01",
        eind_datum="2026-01-01",
    )

    rows = []

    for strategy in get_enabled_strategies():
        for interval in INTERVALS:
            try:
                metrics = engine.grid_search(
                    strategie_factory=strategy["factory"],
                    param_grid=strategy["params"],
                    assets=ASSETS,
                    interval=interval,
                )

                params_used = metrics.get("beste_params", {})

                row = make_result_row(
                    strategy=strategy,
                    asset="|".join(ASSETS),
                    interval=interval,
                    params=params_used,
                    metrics=metrics,
                )
            except Exception as e:
                row = make_result_row(
                    strategy=strategy,
                    asset="|".join(ASSETS),
                    interval=interval,
                    params={},
                    metrics={},
                    error=str(e),
                )

            rows.append(row)

    append_results_to_csv(rows)
    write_latest_json(rows)

    print(f"Klaar. {len(rows)} resultaten geschreven.")


if __name__ == "__main__":
    run_research()
