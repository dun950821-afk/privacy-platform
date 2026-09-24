from app.services.finding_service import compute_finding_uid


def test_finding_uid_is_stable():
    a = compute_finding_uid("PRIVACY_CONTACTS_NETWORK", "abc")
    b = compute_finding_uid("PRIVACY_CONTACTS_NETWORK", "abc")
    assert a == b
    assert len(a) == 64


def test_finding_uid_changes_with_dedup_key():
    assert compute_finding_uid("X_CODE", "a") != compute_finding_uid("X_CODE", "b")
