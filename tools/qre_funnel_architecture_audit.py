from __future__ import annotations

import argparse
import ast
import contextlib
import json
import os
import re
import sys
import tempfile
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Final

REPO_ROOT_FOR_IMPORT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT_FOR_IMPORT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT_FOR_IMPORT))

from packages.qre_research.architecture_registry import (  # noqa: E402
    AUTHORITY_FLAGS,
    registry_as_dict,
    registry_entries,
    registry_summary,
    validate_closed_world_audit,
    validate_registry,
)
from packages.qre_research.funnel_classification import (  # noqa: E402
    classification_summary,
    classifications_as_dict,
)

REPORT_KIND: Final[str] = "qre_funnel_architecture_audit"
SCHEMA_VERSION: Final[int] = 1
DEFAULT_OUTPUT_DIR: Final[Path] = Path("logs/qre_funnel_architecture_audit")
SAFETY: Final[dict[str, bool]] = {
    "audit_only": True,
    "runtime_behavior_changed": False,
    "created_candidates": False,
    "created_strategies": False,
    "created_presets": False,
    "created_campaigns": False,
    "ran_screening": False,
    "trading_authority": False,
    "validation_authority": False,
    "paper_authority": False,
    "shadow_authority": False,
    "live_authority": False,
}
KEYWORDS: Final[tuple[str, ...]] = (
    "hypothesis",
    "candidate",
    "strategy",
    "preset",
    "campaign",
    "screening",
    "evidence",
    "ledger",
    "feedback",
    "lesson",
    "memory",
    "digest",
    "registry",
    "matrix",
    "source",
    "snapshot",
    "dataset",
    "provider",
)
PROVIDER_TERMS: Final[tuple[str, ...]] = (
    "tiingo",
    "yfinance",
    "alpaca",
    "binance",
    "kraken",
    "coinbase",
    "crypto",
    "equities",
    "bars.csv",
    "source_id",
    "source_snapshot_id",
    "data/imports",
    "provider",
    "dataset",
)
CANONICAL_OBJECTS: Final[tuple[str, ...]] = (
    "DataProvider",
    "SourceManifest",
    "SourceSnapshot",
    "DatasetFingerprint",
    "ObservationSnapshot",
    "Hypothesis",
    "HypothesisSeed",
    "ResearchInputContract",
    "CandidateSpec",
    "StrategySpec",
    "StrategyIR",
    "PresetSpec",
    "CampaignSpec",
    "CampaignRun",
    "ScreeningResult",
    "EvidencePack",
    "EvidenceLedger",
    "Disposition",
    "FeedbackRecord",
    "LessonMemory",
    "ResearchMemory",
    "DailyDigestInput",
    "OperatorSummary",
    "RegistryEntry",
    "StrategyMatrixRow",
)
TEXT_SUFFIXES: Final[set[str]] = {".py", ".md", ".txt", ".json", ".yaml", ".yml", ".toml", ".csv"}


def _utcnow() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _stable(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _stable(value[key]) for key in sorted(value)}
    if isinstance(value, list | tuple):
        return [_stable(item) for item in value]
    return value


def _json(value: Any) -> str:
    return json.dumps(_stable(value), indent=2, sort_keys=True, ensure_ascii=True) + "\n"


def _rel(path: Path, root: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def _iter_text_files(root: Path) -> list[Path]:
    excluded = {
        ".git",
        ".venv",
        "__pycache__",
        ".pytest_cache",
        "node_modules",
        "logs",
        "data",
        "generated_research",
    }
    files: list[Path] = []
    for path in root.rglob("*"):
        if any(part in excluded for part in path.parts):
            continue
        if path.is_file() and path.suffix.lower() in TEXT_SUFFIXES:
            files.append(path)
    return sorted(files)


def _read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8-sig")
    except UnicodeDecodeError:
        return path.read_text(encoding="utf-8", errors="ignore")


def _module_name(path: Path, root: Path) -> str | None:
    if path.suffix != ".py":
        return None
    rel = path.resolve().relative_to(root.resolve()).with_suffix("")
    parts = list(rel.parts)
    if parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)


def _imports(path: Path, root: Path) -> list[str]:
    try:
        tree = ast.parse(_read(path))
    except SyntaxError:
        return []
    names: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.append(node.module)
    local = []
    for name in names:
        if name.startswith(("research", "agent", "packages", "apps", "tools")) or name == "registry":
            local.append(name)
    return sorted(set(local))


def _artifact_literals(text: str) -> list[str]:
    patterns = (
        r"logs/[A-Za-z0-9_\-/\.]+",
        r"research/[A-Za-z0-9_\-/\.]+",
        r"generated_research/[A-Za-z0-9_\-/\.]+",
        r"data/imports/[A-Za-z0-9_\-/\.]+",
    )
    values: set[str] = set()
    for pattern in patterns:
        values.update(match.group(0).rstrip("'\")`,") for match in re.finditer(pattern, text))
    return sorted(values)


