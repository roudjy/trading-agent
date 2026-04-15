from __future__ import annotations

import argparse
import importlib
import os
import pickle
import shutil
import subprocess
import sys
import time
import uuid
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable

from agent.backtesting.engine import BacktestEngine
from research.candidate_pipeline import SCREENING_REJECTED, screening_param_samples
from research.screening_runtime import (
    FINAL_STATUS_ERRORED,
    FINAL_STATUS_TIMED_OUT,
    execute_screening_candidate,
    execute_screening_candidate_samples,
)

HARD_TIMEOUT_MARGIN_SECONDS = 2.0


def _utc_now() -> datetime:
    return datetime.now(UTC)


def _elapsed_seconds(monotonic_source: Callable[[], float], started_at_monotonic: float) -> int:
    return max(0, int(round(monotonic_source() - started_at_monotonic)))


def _build_engine(
    *,
    engine_class: type[BacktestEngine],
    start_datum: str,
    eind_datum: str,
    evaluation_config: dict[str, Any],
    regime_config: dict[str, Any] | None,
) -> BacktestEngine:
    try:
        return engine_class(
            start_datum=start_datum,
            eind_datum=eind_datum,
            evaluation_config=evaluation_config,
            regime_config=regime_config,
        )
    except TypeError as exc:
        if "regime_config" in str(exc):
            try:
                return engine_class(
                    start_datum=start_datum,
                    eind_datum=eind_datum,
                    evaluation_config=evaluation_config,
                )
            except TypeError as exc2:
                if "evaluation_config" not in str(exc2):
                    raise
                return engine_class(
                    start_datum=start_datum,
                    eind_datum=eind_datum,
                )
        if "evaluation_config" not in str(exc):
            raise
        return engine_class(
            start_datum=start_datum,
            eind_datum=eind_datum,
        )


def _object_reference(target: Any) -> dict[str, str] | None:
    module_name = getattr(target, "__module__", None)
    qualname = getattr(target, "__qualname__", None)
    if not module_name or not qualname or "<locals>" in qualname:
        return None
    return {
        "module": str(module_name),
        "qualname": str(qualname),
    }


def _resolve_reference(reference: dict[str, str]) -> Any:
    target = importlib.import_module(reference["module"])
    for part in reference["qualname"].split("."):
        target = getattr(target, part)
    return target


def _serialized_strategy_samples(
    *,
    strategy: dict[str, Any],
    max_samples: int,
) -> list[dict[str, Any]]:
    samples: list[dict[str, Any]] = []
    for params in screening_param_samples(strategy.get("params") or {}, max_samples=max_samples):
        sample = {
            "params": params,
            "strategy_callable": strategy["factory"](**params),
        }
        pickle.dumps(sample)
        samples.append(sample)
    return samples


def _build_child_payload(
    *,
    strategy: dict[str, Any],
    candidate: dict[str, Any],
    interval_range: dict[str, str],
    evaluation_config: dict[str, Any],
    regime_config: dict[str, Any] | None,
    budget_seconds: int,
    max_samples: int,
    engine_class: type[BacktestEngine],
) -> dict[str, Any]:
    engine_reference = _object_reference(engine_class)
    if engine_reference is None:
        raise TypeError(f"engine class {engine_class!r} is not importable in a child process")

    payload: dict[str, Any] = {
        "candidate": dict(candidate),
        "interval_range": dict(interval_range),
        "evaluation_config": dict(evaluation_config),
        "regime_config": dict(regime_config) if regime_config is not None else None,
        "budget_seconds": int(budget_seconds),
        "max_samples": int(max_samples),
        "engine_class_ref": engine_reference,
        "samples_total": len(screening_param_samples(strategy.get("params") or {}, max_samples=max_samples)),
    }

    factory_reference = _object_reference(strategy.get("factory"))
    if factory_reference is not None:
        payload["factory_ref"] = factory_reference
        payload["strategy_params"] = dict(strategy.get("params") or {})
    else:
        payload["strategy_samples"] = _serialized_strategy_samples(
            strategy=strategy,
            max_samples=max_samples,
        )
    return payload


