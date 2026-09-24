from app.services.correlation import correlate, observation_dedup_key
from app.services.rule_seed import BUILTIN_CORRELATION_RULES

RULES = [{"rule": type("R", (), {"id": 1})(), "version": type("V", (), {"version": "1.0"})(),
          "content": BUILTIN_CORRELATION_RULES[0]["content"]}]

CONTACTS_PERMISSION = {"id": 1, "observation_type": "fact.permission", "subject": "android.permission.READ_CONTACTS", "payload": {}}
CONTACTS_FLOW = {"id": 2, "observation_type": "dataflow.privacy", "subject": "ContactsContract", "payload": {"sink": {"category": "network", "api": "okhttp3.Request"}}}


def test_correlation_requires_both_permission_and_flow():
    assert correlate([CONTACTS_PERMISSION], RULES) == []
    findings = correlate([CONTACTS_PERMISSION, CONTACTS_FLOW], RULES)
    assert len(findings) == 1
    assert findings[0]["finding_code"] == "PRIVACY_CONTACTS_NETWORK"
    assert sorted(findings[0]["observation_ids"]) == [1, 2]


def test_dedup_key_is_stable():
    assert observation_dedup_key(CONTACTS_PERMISSION) == observation_dedup_key(CONTACTS_PERMISSION)


def test_invalid_rule_does_not_suppress_other_rules():
    """单条规则内容非法（如空 rule_content）时，其它规则仍应产出结论。"""
    broken = {"rule": type("R", (), {"id": 9, "rule_key": "BROKEN"})(),
              "version": type("V", (), {"version": "1.0"})(), "content": {}}
    findings = correlate([CONTACTS_PERMISSION, CONTACTS_FLOW], [broken, *RULES])
    assert len(findings) == 1
    assert findings[0]["finding_code"] == "PRIVACY_CONTACTS_NETWORK"
