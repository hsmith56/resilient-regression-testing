from resilient_regression.validators import validate_incident


INCIDENT = {
    "id": 1,
    "name": "Test",
    "properties": {"field_1": "value", "field_2": None},
    "type_ids": ["malware", "phishing"],
    "notes": [{"id": 5000, "text": "Created Test"}],
    "tasks": [{"id": 1000, "name": "Review Test", "status": "Closed"}],
    "script_runs": [{"id": 9000, "name": "Mock Script", "result": {"score": 95}}],
}


def test_validates_dotted_paths_incident_prefix_and_list_indexes():
    failures = validate_incident(
        INCIDENT,
        {
            "properties.field_1": "value",
            "incident.type_ids": {"contains": "phishing"},
            "notes.0.text": "Created Test",
            "tasks.0.status": "Closed",
            "script_runs.0.result.score": 95,
        },
    )

    assert failures == []


def test_validates_equality_contains_exists_not_null_and_is_null_operators():
    failures = validate_incident(
        INCIDENT,
        {
            "name": {"equals": "Test"},
            "properties.field_1": {"exists": True, "not_null": True},
            "properties.field_2": {"is_null": True},
            "missing.optional_field": {"exists": False},
            "type_ids": {"contains": "malware"},
        },
    )

    assert failures == []


def test_failed_validation_reports_expected_actual_and_path():
    failures = validate_incident(INCIDENT, {"properties.field_1": "other"})

    assert len(failures) == 1
    assert failures[0].path == "properties.field_1"
    assert failures[0].expected == "other"
    assert failures[0].actual == "value"
