"""Classify changed files for path-aware CI gates.

The classifier is intentionally deterministic and conservative. It emits
coarse domain booleans only; workflows decide which jobs consume them.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

ZERO_SHA = "0" * 40


def _norm(path: str) -> str:
    return path.strip().replace("\\", "/").lstrip("./")


def _matches_any(path: str, prefixes: tuple[str, ...]) -> bool:
    return any(path == prefix.rstrip("/") or path.startswith(prefix) for prefix in prefixes)


def _git_changed_files(base: str, head: str) -> list[str]:
    if not base or base == ZERO_SHA:
        args = ["git", "diff-tree", "--no-commit-id", "--name-only", "-r", head]
    else:
        args = ["git", "diff", "--name-only", f"{base}...{head}"]
        probe = subprocess.run(
            ["git", "merge-base", base, head],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            text=True,
        )
        if probe.returncode != 0:
            args = ["git", "diff", "--name-only", base, head]

    result = subprocess.run(
        args,
        check=True,
        capture_output=True,
        text=True,
    )
    return [line for line in result.stdout.splitlines() if line.strip()]


def _is_docs_path(path: str) -> bool:
    return path.startswith("docs/") or (
        "/" not in path and path.lower().endswith((".md", ".rst", ".txt"))
    )


def _is_architecture_path(path: str) -> bool:
    return path.startswith(("docs/architecture/", "docs/adr/", "tests/architecture/")) or path in {
        "reporting/architecture_import_scan.py",
    }


def classify_paths(paths: list[str]) -> dict[str, bool]:
    changed = sorted({p for p in (_norm(path) for path in paths) if p})

    categories = {
        "docs_only": False,
        "architecture_only": False,
        "frontend": False,
        "dashboard_or_control_plane": False,
        "ade_governance_or_reporting": False,
        "qre_research": False,
        "packages": False,
        "tests": False,
        "ci_or_governance": False,
        "deployment_sensitive": False,
        "execution_sensitive": False,
    }

    for path in changed:
        if path.startswith("frontend/"):
            categories["frontend"] = True
        if path.startswith(("dashboard/", "apps/control-plane/")):
            categories["dashboard_or_control_plane"] = True
        if path.startswith(("packages/ade_governance/", "reporting/", "orchestration/")):
            categories["ade_governance_or_reporting"] = True
        if path.startswith(("research/", "strategies/", "agent/backtesting/")) or path in {
            "registry.py",
            "researchctl.py",
        }:
            categories["qre_research"] = True
        if path.startswith("packages/"):
            categories["packages"] = True
        if path.startswith("tests/"):
            categories["tests"] = True
        if (
            path.startswith((".github/", "docs/governance/"))
            or path in {
                ".gitleaks.toml",
                ".pre-commit-config.yaml",
                "pyproject.toml",
                "pytest.ini",
                "requirements.txt",
                "SECURITY.md",
            }
            or _matches_any(path, ("scripts/", ".claude/"))
        ):
            categories["ci_or_governance"] = True
        if path.startswith(("ops/", "config/")) or path in {
            ".dockerignore",
            "Dockerfile",
            "docker-compose.prod.yml",
            "docker-compose.yml",
            "requirements.txt",
            "VERSION",
        }:
            categories["deployment_sensitive"] = True
        if path in {"scripts/deploy.sh", "scripts/deploy_vps_dashboard.sh"}:
            categories["deployment_sensitive"] = True
        if path.startswith(
            (
                "agent/execution/",
                "agent/risk/",
                "automation/",
                "broker/",
                "execution/",
                "live/",
                "paper/",
                "shadow/",
                "trading/",
            )
        ):
            categories["execution_sensitive"] = True

    if changed:
        categories["docs_only"] = all(_is_docs_path(path) for path in changed) and not categories[
            "ci_or_governance"
        ]
        categories["architecture_only"] = all(_is_architecture_path(path) for path in changed)

    categories["run_frontend"] = (
        categories["frontend"]
        or categories["dashboard_or_control_plane"]
        or categories["ci_or_governance"]
        or categories["execution_sensitive"]
    )
    categories["run_docker_build"] = (
        categories["frontend"]
        or categories["dashboard_or_control_plane"]
        or categories["packages"]
        or categories["ci_or_governance"]
        or categories["deployment_sensitive"]
        or categories["execution_sensitive"]
    )
    categories["run_dashboard_deploy"] = categories["run_docker_build"]

    return categories


def _bool(value: bool) -> str:
    return "true" if value else "false"


def _write_outputs(outputs: dict[str, bool], path: str | None) -> None:
    lines = [f"{key}={_bool(value)}" for key, value in sorted(outputs.items())]
    if path:
        with Path(path).open("a", encoding="utf-8") as fh:
            for line in lines:
                fh.write(f"{line}\n")
    for line in lines:
        print(line)


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("paths", nargs="*", help="Changed paths to classify.")
    parser.add_argument("--base", help="Base git revision for diff classification.")
    parser.add_argument("--head", help="Head git revision for diff classification.")
    parser.add_argument("--github-output", help="Path to the GitHub Actions output file.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    paths = list(args.paths)
    if args.base or args.head:
        if not args.head:
            raise SystemExit("--head is required when --base is provided")
        paths.extend(_git_changed_files(args.base or "", args.head))
    outputs = classify_paths(paths)
    _write_outputs(outputs, args.github_output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
