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
    assert correlate([CONTACTS_PERMISSION], RULES).findings == []
    findings = correlate([CONTACTS_PERMISSION, CONTACTS_FLOW], RULES).findings
    assert len(findings) == 1
    assert findings[0]["finding_code"] == "PRIVACY_CONTACTS_NETWORK"
    assert sorted(findings[0]["observation_ids"]) == [1, 2]


def test_dedup_key_is_stable():
    assert observation_dedup_key(CONTACTS_PERMISSION) == observation_dedup_key(CONTACTS_PERMISSION)


def test_legacy_literal_rule_is_disabled_and_never_ships_active():
    """通讯录规则必须停用，且不得随种子以启用状态发货。

    它的第 2 个条件是 `payload.rule contains _NetworkTransfer`，会把设备标识与
    位置信息的网络流一并匹配进来：实测 task 810 上，这条规则在一个**没有任何
    通讯录数据流**的样本上产出「通讯录信息存在潜在网络传输路径」，其证据是
    1 条通讯录权限 + 18 条 device_information 流 + 30 条 location 流。

    通讯录的「读取→外传」在当前引擎能力下不可静态表达（Task 1 结论），这条规则
    改不对，只能停用。这条断言防的是「某次改动把它又打开」。
    """
    rule = next(r for r in BUILTIN_CORRELATION_RULES if r["rule_key"] == "PRIVACY_CONTACTS_NETWORK")
    assert rule.get("status") == "disabled"


def test_literal_rule_cannot_tell_device_id_flow_from_contacts():
    """留下这条反例，是为了让「为什么必须停用」有可执行的依据，而不是一句结论。

    同一条 DeviceId_NetworkTransfer 观察，会被 v1 规则当成通讯录的证据。
    """
    device_flow = dict(CONTACTS_FLOW)
    assert "_NetworkTransfer" in device_flow["payload"]["rule"]
    findings = correlate([CONTACTS_PERMISSION, device_flow], RULES).findings
    assert findings and findings[0]["finding_code"] == "PRIVACY_CONTACTS_NETWORK", \
        "这正是误配本身：设备标识的网络流被当作通讯录的证据"


def test_invalid_rule_does_not_suppress_other_rules():
    """单条规则内容非法（如空 rule_content）时，其它规则仍应产出结论。"""
    broken = {"rule": type("R", (), {"id": 9, "rule_key": "BROKEN"})(),
              "version": type("V", (), {"version": "1.0"})(), "content": {}}
    findings = correlate([CONTACTS_PERMISSION, CONTACTS_FLOW], [broken, *RULES]).findings
    assert len(findings) == 1
    assert findings[0]["finding_code"] == "PRIVACY_CONTACTS_NETWORK"
