"""Read-only action usefulness tracking for ADE-QRE-017H."""

from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import json
import os
import tempfile
from collections import Counter, defaultdict
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Final

REPO_ROOT: Final[Path] = Path(__file__).resolve().parent.parent
MODULE_VERSION: Final[str] = "ade-qre-017h-2026-06-26"
SCHEMA_VERSION: Final[int] = 1
REPORT_KIND: Final[str] = "qre_action_usefulness_tracking"

ARTIFACT_DIR: Final[Path] = REPO_ROOT / "logs" / "qre_action_usefulness_tracking"
ARTIFACT_LATEST: Final[Path] = ARTIFACT_DIR / "latest.json"
DOC_PATH: Final[Path] = (
    REPO_ROOT / "docs" / "governance" / "qre_action_usefulness_tracking.md"
)
_WRITE_PREFIXES: Final[tuple[str, ...]] = (
    "logs/qre_action_usefulness_tracking/",
    "docs/governance/qre_action_usefulness_tracking.md",
)


def _utcnow() -> str:
    return (
        _dt.datetime.now(_dt.UTC)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def _rel(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(REPO_ROOT.resolve())).replace("\\", "/")
    except ValueError:
        return str(path).replace("\\", "/")


def _validate_write_target(path: Path) -> None:
    normalized = path.as_posix()
    if not any(prefix in normalized for prefix in _WRITE_PREFIXES):
        raise ValueError(
            "qre_action_usefulness_tracking: refusing write outside allowlist: "
            f"{path!r}"
        )


def _read_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, Mapping) else {}


def _read_history(path: Path) -> list[dict[str, Any]]:
    if not path.is_file():
        return []
    rows: list[dict[str, Any]] = []
    try:
        for line in path.read_text(encoding="utf-8").splitlines():
            item = line.strip()
            if not item:
                continue
            payload = json.loads(item)
            if isinstance(payload, Mapping):
                rows.append(dict(payload))
    except (OSError, json.JSONDecodeError):
        return []
    return rows


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _list_of_mappings(value: Any) -> list[Mapping[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, Mapping)]


def _bounded(value: Any, *, max_len: int = 200) -> str:
    text = str(value or "").strip()
    if len(text) <= max_len:
        return text
    return text[: max_len - 3].rstrip() + "..."


def _stable_hash(payload: Mapping[str, Any]) -> str:
    compact = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(compact.encode("utf-8")).hexdigest()


