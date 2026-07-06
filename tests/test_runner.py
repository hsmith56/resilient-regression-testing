from resilient_regression.client import MockSoarClient
from resilient_regression.models import Scenario, ScenarioStep
from resilient_regression.runner import RunnerConfig, ScenarioRunner


def test_create_and_update_incident_then_validate_dotted_properties():
    scenario = Scenario(
        id="creates-incident-updates-properties-and-validates-final-state",
        steps=[
            ScenarioStep(name="create incident with field one", create_inc={"name": "Test", "properties.field_1": "one"}),
            ScenarioStep(name="update incident with field two", update_inc={"properties.field_2": "two"}),
        ],
        validate={"properties.field_1": "one", "properties.field_2": {"equals": "two"}},
    )
    client = MockSoarClient()
    runner = ScenarioRunner(client=client, config=RunnerConfig(dry_run=True))

    report = runner.run([scenario])

    assert report.passed is True
    assert report.cleanup_ran is True
    assert client.incident_count == 0


def test_run_continues_after_one_scenario_validation_failure():
    failing_scenario = Scenario(
        id="fails-when-incident-field-does-not-match-expected-value",
        steps=[ScenarioStep(name="create incident with actual value", create_inc={"properties.field_1": "actual"})],
        validate={"properties.field_1": "expected"},
    )
    passing_scenario = Scenario(
        id="passes-after-previous-scenario-failed",
        steps=[ScenarioStep(name="create incident with expected value", create_inc={"properties.field_1": "expected"})],
        validate={"properties.field_1": "expected"},
    )
    runner = ScenarioRunner(config=RunnerConfig(dry_run=True))

    report = runner.run([failing_scenario, passing_scenario])

    assert report.passed is False
    assert [result.passed for result in report.results] == [False, True]


def test_cleanup_runs_even_when_validation_fails():
    scenario = Scenario(
        id="cleanup-runs-after-failed-incident-validation",
        steps=[ScenarioStep(name="create incident that will fail validation", create_inc={"name": "Test"})],
        validate={"name": "Wrong"},
    )
    client = MockSoarClient()
    runner = ScenarioRunner(client=client, config=RunnerConfig(dry_run=True))

    report = runner.run([scenario])

    assert report.cleanup_ran is True
    assert report.cleanup_deleted_ids == [1]
    assert client.incident_count == 0


def test_no_cleanup_leaves_created_incident_in_mock_store():
    scenario = Scenario(
        id="no-cleanup-leaves-created-incident-available",
        steps=[ScenarioStep(name="create incident and keep it", create_inc={"name": "Test"})],
    )
    client = MockSoarClient()
    runner = ScenarioRunner(client=client, config=RunnerConfig(dry_run=True, no_cleanup=True))

    report = runner.run([scenario])

    assert report.cleanup_ran is False
    assert client.incident_count == 1


def test_allow_failure_scenario_does_not_fail_entire_suite():
    scenario = Scenario(
        id="known-broken-scenario-is-reported-but-suite-still-passes",
        steps=[ScenarioStep(name="create incident with actual value", create_inc={"name": "Actual"})],
        validate={"name": "Expected"},
        allow_failure=True,
    )
    runner = ScenarioRunner(config=RunnerConfig(dry_run=True))

    report = runner.run([scenario])

    assert report.results[0].passed is False
    assert report.results[0].allow_failure is True
    assert report.passed is True
    assert report.allowed_failure_results == [report.results[0]]


def test_note_task_script_and_close_actions_share_incident_and_task_variables():
    scenario = Scenario(
        id="creates-note-task-script-run-and-closes-incident-using-predefined-variables",
        steps=[
            ScenarioStep(name="create incident", create_inc={"name": "Incident A"}),
            ScenarioStep(name="add note from incident variables", add_note={"text": "Created ${incident.name} (${incident.id})"}),
            ScenarioStep(name="add review task", add_task={"name": "Review ${incident.name}", "status": "Open"}),
            ScenarioStep(name="close latest task", update_task={"id": "${task.id}", "status": "Closed"}),
            ScenarioStep(name="run mock script", run_script={"name": "Mock Script", "inputs": {"incident_id": "${incident.id}", "task_id": "${task.id}"}}),
            ScenarioStep(name="close incident", close_incident={"status": "Closed"}),
        ],
        validate={
            "status": "Closed",
            "notes.0.text": "Created Incident A (1)",
            "tasks.0.name": "Review Incident A",
            "tasks.0.status": "Closed",
            "script_runs.0.name": "Mock Script",
            "script_runs.0.inputs.incident_id": 1,
            "script_runs.0.inputs.task_id": 1000,
        },
    )
    runner = ScenarioRunner(config=RunnerConfig(dry_run=True))

    report = runner.run([scenario])

    assert report.passed is True
    assert [step.action for step in report.results[0].steps] == [
        "create-inc",
        "add-note",
        "add-task",
        "update-task",
        "run-script",
        "close-incident",
    ]


def test_close_task_closes_task_by_name_from_tasktree():
    scenario = Scenario(
        id="close-task-by-name",
        steps=[
            ScenarioStep(name="create incident", create_inc={"name": "Incident A"}),
            ScenarioStep(name="add task", add_task={"name": "Task to Close", "status": "O"}),
            ScenarioStep(name="close task by name", close_task={"name": "Task to Close"}),
        ],
        validate={"tasks.0.name": "Task to Close", "tasks.0.status": "C"},
    )
    runner = ScenarioRunner(config=RunnerConfig(dry_run=True))

    report = runner.run([scenario])

    assert report.passed is True
    assert [step.action for step in report.results[0].steps] == ["create-inc", "add-task", "close-task"]