def scan_repo(root: Path) -> dict[str, Any]:
    files = _iter_text_files(root)
    records: list[dict[str, Any]] = []
    module_index: dict[str, str] = {}
    for path in files:
        rel = _rel(path, root)
        text = _read(path)
        module = _module_name(path, root)
        if module:
            module_index[module] = rel
        records.append(
            {
                "path": rel,
                "suffix": path.suffix.lower(),
                "module": module,
                "text": text,
                "imports": _imports(path, root) if path.suffix == ".py" else [],
                "artifacts": _artifact_literals(text),
                "keywords": [term for term in KEYWORDS if term in rel.lower() or term in text.lower()],
            }
        )
    return {"files": records, "module_index": module_index}


def _matching(scan: dict[str, Any], *needles: str) -> list[str]:
    out = []
    for record in scan["files"]:
        haystack = (record["path"] + "\n" + record["text"]).lower()
        if all(needle.lower() in haystack for needle in needles):
            out.append(record["path"])
    return sorted(set(out))


def build_funnel_inventory(scan: dict[str, Any]) -> list[dict[str, Any]]:
    def exists(path: str) -> bool:
        return any(record["path"] == path for record in scan["files"])

    funnels: list[dict[str, Any]] = []
    tiingo_modules = [
        path
        for path in (
            "research/qre_tiingo_hypothesis_generator_e2e.py",
            "research/qre_tiingo_hypothesis_lifecycle.py",
            "research/qre_tiingo_candidate_research_loop.py",
        )
        if exists(path)
    ]
    if tiingo_modules:
        funnels.append(
            _funnel(
                funnel_id="tiingo_hypothesis_candidate_research_mini_loop",
                name="Tiingo hypothesis/candidate research mini-loop",
                description="Provider-specific research-only loop from Tiingo evidence through lifecycle, candidate specs, screening, evidence ledger, feedback, and next-run feedback consumption.",
                modules=tiingo_modules,
                tests=_matching(scan, "test_qre_tiingo"),
                docs=_matching(scan, "tiingo_candidate_research_loop"),
                input_artifacts=[
                    "logs/qre_tiingo_hypothesis_generator_e2e/latest.json",
                    "logs/qre_tiingo_hypothesis_lifecycle/latest.json",
                    "data/imports/tiingo_eod_equities_free/tiingo_eod_etf_20210101_20251231/bars.csv",
                ],
                output_artifacts=[
                    "logs/qre_tiingo_candidate_research_loop/latest.json",
                    "logs/qre_tiingo_candidate_research_loop/evidence_ledger.jsonl",
                    "logs/qre_tiingo_candidate_research_loop/feedback_records.jsonl",
                ],
                canonical_objects=["HypothesisSeed", "ResearchInputContract", "CandidateSpec", "ScreeningResult", "EvidenceLedger", "FeedbackRecord"],
                provider_specificity="provider_specific",
                canonicality="provider_adapter",
                loop_claim="mini_loop",
                runtime_authority={"creates_candidates": True, "runs_screening": True},
                upstream_dependencies=["Tiingo source snapshot", "Tiingo lifecycle artifact"],
                downstream_dependencies=["daily status digest observability"],
                status_recommendation="KEEP_AS_PROVIDER_ADAPTER",
                evidence=tiingo_modules,
            )
        )
    if exists("research/qre_daily_status_digest.py"):
        funnels.append(
            _funnel(
                funnel_id="daily_status_digest_observability",
                name="Daily status digest / observability funnel",
                description="Read-only digest aggregator over research sidecars and governance artifacts.",
                modules=["research/qre_daily_status_digest.py"],
                tests=_matching(scan, "test_qre_daily_status_digest"),
                docs=_matching(scan, "daily status digest"),
                input_artifacts=["logs/**/latest.json"],
                output_artifacts=["logs/qre_daily_status_digest/latest.json", "logs/qre_daily_status_digest/operator_summary.md"],
                canonical_objects=["DailyDigestInput", "OperatorSummary"],
                provider_specificity="mixed",
                canonicality="observability_only",
                loop_claim="observability_only",
                runtime_authority={},
                upstream_dependencies=["research sidecars"],
                downstream_dependencies=["operator"],
                status_recommendation="OBSERVABILITY_ONLY",
                evidence=["research/qre_daily_status_digest.py"],
            )
        )
    if exists("research/run_research.py") or exists("registry.py"):
        funnels.append(
            _funnel(
                funnel_id="run_research_registry_matrix",
                name="run_research / registry / strategy_matrix funnel",
                description="Legacy or canonical backtest output funnel around registry, strategy execution, research_latest, and strategy_matrix.",
                modules=[path for path in ("research/run_research.py", "registry.py", "agent/backtesting/strategies.py") if exists(path)],
                tests=_matching(scan, "run_research"),
                docs=_matching(scan, "strategy_matrix"),
                input_artifacts=["registry.py", "agent/backtesting/strategies.py"],
                output_artifacts=["research/research_latest.json", "research/strategy_matrix.csv"],
                canonical_objects=["RegistryEntry", "StrategyMatrixRow"],
                provider_specificity="mixed",
                canonicality="unknown",
                loop_claim="partial_loop",
                runtime_authority={"creates_strategies": False},
                upstream_dependencies=["strategy registry"],
                downstream_dependencies=["research reports"],
                status_recommendation="UNKNOWN_REQUIRES_OPERATOR_DECISION",
                evidence=["research/research_latest.json", "research/strategy_matrix.csv"],
            )
        )
    alpha_modules = [record["path"] for record in scan["files"] if "alpha" in record["path"].lower() or "strategy_ir" in record["text"].lower()]
    campaign_modules = [record["path"] for record in scan["files"] if "campaign" in record["path"].lower() and record["suffix"] == ".py"]
    lesson_modules = [record["path"] for record in scan["files"] if any(term in record["path"].lower() for term in ("lesson", "memory", "disposition")) and record["suffix"] == ".py"]
    if alpha_modules or campaign_modules or lesson_modules:
        funnels.append(
            _funnel(
                funnel_id="alpha_discovery_strategy_ir_campaign_lesson",
                name="Alpha discovery / Strategy IR / campaign / lesson funnel",
                description="Suspected broader discovery funnel spanning alpha discovery, strategy IR semantics, campaign planning, dispositions, lessons, and memory.",
                modules=sorted(set(alpha_modules + campaign_modules + lesson_modules))[:80],
                tests=_matching(scan, "campaign") + _matching(scan, "lesson"),
                docs=_matching(scan, "campaign") + _matching(scan, "memory"),
                input_artifacts=["generated_research/**", "logs/**"],
                output_artifacts=["generated_research/**", "logs/**"],
                canonical_objects=["StrategyIR", "CampaignSpec", "EvidencePack", "Disposition", "LessonMemory", "ResearchMemory"],
                provider_specificity="mixed",
                canonicality="unknown",
                loop_claim="partial_loop",
                runtime_authority={"creates_campaigns": True},
                upstream_dependencies=["source authority", "candidate or strategy specs"],
                downstream_dependencies=["memory/lesson stores"],
                status_recommendation="BRIDGE_TO_CANONICAL",
                evidence=sorted(set(alpha_modules + campaign_modules + lesson_modules))[:20],
            )
        )
    smoke = [record["path"] for record in scan["files"] if "smoke" in record["path"].lower() or "fixture" in record["path"].lower()]
    if smoke:
        funnels.append(
            _funnel(
                funnel_id="test_smoke_fixture_funnels",
                name="Legacy or smoke/test-only funnel patterns",
                description="Test fixtures and smoke paths that can mimic funnel semantics without owning production contracts.",
                modules=[],
                tests=smoke[:80],
                docs=[],
                input_artifacts=[],
                output_artifacts=[],
                canonical_objects=[],
                provider_specificity="unknown",
                canonicality="test_fixture_only",
                loop_claim="unknown",
                runtime_authority={},
                upstream_dependencies=[],
                downstream_dependencies=[],
                status_recommendation="TEST_FIXTURE_ONLY",
                evidence=smoke[:20],
            )
        )
    return funnels


