# ADE-QRE-021 Governance Conflict Matrix

## Status

Active reference for ADE-QRE-021.

## Conflicts Resolved

| Source | Prior rule | ADE-QRE-021 replacement |
|---|---|---|
| `AGENTS.md` | Do not let Codex invent strategies. | Do not let Codex invent unconstrained primitives or strategies. ADE-QRE-021 may deterministically compile an authoritative bounded primitive-extension request through a closed primitive schema, generated implementation, generated tests, static validation, sandbox validation, and research-only generated primitive registry. |
| `docs/governance/no_touch_paths.md` | `research/**` stays categorically protected. | Preserved. ADE-QRE-021 uses isolated generated-primitive surfaces outside `research/**`; no hook narrowing required. |
| ADE-QRE-020 historical status | Cross-sectional thesis was generation-blocked behind `cross_sectional_rank`. | ADE-QRE-021 is the governed follow-on that can satisfy the bounded primitive request without altering the historical ADE-QRE-020 result. |

## Non-Conflicting Permanent Safety Boundaries

- `.claude/**` remains immutable.
- `research/research_latest.json` remains frozen.
- `research/strategy_matrix.csv` remains frozen.
- Protected empirical `research/**` artifacts remain write-denied.
- No paper, shadow, live, broker, risk, execution, or capital authority is
  granted.
- No network, subprocess, arbitrary file-write, `eval`, or `exec` capability is
  allowed in generated primitives or generated strategies.
