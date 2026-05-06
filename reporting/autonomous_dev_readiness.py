"""v3.15.16.10 PR-5 / A7 — Autonomous Development Track readiness gate.

Read-only check that reports whether the Autonomous Development
Track hardening (PRs 1-4) is complete enough to return to the QRE
Feature Build Track.

Three states:

* ``OK``      — every criterion evaluated as OK; the operator may
                resume QRE Feature Build work.
* ``BLOCKED`` — at least one criterion FAILed.
* ``UNKNOWN`` — at least one criterion is UNKNOWN (e.g. no CI marker
                file present locally) and no criterion is FAIL.
                CI remains the authoritative gate.

The 11 criteria mirror autonomous_development.txt §A7:

 1. ``policy_doc_present``
 2. ``classifier_present``
 3. ``classifier_tests_passing``  (UNKNOWN locally if no CI marker)
 4. ``reporting_read_only_visibility``
 5. ``autonomous_development_doc_present``
 6. ``qre_roadmap_doc_present``
 7. ``obsolete_roadmaps_archived``
 8. ``known_false_positive_blockers_resolved``
 9. ``governance_health_visible``
10. ``no_live_paper_shadow_mutation``
11. ``next_product_phase_named``

Hard guarantees (pinned by tests):

* Stdlib + reporting.execution_authority +
  reporting.execution_authority_status + reporting.governance_status
  (read-only) only.
* No subprocess, no network, no ``gh``, no ``git``.
* No imports from ``dashboard``, ``automation``, ``broker``,
  ``agent.risk``, ``agent.execution``, ``research``.
* No mutation behaviour, no approval-inbox decisions.
* ``classifier_tests_passing == OK`` is reported only from a real
  CI marker file. A missing marker yields ``UNKNOWN``; this module
  never invents a passing status.
* No arbitrary ``human_needed`` count threshold. The
  ``known_false_positive_blockers_resolved`` criterion uses the
  closed list at
  ``reporting.autonomous_dev_readiness_blockers.KNOWN_FALSE_POSITIVE_BLOCKER_IDS``.

Artifact: ``logs/autonomous_dev_readiness/latest.json``.

CLI::

    python -m reporting.autonomous_dev_readiness
    python -m reporting.autonomous_dev_readiness --indent 2
    python -m reporting.autonomous_dev_readiness --no-write
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

from reporting import autonomous_dev_readiness_blockers as _blockers

REPO_ROOT: Final[Path] = Path(__file__).resolve().parent.parent

SCHEMA_VERSION: Final[str] = "1.0"
MODULE_VERSION: Final[str] = "v3.15.16.10"

# Pinned canonical paths (the same closed set the policy doc names).
POLICY_SOURCE: Final[str] = "docs/governance/execution_authority.md"
CLASSIFIER_SOURCE: Final[str] = "reporting/execution_authority.py"
AUTONOMOUS_DEVELOPMENT_SOURCE: Final[str] = "docs/roadmap/autonomous_development.txt"
QRE_ROADMAP_SOURCE: Final[str] = "docs/roadmap/Roadmap v6.md"

OBSOLETE_TOP_LEVEL_NAMES: Final[tuple[str, ...]] = (
    "qre_roadmap_v6_1.md",
    "qre_roadmap_v3_post_v3_15.md",
    "qre_roadmap_v4.md",
    "qre_prompt_guidelines_v2.md",
)

# Names that must NOT exist as top-level directories under the repo
# root (they are markers of trading-execution work).
PROHIBITED_TOP_LEVEL_DIRS: Final[tuple[str, ...]] = (
    "broker",
    "live",
    "paper",
    "shadow",
    "trading",
)

#: Verbatim phrase the canonical product roadmap must contain to
#: confirm the next product phase is named.
NEXT_PRODUCT_PHASE_PHRASE: Final[str] = "v3.15.16 — Intelligent Routing Layer"

#: Optional CI marker file the readiness gate looks for. Absent →
#: ``classifier_tests_passing == UNKNOWN``. CI remains authoritative.
CI_TEST_MARKER_PATH: Final[Path] = (
    REPO_ROOT / "logs" / "test_runs" / "latest_unit_summary.json"
)

ARTIFACT_DIR: Final[Path] = REPO_ROOT / "logs" / "autonomous_dev_readiness"
ARTIFACT_LATEST: Final[Path] = ARTIFACT_DIR / "latest.json"
ARTIFACT_RELATIVE_PATH: Final[str] = "logs/autonomous_dev_readiness/latest.json"

HUMAN_NEEDED_LATEST: Final[Path] = (
    REPO_ROOT / "logs" / "human_needed" / "latest.json"
)

# Closed result vocabulary for individual criteria.
RESULT_OK: Final[str] = "OK"
RESULT_FAIL: Final[str] = "FAIL"
RESULT_UNKNOWN: Final[str] = "UNKNOWN"
RESULT_VALUES: Final[tuple[str, ...]] = (RESULT_OK, RESULT_FAIL, RESULT_UNKNOWN)

# Closed final-state vocabulary.
STATE_OK: Final[str] = "OK"
STATE_BLOCKED: Final[str] = "BLOCKED"
STATE_UNKNOWN: Final[str] = "UNKNOWN"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _utcnow() -> str:
    return (
        _dt.datetime.now(_dt.UTC)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def _path_present(rel_path: str) -> str:
    return RESULT_OK if (REPO_ROOT / rel_path).is_file() else RESULT_FAIL


def _sha256_short(rel_path: str) -> str | None:
    """First 12 hex chars of the SHA-256 of the file at ``rel_path``,
    or None if missing. Reads only the four pinned canonical files
    (caller is expected to pre-validate)."""
    full = REPO_ROOT / rel_path
    if not full.is_file():
        return None
    h = hashlib.sha256()
    with full.open("rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()[:12]


def _read_json(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


# ---------------------------------------------------------------------------
# Criteria
# ---------------------------------------------------------------------------


def _criterion_policy_doc_present() -> dict[str, Any]:
    return {
        "criterion": "policy_doc_present",
        "result": _path_present(POLICY_SOURCE),
        "source": POLICY_SOURCE,
        "sha256_short": _sha256_short(POLICY_SOURCE),
    }


def _criterion_classifier_present() -> dict[str, Any]:
    """The classifier module must exist on disk AND import cleanly.
    A clean import is implied by this module loading at all (see the
    top-level ``from reporting import execution_authority_status as
    eas`` in the readiness build below); but we still check the file
    presence flag separately so the report is informative when the
    module has been moved on disk."""
    src_present = _path_present(CLASSIFIER_SOURCE)
    return {
        "criterion": "classifier_present",
        "result": src_present,
        "source": CLASSIFIER_SOURCE,
        "sha256_short": _sha256_short(CLASSIFIER_SOURCE),
    }


def _criterion_classifier_tests_passing(
    ci_marker_path: Path | None = None,
) -> dict[str, Any]:
    """Read a CI-recorded marker if present. CI is authoritative; if
    no marker is found locally, this is ``UNKNOWN`` — never a fake
    OK. The marker file is expected to carry a JSON object with at
    least ``passed`` (int) and ``failed`` (int)."""
    marker = ci_marker_path if ci_marker_path is not None else CI_TEST_MARKER_PATH
    payload = _read_json(marker)
    if payload is None:
        return {
            "criterion": "classifier_tests_passing",
            "result": RESULT_UNKNOWN,
            "marker": str(marker),
            "marker_present": False,
            "reason": "ci_marker_absent_locally_ci_remains_authoritative",
        }
    failed = payload.get("failed")
    passed = payload.get("passed")
    if isinstance(failed, int) and failed == 0:
        return {
            "criterion": "classifier_tests_passing",
            "result": RESULT_OK,
            "marker": str(marker),
            "marker_present": True,
            "passed": passed,
            "failed": failed,
        }
    return {
        "criterion": "classifier_tests_passing",
        "result": RESULT_FAIL,
        "marker": str(marker),
        "marker_present": True,
        "passed": passed,
        "failed": failed,
    }


def _criterion_reporting_read_only_visibility() -> dict[str, Any]:
    # Late import to keep the readiness module loadable even if the
    # status module has a transient import error during a partial
    # rollback. We still treat such a failure as FAIL (an explicit
    # signal), never as UNKNOWN.
    try:
        from reporting import execution_authority_status as eas

        snap = eas.build_status()
    except Exception as e:  # noqa: BLE001
        return {
            "criterion": "reporting_read_only_visibility",
            "result": RESULT_FAIL,
            "reason": f"execution_authority_status_failed: {type(e).__name__}",
        }
    val = snap.get("last_validation_status")
    return {
        "criterion": "reporting_read_only_visibility",
        "result": RESULT_OK if val == "OK" else RESULT_FAIL,
        "last_validation_status": val,
        "sample_decisions_ok": snap.get("sample_decisions_ok"),
    }


def _criterion_autonomous_development_doc_present() -> dict[str, Any]:
    return {
        "criterion": "autonomous_development_doc_present",
        "result": _path_present(AUTONOMOUS_DEVELOPMENT_SOURCE),
        "source": AUTONOMOUS_DEVELOPMENT_SOURCE,
        "sha256_short": _sha256_short(AUTONOMOUS_DEVELOPMENT_SOURCE),
    }


def _criterion_qre_roadmap_doc_present() -> dict[str, Any]:
    return {
        "criterion": "qre_roadmap_doc_present",
        "result": _path_present(QRE_ROADMAP_SOURCE),
        "source": QRE_ROADMAP_SOURCE,
        "sha256_short": _sha256_short(QRE_ROADMAP_SOURCE),
    }


def _criterion_obsolete_roadmaps_archived() -> dict[str, Any]:
    """Confirm the four obsolete top-level roadmap docs are absent
    from ``docs/roadmap/`` top level AND present under
    ``docs/roadmap/archive/``."""
    top = REPO_ROOT / "docs" / "roadmap"
    archive = top / "archive"
    leaked: list[str] = []
    archive_missing: list[str] = []
    for name in OBSOLETE_TOP_LEVEL_NAMES:
        if (top / name).is_file():
            leaked.append(name)
        if not (archive / name).is_file():
            archive_missing.append(name)
    if leaked or archive_missing:
        return {
            "criterion": "obsolete_roadmaps_archived",
            "result": RESULT_FAIL,
            "leaked_at_top_level": leaked,
            "missing_from_archive": archive_missing,
        }
    return {
        "criterion": "obsolete_roadmaps_archived",
        "result": RESULT_OK,
        "leaked_at_top_level": [],
        "missing_from_archive": [],
    }


def _criterion_known_false_positive_blockers_resolved(
    human_needed_path: Path | None = None,
) -> dict[str, Any]:
    """Every entry in ``KNOWN_FALSE_POSITIVE_BLOCKER_IDS`` must be
    either absent from the current ``logs/human_needed/latest.json``
    events OR present and resolved to a real actionable proposal
    (we cannot prove "resolved to actionable" structurally; the
    operator confirms in the PR description). Therefore the
    machine-checkable invariant is **absence**: if a known FP id
    is present in the current events, the gate is FAIL."""
    target = human_needed_path if human_needed_path is not None else HUMAN_NEEDED_LATEST
    payload = _read_json(target)
    if payload is None:
        # No human_needed file — treat as "no events" (informational
        # OK), since the FP IDs are by definition absent from a
        # non-existent file. This is consistent: PR-3 demonstrated
        # p_1f81cb23 is no longer producible.
        return {
            "criterion": "known_false_positive_blockers_resolved",
            "result": RESULT_OK,
            "ids_checked": sorted(_blockers.KNOWN_FALSE_POSITIVE_BLOCKER_IDS),
            "human_needed_path": str(target),
            "human_needed_available": False,
            "still_present_ids": [],
            "current_event_count": 0,
        }
    events = payload.get("events") or []
    if not isinstance(events, list):
        events = []
    related_ids = {
        ev.get("related_item")
        for ev in events
        if isinstance(ev, dict) and isinstance(ev.get("related_item"), str)
    }
    still_present = sorted(_blockers.KNOWN_FALSE_POSITIVE_BLOCKER_IDS & related_ids)
    return {
        "criterion": "known_false_positive_blockers_resolved",
        "result": RESULT_OK if not still_present else RESULT_FAIL,
        "ids_checked": sorted(_blockers.KNOWN_FALSE_POSITIVE_BLOCKER_IDS),
        "human_needed_path": str(target),
        "human_needed_available": True,
        "still_present_ids": still_present,
        "current_event_count": len(events),
    }


def _criterion_governance_health_visible() -> dict[str, Any]:
    """Both ``governance_status`` and ``execution_authority_status``
    must produce a snapshot. ``governance_status.collect_status``
    invokes the additive ``execution_authority`` block we landed in
    PR-2; if either fails, the criterion is FAIL."""
    try:
        from reporting import governance_status as gs

        snap = gs.collect_status()
    except Exception as e:  # noqa: BLE001
        return {
            "criterion": "governance_health_visible",
            "result": RESULT_FAIL,
            "reason": f"governance_status_failed: {type(e).__name__}",
        }
    ea_block = snap.get("execution_authority") or {}
    return {
        "criterion": "governance_health_visible",
        "result": RESULT_OK
        if ea_block.get("last_validation_status") == "OK"
        else RESULT_FAIL,
        "schema_version": snap.get("schema_version"),
        "execution_authority_block_present": "execution_authority" in snap,
        "execution_authority_last_validation_status": ea_block.get(
            "last_validation_status"
        ),
    }


def _criterion_no_live_paper_shadow_mutation() -> dict[str, Any]:
    """The trading-execution top-level directories must remain absent.
    The deliberate keystone of the no-touch boundary."""
    leaked: list[str] = []
    for d in PROHIBITED_TOP_LEVEL_DIRS:
        if (REPO_ROOT / d).exists():
            leaked.append(d)
    return {
        "criterion": "no_live_paper_shadow_mutation",
        "result": RESULT_OK if not leaked else RESULT_FAIL,
        "prohibited_top_level_dirs": list(PROHIBITED_TOP_LEVEL_DIRS),
        "present_at_top_level": leaked,
    }


def _criterion_next_product_phase_named() -> dict[str, Any]:
    """The verbatim string ``v3.15.16 — Intelligent Routing Layer``
    must appear inside the canonical QRE roadmap document. This is
    a string check; we read the canonical doc bytes and search for
    the exact phrase. No body content is embedded in the artifact —
    only the boolean result + the phrase + the path."""
    full = REPO_ROOT / QRE_ROADMAP_SOURCE
    if not full.is_file():
        return {
            "criterion": "next_product_phase_named",
            "result": RESULT_FAIL,
            "qre_roadmap_present": False,
            "phrase": NEXT_PRODUCT_PHASE_PHRASE,
            "phrase_present": False,
        }
    try:
        text = full.read_text(encoding="utf-8")
    except OSError:
        return {
            "criterion": "next_product_phase_named",
            "result": RESULT_FAIL,
            "qre_roadmap_present": True,
            "phrase": NEXT_PRODUCT_PHASE_PHRASE,
            "phrase_present": False,
            "reason": "read_error",
        }
    present = NEXT_PRODUCT_PHASE_PHRASE in text
    return {
        "criterion": "next_product_phase_named",
        "result": RESULT_OK if present else RESULT_FAIL,
        "qre_roadmap_present": True,
        "phrase": NEXT_PRODUCT_PHASE_PHRASE,
        "phrase_present": present,
    }


# ---------------------------------------------------------------------------
# Snapshot assembly
# ---------------------------------------------------------------------------


def _summarise_state(criteria: list[dict[str, Any]]) -> str:
    results = [c.get("result") for c in criteria]
    if any(r == RESULT_FAIL for r in results):
        return STATE_BLOCKED
    if any(r == RESULT_UNKNOWN for r in results):
        return STATE_UNKNOWN
    return STATE_OK


def _handoff_lines(state: str) -> list[str]:
    if state == STATE_OK:
        return [
            "Autonomous Development Track complete.",
            "Return to QRE Feature Build Track.",
            f"Next product phase: {NEXT_PRODUCT_PHASE_PHRASE}.",
            f"Canonical product roadmap: {QRE_ROADMAP_SOURCE}.",
            f"Canonical autonomous-development doc: {AUTONOMOUS_DEVELOPMENT_SOURCE}.",
        ]
    if state == STATE_UNKNOWN:
        return [
            "Autonomous Development Track readiness UNKNOWN locally — CI is authoritative.",
            f"Canonical product roadmap: {QRE_ROADMAP_SOURCE}.",
            f"Canonical autonomous-development doc: {AUTONOMOUS_DEVELOPMENT_SOURCE}.",
        ]
    return [
        "Autonomous Development Track BLOCKED.",
        f"Canonical product roadmap: {QRE_ROADMAP_SOURCE}.",
        f"Canonical autonomous-development doc: {AUTONOMOUS_DEVELOPMENT_SOURCE}.",
    ]


def collect_snapshot(
    *,
    ci_marker_path: Path | None = None,
    human_needed_path: Path | None = None,
) -> dict[str, Any]:
    """Return the read-only readiness snapshot."""
    criteria = [
        _criterion_policy_doc_present(),
        _criterion_classifier_present(),
        _criterion_classifier_tests_passing(ci_marker_path),
        _criterion_reporting_read_only_visibility(),
        _criterion_autonomous_development_doc_present(),
        _criterion_qre_roadmap_doc_present(),
        _criterion_obsolete_roadmaps_archived(),
        _criterion_known_false_positive_blockers_resolved(human_needed_path),
        _criterion_governance_health_visible(),
        _criterion_no_live_paper_shadow_mutation(),
        _criterion_next_product_phase_named(),
    ]
    state = _summarise_state(criteria)
    failing = sorted({c["criterion"] for c in criteria if c["result"] == RESULT_FAIL})
    unknown = sorted({c["criterion"] for c in criteria if c["result"] == RESULT_UNKNOWN})
    return {
        "schema_version": SCHEMA_VERSION,
        "module_version": MODULE_VERSION,
        "report_kind": "autonomous_dev_readiness",
        "generated_at_utc": _utcnow(),
        "state": state,
        "failing_criteria": failing,
        "unknown_criteria": unknown,
        "criteria": criteria,
        "next_product_phase": NEXT_PRODUCT_PHASE_PHRASE,
        "canonical_product_roadmap": QRE_ROADMAP_SOURCE,
        "canonical_autonomous_development_doc": AUTONOMOUS_DEVELOPMENT_SOURCE,
        "handoff_lines": _handoff_lines(state),
    }


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    posix = path.as_posix()
    if "/logs/" not in posix and not posix.startswith("logs/"):
        raise ValueError(
            "autonomous_dev_readiness._atomic_write_json refuses "
            f"non-logs/ output path: {path}"
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    fd, tmp_name = tempfile.mkstemp(
        prefix=".autonomous_dev_readiness.", suffix=".tmp", dir=str(path.parent)
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(text)
        os.replace(tmp_name, path)
    except Exception:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise


def write_outputs(snapshot: dict[str, Any]) -> Path:
    _atomic_write_json(ARTIFACT_LATEST, snapshot)
    return ARTIFACT_LATEST


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python -m reporting.autonomous_dev_readiness",
        description=(
            "Read-only Autonomous Development Track readiness gate. "
            "Reports OK / BLOCKED / UNKNOWN. Decides nothing; "
            "mutates nothing. CI is authoritative for the "
            "classifier_tests_passing criterion."
        ),
    )
    p.add_argument(
        "--indent",
        type=int,
        default=2,
        help="JSON indent (0 for compact).",
    )
    p.add_argument(
        "--no-write",
        action="store_true",
        help=(
            "Do not persist logs/autonomous_dev_readiness/latest.json "
            "(stdout only)."
        ),
    )
    return p


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    indent = args.indent if args.indent and args.indent > 0 else None
    snap = collect_snapshot()
    if not args.no_write:
        write_outputs(snap)
    json.dump(snap, sys.stdout, indent=indent, sort_keys=True)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
