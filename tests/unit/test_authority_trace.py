"""Unit tests for ``research.authority_trace`` (v3.15.15.11).

Pins the opt-in / additive contract:

- ``AuthorityTraceSink(path=None)`` is a no-op: ``emit()`` returns
  ``False`` and creates no file. Existing tests that don't configure
  the trace path see no new state.
- ``AuthorityTraceSink(path=...)`` writes one JSONL line per emit and
  one ``.meta.json`` companion. Replaying the same event id is a
  no-op (idempotency).
- ``read_trace`` deduplicates by ``event_id`` so torn appends are
  recoverable.
- Closed-vocabulary inputs raise on unknown values.
- Pure decision modules MUST NOT import ``research.authority_trace``.
"""

from __future__ import annotations

import ast
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from research.authority_trace import (
    AUTHORITY_TRACE_META_SCHEMA_VERSION,
    AUTHORITY_TRACE_SCHEMA_VERSION,
    AUTHORITY_TRACE_VERSION,
    AuthorityTraceEvent,
    AuthorityTraceSink,
    ENV_VAR_TRACE_PATH,
    SOURCE_AUTHORITIES,
    TRANSITION_KINDS,
    append_events,
    build_event,
    read_trace,
    trace_path_from_env,
)


_T = datetime(2026, 4, 29, 12, 0, 0, tzinfo=UTC)


def _make(transition_kind: str = "catalog_persisted", **overrides) -> AuthorityTraceEvent:
    base = {
        "transition_kind": transition_kind,
        "source_authority": "catalog",
        "target_authority": "catalog",
        "ts_utc": _T,
        "run_id": "20260429T120000000000Z",
        "evidence": {"site": "post_run"},
    }
    base.update(overrides)
    return build_event(**base)


# ---------------------------------------------------------------------------
# Closed vocabulary
# ---------------------------------------------------------------------------


def test_transition_kinds_match_spec() -> None:
    assert TRANSITION_KINDS == (
        "promotion_classified",
        "candidate_registry_written",
        "falsification_payload_emitted",
        "catalog_persisted",
        "campaign_state_transitioned",
        "campaign_policy_decided",
        "stale_authority_detected",
    )


def test_source_authorities_match_spec() -> None:
    assert SOURCE_AUTHORITIES == (
        "registry",
        "presets",
        "catalog",
        "promotion",
        "falsification",
        "candidate_registry",
        "campaign_registry",
        "campaign_policy",
    )


def test_build_event_rejects_unknown_transition_kind() -> None:
    with pytest.raises(ValueError, match="unknown transition_kind"):
        build_event(
            transition_kind="not_a_kind",
            source_authority="catalog",
            target_authority="catalog",
            ts_utc=_T,
        )


def test_build_event_rejects_unknown_authority() -> None:
    with pytest.raises(ValueError, match="unknown source_authority"):
        build_event(
            transition_kind="catalog_persisted",
            source_authority="not_an_authority",
            target_authority="catalog",
            ts_utc=_T,
        )
    with pytest.raises(ValueError, match="unknown target_authority"):
        build_event(
            transition_kind="catalog_persisted",
            source_authority="catalog",
            target_authority="not_an_authority",
            ts_utc=_T,
        )


# ---------------------------------------------------------------------------
# build_event shape + determinism
# ---------------------------------------------------------------------------


def test_build_event_shape() -> None:
    event = _make()
    payload = event.to_payload()
    expected_keys = {
        "event_id",
        "schema_version",
        "ts_utc",
        "run_id",
        "transition_kind",
        "source_authority",
        "target_authority",
        "hypothesis_id",
        "candidate_id",
        "evidence_hash",
    }
    assert set(payload.keys()) == expected_keys
    assert payload["schema_version"] == AUTHORITY_TRACE_SCHEMA_VERSION
    assert payload["transition_kind"] == "catalog_persisted"
    # Deterministic id + hash given identical inputs.
    repeat = _make()
    assert event.event_id == repeat.event_id
    assert event.evidence_hash == repeat.evidence_hash


def test_build_event_id_changes_with_evidence_unchanged_inputs() -> None:
    """event_id ignores evidence; evidence_hash captures it."""
    base = _make(evidence={"k": "v1"})
    other = _make(evidence={"k": "v2"})
    assert base.event_id == other.event_id
    assert base.evidence_hash != other.evidence_hash


def test_build_event_id_differs_per_transition_kind() -> None:
    a = _make(transition_kind="catalog_persisted")
    b = _make(transition_kind="falsification_payload_emitted",
              source_authority="falsification",
              target_authority="candidate_registry")
    assert a.event_id != b.event_id


# ---------------------------------------------------------------------------
# Disabled sink — strict no-op
# ---------------------------------------------------------------------------


def test_disabled_sink_emit_is_no_op_and_creates_no_file(tmp_path: Path) -> None:
    sink = AuthorityTraceSink(path=None)
    assert sink.enabled is False
    result = sink.emit(_make())
    assert result is False
    # Confirm no files appeared anywhere under tmp_path.
    assert list(tmp_path.iterdir()) == []


def test_disabled_sink_does_not_create_meta_file(tmp_path: Path) -> None:
    sink = AuthorityTraceSink(path=None)
    sink.emit(_make())
    sink.emit(_make(transition_kind="falsification_payload_emitted",
                    source_authority="falsification",
                    target_authority="candidate_registry"))
    assert list(tmp_path.iterdir()) == []


