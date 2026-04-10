# polymarket-paper-trader assessment

Repository reviewed: https://github.com/agent-next/polymarket-paper-trader
Package reviewed: https://pypi.org/project/polymarket-paper-trader/
Version inspected locally: `0.1.7`

## 1. License

The repository and published package are MIT licensed. That is compatible with reference use, wrapper use, or selective vendor use inside this repository.

## 2. Dependency tree

Direct package dependencies from the published wheel:

- `click`
- `httpx`
- `mcp`

Notable transitive dependencies observed from `mcp`:

- `starlette`
- `uvicorn`
- `jsonschema`
- `pydantic-settings`
- `pyjwt`
- `python-multipart`

Assessment: the dependency tree is materially heavier than this Phase 2 scope needs. It does not pull in `web3` or `eth-account`, which is good, but the MCP stack adds server and framework weight that is unrelated to our execution realism module.

## 3. Library API cleanliness

There is a usable Python API. The package exposes importable modules such as:

- `pm_trader.engine.Engine`
- `pm_trader.api.PolymarketClient`
- `pm_trader.orderbook.simulate_buy_fill`
- `pm_trader.orderbook.simulate_sell_fill`

Import-time behavior is mostly clean:

- `pm_trader.__init__` is effectively empty.
- `pm_trader.api` defines an HTTP client class but does not hit the network on import.
- `pm_trader.engine` wires components but does not create storage or network connections on import.

However, the usable surface is still opinionated:

- `Engine(Path)` immediately initializes SQLite schema and owns storage.
- `PolymarketClient` owns direct Gamma and CLOB HTTP access.
- CLI and MCP entrypoints are first-class, not thin wrappers around a minimal pure library core.

Conclusion: importable and callable without the CLI, but not a clean backend library in the sense required for our architecture boundary.

## 4. State and storage conventions

The package persists state in SQLite and uses fixed defaults under the user home directory:

- CLI default data dir: `~/.pm-trader`
- MCP default account dir: `~/.pm-trader/<account>`
- SQLite file: `paper.db`
- Additional tables include account, trades, positions, and market metadata cache

The CLI allows overriding the data directory via `--data-dir` or `PM_TRADER_DATA_DIR`, which helps, but the package still assumes ownership of account state layout and DB schema.

Assessment: this conflicts with our requirement that external integrations must not drive storage conventions.

## 5. Network behavior

The package fetches Polymarket data itself through:

- Gamma API: market discovery and metadata
- CLOB API: live order books, midpoint prices, fee rates, tick sizes

It also caches market metadata in its own SQLite layer while explicitly keeping order books and prices live.

Assessment: if wrapped directly, this would collide with our own adapter boundary because network access and market-data policy would be controlled by the external package, not by our repository.

## 6. Recommended integration mode

Recommended mode: **A = reference only, reimplement ourselves**

Reasoning:

- The pure execution logic in `pm_trader.orderbook` is useful as a reference.
- The package as a whole owns too much: network calls, SQLite schema, CLI, MCP server, account model, and cache behavior.
- Wrapping `Engine` would let an external package dictate storage, network, and lifecycle assumptions.

Mode B is not recommended. There is an importable API, but it is not clean enough as an isolated backend because it couples execution realism to its own DB and Polymarket client.

Mode C is possible only as a very narrow selective vendor of pure functions, but it is unnecessary for Phase 2 because the fee and order-book walking logic are small enough to reimplement cleanly.

Mode D is forbidden by project architecture and is not recommended.

## 7. Risks of the recommended mode

- Reimplementation risk: we must match fee and slippage semantics carefully to avoid false realism.
- Snapshot-shape risk: our simulator will need a stable internal order-book snapshot contract so tests stay deterministic.
- Drift risk: if Polymarket changes its fee model or book schema, our implementation must be updated manually.

These risks are lower than the architectural risk of letting the external package own our execution, storage, and network boundaries.

## 8. Minimum shim surface needed inside `execution/paper/polymarket_sim.py`

The smallest useful boundary is:

- input: one canonical Polymarket order-book snapshot plus intended side, size, and intended price
- pure helpers:
  - fee calculation
  - buy-side book walking
  - sell-side book walking
  - slippage basis-point calculation
- output:
  - our own `Fill` dataclass from `execution/protocols.py`

If Phase 3 wants selective reuse, the only plausible candidate is the order-book math pattern from `pm_trader.orderbook`. Do not reuse:

- `pm_trader.engine.Engine`
- `pm_trader.db.Database`
- `pm_trader.api.PolymarketClient`
- CLI or MCP server modules

## Final recommendation

Proceed with **Mode A**. Use `polymarket-paper-trader` as a reference implementation only. Reimplement the execution realism logic inside our own `execution/paper/polymarket_sim.py` against our own snapshot/input/output contracts.
