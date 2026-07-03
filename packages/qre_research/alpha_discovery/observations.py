from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

import pandas as pd

from agent.backtesting.features import resolved_feature_registry
from packages.qre_data import cache_manifest as cm
from packages.qre_data import source_quality_readiness as sqr
from packages.qre_data.dataset_catalog import materialize_data_truth
from packages.qre_research import automated_hypothesis_generation as a20
from packages.qre_research import research_memory as rm

from .contracts import DiscoveryContext, ObservationSnapshot, content_id, payload_identity


def _read_json(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        import json

        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception:
        return None
    return payload if isinstance(payload, dict) else None


def _load_manifest(repo_root: Path) -> dict[str, Any]:
    latest = _read_json(repo_root / "logs/qre_data_cache_manifest/latest.json")
    if isinstance(latest, dict) and latest:
        return latest
    return cm.build_cache_manifest(repo_root=repo_root)


def _load_source_quality(repo_root: Path, manifest: Mapping[str, Any]) -> dict[str, Any]:
    latest = _read_json(repo_root / "logs/qre_data_source_quality_readiness/latest.json")
    if isinstance(latest, dict) and latest:
        return latest
    return sqr.build_source_quality_report(manifest)


def _load_memory(repo_root: Path) -> dict[str, Any]:
    return rm.build_research_memory(repo_root=repo_root)


def _latest_cov_rows(manifest: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows = manifest.get("coverage")
    if isinstance(rows, list):
        return [dict(row) for row in rows if isinstance(row, dict)]
    return []


def _single_frame_diagnostics(repo_root: Path, rows: list[dict[str, Any]]) -> dict[str, Any]:
    if not rows:
        return {"status": "NOT_AVAILABLE"}
    row = rows[0]
    frame = row.get("__frame__")
    if not isinstance(frame, pd.DataFrame) or frame.empty:
        return {"status": "NOT_AVAILABLE", "missing_dataset_id": str(row.get("dataset_id") or "")}
    frame = frame.copy()
    if "timestamp_utc" in frame.columns:
        frame["timestamp_utc"] = pd.to_datetime(frame["timestamp_utc"], utc=True)
        frame = frame.sort_values("timestamp_utc")
    close = frame["close"].astype(float) if "close" in frame.columns else pd.Series(dtype=float)
    returns = close.pct_change().dropna() if not close.empty else pd.Series(dtype=float)
    vol = returns.rolling(10).std().dropna() if not returns.empty else pd.Series(dtype=float)
    trend = close.diff(5).dropna() if len(close) > 5 else pd.Series(dtype=float)
    latest = {
        "status": "READY" if len(frame) else "EMPTY",
        "row_count": int(len(frame)),
        "close_min": float(close.min()) if len(close) else None,
        "close_max": float(close.max()) if len(close) else None,
        "recent_return_mean": float(returns.tail(10).mean()) if len(returns) else 0.0,
        "recent_volatility": float(vol.tail(10).mean()) if len(vol) else 0.0,
        "recent_trend": float(trend.tail(5).mean()) if len(trend) else 0.0,
        "asset": str(row.get("instrument") or "unknown"),
        "timeframe": str(row.get("timeframe") or "unknown"),
    }
    latest["content_identity"] = content_id("qadm", latest)
    return latest


def build_observation_snapshot(context: DiscoveryContext) -> ObservationSnapshot:
    repo_root = context.repo_root
    manifest = _load_manifest(repo_root)
    source_quality = _load_source_quality(repo_root, manifest)
    data_truth = materialize_data_truth(repo_root)
    memory = _load_memory(repo_root)
    coverage_rows = [dict(row) for row in data_truth["catalog"].get("datasets") or [] if isinstance(row, dict)]
    selected_rows = [row for row in coverage_rows if str(row.get("timeframe") or "") and str(row.get("source_id") or "")]
    for row in selected_rows[:3]:
        partitions = [str(item) for item in row.get("partition_refs") or [] if item]
        frames: list[pd.DataFrame] = []
        for rel_path in partitions:
            path = repo_root / rel_path
            if not path.is_file():
                continue
            frame = pd.read_parquet(path)
            if "timestamp_utc" in frame.columns:
                frame = frame.copy()
                frame["timestamp_utc"] = pd.to_datetime(frame["timestamp_utc"], utc=True)
            frames.append(frame)
        if frames:
            combined = pd.concat(frames, ignore_index=True).sort_values("timestamp_utc").drop_duplicates(subset=["timestamp_utc"], keep="last")
            row["__frame__"] = combined
    diagnostics = _single_frame_diagnostics(repo_root, selected_rows)
    try:
        evidence_snapshot = a20.build_evidence_snapshot(repo_root=repo_root)
    except Exception:
        evidence_snapshot = {"summary": {}, "rows": []}
    try:
        opportunities = a20.detect_opportunities(repo_root=repo_root)
    except Exception:
        opportunities = {"summary": {}, "rows": []}
    registry = resolved_feature_registry()
    primitive_inventory = {
        "resolved_feature_registry_version": "1.0",
        "feature_count": len(registry),
        "available_primitives": sorted(registry),
    }
    executor_inventory = {
        "canonical_engine": "agent.backtesting.engine.BacktestEngine",
        "thin_contract": "agent.backtesting.thin_strategy",
        "campaign_path": "canonical_backtesting_engine",
    }
    memory_matches = rm.retrieve(
        memory,
        "trend volatility breakout reversal mean reversion regime",
        limit=5,
    )
    active_contradictions = [
        row for row in memory.get("entries", []) if isinstance(row, Mapping) and "contradiction" in row.get("ontology_tags", [])
    ]
    resolved_contradictions = [
        row for row in memory.get("entries", []) if isinstance(row, Mapping) and "resolved" in str(row.get("title") or "").lower()
    ]
    regime_diagnostics = {
        "regime_signature": [
            str(diagnostics.get("recent_trend") or 0.0)[:8],
            str(diagnostics.get("recent_volatility") or 0.0)[:8],
        ],
        "latest_complete_bar_by_asset_timeframe": {
            f"{(row.get('instrument_ids') or ['unknown'])[0]}|{row.get('timeframe')}": str(row.get("complete_bar_end") or "")
            for row in coverage_rows
            if row.get("timeframe")
        },
    }
    current_queue = list((opportunities.get("rows") or [])[:3]) if isinstance(opportunities, dict) else []
    recent_terminal_outcomes = [
        {
            "artifact": "research_memory",
            "title": str(entry.get("title") or ""),
            "record_kind": str(entry.get("record_kind") or ""),
        }
        for entry in memory_matches[:3]
    ]
    mechanism_coverage = {
        "from_evidence_snapshot": evidence_snapshot.get("summary", {}),
        "opportunity_count": len(opportunities.get("rows") or []) if isinstance(opportunities, dict) else 0,
    }
    try:
        from packages.qre_research import automated_strategy_generation as asg

        resolved_catalog = asg.build_resolved_strategy_catalog(repo_root)
        resolved_strategy_count = len(resolved_catalog.get("rows") or [])
    except Exception:
        resolved_strategy_count = 0
    behavior_family_coverage = {
        "resolved_strategy_count": resolved_strategy_count,
    }
    snapshot_core = {
        "manifest": manifest,
        "source_quality": source_quality,
        "diagnostics": diagnostics,
        "opportunities": opportunities,
        "memory_identity": memory.get("summary", {}).get("memory_content_hash"),
    }
    snapshot_id = content_id("qos", snapshot_core)
    return ObservationSnapshot(
        observation_snapshot_id=snapshot_id,
        schema_version="1.0",
        policy_version="qre_alpha_discovery_mvp_v2",
        market_diagnostics=diagnostics,
        regime_diagnostics=regime_diagnostics,
        cross_asset_diagnostics={"status": "NOT_AVAILABLE"},
        data_coverage={
            "coverage_rows": len(coverage_rows),
            "ready_rows": len(selected_rows),
            "research_ready": any(str(row.get("highest_admissible_tier") or "") in {"EMPIRICAL_SCREENING", "LOCKED_OOS_VALIDATION"} for row in coverage_rows),
        },
        source_quality={
            "summary": source_quality.get("summary", {}),
            "sources": source_quality.get("sources", []),
        },
        identity_readiness=str(
            source_quality.get("summary", {}).get("status") or "UNKNOWN"
        ),
        current_queue=current_queue,
        recent_terminal_outcomes=recent_terminal_outcomes,
        active_contradictions=[dict(row) for row in active_contradictions[:5]],
        resolved_contradictions=[dict(row) for row in resolved_contradictions[:5]],
        mechanism_coverage=mechanism_coverage,
        behavior_family_coverage=behavior_family_coverage,
        primitive_inventory=primitive_inventory,
        executor_inventory=executor_inventory,
        relevant_research_memory={
            "summary": memory.get("summary", {}),
            "matches": memory_matches,
        },
        content_identity=payload_identity(snapshot_core, prefix="qos"),
    )
