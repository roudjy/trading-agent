from __future__ import annotations

import argparse
import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Final

from packages.qre_research import research_memory
from research import qre_behavior_thesis_evidence as thesis_evidence
from research import qre_behavior_thesis_registry as thesis_registry
from research import qre_research_memory_retrieval as memory_retrieval


SCHEMA_VERSION: Final[str] = "1.0"
REPORT_KIND: Final[str] = "qre_prior_failure_retrieval"
MODULE_VERSION: Final[str] = "ade-qre-017n-2026-06-26"
DEFAULT_OUTPUT_DIR: Final[Path] = Path("logs/qre_prior_failure_retrieval")
LATEST_NAME: Final[str] = "latest.json"
DOC_PATH: Final[Path] = Path("docs/governance/qre_prior_failure_retrieval.md")
WRITE_PREFIXES: Final[tuple[str, ...]] = (
    "logs/qre_prior_failure_retrieval/",
    "docs/governance/qre_prior_failure_retrieval.md",
)
DEFAULT_RESEARCH_MEMORY_RETRIEVAL_PATH: Final[Path] = (
    memory_retrieval.DEFAULT_OUTPUT_DIR / memory_retrieval.LATEST_NAME
)
DEFAULT_DISPOSITION_MEMORY_PATH: Final[Path] = Path(
    "logs/qre_hypothesis_disposition_memory/latest.json"
)
DEFAULT_BREADTH_PATH: Final[Path] = Path(
    "logs/qre_evidence_breadth_framework/latest.json"
)
DEFAULT_ROUTER_PATH: Final[Path] = Path(
    "logs/qre_research_cycle_router/latest.json"
)
DEFAULT_DEDUP_PATH: Final[Path] = Path(
    "logs/qre_experiment_dedup_novelty_enforcement/latest.json"
)

SUMMARY_STATUS_VALUES: Final[tuple[str, ...]] = (
    "missing_context",
    "dead_zone_visible",
    "prior_failure_visible",
    "prior_failure_dead_zone_visible",
    "prior_failure_dead_zone_action_visible",
)
ITEM_KIND_VALUES: Final[tuple[str, ...]] = (
    "prior_failure",
    "dead_zone",
    "prior_action",
    "retrieval_match",
)
ITEM_STATUS_VALUES: Final[tuple[str, ...]] = (
    "present",
    "missing",
    "blocked",
)
ROW_REQUIRED_FIELDS: Final[tuple[str, ...]] = (
    "thesis_id",
    "source_hypothesis_id",
    "behavior_family",
    "thesis_status",
    "summary_status",
    "retrieval_query",
    "prior_failure_count",
    "dead_zone_count",
    "prior_action_count",
    "retrieval_match_count",
    "retrieval_items",
    "provenance_refs",
    "schema_version",
)
ITEM_REQUIRED_FIELDS: Final[tuple[str, ...]] = (
    "retrieval_id",
    "thesis_id",
    "retrieval_kind",
    "status",
    "retrieval_ref",
    "summary",
    "linked_by",
    "provenance_refs",
)


@dataclass(frozen=True)
class PriorFailureItem:
    retrieval_id: str
    thesis_id: str
    retrieval_kind: str
    status: str
    retrieval_ref: str
    summary: str
    linked_by: str
    provenance_refs: tuple[str, ...]

    def to_payload(self) -> dict[str, Any]:
        return {
            "retrieval_id": self.retrieval_id,
            "thesis_id": self.thesis_id,
            "retrieval_kind": self.retrieval_kind,
            "status": self.status,
            "retrieval_ref": self.retrieval_ref,
            "summary": self.summary,
            "linked_by": self.linked_by,
            "provenance_refs": list(self.provenance_refs),
            "authority": {
                "can_generate_executable_strategy": False,
                "can_register_strategy": False,
                "can_promote_candidate": False,
                "can_launch_campaign": False,
                "can_activate_paper_shadow_live": False,
                "evidence_authority": "context_only",
            },
        }


