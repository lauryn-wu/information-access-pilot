"""Use python -m information_access --help. Only run --execute can spend money."""

import argparse
import json
from pathlib import Path
import sys

from .analysis import analyze
from .runner import load_config, plan, run
from .tasks import generate, save_cases


def main(argv=None):
    parser = argparse.ArgumentParser(description="Information-access diagnostic screen")
    parser.add_argument("--config", default="configs/screen.json")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("plan", help="Offline cost envelope and dataset validation")
    gen = sub.add_parser("generate", help="Write the deterministic 64-cell dataset")
    gen.add_argument("--output", default="data/screen.jsonl")
    paid = sub.add_parser("run", help="Resume the shared-budget pilot; requires --execute")
    paid.add_argument("--execute", action="store_true", help="Explicitly enable paid API generation")
    paid.add_argument("--run-dir", default="runs/screen")
    paid.add_argument("--model", action="append", choices=("sonnet", "gemini"))
    paid.add_argument("--limit", type=int, help="At most this many new generation attempts this invocation")
    paid.add_argument("--retry-failed", action="store_true", help="Allow one retry of failed/invalid cells; never retry a valid answer")
    demo = sub.add_parser("demo", help="Offline synthetic reference policy; zero API calls")
    demo.add_argument("--policy", choices=("feasible", "perfect_information", "fixed_action"), default="feasible")
    demo.add_argument("--run-dir", help="Default: runs/demo-POLICY (cannot be reused for paid runs)")
    report = sub.add_parser("analyze", help="Read frozen run, write JSON and CSV reports")
    report.add_argument("--run-dir", default="runs/screen")
    args = parser.parse_args(argv)
    try:
        if args.command == "analyze":
            result = analyze(args.run_dir)
        else:
            config = load_config(args.config)
            cases = generate(config["seed"])
            if args.command == "plan":
                result = plan(config, cases)
            elif args.command == "generate":
                path = Path(args.output)
                path.parent.mkdir(parents=True, exist_ok=True)
                save_cases(path, cases)
                result = {"saved": str(path), "cells": len(cases)}
            elif args.command == "run":
                if not args.execute:
                    parser.error("No API calls made. Paid execution requires run --execute.")
                result = run(config, cases, args.run_dir, selected=args.model,
                             retry=args.retry_failed, limit=args.limit)
            else:
                result = run(config, cases, args.run_dir or f"runs/demo-{args.policy}",
                             mode=f"simulation:{args.policy}", progress=lambda _: None)
        print(json.dumps(result, indent=2))
        return 0
    except (ValueError, OSError, RuntimeError) as exc:
        print(f"Stopped: {exc}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print("Interrupted. Any pending request keeps its full reservation. Resume in the same run directory.", file=sys.stderr)
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
