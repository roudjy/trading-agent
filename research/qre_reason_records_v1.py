from __future__ import annotations

import argparse
import hashlib
import json
import os
from collections import Counter
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any, Final

from research import qre_real_basket_diagnosis as basket_diagnosis
from research import qre_routing_readiness_from_basket as routing_readiness
from research import qre_sampling_readiness_from_basket as sampling_readiness


SCHEMA_VERSION: Final[str] = "1.0"
RECORD_KIND: Final[str] = "qre_reason_record"
MODULE_VERSION: Final[str] = "v1"
DEFAULT_OUTPUT_DIR: Final[Path] = Path("logs/qre_reason_records")
LATEST_JSONL_NAME: Final[str] = "latest.jsonl"
LATEST_META_NAME: Final[str] = "latest.meta.json"
_WRITE_PREFIX: Final[str] = "logs/qre_reason_records/"
_PRODUCTION_CATALOG_REF: Final[str] = "research/production_discovery_catalog.py"
_SOURCE_QUALITY_REF: Final[str] = "logs/qre_data_source_quality_readiness/latest.json"
_CACHE_MANIFEST_REF: Final[str] = "logs/qre_data_cache_manifest/latest.json"
_SCREENING_REF: Final[str] = "research/screening_evidence_latest.v1.json"
_CAMPAIGN_REF: Final[str] = "research/campaign_registry_latest.v1.json"
_CANDIDATE_REF: Final[str] = "research/candidate_registry_latest.v1.json"


def _bounded_list(value: Any) -> list[str]:
    if not isinstance(value, Sequence) or isinstance(value, str | bytes):
        return []
    out: list[str] = []
    for item in value:
        if not isinstance(item, str):
            continue
        text = item.strip()
        if text and text not in out:
            out.append(text[:160])
    return out[:16]


def _digest(payload: Mapping[str, Any]) -> str:
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def _record_id(surface: str, subject_id: str, inputs_digest: str) -> str:
    h = hashlib.sha256()
    h.update(surface.encode("utf-8"))
    h.update(b"\x1f")
    h.update(subject_id.encode("utf-8"))
    h.update(b"\x1f")
    h.update(inputs_digest.encode("utf-8"))
    return "qrr_" + h.hexdigest()[:16]


def _basket_evidence_refs(row: Mapping[str, Any]) -> list[str]:
    evidence = row.get("current_evidence")
    if not isinstance(evidence, Mapping):
        evidence = {}
    refs = [_PRODUCTION_CATALOG_REF]
    if int(evidence.get("source_quality_rows") or 0) > 0 or "source" in str(row.get("reason_code") or ""):
        refs.append(_SOURCE_QUALITY_REF)
    if int(evidence.get("cache_coverage_rows") or 0) > 0 or "cache" in str(row.get("reason_code") or ""):
        refs.append(_CACHE_MANIFEST_REF)
    if int(evidence.get("screening_rows") or 0) > 0:
        refs.append(_SCREENING_REF)
    if int(evidence.get("campaign_rows") or 0) > 0:
        refs.append(_CAMPAIGN_REF)
    if int(evidence.get("candidate_rows") or 0) > 0:
        refs.append(_CANDIDATE_REF)
    return refs


def _routing_evidence_refs(row: Mapping[str, Any]) -> list[str]:
    refs = [_PRODUCTION_CATALOG_REF]
    evidence = row.get("evidence_presence")
    if not isinstance(evidence, Mapping):
        evidence = {}
    if bool(evidence.get("source_quality_ready")):
        refs.append(_SOURCE_QUALITY_REF)
    if bool(evidence.get("cache_ready")):
        refs.append(_CACHE_MANIFEST_REF)
    if bool(evidence.get("screening_evidence_present")) or bool(evidence.get("oos_evidence_known")):
        refs.append(_SCREENING_REF)
    if bool(evidence.get("campaign_lineage_present")):
        refs.append(_CAMPAIGN_REF)
    if bool(evidence.get("candidate_lineage_present")):
        refs.append(_CANDIDATE_REF)
    return refs


def _sampling_evidence_refs(row: Mapping[str, Any]) -> list[str]:
    refs = _routing_evidence_refs(row)
    if str(row.get("sampling_readiness_state") or "") == "ready" and _SCREENING_REF not in refs:
        refs.append(_SCREENING_REF)
    return refs


def _reason_text(surface: str, row: Mapping[str, Any]) -> str:
    if surface == "basket_diagnosis":
        return (
            f"Basket diagnosis for {row.get('symbol')} is "
            f"{row.get('diagnosis_class')} because {row.get('reason_code')}."
        )[:300]
    if surface == "routing_readiness":
        return (
            f"Routing readiness for {row.get('symbol')} is "
            f"{row.get('routing_readiness_state')} because {row.get('primary_reason_code')}."
        )[:300]
    return (
        f"Sampling readiness for {row.get('symbol')} is "
        f"{row.get('sampling_readiness_state')} because {row.get('primary_reason_code')}."
    )[:300]


def _reason_codes(surface: str, row: Mapping[str, Any]) -> list[str]:
    if surface == "basket_diagnosis":
        return [str(row.get("reason_code") or "")] if row.get("reason_code") else []
    return [str(row.get("primary_reason_code") or "")] if row.get("primary_reason_code") else []


