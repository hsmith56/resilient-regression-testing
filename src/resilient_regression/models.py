from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator


SUPPORTED_ASSERTIONS = {"contains", "equals", "exists", "not_null", "is_null"}


class ScenarioStep(BaseModel):
    name: str
    create_inc: dict[str, Any] | None = Field(default=None, alias="create-inc")
    update_inc: dict[str, Any] | None = Field(default=None, alias="update-inc")
    add_note: dict[str, Any] | str | None = Field(default=None, alias="add-note")
    add_task: dict[str, Any] | None = Field(default=None, alias="add-task")
    update_task: dict[str, Any] | None = Field(default=None, alias="update-task")
    close_incident: dict[str, Any] | str | None = Field(default=None, alias="close-incident")
    run_script: dict[str, Any] | None = Field(default=None, alias="run-script")
    wait_before_run: str | int | float | None = Field(default=None, alias="wait-before-run")

    model_config = {"populate_by_name": True, "extra": "forbid"}

    @model_validator(mode="after")
    def require_action(self) -> "ScenarioStep":
        actions = [
            self.create_inc,
            self.update_inc,
            self.add_note,
            self.add_task,
            self.update_task,
            self.close_incident,
            self.run_script,
            self.wait_before_run,
        ]
        if all(action is None for action in actions):
            raise ValueError(f"step '{self.name}' must define an action or wait-before-run")
        return self


class Scenario(BaseModel):
    id: str
    steps: list[ScenarioStep]
    validations: dict[str, Any] = Field(default_factory=dict, alias="validate")
    allow_failure: bool = False
    incident_id: int | None = None
    source: Path | None = None

    model_config = {"arbitrary_types_allowed": True, "populate_by_name": True}

    @field_validator("steps")
    @classmethod
    def require_steps(cls, value: list[ScenarioStep]) -> list[ScenarioStep]:
        if not value:
            raise ValueError("scenario must contain at least one executable step")
        return value


@dataclass
class ValidationFailure:
    path: str
    assertion: str
    expected: Any
    actual: Any
    message: str


@dataclass
class StepResult:
    name: str
    action: str
    passed: bool = True
    error: str | None = None


@dataclass
class ScenarioResult:
    id: str
    passed: bool
    source: str | None = None
    allow_failure: bool = False
    steps: list[StepResult] = field(default_factory=list)
    validation_failures: list[ValidationFailure] = field(default_factory=list)
    error: str | None = None
    incident_id: int | None = None

    @property
    def counts_as_passed(self) -> bool:
        return self.passed or self.allow_failure


@dataclass
class RunReport:
    results: list[ScenarioResult]
    cleanup_ran: bool
    cleanup_deleted_ids: list[int]

    @property
    def passed(self) -> bool:
        return all(result.counts_as_passed for result in self.results)

    @property
    def failed_results(self) -> list[ScenarioResult]:
        return [result for result in self.results if not result.passed and not result.allow_failure]

    @property
    def allowed_failure_results(self) -> list[ScenarioResult]:
        return [result for result in self.results if not result.passed and result.allow_failure]
