"""Governance-Bootstrap PR-Template Synthesizer (v3.15.16.9).

Pure read-only text synthesizer. Reads logs/human_needed/latest.json
(v3.15.16.8) and produces copy-paste-able bootstrap-PR templates
the operator can apply in seconds. Each template is byte-identical
across runs for the same input.

The synthesizer **never**:

* opens a branch
* opens a PR
* invokes ``gh``
* invokes ``git``
* writes to anything outside ``logs/governance_bootstrap/``
* mutates any input artifact

For every human_needed event with reason in
``governance_bootstrap_required`` the synthesizer emits a
template with:

* ``branch_name``: deterministic branch shape
  ``governance-bootstrap/<event_id>``.
* ``commit_message``: ``governance-bootstrap: <short summary>``.
* ``file_diff``: literal text (NOT applied — copied as-is from
  the upstream event's ``proposed_patch``).
* ``pr_title``: ``governance-bootstrap: <short summary>``.
* ``pr_body``: explanatory operator-facing text + cross-reference
  to the underlying event_id and the related PR.
* ``validation_checklist``: deterministic list the operator can
  tick.

Hard guarantees (enforced by code AND tests)
--------------------------------------------

* Stdlib-only. No subprocess, no ``gh``, no ``git``, no network.
* Output limited to ``logs/governance_bootstrap/``.
* Atomic writes (``tmp`` + ``os.replace``).
* ``safe_to_execute`` is hard-coded ``false`` at the digest level.
* Module source contains no ``git apply``, ``patch -``,
  ``subprocess.run``, ``subprocess.Popen`` (pinned). The synthesizer
  produces text only.
* Determinism: two runs on the same input produce a byte-identical
  ``templates`` list (modulo ``generated_at_utc``).
* Closed reason vocabulary mirrors v3.15.16.8.

CLI
---

::

    python -m reporting.governance_bootstrap
    python -m reporting.governance_bootstrap --no-write
    python -m reporting.governance_bootstrap --status

Stdlib-only.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
import sys
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

REPO_ROOT: Path = Path(__file__).resolve().parent.parent
MODULE_VERSION: str = "v3.15.16.9"
SCHEMA_VERSION: int = 1

DIGEST_DIR_JSON: Path = REPO_ROOT / "logs" / "governance_bootstrap"
SOURCE_HUMAN_NEEDED: Path = (
    REPO_ROOT / "logs" / "human_needed" / "latest.json"
)


# ---------------------------------------------------------------------------
# Closed taxonomies
# ---------------------------------------------------------------------------


# Reasons that produce a bootstrap-PR template. Other reasons (e.g.
# decision_cannot_be_inferred) require human triage and have no
# deterministic patch — we deliberately do not synthesize templates
# for them.
BOOTSTRAPPABLE_REASONS: tuple[str, ...] = (
    "governance_bootstrap_required",
    "no_touch_path_blocks_wiring",
    "allowlist_blocks_completion",
    "add_no_touch_carveout",
)


REC_OK: str = "ok"
REC_NOT_AVAILABLE: str = "not_available"

FINAL_RECOMMENDATIONS: tuple[str, ...] = (REC_OK, REC_NOT_AVAILABLE)


# ---------------------------------------------------------------------------
# Time / path helpers
# ---------------------------------------------------------------------------


def _utcnow() -> str:
    return (
        _dt.datetime.now(_dt.UTC)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def _rel(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(REPO_ROOT.resolve())).replace(
            "\\", "/"
        )
    except ValueError:
        return str(path).replace("\\", "/")


# ---------------------------------------------------------------------------
# Source read (passive)
# ---------------------------------------------------------------------------


def _read_json_artifact(
    path: Path,
) -> tuple[dict[str, Any] | None, str | None]:
    if not path.exists():
        return (None, "missing")
    if not path.is_file():
        return (None, "not_a_file")
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as e:
        return (None, f"unreadable: {type(e).__name__}")
    try:
        data = json.loads(text)
    except json.JSONDecodeError as e:
        return (None, f"malformed: {type(e).__name__}")
    if not isinstance(data, dict):
        return (None, "not_an_object")
    return (data, None)


# ---------------------------------------------------------------------------
# Per-event template synthesis
# ---------------------------------------------------------------------------


def _short_summary(event: Mapping[str, Any]) -> str:
    """Short one-line summary used in branch / commit / PR title."""
    reason = str(event.get("reason") or "")
    component = str(event.get("blocking_component") or "")
    # Strip leading file/module indicators to keep the message tight.
    short = component.split(":", 1)[-1] if ":" in component else component
    return f"{reason}: {short}"[:120]


def _commit_message(event: Mapping[str, Any]) -> str:
    return f"governance-bootstrap: {_short_summary(event)}"


def _branch_name(event: Mapping[str, Any]) -> str:
    event_id = str(event.get("event_id") or "")
    if not event_id:
        return "governance-bootstrap/unknown"
    return f"governance-bootstrap/{event_id}"


def _pr_title(event: Mapping[str, Any]) -> str:
    return f"governance-bootstrap: {_short_summary(event)}"


def _pr_body(event: Mapping[str, Any]) -> str:
    reason = str(event.get("reason") or "")
    component = str(event.get("blocking_component") or "")
    required = str(event.get("required_action") or "")
    impact = str(event.get("impact") or "MEDIUM")
    priority = str(event.get("priority") or "MEDIUM")
    related = event.get("related_item")
    body_lines = [
        "## Governance Bootstrap PR",
        "",
        "Synthesized automatically by `reporting.governance_bootstrap`",
        f"({MODULE_VERSION}) from a v3.15.16.8 `human_needed` event.",
        "",
        "## Source event",
        "",
        f"- event_id: `{event.get('event_id', '')}`",
        f"- reason: `{reason}`",
        f"- blocking_component: `{component}`",
        f"- impact: `{impact}`",
        f"- priority: `{priority}`",
    ]
    if isinstance(related, str) and related:
        body_lines.append(f"- related_item: `{related}`")
    body_lines.extend(
        [
            "",
            "## Required operator action",
            "",
            required,
            "",
            "## Validation checklist",
            "",
            "- [ ] PR diff matches the synthesized `file_diff` byte-for-byte",
            "- [ ] CI green on every required check",
            "- [ ] Frozen-contract sha256 unchanged",
            "- [ ] No `.claude/` change beyond the explicit governance-bootstrap delta",
            "- [ ] No live / paper / shadow / risk path touch",
            "",
            "## Out of scope",
            "",
            "- This PR resolves only the specific blocker above.",
            "- The autonomous engine (v3.15.16.11, future) does NOT auto-merge",
            "  governance-bootstrap PRs — operator merges manually.",
            "",
            "🤖 Synthesized by `reporting.governance_bootstrap`",
        ]
    )
    return "\n".join(body_lines)


def _validation_checklist() -> list[str]:
    """Deterministic checklist surfaced as a structured field."""
    return [
        "PR diff matches the synthesized file_diff byte-for-byte",
        "CI green on every required check",
        "Frozen-contract sha256 unchanged",
        "No .claude/ change beyond the explicit governance-bootstrap delta",
        "No live / paper / shadow / risk path touch",
    ]


def _build_template(event: Mapping[str, Any]) -> dict[str, Any] | None:
    """Synthesize one bootstrap-PR template from one human_needed
    event. Returns ``None`` if the event has no derivable patch
    (proposed_patch is None) or its reason is not in the bootstrappable
    set."""
    reason = str(event.get("reason") or "")
    if reason not in BOOTSTRAPPABLE_REASONS:
        return None
    proposed = event.get("proposed_patch")
    if not isinstance(proposed, str) or not proposed.strip():
        return None
    event_id = str(event.get("event_id") or "")
    if not event_id:
        return None
    return {
        "template_id": f"gb_{event_id[2:]}" if event_id.startswith("h_") else f"gb_{event_id}",
        "source_event_id": event_id,
        "source_reason": reason,
        "branch_name": _branch_name(event),
        "commit_message": _commit_message(event),
        "file_diff": str(proposed),  # text only — NEVER applied
        "pr_title": _pr_title(event),
        "pr_body": _pr_body(event),
        "validation_checklist": _validation_checklist(),
        "evidence": {
            "blocking_component": str(event.get("blocking_component") or ""),
            "impact": str(event.get("impact") or "MEDIUM"),
            "priority": str(event.get("priority") or "MEDIUM"),
            "related_item": event.get("related_item"),
        },
    }


# ---------------------------------------------------------------------------
# Snapshot construction
# ---------------------------------------------------------------------------


def collect_snapshot(
    *,
    frozen_utc: str | None = None,
    human_needed_override: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Build the full governance-bootstrap digest. Pure function."""
    generated = frozen_utc or _utcnow()

    if human_needed_override is not None:
        hn: Mapping[str, Any] | None = human_needed_override
        hn_error: str | None = None
    else:
        hn, hn_error = _read_json_artifact(SOURCE_HUMAN_NEEDED)

    if hn is None:
        return _build_not_available_digest(
            generated_at_utc=generated,
            reason=hn_error or "unknown",
            source_path=_rel(SOURCE_HUMAN_NEEDED),
        )

    events = hn.get("events")
    if not isinstance(events, list):
        return _build_not_available_digest(
            generated_at_utc=generated,
            reason="events_field_not_a_list",
            source_path=_rel(SOURCE_HUMAN_NEEDED),
        )

    templates: list[dict[str, Any]] = []
    skipped = 0
    for ev in events:
        if not isinstance(ev, Mapping):
            skipped += 1
            continue
        t = _build_template(ev)
        if t is None:
            skipped += 1
            continue
        templates.append(t)

    # Stable ordering: by template_id ascending.
    templates.sort(key=lambda t: str(t.get("template_id") or ""))

    return {
        "schema_version": SCHEMA_VERSION,
        "report_kind": "governance_bootstrap_digest",
        "module_version": MODULE_VERSION,
        "generated_at_utc": generated,
        "mode": "dry-run",
        "source_human_needed": {
            "path": _rel(SOURCE_HUMAN_NEEDED),
            "status": "ok",
            "module_version": hn.get("module_version"),
            "events_total": len(events),
            "skipped_events": skipped,
        },
        "policy": {
            "bootstrappable_reasons": list(BOOTSTRAPPABLE_REASONS),
        },
        "counts": {
            "templates_total": len(templates),
        },
        "templates": templates,
        "final_recommendation": REC_OK,
        "safe_to_execute": False,
    }