def _funnel(**kwargs: Any) -> dict[str, Any]:
    authority = {
        "creates_candidates": False,
        "creates_strategies": False,
        "creates_presets": False,
        "creates_campaigns": False,
        "runs_screening": False,
        "runs_validation": False,
        "trading_authority": False,
    }
    authority.update(kwargs.pop("runtime_authority", {}))
    return {"entrypoints": kwargs.get("modules", []), "runtime_authority": authority, **kwargs}


def build_contract_map(scan: dict[str, Any], funnels: list[dict[str, Any]]) -> dict[str, Any]:
    producers: dict[str, list[str]] = defaultdict(list)
    consumers: dict[str, list[str]] = defaultdict(list)
    artifact_paths: dict[str, set[str]] = defaultdict(set)
    for record in scan["files"]:
        text = record["text"].lower()
        path = record["path"]
        for obj in CANONICAL_OBJECTS:
            token = obj.lower()
            snake = re.sub(r"(?<!^)(?=[A-Z])", "_", obj).lower()
            if token in text or snake in text or snake in path.lower():
                if any(word in text for word in ("write", "emit", "produce", "return", "build_", "materialize")):
                    producers[obj].append(path)
                if any(word in text for word in ("read", "consume", "input", "load", "parse")):
                    consumers[obj].append(path)
                for artifact in record["artifacts"]:
                    artifact_paths[obj].add(artifact)
    recommended_owner = {
        "CandidateSpec": "research/qre_tiingo_candidate_research_loop.py",
        "HypothesisSeed": "research/qre_tiingo_hypothesis_lifecycle.py",
        "EvidenceLedger": "research/qre_tiingo_candidate_research_loop.py",
        "FeedbackRecord": "research/qre_tiingo_candidate_research_loop.py",
        "DailyDigestInput": "research/qre_daily_status_digest.py",
        "OperatorSummary": "research/qre_daily_status_digest.py",
        "RegistryEntry": "registry.py",
        "StrategyMatrixRow": "research/strategy_matrix.csv",
    }
    contract_map = {}
    for obj in CANONICAL_OBJECTS:
        prod = sorted(set(producers[obj]))
        cons = sorted(set(consumers[obj]))
        owner = recommended_owner.get(obj)
        status = "present" if prod or cons or owner else "missing"
        if obj in {"StrategySpec", "StrategyIR", "PresetSpec", "CampaignSpec", "EvidencePack", "LessonMemory", "ResearchMemory"} and len(prod) > 1:
            status = "ambiguous"
        provider_findings = [
            path for path in sorted(set(prod + cons)) if any(term in path.lower() for term in ("tiingo", "yfinance", "binance", "crypto"))
        ]
        duplicate = []
        if obj in {"Hypothesis", "CandidateSpec", "EvidenceLedger", "FeedbackRecord", "CampaignSpec"} and len(prod) > 1:
            duplicate.append("multiple producer modules mention or produce equivalent semantics")
        action = "KEEP"
        if status == "missing":
            action = "DEFINE_CANONICAL_SCHEMA"
        elif status == "ambiguous" or duplicate:
            action = "OPERATOR_DECISION_REQUIRED"
        elif provider_findings and obj not in {"SourceSnapshot", "DatasetFingerprint", "HypothesisSeed"}:
            action = "GENERALIZE"
        contract_map[obj] = {
            "object_name": obj,
            "status": status,
            "canonical_owner_module": owner or ("ambiguous" if prod else "missing"),
            "producer_modules": prod[:50],
            "consumer_modules": cons[:50],
            "artifact_paths": sorted(artifact_paths[obj])[:50],
            "provider_agnostic_expected": obj not in {"DataProvider", "SourceManifest", "SourceSnapshot", "DatasetFingerprint"},
            "provider_specific_current": bool(provider_findings),
            "hardcoded_provider_findings": provider_findings[:50],
            "duplicate_names_or_semantics": duplicate,
            "recommended_action": action,
        }
    contract_map["_canonical_answers"] = {
        "Hypothesis": contract_map["Hypothesis"]["canonical_owner_module"],
        "CandidateSpec": contract_map["CandidateSpec"]["canonical_owner_module"],
        "StrategySpec_or_StrategyIR": {
            "StrategySpec": contract_map["StrategySpec"]["canonical_owner_module"],
            "StrategyIR": contract_map["StrategyIR"]["canonical_owner_module"],
        },
        "PresetSpec": contract_map["PresetSpec"]["canonical_owner_module"],
        "CampaignSpec": contract_map["CampaignSpec"]["canonical_owner_module"],
        "EvidencePack_or_EvidenceLedger": {
            "EvidencePack": contract_map["EvidencePack"]["canonical_owner_module"],
            "EvidenceLedger": contract_map["EvidenceLedger"]["canonical_owner_module"],
        },
        "FeedbackRecord_or_LessonMemory": {
            "FeedbackRecord": contract_map["FeedbackRecord"]["canonical_owner_module"],
            "LessonMemory": contract_map["LessonMemory"]["canonical_owner_module"],
        },
    }
    return contract_map


