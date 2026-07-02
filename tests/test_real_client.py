from copy import deepcopy
from typing import Any

import pytest

from resilient_regression.client import BaseSoarClient, RealSoarClient, SoarClientError, build_resilient_options, normalize_patch_field_name, set_dotted

class FakePatch:
    def __init__(self, incident: dict[str, Any]) -> None:
        self.incident = deepcopy(incident)
        self.values: dict[str, Any] = {}

    def add_value(self, field_name: str, value: Any) -> None:
        self.values[field_name] = value
from resilient_regression.models import Scenario, ScenarioStep
from resilient_regression.runner import RunnerConfig, ScenarioRunner

class RecordingRestClient:
    def __init__(self) -> None:
        self.calls: list[tuple[Any, ...]] = []
        self.incidents: dict[int, dict[str, Any]] = {}

    def post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        self.calls.append(("post", path, deepcopy(payload)))
        incident = {"id": 1, "status": "Active", **payload}
        self.incidents[1] = incident
        return incident

    def patch(self, path: str, payload: FakePatch, overwrite_conflict: bool = False) -> dict[str, Any]:
        self.calls.append(("patch", path, deepcopy(payload.values), {"overwrite_conflict": overwrite_conflict}))
        for key, value in payload.values.items():
            if "." in key:
                set_dotted(self.incidents[1], key, value)
            elif key in {"name", "description", "status", "resolution"}:
                self.incidents[1][key] = value
            else:
                set_dotted(self.incidents[1], f"properties.{key}", value)
        return self.incidents[1]

    def get(self, path: str) -> dict[str, Any]:
        self.calls.append(("get", path, None))
        return self.incidents[1]

    def delete(self, path: str) -> dict[str, Any]:
        self.calls.append(("delete", path, None))
        return {}

    def put(self, path: str, payload: list[int]) -> dict[str, Any]:
        self.calls.append(("put", path, payload))
        for incident_id in payload:
            self.incidents.pop(incident_id, None)
        return {}

