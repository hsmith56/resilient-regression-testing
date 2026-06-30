from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from pydantic import ValidationError

from .models import Scenario, ScenarioStep


class ScenarioLoaderError(ValueError):
    pass


def load_scenarios(paths: list[str | Path]) -> list[Scenario]:
    scenarios: list[Scenario] = []
    for path in _expand_paths(paths):
        scenarios.extend(load_scenario_file(path))
    return scenarios


def _expand_paths(paths: list[str | Path]) -> list[Path]:
    expanded: list[Path] = []
    for raw_path in paths:
        path = Path(raw_path)
        if path.is_dir():
            expanded.extend(sorted(path.glob("*.yaml")))
            expanded.extend(sorted(path.glob("*.yml")))
        else:
            expanded.append(path)
    return expanded


def load_scenario_file(path: str | Path) -> list[Scenario]:
    source = Path(path)
    try:
        raw = yaml.safe_load(source.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise ScenarioLoaderError(f"failed to parse {source}: {exc}") from exc

    if not isinstance(raw, dict):
        raise ScenarioLoaderError(f"{source} must contain a top-level mapping")

    scenarios: list[Scenario] = []
    for scenario_id, definition in raw.items():
        scenarios.append(_parse_scenario(str(scenario_id), definition, source))
    return scenarios


def _parse_scenario(scenario_id: str, definition: Any, source: Path) -> Scenario:
    allow_failure = False

    if isinstance(definition, dict):
        allow_failure = bool(definition.get("allow_failure", False))
        entries = definition.get("steps", [])
        validate = definition.get("validate", {}) or {}
    elif isinstance(definition, list):
        entries = definition
        validate = {}
    else:
        raise ScenarioLoaderError(f"scenario {scenario_id} must be a list or mapping")

    if not isinstance(entries, list):
        raise ScenarioLoaderError(f"scenario {scenario_id} steps must be a list")
    if not isinstance(validate, dict):
        raise ScenarioLoaderError(f"scenario {scenario_id} validate must be a mapping")

    steps: list[ScenarioStep] = []
    for entry in entries:
        if not isinstance(entry, dict) or len(entry) != 1:
            raise ScenarioLoaderError(f"scenario {scenario_id} entries must have one step name")
        step_name, body = next(iter(entry.items()))
        if step_name == "allow_failure":
            allow_failure = bool(body)
            continue
        if body is None:
            body = {}
        if not isinstance(body, dict):
            raise ScenarioLoaderError(f"step {step_name} in {scenario_id} must be a mapping")
        if step_name == "validate":
            validate.update(body)
            continue
        try:
            steps.append(ScenarioStep(name=str(step_name), **body))
        except ValidationError as exc:
            raise ScenarioLoaderError(f"invalid step {step_name} in {scenario_id}: {exc}") from exc

    try:
        return Scenario(
            id=scenario_id,
            steps=steps,
            validations=validate,
            allow_failure=allow_failure,
            source=source,
        )
    except ValidationError as exc:
        raise ScenarioLoaderError(f"invalid scenario {scenario_id}: {exc}") from exc
