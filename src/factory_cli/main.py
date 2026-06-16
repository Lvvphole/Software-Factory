"""factory CLI: `factory run --signal <path>`"""
from __future__ import annotations
import argparse
import json
import sys
from workflows import run_factory


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="factory", description="Software Factory v1 CLI")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_run = sub.add_parser("run", help="execute a factory run from a signal file")
    p_run.add_argument("--signal", required=True, help="path to signal JSON")
    p_run.add_argument("--runs-root", default=".factory-runs")
    p_run.add_argument("--autonomy", type=int, default=2)

    args = parser.parse_args(argv)

    if args.cmd == "run":
        try:
            result = run_factory(args.signal, args.runs_root, args.autonomy)
            print(json.dumps({
                "run_id": result["run_id"],
                "run_dir": result["run_dir"],
                "verifier_decision": result["verifier"]["decision"],
            }, indent=2))
            return 0 if result["verifier"]["decision"] == "pass" else 2
        except Exception as e:
            print(f"factory: ERROR: {e}", file=sys.stderr)
            return 1

    return 1


if __name__ == "__main__":
    sys.exit(main())
