from app.services.correlation import correlate, observation_dedup_key
from app.services.rule_seed import BUILTIN_CORRELATION_RULES

RULES = [{"rule": type("R", (), {"id": 1})(), "version": type("V", (), {"version": "1.0"})(),
          "content": BUILTIN_CORRELATION_RULES[0]["content"]}]

# 观察对象形状取自真实引擎产物（端到端任务 465 / app_version 11）：
# androguard 的 fact.sensitive_permission（subject 为短名, payload.category 为分类）；
# appshark 的 dataflow.privacy（payload.rule 为 AppShark 规则名, payload.sink 为方法签名列表）
CONTACTS_PERMISSION = {"id": 1, "observation_type": "fact.sensitive_permission", "subject": "READ_CONTACTS",
                       "payload": {"api": "READ_CONTACTS", "category": "CONTACTS", "permission": "READ_CONTACTS"}}
CONTACTS_FLOW = {"id": 2, "observation_type": "dataflow.privacy",
                 "subject": "['<com.intsig.view.ICCardAuthUtil: java.lang.String report(android.content.Context)>->$r10']",
                 "payload": {"section": "ComplianceInfo", "rule": "DeviceId_NetworkTransfer", "level": "L3",
                             "detail": "设备标识符(IMEI/IMSI/序列号/MAC/AndroidId)通过网络发送",
                             "sink": ["<com.intsig.view.ICCardAuthUtil: java.lang.String report(android.content.Context)>->$r10"],
                             "source": ["<com.intsig.view.ICCardAuthUtil: java.lang.String getDeviceId(android.content.Context)>->$r1"]}}


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
