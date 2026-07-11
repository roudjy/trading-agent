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
    parser = argparse.ArgumentParser(description="Run governed offline QRE research.")
    parser.add_argument("--hypothesis-id", required=True)
    parser.add_argument("--dataset-id", required=True)
    parser.add_argument("--dataset-catalog", type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--run-id")
    parser.add_argument(
        "--source-mode",
        default="offline_fixture",
        choices=("offline_fixture", "offline_sample", "offline_cached"),
    )
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--fail-on-blocked", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    result = runner.run_governed_offline_research(
        hypothesis_id=args.hypothesis_id,
        dataset_id=args.dataset_id,
        output_dir=args.output_dir,
        run_id=args.run_id,
        source_mode=args.source_mode,
        dataset_catalog_path=args.dataset_catalog,
    )
    payload = result.as_dict()
    if args.json:
        print(json.dumps(payload, indent=2, sort_keys=True))
    else:
        print(
            f"{payload['report_kind']} {payload['run_id']}: "
            f"{payload['operator_review']['offline_eligibility_decision']}"
        )
    if args.fail_on_blocked and not payload["eligible_for_more_offline_research"]:
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
