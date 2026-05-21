"""Proposal-only campaign seed scaffold for Hypothesis Discovery."""

from __future__ import annotations

import datetime as _dt
import hashlib
import json
import os
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Final

from reporting import reason_records as _rr
from research.hypothesis_discovery.behavior_catalog import get_behavior
from research.hypothesis_discovery.behavior_hypotheses import (
    build_behavior_hypotheses,
)
from research.hypothesis_discovery.opportunity_scoring import (
    ACTIVE_DIAGNOSTICS,
    MODULE_VERSION as SCORING_MODULE_VERSION,
    score_opportunity,
)
from research.hypothesis_discovery.preset_feasibility import (
    evaluate_preset_feasibility,
)


REPO_ROOT: Final[Path] = Path(__file__).resolve().parents[2]
SCHEMA_VERSION: Final[int] = 1
SEED_SCHEMA_VERSION: Final[str] = "v1"
MODULE_VERSION: Final[str] = "v3.15.19-minimal-2026-05-21"
REPORT_KIND: Final[str] = "hypothesis_discovery_minimal_digest"

ARTIFACT_DIR: Final[Path] = (
    REPO_ROOT / "logs" / "hypothesis_discovery_minimal"
)
ARTIFACT_LATEST: Final[Path] = ARTIFACT_DIR / "latest.json"
SEED_LOG: Final[Path] = ARTIFACT_DIR / "seeds_v1.jsonl"
HISTORY: Final[Path] = ARTIFACT_DIR / "history.jsonl"
_WRITE_PREFIX: Final[str] = "logs/hypothesis_discovery_minimal/"


