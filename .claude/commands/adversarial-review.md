---
description: Spawn the adversarial-reviewer agent for a red-team pass on the current diff.
allowed-tools: [Agent]
---

# /adversarial-review

Spawns the adversarial-reviewer agent. The agent attempts to break
the diff: hook bypasses, secret exfiltration, determinism drift,
live-connector introduction, test weakening, schema mutation,
audit-chain tampering. Output: a list of findings tagged block |
revise | informational.

A block finding is recommendation-only - humans always decide.
