# QRE Candidate Maturity and Operator Trust PR 4

This PR adds a read-only certification layer for candidate maturity, operator trust, and shadow readiness.

## Canonical decisions

- Portfolio planning outcomes are audited separately from empirical campaign dispositions.
- Operator-trust acceptance cycles are deterministic replays, not empirical research cycles.
- Benchmark candidates remain non-real and do not contribute to real candidate counts.
- `PASS` is reserved for complete required evidence only.
- `INSUFFICIENT_HISTORY` is the canonical fail-closed outcome when the capability works but independent longitudinal evidence is still too thin.

## Current repository result

- The current empirical history remains bounded to one real campaign for `cross_sectional_momentum_v0`.
- The certification harness therefore returns `operator_trust_readiness = INSUFFICIENT_HISTORY`.
- No real shadow-eligible candidate exists, so `shadow_readiness` cannot pass.

## Artifact families

- `logs/qre_candidate_operator_trust_review/latest.json`
- `logs/qre_candidate_operator_trust_review/latest.md`
- Sidecars for candidate inventory, maturity, robustness, portfolio analysis, trust policy, acceptance, history, summary consistency, recovery validation, and shadow readiness.
