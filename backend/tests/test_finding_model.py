from app.services.finding_model import PlatformFindingData


def test_platform_finding_defaults():
    finding = PlatformFindingData(task_id=1, finding_code="TEST", title="Test", category="security")
    assert finding.triage_status == "needs_review"
    assert finding.baseline_state == "new"
    assert finding.schema_version == "1.0"