def classify_provider_reference(path: str, line: str) -> str:
    lowered = (path + " " + line).lower()
    if "test" in lowered or "fixture" in lowered:
        return "allowed_test_fixture_reference"
    if path.endswith(".md"):
        return "allowed_doc_example_reference"
    if any(term in lowered for term in ("source_manifest", "source_resolution", "source snapshot", "source_snapshot", "datasetfingerprint", "data_profile")):
        return "allowed_source_manifest_reference" if "manifest" in lowered else "allowed_provenance_reference"
    if any(term in lowered for term in ("adapter", "ingest", "imports", "provider", "tiingo_hypothesis_generator", "tiingo_hypothesis_lifecycle")):
        return "allowed_adapter_reference"
    if any(term in lowered for term in ("preset", "campaign admission", "promotion", "readiness", "registry")):
        return "forbidden_provider_coupling"
    if any(term in lowered for term in ("candidate", "strategy", "campaign", "evidence", "feedback")):
        return "suspicious_layer_leak"
    return "allowed_provenance_reference"


def build_provider_leakage_report(scan: dict[str, Any]) -> dict[str, Any]:
    findings = []
    counts: Counter[str] = Counter()
    for record in scan["files"]:
        for lineno, line in enumerate(record["text"].splitlines(), start=1):
            if not any(term in line.lower() for term in PROVIDER_TERMS):
                continue
            classification = classify_provider_reference(record["path"], line)
            counts[classification] += 1
            findings.append(
                {
                    "file": record["path"],
                    "line": lineno,
                    "term": next(term for term in PROVIDER_TERMS if term in line.lower()),
                    "classification": classification,
                    "excerpt": line.strip()[:240],
                }
            )
    summary = {key: counts[key] for key in (
        "allowed_adapter_reference",
        "allowed_source_manifest_reference",
        "allowed_provenance_reference",
        "allowed_test_fixture_reference",
        "allowed_doc_example_reference",
        "suspicious_layer_leak",
        "forbidden_provider_coupling",
    )}
    return {"provider_leakage_findings": findings[:1000], "summary": summary}


