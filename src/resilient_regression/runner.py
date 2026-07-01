from __future__ import annotations

import re
import time
from dataclasses import dataclass
from typing import Any

from .cleanup import cleanup_created_incidents
from .client import BaseSoarClient, MockSoarClient
from .models import RunReport, Scenario, ScenarioResult, ScenarioStep, StepResult
from .validators import validate_incident


_VARIABLE_RE = re.compile(r"\$\{([^}]+)\}")


@dataclass
class RunnerConfig:
    dry_run: bool = True
    no_cleanup: bool = False
    sleep_in_dry_run: bool = False
    verbose: bool = False


class ScenarioRunner:
    def __init__(self, client: BaseSoarClient | None = None, config: RunnerConfig | None = None) -> None:
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
        incident_id: int | None = scenario.incident_id
        task_id: int | None = None
        variables: dict[str, Any] = {}
        result.incident_id = incident_id

        try:
            if incident_id is not None:
                incident = self.client.get_incident(incident_id)
                _store_incident_variables(variables, incident)

            for step in scenario.steps:
                if step.wait_before_run is not None:
                    self._wait(step.wait_before_run)

                incident_id, task_id = self._execute_step(step, result, incident_id, task_id, variables)

            if scenario.validations:
                if incident_id is None:
                    raise RuntimeError("validate requires prior create-inc")
                incident = self.client.get_incident(incident_id)
                expectations = _resolve_value(scenario.validations, variables)
                result.validation_failures = validate_incident(incident, expectations)
                if result.validation_failures:
                    result.passed = False
        except Exception as exc:  # continue other scenarios after failure
            result.passed = False
            result.error = str(exc)
        return result

    def _execute_step(
        self,
        step: ScenarioStep,
        result: ScenarioResult,
        incident_id: int | None,
        task_id: int | None,
        variables: dict[str, Any],
    ) -> tuple[int | None, int | None]:
        ran_action = False

        if step.create_inc is not None:
            incident = self.client.create_incident(_resolve_value(step.create_inc, variables))
            incident_id = int(incident["id"])
            _store_incident_variables(variables, incident)
            result.incident_id = incident_id
            result.steps.append(StepResult(name=step.name, action="create-inc"))
            ran_action = True

        if step.update_inc is not None:
            incident_id = _require_incident_id(incident_id, step.name, "update-inc")
            incident = self.client.update_incident(incident_id, _resolve_value(step.update_inc, variables))
            _store_incident_variables(variables, incident)
            result.steps.append(StepResult(name=step.name, action="update-inc"))
            ran_action = True

        if step.add_note is not None:
            incident_id = _require_incident_id(incident_id, step.name, "add-note")
            note_fields = step.add_note if isinstance(step.add_note, dict) else {"text": step.add_note}
            self.client.add_note(incident_id, _resolve_value(note_fields, variables))
            _store_incident_variables(variables, self.client.get_incident(incident_id))
            result.steps.append(StepResult(name=step.name, action="add-note"))
            ran_action = True

        if step.add_task is not None:
            incident_id = _require_incident_id(incident_id, step.name, "add-task")
            task = self.client.add_task(incident_id, _resolve_value(step.add_task, variables))
            task_id = int(task["id"])
            _store_task_variables(variables, task)
            _store_incident_variables(variables, self.client.get_incident(incident_id))
            result.steps.append(StepResult(name=step.name, action="add-task"))
            ran_action = True

        if step.update_task is not None:
            incident_id = _require_incident_id(incident_id, step.name, "update-task")
            resolved = _resolve_value(step.update_task, variables)
            selected_task_id = int(resolved.pop("id", task_id) or 0)
            if not selected_task_id:
                raise RuntimeError(f"step {step.name} update-task requires prior add-task or id")
            task = self.client.update_task(incident_id, selected_task_id, resolved)
            task_id = int(task["id"])
            _store_task_variables(variables, task)
            _store_incident_variables(variables, self.client.get_incident(incident_id))
            result.steps.append(StepResult(name=step.name, action="update-task"))
            ran_action = True

        if step.close_incident is not None:
            incident_id = _require_incident_id(incident_id, step.name, "close-incident")
            close_fields = step.close_incident if isinstance(step.close_incident, dict) else {"status": step.close_incident}
            incident = self.client.close_incident(incident_id, _resolve_value(close_fields, variables))
            _store_incident_variables(variables, incident)
            result.steps.append(StepResult(name=step.name, action="close-incident"))
            ran_action = True

        if step.run_script is not None:
            incident_id = _require_incident_id(incident_id, step.name, "run-script")
            self.client.run_script(incident_id, _resolve_value(step.run_script, variables))
            _store_incident_variables(variables, self.client.get_incident(incident_id))
            result.steps.append(StepResult(name=step.name, action="run-script"))
            ran_action = True

        if not ran_action and step.wait_before_run is not None:
            result.steps.append(StepResult(name=step.name, action="wait-before-run"))

        return incident_id, task_id

    def _wait(self, value: str | int | float) -> None:
        seconds = _parse_wait_seconds(value)
        if self.config.dry_run and not self.config.sleep_in_dry_run:
            return
        time.sleep(seconds)


def _require_incident_id(incident_id: int | None, step_name: str, action: str) -> int:
    if incident_id is None:
        raise RuntimeError(f"step {step_name} {action} requires prior create-inc")
    return incident_id


def _store_incident_variables(variables: dict[str, Any], incident: dict[str, Any]) -> None:
    _store_dotted_variables(variables, "incident", incident)


def _store_task_variables(variables: dict[str, Any], task: dict[str, Any]) -> None:
    _store_dotted_variables(variables, "task", task)


def _store_dotted_variables(variables: dict[str, Any], prefix: str, value: Any) -> None:
    if isinstance(value, dict):
        for key, item in value.items():
            _store_dotted_variables(variables, f"{prefix}.{key}", item)
        return
    if isinstance(value, list):
        for index, item in enumerate(value):
            _store_dotted_variables(variables, f"{prefix}.{index}", item)
        return
    variables[prefix] = value


def _resolve_value(value: Any, variables: dict[str, Any]) -> Any:
    if isinstance(value, dict):
        return {key: _resolve_value(item, variables) for key, item in value.items()}
    if isinstance(value, list):
        return [_resolve_value(item, variables) for item in value]
    if isinstance(value, str):
        full_match = _VARIABLE_RE.fullmatch(value)
        if full_match:
            return variables.get(full_match.group(1), value)
        return _VARIABLE_RE.sub(lambda match: str(variables.get(match.group(1), match.group(0))), value)
    return value


def _parse_wait_seconds(value: str | int | float) -> float:
    if isinstance(value, (int, float)):
        return float(value)
    text = value.strip().lower()
    for suffix in ("seconds", "second", "secs", "sec", "s"):
        if text.endswith(suffix):
            return float(text[: -len(suffix)].strip())
    return float(text)