def _utcnow() -> str:
    return (
        _dt.datetime.now(_dt.UTC)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def _validate_write_target(path: Path) -> None:
    normalised = str(path).replace("\\", "/")
    if _WRITE_PREFIX not in normalised:
        raise ValueError(
            "hypothesis_discovery_minimal: refusing write outside "
            f"allowlist: {path!r}"
        )


def _rel(p: Path) -> str:
    try:
        return str(p.relative_to(REPO_ROOT)).replace("\\", "/")
    except ValueError:
        return str(p).replace("\\", "/")


def _hash_id(prefix: str, *parts: str) -> str:
    h = hashlib.sha256()
    for part in parts:
        h.update(part.encode("utf-8"))
        h.update(b"\x1f")
    return prefix + h.hexdigest()[:16]


def _seed_from(
    *,
    generated_at_utc: str,
    hypothesis_id: str,
    behavior_family: str,
    strategy_mapping_ref: str,
    preset_feasibility_ref: str,
    opportunity_probability_score: float,
    required_diagnostics: tuple[str, ...],
    required_null_model: str,
    scoring_reason_record_id: str,
    inputs_digest: str,
) -> dict[str, object]:
    seed_id = _hash_id(
        "hds_",
        inputs_digest,
        "campaign_seed_proposal",
        behavior_family,
        hypothesis_id,
    )
    return {
        "seed_id": seed_id,
        "generated_at_utc": generated_at_utc,
        "behavior_family": behavior_family,
        "strategy_mapping_ref": strategy_mapping_ref,
        "preset_feasibility_ref": preset_feasibility_ref,
        "opportunity_probability_score": opportunity_probability_score,
        "exploration_priority": "proposal_only",
        "required_diagnostics": list(required_diagnostics),
        "required_null_model": required_null_model,
        "multiplicity_ledger_event_id": _hash_id(
            "ml_pending_", seed_id, inputs_digest
        ),
        "scoring_reason_record_id": scoring_reason_record_id,
        "schema_version": SEED_SCHEMA_VERSION,
    }


def collect_snapshot(
    diagnostics_by_hypothesis: Mapping[str, Mapping[str, Any]] | None = None,
    *,
    frozen_utc: str | None = None,
    reason_records_artifact_dir: Path | None = None,
    emit_reason_records: bool = True,
) -> dict[str, Any]:
    ts = frozen_utc or _utcnow()
    diagnostics = diagnostics_by_hypothesis or {}
    hypotheses = build_behavior_hypotheses()

    items: list[dict[str, object]] = []
    seeds: list[dict[str, object]] = []
    for hyp in hypotheses:
        behavior = get_behavior(hyp.strategy_family)
        feasibility = evaluate_preset_feasibility(hyp.hypothesis_id)
        score = score_opportunity(
            hyp.hypothesis_id,
            diagnostics.get(hyp.hypothesis_id, {}),
            preset_feasible=feasibility.feasible,
            frozen_utc=ts,
        )
        reason_record = _rr.build_record(
            decision_kind=_rr.DECISION_KIND_SCORING,
            subject_id=hyp.hypothesis_id,
            decision=score.decision,
            reason_codes=score.reason_codes,
            reason_text=score.reason_text,
            inputs={
                "hypothesis_id": hyp.hypothesis_id,
                "score_inputs_digest": score.inputs_digest,
                "proposal_surface": "hypothesis_discovery_minimal",
            },
            inputs_digest=score.inputs_digest,
            frozen_utc=ts,
        )
        if emit_reason_records:
            _rr.append(
                reason_record,
                artifact_dir=reason_records_artifact_dir,
            )

        seed: dict[str, object] | None = None
        if score.decision == "keep":
            seed = _seed_from(
                generated_at_utc=ts,
                hypothesis_id=hyp.hypothesis_id,
                behavior_family=hyp.behavior_family,
                strategy_mapping_ref=hyp.strategy_mapping_ref,
                preset_feasibility_ref=feasibility.preset_feasibility_ref,
                opportunity_probability_score=(
                    score.opportunity_probability_score
                ),
                required_diagnostics=behavior.required_diagnostics,
                required_null_model=behavior.required_null_model,
                scoring_reason_record_id=score.scoring_reason_record_id,
                inputs_digest=score.inputs_digest,
            )
            seeds.append(seed)

        items.append({
            "hypothesis_id": hyp.hypothesis_id,
            "behavior_family": hyp.behavior_family,
            "strategy_mapping_ref": hyp.strategy_mapping_ref,
            "preset_feasibility": feasibility.to_payload(),
            "score": score.to_payload(),
            "proposal_emitted": seed is not None,
            "seed_id": seed["seed_id"] if seed is not None else "",
        })

    items.sort(key=lambda it: str(it["hypothesis_id"]))
    seeds.sort(key=lambda seed: str(seed["seed_id"]))

    return {
        "schema_version": SCHEMA_VERSION,
        "module_version": MODULE_VERSION,
        "report_kind": REPORT_KIND,
        "generated_at_utc": ts,
        "mode": "dry-run",
        "safe_to_execute": False,
        "proposal_only": True,
        "score_semantics": "expected_research_value_not_probability",
        "proposal_order": "seed_id_ascending_not_score_ranked",
        "active_diagnostics": list(ACTIVE_DIAGNOSTICS),
        "scoring_module_version": SCORING_MODULE_VERSION,
        "multiplicity_ledger_write_effect": "none_writer_deferred",
        "counts": {
            "hypotheses": len(items),
            "seeds": len(seeds),
            "filtered": len(items) - len(seeds),
        },
        "items": items,
        "seeds": seeds,
        "final_recommendation": (
            "proposal_seeds_available" if seeds else "nothing_to_propose"
        ),
        "note": (
            "Minimal v3.15.19 Hypothesis Discovery. Seeds are proposals "
            "only; funnel policy and campaign mechanics remain the only "
            "candidate-promotion authority."
        ),
    }


def _read_existing_seed_ids(path: Path) -> set[str]:
    if not path.is_file():
        return set()
    ids: set[str] = set()
    with path.open(encoding="utf-8") as f:
        for line in f:
            s = line.strip()
            if not s:
                continue
            try:
                row = json.loads(s)
            except json.JSONDecodeError:
                continue
            sid = row.get("seed_id")
            if isinstance(sid, str) and sid:
                ids.add(sid)
    return ids


def write_outputs(
    snapshot: Mapping[str, Any],
    *,
    artifact_dir: Path | None = None,
) -> dict[str, str]:
    base = artifact_dir or ARTIFACT_DIR
    base.mkdir(parents=True, exist_ok=True)
    latest = base / ARTIFACT_LATEST.name
    seed_log = base / SEED_LOG.name
    history = base / HISTORY.name
    for path in (latest, seed_log, history):
        _validate_write_target(path)

    payload = json.dumps(snapshot, sort_keys=True, indent=2)
    tmp_latest = latest.with_suffix(latest.suffix + ".tmp")
    tmp_latest.write_text(payload, encoding="utf-8")
    os.replace(tmp_latest, latest)

    existing_seed_ids = _read_existing_seed_ids(seed_log)
    with seed_log.open("a", encoding="utf-8") as f:
        for seed in snapshot.get("seeds", []):
            if not isinstance(seed, Mapping):
                continue
            seed_id = seed.get("seed_id")
            if not isinstance(seed_id, str) or seed_id in existing_seed_ids:
                continue
            f.write(json.dumps(seed, sort_keys=True, separators=(",", ":")))
            f.write("\n")
            existing_seed_ids.add(seed_id)

    compact = json.dumps(snapshot, sort_keys=True, separators=(",", ":"))
    with history.open("a", encoding="utf-8") as f:
        f.write(compact + "\n")

    return {
        "latest": _rel(latest),
        "seed_log": _rel(seed_log),
        "history": _rel(history),
    }
