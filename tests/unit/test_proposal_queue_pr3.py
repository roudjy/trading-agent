"""v3.15.16.10 PR-3 / A5 — proposal_queue actionable-heading filter.

These tests pin the new behaviour added in PR-3:

* H2/H3 segments without an explicit actionable payload are
  suppressed (Roadmap headings are not automatic proposals).
* Explicit ``Proposal:`` / ``Risk:`` / ``risk_class:`` /
  ``Decision:`` / ``Status:`` / ``affected_files:`` /
  ``proposal_type:`` markers in body → actionable.
* Backtick-quoted concrete file paths in body → actionable.
* Strategic-roadmap / governance / tooling / CI tokens → actionable.
* Generic words like ``release`` or ``version`` (or version numbers)
  are NOT actionable on their own.
* ``# heading`` lines inside fenced code blocks are not parsed.
* Preamble (lines before the first heading) never surfaces.
* ``--diagnose-id`` reverse-derives (source, title, line) from a
  proposal_id.
* Archive-subdirectory skip and H1-skip remain unchanged
  (regression guards).

All fixtures are synthetic and deterministic — no runtime logs,
no /tmp baselines.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from reporting import proposal_queue as pq


@pytest.fixture
def isolated_pq(tmp_path: Path) -> Path:
    return tmp_path


def test_h2_without_actionable_payload_is_suppressed(
    isolated_pq: Path,
) -> None:
    """Generic explanatory H2s — Purpose / Status / Scope / Why /
    Required behavior / Success criteria — must NOT auto-surface.
    They are documentation structure, not proposals."""
    src = isolated_pq / "explanatory.md"
    src.write_text(
        "# Document title\n\n"
        "## Purpose\n\n"
        "Make routing behavior-aware instead of preset-count-aware.\n\n"
        "## Scope\n\n"
        "Allowed actions are listed below.\n\n"
        "## Status\n\n"
        "Active.\n\n"
        "## Required behavior\n\n"
        "The system must continue to detect explicit blocks.\n\n"
        "## Success criteria\n\n"
        "Operator can see authority health without reading code.\n\n"
        "## Why here in roadmap\n\n"
        "The natural transition point.\n",
        encoding="utf-8",
    )
    snap = pq.collect_snapshot(mode="dry-run", source=str(src))
    assert snap["proposals"] == [], snap["proposals"]


def test_h2_with_explicit_marker_in_body_is_kept(isolated_pq: Path) -> None:
    """Body containing an explicit Proposal: marker -> actionable."""
    src = isolated_pq / "marked.md"
    src.write_text(
        "# Document title\n\n"
        "## Migrate observability surface\n\n"
        "Proposal: rotate the digest format for clarity.\n",
        encoding="utf-8",
    )
    snap = pq.collect_snapshot(mode="dry-run", source=str(src))
    titles = [p["title"] for p in snap["proposals"]]
    assert titles == ["Migrate observability surface"], titles


def test_h2_with_inline_risk_class_marker_is_kept(isolated_pq: Path) -> None:
    """Inline ``risk_class: LOW.`` mid-prose still counts as an
    actionable marker (parser-expected metadata format)."""
    src = isolated_pq / "inline_marker.md"
    src.write_text(
        "# Document title\n\n"
        "## Add a read-only digest\n\n"
        "Add a small reporting digest. risk_class: LOW.\n",
        encoding="utf-8",
    )
    snap = pq.collect_snapshot(mode="dry-run", source=str(src))
    titles = [p["title"] for p in snap["proposals"]]
    assert "Add a read-only digest" in titles


def test_h2_with_backticked_path_is_kept(isolated_pq: Path) -> None:
    """A body that names a concrete file via backticks -> actionable
    (proposal points at a specific file)."""
    src = isolated_pq / "path_marker.md"
    src.write_text(
        "# Document title\n\n"
        "## Replace the digest writer\n\n"
        "The new writer lives at `reporting/foo.py`.\n",
        encoding="utf-8",
    )
    snap = pq.collect_snapshot(mode="dry-run", source=str(src))
    titles = [p["title"] for p in snap["proposals"]]
    assert "Replace the digest writer" in titles


def test_preamble_lines_never_emit_proposals(isolated_pq: Path) -> None:
    """Lines before the first heading must not produce a proposal,
    even if they contain marker-shaped tokens. Preamble is doc
    structure, not a shippable item."""
    src = isolated_pq / "preamble.md"
    src.write_text(
        "Proposal: this is a leading prose paragraph that mentions\n"
        "Proposal: words but is not a heading.\n\n"
        "# Document title\n\n"
        "## Genuine actionable item\n\nrisk_class: LOW.\n",
        encoding="utf-8",
    )
    snap = pq.collect_snapshot(mode="dry-run", source=str(src))
    titles = [p["title"] for p in snap["proposals"]]
    assert "Genuine actionable item" in titles
    # Preamble must not appear as a separate proposal.
    assert "<preamble>" not in titles


def test_fenced_code_headings_are_not_treated_as_headings(
    isolated_pq: Path,
) -> None:
    """``# heading`` lines inside a fenced code block must NOT be
    parsed as headings. This pins the noise pattern from
    ``docs/roadmap/Roadmap v6.md`` where fenced ```text blocks
    contain pseudo-headings like ``# v3.15.16``."""
    src = isolated_pq / "fenced.md"
    src.write_text(
        "# Document title\n\n"
        "## Genuine actionable item\n\n"
        "Proposal: surface a real item.\n\n"
        "```text\n"
        "# v3.15.16 - Intelligent Routing Layer\n"
        "## v3.15.17 - Sampling Intelligence\n"
        "### v3.15.18 - Research Observability Expansion\n"
        "```\n",
        encoding="utf-8",
    )
    snap = pq.collect_snapshot(mode="dry-run", source=str(src))
    titles = [p["title"] for p in snap["proposals"]]
    assert "Genuine actionable item" in titles
    # The pseudo-headings inside the fence must not produce proposals.
    assert "v3.15.16 - Intelligent Routing Layer" not in titles
    assert "v3.15.17 - Sampling Intelligence" not in titles
    assert "v3.15.18 - Research Observability Expansion" not in titles


