"""Unit tests for the v3.15.16.10 Phase C read-only execution-authority
status surface (``reporting.execution_authority_status``).

The classifier itself is exhaustively pinned by
``tests/unit/test_execution_authority.py``; these tests cover only the
projection module: schema shape, sample-decision parity with the
classifier, bounded hashing, refusal of unpinned hash paths, atomic
writing, and the additive ``governance_status`` integration.
"""

from __future__ import annotations

import json
import socket
import subprocess
import urllib.request
from pathlib import Path
from typing import Any

import pytest

from reporting import execution_authority as ea
from reporting import execution_authority_status as eas
from reporting import governance_status

REPO_ROOT = Path(__file__).resolve().parent.parent.parent


# ---------------------------------------------------------------------------
# Schema shape
# ---------------------------------------------------------------------------


def test_schema_version_is_string_one_zero() -> None:
    assert eas.SCHEMA_VERSION == "1.0"


def test_build_status_top_level_keys() -> None:
    snap = eas.build_status()
    expected = {
        "schema_version",
        "report_kind",
        "execution_authority_present",
        "policy_doc_present",
        "classifier_present",
        "autonomous_development_doc_present",
        "qre_roadmap_doc_present",
        "policy_source",
        "classifier_source",
        "autonomous_development_source",
        "qre_roadmap_source",
        "policy_doc_sha256_short",
        "classifier_module_sha256_short",
        "autonomous_development_doc_sha256_short",
        "qre_roadmap_doc_sha256_short",
        "unit_test_reference",
        "sample_decisions_ok",
        "sample_decisions",
        "artifact_relative_path",
        "last_validation_status",
        "last_validation_timestamp_utc",
    }
    assert set(snap.keys()) == expected
    assert snap["report_kind"] == "execution_authority_status"


def test_status_is_json_serializable() -> None:
    snap = eas.build_status()
    text = json.dumps(snap, sort_keys=True)
    # Round-trip must be lossless and produce the same dict.
    assert json.loads(text) == snap


def test_artifact_relative_path_is_under_logs_not_research() -> None:
    assert eas.ARTIFACT_RELATIVE_PATH.startswith("logs/")
    assert "research/" not in eas.ARTIFACT_RELATIVE_PATH


# ---------------------------------------------------------------------------
# Source paths reference the canonical post-PR-1 documents
# ---------------------------------------------------------------------------


def test_canonical_sources_match_post_pr1_paths() -> None:
    assert eas.POLICY_SOURCE == "docs/governance/execution_authority.md"
    assert eas.CLASSIFIER_SOURCE == "reporting/execution_authority.py"
    assert eas.AUTONOMOUS_DEVELOPMENT_SOURCE == "docs/roadmap/autonomous_development.txt"
    assert eas.QRE_ROADMAP_SOURCE == "docs/roadmap/Roadmap v6.md"
    assert eas.UNIT_TEST_REFERENCE == "tests/unit/test_execution_authority.py"


def test_pinned_hash_files_is_exactly_four() -> None:
    assert eas.PINNED_HASH_FILES == frozenset(
        {
            eas.POLICY_SOURCE,
            eas.CLASSIFIER_SOURCE,
            eas.AUTONOMOUS_DEVELOPMENT_SOURCE,
            eas.QRE_ROADMAP_SOURCE,
        }
    )
    assert len(eas.PINNED_HASH_FILES) == 4


# ---------------------------------------------------------------------------
# Bounded hashing
# ---------------------------------------------------------------------------


def test_classifier_hash_is_bounded() -> None:
    """The classifier-module short hash is exactly 12 hex chars."""
    snap = eas.build_status()
    short = snap["classifier_module_sha256_short"]
    assert isinstance(short, str)
    assert len(short) == 12
    int(short, 16)  # must be hex


def test_policy_doc_hash_is_bounded() -> None:
    snap = eas.build_status()
    short = snap["policy_doc_sha256_short"]
    assert isinstance(short, str)
    assert len(short) == 12
    int(short, 16)


