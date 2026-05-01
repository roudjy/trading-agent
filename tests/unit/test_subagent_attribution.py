"""Unit tests for ``reporting.subagent_attribution``.

Properties under test:

* read-only — neither library nor CLI writes to the ledger or run
  summaries;
* no run summary → confidence ``unknown`` (never ``ok``);
* multiple subagents in a session without per-event mapping →
  confidence ``low``;
* solo-subagent session with no conflicting evidence + tool-count
  match → confidence ``high``;
* solo-subagent session with tool-count mismatch → confidence
  ``low`` (tool-count is supporting evidence only);
* per-event mapping hint without parsed-mapping → confidence ``low``
  for multi-subagent sessions (the writer-level fix is required for
  true projection);
* malformed run summary → confidence ``unknown`` with conflict flag;
* events without ``session_id`` → confidence ``unknown``;
* low-confidence is never displayed as fact — every row carries
  inferred + confidence + source + warning;
* secrets scrubbed in evidence fields;
* frozen contracts byte-identical before/after.
"""

from __future__ import annotations

import datetime as _dt
import hashlib
import json
from pathlib import Path

import pytest

from reporting import agent_audit, subagent_attribution

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def _existence_and_sha(path: Path) -> tuple[bool, str | None]:
    if not path.exists():
        return (False, None)
    return (True, _file_sha256(path))


SOLO_SUMMARY = """\
# Agent Run Summary

## Session metadata

- **session_id**: `sess-solo`

## Subagents invoked

| agent | model | calls |
|---|---|---|
| planner | sonnet | 2 |

## Tools used (counts)

| tool | calls |
|---|---|
| Edit | 2 |
"""


MULTI_SUMMARY = """\
# Agent Run Summary

## Session metadata

- **session_id**: `sess-multi`

## Subagents invoked

| agent | model | calls |
|---|---|---|
| planner | sonnet | 1 |
| test-agent | sonnet | 1 |

## Tools used (counts)

| tool | calls |
|---|---|
| Edit | 2 |
"""


SOLO_WITH_PER_EVENT = """\
# Agent Run Summary

## Session metadata

- **session_id**: `sess-mapped`

## Subagents invoked

| agent | model | calls |
|---|---|---|
| planner | sonnet | 2 |

The per-event mapping below references each `sequence_id` explicitly:

- seq=0 → planner
- seq=1 → planner

## Tools used (counts)

| tool | calls |
|---|---|
| Edit | 2 |
"""


MALFORMED_SUMMARY = """\
# Agent Run Summary

## Session metadata

- **session_id**: `sess-bad`

## Subagents invoked

| agent | model | calls |
|---|---|---|
| planner | sonnet | 1 |
| planner | sonnet | 99 |

## Tools used (counts)

| tool | calls |
|---|---|
| Edit | not-a-number |
"""


@pytest.fixture
def isolated_repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    logs_dir = tmp_path / "logs"
    summaries_dir = tmp_path / "docs" / "governance" / "agent_run_summaries"
    logs_dir.mkdir()
    summaries_dir.mkdir(parents=True)
    monkeypatch.setattr(agent_audit, "_LEDGER_DIR", logs_dir)
    monkeypatch.setattr(subagent_attribution, "REPO_ROOT", tmp_path)
    monkeypatch.setattr(subagent_attribution, "RUN_SUMMARY_DIR", summaries_dir)
    return tmp_path


def _seed_event(session_id: str, *, tool: str = "Edit", outcome: str = "ok") -> None:
    agent_audit.append_event(
        {
            "event": "tool_use",
            "tool": tool,
            "outcome": outcome,
            "actor": "claude:audit_emit",
            "session_id": session_id,
        }
    )


def _write_summary(repo: Path, name: str, body: str) -> None:
    target = repo / "docs" / "governance" / "agent_run_summaries" / f"{name}.md"
    target.write_text(body, encoding="utf-8")


# ---------------------------------------------------------------------------
# Read-only invariant
# ---------------------------------------------------------------------------


