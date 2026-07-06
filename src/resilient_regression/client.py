from __future__ import annotations

import inspect
import time
from copy import deepcopy
from typing import Any

from resilient import Patch as ResilientPatch

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

def normalize_patch_field_name(field_name: str) -> str:
    normalized = normalize_path(field_name)
    return normalized.removeprefix("properties.")


def build_resilient_patch(incident: dict[str, Any], fields: dict[str, Any]) -> Any:
    patch = ResilientPatch(incident)
    for field_name, value in fields.items():
        patch.add_value(normalize_patch_field_name(field_name), value)
    return patch


def build_create_incident_payload(fields: dict[str, Any], now_ms: int | None = None) -> dict[str, Any]:
    """Build IBM SOAR /incidents payload from create-inc fields."""
    if "name" not in fields or fields["name"] in (None, ""):
        raise SoarClientError("create-inc requires name")

    timestamp = int(time.time() * 1000) if now_ms is None else now_ms
    payload: dict[str, Any] = {
        "name": fields["name"],
        "discovered_date": timestamp,
        "start_date": timestamp,
    }

    description = fields.get("description")
    if description is not None:
        payload["description"] = description

    properties: dict[str, Any] = {}
    for key, value in fields.items():
        if key in {"name", "description"}:
            continue
        if key == "properties" and isinstance(value, dict):
            properties.update(value)
        elif key.startswith("properties."):
            set_dotted(properties, key.removeprefix("properties."), value)
        else:
            properties[key] = value

    if properties:
        payload["properties"] = properties
    return payload


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

    def resolve_field_value(self, path: str, value: Any) -> Any:
        return value

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

    def get_tasks_for_inc(self, incident_id: int) -> list[dict[str, Any]]:
        raise UnsupportedRealActionError("get-tasks-for-inc is not supported in real mode yet")

    def close_task(self, incident_id: int, name: str) -> dict[str, Any]:
        task = find_task_by_name(self.get_tasks_for_inc(incident_id), name)
        if task is None:
            raise KeyError(f"task named {name!r} not found for incident {incident_id}")
        return self.update_task(incident_id, int(task["id"]), {**task, "status": "C"})

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

    def get_tasks_for_inc(self, incident_id: int) -> list[dict[str, Any]]:
        incident = self._require_incident(incident_id)
        return [
            {
                "child_cats": [],
                "child_tasks": deepcopy(incident["tasks"]),
                "name": "Tasks",
                "parent_id": "",
                "status": "O",
            }
        ]

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
    """IBM SOAR client backed by direct resilient-circuits credentials."""

    def __init__(
        self,
        host: str,
        org: str | int,
        *,
        api_key_id: str | None = None,
        api_key_secret: str | None = None,
        email: str | None = None,
        password: str | None = None,
        cafile: str | bool = False,
        allow_delete: bool = False,
        resilient_client: Any | None = None,
    ) -> None:
        super().__init__()
        self.host = host
        self.org = org
        self.allow_delete = allow_delete
        self._field_value_labels: dict[str, dict[Any, str]] | None = None
        self._field_value_ids: dict[str, dict[Any, Any]] | None = None
        self._multiselect_fields: set[str] | None = None
        self._client = resilient_client or _build_resilient_client(
            host=host,
            org=org,
            api_key_id=api_key_id,
            api_key_secret=api_key_secret,
            email=email,
            password=password,
            cafile=cafile,
        )

    def create_incident(self, fields: dict[str, Any]) -> dict[str, Any]:
        incident = self._request("post", "/incidents", build_create_incident_payload(fields), timeout=50)
        self.created_incident_ids.append(int(incident["id"]))
        return incident

    def update_incident(self, incident_id: int, fields: dict[str, Any]) -> dict[str, Any]:
        uri = f"/incidents/{incident_id}"
        incident = self.get_incident(incident_id)
        patch = self._build_update_patch(incident, fields)
        self._request("patch", uri, patch, overwrite_conflict=True)
        return self.get_incident(incident_id)

    def get_incident(self, incident_id: int) -> dict[str, Any]:
        return self._request("get", f"/incidents/{incident_id}")

    def resolve_field_value(self, path: str, value: Any) -> Any:
        field_name = normalize_patch_field_name(path)
        labels = self._get_field_value_labels().get(field_name)
        if not labels:
            return value
        return _resolve_option_value(value, labels)

    def close_incident(self, incident_id: int, fields: dict[str, Any] | None = None) -> dict[str, Any]:
        payload = {"status": "Closed"}
        if fields:
            payload.update(fields)
        return self.update_incident(incident_id, payload)

    def get_tasks_for_inc(self, incident_id: int) -> list[dict[str, Any]]:
        tasktree = self._request("get", f"/incidents/{incident_id}/tasktree")
        if not isinstance(tasktree, list):
            raise SoarClientError(f"SOAR API GET /incidents/{incident_id}/tasktree returned unexpected response")
        return tasktree

    def close_task(self, incident_id: int, name: str) -> dict[str, Any]:
        task = find_task_by_name(self.get_tasks_for_inc(incident_id), name)
        if task is None:
            raise KeyError(f"task named {name!r} not found for incident {incident_id}")
        payload = deepcopy(task)
        payload["status"] = "C"
        response = self._request("put", f"/tasks/{int(payload['id'])}", payload)
        return response if isinstance(response, dict) and "id" in response else payload

    def delete_incident(self, incident_id: int) -> None:
        if not self.allow_delete:
            raise UnsupportedRealActionError("delete incident is disabled")
        self._request("put", "/incidents/delete", [incident_id])

    def _build_update_patch(self, incident: dict[str, Any], fields: dict[str, Any]) -> Any:
        multiselect_fields = self._get_multiselect_fields()
        if not any(normalize_patch_field_name(field_name) in multiselect_fields for field_name in fields):
            return build_resilient_patch(incident, fields)

        changes: list[dict[str, Any]] = []
        field_value_ids = self._get_field_value_ids()
        for field_name, value in fields.items():
            normalized = normalize_patch_field_name(field_name)
            if normalized in multiselect_fields:
                changes.append(
                    {
                        "field": normalized,
                        "old_value": _current_multiselect_patch_value(incident, normalized),
                        "new_value": {"ids": _multiselect_ids_for_value(value, field_value_ids.get(normalized, {}))},
                    }
                )
            else:
                changes.append(
                    {
                        "field": normalized,
                        "old_value": {"object": get_dotted(incident, normalized, default=None)},
                        "new_value": {"object": value},
                    }
                )
        patch: dict[str, Any] = {"changes": changes}
        if incident.get("vers"):
            patch["version"] = incident["vers"]
        return patch

    def _get_field_value_labels(self) -> dict[str, dict[Any, str]]:
        self._ensure_field_metadata()
        return self._field_value_labels or {}

    def _get_field_value_ids(self) -> dict[str, dict[Any, Any]]:
        self._ensure_field_metadata()
        return self._field_value_ids or {}

    def _get_multiselect_fields(self) -> set[str]:
        self._ensure_field_metadata()
        return self._multiselect_fields or set()

    def _ensure_field_metadata(self) -> None:
        if self._field_value_labels is not None:
            return
        self._field_value_labels = {}
        self._field_value_ids = {}
        self._multiselect_fields = set()
        try:
            fields = self._request("get", "/types/incident/fields")
        except SoarClientError:
            return
        for field in _iter_field_definitions(fields):
            field_name = _field_api_name(field)
            if not field_name:
                continue
            value_labels = _field_value_labels(field)
            value_ids = _field_value_ids(field)
            if value_labels:
                self._field_value_labels[field_name] = value_labels
            if value_ids:
                self._field_value_ids[field_name] = value_ids
            if _field_is_multiselect(field):
                self._multiselect_fields.add(field_name)

    def cleanup_created_incidents(self) -> list[int]:
        ids = list(self.created_incident_ids)
        if ids:
            self._request("put", "/incidents/delete", ids)
        return ids

    def _request(
        self,
        method: str,
        path: str,
        payload: Any | None = None,
        timeout: int | None = None,
        **request_kwargs: Any,
    ) -> Any:
        try:
            client_method = getattr(self._client, method)
            kwargs = {"timeout": timeout} if timeout is not None and _accepts_keyword(client_method, "timeout") else {}
            kwargs.update(request_kwargs)
            if payload is None:
                result = client_method(path, **kwargs)
            else:
                result = client_method(path, payload, **kwargs)
        except Exception as exc:
            raise SoarClientError(f"SOAR API {method.upper()} {path} failed") from exc
        return result if result is not None else {}

