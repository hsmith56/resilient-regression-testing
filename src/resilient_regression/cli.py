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
    run.add_argument("--host", help="IBM SOAR / Resilient host URL for real mode")
    run.add_argument("--org", help="IBM SOAR / Resilient organization id for real mode")
    run.add_argument("--api-key-id", help="IBM SOAR API key id for real mode")
    run.add_argument("--api-key-secret", help="IBM SOAR API key secret for real mode")
    run.add_argument("--email", help="IBM SOAR email for real mode")
    run.add_argument("--password", help="IBM SOAR password for real mode")
    run.add_argument("--cafile", default=False, help="CA bundle path for TLS verification in real mode")
    run.add_argument("--no-cleanup", action="store_true", help="Do not cleanup incidents created during this run")
    run.add_argument("--report-json", help="Write JSON report to this path")
    run.add_argument("--verbose", action="store_true", help="Show step-level details")
    return parser


def _validate_real_mode_args(args: argparse.Namespace) -> str | None:
    missing = [name for name in ("host", "org") if not getattr(args, name)]
    has_api_key_id = bool(args.api_key_id)
    has_api_key_secret = bool(args.api_key_secret)
    has_email = bool(args.email)
    has_password = bool(args.password)

    if has_api_key_id != has_api_key_secret:
        missing.append("api-key-secret" if has_api_key_id else "api-key-id")
    if has_email != has_password:
        missing.append("password" if has_email else "email")
    if has_api_key_id and has_email:
        return "real mode requires either API key credentials or email/password credentials, not both"
    if not (has_api_key_id or has_email):
        missing.append("api-key-id/api-key-secret or email/password")
    if missing:
        return "real mode missing required option(s): " + ", ".join(f"--{name}" for name in missing)
    return None


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "run":
        if not args.dry_run:
            setup_error = _validate_real_mode_args(args)
            if setup_error:
                print(setup_error, file=sys.stderr)
                return 2

        try:
            scenarios = load_scenarios(args.scenario_files)
        except ScenarioLoaderError as exc:
            print(f"Load failed: {exc}", file=sys.stderr)
            return 2

        try:
            client = MockSoarClient() if args.dry_run else RealSoarClient(
                host=args.host,
                org=args.org,
                api_key_id=args.api_key_id,
                api_key_secret=args.api_key_secret,
                email=args.email,
                password=args.password,
                cafile=args.cafile,
            )
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