def _text(value: Any) -> str:
    return str(value or "").strip()


def _read_json(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _unique(values: list[Any] | tuple[Any, ...]) -> tuple[str, ...]:
    out: list[str] = []
    for value in values:
        text = _text(value)
        if text and text not in out:
            out.append(text)
    return tuple(out)


def _sha(value: Any) -> str:
    blob = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def _validate_write_target(path: Path) -> None:
    normalized = path.as_posix()
    if not any(prefix in normalized for prefix in WRITE_PREFIXES):
        raise ValueError(
            f"qre_prior_failure_retrieval: refusing write outside allowlist: {path!r}"
        )


def _item_id(*, thesis_id: str, retrieval_kind: str, retrieval_ref: str) -> str:
    digest = _sha(
        {
            "thesis_id": thesis_id,
            "retrieval_kind": retrieval_kind,
            "retrieval_ref": retrieval_ref,
        }
    )
    return f"qpf_{digest[:16]}"


def _read_rows(payload: dict[str, Any] | None, field: str) -> list[dict[str, Any]]:
    if not isinstance(payload, dict):
        return []
    rows = payload.get(field)
    if not isinstance(rows, list):
        return []
    return [dict(row) for row in rows if isinstance(row, dict)]


def _query_row(payload: dict[str, Any] | None, query_id: str) -> dict[str, Any] | None:
    for row in _read_rows(payload, "queries"):
        if _text(row.get("query_id")) == query_id:
            return row
    return None


def _matched_disposition(
    payload: dict[str, Any] | None,
    *,
    source_hypothesis_id: str,
    behavior_family: str,
) -> dict[str, Any] | None:
    if not isinstance(payload, dict):
        return None
    record = payload.get("record")
    if not isinstance(record, dict):
        return None
    if _text(record.get("hypothesis_id")) == source_hypothesis_id:
        return dict(record)
    behavior_id = _text(record.get("behavior_id"))
    if behavior_id and behavior_family and behavior_family in behavior_id:
        return dict(record)
    return None


def _breadth_behavior_row(
    payload: dict[str, Any] | None,
    *,
    behavior_family: str,
) -> dict[str, Any] | None:
    for row in _read_rows(payload, "coverage_matrix"):
        if _text(row.get("dimension")) != "behavior":
            continue
        scope_key = _text(row.get("scope_key"))
        if scope_key == behavior_family or behavior_family in scope_key:
            return row
    return None


def _dedup_rows(
    payload: dict[str, Any] | None,
    *,
    source_hypothesis_id: str,
    exact_scope_matched: bool,
) -> list[dict[str, Any]]:
    if not exact_scope_matched:
        return []
    rows: list[dict[str, Any]] = []
    for row in _read_rows(payload, "duplicate_rows"):
        duplicate_class = _text(row.get("duplicate_class"))
        if duplicate_class not in {"exact_failed_scope", "materially_equivalent_retry"}:
            continue
        refs = [str(ref) for ref in row.get("evidence_refs") or []]
        if any("qre_hypothesis_disposition_memory" in ref for ref in refs):
            rows.append(row)
            continue
        if source_hypothesis_id and any(source_hypothesis_id in ref for ref in refs):
            rows.append(row)
    return rows


def _router_action(
    router_payload: dict[str, Any] | None,
    *,
    exact_scope_matched: bool,
) -> dict[str, Any] | None:
    if not exact_scope_matched or not isinstance(router_payload, dict):
        return None
    action = _text(router_payload.get("recommended_research_action"))
    directions = _read_rows(router_payload, "eligible_directions")
    if not action and not directions:
        return None
    return {
        "recommended_research_action": action,
        "eligible_directions": directions,
    }


def _filtered_prior_failures(values: list[Any] | tuple[Any, ...]) -> list[str]:
    return [
        text
        for text in (_text(value) for value in values)
        if text and not text.startswith("none_recorded:")
    ]


def _retrieval_query(row: dict[str, Any]) -> str:
    tokens = [
        _text(row.get("source_hypothesis_id")),
        _text(row.get("behavior_family")),
        _text(row.get("strategy_family")),
    ]
    tokens.extend(_filtered_prior_failures(tuple(row.get("prior_similar_failures") or ())))
    return " ".join(token for token in _unique(tokens) if token)


def _item(
    *,
    thesis_id: str,
    retrieval_kind: str,
    status: str,
    retrieval_ref: str,
    summary: str,
    linked_by: str,
    provenance_refs: list[str] | tuple[str, ...],
) -> PriorFailureItem:
    return PriorFailureItem(
        retrieval_id=_item_id(
            thesis_id=thesis_id,
            retrieval_kind=retrieval_kind,
            retrieval_ref=retrieval_ref,
        ),
        thesis_id=thesis_id,
        retrieval_kind=retrieval_kind,
        status=status,
        retrieval_ref=retrieval_ref,
        summary=summary,
        linked_by=linked_by,
        provenance_refs=_unique(provenance_refs),
    )


def _summary_status(
    *,
    prior_failure_count: int,
    dead_zone_count: int,
    prior_action_count: int,
) -> str:
    if prior_failure_count and dead_zone_count and prior_action_count:
        return "prior_failure_dead_zone_action_visible"
    if prior_failure_count and dead_zone_count:
        return "prior_failure_dead_zone_visible"
    if prior_failure_count:
        return "prior_failure_visible"
    if dead_zone_count:
        return "dead_zone_visible"
    return "missing_context"


def _build_row(
    row: dict[str, Any],
    *,
    evidence_row: dict[str, Any] | None,
    disposition_payload: dict[str, Any] | None,
    retrieval_payload: dict[str, Any] | None,
    breadth_payload: dict[str, Any] | None,
    router_payload: dict[str, Any] | None,
    dedup_payload: dict[str, Any] | None,
    memory: dict[str, Any],
) -> tuple[dict[str, Any], int]:
    thesis_id = _text(row.get("thesis_id"))
    source_hypothesis_id = _text(row.get("source_hypothesis_id"))
    behavior_family = _text(row.get("behavior_family"))
    retrieval_query = _retrieval_query(row)
    disposition = _matched_disposition(
        disposition_payload,
        source_hypothesis_id=source_hypothesis_id,
        behavior_family=behavior_family,
    )
    exact_scope = _query_row(retrieval_payload, "exact_scope_already_tested")
    similar_scope = _query_row(retrieval_payload, "materially_similar_scope_rejected")
    recurring_failures = _query_row(
        retrieval_payload, "recurring_evidence_or_source_failures"
    )
    exact_scope_matched = bool(disposition) or (
        isinstance(exact_scope, dict)
        and _text(((exact_scope.get("scope_signature") or {}).get("hypothesis_id")))
        == source_hypothesis_id
    )
    duplicate_rows = _dedup_rows(
        dedup_payload,
        source_hypothesis_id=source_hypothesis_id,
        exact_scope_matched=exact_scope_matched,
    )
    breadth_row = _breadth_behavior_row(breadth_payload, behavior_family=behavior_family)
    router_action = _router_action(router_payload, exact_scope_matched=exact_scope_matched)

    provenance = list(row.get("provenance_refs") or [])
    if evidence_row:
        provenance.extend(evidence_row.get("provenance_refs") or [])
    retrieval_items: list[dict[str, Any]] = []
    duplicate_count = 0

    prior_failures = _filtered_prior_failures(tuple(row.get("prior_similar_failures") or ()))
    if disposition:
        prior_failures.extend(
            value
            for value in _filtered_prior_failures(
                tuple(disposition.get("failure_classes") or ())
            )
            if value not in prior_failures
        )
    prior_failure_refs = []
    if disposition:
        record_id = _text(disposition.get("memory_record_id")) or "record"
        prior_failure_refs.append(
            f"{DEFAULT_DISPOSITION_MEMORY_PATH.as_posix()}#record::{record_id}"
        )
    if exact_scope_matched and isinstance(similar_scope, dict) and similar_scope.get("answer") is True:
        prior_failure_refs.append(
            f"{DEFAULT_RESEARCH_MEMORY_RETRIEVAL_PATH.as_posix()}#queries.materially_similar_scope_rejected"
        )
    if prior_failures:
        retrieval_items.append(
            _item(
                thesis_id=thesis_id,
                retrieval_kind="prior_failure",
                status="present",
                retrieval_ref=prior_failure_refs[0]
                if prior_failure_refs
                else f"state:prior_failure:{source_hypothesis_id}",
                summary="; ".join(prior_failures),
                linked_by="prior_similar_failures",
                provenance_refs=provenance + prior_failure_refs,
            ).to_payload()
        )
    else:
        retrieval_items.append(
            _item(
                thesis_id=thesis_id,
                retrieval_kind="prior_failure",
                status="missing",
                retrieval_ref=f"state:none_recorded:prior_failure:{source_hypothesis_id}",
                summary="No repository-backed prior failure record is linked to this thesis.",
                linked_by="fail_closed_state",
                provenance_refs=provenance,
            ).to_payload()
        )

    dead_zone_refs: list[str] = []
    dead_zone_summary = ""
    if duplicate_rows:
        dead_zone_refs.extend(
            f"{DEFAULT_DEDUP_PATH.as_posix()}#duplicate_rows[{index}]"
            for index, _row in enumerate(_read_rows(dedup_payload, "duplicate_rows"))
            if _row in duplicate_rows
        )
        dead_zone_summary = "; ".join(
            sorted(_text(dup.get("duplicate_class")) for dup in duplicate_rows)
        )
    elif breadth_row and list(breadth_row.get("blocker_reasons") or []):
        dead_zone_refs.append(
            f"{DEFAULT_BREADTH_PATH.as_posix()}#coverage_matrix[{_read_rows(breadth_payload, 'coverage_matrix').index(breadth_row)}]"
        )
        dead_zone_summary = "; ".join(
            _unique(tuple(str(reason) for reason in breadth_row.get("blocker_reasons") or ()))
        )

    if dead_zone_refs:
        retrieval_items.append(
            _item(
                thesis_id=thesis_id,
                retrieval_kind="dead_zone",
                status="present",
                retrieval_ref=dead_zone_refs[0],
                summary=dead_zone_summary or "Dead-zone or duplicate suppression context is visible.",
                linked_by="dedup_or_breadth",
                provenance_refs=provenance + dead_zone_refs,
            ).to_payload()
        )
    else:
        retrieval_items.append(
            _item(
                thesis_id=thesis_id,
                retrieval_kind="dead_zone",
                status="missing",
                retrieval_ref=f"state:none_recorded:dead_zone:{source_hypothesis_id}",
                summary="No repository-backed dead-zone or duplicate suppression context is linked to this thesis.",
                linked_by="fail_closed_state",
                provenance_refs=provenance,
            ).to_payload()
        )

    if router_action:
        action = _text(router_action.get("recommended_research_action")) or "review_retrieval_context"
        retrieval_items.append(
            _item(
                thesis_id=thesis_id,
                retrieval_kind="prior_action",
                status="present",
                retrieval_ref=f"{DEFAULT_ROUTER_PATH.as_posix()}#recommended_research_action",
                summary=action,
                linked_by="research_cycle_router",
                provenance_refs=provenance
                + [DEFAULT_ROUTER_PATH.as_posix()]
                + [
                    f"{DEFAULT_RESEARCH_MEMORY_RETRIEVAL_PATH.as_posix()}#queries.novel_remaining_research_directions"
                ],
            ).to_payload()
        )
    else:
        retrieval_items.append(
            _item(
                thesis_id=thesis_id,
                retrieval_kind="prior_action",
                status="missing",
                retrieval_ref=f"state:none_recorded:prior_action:{source_hypothesis_id}",
                summary="No repository-backed prior action is linked to this thesis.",
                linked_by="fail_closed_state",
                provenance_refs=provenance,
            ).to_payload()
        )

    memory_matches = research_memory.find_related_failures(
        memory,
        retrieval_query,
        limit=5,
    ) if retrieval_query else []
    for match in memory_matches:
        retrieval_items.append(
            _item(
                thesis_id=thesis_id,
                retrieval_kind="retrieval_match",
                status="present",
                retrieval_ref=_text(match.get("artifact_id")) or _text(match.get("artifact_path")),
                summary=_text(match.get("title")) or _text(match.get("record_kind")),
                linked_by="research_memory",
                provenance_refs=provenance + [_text(match.get("artifact_id"))],
            ).to_payload()
        )

    deduped: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for item in retrieval_items:
        item_id = _text(item.get("retrieval_id"))
        if item_id in seen_ids:
            duplicate_count += 1
            continue
        seen_ids.add(item_id)
        deduped.append(item)

    prior_failure_count = sum(
        1
        for item in deduped
        if item["retrieval_kind"] == "prior_failure" and item["status"] == "present"
    )
    dead_zone_count = sum(
        1
        for item in deduped
        if item["retrieval_kind"] == "dead_zone" and item["status"] == "present"
    )
    prior_action_count = sum(
        1
        for item in deduped
        if item["retrieval_kind"] == "prior_action" and item["status"] == "present"
    )

    row_payload = {
        "thesis_id": thesis_id,
        "source_hypothesis_id": source_hypothesis_id,
        "behavior_family": behavior_family,
        "thesis_status": _text(row.get("status")),
        "summary_status": _summary_status(
            prior_failure_count=prior_failure_count,
            dead_zone_count=dead_zone_count,
            prior_action_count=prior_action_count,
        ),
        "retrieval_query": retrieval_query or f"state:no_query:{source_hypothesis_id}",
        "prior_failure_count": prior_failure_count,
        "dead_zone_count": dead_zone_count,
        "prior_action_count": prior_action_count,
        "retrieval_match_count": len(memory_matches),
        "retrieval_matches": [
            {
                "artifact_id": _text(match.get("artifact_id")),
                "artifact_path": _text(match.get("artifact_path")),
                "record_kind": _text(match.get("record_kind")),
                "score": int(match.get("score") or 0),
                "ontology_tags": list(match.get("ontology_tags") or []),
            }
            for match in memory_matches
        ],
        "recurring_failure_snapshot": [
            dict(item)
            for item in ((recurring_failures or {}).get("rows") or [])[:5]
            if isinstance(item, dict)
        ],
        "retrieval_items": deduped,
        "provenance_refs": list(_unique(provenance)),
        "schema_version": SCHEMA_VERSION,
    }
    return row_payload, duplicate_count


def validate_prior_failure_row(row: dict[str, Any]) -> dict[str, Any]:
    rejections: list[str] = []
    missing: list[str] = []
    for field in ROW_REQUIRED_FIELDS:
        if field not in row:
            missing.append(field)
            continue
        value = row.get(field)
        if value is None:
            missing.append(field)
            continue
        if isinstance(value, str) and not _text(value):
            missing.append(field)
            continue
        if isinstance(value, list) and not value:
            missing.append(field)
    if missing:
        rejections.append("missing_required_fields")
    if _text(row.get("summary_status")) not in SUMMARY_STATUS_VALUES:
        rejections.append("invalid_summary_status")
    if _text(row.get("schema_version")) != SCHEMA_VERSION:
        rejections.append("invalid_schema_version")
    items = row.get("retrieval_items") if isinstance(row.get("retrieval_items"), list) else []
    if not items:
        rejections.append("missing_retrieval_items")
    seen_ids: set[str] = set()
    seen_kinds: set[str] = set()
    for item in items:
        if not isinstance(item, dict):
            rejections.append("invalid_item_shape")
            continue
        if any(not item.get(field) for field in ITEM_REQUIRED_FIELDS):
            rejections.append("missing_item_fields")
        if _text(item.get("retrieval_kind")) not in ITEM_KIND_VALUES:
            rejections.append("invalid_retrieval_kind")
        if _text(item.get("status")) not in ITEM_STATUS_VALUES:
            rejections.append("invalid_item_status")
        item_id = _text(item.get("retrieval_id"))
        if item_id in seen_ids:
            rejections.append("duplicate_retrieval_id")
        seen_ids.add(item_id)
        kind = _text(item.get("retrieval_kind"))
        if kind in {"prior_failure", "dead_zone", "prior_action"}:
            seen_kinds.add(kind)
        authority = item.get("authority") if isinstance(item.get("authority"), dict) else {}
        if authority.get("can_generate_executable_strategy") is not False:
            rejections.append("strategy_generation_authority_forbidden")
        if authority.get("can_register_strategy") is not False:
            rejections.append("strategy_registration_authority_forbidden")
        if authority.get("can_launch_campaign") is not False:
            rejections.append("campaign_authority_forbidden")
    for required_kind in ("prior_failure", "dead_zone", "prior_action"):
        if required_kind not in seen_kinds:
            rejections.append(f"missing_explicit_{required_kind}_state")
    return {
        "valid": not rejections,
        "rejection_reasons": list(dict.fromkeys(rejections)),
        "thesis_id": _text(row.get("thesis_id")),
    }


def build_prior_failure_retrieval(
    *,
    repo_root: Path = Path("."),
    registry_report: dict[str, Any] | None = None,
    evidence_report: dict[str, Any] | None = None,
    disposition_memory_path: Path = DEFAULT_DISPOSITION_MEMORY_PATH,
    research_memory_retrieval_path: Path = DEFAULT_RESEARCH_MEMORY_RETRIEVAL_PATH,
    breadth_path: Path = DEFAULT_BREADTH_PATH,
    router_path: Path = DEFAULT_ROUTER_PATH,
    dedup_path: Path = DEFAULT_DEDUP_PATH,
) -> dict[str, Any]:
    registry_upstream = registry_report or thesis_registry.build_behavior_thesis_registry(
        repo_root=repo_root
    )
    evidence_upstream = evidence_report or thesis_evidence.build_behavior_thesis_evidence(
        repo_root=repo_root,
        registry_report=registry_upstream,
    )
    registry_rows = _read_rows(registry_upstream, "rows")
    evidence_rows = {
        _text(row.get("thesis_id")): row for row in _read_rows(evidence_upstream, "rows")
    }
    disposition_payload = _read_json(repo_root / disposition_memory_path)
    retrieval_payload = _read_json(repo_root / research_memory_retrieval_path)
    breadth_payload = _read_json(repo_root / breadth_path)
    router_payload = _read_json(repo_root / router_path)
    dedup_payload = _read_json(repo_root / dedup_path)
    memory = research_memory.build_research_memory(
        artifact_paths=tuple(
            path
            for path in memory_retrieval.DEFAULT_ARTIFACT_PATHS
            if path.as_posix() != DEFAULT_OUTPUT_DIR.joinpath(LATEST_NAME).as_posix()
        ),
        repo_root=repo_root,
    )

    registry_validations = [
        thesis_registry.validate_behavior_thesis(row) for row in registry_rows
    ]
    evidence_validations = [
        thesis_evidence.validate_thesis_evidence_row(row)
        for row in _read_rows(evidence_upstream, "rows")
    ]
    rows: list[dict[str, Any]] = []
    duplicate_item_count = 0
    for row in sorted(registry_rows, key=lambda item: _text(item.get("thesis_id"))):
        payload, duplicates = _build_row(
            row,
            evidence_row=evidence_rows.get(_text(row.get("thesis_id"))),
            disposition_payload=disposition_payload,
            retrieval_payload=retrieval_payload,
            breadth_payload=breadth_payload,
            router_payload=router_payload,
            dedup_payload=dedup_payload,
            memory=memory,
        )
        duplicate_item_count += duplicates
        rows.append(payload)

    validations = [validate_prior_failure_row(row) for row in rows]
    invalid_rows = [row for row in validations if not row["valid"]]
    invalid_registry_rows = [row for row in registry_validations if not row["valid"]]
    invalid_evidence_rows = [row for row in evidence_validations if not row["valid"]]
    prior_failure_count = sum(int(row["prior_failure_count"]) for row in rows)
    dead_zone_count = sum(int(row["dead_zone_count"]) for row in rows)
    prior_action_count = sum(int(row["prior_action_count"]) for row in rows)
    retrieval_match_count = sum(int(row["retrieval_match_count"]) for row in rows)
    return {
        "schema_version": SCHEMA_VERSION,
        "report_kind": REPORT_KIND,
        "module_version": MODULE_VERSION,
        "rows": rows,
        "summary": {
            "status": (
                "ready"
                if not invalid_rows and not invalid_registry_rows and not invalid_evidence_rows
                else "not_ready"
            ),
            "prior_failure_retrieval_ready": not invalid_rows
            and not invalid_registry_rows
            and not invalid_evidence_rows,
            "thesis_count": len(rows),
            "invalid_row_count": len(invalid_rows),
            "invalid_registry_row_count": len(invalid_registry_rows),
            "invalid_evidence_row_count": len(invalid_evidence_rows),
            "prior_failure_count": prior_failure_count,
            "dead_zone_count": dead_zone_count,
            "prior_action_count": prior_action_count,
            "retrieval_match_count": retrieval_match_count,
            "duplicate_item_count": duplicate_item_count,
            "operator_summary": (
                "Prior failures, dead zones, and prior actions are linked back to "
                "behavior theses as provenance-backed context only."
            ),
            "final_recommendation": (
                "prior_failure_retrieval_ready"
                if not invalid_rows and not invalid_registry_rows and not invalid_evidence_rows
                else "prior_failure_retrieval_not_ready"
            ),
        },
        "artifact_references": {
            "behavior_thesis_registry": "logs/qre_behavior_thesis_registry/latest.json",
            "behavior_thesis_evidence": "logs/qre_behavior_thesis_evidence/latest.json",
            "research_memory_retrieval": research_memory_retrieval_path.as_posix(),
            "disposition_memory": disposition_memory_path.as_posix(),
            "breadth_framework": breadth_path.as_posix(),
            "research_cycle_router": router_path.as_posix(),
            "experiment_dedup": dedup_path.as_posix(),
        },
        "validations": validations,
        "upstream_validations": {
            "behavior_thesis_registry": registry_validations,
            "behavior_thesis_evidence": evidence_validations,
        },
        "safety_invariants": {
            "can_generate_executable_strategy": False,
            "can_register_strategy": False,
            "can_promote_candidate": False,
            "can_launch_campaign": False,
            "can_activate_paper_shadow_live": False,
            "retrieval_is_context_only": True,
            "read_only": True,
            "uses_local_artifacts_only": True,
            "uses_network": False,
            "uses_subprocess": False,
            "paper_shadow_live_forbidden": True,
            "broker_risk_execution_forbidden": True,
        },
        "authority_boundary": {
            "can_generate_executable_strategy": False,
            "can_register_strategy": False,
            "can_promote_candidate": False,
            "can_launch_campaign": False,
            "can_activate_paper_shadow_live": False,
            "retrieval_is_context_not_authority": True,
            "operator_review_required": True,
        },
    }


def render_doc(report: dict[str, Any]) -> str:
    summary = report.get("summary") if isinstance(report.get("summary"), dict) else {}
    lines = [
        "# QRE Prior-Failure Retrieval",
        "",
        "This surface links behavior theses to prior failures, dead zones, and prior",
        "actions using existing local retrieval and research-memory artifacts.",
        "",
        "Retrieval remains context only. It cannot generate executable strategies,",
        "register strategies, promote candidates, mutate campaigns, or activate",
        "paper/shadow/live paths.",
        "",
        "## Summary",
        "",
        f"- Status: `{_text(summary.get('status'))}`",
        f"- Thesis count: `{int(summary.get('thesis_count') or 0)}`",
        f"- Prior failure count: `{int(summary.get('prior_failure_count') or 0)}`",
        f"- Dead-zone count: `{int(summary.get('dead_zone_count') or 0)}`",
        f"- Prior action count: `{int(summary.get('prior_action_count') or 0)}`",
        f"- Retrieval match count: `{int(summary.get('retrieval_match_count') or 0)}`",
        "",
        "## Commands",
        "",
        "```powershell",
        "python -m research.qre_prior_failure_retrieval --status",
        "python -m research.qre_prior_failure_retrieval --write",
        "```",
        "",
        "## Capability Boundary",
        "",
        "- automatic hypothesis proposals or campaign-seed proposals remain context",
        "  unless separately authorized elsewhere;",
        "- this surface does not generate executable strategy code;",
        "- this surface does not register strategies or launch campaigns;",
        "- retrieved prior failures remain provenance-linked context, not truth authority.",
        "",
    ]
    return "\n".join(lines) + "\n"


def write_outputs(report: dict[str, Any], *, repo_root: Path = Path(".")) -> dict[str, str]:
    base = repo_root / DEFAULT_OUTPUT_DIR
    base.mkdir(parents=True, exist_ok=True)
    latest = base / LATEST_NAME
    doc = repo_root / DOC_PATH
    for target in (latest, doc):
        _validate_write_target(target)
    latest_payload = json.dumps(report, indent=2, sort_keys=True) + "\n"
    latest_tmp = latest.with_suffix(latest.suffix + ".tmp")
    latest_tmp.write_text(latest_payload, encoding="utf-8")
    os.replace(latest_tmp, latest)

    doc.parent.mkdir(parents=True, exist_ok=True)
    doc_tmp = doc.with_suffix(doc.suffix + ".tmp")
    doc_tmp.write_text(render_doc(report), encoding="utf-8")
    os.replace(doc_tmp, doc)
    return {
        "latest": DEFAULT_OUTPUT_DIR.joinpath(LATEST_NAME).as_posix(),
        "doc": DOC_PATH.as_posix(),
    }


def read_prior_failure_retrieval_status(
    *,
    repo_root: Path = Path("."),
) -> dict[str, Any]:
    path = repo_root / DEFAULT_OUTPUT_DIR / LATEST_NAME
    payload = _read_json(path)
    summary = payload.get("summary") if isinstance(payload, dict) else {}
    if not isinstance(summary, dict):
        summary = {}
    return {
        "status": _text(summary.get("status")) or "missing",
        "path": DEFAULT_OUTPUT_DIR.joinpath(LATEST_NAME).as_posix(),
        "fails_closed": not bool(payload),
        "schema_version": _text((payload or {}).get("schema_version")) or SCHEMA_VERSION,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="QRE prior-failure retrieval")
    parser.add_argument("--write", action="store_true", help="write deterministic outputs")
    parser.add_argument("--status", action="store_true", help="read latest output status")
    args = parser.parse_args(argv)
    if args.status:
        print(json.dumps(read_prior_failure_retrieval_status(), indent=2))
        return 0
    report = build_prior_failure_retrieval()
    if args.write or not args.status:
        report["_artifact_paths"] = write_outputs(report)
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
