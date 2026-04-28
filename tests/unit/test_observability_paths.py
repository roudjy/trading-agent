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
