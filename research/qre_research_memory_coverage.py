from __future__ import annotations

import argparse
import hashlib
import json
import os
from collections import Counter
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Final

from research import qre_failure_action_from_basket as failure_action
from research import qre_reason_records_v1 as reason_records
from research import qre_real_basket_diagnosis as basket_diagnosis
from research.qre_entity_resolution import resolve_entities_from_text
from research.qre_research_ontology import classify_research_text


MEMORY_REPORT_KIND: Final[str] = "qre_research_memory_coverage"
FAILURE_REPORT_KIND: Final[str] = "qre_failure_retrieval"
SCHEMA_VERSION: Final[str] = "1.0"
MEMORY_OUTPUT_DIR: Final[Path] = Path("logs/qre_research_memory_coverage")
FAILURE_OUTPUT_DIR: Final[Path] = Path("logs/qre_failure_retrieval")
LATEST_NAME: Final[str] = "latest.json"
_MEMORY_PREFIX: Final[str] = "logs/qre_research_memory_coverage/"
_FAILURE_PREFIX: Final[str] = "logs/qre_failure_retrieval/"


def _tokenize(*values: Any) -> list[str]:
    tokens: list[str] = []
    for value in values:
        if isinstance(value, Sequence) and not isinstance(value, str | bytes):
            tokens.extend(_tokenize(*value))
            continue
        text = str(value).strip().lower()
        if not text:
            continue
        for token in text.replace("/", " ").replace("-", "_").replace(",", " ").split():
            clean = token.strip("`'\"()[]{}:;")
            if clean and clean not in tokens:
                tokens.append(clean[:80])
    return tokens[:32]


def _digest(payload: Mapping[str, Any]) -> str:
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(blob.encode("utf-8")).hexdigest()


def _ontology_tags_for_record(*, record_kind: str, metadata: Mapping[str, Any]) -> tuple[str, ...]:
    tags: set[str] = {"data_readiness", "evidence"}

    if record_kind == "basket":
        tags.update({"basket", "candidate", "diagnostic"})
    elif record_kind == "failure_action":
        tags.update({"failure", "policy_action", "readiness"})
    elif record_kind == "reason_record":
        tags.update({"diagnostic", "retrieval"})

    if metadata.get("symbol"):
        tags.add("identity")
    if metadata.get("preset_id"):
        tags.add("strategy_context")
    if metadata.get("hypothesis_id"):
        tags.add("hypothesis")
    if metadata.get("blocker_code"):
        tags.add("failure")
    if metadata.get("reason_code") or metadata.get("reason_codes"):
        tags.add("diagnostic")

    return tuple(sorted(tags))


def _memory_entry(
    *,
    artifact_id: str,
    record_kind: str,
    subject_id: str,
    title: str,
    text_preview: str,
    metadata: Mapping[str, Any],
) -> dict[str, Any]:
    ontology_tags = _ontology_tags_for_record(record_kind=record_kind, metadata=metadata)
    classification = classify_research_text(
        title=title,
        artifact_path=artifact_id,
        ontology_tags=ontology_tags,
        text_preview=text_preview,
    )
    resolved_entities = resolve_entities_from_text(
        title=title,
        artifact_path=artifact_id,
        text_preview=text_preview,
        ontology_tags=classification.ontology_tags,
    )
    return {
        "artifact_id": artifact_id,
        "record_kind": record_kind,
        "subject_id": subject_id,
        "title": title,
        "keywords": _tokenize(title, text_preview, metadata),
        "metadata": dict(sorted(metadata.items())),
        "ontology_tags": list(classification.ontology_tags),
        "ontology_classification": {
            "asset_class": classification.asset_class,
            "research_scope": classification.research_scope,
            "readiness_state": classification.readiness_state,
            "blocker_classes": list(classification.blocker_classes),
            "explanation": classification.explanation,
        },
        "resolved_entities": [
            {
                "entity_id": entity.entity_id,
                "entity_type": entity.entity_type,
                "label": entity.label,
                "confidence": entity.confidence,
                "ambiguity_status": entity.ambiguity_status,
                "evidence": list(entity.evidence),
            }
            for entity in resolved_entities
        ],
        "text_preview": text_preview[:280],
    }


