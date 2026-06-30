from resilient_regression.validators import validate_incident


INCIDENT = {
    "id": 1,
    "name": "Test",
    "properties": {"field_1": "value", "field_2": None},
    "type_ids": ["malware", "phishing"],
}


def test_dotted_path_equals_and_incident_prefix():
    failures = validate_incident(
        INCIDENT,
        {
            "properties.field_1": "value",
            "incident.type_ids": {"contains": "phishing"},
        },
    )

    assert failures == []


def test_validation_operators():
    failures = validate_incident(
        INCIDENT,
        {
            "name": {"equals": "Test"},
            "properties.field_1": {"exists": True},
            "properties.field_1": {"not_null": True},
            "properties.field_2": {"is_null": True},
            "type_ids": {"contains": "malware"},
        },
    )

    assert failures == []


def test_failed_validation_reports_expected_actual():
    failures = validate_incident(INCIDENT, {"properties.field_1": "other"})

    assert len(failures) == 1
    assert failures[0].expected == "other"
    assert failures[0].actual == "value"
