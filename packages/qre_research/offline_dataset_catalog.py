"""Offline-only dataset admission catalog for governed QRE replay."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

SourceMode = Literal["offline_fixture", "offline_sample", "offline_cached"]
AdmissionStatus = Literal["ADMITTED", "BLOCKED", "REVIEW_REQUIRED"]

SCHEMA_VERSION = 1
REPORT_KIND = "qre_offline_dataset_catalog"
SOURCE_MODES: tuple[str, ...] = ("offline_fixture", "offline_sample", "offline_cached")
ADMISSION_STATUSES: tuple[str, ...] = ("ADMITTED", "BLOCKED", "REVIEW_REQUIRED")


def authority_denial() -> dict[str, bool]:
    return {
        "offline_only": True,
        "external_fetching": False,
        "shadow_authority": False,
        "paper_authority": False,
        "live_authority": False,
        "broker_authority": False,
        "risk_authority": False,
        "order_authority": False,
        "capital_allocation_authority": False,
    }


@dataclass(frozen=True, slots=True)
class OfflineDatasetCatalogEntry:
    dataset_id: str
    name: str
    source_mode: SourceMode
    provider_or_source: str
    source_identity: str
    symbol_scope: tuple[str, ...]
    timeframe: str
    date_range: dict[str, str]
    local_reference: str
    dataset_fingerprint: str
    quality_status: str
    admission_status: AdmissionStatus
    block_reasons: tuple[str, ...]
    operator_notes: str
    created_at_utc: str
    authority: dict[str, bool]

    def as_dict(self) -> dict[str, object]:
        return {
            "dataset_id": self.dataset_id,
            "name": self.name,
            "source_mode": self.source_mode,
            "provider_or_source": self.provider_or_source,
            "source_identity": self.source_identity,
            "symbol_scope": list(self.symbol_scope),
            "timeframe": self.timeframe,
            "date_range": dict(self.date_range),
            "local_reference": self.local_reference,
            "dataset_fingerprint": self.dataset_fingerprint,
            "quality_status": self.quality_status,
            "admission_status": self.admission_status,
            "block_reasons": list(self.block_reasons),
            "operator_notes": self.operator_notes,
            "created_at_utc": self.created_at_utc,
            "authority": dict(self.authority),
        }

    def admission_decision(self) -> dict[str, object]:
        source_approved = bool(self.source_identity)
        data_admitted = self.admission_status == "ADMITTED" and self.quality_status == "passed"
        decision = "admitted" if source_approved and data_admitted else "blocked"
        reason = "ADMITTED"
        if not source_approved:
            reason = "SOURCE_NOT_APPROVED"
        elif not data_admitted:
            reason = "BLOCKED_DATA_NOT_ADMITTED"
        return {
            "dataset_id": self.dataset_id,
            "source_mode": self.source_mode,
            "dataset_admitted": data_admitted,
            "source_approved": source_approved,
            "decision": decision,
            "decision_reason": reason,
            "dataset_fingerprint": self.dataset_fingerprint,
            "source_provenance": f"{self.source_mode}:source_manifest:{self.source_identity}",
            "data_provenance": f"{self.source_mode}:dataset_boundary:{self.local_reference}",
            "block_reasons": list(self.block_reasons),
            "authority": dict(self.authority),
        }


@dataclass(frozen=True, slots=True)
class OfflineDatasetCatalog:
    entries: tuple[OfflineDatasetCatalogEntry, ...]

    def as_dict(self) -> dict[str, object]:
        return {
            "schema_version": SCHEMA_VERSION,
            "report_kind": REPORT_KIND,
            "entries": [entry.as_dict() for entry in self.entries],
        }

    def lookup(self, dataset_id: str) -> OfflineDatasetCatalogEntry:
        for entry in self.entries:
            if entry.dataset_id == dataset_id:
                return entry
        raise KeyError(dataset_id)


def _required_string(data: dict[str, object], key: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value:
        raise ValueError(f"missing_{key}")
    return value


def _entry_from_dict(data: dict[str, object]) -> OfflineDatasetCatalogEntry:
    source_mode = _required_string(data, "source_mode")
    if source_mode not in SOURCE_MODES:
        raise ValueError(f"unknown_source_mode:{source_mode}")
    admission_status = _required_string(data, "admission_status")
    if admission_status not in ADMISSION_STATUSES:
        raise ValueError(f"unknown_admission_status:{admission_status}")
    authority = data.get("authority")
    if authority != authority_denial():
        raise ValueError("invalid_authority_denial")
    symbol_scope = data.get("symbol_scope", data.get("asset_scope"))
    if not isinstance(symbol_scope, list) or not all(isinstance(item, str) and item for item in symbol_scope):
        raise ValueError("missing_symbol_scope")
    date_range = data.get("date_range")
    if not isinstance(date_range, dict) or not date_range:
        raise ValueError("missing_date_range")
    block_reasons = data.get("block_reasons", [])
    if not isinstance(block_reasons, list) or not all(isinstance(reason, str) for reason in block_reasons):
        raise ValueError("invalid_block_reasons")
    entry = OfflineDatasetCatalogEntry(
        dataset_id=_required_string(data, "dataset_id"),
        name=_required_string(data, "name"),
        source_mode=source_mode,  # type: ignore[arg-type]
        provider_or_source=_required_string(data, "provider_or_source"),
        source_identity=str(data.get("source_identity", "")),
        symbol_scope=tuple(symbol_scope),
        timeframe=_required_string(data, "timeframe"),
        date_range={str(key): str(value) for key, value in date_range.items()},
        local_reference=_required_string(data, "local_reference"),
        dataset_fingerprint=str(data.get("dataset_fingerprint", "")),
        quality_status=_required_string(data, "quality_status"),
        admission_status=admission_status,  # type: ignore[arg-type]
        block_reasons=tuple(block_reasons),
        operator_notes=str(data.get("operator_notes", "")),
        created_at_utc=_required_string(data, "created_at_utc"),
        authority=authority,
    )
    _validate_entry(entry)
    return entry


def _validate_entry(entry: OfflineDatasetCatalogEntry) -> None:
    if not entry.source_identity:
        raise ValueError(f"missing_source_identity:{entry.dataset_id}")
    if entry.admission_status == "ADMITTED" and not entry.dataset_fingerprint:
        raise ValueError(f"missing_dataset_fingerprint:{entry.dataset_id}")
    if entry.admission_status == "ADMITTED" and entry.quality_status != "passed":
        raise ValueError(f"admitted_dataset_quality_not_passed:{entry.dataset_id}")
    if entry.admission_status != "ADMITTED" and not entry.block_reasons:
        raise ValueError(f"blocked_dataset_missing_reasons:{entry.dataset_id}")


def load_catalog(path: Path) -> OfflineDatasetCatalog:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if payload.get("schema_version") != SCHEMA_VERSION:
        raise ValueError("unsupported_schema_version")
    entries = payload.get("entries")
    if not isinstance(entries, list):
        raise ValueError("missing_entries")
    parsed = tuple(_entry_from_dict(entry) for entry in entries if isinstance(entry, dict))
    if len(parsed) != len(entries):
        raise ValueError("invalid_entry")
    ids = [entry.dataset_id for entry in parsed]
    if len(ids) != len(set(ids)):
        raise ValueError("duplicate_dataset_id")
    return OfflineDatasetCatalog(entries=parsed)


__all__ = [
    "ADMISSION_STATUSES",
    "REPORT_KIND",
    "SCHEMA_VERSION",
    "SOURCE_MODES",
    "AdmissionStatus",
    "OfflineDatasetCatalog",
    "OfflineDatasetCatalogEntry",
    "SourceMode",
    "authority_denial",
    "load_catalog",
]
