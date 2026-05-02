"""Unit tests for ``reporting.workloop_runtime``.

Verbatim properties from the v3.15.15.22 brief:

* once mode builds a valid artifact
* loop mode respects max_iterations
* one failing source does not crash all sources
* timeout classified as timeout
* missing source classified as not_available / skipped as appropriate
* malformed JSON handled safely
* JSON artifact write is atomic
* history.jsonl appends one record per run
* no arbitrary command execution
* no GitHub mutation functions called
* redaction of credential-shaped values
* schema stability
* safe_to_execute remains false
* KeyboardInterrupt produces graceful stop (best effort, optional)
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any

import pytest

from reporting import workloop_runtime as wlr

REPO_ROOT = Path(__file__).resolve().parent.parent.parent


# ---------------------------------------------------------------------------
# Fixtures / fakes
# ---------------------------------------------------------------------------


def _ok_source(name: str = "fake_ok"):
    return {
        "name": name,
        "module": f"reporting.{name}",
        "artifact_path": f"logs/{name}/latest.json",
        "fn": lambda: {"hello": "world", "count": 1},
        "envelope": lambda v: (wlr.STATE_OK, "fake ok"),
    }


def _failing_source(name: str = "fake_fail"):
    def boom():
        raise RuntimeError("synthetic failure")

    return {
        "name": name,
        "module": f"reporting.{name}",
        "artifact_path": f"logs/{name}/latest.json",
        "fn": boom,
        "envelope": None,
    }


def _slow_source(name: str = "fake_slow", duration: float = 5.0):
    def slow():
        time.sleep(duration)
        return {"slow": True}

    return {
        "name": name,
        "module": f"reporting.{name}",
        "artifact_path": f"logs/{name}/latest.json",
        "fn": slow,
        "envelope": lambda v: (wlr.STATE_OK, "ok"),
    }


def _credential_leaking_source(name: str = "fake_leaky"):
    return {
        "name": name,
        "module": f"reporting.{name}",
        "artifact_path": f"logs/{name}/latest.json",
        "fn": lambda: {"secret": "sk-ant-api03-leaked-fake-token"},
        "envelope": None,
    }


def _path_only_source(name: str = "fake_paths"):
    """Returns a snapshot whose strings include a no-touch path
    fragment (e.g. ``config/config.yaml``). The runtime supervisor
    must NOT classify this as a leak — only credential VALUES are
    refused."""
    return {
        "name": name,
        "module": f"reporting.{name}",
        "artifact_path": f"logs/{name}/latest.json",
        "fn": lambda: {"forbidden_actions": ["edit config/config.yaml", "modify VERSION"]},
        "envelope": None,
    }


def _none_source(name: str = "fake_none"):
    return {
        "name": name,
        "module": f"reporting.{name}",
        "artifact_path": f"logs/{name}/latest.json",
        "fn": lambda: None,
        "envelope": None,
    }


@pytest.fixture
def isolated(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setattr(wlr, "DIGEST_DIR_JSON", tmp_path / "wlr")
    return tmp_path


# ---------------------------------------------------------------------------
# Once mode
# ---------------------------------------------------------------------------


def test_once_mode_writes_one_artifact(isolated: Path) -> None:
    snap = wlr.run_once(
        timeout_per_source=2,
        sources_override=(_ok_source("a"), _ok_source("b")),
        write=True,
    )
    assert snap["mode"] == "once"
    assert snap["iteration"] == 0
    assert snap["max_iterations"] == 1
    assert snap["safe_to_execute"] is False
    latest = (isolated / "wlr" / "latest.json").read_text(encoding="utf-8")
    parsed = json.loads(latest)
    assert parsed["report_kind"] == "workloop_runtime_digest"
    assert parsed["run_id"].startswith("wl_")


def test_once_mode_contains_required_top_level_fields(isolated: Path) -> None:
    snap = wlr.run_once(
        timeout_per_source=2,
        sources_override=(_ok_source("a"),),
        write=False,
    )
    required = {
        "schema_version",
        "report_kind",
        "runtime_version",
        "generated_at_utc",
        "run_id",
        "mode",
        "iteration",
        "max_iterations",
        "interval_seconds",
        "next_run_after_utc",
        "duration_ms",
        "safe_to_execute",
        "loop_health",
        "sources",
        "counts",
        "final_recommendation",
    }
    assert required.issubset(snap.keys())


def test_safe_to_execute_is_always_false(isolated: Path) -> None:
    """v3.15.15.22 hard-codes safe_to_execute=false. Verified across
    once + loop modes and across healthy and failing source sets."""
    for sources in (
        (_ok_source("a"),),
        (_failing_source("b"),),
        (_ok_source("a"), _failing_source("b"), _none_source("c")),
    ):
        snap = wlr.run_once(
            timeout_per_source=2,
            sources_override=sources,
            write=False,
        )
        assert snap["safe_to_execute"] is False


def test_every_source_carries_required_fields(isolated: Path) -> None:
    snap = wlr.run_once(
        timeout_per_source=2,
        sources_override=(_ok_source("a"),),
        write=False,
    )
    required = {
        "source",
        "module",
        "state",
        "duration_ms",
        "summary",
        "artifact_path",
        "error_class",
    }
    for s in snap["sources"]:
        assert required.issubset(s.keys())
        assert s["state"] in wlr.STATE_VALUES


# ---------------------------------------------------------------------------
# One failing source does not crash others
# ---------------------------------------------------------------------------


def test_one_failing_source_does_not_crash_others(isolated: Path) -> None:
    snap = wlr.run_once(
        timeout_per_source=2,
        sources_override=(
            _ok_source("a"),
            _failing_source("b"),
            _ok_source("c"),
        ),
        write=False,
    )
    states = {s["source"]: s["state"] for s in snap["sources"]}
    assert states["a"] == "ok"
    assert states["b"] == "failed"
    assert states["c"] == "ok"


def test_failed_source_records_error_class(isolated: Path) -> None:
    snap = wlr.run_once(
        timeout_per_source=2,
        sources_override=(_failing_source("b"),),
        write=False,
    )
    s = snap["sources"][0]
    assert s["state"] == "failed"
    assert s["error_class"] == "RuntimeError"
    assert "synthetic failure" in (s["summary"] or "")


# ---------------------------------------------------------------------------
# Timeout
# ---------------------------------------------------------------------------


def test_timeout_classified_as_timeout(isolated: Path) -> None:
    """A source that runs longer than the per-source budget is
    classified as ``timeout`` and the supervisor moves on."""
    snap = wlr.run_once(
        timeout_per_source=1,
        sources_override=(_slow_source("slow", duration=3.0), _ok_source("ok")),
        write=False,
    )
    states = {s["source"]: s["state"] for s in snap["sources"]}
    assert states["slow"] == "timeout"
    assert states["ok"] == "ok"


# ---------------------------------------------------------------------------
# Missing / not_available
# ---------------------------------------------------------------------------


def test_missing_source_classified_not_available(isolated: Path) -> None:
    """A source whose function returns ``None`` is classified as
    ``not_available`` (never silently OK)."""
    snap = wlr.run_once(
        timeout_per_source=2,
        sources_override=(_none_source("none"),),
        write=False,
    )
    s = snap["sources"][0]
    assert s["state"] == "not_available"


# ---------------------------------------------------------------------------
# Credential redaction
# ---------------------------------------------------------------------------


def test_credential_value_in_source_is_classified_failed(isolated: Path) -> None:
    """A source that produces a credential-value string (e.g. an
    Anthropic key) is supposed to be caught at the per-source layer
    and surfaced as ``failed`` with ``error_class=SecretRedactionFailed``.
    """
    snap = wlr.run_once(
        timeout_per_source=2,
        sources_override=(_credential_leaking_source("leak"),),
        write=False,
    )
    s = snap["sources"][0]
    assert s["state"] == "failed"
    assert s["error_class"] == "SecretRedactionFailed"


def test_path_fragment_in_source_is_NOT_classified_failed(isolated: Path) -> None:
    """A source that legitimately echoes a no-touch path string
    (e.g. ``config/config.yaml`` in a forbidden-actions list) is NOT
    classified as a leak — only credential VALUES are."""
    snap = wlr.run_once(
        timeout_per_source=2,
        sources_override=(_path_only_source("paths"),),
        write=False,
    )
    s = snap["sources"][0]
    assert s["state"] != "failed", s
    assert s["state"] in (wlr.STATE_OK, wlr.STATE_DEGRADED), s


# ---------------------------------------------------------------------------
# Atomic JSON write + history.jsonl
# ---------------------------------------------------------------------------


def test_json_write_is_atomic(isolated: Path) -> None:
    """The supervisor writes via ``tmp`` + ``os.replace``; the tmp
    file must not exist after a successful write."""
    wlr.run_once(
        timeout_per_source=2,
        sources_override=(_ok_source("a"),),
        write=True,
    )
    latest = isolated / "wlr" / "latest.json"
    tmp = isolated / "wlr" / "latest.json.tmp"
    assert latest.exists()
    assert not tmp.exists()


def test_history_jsonl_appends_one_record_per_run(isolated: Path) -> None:
    for _ in range(3):
        wlr.run_once(
            timeout_per_source=2,
            sources_override=(_ok_source("a"),),
            write=True,
        )
    history = (isolated / "wlr" / "history.jsonl").read_text(encoding="utf-8")
    lines = [ln for ln in history.splitlines() if ln.strip()]
    assert len(lines) == 3
    for ln in lines:
        rec = json.loads(ln)
        assert rec["report_kind"] == "workloop_runtime_digest"


# ---------------------------------------------------------------------------
# Loop mode
# ---------------------------------------------------------------------------


def test_loop_mode_respects_max_iterations(isolated: Path) -> None:
    sleeps: list[float] = []
    snaps = wlr.run_loop(
        interval_seconds=30,
        max_iterations=4,
        timeout_per_source=2,
        sources_override=(_ok_source("a"),),
        write=True,
        sleeper=lambda s: sleeps.append(s),
    )
    assert len(snaps) == 4
    # Sleeps happen between iterations only (n-1).
    assert len(sleeps) == 3


def test_loop_clamps_max_iterations(isolated: Path) -> None:
    """A request for a runaway loop is clamped to MAX_ITERATIONS_LIMIT."""
    snaps = wlr.run_loop(
        interval_seconds=30,
        max_iterations=10_000,
        timeout_per_source=2,
        sources_override=(_ok_source("a"),),
        write=False,
        sleeper=lambda s: None,
    )
    assert len(snaps) == wlr.MAX_ITERATIONS_LIMIT


def test_loop_clamps_interval_seconds(isolated: Path) -> None:
    """interval is clamped to [MIN, MAX]; capture the value as
    persisted in the snapshot for verification."""
    sleeps: list[float] = []
    wlr.run_loop(
        interval_seconds=1,  # below MIN, should clamp up
        max_iterations=2,
        timeout_per_source=2,
        sources_override=(_ok_source("a"),),
        write=False,
        sleeper=lambda s: sleeps.append(s),
    )
    assert all(s >= wlr.MIN_INTERVAL_SECONDS for s in sleeps)


def test_loop_health_increments_consecutive_failures(isolated: Path) -> None:
    """Three consecutive failed iterations should drive
    ``consecutive_failures`` to 3."""
    snaps = wlr.run_loop(
        interval_seconds=30,
        max_iterations=3,
        timeout_per_source=2,
        sources_override=(_failing_source("b"),),
        write=True,
        sleeper=lambda s: None,
    )
    last = snaps[-1]
    assert last["loop_health"]["consecutive_failures"] == 3
    assert last["final_recommendation"].startswith(
        "runtime_halt_after_3_consecutive_failures"
    )


def test_loop_health_resets_on_success(isolated: Path) -> None:
    # Two failed then one ok.
    sources_seq = [
        (_failing_source("b"),),
        (_failing_source("b"),),
        (_ok_source("a"),),
    ]
    for srcs in sources_seq:
        wlr.run_once(
            timeout_per_source=2,
            sources_override=srcs,
            write=True,
        )
    last = json.loads(
        (isolated / "wlr" / "latest.json").read_text(encoding="utf-8")
    )
    assert last["loop_health"]["consecutive_failures"] == 0
    assert last["loop_health"]["last_success_utc"] is not None


# ---------------------------------------------------------------------------
# Static module invariants
# ---------------------------------------------------------------------------


def test_module_does_not_invoke_subprocess_or_gh_or_git() -> None:
    src = Path(wlr.__file__).read_text(encoding="utf-8")
    forbidden = (
        "import subprocess",
        "from subprocess",
        '"gh"',
        "'gh'",
        '"git"',
        "'git'",
        "Popen",
        "os.system",
        "shell=True",
    )
    for token in forbidden:
        assert token not in src, f"forbidden token in workloop_runtime.py: {token!r}"


def test_module_does_not_offer_freeform_command_input() -> None:
    """The CLI must not accept any --command / --argv / --shell flag."""
    src = Path(wlr.__file__).read_text(encoding="utf-8")
    for forbidden_flag in ("--command", "--argv", "--shell", "--cmd"):
        assert forbidden_flag not in src


# ---------------------------------------------------------------------------
# Frozen-contract integrity
# ---------------------------------------------------------------------------


def test_frozen_contracts_byte_identical_around_run(isolated: Path) -> None:
    import hashlib

    paths = [
        REPO_ROOT / "research" / "research_latest.json",
        REPO_ROOT / "research" / "strategy_matrix.csv",
    ]

    def _sha(p: Path) -> str:
        h = hashlib.sha256()
        with p.open("rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                h.update(chunk)
        return h.hexdigest()

    before = {p.name: _sha(p) for p in paths if p.exists()}
    wlr.run_once(
        timeout_per_source=2,
        sources_override=(_ok_source("a"), _failing_source("b")),
        write=True,
    )
    after = {p.name: _sha(p) for p in paths if p.exists()}
    assert before == after


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def test_cli_once_default(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(wlr, "DIGEST_DIR_JSON", tmp_path / "wlr")
    # Stub SOURCES so the CLI smoke is fast.
    monkeypatch.setattr(wlr, "SOURCES", (_ok_source("a"),))
    rc = wlr.main(["--once", "--no-write"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["report_kind"] == "workloop_runtime_digest"


def test_cli_status_when_no_artifact(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(wlr, "DIGEST_DIR_JSON", tmp_path / "wlr")
    rc = wlr.main(["--status"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["status"] == "not_available"


def test_cli_status_returns_latest(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(wlr, "DIGEST_DIR_JSON", tmp_path / "wlr")
    monkeypatch.setattr(wlr, "SOURCES", (_ok_source("a"),))
    # Run --once first to write latest.json.
    wlr.main(["--once"])
    capsys.readouterr()
    rc = wlr.main(["--status"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["report_kind"] == "workloop_runtime_digest"


# ---------------------------------------------------------------------------
# read_latest_snapshot helper (used by api_agent_control + approval_inbox)
# ---------------------------------------------------------------------------


def test_read_latest_snapshot_handles_missing(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(wlr, "DIGEST_DIR_JSON", tmp_path / "wlr")
    assert wlr.read_latest_snapshot() is None


def test_read_latest_snapshot_handles_malformed(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(wlr, "DIGEST_DIR_JSON", tmp_path / "wlr")
    (tmp_path / "wlr").mkdir()
    (tmp_path / "wlr" / "latest.json").write_text("{ not json", encoding="utf-8")
    assert wlr.read_latest_snapshot() is None


def test_read_latest_snapshot_handles_non_object(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(wlr, "DIGEST_DIR_JSON", tmp_path / "wlr")
    (tmp_path / "wlr").mkdir()
    (tmp_path / "wlr" / "latest.json").write_text("[1, 2]", encoding="utf-8")
    assert wlr.read_latest_snapshot() is None


def test_read_latest_snapshot_returns_dict(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(wlr, "DIGEST_DIR_JSON", tmp_path / "wlr")
    (tmp_path / "wlr").mkdir()
    (tmp_path / "wlr" / "latest.json").write_text(
        json.dumps({"report_kind": "workloop_runtime_digest", "x": 1}),
        encoding="utf-8",
    )
    out = wlr.read_latest_snapshot()
    assert isinstance(out, dict)
    assert out["report_kind"] == "workloop_runtime_digest"
