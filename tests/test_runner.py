from resilient_regression.client import MockSoarClient
from resilient_regression.models import Scenario, ScenarioStep
from resilient_regression.runner import RunnerConfig, ScenarioRunner


def test_runner_executes_scenario_with_mock_client():
    scenario = Scenario(
        id="test-pass",
        steps=[
            ScenarioStep(name="create", create_inc={"name": "Test", "properties.field_1": "one"}),
            ScenarioStep(name="update", update_inc={"properties.field_2": "two"}),
        ],
        validate={"properties.field_1": "one", "properties.field_2": {"equals": "two"}},
    )
    client = MockSoarClient()
    runner = ScenarioRunner(client=client, config=RunnerConfig(dry_run=True))

    report = runner.run([scenario])

    assert report.passed is True
    assert report.cleanup_ran is True
    assert client.incident_count == 0


def test_runner_continues_after_failure():
    fail = Scenario(
        id="test-fail",
        steps=[ScenarioStep(name="create", create_inc={"properties.field_1": "actual"})],
        validate={"properties.field_1": "expected"},
    )
    passed = Scenario(
        id="test-pass",
        steps=[ScenarioStep(name="create", create_inc={"properties.field_1": "expected"})],
        validate={"properties.field_1": "expected"},
    )
    runner = ScenarioRunner(config=RunnerConfig(dry_run=True))

    report = runner.run([fail, passed])

    assert report.passed is False
    assert [result.passed for result in report.results] == [False, True]


def test_cleanup_runs_after_failure():
    scenario = Scenario(
        id="test-fail-cleanup",
        steps=[ScenarioStep(name="create", create_inc={"name": "Test"})],
        validate={"name": "Wrong"},
    )
    client = MockSoarClient()
    runner = ScenarioRunner(client=client, config=RunnerConfig(dry_run=True))

    report = runner.run([scenario])

    assert report.cleanup_ran is True
    assert report.cleanup_deleted_ids == [1]
    assert client.incident_count == 0


def test_no_cleanup_skips_cleanup():
    scenario = Scenario(id="test-no-cleanup", steps=[ScenarioStep(name="create", create_inc={"name": "Test"})])
    client = MockSoarClient()
    runner = ScenarioRunner(client=client, config=RunnerConfig(dry_run=True, no_cleanup=True))

    report = runner.run([scenario])

    assert report.cleanup_ran is False
    assert client.incident_count == 1


def test_allow_failure_does_not_fail_suite():
    scenario = Scenario(
        id="known-broken",
        steps=[ScenarioStep(name="create", create_inc={"name": "Actual"})],
        validate={"name": "Expected"},
        allow_failure=True,
    )
    runner = ScenarioRunner(config=RunnerConfig(dry_run=True))

    report = runner.run([scenario])

    assert report.results[0].passed is False
    assert report.results[0].allow_failure is True
    assert report.passed is True
    assert report.allowed_failure_results == [report.results[0]]
