"""
Research runner:
voert alle enabled strategieën uit via de registry
en schrijft resultaten naar CSV + latest JSON.
"""

from datetime import datetime, timedelta, UTC

from agent.backtesting.engine import BacktestEngine
from research.registry import get_enabled_strategies
from research.results import make_result_row, append_results_to_csv, write_latest_json


ASSETS = ["BTC-USD", "ETH-USD"]
INTERVALS = ["1h", "4h"]

def get_date_range(interval):
    now = datetime.now(UTC)

    if interval in ["1h", "4h"]:
        start = now - timedelta(days=700)
    else:
        start = now - timedelta(days=1500)

    return start.strftime("%Y-%m-%d"), now.strftime("%Y-%m-%d")

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
                        assets=[asset],
                        interval=interval,
                    )

                    params_used = metrics.get("beste_params", {})

                    row = make_result_row(
                        strategy=strategy,
                        asset=asset,
                        interval=interval,
                        params=params_used,
                        metrics=metrics,
                    )
                except Exception as e:
                    row = make_result_row(
                        strategy=strategy,
                        asset=asset,
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