def build_hardcoded_coupling_report(scan: dict[str, Any]) -> dict[str, Any]:
    findings = []
    idx = 0
    for record in scan["files"]:
        if record["suffix"] != ".py":
            continue
        layer = "generic"
        if "tiingo" in record["path"].lower():
            layer = "provider_adapter"
        if "daily_status_digest" in record["path"]:
            layer = "observability"
        for lineno, line in enumerate(record["text"].splitlines(), start=1):
            lowered = line.lower()
            if "logs/" in lowered or "data/imports" in lowered:
                idx += 1
                findings.append(
                    {
                        "finding_id": f"coupling_{idx:04d}",
                        "severity": "info" if layer in {"provider_adapter", "observability"} else "warning",
                        "file": record["path"],
                        "line": lineno,
                        "pattern": "hardcoded_artifact_path",
                        "layer": layer,
                        "why_it_matters": "Hardcoded artifact paths can couple layers directly unless documented as sidecar or adapter contracts.",
                        "recommended_fix": "Route through a canonical contract resolver or mark as sidecar/observability-only.",
                    }
                )
            if "from research.qre_tiingo" in lowered and "tiingo" not in record["path"].lower():
                idx += 1
                findings.append(
                    {
                        "finding_id": f"coupling_{idx:04d}",
                        "severity": "warning",
                        "file": record["path"],
                        "line": lineno,
                        "pattern": "generic_imports_provider_specific_module",
                        "layer": layer,
                        "why_it_matters": "Provider-specific implementation can leak into provider-agnostic logic.",
                        "recommended_fix": "Depend on a provider-agnostic interface or artifact contract.",
                    }
                )
    return {"hardcoded_coupling_findings": findings[:1000]}


def build_dependency_graph(scan: dict[str, Any], funnels: list[dict[str, Any]], contract_map: dict[str, Any], provider_report: dict[str, Any]) -> dict[str, Any]:
    nodes: dict[str, dict[str, Any]] = {}
    edges: list[dict[str, Any]] = []

    def node(node_id: str, kind: str) -> None:
        nodes[node_id] = {"id": node_id, "node_type": kind}

    def edge(source: str, target: str, edge_type: str, classification: str, evidence: list[str]) -> None:
        node(source, source.split(":", 1)[0])
        node(target, target.split(":", 1)[0])
        edges.append({"source": source, "target": target, "edge_type": edge_type, "classification": classification, "evidence": evidence})

    for funnel in funnels:
        fid = "funnel:" + funnel["funnel_id"]
        node(fid, "funnel")
        for module in funnel["modules"]:
            edge("module:" + module, fid, "claims_loop", funnel["canonicality"], [module])
        for artifact in funnel["input_artifacts"]:
            edge("artifact:" + artifact, fid, "consumes", "adapter" if "tiingo" in artifact else "unknown", [artifact])
        for artifact in funnel["output_artifacts"]:
            edge(fid, "artifact:" + artifact, "produces", "sidecar" if artifact.startswith("logs/") else "canonical", [artifact])
        for doc in funnel["docs"]:
            edge("doc:" + doc, fid, "documents", "observability" if "digest" in funnel["funnel_id"] else "unknown", [doc])
        for test in funnel["tests"]:
            edge("test:" + test, fid, "tests", "test", [test])
    for left_index, left in enumerate(funnels):
        for right in funnels[left_index + 1 :]:
            if "observability" in {left["canonicality"], right["canonicality"]}:
                continue
            overlap = sorted(set(left["canonical_objects"]) & set(right["canonical_objects"]))
            if overlap:
                edge(
                    "funnel:" + left["funnel_id"],
                    "funnel:" + right["funnel_id"],
                    "duplicates_semantics_with",
                    "duplicate",
                    overlap,
                )
    for record in scan["files"]:
        if not record["module"]:
            continue
        for imported in record["imports"]:
            classification = "adapter" if "tiingo" in imported else "unknown"
            edge("module:" + record["path"], "module:" + imported.replace(".", "/") + ".py", "imports", classification, [record["path"]])
        for artifact in record["artifacts"]:
            edge("module:" + record["path"], "artifact:" + artifact, "consumes", "observability" if "digest" in record["path"] else "unknown", [record["path"]])
    for obj, payload in contract_map.items():
        if obj.startswith("_"):
            continue
        node("canonical_object:" + obj, "canonical_object")
        for producer in payload["producer_modules"][:20]:
            edge("module:" + producer, "canonical_object:" + obj, "produces", "canonical" if payload["recommended_action"] == "KEEP" else "unknown", [producer])
        for consumer in payload["consumer_modules"][:20]:
            edge("canonical_object:" + obj, "module:" + consumer, "consumes", "canonical" if payload["recommended_action"] == "KEEP" else "unknown", [consumer])
    for finding in provider_report["provider_leakage_findings"][:200]:
        if finding["classification"] in {"suspicious_layer_leak", "forbidden_provider_coupling"}:
            edge("provider:" + finding["term"], "module:" + finding["file"], "leaks_provider_into", "forbidden" if finding["classification"] == "forbidden_provider_coupling" else "suspicious", [f"{finding['file']}:{finding['line']}"])
    summary = {
        "nodes": len(nodes),
        "edges": len(edges),
        "suspicious_edges": sum(1 for item in edges if item["classification"] == "suspicious"),
        "forbidden_edges": sum(1 for item in edges if item["classification"] == "forbidden"),
        "duplicate_edges": sum(1 for item in edges if item["classification"] == "duplicate"),
        "unknown_edges": sum(1 for item in edges if item["classification"] == "unknown"),
    }
    return {"nodes": sorted(nodes.values(), key=lambda item: item["id"]), "edges": edges, "summary": summary}


