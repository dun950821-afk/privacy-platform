from app.services.correlation import correlate
from app.services.finding_baseline import apply_mas_mapping


def test_finding_payload_is_complete_for_persistence():
    observations = [
        {"id": 1, "observation_type": "fact.permission", "subject": "android.permission.READ_CONTACTS", "payload": {}},
        {"id": 2, "observation_type": "dataflow.privacy", "subject": "Contacts", "payload": {"sink": {"category": "network"}}},
    ]
    findings = [apply_mas_mapping(f) for f in correlate(observations)]
    assert len(findings) == 1
    finding = findings[0]
    for key in ("finding_code", "title", "category", "severity", "recommendation", "dedup_key", "observation_ids"):
        assert key in finding
    assert finding["maswe_ids"]
