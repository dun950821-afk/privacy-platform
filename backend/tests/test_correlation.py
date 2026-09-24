from app.services.correlation import correlate, observation_dedup_key

CONTACTS_PERMISSION = {"id": 1, "observation_type": "fact.permission", "subject": "android.permission.READ_CONTACTS"}
CONTACTS_FLOW = {"id": 2, "observation_type": "dataflow.privacy", "subject": "ContactsContract", "payload": {"sink": {"category": "network", "api": "okhttp3.Request"}}}


def test_correlation_requires_both_permission_and_flow():
    assert correlate([CONTACTS_PERMISSION]) == []
    findings = correlate([CONTACTS_PERMISSION, CONTACTS_FLOW])
    assert len(findings) == 1
    assert findings[0]["finding_code"] == "PRIVACY_CONTACTS_NETWORK"
    assert sorted(findings[0]["observation_ids"]) == [1, 2]


def test_dedup_key_is_stable():
    assert observation_dedup_key(CONTACTS_PERMISSION) == observation_dedup_key(CONTACTS_PERMISSION)