def _build_record(surface: str, row: Mapping[str, Any], evidence_refs: Sequence[str]) -> dict[str, Any]:
    subject_id = str(row.get("candidate_id") or "")
    inputs = {
        "surface": surface,
        "subject_id": subject_id,
        "state": (
            row.get("diagnosis_class")
            if surface == "basket_diagnosis"
            else row.get("routing_readiness_state")
            if surface == "routing_readiness"
            else row.get("sampling_readiness_state")
        ),
        "reason_codes": _reason_codes(surface, row),
        "evidence_refs": list(evidence_refs),
    }
    digest = _digest(inputs)
    return {
        "schema_version": SCHEMA_VERSION,
        "record_kind": RECORD_KIND,
        "record_family": surface,
        "record_id": _record_id(surface, subject_id, digest),
        "subject_id": subject_id,
        "reason_codes": _reason_codes(surface, row),
        "reason_text": _reason_text(surface, row),
        "evidence_refs": list(evidence_refs),
        "inputs_digest": digest,
    }


def build_reason_records_snapshot(
    *,
    repo_root: Path = Path("."),
    max_candidates: int = 15,
) -> dict[str, Any]:
    basket_rows = basket_diagnosis.build_real_basket_diagnosis(
        repo_root=repo_root,
        max_candidates=max_candidates,
    ).get("rows") or []
    routing_rows = routing_readiness.build_routing_readiness_from_basket(
        repo_root=repo_root,
        max_candidates=max_candidates,
    ).get("rows") or []
    sampling_rows = sampling_readiness.build_sampling_readiness_from_basket(
        repo_root=repo_root,
        max_candidates=max_candidates,
    ).get("rows") or []

    records: list[dict[str, Any]] = []
    skipped_missing_refs: list[dict[str, Any]] = []
    surface_counts: Counter[str] = Counter()

    for surface, rows, ref_builder in (
        ("basket_diagnosis", basket_rows, _basket_evidence_refs),
        ("routing_readiness", routing_rows, _routing_evidence_refs),
        ("sampling_readiness", sampling_rows, _sampling_evidence_refs),
    ):
        for row in rows:
            if not isinstance(row, Mapping):
                continue
            refs = _bounded_list(ref_builder(row))
            if not refs:
                skipped_missing_refs.append(
                    {
                        "surface": surface,
                        "subject_id": str(row.get("candidate_id") or ""),
                        "reason": "missing_evidence_refs",
                    }
                )
                continue
            record = _build_record(surface, row, refs)
            records.append(record)
            surface_counts.update([surface])

    records.sort(key=lambda record: (str(record["record_family"]), str(record["subject_id"])))
    return {
        "schema_version": SCHEMA_VERSION,
        "module_version": MODULE_VERSION,
        "record_kind": RECORD_KIND,
        "max_candidates": max_candidates,
        "records": records,
        "meta": {
            "record_count": len(records),
            "records_by_surface": dict(sorted(surface_counts.items())),
            "skipped_missing_refs_count": len(skipped_missing_refs),
            "skipped_missing_refs_top": skipped_missing_refs[:16],
            "final_recommendation": (
                "reason_records_v1_fail_closed_missing_refs"
                if skipped_missing_refs
                else "reason_records_v1_ready"
            ),
            "operator_summary": (
                "Durable QRE reason records v1 materialize read-only basket, routing, "
                "and sampling decisions with explicit evidence refs."
            ),
        },
        "safety_invariants": {
            "read_only": True,
            "mutates_frozen_contracts": False,
            "paper_shadow_live_forbidden": True,
            "broker_risk_execution_forbidden": True,
            "authorizes_actions": False,
        },
    }


def _validate_write_target(path: Path) -> None:
    if _WRITE_PREFIX not in path.as_posix():
        raise ValueError(f"qre_reason_records_v1: refusing write outside allowlist: {path!r}")


def write_outputs(
    snapshot: Mapping[str, Any],
    *,
    output_dir: Path = DEFAULT_OUTPUT_DIR,
    repo_root: Path = Path("."),
) -> dict[str, str]:
    base = repo_root / output_dir
    base.mkdir(parents=True, exist_ok=True)
    jsonl_path = base / LATEST_JSONL_NAME
    meta_path = base / LATEST_META_NAME
    for target in (jsonl_path, meta_path):
        _validate_write_target(target)
    lines = [
        json.dumps(record, sort_keys=True, separators=(",", ":"))
        for record in snapshot.get("records") or []
        if isinstance(record, Mapping)
    ]
    tmp_jsonl = jsonl_path.with_suffix(jsonl_path.suffix + ".tmp")
    tmp_jsonl.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
    os.replace(tmp_jsonl, jsonl_path)
    meta_payload = {
        "schema_version": snapshot.get("schema_version"),
        "module_version": snapshot.get("module_version"),
        "record_kind": snapshot.get("record_kind"),
        "max_candidates": snapshot.get("max_candidates"),
        "meta": snapshot.get("meta"),
        "safety_invariants": snapshot.get("safety_invariants"),
    }
    tmp_meta = meta_path.with_suffix(meta_path.suffix + ".tmp")
    tmp_meta.write_text(json.dumps(meta_payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    os.replace(tmp_meta, meta_path)
    return {
        "latest_jsonl": jsonl_path.relative_to(repo_root).as_posix(),
        "latest_meta": meta_path.relative_to(repo_root).as_posix(),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m research.qre_reason_records_v1",
        description="Materialize durable read-only QRE reason records v1.",
    )
    parser.add_argument("--max-candidates", type=int, default=15)
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args(argv)
    snapshot = build_reason_records_snapshot(max_candidates=args.max_candidates)
    if args.write:
        snapshot["_artifact_paths"] = write_outputs(snapshot)
    print(json.dumps(snapshot["meta"], indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