def test_real_client_uses_resilient_client_methods_and_builds_dotted_payloads(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr("resilient_regression.client.time.time", lambda: 123.456)
    monkeypatch.setattr("resilient_regression.client.ResilientPatch", FakePatch)
    rest_client = RecordingRestClient()
    client = RealSoarClient("https://soar.example.test", "201", resilient_client=rest_client)

    incident = client.create_incident({"name": "Regression", "description": "Created by test", "test_field": "initial"})
    updated = client.update_incident(incident["id"], {"properties.test_field": "updated"})

    assert rest_client.calls[0] == (
        "post",
        "/incidents",
        {
            "name": "Regression",
            "discovered_date": 123456,
            "start_date": 123456,
            "description": "Created by test",
            "properties": {"test_field": "initial"},
        },
    )
    assert rest_client.calls[1] == ("get", "/incidents/1", None)
    assert rest_client.calls[2] == ("patch", "/incidents/1", {"test_field": "updated"}, {"overwrite_conflict": True})
    assert rest_client.calls[3] == ("get", "/incidents/1", None)
    assert updated["properties"] == {"test_field": "updated"}

def test_patch_field_names_strip_incident_and_properties_prefixes():
    assert normalize_patch_field_name("properties.test_field") == "test_field"
    assert normalize_patch_field_name("incident.properties.test_field") == "test_field"
    assert normalize_patch_field_name("name") == "name"


def test_build_resilient_options_supports_api_key_credentials():
    opts = build_resilient_options(
        host="https://soar.example.test",
        org="201",
        api_key_id="test-key",
        api_key_secret="secret-value",
    )

    assert opts == {
        "host": "https://soar.example.test",
        "org": "201",
        "cafile": False,
        "api_key_id": "test-key",
        "api_key_secret": "secret-value",
    }

def test_build_resilient_options_supports_username_password_credentials():
    opts = build_resilient_options(
        host="https://soar.example.test",
        org="201",
        user_name="user@example.test",
        password="secret-value",
    )

    assert opts == {
        "host": "https://soar.example.test",
        "org": "201",
        "cafile": False,
        "email": "user@example.test",
        "user_name": "user@example.test",
        "password": "secret-value",
    }

def test_build_resilient_options_supports_cafile():
    opts = build_resilient_options(
        host="https://soar.example.test",
        org="201",
        api_key_id="test-key",
        api_key_secret="secret-value",
        cafile="/path/to/ca.pem",
    )

    assert opts["cafile"] == "/path/to/ca.pem"


def test_build_resilient_options_does_not_include_secret_in_errors():
    with pytest.raises(SoarClientError) as exc_info:
        build_resilient_options(host="https://soar.example.test", org="201", api_key_secret="super-secret-token")

    assert "super-secret-token" not in str(exc_info.value)
    assert "api_key_id" in str(exc_info.value)

class CleanupRecordingClient(BaseSoarClient):
    def __init__(self) -> None:
        super().__init__()
        self.incidents: dict[int, dict[str, Any]] = {}
        self.closed_ids: list[int] = []

    def create_incident(self, fields: dict[str, Any]) -> dict[str, Any]:
        incident = {"id": 1, "status": "Active", **fields}
        self.incidents[1] = incident
        self.created_incident_ids.append(1)
        return incident

    def update_incident(self, incident_id: int, fields: dict[str, Any]) -> dict[str, Any]:
        self.incidents[incident_id].update(fields)
        return self.incidents[incident_id]

    def get_incident(self, incident_id: int) -> dict[str, Any]:
        if incident_id not in self.incidents:
            raise KeyError(f"incident {incident_id} not found")
        return self.incidents[incident_id]

    def close_incident(self, incident_id: int, fields: dict[str, Any] | None = None) -> dict[str, Any]:
        self.closed_ids.append(incident_id)
        self.incidents[incident_id].update(fields or {"status": "Closed"})
        return self.incidents[incident_id]

def test_cleanup_runs_after_real_mode_failure_and_closes_created_incident():
    client = CleanupRecordingClient()
    scenario = Scenario(
        id="real-cleanup-after-failure",
        steps=[
            ScenarioStep(name="create real incident", create_inc={"name": "Real"}),
            ScenarioStep(name="unsupported real script", run_script={"name": "Not Supported"}),
        ],
    )
    runner = ScenarioRunner(client=client, config=RunnerConfig(dry_run=False))

    report = runner.run([scenario])

    assert report.passed is False
    assert "run-script is dry-run only" in report.results[0].error
    assert report.cleanup_ran is True
    assert client.closed_ids == [1]

def test_real_cleanup_uses_bulk_delete_endpoint():
    rest_client = RecordingRestClient()
    client = RealSoarClient("https://soar.example.test", "201", resilient_client=rest_client)
    scenario = Scenario(
        id="real-cleanup-uses-delete-endpoint",
        steps=[
            ScenarioStep(name="create real incident", create_inc={"name": "Real"}),
            ScenarioStep(name="unsupported real script", run_script={"name": "Not Supported"}),
        ],
    )
    runner = ScenarioRunner(client=client, config=RunnerConfig(dry_run=False))

    report = runner.run([scenario])

    assert report.passed is False
    assert report.cleanup_deleted_ids == [1]
    assert ("put", "/incidents/delete", [1]) in rest_client.calls

def test_user_provided_incident_id_is_not_auto_cleaned():
    client = CleanupRecordingClient()
    client.incidents[99] = {"id": 99, "name": "Existing", "status": "Active"}
    scenario = Scenario(
        id="existing-incident-not-cleaned",
        incident_id=99,
        steps=[ScenarioStep(name="update existing incident", update_inc={"status": "Active"})],
        validate={"id": 99},
    )
    runner = ScenarioRunner(client=client, config=RunnerConfig(dry_run=False))

    report = runner.run([scenario])

    assert report.passed is True
    assert client.closed_ids == []
    assert report.cleanup_deleted_ids == []

def test_unsupported_real_mode_action_fails_clearly():
    rest_client = RecordingRestClient()
    client = RealSoarClient("https://soar.example.test", "201", resilient_client=rest_client)
    incident = client.create_incident({"name": "Existing"})
    scenario = Scenario(
        id="unsupported-real-action",
        incident_id=incident["id"],
        steps=[ScenarioStep(name="run script", run_script={"name": "Dry Run Only"})],
    )
    runner = ScenarioRunner(client=client, config=RunnerConfig(dry_run=False))

    report = runner.run([scenario])

    assert report.passed is False
    assert report.results[0].error == "run-script is dry-run only and is not supported in real mode"
