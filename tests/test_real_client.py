from pathlib import Path
from typing import Any

import pytest

from resilient_regression.client import BaseSoarClient, RealSoarClient
from resilient_regression.models import Scenario, ScenarioStep
from resilient_regression.runner import RunnerConfig, ScenarioRunner


def write_app_config(path: Path, secret: str = "secret-value") -> Path:
    path.write_text(
        f"""
[resilient]
host=https://soar.example.test
org=201
api_key_id=test-key
api_key_secret={secret}
""".strip(),
        encoding="utf-8",
    )
    return path


class RecordingRestClient:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, dict[str, Any] | None]] = []
        self.incidents: dict[int, dict[str, Any]] = {}

    def post(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        self.calls.append(("post", path, payload))
        incident = {"id": 1, "status": "Active", **payload}
        self.incidents[1] = incident
        return incident

    def patch(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        self.calls.append(("patch", path, payload))
        self.incidents[1].update(payload)
        return self.incidents[1]

    def get(self, path: str) -> dict[str, Any]:
        self.calls.append(("get", path, None))
        return self.incidents[1]

    def delete(self, path: str) -> dict[str, Any]:
        self.calls.append(("delete", path, None))
        return {}


def test_real_client_uses_resilient_client_methods_and_builds_dotted_payloads(tmp_path: Path):
    rest_client = RecordingRestClient()
    client = RealSoarClient(write_app_config(tmp_path / "app.config"), resilient_client=rest_client)

    incident = client.create_incident({"name": "Regression", "properties.test_field": "initial"})
    updated = client.update_incident(incident["id"], {"properties.test_field": "updated"})

    assert rest_client.calls[0] == (
        "post",
        "/incidents",
        {"name": "Regression", "properties": {"test_field": "initial"}},
    )
    assert rest_client.calls[1] == ("patch", "/incidents/1", {"properties": {"test_field": "updated"}})
    assert rest_client.calls[2] == ("get", "/incidents/1", None)
    assert updated["properties"] == {"test_field": "updated"}


def test_real_client_does_not_include_secret_in_config_errors(tmp_path: Path):
    config = write_app_config(tmp_path / "app.config", secret="super-secret-token")
    text = config.read_text(encoding="utf-8").replace("host=https://soar.example.test\n", "")
    config.write_text(text, encoding="utf-8")

    with pytest.raises(Exception) as exc_info:
        RealSoarClient(config)

    assert "super-secret-token" not in str(exc_info.value)


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


def test_unsupported_real_mode_action_fails_clearly(tmp_path: Path):
    rest_client = RecordingRestClient()
    client = RealSoarClient(write_app_config(tmp_path / "app.config"), resilient_client=rest_client)
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