def test_fenced_code_headings_with_tilde_fence(isolated_pq: Path) -> None:
    """Tilde fences (``~~~``) are also recognized as code blocks."""
    src = isolated_pq / "tilde_fence.md"
    src.write_text(
        "# Document title\n\n"
        "## Real item\n\nrisk_class: MEDIUM.\n\n"
        "~~~text\n"
        "## fake heading inside tilde fence\n"
        "~~~\n",
        encoding="utf-8",
    )
    snap = pq.collect_snapshot(mode="dry-run", source=str(src))
    titles = [p["title"] for p in snap["proposals"]]
    assert titles == ["Real item"], titles


def test_release_tag_alone_is_not_actionable(isolated_pq: Path) -> None:
    """A heading that contains a release tag (``v3.15.16``) but no
    explicit marker / path / governance / tooling token must NOT
    auto-surface. Generic words like ``release`` or ``version`` -
    or version numbers - are not actionable on their own."""
    src = isolated_pq / "release_tag_only.md"
    src.write_text(
        "# Document title\n\n"
        "## v3.15.16 - Intelligent Routing Layer\n\n"
        "Make campaign routing behavior-aware. This describes the\n"
        "future product phase but carries no actionable proposal\n"
        "metadata.\n",
        encoding="utf-8",
    )
    snap = pq.collect_snapshot(mode="dry-run", source=str(src))
    assert snap["proposals"] == [], snap["proposals"]


