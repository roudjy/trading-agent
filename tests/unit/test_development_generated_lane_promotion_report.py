"""Tests for the A18 promotion-readiness report (read-only).

Hard guarantees verified here:

* Default-disabled-style invariants: this module is read-only
  by construction; it never promotes any row. ``PROMOTION_ALLOWED_DEFAULT``
  is the pinned constant False; every emitted row carries
  ``promotion_allowed=False`` regardless of the underlying A18c
  admission decision.
* A18c artefact absent → safe ``not_available`` envelope
  (``a18c_artifact_available=False``, ``readiness_note="a18c_artifact_absent"``).
* A18c artefact malformed → safe ``not_available`` envelope
  (``readiness_note="a18c_artifact_malformed"``), no crash.
* Phase-2 diagnostic row (the
  ``a18b-phase2-smoke-2026-05-13-001`` candidate-id, projected
  by A18c with ``admission_decision="needs_human"``) → one
  report row, ``promotion_allowed=False``,
  ``block_reason="needs_human_per_a17_policy"``,
  ``required_operator_go_phrase="GO A18 promotion operator-promote"``.
* Defense-in-depth: an A18c row carrying
  ``admission_decision="admissible"`` (the A18c first-cut
  posture never emits this, but if a future change did) STILL
  produces a report row with ``promotion_allowed=False`` and
  ``block_reason="promotion_disabled_by_default"``.
* Closed envelope schema and closed BLOCK_REASONS / READINESS_NOTES
  vocabularies.
* Atomic write sentinel refuses any path outside
  ``logs/development_generated_lane_promotion_report/``.
* Source / AST scans: no subprocess, no socket / urllib /
  requests / httpx / aiohttp / gh / git, no dashboard /
  frontend / approval-token / A18b writer imports, no
  seed.jsonl / delegation_seed.jsonl / generated_seed.jsonl
  write Call (the module never opens those files for write).
* CLI ``--no-write`` works; default invocation writes the
  canonical report path.
* Step 5 / Level 6 invariants intact.
"""

from __future__ import annotations

import ast
import json
from pathlib import Path
from typing import Any

import pytest

from reporting import development_generated_lane_a18c as a18c
from reporting import development_generated_lane_promotion_report as report
from reporting import development_queue_admission_policy as a17

REPO_ROOT = Path(__file__).resolve().parents[2]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _a18c_row(
    *,
    candidate_id: str,
    admission_decision: str = "needs_human",
    admission_reason: str = "needs_human_authority_decision",
    would_target_lane: str = "none",
    human_needed: bool = True,
    human_needed_reason: str = "would_require_operator_go",
    candidate_kind: str = "e2e_proof",
    risk_level: str = "UNKNOWN",
    source_kind: str = "generated_seed_lane",
    evaluated_at: str = "2026-05-13T13:00:00Z",
) -> dict[str, Any]:
    """Build a single A18c-shape row matching A17's
    ADMISSION_SCHEMA_KEYS verbatim. The promotion-report consumes
    only a subset of these fields; we set every key present in
    A17's schema so a future A18c key addition does not silently
    break the test fixture."""
    return {
        "candidate_id": candidate_id,
        "title": "diagnostic title",
        "source_document": "/app/generated_seed.jsonl",
        "source_kind": source_kind,
        "roadmap_phase": "",
        "candidate_kind": candidate_kind,
        "required_agent_role": "operator" if human_needed else "",
        "risk_level": risk_level,
        "target_path": "",
        "upstream_intake_status": "generated_seed_present",
        "upstream_decision_state": "needs_human",
        "upstream_execution_authority_decision": "NEEDS_HUMAN",
        "reclassified_execution_authority_decision": "NEEDS_HUMAN",
        "classification_drift": False,
        "human_needed": human_needed,
        "human_needed_reason": human_needed_reason,
        "admission_decision": admission_decision,
        "admission_reason": admission_reason,
        "would_target_lane": would_target_lane,
        "already_in_seed_jsonl": False,
        "already_in_delegation_seed": False,
        "policy_version": "v3.15.16.A17",
        "evaluated_at": evaluated_at,
    }