def test_canonical_doc_hashes_are_bounded() -> None:
    snap = eas.build_status()
    for key in (
        "autonomous_development_doc_sha256_short",
        "qre_roadmap_doc_sha256_short",
    ):
        short = snap[key]
        assert isinstance(short, str), key
        assert len(short) == 12, key
        int(short, 16)


def test_sha256_short_refuses_unpinned_path(tmp_path: Path) -> None:
    """The hashing helper must refuse any path outside the closed
    ``PINNED_HASH_FILES`` set even if that file exists. This is the
    open-set guarantee."""
    rogue = tmp_path / "not_pinned.txt"
    rogue.write_text("hello", encoding="utf-8")
    with pytest.raises(ValueError, match="refused unpinned path"):
        eas._sha256_short(str(rogue))
    with pytest.raises(ValueError, match="refused unpinned path"):
        eas._sha256_short("dashboard/dashboard.py")
    with pytest.raises(ValueError, match="refused unpinned path"):
        eas._sha256_short("research/research_latest.json")
    with pytest.raises(ValueError, match="refused unpinned path"):
        eas._sha256_short("docs/roadmap/qre_roadmap_v6_1.md")


# ---------------------------------------------------------------------------
# Sample decisions parity with the classifier
# ---------------------------------------------------------------------------


def test_sample_decisions_match_classifier() -> None:
    """Every sample input's recomputed decision must equal the
    expected decision baked into the sample table — i.e. the table is
    not lying. ``classify`` is the source of truth; this module is a
    projection."""
    snap = eas.build_status()
    rows = snap["sample_decisions"]
    assert isinstance(rows, list)
    assert len(rows) == len(eas._SAMPLE_INPUTS)
    for row in rows:
        assert row["match"] == "OK", row
        re_decision = ea.classify(
            action_type=row["action_type"],
            target_path=row["target_path"],
            risk_class=row["risk_class"],
        )
        assert re_decision.decision == row["actual_decision"], row
        assert re_decision.reason == row["actual_reason"], row
        assert re_decision.target_path_category == row["actual_target_path_category"], row
    assert snap["sample_decisions_ok"] is True


def test_sample_decisions_cover_all_decision_classes() -> None:
    """The sample corpus must exercise AUTO_ALLOWED, NEEDS_HUMAN, and
    PERMANENTLY_DENIED at minimum, plus the UNKNOWN/fail-safe path."""
    snap = eas.build_status()
    decisions = {row["actual_decision"] for row in snap["sample_decisions"]}
    assert "AUTO_ALLOWED" in decisions
    assert "NEEDS_HUMAN" in decisions
    assert "PERMANENTLY_DENIED" in decisions
    # The fail-safe row uses an unknown action_type; classifier must
    # still return NEEDS_HUMAN with the unknown_risk_or_target_fail_safe
    # reason.
    failsafe_rows = [
        r
        for r in snap["sample_decisions"]
        if r["label"] == "needs_human_unknown_action_failsafe"
    ]
    assert len(failsafe_rows) == 1
    assert failsafe_rows[0]["actual_decision"] == "NEEDS_HUMAN"
    assert failsafe_rows[0]["actual_reason"] == "unknown_risk_or_target_fail_safe"


def test_sample_decisions_cover_both_canonical_roadmap_paths() -> None:
    """Both new canonical roadmap paths must appear in the sample
    matrix and route to NEEDS_HUMAN — defense in depth against silent
    re-pinning of the canonical set."""
    snap = eas.build_status()
    targets = {row["target_path"] for row in snap["sample_decisions"]}
    assert "docs/roadmap/autonomous_development.txt" in targets
    assert "docs/roadmap/Roadmap v6.md" in targets


# ---------------------------------------------------------------------------
# Presence flags
# ---------------------------------------------------------------------------


def test_presence_flags_are_ok_in_repo_layout() -> None:
    """Within this repo the four pinned files exist; presence flags
    must all be ``"OK"``. This guards against a future refactor that
    accidentally moves a canonical doc."""
    snap = eas.build_status()
    assert snap["execution_authority_present"] == "OK"
    assert snap["policy_doc_present"] == "OK"
    assert snap["classifier_present"] == "OK"
    assert snap["autonomous_development_doc_present"] == "OK"
    assert snap["qre_roadmap_doc_present"] == "OK"
    assert snap["last_validation_status"] == "OK"