def _run_child_payload(payload: dict[str, Any]) -> dict[str, Any]:
    engine = None
    try:
        engine_class = _resolve_reference(payload["engine_class_ref"])
        engine = _build_engine(
            engine_class=engine_class,
            start_datum=str(payload["interval_range"]["start"]),
            eind_datum=str(payload["interval_range"]["end"]),
            evaluation_config=dict(payload["evaluation_config"]),
            regime_config=payload["regime_config"],
        )
        if payload.get("factory_ref") is not None:
            strategy = {
                "factory": _resolve_reference(payload["factory_ref"]),
                "params": dict(payload["strategy_params"]),
            }
            outcome = execute_screening_candidate(
                strategy=strategy,
                candidate=dict(payload["candidate"]),
                engine=engine,
                budget_seconds=int(payload["budget_seconds"]),
                max_samples=int(payload["max_samples"]),
            )
        else:
            strategy_samples = [
                (dict(sample["params"]), sample["strategy_callable"])
                for sample in payload["strategy_samples"]
            ]
            outcome = execute_screening_candidate_samples(
                candidate=dict(payload["candidate"]),
                engine=engine,
                budget_seconds=int(payload["budget_seconds"]),
                strategy_samples=strategy_samples,
                samples_total=int(payload["samples_total"]),
            )
        return {
            "execution_state": "completed",
            "outcome": outcome,
            "provenance_events": list(getattr(engine, "_provenance_events", [])),
        }
    except Exception as exc:
        return {
            "execution_state": "failed",
            "reason_detail": str(exc),
            "error_type": type(exc).__name__,
            "provenance_events": list(getattr(engine, "_provenance_events", [])) if engine is not None else [],
        }


def _failed_outcome(
    *,
    started_at: datetime,
    now_source: Callable[[], datetime],
    monotonic_source: Callable[[], float],
    started_at_monotonic: float,
    reason_detail: str,
    samples_total: int,
    samples_completed: int,
) -> dict[str, Any]:
    return {
        "legacy_decision": {
            "status": SCREENING_REJECTED,
            "reason": "screening_candidate_error",
            "sampled_combination_count": int(samples_completed),
        },
        "runtime_status": "running",
        "final_status": FINAL_STATUS_ERRORED,
        "started_at": started_at.isoformat(),
        "finished_at": now_source().astimezone(UTC).isoformat(),
        "elapsed_seconds": _elapsed_seconds(monotonic_source, started_at_monotonic),
        "samples_total": int(samples_total),
        "samples_completed": int(samples_completed),
        "decision": SCREENING_REJECTED,
        "reason_code": "screening_candidate_error",
        "reason_detail": reason_detail,
    }


def _timed_out_outcome(
    *,
    started_at: datetime,
    now_source: Callable[[], datetime],
    monotonic_source: Callable[[], float],
    started_at_monotonic: float,
    budget_seconds: int,
    samples_total: int,
    samples_completed: int,
) -> dict[str, Any]:
    return {
        "legacy_decision": {
            "status": SCREENING_REJECTED,
            "reason": "candidate_budget_exceeded",
            "sampled_combination_count": int(samples_completed),
        },
        "runtime_status": "running",
        "final_status": FINAL_STATUS_TIMED_OUT,
        "started_at": started_at.isoformat(),
        "finished_at": now_source().astimezone(UTC).isoformat(),
        "elapsed_seconds": _elapsed_seconds(monotonic_source, started_at_monotonic),
        "samples_total": int(samples_total),
        "samples_completed": int(samples_completed),
        "decision": SCREENING_REJECTED,
        "reason_code": "candidate_budget_exceeded",
        "reason_detail": f"candidate exceeded screening budget of {int(budget_seconds)} seconds",
    }


def _scratch_dir() -> Path:
    target = Path.cwd() / ".tmp" / "screening-process"
    target.mkdir(parents=True, exist_ok=True)
    return target


def _child_command(input_path: Path, output_path: Path) -> tuple[list[str], dict[str, str]]:
    repo_root = Path(__file__).resolve().parent.parent
    env = dict(os.environ)
    existing_pythonpath = env.get("PYTHONPATH")
    env["PYTHONPATH"] = str(repo_root) if not existing_pythonpath else os.pathsep.join([str(repo_root), existing_pythonpath])
    return [
        sys.executable,
        "-m",
        "research.screening_process",
        "--child",
        str(input_path),
        str(output_path),
    ], env


def _stderr_snippet(path: Path, *, max_lines: int = 8, max_chars: int = 400) -> str | None:
    if not path.exists():
        return None
    try:
        content = path.read_text(encoding="utf-8", errors="replace").strip()
    except OSError:
        return None
    if not content:
        return None
    lines = content.splitlines()
    snippet = "\n".join(lines[-max_lines:])
    if len(snippet) > max_chars:
        snippet = snippet[-max_chars:]
    return snippet


