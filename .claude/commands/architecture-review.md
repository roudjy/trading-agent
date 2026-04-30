---
description: Run an architecture-guardian review on the current diff.
allowed-tools: [Agent]
---

# /architecture-review

Spawns the architecture-guardian agent against the current branch
diff. Output: approve / revise / block, with citation of the ADR
invariant that would be violated (if any).

This command is read-only.
