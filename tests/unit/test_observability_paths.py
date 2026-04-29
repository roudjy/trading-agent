"""Path consistency drift test.

Verifies that the path literals in
``research/observability/paths.py`` still match the writer modules'
``*_PATH`` constants. Done by parsing the writer modules as TEXT
(no ``import``) so this test never triggers any module-level code.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parents[2]
RESEARCH_DIR = PROJECT_ROOT / "research"

# Each entry: (filename_to_find, writer_module_filename)
#
# We assert the bare filename appears both in research/observability/paths.py
# (so the observability layer is tracking it) and in the writer module
# under research/ (so the runtime writer is still producing it under that
# name). Substring presence — not full-line equality — so wrapping /
# whitespace differences don't break the drift check.
DRIFT_CHECKS = [
    ("campaign_registry_latest.v1.json", "campaign_registry.py"),
    ("campaign_queue_latest.v1.json", "campaign_queue.py"),
    ("campaign_digest_latest.v1.json", "campaign_digest.py"),
    ("screening_evidence_latest.v1.json", "screening_evidence.py"),
    ("public_artifact_status_latest.v1.json", "public_artifact_status.py"),
    ("discovery_sprint_progress_latest.v1.json", "discovery_sprint.py"),
    ("sprint_registry_latest.v1.json", "discovery_sprint.py"),
    # v3.15.15.7 — pin the campaign event ledger filename. The launcher
    # writes ``campaign_evidence_ledger_latest.v1.jsonl`` (the project's
    # universal ``_latest.v1`` snapshot-current convention). Pre-v3.15.15.7
    # the diagnostics constant was missing the suffix, causing a silent
    # ``ledger_available=false`` on every read. This row prevents the
    # regression from recurring on either side of the drift.
    ("campaign_evidence_ledger_latest.v1.jsonl", "campaign_launcher.py"),
]


@pytest.mark.parametrize(
    "filename, writer_filename",
    DRIFT_CHECKS,
    ids=[f"{c[0]}-vs-{c[1]}" for c in DRIFT_CHECKS],
)
def test_writer_module_still_uses_filename(filename: str, writer_filename: str):
    paths_py = (
        PROJECT_ROOT / "research" / "diagnostics" / "paths.py"
    ).read_text(encoding="utf-8")
    assert filename in paths_py, (
        f"paths.py no longer mentions {filename!r}; "
        f"observability path constants are out of date."
    )

    writer_text = (RESEARCH_DIR / writer_filename).read_text(encoding="utf-8")
    assert filename in writer_text, (
        f"writer {writer_filename} no longer references {filename!r}; "
        f"observability would silently report this artifact as missing.\n"
        f"Update research/observability/paths.py to track the new filename."
    )


def test_paths_module_does_not_import_other_research_modules():
    """paths.py must import nothing from research.* — single source of truth."""
    text = (
        PROJECT_ROOT / "research" / "diagnostics" / "paths.py"
    ).read_text(encoding="utf-8")
    forbidden = re.findall(
        r"^\s*(?:from|import)\s+research\.(?!diagnostics|_sidecar_io)\S+",
        text,
        flags=re.MULTILINE,
    )
    assert not forbidden, (
        f"paths.py imports forbidden research modules: {forbidden}"
    )


def test_observability_dir_constant_is_fixed():
    """OBSERVABILITY_DIR must be exactly research/observability/."""
    from research.diagnostics.paths import OBSERVABILITY_DIR

    assert (
        str(OBSERVABILITY_DIR).replace("\\", "/")
        == "research/observability"
    )


def test_no_pre_v3_15_15_7_wrong_ledger_path_anywhere_in_diagnostics():
    """Regression guard for the v3.15.15.7 path-bug fix.

    Pre-v3.15.15.7 ``research/diagnostics/paths.py`` carried
    ``CAMPAIGN_EVIDENCE_LEDGER_PATH = RESEARCH_DIR / "campaign_evidence_ledger.jsonl"``
    (no ``_latest.v1`` suffix). The launcher actually writes
    ``campaign_evidence_ledger_latest.v1.jsonl`` — the universal
    snapshot-current convention. The mismatch caused a silent
    ``ledger_available=false`` and ``diagnostic_mode=registry_plus_digest_enriched``
    even though the artifact existed on disk and contained 80+ events.

    This test scans every ``.py`` file under ``research/diagnostics/`` AS TEXT
    (no import) and fails if the OLD wrong filename ever reappears as a string
    literal alongside ``campaign_evidence_ledger`` (the prefix). Allowed: the
    correct full filename ``campaign_evidence_ledger_latest.v1.jsonl``.
    """
    diagnostics_dir = PROJECT_ROOT / "research" / "diagnostics"
    bad_literal = '"campaign_evidence_ledger.jsonl"'
    offenders: list[str] = []
    for py_path in sorted(diagnostics_dir.glob("*.py")):
        text = py_path.read_text(encoding="utf-8")
        if bad_literal in text:
            offenders.append(py_path.name)
    assert not offenders, (
        f"v3.15.15.7 regression: the pre-fix filename "
        f"'campaign_evidence_ledger.jsonl' (no '_latest.v1' suffix) "
        f"reappeared in: {offenders}. The correct constant is "
        f"'campaign_evidence_ledger_latest.v1.jsonl' — see "
        f"research/campaign_launcher.py:139 for the writer side."
    )


def test_campaign_evidence_ledger_path_constant_uses_latest_v1_suffix():
    """Pin the runtime value of ``CAMPAIGN_EVIDENCE_LEDGER_PATH``.

    The drift test above asserts the literal string is in ``paths.py``;
    this test additionally asserts the imported Path object resolves to
    the right filename, so a future refactor that splits the constant
    across multiple lines or adds path joining cannot silently regress.
    """
    from research.diagnostics.paths import CAMPAIGN_EVIDENCE_LEDGER_PATH

    assert (
        CAMPAIGN_EVIDENCE_LEDGER_PATH.name
        == "campaign_evidence_ledger_latest.v1.jsonl"
    ), (
        f"expected filename 'campaign_evidence_ledger_latest.v1.jsonl', "
        f"got {CAMPAIGN_EVIDENCE_LEDGER_PATH.name!r}"
    )
    assert (
        str(CAMPAIGN_EVIDENCE_LEDGER_PATH).replace("\\", "/")
        == "research/campaign_evidence_ledger_latest.v1.jsonl"
    )
