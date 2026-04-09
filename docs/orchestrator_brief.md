# Orchestrator Brief: Quant Strategy & Research Framework --- ## 1. Strategy Universe The 
system must support a defined set of quantitative strategy classes. Each strategy must be 
modular, parameterized, and fully compatible with the existing layered architecture. ### Core 
Strategy Classes 1. **Trend Following (Momentum)** * Objective: capture persistent directional 
moves * Typical signals: * Moving average crossovers * Breakouts (e.g. Donchian channels) * 
Requirements: * deterministic signal generation * configurable lookback windows 2. **Mean 
Reversion** * Objective: exploit deviations from equilibrium * Typical signals: * Z-score 
thresholds * Bollinger Band reversion * Requirements: * rolling statistics * regime awareness 
(avoid strong trends) 3. **Statistical Arbitrage (Pairs Trading)** * Objective: exploit 
relative mispricing between assets * Typical signals: * spread deviation from mean * 
cointegration residuals * Requirements: * pair selection logic * spread construction * 
normalization (Z-score) 4. **Volatility-Based Strategies** * Objective: trade volatility 
regimes or expansions * Typical signals: * volatility breakout * ATR-based triggers * 
Requirements: * volatility estimation * dynamic thresholds 5. **Regime-Based Meta Layer** * 
Objective: switch or filter strategies based on market conditions * Regimes: * trending vs 
mean-reverting * low vs high volatility * Requirements: * regime classification model * gating 
logic for strategies --- ## 2. Core Mathematical Foundations The research system must implement 
standardized mathematical primitives. These must be reusable, deterministic, and validated. ### 
Required Metrics & Transformations * **Returns** * simple returns * log returns (preferred for 
aggregation) * **Moving Averages** * simple moving average (SMA) * exponential moving average 
(EMA) * **Z-Score** * standardized deviation from mean * used in mean reversion and stat arb * 
**Volatility** * rolling standard deviation of returns * required for risk normalization * 
**Sharpe Ratio** * risk-adjusted performance metric * must support configurable risk-free rate 
* **Maximum Drawdown** * peak-to-trough loss * required for risk constraints * **Cointegration 
Model** * linear relationship between assets * residual used as tradable signal * **Position 
Sizing** * volatility targeting (required) * optional: Kelly criterion (experimental) --- ## 3. 
Layer Mapping (Strict Enforcement) All components must adhere to the defined system layers. No 
cross-layer leakage is allowed. ### Data Layer * raw market data ingestion * normalization and 
storage * schema enforcement ### Feature Layer * returns * moving averages * volatility * 
z-scores * spreads (for pairs) ### Strategy Layer * signal generation only * no execution logic 
* no portfolio state mutation ### Execution Layer * order simulation or live execution * 
position sizing * slippage and transaction cost modeling ### Evaluation Layer * backtesting 
engine * performance metrics (Sharpe, drawdown, etc.) * reproducibility guarantees ### 
Orchestration Layer (this agent) * pipeline coordination * scheduling runs * managing 
experiment lifecycle * enforcing configuration-driven execution --- ## 4. Initial Strategy Set 
(Mandatory Implementation Order) The system must first implement a minimal but orthogonal 
strategy set: 1. **SMA Crossover (Trend Following)** * Inputs: price series * Parameters: fast 
window, slow window * Output: long/flat or long/short signal 2. **Z-Score Mean Reversion** * 
Inputs: price or spread * Parameters: lookback window, entry/exit thresholds * Output: mean 
reversion signal 3. **Pairs Trading (Statistical Arbitrage)** * Inputs: two asset price series 
* Parameters: hedge ratio, z-score thresholds * Output: long/short pair positions ### 
Constraints * each strategy must be independently testable * all parameters must be externally 
configurable * no hardcoded constants --- ## 5. Orchestrator Responsibilities & Rules The 
orchestrator agent is responsible for enforcing system integrity and automation. ### 
Responsibilities * Execute full pipeline: * data → features → strategy → execution → 
evaluation * Schedule: * backtests * parameter sweeps * research experiments * Manage 
configurations: * assets * timeframes * parameters * risk limits ### Enforcement Rules * No 
execution without validated data contracts * No strategy run without explicit configuration * 
All runs must be: * logged * reproducible * versioned ### Observability Each pipeline run must 
log: * input configuration * feature outputs * generated signals * executed trades * evaluation 
metrics Errors must: * halt execution * include full context * be traceable to module + input 
### Automation Target * fully automated research → validation → deployment loop * minimal 
manual intervention * CLI-driven orchestration with agent coordination --- End of 
specification.
