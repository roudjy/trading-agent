from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from tools import qre_build_backend_adapter as adapter


def _build_request(tmp_path: Path) -> Path:
    path = tmp_path / "latest_build_request.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "report_kind": "qre_build_request",
                "request_id": "build-request-test",
                "safe_for_ade_build": True,
                "execution_allowed": False,
                "recommended_branch": "feat/qre-add-cache-only-metric-path",
                "recommended_pr_title": "feat: add cache only metric path",
                "acceptance_commands": [
                    "python -m pytest tests/unit/test_qre_build_request_consumer.py -q"
                ],
                "forbidden_actions": ["paper_shadow_live", "broker_risk_execution"],
                "implementation_scope": ["add safe cache-only metric path"],
            }
        ),
        encoding="utf-8",
    )
    return path


def _runner(calls: list[list[str]]) -> Any:
    def run(cmd: list[str], *, timeout: int = 3600) -> tuple[int, str, str]:
        calls.append(cmd)
        if cmd[:3] == ["git", "branch", "--show-current"]:
            return (0, "main\n", "")
        if cmd[:3] == ["git", "fetch", "origin"]:
            return (0, "", "")
        if cmd[:3] == ["git", "diff", "--name-only"]:
            return (0, "", "")
        if cmd[:3] == ["gh", "pr", "view"]:
            return (1, "", "no pr")
        return (0, "backend ok", "")

    return run


def _protected_bytes() -> dict[str, bytes | None]:
    paths = [Path("research/research_latest.json"), Path("research/strategy_matrix.csv")]
    return {path.as_posix(): path.read_bytes() if path.exists() else None for path in paths}


def test_codex_command_override_is_used(monkeypatch: Any, tmp_path: Path) -> None:
    calls: list[list[str]] = []
    monkeypatch.setenv("QRE_CODEX_COMMAND", "custom-codex --profile qre")
    monkeypatch.setattr(adapter, "_run", _runner(calls))

    result = adapter.build_backend_result(
        build_request_path=_build_request(tmp_path),
        backend="codex_cli",
        output_dir=tmp_path / "out",
    )

    assert calls[0][:2] == ["custom-codex", "--profile"]
    assert "exec" in calls[0]
    assert result["backend_command_resolved"] is True
    assert result["backend_command_source"] == "command_env"
    assert result["backend_command_path"] == "custom-codex"


def test_codex_path_override_is_used(monkeypatch: Any, tmp_path: Path) -> None:
    codex_path = tmp_path / "codex.cmd"
    codex_path.write_text("@echo off\n", encoding="utf-8")
    calls: list[list[str]] = []
    monkeypatch.setenv("QRE_CODEX_PATH", str(codex_path))
    monkeypatch.setattr(adapter, "_run", _runner(calls))

    result = adapter.build_backend_result(
        build_request_path=_build_request(tmp_path),
        backend="codex_cli",
        output_dir=tmp_path / "out",
    )

    assert calls[0][0] == str(codex_path)
    assert result["backend_command_resolved"] is True
    assert result["backend_command_source"] == "path_env"
    assert result["backend_command_kind"] == "cmd"
    assert result["backend_command_path"] == str(codex_path)


def test_ps1_codex_path_is_wrapped_with_powershell(monkeypatch: Any, tmp_path: Path) -> None:
    codex_path = tmp_path / "codex.ps1"
    codex_path.write_text("Write-Output codex\n", encoding="utf-8")
    calls: list[list[str]] = []
    monkeypatch.setenv("QRE_CODEX_PATH", str(codex_path))
    monkeypatch.setattr(adapter, "_run", _runner(calls))

    result = adapter.build_backend_result(
        build_request_path=_build_request(tmp_path),
        backend="codex_cli",
        output_dir=tmp_path / "out",
    )

    assert calls[0][:6] == [
        "powershell",
        "-NoProfile",
        "-ExecutionPolicy",
        "Bypass",
        "-File",
        str(codex_path),
    ]
    assert "exec" in calls[0]
    assert result["backend_command_kind"] == "powershell_ps1"


def test_missing_codex_fails_closed(monkeypatch: Any, tmp_path: Path) -> None:
    monkeypatch.delenv("QRE_CODEX_COMMAND", raising=False)
    monkeypatch.delenv("QRE_CODEX_PATH", raising=False)
    monkeypatch.setattr(adapter.shutil, "which", lambda _: None)
    monkeypatch.setattr(adapter, "KNOWN_WINDOWS_CODEX_PS1", tmp_path / "missing" / "codex.ps1")
    calls: list[list[str]] = []
    monkeypatch.setattr(adapter, "_run", _runner(calls))

    result = adapter.build_backend_result(
        build_request_path=_build_request(tmp_path),
        backend="codex_cli",
        output_dir=tmp_path / "out",
    )

    assert result["backend_command_resolved"] is False
    assert result["blocked_reason"] == "codex_cli_not_found"
    assert result["backend_returncode"] == -1
    assert result["build_started"] is False
    assert calls[0][:3] == ["git", "branch", "--show-current"]


def test_adapter_emits_consumer_compatible_json(monkeypatch: Any, tmp_path: Path) -> None:
    codex_path = tmp_path / "codex.exe"
    codex_path.write_text("", encoding="utf-8")
    monkeypatch.setenv("QRE_CODEX_PATH", str(codex_path))
    monkeypatch.setattr(adapter, "_run", _runner([]))

    result = adapter.build_backend_result(
        build_request_path=_build_request(tmp_path),
        backend="codex_cli",
        output_dir=tmp_path / "out",
        execute=False,
    )
    persisted = json.loads((tmp_path / "out" / "build-request-test.json").read_text(encoding="utf-8"))

    for key in (
        "build_request_consumed",
        "build_started",
        "branch_created",
        "code_changed",
        "tests_run",
        "pr_created",
        "pr_metadata",
    ):
        assert key in result
        assert key in persisted
    assert persisted["backend_command_resolved"] is True
    assert persisted["backend_command_kind"] == "exe"


def test_adapter_does_not_mutate_protected_artifacts(monkeypatch: Any, tmp_path: Path) -> None:
    before = _protected_bytes()
    codex_path = tmp_path / "codex.cmd"
    codex_path.write_text("@echo off\n", encoding="utf-8")
    monkeypatch.setenv("QRE_CODEX_PATH", str(codex_path))
    monkeypatch.setattr(adapter, "_run", _runner([]))

    adapter.build_backend_result(
        build_request_path=_build_request(tmp_path),
        backend="codex_cli",
        output_dir=tmp_path / "out",
        execute=False,
    )

    assert _protected_bytes() == before
