"""Unit tests for ``reporting.approval_inbox``.

Properties enforced (verbatim from the v3.15.15.20 brief):

* proposal with ``roadmap_adoption`` HIGH + ``needs_human`` becomes
  a ``roadmap_adoption_required`` inbox item.
* HIGH PR from github_pr_lifecycle becomes a ``high_risk_pr`` item.
* protected-path proposal becomes a ``protected_path_change`` item.
* free dev-only tooling without telemetry does NOT require approval
  unless risk says so.
* hosted / token / telemetry / paid tooling becomes the appropriate
  external/telemetry/paid item.
* frozen-contract risk becomes a ``frozen_contract_risk`` item.
* live / paper / shadow change becomes
  ``live_paper_shadow_risk_change``.
* unknown / malformed source becomes ``unknown_state``.
* manual dashboard route wiring is represented as
  ``manual_route_wiring_required``.
* ``item_id`` is deterministic.
* No subprocess / no ``gh`` / no ``git`` / no network in pure builder.
* ``dry-run`` is the only allowed mode.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import pytest

from reporting import approval_inbox as ai

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


def _ok_envelope(data: dict) -> dict:
    return {"status": "ok", "path": "test", "reason": None, "data": data}


def _missing_envelope(name: str = "test") -> dict:
    return {
        "status": "not_available",
        "path": name,
        "reason": "missing",
        "data": None,
    }


def _proposal(
    *,
    proposal_id: str = "p_test001",
    title: str = "Sample",
    summary: str = "",
    proposal_type: str = "approval_required",
    risk_class: str = "MEDIUM",
    status: str = "proposed",
    affected_files: list[str] | None = None,
) -> dict:
    return {
        "proposal_id": proposal_id,
        "title": title,
        "summary": summary,
        "proposal_type": proposal_type,
        "risk_class": risk_class,
        "status": status,
        "affected_files": affected_files or [],
    }


def _proposal_envelope(proposals: list[dict]) -> dict:
    return _ok_envelope(
        {
            "schema_version": 1,
            "report_kind": "proposal_queue_digest",
            "proposals": proposals,
        }
    )


def _pr(
    *,
    number: int = 100,
    title: str = "PR title",
    decision: str = "merge_allowed",
    risk_class: str = "LOW",
    protected_paths_touched: bool = False,
    reason: str = "",
    url: str = "",
) -> dict:
    return {
        "number": number,
        "title": title,
        "decision": decision,
        "risk_class": risk_class,
        "protected_paths_touched": protected_paths_touched,
        "reason": reason,
        "url": url,
    }


def _pr_envelope(prs: list[dict]) -> dict:
    return _ok_envelope(
        {"schema_version": 1, "report_kind": "github_pr_lifecycle_digest", "prs": prs}
    )


def _empty_workloop() -> dict:
    return _ok_envelope(
        {
            "schema_version": 1,
            "pr_queue": [],
            "dependabot_queue": [],
            "roadmap_queue": [],
        }
    )


def _empty_governance() -> dict:
    return _ok_envelope(
        {
            "schema_version": 1,
            "audit_chain_status": {"status": "intact", "first_corrupt_index": None},
        }
    )


def _build(sources: dict) -> dict:
    """Run collect_snapshot with overridden sources, suppressing the
    manual-wiring rows (they're tested separately)."""
    return ai.collect_snapshot(
        mode="dry-run",
        sources_override=sources,
        skip_manual_route_items=True,
    )


def _categories(snap: dict) -> list[str]:
    return [it["category"] for it in snap["items"]]


# ---------------------------------------------------------------------------
# Mode boundary
# ---------------------------------------------------------------------------


def test_non_dry_run_mode_is_refused() -> None:
    snap = ai.collect_snapshot(mode="execute-safe")
    assert snap.get("status") == "refused"
    assert "dry-run" in snap.get("reason", "")
    assert snap["items"] == []


# ---------------------------------------------------------------------------
# Proposal-queue projection
# ---------------------------------------------------------------------------


def test_roadmap_adoption_proposal_becomes_inbox_item() -> None:
    sources = {
        "proposal_queue": _proposal_envelope(
            [
                _proposal(
                    title="Adopt canonical roadmap v4",
                    proposal_type="roadmap_adoption",
                    risk_class="HIGH",
                    status="needs_human",
                )
            ]
        ),
        "pr_lifecycle": _pr_envelope([]),
        "workloop": _empty_workloop(),
        "governance_status": _empty_governance(),
    }
    snap = _build(sources)
    cats = _categories(snap)
    assert "roadmap_adoption_required" in cats
    item = next(it for it in snap["items"] if it["category"] == "roadmap_adoption_required")
    assert item["severity"] == "high"
    assert item["status"] == ai.STATUS_OPEN
    assert item["approval_required"] is True
    assert item["related_proposal_id"] == "p_test001"


def test_protected_path_proposal_becomes_protected_path_change() -> None:
    sources = {
        "proposal_queue": _proposal_envelope(
            [
                _proposal(
                    title="Edit hooks",
                    proposal_type="governance_change",
                    risk_class="HIGH",
                    status="blocked",
                    affected_files=[".claude/hooks/audit_emit.py"],
                )
            ]
        ),
        "pr_lifecycle": _pr_envelope([]),
        "workloop": _empty_workloop(),
        "governance_status": _empty_governance(),
    }
    snap = _build(sources)
    cats = _categories(snap)
    assert "protected_path_change" in cats
    item = next(it for it in snap["items"] if it["category"] == "protected_path_change")
    assert item["status"] == ai.STATUS_BLOCKED
    assert ".claude/hooks/audit_emit.py" in item["affected_files"]


def test_frozen_contract_proposal_becomes_frozen_contract_risk() -> None:
    sources = {
        "proposal_queue": _proposal_envelope(
            [
                _proposal(
                    title="Edit frozen contract",
                    proposal_type="release_candidate",
                    risk_class="HIGH",
                    status="blocked",
                    affected_files=["research/research_latest.json"],
                )
            ]
        ),
        "pr_lifecycle": _pr_envelope([]),
        "workloop": _empty_workloop(),
        "governance_status": _empty_governance(),
    }
    snap = _build(sources)
    item = next(
        it for it in snap["items"] if it["category"] == "frozen_contract_risk"
    )
    assert item["severity"] == "critical"
    assert item["status"] == ai.STATUS_BLOCKED


def test_live_trading_proposal_becomes_live_paper_shadow_risk_change() -> None:
    sources = {
        "proposal_queue": _proposal_envelope(
            [
                _proposal(
                    title="Wire live broker",
                    proposal_type="release_candidate",
                    risk_class="HIGH",
                    status="blocked",
                    affected_files=["execution/live/broker.py"],
                )
            ]
        ),
        "pr_lifecycle": _pr_envelope([]),
        "workloop": _empty_workloop(),
        "governance_status": _empty_governance(),
    }
    snap = _build(sources)
    item = next(
        it
        for it in snap["items"]
        if it["category"] == "live_paper_shadow_risk_change"
    )
    assert item["severity"] == "critical"


@pytest.mark.parametrize(
    "summary,expected_category",
    [
        (
            "Add Datadog APM. Requires an API key.",
            "external_account_or_secret_required",
        ),
        ("Wire Sentry telemetry endpoint.", "telemetry_or_data_egress_required"),
        ("Hosted SaaS service with paid plan.", "paid_tool_required"),
        ("OAuth signup integration.", "external_account_or_secret_required"),
    ],
)
def test_high_tooling_proposal_becomes_correct_external_subcategory(
    summary: str, expected_category: str
) -> None:
    sources = {
        "proposal_queue": _proposal_envelope(
            [
                _proposal(
                    title="Tooling intake — risky",
                    summary=summary,
                    proposal_type="tooling_intake",
                    risk_class="HIGH",
                    status="needs_human",
                )
            ]
        ),
        "pr_lifecycle": _pr_envelope([]),
        "workloop": _empty_workloop(),
        "governance_status": _empty_governance(),
    }
    snap = _build(sources)
    cats = _categories(snap)
    assert expected_category in cats, cats


def test_low_tooling_proposal_does_not_create_inbox_item() -> None:
    """Free / dev-only / no-telemetry tooling proposals do not require
    approval — they flow as normal proposed work and should not
    appear in the approval inbox."""
    sources = {
        "proposal_queue": _proposal_envelope(
            [
                _proposal(
                    title="Add ruff",
                    summary="MIT license, dev-only, no telemetry.",
                    proposal_type="tooling_intake",
                    risk_class="LOW",
                    status="proposed",
                )
            ]
        ),
        "pr_lifecycle": _pr_envelope([]),
        "workloop": _empty_workloop(),
        "governance_status": _empty_governance(),
    }
    snap = _build(sources)
    assert snap["items"] == [], snap["items"]


def test_blocked_unknown_proposal_becomes_unknown_state() -> None:
    sources = {
        "proposal_queue": _proposal_envelope(
            [
                _proposal(
                    title="Garbled source",
                    proposal_type="blocked_unknown",
                    risk_class="MEDIUM",
                    status="blocked",
                )
            ]
        ),
        "pr_lifecycle": _pr_envelope([]),
        "workloop": _empty_workloop(),
        "governance_status": _empty_governance(),
    }
    snap = _build(sources)
    cats = _categories(snap)
    assert "unknown_state" in cats


# ---------------------------------------------------------------------------
# PR-lifecycle projection
# ---------------------------------------------------------------------------


def test_high_risk_pr_becomes_inbox_item() -> None:
    sources = {
        "proposal_queue": _proposal_envelope([]),
        "pr_lifecycle": _pr_envelope(
            [
                _pr(
                    number=42,
                    title="numpy major bump",
                    decision="blocked_high_risk",
                    risk_class="HIGH",
                    reason="numpy is on the HIGH-risk list",
                )
            ]
        ),
        "workloop": _empty_workloop(),
        "governance_status": _empty_governance(),
    }
    snap = _build(sources)
    item = next(it for it in snap["items"] if it["category"] == "high_risk_pr")
    assert item["related_pr_number"] == 42
    assert item["severity"] == "high"


def test_pr_with_protected_paths_becomes_protected_path_change() -> None:
    sources = {
        "proposal_queue": _proposal_envelope([]),
        "pr_lifecycle": _pr_envelope(
            [
                _pr(
                    number=43,
                    title="Touch frozen contract",
                    decision="blocked_protected_path",
                    risk_class="HIGH",
                    protected_paths_touched=True,
                    reason="diff touches frozen contract",
                )
            ]
        ),
        "workloop": _empty_workloop(),
        "governance_status": _empty_governance(),
    }
    snap = _build(sources)
    cats = _categories(snap)
    assert "protected_path_change" in cats


def test_failing_checks_pr_becomes_blocked_checks() -> None:
    sources = {
        "proposal_queue": _proposal_envelope([]),
        "pr_lifecycle": _pr_envelope(
            [_pr(number=44, decision="blocked_failing_checks", risk_class="LOW")]
        ),
        "workloop": _empty_workloop(),
        "governance_status": _empty_governance(),
    }
    snap = _build(sources)
    cats = _categories(snap)
    assert "blocked_checks" in cats


def test_behind_pr_becomes_blocked_rebase() -> None:
    sources = {
        "proposal_queue": _proposal_envelope([]),
        "pr_lifecycle": _pr_envelope(
            [_pr(number=45, decision="wait_for_rebase", risk_class="LOW")]
        ),
        "workloop": _empty_workloop(),
        "governance_status": _empty_governance(),
    }
    snap = _build(sources)
    cats = _categories(snap)
    assert "blocked_rebase" in cats


def test_merge_allowed_pr_does_not_create_inbox_item() -> None:
    sources = {
        "proposal_queue": _proposal_envelope([]),
        "pr_lifecycle": _pr_envelope(
            [_pr(number=46, decision="merge_allowed", risk_class="LOW")]
        ),
        "workloop": _empty_workloop(),
        "governance_status": _empty_governance(),
    }
    snap = _build(sources)
    assert snap["items"] == []


def test_pr_conflict_becomes_failed_automation() -> None:
    sources = {
        "proposal_queue": _proposal_envelope([]),
        "pr_lifecycle": _pr_envelope(
            [_pr(number=47, decision="blocked_conflict", risk_class="LOW")]
        ),
        "workloop": _empty_workloop(),
        "governance_status": _empty_governance(),
    }
    snap = _build(sources)
    cats = _categories(snap)
    assert "failed_automation" in cats


# ---------------------------------------------------------------------------
# Workloop projection
# ---------------------------------------------------------------------------


def test_workloop_contract_risk_row_becomes_frozen_contract_risk() -> None:
    sources = {
        "proposal_queue": _proposal_envelope([]),
        "pr_lifecycle": _pr_envelope([]),
        "workloop": _ok_envelope(
            {
                "pr_queue": [
                    {
                        "item_id": "fix/x",
                        "branch_or_pr": "fix/x",
                        "title": "fix x",
                        "risk_class": "needs_human_contract_risk",
                        "decision": "needs_human",
                        "reason": "diff touches frozen contract: research/research_latest.json",
                    }
                ],
                "dependabot_queue": [],
            }
        ),
        "governance_status": _empty_governance(),
    }
    snap = _build(sources)
    cats = _categories(snap)
    assert "frozen_contract_risk" in cats


def test_workloop_trading_risk_row_becomes_live_paper_shadow_risk_change() -> None:
    sources = {
        "proposal_queue": _proposal_envelope([]),
        "pr_lifecycle": _pr_envelope([]),
        "workloop": _ok_envelope(
            {
                "pr_queue": [
                    {
                        "item_id": "fix/y",
                        "branch_or_pr": "fix/y",
                        "title": "fix y",
                        "risk_class": "needs_human_trading_or_risk",
                        "decision": "needs_human",
                        "reason": "live path",
                    }
                ],
                "dependabot_queue": [],
            }
        ),
        "governance_status": _empty_governance(),
    }
    snap = _build(sources)
    cats = _categories(snap)
    assert "live_paper_shadow_risk_change" in cats


# ---------------------------------------------------------------------------
# Governance projection
# ---------------------------------------------------------------------------


def test_broken_audit_chain_becomes_security_alert() -> None:
    sources = {
        "proposal_queue": _proposal_envelope([]),
        "pr_lifecycle": _pr_envelope([]),
        "workloop": _empty_workloop(),
        "governance_status": _ok_envelope(
            {
                "audit_chain_status": {
                    "status": "broken",
                    "first_corrupt_index": 42,
                }
            }
        ),
    }
    snap = _build(sources)
    item = next(it for it in snap["items"] if it["category"] == "security_alert")
    assert item["severity"] == "critical"


# ---------------------------------------------------------------------------
# Missing-source handling
# ---------------------------------------------------------------------------


def test_missing_proposal_queue_becomes_unknown_state_item() -> None:
    sources = {
        "proposal_queue": _missing_envelope("proposal_queue"),
        "pr_lifecycle": _pr_envelope([]),
        "workloop": _empty_workloop(),
        "governance_status": _empty_governance(),
    }
    snap = _build(sources)
    cats = _categories(snap)
    assert "unknown_state" in cats


def test_all_sources_missing_yields_only_unknown_state_items() -> None:
    sources = {
        "proposal_queue": _missing_envelope("proposal_queue"),
        "pr_lifecycle": _missing_envelope("pr_lifecycle"),
        "workloop": _missing_envelope("workloop"),
        "governance_status": _missing_envelope("governance_status"),
    }
    snap = _build(sources)
    assert all(it["category"] == "unknown_state" for it in snap["items"])
    assert len(snap["items"]) == 4


# ---------------------------------------------------------------------------
# Manual route wiring
# ---------------------------------------------------------------------------


def test_manual_route_wiring_items_default_on(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When ``dashboard.py`` is empty / does not yet contain the
    ``register_*_routes`` calls, the inbox emits all three pending
    items."""
    monkeypatch.setattr(ai, "_dashboard_py_text", lambda: "")
    sources = {
        "proposal_queue": _proposal_envelope([]),
        "pr_lifecycle": _pr_envelope([]),
        "workloop": _empty_workloop(),
        "governance_status": _empty_governance(),
    }
    snap = ai.collect_snapshot(mode="dry-run", sources_override=sources)
    cats = _categories(snap)
    assert cats.count("manual_route_wiring_required") == 3


def test_manual_route_wiring_items_clear_when_dashboard_wires_them(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When ``dashboard.py`` actually contains the
    ``register_*_routes(app)`` call AND the matching import, the
    inbox emits NO ``manual_route_wiring_required`` item for that
    module. Detection is a pure substring check on the file text."""
    fake_dashboard = """
# v3.15.15.21 — read-only Agent Control PWA wiring (operator approved).
from dashboard.api_agent_control import register_agent_control_routes
from dashboard.api_proposal_queue import register_proposal_queue_routes
from dashboard.api_approval_inbox import register_approval_inbox_routes

register_agent_control_routes(app)
register_proposal_queue_routes(app)
register_approval_inbox_routes(app)
"""
    monkeypatch.setattr(ai, "_dashboard_py_text", lambda: fake_dashboard)
    sources = {
        "proposal_queue": _proposal_envelope([]),
        "pr_lifecycle": _pr_envelope([]),
        "workloop": _empty_workloop(),
        "governance_status": _empty_governance(),
    }
    snap = ai.collect_snapshot(mode="dry-run", sources_override=sources)
    cats = _categories(snap)
    assert "manual_route_wiring_required" not in cats


def test_manual_route_wiring_partially_wired_yields_remainder(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Only the module whose register call AND import are both
    present is cleared; others remain in the inbox."""
    fake_dashboard = """
from dashboard.api_agent_control import register_agent_control_routes
register_agent_control_routes(app)
"""
    monkeypatch.setattr(ai, "_dashboard_py_text", lambda: fake_dashboard)
    sources = {
        "proposal_queue": _proposal_envelope([]),
        "pr_lifecycle": _pr_envelope([]),
        "workloop": _empty_workloop(),
        "governance_status": _empty_governance(),
    }
    snap = ai.collect_snapshot(mode="dry-run", sources_override=sources)
    items = [
        it for it in snap["items"] if it["category"] == "manual_route_wiring_required"
    ]
    # Two pending: api_proposal_queue, api_approval_inbox.
    assert len(items) == 2
    titles = " ".join(it["title"] for it in items)
    assert "register_proposal_queue_routes" in titles
    assert "register_approval_inbox_routes" in titles
    assert "register_agent_control_routes" not in titles


# ---------------------------------------------------------------------------
# Determinism
# ---------------------------------------------------------------------------


def test_item_id_is_deterministic() -> None:
    sources = {
        "proposal_queue": _proposal_envelope(
            [
                _proposal(
                    title="Adopt canonical roadmap v4",
                    proposal_type="roadmap_adoption",
                    risk_class="HIGH",
                    status="needs_human",
                )
            ]
        ),
        "pr_lifecycle": _pr_envelope([]),
        "workloop": _empty_workloop(),
        "governance_status": _empty_governance(),
    }
    snap1 = _build(sources)
    snap2 = _build(sources)
    ids1 = sorted(it["item_id"] for it in snap1["items"])
    ids2 = sorted(it["item_id"] for it in snap2["items"])
    assert ids1 == ids2 and ids1


# ---------------------------------------------------------------------------
# Schema invariants
# ---------------------------------------------------------------------------


def test_every_item_carries_required_fields() -> None:
    sources = {
        "proposal_queue": _proposal_envelope(
            [
                _proposal(
                    title="Adopt canonical roadmap v4",
                    proposal_type="roadmap_adoption",
                    risk_class="HIGH",
                    status="needs_human",
                )
            ]
        ),
        "pr_lifecycle": _pr_envelope(
            [_pr(number=42, decision="blocked_high_risk", risk_class="HIGH")]
        ),
        "workloop": _empty_workloop(),
        "governance_status": _empty_governance(),
    }
    snap = _build(sources)
    required = {
        "item_id",
        "created_at",
        "source",
        "source_type",
        "title",
        "summary",
        "category",
        "severity",
        "status",
        "risk_class",
        "approval_required",
        "recommended_operator_action",
        "forbidden_agent_actions",
        "evidence",
        "affected_files",
        "related_proposal_id",
        "related_pr_number",
        "related_release_id",
        "dependencies",
        "stale_after",
        "audit_refs",
    }
    for it in snap["items"]:
        assert required.issubset(it.keys())
        # forbidden_agent_actions is the universal hard-no list.
        assert "git push origin main" in it["forbidden_agent_actions"]
        assert "edit .claude/**" in it["forbidden_agent_actions"]


def test_top_level_shape() -> None:
    snap = _build(
        {
            "proposal_queue": _proposal_envelope([]),
            "pr_lifecycle": _pr_envelope([]),
            "workloop": _empty_workloop(),
            "governance_status": _empty_governance(),
        }
    )
    required = {
        "schema_version",
        "report_kind",
        "module_version",
        "generated_at_utc",
        "mode",
        "sources",
        "items",
        "counts",
        "final_recommendation",
    }
    assert required.issubset(snap.keys())
    assert snap["schema_version"] == ai.SCHEMA_VERSION
    assert snap["report_kind"] == "approval_inbox_digest"


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def test_cli_dry_run_default(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(ai, "DIGEST_DIR_JSON", tmp_path / "ai")
    monkeypatch.setattr(ai, "SOURCE_PROPOSAL_QUEUE", tmp_path / "missing-1.json")
    monkeypatch.setattr(ai, "SOURCE_PR_LIFECYCLE", tmp_path / "missing-2.json")
    monkeypatch.setattr(ai, "SOURCE_WORKLOOP", tmp_path / "missing-3.json")
    rc = ai.main(["--mode", "dry-run", "--no-write"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["mode"] == "dry-run"
    assert payload["report_kind"] == "approval_inbox_digest"


# ---------------------------------------------------------------------------
# Frozen contract integrity
# ---------------------------------------------------------------------------


def test_frozen_contracts_byte_identical_around_snapshot() -> None:
    paths = [
        REPO_ROOT / "research" / "research_latest.json",
        REPO_ROOT / "research" / "strategy_matrix.csv",
    ]
    before = {p.name: _file_sha256(p) for p in paths if p.exists()}
    ai.collect_snapshot(
        mode="dry-run",
        sources_override={
            "proposal_queue": _proposal_envelope([]),
            "pr_lifecycle": _pr_envelope([]),
            "workloop": _empty_workloop(),
            "governance_status": _empty_governance(),
        },
        skip_manual_route_items=True,
    )
    after = {p.name: _file_sha256(p) for p in paths if p.exists()}
    assert before == after


# ---------------------------------------------------------------------------
# Module-level invariants
# ---------------------------------------------------------------------------


def test_no_subprocess_or_gh_or_git_in_module() -> None:
    src = Path(ai.__file__).read_text(encoding="utf-8")
    assert "import subprocess" not in src
    assert "from subprocess" not in src
    forbidden = ('"gh"', "'gh'", '"git"', "'git'", "Popen")
    for token in forbidden:
        assert token not in src, f"forbidden token in approval_inbox.py: {token!r}"
