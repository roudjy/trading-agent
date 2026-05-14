"""Pin tests for the v3.15.16.A15.B2.0b Agent Activity Center
read-only aggregator (``reporting.development_agent_activity_timeline``).

These tests pin:

* closed vocabularies and module-version anchor;
* AST-level absence of subprocess / network / QRE imports;
* AST-level absence of ``os.environ`` reads;
* source-text absence of GitHub CLI / version-control CLI tokens
  and ``os.system`` / ``popen`` / ``shell=True``;
* context-aware AST scan rejecting any *write-call context*
  targeting ``seed.jsonl`` / ``generated_seed.jsonl`` /
  ``delegation_seed.jsonl`` (the module is permitted to mention
  ``generated_seed.jsonl`` as a *read path* in the catalog);
* the sentinel-restricted write helper refuses non-allowlist
  paths;
* the persisted envelope carries all 12 required top-level keys;
* deterministic output across two consecutive calls with the same
  injected ``generated_at_utc``;
* graceful absence (every upstream missing) → valid empty
  envelope;
* graceful malformation → ``parse_ok=False`` with ``parse_error``,
  no raise;
* read-only over upstreams (sha256 byte-equality before/after a
  run);
* narrow v0.1 projection: WorkItems emitted only from
  ``step5_loop``, ``generated_lane_a18c``,
  ``generated_lane_promotion``, ``merge_preflight``;
* health-only upstreams emit no WorkItems;
* operator-approved invariant defaults (``agent_service`` static
  ``healthy`` / ``on``);
* A18c rows: ``required_phrase`` stays ``None`` (no synthesis);
* A18 promotion-report rows: ``required_phrase`` sourced from the
  row when present;
* CLI ``--no-write`` does not mutate ``logs/`` and the default run
  materialises the tmp-redirected canonical path.

These tests are stdlib + pytest only. No subprocess. No network.
No env writes. No mutation outside ``tmp_path``.
"""

from __future__ import annotations

import ast
import hashlib
import inspect
import io
import json
import sys
from pathlib import Path
from typing import Any

import pytest

from reporting import development_agent_activity_timeline as aat

REPO_ROOT = Path(__file__).resolve().parents[2]


# ---------------------------------------------------------------------------
# Fixtures and helpers
# ---------------------------------------------------------------------------


def _module_source() -> str:
    return Path(aat.__file__).read_text(encoding="utf-8")


def _module_ast() -> ast.AST:
    return ast.parse(_module_source())