def test_release_tag_with_explicit_marker_is_actionable(
    isolated_pq: Path,
) -> None:
    """Release-tagged heading with an explicit marker DOES surface."""
    src = isolated_pq / "release_tag_marked.md"
    src.write_text(
        "# Document title\n\n"
        "## v3.15.16.10 - Phase B classifier\n\n"
        "Decision: ship the deterministic classifier.\n",
        encoding="utf-8",
    )
    snap = pq.collect_snapshot(mode="dry-run", source=str(src))
    titles = [p["title"] for p in snap["proposals"]]
    assert "v3.15.16.10 - Phase B classifier" in titles


def test_strategic_roadmap_token_in_body_is_actionable(
    isolated_pq: Path,
) -> None:
    """Bodies containing existing closed STRATEGIC_ROADMAP_TOKENS
    (e.g. ``canonical roadmap``) continue to surface - these are
    legitimate high-risk governance signals."""
    src = isolated_pq / "strategic.md"
    src.write_text(
        "# Document title\n\n"
        "## Adopt new plan\n\n"
        "Replace the canonical roadmap with the new plan.\n",
        encoding="utf-8",
    )
    snap = pq.collect_snapshot(mode="dry-run", source=str(src))
    rows = snap["proposals"]
    assert rows, rows
    assert any(p["risk_class"] == "HIGH" for p in rows), rows


def test_governance_token_is_actionable(isolated_pq: Path) -> None:
    """Bodies mentioning governance tokens (e.g. ``branch protection``,
    ``CODEOWNERS``, ``release gate``) continue to surface."""
    src = isolated_pq / "governance.md"
    src.write_text(
        "# Document title\n\n"
        "## Tighten branch protection\n\n"
        "Update branch protection to require a green release gate.\n",
        encoding="utf-8",
    )
    snap = pq.collect_snapshot(mode="dry-run", source=str(src))
    titles = [p["title"] for p in snap["proposals"]]
    assert "Tighten branch protection" in titles


def test_archive_subdir_skip_unchanged(isolated_pq: Path) -> None:
    """Regression: ``archive/`` subdirectory is still skipped.
    Archived material does not generate active queue noise."""
    archive_dir = isolated_pq / "archive"
    archive_dir.mkdir()
    (archive_dir / "old.md").write_text(
        "# Old\n\n## Add ruff\n\nMIT license, dev-only.\n",
        encoding="utf-8",
    )
    (isolated_pq / "active.md").write_text(
        "# Active\n\n## Add ruff\n\nMIT license, dev-only.\n",
        encoding="utf-8",
    )
    snap = pq.collect_snapshot(mode="dry-run", source=str(isolated_pq))
    sources = sorted({p["source"] for p in snap["proposals"]})
    # Cross-platform: archive paths can serialize as either separator.
    assert all("archive/" not in s and "archive\\" not in s for s in sources)


def test_h1_skip_unchanged(isolated_pq: Path) -> None:
    """Regression: H1 is still skipped unconditionally even when its
    body mentions tokens that would otherwise be actionable."""
    src = isolated_pq / "h1_with_marker_body.md"
    src.write_text(
        "# Title\n\n"
        "Proposal: this is preamble after the H1, not a shippable item.\n",
        encoding="utf-8",
    )
    snap = pq.collect_snapshot(mode="dry-run", source=str(src))
    titles = [p["title"] for p in snap["proposals"]]
    assert "Title" not in titles
    # Preamble after an H1 is not a heading and must not surface.
    assert "<preamble>" not in titles


def test_diagnose_id_returns_source_title_line(isolated_pq: Path) -> None:
    """``--diagnose-id`` must reverse-derive (source, title, line)
    from a known proposal_id by replaying _proposal_id over default
    sources."""
    src = isolated_pq / "synthetic.md"
    src.write_text(
        "# Document title\n\n"
        "## A real proposal\n\nrisk_class: LOW.\n",
        encoding="utf-8",
    )
    snap = pq.collect_snapshot(mode="dry-run", source=str(src))
    assert snap["proposals"], snap
    target_id = snap["proposals"][0]["proposal_id"]
    title = snap["proposals"][0]["title"]
    result = pq._diagnose_id(target_id, sources=[src])
    assert result["report_kind"] == "proposal_queue_diagnose_id"
    assert result["target_id"] == target_id
    assert result["matches"], result
    matched = result["matches"][0]
    assert matched["title"] == title
    assert matched["heading_level"] in (2, 3)
    assert matched["line_idx"] >= 0


