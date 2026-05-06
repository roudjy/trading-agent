"""PR-B integration — CLI determinism for reporting.intelligent_routing.

Pins:

* Two consecutive ``--no-write`` invocations with identical inputs and
  identical ``now_utc`` produce byte-identical stdout.
* One ``--no-write`` and one ``--write`` with identical inputs and
  identical ``now_utc`` produce equal JSON content.
* The ``logs/intelligent_routing/`` directory contains exactly
  ``latest.json`` and nothing else (Correction 8 — no timestamped
  siblings).
* Importing or invoking the module never opens any path under
  ``research/**`` in write mode.
"""

from __future__ import annotations

import builtins
import datetime as _dt
import json
from pathlib import Path

import pytest

from reporting import intelligent_routing as ir


@pytest.fixture
def fixed_now() -> _dt.datetime:
    return _dt.datetime(2026, 5, 6, 12, 0, 0, tzinfo=_dt.timezone.utc)


def _redirect_paths(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> Path:
    """Redirect inputs to absent paths and outputs into ``tmp_path``."""
    out_dir = tmp_path / "logs" / "intelligent_routing"
    out_path = out_dir / "latest.json"
    monkeypatch.setattr(ir, "OUTPUT_DIR", out_dir)
    monkeypatch.setattr(ir, "LATEST_OUTPUT_PATH", out_path)
    # Force inputs to absent paths so the test does not depend on
    # repository state. The ``not_available`` envelope path is the
    # determinism-critical one.
    monkeypatch.setattr(ir, "CAMPAIGN_QUEUE_PATH", tmp_path / "queue.json")
    monkeypatch.setattr(
        ir, "CAMPAIGN_REGISTRY_PATH", tmp_path / "registry.json",
    )
    monkeypatch.setattr(ir, "DEAD_ZONES_PATH", tmp_path / "dz.json")
    monkeypatch.setattr(
        ir, "INFORMATION_GAIN_PATH", tmp_path / "ig.json",
    )
    return out_path


def test_cli_no_write_byte_deterministic(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    fixed_now: _dt.datetime,
) -> None:
    _redirect_paths(monkeypatch, tmp_path)
    monkeypatch.setattr(ir, "_now_utc_default", lambda: fixed_now)
    rc1 = ir.main(["--no-write"])
    out1 = capsys.readouterr().out
    rc2 = ir.main(["--no-write"])
    out2 = capsys.readouterr().out
    assert rc1 == rc2 == 0
    assert out1 == out2


def test_cli_no_write_equals_write_content(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    fixed_now: _dt.datetime,
) -> None:
    out_path = _redirect_paths(monkeypatch, tmp_path)
    monkeypatch.setattr(ir, "_now_utc_default", lambda: fixed_now)
    rc1 = ir.main(["--no-write"])
    out1 = capsys.readouterr().out
    rc2 = ir.main(["--write"])
    out2 = capsys.readouterr().out
    assert rc1 == rc2 == 0
    written = out_path.read_text(encoding="utf-8")
    # The serialization is identical (same indent / sort_keys).
    assert json.loads(out1) == json.loads(out2) == json.loads(written)


def test_cli_write_creates_only_latest_json(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    fixed_now: _dt.datetime,
) -> None:
    out_path = _redirect_paths(monkeypatch, tmp_path)
    monkeypatch.setattr(ir, "_now_utc_default", lambda: fixed_now)
    ir.main(["--write"])
    out_dir = out_path.parent
    files = sorted(p.name for p in out_dir.iterdir())
    assert files == ["latest.json"]


def test_cli_run_does_not_write_to_research_paths(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    fixed_now: _dt.datetime,
) -> None:
    """Spy on ``builtins.open`` and ``Path.open`` to assert no write
    against any path containing ``research/`` or ``research\\``."""
    _redirect_paths(monkeypatch, tmp_path)
    monkeypatch.setattr(ir, "_now_utc_default", lambda: fixed_now)

    forbidden_modes = {"w", "a", "x", "+"}
    bad_writes: list[tuple[str, str]] = []

    real_builtins_open = builtins.open
    real_path_open = Path.open

    def _spy_builtins_open(file: object, mode: str = "r", *a: object, **kw: object):
        m = mode if isinstance(mode, str) else ""
        if any(c in m for c in forbidden_modes):
            sf = str(file).replace("\\", "/")
            if "/research/" in sf or sf.startswith("research/"):
                bad_writes.append((sf, m))
        return real_builtins_open(file, mode, *a, **kw)

    def _spy_path_open(self: Path, mode: str = "r", *a: object, **kw: object):
        m = mode if isinstance(mode, str) else ""
        if any(c in m for c in forbidden_modes):
            sf = str(self).replace("\\", "/")
            if "/research/" in sf or sf.startswith("research/"):
                bad_writes.append((sf, m))
        return real_path_open(self, mode, *a, **kw)

    monkeypatch.setattr(builtins, "open", _spy_builtins_open)
    monkeypatch.setattr(Path, "open", _spy_path_open)
    ir.main(["--write"])
    assert bad_writes == [], (
        f"reporting.intelligent_routing wrote into research/ during a "
        f"--write invocation: {bad_writes!r}"
    )