def _redirect_to_tmp(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> Path:
    """Redirect aggregator paths into a hermetic tmp tree."""
    tmp_logs = tmp_path / "logs"
    tmp_aat_dir = tmp_logs / "development_agent_activity_timeline"
    tmp_aat_dir.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(aat, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(aat, "ARTIFACT_DIR", tmp_aat_dir)
    monkeypatch.setattr(
        aat, "ARTIFACT_LATEST", tmp_aat_dir / "latest.json"
    )
    return tmp_logs


def _write_upstream(
    tmp_path: Path, rel_path: str, payload: dict[str, Any]
) -> Path:
    """Write an upstream JSON file into the hermetic tmp tree."""
    target = tmp_path / rel_path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(payload, sort_keys=True), encoding="utf-8"
    )
    return target


def _sha256_of(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


# ---------------------------------------------------------------------------
# Closed vocab and constants
# ---------------------------------------------------------------------------


def test_module_version_is_aat_v0_1() -> None:
    assert aat.MODULE_VERSION == "aat.v0.1"


def test_report_kind_is_agent_activity_timeline() -> None:
    assert aat.REPORT_KIND == "agent_activity_timeline"


def test_schema_version_is_1() -> None:
    assert aat.SCHEMA_VERSION == 1


def test_step5_implementation_allowed_is_false_constant() -> None:
    assert aat.step5_implementation_allowed is False


def test_step5_enabled_substage_is_none_constant() -> None:
    assert aat.STEP5_ENABLED_SUBSTAGE == "none"


def test_closed_vocab_cardinalities() -> None:
    """Pin the cardinalities of every closed vocab and the three
    catalog cardinality constants."""
    assert len(aat.STAGES) == 11
    assert len(aat.SEVERITIES) == 4
    assert len(aat.DECISIONS) == 16
    assert len(aat.RISKS) == 4
    assert len(aat.FRESHNESS_STATES) == 4
    assert len(aat.ARTIFACT_HEALTH_STATES) == 5
    assert len(aat.HUMAN_ACTION_TYPES) == 4
    assert len(aat.INVARIANT_STATES) == 5
    assert len(aat.SOURCE_KINDS) == 13
    assert len(aat.AGENT_ROLES) == 16
    assert len(aat.EVENT_TYPES) == 16
    assert aat.UPSTREAM_CATALOG_LEN == 11
    assert aat.PROJECTABLE_UPSTREAM_LEN == 4
    assert aat.HEALTH_ONLY_UPSTREAM_LEN == 7
    assert len(aat.UPSTREAM_CATALOG) == aat.UPSTREAM_CATALOG_LEN


def test_upstream_catalog_partition_is_exhaustive_and_mutually_exclusive() -> None:
    """Every catalog entry is either projectable or health-only;
    never both, never neither. Counts match the constants."""
    projectable = [c for c in aat.UPSTREAM_CATALOG if c[3] is True]
    health_only = [c for c in aat.UPSTREAM_CATALOG if c[3] is False]
    assert len(projectable) == aat.PROJECTABLE_UPSTREAM_LEN
    assert len(health_only) == aat.HEALTH_ONLY_UPSTREAM_LEN
    assert (
        len(projectable) + len(health_only) == aat.UPSTREAM_CATALOG_LEN
    )
    # Exhaustive: every entry has a boolean (not None) in slot 3.
    for entry in aat.UPSTREAM_CATALOG:
        assert isinstance(entry[3], bool)


def test_invariant_keys_match_schema_invariant_state_vocab() -> None:
    """Every InvariantStatus row's ``tone`` belongs to the closed
    ``invariant_state`` vocab."""
    snap = aat.collect_snapshot(
        repo_root=Path("/nonexistent"),
        generated_at_utc="2026-05-14T00:00:00Z",
    )
    for row in snap["invariant_status"]:
        assert row["tone"] in aat.INVARIANT_STATES


def test_ttl_defaults_match_operator_pinned_values() -> None:
    """TTL defaults are pinned per operator approval."""
    assert aat.TTL_BY_GROUP == {
        "queue": 600,
        "loops": 1800,
        "step5": 1800,
        "gates": 1800,
        "generated": 1800,
        "digest": 1800,
        "seed": 86400,
    }


# ---------------------------------------------------------------------------
# AST scans
# ---------------------------------------------------------------------------


_FORBIDDEN_TOP_LEVEL_IMPORTS = (
    "subprocess",
    "socket",
    "urllib",
    "requests",
    "httpx",
    "aiohttp",
)

_FORBIDDEN_QRE_IMPORTS = (
    "research",
    "automation",
    "broker",
)

_FORBIDDEN_QRE_FROM_PREFIXES = (
    "research",
    "automation",
    "broker",
    "agent.risk",
    "agent.execution",
    "reporting.intelligent_routing",
)


def test_module_has_no_subprocess_or_network_imports() -> None:
    tree = _module_ast()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                top = alias.name.split(".", 1)[0]
                assert top not in _FORBIDDEN_TOP_LEVEL_IMPORTS, (
                    f"forbidden import: {alias.name!r}"
                )
        if isinstance(node, ast.ImportFrom) and node.module is not None:
            top = node.module.split(".", 1)[0]
            assert top not in _FORBIDDEN_TOP_LEVEL_IMPORTS, (
                f"forbidden import: from {node.module!r}"
            )


def test_module_has_no_qre_or_dashboard_imports() -> None:
    tree = _module_ast()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                top = alias.name.split(".", 1)[0]
                assert top not in _FORBIDDEN_QRE_IMPORTS, (
                    f"forbidden QRE import: {alias.name!r}"
                )
                assert alias.name != "dashboard.dashboard"
        if isinstance(node, ast.ImportFrom) and node.module is not None:
            for prefix in _FORBIDDEN_QRE_FROM_PREFIXES:
                assert not (
                    node.module == prefix or node.module.startswith(prefix + ".")
                ), f"forbidden QRE/dashboard import: from {node.module!r}"
            assert node.module != "dashboard.dashboard"


def test_module_has_no_os_environ_read() -> None:
    """Stricter than merge-preflight: ``_compute_invariant_status``
    must source from artefacts only."""
    tree = _module_ast()
    for node in ast.walk(tree):
        # ``os.environ[...]`` subscript or attribute chain.
        if isinstance(node, ast.Attribute):
            if (
                node.attr == "environ"
                and isinstance(node.value, ast.Name)
                and node.value.id == "os"
            ):
                raise AssertionError(
                    "aggregator references os.environ — forbidden"
                )
        # ``os.getenv(...)`` call.
        if isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Attribute):
                if (
                    func.attr == "getenv"
                    and isinstance(func.value, ast.Name)
                    and func.value.id == "os"
                ):
                    raise AssertionError(
                        "aggregator calls os.getenv — forbidden"
                    )


def test_module_source_has_no_gh_or_git_or_os_system_tokens() -> None:
    """Source-text scan for write-call CLI tokens. Module-level
    scan; bare docstring mentions of ``subprocess`` are tolerated
    where the actual scan targets a syntactic pattern."""
    src = _module_source()
    # The exact patterns we forbid are syntactic, not bare words.
    forbidden = (
        "subprocess.run(",
        "subprocess.Popen(",
        "subprocess.call(",
        "os.system(",
        "os.popen(",
        "shell=True",
        "shell = True",
    )
    for needle in forbidden:
        assert needle not in src, (
            f"aggregator source contains forbidden invocation: {needle!r}"
        )


def test_module_writes_no_seed_files_context_aware() -> None:
    """Context-aware scan: the module is permitted to mention
    ``generated_seed.jsonl`` as a *read path* in the catalog, but
    must not call any write helper with a path argument that
    contains a seed-JSONL filename.

    Closed list of write contexts scanned:

    * ``open(<lit>, mode=<lit>)`` where mode contains 'w'/'a'/'x';
    * ``<x>.write_text(...)`` / ``<x>.write_bytes(...)``;
    * ``os.replace(<src>, <dst>)`` where ``<dst>`` resolves to a
      seed literal;
    * ``_atomic_write_json(<target>, ...)`` where ``<target>``
      resolves to a seed literal.

    The aggregator's only write context in v0.1 is
    ``_atomic_write_json(ARTIFACT_LATEST, snapshot)``, which is
    sentinel-restricted to ``logs/development_agent_activity_timeline/``.
    """
    src = _module_source()
    tree = ast.parse(src)
    seed_names = (
        "seed.jsonl",
        "generated_seed.jsonl",
        "delegation_seed.jsonl",
    )

    def _string_contains_seed(node: ast.AST) -> bool:
        return (
            isinstance(node, ast.Constant)
            and isinstance(node.value, str)
            and any(name in node.value for name in seed_names)
        )

    for call in ast.walk(tree):
        if not isinstance(call, ast.Call):
            continue
        func = call.func

        # Case A: open(<lit>, "w"|"a"|"x"|...).
        is_open = (
            isinstance(func, ast.Name) and func.id == "open"
        ) or (
            isinstance(func, ast.Attribute) and func.attr == "open"
        )
        if is_open and call.args:
            first = call.args[0]
            mode_is_write = False
            if len(call.args) >= 2 and isinstance(
                call.args[1], ast.Constant
            ):
                mode = call.args[1].value
                if isinstance(mode, str) and any(
                    ch in mode for ch in ("w", "a", "x")
                ):
                    mode_is_write = True
            for kw in call.keywords:
                if kw.arg == "mode" and isinstance(kw.value, ast.Constant):
                    mode = kw.value.value
                    if isinstance(mode, str) and any(
                        ch in mode for ch in ("w", "a", "x")
                    ):
                        mode_is_write = True
            if mode_is_write and _string_contains_seed(first):
                raise AssertionError(
                    f"forbidden seed write via open(): {ast.dump(call)}"
                )

        # Case B: <x>.write_text(<lit>...) / <x>.write_bytes(<lit>...).
        if isinstance(func, ast.Attribute) and func.attr in {
            "write_text",
            "write_bytes",
        }:
            # The receiver must not be a Constant string with a
            # seed filename (uncommon but pinned).
            if _string_contains_seed(func.value):
                raise AssertionError(
                    f"forbidden seed write_text/_bytes: {ast.dump(call)}"
                )

        # Case C: os.replace(<src>, <dst>) where <dst> is a seed
        # literal.
        if (
            isinstance(func, ast.Attribute)
            and func.attr == "replace"
            and isinstance(func.value, ast.Name)
            and func.value.id == "os"
            and len(call.args) >= 2
        ):
            dst = call.args[1]
            if _string_contains_seed(dst):
                raise AssertionError(
                    f"forbidden seed os.replace target: {ast.dump(call)}"
                )

        # Case D: _atomic_write_json(<target>, ...).
        is_atomic_write = (
            isinstance(func, ast.Name)
            and func.id == "_atomic_write_json"
        ) or (
            isinstance(func, ast.Attribute)
            and func.attr == "_atomic_write_json"
        )
        if is_atomic_write and call.args:
            first = call.args[0]
            if _string_contains_seed(first):
                raise AssertionError(
                    "forbidden seed _atomic_write_json target"
                )


# ---------------------------------------------------------------------------
# Write-path sentinel
# ---------------------------------------------------------------------------


def test_atomic_write_refuses_paths_outside_logs_aat(
    tmp_path: Path,
) -> None:
    with pytest.raises(ValueError):
        aat._atomic_write_json(
            tmp_path / "foo.json", {"hello": "world"}
        )


def test_write_outputs_writes_to_canonical_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    tmp_logs = _redirect_to_tmp(monkeypatch, tmp_path)
    snap = aat.collect_snapshot(
        repo_root=tmp_path,
        generated_at_utc="2026-05-14T00:00:00Z",
    )
    written = aat.write_outputs(snap)
    assert written == (
        tmp_logs / "development_agent_activity_timeline" / "latest.json"
    )
    assert written.is_file()


# ---------------------------------------------------------------------------
# Schema fidelity
# ---------------------------------------------------------------------------


def test_envelope_contains_all_required_top_level_keys() -> None:
    snap = aat.collect_snapshot(
        repo_root=Path("/nonexistent"),
        generated_at_utc="2026-05-14T00:00:00Z",
    )
    required = {
        "schema_version",
        "module_version",
        "report_kind",
        "generated_at_utc",
        "freshness",
        "counts",
        "work_items",
        "agent_events",
        "human_actions",
        "artifact_health",
        "invariant_status",
        "vocabularies",
    }
    assert required.issubset(set(snap.keys()))


def test_envelope_carries_module_version_anchor() -> None:
    snap = aat.collect_snapshot(
        repo_root=Path("/nonexistent"),
        generated_at_utc="2026-05-14T00:00:00Z",
    )
    assert snap["module_version"] == "aat.v0.1"
    assert snap["schema_version"] == 1
    assert snap["report_kind"] == "agent_activity_timeline"


def test_envelope_vocabularies_block_matches_constants() -> None:
    snap = aat.collect_snapshot(
        repo_root=Path("/nonexistent"),
        generated_at_utc="2026-05-14T00:00:00Z",
    )
    vocab = snap["vocabularies"]
    assert vocab["stage"] == list(aat.STAGES)
    assert vocab["severity"] == list(aat.SEVERITIES)
    assert vocab["decision"] == list(aat.DECISIONS)
    assert vocab["risk"] == list(aat.RISKS)
    assert vocab["freshness"] == list(aat.FRESHNESS_STATES)
    assert vocab["artifact_health"] == list(aat.ARTIFACT_HEALTH_STATES)
    assert vocab["human_action"] == list(aat.HUMAN_ACTION_TYPES)
    assert vocab["invariant_state"] == list(aat.INVARIANT_STATES)


def test_envelope_invariant_status_includes_level_6_danger_off() -> None:
    snap = aat.collect_snapshot(
        repo_root=Path("/nonexistent"),
        generated_at_utc="2026-05-14T00:00:00Z",
    )
    l6 = [r for r in snap["invariant_status"] if r["key"] == "level_6"]
    assert len(l6) == 1
    assert l6[0]["value"] == "permanently_disabled"
    assert l6[0]["tone"] == "danger_off"


# ---------------------------------------------------------------------------
# Determinism
# ---------------------------------------------------------------------------


def test_collect_snapshot_is_deterministic_with_injected_timestamp(
    tmp_path: Path,
) -> None:
    snap_a = aat.collect_snapshot(
        repo_root=tmp_path,
        generated_at_utc="2026-05-14T08:00:00Z",
    )
    snap_b = aat.collect_snapshot(
        repo_root=tmp_path,
        generated_at_utc="2026-05-14T08:00:00Z",
    )
    serialized_a = json.dumps(snap_a, sort_keys=True, indent=2)
    serialized_b = json.dumps(snap_b, sort_keys=True, indent=2)
    assert serialized_a == serialized_b


def test_collect_snapshot_arrays_are_sorted_deterministically(
    tmp_path: Path,
) -> None:
    """Build two A18c rows in non-sorted order and verify the
    aggregator's output is sorted by ``item_id``."""
    _write_upstream(
        tmp_path,
        "logs/development_generated_lane_a18c/latest.json",
        {
            "schema_version": 1,
            "module_version": "a18c.v1.3",
            "enabled": True,
            "rows": [
                {
                    "a18c_candidate_id": "zzz",
                    "admission_decision": "needs_human",
                },
                {
                    "a18c_candidate_id": "aaa",
                    "admission_decision": "needs_human",
                },
            ],
            "generated_at_utc": "2026-05-14T07:00:00Z",
        },
    )
    snap = aat.collect_snapshot(
        repo_root=tmp_path,
        generated_at_utc="2026-05-14T08:00:00Z",
    )
    ids = [w["item_id"] for w in snap["work_items"]]
    assert ids == sorted(ids)
    health_paths = [r["path"] for r in snap["artifact_health"]]
    assert health_paths == sorted(health_paths)
    invariant_keys = [r["key"] for r in snap["invariant_status"]]
    assert invariant_keys == sorted(invariant_keys)


# ---------------------------------------------------------------------------
# Graceful absence / malformation
# ---------------------------------------------------------------------------


def test_collect_snapshot_with_all_upstreams_absent_returns_valid_envelope(
    tmp_path: Path,
) -> None:
    snap = aat.collect_snapshot(
        repo_root=tmp_path,
        generated_at_utc="2026-05-14T08:00:00Z",
    )
    assert snap["work_items"] == []
    assert snap["counts"]["total_open"] == 0
    assert len(snap["artifact_health"]) == aat.UPSTREAM_CATALOG_LEN
    assert len(snap["invariant_status"]) == 9


def test_freshness_pins_any_stale_when_upstreams_absent(
    tmp_path: Path,
) -> None:
    snap = aat.collect_snapshot(
        repo_root=tmp_path,
        generated_at_utc="2026-05-14T08:00:00Z",
    )
    assert snap["freshness"]["any_stale"] is True


def test_artifact_health_includes_one_row_per_catalog_entry(
    tmp_path: Path,
) -> None:
    snap = aat.collect_snapshot(
        repo_root=tmp_path,
        generated_at_utc="2026-05-14T08:00:00Z",
    )
    paths = [r["path"] for r in snap["artifact_health"]]
    expected_paths = [c[2] for c in aat.UPSTREAM_CATALOG]
    assert sorted(paths) == sorted(expected_paths)


def test_collect_snapshot_with_malformed_upstream_emits_warning_not_raise(
    tmp_path: Path,
) -> None:
    target = tmp_path / "logs" / "development_work_queue" / "latest.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("{not valid json", encoding="utf-8")
    snap = aat.collect_snapshot(
        repo_root=tmp_path,
        generated_at_utc="2026-05-14T08:00:00Z",
    )
    wq = next(
        r
        for r in snap["artifact_health"]
        if r["path"] == "logs/development_work_queue/latest.json"
    )
    assert wq["parse_ok"] is False
    assert isinstance(wq.get("parse_error"), str)
    assert len(wq["parse_error"]) <= aat.MAX_PARSE_ERROR_LEN


def test_freshness_pins_any_malformed_when_upstream_malformed(
    tmp_path: Path,
) -> None:
    target = tmp_path / "logs" / "development_work_queue" / "latest.json"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("nope", encoding="utf-8")
    snap = aat.collect_snapshot(
        repo_root=tmp_path,
        generated_at_utc="2026-05-14T08:00:00Z",
    )
    assert snap["freshness"]["any_malformed"] is True


# ---------------------------------------------------------------------------
# Read-only over upstreams
# ---------------------------------------------------------------------------


def test_collect_snapshot_does_not_mutate_upstream_artefacts(
    tmp_path: Path,
) -> None:
    """Write hand-crafted upstreams and verify byte-equality
    before and after a ``collect_snapshot`` call."""
    target_a18c = _write_upstream(
        tmp_path,
        "logs/development_generated_lane_a18c/latest.json",
        {
            "schema_version": 1,
            "module_version": "a18c.v1.3",
            "enabled": True,
            "rows": [
                {
                    "a18c_candidate_id": "abc",
                    "admission_decision": "needs_human",
                }
            ],
            "generated_at_utc": "2026-05-14T07:00:00Z",
        },
    )
    target_mp = _write_upstream(
        tmp_path,
        "logs/development_merge_preflight/latest.json",
        {
            "schema_version": "1.0",
            "module_version": "mp.v1.1",
            "candidates": [
                {
                    "preflight_id": "mp_001",
                    "dry_run_verdict": "would_require_operator",
                }
            ],
            "generated_at_utc": "2026-05-14T07:00:00Z",
        },
    )
    before = (_sha256_of(target_a18c), _sha256_of(target_mp))
    aat.collect_snapshot(
        repo_root=tmp_path,
        generated_at_utc="2026-05-14T08:00:00Z",
    )
    after = (_sha256_of(target_a18c), _sha256_of(target_mp))
    assert before == after


# ---------------------------------------------------------------------------
# Projection correctness — narrow v0.1 slice
# ---------------------------------------------------------------------------


def test_step5_loop_no_op_does_not_emit_workitem(tmp_path: Path) -> None:
    _write_upstream(
        tmp_path,
        "logs/step5_loop/latest.json",
        {
            "module_version": "v3.15.16.A14",
            "report_kind": "step5_loop",
            "step5_enabled_substage": "none",
            "step5_implementation_allowed": False,
            "current_plan": {
                "cycle_id": "noop-id",
                "outcome": "no_op_no_eligible_item",
                "halt_reason": "ok",
                "source_kind": "queue",
                "source_id": "",
                "execution_authority_decision": "AUTO_ALLOWED",
            },
            "generated_at_utc": "2026-05-14T07:00:00Z",
        },
    )
    snap = aat.collect_snapshot(
        repo_root=tmp_path,
        generated_at_utc="2026-05-14T08:00:00Z",
    )
    step5_items = [
        w for w in snap["work_items"] if w["source_kind"] == "step5_loop"
    ]
    assert step5_items == []


def test_step5_loop_plan_emitted_produces_workitem(tmp_path: Path) -> None:
    _write_upstream(
        tmp_path,
        "logs/step5_loop/latest.json",
        {
            "module_version": "v3.15.16.A14",
            "report_kind": "step5_loop",
            "step5_enabled_substage": "none",
            "step5_implementation_allowed": False,
            "current_plan": {
                "cycle_id": "plan-cycle-001",
                "outcome": "plan_emitted",
                "halt_reason": "ok",
                "source_kind": "queue",
                "source_id": "dwq_001",
                "execution_authority_decision": "AUTO_ALLOWED",
            },
            "generated_at_utc": "2026-05-14T07:00:00Z",
        },
    )
    snap = aat.collect_snapshot(
        repo_root=tmp_path,
        generated_at_utc="2026-05-14T08:00:00Z",
    )
    step5_items = [
        w for w in snap["work_items"] if w["source_kind"] == "step5_loop"
    ]
    assert len(step5_items) == 1
    assert step5_items[0]["current_stage"] == "planned"
    assert step5_items[0]["human_needed"] is False


def test_a18c_row_produces_workitem(tmp_path: Path) -> None:
    _write_upstream(
        tmp_path,
        "logs/development_generated_lane_a18c/latest.json",
        {
            "schema_version": 1,
            "module_version": "a18c.v1.3",
            "enabled": True,
            "rows": [
                {
                    "a18c_candidate_id": "cand_x",
                    "admission_decision": "needs_human",
                    "admission_reason": "needs_human_authority_decision",
                    "would_target_lane": "none",
                    "would_require_operator_go": True,
                }
            ],
            "generated_at_utc": "2026-05-14T07:00:00Z",
        },
    )
    snap = aat.collect_snapshot(
        repo_root=tmp_path,
        generated_at_utc="2026-05-14T08:00:00Z",
    )
    a18c_items = [
        w
        for w in snap["work_items"]
        if w["source_kind"] == "generated_lane"
    ]
    assert len(a18c_items) == 1
    assert a18c_items[0]["human_needed"] is True
    assert a18c_items[0]["current_stage"] == "needs_human"


def test_a18c_needs_human_row_does_not_synthesize_required_phrase(
    tmp_path: Path,
) -> None:
    """Operator-pinned default: A18c rows must not synthesise a
    phrase. ``required_phrase`` must be ``None``."""
    _write_upstream(
        tmp_path,
        "logs/development_generated_lane_a18c/latest.json",
        {
            "schema_version": 1,
            "module_version": "a18c.v1.3",
            "enabled": True,
            "rows": [
                {
                    "a18c_candidate_id": "cand_phrase_test",
                    "admission_decision": "needs_human",
                    "would_require_operator_go": True,
                }
            ],
            "generated_at_utc": "2026-05-14T07:00:00Z",
        },
    )
    snap = aat.collect_snapshot(
        repo_root=tmp_path,
        generated_at_utc="2026-05-14T08:00:00Z",
    )
    a18c_actions = [
        a
        for a in snap["human_actions"]
        if a["source_artifact_path"].endswith(
            "development_generated_lane_a18c/latest.json"
        )
    ]
    assert len(a18c_actions) == 1
    assert a18c_actions[0]["required_phrase"] is None


def test_promotion_report_row_produces_workitem(tmp_path: Path) -> None:
    _write_upstream(
        tmp_path,
        "logs/development_generated_lane_promotion_report/latest.json",
        {
            "schema_version": "1.0",
            "module_version": "v3.15.16.A18.promotion_report",
            "rows": [
                {
                    "a18c_candidate_id": "cand_prom",
                    "promotion_allowed": False,
                    "block_reason": "promotion_disabled_by_default",
                }
            ],
            "generated_at_utc": "2026-05-14T07:00:00Z",
        },
    )
    snap = aat.collect_snapshot(
        repo_root=tmp_path,
        generated_at_utc="2026-05-14T08:00:00Z",
    )
    prom_items = [
        w
        for w in snap["work_items"]
        if w["source_kind"] == "generated_lane_promotion"
    ]
    assert len(prom_items) == 1
    assert prom_items[0]["human_needed"] is True


def test_promotion_report_required_phrase_sourced_from_row(
    tmp_path: Path,
) -> None:
    """Operator-pinned default: promotion-report rows MAY carry
    ``required_phrase`` sourced from ``required_operator_go_phrase``."""
    _write_upstream(
        tmp_path,
        "logs/development_generated_lane_promotion_report/latest.json",
        {
            "schema_version": "1.0",
            "module_version": "v3.15.16.A18.promotion_report",
            "operator_go_phrase_required": (
                "GO A18 promotion operator-promote"
            ),
            "rows": [
                {
                    "a18c_candidate_id": "cand_with_phrase",
                    "promotion_allowed": False,
                    "block_reason": "needs_human_per_a17_policy",
                    "required_operator_go_phrase": (
                        "GO A18 promotion operator-promote"
                    ),
                }
            ],
            "generated_at_utc": "2026-05-14T07:00:00Z",
        },
    )
    snap = aat.collect_snapshot(
        repo_root=tmp_path,
        generated_at_utc="2026-05-14T08:00:00Z",
    )
    prom_actions = [
        a
        for a in snap["human_actions"]
        if a["source_artifact_path"].endswith(
            "development_generated_lane_promotion_report/latest.json"
        )
    ]
    assert len(prom_actions) == 1
    assert (
        prom_actions[0]["required_phrase"]
        == "GO A18 promotion operator-promote"
    )


def test_merge_preflight_candidate_produces_workitem(
    tmp_path: Path,
) -> None:
    _write_upstream(
        tmp_path,
        "logs/development_merge_preflight/latest.json",
        {
            "schema_version": "1.0",
            "module_version": "mp.v1.1",
            "candidates": [
                {
                    "preflight_id": "pf_001",
                    "dry_run_verdict": "would_require_operator",
                    "pr_number": 42,
                }
            ],
            "generated_at_utc": "2026-05-14T07:00:00Z",
        },
    )
    snap = aat.collect_snapshot(
        repo_root=tmp_path,
        generated_at_utc="2026-05-14T08:00:00Z",
    )
    mp_items = [
        w
        for w in snap["work_items"]
        if w["source_kind"] == "merge_preflight"
    ]
    assert len(mp_items) == 1
    assert mp_items[0]["current_stage"] == "needs_human"


def test_health_only_upstreams_emit_no_workitems(tmp_path: Path) -> None:
    """Hand-craft fixtures for the 6 health-only ADE upstreams +
    the seed entry, then verify zero WorkItems are produced."""
    _write_upstream(
        tmp_path,
        "logs/development_work_queue/latest.json",
        {
            "module_version": "wq.v4.2",
            "rows": [
                {
                    "item_id": "wq_001",
                    "title": "hand-crafted queue row",
                    "current_state": "queued",
                }
            ],
            "generated_at_utc": "2026-05-14T07:00:00Z",
        },
    )
    _write_upstream(
        tmp_path,
        "logs/development_delegation/latest.json",
        {
            "module_version": "del.v3.1",
            "rows": [],
            "generated_at_utc": "2026-05-14T07:00:00Z",
        },
    )
    _write_upstream(
        tmp_path,
        "logs/development_bugfix_loop/latest.json",
        {
            "module_version": "bug.v2.0",
            "rows": [],
            "generated_at_utc": "2026-05-14T07:00:00Z",
        },
    )
    _write_upstream(
        tmp_path,
        "logs/development_release_gate/latest.json",
        {
            "module_version": "rg.v5.0",
            "rows": [],
            "generated_at_utc": "2026-05-14T07:00:00Z",
        },
    )
    _write_upstream(
        tmp_path,
        "logs/development_operational_digest/latest.json",
        {
            "module_version": "od.v3.0",
            "summary": "ok",
            "generated_at_utc": "2026-05-14T07:00:00Z",
        },
    )
    # step5_plan history is JSONL
    history = tmp_path / "logs" / "step5_plan" / "history.jsonl"
    history.parent.mkdir(parents=True, exist_ok=True)
    history.write_text(
        json.dumps({"cycle_id": "abc"}) + "\n", encoding="utf-8"
    )
    # seed file (read-only, no projection)
    seed = tmp_path / "generated_seed.jsonl"
    seed.write_text(
        json.dumps({"generated_candidate_id": "syn_001"}) + "\n",
        encoding="utf-8",
    )

    snap = aat.collect_snapshot(
        repo_root=tmp_path,
        generated_at_utc="2026-05-14T08:00:00Z",
    )
    # No upstream from the projectable subset is present, so no
    # WorkItems are emitted.
    assert snap["work_items"] == []
    # Every health-only upstream is represented in artifact_health.
    paths = {r["path"] for r in snap["artifact_health"]}
    for rel in (
        "logs/development_work_queue/latest.json",
        "logs/development_delegation/latest.json",
        "logs/development_bugfix_loop/latest.json",
        "logs/development_release_gate/latest.json",
        "logs/development_operational_digest/latest.json",
        "logs/step5_plan/history.jsonl",
        "generated_seed.jsonl",
    ):
        assert rel in paths


def test_artifact_health_includes_seed_read_only_warning(
    tmp_path: Path,
) -> None:
    snap = aat.collect_snapshot(
        repo_root=tmp_path,
        generated_at_utc="2026-05-14T08:00:00Z",
    )
    seed_row = next(
        r
        for r in snap["artifact_health"]
        if r["path"] == "generated_seed.jsonl"
    )
    assert (
        seed_row.get("read_only_warning")
        == aat.SEED_READ_ONLY_WARNING
    )


# ---------------------------------------------------------------------------
# Invariant block pins
# ---------------------------------------------------------------------------


def test_invariant_status_pins_step5_invariants(tmp_path: Path) -> None:
    snap = aat.collect_snapshot(
        repo_root=tmp_path,
        generated_at_utc="2026-05-14T08:00:00Z",
    )
    by_key = {r["key"]: r for r in snap["invariant_status"]}
    assert by_key["step5_implementation_allowed"]["value"] is False
    assert by_key["step5_implementation_allowed"]["tone"] == "off"
    assert by_key["step5_substage"]["value"] == "none"
    assert by_key["live_merge_implemented"]["value"] is False
    assert by_key["live_merge_implemented"]["tone"] == "off"
    assert by_key["deploy_coupled"]["value"] is False
    assert by_key["deploy_coupled"]["tone"] == "off"
    assert by_key["n5b_live_execute"]["value"] is False
    assert by_key["agent_service"]["value"] == "healthy"
    assert by_key["agent_service"]["tone"] == "on"


def test_invariant_status_a18c_enabled_sourced_from_artefact(
    tmp_path: Path,
) -> None:
    """When the A18c artefact is present with ``enabled=true``, the
    invariant pins ``a18c_enabled.value == True / tone == "on"``.
    When the artefact is absent, ``tone == "unknown"``."""
    # Case A: absent.
    snap_absent = aat.collect_snapshot(
        repo_root=tmp_path,
        generated_at_utc="2026-05-14T08:00:00Z",
    )
    by_key_absent = {
        r["key"]: r for r in snap_absent["invariant_status"]
    }
    assert by_key_absent["a18c_enabled"]["tone"] == "unknown"

    # Case B: enabled=True in the artefact.
    _write_upstream(
        tmp_path,
        "logs/development_generated_lane_a18c/latest.json",
        {
            "schema_version": 1,
            "module_version": "a18c.v1.3",
            "enabled": True,
            "rows": [],
            "generated_at_utc": "2026-05-14T07:00:00Z",
        },
    )
    snap_on = aat.collect_snapshot(
        repo_root=tmp_path,
        generated_at_utc="2026-05-14T08:00:00Z",
    )
    by_key_on = {r["key"]: r for r in snap_on["invariant_status"]}
    assert by_key_on["a18c_enabled"]["value"] is True
    assert by_key_on["a18c_enabled"]["tone"] == "on"


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def test_cli_no_write_does_not_mutate_logs(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _redirect_to_tmp(monkeypatch, tmp_path)
    rc = aat.main(["--no-write"])
    assert rc == 0
    # The redirected canonical path must not exist after --no-write.
    canonical = (
        tmp_path
        / "logs"
        / "development_agent_activity_timeline"
        / "latest.json"
    )
    assert not canonical.is_file()
    out = capsys.readouterr().out
    # Output must be valid JSON.
    parsed = json.loads(out)
    assert parsed["module_version"] == "aat.v0.1"


def test_cli_default_writes_to_canonical_path(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _redirect_to_tmp(monkeypatch, tmp_path)
    rc = aat.main([])
    assert rc == 0
    canonical = (
        tmp_path
        / "logs"
        / "development_agent_activity_timeline"
        / "latest.json"
    )
    assert canonical.is_file()
    snap = json.loads(canonical.read_text(encoding="utf-8"))
    assert snap["report_kind"] == "agent_activity_timeline"