def test_complex_workflow_handles_multiple_notes_multiple_tasks_explicit_task_ids_and_script_results():
    scenario = Scenario(
        id="multi-operation-workflow-validates-notes-two-tasks-script-result-and-close-metadata",
        steps=[
            ScenarioStep(
                name="create phishing incident",
                create_inc={"name": "Phishing Case", "properties.severity": "High", "type_ids": ["phishing"]},
            ),
            ScenarioStep(name="add opening note with incident id", add_note="Opened ${incident.name} as ${incident.id}"),
            ScenarioStep(name="add triage task", add_task={"name": "Triage ${incident.name}", "status": "Open"}),
            ScenarioStep(name="complete triage task", update_task={"id": "${task.id}", "status": "Complete", "resolution": "triaged"}),
            ScenarioStep(name="add containment task", add_task={"name": "Contain ${incident.name}", "status": "Open"}),
            ScenarioStep(
                name="run enrichment script with latest task variables",
                run_script={
                    "name": "URL Reputation Enrichment",
                    "status": "Completed",
                    "inputs": {"incident_id": "${incident.id}", "latest_task_id": "${task.id}"},
                    "result": {"score": 95, "category": "malicious"},
                },
            ),
            ScenarioStep(name="close first task by explicit id", update_task={"id": 1000, "status": "Verified Closed"}),
            ScenarioStep(name="add closing note after explicit task update", add_note={"text": "Latest task ${task.name} is ${task.status}"}),
            ScenarioStep(name="close incident with resolution", close_incident={"status": "Closed", "resolution": "Confirmed phishing"}),
        ],
        validate={
            "name": "Phishing Case",
            "status": "Closed",
            "resolution": "Confirmed phishing",
            "properties.severity": "High",
            "type_ids": {"contains": "phishing"},
            "notes.0.text": "Opened Phishing Case as 1",
            "notes.1.text": "Latest task Triage Phishing Case is Verified Closed",
            "tasks.0.name": "Triage Phishing Case",
            "tasks.0.status": "Verified Closed",
            "tasks.0.resolution": "triaged",
            "tasks.1.name": "Contain Phishing Case",
            "tasks.1.status": "Open",
            "script_runs.0.name": "URL Reputation Enrichment",
            "script_runs.0.status": "Completed",
            "script_runs.0.inputs.incident_id": 1,
            "script_runs.0.inputs.latest_task_id": 1001,
            "script_runs.0.result.score": 95,
            "script_runs.0.result.category": "malicious",
        },
    )
    runner = ScenarioRunner(config=RunnerConfig(dry_run=True))

    report = runner.run([scenario])

    assert report.passed is True


def test_incident_response_fields_are_available_as_dotted_variables():
    scenario = Scenario(
        id="created-incident-response-is-available-to-later-steps",
        steps=[
            ScenarioStep(name="create incident", create_inc={"name": "Variable Test", "properties": {"ticket": "TCK-1"}}),
            ScenarioStep(name="copy response property", update_inc={"properties.copied_ticket": "${incident.properties.ticket}"}),
        ],
        validate={"properties.copied_ticket": "TCK-1"},
    )
    runner = ScenarioRunner(config=RunnerConfig(dry_run=True))

    report = runner.run([scenario])

    assert report.passed is True


def test_wait_only_step_is_reported_without_sleeping_in_dry_run():
    scenario = Scenario(
        id="wait-step-is-recorded-but-does-not-sleep-in-dry-run",
        steps=[
            ScenarioStep(name="create incident before wait", create_inc={"name": "Wait Test"}),
            ScenarioStep(name="wait for playbook processing", wait_before_run="10 sec"),
        ],
        validate={"name": "Wait Test"},
    )
    runner = ScenarioRunner(config=RunnerConfig(dry_run=True))

    report = runner.run([scenario])

    assert report.passed is True
    assert [step.action for step in report.results[0].steps] == ["create-inc", "wait-before-run"]


def test_existing_incident_id_runs_actions_against_preexisting_incident():
    client = MockSoarClient()
    incident = client.create_incident({"name": "Existing Incident", "properties.owner": "soc"})
    task = client.add_task(incident["id"], {"name": "Existing Task", "status": "Open"})
    scenario = Scenario(
        id="uses-top-level-incident-id-to-update-existing-incident",
        incident_id=incident["id"],
        steps=[
            ScenarioStep(name="update existing incident field", update_inc={"properties.owner": "tier2"}),
            ScenarioStep(name="add note to existing incident", add_note="Working ${incident.name} (${incident.id})"),
            ScenarioStep(name="close existing task by id", update_task={"id": task["id"], "status": "Closed"}),
            ScenarioStep(name="run script against existing incident", run_script={"name": "Existing Incident Script", "inputs": {"incident_id": "${incident.id}"}}),
            ScenarioStep(name="close existing incident", close_incident={"status": "Closed"}),
        ],
        validate={
            "id": incident["id"],
            "status": "Closed",
            "properties.owner": "tier2",
            "notes.0.text": "Working Existing Incident (1)",
            "tasks.0.status": "Closed",
            "script_runs.0.inputs.incident_id": 1,
        },
    )
    runner = ScenarioRunner(client=client, config=RunnerConfig(dry_run=True))

    report = runner.run([scenario])

    assert report.passed is True
    assert report.results[0].incident_id == 1


def test_existing_incident_id_fails_when_incident_does_not_exist():
    scenario = Scenario(
        id="missing-top-level-incident-id-fails-before-actions-run",
        incident_id=999,
        steps=[ScenarioStep(name="add note to missing incident", add_note="should not work")],
    )
    runner = ScenarioRunner(config=RunnerConfig(dry_run=True))

    report = runner.run([scenario])

    assert report.passed is False
    assert report.results[0].error == "'incident 999 not found'"
    assert report.results[0].steps == []
