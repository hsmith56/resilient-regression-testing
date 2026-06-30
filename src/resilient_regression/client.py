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
        else:
            if default is _MISSING:
                raise KeyError(path)
            return default
    return current


class MockSoarClient:
    """In-memory IBM SOAR-like incident store for dry-run tests."""

    def __init__(self) -> None:
        self._incidents: dict[int, dict[str, Any]] = {}
        self._next_id = 1
        self.created_incident_ids: list[int] = []
        self.deleted_incident_ids: list[int] = []

    def create_incident(self, fields: dict[str, Any]) -> dict[str, Any]:
        incident_id = self._next_id
        self._next_id += 1
        incident: dict[str, Any] = {"id": incident_id, "properties": {}}
        self._apply_fields(incident, fields)
        self._incidents[incident_id] = incident
        self.created_incident_ids.append(incident_id)
        return deepcopy(incident)

    def update_incident(self, incident_id: int, fields: dict[str, Any]) -> dict[str, Any]:
        if incident_id not in self._incidents:
            raise KeyError(f"incident {incident_id} not found")
        self._apply_fields(self._incidents[incident_id], fields)
        return deepcopy(self._incidents[incident_id])

    def get_incident(self, incident_id: int) -> dict[str, Any]:
        if incident_id not in self._incidents:
            raise KeyError(f"incident {incident_id} not found")
        return deepcopy(self._incidents[incident_id])

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

    @staticmethod
    def _apply_fields(incident: dict[str, Any], fields: dict[str, Any]) -> None:
        for key, value in fields.items():
            if "." in key:
                set_dotted(incident, key, value)
            else:
                incident[key] = value