def execute_screening_candidate_isolated(
    *,
    strategy: dict[str, Any],
    candidate: dict[str, Any],
    interval_range: dict[str, str],
    evaluation_config: dict[str, Any],
    regime_config: dict[str, Any] | None,
    budget_seconds: int,
    max_samples: int,
    engine_class: type[BacktestEngine] = BacktestEngine,
    timeout_margin_seconds: float = HARD_TIMEOUT_MARGIN_SECONDS,
    now_source: Callable[[], datetime] | None = None,
    monotonic_source: Callable[[], float] | None = None,
    on_progress: Callable[[dict[str, int]], None] | None = None,
) -> dict[str, Any]:
    del on_progress

    now = now_source or _utc_now
    monotonic = monotonic_source or time.monotonic
    started_at = now().astimezone(UTC)
    started_at_monotonic = monotonic()

    try:
        payload = _build_child_payload(
            strategy=strategy,
            candidate=candidate,
            interval_range=interval_range,
            evaluation_config=evaluation_config,
            regime_config=regime_config,
            budget_seconds=budget_seconds,
            max_samples=max_samples,
            engine_class=engine_class,
        )
    except Exception as exc:
        return {
            "execution_state": "failed",
            "outcome": _failed_outcome(
                started_at=started_at,
                now_source=now,
                monotonic_source=monotonic,
                started_at_monotonic=started_at_monotonic,
                reason_detail=str(exc),
                samples_total=0,
                samples_completed=0,
            ),
            "provenance_events": [],
        }

    scratch_root = _scratch_dir() / f"screening-{uuid.uuid4().hex}"
    scratch_root.mkdir(parents=True, exist_ok=False)
    input_path = scratch_root / f"{uuid.uuid4().hex}.input.pkl"
    output_path = scratch_root / f"{uuid.uuid4().hex}.output.pkl"
    stderr_path = scratch_root / f"{uuid.uuid4().hex}.stderr.txt"
    input_path.write_bytes(pickle.dumps(payload))

    command, env = _child_command(input_path, output_path)
    try:
        with stderr_path.open("w", encoding="utf-8") as stderr_handle:
            process = subprocess.Popen(
                command,
                cwd=str(Path.cwd()),
                env=env,
                stdout=subprocess.DEVNULL,
                stderr=stderr_handle,
            )

            try:
                process.wait(timeout=max(0.0, float(budget_seconds)) + max(0.0, float(timeout_margin_seconds)))
            except subprocess.TimeoutExpired:
                process.terminate()
                try:
                    process.wait(timeout=1.0)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=1.0)
                return {
                    "execution_state": "timed_out",
                    "outcome": _timed_out_outcome(
                        started_at=started_at,
                        now_source=now,
                        monotonic_source=monotonic,
                        started_at_monotonic=started_at_monotonic,
                        budget_seconds=budget_seconds,
                        samples_total=int(payload["samples_total"]),
                        samples_completed=0,
                    ),
                    "provenance_events": [],
                }

        if process.returncode != 0 or not output_path.exists():
            reason_detail = f"screening child process exited with code {process.returncode}"
            stderr_snippet = _stderr_snippet(stderr_path)
            if stderr_snippet:
                reason_detail = f"{reason_detail}; stderr: {stderr_snippet}"
            return {
                "execution_state": "failed",
                "outcome": _failed_outcome(
                    started_at=started_at,
                    now_source=now,
                    monotonic_source=monotonic,
                    started_at_monotonic=started_at_monotonic,
                    reason_detail=reason_detail,
                    samples_total=int(payload["samples_total"]),
                    samples_completed=0,
                ),
                "provenance_events": [],
            }

        result = pickle.loads(output_path.read_bytes())
        if result["execution_state"] == "failed":
            return {
                "execution_state": "failed",
                "outcome": _failed_outcome(
                    started_at=started_at,
                    now_source=now,
                    monotonic_source=monotonic,
                    started_at_monotonic=started_at_monotonic,
                    reason_detail=str(result.get("reason_detail") or "screening child process failed"),
                    samples_total=int(payload["samples_total"]),
                    samples_completed=0,
                ),
                "provenance_events": list(result.get("provenance_events") or []),
            }

        return {
            "execution_state": "completed",
            "outcome": dict(result["outcome"]),
            "provenance_events": list(result.get("provenance_events") or []),
        }
    finally:
        shutil.rmtree(scratch_root, ignore_errors=True)


def _run_child_cli(input_path: str, output_path: str) -> int:
    payload = pickle.loads(Path(input_path).read_bytes())
    result = _run_child_payload(payload)
    Path(output_path).write_bytes(pickle.dumps(result))
    return 0


def _parse_cli_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Screening candidate child process entrypoint.")
    parser.add_argument("--child", action="store_true")
    parser.add_argument("input_path", nargs="?")
    parser.add_argument("output_path", nargs="?")
    return parser.parse_args()


if __name__ == "__main__":
    args = _parse_cli_args()
    if args.child and args.input_path and args.output_path:
        raise SystemExit(_run_child_cli(args.input_path, args.output_path))
