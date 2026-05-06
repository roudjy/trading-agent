"""Unit tests for v3.15.16.10 PR-4 / A6 — autonomous backlog discipline.

Synthetic deterministic fixtures only — no operator-runtime logs, no
``/tmp`` baselines committed. The recurring-maintenance integration is
verified at the registry level only (no scheduling tick).
"""

from __future__ import annotations

import json
import socket
import subprocess
import urllib.request
from pathlib import Path
from typing import Any

import pytest

from reporting import autonomous_backlog_summary as abs_
from reporting import execution_authority as ea
from reporting import recurring_maintenance as rm


# ---------------------------------------------------------------------------
# Fixture helpers
# ---------------------------------------------------------------------------


def _write_pq(
    tmp_path: Path,
    proposals: list[dict[str, Any]],
) -> Path:
    pq = tmp_path / "proposal_queue.json"
    pq.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "report_kind": "proposal_queue_digest",
                "proposals": proposals,
            }
        ),
        encoding="utf-8",
    )
    return pq


@pytest.fixture(autouse=True)
def _isolate_prior_ledger(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> Path:
    """Every test starts with an empty prior-id ledger pointed at a
    fresh tmp path. Otherwise the operator's real
    ``logs/autonomous_backlog/last_seen_proposal_ids.json`` would
    leak in and pollute stale-detection assertions."""
    ledger = tmp_path / "logs" / "autonomous_backlog" / "last_seen_proposal_ids.json"
    monkeypatch.setattr(abs_, "PRIOR_IDS_LEDGER", ledger)
    return ledger


def _proposal(
    pid: str,
    *,
    title: str = "x",
    source: str = "docs/roadmap/Roadmap v6.md",
    affected: list[str] | None = None,
    risk_class: str = "MEDIUM",
    proposal_type: str = "approval_required",
    status: str = "proposed",
) -> dict[str, Any]:
    return {
        "proposal_id": pid,
        "title": title,
        "source": source,
        "affected_files": affected if affected is not None else [],
        "risk_class": risk_class,
        "proposal_type": proposal_type,
        "status": status,
    }


# ---------------------------------------------------------------------------
# Schema / shape
# ---------------------------------------------------------------------------


def test_groups_vocabulary_is_closed_and_exhaustive() -> None:
    """The five required groups are present and the order is stable."""
    assert abs_.GROUPS == (
        "permanently_denied",
        "needs_human",
        "auto_allowed",
        "stale_or_resolved",
        "unknown_failsafe",
    )


def test_artifact_path_is_under_logs_not_research() -> None:
    assert abs_.ARTIFACT_RELATIVE_PATH.startswith("logs/")
    assert "research/" not in abs_.ARTIFACT_RELATIVE_PATH


def test_collect_snapshot_top_level_keys(tmp_path: Path) -> None:
    pq = _write_pq(tmp_path, [])
    snap = abs_.collect_snapshot(
        proposal_queue_path=pq, persist_prior_ids=False
    )
    expected = {
        "schema_version",
        "module_version",
        "report_kind",
        "generated_at_utc",
        "source_path",
        "source_available",
        "groups",
        "counts",
        "execution_authority_module_version",
    }
    assert set(snap.keys()) == expected
    assert snap["report_kind"] == "autonomous_backlog_summary"
    assert snap["schema_version"] == "1.0"
    assert set(snap["groups"].keys()) == set(abs_.GROUPS)
    assert set(snap["counts"].keys()) == set(abs_.GROUPS) | {"total"}


def test_missing_proposal_queue_yields_empty_groups(tmp_path: Path) -> None:
    snap = abs_.collect_snapshot(
        proposal_queue_path=tmp_path / "does_not_exist.json",
        persist_prior_ids=False,
    )
    assert snap["source_available"] is False
    for g in abs_.GROUPS:
        assert snap["groups"][g] == []
    assert snap["counts"]["total"] == 0


# ---------------------------------------------------------------------------
# Classification boundaries
# ---------------------------------------------------------------------------


def test_frozen_contract_routes_to_permanently_denied(tmp_path: Path) -> None:
    pq = _write_pq(
        tmp_path,
        [
            _proposal(
                "p_aaaa1111",
                affected=["research/research_latest.json"],
                risk_class="HIGH",
            )
        ],
    )
    snap = abs_.collect_snapshot(
        proposal_queue_path=pq, persist_prior_ids=False
    )
    assert snap["counts"]["permanently_denied"] == 1
    row = snap["groups"]["permanently_denied"][0]
    assert row["execution_authority_decision"] == "PERMANENTLY_DENIED"


def test_canonical_roadmap_routes_to_needs_human(tmp_path: Path) -> None:
    """Both new canonical roadmap paths must route to NEEDS_HUMAN."""
    for canonical in (
        "docs/roadmap/Roadmap v6.md",
        "docs/roadmap/autonomous_development.txt",
    ):
        pq = _write_pq(
            tmp_path,
            [
                _proposal(
                    "p_canon000",
                    affected=[canonical],
                    risk_class="HIGH",
                )
            ],
        )
        snap = abs_.collect_snapshot(
            proposal_queue_path=pq, persist_prior_ids=False
        )
        assert snap["counts"]["needs_human"] == 1, canonical
        row = snap["groups"]["needs_human"][0]
        assert row["execution_authority_reason"] == "high_risk_canonical_roadmap_change"


def test_doc_non_policy_low_routes_to_auto_allowed(tmp_path: Path) -> None:
    pq = _write_pq(
        tmp_path,
        [
            _proposal(
                "p_auto0001",
                affected=["docs/operator/note.md"],
                risk_class="LOW",
            )
        ],
    )
    snap = abs_.collect_snapshot(
        proposal_queue_path=pq, persist_prior_ids=False
    )
    assert snap["counts"]["auto_allowed"] == 1


def test_unknown_risk_routes_to_unknown_failsafe(tmp_path: Path) -> None:
    """A proposal with an unknown ``risk_class`` for a non-trivial
    target falls through to the classifier's fail-safe NEEDS_HUMAN
    with reason ``unknown_risk_or_target_fail_safe``. The bucketer
    must lift this into ``unknown_failsafe`` (separate from the
    governance-shaped ``needs_human`` bucket)."""
    # Using "other" category (path with no recognized classification)
    # and an unknown risk pushes the classifier through risk-class
    # escalation to the fail-safe reason.
    pq = _write_pq(
        tmp_path,
        [
            _proposal(
                "p_unk00001",
                affected=["random/path.py"],
                risk_class="UNKNOWN",
            )
        ],
    )
    snap = abs_.collect_snapshot(
        proposal_queue_path=pq, persist_prior_ids=False
    )
    assert snap["counts"]["unknown_failsafe"] == 1
    row = snap["groups"]["unknown_failsafe"][0]
    assert row["execution_authority_reason"] == "unknown_risk_or_target_fail_safe"


def test_archive_path_routes_to_stale_or_resolved(tmp_path: Path) -> None:
    pq = _write_pq(
        tmp_path,
        [
            _proposal(
                "p_arch0001",
                source="docs/roadmap/archive/qre_roadmap_v6_1.md",
                affected=["docs/roadmap/archive/qre_roadmap_v6_1.md"],
                risk_class="LOW",
            )
        ],
    )
    snap = abs_.collect_snapshot(
        proposal_queue_path=pq, persist_prior_ids=False
    )
    assert snap["counts"]["stale_or_resolved"] == 1
    assert snap["counts"]["auto_allowed"] == 0


def test_disappeared_proposal_id_routes_to_stale_or_resolved(
    tmp_path: Path, _isolate_prior_ledger: Path
) -> None:
    """A proposal_id present in the prior ledger but absent from the
    current snapshot is bucketed as stale_or_resolved with reason
    ``stale_proposal_id_disappeared``."""
    ledger = _isolate_prior_ledger
    ledger.parent.mkdir(parents=True, exist_ok=True)
    ledger.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "module_version": "test",
                "saved_at_utc": "2026-05-06T00:00:00Z",
                "proposal_ids": ["p_zombi001", "p_alive001"],
            }
        ),
        encoding="utf-8",
    )
    pq = _write_pq(
        tmp_path,
        [
            _proposal(
                "p_alive001",
                affected=["docs/operator/note.md"],
                risk_class="LOW",
            )
        ],
    )
    snap = abs_.collect_snapshot(
        proposal_queue_path=pq, persist_prior_ids=False
    )
    titles_or_ids = [
        r.get("proposal_id") for r in snap["groups"]["stale_or_resolved"]
    ]
    assert "p_zombi001" in titles_or_ids
    zombie = [
        r
        for r in snap["groups"]["stale_or_resolved"]
        if r.get("proposal_id") == "p_zombi001"
    ][0]
    assert zombie["execution_authority_reason"] == "stale_proposal_id_disappeared"


