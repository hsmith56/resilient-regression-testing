from resilient_regression.models import RunReport, ScenarioResult
from resilient_regression.reporting import print_report


def test_print_report_shows_incident_id_per_scenario(capsys):
    report = RunReport(
        results=[
            ScenarioResult(id="scenario-with-incident", passed=True, source="test.yaml", incident_id=42),
            ScenarioResult(id="scenario-without-incident", passed=False, source="test.yaml", error="failed before incident"),
        ],
        cleanup_ran=True,
        cleanup_deleted_ids=[],
    )

    print_report(report)

    output = capsys.readouterr().out
    assert "Incident" in output
    assert "42" in output
    assert "scenario-with-incident" in output
    assert "scenario-without-incident" in output
