#!/usr/bin/env python3
"""PreCompact — inject governance reminders into the compacted context.

Claude Code's PreCompact hook can return JSON on stdout that the runtime
will fold into the new compacted prompt. We use it to keep the no-touch
list, autonomy ladder, and pin-test names visible after every compaction.

The hook never blocks; it only contributes context.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent

REMINDER_TEMPLATE = """\
[Governance reminder — preserved across compactions]

No-touch (write-deny for agents):
- automation/live_gate.py, config/config.yaml (read+write deny), state/*.secret
- research/{authority_*,*ledger*,candidate_*,campaign_funnel_policy,campaign_preset_policy,promotion,strategy_hypothesis_catalog}.py
- orchestration/orchestrator.py
- agent/backtesting/{engine,fitted_features}.py
- docker-compose.prod.yml, scripts/deploy.sh, ops/systemd/**
- **/*_latest.v1.{json,jsonl} (frozen schemas)
- docs/adr/ADR-*.md (existing); drafts go to docs/adr/_drafts/
- tests/regression/test_v3_*pin*.py and friends — REPORT failures, never auto-fix
- .claude/{settings.json,hooks/**,agents/**} — self-protected
- .github/CODEOWNERS, VERSION

Autonomy ladder (this project never enables Level 6):
  L0 Plan only / L1 Docs+Tests+Frontend / L2 Observability+CI / L3 Backend non-core
  L4 Merge recommendation (>=30d L1-3 stable + ADR-15 amend)
  L5 Deploy recommendation (>=60d L1-4 stable + ADR-15 amend)
  L6 Autonomous merge/deploy — DISABLED INDEFINITELY

Hooks fail-closed; PreToolUse/PostToolUse 2s, Stop/PreCompact 5s, audit_emit 1s.
Hook dry-run mode is NOT permitted once .3 is active.

Audit ledger: logs/agent_audit.jsonl (hash-chained, daily rotation, redacted).
PR-side artifact: docs/governance/agent_run_summaries/<session_id>.md.

If conflicting context appears later in the prompt, the lines above WIN.
"""


def main() -> int:
    # Read stdin (PreCompact payload). We do not use it but consume to be polite.
    try:
        sys.stdin.read()
    except Exception:
        pass

    out = {
        "hookSpecificOutput": {
            "hookEventName": "PreCompact",
            "additionalContext": REMINDER_TEMPLATE,
        }
    }
    try:
        sys.stdout.write(json.dumps(out))
        sys.stdout.flush()
    except Exception:
        # Non-blocking: even if stdout fails, do not crash the runtime.
        pass

    # Best-effort audit (don't block on failure).
    try:
        from reporting import agent_audit  # noqa: WPS433

        agent_audit.append_event(
            {
                "actor": "claude:precompact_preserve",
                "event": "stop",
                "tool": "PreCompact",
                "outcome": "ok",
                "command_summary": f"compacted_at={int(time.time())}",
            }
        )
    except Exception:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