def test_collect_does_not_mutate_ledger_or_summaries(isolated_repo: Path) -> None:
    _seed_event("sess-solo")
    _seed_event("sess-solo")
    _write_summary(isolated_repo, "sess-solo", SOLO_SUMMARY)
    ledger = agent_audit.current_ledger_path()
    summary = isolated_repo / "docs" / "governance" / "agent_run_summaries" / "sess-solo.md"
    before_l = _file_sha256(ledger)
    before_s = _file_sha256(summary)
    subagent_attribution.collect_attribution(ledger)
    assert _file_sha256(ledger) == before_l
    assert _file_sha256(summary) == before_s


# ---------------------------------------------------------------------------
# Confidence rules (round-3 tightened)
# ---------------------------------------------------------------------------


def test_no_run_summary_yields_confidence_unknown(isolated_repo: Path) -> None:
    _seed_event("sess-orphan")
    snap = subagent_attribution.collect_attribution(agent_audit.current_ledger_path())
    by_session = snap["by_session"]
    assert by_session["sess-orphan"]["subagent_confidence"] == "unknown"
    assert by_session["sess-orphan"]["inferred_subagent"] == "unknown"
    # And it must NOT be 'ok' anywhere.
    flat = json.dumps(snap)
    assert '"subagent_confidence": "ok"' not in flat


def test_solo_subagent_with_matching_tool_count_yields_high(
    isolated_repo: Path,
) -> None:
    _seed_event("sess-solo")
    _seed_event("sess-solo")
    _write_summary(isolated_repo, "sess-solo", SOLO_SUMMARY)
    snap = subagent_attribution.collect_attribution(agent_audit.current_ledger_path())
    info = snap["by_session"]["sess-solo"]
    assert info["subagent_confidence"] == "high"
    assert info["inferred_subagent"] == "claude:planner"
    assert info["attribution_warning"] is None


def test_solo_subagent_strict_tool_count_mismatch_yields_low(
    isolated_repo: Path,
) -> None:
    # Summary says 2 calls; ledger has 5. |2-5| = 3, downgrade.
    for _ in range(5):
        _seed_event("sess-solo")
    _write_summary(isolated_repo, "sess-solo", SOLO_SUMMARY)
    snap = subagent_attribution.collect_attribution(agent_audit.current_ledger_path())
    info = snap["by_session"]["sess-solo"]
    assert info["subagent_confidence"] == "low"
    assert info["attribution_warning"] is not None


def test_multi_subagent_without_event_mapping_yields_low(
    isolated_repo: Path,
) -> None:
    _seed_event("sess-multi")
    _seed_event("sess-multi")
    _write_summary(isolated_repo, "sess-multi", MULTI_SUMMARY)
    snap = subagent_attribution.collect_attribution(agent_audit.current_ledger_path())
    info = snap["by_session"]["sess-multi"]
    assert info["subagent_confidence"] == "low"
    assert info["inferred_subagent"] == "unknown"
    assert "multiple subagents" in (info["attribution_warning"] or "").lower()


def test_multi_subagent_with_event_mapping_still_low_for_this_module(
    isolated_repo: Path,
) -> None:
    """Per-event mapping is the path to ``high``, but only the writer
    can apply it. This module documents the limitation and reports
    ``low`` so the operator knows to look at ADR-016."""
    body = MULTI_SUMMARY + "\n\nseq=0 → planner\nseq=1 → test-agent\n"
    _seed_event("sess-mapped-multi")
    _seed_event("sess-mapped-multi")
    _write_summary(isolated_repo, "sess-mapped-multi", body.replace("sess-multi", "sess-mapped-multi"))
    snap = subagent_attribution.collect_attribution(agent_audit.current_ledger_path())
    info = snap["by_session"]["sess-mapped-multi"]
    assert info["subagent_confidence"] == "low"


def test_malformed_summary_yields_unknown_with_conflict_evidence(
    isolated_repo: Path,
) -> None:
    _seed_event("sess-bad")
    _write_summary(isolated_repo, "sess-bad", MALFORMED_SUMMARY)
    snap = subagent_attribution.collect_attribution(agent_audit.current_ledger_path())
    info = snap["by_session"]["sess-bad"]
    assert info["subagent_confidence"] == "unknown"
    assert "conflict" in info["subagent_evidence"]