def find_task_by_name(tasktree: Any, name: str) -> dict[str, Any] | None:
    for task in _iter_tasktree_tasks(tasktree):
        if task.get("name") == name:
            return deepcopy(task)
    return None


def _iter_tasktree_tasks(node: Any) -> list[dict[str, Any]]:
    tasks: list[dict[str, Any]] = []
    if isinstance(node, list):
        for item in node:
            tasks.extend(_iter_tasktree_tasks(item))
    elif isinstance(node, dict):
        child_tasks = node.get("child_tasks")
        if isinstance(child_tasks, list):
            tasks.extend(task for task in child_tasks if isinstance(task, dict))
        child_cats = node.get("child_cats")
        if isinstance(child_cats, list):
            tasks.extend(_iter_tasktree_tasks(child_cats))
    return tasks


def _iter_field_definitions(fields: Any) -> list[dict[str, Any]]:
    if isinstance(fields, list):
        return [field for field in fields if isinstance(field, dict)]
    if isinstance(fields, dict):
        for key in ("fields", "entities"):
            value = fields.get(key)
            if isinstance(value, list):
                return [field for field in value if isinstance(field, dict)]
        return [field for field in fields.values() if isinstance(field, dict)]
    return []


def _field_api_name(field: dict[str, Any]) -> str | None:
    for key in ("name", "api_name", "apiName", "property_name"):
        value = field.get(key)
        if isinstance(value, str) and value:
            return normalize_patch_field_name(value)
    return None