def _current_action_items(
    *,
    taxonomy_payload: Mapping[str, Any],
    queue_payload: Mapping[str, Any],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for row in _list_of_mappings(taxonomy_payload.get("taxonomy_rows")):
        recommended_action = _bounded(row.get("recommended_action"))
        if not recommended_action:
            continue
        taxonomy_id = _bounded(row.get("taxonomy_id")) or "unknown_taxonomy_subject"
        rows.append(
            {
                "subject_key": f"taxonomy::{taxonomy_id}",
                "subject_kind": "taxonomy_class",
                "source_surface": _bounded(row.get("source_surface")) or "unknown",
                "recommended_action": recommended_action,
                "blocker_or_failure": _bounded(row.get("failure_class")) or "unknown",
                "supported": bool(row.get("supported")),
                "evidence_status": _bounded(row.get("evidence_status")) or "unknown",
                "operator_explanation": _bounded(row.get("operator_explanation")),
                "evidence_refs": [
                    _bounded(ref) for ref in row.get("evidence_refs") or [] if _bounded(ref)
                ],
            }
        )

    for row in _list_of_mappings(queue_payload.get("rows")):
        recommended_action = _bounded(row.get("exact_next_action"))
        if not recommended_action:
            continue
        candidate_id = _bounded(row.get("candidate_id")) or "unknown_candidate"
        blocker_code = _bounded(row.get("blocker_code")) or "unknown_blocker"
        rows.append(
            {
                "subject_key": f"queue::{candidate_id}::{blocker_code}",
                "subject_kind": "candidate_blocker",
                "source_surface": "qre_basket_next_action_queue",
                "recommended_action": recommended_action,
                "blocker_or_failure": blocker_code,
                "supported": True,
                "evidence_status": "candidate_specific_recommendation",
                "operator_explanation": _bounded(row.get("operator_explanation")),
                "evidence_refs": [
                    _bounded(ref) for ref in row.get("evidence_refs") or [] if _bounded(ref)
                ],
            }
        )
    return rows


def _previous_action_index(history_rows: Sequence[Mapping[str, Any]]) -> dict[str, set[str]]:
    if not history_rows:
        return {}
    latest = history_rows[-1]
    action_rows = _list_of_mappings(latest.get("action_rows"))
    index: dict[str, set[str]] = {}
    for row in action_rows:
        action = _bounded(row.get("recommended_action"))
        subjects = row.get("current_subject_keys")
        if not action or not isinstance(subjects, list):
            continue
        index[action] = {
            _bounded(subject_key) for subject_key in subjects if _bounded(subject_key)
        }
    return index


def _state_from_counts(
    *,
    repeated_count: int,
    resolved_count: int,
    new_count: int,
    prior_subject_count: int,
    action: str,
    routing_ready_count: int,
    sampling_ready_count: int,
    global_false_positive_proxy_rows: int,
) -> dict[str, Any]:
    if prior_subject_count == 0:
        execution_state = "baseline_no_prior_snapshot"
        blocker_resolution_state = "insufficient_evidence"
        repeated_failure_state = "insufficient_evidence"
        useful_outcome_state = (
            "downstream_readiness_visible"
            if action == "eligible_for_readonly_routing"
            and (routing_ready_count > 0 or sampling_ready_count > 0)
            else "insufficient_evidence"
        )
        compute_saving_state = "insufficient_evidence"
    else:
        if resolved_count > 0 and repeated_count > 0:
            execution_state = "mixed_effect_visible_and_unresolved"
            blocker_resolution_state = "partially_resolved"
        elif resolved_count > 0:
            execution_state = "prior_subjects_no_longer_present"
            blocker_resolution_state = "resolved_for_subset"
        elif repeated_count > 0:
            execution_state = "same_subjects_still_present"
            blocker_resolution_state = "still_blocked"
        elif new_count > 0:
            execution_state = "new_subjects_only_since_prior_snapshot"
            blocker_resolution_state = "insufficient_evidence"
        else:
            execution_state = "insufficient_evidence"
            blocker_resolution_state = "insufficient_evidence"

        repeated_failure_state = (
            "same_failure_still_present"
            if repeated_count > 0
            else "not_repeated_in_current_snapshot"
        )
        if action == "eligible_for_readonly_routing" and (
            routing_ready_count > 0 or sampling_ready_count > 0
        ):
            useful_outcome_state = "downstream_readiness_visible"
        elif resolved_count > 0:
            useful_outcome_state = "possible_improvement_visible_not_proven"
        elif repeated_count > 0:
            useful_outcome_state = "no_improvement_visible"
        else:
            useful_outcome_state = "insufficient_evidence"
        compute_saving_state = (
            "possible_compute_saving_not_proven"
            if resolved_count > 0
            else "insufficient_evidence"
        )

    false_positive_state = (
        "global_false_positive_proxy_present"
        if global_false_positive_proxy_rows > 0
        else "no_global_false_positive_proxy_visible"
    )
    return {
        "execution_evidence_state": execution_state,
        "blocker_resolution_state": blocker_resolution_state,
        "repeated_failure_state": repeated_failure_state,
        "useful_outcome_state": useful_outcome_state,
        "compute_saving_state": compute_saving_state,
        "false_positive_state": false_positive_state,
    }


def collect_snapshot(
    *,
    repo_root: Path = REPO_ROOT,
    frozen_utc: str | None = None,
) -> dict[str, Any]:
    generated_at_utc = frozen_utc or _utcnow()
    taxonomy_path = repo_root / "logs" / "qre_actionable_failure_taxonomy" / "latest.json"
    queue_path = repo_root / "logs" / "qre_basket_next_action_queue" / "latest.json"
    routing_path = repo_root / "logs" / "qre_routing_sampling_readiness" / "latest.json"
    source_usefulness_path = repo_root / "logs" / "qre_source_usefulness_ledger" / "latest.json"
    history_path = repo_root / "logs" / "qre_action_usefulness_tracking" / "history.jsonl"

    taxonomy_payload = _read_json(taxonomy_path)
    queue_payload = _read_json(queue_path)
    routing_payload = _read_json(routing_path)
    source_usefulness_payload = _read_json(source_usefulness_path)
    history_rows = _read_history(history_path)

    current_items = _current_action_items(
        taxonomy_payload=taxonomy_payload,
        queue_payload=queue_payload,
    )
    grouped: dict[str, dict[str, Any]] = defaultdict(
        lambda: {
            "source_surfaces": set(),
            "subject_keys": set(),
            "subject_kinds": Counter(),
            "blockers_or_failures": Counter(),
            "supported_subject_count": 0,
            "evidence_statuses": Counter(),
            "evidence_refs": set(),
            "sample_operator_explanations": [],
        }
    )
    for item in current_items:
        action = str(item["recommended_action"])
        bucket = grouped[action]
        bucket["source_surfaces"].add(str(item["source_surface"]))
        bucket["subject_keys"].add(str(item["subject_key"]))
        bucket["subject_kinds"][str(item["subject_kind"])] += 1
        bucket["blockers_or_failures"][str(item["blocker_or_failure"])] += 1
        if bool(item["supported"]):
            bucket["supported_subject_count"] += 1
        bucket["evidence_statuses"][str(item["evidence_status"])] += 1
        for ref in item["evidence_refs"]:
            bucket["evidence_refs"].add(str(ref))
        explanation = str(item["operator_explanation"] or "")
        if explanation and explanation not in bucket["sample_operator_explanations"]:
            bucket["sample_operator_explanations"].append(explanation)

    previous_index = _previous_action_index(history_rows)
    routing_summary = _mapping(routing_payload.get("summary"))
    source_usefulness_summary = _mapping(source_usefulness_payload.get("summary"))
    routing_ready_count = int(routing_summary.get("routing_ready_count") or 0)
    sampling_ready_count = int(routing_summary.get("sampling_ready_count") or 0)
    global_false_positive_proxy_rows = int(
        source_usefulness_summary.get("false_positive_proxy_rows") or 0
    )

    action_rows: list[dict[str, Any]] = []
    for action in sorted(grouped):
        bucket = grouped[action]
        current_subject_keys = sorted(bucket["subject_keys"])
        prior_subject_keys = previous_index.get(action, set())
        repeated_subject_keys = sorted(set(current_subject_keys) & set(prior_subject_keys))
        resolved_subject_keys = sorted(set(prior_subject_keys) - set(current_subject_keys))
        new_subject_keys = sorted(set(current_subject_keys) - set(prior_subject_keys))
        states = _state_from_counts(
            repeated_count=len(repeated_subject_keys),
            resolved_count=len(resolved_subject_keys),
            new_count=len(new_subject_keys),
            prior_subject_count=len(prior_subject_keys),
            action=action,
            routing_ready_count=routing_ready_count,
            sampling_ready_count=sampling_ready_count,
            global_false_positive_proxy_rows=global_false_positive_proxy_rows,
        )
        action_rows.append(
            {
                "recommended_action": action,
                "current_subject_count": len(current_subject_keys),
                "prior_subject_count": len(prior_subject_keys),
                "repeated_subject_count": len(repeated_subject_keys),
                "resolved_subject_count": len(resolved_subject_keys),
                "new_subject_count": len(new_subject_keys),
                "supported_subject_count": int(bucket["supported_subject_count"]),
                "current_subject_keys": current_subject_keys,
                "prior_subject_keys": sorted(prior_subject_keys),
                "repeated_subject_keys": repeated_subject_keys,
                "resolved_subject_keys": resolved_subject_keys,
                "new_subject_keys": new_subject_keys,
                "source_surfaces": sorted(bucket["source_surfaces"]),
                "subject_kind_counts": {
                    key: int(bucket["subject_kinds"][key])
                    for key in sorted(bucket["subject_kinds"])
                },
                "blocker_or_failure_counts": {
                    key: int(bucket["blockers_or_failures"][key])
                    for key in sorted(bucket["blockers_or_failures"])
                },
                "evidence_status_counts": {
                    key: int(bucket["evidence_statuses"][key])
                    for key in sorted(bucket["evidence_statuses"])
                },
                "evidence_refs": sorted(bucket["evidence_refs"]),
                "sample_operator_explanations": list(bucket["sample_operator_explanations"][:3]),
                **states,
            }
        )

    state_counters = {
        "execution_evidence_states": Counter(
            str(row["execution_evidence_state"]) for row in action_rows
        ),
        "blocker_resolution_states": Counter(
            str(row["blocker_resolution_state"]) for row in action_rows
        ),
        "repeated_failure_states": Counter(
            str(row["repeated_failure_state"]) for row in action_rows
        ),
        "useful_outcome_states": Counter(
            str(row["useful_outcome_state"]) for row in action_rows
        ),
        "compute_saving_states": Counter(
            str(row["compute_saving_state"]) for row in action_rows
        ),
        "false_positive_states": Counter(
            str(row["false_positive_state"]) for row in action_rows
        ),
    }

    snapshot_id = _stable_hash(
        {
            "generated_at_utc": generated_at_utc,
            "action_rows": action_rows,
            "routing_ready_count": routing_ready_count,
            "sampling_ready_count": sampling_ready_count,
            "global_false_positive_proxy_rows": global_false_positive_proxy_rows,
        }
    )

    return {
        "schema_version": SCHEMA_VERSION,
        "report_kind": REPORT_KIND,
        "module_version": MODULE_VERSION,
        "generated_at_utc": generated_at_utc,
        "snapshot_identity": {"snapshot_id": snapshot_id},
        "source_artifacts": {
            "qre_actionable_failure_taxonomy": {
                "path": _rel(taxonomy_path),
                "status": "present" if taxonomy_payload else "missing_or_unreadable",
            },
            "qre_basket_next_action_queue": {
                "path": _rel(queue_path),
                "status": "present" if queue_payload else "missing_or_unreadable",
            },
            "qre_routing_sampling_readiness": {
                "path": _rel(routing_path),
                "status": "present" if routing_payload else "missing_or_unreadable",
            },
            "qre_source_usefulness_ledger": {
                "path": _rel(source_usefulness_path),
                "status": "present" if source_usefulness_payload else "missing_or_unreadable",
            },
            "qre_action_usefulness_tracking_history": {
                "path": _rel(history_path),
                "status": "present" if history_rows else "missing_or_empty",
            },
        },
        "action_rows": action_rows,
        "summary": {
            "action_count": len(action_rows),
            "current_subject_count": sum(
                int(row["current_subject_count"]) for row in action_rows
            ),
            "prior_snapshot_available": bool(history_rows),
            "prior_action_count": len(previous_index),
            "routing_ready_count": routing_ready_count,
            "sampling_ready_count": sampling_ready_count,
            "global_false_positive_proxy_rows": global_false_positive_proxy_rows,
            "execution_evidence_state_counts": {
                key: int(state_counters["execution_evidence_states"][key])
                for key in sorted(state_counters["execution_evidence_states"])
            },
            "blocker_resolution_state_counts": {
                key: int(state_counters["blocker_resolution_states"][key])
                for key in sorted(state_counters["blocker_resolution_states"])
            },
            "repeated_failure_state_counts": {
                key: int(state_counters["repeated_failure_states"][key])
                for key in sorted(state_counters["repeated_failure_states"])
            },
            "useful_outcome_state_counts": {
                key: int(state_counters["useful_outcome_states"][key])
                for key in sorted(state_counters["useful_outcome_states"])
            },
            "compute_saving_state_counts": {
                key: int(state_counters["compute_saving_states"][key])
                for key in sorted(state_counters["compute_saving_states"])
            },
            "false_positive_state_counts": {
                key: int(state_counters["false_positive_states"][key])
                for key in sorted(state_counters["false_positive_states"])
            },
            "final_recommendation": (
                "action_usefulness_tracking_ready"
                if action_rows
                else "action_usefulness_tracking_missing_inputs"
            ),
            "operator_summary": (
                "Action usefulness tracking compares current bounded recommendations "
                "against prior action-usefulness snapshots when available. It proves "
                "only repo-backed effects, leaves compute-saved and false-positive "
                "claims fail-closed when they are not action-specific, and appends "
                "bounded history so later runs can become truly comparative."
            ),
            "exact_next_action": (
                "preserve_history_and_recheck_after_new_research_evidence"
            ),
        },
        "safety_invariants": {
            "read_only": True,
            "mutates_frozen_contracts": False,
            "mutates_queue": False,
            "mutates_research_outputs": False,
            "mutates_routing": False,
            "mutates_sampling": False,
            "mutates_strategy_or_registry": False,
            "paper_shadow_live_forbidden": True,
            "broker_risk_execution_forbidden": True,
            "invents_action_execution": False,
        },
    }


def render_markdown(snapshot: Mapping[str, Any]) -> str:
    summary = _mapping(snapshot.get("summary"))
    rows = _list_of_mappings(snapshot.get("action_rows"))
    lines = [
        "# QRE Action Usefulness Tracking",
        "",
        f"- generated_at_utc: `{_bounded(snapshot.get('generated_at_utc'))}`",
        f"- module_version: `{_bounded(snapshot.get('module_version'))}`",
        "",
        "## Summary",
        "",
        f"- {summary.get('operator_summary') or ''}",
        f"- action count: `{summary.get('action_count') or 0}`",
        f"- current subject count: `{summary.get('current_subject_count') or 0}`",
        f"- prior snapshot available: `{bool(summary.get('prior_snapshot_available'))}`",
        f"- routing ready count: `{summary.get('routing_ready_count') or 0}`",
        f"- sampling ready count: `{summary.get('sampling_ready_count') or 0}`",
        f"- global false-positive proxy rows: `{summary.get('global_false_positive_proxy_rows') or 0}`",
        f"- final recommendation: `{summary.get('final_recommendation') or ''}`",
        "",
        "## Action Rows",
        "",
        "| Action | Current | Prior | Repeated | Resolved | Execution state | Useful outcome |",
        "| --- | ---: | ---: | ---: | ---: | --- | --- |",
    ]
    for row in rows:
        lines.append(
            "| "
            + " | ".join(
                [
                    _bounded(row.get("recommended_action")),
                    str(int(row.get("current_subject_count") or 0)),
                    str(int(row.get("prior_subject_count") or 0)),
                    str(int(row.get("repeated_subject_count") or 0)),
                    str(int(row.get("resolved_subject_count") or 0)),
                    _bounded(row.get("execution_evidence_state")),
                    _bounded(row.get("useful_outcome_state")),
                ]
            )
            + " |"
        )
    return "\n".join(lines) + "\n"


def write_outputs(
    snapshot: Mapping[str, Any],
    *,
    output_dir: Path = ARTIFACT_DIR,
    doc_path: Path = DOC_PATH,
    repo_root: Path = REPO_ROOT,
) -> dict[str, str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    doc_path.parent.mkdir(parents=True, exist_ok=True)
    latest = output_dir / "latest.json"
    timestamped = output_dir / (str(snapshot["generated_at_utc"]).replace(":", "-") + ".json")
    history = output_dir / "history.jsonl"
    for target in (latest, timestamped, history, doc_path):
        _validate_write_target(target)

    json_payload = json.dumps(snapshot, indent=2, sort_keys=True) + "\n"
    markdown = render_markdown(snapshot)

    for target in (latest, timestamped):
        with tempfile.NamedTemporaryFile(
            "w",
            encoding="utf-8",
            dir=str(target.parent),
            delete=False,
        ) as handle:
            handle.write(json_payload)
            tmp_path = Path(handle.name)
        os.replace(tmp_path, target)

    with history.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(snapshot, sort_keys=True) + "\n")

    with tempfile.NamedTemporaryFile(
        "w",
        encoding="utf-8",
        dir=str(doc_path.parent),
        delete=False,
    ) as handle:
        handle.write(markdown)
        tmp_doc = Path(handle.name)
    os.replace(tmp_doc, doc_path)

    def _project(path: Path) -> str:
        try:
            rel = path.relative_to(repo_root)
        except ValueError:
            rel = path
        return str(rel).replace("\\", "/")

    return {
        "latest": _project(latest),
        "timestamped": _project(timestamped),
        "history": _project(history),
        "doc": _project(doc_path),
    }


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m reporting.qre_action_usefulness_tracking",
        description="Build read-only QRE action usefulness tracking snapshot.",
    )
    parser.add_argument("--write", action="store_true")
    parser.add_argument("--frozen-utc")
    args = parser.parse_args(list(argv) if argv is not None else None)

    snapshot = collect_snapshot(frozen_utc=args.frozen_utc)
    if args.write:
        snapshot["_artifact_paths"] = write_outputs(snapshot)
    print(json.dumps(snapshot, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