def _build_not_available_digest(
    *, generated_at_utc: str, reason: str, source_path: str
) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "report_kind": "governance_bootstrap_digest",
        "module_version": MODULE_VERSION,
        "generated_at_utc": generated_at_utc,
        "mode": "dry-run",
        "source_human_needed": {
            "path": source_path,
            "status": "not_available",
            "error": reason,
            "module_version": None,
            "events_total": 0,
            "skipped_events": 0,
        },
        "policy": {
            "bootstrappable_reasons": list(BOOTSTRAPPABLE_REASONS),
        },
        "counts": {
            "templates_total": 0,
        },
        "templates": [],
        "final_recommendation": REC_NOT_AVAILABLE,
        "safe_to_execute": False,
    }


# ---------------------------------------------------------------------------
# Atomic write
# ---------------------------------------------------------------------------


def write_outputs(snapshot: Mapping[str, Any]) -> dict[str, str]:
    DIGEST_DIR_JSON.mkdir(parents=True, exist_ok=True)
    ts = str(snapshot["generated_at_utc"]).replace(":", "-")
    json_now = DIGEST_DIR_JSON / f"{ts}.json"
    json_latest = DIGEST_DIR_JSON / "latest.json"
    history = DIGEST_DIR_JSON / "history.jsonl"
    payload = json.dumps(snapshot, sort_keys=True, indent=2)

    tmp_now = json_now.with_suffix(json_now.suffix + ".tmp")
    tmp_now.write_text(payload, encoding="utf-8")
    os.replace(tmp_now, json_now)

    tmp_latest = json_latest.with_suffix(json_latest.suffix + ".tmp")
    tmp_latest.write_text(payload, encoding="utf-8")
    os.replace(tmp_latest, json_latest)

    compact = json.dumps(snapshot, sort_keys=True, separators=(",", ":"))
    with history.open("a", encoding="utf-8") as f:
        f.write(compact + "\n")

    return {
        "latest": _rel(json_latest),
        "timestamped": _rel(json_now),
        "history": _rel(history),
    }


