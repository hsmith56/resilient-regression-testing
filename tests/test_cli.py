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


def test_real_mode_requires_config(capsys):
    exit_code = cli.main(["run", "scenarios/example.yaml"])

    captured = capsys.readouterr()
    assert exit_code == 2
    assert "real mode requires --config app.config" in captured.err


def test_dry_run_does_not_require_config(monkeypatch):
    monkeypatch.setattr(cli, "load_scenarios", lambda paths: [])
    monkeypatch.setattr(cli, "ScenarioRunner", FakeRunner)

    exit_code = cli.main(["run", "scenarios/example.yaml", "--dry-run"])

    assert exit_code == 0
    assert isinstance(FakeRunner.last_client, MockSoarClient)
    assert FakeRunner.last_config.dry_run is True


def test_real_mode_selects_real_client_with_config(monkeypatch, tmp_path):
    config = tmp_path / "app.config"
    config.write_text("[resilient]\nhost=https://soar.example.test\norg=201\napi_key_id=id\napi_key_secret=secret\n", encoding="utf-8")

    class FakeRealClient:
        def __init__(self, config_path):
            self.config_path = config_path

    monkeypatch.setattr(cli, "load_scenarios", lambda paths: [])
    monkeypatch.setattr(cli, "ScenarioRunner", FakeRunner)
    monkeypatch.setattr(cli, "RealSoarClient", FakeRealClient)

    exit_code = cli.main(["run", "scenarios/example.yaml", "--config", str(config)])

    assert exit_code == 0
    assert isinstance(FakeRunner.last_client, FakeRealClient)
    assert FakeRunner.last_client.config_path == str(config)
    assert FakeRunner.last_config.dry_run is False


def test_config_setup_error_does_not_print_secret(monkeypatch, tmp_path, capsys):
    config = tmp_path / "app.config"
    config.write_text("[resilient]\napi_key_secret=super-secret-token\n", encoding="utf-8")
    monkeypatch.setattr(cli, "load_scenarios", lambda paths: [])

    exit_code = cli.main(["run", "scenarios/example.yaml", "--config", str(config)])

    captured = capsys.readouterr()
    assert exit_code == 2
    assert "super-secret-token" not in captured.err