def build_reconciliation_plan(funnels: list[dict[str, Any]], contract_map: dict[str, Any]) -> list[dict[str, Any]]:
    plan = []
    for funnel in funnels:
        decision = funnel["status_recommendation"]
        future = {
            "KEEP_AS_PROVIDER_ADAPTER": "Bridge provider-specific artifacts to provider-agnostic canonical contracts.",
            "OBSERVABILITY_ONLY": "Keep read-only; do not let digest become a producer.",
            "BRIDGE_TO_CANONICAL": "Map objects to settled canonical vocabulary before further feature work.",
            "UNKNOWN_REQUIRES_OPERATOR_DECISION": "Settle ownership before treating this path as canonical.",
            "TEST_FIXTURE_ONLY": "Quarantine as test-only and avoid architectural claims.",
        }.get(decision, "Operator decision required.")
        plan.append(
            {
                "funnel": funnel["name"],
                "current_status": funnel["loop_claim"],
                "canonicality": funnel["canonicality"],
                "provider_specificity": funnel["provider_specificity"],
                "decision": decision,
                "required_future_pr": future,
            }
        )
    ambiguous = [name for name, payload in contract_map.items() if isinstance(payload, dict) and payload.get("recommended_action") == "OPERATOR_DECISION_REQUIRED"]
    if ambiguous:
        plan.append(
            {
                "funnel": "canonical contract settlement",
                "current_status": "ambiguous_contract_ownership",
                "canonicality": "unknown",
                "provider_specificity": "mixed",
                "decision": "UNKNOWN_REQUIRES_OPERATOR_DECISION",
                "required_future_pr": "Settle canonical ownership for: " + ", ".join(ambiguous[:12]),
            }
        )
    return plan


def build_funnel_classification_report() -> dict[str, Any]:
    classifications = classifications_as_dict()
    return {
        "summary": classification_summary(),
        "classifications": classifications,
        "canonical_contract_loop": classifications.get("canonical_provider_agnostic_contract_bridge_loop", {}),
    }


def build_closed_world_audit(contract_map: dict[str, Any]) -> dict[str, Any]:
    entries = registry_entries()
    maturity_claims = tuple(entry.maturity_level for entry in entries)
    authority_flags = tuple(flag for entry in entries for flag in entry.authority_flags)
    canonical_objects = tuple(name for name in contract_map if not name.startswith("_"))
    failures = validate_closed_world_audit(
        canonical_objects=canonical_objects,
        maturity_claims=maturity_claims,
        authority_flags=authority_flags,
    )
    return {
        "verdict": "fail" if failures else "pass",
        "failures": failures,
        "registry_validation_errors": validate_registry(),
        "registry_summary": registry_summary(),
        "registered_entries": registry_as_dict(),
        "known_authority_flags": list(AUTHORITY_FLAGS),
        "enforcement_scope": {
            "static_audit_only": True,
            "runtime_behavior_changed": False,
            "created_candidates": False,
            "created_strategies": False,
            "created_presets": False,
            "created_campaigns": False,
            "ran_screening": False,
            "trading_authority": False,
            "paper_authority": False,
            "shadow_authority": False,
            "live_authority": False,
        },
    }


