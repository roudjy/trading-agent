"""v3.15.16.10 PR-5 / A7 — known false-positive blockers ledger.

Closed, deliberately curated list of historical false-positive
blocker IDs that PR-3 / A5 demonstrably resolves. The readiness
gate (``reporting.autonomous_dev_readiness``) requires every entry
in this set to be either absent from the current
``logs/human_needed/latest.json`` events OR resolved to a real
actionable proposal under the post-PR-3 parser.

This file is **not** a runtime baseline copy. Each entry is added
deliberately during a PR's diagnose pass and reviewed as code.
"""

from __future__ import annotations

from typing import Final

#: The single historical blocker the operator surfaced when scoping
#: A5: ``task_board:p_1f81cb23``. After PR-1 (archive of obsolete
#: roadmap docs) + PR-3 (suppression of explanatory H2 headings via
#: the actionable-heading filter), ``--diagnose-id p_1f81cb23`` reports
#: ``no_match_found_in_default_sources`` — the ID can no longer be
#: produced by any current source, so it is by definition not a live
#: blocker.
#:
#: To add a new entry: do so only in the PR that resolves the
#: corresponding blocker, and reference the diagnose result in the
#: PR description.
KNOWN_FALSE_POSITIVE_BLOCKER_IDS: Final[frozenset[str]] = frozenset(
    {
        "p_1f81cb23",
    }
)
