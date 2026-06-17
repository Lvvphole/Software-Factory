"""factory CLI: `factory run --signal <path> [--target-repo …] [--executor …]`"""
from __future__ import annotations
import argparse
import json
import sys
from workflows import run_factory


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="factory", description="Software Factory v1.1 CLI")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_run = sub.add_parser("run", help="execute a factory run from a signal file")
    p_run.add_argument("--signal", required=True, help="path to signal JSON")
    p_run.add_argument("--runs-root", default=".factory-runs")
    p_run.add_argument("--autonomy", type=int, default=2)
    # v1.1
    p_run.add_argument("--target-repo", default=None,
                       help="path to target git repo for real execution (omit for mock)")
    p_run.add_argument("--executor", default="mock", choices=["mock", "claude_code"],
                       help="executor for the coding stage (default: mock)")
    p_run.add_argument("--test-cmd", default=None,
                       help="override test command (e.g. 'pytest -q'); auto-detected otherwise")
    p_run.add_argument("--allow-dirty", action="store_true",
                       help="allow target_repo with uncommitted changes")
    p_run.add_argument("--allow-protected-branch", action="store_true",
                       help="allow target_repo on main/master/etc.")
    # v1.2
    p_run.add_argument("--max-attempts", type=int, default=2,
                       help="maximum executor attempts when real tests fail (default: 2). "
                            "Only takes effect with a non-mock executor and a target_repo.")

    args = parser.parse_args(argv)

    if args.cmd == "run":
        try:
            result = run_factory(
                args.signal,
                runs_root=args.runs_root,
                autonomy_level=args.autonomy,
                target_repo=args.target_repo,
                executor=args.executor,
                test_cmd=args.test_cmd.split() if args.test_cmd else None,
                allow_dirty=args.allow_dirty,
                allow_protected_branch=args.allow_protected_branch,
                max_attempts=args.max_attempts,
            )
            print(json.dumps({
                "run_id": result["run_id"],
                "run_dir": result["run_dir"],
                "executor": result["verifier"]["executor"],
                "grading_mode": result["verifier"]["grading_mode"],
                "verifier_decision": result["verifier"]["decision"],
                "tests_exit_code": result["verifier"]["tests_exit_code"],
                "diff_size_bytes": result["verifier"]["diff_size_bytes"],
                "attempts_used": result["attempts_used"],
            }, indent=2))
            return 0 if result["verifier"]["decision"] == "pass" else 2
        except Exception as e:
            print(f"factory: ERROR: {e}", file=sys.stderr)
            return 1

    return 1


if __name__ == "__main__":
    sys.exit(main())
