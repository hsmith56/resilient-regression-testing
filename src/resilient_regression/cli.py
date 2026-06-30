from __future__ import annotations

import argparse
import sys

from .client import MockSoarClient, RealSoarClient, SoarClientError
from .loader import ScenarioLoaderError, load_scenarios
from .reporting import print_report, write_json_report
from .runner import RunnerConfig, ScenarioRunner


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="resilient-regression")
    subparsers = parser.add_subparsers(dest="command", required=True)

    run = subparsers.add_parser("run", help="Run YAML regression scenarios")
    run.add_argument("scenario_files", nargs="+", help="YAML scenario file(s)")
    run.add_argument("--dry-run", action="store_true", help="Use mocked local SOAR client")
    run.add_argument("--config", help="Path to IBM SOAR / Resilient app.config for real mode")
    run.add_argument("--no-cleanup", action="store_true", help="Do not cleanup incidents created during this run")
    run.add_argument("--report-json", help="Write JSON report to this path")
    run.add_argument("--verbose", action="store_true", help="Show step-level details")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "run":
        if not args.dry_run and not args.config:
            print("real mode requires --config app.config; use --dry-run for the mock client", file=sys.stderr)
            return 2

        try:
            scenarios = load_scenarios(args.scenario_files)
        except ScenarioLoaderError as exc:
            print(f"Load failed: {exc}", file=sys.stderr)
            return 2

        try:
            client = MockSoarClient() if args.dry_run else RealSoarClient(args.config)
        except SoarClientError as exc:
            print(f"Client setup failed: {exc}", file=sys.stderr)
            return 2

        runner = ScenarioRunner(
            client=client,
            config=RunnerConfig(dry_run=args.dry_run, no_cleanup=args.no_cleanup, verbose=args.verbose),
        )
        report = runner.run(scenarios)
        print_report(report, verbose=args.verbose)
        if args.report_json:
            write_json_report(report, args.report_json)
        return 0 if report.passed else 1

    parser.error("unknown command")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
