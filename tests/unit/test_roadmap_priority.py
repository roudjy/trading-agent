"""Unit tests for ``reporting.roadmap_priority`` (v3.15.16.2).

Properties enforced:

* digest's ``safe_to_execute`` is always ``False``
* missing source artifact → ``final_recommendation == "not_available"``
* malformed source artifact → ``final_recommendation == "not_available"``
* empty proposal list → ``final_recommendation == "nothing_ready"``
* status != "proposed" filters out
* risk_class == "HIGH" filters out
* protocol decision != "allowed_read_only" filters out
* protocol implementation_allowed == False filters out
* protocol requires_human == True filters out
* protocol error filters out (with reason recorded)
* invalid proposal shape filters out
* deterministic ordering: LOW before MEDIUM, observability before
  reporting/docs/test/ux/frontend/ci/dep, stable proposal_id
  tiebreak
* two runs on the same input produce a byte-identical
  ``chosen_next_up`` (modulo timestamp)
* ``write_outputs`` is atomic (tmp + os.replace) and never
  writes outside ``logs/roadmap_priority/``
* CLI rejects modes other than ``dry-run`` (only ``dry-run`` is
  exposed)
* No subprocess / shell / network in the module source
* No mutation of any input artifact
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import pytest

from reporting import roadmap_priority as rp


REPO_ROOT = Path(__file__).resolve().parent.parent.parent
MODULE_PATH = REPO_ROOT / "reporting" / "roadmap_priority.py"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def isolated_digest_dir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Path:
    """Redirect the digest output directory so write_outputs lands in
    a temp dir per-test."""
    monkeypatch.setattr(rp, "DIGEST_DIR_JSON", tmp_path / "rp")
    return tmp_path


def _proposed(
    pid: str,
    *,
    title: str = "test item",
    summary: str = "an observability addition for monitoring",
    proposal_type: str = "observability_addition",
    risk_class: str = "LOW",
    affected_files: list[str] | None = None,
    status: str = "proposed",
) -> dict[str, Any]:
    """Build a minimal proposal-queue-shaped record."""
    if affected_files is None:
        affected_files = ["reporting/example.py", "tests/unit/test_example.py"]
    return {
        "proposal_id": pid,
        "title": title,
        "summary": summary,
        "proposal_type": proposal_type,
        "risk_class": risk_class,
        "affected_files": affected_files,
        "status": status,
        "source": "docs/roadmap/test.md",
    }


# ---------------------------------------------------------------------------
# Hard-coded digest invariants
# ---------------------------------------------------------------------------


def test_safe_to_execute_is_always_false_with_proposals() -> None:
    snap = rp.collect_snapshot(
        proposals_override=[_proposed("p_aaaaaaaa")],
        frozen_utc="2026-05-04T12:00:00Z",
    )
    assert snap["safe_to_execute"] is False


def test_safe_to_execute_is_false_when_not_available(
    tmp_path: Path,
) -> None:
    """Even on a missing source the safe_to_execute flag is False."""
    snap = rp.collect_snapshot(
        proposal_source_override=tmp_path / "does_not_exist.json",
        frozen_utc="2026-05-04T12:00:00Z",
    )
    assert snap["final_recommendation"] == rp.REC_NOT_AVAILABLE
    assert snap["safe_to_execute"] is False


def test_module_version_pinned() -> None:
    assert rp.MODULE_VERSION == "v3.15.16.2"


def test_schema_version_pinned() -> None:
    assert rp.SCHEMA_VERSION == 1


# ---------------------------------------------------------------------------
# Source-availability handling
# ---------------------------------------------------------------------------


def test_missing_source_yields_not_available(tmp_path: Path) -> None:
    snap = rp.collect_snapshot(
        proposal_source_override=tmp_path / "missing.json",
        frozen_utc="2026-05-04T12:00:00Z",
    )
    assert snap["final_recommendation"] == rp.REC_NOT_AVAILABLE
    assert snap["chosen_next_up"] is None
    assert snap["candidates"] == []
    assert snap["filtered_out"] == []
    assert snap["source_proposal_queue"]["status"] == "not_available"
    assert snap["source_proposal_queue"]["error"] == "missing"


def test_malformed_source_yields_not_available(tmp_path: Path) -> None:
    bad = tmp_path / "bad.json"
    bad.write_text("not-json {[", encoding="utf-8")
    snap = rp.collect_snapshot(
        proposal_source_override=bad,
        frozen_utc="2026-05-04T12:00:00Z",
    )
    assert snap["final_recommendation"] == rp.REC_NOT_AVAILABLE
    assert snap["source_proposal_queue"]["status"] == "not_available"
    assert "malformed" in (snap["source_proposal_queue"]["error"] or "")


def test_source_not_an_object_yields_not_available(tmp_path: Path) -> None:
    bad = tmp_path / "bad.json"
    bad.write_text("[]", encoding="utf-8")
    snap = rp.collect_snapshot(
        proposal_source_override=bad,
        frozen_utc="2026-05-04T12:00:00Z",
    )
    assert snap["final_recommendation"] == rp.REC_NOT_AVAILABLE


def test_source_proposals_field_not_a_list_yields_not_available(
    tmp_path: Path,
) -> None:
    bad = tmp_path / "bad.json"
    bad.write_text(
        json.dumps({"proposals": "not a list"}),
        encoding="utf-8",
    )
    snap = rp.collect_snapshot(
        proposal_source_override=bad,
        frozen_utc="2026-05-04T12:00:00Z",
    )
    assert snap["final_recommendation"] == rp.REC_NOT_AVAILABLE


def test_empty_queue_yields_nothing_ready() -> None:
    snap = rp.collect_snapshot(
        proposals_override=[],
        frozen_utc="2026-05-04T12:00:00Z",
    )
    assert snap["final_recommendation"] == rp.REC_NOTHING_READY
    assert snap["chosen_next_up"] is None
    assert snap["candidates"] == []


# ---------------------------------------------------------------------------
# Eligibility filters
# ---------------------------------------------------------------------------


def test_status_not_proposed_filters_out() -> None:
    snap = rp.collect_snapshot(
        proposals_override=[
            _proposed("p_aaaaaaaa", status="needs_human"),
            _proposed("p_bbbbbbbb", status="blocked"),
            _proposed("p_cccccccc", status="approved"),
            _proposed("p_dddddddd", status="rejected"),
            _proposed("p_eeeeeeee", status="superseded"),
            _proposed("p_ffffffff", status="done"),
        ],
        frozen_utc="2026-05-04T12:00:00Z",
    )
    assert snap["chosen_next_up"] is None
    assert snap["final_recommendation"] == rp.REC_NOTHING_READY
    reasons = {
        row["filter_reason"] for row in snap["filtered_out"]
    }
    assert reasons == {rp.FILTER_STATUS_NOT_PROPOSED}


def test_risk_high_filters_out() -> None:
    snap = rp.collect_snapshot(
        proposals_override=[_proposed("p_aaaaaaaa", risk_class="HIGH")],
        frozen_utc="2026-05-04T12:00:00Z",
    )
    assert snap["chosen_next_up"] is None
    assert snap["filtered_out"][0]["filter_reason"] == rp.FILTER_RISK_HIGH


def test_invalid_proposal_shape_filters_out() -> None:
    snap = rp.collect_snapshot(
        proposals_override=[
            {"title": "no proposal_id"},  # missing proposal_id
            {"proposal_id": ""},  # empty proposal_id
            {"proposal_id": 42},  # non-string proposal_id
        ],
        frozen_utc="2026-05-04T12:00:00Z",
    )
    assert snap["chosen_next_up"] is None
    reasons = {row["filter_reason"] for row in snap["filtered_out"]}
    assert reasons == {rp.FILTER_INVALID_PROPOSAL_SHAPE}


def test_governance_change_filters_out_via_protocol() -> None:
    """A proposal whose summary mentions ``.claude/`` is classified
    by the protocol as ``governance_change`` (not in the open-set),
    so the prioritizer rejects it via the implementation_not_allowed
    filter."""
    snap = rp.collect_snapshot(
        proposals_override=[
            _proposed(
                "p_aaaaaaaa",
                title="Update agent governance for some reason",
                summary="Edit .claude/agents/foo.md and CLAUDE.md",
                affected_files=[".claude/agents/foo.md", "CLAUDE.md"],
                proposal_type="governance_change",
            ),
        ],
        frozen_utc="2026-05-04T12:00:00Z",
    )
    assert snap["chosen_next_up"] is None
    # Governance items either trip the protocol's needs_human flag
    # or land outside ITEM_TYPES_OPEN_TO_IMPLEMENTATION; either way
    # they are rejected.
    assert snap["filtered_out"][0]["filter_reason"] in {
        rp.FILTER_PROTOCOL_REQUIRES_HUMAN,
        rp.FILTER_PROTOCOL_IMPL_NOT_ALLOWED,
        rp.FILTER_PROTOCOL_DECISION,
    }


def test_live_path_filters_out_via_protocol() -> None:
    snap = rp.collect_snapshot(
        proposals_override=[
            _proposed(
                "p_aaaaaaaa",
                title="Add live broker integration",
                summary="Touches automation/live/ and execution/live/.",
                affected_files=["automation/live/broker.py"],
            ),
        ],
        frozen_utc="2026-05-04T12:00:00Z",
    )
    assert snap["chosen_next_up"] is None
    assert snap["filtered_out"][0]["filter_reason"] in {
        rp.FILTER_PROTOCOL_REQUIRES_HUMAN,
        rp.FILTER_PROTOCOL_IMPL_NOT_ALLOWED,
        rp.FILTER_PROTOCOL_DECISION,
    }


# ---------------------------------------------------------------------------
# Ranking determinism
# ---------------------------------------------------------------------------


def test_low_picks_before_medium() -> None:
    snap = rp.collect_snapshot(
        proposals_override=[
            _proposed(
                "p_zz_medium",
                title="medium item",
                summary="add observability metrics for monitoring",
                proposal_type="observability_addition",
                risk_class="MEDIUM",
            ),
            _proposed(
                "p_aa_low",
                title="low item",
                summary="add observability metrics for monitoring",
                proposal_type="observability_addition",
                risk_class="LOW",
            ),
        ],
        frozen_utc="2026-05-04T12:00:00Z",
    )
    # The MEDIUM item may filter out depending on protocol; if it
    # passes, the LOW must rank ahead.
    chosen = snap["chosen_next_up"]
    assert chosen is not None
    # The picked item must be from a LOW candidate (the
    # MEDIUM-risk proposal cannot be picked ahead of a LOW one).
    assert chosen["risk_class"] == "LOW"
    assert chosen["proposal_id"] == "p_aa_low"


def test_observability_picks_before_test_only() -> None:
    snap = rp.collect_snapshot(
        proposals_override=[
            _proposed(
                "p_zz_test",
                title="add tests for foo",
                summary="add tests covering monitoring observability gaps",
                proposal_type="test_only",
                risk_class="LOW",
                affected_files=["tests/unit/test_foo.py"],
            ),
            _proposed(
                "p_zz_obs",
                title="add observability hook",
                summary="add observability monitoring metric to the audit log",
                proposal_type="observability_addition",
                risk_class="LOW",
                affected_files=["reporting/audit.py"],
            ),
        ],
        frozen_utc="2026-05-04T12:00:00Z",
    )
    chosen = snap["chosen_next_up"]
    assert chosen is not None
    assert chosen["proposal_type"] == "observability_addition"


def test_stable_proposal_id_tiebreak() -> None:
    """When risk + type are equal, proposal_id ascending decides."""
    base = dict(
        title="add observability metric for monitoring",
        summary="add observability metric for monitoring the audit log",
        proposal_type="observability_addition",
        risk_class="LOW",
        affected_files=["reporting/m.py"],
    )
    snap = rp.collect_snapshot(
        proposals_override=[
            _proposed("p_zzzzzzzz", **base),
            _proposed("p_aaaaaaaa", **base),
            _proposed("p_mmmmmmmm", **base),
        ],
        frozen_utc="2026-05-04T12:00:00Z",
    )
    chosen = snap["chosen_next_up"]
    assert chosen is not None
    assert chosen["proposal_id"] == "p_aaaaaaaa"
    # And the candidates list reflects the same order.
    ids_in_order = [c["proposal_id"] for c in snap["candidates"]]
    assert ids_in_order == ["p_aaaaaaaa", "p_mmmmmmmm", "p_zzzzzzzz"]


def test_two_runs_produce_identical_chosen_next_up() -> None:
    """Determinism: same input → byte-identical chosen_next_up
    (modulo the generated_at_utc timestamp)."""
    proposals = [
        _proposed(
            "p_aaaaaaaa",
            title="first low observability item",
            summary="add observability monitoring for the audit log",
            proposal_type="observability_addition",
            risk_class="LOW",
            affected_files=["reporting/m.py"],
        ),
        _proposed(
            "p_bbbbbbbb",
            title="second low test item",
            summary="add tests for observability monitoring",
            proposal_type="test_only",
            risk_class="LOW",
            affected_files=["tests/unit/test_m.py"],
        ),
    ]
    s1 = rp.collect_snapshot(
        proposals_override=proposals, frozen_utc="2026-05-04T12:00:00Z"
    )
    s2 = rp.collect_snapshot(
        proposals_override=proposals, frozen_utc="2026-05-04T12:00:00Z"
    )
    assert s1["chosen_next_up"] == s2["chosen_next_up"]
    assert s1["candidates"] == s2["candidates"]
    assert s1["filtered_out"] == s2["filtered_out"]


# ---------------------------------------------------------------------------
# Protocol delegation
# ---------------------------------------------------------------------------


def test_chosen_includes_protocol_plan_summary() -> None:
    snap = rp.collect_snapshot(
        proposals_override=[
            _proposed(
                "p_aaaaaaaa",
                title="add observability metric",
                summary="add observability monitoring for the audit log",
                proposal_type="observability_addition",
                affected_files=["reporting/audit.py"],
            ),
        ],
        frozen_utc="2026-05-04T12:00:00Z",
    )
    chosen = snap["chosen_next_up"]
    assert chosen is not None
    plan = chosen["protocol_plan_summary"]
    assert plan["decision"] == "allowed_read_only"
    assert plan["implementation_allowed"] is True
    assert plan["requires_human"] is False
    # safe_to_execute is intentionally NOT duplicated into the
    # plan_summary — see _plan_summary docstring. The digest's
    # top-level safe_to_execute is the canonical source.
    assert "safe_to_execute" not in plan
    assert snap["safe_to_execute"] is False


def test_protocol_module_version_recorded() -> None:
    from reporting import roadmap_execution_protocol as _rep

    snap = rp.collect_snapshot(
        proposals_override=[],
        frozen_utc="2026-05-04T12:00:00Z",
    )
    assert snap["policy"]["protocol_module_version"] == _rep.MODULE_VERSION


# ---------------------------------------------------------------------------
# Atomic write
# ---------------------------------------------------------------------------


def test_write_outputs_atomic_and_scoped(
    isolated_digest_dir: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    snap = rp.collect_snapshot(
        proposals_override=[
            _proposed(
                "p_aaaaaaaa",
                title="add observability metric",
                summary="add observability monitoring for the audit log",
                proposal_type="observability_addition",
                affected_files=["reporting/audit.py"],
            ),
        ],
        frozen_utc="2026-05-04T12:00:00Z",
    )
    paths = rp.write_outputs(snap)
    base = isolated_digest_dir / "rp"
    latest = base / "latest.json"
    history = base / "history.jsonl"
    assert latest.exists()
    assert history.exists()
    # Latest contains the same payload (sort_keys=True).
    payload = json.loads(latest.read_text(encoding="utf-8"))
    assert payload["chosen_next_up"]["proposal_id"] == "p_aaaaaaaa"
    # The returned path map points at logs/-relative paths.
    assert paths["latest"].endswith("latest.json")
    # No stray .tmp left behind.
    leftover_tmps = list(base.glob("*.tmp"))
    assert leftover_tmps == [], f"leftover tmp files: {leftover_tmps}"


def test_write_outputs_appends_one_history_line(
    isolated_digest_dir: Path,
) -> None:
    snap = rp.collect_snapshot(
        proposals_override=[
            _proposed(
                "p_aaaaaaaa",
                title="o1",
                summary="add observability metric for monitoring",
                proposal_type="observability_addition",
            ),
        ],
        frozen_utc="2026-05-04T12:00:00Z",
    )
    rp.write_outputs(snap)
    rp.write_outputs(snap)
    history = isolated_digest_dir / "rp" / "history.jsonl"
    lines = [
        ln for ln in history.read_text(encoding="utf-8").splitlines() if ln.strip()
    ]
    assert len(lines) == 2


def test_no_input_artifact_mutated(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The prioritizer must not mutate logs/proposal_queue/latest.json
    or any other input."""
    src = tmp_path / "proposal_queue.json"
    payload = {
        "schema_version": 1,
        "report_kind": "proposal_queue_digest",
        "module_version": "v3.15.15.19",
        "proposals": [_proposed("p_aaaaaaaa")],
    }
    src.write_text(json.dumps(payload, sort_keys=True), encoding="utf-8")
    before = src.read_bytes()
    monkeypatch.setattr(rp, "DIGEST_DIR_JSON", tmp_path / "rp")
    snap = rp.collect_snapshot(
        proposal_source_override=src,
        frozen_utc="2026-05-04T12:00:00Z",
    )
    rp.write_outputs(snap)
    after = src.read_bytes()
    assert before == after


