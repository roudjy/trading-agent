"""Read-only governance status snapshot.

This module reports — never decides, never mutates — the current state
of the v3.15.15.12 Claude Agent Governance & Safety Layer. It exists so
operators and CI can confirm at a glance:

* whether the policy / hook / agent definitions are present;
* whether the audit ledger for today is reachable and chain-intact;
* how many actions the hooks denied or allowed in the current daily
  ledger;
* what version, branch, and head SHA are checked out;
* whether the working copy is on ``main`` (a soft signal — branch
  protection, not this report, is the actual guard).

Anything the module cannot determine deterministically is reported as
``"unknown"`` or ``"not_available"``. Nothing is ever reported as
``"ok"`` by default — ``ok`` requires positive evidence.

Stdlib-only. No imports from ``research``, ``automation``, ``execution``,
``orchestration``, or any trading-flow module.

Usage::

    python -m reporting.governance_status
    python -m reporting.governance_status --indent 2

The CLI prints a JSON document to stdout and exits 0. The exit code
does *not* reflect governance health — this is a diagnostic, not a
gate.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import re
import subprocess
import sys
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from reporting import agent_audit

REPO_ROOT: Path = Path(__file__).resolve().parent.parent

VERSION_FILE: Path = REPO_ROOT / "VERSION"
SETTINGS_FILE: Path = REPO_ROOT / ".claude" / "settings.json"
HOOKS_DIR: Path = REPO_ROOT / ".claude" / "hooks"
AGENTS_DIR: Path = REPO_ROOT / ".claude" / "agents"
LADDER_DOC: Path = REPO_ROOT / "docs" / "governance" / "autonomy_ladder.md"
LEDGER_DIR: Path = REPO_ROOT / "logs"

# Hook files we expect to exist as part of the v3.15.15.12 layer. Each
# missing file is reported individually rather than collapsed into a
# single boolean, so the operator can see exactly which guard is gone.
EXPECTED_HOOKS: tuple[str, ...] = (
    "_hook_runtime.py",
    "audit_emit.py",
    "deny_config_read.py",
    "deny_dangerous_bash.py",
    "deny_live_connector.py",
    "deny_no_touch.py",
    "deny_outside_agent_allowlist.py",
    "deny_test_weakening.py",
    "precompact_preserve.py",
)

# Keys that can legitimately appear in the snapshot. Every public value
# is one of: a string, an int, a list of strings, a dict of strings, or
# ``None``. The CLI / tests assert this shape.
# A 3+-column markdown table row whose first column is digits-only.
# Group 1 = the level number; group 2 = the last column's content. We
# constrain every wildcard to non-pipe, non-newline characters so the
# match cannot accidentally cross lines (note that \s includes \n by
# default, which is why we use [ \t] for inter-cell whitespace).
_AUTONOMY_AVAILABLE_RE = re.compile(
    r"^\|[ \t]*(\d+)[ \t]*\|[^\n]*\|[ \t]*([^|\n]*?)[ \t]*\|[ \t]*$",
    re.MULTILINE,
)


def _is_available_marker(text: str) -> bool:
    """Treat a ladder cell as 'level is operationally available'.

    The ladder doc uses prose like 'Always available', 'Available after
    v3.15.15.12.3 active', 'Available after v3.15.15.12.4 active', or
    'NOT enabled', 'Locked', 'Permanently disabled'. We accept only the
    explicit ``Always available`` / ``Available after`` forms; anything
    else (including the bare word 'available' inside 'NOT available')
    is rejected.
    """
    lowered = text.strip().lower()
    if lowered.startswith("always available"):
        return True
    return lowered.startswith("available after")


def _read_text(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return None


def _read_version() -> str | None:
    raw = _read_text(VERSION_FILE)
    if raw is None:
        return None
    stripped = raw.strip()
    return stripped or None


def _git_capture(args: list[str]) -> str | None:
    try:
        result = subprocess.run(
            ["git", *args],
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            timeout=2,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    out = (result.stdout or "").strip()
    return out or None


def _git_branch() -> str | None:
    return _git_capture(["rev-parse", "--abbrev-ref", "HEAD"])


def _git_head_sha() -> str | None:
    return _git_capture(["rev-parse", "HEAD"])


def _hook_inventory() -> dict[str, str]:
    """Return ``{hook_name: 'present' | 'missing'}`` for every expected hook."""
    inventory: dict[str, str] = {}
    for name in EXPECTED_HOOKS:
        inventory[name] = "present" if (HOOKS_DIR / name).is_file() else "missing"
    return inventory


def _hook_layer_state(inventory: dict[str, str]) -> str:
    """Aggregate inventory + settings into one of:

    ``installed`` — every expected hook + ``settings.json`` present.
    ``degraded``  — settings.json present but at least one hook missing.
    ``not_available`` — settings.json itself missing.

    The string is intentionally not ``ok``: callers must read the full
    inventory to know which guard is missing.
    """
    if not SETTINGS_FILE.is_file():
        return "not_available"
    if all(state == "present" for state in inventory.values()):
        return "installed"
    return "degraded"


def _autonomy_levels_available() -> dict[str, Any]:
    """Parse the autonomy ladder doc for which levels are operationally
    available right now. Anything we cannot parse is ``unknown``.
    """
    text = _read_text(LADDER_DOC)
    if text is None:
        return {
            "doc_path": _rel(LADDER_DOC),
            "max_available_level": "unknown",
            "available_levels": "unknown",
            "level_6_status": "unknown",
        }
    available: list[int] = []
    seen_levels: set[int] = set()
    for match in _AUTONOMY_AVAILABLE_RE.finditer(text):
        try:
            level = int(match.group(1))
        except ValueError:
            continue
        if level in seen_levels:
            # The ladder table is followed by a per-agent caps table that
            # also starts each row with a number; we want only the first
            # occurrence of each level (the ladder).
            continue
        seen_levels.add(level)
        if 0 <= level <= 6 and _is_available_marker(match.group(2)):
            available.append(level)
    available_sorted = sorted(set(available))
    if not available_sorted:
        # We could not confidently identify any available level. Report
        # unknown rather than guessing.
        return {
            "doc_path": _rel(LADDER_DOC),
            "max_available_level": "unknown",
            "available_levels": "unknown",
            "level_6_status": "unknown",
        }
    return {
        "doc_path": _rel(LADDER_DOC),
        "max_available_level": max(available_sorted),
        "available_levels": available_sorted,
        # Level 6 is permanently disabled per ADR-015. We do not parse this
        # claim — we hard-code it, because if we ever fail to find that
        # statement in the doc, we still want the report to say so.
        "level_6_status": "permanently_disabled",
    }


def _ledger_summary() -> dict[str, Any]:
    """Summarise today's UTC audit ledger.

    Never opens any past day's ledger; per the audit-chain doctrine, only
    today's file is the authoritative tail. Past days are sealed and
    verified out-of-band.

    Returns a dict with ``status`` set to one of:

    * ``not_available`` — file missing or empty.
    * ``intact``        — chain verifies end-to-end.
    * ``broken``        — chain breaks at index ``first_corrupt_index``.
    * ``unreadable``    — the ledger exists but cannot be parsed.

    Also returns counts (``allowed_count``, ``blocked_count``,
    ``other_count``) and a redacted tail (last sequence_id, timestamp,
    outcome — never command_summary or target_path).
    """
    today_path = agent_audit.current_ledger_path()
    out: dict[str, Any] = {
        "ledger_path": _rel(today_path),
        "ledger_date_utc": _dt.datetime.now(_dt.UTC).strftime("%Y-%m-%d"),
        "status": "not_available",
        "first_corrupt_index": None,
        "event_count": 0,
        "allowed_count": 0,
        "blocked_count": 0,
        "other_count": 0,
        "last_event": None,
    }
    if not today_path.exists() or today_path.stat().st_size == 0:
        return out
    try:
        ok, first_bad = agent_audit.verify_chain(today_path)
    except Exception:
        out["status"] = "unreadable"
        return out
    out["status"] = "intact" if ok else "broken"
    out["first_corrupt_index"] = first_bad
    last: dict[str, Any] | None = None
    count = 0
    allowed = 0
    blocked = 0
    other = 0
    try:
        for ev in agent_audit.iter_events(today_path):
            count += 1
            outcome = ev.get("outcome")
            if outcome == "blocked_by_hook":
                blocked += 1
            elif outcome == "ok":
                allowed += 1
            else:
                other += 1
            last = ev
    except Exception:
        out["status"] = "unreadable"
        return out
    # File has bytes but iter_events parsed nothing => the JSON decoder
    # silently dropped every line. verify_chain returned True only
    # because it walked an empty stream. Surface this as unreadable so
    # the operator sees the discrepancy.
    if count == 0 and today_path.stat().st_size > 0:
        out["status"] = "unreadable"
        out["first_corrupt_index"] = 0
        return out
    out["event_count"] = count
    out["allowed_count"] = allowed
    out["blocked_count"] = blocked
    out["other_count"] = other
    if last is not None:
        # Redacted tail — omit command_summary, diff_summary,
        # target_path. These can carry user-controlled strings; even
        # though agent_audit redacts them for the ledger, we do not
        # surface them via this status snapshot.
        out["last_event"] = {
            "sequence_id": last.get("sequence_id"),
            "timestamp_utc": last.get("timestamp_utc"),
            "outcome": last.get("outcome"),
            "tool": last.get("tool"),
            "block_reason": last.get("block_reason"),
            "branch": last.get("branch"),
            "head_sha": last.get("head_sha"),
        }
    return out


def _branch_state() -> dict[str, Any]:
    branch = _git_branch()
    head = _git_head_sha()
    if branch is None and head is None:
        on_main: bool | str = "unknown"
    else:
        on_main = branch == "main"
    return {
        "branch": branch,
        "head_sha": head,
        "on_main_branch": on_main,
        "main_branch_protection_authority": "github_branch_protection_outside_this_process",
    }


def _autonomous_mode_state() -> dict[str, Any]:
    """The autonomous-execution flag is policy, not machine-detectable.

    Settings.json describes what the *operator* may delegate; whether a
    given session is being driven autonomously is a runtime claim by the
    agent and is recorded per-event in the audit ledger
    (``autonomy_level_claimed``). We therefore do not infer it here; we
    return ``not_machine_enforceable`` plus a pointer to the ledger
    field.
    """
    return {
        "status": "not_machine_enforceable",
        "evidence_field": "autonomy_level_claimed",
        "evidence_source": "logs/agent_audit.<UTC date>.jsonl per-event",
        "settings_present": SETTINGS_FILE.is_file(),
    }


def _rel(path: Path) -> str:
    """Return a forward-slash, repo-relative path string. Never raises."""
    try:
        rel = path.relative_to(REPO_ROOT)
    except ValueError:
        return str(path).replace("\\", "/")
    return str(rel).replace("\\", "/")


def _last_evaluation_timestamp() -> str:
    return (
        _dt.datetime.now(_dt.UTC)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def collect_status() -> dict[str, Any]:
    """Return the read-only governance status snapshot.

    Determinism note: the snapshot is a function of repo state plus a
    timestamp. The ``last_evaluation_at_utc`` field is the only
    intentionally non-deterministic value; tests should pin it via
    monkeypatching or treat it as opaque.
    """
    inventory = _hook_inventory()
    return {
        "schema_version": 1,
        "report_kind": "governance_status",
        "last_evaluation_at_utc": _last_evaluation_timestamp(),
        "version": {
            "file_version": _read_version(),
            "version_file": _rel(VERSION_FILE),
        },
        "git": _branch_state(),
        "policy": {
            "settings_file": _rel(SETTINGS_FILE),
            "settings_present": SETTINGS_FILE.is_file(),
            "agents_dir": _rel(AGENTS_DIR),
            "agents_present": AGENTS_DIR.is_dir(),
        },
        "hooks": {
            "layer_state": _hook_layer_state(inventory),
            "expected": list(EXPECTED_HOOKS),
            "inventory": inventory,
            "hooks_dir": _rel(HOOKS_DIR),
        },
        "autonomy": _autonomy_levels_available(),
        "audit_ledger_today": _ledger_summary(),
        "autonomous_mode": _autonomous_mode_state(),
    }


# ---------------------------------------------------------------------------
# Self-check helpers (used by tests)
# ---------------------------------------------------------------------------


# Patterns we never want to see leaving the snapshot. This is a defense
# layer; the underlying agent_audit.append_event already redacts these
# before they reach disk, but the status surface re-applies the check
# at presentation time.
_FORBIDDEN_VALUE_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"sk-ant-[A-Za-z0-9_\-]{8,}"),
    re.compile(r"ghp_[A-Za-z0-9]{8,}"),
    re.compile(r"github_pat_[A-Za-z0-9_]{8,}"),
    re.compile(r"AKIA[0-9A-Z]{12,}"),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
)

_FORBIDDEN_VALUE_FRAGMENTS: tuple[str, ...] = (
    "config/config.yaml",
    "live_gate.secret",
    "fred.secret",
    "operator_token.secret",
    "dashboard_session.secret",
)


def _walk_strings(obj: Any) -> Iterable[str]:
    if isinstance(obj, str):
        yield obj
        return
    if isinstance(obj, dict):
        for v in obj.values():
            yield from _walk_strings(v)
        return
    if isinstance(obj, list | tuple):
        for v in obj:
            yield from _walk_strings(v)


def assert_no_secrets(snapshot: dict[str, Any]) -> None:
    """Raise ``AssertionError`` if the snapshot contains a forbidden
    string. The check is conservative: any high-entropy credential
    pattern OR any literal sensitive-path fragment counts.

    The snapshot is supposed to be entirely path/state metadata — there
    is no legitimate reason for a credential or secret-path string to
    appear in it.
    """
    for s in _walk_strings(snapshot):
        for pat in _FORBIDDEN_VALUE_PATTERNS:
            if pat.search(s):
                raise AssertionError(
                    f"governance_status leaked credential-like string: pattern={pat.pattern!r}"
                )
        lowered = s.lower()
        for frag in _FORBIDDEN_VALUE_FRAGMENTS:
            if frag in lowered:
                raise AssertionError(
                    f"governance_status leaked sensitive path fragment: {frag!r}"
                )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python -m reporting.governance_status",
        description=(
            "Print a JSON snapshot of the v3.15.15.12 Claude Agent "
            "Governance & Safety Layer state. Read-only; decides nothing."
        ),
    )
    p.add_argument(
        "--indent",
        type=int,
        default=2,
        help="JSON indentation (default: 2). Pass 0 for compact output.",
    )
    return p


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    snapshot = collect_status()
    assert_no_secrets(snapshot)
    indent = args.indent if args.indent and args.indent > 0 else None
    json.dump(snapshot, sys.stdout, indent=indent, sort_keys=True)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