def test_event_without_session_id_yields_unknown(isolated_repo: Path) -> None:
    agent_audit.append_event(
        {"event": "tool_use", "tool": "Edit", "outcome": "ok"}
    )
    snap = subagent_attribution.collect_attribution(agent_audit.current_ledger_path())
    assert "_no_session_id" in snap["by_session"]
    info = snap["by_session"]["_no_session_id"]
    assert info["subagent_confidence"] == "unknown"


# ---------------------------------------------------------------------------
# Row projection — never display low-confidence as fact
# ---------------------------------------------------------------------------


def test_every_row_carries_four_attribution_columns(isolated_repo: Path) -> None:
    _seed_event("sess-multi")
    _seed_event("sess-multi")
    _write_summary(isolated_repo, "sess-multi", MULTI_SUMMARY)
    snap = subagent_attribution.collect_attribution(agent_audit.current_ledger_path())
    assert snap["rows"], "expected at least one row"
    for row in snap["rows"]:
        assert "inferred_subagent" in row
        assert "subagent_confidence" in row
        assert "attribution_source" in row
        assert "attribution_warning" in row


def test_low_confidence_row_includes_warning(isolated_repo: Path) -> None:
    _seed_event("sess-multi")
    _seed_event("sess-multi")
    _write_summary(isolated_repo, "sess-multi", MULTI_SUMMARY)
    snap = subagent_attribution.collect_attribution(agent_audit.current_ledger_path())
    for row in snap["rows"]:
        if row["subagent_confidence"] == "low":
            assert row["attribution_warning"], (
                "low-confidence rows must carry a warning so they "
                "are never displayed as fact"
            )


# ---------------------------------------------------------------------------
# Secret scrub
# ---------------------------------------------------------------------------


def test_evidence_fields_scrub_credential_patterns(
    isolated_repo: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """The evidence label is generated by the module itself, so a leak
    would only happen via a bug. We assert the scrub is applied — pass
    a bogus value through ``_scrub`` directly and confirm the regex
    still applies.
    """
    leaky = "ghp_AAAAAAAAAAAAAAAAAAAAAAAAAA in evidence label"
    scrubbed = subagent_attribution._scrub(leaky)
    assert "[REDACTED]" in scrubbed
    assert "ghp_AAAA" not in scrubbed


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def test_cli_emits_valid_json_zero_exit(
    isolated_repo: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _seed_event("sess-solo")
    _seed_event("sess-solo")
    _write_summary(isolated_repo, "sess-solo", SOLO_SUMMARY)
    rc = subagent_attribution.main(
        ["--path", str(agent_audit.current_ledger_path()), "--indent", "0"]
    )
    assert rc == 0
    parsed = json.loads(capsys.readouterr().out)
    assert parsed["report_kind"] == "subagent_attribution"
    assert parsed["caveat"].startswith("convenience-only")


def test_cli_returns_zero_when_ledger_missing(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    rc = subagent_attribution.main(
        ["--path", str(tmp_path / "nope.jsonl"), "--indent", "0"]
    )
    assert rc == 0
    parsed = json.loads(capsys.readouterr().out)
    assert parsed["ledger_present"] is False


# ---------------------------------------------------------------------------
# Frozen-contract integrity
# ---------------------------------------------------------------------------


def test_collect_does_not_touch_frozen_contracts() -> None:
    repo_root = Path(__file__).resolve().parent.parent.parent
    research_latest = repo_root / "research" / "research_latest.json"
    strategy_matrix = repo_root / "research" / "strategy_matrix.csv"

    before_a = _existence_and_sha(research_latest)
    before_b = _existence_and_sha(strategy_matrix)

    from reporting.agent_audit_summary import assert_no_secrets as _no_secrets

    today = (
        repo_root
        / "logs"
        / f"agent_audit.{_dt.datetime.now(_dt.UTC).strftime('%Y-%m-%d')}.jsonl"
    )
    snap = subagent_attribution.collect_attribution(today)
    _no_secrets(snap)

    after_a = _existence_and_sha(research_latest)
    after_b = _existence_and_sha(strategy_matrix)
    assert before_a == after_a
    assert before_b == after_b

    flat = json.dumps(snap)
    assert "research_latest.json" not in flat
    assert "strategy_matrix.csv" not in flat