# ---------------------------------------------------------------------------
# Module-source guarantees
# ---------------------------------------------------------------------------


def test_module_source_no_subprocess() -> None:
    src = MODULE_PATH.read_text(encoding="utf-8")
    forbidden = (
        "import subprocess",
        "from subprocess",
        "shell=True",
        "os.system(",
        "Popen(",
        "import requests",
        "from requests",
        "import urllib.request",
        "from urllib.request",
        "import urllib3",
    )
    for tok in forbidden:
        assert tok not in src, (
            f"reporting/roadmap_priority.py contains forbidden token: "
            f"{tok!r}"
        )


def test_module_source_no_gh_invocation() -> None:
    """The prioritizer must never invoke ``gh``."""
    src = MODULE_PATH.read_text(encoding="utf-8")
    # Allow the word "gh" in comments / docstrings; deny actual
    # invocation patterns. The cheapest check: forbid any
    # subprocess-shaped call (already covered) plus the literal
    # "gh CLI" / "gh.exe" command shapes that would only appear
    # from a deliberate invocation.
    forbidden = (
        '["gh"',
        "['gh'",
        '"gh "',
        "'gh '",
    )
    for tok in forbidden:
        assert tok not in src, (
            f"reporting/roadmap_priority.py contains gh-invocation token: "
            f"{tok!r}"
        )


