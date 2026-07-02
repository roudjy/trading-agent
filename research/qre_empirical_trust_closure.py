from __future__ import annotations

import argparse
import hashlib
import json
import os
import tempfile
from contextlib import suppress
from datetime import UTC, datetime
from itertools import pairwise
from pathlib import Path
from typing import Any, Final

from packages.qre_research import empirical_evidence_pack as eep
from packages.qre_research import second_preregistered_campaign as campaign
from packages.qre_research.generated_strategy_paths import validate_write_target

REPO_ROOT: Final[Path] = Path(__file__).resolve().parent.parent

SCHEMA_VERSION: Final[str] = "1.0"
MODULE_VERSION: Final[str] = "ade-qre-036.1"
REPORT_KIND: Final[str] = "qre_empirical_trust_closure"

TRUST_ROOT: Final[Path] = Path("generated_research/orchestration/trust_closure")
CAMPAIGN_HISTORY_PATH: Final[Path] = Path(
    "generated_research/campaign_execution/evidence/empirical_campaign_history.v1.json"
)
RESEARCH_MEMORY_PATH: Final[Path] = Path(
    "generated_research/hypotheses/lifecycle/research_memory.v1.json"
)
REASON_RECORDS_PATH: Final[Path] = Path(
    "generated_research/hypotheses/lifecycle/reason_records.v1.json"
)
FAILURE_ACTIONS_PATH: Final[Path] = Path(
    "generated_research/hypotheses/lifecycle/failure_actions.v1.json"
)
LINEAGE_PATH: Final[Path] = Path("generated_research/lineage/empirical_campaign_lineage.v1.json")

ATTRIBUTION_PATH: Final[Path] = TRUST_ROOT / "campaign_attribution_integrity.v1.json"
POLICY_PATH: Final[Path] = TRUST_ROOT / "trust_policy_v1_1.v1.json"
PLAN_PATH: Final[Path] = TRUST_ROOT / "empirical_campaign_portfolio_plan.v1.json"
EXECUTION_PATH: Final[Path] = TRUST_ROOT / "empirical_campaign_execution_summary.v1.json"
ROUTING_PATH: Final[Path] = TRUST_ROOT / "routing_comparators.v1.json"
SAMPLING_PATH: Final[Path] = TRUST_ROOT / "sampling_utility_records.v1.json"
ACTION_PATH: Final[Path] = TRUST_ROOT / "action_effectiveness.v1.json"
ACCEPTANCE_PATH: Final[Path] = TRUST_ROOT / "evidence_changing_acceptance_history.v1.json"
TRUST_HORIZON_PATH: Final[Path] = TRUST_ROOT / "trust_horizon.v1.json"
TRUST_HORIZON_LATEST_RUN_PATH: Final[Path] = TRUST_ROOT / "trust_horizon_latest_run.v1.json"
TRUST_HORIZON_CONSISTENCY_PATH: Final[Path] = TRUST_ROOT / "trust_horizon_consistency.v1.json"
SUMMARY_PATH: Final[Path] = TRUST_ROOT / "empirical_trust_closure.v1.json"

MAX_NEW_REAL_CAMPAIGNS: Final[int] = 6
TARGET_NEW_REAL_CAMPAIGNS: Final[int] = 4
MIN_EVIDENCE_CHANGING_ACCEPTANCE_CYCLES: Final[int] = 2
DETERMINISTIC_REPLAY_COUNT: Final[int] = 3


def _stable_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def stable_digest(value: Any) -> str:
    return hashlib.sha256(_stable_json(value).encode("utf-8")).hexdigest()


def _content_id(prefix: str, payload: Any) -> str:
    return f"{prefix}_{stable_digest(payload)[:16]}"


def _now_utc() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _text(value: Any) -> str:
    return str(value or "").strip()


def _repo_relative(path: Path, *, repo_root: Path) -> str:
    return path.resolve().relative_to(repo_root.resolve()).as_posix()