def build_research_memory_coverage(
    *,
    repo_root: Path = Path("."),
    max_candidates: int = 15,
) -> dict[str, Any]:
    basket_report = basket_diagnosis.build_real_basket_diagnosis(
        repo_root=repo_root,
        max_candidates=max_candidates,
    )
    failure_report = failure_action.build_failure_action_from_basket(
        repo_root=repo_root,
        max_candidates=max_candidates,
    )
    reason_snapshot = reason_records.build_reason_records_snapshot(
        repo_root=repo_root,
        max_candidates=max_candidates,
    )

    basket_rows = basket_report.get("rows")
    if not isinstance(basket_rows, list):
        basket_rows = []
    failure_rows = failure_report.get("rows")
    if not isinstance(failure_rows, list):
        failure_rows = []
    reason_rows = reason_snapshot.get("records")
    if not isinstance(reason_rows, list):
        reason_rows = []

    entries: list[dict[str, Any]] = []
    for row in basket_rows:
        if not isinstance(row, Mapping):
            continue
        subject_id = str(row.get("candidate_id") or "")
        entries.append(
            _memory_entry(
                artifact_id=f"basket:{subject_id}",
                record_kind="basket",
                subject_id=subject_id,
                title=f"{row.get('symbol')} {row.get('preset_id')}",
                text_preview=(
                    f"Basket {row.get('symbol')} {row.get('preset_id')} "
                    f"{row.get('diagnosis_class')} {row.get('reason_code')}"
                ),
                metadata={
                    "symbol": row.get("symbol"),
                    "preset_id": row.get("preset_id"),
                    "hypothesis_id": row.get("hypothesis_id"),
                    "behavior_family": row.get("behavior_family"),
                    "diagnosis_class": row.get("diagnosis_class"),
                    "reason_code": row.get("reason_code"),
                },
            )
        )
    for row in failure_rows:
        if not isinstance(row, Mapping):
            continue
        subject_id = str(row.get("candidate_id") or "")
        actionability = row.get("actionability")
        if not isinstance(actionability, Mapping):
            actionability = {}
        entries.append(
            _memory_entry(
                artifact_id=f"failure:{subject_id}",
                record_kind="failure_action",
                subject_id=subject_id,
                title=f"{row.get('symbol')} {row.get('blocker_code')}",
                text_preview=(
                    f"Failure action {row.get('symbol')} {row.get('blocker_code')} "
                    f"{row.get('recommended_action')} {actionability.get('operator_explanation')}"
                ),
                metadata={
                    "symbol": row.get("symbol"),
                    "preset_id": row.get("preset_id"),
                    "hypothesis_id": row.get("hypothesis_id"),
                    "behavior_family": row.get("behavior_family"),
                    "blocker_code": row.get("blocker_code"),
                    "recommended_action": row.get("recommended_action"),
                    "actionability_status": actionability.get("status"),
                },
            )
        )
    for row in reason_rows:
        if not isinstance(row, Mapping):
            continue
        subject_id = str(row.get("subject_id") or "")
        entries.append(
            _memory_entry(
                artifact_id=f"reason:{row.get('record_id')}",
                record_kind="reason_record",
                subject_id=subject_id,
                title=f"{row.get('record_family')} {subject_id}",
                text_preview=str(row.get("reason_text") or ""),
                metadata={
                    "record_family": row.get("record_family"),
                    "reason_codes": ",".join(str(code) for code in row.get("reason_codes") or []),
                    "evidence_ref_count": len(row.get("evidence_refs") or []),
                },
            )
        )

    entries.sort(key=lambda row: (str(row["record_kind"]), str(row["artifact_id"])))
    kind_counts = Counter(str(row["record_kind"]) for row in entries)
    research_scope_counts = Counter(
        str((row.get("ontology_classification") or {}).get("research_scope") or "unknown")
        for row in entries
    )
    asset_class_counts = Counter(
        str((row.get("ontology_classification") or {}).get("asset_class") or "unknown")
        for row in entries
    )
    readiness_state_counts = Counter(
        str((row.get("ontology_classification") or {}).get("readiness_state") or "unknown")
        for row in entries
    )
    ontology_tag_counts = Counter(
        str(tag)
        for row in entries
        for tag in row.get("ontology_tags") or []
    )
    candidate_ids = sorted(
        {
            str(row.get("subject_id") or "")
            for row in entries
            if str(row.get("subject_id") or "")
        }
    )
    return {
        "schema_version": SCHEMA_VERSION,
        "report_kind": MEMORY_REPORT_KIND,
        "max_candidates": max_candidates,
        "summary": {
            "indexed_entry_count": len(entries),
            "indexed_basket_count": len(
                [row for row in entries if str(row["record_kind"]) == "basket"]
            ),
            "indexed_failure_action_count": len(
                [row for row in entries if str(row["record_kind"]) == "failure_action"]
            ),
            "indexed_reason_record_count": len(
                [row for row in entries if str(row["record_kind"]) == "reason_record"]
            ),
            "indexed_candidate_count": len(candidate_ids),
            "record_kind_counts": dict(sorted(kind_counts.items())),
            "ontology_research_scope_counts": dict(sorted(research_scope_counts.items())),
            "ontology_asset_class_counts": dict(sorted(asset_class_counts.items())),
            "ontology_readiness_state_counts": dict(sorted(readiness_state_counts.items())),
            "ontology_tag_counts": dict(sorted(ontology_tag_counts.items())),
            "memory_content_hash": _digest({"entries": entries}),
            "final_recommendation": (
                "research_memory_coverage_ready" if entries else "research_memory_coverage_missing"
            ),
            "operator_summary": (
                "Research memory coverage indexes current read-only basket, failure-action, "
                "and durable reason-record surfaces with context-only ontology classification "
                "without adding authority or runtime behavior."
            ),
        },
        "entries": entries,
        "safety_invariants": {
            "read_only": True,
            "uses_embeddings": False,
            "uses_vector_db": False,
            "uses_llm_authority": False,
            "ontology_context_only": True,
            "paper_shadow_live_forbidden": True,
            "broker_risk_execution_forbidden": True,
        },
    }


