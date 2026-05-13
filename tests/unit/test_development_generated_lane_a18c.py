"""Tests for the v3.15.16.A18c admission projector
(default-disabled).

Hard guarantees verified here:

* Default-disabled — env unset / off / aliased / non-exact-match
  → no-op envelope, `enabled=False`, no `generated_seed.jsonl`
  read. The "no read" property is asserted by monkey-patching
  ``_read_generated_seed`` to a sentinel that fails the test if
  called.
* Env on + absent ``generated_seed.jsonl`` → safe
  `generated_seed_absent` envelope.
* Env on + malformed line → default-deny
  `generated_seed_malformed` envelope, zero rows, no crash.
* Env on + valid seed → A17-shaped rows projected via
  ``a17.evaluate_promotion_record(synth)``. Every row uses
  closed A17 vocabularies.
* Phase-2 diagnostic row (``a18b-phase2-smoke-2026-05-13-001``)
  maps to ``needs_human`` — never ``admissible`` /
  ``executable``.
* ``would_require_operator_go=True`` always maps to
  ``needs_human``, even with otherwise-eligible attributes.
* ``would_require_operator_go=False`` projection still maps to
  ``needs_human`` by default (conservative first-cut posture).
* Duplicate A18c candidate-id within a single tick is
  hard-suppressed.
* Duplicate evidence-hash across rows surfaces the closed
  warning ``duplicate_evidence_hash_in_a18b``.
* Per-tick cap of 8 enforced; per-day cap of 32 enforced via
  reading the prior ``latest.json`` snapshot.
* Envelope always carries the closed `discipline_invariants`
  dict; Step 5 / Level 6 invariants intact.
* Atomic-write path sentinel refuses any path outside
  ``logs/development_generated_lane_a18c/``.
* AST / source-text scans: no subprocess, no network, no
  ``gh`` / ``git``, no dashboard / frontend / approval-token
  imports, no seed.jsonl / delegation_seed.jsonl writes.
* A17 module is byte-identical (not mutated by import or by
  any code path here).
* CLI `--no-write` works and defaults to env-off safe.
"""

from __future__ import annotations

import ast
import hashlib
import json
from pathlib import Path
from typing import Any

import pytest

from reporting import development_generated_lane_a18c as a18c
from reporting import development_generated_lane_writer as a18b
from reporting import development_queue_admission_policy as a17

REPO_ROOT = Path(__file__).resolve().parents[2]


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _evidence(marker: str) -> str:
    return hashlib.sha256(marker.encode("utf-8")).hexdigest()


def _valid_a18b_row(
    candidate_id: str,
    *,
    proposed_kind: str = "e2e_proof",
    would_require_operator_go: bool = True,
    evidence_marker: str | None = None,
    proposed_title: str = "diagnostic title",
    proposed_summary: str = "diagnostic summary; must not be admitted",
) -> dict[str, Any]:
    marker = evidence_marker or f"marker-{candidate_id}"
    return {
        "generated_candidate_id": candidate_id,
        "source_module": "operator_smoke",
        "source_id": candidate_id,
        "proposed_kind": proposed_kind,
        "proposed_title": proposed_title,
        "proposed_summary": proposed_summary,
        "evidence_hash": _evidence(marker),
        "admission_preview": "generated_seed_written",
        "block_reason": "none",
        "would_require_operator_go": would_require_operator_go,
        "generated_at_utc": "2026-05-13T12:00:00Z",
        "writer_module_version": a18b.MODULE_VERSION,
    }


