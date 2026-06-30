from __future__ import annotations

from copy import deepcopy
from typing import Any


_MISSING = object()


def normalize_path(path: str) -> str:
    return path.removeprefix("incident.")


def set_dotted(target: dict[str, Any], path: str, value: Any) -> None:
    parts = normalize_path(path).split(".")
    current = target
    for part in parts[:-1]:
        existing = current.get(part)
        if not isinstance(existing, dict):
            existing = {}
            current[part] = existing
        current = existing
    current[parts[-1]] = value


def get_dotted(target: dict[str, Any], path: str, default: Any = _MISSING) -> Any:
    parts = normalize_path(path).split(".")
    current: Any = target
    for part in parts:
        if isinstance(current, dict) and part in current:
            current = current[part]
        elif isinstance(current, list) and part.isdigit() and int(part) < len(current):
            current = current[int(part)]
        else:
            if default is _MISSING:
                raise KeyError(path)
            return default
    return current


class MockSoarClient:
    """In-memory IBM SOAR-like incident store for dry-run tests."""

    def __init__(self) -> None:
        self._incidents: dict[int, dict[str, Any]] = {}
        self._next_incident_id = 1
        self._next_task_id = 1000
        self._next_note_id = 5000
        self._next_script_run_id = 9000
        self.created_incident_ids: list[int] = []
        self.deleted_incident_ids: list[int] = []

    def create_incident(self, fields: dict[str, Any]) -> dict[str, Any]:
        incident_id = self._next_incident_id
        self._next_incident_id += 1
        incident: dict[str, Any] = {
            "id": incident_id,
            "status": "Active",
            "properties": {},
            "notes": [],
            "tasks": [],
            "script_runs": [],
        }
        self._apply_fields(incident, fields)
        self._incidents[incident_id] = incident
        self.created_incident_ids.append(incident_id)
        return deepcopy(incident)

    def update_incident(self, incident_id: int, fields: dict[str, Any]) -> dict[str, Any]:
        incident = self._require_incident(incident_id)
        self._apply_fields(incident, fields)
        return deepcopy(incident)

    def add_note(self, incident_id: int, fields: dict[str, Any]) -> dict[str, Any]:
        incident = self._require_incident(incident_id)
        note = {"id": self._next_note_id, **fields}
        self._next_note_id += 1
        incident["notes"].append(note)
        return deepcopy(note)

    def add_task(self, incident_id: int, fields: dict[str, Any]) -> dict[str, Any]:
        incident = self._require_incident(incident_id)
        task = {"id": self._next_task_id, "status": "Open", **fields}
        self._next_task_id += 1
        incident["tasks"].append(task)
        return deepcopy(task)

    def update_task(self, incident_id: int, task_id: int, fields: dict[str, Any]) -> dict[str, Any]:
        incident = self._require_incident(incident_id)
        for task in incident["tasks"]:
            if task["id"] == task_id:
                self._apply_fields(task, fields)
                return deepcopy(task)
        raise KeyError(f"task {task_id} not found")

    def close_incident(self, incident_id: int, fields: dict[str, Any] | None = None) -> dict[str, Any]:
        incident = self._require_incident(incident_id)
        close_fields = {"status": "Closed"}
        if fields:
            close_fields.update(fields)
        self._apply_fields(incident, close_fields)
        return deepcopy(incident)

    def run_script(self, incident_id: int, fields: dict[str, Any]) -> dict[str, Any]:
        incident = self._require_incident(incident_id)
        run = {
            "id": self._next_script_run_id,
            "name": fields.get("name"),
            "status": fields.get("status", "Completed"),
            "inputs": fields.get("inputs", {}),
            "result": fields.get("result", {}),
        }
        self._next_script_run_id += 1
        incident["script_runs"].append(run)
        return deepcopy(run)

    def get_incident(self, incident_id: int) -> dict[str, Any]:
        return deepcopy(self._require_incident(incident_id))

    def delete_incident(self, incident_id: int) -> None:
        self._incidents.pop(incident_id, None)
        if incident_id not in self.deleted_incident_ids:
            self.deleted_incident_ids.append(incident_id)

    def cleanup_created_incidents(self) -> list[int]:
        ids = list(self.created_incident_ids)
        for incident_id in ids:
            self.delete_incident(incident_id)
        return ids

    @property
    def incident_count(self) -> int:
        return len(self._incidents)

    def _require_incident(self, incident_id: int) -> dict[str, Any]:
        if incident_id not in self._incidents:
            raise KeyError(f"incident {incident_id} not found")
        return self._incidents[incident_id]

    @staticmethod
    def _apply_fields(target: dict[str, Any], fields: dict[str, Any]) -> None:
        for key, value in fields.items():
            if "." in key:
                set_dotted(target, key, value)
            else:
                target[key] = value