def _failure_similarity(left: Mapping[str, Any], right: Mapping[str, Any]) -> int:
    left_meta = left.get("metadata")
    right_meta = right.get("metadata")
    if not isinstance(left_meta, Mapping) or not isinstance(right_meta, Mapping):
        return 0
    score = 0
    if str(left_meta.get("blocker_code") or "") == str(right_meta.get("blocker_code") or ""):
        score += 5
    if str(left_meta.get("recommended_action") or "") == str(
        right_meta.get("recommended_action") or ""
    ):
        score += 3
    if str(left_meta.get("behavior_family") or "") == str(right_meta.get("behavior_family") or ""):
        score += 2
    if str(left_meta.get("preset_id") or "") == str(right_meta.get("preset_id") or ""):
        score += 1
    return score


def build_failure_retrieval(
    memory: Mapping[str, Any],
    *,
    top_k: int = 3,
) -> dict[str, Any]:
    entries = memory.get("entries")
    if not isinstance(entries, list):
        entries = []
    failure_entries = [
        row
        for row in entries
        if isinstance(row, Mapping)
        and str(row.get("record_kind") or "") == "failure_action"
        and str((row.get("metadata") or {}).get("recommended_action") or "")
        != "eligible_for_readonly_routing"
    ]

    retrieval_rows: list[dict[str, Any]] = []
    for entry in failure_entries:
        subject_id = str(entry.get("subject_id") or "")
        matches: list[dict[str, Any]] = []
        for candidate in failure_entries:
            other_subject = str(candidate.get("subject_id") or "")
            if other_subject == subject_id:
                continue
            score = _failure_similarity(entry, candidate)
            if score <= 0:
                continue
            matches.append(
                {
                    "subject_id": other_subject,
                    "artifact_id": candidate.get("artifact_id"),
                    "title": candidate.get("title"),
                    "score": score,
                    "blocker_code": (candidate.get("metadata") or {}).get("blocker_code"),
                    "recommended_action": (candidate.get("metadata") or {}).get(
                        "recommended_action"
                    ),
                }
            )
        matches.sort(key=lambda row: (-int(row["score"]), str(row["subject_id"])))
        retrieval_rows.append(
            {
                "subject_id": subject_id,
                "artifact_id": entry.get("artifact_id"),
                "title": entry.get("title"),
                "blocker_code": (entry.get("metadata") or {}).get("blocker_code"),
                "recommended_action": (entry.get("metadata") or {}).get("recommended_action"),
                "similar_failures": matches[:top_k],
            }
        )

    blocker_counts = Counter(str(row.get("blocker_code") or "") for row in retrieval_rows)
    return {
        "schema_version": SCHEMA_VERSION,
        "report_kind": FAILURE_REPORT_KIND,
        "summary": {
            "failure_subject_count": len(retrieval_rows),
            "retrievable_failure_subject_count": sum(
                1 for row in retrieval_rows if row.get("similar_failures")
            ),
            "blocker_counts": dict(sorted(blocker_counts.items())),
            "final_recommendation": (
                "failure_retrieval_ready" if retrieval_rows else "failure_retrieval_not_ready"
            ),
            "operator_summary": (
                "Failure retrieval provides deterministic similar-failure lookup over "
                "current read-only failure-action entries only."
            ),
        },
        "rows": retrieval_rows,
        "safety_invariants": {
            "read_only": True,
            "uses_embeddings": False,
            "uses_vector_db": False,
            "uses_llm_authority": False,
            "paper_shadow_live_forbidden": True,
            "broker_risk_execution_forbidden": True,
        },
    }


