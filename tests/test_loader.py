from pathlib import Path

from resilient_regression.loader import load_scenario_file, load_scenarios


def test_loads_list_style_yaml_scenario_with_create_update_and_validate_steps(tmp_path: Path):
    path = tmp_path / "incident_update.yaml"
    path.write_text(
        """
incident-update-validates-property:
  - create incident with initial property:
      create-inc:
        name: Test Incident
        properties.field_1: value
  - validate:
      properties.field_1: value
""".strip(),
        encoding="utf-8",
    )

    scenarios = load_scenario_file(path)

    assert len(scenarios) == 1
    assert scenarios[0].id == "incident-update-validates-property"
    assert scenarios[0].steps[0].name == "create incident with initial property"
    assert scenarios[0].steps[0].create_inc == {"name": "Test Incident", "properties.field_1": "value"}
    assert scenarios[0].validations == {"properties.field_1": "value"}


def test_loads_mapping_style_scenario_with_allow_failure_and_top_level_validate(tmp_path: Path):
    path = tmp_path / "allow_failure.yaml"
    path.write_text(
        """
known-broken-incident-name-regression:
  allow_failure: true
  incident_id: 1
  steps:
    - create incident with current behavior:
        create-inc:
          name: Known Broken
  validate:
    name: Other
""".strip(),
        encoding="utf-8",
    )

    scenarios = load_scenario_file(path)

    assert scenarios[0].id == "known-broken-incident-name-regression"
    assert scenarios[0].allow_failure is True
    assert scenarios[0].incident_id == 1
    assert scenarios[0].validations == {"name": "Other"}


def test_loads_every_supported_action_from_yaml(tmp_path: Path):
    path = tmp_path / "all_actions.yaml"
    path.write_text(
        """
full-action-syntax-loads:
  - create incident:
      create-inc:
        name: Full Action Incident
  - update incident:
      update-inc:
        properties.field_1: updated
  - add note:
      add-note:
        text: "Incident ${incident.id} note"
  - add task:
      add-task:
        name: "Review ${incident.name}"
  - update task:
      update-task:
        id: "${task.id}"
        status: Closed
  - run script:
      run-script:
        name: Mock Script
        inputs:
          incident_id: "${incident.id}"
  - close incident:
      close-incident:
        status: Closed
  - wait before validation:
      wait-before-run: 1 sec
  - validate:
      status: Closed
""".strip(),
        encoding="utf-8",
    )

    scenario = load_scenario_file(path)[0]

    assert scenario.steps[0].create_inc == {"name": "Full Action Incident"}
    assert scenario.steps[1].update_inc == {"properties.field_1": "updated"}
    assert scenario.steps[2].add_note == {"text": "Incident ${incident.id} note"}
    assert scenario.steps[3].add_task == {"name": "Review ${incident.name}"}
    assert scenario.steps[4].update_task == {"id": "${task.id}", "status": "Closed"}
    assert scenario.steps[5].run_script == {"name": "Mock Script", "inputs": {"incident_id": "${incident.id}"}}
    assert scenario.steps[6].close_incident == {"status": "Closed"}
    assert scenario.steps[7].wait_before_run == "1 sec"
    assert scenario.validations == {"status": "Closed"}


def test_loads_all_yaml_files_from_directory_in_sorted_order(tmp_path: Path):
    (tmp_path / "create_incident_a.yaml").write_text(
        """
creates-incident-from-first-file:
  - create incident:
      create-inc:
        name: One
""".strip(),
        encoding="utf-8",
    )
    (tmp_path / "create_incident_b.yaml").write_text(
        """
creates-incident-from-second-file:
  - create incident:
      create-inc:
        name: Two
""".strip(),
        encoding="utf-8",
    )

    scenarios = load_scenarios([tmp_path])

    assert [scenario.id for scenario in scenarios] == [
        "creates-incident-from-first-file",
        "creates-incident-from-second-file",
    ]
