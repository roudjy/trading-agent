from __future__ import annotations

import hashlib
import json
import os
import time
from dataclasses import dataclass
from json import JSONDecodeError
from pathlib import Path
from typing import Any

from agent.backtesting.engine import EngineExecutionSnapshot

RESUME_STATE_DIRNAME = "candidate_resume"
RESUME_STATE_FILENAME_SUFFIX = ".v1.json"
RESUME_STATE_VERSION = "v1"
RESUME_STATE_KIND = "screening_candidate_resume"


@dataclass(frozen=True)
class CandidateResumeState:
    completed_samples: tuple[dict[str, Any], ...]
    active_sample_index: int | None
    active_snapshot: EngineExecutionSnapshot | None


def candidate_resume_state_path(
    *,
    history_root: Path,
    run_id: str,
    batch_id: str,
    candidate_id: str,
) -> Path:
    candidate_key = hashlib.sha256(str(candidate_id).encode("utf-8")).hexdigest()[:16]
    return (
        history_root
        / run_id
        / "batches"
        / batch_id
        / RESUME_STATE_DIRNAME
        / f"{candidate_key}{RESUME_STATE_FILENAME_SUFFIX}"
    )


def build_candidate_resume_state_payload(
    *,
    batch_id: str,
    candidate: dict[str, Any],
    plan_fingerprint: str,
    completed_samples: list[dict[str, Any]],
    active_sample_index: int | None,
    active_snapshot: EngineExecutionSnapshot | None,
) -> dict[str, Any]:
    return {
        "version": RESUME_STATE_VERSION,
        "kind": RESUME_STATE_KIND,
        "batch_id": str(batch_id),
        "candidate": {
            "candidate_id": str(candidate["candidate_id"]),
            "strategy_name": str(candidate["strategy_name"]),
            "asset": str(candidate["asset"]),
            "interval": str(candidate["interval"]),
        },
        "plan_fingerprint": str(plan_fingerprint),
        "completed_samples": [
            {
                "status": str(item["status"]),
                "reason": None if item.get("reason") is None else str(item["reason"]),
            }
            for item in completed_samples
        ],
        "active_resume": (
            None
            if active_snapshot is None or active_sample_index is None
            else {
                "sample_index": int(active_sample_index),
                "engine_snapshot": _serialize_engine_snapshot(active_snapshot),
            }
        ),
    }


def build_screening_candidate_plan_fingerprint(
    *,
    candidate: dict[str, Any],
    interval_range: dict[str, str],
    evaluation_config: dict[str, Any],
    regime_config: dict[str, Any] | None,
    budget_seconds: int,
    samples: list[dict[str, Any]],
) -> str:
    payload = {
        "candidate": {
            "candidate_id": str(candidate["candidate_id"]),
            "strategy_name": str(candidate["strategy_name"]),
            "asset": str(candidate["asset"]),
            "interval": str(candidate["interval"]),
        },
        "interval_range": {
            "start": str(interval_range["start"]),
            "end": str(interval_range["end"]),
        },
        "evaluation_config": evaluation_config,
        "regime_config": regime_config,
        "budget_seconds": int(budget_seconds),
        "samples": samples,
    }
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def read_candidate_resume_state(path: Path) -> dict[str, Any] | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, JSONDecodeError):
        return None


def parse_candidate_resume_state(
    *,
    payload: dict[str, Any] | None,
    batch_id: str,
    candidate: dict[str, Any],
    plan_fingerprint: str,
) -> CandidateResumeState | None:
    if not isinstance(payload, dict):
        return None
    if payload.get("version") != RESUME_STATE_VERSION:
        return None
    if payload.get("kind") != RESUME_STATE_KIND:
        return None
    if str(payload.get("batch_id") or "") != str(batch_id):
        return None
    candidate_payload = payload.get("candidate")
    if not isinstance(candidate_payload, dict):
        return None
    if candidate_payload != {
        "candidate_id": str(candidate["candidate_id"]),
        "strategy_name": str(candidate["strategy_name"]),
        "asset": str(candidate["asset"]),
        "interval": str(candidate["interval"]),
    }:
        return None
    if str(payload.get("plan_fingerprint") or "") != str(plan_fingerprint):
        return None
    completed_payload = payload.get("completed_samples")
    if not isinstance(completed_payload, list):
        return None
    completed_samples: list[dict[str, Any]] = []
    for item in completed_payload:
        if not isinstance(item, dict):
            return None
        status = item.get("status")
        reason = item.get("reason")
        if not isinstance(status, str):
            return None
        if reason is not None and not isinstance(reason, str):
            return None
        completed_samples.append({"status": status, "reason": reason})
    active_payload = payload.get("active_resume")
    if active_payload is None:
        return CandidateResumeState(
            completed_samples=tuple(completed_samples),
            active_sample_index=None,
            active_snapshot=None,
        )
    if not isinstance(active_payload, dict):
        return None
    sample_index = active_payload.get("sample_index")
    if not isinstance(sample_index, int):
        return None
    if sample_index != len(completed_samples):
        return None
    snapshot_payload = active_payload.get("engine_snapshot")
    snapshot = _parse_engine_snapshot(snapshot_payload)
    if snapshot is None:
        return None
    return CandidateResumeState(
        completed_samples=tuple(completed_samples),
        active_sample_index=sample_index,
        active_snapshot=snapshot,
    )


def write_candidate_resume_state(
    *,
    path: Path,
    payload: dict[str, Any],
) -> None:
    _write_json_atomic(path, payload)


def delete_candidate_resume_state(path: Path) -> None:
    try:
        path.unlink()
    except FileNotFoundError:
        return
    except OSError:
        return


def _serialize_engine_snapshot(snapshot: EngineExecutionSnapshot) -> dict[str, Any]:
    return {
        "phase": snapshot.phase,
        "asset_index": snapshot.asset_index,
        "fold_index": snapshot.fold_index,
        "completed_window_ids": [
            [str(asset), str(window_kind), int(fold_index)]
            for asset, window_kind, fold_index in snapshot.completed_window_ids
        ],
    }


def _parse_engine_snapshot(payload: Any) -> EngineExecutionSnapshot | None:
    if not isinstance(payload, dict):
        return None
    phase = payload.get("phase")
    asset_index = payload.get("asset_index")
    fold_index = payload.get("fold_index")
    completed_window_ids = payload.get("completed_window_ids")
    if not isinstance(phase, str):
        return None
    if asset_index is not None and not isinstance(asset_index, int):
        return None
    if fold_index is not None and not isinstance(fold_index, int):
        return None
    if not isinstance(completed_window_ids, list):
        return None
    completed: list[tuple[str, str, int]] = []
    for item in completed_window_ids:
        if not isinstance(item, list) or len(item) != 3:
            return None
        asset, window_kind, fold_number = item
        if not isinstance(asset, str) or not isinstance(window_kind, str) or not isinstance(fold_number, int):
            return None
        completed.append((asset, window_kind, fold_number))
    return EngineExecutionSnapshot(
        phase=phase,
        asset_index=asset_index,
        fold_index=fold_index,
        completed_window_ids=tuple(completed),
    )


def _write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.parent / f".candidate-resume-{os.getpid()}.tmp"
    with tmp_path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, indent=2, sort_keys=False)
    for attempt in range(3):
        try:
            os.replace(tmp_path, path)
            return
        except PermissionError:
            if attempt == 2:
                raise
            time.sleep(0.05)
