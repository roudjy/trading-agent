"""Unit tests for A18a — Generated Queue Lane projector (DRY-RUN).

Pins:
* ``--no-write`` mode creates no file.
* Default mode atomic-writes EXACTLY
  ``logs/development_generated_lane/latest.json`` and nothing else.
* Atomic-write helper refuses any path outside the closed sentinel
  prefix.
* Missing upstream artefacts → safe empty report.
* Valid upstream artefacts → bounded candidates ≤
  :data:`MAX_GENERATED_CANDIDATES`, each with the closed
  10-key schema.
* ``admission_preview`` is always ``"report_only_not_admitted"``;
  ``block_reason`` is always ``"generated_lane_writer_not_authorized"``;
  ``would_require_operator_go`` is always ``True``.
* No ``generated_seed.jsonl`` is created or written in any mode.
* Discipline-invariant block carries every required flag with the
  exact expected value.
* Source-text + AST scans: no subprocess / gh / git / pywebpush /
  approval-token mint imports / merge or deploy call patterns;
  ``generated_seed.jsonl`` literal never appears in a write
  context.
* Step 5 invariants preserved by import.

The tests **never** allow the projector to read the real
``logs/`` directory; ``ARTIFACT_LATEST`` and the three upstream-
artefact paths are redirected into ``tmp_path``.
"""

from __future__ import annotations

import ast
import importlib
import json
from pathlib import Path
from typing import Any

import pytest

from reporting import development_generated_lane as dgl


REPO_ROOT = Path(__file__).resolve().parents[2]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def isolated_artifacts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> dict[str, Path]:
    """Redirect every read + write path into ``tmp_path``."""
    out_dir = tmp_path / "logs" / "development_generated_lane"
    out_latest = out_dir / "latest.json"
    monkeypatch.setattr(dgl, "ARTIFACT_DIR", out_dir)
    monkeypatch.setattr(dgl, "ARTIFACT_LATEST", out_latest)
    # Redirect upstream-artefact reads.
    bp = tmp_path / "logs" / "development_bugfix_loop" / "latest.json"
    dp = tmp_path / "logs" / "development_delegation" / "latest.json"
    ep = tmp_path / "logs" / "development_e2e_proof" / "latest.json"
    monkeypatch.setattr(dgl, "_BUGFIX_LOOP_LATEST", bp)
    monkeypatch.setattr(dgl, "_DELEGATION_LATEST", dp)
    monkeypatch.setattr(dgl, "_E2E_PROOF_LATEST", ep)
    return {
        "out_dir": out_dir,
        "out_latest": out_latest,
        "bugfix_loop": bp,
        "delegation": dp,
        "e2e_proof": ep,
        "tmp_root": tmp_path,
    }