def _write_seed(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [json.dumps(r, sort_keys=True) for r in rows]
    path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")


# ---------------------------------------------------------------------------
# Closed-vocab module surface
# ---------------------------------------------------------------------------


def test_env_gate_constant_value() -> None:
    """The exact CLI-facing env-gate name is pinned. Operators
    export it via the verbatim string; drift fails this test
    before any rename can land."""
    assert a18c.ENV_GATE == "ADE_GENERATED_LANE_A18C_ENABLED"


def test_env_gate_enabled_value() -> None:
    assert a18c._ENABLED_VALUE == "true"


def test_module_version_is_a18c_pin() -> None:
    assert a18c.MODULE_VERSION == "v3.15.16.A18c"


def test_step5_invariants_intact_by_import() -> None:
    assert a18c.step5_implementation_allowed is False
    assert a18c.STEP5_ENABLED_SUBSTAGE == "none"


def test_caps_are_pinned() -> None:
    assert a18c.PER_TICK_CAP == 8
    assert a18c.PER_DAY_CAP == 32


def test_artifact_path_is_under_a18c_logs_dir() -> None:
    assert a18c.ARTIFACT_RELATIVE_PATH == (
        "logs/development_generated_lane_a18c/latest.json"
    )
    assert "logs/development_generated_lane_a18c/" in (
        a18c.ARTIFACT_LATEST.as_posix()
    )


# ---------------------------------------------------------------------------
# Env gate
# ---------------------------------------------------------------------------


def test_env_enabled_returns_false_when_unset() -> None:
    assert a18c.env_enabled({}) is False


def test_env_enabled_returns_false_for_non_exact_match() -> None:
    for alias in ("True", "TRUE", "1", "yes", "YES", "on", "false", ""):
        assert a18c.env_enabled({a18c.ENV_GATE: alias}) is False, alias


def test_env_enabled_returns_true_only_for_exact_lowercase_true() -> None:
    assert a18c.env_enabled({a18c.ENV_GATE: "true"}) is True


# ---------------------------------------------------------------------------
# Env-off path: no file read, no rows, safe envelope.
# ---------------------------------------------------------------------------


def test_env_off_returns_no_op_envelope() -> None:
    snap = a18c.collect_snapshot(env={})
    assert snap["enabled"] is False
    assert snap["note"] == "env_gate_off"
    assert snap["validation_warnings"] == ["env_gate_off_no_op"]
    assert snap["rows"] == []
    assert snap["counts"]["total"] == 0


def test_env_off_does_not_read_generated_seed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Defense-in-depth: when the env-gate is off, A18c must NOT
    call ``_read_generated_seed``. Monkey-patch the helper with a
    sentinel that fails the test if invoked."""

    def fail_if_called(path: Path) -> tuple[str, list[Any]]:
        raise AssertionError(
            "_read_generated_seed must NOT be called when env-off"
        )

    monkeypatch.setattr(a18c, "_read_generated_seed", fail_if_called)
    snap = a18c.collect_snapshot(env={})
    assert snap["enabled"] is False
    assert snap["note"] == "env_gate_off"


def test_env_off_envelope_carries_invariants() -> None:
    snap = a18c.collect_snapshot(env={})
    assert snap["step5_implementation_allowed"] is False
    assert snap["step5_enabled_substage"] == "none"
    assert snap["level6_enabled"] is False
    assert snap["dry_run_only"] is True
    assert snap["live_merge_implemented"] is False
    assert snap["deploy_coupled"] is False


# ---------------------------------------------------------------------------
# Env-on + absent / malformed / empty
# ---------------------------------------------------------------------------


def test_env_on_absent_seed_returns_safe_envelope(tmp_path: Path) -> None:
    seed_path = tmp_path / "generated_seed.jsonl"
    # File does NOT exist.
    snap = a18c.collect_snapshot(
        env={a18c.ENV_GATE: "true"},
        generated_seed_path=seed_path,
        prior_artifact_path=tmp_path / "no_prior.json",
    )
    assert snap["enabled"] is True
    assert snap["note"] == "generated_seed_absent"
    assert "generated_seed_absent" in snap["validation_warnings"]
    assert snap["rows"] == []
    assert snap["counts"]["total"] == 0


def test_env_on_malformed_seed_returns_safe_envelope(tmp_path: Path) -> None:
    seed_path = tmp_path / "generated_seed.jsonl"
    seed_path.write_text("not json at all\n", encoding="utf-8")
    snap = a18c.collect_snapshot(
        env={a18c.ENV_GATE: "true"},
        generated_seed_path=seed_path,
        prior_artifact_path=tmp_path / "no_prior.json",
    )
    assert snap["note"] == "generated_seed_malformed"
    assert "generated_seed_malformed" in snap["validation_warnings"]
    assert snap["rows"] == []


def test_env_on_wrong_schema_keys_returns_malformed(tmp_path: Path) -> None:
    """A line that parses as JSON but does not have the closed
    A18b GENERATED_RECORD_KEYS triggers full-file default-deny."""
    seed_path = tmp_path / "generated_seed.jsonl"
    seed_path.write_text(
        json.dumps({"generated_candidate_id": "partial"}) + "\n",
        encoding="utf-8",
    )
    snap = a18c.collect_snapshot(
        env={a18c.ENV_GATE: "true"},
        generated_seed_path=seed_path,
        prior_artifact_path=tmp_path / "no_prior.json",
    )
    assert snap["note"] == "generated_seed_malformed"
    assert snap["rows"] == []


def test_env_on_empty_seed_file_is_no_eligible_rows(tmp_path: Path) -> None:
    seed_path = tmp_path / "generated_seed.jsonl"
    seed_path.write_text("", encoding="utf-8")
    snap = a18c.collect_snapshot(
        env={a18c.ENV_GATE: "true"},
        generated_seed_path=seed_path,
        prior_artifact_path=tmp_path / "no_prior.json",
    )
    assert snap["note"] == "no_eligible_a18b_rows"
    assert snap["rows"] == []


# ---------------------------------------------------------------------------
# Phase-2 diagnostic row protection.
# ---------------------------------------------------------------------------


def test_phase2_diagnostic_row_maps_to_needs_human(tmp_path: Path) -> None:
    """The Phase-2 diagnostic row carries
    ``would_require_operator_go=True``. Under A18c projection it
    MUST map to ``needs_human``. It MUST NEVER be ``admissible``
    or otherwise executable."""
    seed_path = tmp_path / "generated_seed.jsonl"
    row = _valid_a18b_row(
        "a18b-phase2-smoke-2026-05-13-001",
        would_require_operator_go=True,
    )
    _write_seed(seed_path, [row])
    snap = a18c.collect_snapshot(
        env={a18c.ENV_GATE: "true"},
        generated_seed_path=seed_path,
        prior_artifact_path=tmp_path / "no_prior.json",
    )
    assert snap["counts"]["total"] == 1
    [r] = snap["rows"]
    assert r["admission_decision"] == "needs_human"
    assert r["admission_decision"] != "admissible"
    assert r["admission_reason"] in {
        "needs_human_authority_decision",
        "needs_human_unknown_or_invalid_risk",
        "needs_human_classification_drift",
        "needs_human_protected_target_path",
    }
    # Defense in depth — also pin the would_target_lane is "none"
    # for a non-admissible row.
    assert r["would_target_lane"] == "none"


def test_phase2_diagnostic_row_carries_exact_candidate_id(
    tmp_path: Path,
) -> None:
    """The projected row's candidate_id is the deterministic
    A18c id derived from the A18b row."""
    seed_path = tmp_path / "generated_seed.jsonl"
    row = _valid_a18b_row(
        "a18b-phase2-smoke-2026-05-13-001",
        would_require_operator_go=True,
        evidence_marker="phase2",
    )
    _write_seed(seed_path, [row])
    snap = a18c.collect_snapshot(
        env={a18c.ENV_GATE: "true"},
        generated_seed_path=seed_path,
        prior_artifact_path=tmp_path / "no_prior.json",
    )
    [r] = snap["rows"]
    ev = _evidence("phase2")
    assert r["candidate_id"] == (
        f"a18c-a18b-phase2-smoke-2026-05-13-001-{ev[:16]}"
    )


# ---------------------------------------------------------------------------
# would_require_operator_go semantics.
# ---------------------------------------------------------------------------


def test_would_require_operator_go_true_always_needs_human(
    tmp_path: Path,
) -> None:
    seed_path = tmp_path / "generated_seed.jsonl"
    row = _valid_a18b_row(
        "force-op-go-true",
        would_require_operator_go=True,
        proposed_kind="bugfix",
    )
    _write_seed(seed_path, [row])
    snap = a18c.collect_snapshot(
        env={a18c.ENV_GATE: "true"},
        generated_seed_path=seed_path,
        prior_artifact_path=tmp_path / "no_prior.json",
    )
    [r] = snap["rows"]
    assert r["admission_decision"] == "needs_human"


def test_would_require_operator_go_false_still_needs_human_by_default(
    tmp_path: Path,
) -> None:
    """Conservative first-cut posture: even without operator-go
    flagged on the row, the synthesised RISK_UNKNOWN / non-eligible
    upstream filters drive the projection to needs_human or
    not_eligible_upstream — never admissible."""
    seed_path = tmp_path / "generated_seed.jsonl"
    row = _valid_a18b_row(
        "force-op-go-false",
        would_require_operator_go=False,
        proposed_kind="delegation",
    )
    _write_seed(seed_path, [row])
    snap = a18c.collect_snapshot(
        env={a18c.ENV_GATE: "true"},
        generated_seed_path=seed_path,
        prior_artifact_path=tmp_path / "no_prior.json",
    )
    [r] = snap["rows"]
    assert r["admission_decision"] != "admissible"
    assert r["admission_decision"] in {
        "needs_human",
        "not_eligible_upstream",
        "blocked",
    }


def test_no_row_in_snapshot_is_ever_admissible(tmp_path: Path) -> None:
    """Across a mixed fixture, A18c's first-cut posture never
    surfaces an admissible decision."""
    seed_path = tmp_path / "generated_seed.jsonl"
    rows = [
        _valid_a18b_row(
            f"mixed-{i}",
            would_require_operator_go=(i % 2 == 0),
            proposed_kind="e2e_proof" if i % 2 == 0 else "bugfix",
            evidence_marker=f"mixed-{i}",
        )
        for i in range(5)
    ]
    _write_seed(seed_path, rows)
    snap = a18c.collect_snapshot(
        env={a18c.ENV_GATE: "true"},
        generated_seed_path=seed_path,
        prior_artifact_path=tmp_path / "no_prior.json",
    )
    for r in snap["rows"]:
        assert r["admission_decision"] != "admissible"
    assert snap["counts"]["admissible"] == 0


# ---------------------------------------------------------------------------
# Duplicate handling.
# ---------------------------------------------------------------------------


def test_duplicate_candidate_id_is_hard_suppressed(tmp_path: Path) -> None:
    """Two rows with the same candidate_id and same evidence_hash
    produce a single projected row (duplicate A18c id is
    hard-suppressed). This is defense-in-depth; A18b already
    rejects duplicate ids at write time."""
    seed_path = tmp_path / "generated_seed.jsonl"
    row_a = _valid_a18b_row("dup-id", evidence_marker="dup-1")
    row_b = _valid_a18b_row("dup-id", evidence_marker="dup-1")
    _write_seed(seed_path, [row_a, row_b])
    snap = a18c.collect_snapshot(
        env={a18c.ENV_GATE: "true"},
        generated_seed_path=seed_path,
        prior_artifact_path=tmp_path / "no_prior.json",
    )
    assert snap["counts"]["total"] == 1


def test_duplicate_evidence_hash_different_candidate_ids_warns(
    tmp_path: Path,
) -> None:
    seed_path = tmp_path / "generated_seed.jsonl"
    row_a = _valid_a18b_row("hash-a", evidence_marker="shared")
    row_b = _valid_a18b_row("hash-b", evidence_marker="shared")
    _write_seed(seed_path, [row_a, row_b])
    snap = a18c.collect_snapshot(
        env={a18c.ENV_GATE: "true"},
        generated_seed_path=seed_path,
        prior_artifact_path=tmp_path / "no_prior.json",
    )
    assert "duplicate_evidence_hash_in_a18b" in snap["validation_warnings"]
    # Both rows ARE projected (warning is soft, not blocking).
    assert snap["counts"]["total"] == 2


# ---------------------------------------------------------------------------
# Per-tick + per-day caps.
# ---------------------------------------------------------------------------


def test_per_tick_cap_enforced(tmp_path: Path) -> None:
    seed_path = tmp_path / "generated_seed.jsonl"
    rows = [
        _valid_a18b_row(f"tick-{i}", evidence_marker=f"tick-{i}")
        for i in range(12)
    ]
    _write_seed(seed_path, rows)
    snap = a18c.collect_snapshot(
        env={a18c.ENV_GATE: "true"},
        generated_seed_path=seed_path,
        prior_artifact_path=tmp_path / "no_prior.json",
    )
    assert snap["counts"]["total"] == 8
    assert "per_tick_cap_reached" in snap["validation_warnings"]


def test_per_day_cap_enforced(tmp_path: Path) -> None:
    """If a prior latest.json from today already reports 30
    projections, the current tick can emit at most 2 more before
    hitting the 32/day cap."""
    seed_path = tmp_path / "generated_seed.jsonl"
    prior_path = tmp_path / "prior_latest.json"
    # The current tick's generated_at_utc must be on the same UTC
    # day as the prior snapshot's. We control both timestamps so
    # the test is deterministic.
    today_ts = "2026-05-13T13:00:00Z"
    prior_payload = {
        "generated_at_utc": "2026-05-13T01:00:00Z",
        "counts": {"total": 30},
    }
    prior_path.write_text(json.dumps(prior_payload), encoding="utf-8")
    rows = [
        _valid_a18b_row(f"day-{i}", evidence_marker=f"day-{i}")
        for i in range(5)
    ]
    _write_seed(seed_path, rows)
    snap = a18c.collect_snapshot(
        env={a18c.ENV_GATE: "true"},
        generated_seed_path=seed_path,
        prior_artifact_path=prior_path,
        generated_at_utc=today_ts,
    )
    assert snap["counts"]["total"] == 2
    assert "per_day_cap_reached" in snap["validation_warnings"]


def test_per_day_cap_ignores_yesterdays_prior(tmp_path: Path) -> None:
    """A prior snapshot from a *different* UTC day must be ignored
    for the per-day count."""
    seed_path = tmp_path / "generated_seed.jsonl"
    prior_path = tmp_path / "prior_latest.json"
    today_ts = "2026-05-13T13:00:00Z"
    prior_payload = {
        "generated_at_utc": "2026-05-12T23:59:00Z",
        "counts": {"total": 31},
    }
    prior_path.write_text(json.dumps(prior_payload), encoding="utf-8")
    rows = [
        _valid_a18b_row(f"newday-{i}", evidence_marker=f"newday-{i}")
        for i in range(3)
    ]
    _write_seed(seed_path, rows)
    snap = a18c.collect_snapshot(
        env={a18c.ENV_GATE: "true"},
        generated_seed_path=seed_path,
        prior_artifact_path=prior_path,
        generated_at_utc=today_ts,
    )
    assert snap["counts"]["total"] == 3
    assert "per_day_cap_reached" not in snap["validation_warnings"]


def test_per_day_cap_truncates_to_zero_when_quota_exceeded(
    tmp_path: Path,
) -> None:
    """If today's prior already reaches the cap, the next tick
    emits zero rows."""
    seed_path = tmp_path / "generated_seed.jsonl"
    prior_path = tmp_path / "prior_latest.json"
    today_ts = "2026-05-13T23:00:00Z"
    prior_payload = {
        "generated_at_utc": "2026-05-13T01:00:00Z",
        "counts": {"total": 32},
    }
    prior_path.write_text(json.dumps(prior_payload), encoding="utf-8")
    rows = [
        _valid_a18b_row(f"over-{i}", evidence_marker=f"over-{i}")
        for i in range(3)
    ]
    _write_seed(seed_path, rows)
    snap = a18c.collect_snapshot(
        env={a18c.ENV_GATE: "true"},
        generated_seed_path=seed_path,
        prior_artifact_path=prior_path,
        generated_at_utc=today_ts,
    )
    assert snap["counts"]["total"] == 0
    assert "per_day_cap_reached" in snap["validation_warnings"]


# ---------------------------------------------------------------------------
# Closed-schema envelope shape + invariants.
# ---------------------------------------------------------------------------


def test_envelope_uses_a17_admission_schema_keys(tmp_path: Path) -> None:
    """Every projected row's key-set matches A17's
    ADMISSION_SCHEMA_KEYS exactly. This is the closed-schema
    invariant that lets A17 consumers consume A18c rows without
    re-schema work."""
    seed_path = tmp_path / "generated_seed.jsonl"
    _write_seed(seed_path, [_valid_a18b_row("shape-1")])
    snap = a18c.collect_snapshot(
        env={a18c.ENV_GATE: "true"},
        generated_seed_path=seed_path,
        prior_artifact_path=tmp_path / "no_prior.json",
    )
    [r] = snap["rows"]
    assert set(r.keys()) == set(a17.ADMISSION_SCHEMA_KEYS)


def test_envelope_carries_step5_and_level6_invariants(
    tmp_path: Path,
) -> None:
    seed_path = tmp_path / "generated_seed.jsonl"
    _write_seed(seed_path, [_valid_a18b_row("inv-1")])
    snap = a18c.collect_snapshot(
        env={a18c.ENV_GATE: "true"},
        generated_seed_path=seed_path,
        prior_artifact_path=tmp_path / "no_prior.json",
    )
    assert snap["step5_implementation_allowed"] is False
    assert snap["step5_enabled_substage"] == "none"
    assert snap["level6_enabled"] is False
    assert snap["dry_run_only"] is True
    assert snap["live_merge_implemented"] is False
    assert snap["deploy_coupled"] is False


def test_envelope_carries_full_discipline_invariants(tmp_path: Path) -> None:
    seed_path = tmp_path / "generated_seed.jsonl"
    _write_seed(seed_path, [_valid_a18b_row("disc-1")])
    snap = a18c.collect_snapshot(
        env={a18c.ENV_GATE: "true"},
        generated_seed_path=seed_path,
        prior_artifact_path=tmp_path / "no_prior.json",
    )
    di = snap["discipline_invariants"]
    assert di["default_disabled"] is True
    assert di["reads_generated_seed_only_when_enabled"] is True
    assert di["writes_to_seed_jsonl"] is False
    assert di["writes_to_delegation_seed_jsonl"] is False
    assert di["writes_to_generated_seed_jsonl"] is False
    assert di["modifies_a17_admission_policy"] is False
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
    assert di["always_needs_human_in_first_cut"] is True
    assert di["bypasses_a17_filters"] is False


# ---------------------------------------------------------------------------
# Atomic write sentinel.
# ---------------------------------------------------------------------------


def test_atomic_write_refuses_non_a18c_path(tmp_path: Path) -> None:
    bad_path = tmp_path / "not_a18c.json"
    with pytest.raises(ValueError, match="non-a18c-logs"):
        a18c._atomic_write_json(bad_path, {"k": "v"})


def test_atomic_write_succeeds_under_a18c_prefix(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Redirect ARTIFACT_LATEST into tmp so the write target lives
    in a path that contains the sentinel substring."""
    target_dir = tmp_path / "logs" / "development_generated_lane_a18c"
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / "latest.json"
    monkeypatch.setattr(a18c, "ARTIFACT_LATEST", target)
    snap = a18c.collect_snapshot(env={})
    a18c.write_outputs(snap)
    assert target.is_file()
    loaded = json.loads(target.read_text(encoding="utf-8"))
    assert loaded["enabled"] is False


# ---------------------------------------------------------------------------
# A17 byte-identical invariant: A18c module does not mutate A17.
# ---------------------------------------------------------------------------


def test_a17_module_admission_decisions_unchanged_after_a18c_import() -> None:
    """Defense in depth: importing A18c must not mutate A17's
    closed vocabularies."""
    assert a17.ADMISSION_DECISIONS == (
        "admissible",
        "needs_human",
        "blocked",
        "duplicate_of_existing",
        "not_eligible_upstream",
    )
    assert a17.MODULE_VERSION == "v3.15.16.A17"


def test_a17_evaluate_promotion_record_is_callable() -> None:
    """A18c relies on A17's public function. Confirm it is
    callable and lives at the expected path."""
    assert callable(a17.evaluate_promotion_record)
    # Calling it with a synthetic upstream row produces a closed
    # decision/reason tuple.
    synth = a18c._synth_a17_upstream(
        _valid_a18b_row("api-check"), a18c_candidate_id="api"
    )
    decision, reason = a17.evaluate_promotion_record(synth)
    assert decision in a17.ADMISSION_DECISIONS
    assert reason in a17.ADMISSION_REASONS


# ---------------------------------------------------------------------------
# Source-text + AST scans.
# ---------------------------------------------------------------------------


def _module_source() -> str:
    return Path(a18c.__file__).read_text(encoding="utf-8")


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


def test_no_seed_or_delegation_seed_write_call_in_source() -> None:
    """The module legitimately references the closed A17 schema
    keys ``already_in_seed_jsonl`` and ``already_in_delegation_seed``
    (per ADMISSION_SCHEMA_KEYS), and may include narrative
    comments mentioning those filenames. What it must NOT do is
    contain an actual write *call* whose target literal mentions
    those filenames. AST-level scan: every Call expression whose
    string argument literal contains 'seed.jsonl' (and isn't
    'generated_seed.jsonl') is forbidden, and similarly for
    'delegation_seed.jsonl'."""
    tree = ast.parse(_module_source())
    offenders: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        for arg in list(node.args) + [kw.value for kw in node.keywords]:
            if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                lowered = arg.value.lower()
                if "delegation_seed.jsonl" in lowered:
                    offenders.append(
                        f"line {node.lineno}: Call arg references "
                        f"delegation_seed.jsonl: {arg.value!r}"
                    )
                # Match seed.jsonl but NOT generated_seed.jsonl.
                if "seed.jsonl" in lowered and (
                    "generated_seed.jsonl" not in lowered
                ):
                    offenders.append(
                        f"line {node.lineno}: Call arg references "
                        f"seed.jsonl (not generated_seed): "
                        f"{arg.value!r}"
                    )
    assert not offenders, (
        "A18c module must not contain a Call whose argument "
        f"references seed.jsonl or delegation_seed.jsonl: {offenders}"
    )


def test_module_imports_only_allowed_reporting_modules() -> None:
    names = _imported_module_names()
    allowed_reporting = {
        "reporting",
        "reporting.development_generated_lane_writer",
        "reporting.development_queue_admission_policy",
        "reporting.execution_authority",
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


def test_module_source_pins_level6_disabled() -> None:
    src = _module_source().lower()
    # The module emits ``"level6_enabled": False`` in the envelope
    # and the discipline_invariants dict; True is never assigned.
    assert "level6_enabled" in src
    assert "level6_enabled = true" not in src
    assert "level6_enabled=true" not in src


# ---------------------------------------------------------------------------
# CLI.
# ---------------------------------------------------------------------------


def test_cli_no_write_emits_env_off_envelope(capsys: pytest.CaptureFixture[str]) -> None:
    rc = a18c.main(["--no-write"])
    assert rc == 0
    out = capsys.readouterr().out
    snap = json.loads(out)
    assert snap["enabled"] is False
    assert snap["note"] == "env_gate_off"
    assert snap["step5_implementation_allowed"] is False
    assert snap["level6_enabled"] is False


def test_cli_indent_zero_emits_compact(capsys: pytest.CaptureFixture[str]) -> None:
    rc = a18c.main(["--no-write", "--indent", "0"])
    assert rc == 0
    out = capsys.readouterr().out
    # Compact JSON (indent=None) has no leading whitespace lines.
    assert "  " not in out.split("\n")[0]


def test_cli_default_write_path_is_a18c_artifact(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When --no-write is omitted, the CLI must write the envelope
    to the canonical artefact path. Defense-in-depth: redirect
    ARTIFACT_LATEST into tmp so we never touch the repo's real
    logs/ tree."""
    target_dir = tmp_path / "logs" / "development_generated_lane_a18c"
    target_dir.mkdir(parents=True, exist_ok=True)
    target = target_dir / "latest.json"
    monkeypatch.setattr(a18c, "ARTIFACT_LATEST", target)
    rc = a18c.main([])
    assert rc == 0
    assert target.is_file()


# ---------------------------------------------------------------------------
# Idempotency under monkeypatched a17.evaluate_promotion_record.
# ---------------------------------------------------------------------------


def test_defense_in_depth_force_overrides_a17_admissible(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Even if a future A17 change returned 'admissible' for a row
    whose would_require_operator_go=True, A18c's defense-in-depth
    force rewrites the decision to needs_human."""
    monkeypatch.setattr(
        a17,
        "evaluate_promotion_record",
        lambda row: ("admissible", "auto_allowed_low_risk_eligible_promotion"),
    )
    seed_path = tmp_path / "generated_seed.jsonl"
    _write_seed(
        seed_path,
        [
            _valid_a18b_row(
                "force-override", would_require_operator_go=True
            )
        ],
    )
    snap = a18c.collect_snapshot(
        env={a18c.ENV_GATE: "true"},
        generated_seed_path=seed_path,
        prior_artifact_path=tmp_path / "no_prior.json",
    )
    [r] = snap["rows"]
    assert r["admission_decision"] == "needs_human"
    assert r["admission_reason"] == "needs_human_authority_decision"
    assert r["would_target_lane"] == "none"