# ---------------------------------------------------------------------------
# Enabled sink — JSONL + meta + idempotency
# ---------------------------------------------------------------------------


def test_enabled_sink_writes_jsonl_and_meta(tmp_path: Path) -> None:
    trace_path = tmp_path / "authority_trace_latest.v1.jsonl"
    meta_path = tmp_path / "authority_trace_latest.v1.meta.json"
    sink = AuthorityTraceSink(path=trace_path)
    assert sink.enabled is True
    appended = sink.emit(_make())
    assert appended is True
    assert trace_path.exists()
    assert meta_path.exists()
    # Sidecar shape.
    line = trace_path.read_text(encoding="utf-8").splitlines()[0]
    parsed = json.loads(line)
    assert parsed["transition_kind"] == "catalog_persisted"
    assert parsed["schema_version"] == AUTHORITY_TRACE_SCHEMA_VERSION


def test_enabled_sink_emit_is_idempotent(tmp_path: Path) -> None:
    trace_path = tmp_path / "trace.v1.jsonl"
    sink = AuthorityTraceSink(path=trace_path)
    event = _make()
    assert sink.emit(event) is True
    # Second call with identical event id: no new line.
    assert sink.emit(event) is False
    lines = trace_path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1


def test_read_trace_dedupes_torn_append(tmp_path: Path) -> None:
    trace_path = tmp_path / "trace.v1.jsonl"
    event = _make()
    payload = json.dumps(event.to_payload(), sort_keys=True)
    # Simulate a torn append: same event_id appears twice + one corrupt
    # tail line that is invalid JSON.
    trace_path.write_text(
        payload + "\n" + payload + "\n" + "not-json{\n",
        encoding="utf-8",
    )
    out = read_trace(trace_path)
    assert len(out) == 1
    assert out[0]["event_id"] == event.event_id


def test_read_trace_missing_file_returns_empty(tmp_path: Path) -> None:
    assert read_trace(tmp_path / "does_not_exist.jsonl") == []


def test_meta_file_pin_block_shape(tmp_path: Path) -> None:
    trace_path = tmp_path / "trace.v1.jsonl"
    sink = AuthorityTraceSink(path=trace_path, git_revision="abc1234")
    sink.emit(_make())
    meta = json.loads(
        (tmp_path / "trace.v1.meta.json").read_text(encoding="utf-8")
    )
    # Pin-block fields (mirrors campaign_evidence_ledger meta).
    assert meta["schema_version"] == AUTHORITY_TRACE_META_SCHEMA_VERSION
    assert meta["live_eligible"] is False
    assert meta["authoritative"] is False
    assert meta["diagnostic_only"] is True
    # Trace-specific fields.
    assert meta["additive"] is True
    assert meta["doctrine_reference"] == "ADR-014"
    assert meta["trace_schema_version"] == AUTHORITY_TRACE_SCHEMA_VERSION
    assert meta["trace_version"] == AUTHORITY_TRACE_VERSION
    assert meta["event_count"] == 1


def test_append_events_skips_duplicates(tmp_path: Path) -> None:
    trace_path = tmp_path / "trace.v1.jsonl"
    e1 = _make()
    e2 = _make(transition_kind="falsification_payload_emitted",
               source_authority="falsification",
               target_authority="candidate_registry")
    appended_first = append_events(trace_path, [e1, e2])
    assert len(appended_first) == 2
    appended_second = append_events(trace_path, [e1, e2])
    assert appended_second == []
    assert len(read_trace(trace_path)) == 2


# ---------------------------------------------------------------------------
# Env-var enablement
# ---------------------------------------------------------------------------


def test_trace_path_from_env_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(ENV_VAR_TRACE_PATH, raising=False)
    assert trace_path_from_env() is None


def test_trace_path_from_env_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(ENV_VAR_TRACE_PATH, "")
    assert trace_path_from_env() is None


def test_trace_path_from_env_set(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    target = tmp_path / "trace.v1.jsonl"
    monkeypatch.setenv(ENV_VAR_TRACE_PATH, str(target))
    assert trace_path_from_env() == target


# ---------------------------------------------------------------------------
# Forbidden-import surface (ADR-014 §A pure-function preservation)
# ---------------------------------------------------------------------------

_REPO_ROOT = Path(__file__).resolve().parents[2]

_PURE_MODULES_FORBIDDEN_IMPORT = (
    "research/promotion.py",
    "research/campaign_policy.py",
    "research/campaign_funnel_policy.py",
    "research/falsification.py",
    "research/falsification_reporting.py",
    "research/candidate_lifecycle.py",
    "research/paper_readiness.py",
)


def _module_imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.module is not None:
                names.add(node.module)
    return names


@pytest.mark.parametrize("relative_path", _PURE_MODULES_FORBIDDEN_IMPORT)
def test_pure_module_does_not_import_authority_trace(relative_path: str) -> None:
    target = _REPO_ROOT / relative_path
    assert target.exists(), f"missing protected module: {relative_path}"
    imports = _module_imports(target)
    for name in imports:
        assert name != "research.authority_trace", (
            f"{relative_path} imports research.authority_trace — pure "
            f"decision modules must stay pure (ADR-014 §A)."
        )
        assert not name.startswith("research.authority_trace."), (
            f"{relative_path} imports a submodule of "
            f"research.authority_trace — same constraint."
        )