def _write_artifact(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


# ---------------------------------------------------------------------------
# Step 5 + module-level invariants
# ---------------------------------------------------------------------------


def test_step5_invariants_intact() -> None:
    assert dgl.STEP5_ENABLED_SUBSTAGE == "none"
    assert dgl.step5_implementation_allowed is False


def test_module_version_pinned() -> None:
    assert dgl.MODULE_VERSION == "v3.15.16.A18a"


def test_report_kind_pinned() -> None:
    assert dgl.REPORT_KIND == "development_generated_lane"


def test_closed_vocabularies_pinned() -> None:
    assert dgl.PROPOSED_KINDS == (
        "bugfix",
        "delegation",
        "e2e_proof",
        "unknown",
    )
    assert dgl.ADMISSION_PREVIEWS == ("report_only_not_admitted",)
    assert dgl.BLOCK_REASONS == (
        "generated_lane_writer_not_authorized",
    )
    assert dgl.GENERATED_CANDIDATE_KEYS == (
        "generated_candidate_id",
        "source_module",
        "source_id",
        "proposed_kind",
        "proposed_title",
        "proposed_summary",
        "evidence_hash",
        "admission_preview",
        "block_reason",
        "would_require_operator_go",
    )


def test_artifact_path_under_generated_lane_logs() -> None:
    assert dgl.ARTIFACT_RELATIVE_PATH == (
        "logs/development_generated_lane/latest.json"
    )


def test_max_candidates_is_bounded() -> None:
    assert dgl.MAX_GENERATED_CANDIDATES == 16


# ---------------------------------------------------------------------------
# Empty-state behaviour
# ---------------------------------------------------------------------------


def test_collect_snapshot_no_sources_returns_safe_empty(
    isolated_artifacts: dict[str, Path],
) -> None:
    snap = dgl.collect_snapshot()
    assert snap["candidate_count"] == 0
    assert snap["candidates"] == []
    assert snap["note"] == dgl.NOTE_NO_SOURCES
    # All three sources absent.
    for w in (
        "bugfix_loop_artifact_absent",
        "delegation_artifact_absent",
        "e2e_proof_artifact_absent",
    ):
        assert w in snap["validation_warnings"]
    # Step 5 invariants surfaced in the snapshot.
    assert snap["step5_implementation_allowed"] is False
    assert snap["step5_enabled_substage"] == "none"


def test_collect_snapshot_unparseable_source_returns_warning(
    isolated_artifacts: dict[str, Path],
) -> None:
    isolated_artifacts["bugfix_loop"].parent.mkdir(
        parents=True, exist_ok=True
    )
    isolated_artifacts["bugfix_loop"].write_text(
        "not json", encoding="utf-8"
    )
    snap = dgl.collect_snapshot()
    assert "bugfix_loop_artifact_unparseable" in snap["validation_warnings"]


# ---------------------------------------------------------------------------
# Candidate projection from each source
# ---------------------------------------------------------------------------


def _bugfix_payload(n: int) -> dict[str, Any]:
    return {
        "candidates": [
            {
                "candidate_id": f"bugfix_cand_{i:04d}",
                "target_path": f"reporting/some_module_{i}.py",
                "failure_class": "unit_test",
                "rationale": "Failing assertion in some_module.py.",
            }
            for i in range(n)
        ]
    }


def _delegation_payload(n: int) -> dict[str, Any]:
    return {
        "rows": [
            {
                "candidate_id": f"deleg_cand_{i:04d}",
                "title": f"Delegation candidate {i}",
                "summary": "A bounded delegation summary.",
            }
            for i in range(n)
        ]
    }


def _e2e_proof_payload(n: int) -> dict[str, Any]:
    return {
        "records": [
            {
                "proof_id": f"e2e_proof_{i:04d}",
                "title": f"E2E proof candidate {i}",
                "summary": "A bounded e2e proof summary.",
            }
            for i in range(n)
        ]
    }


def test_collect_snapshot_with_all_sources_projects_candidates(
    isolated_artifacts: dict[str, Path],
) -> None:
    _write_artifact(isolated_artifacts["bugfix_loop"], _bugfix_payload(3))
    _write_artifact(isolated_artifacts["delegation"], _delegation_payload(3))
    _write_artifact(isolated_artifacts["e2e_proof"], _e2e_proof_payload(3))
    snap = dgl.collect_snapshot()
    assert snap["candidate_count"] >= 1
    assert snap["note"] == dgl.NOTE_CANDIDATES_PRESENT
    for c in snap["candidates"]:
        assert set(c.keys()) == set(dgl.GENERATED_CANDIDATE_KEYS)
        assert c["admission_preview"] == "report_only_not_admitted"
        assert c["block_reason"] == "generated_lane_writer_not_authorized"
        assert c["would_require_operator_go"] is True
        assert c["proposed_kind"] in dgl.PROPOSED_KINDS


def test_candidates_bounded_to_max_generated_candidates(
    isolated_artifacts: dict[str, Path],
) -> None:
    # Far more than MAX_GENERATED_CANDIDATES across all sources.
    _write_artifact(isolated_artifacts["bugfix_loop"], _bugfix_payload(50))
    _write_artifact(isolated_artifacts["delegation"], _delegation_payload(50))
    _write_artifact(isolated_artifacts["e2e_proof"], _e2e_proof_payload(50))
    snap = dgl.collect_snapshot()
    assert snap["candidate_count"] <= dgl.MAX_GENERATED_CANDIDATES


def test_candidate_scalars_are_bounded(
    isolated_artifacts: dict[str, Path],
) -> None:
    huge_title = "x" * 5000
    huge_summary = "y" * 5000
    _write_artifact(
        isolated_artifacts["delegation"],
        {
            "rows": [
                {
                    "candidate_id": "deleg_huge",
                    "title": huge_title,
                    "summary": huge_summary,
                }
            ]
        },
    )
    snap = dgl.collect_snapshot()
    for c in snap["candidates"]:
        assert len(c["proposed_title"]) <= dgl.MAX_TITLE_LEN
        assert len(c["proposed_summary"]) <= dgl.MAX_SUMMARY_LEN


def test_candidate_scalars_reject_diff_and_pem_markers(
    isolated_artifacts: dict[str, Path],
) -> None:
    """Defense-in-depth: diff hunks / PEM markers in upstream
    titles/summaries are stripped to empty rather than passed
    through."""
    _write_artifact(
        isolated_artifacts["delegation"],
        {
            "rows": [
                {
                    "candidate_id": "deleg_pem",
                    "title": "diff --git a/x b/x",
                    "summary": "BEGIN PRIVATE KEY abc...",
                }
            ]
        },
    )
    snap = dgl.collect_snapshot()
    assert len(snap["candidates"]) >= 1
    c = snap["candidates"][0]
    assert "diff --git " not in c["proposed_title"]
    assert "BEGIN PRIVATE KEY" not in c["proposed_summary"]


# ---------------------------------------------------------------------------
# Discipline invariants
# ---------------------------------------------------------------------------


def test_discipline_invariants_carry_required_flags(
    isolated_artifacts: dict[str, Path],
) -> None:
    snap = dgl.collect_snapshot()
    inv = snap["discipline_invariants"]
    assert inv["step5_implementation_allowed"] is False
    assert inv["step5_enabled_substage"] == "none"
    assert inv["generated_seed_writer_authorized"] is False
    assert inv["mutates_generated_seed"] is False
    assert inv["admits_queue_items"] is False
    assert inv["executes_work"] is False
    assert inv["operator_promotion_required"] is True
    assert inv["operator_go_required_for_writer"] is True
    assert inv["writes_to_seed_jsonl"] is False
    assert inv["writes_to_delegation_seed_jsonl"] is False
    assert inv["writes_to_generated_seed_jsonl"] is False
    assert inv["mints_or_verifies_approval_tokens"] is False
    assert inv["sends_real_push"] is False
    assert inv["uses_subprocess_or_network"] is False


# ---------------------------------------------------------------------------
# Write modes
# ---------------------------------------------------------------------------


def test_no_write_mode_creates_no_files(
    isolated_artifacts: dict[str, Path],
) -> None:
    _write_artifact(isolated_artifacts["bugfix_loop"], _bugfix_payload(2))
    rc = dgl.main(["--no-write"])
    assert rc == 0
    assert not isolated_artifacts["out_latest"].exists()
    # And no other file is created under the sentinel dir.
    if isolated_artifacts["out_dir"].exists():
        assert list(isolated_artifacts["out_dir"].iterdir()) == []


def test_default_mode_writes_only_latest_json(
    isolated_artifacts: dict[str, Path],
) -> None:
    _write_artifact(isolated_artifacts["bugfix_loop"], _bugfix_payload(2))
    rc = dgl.main([])
    assert rc == 0
    assert isolated_artifacts["out_latest"].is_file()
    # ONLY latest.json is created in the sentinel directory.
    entries = sorted(p.name for p in isolated_artifacts["out_dir"].iterdir())
    assert entries == ["latest.json"]


def test_atomic_write_refuses_non_sentinel_path(
    isolated_artifacts: dict[str, Path],
    tmp_path: Path,
) -> None:
    bogus = tmp_path / "logs" / "elsewhere" / "latest.json"
    bogus.parent.mkdir(parents=True, exist_ok=True)
    with pytest.raises(ValueError):
        dgl._atomic_write_json(bogus, {"x": 1})


def test_atomic_write_refuses_seed_jsonl_paths(
    isolated_artifacts: dict[str, Path],
    tmp_path: Path,
) -> None:
    """The sentinel guard refuses any seed.jsonl / delegation_seed.jsonl
    / generated_seed.jsonl write attempt."""
    for name in ("seed.jsonl", "delegation_seed.jsonl", "generated_seed.jsonl"):
        target = tmp_path / name
        with pytest.raises(ValueError):
            dgl._atomic_write_json(target, {"x": 1})
        # And the file must NOT have been created as a side effect.
        assert not target.exists()


# ---------------------------------------------------------------------------
# generated_seed.jsonl ABSENCE invariant
# ---------------------------------------------------------------------------


def test_generated_seed_jsonl_remains_absent_in_repo() -> None:
    """The repo root must not contain ``generated_seed.jsonl`` —
    the A18b writer slice is not authorised."""
    path = REPO_ROOT / "generated_seed.jsonl"
    assert not path.exists(), (
        "generated_seed.jsonl must not exist; the A18b writer slice "
        "is operator-go territory and has not been authorised."
    )


def test_default_mode_does_not_create_generated_seed_jsonl(
    isolated_artifacts: dict[str, Path],
) -> None:
    """Even after running default mode (which writes to its sentinel
    path), generated_seed.jsonl must not appear anywhere under
    tmp_path."""
    _write_artifact(isolated_artifacts["bugfix_loop"], _bugfix_payload(2))
    rc = dgl.main([])
    assert rc == 0
    for found in isolated_artifacts["tmp_root"].rglob("generated_seed.jsonl"):
        raise AssertionError(
            f"generated_seed.jsonl appeared at {found} after A18a run — "
            "A18b writer is not authorised"
        )


def test_no_write_mode_does_not_create_generated_seed_jsonl(
    isolated_artifacts: dict[str, Path],
) -> None:
    _write_artifact(isolated_artifacts["bugfix_loop"], _bugfix_payload(2))
    rc = dgl.main(["--no-write"])
    assert rc == 0
    for found in isolated_artifacts["tmp_root"].rglob("generated_seed.jsonl"):
        raise AssertionError(
            f"generated_seed.jsonl appeared at {found} during --no-write run"
        )


# ---------------------------------------------------------------------------
# Source-text + AST scans
# ---------------------------------------------------------------------------


def _module_source() -> str:
    return Path(dgl.__file__).read_text(encoding="utf-8")


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


def test_no_subprocess_in_module() -> None:
    src = _module_source()
    assert "import subprocess" not in src
    assert "from subprocess" not in src


def test_no_gh_or_git_in_module() -> None:
    src = _module_source()
    for needle in ("subprocess.run", " gh ", " git "):
        assert needle not in src, needle


def test_no_network_imports_in_module() -> None:
    src = _module_source()
    for forbidden in (
        "import socket",
        "import urllib",
        "import http.client",
        "import requests",
        "import httpx",
        "import aiohttp",
    ):
        assert forbidden not in src, forbidden


def test_no_web_push_library_import_in_module() -> None:
    names = _imported_module_names()
    for n in names:
        assert n not in {"pywebpush", "webpush", "web_push"}, n
        assert not n.startswith("pywebpush."), n


def test_no_token_mint_helpers_imported() -> None:
    """A18a must not import the approval-token mint/verify helpers.
    Acting on a generated candidate is N5b / A18b/A18c territory."""
    names = _imported_module_names()
    for forbidden in (
        "reporting.approval_token_gate",
        "reporting.approval_token_runtime",
        "reporting.web_push_real_transport",
    ):
        assert forbidden not in names, forbidden


def test_no_vapid_or_token_env_literal_in_module() -> None:
    src = _module_source()
    assert "WEB_PUSH_VAPID_PRIVATE_KEY" not in src
    assert "ADE_APPROVAL_TOKEN_HMAC_SECRET" not in src


def test_no_decision_verb_call_in_module() -> None:
    src = _module_source().lower()
    for verb in ("approve(", "reject(", "merge(", "deploy(", "trade("):
        assert verb not in src, verb


def test_no_seed_jsonl_writes_in_module() -> None:
    """The literal seed-file names may appear in DOCSTRING / discipline-
    invariant flag names (asserting absence), but must NEVER appear on a
    write code path. The atomic-write helper restricts to the sentinel
    prefix, and the test above pins that helper refuses the seed paths.
    Here we additionally pin that no ``open(...,"w"`` / ``write_text``
    / ``.write(`` call site mentions a seed filename."""
    src = _module_source()
    # Reject open() write modes mentioning seed file names.
    forbidden_write_call_patterns = (
        '"seed.jsonl"',
        '"delegation_seed.jsonl"',
        '"generated_seed.jsonl"',
    )
    # The docstring mentions ``generated_seed.jsonl`` (as the file we
    # do NOT create) and the discipline invariants use
    # ``writes_to_generated_seed_jsonl`` as a flag name. These uses
    # appear OUTSIDE of write-call contexts; we scan executable lines
    # only.
    executable_lines = [
        ln for ln in src.splitlines() if not ln.lstrip().startswith("#")
    ]
    executable = "\n".join(executable_lines)
    # Defense-in-depth: no Python write-call (open(...,"w") /
    # write_text(...) / .write(...)) on the same line as a seed name.
    for line in executable.splitlines():
        if "open(" in line or "write_text(" in line or ".write(" in line:
            for needle in forbidden_write_call_patterns:
                assert needle not in line, (
                    f"seed-name literal {needle!r} appears on a write line: "
                    f"{line!r}"
                )


def test_no_forbidden_module_imports() -> None:
    forbidden_prefixes = (
        "dashboard",
        "frontend",
        "automation",
        "broker",
        "agent.risk",
        "agent.execution",
        "research",
        "reporting.intelligent_routing",
        "live",
        "paper",
        "shadow",
        "trading",
    )
    for module in _imported_module_names():
        for prefix in forbidden_prefixes:
            assert module != prefix, module
            assert not module.startswith(prefix + "."), module


def test_imports_only_stdlib_and_assert_no_secrets() -> None:
    """The projector must import only stdlib plus the secret-redactor
    guard."""
    names = _imported_module_names()
    allowed_reporting = {
        "reporting",
        "reporting.agent_audit_summary",
    }
    for n in names:
        if n == "reporting" or n.startswith("reporting."):
            assert n in allowed_reporting, n


# ---------------------------------------------------------------------------
# Step 5 + Level 6 invariants
# ---------------------------------------------------------------------------


def test_import_does_not_flip_step5_invariants() -> None:
    importlib.reload(dgl)
    assert dgl.step5_implementation_allowed is False
    assert dgl.STEP5_ENABLED_SUBSTAGE == "none"


def test_module_source_pins_step5_invariants() -> None:
    src = _module_source()
    assert "step5_implementation_allowed: Final[bool] = False" in src
    assert 'STEP5_ENABLED_SUBSTAGE: Final[str] = "none"' in src
    assert "step5_implementation_allowed = True" not in src


# ---------------------------------------------------------------------------
# Doc invariants
# ---------------------------------------------------------------------------


def _doc_text() -> str:
    return (
        REPO_ROOT
        / "docs"
        / "governance"
        / "development_generated_lane.md"
    ).read_text(encoding="utf-8")


def test_doc_states_dry_run_only() -> None:
    text = _doc_text().lower()
    assert "dry-run" in text or "report-only" in text


def test_doc_states_writer_not_authorized() -> None:
    text = _doc_text().lower()
    assert "writer is not authorised" in text or (
        "writer is not authorized" in text
    ) or "writer not authorised" in text or (
        "writer not authorized" in text
    )


def test_doc_states_step5_blocked() -> None:
    text = _doc_text().lower()
    assert "step 5" in text
    assert "blocked" in text or "remains blocked" in text or (
        "permanently disabled" in text
    )


def test_doc_states_level_6_permanently_disabled() -> None:
    text = _doc_text().lower()
    assert "level 6" in text
    assert "permanently disabled" in text


def test_doc_mentions_a18b_and_a18c_as_separate_operator_go() -> None:
    text = _doc_text().lower()
    assert "a18b" in text
    assert "a18c" in text
    assert "operator" in text
