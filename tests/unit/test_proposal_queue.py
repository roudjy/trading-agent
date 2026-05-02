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
        "# Adopt canonical roadmap v4\n\n"
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
        "# v3.15.15.20 — touch live gate\n\n"
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
        "# Add Datadog\n\nWire Datadog APM. Requires an API key.\n",
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
        "# Add ruff\n\nMIT license, dev-only, no telemetry.\n",
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
        "# v3.15.15.42 — repeatable\n\nThis is a release candidate.\n",
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
            "# Adopt canonical roadmap v4\n\nNew roadmap.\n\n"
            "# Add ruff\n\nMIT license, dev-only, no telemetry.\n\n"
            "# CI hygiene\n\nGitHub Actions SHA pin sweep.\n"
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