def build_visual_maps() -> dict[str, str]:
    return {
        "c4_context": "docs/architecture/qre_funnel_visual_maps.md#diagram-1-c4-context-qre-research-system-boundary",
        "current_funnels": "docs/architecture/qre_funnel_visual_maps.md#diagram-2-c4-containercomponent-current-detected-funnels",
        "target_data_flow": "docs/architecture/qre_funnel_visual_maps.md#diagram-3-target-canonical-data-flow-architecture",
        "integration_graph": "docs/architecture/qre_funnel_visual_maps.md#diagram-4-integrationdependency-graph-producerconsumer-artifact-map",
        "sequence": "docs/architecture/qre_funnel_visual_maps.md#diagram-5-sequence-intended-full-canonical-loop",
        "provider_boundary": "docs/architecture/qre_funnel_visual_maps.md#diagram-6-provider-leakage-boundary",
    }


def build_report(repo_root: Path = Path(".")) -> dict[str, Any]:
    root = repo_root.resolve()
    try:
        scan = scan_repo(root)
    except OSError:
        return {
            "report_kind": REPORT_KIND,
            "schema_version": SCHEMA_VERSION,
            "generated_at": _utcnow(),
            "repo_root": str(root),
            "summary": {
                "audit_verdict": "blocked_unable_to_scan_repo",
                "funnels_detected": 0,
                "canonical_funnels": 0,
                "provider_specific_funnels": 0,
                "observability_funnels": 0,
                "duplicate_semantics_detected": False,
                "provider_leakage_findings": 0,
                "hardcoded_coupling_findings": 0,
                "contract_drift_findings": 0,
                "unknown_canonical_ownership_findings": 0,
                "recommended_next_action": "repair_audit_scan_permissions",
            },
            "funnel_inventory": [],
            "contract_map": {},
            "dependency_graph_summary": {},
            "provider_leakage_summary": {},
            "hardcoded_coupling_summary": {},
            "canonicality_assessment": {},
            "reconciliation_plan": [],
            "funnel_classification": build_funnel_classification_report(),
            "closed_world_audit": {
                "verdict": "fail",
                "failures": ["blocked_unable_to_scan_repo"],
                "registry_validation_errors": validate_registry(),
            },
            "visual_maps": build_visual_maps(),
            "safety": dict(SAFETY),
        }
    funnels = build_funnel_inventory(scan)
    contract_map = build_contract_map(scan, funnels)
    provider_report = build_provider_leakage_report(scan)
    coupling_report = build_hardcoded_coupling_report(scan)
    graph = build_dependency_graph(scan, funnels, contract_map, provider_report)
    reconciliation = build_reconciliation_plan(funnels, contract_map)
    funnel_classification = build_funnel_classification_report()
    closed_world = build_closed_world_audit(contract_map)
    unknown_contracts = [
        name
        for name, payload in contract_map.items()
        if isinstance(payload, dict) and payload.get("recommended_action") in {"OPERATOR_DECISION_REQUIRED", "DEFINE_CANONICAL_SCHEMA"}
    ]
    duplicate_semantics = len(funnels) > 1 or any(
        isinstance(payload, dict) and payload.get("duplicate_names_or_semantics")
        for payload in contract_map.values()
    )
    summary = {
        "audit_verdict": "pass_inventory_complete_with_reconciliation_needed",
        "funnels_detected": len(funnels),
        "canonical_funnels": sum(1 for funnel in funnels if funnel["canonicality"] == "canonical_candidate"),
        "provider_specific_funnels": sum(1 for funnel in funnels if funnel["provider_specificity"] == "provider_specific"),
        "observability_funnels": sum(1 for funnel in funnels if funnel["canonicality"] == "observability_only"),
        "duplicate_semantics_detected": bool(duplicate_semantics),
        "provider_leakage_findings": len(provider_report["provider_leakage_findings"]),
        "hardcoded_coupling_findings": len(coupling_report["hardcoded_coupling_findings"]),
        "contract_drift_findings": sum(1 for payload in contract_map.values() if isinstance(payload, dict) and payload.get("duplicate_names_or_semantics")),
        "unknown_canonical_ownership_findings": len(unknown_contracts),
        "recommended_next_action": "settle_canonical_contract_vocabulary_then_bridge_provider_specific_funnels",
    }
    return {
        "report_kind": REPORT_KIND,
        "schema_version": SCHEMA_VERSION,
        "generated_at": _utcnow(),
        "repo_root": str(root),
        "summary": summary,
        "funnel_inventory": funnels,
        "contract_map": contract_map,
        "dependency_graph_summary": graph["summary"],
        "provider_leakage_summary": provider_report["summary"],
        "hardcoded_coupling_summary": {"findings": len(coupling_report["hardcoded_coupling_findings"])},
        "canonicality_assessment": {
            "full_provider_agnostic_loop_exists": False,
            "canonical_contract_bridge_loop_classified": True,
            "assessment": "Multiple runtime funnels still exist. PR A-F classify one provider-agnostic contract/bridge/memory path as canonical at the contract level; the Tiingo path remains a provider adapter; daily digest is observability-only.",
            "unknown_contracts": unknown_contracts,
        },
        "reconciliation_plan": reconciliation,
        "funnel_classification": funnel_classification,
        "closed_world_audit": closed_world,
        "visual_maps": build_visual_maps(),
        "provider_leakage_report": provider_report,
        "hardcoded_coupling_report": coupling_report,
        "dependency_graph": graph,
        "safety": dict(SAFETY),
    }