def test_empty_affected_files_routes_to_stale_when_auto_allowed(
    tmp_path: Path,
) -> None:
    """A proposal with no concrete files, no governance signal in its
    source, must not auto-allow on faith — it's stale until the
    operator names target files. Real high-risk classifications still
    take precedence over the empty-files rule."""
    pq = _write_pq(
        tmp_path,
        [
            _proposal(
                "p_emp00001",
                source="docs/operator/something.md",
                affected=[],
                risk_class="LOW",
            )
        ],
    )
    snap = abs_.collect_snapshot(
        proposal_queue_path=pq, persist_prior_ids=False
    )
    assert snap["counts"]["stale_or_resolved"] == 1
    assert snap["counts"]["auto_allowed"] == 0


def test_canonical_roadmap_with_empty_affected_still_needs_human(
    tmp_path: Path,
) -> None:
    """A proposal whose source is a canonical roadmap doc and whose
    affected_files is empty must NOT slip into stale_or_resolved on
    the empty-files rule — the canonical-roadmap classification wins."""
    pq = _write_pq(
        tmp_path,
        [
            _proposal(
                "p_canemp01",
                source="docs/roadmap/Roadmap v6.md",
                affected=[],
                risk_class="HIGH",
            )
        ],
    )
    snap = abs_.collect_snapshot(
        proposal_queue_path=pq, persist_prior_ids=False
    )
    assert snap["counts"]["needs_human"] == 1
    assert snap["counts"]["stale_or_resolved"] == 0


