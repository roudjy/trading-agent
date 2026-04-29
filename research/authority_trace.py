"""Authority transition trace — opt-in append-only observability sidecar.

ADR-014 §B / Phase 2 verification (audit §19.2). Makes cross-authority
transitions diagnosable without changing any policy or schema.

Default behavior: ``AuthorityTraceSink(path=None)`` is a no-op. Calling
``emit(...)`` does nothing and creates no file. Existing tests see no
new state. The sink is enabled by passing an explicit path (constructed
at the orchestrator boundary from ``RESEARCH_AUTHORITY_TRACE_PATH``).

Contract (mirrors ``research.campaign_evidence_ledger``):

- JSONL body (``authority_trace_latest.v1.jsonl``) — one event per line.
- Companion ``.meta.json`` carries the pin block (JSONL has no
  top-level header).
- Idempotent ``event_id`` (sha256 of stable fields). Replaying the same
  event produces zero new lines.
- Append-only. Crash-recovery is dedup-on-append.

Layer rules (ADR-014 §A — preserve pure-function shape of decision
modules):

- This module MUST NEVER be imported from ``research.promotion``,
  ``research.campaign_policy``, ``research.campaign_funnel_policy``,
  ``research.falsification``, ``research.falsification_reporting``,
  ``research.candidate_lifecycle``, ``research.paper_readiness``.
  Trace emission happens at *callers* (``research.run_research``,
  ``research.campaign_launcher``) so the pure modules stay pure.
- This module MUST NEVER mutate any frozen artifact. The trace sidecar
  is adjacent and additive.
- Emission ordering: emit AFTER the authoritative sidecar/artifact
  write returns successfully. Never emit-then-write.
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Final, Iterable, Literal

from research._sidecar_io import write_sidecar_atomic
from research.campaign_os_artifacts import build_pin_block, iso_utc


AUTHORITY_TRACE_SCHEMA_VERSION: Final[str] = "1.0"
AUTHORITY_TRACE_VERSION: Final[str] = "v0.1"
AUTHORITY_TRACE_META_SCHEMA_VERSION: Final[str] = "1.0"


# Closed transition vocabulary. New transitions require an ADR amendment.
TransitionKind = Literal[
    "promotion_classified",
    "candidate_registry_written",
    "falsification_payload_emitted",
    "catalog_persisted",
    "campaign_state_transitioned",
    "campaign_policy_decided",
    "stale_authority_detected",
]

TRANSITION_KINDS: Final[tuple[str, ...]] = (
    "promotion_classified",
    "candidate_registry_written",
    "falsification_payload_emitted",
    "catalog_persisted",
    "campaign_state_transitioned",
    "campaign_policy_decided",
    "stale_authority_detected",
)


# Closed authority vocabulary mirroring ADR-014 §A row labels.
SOURCE_AUTHORITIES: Final[tuple[str, ...]] = (
    "registry",
    "presets",
    "catalog",
    "promotion",
    "falsification",
    "candidate_registry",
    "campaign_registry",
    "campaign_policy",
)


# ---------------------------------------------------------------------------
# Environment-driven enablement.
# ---------------------------------------------------------------------------

ENV_VAR_TRACE_PATH: Final[str] = "RESEARCH_AUTHORITY_TRACE_PATH"


def trace_path_from_env() -> Path | None:
    """Return the trace path configured via ``RESEARCH_AUTHORITY_TRACE_PATH``.

    Returns ``None`` when the env var is unset or empty — the caller
    constructs an opt-in disabled sink in that case (no file created).
    """
    raw = os.environ.get(ENV_VAR_TRACE_PATH)
    if not raw:
        return None
    return Path(raw)


# ---------------------------------------------------------------------------
# Event construction.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class AuthorityTraceEvent:
    """One line in the authority-trace JSONL.

    The shape is intentionally narrow. Per-transition specifics belong in
    ``evidence_hash`` (sha256 of the caller's compact-JSON evidence dict),
    not in extra fields.
    """

    event_id: str
    schema_version: str
    ts_utc: str
    run_id: str | None
    transition_kind: str
    source_authority: str
    target_authority: str
    hypothesis_id: str | None
    candidate_id: str | None
    evidence_hash: str

    def to_payload(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id,
            "schema_version": self.schema_version,
            "ts_utc": self.ts_utc,
            "run_id": self.run_id,
            "transition_kind": self.transition_kind,
            "source_authority": self.source_authority,
            "target_authority": self.target_authority,
            "hypothesis_id": self.hypothesis_id,
            "candidate_id": self.candidate_id,
            "evidence_hash": self.evidence_hash,
        }


def _hash_evidence(evidence: dict[str, Any]) -> str:
    """Deterministic sha256 of the compact-JSON form of ``evidence``."""
    blob = json.dumps(evidence, sort_keys=True, ensure_ascii=False).encode(
        "utf-8"
    )
    return hashlib.sha256(blob).hexdigest()


def _build_event_id(
    *,
    run_id: str | None,
    transition_kind: str,
    source_authority: str,
    target_authority: str,
    candidate_id: str | None,
    hypothesis_id: str | None,
    ts_utc: str,
) -> str:
    """Pipe-delimited sha256 mirroring campaign_evidence_ledger.

    Stable across replays of the same logical transition: same inputs
    produce the same id, so dedup-on-append is replay-safe.
    """
    identifier = candidate_id or hypothesis_id or ""
    parts = [
        run_id if run_id is not None else "",
        transition_kind,
        source_authority,
        target_authority,
        identifier,
        ts_utc,
    ]
    raw = "|".join(parts).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def build_event(
    *,
    transition_kind: str,
    source_authority: str,
    target_authority: str,
    ts_utc: datetime,
    run_id: str | None = None,
    hypothesis_id: str | None = None,
    candidate_id: str | None = None,
    evidence: dict[str, Any] | None = None,
) -> AuthorityTraceEvent:
    """Pure event factory. Loud-fails on closed-vocabulary violations."""
    if transition_kind not in TRANSITION_KINDS:
        raise ValueError(
            f"unknown transition_kind {transition_kind!r}; "
            f"must be one of {TRANSITION_KINDS!r}"
        )
    if source_authority not in SOURCE_AUTHORITIES:
        raise ValueError(
            f"unknown source_authority {source_authority!r}; "
            f"must be one of {SOURCE_AUTHORITIES!r}"
        )
    if target_authority not in SOURCE_AUTHORITIES:
        raise ValueError(
            f"unknown target_authority {target_authority!r}; "
            f"must be one of {SOURCE_AUTHORITIES!r}"
        )
    ts_iso = iso_utc(ts_utc)
    evidence_dict = dict(evidence or {})
    event_id = _build_event_id(
        run_id=run_id,
        transition_kind=transition_kind,
        source_authority=source_authority,
        target_authority=target_authority,
        candidate_id=candidate_id,
        hypothesis_id=hypothesis_id,
        ts_utc=ts_iso,
    )
    return AuthorityTraceEvent(
        event_id=event_id,
        schema_version=AUTHORITY_TRACE_SCHEMA_VERSION,
        ts_utc=ts_iso,
        run_id=run_id,
        transition_kind=transition_kind,
        source_authority=source_authority,
        target_authority=target_authority,
        hypothesis_id=hypothesis_id,
        candidate_id=candidate_id,
        evidence_hash=_hash_evidence(evidence_dict),
    )


# ---------------------------------------------------------------------------
# Sink — wraps the JSONL path; default no-op when path is None.
# ---------------------------------------------------------------------------


def _meta_path_for(jsonl_path: Path) -> Path:
    """Companion ``.meta.json`` path adjacent to the JSONL.

    ``authority_trace_latest.v1.jsonl`` →
    ``authority_trace_latest.v1.meta.json``.
    """
    if jsonl_path.name.endswith(".jsonl"):
        meta_name = jsonl_path.name[: -len(".jsonl")] + ".meta.json"
    else:
        meta_name = jsonl_path.name + ".meta.json"
    return jsonl_path.with_name(meta_name)


@dataclass(frozen=True)
class AuthorityTraceSink:
    """Append-only trace sink. Default-disabled when ``path`` is ``None``.

    A disabled sink is a no-op: ``emit()`` does not write, does not create
    any file, and does not raise. This makes the sink safe to inject at
    every authoritative transition boundary without altering existing
    test fixtures.
    """

    path: Path | None
    git_revision: str | None = None
    _enabled_marker: dict[str, bool] = field(
        default_factory=lambda: {"meta_written": False}
    )

    @property
    def enabled(self) -> bool:
        return self.path is not None

    def emit(self, event: AuthorityTraceEvent) -> bool:
        """Append ``event`` if the sink is enabled and the id is new.

        Returns ``True`` when a new line was written, ``False`` otherwise
        (sink disabled OR replay duplicate).
        """
        if self.path is None:
            return False
        return _append_one(
            self.path,
            event,
            git_revision=self.git_revision,
            meta_marker=self._enabled_marker,
        )


def _append_one(
    path: Path,
    event: AuthorityTraceEvent,
    *,
    git_revision: str | None,
    meta_marker: dict[str, bool],
) -> bool:
    path.parent.mkdir(parents=True, exist_ok=True)
    existing_ids = {ev["event_id"] for ev in read_trace(path)}
    if event.event_id in existing_ids:
        return False
    line = json.dumps(event.to_payload(), sort_keys=True, ensure_ascii=False)
    with path.open("a", encoding="utf-8", newline="\n") as handle:
        handle.write(line)
        handle.write("\n")
    if not meta_marker.get("meta_written", False):
        write_meta(
            _meta_path_for(path),
            generated_at_utc=datetime.now(UTC),
            git_revision=git_revision,
            ledger_path=str(path),
            event_count=len(existing_ids) + 1,
        )
        meta_marker["meta_written"] = True
    return True


# ---------------------------------------------------------------------------
# IO — read + meta. Read is dedup-aware; meta is canonical pin block.
# ---------------------------------------------------------------------------


def read_trace(path: Path) -> list[dict[str, Any]]:
    """Read JSONL; deduplicate by ``event_id``; missing file → ``[]``.

    Tolerates a corrupt tail line (skipped without raising), matching the
    campaign_evidence_ledger pattern. Order: first-occurrence-wins.
    """
    if not path.exists():
        return []
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            event_id = event.get("event_id")
            if not isinstance(event_id, str) or event_id in seen:
                continue
            seen.add(event_id)
            out.append(event)
    return out


def write_meta(
    meta_path: Path,
    *,
    generated_at_utc: datetime,
    git_revision: str | None,
    ledger_path: str | None,
    event_count: int,
) -> None:
    """Emit / refresh the companion ``.meta.json`` pin block.

    Pin block declares ``additive=True`` and references ADR-014 by id;
    no consumer treats the trace sidecar as authoritative for any
    decision.
    """
    pins = build_pin_block(
        schema_version=AUTHORITY_TRACE_META_SCHEMA_VERSION,
        generated_at_utc=generated_at_utc,
        git_revision=git_revision,
        run_id=None,
        artifact_state="healthy",
    )
    payload = {
        **pins,
        "additive": True,
        "doctrine_reference": "ADR-014",
        "trace_schema_version": AUTHORITY_TRACE_SCHEMA_VERSION,
        "trace_version": AUTHORITY_TRACE_VERSION,
        "ledger_path": ledger_path,
        "event_count": int(event_count),
    }
    write_sidecar_atomic(meta_path, payload)


def append_events(
    path: Path,
    new_events: Iterable[AuthorityTraceEvent],
    *,
    git_revision: str | None = None,
) -> list[AuthorityTraceEvent]:
    """Bulk-append. Mirrors the campaign_evidence_ledger interface.

    Idempotent on ``event_id``. Caller is responsible for cross-process
    locking if used outside the run lifecycle.
    """
    sink = AuthorityTraceSink(path=path, git_revision=git_revision)
    appended: list[AuthorityTraceEvent] = []
    for event in new_events:
        if sink.emit(event):
            appended.append(event)
    return appended


__all__ = [
    "AUTHORITY_TRACE_SCHEMA_VERSION",
    "AUTHORITY_TRACE_VERSION",
    "AUTHORITY_TRACE_META_SCHEMA_VERSION",
    "ENV_VAR_TRACE_PATH",
    "TRANSITION_KINDS",
    "SOURCE_AUTHORITIES",
    "AuthorityTraceEvent",
    "AuthorityTraceSink",
    "append_events",
    "build_event",
    "read_trace",
    "trace_path_from_env",
    "write_meta",
]