def _validate_write_target(path: Path) -> None:
    text = path.as_posix()
    if _MEMORY_PREFIX not in text and _FAILURE_PREFIX not in text:
        raise ValueError(
            f"qre_research_memory_coverage: refusing write outside allowlist: {path!r}"
        )


def write_outputs(
    memory: Mapping[str, Any],
    retrieval: Mapping[str, Any],
    *,
    repo_root: Path = Path("."),
) -> dict[str, str]:
    memory_dir = repo_root / MEMORY_OUTPUT_DIR
    failure_dir = repo_root / FAILURE_OUTPUT_DIR
    memory_dir.mkdir(parents=True, exist_ok=True)
    failure_dir.mkdir(parents=True, exist_ok=True)
    memory_path = memory_dir / LATEST_NAME
    failure_path = failure_dir / LATEST_NAME
    for target in (memory_path, failure_path):
        _validate_write_target(target)
    for path, payload in ((memory_path, memory), (failure_path, retrieval)):
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        os.replace(tmp, path)
    return {
        "memory_latest": memory_path.relative_to(repo_root).as_posix(),
        "failure_latest": failure_path.relative_to(repo_root).as_posix(),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m research.qre_research_memory_coverage",
        description="Build read-only QRE research memory coverage and failure retrieval.",
    )
    parser.add_argument("--max-candidates", type=int, default=15)
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args(argv)
    memory = build_research_memory_coverage(max_candidates=args.max_candidates)
    retrieval = build_failure_retrieval(memory)
    payload = {"memory": memory["summary"], "failure_retrieval": retrieval["summary"]}
    if args.write:
        payload["_artifact_paths"] = write_outputs(memory, retrieval)
    print(json.dumps(payload, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
