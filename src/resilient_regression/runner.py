from __future__ import annotations

import time
from dataclasses import dataclass

from .cleanup import cleanup_created_incidents
from .client import MockSoarClient
from .models import RunReport, Scenario, ScenarioResult, StepResult
from .validators import validate_incident


@dataclass
class RunnerConfig:
    dry_run: bool = True
    no_cleanup: bool = False
    sleep_in_dry_run: bool = False
    verbose: bool = False


class ScenarioRunner:
    def __init__(self, client: MockSoarClient | None = None, config: RunnerConfig | None = None) -> None:
        self.client = client or MockSoarClient()
        self.config = config or RunnerConfig()

    def run(self, scenarios: list[Scenario]) -> RunReport:
        results: list[ScenarioResult] = []
        cleanup_deleted_ids: list[int] = []
        cleanup_ran = False
        try:
            for scenario in scenarios:
                results.append(self._run_scenario(scenario))
        finally:
            if not self.config.no_cleanup:
                cleanup_deleted_ids = cleanup_created_incidents(self.client)
                cleanup_ran = True
        return RunReport(results=results, cleanup_ran=cleanup_ran, cleanup_deleted_ids=cleanup_deleted_ids)

    def _run_scenario(self, scenario: Scenario) -> ScenarioResult:
        result = ScenarioResult(
            id=scenario.id,
            passed=True,
            source=str(scenario.source) if scenario.source else None,
            allow_failure=scenario.allow_failure,
        )
        incident_id: int | None = None

        try:
            for step in scenario.steps:
                if step.wait_before_run is not None:
                    self._wait(step.wait_before_run)

                if step.create_inc is not None:
                    incident = self.client.create_incident(step.create_inc)
                    incident_id = int(incident["id"])
                    result.incident_id = incident_id
                    result.steps.append(StepResult(name=step.name, action="create-inc"))

                if step.update_inc is not None:
                    if incident_id is None:
                        raise RuntimeError(f"step {step.name} update-inc requires prior create-inc")
                    self.client.update_incident(incident_id, step.update_inc)
                    result.steps.append(StepResult(name=step.name, action="update-inc"))

                if step.create_inc is None and step.update_inc is None and step.wait_before_run is not None:
                    result.steps.append(StepResult(name=step.name, action="wait-before-run"))

            if scenario.validations:
                if incident_id is None:
                    raise RuntimeError("validate requires prior create-inc")
                incident = self.client.get_incident(incident_id)
                result.validation_failures = validate_incident(incident, scenario.validations)
                if result.validation_failures:
                    result.passed = False
        except Exception as exc:  # continue other scenarios after failure
            result.passed = False
            result.error = str(exc)
        return result

    def _wait(self, value: str | int | float) -> None:
        seconds = _parse_wait_seconds(value)
        if self.config.dry_run and not self.config.sleep_in_dry_run:
            return
        time.sleep(seconds)


def _parse_wait_seconds(value: str | int | float) -> float:
    if isinstance(value, (int, float)):
        return float(value)
    text = value.strip().lower()
    for suffix in ("seconds", "second", "secs", "sec", "s"):
        if text.endswith(suffix):
            return float(text[: -len(suffix)].strip())
    return float(text)