# ---------------------------------------------------------------------------
# No mutation / no I/O guarantees
# ---------------------------------------------------------------------------


def test_collect_snapshot_does_not_invoke_subprocess(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def _raise(*a: Any, **kw: Any) -> Any:
        raise AssertionError("autonomous_backlog_summary invoked subprocess")

    monkeypatch.setattr(subprocess, "run", _raise)
    monkeypatch.setattr(subprocess, "Popen", _raise)
    pq = _write_pq(tmp_path, [])
    snap = abs_.collect_snapshot(
        proposal_queue_path=pq, persist_prior_ids=False
    )
    assert snap["report_kind"] == "autonomous_backlog_summary"


def test_collect_snapshot_does_not_open_network(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def _raise(*a: Any, **kw: Any) -> Any:
        raise AssertionError("autonomous_backlog_summary opened socket/url")

    monkeypatch.setattr(socket, "socket", _raise)
    monkeypatch.setattr(urllib.request, "urlopen", _raise)
    pq = _write_pq(tmp_path, [])
    abs_.collect_snapshot(proposal_queue_path=pq, persist_prior_ids=False)


def test_module_has_no_subprocess_or_gh_or_git_tokens() -> None:
    """Static check: the module must not import subprocess or invoke
    gh/git. Mirrors the stricter pattern from execution_authority."""
    src = Path(abs_.__file__).read_text(encoding="utf-8")
    assert "import subprocess" not in src
    assert "from subprocess" not in src
    forbidden = ('"gh"', "'gh'", '"git"', "'git'", "Popen")
    for tok in forbidden:
        assert tok not in src, tok


# ---------------------------------------------------------------------------
# Atomic write + logs/-only guard
# ---------------------------------------------------------------------------


def test_atomic_write_refuses_non_logs_path(tmp_path: Path) -> None:
    bad = tmp_path / "research" / "leaked.json"
    with pytest.raises(ValueError, match="non-logs/"):
        abs_._atomic_write_json(bad, {"x": 1})


def test_atomic_write_under_logs_succeeds_and_leaves_no_temp(
    tmp_path: Path,
) -> None:
    out = tmp_path / "logs" / "autonomous_backlog" / "latest.json"
    abs_._atomic_write_json(out, {"hello": "world"})
    assert out.is_file()
    assert json.loads(out.read_text(encoding="utf-8")) == {"hello": "world"}
    leftovers = [
        p
        for p in out.parent.iterdir()
        if p.name.startswith(".autonomous_backlog_summary.")
    ]
    assert leftovers == []


# ---------------------------------------------------------------------------
# recurring_maintenance integration (registry-level only — no tick)
# ---------------------------------------------------------------------------


def test_recurring_maintenance_registers_autonomous_backlog_job() -> None:
    """The new job constant exists, is in JOB_TYPES, and has a
    registry entry with a callable executor and the expected default
    posture (LOW risk, enabled by default, no gh, sane interval)."""
    assert rm.JOB_REFRESH_AUTONOMOUS_BACKLOG == "refresh_autonomous_backlog"
    assert rm.JOB_REFRESH_AUTONOMOUS_BACKLOG in rm.JOB_TYPES
    spec = rm._JOB_REGISTRY[rm.JOB_REFRESH_AUTONOMOUS_BACKLOG]
    assert callable(spec["executor"])
    assert spec["risk_class"] == rm.RISK_LOW
    assert spec["needs_gh"] is False
    assert spec["default_enabled"] is True
    assert spec["default_interval_seconds"] >= 60  # not paranoia, sanity


def test_executor_returns_summary_without_gh_or_subprocess(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The executor delegates to ``run_once(write=True)``. We patch
    the runtime path so the executor exercises the wire-up without
    touching the operator's real ``logs/`` directory."""
    # All artifact paths live under tmp_path/logs/ so the
    # logs/-only atomic-write guard accepts them.
    logs = tmp_path / "logs" / "autonomous_backlog"
    monkeypatch.setattr(abs_, "PROPOSAL_QUEUE_LATEST", tmp_path / "pq.json")
    monkeypatch.setattr(abs_, "ARTIFACT_DIR", logs)
    monkeypatch.setattr(abs_, "ARTIFACT_LATEST", logs / "latest.json")
    monkeypatch.setattr(
        abs_, "PRIOR_IDS_LEDGER", logs / "last_seen_proposal_ids.json"
    )
    (tmp_path / "pq.json").write_text(
        json.dumps({"proposals": []}), encoding="utf-8"
    )
    # Block subprocess / sockets defensively.
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *a, **kw: (_ for _ in ()).throw(
            AssertionError("subprocess called")
        ),
    )
    out = rm._exec_refresh_autonomous_backlog()
    assert "summary" in out
    assert "evidence" in out
    assert out["evidence"]["total"] is not None


# ---------------------------------------------------------------------------
# Classifier vocabulary parity (defense in depth)
# ---------------------------------------------------------------------------


def test_module_uses_same_decision_vocabulary_as_classifier() -> None:
    """The bucket vocabulary must compose with the closed
    ``ea.DECISIONS`` enum. Any drift is caught at import time."""
    assert ea.DECISION_AUTO_ALLOWED == "AUTO_ALLOWED"
    assert ea.DECISION_NEEDS_HUMAN == "NEEDS_HUMAN"
    assert ea.DECISION_PERMANENTLY_DENIED == "PERMANENTLY_DENIED"
    # The bucketer's branches match these decision strings exactly.
    src = Path(abs_.__file__).read_text(encoding="utf-8")
    for tok in (
        "DECISION_AUTO_ALLOWED",
        "DECISION_NEEDS_HUMAN",
        "DECISION_PERMANENTLY_DENIED",
    ):
        assert tok in src, tok
