"""PR-D smoke — minimal happy-path import + CLI dispatch.

Picked up by ``tests/run_tests.sh`` and the CI ``unit (smoke + unit)``
job. Confirms the module imports cleanly and a default ``--no-write``
invocation returns exit code 0 with a valid JSON envelope on stdout.
"""

from __future__ import annotations

import json

import pytest


def test_intelligent_routing_module_imports_clean() -> None:
    from reporting import intelligent_routing as ir
    assert ir.SCHEMA_VERSION == "1.0"
    assert ir.MODULE_VERSION == "v3.15.16"
    assert ir.ROUTING_EFFECT_ADVISORY_ONLY == "advisory_only"
    assert ir.QUEUE_ORDERING_EFFECT_NONE == "none"


def test_intelligent_routing_status_module_imports_clean() -> None:
    from reporting import intelligent_routing_status as irs
    assert irs.SCHEMA_VERSION == "1.0"
    assert irs.MODULE_VERSION == "v3.15.16"
    assert irs.REPORT_KIND == "intelligent_routing_status"


def test_intelligent_routing_cli_default_no_write_smoke(
    tmp_path, monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Default CLI invocation prints valid JSON, writes nothing."""
    from reporting import intelligent_routing as ir
    out_dir = tmp_path / "logs" / "intelligent_routing"
    monkeypatch.setattr(ir, "OUTPUT_DIR", out_dir)
    monkeypatch.setattr(ir, "LATEST_OUTPUT_PATH", out_dir / "latest.json")
    monkeypatch.setattr(ir, "CAMPAIGN_QUEUE_PATH", tmp_path / "absent_q.json")
    monkeypatch.setattr(ir, "CAMPAIGN_REGISTRY_PATH", tmp_path / "absent_r.json")
    monkeypatch.setattr(ir, "DEAD_ZONES_PATH", tmp_path / "absent_d.json")
    monkeypatch.setattr(ir, "INFORMATION_GAIN_PATH", tmp_path / "absent_i.json")
    rc = ir.main([])
    assert rc == 0
    body = json.loads(capsys.readouterr().out)
    assert body["routing_effect"] == "advisory_only"
    assert body["queue_ordering_effect"] == "none"
    assert body["report_kind"] == "intelligent_routing"
    assert not out_dir.exists()


def test_intelligent_routing_status_cli_default_no_write_smoke(
    tmp_path, monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    from reporting import intelligent_routing_status as irs
    out_dir = tmp_path / "logs" / "intelligent_routing_status"
    monkeypatch.setattr(irs, "STATUS_OUTPUT_DIR", out_dir)
    monkeypatch.setattr(
        irs, "STATUS_LATEST_OUTPUT_PATH", out_dir / "latest.json",
    )
    rc = irs.main([])
    assert rc == 0
    body = json.loads(capsys.readouterr().out)
    assert body["report_kind"] == "intelligent_routing_status"
    assert body["routing_effect"] == "advisory_only"
    assert body["queue_ordering_effect"] == "none"
    assert not out_dir.exists()
