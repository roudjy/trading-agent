"""Unit tests for ``reporting.proposal_queue``.

Properties enforced (verbatim from the v3.15.15.19 brief):

* large roadmap input produces proposals, NOT execution;
* strategic roadmap adoption is HIGH and ``needs_human``;
* live trading / broker / capital scope is ``blocked_high_risk``;
* free dev-only tooling proposal can be LOW/MEDIUM if no secrets /
  accounts / telemetry;
* hosted / telemetry / token tool proposal is HIGH and ``needs_human``;
* protected paths produce HIGH / ``blocked_protected_path``;
* unknown source produces ``blocked_unknown`` / ``not_available``;
* malformed input does not crash;
* dry-run is the only allowed mode in this release;
* proposal_id is deterministic for the same input;
* JSON snapshot carries every required top-level key.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import pytest

from reporting import proposal_queue as pq

REPO_ROOT = Path(__file__).resolve().parent.parent.parent


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def _write(path: Path, body: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    return path


# ---------------------------------------------------------------------------
# Risk classifier
# ---------------------------------------------------------------------------


def test_strategic_roadmap_adoption_is_high_and_needs_human() -> None:
    risk, reason = pq._classify_risk(
        "roadmap_adoption",
        "Adopt new canonical roadmap v4",
        "Replace the canonical roadmap with the v4 plan.",
        [],
    )
    assert risk == pq.RISK_HIGH
    assert "strategic" in reason.lower()
    status, blocked_reason = pq._decide_status("roadmap_adoption", risk, [])
    assert status == pq.STATUS_NEEDS_HUMAN
    assert blocked_reason is None


def test_live_trading_path_is_blocked_high_risk() -> None:
    files = ["agent/execution/live/broker.py", "automation/live_gate.py"]
    risk, reason = pq._classify_risk(
        "release_candidate",
        "v3.15.15.20 — live broker",
        "Wire live broker.",
        files,
    )
    assert risk == pq.RISK_HIGH
    assert "live" in reason.lower()
    status, blocked_reason = pq._decide_status("release_candidate", risk, files)
    assert status == pq.STATUS_BLOCKED
    assert "live" in (blocked_reason or "").lower()


def test_protected_path_is_blocked_protected_path() -> None:
    files = [".claude/hooks/audit_emit.py"]
    risk, reason = pq._classify_risk(
        "governance_change", "Replace hook", "Replace.", files
    )
    assert risk == pq.RISK_HIGH
    assert "protected" in reason.lower()
    status, blocked_reason = pq._decide_status("governance_change", risk, files)
    assert status == pq.STATUS_BLOCKED
    assert "blocked_protected_path" in (blocked_reason or "")


def test_frozen_contract_path_is_blocked_protected_path() -> None:
    files = ["research/research_latest.json"]
    risk, _ = pq._classify_risk(
        "release_candidate", "Touch frozen", "x.", files
    )
    assert risk == pq.RISK_HIGH
    status, blocked_reason = pq._decide_status("release_candidate", risk, files)
    assert status == pq.STATUS_BLOCKED
    assert "blocked_protected_path" in (blocked_reason or "")


def test_governance_change_is_high_and_needs_human() -> None:
    risk, _ = pq._classify_risk(
        "governance_change",
        "Edit branch protection",
        "Change required-status rules.",
        [],
    )
    assert risk == pq.RISK_HIGH
    status, _ = pq._decide_status("governance_change", risk, [])
    assert status == pq.STATUS_NEEDS_HUMAN


# ---------------------------------------------------------------------------
# Tooling-intake policy
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "body",
    [
        "Add Datadog APM. Requires an API key.",
        "Wire Sentry; needs auth token.",
        "Use the hosted Segment.io ingestion endpoint with telemetry.",
        "Add a paid plan for the SaaS observability service.",
        "OAuth signup to integrate the third-party dashboard.",
    ],
)
def test_tooling_with_secrets_or_telemetry_is_high(body: str) -> None:
    risk, reason = pq._classify_risk(
        "tooling_intake", "Tooling intake — risky", body, []
    )
    assert risk == pq.RISK_HIGH
    assert "secrets" in reason.lower() or "telemetry" in reason.lower()
    status, _ = pq._decide_status("tooling_intake", risk, [])
    assert status == pq.STATUS_NEEDS_HUMAN


@pytest.mark.parametrize(
    "body",
    [
        "Add `vite-plugin-pwa`, MIT license, dev-only, no telemetry.",
        "Bring in an open-source stdlib-only helper, no signup required.",
        "Apache 2.0 dev dependency, no-telemetry.",
    ],
)
def test_tooling_marked_free_dev_only_is_low(body: str) -> None:
    risk, reason = pq._classify_risk(
        "tooling_intake", "Add a free dev-only tool", body, []
    )
    assert risk == pq.RISK_LOW
    assert "dev-only" in reason.lower() or "free" in reason.lower()
    status, _ = pq._decide_status("tooling_intake", risk, [])
    assert status == pq.STATUS_PROPOSED


def test_tooling_without_explicit_marker_is_medium() -> None:
    risk, _ = pq._classify_risk(
        "tooling_intake",
        "Add a tool",
        "Some package that improves devx.",
        [],
    )
    assert risk == pq.RISK_MEDIUM


# ---------------------------------------------------------------------------
# Proposal type classifier
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "title,body,expected",
    [
        (
            "v3.15.15.30 — frontend refactor",
            "Refactor.",
            "release_candidate",
        ),
        (
            "Adopt the new canonical roadmap",
            "Strategic roadmap adoption.",
            "roadmap_adoption",
        ),
        (
            "Roadmap diff vs v3 plan",
            "Diff against the existing canonical roadmap.",
            "roadmap_diff",
        ),
        (
            "Branch protection update",
            "Change CODEOWNERS.",
            "governance_change",
        ),
        (
            "Add ruff",
            "Add ruff as a tool. dev-only.",
            "tooling_intake",
        ),
        (
            "GitHub Actions SHA pin sweep",
            "Update workflow pins.",
            "ci_hygiene",
        ),
        (
            "Requirements bump",
            "dependency cleanup of requirements.txt.",
            "dependency_cleanup",
        ),
        (
            "More logging",
            "observability gap in the workloop.",
            "observability_gap",
        ),
        (
            "Missing tests for X",
            "testing gap; no tests cover Y.",
            "testing_gap",
        ),
        (
            "UX gap on mobile",
            "frontend gap on the dashboard.",
            "ux_gap",
        ),
    ],
)
def test_classify_type(title: str, body: str, expected: str) -> None:
    assert pq._classify_type(title, body, "docs/roadmap/sample.md") == expected


# ---------------------------------------------------------------------------
# Snapshot — happy path on synthetic markdown
# ---------------------------------------------------------------------------


@pytest.fixture
def isolated_pq(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Path:
    monkeypatch.setattr(pq, "DIGEST_DIR_JSON", tmp_path / "dq")
    return tmp_path


def test_dry_run_default_emits_required_top_level_fields(isolated_pq: Path) -> None:
    snap = pq.collect_snapshot(
        mode="dry-run",
        source=None,
        proposals_override=[],  # skip filesystem walk
    )
    required = {
        "schema_version",
        "report_kind",
        "module_version",
        "generated_at_utc",
        "mode",
        "sources",
        "missing_sources",
        "proposals",
        "counts",
        "final_recommendation",
    }
    assert required.issubset(snap.keys())
    assert snap["schema_version"] == pq.SCHEMA_VERSION
    assert snap["mode"] == "dry-run"
    assert snap["report_kind"] == "proposal_queue_digest"
    assert snap["final_recommendation"] == "no_proposals"


def test_non_dry_run_mode_is_refused() -> None:
    """Hard guarantee: only dry-run is allowed in v3.15.15.19."""
    snap = pq.collect_snapshot(mode="execute-safe")
    assert snap.get("status") == "refused"
    assert "dry-run" in snap.get("reason", "")
    assert snap["proposals"] == []


def test_strategic_roadmap_doc_yields_high_needs_human(
    isolated_pq: Path,
) -> None:
    src = isolated_pq / "roadmap_v4.md"
    src.write_text(
        "# Roadmap test fixture\n\n"
        "## Adopt canonical roadmap v4\n\n"
        "Replace the existing roadmap with this new canonical roadmap.\n",
        encoding="utf-8",
    )
    snap = pq.collect_snapshot(mode="dry-run", source=str(src))
    assert any(
        p["risk_class"] == "HIGH" and p["status"] == "needs_human"
        for p in snap["proposals"]
    ), snap["proposals"]


def test_release_candidate_with_protected_path_is_blocked(
    isolated_pq: Path,
) -> None:
    src = isolated_pq / "rc.md"
    src.write_text(
        "# Release candidate test fixture\n\n"
        "## v3.15.15.20 — touch live gate\n\n"
        "Modify `automation/live_gate.py` to wire the broker.\n",
        encoding="utf-8",
    )
    snap = pq.collect_snapshot(mode="dry-run", source=str(src))
    rows = snap["proposals"]
    assert rows, "expected at least one proposal"
    blocking = [r for r in rows if r["status"] == "blocked"]
    assert blocking, "expected the live-gate row to be blocked"
    reasons = " ".join((r["blocked_reason"] or "") for r in blocking)
    assert "live" in reasons or "protected" in reasons


def test_tooling_intake_marked_secrets_is_high(isolated_pq: Path) -> None:
    src = isolated_pq / "tooling.md"
    src.write_text(
        "# Tooling test fixture\n\n"
        "## Add Datadog\n\nWire Datadog APM. Requires an API key.\n",
        encoding="utf-8",
    )
    snap = pq.collect_snapshot(mode="dry-run", source=str(src))
    assert any(
        p["risk_class"] == "HIGH" and p["proposal_type"] == "tooling_intake"
        for p in snap["proposals"]
    )


def test_tooling_intake_marked_free_is_low(isolated_pq: Path) -> None:
    src = isolated_pq / "free_tool.md"
    src.write_text(
        "# Tooling test fixture\n\n"
        "## Add ruff\n\nMIT license, dev-only, no telemetry.\n",
        encoding="utf-8",
    )
    snap = pq.collect_snapshot(mode="dry-run", source=str(src))
    rows = [p for p in snap["proposals"] if p["proposal_type"] == "tooling_intake"]
    assert rows, snap
    assert all(p["risk_class"] == "LOW" for p in rows)
    assert all(p["status"] == "proposed" for p in rows)


def test_unknown_source_yields_blocked_unknown_or_missing(
    isolated_pq: Path,
) -> None:
    snap = pq.collect_snapshot(
        mode="dry-run", source=str(isolated_pq / "does_not_exist.md")
    )
    # Either blocked_unknown row OR missing_sources entry — both are
    # acceptable representations of "the operator pointed at nothing".
    blocked_rows = [p for p in snap["proposals"] if p["status"] == "blocked"]
    has_blocked = any(
        (r.get("blocked_reason") or "").startswith("blocked_unknown")
        or r.get("proposal_type") == "blocked_unknown"
        for r in blocked_rows
    )
    has_missing = bool(snap["missing_sources"])
    assert has_blocked or has_missing


def test_malformed_input_does_not_crash(isolated_pq: Path) -> None:
    src = isolated_pq / "garbled.md"
    # Non-utf8 content via raw bytes that decode-error on utf-8.
    src.write_bytes(b"\xff\xfe\xff\xfe# title\nbroken")
    snap = pq.collect_snapshot(mode="dry-run", source=str(src))
    # Either a blocked_unknown row OR an empty proposals list — both
    # are valid; the requirement is that we did not crash.
    assert "proposals" in snap


def test_proposal_id_is_deterministic(isolated_pq: Path) -> None:
    src = isolated_pq / "x.md"
    src.write_text(
        "# Repeatable test fixture\n\n"
        "## v3.15.15.42 — repeatable\n\nThis is a release candidate.\n",
        encoding="utf-8",
    )
    snap1 = pq.collect_snapshot(mode="dry-run", source=str(src))
    snap2 = pq.collect_snapshot(mode="dry-run", source=str(src))
    ids1 = sorted(p["proposal_id"] for p in snap1["proposals"])
    ids2 = sorted(p["proposal_id"] for p in snap2["proposals"])
    assert ids1 == ids2 and ids1


def test_counts_aggregate_correctly(isolated_pq: Path) -> None:
    src = isolated_pq / "mix.md"
    src.write_text(
        (
            "# Mixed test fixture\n\n"
            "## Adopt canonical roadmap v4\n\nNew roadmap.\n\n"
            "## Add ruff\n\nMIT license, dev-only, no telemetry.\n\n"
            "## CI hygiene\n\nGitHub Actions SHA pin sweep.\n"
        ),
        encoding="utf-8",
    )
    snap = pq.collect_snapshot(mode="dry-run", source=str(src))
    counts = snap["counts"]
    assert counts["total"] == len(snap["proposals"])
    # Adoption is HIGH; ruff (free) is LOW; CI hygiene is MEDIUM.
    assert counts["by_risk"].get("HIGH", 0) >= 1
    assert counts["by_risk"].get("LOW", 0) >= 1


# ---------------------------------------------------------------------------
# H1 ingestion bugfix — H1 is the document title, never a shippable item.
# ---------------------------------------------------------------------------
#
# By the documented authoring convention used by every intake doc under
# DEFAULT_SOURCE_ROOTS (docs/roadmap, docs/backlog, docs/spillovers),
# H1 = document title; shippable items are at H2 / H3. An H1 with a
# non-empty preamble body otherwise self-classifies as a fresh
# roadmap_adoption / governance_change proposal via trigger tokens
# in the rationale text — false positive.


def test_h1_with_empty_body_is_skipped(isolated_pq: Path) -> None:
    """Regression guard: H1 with empty body remains skipped (existing
    behavior before the bugfix)."""
    src = isolated_pq / "empty_body.md"
    src.write_text("# Document title\n", encoding="utf-8")
    snap = pq.collect_snapshot(mode="dry-run", source=str(src))
    assert snap["proposals"] == []


def test_h1_with_non_empty_body_is_skipped(isolated_pq: Path) -> None:
    """The bugfix: H1 with a preamble body is ALSO skipped. Previously
    this body would be classified through the type/risk/status pipeline
    and emit a proposal record. Now: skipped."""
    src = isolated_pq / "h1_with_preamble.md"
    src.write_text(
        "# Document title\n\n"
        "This is a self-describing preamble. It explains the doc and may "
        "mention canonical post-v3.15 phases. It is not a shippable item.\n",
        encoding="utf-8",
    )
    snap = pq.collect_snapshot(mode="dry-run", source=str(src))
    assert snap["proposals"] == [], snap["proposals"]


def test_h2_after_h1_with_preamble_still_produces_proposal(
    isolated_pq: Path,
) -> None:
    """H2 after a non-empty-body H1 is still ingested. The H1 body
    being skipped must NOT mute H2/H3 ingestion."""
    src = isolated_pq / "h1_then_h2.md"
    src.write_text(
        "# Document title\n\n"
        "Doc-level preamble describing the file purpose.\n\n"
        "## Add ruff\n\nMIT license, dev-only, no telemetry.\n",
        encoding="utf-8",
    )
    snap = pq.collect_snapshot(mode="dry-run", source=str(src))
    titles = [p["title"] for p in snap["proposals"]]
    assert "Document title" not in titles
    assert "Add ruff" in titles


def test_h3_still_produces_proposal(isolated_pq: Path) -> None:
    """H3 ingestion is unchanged — these are the canonical shippable
    items in the v6.1 roadmap convention."""
    src = isolated_pq / "h3_item.md"
    src.write_text(
        "# Document title\n\n"
        "## Release group\n\n"
        "### v3.15.15.50 — observability addition\n\n"
        "Add a read-only digest. risk_class: LOW.\n",
        encoding="utf-8",
    )
    snap = pq.collect_snapshot(mode="dry-run", source=str(src))
    titles = [p["title"] for p in snap["proposals"]]
    assert "Document title" not in titles
    assert "v3.15.15.50 — observability addition" in titles


def test_h1_skipped_even_when_body_contains_strategic_roadmap_token(
    isolated_pq: Path,
) -> None:
    """Specifically pin the canonical case that motivated this fix:
    an H1 whose body contains the substring "post-v3.15" (which is in
    STRATEGIC_ROADMAP_TOKENS and otherwise triggers
    roadmap_adoption / HIGH / needs_human classification) must be
    skipped rather than emitted as a proposal."""
    src = isolated_pq / "qre_roadmap_v6_1_like.md"
    src.write_text(
        "# Roadmap v6.1 — Quant Research Engine\n\n"
        "> Canonical, structured roadmap for the post-v3.15.16.0 phase of the\n"
        "> Quant Research Engine. This document is parsed by the ingester.\n",
        encoding="utf-8",
    )
    snap = pq.collect_snapshot(mode="dry-run", source=str(src))
    assert snap["proposals"] == [], snap["proposals"]


def test_h1_skipped_even_when_body_contains_governance_token(
    isolated_pq: Path,
) -> None:
    """Cousin pin: an H1 whose body contains a governance token (e.g.
    "release gate") must also be skipped — the fix is unconditional."""
    src = isolated_pq / "governance_doc.md"
    src.write_text(
        "# Agent governance retrospective\n\n"
        "Build the safety perimeter required before agents are given any "
        "autonomy. Ordering: secrets first, then CI, then release gate.\n",
        encoding="utf-8",
    )
    snap = pq.collect_snapshot(mode="dry-run", source=str(src))
    assert snap["proposals"] == [], snap["proposals"]


# ---------------------------------------------------------------------------
# Archive-subdirectory skip — _expand_source must honor the operator's
# git-mv-into-archive convention.
# ---------------------------------------------------------------------------
#
# Operators move historical retrospectives into a subdirectory named
# ``archive`` (e.g. ``docs/roadmap/archive/<retrospective>.md``) to opt
# them out of fresh ingestion. The recursive walker must skip files
# under any directory segment named ``archive`` (case-insensitive). The
# filter operates on path *components* only — a top-level filename
# containing the word ``archive`` is NOT skipped.


def test_archive_subdirectory_is_skipped(isolated_pq: Path) -> None:
    """Direct ``archive/`` subdirectory: files inside are excluded; a
    sibling file at the source root is still included."""
    archive_dir = isolated_pq / "archive"
    archive_dir.mkdir()
    (archive_dir / "old_retrospective.md").write_text(
        "# Historical title\n\n"
        "## Goal\n\nLegacy goal that should not re-emit a proposal.\n",
        encoding="utf-8",
    )
    (isolated_pq / "active.md").write_text(
        "# Active doc\n\n## Add ruff\n\nMIT license, dev-only.\n",
        encoding="utf-8",
    )
    files = pq._expand_source(isolated_pq)
    rels = sorted(p.name for p in files)
    assert rels == ["active.md"], rels


def test_nested_archive_subdirectory_is_skipped(isolated_pq: Path) -> None:
    """Nested ``sub/archive/...`` is also skipped — the rule matches
    any directory segment in the relative path, not just the first."""
    nested = isolated_pq / "sub" / "archive" / "deep"
    nested.mkdir(parents=True)
    (nested / "buried.md").write_text("# t\n", encoding="utf-8")
    files = pq._expand_source(isolated_pq)
    assert files == []


@pytest.mark.parametrize("segment", ["Archive", "ARCHIVE", "ArCHive"])
def test_archive_segment_match_is_case_insensitive(
    isolated_pq: Path, segment: str
) -> None:
    """``Archive/``, ``ARCHIVE/``, ``ArCHive/`` segments are all
    skipped. One fresh tmp_path per parameter — Windows filesystems
    are case-insensitive, so each variant needs an isolated
    workspace."""
    d = isolated_pq / segment
    d.mkdir()
    (d / "x.md").write_text("# t\n", encoding="utf-8")
    (isolated_pq / "active.md").write_text(
        "# active\n\n## body\n", encoding="utf-8"
    )
    files = pq._expand_source(isolated_pq)
    rels = sorted(p.name for p in files)
    assert rels == ["active.md"], rels


def test_archive_in_filename_outside_archive_dir_is_not_skipped(
    isolated_pq: Path,
) -> None:
    """A *filename* containing the word ``archive`` at the root of the
    source tree is NOT a directory segment and must still be ingested.
    Skipping by filename would over-exclude legitimate operator docs
    such as ``archive_strategy_sketch.md`` placed alongside live items."""
    (isolated_pq / "archive_strategy_sketch.md").write_text(
        "# Doc title\n\n## Some idea\n\nbody\n", encoding="utf-8"
    )
    (isolated_pq / "archived_quarterly_review.md").write_text(
        "# Doc title\n\n## Notes\n\nbody\n", encoding="utf-8"
    )
    files = pq._expand_source(isolated_pq)
    rels = sorted(p.name for p in files)
    assert rels == [
        "archive_strategy_sketch.md",
        "archived_quarterly_review.md",
    ], rels


def test_normal_markdown_files_are_still_included(isolated_pq: Path) -> None:
    """Regression guard: ordinary subdirectories without the ``archive``
    name continue to be walked recursively. This pins that the
    archive-skip rule is narrow."""
    sub = isolated_pq / "subdir"
    sub.mkdir()
    (sub / "nested.md").write_text("# t\n\n## item\n\nbody\n", encoding="utf-8")
    (isolated_pq / "top.md").write_text("# t\n\n## item\n\nbody\n", encoding="utf-8")
    files = pq._expand_source(isolated_pq)
    rels = sorted(str(p.relative_to(isolated_pq)).replace("\\", "/") for p in files)
    assert rels == ["subdir/nested.md", "top.md"], rels


# ---------------------------------------------------------------------------
# Frozen contract integrity
# ---------------------------------------------------------------------------


def test_frozen_contracts_byte_identical_around_snapshot(
    isolated_pq: Path,
) -> None:
    """The intake run must not mutate frozen contract files."""
    paths = [
        REPO_ROOT / "research" / "research_latest.json",
        REPO_ROOT / "research" / "strategy_matrix.csv",
    ]
    before = {p.name: _file_sha256(p) for p in paths if p.exists()}
    pq.collect_snapshot(mode="dry-run", source=str(isolated_pq))
    after = {p.name: _file_sha256(p) for p in paths if p.exists()}
    assert before == after


# ---------------------------------------------------------------------------
# CLI — stdout + persistence
# ---------------------------------------------------------------------------


def test_cli_dry_run_default_writes_no_files_with_no_write(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(pq, "DIGEST_DIR_JSON", tmp_path / "dq")
    rc = pq.main(["--mode", "dry-run", "--no-write", "--source", str(tmp_path)])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["mode"] == "dry-run"
    assert not (tmp_path / "dq").exists()


def test_cli_dry_run_persists_to_logs_dir(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(pq, "DIGEST_DIR_JSON", tmp_path / "dq")
    src = tmp_path / "x.md"
    src.write_text("# h1\n\nbody\n", encoding="utf-8")
    rc = pq.main(["--mode", "dry-run", "--source", str(src)])
    assert rc == 0
    capsys.readouterr()
    latest = (tmp_path / "dq" / "latest.json").read_text(encoding="utf-8")
    assert json.loads(latest)["report_kind"] == "proposal_queue_digest"


# ---------------------------------------------------------------------------
# Module-level invariants (paranoid static checks)
# ---------------------------------------------------------------------------


def test_no_subprocess_import_in_module() -> None:
    src = Path(pq.__file__).read_text(encoding="utf-8")
    assert "import subprocess" not in src
    assert "from subprocess" not in src


def test_no_gh_or_git_invocation_in_module() -> None:
    src = Path(pq.__file__).read_text(encoding="utf-8")
    forbidden = ('"gh"', "'gh'", '"git"', "'git'", "Popen")
    for token in forbidden:
        assert token not in src, f"forbidden token in proposal_queue.py: {token!r}"