def _field_value_labels(field: dict[str, Any]) -> dict[Any, str]:
    labels: dict[Any, str] = {}
    for option in _iter_field_options(field):
        value = _option_value(option)
        label = _option_label(option)
        if value is not _MISSING and label is not None:
            _store_option_label(labels, value, label)
    return labels


def _field_value_ids(field: dict[str, Any]) -> dict[Any, Any]:
    ids: dict[Any, Any] = {}
    for option in _iter_field_options(field):
        value = _option_value(option)
        label = _option_label(option)
        if value is not _MISSING and label is not None:
            ids[label] = value
            ids[str(label)] = value
    return ids


def _field_is_multiselect(field: dict[str, Any]) -> bool:
    if "multi_select_values" in field or "multiselect_values" in field:
        return True
    for key in ("input_type", "inputType", "type", "field_type", "fieldType"):
        value = field.get(key)
        if isinstance(value, str) and "multi" in value.lower() and "select" in value.lower():
            return True
    return False


def _iter_field_options(field: dict[str, Any]) -> list[dict[str, Any]]:
    for key in ("values", "options", "select_values", "multi_select_values", "multiselect_values"):
        value = field.get(key)
        if isinstance(value, list):
            return [_option_from_list_item(option) for option in value]
        if isinstance(value, dict):
            return [_option_from_mapping(item_key, item_value) for item_key, item_value in value.items()]
    return []


def _current_multiselect_patch_value(incident: dict[str, Any], field_name: str) -> dict[str, list[Any]]:
    current = get_dotted(incident, f"properties.{field_name}", default=get_dotted(incident, field_name, default=None))
    if isinstance(current, dict) and isinstance(current.get("ids"), list):
        return {"ids": list(current["ids"])}
    if isinstance(current, list):
        return {"ids": list(current)}
    if current in (None, ""):
        return {"ids": []}
    return {"ids": [current]}


def _multiselect_ids_for_value(value: Any, ids_by_label: dict[Any, Any]) -> list[Any]:
    if isinstance(value, dict) and isinstance(value.get("ids"), list):
        return [_option_id_for_value(item, ids_by_label) for item in value["ids"]]
    if isinstance(value, (list, tuple, set)):
        return [_option_id_for_value(item, ids_by_label) for item in value]
    if value in (None, ""):
        return []
    return [_option_id_for_value(value, ids_by_label)]


def _option_id_for_value(value: Any, ids_by_label: dict[Any, Any]) -> Any:
    if isinstance(value, dict):
        option_value = _option_value(value)
        if option_value is not _MISSING:
            return option_value
        label = _option_label(value)
        if label is not None:
            return ids_by_label.get(label, ids_by_label.get(str(label), label))
    return ids_by_label.get(value, ids_by_label.get(str(value), value))