def render_operator_summary(report: dict[str, Any]) -> str:
    summary = report["summary"]
    lines = [
        "# QRE Funnel Architecture Audit",
        "",
        "## Verdict",
        f"- Audit verdict: {summary['audit_verdict']}",
        f"- Recommended next action: {summary['recommended_next_action']}",
        "- Blunt assessment: multiple partial funnels exist; the full provider-agnostic canonical loop is not proven closed.",
        "",
        "## Funnels detected",
    ]
    for funnel in report.get("funnel_inventory", []):
        lines.append(f"- {funnel['name']}: {funnel['canonicality']} / {funnel['status_recommendation']}")
    lines.extend(
        [
            "",
            "## Canonical ownership",
            f"- Unknown or unsettled canonical ownership findings: {summary['unknown_canonical_ownership_findings']}",
            f"- Contract drift findings: {summary['contract_drift_findings']}",
            "",
            "## Provider leakage",
            f"- Provider leakage findings: {summary['provider_leakage_findings']}",
            f"- Suspicious leaks: {report['provider_leakage_summary'].get('suspicious_layer_leak', 0)}",
            f"- Forbidden coupling: {report['provider_leakage_summary'].get('forbidden_provider_coupling', 0)}",
            "",
            "## Hardcoded coupling",
            f"- Hardcoded coupling findings: {summary['hardcoded_coupling_findings']}",
            "",
            "## Duplicate or parallel semantics",
            f"- Duplicate or parallel semantics detected: {str(summary['duplicate_semantics_detected']).lower()}",
            "",
            "## Funnel classification",
            f"- Canonical contract loop: {report['funnel_classification']['summary'].get('canonical_contract_loop')}",
            f"- Duplicate canonical claims: {str(report['funnel_classification']['summary'].get('duplicate_canonical_claims')).lower()}",
            "",
            "## Visual maps",
        ]
    )
    for name, target in report.get("visual_maps", {}).items():
        lines.append(f"- {name}: {target}")
    lines.extend(["", "## Reconciliation decisions"])
    for item in report.get("reconciliation_plan", []):
        lines.append(f"- {item['funnel']}: {item['decision']} -> {item['required_future_pr']}")
    lines.extend(
        [
            "",
            "## Recommended next PR",
            "- PR A: settle canonical contract vocabulary before broadening any funnel.",
            "",
            "## Safety confirmation",
            "- Audit only: true",
            "- Runtime behavior changed: false",
            "- No candidates, strategies, presets, campaigns, screening, validation, paper, shadow, live, or trading authority created.",
            "",
        ]
    )
    return "\n".join(lines)


def _atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            handle.write(text)
        os.replace(tmp_name, path)
    except Exception:
        with contextlib.suppress(OSError):  # type: ignore[name-defined]
            os.unlink(tmp_name)
        raise


def write_outputs(report: dict[str, Any], *, repo_root: Path = Path("."), output_dir: Path = DEFAULT_OUTPUT_DIR) -> dict[str, str]:
    root = repo_root.resolve()
    resolved = output_dir if output_dir.is_absolute() else root / output_dir
    resolved = resolved.resolve()
    allowed = (root / DEFAULT_OUTPUT_DIR).resolve()
    if resolved != allowed:
        raise ValueError("output_dir_must_be_logs_qre_funnel_architecture_audit")
    outputs = {
        "latest": resolved / "latest.json",
        "dependency_graph": resolved / "dependency_graph.json",
        "provider_leakage_report": resolved / "provider_leakage_report.json",
        "contract_map": resolved / "contract_map.json",
        "funnel_inventory": resolved / "funnel_inventory.json",
        "operator_summary": resolved / "operator_summary.md",
    }
    _atomic_write(outputs["latest"], _json(report))
    _atomic_write(outputs["dependency_graph"], _json(report["dependency_graph"]))
    _atomic_write(outputs["provider_leakage_report"], _json(report["provider_leakage_report"]))
    _atomic_write(outputs["contract_map"], _json(report["contract_map"]))
    _atomic_write(outputs["funnel_inventory"], _json(report["funnel_inventory"]))
    _atomic_write(outputs["operator_summary"], render_operator_summary(report))
    return {key: _rel(path, root) for key, path in outputs.items()}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Statically audit QRE funnel architecture.")
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR.as_posix())
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args(argv)
    root = Path(args.repo_root).resolve()
    report = build_report(root)
    if args.write:
        report["_artifact_paths"] = write_outputs(report, repo_root=root, output_dir=Path(args.output_dir))
    print(json.dumps(_stable(report), indent=2, sort_keys=True, ensure_ascii=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