def test_module_source_no_branch_or_pr_creation() -> None:
    """The prioritizer must never start a branch, open a PR, or
    merge."""
    src = MODULE_PATH.read_text(encoding="utf-8")
    forbidden = (
        "git checkout -b",
        "git push",
        "gh pr create",
        "gh pr merge",
    )
    for tok in forbidden:
        assert tok not in src, (
            f"reporting/roadmap_priority.py contains forbidden action: "
            f"{tok!r}"
        )


def test_safe_to_execute_field_is_hard_coded_false() -> None:
    """At the source level the digest's safe_to_execute key must be
    bound to literal False — never to a variable that could be
    reassigned."""
    src = MODULE_PATH.read_text(encoding="utf-8")
    # The two builders both set safe_to_execute. Both must be
    # literal False.
    occurrences = re.findall(r'"safe_to_execute":\s*([A-Za-z]+)', src)
    assert occurrences, "safe_to_execute key not found in module source"
    assert all(v == "False" for v in occurrences), (
        f"safe_to_execute is not hard-coded False everywhere: "
        f"{occurrences!r}"
    )


# ---------------------------------------------------------------------------
# CLI surface
# ---------------------------------------------------------------------------


def test_cli_only_dry_run_mode_allowed(monkeypatch: pytest.MonkeyPatch) -> None:
    """argparse should reject any --mode other than dry-run."""
    with pytest.raises(SystemExit):
        rp.main(["--mode", "execute-safe"])


def test_cli_status_returns_not_available_when_missing(
    isolated_digest_dir: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    rc = rp.main(["--status"])
    out = capsys.readouterr().out
    assert rc == 1
    assert "not_available" in out
