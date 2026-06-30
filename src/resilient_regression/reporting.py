from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import asdict
from pathlib import Path

from rich.console import Console
from rich.table import Table

from .models import RunReport, ScenarioResult


def print_report(report: RunReport, verbose: bool = False) -> None:
    console = Console()

    grouped: dict[str, list[ScenarioResult]] = defaultdict(list)
    for result in report.results:
        grouped[result.source or "<unknown>"].append(result)

    for source, results in grouped.items():
        console.print(source)
        table = Table()
        table.add_column("Scenario", overflow="fold")
        table.add_column("Status", no_wrap=True)
        table.add_column("Details", overflow="fold")

        for result in results:
            table.add_row(result.id, _status(result), _details(result))
        console.print(table)

        if verbose:
            for result in results:
                for step in result.steps:
                    console.print(f"{source}::{result.id}::{step.name} {step.action} {'PASS' if step.passed else 'FAIL'}")

    passed = sum(1 for result in report.results if result.passed)
    failed = len(report.failed_results)
    allowed = len(report.allowed_failure_results)
    total = len(report.results)
    files = len(grouped)
    summary_style = "green" if report.passed else "red"
    console.print(
        f"[{summary_style}]Total: {total} scenarios across {files} file(s), "
        f"{passed} passed, {failed} failed, {allowed} allowed failure(s)[/{summary_style}]"
    )

    if report.cleanup_ran:
        console.print(f"Cleanup processed created incidents: {report.cleanup_deleted_ids}")
    else:
        console.print("Cleanup skipped (--no-cleanup)")


def _status(result: ScenarioResult) -> str:
    if result.passed:
        return "[green]PASS[/green]"
    if result.allow_failure:
        return "[yellow]ALLOWED FAIL[/yellow]"
    return "[red]FAIL[/red]"


def _details(result: ScenarioResult) -> str:
    details = result.error or ""
    if result.validation_failures:
        details = "; ".join(
            f"{failure.path}: expected {failure.expected!r}, actual {failure.actual!r}"
            for failure in result.validation_failures
        )
    if result.allow_failure and not result.passed:
        details = f"allow_failure=true; {details}".rstrip()
    return details


def write_json_report(report: RunReport, path: str | Path) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(asdict(report), indent=2, default=str), encoding="utf-8")