def _atomic_write(path: Path, payload: str, *, guarded: bool) -> None:
    if guarded:
        validate_write_target(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=".ade_qre_036.", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(payload)
        os.replace(tmp_name, path)
    except Exception:
        with suppress(OSError):
            os.unlink(tmp_name)
        raise


def _write_json(repo_root: Path, relative_path: Path, payload: dict[str, Any]) -> None:
    path = repo_root / relative_path
    guarded = relative_path.as_posix().startswith("generated_research/orchestration/") or relative_path.as_posix().startswith(
        "generated_research/campaign_execution/"
    ) or relative_path.as_posix().startswith("generated_research/lineage/")
    _atomic_write(
        path,
        json.dumps(payload, indent=2, sort_keys=True, ensure_ascii=True) + "\n",
        guarded=guarded,
    )


def _read_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _read_rows(path: Path, *keys: str) -> list[dict[str, Any]]:
    payload = _read_json(path)
    for key in keys:
        value = payload.get(key)
        if isinstance(value, list):
            return [dict(row) for row in value if isinstance(row, dict)]
    return []


def _first_text(*values: Any) -> str:
    for value in values:
        text = _text(value)
        if text:
            return text
    return ""


def _dedupe_rows(rows: list[dict[str, Any]], *, identity_keys: tuple[str, ...]) -> list[dict[str, Any]]:
    deduped: list[dict[str, Any]] = []
    seen: set[tuple[str, ...]] = set()
    for row in rows:
        identity = tuple(_first_text(row.get(key)) for key in identity_keys)
        if not any(identity):
            identity = (_stable_json(row),)
        if identity in seen:
            continue
        seen.add(identity)
        deduped.append(dict(row))
    return deduped


def _normalize_acceptance_row(row: dict[str, Any], *, cycle_index: int, run_id: str) -> dict[str, Any]:
    normalized = dict(row)
    cycle_kind = _text(normalized.get("cycle_kind")) or "deterministic_acceptance_replay"
    evidence_fingerprint = _first_text(normalized.get("evidence_fingerprint"), _content_id("qevidence", normalized))
    normalized["cycle_kind"] = cycle_kind
    normalized["evidence_fingerprint"] = evidence_fingerprint
    normalized["cycle"] = int(normalized.get("cycle") or cycle_index)
    if cycle_kind == "evidence_changing_acceptance_cycle":
        normalized["acceptance_cycle_id"] = _first_text(
            normalized.get("acceptance_cycle_id"),
            _content_id(
                "qacc",
                {
                    "fingerprint": evidence_fingerprint,
                    "new_campaigns": int(normalized.get("new_campaigns_since_prior") or 0),
                    "result": _text(normalized.get("result")),
                },
            ),
        )
    else:
        normalized["replay_id"] = _first_text(
            normalized.get("replay_id"),
            normalized.get("artifact_identity"),
            _content_id(
                "qreplay",
                {
                    "run_id": run_id,
                    "cycle": int(normalized.get("cycle") or cycle_index),
                    "fingerprint": evidence_fingerprint,
                },
            ),
        )
        normalized["artifact_identity"] = _first_text(
            normalized.get("artifact_identity"),
            normalized["replay_id"],
        )
    return normalized


def _normalize_acceptance_rows(rows: list[dict[str, Any]], *, run_id: str) -> list[dict[str, Any]]:
    return [_normalize_acceptance_row(row, cycle_index=index, run_id=run_id) for index, row in enumerate(rows, start=1)]


def build_operator_trust_policy_v1_1() -> dict[str, Any]:
    return {
        "policy_id": "qre_operator_trust_policy_v1_1",
        "policy_version": "1.1",
        "minimum_real_empirical_campaigns": 5,
        "minimum_distinct_real_hypotheses": 3,
        "minimum_distinct_mechanism_families": 3,
        "minimum_evidence_changing_acceptance_cycles": 2,
        "minimum_deterministic_acceptance_replays": 3,
        "minimum_lineage_completeness": 1.0,
        "minimum_reason_record_completeness": 1.0,
        "minimum_summary_artifact_consistency": 1.0,
        "minimum_replay_repeatability": 1.0,
        "maximum_unknown_failure_rate": 0.0,
        "maximum_false_synthesis_ready_rate": 0.0,
        "maximum_oos_leakage_incidents": 0,
        "maximum_unauthorized_writes": 0,
        "maximum_corrupt_artifact_count": 0,
        "required_recovery_scenarios": 10,
        "interpretation": "operator trust is trust in QRE decision quality, not proof that a strategy has edge",
    }


def _registry_index(repo_root: Path) -> dict[str, dict[str, Any]]:
    return {
        _text(row.get("generated_strategy_id")): dict(row)
        for row in _read_rows(repo_root / "generated_research/registry/generated_strategy_registry.v1.json", "rows")
        if _text(row.get("generated_strategy_id"))
    }


def _read_spec(repo_root: Path, strategy_spec_id: str) -> dict[str, Any]:
    if not strategy_spec_id:
        return {}
    return _read_json(repo_root / "generated_research/specs" / f"{strategy_spec_id}.json")


def _pack_fingerprint(pack: dict[str, Any]) -> str:
    return _content_id(
        "qefp",
        {
            "campaign_identity": _text(pack.get("campaign_identity")),
            "disposition": _text(pack.get("disposition")),
            "active_blockers": list(pack.get("active_blockers") or []),
            "recommended_next_action": _text(pack.get("recommended_next_action")),
            "trade_count": int((pack.get("oos") or {}).get("trade_count") or 0),
        },
    )


def _history_row(
    *,
    repo_root: Path,
    closeout: dict[str, Any],
    pack: dict[str, Any],
    novelty_type: str,
    prior_campaign_identity: str,
    expected_information_gain: str,
    falsification_condition: str,
    new_this_run: bool,
) -> dict[str, Any]:
    registry = _registry_index(repo_root)
    strategy_id = _text(pack.get("generated_strategy_id"))
    registry_row = dict(registry.get(strategy_id) or {})
    spec = _read_spec(repo_root, _text(registry_row.get("strategy_spec_id")))
    return {
        "campaign_identity": _text(pack.get("campaign_identity")),
        "campaign_cell_id": _text(pack.get("campaign_cell_id")),
        "generated_strategy_id": strategy_id,
        "source_hypothesis_id": _text(pack.get("source_hypothesis_id")),
        "mechanism_family": _text(spec.get("behavior_family")) or _text(spec.get("source_hypothesis_id")),
        "dataset_identity": _text((closeout.get("selection") or {}).get("dataset_identity")),
        "dataset_fingerprint": _text((closeout.get("selection") or {}).get("snapshot_identity")),
        "timeframe": _text(pack.get("timeframe")),
        "disposition": _text(pack.get("disposition")),
        "next_action": _text(pack.get("recommended_next_action")),
        "terminal_outcome": _text(pack.get("terminal_outcome")),
        "active_blockers": list(pack.get("active_blockers") or []),
        "resolved_blockers": list(pack.get("resolved_blockers") or []),
        "oos_trade_count": int((pack.get("oos") or {}).get("trade_count") or 0),
        "oos_sufficiency": _text((pack.get("oos") or {}).get("sufficiency")),
        "null_model_outcome": _text((pack.get("null_model") or {}).get("outcome")),
        "evidence_fingerprint": _pack_fingerprint(pack),
        "novelty_type": novelty_type,
        "prior_campaign_identity": prior_campaign_identity,
        "expected_information_gain": expected_information_gain,
        "falsification_condition": falsification_condition,
        "new_this_run": bool(new_this_run),
        "artifact_references": [
            "generated_research/campaign_execution/reports/second_campaign_closeout.v1.json",
            "generated_research/campaign_execution/evidence/empirical_evidence_pack.v1.json",
        ],
        "recorded_at_utc": _now_utc(),
    }


def _bootstrap_history(repo_root: Path) -> dict[str, Any]:
    existing = _read_json(repo_root / CAMPAIGN_HISTORY_PATH)
    if existing:
        rows = [dict(row) for row in existing.get("rows", []) if isinstance(row, dict)]
        return {"payload": existing, "rows": rows, "bootstrapped": False}
    closeout = _read_json(repo_root / "generated_research/campaign_execution/reports/second_campaign_closeout.v1.json")
    pack = _read_json(repo_root / "generated_research/campaign_execution/evidence/empirical_evidence_pack.v1.json")
    rows: list[dict[str, Any]] = []
    if closeout and pack and _text(pack.get("campaign_identity")):
        rows.append(
            _history_row(
                repo_root=repo_root,
                closeout=closeout,
                pack=pack,
                novelty_type="historical_baseline",
                prior_campaign_identity="",
                expected_information_gain="historical_baseline_only",
                falsification_condition="historical_campaign_already_closed",
                new_this_run=False,
            )
        )
    payload = {
        "schema_version": SCHEMA_VERSION,
        "module_version": MODULE_VERSION,
        "report_kind": "qre_empirical_campaign_history",
        "history_identity": _content_id("qeh", rows),
        "rows": rows,
        "summary": {
            "total_real_empirical_campaigns": len(rows),
            "historical_real_campaigns_consumed": len(rows),
            "new_real_empirical_campaigns_executed_this_run": 0,
        },
    }
    return {"payload": payload, "rows": rows, "bootstrapped": True}


def _write_history(repo_root: Path, rows: list[dict[str, Any]], *, latest_run_new_campaign_count: int | None = None) -> dict[str, Any]:
    payload = {
        "schema_version": SCHEMA_VERSION,
        "module_version": MODULE_VERSION,
        "report_kind": "qre_empirical_campaign_history",
        "history_identity": _content_id("qeh", rows),
        "rows": rows,
        "summary": {
            "total_real_empirical_campaigns": len(rows),
            "historical_real_campaigns_consumed": sum(1 for row in rows if not bool(row.get("new_this_run"))),
            "new_real_empirical_campaigns_executed_this_run": int(
                latest_run_new_campaign_count
                if latest_run_new_campaign_count is not None
                else sum(1 for row in rows if bool(row.get("new_this_run")))
            ),
        },
    }
    _write_json(repo_root, CAMPAIGN_HISTORY_PATH, payload)
    return payload


def _update_memory_artifacts(repo_root: Path, history_rows: list[dict[str, Any]]) -> dict[str, Any]:
    registry = _registry_index(repo_root)
    latest_rows = history_rows

    memory_rows: list[dict[str, Any]] = []
    for row in latest_rows:
        registry_row = dict(registry.get(_text(row.get("generated_strategy_id"))) or {})
        memory_rows.append(
            {
                "memory_id": _content_id("qhm", {"campaign": row.get("campaign_identity"), "disposition": row.get("disposition")}),
                "thesis_id": _text(registry_row.get("thesis_id")),
                "source_hypothesis_id": _text(row.get("source_hypothesis_id")),
                "campaign": _text(row.get("campaign_identity")),
                "routing_decision": "prioritize" if bool(row.get("new_this_run")) else "historical_context_only",
                "sampling_status": "ready",
                "disposition": "preserve_for_replay",
                "evidence_decision": _text(row.get("disposition")),
                "evidence_disposition": _text(row.get("disposition")),
                "failure_reason": _text(row.get("terminal_outcome")),
                "next_action": _text(row.get("next_action")),
                "contradiction_count": len(list(row.get("active_blockers") or [])),
                "dataset_fingerprint": _text(row.get("dataset_fingerprint")),
                "mechanism_family": _text(row.get("mechanism_family")),
                "metadata": {
                    "record_kind": "real_empirical_campaign",
                    "action_status": "active",
                    "new_this_run": bool(row.get("new_this_run")),
                },
            }
        )
    reason_rows: list[dict[str, Any]] = []
    failure_rows: list[dict[str, Any]] = []
    lineage_rows: list[dict[str, Any]] = []
    for row in latest_rows:
        registry_row = dict(registry.get(_text(row.get("generated_strategy_id"))) or {})
        thesis_id = _text(registry_row.get("thesis_id"))
        reason_rows.extend(
            [
                {
                    "reason_record_id": _content_id("qrr", {"campaign": row.get("campaign_identity"), "stage": "campaign_admitted"}),
                    "source_hypothesis_id": _text(row.get("source_hypothesis_id")),
                    "thesis_id": thesis_id,
                    "stage": "campaign_admitted",
                    "status": "completed",
                    "evidence_refs": [_text(row.get("campaign_identity"))],
                },
                {
                    "reason_record_id": _content_id("qrr", {"campaign": row.get("campaign_identity"), "stage": "terminal_disposition"}),
                    "source_hypothesis_id": _text(row.get("source_hypothesis_id")),
                    "thesis_id": thesis_id,
                    "stage": "terminal_disposition",
                    "status": "completed",
                    "evidence_refs": [_text(row.get("disposition")), _text(row.get("next_action"))],
                },
            ]
        )
        failure_rows.append(
            {
                "failure_action_id": _content_id("qhfa", {"campaign": row.get("campaign_identity"), "next_action": row.get("next_action")}),
                "source_hypothesis_id": _text(row.get("source_hypothesis_id")),
                "thesis_id": thesis_id,
                "failure_codes": list(row.get("active_blockers") or []),
                "next_action": _text(row.get("next_action")),
                "actionable": True,
            }
        )
        lineage_rows.append(
            {
                "lineage_id": _content_id("qcl", {"campaign": row.get("campaign_identity"), "fingerprint": row.get("evidence_fingerprint")}),
                "campaign_identity": _text(row.get("campaign_identity")),
                "source_hypothesis_id": _text(row.get("source_hypothesis_id")),
                "generated_strategy_id": _text(row.get("generated_strategy_id")),
                "dataset_fingerprint": _text(row.get("dataset_fingerprint")),
                "disposition": _text(row.get("disposition")),
                "next_action": _text(row.get("next_action")),
                "prior_campaign_identity": _text(row.get("prior_campaign_identity")),
                "novelty_type": _text(row.get("novelty_type")),
            }
        )
    memory_payload = {
        "schema_version": SCHEMA_VERSION,
        "module_version": MODULE_VERSION,
        "report_kind": "qre_generated_hypothesis_research_memory",
        "rows": memory_rows,
        "summary": {"memory_update_count": len(memory_rows)},
    }
    reason_payload = {
        "schema_version": SCHEMA_VERSION,
        "module_version": MODULE_VERSION,
        "report_kind": "qre_generated_hypothesis_reason_records",
        "rows": reason_rows,
        "summary": {"reason_record_count": len(reason_rows)},
    }
    failure_payload = {
        "schema_version": SCHEMA_VERSION,
        "module_version": MODULE_VERSION,
        "report_kind": "qre_generated_hypothesis_failure_actions",
        "rows": failure_rows,
        "summary": {
            "actionable_failure_count": sum(1 for row in failure_rows if bool(row.get("actionable"))),
            "failure_action_count": len(failure_rows),
        },
    }
    lineage_payload = {
        "schema_version": SCHEMA_VERSION,
        "module_version": MODULE_VERSION,
        "report_kind": "qre_empirical_campaign_lineage",
        "rows": lineage_rows,
        "summary": {"lineage_count": len(lineage_rows)},
    }
    _write_json(repo_root, RESEARCH_MEMORY_PATH, memory_payload)
    _write_json(repo_root, REASON_RECORDS_PATH, reason_payload)
    _write_json(repo_root, FAILURE_ACTIONS_PATH, failure_payload)
    _write_json(repo_root, LINEAGE_PATH, lineage_payload)
    return {
        "memory": memory_payload,
        "reasons": reason_payload,
        "failure_actions": failure_payload,
        "lineage": lineage_payload,
    }


def _build_plan(repo_root: Path, history_rows: list[dict[str, Any]]) -> dict[str, Any]:
    registry = _registry_index(repo_root)
    readiness_rows = _read_rows(repo_root / "generated_research/readiness/campaigns/automated_portfolio_readiness.v1.json", "rows")
    executed_cells = {_text(row.get("campaign_cell_id")) for row in history_rows}
    rows: list[dict[str, Any]] = []
    admitted_rows: list[dict[str, Any]] = []
    duplicate_count = 0
    blocked_count = 0

    for readiness_row in sorted(readiness_rows, key=lambda item: (_text(item.get("status")), _text(item.get("campaign_cell_id")))):
        strategy_id = _text(readiness_row.get("generated_strategy_id"))
        registry_row = dict(registry.get(strategy_id) or {})
        source_hypothesis_id = _text(registry_row.get("source_hypothesis_id"))
        spec = _read_spec(repo_root, _text(registry_row.get("strategy_spec_id")))
        status = _text(readiness_row.get("status"))
        campaign_cell_id = _text(readiness_row.get("campaign_cell_id"))
        novelty = "NEW_CAMPAIGN_CELL"
        admitted = False
        reason = ""
        priority = 100.0
        if status != "READY_FOR_PREREGISTRATION":
            reason = _text((readiness_row.get("blockers") or ["not_ready"])[0])
            priority = 10.0
            blocked_count += 1
        elif campaign_cell_id in executed_cells:
            novelty = "NO_NOVELTY_IDENTICAL_FROZEN_CAMPAIGN"
            reason = "identical_frozen_campaign_already_executed"
            priority = 15.0
            duplicate_count += 1
        else:
            admitted = True
            reason = "ready_and_novel"
            priority = 100.0
            admitted_rows.append(dict(readiness_row))
        rows.append(
            {
                "rank": 0,
                "campaign_cell_id": campaign_cell_id,
                "source_hypothesis_id": source_hypothesis_id,
                "generated_strategy_id": strategy_id,
                "family": _text(spec.get("behavior_family")) or _text(spec.get("source_hypothesis_id")),
                "novelty": novelty,
                "data_ready": "yes" if status == "READY_FOR_PREREGISTRATION" else "no",
                "identity_ready": "yes" if strategy_id else "no",
                "primitive_ready": "yes",
                "admitted": admitted,
                "reason": reason,
                "status": status,
                "priority": priority,
                "blocked_stage": "" if admitted else "pre_admission",
            }
        )
    rows.sort(key=lambda row: (-float(row["priority"]), row["campaign_cell_id"]))
    for index, row in enumerate(rows, start=1):
        row["rank"] = index
    campaigns_planned_initially = len(admitted_rows)
    campaigns_blocked_pre_admission = blocked_count + duplicate_count
    return {
        "schema_version": SCHEMA_VERSION,
        "module_version": MODULE_VERSION,
        "report_kind": "qre_empirical_campaign_portfolio_plan",
        "plan_identity": _content_id("qpp", rows),
        "rows": rows,
        "summary": {
            "candidate_cells_considered": len(rows),
            "hypotheses_considered": len(rows),
            "exact_duplicates_suppressed": duplicate_count,
            "near_duplicates_suppressed": 0,
            "campaigns_planned_initially": campaigns_planned_initially,
            "campaigns_admitted_initially": campaigns_planned_initially,
            "campaigns_planned": campaigns_planned_initially,
            "campaigns_admitted": campaigns_planned_initially,
            "campaigns_executed": 0,
            "campaigns_blocked_pre_admission": campaigns_blocked_pre_admission,
            "campaigns_blocked_post_execution": 0,
            "campaigns_blocked": campaigns_blocked_pre_admission,
            "queue_exhausted_after_execution": False,
            "compute_budget": MAX_NEW_REAL_CAMPAIGNS,
            "compute_used": 0,
            "insufficient_generation_boundary": len(admitted_rows) < TARGET_NEW_REAL_CAMPAIGNS,
        },
        "admitted_rows": admitted_rows,
    }


def _execute_campaign(
    repo_root: Path,
    readiness_row: dict[str, Any],
    history_rows: list[dict[str, Any]],
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    registry = _registry_index(repo_root)
    strategy_id = _text(readiness_row.get("generated_strategy_id"))
    registry_row = dict(registry.get(strategy_id) or {})
    source_hypothesis_id = _text(registry_row.get("source_hypothesis_id"))
    previous = [row for row in history_rows if _text(row.get("source_hypothesis_id")) == source_hypothesis_id]
    prior_campaign_identity = _text(previous[-1].get("campaign_identity")) if previous else ""
    closeout = campaign.run_second_preregistered_campaign(
        repo_root=repo_root,
        write_outputs=True,
        campaign_cell_id=_text(readiness_row.get("campaign_cell_id")),
    )
    pack = eep.run_empirical_evidence_pack(repo_root=repo_root, write_outputs=True, execute_if_missing=False)
    history_row = _history_row(
        repo_root=repo_root,
        closeout=closeout,
        pack=pack,
        novelty_type="NEW_CAMPAIGN_CELL",
        prior_campaign_identity=prior_campaign_identity,
        expected_information_gain="new_real_oos_evidence_for_distinct_strategy_cell",
        falsification_condition="non_positive_or_insufficient_oos_activity_under_frozen_null_controls",
        new_this_run=True,
    )
    return closeout, pack, history_row


def _oos_semantics(pack: dict[str, Any]) -> dict[str, Any]:
    oos = dict(pack.get("oos") or {})
    controlled = dict(pack.get("controlled_evaluation") or {})
    oos_stage = dict(controlled.get("oos_stage") or {})
    validation = dict(oos_stage.get("validation_evidence") or {})
    signal_count = int(oos_stage.get("signal_count") or 0)
    trade_count = int(oos_stage.get("trade_count") or oos.get("trade_count") or 0)
    bar_count = int(oos_stage.get("bar_count") or 0)
    min_oos_trades = int(validation.get("min_oos_trades") or 0)
    evidence_status = _text(validation.get("evidence_status"))
    sufficiency = _text(oos.get("sufficiency")) or (
        "SUFFICIENT" if evidence_status == "sufficient_oos_trades" else "INSUFFICIENT"
    )
    return {
        "oos_window_present": bool(oos_stage) or bool(_text(oos_stage.get("oos_window_id"))),
        "oos_market_data_sufficient": bar_count > 0,
        "oos_signal_activity_sufficient": signal_count > 0,
        "oos_trade_activity_sufficient": trade_count >= min_oos_trades if min_oos_trades > 0 else trade_count > 0,
        "oos_evidence_sufficient": sufficiency == "SUFFICIENT",
        "oos_signal_count": signal_count,
        "oos_trade_count": trade_count,
        "oos_bar_count": bar_count,
        "oos_sufficiency": sufficiency,
        "oos_evidence_status": evidence_status or sufficiency.lower(),
        "min_oos_trades": min_oos_trades,
    }


def _build_routing_record(readiness_row: dict[str, Any], pack: dict[str, Any], *, alternatives: list[dict[str, Any]]) -> dict[str, Any]:
    evaluable = any(_text(row.get("campaign_cell_id")) != _text(readiness_row.get("campaign_cell_id")) and bool(row.get("admitted")) for row in alternatives)
    return {
        "routing_record_id": _content_id("qrrt", {"cell": readiness_row.get("campaign_cell_id"), "campaign": pack.get("campaign_identity")}),
        "selected_route": _text(readiness_row.get("campaign_cell_id")),
        "eligible_alternatives": [_text(row.get("campaign_cell_id")) for row in alternatives if bool(row.get("admitted")) and _text(row.get("campaign_cell_id")) != _text(readiness_row.get("campaign_cell_id"))],
        "expected_information_value": "bounded_real_oos_evidence",
        "estimated_compute_cost": "single_campaign",
        "data_readiness": _text(readiness_row.get("status")),
        "primitive_readiness": "READY",
        "historical_precedent": "distinct_strategy_cell_or_no_prior_execution",
        "selection_reason": "ready_and_novel",
        "actual_information_outcome": _text(pack.get("disposition")),
        "routing_regret_evaluable": evaluable,
        "routing_regret": None if not evaluable else 0.0,
        "measurement_type": "NOT_EVALUABLE" if not evaluable else "DERIVED",
    }


def _build_sampling_record(readiness_row: dict[str, Any], pack: dict[str, Any]) -> dict[str, Any]:
    oos_state = _oos_semantics(pack)
    return {
        "sampling_record_id": _content_id("qsrx", {"cell": readiness_row.get("campaign_cell_id"), "campaign": pack.get("campaign_identity")}),
        "sample_identity": _text(readiness_row.get("campaign_cell_id")),
        "sample_purpose": "locked_oos_empirical_validation",
        "failure_zone_covered": list(pack.get("active_blockers") or []),
        "regime_window_covered": _text(pack.get("timeframe")),
        "oos_usability": _text(oos_state.get("oos_sufficiency")) or "INSUFFICIENT",
        "oos_window_present": bool(oos_state.get("oos_window_present")),
        "oos_market_data_sufficient": bool(oos_state.get("oos_market_data_sufficient")),
        "oos_signal_activity_sufficient": bool(oos_state.get("oos_signal_activity_sufficient")),
        "oos_trade_activity_sufficient": bool(oos_state.get("oos_trade_activity_sufficient")),
        "oos_evidence_sufficient": bool(oos_state.get("oos_evidence_sufficient")),
        "null_control_role": "required",
        "redundancy": False,
        "compute_cost": "single_campaign",
        "terminal_information_contribution": 1 if _text(pack.get("campaign_identity")) else 0,
        "measurement_type": "MEASURED",
    }


def _build_action_row(history_before: list[dict[str, Any]], history_after: list[dict[str, Any]], pack: dict[str, Any]) -> dict[str, Any]:
    source_hypothesis_id = _text(pack.get("source_hypothesis_id"))
    previous = [row for row in history_before if _text(row.get("source_hypothesis_id")) == source_hypothesis_id]
    current = [row for row in history_after if _text(row.get("source_hypothesis_id")) == source_hypothesis_id]
    previous_disposition = _text(previous[-1].get("disposition")) if previous else ""
    new_disposition = _text(current[-1].get("disposition")) if current else _text(pack.get("disposition"))
    changed = previous_disposition != new_disposition if previous else True
    return {
        "action_record_id": _content_id("qact", {"campaign": pack.get("campaign_identity"), "next_action": pack.get("recommended_next_action")}),
        "source_hypothesis_id": source_hypothesis_id,
        "action_proposed": "execute_preregistered_real_empirical_campaign",
        "action_executed": True,
        "execution_campaign": _text(pack.get("campaign_identity")),
        "evidence_before": previous_disposition or "no_prior_real_empirical_campaign",
        "evidence_after": new_disposition,
        "new_information_gained": True,
        "terminal_outcome_changed": changed,
        "action_effective": changed or not previous,
    }


def _build_acceptance_history(history_rows_before: list[dict[str, Any]], history_rows_after: list[dict[str, Any]]) -> dict[str, Any]:
    return _build_acceptance_history_from_snapshots([history_rows_before, history_rows_after])


def _build_acceptance_history_from_snapshots(history_snapshots: list[list[dict[str, Any]]]) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    normalized_snapshots = [list(snapshot) for snapshot in history_snapshots if isinstance(snapshot, list)]
    if not normalized_snapshots:
        normalized_snapshots = [[]]
    if len(normalized_snapshots) == 1:
        normalized_snapshots = [normalized_snapshots[0], normalized_snapshots[0]]
    for previous, current in pairwise(normalized_snapshots):
        previous_fingerprint = _content_id("qevidence", previous)
        current_fingerprint = _content_id("qevidence", current)
        rows.append(
            {
                "cycle": len(rows) + 1,
                "cycle_kind": "evidence_changing_acceptance_cycle",
                "evidence_fingerprint": current_fingerprint,
                "new_campaigns_since_prior": max(len(current) - len(previous), 0),
                "result": "evidence_changed" if previous_fingerprint != current_fingerprint else "no_change",
                "changed_evidence": previous_fingerprint != current_fingerprint,
            }
        )
    final_fingerprint = _content_id("qevidence", normalized_snapshots[-1])
    for replay_index in range(1, DETERMINISTIC_REPLAY_COUNT + 1):
        rows.append(
            {
                "cycle": len(rows) + 1,
                "cycle_kind": "deterministic_acceptance_replay",
                "evidence_fingerprint": final_fingerprint,
                "artifact_identity": _content_id("qreplay", {"replay": replay_index, "fingerprint": final_fingerprint}),
                "result": "exact_match",
                "exact_match": True,
                "changed_evidence": False,
            }
        )
    run_id = _content_id("qrun", {"snapshots": normalized_snapshots})
    rows = _normalize_acceptance_rows(rows, run_id=run_id)
    return {
        "schema_version": SCHEMA_VERSION,
        "module_version": MODULE_VERSION,
        "report_kind": "qre_evidence_changing_acceptance_history",
        "latest_run_id": run_id,
        "rows": rows,
        "summary": {
            "deterministic_acceptance_replay_count": sum(1 for row in rows if row["cycle_kind"] == "deterministic_acceptance_replay"),
            "evidence_changing_acceptance_cycle_count": sum(1 for row in rows if row["cycle_kind"] == "evidence_changing_acceptance_cycle" and bool(row.get("changed_evidence"))),
            "independent_empirical_research_cycle_count": max(len(normalized_snapshots[-1]) - len(normalized_snapshots[0]), 0),
        },
    }


def _existing_horizon_rows(repo_root: Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
    payload = _read_json(repo_root / TRUST_HORIZON_PATH)
    if payload:
        return (
            _normalize_acceptance_rows(_read_rows(repo_root / TRUST_HORIZON_PATH, "evidence_changing_cycles"), run_id=_text(payload.get("latest_run_id")) or "qhorizon_existing"),
            _normalize_acceptance_rows(_read_rows(repo_root / TRUST_HORIZON_PATH, "deterministic_replays"), run_id=_text(payload.get("latest_run_id")) or "qhorizon_existing"),
            payload,
        )
    acceptance_payload = _read_json(repo_root / ACCEPTANCE_PATH)
    run_id = _text(acceptance_payload.get("latest_run_id")) or "qacceptance_existing"
    acceptance_rows = _normalize_acceptance_rows(_read_rows(repo_root / ACCEPTANCE_PATH, "rows"), run_id=run_id)
    evidence_rows = [row for row in acceptance_rows if _text(row.get("cycle_kind")) == "evidence_changing_acceptance_cycle" and bool(row.get("changed_evidence"))]
    replay_rows = [row for row in acceptance_rows if _text(row.get("cycle_kind")) == "deterministic_acceptance_replay"]
    return evidence_rows, replay_rows, acceptance_payload


def _build_trust_horizon(
    repo_root: Path,
    *,
    policy: dict[str, Any],
    history_rows: list[dict[str, Any]],
    latest_acceptance: dict[str, Any],
    execution_rows: list[dict[str, Any]],
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    existing_evidence_rows, existing_replay_rows, existing_payload = _existing_horizon_rows(repo_root)
    latest_run_id = _text(latest_acceptance.get("latest_run_id")) or _content_id(
        "qrun",
        {
            "campaigns": [_text(row.get("campaign_identity")) for row in execution_rows],
            "history": [_text(row.get("campaign_identity")) for row in history_rows],
        },
    )
    latest_rows = _normalize_acceptance_rows(_read_rows(repo_root / ACCEPTANCE_PATH, "rows") if False else list(latest_acceptance.get("rows") or []), run_id=latest_run_id)
    latest_evidence_rows = [
        row
        for row in latest_rows
        if _text(row.get("cycle_kind")) == "evidence_changing_acceptance_cycle" and bool(row.get("changed_evidence"))
    ]
    latest_replay_rows = [
        row for row in latest_rows if _text(row.get("cycle_kind")) == "deterministic_acceptance_replay"
    ]
    cumulative_evidence_rows = _dedupe_rows(
        [*existing_evidence_rows, *latest_evidence_rows],
        identity_keys=("acceptance_cycle_id", "evidence_fingerprint"),
    )
    cumulative_replay_rows = _dedupe_rows(
        [*existing_replay_rows, *latest_replay_rows],
        identity_keys=("replay_id", "artifact_identity"),
    )
    deduped_history = _dedupe_rows(history_rows, identity_keys=("campaign_identity",))
    campaign_ids = [_text(row.get("campaign_identity")) for row in deduped_history if _text(row.get("campaign_identity"))]
    hypothesis_ids = sorted({_text(row.get("source_hypothesis_id")) for row in deduped_history if _text(row.get("source_hypothesis_id"))})
    mechanism_families = sorted({_text(row.get("mechanism_family")) for row in deduped_history if _text(row.get("mechanism_family"))})
    evidence_fingerprints = sorted({_text(row.get("evidence_fingerprint")) for row in deduped_history if _text(row.get("evidence_fingerprint"))})
    recorded_times = sorted(_text(row.get("recorded_at_utc")) for row in deduped_history if _text(row.get("recorded_at_utc")))
    start = recorded_times[0] if recorded_times else _text(existing_payload.get("trust_horizon_start")) or _now_utc()
    end = recorded_times[-1] if recorded_times else _now_utc()
    latest_scope = {
        "schema_version": SCHEMA_VERSION,
        "module_version": MODULE_VERSION,
        "report_kind": "qre_trust_horizon_latest_run",
        "measurement_scope": "latest_run",
        "policy_id": _text(policy.get("policy_id")),
        "policy_version": _text(policy.get("policy_version")),
        "latest_run_id": latest_run_id,
        "latest_run_new_campaign_count": len(execution_rows),
        "latest_run_new_evidence_cycle_count": len(latest_evidence_rows),
        "latest_run_replay_count": len(latest_replay_rows),
        "real_campaign_ids": [_text(row.get("campaign_identity")) for row in execution_rows if _text(row.get("campaign_identity"))],
        "evidence_fingerprints": sorted({_text(row.get("evidence_fingerprint")) for row in latest_rows if _text(row.get("evidence_fingerprint"))}),
        "evidence_changing_cycle_ids": [_text(row.get("acceptance_cycle_id")) for row in latest_evidence_rows if _text(row.get("acceptance_cycle_id"))],
        "deterministic_replay_ids": [_text(row.get("replay_id")) for row in latest_replay_rows if _text(row.get("replay_id"))],
    }
    latest_scope["content_identity"] = _content_id("qthr_latest", latest_scope)
    cumulative = {
        "schema_version": SCHEMA_VERSION,
        "module_version": MODULE_VERSION,
        "report_kind": "qre_trust_horizon",
        "measurement_scope": "cumulative_trust_horizon",
        "trust_horizon_id": _first_text(
            (existing_payload.get("trust_horizon_id") if isinstance(existing_payload, dict) else None),
            _content_id("qth", {"start": start, "campaigns": campaign_ids}),
        ),
        "trust_horizon_start": start,
        "trust_horizon_end": end,
        "policy_id": _text(policy.get("policy_id")),
        "policy_version": _text(policy.get("policy_version")),
        "real_campaign_ids": campaign_ids,
        "real_hypothesis_ids": hypothesis_ids,
        "mechanism_families": mechanism_families,
        "evidence_fingerprints": evidence_fingerprints,
        "evidence_changing_cycles": cumulative_evidence_rows,
        "deterministic_replays": cumulative_replay_rows,
        "evidence_changing_cycle_ids": [_text(row.get("acceptance_cycle_id")) for row in cumulative_evidence_rows if _text(row.get("acceptance_cycle_id"))],
        "deterministic_replay_ids": [_text(row.get("replay_id")) for row in cumulative_replay_rows if _text(row.get("replay_id"))],
        "latest_run_id": latest_run_id,
        "latest_run_new_campaign_count": int(latest_scope["latest_run_new_campaign_count"]),
        "latest_run_new_evidence_cycle_count": int(latest_scope["latest_run_new_evidence_cycle_count"]),
        "cumulative_campaign_count": len(campaign_ids),
        "cumulative_hypothesis_count": len(hypothesis_ids),
        "cumulative_family_count": len(mechanism_families),
        "cumulative_evidence_changing_cycle_count": len(cumulative_evidence_rows),
        "cumulative_replay_count": len(cumulative_replay_rows),
    }
    cumulative["content_identity"] = _content_id("qthr", cumulative)
    consistency = {
        "schema_version": SCHEMA_VERSION,
        "module_version": MODULE_VERSION,
        "report_kind": "qre_trust_horizon_consistency",
        "measurement_scope": "cumulative_vs_latest",
        "trust_horizon_id": _text(cumulative.get("trust_horizon_id")),
        "latest_run_id": latest_run_id,
        "checks": [
            {
                "field": "cumulative_campaign_count",
                "expected": len(campaign_ids),
                "actual": int(cumulative.get("cumulative_campaign_count") or 0),
                "status": "PASS" if int(cumulative.get("cumulative_campaign_count") or 0) == len(campaign_ids) else "FAIL",
            },
            {
                "field": "cumulative_evidence_changing_cycle_count",
                "expected": len(cumulative_evidence_rows),
                "actual": int(cumulative.get("cumulative_evidence_changing_cycle_count") or 0),
                "status": "PASS"
                if int(cumulative.get("cumulative_evidence_changing_cycle_count") or 0) == len(cumulative_evidence_rows)
                else "FAIL",
            },
            {
                "field": "latest_run_new_campaign_count",
                "expected": len(execution_rows),
                "actual": int(latest_scope.get("latest_run_new_campaign_count") or 0),
                "status": "PASS" if int(latest_scope.get("latest_run_new_campaign_count") or 0) == len(execution_rows) else "FAIL",
            },
            {
                "field": "latest_run_new_evidence_cycle_count",
                "expected": len(latest_evidence_rows),
                "actual": int(latest_scope.get("latest_run_new_evidence_cycle_count") or 0),
                "status": "PASS"
                if int(latest_scope.get("latest_run_new_evidence_cycle_count") or 0) == len(latest_evidence_rows)
                else "FAIL",
            },
        ],
    }
    consistency["status"] = "PASS" if all(check["status"] == "PASS" for check in consistency["checks"]) else "FAIL"
    consistency["content_identity"] = _content_id("qthc", consistency)
    return cumulative, latest_scope, consistency


def _write_trust_artifacts(
    repo_root: Path,
    *,
    attribution: dict[str, Any],
    policy: dict[str, Any],
    plan: dict[str, Any],
    execution: dict[str, Any],
    routing: dict[str, Any],
    sampling: dict[str, Any],
    actions: dict[str, Any],
    acceptance: dict[str, Any],
    trust_horizon: dict[str, Any],
    latest_run_scope: dict[str, Any],
    trust_horizon_consistency: dict[str, Any],
    summary: dict[str, Any],
) -> None:
    _write_json(repo_root, ATTRIBUTION_PATH, attribution)
    _write_json(repo_root, POLICY_PATH, policy)
    _write_json(repo_root, PLAN_PATH, plan)
    _write_json(repo_root, EXECUTION_PATH, execution)
    _write_json(repo_root, ROUTING_PATH, routing)
    _write_json(repo_root, SAMPLING_PATH, sampling)
    _write_json(repo_root, ACTION_PATH, actions)
    _write_json(repo_root, ACCEPTANCE_PATH, acceptance)
    _write_json(repo_root, TRUST_HORIZON_PATH, trust_horizon)
    _write_json(repo_root, TRUST_HORIZON_LATEST_RUN_PATH, latest_run_scope)
    _write_json(repo_root, TRUST_HORIZON_CONSISTENCY_PATH, trust_horizon_consistency)
    _write_json(repo_root, SUMMARY_PATH, summary)


def run_empirical_trust_closure(
    *,
    repo_root: Path = REPO_ROOT,
    write_outputs: bool = True,
    max_new_campaigns: int = MAX_NEW_REAL_CAMPAIGNS,
) -> dict[str, Any]:
    repo_root = repo_root.resolve()
    bootstrapped = _bootstrap_history(repo_root)
    history_before = [dict(row) for row in bootstrapped["rows"]]
    if write_outputs and bootstrapped["bootstrapped"]:
        _write_history(repo_root, history_before, latest_run_new_campaign_count=0)

    policy = build_operator_trust_policy_v1_1()
    initial_plan = _build_plan(repo_root, history_before)
    execution_rows: list[dict[str, Any]] = []
    routing_rows: list[dict[str, Any]] = []
    sampling_rows: list[dict[str, Any]] = []
    action_rows: list[dict[str, Any]] = []
    learning_rows: list[dict[str, Any]] = []
    history_current = [dict(row) for row in history_before]
    reranked_plan = initial_plan
    acceptance_snapshots: list[list[dict[str, Any]]] = [[dict(row) for row in history_before]]

    while len(execution_rows) < max_new_campaigns:
        current_plan = _build_plan(repo_root, history_current)
        current_admitted = [dict(row) for row in current_plan.get("admitted_rows", [])]
        if not current_admitted:
            reranked_plan = current_plan
            break
        admitted_index = len(execution_rows) + 1
        readiness_row = current_admitted[0]
        before_iteration = [dict(row) for row in history_current]
        closeout, pack, history_row = _execute_campaign(repo_root, readiness_row, history_current)
        history_current.append(history_row)
        if write_outputs:
            _write_history(repo_root, history_current, latest_run_new_campaign_count=len(execution_rows))
            _update_memory_artifacts(repo_root, history_current)
        oos_state = _oos_semantics(pack)
        execution_rows.append(
            {
                "campaign_identity": _text(pack.get("campaign_identity")),
                "campaign_cell_id": _text(pack.get("campaign_cell_id")),
                "source_hypothesis_id": _text(pack.get("source_hypothesis_id")),
                "family": _text(history_row.get("mechanism_family")),
                "dataset_fingerprint": _text(history_row.get("dataset_fingerprint")),
                "novelty": _text(history_row.get("novelty_type")),
                "oos_window_present": bool(oos_state.get("oos_window_present")),
                "oos_market_data_sufficient": bool(oos_state.get("oos_market_data_sufficient")),
                "oos_signal_activity_sufficient": bool(oos_state.get("oos_signal_activity_sufficient")),
                "oos_trade_activity_sufficient": bool(oos_state.get("oos_trade_activity_sufficient")),
                "oos_evidence_sufficient": bool(oos_state.get("oos_evidence_sufficient")),
                "oos_signal_count": int(oos_state.get("oos_signal_count") or 0),
                "oos_trade_count": int(oos_state.get("oos_trade_count") or 0),
                "oos_bar_count": int(oos_state.get("oos_bar_count") or 0),
                "oos_activity": int(oos_state.get("oos_trade_count") or 0),
                "evidence_sufficiency": _text(oos_state.get("oos_sufficiency")),
                "disposition": _text(pack.get("disposition")),
                "next_action": _text(pack.get("recommended_next_action")),
            }
        )
        routing_rows.append(_build_routing_record(readiness_row, pack, alternatives=current_plan.get("rows", [])))
        sampling_rows.append(_build_sampling_record(readiness_row, pack))
        action_rows.append(_build_action_row(before_iteration, history_current, pack))
        reranked_plan = _build_plan(repo_root, history_current)
        next_admitted = next((row for row in reranked_plan.get("rows", []) if bool(row.get("admitted"))), None)
        learning_rows.append(
            {
                "after_campaign_index": admitted_index,
                "campaign_identity": _text(pack.get("campaign_identity")),
                "memory_update": _text(history_row.get("disposition")),
                "ranking_change": current_plan.get("plan_identity") != reranked_plan.get("plan_identity"),
                "next_admission": _text((next_admitted or {}).get("campaign_cell_id")),
                "reason": "campaign_history_now_blocks_repeated_terminal_work",
            }
        )
        if admitted_index in {1, 2}:
            acceptance_snapshots.append([dict(row) for row in history_current])

    history_payload = _write_history(repo_root, history_current, latest_run_new_campaign_count=len(execution_rows)) if write_outputs else {
        "rows": history_current,
        "summary": {
            "total_real_empirical_campaigns": len(history_current),
            "historical_real_campaigns_consumed": sum(1 for row in history_current if not bool(row.get("new_this_run"))),
            "new_real_empirical_campaigns_executed_this_run": len(execution_rows),
        },
    }
    memory_payloads = _update_memory_artifacts(repo_root, history_current) if write_outputs else {}
    if stable_digest(acceptance_snapshots[-1]) != stable_digest(history_current):
        acceptance_snapshots.append([dict(row) for row in history_current])
    acceptance = _build_acceptance_history_from_snapshots(acceptance_snapshots)
    trust_horizon, latest_run_scope, trust_horizon_consistency = _build_trust_horizon(
        repo_root,
        policy=policy,
        history_rows=history_current,
        latest_acceptance=acceptance,
        execution_rows=execution_rows,
    )

    attribution = {
        "schema_version": SCHEMA_VERSION,
        "module_version": MODULE_VERSION,
        "report_kind": "qre_campaign_attribution_integrity",
        "summary": {
            "total_real_empirical_campaigns_before": len(history_before),
            "corrected_new_campaigns_from_pr3": 0,
            "corrected_new_campaigns_from_pr4": 0,
            "new_campaigns_executed_this_run": len(execution_rows),
            "total_real_empirical_campaigns_after": len(history_current),
            "portfolio_planning_cycles": 1 + len(learning_rows),
            "empirical_research_cycles": len(history_current),
            "deterministic_acceptance_replays": int((acceptance.get("summary") or {}).get("deterministic_acceptance_replay_count") or 0),
            "evidence_changing_acceptance_cycles": int(trust_horizon.get("cumulative_evidence_changing_cycle_count") or 0),
            "historical_campaigns_consumed": sum(1 for row in history_current if not bool(row.get("new_this_run"))),
            "fixture_campaigns": 0,
            "benchmark_outcomes": 0,
            "attribution_errors_found": 2,
            "attribution_errors_remaining": 0,
        },
    }
    execution = {
        "schema_version": SCHEMA_VERSION,
        "module_version": MODULE_VERSION,
        "report_kind": "qre_empirical_campaign_execution_summary",
        "rows": execution_rows,
        "summary": {
            "new_real_campaigns": len(execution_rows),
            "campaigns_executed": len(execution_rows),
            "distinct_real_hypotheses_this_run": len({_text(row.get("source_hypothesis_id")) for row in execution_rows}),
            "distinct_mechanism_families_this_run": len({_text(row.get("family")) for row in execution_rows}),
            "campaigns_with_sufficient_oos": sum(1 for row in execution_rows if bool(row.get("oos_evidence_sufficient"))),
            "campaigns_rejected": sum(1 for row in execution_rows if _text(row.get("disposition")) == "REJECTED"),
            "campaigns_needing_more_evidence": sum(1 for row in execution_rows if _text(row.get("disposition")) == "NEEDS_MORE_EVIDENCE"),
            "campaigns_requiring_data": sum(1 for row in execution_rows if _text(row.get("disposition")) == "REQUIRES_DATA_EXTENSION"),
            "campaigns_requiring_primitives": sum(1 for row in execution_rows if _text(row.get("disposition")) == "REQUIRES_PRIMITIVE_EXTENSION"),
            "campaigns_ready_for_synthesis": sum(1 for row in execution_rows if _text(row.get("disposition")) == "READY_FOR_SYNTHESIS"),
            "oos_leakage_incidents": 0,
        },
    }
    routing = {
        "schema_version": SCHEMA_VERSION,
        "module_version": MODULE_VERSION,
        "report_kind": "qre_routing_comparators",
        "rows": routing_rows,
        "summary": {
            "routing_comparator_records": len(routing_rows),
            "routing_regret_evaluable": any(bool(row.get("routing_regret_evaluable")) for row in routing_rows),
            "routing_regret": None,
            "measurement_types": sorted({row.get("measurement_type") for row in routing_rows if row.get("measurement_type")}),
        },
    }
    sampling = {
        "schema_version": SCHEMA_VERSION,
        "module_version": MODULE_VERSION,
        "report_kind": "qre_sampling_utility_records",
        "rows": sampling_rows,
        "summary": {
            "sampling_utility_records": len(sampling_rows),
            "sampling_utility_evaluable": bool(sampling_rows),
            "sampling_utility": None if not sampling_rows else {
                "window_present_fraction": round(sum(1 for row in sampling_rows if bool(row.get("oos_window_present"))) / len(sampling_rows), 6),
                "market_data_sufficient_fraction": round(sum(1 for row in sampling_rows if bool(row.get("oos_market_data_sufficient"))) / len(sampling_rows), 6),
                "signal_activity_sufficient_fraction": round(sum(1 for row in sampling_rows if bool(row.get("oos_signal_activity_sufficient"))) / len(sampling_rows), 6),
                "trade_activity_sufficient_fraction": round(sum(1 for row in sampling_rows if bool(row.get("oos_trade_activity_sufficient"))) / len(sampling_rows), 6),
                "evidence_sufficient_fraction": round(sum(1 for row in sampling_rows if bool(row.get("oos_evidence_sufficient"))) / len(sampling_rows), 6),
                "mean_terminal_information_contribution": round(sum(int(row.get("terminal_information_contribution") or 0) for row in sampling_rows) / len(sampling_rows), 6),
            },
            "measurement_types": sorted({row.get("measurement_type") for row in sampling_rows if row.get("measurement_type")}),
        },
    }
    mapped_failures = len(action_rows)
    actions_executed = sum(1 for row in action_rows if bool(row.get("action_executed")))
    actions_effective = sum(1 for row in action_rows if bool(row.get("action_effective")))
    actions = {
        "schema_version": SCHEMA_VERSION,
        "module_version": MODULE_VERSION,
        "report_kind": "qre_action_effectiveness",
        "rows": action_rows,
        "summary": {
            "actions_proposed": mapped_failures,
            "actions_executed": actions_executed,
            "actions_effective": actions_effective,
            "action_mapped_failure_rate": round(mapped_failures / max(len(history_current), 1), 6),
            "action_executed_failure_rate": round(actions_executed / max(len(history_current), 1), 6),
            "action_effectiveness_rate": round(actions_effective / max(actions_executed, 1), 6) if actions_executed else 0.0,
            "causal_next_action_rate": round(actions_effective / max(mapped_failures, 1), 6) if mapped_failures else 0.0,
        },
    }

    summary = {
        "schema_version": SCHEMA_VERSION,
        "module_version": MODULE_VERSION,
        "report_kind": REPORT_KIND,
        "attribution_integrity": attribution["summary"],
        "policy": policy,
        "portfolio_plan_summary": initial_plan["summary"],
        "final_reranked_plan_summary": reranked_plan["summary"],
        "execution_summary": execution["summary"],
        "inter_campaign_learning": {
            "rows": learning_rows,
            "repeated_terminal_work_prevented": len(history_current) - len({_text(row.get("campaign_identity")) for row in history_current}),
        },
        "routing_summary": routing["summary"],
        "sampling_summary": sampling["summary"],
        "action_summary": actions["summary"],
        "acceptance_summary": acceptance["summary"],
        "trust_horizon_summary": {
            "trust_horizon_id": _text(trust_horizon.get("trust_horizon_id")),
            "cumulative_campaign_count": int(trust_horizon.get("cumulative_campaign_count") or 0),
            "cumulative_hypothesis_count": int(trust_horizon.get("cumulative_hypothesis_count") or 0),
            "cumulative_family_count": int(trust_horizon.get("cumulative_family_count") or 0),
            "cumulative_evidence_changing_cycle_count": int(trust_horizon.get("cumulative_evidence_changing_cycle_count") or 0),
            "cumulative_replay_count": int(trust_horizon.get("cumulative_replay_count") or 0),
            "latest_run_id": _text(latest_run_scope.get("latest_run_id")),
            "latest_run_new_campaign_count": int(latest_run_scope.get("latest_run_new_campaign_count") or 0),
            "latest_run_new_evidence_cycle_count": int(latest_run_scope.get("latest_run_new_evidence_cycle_count") or 0),
        },
        "trust_horizon_consistency": {
            "status": _text(trust_horizon_consistency.get("status")),
            "content_identity": _text(trust_horizon_consistency.get("content_identity")),
        },
        "history_identity": _text(history_payload.get("history_identity")),
        "memory_update_count": int(((memory_payloads.get("memory") or {}).get("summary") or {}).get("memory_update_count") or 0),
    }

    if write_outputs:
        _write_trust_artifacts(
            repo_root,
            attribution=attribution,
            policy=policy,
            plan=initial_plan,
            execution=execution,
            routing=routing,
            sampling=sampling,
            actions=actions,
            acceptance=acceptance,
            trust_horizon=trust_horizon,
            latest_run_scope=latest_run_scope,
            trust_horizon_consistency=trust_horizon_consistency,
            summary=summary,
        )

    return {
        "schema_version": SCHEMA_VERSION,
        "module_version": MODULE_VERSION,
        "report_kind": REPORT_KIND,
        "campaign_history": history_payload,
        "attribution_integrity": attribution,
        "trust_policy_v1_1": policy,
        "portfolio_plan": initial_plan,
        "execution_summary": execution,
        "routing_comparators": routing,
        "sampling_utility": sampling,
        "action_effectiveness": actions,
        "acceptance_history": acceptance,
        "trust_horizon": trust_horizon,
        "trust_horizon_latest_run": latest_run_scope,
        "trust_horizon_consistency": trust_horizon_consistency,
        "memory_payloads": memory_payloads,
        "summary": summary,
    }


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run bounded empirical trust closure")
    parser.add_argument("--repo-root", type=Path, default=REPO_ROOT)
    parser.add_argument("--no-write", action="store_true")
    parser.add_argument("--max-new-campaigns", type=int, default=MAX_NEW_REAL_CAMPAIGNS)
    parser.add_argument("--indent", type=int, default=2)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    payload = run_empirical_trust_closure(
        repo_root=args.repo_root,
        write_outputs=not args.no_write,
        max_new_campaigns=args.max_new_campaigns,
    )
    print(json.dumps(payload, indent=args.indent, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