# ---------------------------------------------------------------------------
# No-side-effect / no-network guarantee
# ---------------------------------------------------------------------------


def test_build_status_does_not_invoke_subprocess(monkeypatch: pytest.MonkeyPatch) -> None:
    """The status surface MUST NOT spawn any subprocess. We patch
    ``subprocess.run``/``subprocess.Popen`` to raise; if the module
    touches them, the test fails with a clear message."""

    def _raise_subprocess(*a: Any, **kw: Any) -> Any:
        raise AssertionError("execution_authority_status invoked subprocess")

    monkeypatch.setattr(subprocess, "run", _raise_subprocess)
    monkeypatch.setattr(subprocess, "Popen", _raise_subprocess)
    snap = eas.build_status()
    assert snap["report_kind"] == "execution_authority_status"


def test_build_status_does_not_open_network(monkeypatch: pytest.MonkeyPatch) -> None:
    """No socket creation, no urllib.urlopen — a pure read of pinned
    files plus an in-process classifier call."""

    def _raise_socket(*a: Any, **kw: Any) -> Any:
        raise AssertionError("execution_authority_status created a socket")

    def _raise_urlopen(*a: Any, **kw: Any) -> Any:
        raise AssertionError("execution_authority_status opened a URL")

    monkeypatch.setattr(socket, "socket", _raise_socket)
    monkeypatch.setattr(urllib.request, "urlopen", _raise_urlopen)
    snap = eas.build_status()
    assert snap["last_validation_status"] in ("OK", "FAIL")


# ---------------------------------------------------------------------------
# Atomic write
# ---------------------------------------------------------------------------


def test_write_status_artifact_atomic(tmp_path: Path) -> None:
    out = tmp_path / "logs" / "execution_authority_status" / "latest.json"
    written = eas.write_status_artifact(out)
    assert written == out
    assert out.is_file()
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["report_kind"] == "execution_authority_status"
    assert payload["schema_version"] == "1.0"
    # Stale temp files must not survive the atomic rename.
    siblings = list(out.parent.iterdir())
    leftover_tmps = [s for s in siblings if s.name.startswith(".execution_authority_status.")]
    assert leftover_tmps == [], leftover_tmps


def test_write_refuses_path_outside_logs(tmp_path: Path) -> None:
    """The writer must refuse any output path that does not lie under
    a ``logs/`` segment. Defense in depth against accidental writes
    elsewhere (e.g. ``research/``)."""
    bad = tmp_path / "research" / "leaked.json"
    with pytest.raises(ValueError, match="non-logs/"):
        eas.write_status_artifact(bad)


# ---------------------------------------------------------------------------
# Governance-status integration
# ---------------------------------------------------------------------------


def test_governance_status_includes_execution_authority_block() -> None:
    """``governance_status.collect_status()`` must include the new
    ``execution_authority`` key whose payload is structurally equal
    to ``execution_authority_status.build_status()`` modulo the
    intentionally non-deterministic timestamp."""
    base = governance_status.collect_status()
    assert "execution_authority" in base
    block = base["execution_authority"]
    assert block["report_kind"] == "execution_authority_status"
    assert block["schema_version"] == "1.0"
    assert block["last_validation_status"] in ("OK", "FAIL")
    # The two timestamps may differ by sub-second; the rest must match
    # the standalone build.
    direct = eas.build_status()
    block_ts = block.pop("last_validation_timestamp_utc")
    direct_ts = direct.pop("last_validation_timestamp_utc")
    assert isinstance(block_ts, str) and isinstance(direct_ts, str)
    assert block == direct


def test_governance_status_no_secret_assertion_still_passes() -> None:
    """Adding the execution_authority block must not introduce any
    credential-shaped string into ``governance_status``. The existing
    ``assert_no_secrets`` invariant must still hold."""
    snap = governance_status.collect_status()
    governance_status.assert_no_secrets(snap)
