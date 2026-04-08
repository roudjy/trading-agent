"""
Research runner:
voert alle enabled strategieën uit via de registry
en schrijft resultaten naar CSV + latest JSON.
"""

from agent.backtesting.engine import BacktestEngine
from research.registry import get_enabled_strategies
from research.results import make_result_row, append_results_to_csv, write_latest_json
from research.universe import ASSETS, INTERVALS, get_date_range

def run_research():
    rows = []

    for strategy in get_enabled_strategies():
        for interval in INTERVALS:
            for asset in ASSETS:
                start_datum, eind_datum = get_date_range(interval)

                engine = BacktestEngine(
                    start_datum=start_datum,
                    eind_datum=eind_datum,
                )

                try:
                    metrics = engine.grid_search(
                        strategie_factory=strategy["factory"],
                        param_grid=strategy["params"],
                        assets=[asset.symbol],
                        interval=interval,
                    )

                    params_used = metrics.get("beste_params", {})

                    row = make_result_row(
                        strategy=strategy,
                        asset=asset.symbol,
                        interval=interval,
                        params=params_used,
                        metrics=metrics,
                    )
                except Exception as e:
                    row = make_result_row(
                        strategy=strategy,
                        asset=asset.symbol,
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
