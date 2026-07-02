from resilient_regression import cli
from resilient_regression.client import MockSoarClient
from resilient_regression.models import RunReport

class FakeRunner:
    last_client = None
    last_config = None

    def __init__(self, client, config):
        FakeRunner.last_client = client
        FakeRunner.last_config = config

    def run(self, scenarios):
        return RunReport(results=[], cleanup_ran=True, cleanup_deleted_ids=[])

def test_real_mode_requires_direct_credentials(capsys):
    exit_code = cli.main(["run", "scenarios/example.yaml"])

    captured = capsys.readouterr()
    assert exit_code == 2
    assert "real mode missing required option" in captured.err
    assert "--host" in captured.err
    assert "--org" in captured.err
    assert "--api-key-id/api-key-secret or user-name/password" in captured.err

def test_real_mode_requires_matching_api_key_pair(capsys):
    exit_code = cli.main(["run", "scenarios/example.yaml", "--host", "https://soar.example.test", "--org", "201", "--api-key-id", "id"])

    captured = capsys.readouterr()
    assert exit_code == 2
    assert "--api-key-secret" in captured.err

def test_real_mode_requires_matching_user_password_pair(capsys):
    exit_code = cli.main(["run", "scenarios/example.yaml", "--host", "https://soar.example.test", "--org", "201", "--user-name", "user@example.test"])

    captured = capsys.readouterr()
    assert exit_code == 2
    assert "--password" in captured.err

def test_real_mode_rejects_both_credential_types(capsys):
    exit_code = cli.main([
        "run",
        "scenarios/example.yaml",
        "--host",
        "https://soar.example.test",
        "--org",
        "201",
        "--api-key-id",
        "id",
        "--api-key-secret",
        "secret",
        "--user-name",
        "user@example.test",
        "--password",
        "password",
    ])

    captured = capsys.readouterr()
    assert exit_code == 2
    assert "either API key credentials or username/password credentials, not both" in captured.err

def test_dry_run_does_not_require_credentials(monkeypatch):
    monkeypatch.setattr(cli, "load_scenarios", lambda paths: [])
    monkeypatch.setattr(cli, "ScenarioRunner", FakeRunner)

    exit_code = cli.main(["run", "scenarios/example.yaml", "--dry-run"])

    assert exit_code == 0
    assert isinstance(FakeRunner.last_client, MockSoarClient)
    assert FakeRunner.last_config.dry_run is True

def test_real_mode_selects_real_client_with_api_key_credentials(monkeypatch):
    class FakeRealClient:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

    monkeypatch.setattr(cli, "load_scenarios", lambda paths: [])
    monkeypatch.setattr(cli, "ScenarioRunner", FakeRunner)
    monkeypatch.setattr(cli, "RealSoarClient", FakeRealClient)

    exit_code = cli.main([
        "run",
        "scenarios/example.yaml",
        "--host",
        "https://soar.example.test",
        "--org",
        "201",
        "--api-key-id",
        "id",
        "--api-key-secret",
        "secret",
    ])

    assert exit_code == 0
    assert isinstance(FakeRunner.last_client, FakeRealClient)
    assert FakeRunner.last_client.kwargs == {
        "host": "https://soar.example.test",
        "org": "201",
        "api_key_id": "id",
        "api_key_secret": "secret",
        "user_name": None,
        "password": None,
    }
    assert FakeRunner.last_config.dry_run is False

def test_real_mode_selects_real_client_with_username_password(monkeypatch):
    class FakeRealClient:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

    monkeypatch.setattr(cli, "load_scenarios", lambda paths: [])
    monkeypatch.setattr(cli, "ScenarioRunner", FakeRunner)
    monkeypatch.setattr(cli, "RealSoarClient", FakeRealClient)

    exit_code = cli.main([
        "run",
        "scenarios/example.yaml",
        "--host",
        "https://soar.example.test",
        "--org",
        "201",
        "--user-name",
        "user@example.test",
        "--password",
        "password",
    ])

    assert exit_code == 0
    assert FakeRunner.last_client.kwargs == {
        "host": "https://soar.example.test",
        "org": "201",
        "api_key_id": None,
        "api_key_secret": None,
        "user_name": "user@example.test",
        "password": "password",
    }
