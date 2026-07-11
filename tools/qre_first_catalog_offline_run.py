from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from packages.qre_research import governed_offline_research_runner as runner  # noqa: E402


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the first catalog-admitted governed offline QRE workflow.")
    parser.add_argument("--catalog", required=True, type=Path)
    parser.add_argument("--dataset-id", required=True)
    parser.add_argument("--hypothesis-id", required=True)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--run-id")
    parser.add_argument("--json", action="store_true")
    return parser


def _summary(payload: dict[str, object]) -> dict[str, object]:
    return {
        "report_kind": "qre_first_catalog_admitted_offline_run",
        "run_id": payload["run_id"],
        "hypothesis_id": payload["hypothesis_id"],
        "dataset_id": payload["dataset_id"],
        "dataset_admission": payload["dataset_admission"],
        "disposition": payload["disposition"],
        "operator_review": payload["operator_review"],
        "artifact_path": payload["artifact_path"],
        "latest_path": payload["latest_path"],
        "authority": payload["authority"],
    }


def run_first_catalog_offline_run(
    *,
    catalog_path: Path,
    dataset_id: str,
    hypothesis_id: str,
    output_dir: Path,
    run_id: str | None = None,
) -> dict[str, object]:
    result = runner.run_governed_offline_research(
        hypothesis_id=hypothesis_id,
        dataset_id=dataset_id,
        dataset_catalog_path=catalog_path,
        output_dir=output_dir,
        run_id=run_id,
    )
    return _summary(result.as_dict())


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    payload = run_first_catalog_offline_run(
        catalog_path=args.catalog,
        dataset_id=args.dataset_id,
        hypothesis_id=args.hypothesis_id,
        output_dir=args.output_dir,
        run_id=args.run_id,
    )
    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print(
            f"{payload['report_kind']} {payload['run_id']}: "
            f"{payload['dataset_admission']['decision']} -> "
            f"{payload['operator_review']['offline_eligibility_decision']}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
