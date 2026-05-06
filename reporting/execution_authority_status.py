"""v3.15.16.10 Phase C — Execution Authority read-only status surface.

Read-only health/status projection for the Agent Execution Authority
classifier (PR #110 policy + PR #111 classifier).

This module reports — never decides, never mutates — whether:

* the canonical policy doc is present,
* the classifier module is present and importable,
* both canonical roadmap/governance-planning documents are present,
* the classifier returns the expected decision for a small fixed set
  of sample inputs covering AUTO_ALLOWED, NEEDS_HUMAN, PERMANENTLY_DENIED,
  and the UNKNOWN-input fail-safe.

The artifact path is ``logs/execution_authority_status/latest.json``;
the module never writes anywhere else.

Hard guarantees (pinned by tests):

* Stdlib + ``reporting.execution_authority`` only.
* No subprocess, no network, no ``gh``, no ``git``.
* No imports from ``dashboard``, ``automation``, ``broker``,
  ``agent.risk``, ``agent.execution``, ``research``.
* No file body content embedded in artifacts; bounded ``sha256_short``
  reads only for explicitly pinned files.
* No mutation route. No approval-inbox decisions. No PWA blueprint.
* Sample decisions are derived purely from
  ``reporting.execution_authority.classify``; this module is a
  projection, not a redefinition.

CLI::

    python -m reporting.execution_authority_status            # JSON to stdout
    python -m reporting.execution_authority_status --indent 2
    python -m reporting.execution_authority_status --write    # also write the artifact

The CLI exit code is always 0 — this is a diagnostic, not a gate.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import json
import os
import sys
import tempfile
from pathlib import Path
from typing import Any, Final

from reporting import execution_authority as ea

REPO_ROOT: Final[Path] = Path(__file__).resolve().parent.parent

SCHEMA_VERSION: Final[str] = "1.0"

POLICY_SOURCE: Final[str] = "docs/governance/execution_authority.md"
CLASSIFIER_SOURCE: Final[str] = "reporting/execution_authority.py"
AUTONOMOUS_DEVELOPMENT_SOURCE: Final[str] = "docs/roadmap/autonomous_development.txt"
QRE_ROADMAP_SOURCE: Final[str] = "docs/roadmap/Roadmap v6.md"
UNIT_TEST_REFERENCE: Final[str] = "tests/unit/test_execution_authority.py"

#: The complete, closed open-set of files this module will hash. Every
#: read goes through :func:`_sha256_short` which checks membership in
#: this set and refuses any path outside it. Pinned by tests.
PINNED_HASH_FILES: Final[frozenset[str]] = frozenset(
    {
        POLICY_SOURCE,
        CLASSIFIER_SOURCE,
        AUTONOMOUS_DEVELOPMENT_SOURCE,
        QRE_ROADMAP_SOURCE,
    }
)

ARTIFACT_RELATIVE_PATH: Final[str] = "logs/execution_authority_status/latest.json"

#: First 12 hex chars of SHA-256 — bounded; never the full digest, never
#: the file content.
_HASH_PREFIX_LEN: Final[int] = 12

#: Sample decision corpus. Each row is a synthetic input that exercises
#: a specific (decision, reason) cell in the policy matrix. The expected
#: decision is recomputed at test time against ``classify`` to keep this
#: list honest.
_SAMPLE_INPUTS: Final[tuple[dict[str, str], ...]] = (
    {
        "label": "auto_allowed_doc_non_policy_low",
        "action_type": "file_edit",
        "target_path": "docs/operator/getting_started.md",
        "risk_class": "LOW",
        "expected_decision": "AUTO_ALLOWED",
    },
    {
        "label": "needs_human_canonical_policy_modify",
        "action_type": "file_edit",
        "target_path": POLICY_SOURCE,
        "risk_class": "HIGH",
        "expected_decision": "NEEDS_HUMAN",
    },
    {
        "label": "needs_human_canonical_roadmap_autonomous_dev",
        "action_type": "file_edit",
        "target_path": AUTONOMOUS_DEVELOPMENT_SOURCE,
        "risk_class": "HIGH",
        "expected_decision": "NEEDS_HUMAN",
    },
    {
        "label": "needs_human_canonical_roadmap_qre",
        "action_type": "file_edit",
        "target_path": QRE_ROADMAP_SOURCE,
        "risk_class": "HIGH",
        "expected_decision": "NEEDS_HUMAN",
    },
    {
        "label": "permanently_denied_live_broker_call",
        "action_type": "live_broker_call",
        "target_path": "broker/place_order.py",
        "risk_class": "HIGH",
        "expected_decision": "PERMANENTLY_DENIED",
    },
    {
        "label": "permanently_denied_frozen_contract_mutate",
        "action_type": "frozen_contract_mutate",
        "target_path": "research/research_latest.json",
        "risk_class": "HIGH",
        "expected_decision": "PERMANENTLY_DENIED",
    },
    {
        "label": "needs_human_unknown_action_failsafe",
        "action_type": "this_action_does_not_exist",
        "target_path": "docs/operator/getting_started.md",
        "risk_class": "UNKNOWN",
        "expected_decision": "NEEDS_HUMAN",
    },
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _check_present(rel_path: str) -> str:
    """Return ``"OK"`` if the repo-relative path resolves to an existing
    file, ``"FAIL"`` otherwise. Never reads file contents."""
    return "OK" if (REPO_ROOT / rel_path).is_file() else "FAIL"


def _sha256_short(rel_path: str) -> str | None:
    """Return the first 12 hex chars of the SHA-256 digest of the bytes
    of the file at ``rel_path``, or ``None`` if the file is missing.

    Refuses any path not in :data:`PINNED_HASH_FILES`. This refusal is
    the security keystone: callers cannot persuade this module to hash
    arbitrary files.
    """
    if rel_path not in PINNED_HASH_FILES:
        raise ValueError(
            "execution_authority_status._sha256_short refused unpinned path: "
            f"{rel_path!r}"
        )
    full = REPO_ROOT / rel_path
    if not full.is_file():
        return None
    h = hashlib.sha256()
    with full.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()[:_HASH_PREFIX_LEN]


def _classifier_importable() -> str:
    """The classifier is imported at module top-level. If we got here,
    it imported cleanly; this returns ``"OK"``. Any import failure
    would have raised at module load and produced a hard failure
    rather than a soft FAIL string. This keeps the surface honest:
    we never invent a passing status from a failing import.
    """
    if hasattr(ea, "classify") and callable(ea.classify):
        return "OK"
    return "FAIL"  # pragma: no cover — defensive; module-level import would fail first


def _build_sample_decisions() -> tuple[list[dict[str, str]], bool]:
    """Run each sample input through ``ea.classify`` and return
    ``(rows, all_match)`` where each row carries the expected and
    actual decisions and ``all_match`` is True iff every row matches.

    ``rows`` is bounded — only paths, decision enums, and reason enums.
    Never file body content, diffs, PR text, or commit messages.
    """
    rows: list[dict[str, str]] = []
    all_match = True
    for sample in _SAMPLE_INPUTS:
        decision = ea.classify(
            action_type=sample["action_type"],
            target_path=sample["target_path"],
            risk_class=sample["risk_class"],
        )
        actual = decision.decision
        match = actual == sample["expected_decision"]
        if not match:
            all_match = False
        rows.append(
            {
                "label": sample["label"],
                "action_type": sample["action_type"],
                "target_path": sample["target_path"],
                "risk_class": sample["risk_class"],
                "expected_decision": sample["expected_decision"],
                "actual_decision": actual,
                "actual_reason": decision.reason,
                "actual_target_path_category": decision.target_path_category,
                "match": "OK" if match else "FAIL",
            }
        )
    return rows, all_match


def _last_evaluation_timestamp() -> str:
    return (
        _dt.datetime.now(_dt.UTC)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


# ---------------------------------------------------------------------------
# Public surface
# ---------------------------------------------------------------------------


def build_status() -> dict[str, Any]:
    """Return the read-only execution-authority status snapshot.

    Schema version 1.0 (additive-only). Bounded scalars only:
    presence flags (``"OK"``/``"FAIL"``), short SHA-256 prefixes
    (12 hex chars), pinned source paths, and decision/reason enum
    values. No file body content, no diffs, no PR text, no commit
    messages.
    """
    sample_rows, samples_ok = _build_sample_decisions()
    classifier_present = _classifier_importable()
    policy_present = _check_present(POLICY_SOURCE)
    autonomous_dev_present = _check_present(AUTONOMOUS_DEVELOPMENT_SOURCE)
    qre_roadmap_present = _check_present(QRE_ROADMAP_SOURCE)
    classifier_module_present = _check_present(CLASSIFIER_SOURCE)

    presence_all_ok = (
        classifier_present == "OK"
        and policy_present == "OK"
        and autonomous_dev_present == "OK"
        and qre_roadmap_present == "OK"
        and classifier_module_present == "OK"
    )

    last_validation_status: str
    if presence_all_ok and samples_ok:
        last_validation_status = "OK"
    elif not presence_all_ok:
        last_validation_status = "FAIL"
    else:
        last_validation_status = "FAIL"

    return {
        "schema_version": SCHEMA_VERSION,
        "report_kind": "execution_authority_status",
        "execution_authority_present": classifier_present,
        "policy_doc_present": policy_present,
        "classifier_present": classifier_module_present,
        "autonomous_development_doc_present": autonomous_dev_present,
        "qre_roadmap_doc_present": qre_roadmap_present,
        "policy_source": POLICY_SOURCE,
        "classifier_source": CLASSIFIER_SOURCE,
        "autonomous_development_source": AUTONOMOUS_DEVELOPMENT_SOURCE,
        "qre_roadmap_source": QRE_ROADMAP_SOURCE,
        "policy_doc_sha256_short": _sha256_short(POLICY_SOURCE),
        "classifier_module_sha256_short": _sha256_short(CLASSIFIER_SOURCE),
        "autonomous_development_doc_sha256_short": _sha256_short(
            AUTONOMOUS_DEVELOPMENT_SOURCE
        ),
        "qre_roadmap_doc_sha256_short": _sha256_short(QRE_ROADMAP_SOURCE),
        "unit_test_reference": UNIT_TEST_REFERENCE,
        "sample_decisions_ok": samples_ok,
        "sample_decisions": sample_rows,
        "artifact_relative_path": ARTIFACT_RELATIVE_PATH,
        "last_validation_status": last_validation_status,
        "last_validation_timestamp_utc": _last_evaluation_timestamp(),
    }


def write_status_artifact(out_path: Path | None = None) -> Path:
    """Atomically write the snapshot JSON to ``out_path`` (default:
    ``logs/execution_authority_status/latest.json`` under the repo).

    Returns the resolved output path. Refuses to write outside
    ``logs/``: the artifact path must contain ``logs/`` as a path
    segment. This is a soft guard; the canonical guard is the
    classifier itself (this module is a ``reporting_module``).
    """
    if out_path is None:
        out_path = REPO_ROOT / ARTIFACT_RELATIVE_PATH
    out_path = Path(out_path)
    posix = out_path.as_posix()
    if "/logs/" not in posix and not posix.startswith("logs/"):
        raise ValueError(
            "execution_authority_status.write_status_artifact refuses "
            f"non-logs/ output path: {out_path}"
        )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    snapshot = build_status()
    payload = json.dumps(snapshot, indent=2, sort_keys=True) + "\n"
    # Atomic write: write to a sibling temp file in the same directory,
    # then rename. ``os.replace`` is atomic on POSIX and Windows.
    fd, tmp_name = tempfile.mkstemp(
        prefix=".execution_authority_status.",
        suffix=".tmp",
        dir=str(out_path.parent),
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(payload)
        os.replace(tmp_name, out_path)
    except Exception:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise
    return out_path


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python -m reporting.execution_authority_status",
        description=(
            "Print a JSON snapshot of the Agent Execution Authority "
            "governance health (read-only; decides nothing). Use --write "
            "to also persist the snapshot under logs/."
        ),
    )
    p.add_argument(
        "--indent",
        type=int,
        default=2,
        help="JSON indentation (default: 2). Pass 0 for compact output.",
    )
    p.add_argument(
        "--write",
        action="store_true",
        help=(
            "Also atomically write the snapshot to "
            "logs/execution_authority_status/latest.json."
        ),
    )
    return p


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    snapshot = build_status()
    indent = args.indent if args.indent and args.indent > 0 else None
    json.dump(snapshot, sys.stdout, indent=indent, sort_keys=True)
    sys.stdout.write("\n")
    if args.write:
        write_status_artifact()
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
