from __future__ import annotations

import configparser
from copy import deepcopy
from pathlib import Path
from typing import Any


_MISSING = object()


class SoarClientError(RuntimeError):
    pass


class UnsupportedRealActionError(SoarClientError):
    pass


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


def expand_dotted_fields(fields: dict[str, Any]) -> dict[str, Any]:
    expanded: dict[str, Any] = {}
    for key, value in fields.items():
        if "." in key:
            set_dotted(expanded, key, value)
        else:
            expanded[key] = value
    return expanded


class BaseSoarClient:
    is_dry_run = False

    def __init__(self) -> None:
        self.created_incident_ids: list[int] = []

    def create_incident(self, fields: dict[str, Any]) -> dict[str, Any]:
        raise NotImplementedError

    def update_incident(self, incident_id: int, fields: dict[str, Any]) -> dict[str, Any]:
        raise NotImplementedError

    def get_incident(self, incident_id: int) -> dict[str, Any]:
        raise NotImplementedError

    def close_incident(self, incident_id: int, fields: dict[str, Any] | None = None) -> dict[str, Any]:
        raise NotImplementedError

    def delete_incident(self, incident_id: int) -> None:
        raise UnsupportedRealActionError("delete incident is not enabled for this client")

    def add_note(self, incident_id: int, fields: dict[str, Any]) -> dict[str, Any]:
        raise UnsupportedRealActionError("add-note is not supported in real mode yet")

    def add_task(self, incident_id: int, fields: dict[str, Any]) -> dict[str, Any]:
        raise UnsupportedRealActionError("add-task is not supported in real mode yet")

    def update_task(self, incident_id: int, task_id: int, fields: dict[str, Any]) -> dict[str, Any]:
        raise UnsupportedRealActionError("update-task is not supported in real mode yet")

    def run_script(self, incident_id: int, fields: dict[str, Any]) -> dict[str, Any]:
        raise UnsupportedRealActionError("run-script is dry-run only and is not supported in real mode")

    def cleanup_created_incidents(self) -> list[int]:
        cleaned: list[int] = []
        for incident_id in list(self.created_incident_ids):
            self.close_incident(incident_id, {"status": "Closed", "resolution": "Closed by resilient-regression cleanup"})
            cleaned.append(incident_id)
        return cleaned


class MockSoarClient(BaseSoarClient):
    """In-memory IBM SOAR-like incident store for dry-run tests."""

    is_dry_run = True

    def __init__(self) -> None:
        super().__init__()
        self._incidents: dict[int, dict[str, Any]] = {}
        self._next_incident_id = 1
        self._next_task_id = 1000
        self._next_note_id = 5000
        self._next_script_run_id = 9000
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


class RealSoarClient(BaseSoarClient):
    """IBM SOAR client backed by resilient-circuits app.config loading."""

    def __init__(self, config_path: str | Path, allow_delete: bool = False, resilient_client: Any | None = None) -> None:
        super().__init__()
        self.config_path = Path(config_path)
        self.allow_delete = allow_delete
        self._client = resilient_client or _build_resilient_client(self.config_path)

    def create_incident(self, fields: dict[str, Any]) -> dict[str, Any]:
        incident = self._request("post", "/incidents", expand_dotted_fields(fields))
        self.created_incident_ids.append(int(incident["id"]))
        return incident

    def update_incident(self, incident_id: int, fields: dict[str, Any]) -> dict[str, Any]:
        payload = expand_dotted_fields(fields)
        self._request("patch", f"/incidents/{incident_id}", payload)
        return self.get_incident(incident_id)

    def get_incident(self, incident_id: int) -> dict[str, Any]:
        return self._request("get", f"/incidents/{incident_id}")

    def close_incident(self, incident_id: int, fields: dict[str, Any] | None = None) -> dict[str, Any]:
        payload = {"status": "Closed"}
        if fields:
            payload.update(fields)
        return self.update_incident(incident_id, payload)

    def delete_incident(self, incident_id: int) -> None:
        if not self.allow_delete:
            raise UnsupportedRealActionError("delete incident is disabled; cleanup closes incidents instead")
        self._request("delete", f"/incidents/{incident_id}")

    def _request(self, method: str, path: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        try:
            client_method = getattr(self._client, method)
            if payload is None:
                result = client_method(path)
            else:
                result = client_method(path, payload)
        except Exception as exc:
            raise SoarClientError(f"SOAR API {method.upper()} {path} failed") from exc
        return result or {}


def _build_resilient_client(config_path: Path) -> Any:
    try:
        from resilient_circuits import helpers
        from resilient_circuits.rest_helper import get_resilient_client
    except ImportError as exc:
        raise SoarClientError("real mode requires resilient-circuits; run `uv sync` to install dependencies") from exc

    try:
        _prevalidate_app_config(config_path)
        opts = helpers.get_configs(path_config_file=str(config_path))
        _validate_resilient_options(opts)
        return get_resilient_client(opts)
    except SoarClientError:
        raise
    except Exception as exc:
        raise SoarClientError(f"Unable to create resilient client from app.config at {config_path}") from exc


def _prevalidate_app_config(path: Path) -> None:
    parser = configparser.ConfigParser()
    if not parser.read(path):
        raise SoarClientError(f"Unable to read app.config at {path}")
    if "resilient" not in parser:
        raise SoarClientError("app.config missing [resilient] section")
    section = parser["resilient"]
    required = ["host", "org"]
    missing = [key for key in required if not section.get(key)]
    has_api_key = bool(section.get("api_key_id") and section.get("api_key_secret"))
    has_password = bool(section.get("email") and section.get("password"))
    if missing or not (has_api_key or has_password):
        missing_text = ", ".join(missing + ([] if has_api_key or has_password else ["api_key_id/api_key_secret or email/password"]))
        raise SoarClientError(f"app.config missing required resilient setting(s): {missing_text}")


def _validate_resilient_options(opts: dict[str, Any]) -> None:
    required = ["host", "org"]
    missing = [key for key in required if not opts.get(key)]
    has_api_key = bool(opts.get("api_key_id") and opts.get("api_key_secret"))
    has_password = bool(opts.get("email") and opts.get("password"))
    if missing or not (has_api_key or has_password):
        missing_text = ", ".join(missing + ([] if has_api_key or has_password else ["api_key_id/api_key_secret or email/password"]))
        raise SoarClientError(f"app.config missing required resilient setting(s): {missing_text}")
