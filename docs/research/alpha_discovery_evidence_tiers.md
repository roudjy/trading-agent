# Alpha Discovery Evidence Tiers

Alpha discovery now separates technical execution capability from empirical authority.

## Tiers

- `COMPILER_ONLY`
  Proves only that the hypothesis, experiment contract, Strategy IR, and primitive resolution are structurally valid.
- `EXECUTOR_SMOKE`
  Proves that the generic strategy path can load, read data, emit signals, complete a bounded backtest adapter run, and write artifacts.
- `EMPIRICAL_SCREENING`
  Requires research-ready source lineage, resolved identity, sufficient history, sufficient expected activity, and non-placeholder cost/slippage assumptions for a first falsification attempt.
- `LOCKED_OOS_VALIDATION`
  Requires a locked OOS window, sufficient OOS activity, frozen experiment semantics, and the full evidence-family set needed for synthesis and maturity-adjacent conclusions.

## Hard Rules

- An executor smoke test is not empirical research.
- A cache row is not research-ready when its authoritative source is blocked.
- `AVAILABLE` does not mean `SUFFICIENT`.
- Missing locked OOS keeps OOS evidence insufficient.
- Zero-slippage and fixed-cost proxies cannot claim robustness.
- Smoke, data, and capability lessons cannot adjust mechanism priors.
- Evidence insufficiency cannot recommend threshold relaxation as an automatic next step.