def _option_from_list_item(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    return {"value": value, "label": str(value)}


def _option_from_mapping(key: Any, value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return {"value": key, **value}
    return {"value": key, "label": value}


def _store_option_label(labels: dict[Any, str], value: Any, label: str) -> None:
    if isinstance(value, (list, dict, set)):
        return
    labels[value] = label
    labels[str(value)] = label


def _resolve_option_value(value: Any, labels: dict[Any, str]) -> Any:
    if isinstance(value, list):
        return [_resolve_option_value(item, labels) for item in value]
    if isinstance(value, tuple):
        return tuple(_resolve_option_value(item, labels) for item in value)
    if isinstance(value, set):
        return {_resolve_option_value(item, labels) for item in value}
    if isinstance(value, dict):
        ids = value.get("ids")
        if isinstance(ids, list):
            return [_resolve_option_value(item, labels) for item in ids]
        option_value = _option_value(value)
        if option_value is not _MISSING:
            resolved = _resolve_option_value(option_value, labels)
            if resolved != option_value:
                return resolved
        label = _option_label(value)
        if label is not None:
            return label
        return {key: _resolve_option_value(item, labels) for key, item in value.items()}
    return labels.get(value, labels.get(str(value), value))


def _option_value(option: dict[str, Any]) -> Any:
    for key in ("value", "id", "uuid", "key"):
        if key in option:
            return option[key]
    return _MISSING


def _option_label(option: dict[str, Any]) -> str | None:
    for key in ("label", "display_name", "displayName", "name", "text"):
        value = option.get(key)
        if isinstance(value, str):
            return value
    return None


def _accepts_keyword(func: Any, keyword: str) -> bool:
    try:
        signature = inspect.signature(func)
    except (TypeError, ValueError):
        return False
    return any(
        parameter.kind == inspect.Parameter.VAR_KEYWORD or name == keyword
        for name, parameter in signature.parameters.items()
    )


def _build_resilient_client(
    *,
    host: str,
    org: str | int,
    api_key_id: str | None = None,
    api_key_secret: str | None = None,
    email: str | None = None,
    password: str | None = None,
    cafile: str | bool = False,
) -> Any:
    try:
        from resilient_circuits.rest_helper import get_resilient_client
    except ImportError as exc:
        raise SoarClientError("real mode requires resilient-circuits; run `uv sync` to install dependencies") from exc

    try:
        opts = build_resilient_options(
            host=host,
            org=org,
            api_key_id=api_key_id,
            api_key_secret=api_key_secret,
            email=email,
            password=password,
            cafile=cafile,
        )
        return get_resilient_client(opts)
    except SoarClientError:
        raise
    except Exception as exc:
        raise SoarClientError("Unable to create resilient client from provided credentials") from exc


def build_resilient_options(
    *,
    host: str | None,
    org: str | int | None,
    api_key_id: str | None = None,
    api_key_secret: str | None = None,
    email: str | None = None,
    password: str | None = None,
    cafile: str | bool = False,
) -> dict[str, Any]:
    missing = [name for name, value in (("host", host), ("org", org)) if value in (None, "")]
    has_api_key_id = bool(api_key_id)
    has_api_key_secret = bool(api_key_secret)
    has_email = bool(email)
    has_password = bool(password)

    if has_api_key_id != has_api_key_secret:
        missing.append("api_key_secret" if has_api_key_id else "api_key_id")
    if has_email != has_password:
        missing.append("password" if has_email else "email")
    if has_api_key_id and has_email:
        raise SoarClientError("provide either API key credentials or email/password credentials, not both")
    if not (has_api_key_id or has_email):
        missing.append("api_key_id/api_key_secret or email/password")
    if missing:
        raise SoarClientError(f"missing required real mode setting(s): {', '.join(missing)}")

    opts: dict[str, Any] = {"host": host, "org": org, "cafile": cafile}
    if has_api_key_id:
        opts.update({"api_key_id": api_key_id, "api_key_secret": api_key_secret})
    else:
        opts.update({"email": email, "password": password})
    return opts