def read_latest_snapshot() -> dict[str, Any] | None:
    p = DIGEST_DIR_JSON / "latest.json"
    if not p.exists():
        return None
    try:
        text = p.read_text(encoding="utf-8")
        data = json.loads(text)
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="reporting.governance_bootstrap",
        description=(
            f"Governance-bootstrap PR-template synthesizer "
            f"({MODULE_VERSION}). Stdlib-only. Read-only text "
            "generation over the human_needed digest."
        ),
    )
    g = parser.add_mutually_exclusive_group(required=False)
    g.add_argument(
        "--mode",
        type=str,
        default="dry-run",
        choices=["dry-run"],
        help="Operating mode. Only dry-run is supported.",
    )
    g.add_argument(
        "--status",
        action="store_true",
        help="Read and print the latest digest from logs/.",
    )
    parser.add_argument(
        "--no-write",
        action="store_true",
        help="Do not persist the JSON digest (stdout only).",
    )
    parser.add_argument(
        "--frozen-utc",
        type=str,
        default=None,
        help="Pin generated_at_utc for deterministic tests.",
    )
    parser.add_argument(
        "--indent",
        type=int,
        default=2,
        help="JSON indent for stdout (0 for compact).",
    )
    args = parser.parse_args(argv)

    if args.status:
        snap = read_latest_snapshot()
        if snap is None:
            print(
                json.dumps(
                    {"status": "not_available", "reason": "missing"},
                    indent=args.indent or None,
                )
            )
            return 1
        print(json.dumps(snap, sort_keys=True, indent=args.indent or None))
        return 0

    snap = collect_snapshot(frozen_utc=args.frozen_utc)
    if not args.no_write:
        write_outputs(snap)
    print(json.dumps(snap, sort_keys=True, indent=args.indent or None))
    return 0


if __name__ == "__main__":
    sys.exit(main())
