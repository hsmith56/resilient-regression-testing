from pathlib import Path

from resilient_regression.loader import load_scenario_file, load_scenarios


def test_loads_yaml_scenario(tmp_path: Path):
    path = tmp_path / "scenario.yaml"
    path.write_text(
        """
test-one:
  - step-1:
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
    assert scenarios[0].id == "test-one"
    assert scenarios[0].steps[0].create_inc == {"name": "Test Incident", "properties.field_1": "value"}
    assert scenarios[0].validations == {"properties.field_1": "value"}


def test_loads_mapping_scenario_with_allow_failure(tmp_path: Path):
    path = tmp_path / "scenario.yaml"
    path.write_text(
        """
known-broken:
  allow_failure: true
  steps:
    - step-1:
        create-inc:
          name: Known Broken
  validate:
    name: Other
""".strip(),
        encoding="utf-8",
    )

    scenarios = load_scenario_file(path)

    assert scenarios[0].allow_failure is True
    assert scenarios[0].validations == {"name": "Other"}


def test_loads_all_yaml_files_from_directory(tmp_path: Path):
    (tmp_path / "create_test_1.yaml").write_text(
        """
test-one:
  - step-1:
      create-inc:
        name: One
""".strip(),
        encoding="utf-8",
    )
    (tmp_path / "create_test_2.yaml").write_text(
        """
test-two:
  - step-1:
      create-inc:
        name: Two
""".strip(),
        encoding="utf-8",
    )

    scenarios = load_scenarios([tmp_path])

    assert [scenario.id for scenario in scenarios] == ["test-one", "test-two"]
