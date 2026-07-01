from __future__ import annotations

import json
import os
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Final

from packages.qre_research import automated_hypothesis_generation as a20
from packages.qre_research import autonomous_orchestration as ao
from packages.qre_research import bounded_strategy_synthesis as bss
from packages.qre_research import empirical_evidence_pack as eep
from packages.qre_research import hypothesis_lifecycle as qhl
from packages.qre_research.generated_strategy_paths import REPO_ROOT, validate_write_target


SCHEMA_VERSION: Final[str] = "1.0"
MODULE_VERSION: Final[str] = "ade-qre-032.1"
DEFAULT_MAX_CYCLES: Final[int] = 3
MAX_SYNTHESIS_ATTEMPTS_PER_CYCLE: Final[int] = 1
FLYWHEEL_REPORT_PATH: Final[Path] = Path(
    "generated_research/orchestration/reports/empirical_research_flywheel.v1.json"
)


def _stable_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def stable_digest(value: Any) -> str:
    import hashlib

    return hashlib.sha256(_stable_json(value).encode("utf-8")).hexdigest()


def _content_id(prefix: str, payload: Any) -> str:
    return f"{prefix}_{stable_digest(payload)[:16]}"


def _atomic_write(path: Path, payload: str) -> None:
    validate_write_target(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(
        prefix=".ade_qre_032.",
        suffix=".tmp",
        dir=str(path.parent),
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(payload)
        os.replace(tmp_name, path)
    except Exception:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise


def _now_utc() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _json_safe(value: Any) -> Any:
    if isinstance(value, Path):
        return value.as_posix()
    if isinstance(value, dict):
        return {str(key): _json_safe(child) for key, child in value.items()}
    if isinstance(value, list):
        return [_json_safe(child) for child in value]
    return value


def run_empirical_research_flywheel(
    *,
    repo_root: Path = REPO_ROOT,
    max_cycles: int = DEFAULT_MAX_CYCLES,
    write_outputs: bool = True,
    report_date: str | None = None,
) -> dict[str, Any]:
    compiled = a20.compile_candidate_theses(repo_root=repo_root)
    trusted_before = qhl.run_trusted_hypothesis_loop(repo_root=repo_root, write_outputs=write_outputs)
    feasibility_before = qhl.build_feasibility_snapshot(repo_root=repo_root)
    routing_before = qhl.build_routing_snapshot(repo_root=repo_root)
    sampling_before = qhl.build_sampling_snapshot(repo_root=repo_root)
    orchestration = ao.run_orchestration(
        repo_root=repo_root,
        mode="LOCAL_AUTONOMOUS",
        max_cycles=max_cycles,
        write_outputs=write_outputs,
        report_date=report_date,
    )
    evidence_pack = eep.run_empirical_evidence_pack(
        repo_root=repo_root,
        write_outputs=write_outputs,
        execute_if_missing=True,
    )
    trusted_after = qhl.run_trusted_hypothesis_loop(repo_root=repo_root, write_outputs=write_outputs)
    feasibility_after = qhl.build_feasibility_snapshot(repo_root=repo_root)
    routing_after = qhl.build_routing_snapshot(repo_root=repo_root)
    sampling_after = qhl.build_sampling_snapshot(repo_root=repo_root)
    readiness = bss.materialize_synthesis_readiness(repo_root=repo_root, write_outputs=write_outputs)
    synthesis = bss.run_bounded_strategy_synthesis(repo_root=repo_root, write_outputs=write_outputs)
    behavior_families = sorted(
        {
            str(row.get("behavior_family") or "")
            for row in compiled.get("rows", [])
            if str(row.get("behavior_family") or "")
        }
    )
    summary = {
        "flywheel_identity": _content_id(
            "qef",
            {
                "candidate_count": compiled.get("summary", {}).get("candidate_count"),
                "closeout": orchestration.get("latest_status_identity"),
                "evidence_pack_id": evidence_pack.get("evidence_pack_id"),
                "readiness_status": readiness.get("readiness_status"),
            },
        ),
        "generated_at_utc": _now_utc(),
        "max_cycles": max_cycles,
        "max_synthesis_attempts_per_cycle": MAX_SYNTHESIS_ATTEMPTS_PER_CYCLE,
        "candidate_count": int(compiled.get("summary", {}).get("candidate_count") or 0),
        "admitted_count": int(compiled.get("summary", {}).get("admitted_count") or 0),
        "behavior_families": behavior_families,
        "exact_duplicates_suppressed": int(
            compiled.get("summary", {}).get("exact_duplicate_suppressed_count") or 0
        ),
        "near_duplicates_suppressed": int(
            compiled.get("summary", {}).get("near_duplicate_suppressed_count") or 0
        ),
        "research_cycles_executed": int(orchestration.get("cycles_completed") or 0),
        "campaigns_executed": int(orchestration.get("campaigns_executed") or 0),
        "feasibility_ready_count": int(feasibility_after.get("summary", {}).get("feasibility_ready_count") or 0),
        "routing_ready_count": int(routing_after.get("summary", {}).get("routing_ready_count") or 0),
        "sampling_ready_count": int(sampling_after.get("summary", {}).get("sampling_ready_count") or 0),
        "evidence_pack_disposition": str(evidence_pack.get("disposition") or ""),
        "synthesis_readiness": str(readiness.get("readiness_status") or ""),
        "synthesis_status": str(synthesis.get("status") or ""),
        "next_action": str(
            synthesis.get("recommended_next_actions", [""])[0]
            or readiness.get("recommended_next_actions", [""])[0]
            or evidence_pack.get("recommended_next_action")
            or orchestration.get("next_autonomous_action")
            or trusted_after.get("summary", {}).get("next_action")
            or "no_safe_action"
        ),
    }
    packet = {
        "schema_version": SCHEMA_VERSION,
        "module_version": MODULE_VERSION,
        "report_kind": "qre_empirical_research_flywheel",
        "summary": summary,
        "generation": compiled,
        "trusted_loop_before": trusted_before,
        "feasibility_before": feasibility_before,
        "routing_before": routing_before,
        "sampling_before": sampling_before,
        "orchestration": orchestration,
        "empirical_evidence_pack": evidence_pack,
        "trusted_loop_after": trusted_after,
        "feasibility_after": feasibility_after,
        "routing_after": routing_after,
        "sampling_after": sampling_after,
        "synthesis_readiness": readiness,
        "strategy_synthesis": synthesis,
    }
    packet = _json_safe(packet)
    if write_outputs:
        _atomic_write(
            repo_root / FLYWHEEL_REPORT_PATH,
            json.dumps(packet, indent=2, sort_keys=True) + "\n",
        )
    return packet


__all__ = [
    "DEFAULT_MAX_CYCLES",
    "FLYWHEEL_REPORT_PATH",
    "MODULE_VERSION",
    "SCHEMA_VERSION",
    "run_empirical_research_flywheel",
    "stable_digest",
]
