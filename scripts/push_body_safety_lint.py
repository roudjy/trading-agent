#!/usr/bin/env python3
"""Push-notification body safety lint - v3.15.16.A15.B2.0e.

Closed-scope source-text scanner that fails the build if any push-
publisher surface contains an operator-go-phrase literal. Anchored
in ``docs/governance/agent_activity_center_push_notification_safety.md``
section 2 + section 8.

Closed scan target
------------------

The scanner is intentionally precise: it scans only the closed list
of push-publisher files (``PUSH_PUBLISHER_FILES``) for the closed
list of operator-go-phrase literals (``FORBIDDEN_BODY_TOKENS``).

Generic credential words like ``secret`` / ``token`` / ``password``
are intentionally NOT scanned here. They are already covered by:

* The existing ``secret-scan (gitleaks)`` CI step.
* The ``.claude/hooks/deny_config_read.py`` PreToolUse hook.
* The no-touch read-deny rules over ``state/*.secret``, ``.env``,
  and ``.env.*``.

Why narrow scope:

* Bare word ``secret`` / ``token`` / ``password`` false-positives
  on legitimate prose (e.g. "VAPID secret" or "approval token" in
  comments).
* Operator-go-phrase literals are high-precision signals - they
  never appear in legitimate push-body builder code.
* Adding a new push surface OR a new forbidden literal requires
  updating the closed constants here - intentional friction.

Integration
-----------

* Imported by ``scripts/governance_lint.py`` section 6.
* May also be run standalone: ``python scripts/push_body_safety_lint.py``.
* Stdlib-only.

Violation format
----------------

Per push safety doctrine section 8.1, every violation matches:

::

    push_body_safety_violation: token=<repr> file=<path> line=<n>
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Final

ROOT: Final[Path] = Path(__file__).resolve().parent.parent

PUSH_PUBLISHER_FILES: Final[tuple[str, ...]] = (
    "reporting/web_push_dispatch_adapter.py",
    "reporting/web_push_real_transport.py",
    "reporting/push_subscription_store.py",
    "dashboard/api_push_subscribe.py",
    "dashboard/api_push_dispatch.py",
    "frontend/public/sw-push.js",
)

FORBIDDEN_BODY_TOKENS: Final[tuple[str, ...]] = (
    "required_phrase",
    "operator_go_phrase",
    "OPERATOR-GO",
    "GO Batch",
    "GO A18",
    "GO enable",
)

VIOLATION_FORMAT: Final[str] = (
    "push_body_safety_violation: token={token!r} file={file} line={line}"
)


def find_push_body_safety_violations(
    repo_root: Path | None = None,
    *,
    files: tuple[str, ...] | None = None,
    tokens: tuple[str, ...] | None = None,
) -> list[str]:
    """Return a list of violation strings, one per file, line, token."""
    root = repo_root if repo_root is not None else ROOT
    target_files = files if files is not None else PUSH_PUBLISHER_FILES
    target_tokens = tokens if tokens is not None else FORBIDDEN_BODY_TOKENS

    violations: list[str] = []
    for rel in target_files:
        full = root / rel
        if not full.is_file():
            continue
        try:
            text = full.read_text(encoding="utf-8")
        except OSError:
            continue
        for line_no, line in enumerate(text.splitlines(), 1):
            for token in target_tokens:
                if token in line:
                    violations.append(
                        VIOLATION_FORMAT.format(
                            token=token,
                            file=rel,
                            line=line_no,
                        )
                    )
    return violations


def main(argv: list[str] | None = None) -> int:
    """CLI: prints violations to stdout; exits 1 if any."""
    _ = argv
    vs = find_push_body_safety_violations()
    if vs:
        print("Push-body safety lint FAILED:")
        for v in vs:
            print(f"  - {v}")
        return 1
    print(
        f"Push-body safety lint OK "
        f"({len(PUSH_PUBLISHER_FILES)} surfaces, "
        f"{len(FORBIDDEN_BODY_TOKENS)} tokens checked)."
    )
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
