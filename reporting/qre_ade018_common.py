from __future__ import annotations

import ast
import hashlib
import json
from pathlib import Path
from typing import Any


def text(value: Any) -> str:
    return str(value or "").strip()


def read_json(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def rows(payload: dict[str, Any] | None, field: str) -> list[dict[str, Any]]:
    if not isinstance(payload, dict):
        return []
    raw = payload.get(field)
    if not isinstance(raw, list):
        return []
    return [dict(item) for item in raw if isinstance(item, dict)]


def normalize_list(value: Any) -> list[str]:
    if isinstance(value, list):
        items = value
    elif value is None:
        items = []
    else:
        items = [value]
    out: list[str] = []
    for item in items:
        normalized = text(item)
        if normalized and normalized not in out:
            out.append(normalized)
    return out


def index_by(rows_in: list[dict[str, Any]], field: str) -> dict[str, dict[str, Any]]:
    indexed: dict[str, dict[str, Any]] = {}
    for row in rows_in:
        key = text(row.get(field))
        if key:
            indexed[key] = dict(row)
    return indexed


def stable_digest(payload: Any) -> str:
    return hashlib.sha256(
        json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=True,
        ).encode("utf-8")
    ).hexdigest()


def rel(path: Path, repo_root: Path) -> str:
    try:
        return path.resolve().relative_to(repo_root.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def dedupe(values: list[str]) -> list[str]:
    out: list[str] = []
    for value in values:
        normalized = text(value)
        if normalized and normalized not in out:
            out.append(normalized)
    return out


def behavior_keys(behavior_family: str) -> list[str]:
    aliases = {
        "volatility_compression_breakout": [
            "volatility_compression_breakout",
            "vol_compression_breakout",
        ],
        "trend_continuation": ["trend_continuation"],
        "relative_strength": ["relative_strength"],
        "index_regime_filter": ["index_regime_filter"],
        "mean_reversion": ["mean_reversion"],
        "pullback_continuation": ["pullback_continuation"],
    }
    return aliases.get(behavior_family, [behavior_family] if behavior_family else [])


def literal(node: ast.AST, constants: dict[str, Any]) -> Any:
    if isinstance(node, ast.Constant):
        return node.value
    if isinstance(node, ast.Tuple):
        return tuple(literal(item, constants) for item in node.elts)
    if isinstance(node, ast.List):
        return [literal(item, constants) for item in node.elts]
    if isinstance(node, ast.Dict):
        return {
            literal(key, constants): literal(value, constants)
            for key, value in zip(node.keys, node.values)
        }
    if isinstance(node, ast.Name):
        return constants.get(node.id)
    return None


def parse_preset_catalog(source_text: str | None) -> list[dict[str, Any]]:
    if not source_text:
        return []
    tree = ast.parse(source_text)
    constants: dict[str, Any] = {}
    catalog: list[dict[str, Any]] = []
    for node in tree.body:
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            if node.target.id == "PRESETS" and isinstance(node.value, ast.Tuple):
                for item in node.value.elts:
                    if not isinstance(item, ast.Call) or not isinstance(item.func, ast.Name):
                        continue
                    if item.func.id != "ResearchPreset":
                        continue
                    row: dict[str, Any] = {}
                    for keyword in item.keywords:
                        if keyword.arg is not None:
                            row[keyword.arg] = literal(keyword.value, constants)
                    catalog.append(row)
                continue
            value = literal(node.value, constants) if node.value is not None else None
            if value is not None:
                constants[node.target.id] = value
            continue
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            name = node.targets[0].id
            if name == "PRESETS" and isinstance(node.value, ast.Tuple):
                for item in node.value.elts:
                    if not isinstance(item, ast.Call) or not isinstance(item.func, ast.Name):
                        continue
                    if item.func.id != "ResearchPreset":
                        continue
                    row = {}
                    for keyword in item.keywords:
                        if keyword.arg is not None:
                            row[keyword.arg] = literal(keyword.value, constants)
                    catalog.append(row)
                continue
            value = literal(node.value, constants)
            if value is not None:
                constants[name] = value
    return [row for row in catalog if text(row.get("name"))]