def _a18c_artifact(
    rows: list[dict[str, Any]],
    *,
    module_version: str = "v3.15.16.A18c",
    policy_version: str = "v3.15.16.A17",
    enabled: bool = True,
    note: str = "candidates_projected",
) -> dict[str, Any]:
    """Build a closed-shape A18c snapshot envelope."""
    return {
        "schema_version": "1.0",
        "module_version": module_version,
        "report_kind": "development_generated_lane_a18c",
        "generated_at_utc": "2026-05-13T13:00:00Z",
        "enabled": enabled,
        "env_gate_name": "ADE_GENERATED_LANE_A18C_ENABLED",
        "generated_seed_path": "/app/generated_seed.jsonl",
        "rows": rows,
        "counts": {"total": len(rows)},
        "note": note,
        "validation_warnings": [],
        "vocabularies": {},
        "policy_version": policy_version,
        "a18b_writer_module_version": "v3.15.16.A18b",
        "per_tick_cap": 8,
        "per_day_cap": 32,
        "step5_implementation_allowed": False,
        "step5_enabled_substage": "none",
        "level6_enabled": False,
        "dry_run_only": True,
        "live_merge_implemented": False,
        "deploy_coupled": False,
        "discipline_invariants": {},
    }


def _write_a18c_artifact(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


# ---------------------------------------------------------------------------
# Closed-vocab module surface
# ---------------------------------------------------------------------------


def test_module_version_pin() -> None:
    assert report.MODULE_VERSION == "v3.15.16.A18.promotion_report"


def test_report_kind_pin() -> None:
    assert report.REPORT_KIND == (
        "development_generated_lane_promotion_report"
    )


def test_artifact_relative_path_pin() -> None:
    assert report.ARTIFACT_RELATIVE_PATH == (
        "logs/development_generated_lane_promotion_report/latest.json"
    )


def test_operator_go_phrase_pin() -> None:
    """The exact operator-go phrase a future PR would issue to
    build operator-promote functionality. The phrase itself is
    NOT issued by this module; it identifies the future-go."""
    assert report.OPERATOR_GO_PHRASE == (
        "GO A18 promotion operator-promote"
    )


def test_promotion_allowed_default_is_false() -> None:
    assert report.PROMOTION_ALLOWED_DEFAULT is False


def test_block_reasons_closed_vocab() -> None:
    assert set(report.BLOCK_REASONS) == {
        "needs_human_per_a17_policy",
        "blocked_per_a17_policy",
        "duplicate_per_a17_policy",
        "not_eligible_upstream_per_a17_policy",
        "promotion_disabled_by_default",
    }


def test_readiness_notes_closed_vocab() -> None:
    assert set(report.READINESS_NOTES) == {
        "a18c_artifact_absent",
        "a18c_artifact_malformed",
        "no_source_rows",
        "rows_present_none_promotable",
    }


def test_step5_invariants_intact_by_import() -> None:
    assert report.step5_implementation_allowed is False
    assert report.STEP5_ENABLED_SUBSTAGE == "none"


# ---------------------------------------------------------------------------
# Absent / malformed source artefact.
# ---------------------------------------------------------------------------


def test_absent_a18c_artifact_returns_safe_envelope(tmp_path: Path) -> None:
    a18c_path = tmp_path / "logs" / "development_generated_lane_a18c" / "latest.json"
    snap = report.collect_snapshot(a18c_artifact_path=a18c_path)
    assert snap["a18c_artifact_available"] is False
    assert snap["readiness_note"] == "a18c_artifact_absent"
    assert "a18c_artifact_absent" in snap["validation_warnings"]
    assert snap["source_row_count"] == 0
    assert snap["promotable_row_count"] == 0
    assert snap["blocked_row_count"] == 0
    assert snap["rows"] == []


def test_malformed_a18c_artifact_returns_safe_envelope(tmp_path: Path) -> None:
    a18c_path = tmp_path / "a18c.json"
    a18c_path.write_text("not json at all\n", encoding="utf-8")
    snap = report.collect_snapshot(a18c_artifact_path=a18c_path)
    assert snap["readiness_note"] == "a18c_artifact_malformed"
    assert snap["rows"] == []
    assert snap["promotable_row_count"] == 0


def test_a18c_artifact_non_object_returns_malformed(tmp_path: Path) -> None:
    a18c_path = tmp_path / "a18c.json"
    a18c_path.write_text("[1, 2, 3]", encoding="utf-8")
    snap = report.collect_snapshot(a18c_artifact_path=a18c_path)
    assert snap["readiness_note"] == "a18c_artifact_malformed"
    assert snap["rows"] == []


def test_a18c_artifact_empty_rows_returns_no_source_rows(
    tmp_path: Path,
) -> None:
    a18c_path = tmp_path / "a18c.json"
    _write_a18c_artifact(a18c_path, _a18c_artifact([], note="no_eligible_a18b_rows"))
    snap = report.collect_snapshot(a18c_artifact_path=a18c_path)
    assert snap["a18c_artifact_available"] is True
    assert snap["readiness_note"] == "no_source_rows"
    assert snap["source_row_count"] == 0
    assert snap["promotable_row_count"] == 0
    assert snap["rows"] == []


# ---------------------------------------------------------------------------
# Phase-2 diagnostic row protection (key safety property).
# ---------------------------------------------------------------------------


def test_phase2_diagnostic_row_emits_promotion_allowed_false(
    tmp_path: Path,
) -> None:
    """The exact Phase-2 candidate-id from the operator's
    confirmed VPS state. A18c projects it with
    admission_decision='needs_human'. The report must surface
    one row with promotion_allowed=False and block_reason
    'needs_human_per_a17_policy'."""
    a18c_path = tmp_path / "a18c.json"
    a18c_row = _a18c_row(
        candidate_id=(
            "a18c-a18b-phase2-smoke-2026-05-13-001-abcdef0123456789"
        ),
        admission_decision="needs_human",
        admission_reason="needs_human_authority_decision",
    )
    _write_a18c_artifact(a18c_path, _a18c_artifact([a18c_row]))
    snap = report.collect_snapshot(a18c_artifact_path=a18c_path)
    assert snap["a18c_artifact_available"] is True
    assert snap["source_row_count"] == 1
    assert snap["promotable_row_count"] == 0
    assert snap["blocked_row_count"] == 1
    assert snap["readiness_note"] == "rows_present_none_promotable"
    [r] = snap["rows"]
    assert r["candidate_id"] == (
        "a18c-a18b-phase2-smoke-2026-05-13-001-abcdef0123456789"
    )
    assert r["admission_decision"] == "needs_human"
    assert r["admission_reason"] == "needs_human_authority_decision"
    assert r["promotion_allowed"] is False
    assert r["block_reason"] == "needs_human_per_a17_policy"
    assert r["required_operator_go_phrase"] == (
        "GO A18 promotion operator-promote"
    )
    assert r["would_target_lane"] == "none"
    assert r["human_needed"] is True
    assert r["human_needed_reason"] == "would_require_operator_go"


def test_phase2_diagnostic_row_carries_readiness_reason(
    tmp_path: Path,
) -> None:
    a18c_path = tmp_path / "a18c.json"
    a18c_row = _a18c_row(
        candidate_id="a18c-a18b-phase2-smoke-2026-05-13-001-deadbeefdeadbeef",
        admission_decision="needs_human",
    )
    _write_a18c_artifact(a18c_path, _a18c_artifact([a18c_row]))
    snap = report.collect_snapshot(a18c_artifact_path=a18c_path)
    [r] = snap["rows"]
    assert r["readiness_reason"] == "needs_human_per_a17_policy"


# ---------------------------------------------------------------------------
# Defense-in-depth: even an admissible row never gets
# promotion_allowed=True.
# ---------------------------------------------------------------------------


def test_admissible_a18c_row_still_emits_promotion_allowed_false(
    tmp_path: Path,
) -> None:
    """The A18c first-cut posture never emits admission_decision
    'admissible'. But IF a future A18c change ever did, the
    report's hard-pinned safety property forces
    promotion_allowed=False AND block_reason
    'promotion_disabled_by_default'."""
    a18c_path = tmp_path / "a18c.json"
    a18c_row = _a18c_row(
        candidate_id="a18c-hypothetical-admissible-row-cafef00d12345678",
        admission_decision="admissible",
        admission_reason="auto_allowed_low_risk_eligible_promotion",
        would_target_lane="development_work_queue",
        human_needed=False,
        human_needed_reason="",
    )
    _write_a18c_artifact(a18c_path, _a18c_artifact([a18c_row]))
    snap = report.collect_snapshot(a18c_artifact_path=a18c_path)
    [r] = snap["rows"]
    assert r["admission_decision"] == "admissible"
    # Hard-pinned safety property:
    assert r["promotion_allowed"] is False
    assert r["block_reason"] == "promotion_disabled_by_default"
    # The envelope's promotable_row_count is still 0.
    assert snap["promotable_row_count"] == 0


# ---------------------------------------------------------------------------
# Mixed-decision aggregation.
# ---------------------------------------------------------------------------


def test_mixed_decisions_aggregate_correctly(tmp_path: Path) -> None:
    a18c_path = tmp_path / "a18c.json"
    rows = [
        _a18c_row(
            candidate_id="a18c-row-1",
            admission_decision="needs_human",
            admission_reason="needs_human_authority_decision",
        ),
        _a18c_row(
            candidate_id="a18c-row-2",
            admission_decision="blocked",
            admission_reason="blocked_authority_permanently_denied",
        ),
        _a18c_row(
            candidate_id="a18c-row-3",
            admission_decision="duplicate_of_existing",
            admission_reason="already_in_seed_jsonl",
        ),
        _a18c_row(
            candidate_id="a18c-row-4",
            admission_decision="not_eligible_upstream",
            admission_reason="upstream_intake_status_not_eligible",
        ),
    ]
    _write_a18c_artifact(a18c_path, _a18c_artifact(rows))
    snap = report.collect_snapshot(a18c_artifact_path=a18c_path)
    assert snap["source_row_count"] == 4
    assert snap["promotable_row_count"] == 0
    assert snap["blocked_row_count"] == 4
    by_dec = snap["rows_by_admission_decision"]
    assert by_dec["needs_human"] == 1
    assert by_dec["blocked"] == 1
    assert by_dec["duplicate_of_existing"] == 1
    assert by_dec["not_eligible_upstream"] == 1
    assert by_dec["admissible"] == 0
    # Each row's block_reason maps deterministically.
    reasons = {r["candidate_id"]: r["block_reason"] for r in snap["rows"]}
    assert reasons["a18c-row-1"] == "needs_human_per_a17_policy"
    assert reasons["a18c-row-2"] == "blocked_per_a17_policy"
    assert reasons["a18c-row-3"] == "duplicate_per_a17_policy"
    assert reasons["a18c-row-4"] == (
        "not_eligible_upstream_per_a17_policy"
    )


# ---------------------------------------------------------------------------
# Closed schema invariants.
# ---------------------------------------------------------------------------


def test_every_report_row_uses_closed_key_set(tmp_path: Path) -> None:
    a18c_path = tmp_path / "a18c.json"
    rows = [
        _a18c_row(candidate_id=f"a18c-shape-{i}")
        for i in range(3)
    ]
    _write_a18c_artifact(a18c_path, _a18c_artifact(rows))
    snap = report.collect_snapshot(a18c_artifact_path=a18c_path)
    for r in snap["rows"]:
        assert set(r.keys()) == set(report.REPORT_ROW_KEYS)


def test_envelope_carries_step5_and_level6_invariants(
    tmp_path: Path,
) -> None:
    a18c_path = tmp_path / "a18c.json"
    _write_a18c_artifact(
        a18c_path, _a18c_artifact([_a18c_row(candidate_id="inv-1")])
    )
    snap = report.collect_snapshot(a18c_artifact_path=a18c_path)
    assert snap["step5_implementation_allowed"] is False
    assert snap["step5_enabled_substage"] == "none"
    assert snap["level6_enabled"] is False
    assert snap["dry_run_only"] is True
    assert snap["live_merge_implemented"] is False
    assert snap["deploy_coupled"] is False


def test_envelope_carries_full_discipline_invariants(
    tmp_path: Path,
) -> None:
    a18c_path = tmp_path / "a18c.json"
    _write_a18c_artifact(
        a18c_path, _a18c_artifact([_a18c_row(candidate_id="disc-1")])
    )
    snap = report.collect_snapshot(a18c_artifact_path=a18c_path)
    di = snap["discipline_invariants"]
    assert di["promotes_anything"] is False
    assert di["writes_to_seed_jsonl"] is False
    assert di["writes_to_delegation_seed_jsonl"] is False
    assert di["writes_to_generated_seed_jsonl"] is False
    assert di["mutates_a18c_artifact"] is False
    assert di["mutates_a17_artifact"] is False
    assert di["admits_to_queue"] is False
    assert di["executes_work"] is False
    assert di["creates_branches"] is False
    assert di["opens_prs"] is False
    assert di["merges_prs"] is False
    assert di["deploys"] is False
    assert di["calls_network"] is False
    assert di["uses_subprocess"] is False
    assert di["touches_step5_flags"] is False
    assert di["level6_enabled"] is False


def test_envelope_carries_operator_go_phrase_at_top_level(
    tmp_path: Path,
) -> None:
    a18c_path = tmp_path / "a18c.json"
    _write_a18c_artifact(a18c_path, _a18c_artifact([]))
    snap = report.collect_snapshot(a18c_artifact_path=a18c_path)
    assert snap["operator_go_phrase_required"] == (
        "GO A18 promotion operator-promote"
    )
    assert snap["promotion_allowed_default"] is False


def test_envelope_carries_a17_and_a18c_version_pins(
    tmp_path: Path,
) -> None:
    a18c_path = tmp_path / "a18c.json"
    _write_a18c_artifact(
        a18c_path,
        _a18c_artifact(
            [_a18c_row(candidate_id="v-1")],
            module_version="v3.15.16.A18c",
            policy_version="v3.15.16.A17",
        ),
    )
    snap = report.collect_snapshot(a18c_artifact_path=a18c_path)
    # Top-level version pins agree with the upstream artefacts.
    assert snap["a18c_module_version"] == "v3.15.16.A18c"
    assert snap["a17_policy_version"] == "v3.15.16.A17"
    # The module's own internal pins agree at import time.
    assert snap["a18c_module_version_pin"] == a18c.MODULE_VERSION
    assert snap["policy_version"] == a17.MODULE_VERSION


# ---------------------------------------------------------------------------
# Atomic-write sentinel.
# ---------------------------------------------------------------------------


def test_atomic_write_refuses_non_report_path(tmp_path: Path) -> None:
    bad_path = tmp_path / "not_report.json"
    with pytest.raises(ValueError, match="non-report-logs"):
        report._atomic_write_json(bad_path, {"k": "v"})


def test_atomic_write_succeeds_under_report_prefix(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target_dir = (
        tmp_path / "logs" / "development_generated_lane_promotion_report"
    )
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / "latest.json"
    monkeypatch.setattr(report, "ARTIFACT_LATEST", target)
    snap = report.collect_snapshot(
        a18c_artifact_path=tmp_path / "no_a18c.json"
    )
    report.write_outputs(snap)
    assert target.is_file()
    loaded = json.loads(target.read_text(encoding="utf-8"))
    assert loaded["promotion_allowed_default"] is False


# ---------------------------------------------------------------------------
# A18c artefact must not be mutated by the report.
# ---------------------------------------------------------------------------


def test_a18c_artifact_unchanged_after_collect_snapshot(
    tmp_path: Path,
) -> None:
    a18c_path = tmp_path / "a18c.json"
    rows = [_a18c_row(candidate_id="immut-1")]
    payload = _a18c_artifact(rows)
    _write_a18c_artifact(a18c_path, payload)
    before = a18c_path.read_text(encoding="utf-8")
    report.collect_snapshot(a18c_artifact_path=a18c_path)
    after = a18c_path.read_text(encoding="utf-8")
    assert before == after


# ---------------------------------------------------------------------------
# Source-text + AST scans.
# ---------------------------------------------------------------------------


def _module_source() -> str:
    return Path(report.__file__).read_text(encoding="utf-8")


def _imported_module_names() -> set[str]:
    tree = ast.parse(_module_source())
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                names.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module is not None:
                names.add(node.module)
    return names


def test_no_subprocess_import() -> None:
    src = _module_source()
    assert "import subprocess" not in src
    assert "from subprocess" not in src


def test_no_network_library_import() -> None:
    names = _imported_module_names()
    forbidden_top = {"socket", "urllib", "requests", "httpx", "aiohttp"}
    for n in names:
        top = n.split(".", 1)[0]
        assert top not in forbidden_top, n


def test_no_gh_or_git_in_module_source() -> None:
    src = _module_source()
    for needle in ("subprocess.run", " gh ", " git ", "Popen"):
        assert needle not in src, needle


def test_no_dashboard_or_frontend_import() -> None:
    names = _imported_module_names()
    for n in names:
        top = n.split(".", 1)[0]
        assert top != "dashboard"
        assert top != "frontend"


def test_no_approval_token_import() -> None:
    names = _imported_module_names()
    for forbidden in (
        "reporting.approval_token_gate",
        "reporting.approval_token_runtime",
    ):
        assert forbidden not in names, forbidden


def test_no_a18b_writer_import() -> None:
    """The report never touches A18b directly. It consumes A18c's
    already-projected artefact."""
    names = _imported_module_names()
    assert "reporting.development_generated_lane_writer" not in names


_WRITE_METHOD_NAMES: frozenset[str] = frozenset(
    {
        "open",
        "write_text",
        "write_bytes",
        "replace",
        "rename",
        "unlink",
        "remove",
        "dump",  # json.dump(...) is a write sink
    }
)


def _is_write_call(node: ast.Call) -> bool:
    """Return True iff the Call's target name suggests a file
    write / replace / rename / removal."""
    func = node.func
    if isinstance(func, ast.Attribute):
        return func.attr in _WRITE_METHOD_NAMES
    if isinstance(func, ast.Name):
        return func.id in _WRITE_METHOD_NAMES
    return False


def test_no_seed_or_delegation_seed_write_call_in_source() -> None:
    """AST scan — every WRITE-shaped Call (open/write_text/replace
    /rename/unlink/remove/dump) whose string argument references
    seed.jsonl (and is not generated_seed.jsonl) or
    delegation_seed.jsonl is forbidden.

    The pin scans only write-shaped Calls — narrative mentions
    of the basenames inside ``argparse.ArgumentParser(description=...)``
    or in docstrings are legitimate and not flagged.

    Belt-and-braces over the runtime sentinel
    (``_atomic_write_json`` already refuses any path outside
    the report's own ``logs/development_generated_lane_promotion_report/``
    prefix; see ``test_atomic_write_refuses_non_report_path``)."""
    tree = ast.parse(_module_source())
    offenders: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if not _is_write_call(node):
            continue
        for arg in list(node.args) + [kw.value for kw in node.keywords]:
            if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                lowered = arg.value.lower()
                if "delegation_seed.jsonl" in lowered:
                    offenders.append(
                        f"line {node.lineno}: WRITE Call references "
                        f"delegation_seed.jsonl: {arg.value!r}"
                    )
                if "seed.jsonl" in lowered and (
                    "generated_seed.jsonl" not in lowered
                ):
                    offenders.append(
                        f"line {node.lineno}: WRITE Call references "
                        f"seed.jsonl (not generated_seed): "
                        f"{arg.value!r}"
                    )
                if "generated_seed.jsonl" in lowered:
                    offenders.append(
                        f"line {node.lineno}: WRITE Call references "
                        f"generated_seed.jsonl: {arg.value!r}"
                    )
    assert not offenders, (
        "promotion-report module must not contain a WRITE Call "
        "whose argument references seed.jsonl, "
        "delegation_seed.jsonl, or generated_seed.jsonl: "
        f"{offenders}"
    )


def test_no_a18b_writer_module_used() -> None:
    """Layered: the module must not import (and therefore cannot
    accidentally call) the A18b writer module. A separate test
    (``test_no_a18b_writer_import``) covers the import side. This
    test verifies the import-allowlist test exists by re-checking
    via the same import-names path."""
    names = _imported_module_names()
    assert "reporting.development_generated_lane_writer" not in names
    # The string "development_generated_lane_writer" must not
    # appear as a Name-resolution target in any Call site either.
    src = _module_source()
    assert "development_generated_lane_writer(" not in src
    assert "development_generated_lane_writer." not in src


def test_module_imports_only_allowed_reporting_modules() -> None:
    names = _imported_module_names()
    allowed_reporting = {
        "reporting",
        "reporting.development_generated_lane_a18c",
        "reporting.development_queue_admission_policy",
        "reporting.agent_audit_summary",
    }
    for n in names:
        if n == "reporting" or n.startswith("reporting."):
            assert n in allowed_reporting, n


def test_module_source_pins_step5_invariants() -> None:
    src = _module_source()
    assert "step5_implementation_allowed: Final[bool] = False" in src
    assert 'STEP5_ENABLED_SUBSTAGE: Final[str] = "none"' in src
    assert "step5_implementation_allowed = True" not in src


def test_module_source_pins_promotion_allowed_default_false() -> None:
    src = _module_source()
    assert "PROMOTION_ALLOWED_DEFAULT: Final[bool] = False" in src
    assert "PROMOTION_ALLOWED_DEFAULT = True" not in src


# ---------------------------------------------------------------------------
# CLI.
# ---------------------------------------------------------------------------


def test_cli_no_write_emits_envelope(
    capsys: pytest.CaptureFixture[str],
) -> None:
    rc = report.main(["--no-write"])
    assert rc == 0
    out = capsys.readouterr().out
    snap = json.loads(out)
    assert snap["promotion_allowed_default"] is False
    assert snap["operator_go_phrase_required"] == (
        "GO A18 promotion operator-promote"
    )
    assert snap["step5_implementation_allowed"] is False
    assert snap["level6_enabled"] is False


def test_cli_default_write_path_is_report_artifact(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When --no-write is omitted, the CLI writes the envelope to
    the canonical artefact path. Defense-in-depth: redirect
    ARTIFACT_LATEST into tmp so we never touch the repo's real
    logs/ tree."""
    target_dir = (
        tmp_path / "logs" / "development_generated_lane_promotion_report"
    )
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / "latest.json"
    monkeypatch.setattr(report, "ARTIFACT_LATEST", target)
    rc = report.main([])
    assert rc == 0
    assert target.is_file()


def test_cli_indent_zero_emits_compact(
    capsys: pytest.CaptureFixture[str],
) -> None:
    rc = report.main(["--no-write", "--indent", "0"])
    assert rc == 0
    out = capsys.readouterr().out
    # Compact JSON (indent=None) has no leading whitespace lines.
    assert "  " not in out.split("\n")[0]


# ---------------------------------------------------------------------------
# Hard-pinned safety: promotable_row_count is always 0.
# ---------------------------------------------------------------------------


def test_promotable_row_count_is_always_zero_across_envelopes(
    tmp_path: Path,
) -> None:
    """Across every artefact state — absent, malformed, empty,
    one-row, multi-row, mixed-decision — promotable_row_count
    must be 0."""
    # Absent.
    snap = report.collect_snapshot(
        a18c_artifact_path=tmp_path / "missing.json"
    )
    assert snap["promotable_row_count"] == 0

    # Malformed.
    bad = tmp_path / "bad.json"
    bad.write_text("not json", encoding="utf-8")
    snap = report.collect_snapshot(a18c_artifact_path=bad)
    assert snap["promotable_row_count"] == 0

    # Empty rows.
    empty = tmp_path / "empty.json"
    _write_a18c_artifact(empty, _a18c_artifact([]))
    snap = report.collect_snapshot(a18c_artifact_path=empty)
    assert snap["promotable_row_count"] == 0

    # Mixed-decision (including hypothetical admissible).
    multi = tmp_path / "multi.json"
    rows = [
        _a18c_row(candidate_id="row-1", admission_decision="needs_human"),
        _a18c_row(candidate_id="row-2", admission_decision="blocked"),
        _a18c_row(
            candidate_id="row-3",
            admission_decision="admissible",
            admission_reason="auto_allowed_low_risk_eligible_promotion",
        ),
    ]
    _write_a18c_artifact(multi, _a18c_artifact(rows))
    snap = report.collect_snapshot(a18c_artifact_path=multi)
    assert snap["promotable_row_count"] == 0
    for r in snap["rows"]:
        assert r["promotion_allowed"] is False