def test_diagnose_id_rejects_malformed_id(isolated_pq: Path) -> None:
    result = pq._diagnose_id("not_a_proposal_id", sources=[])
    assert result["matches"] == []
    assert "expected proposal_id" in result["error"]


def test_diagnose_id_no_match_returns_empty(isolated_pq: Path) -> None:
    src = isolated_pq / "empty.md"
    src.write_text(
        "# Title\n\n## A heading\n\nrisk_class: LOW.\n", encoding="utf-8"
    )
    result = pq._diagnose_id("p_deadbeef", sources=[src])
    assert result["matches"] == []
    assert result["error"] == "no_match_found_in_default_sources"


def test_canonical_roadmap_v6_explanatory_h2s_do_not_surface(
    isolated_pq: Path,
) -> None:
    """Synthetic mirror of the canonical Roadmap v6.md authoring
    style: every release section uses generic explanatory H2s with
    no actionable markers. None of them must surface."""
    src = isolated_pq / "roadmap_v6_synthetic.md"
    src.write_text(
        "# Quant Research Engine - Roadmap v6\n\n"
        "## Semantic Versioning Transition\n\nThe roadmap restructures.\n\n"
        "## Purpose of this roadmap\n\nThis roadmap restructures the QRE.\n\n"
        "## Current State\n\nv3.15.15.9.\n\n"
        "## Why this matters\n\nDescribes motivation.\n\n"
        "# v3.15.16 - Intelligent Routing Layer\n\n"
        "## Purpose\n\nMake campaign routing behavior-aware.\n\n"
        "## What it does\n\nIntroduces smarter routing.\n\n"
        "## What it adds\n\nReduced exploration entropy.\n\n"
        "## Why here in roadmap\n\nTransition point.\n\n"
        "## What follows next\n\nv3.15.17 - Sampling Intelligence.\n",
        encoding="utf-8",
    )
    snap = pq.collect_snapshot(mode="dry-run", source=str(src))
    assert snap["proposals"] == [], snap["proposals"]


def test_autonomous_development_synthetic_h2s_do_not_surface(
    isolated_pq: Path,
) -> None:
    """Synthetic mirror of the canonical autonomous_development.txt
    authoring style: A3-A7 sections use Purpose / Scope / Required
    behavior / Success criteria H2s. None of them must surface."""
    src = isolated_pq / "autonomous_development_synthetic.md"
    src.write_text(
        "# Autonomous Development Track\n\n"
        "# A3 - Read-only reporting exposure\n\n"
        "## Purpose\n\nMake the classifier visible.\n\n"
        "## Scope\n\nRead-only only.\n\n"
        "## Success criteria\n\nOperator sees health.\n\n"
        "# A5 - Proposal queue cleanup\n\n"
        "## Purpose\n\nReduce noise.\n\n"
        "## Required behavior\n\nDetect explicit blocks.\n",
        encoding="utf-8",
    )
    snap = pq.collect_snapshot(mode="dry-run", source=str(src))
    assert snap["proposals"] == [], snap["proposals"]


def test_actionable_filter_is_pure_no_subprocess() -> None:
    """The new ``_is_actionable_heading`` must be pure (no I/O).
    Pinning the source for a static check."""
    src = Path(pq.__file__).read_text(encoding="utf-8")
    # The function exists.
    assert "_is_actionable_heading" in src
    # The marker regex exists and is the closed lexicon.
    assert "_MARKER_RE" in src
    # No subprocess in the module overall.
    assert "import subprocess" not in src
    assert "from subprocess" not in src
