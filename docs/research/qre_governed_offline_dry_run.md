# QRE Governed Offline Dry Run

The governed offline dry run proves that one synthetic, safe candidate can move
through the canonical QRE research route in memory without production research
execution.

## Scope

The dry run is:

- offline-only
- deterministic
- fixture-backed
- in-memory/read-only
- governed by throughput, architecture, and maturity gates

It emits stage records, reason records, an `EvidencePack`-like fixture payload,
a disposition, and feedback/memory payloads.

## Non-Authority

The dry run does not:

- mutate `research/research_latest.json`
- mutate `research/strategy_matrix.csv`
- create production candidates, strategies, presets, or campaigns
- run screening against production data
- grant executable strategy synthesis authority
- grant shadow, paper, live, broker, risk, order, or capital authority
