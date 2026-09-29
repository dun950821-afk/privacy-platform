from app.services.correlation import correlate
from app.services.rule_seed import BUILTIN_CORRELATION_RULES

RULES = [{"rule": type("R", (), {"id": 1})(), "version": type("V", (), {"version": "1.0"})(),
          "content": BUILTIN_CORRELATION_RULES[0]["content"]}]


def test_finding_payload_is_complete_for_persistence():
    # 形状取自真实引擎产物（端到端任务 465）
    observations = [
        {"id": 1, "observation_type": "fact.sensitive_permission", "subject": "READ_CONTACTS",
         "payload": {"api": "READ_CONTACTS", "category": "CONTACTS", "permission": "READ_CONTACTS"}},
        {"id": 2, "observation_type": "dataflow.privacy",
         "subject": "['<com.baidu.mobstat.ba: java.net.HttpURLConnection a(android.content.Context,java.lang.String,int,int)>->$r0']",
         "payload": {"section": "ComplianceInfo", "rule": "DeviceId_NetworkTransfer", "level": "L3",
                     "sink": ["<com.baidu.mobstat.ba: java.net.HttpURLConnection a(android.content.Context,java.lang.String,int,int)>->$r0"]}},
    ]
    findings = correlate(observations, RULES).findings
    assert len(findings) == 1
    finding = findings[0]
    for key in ("finding_code", "title", "category", "severity", "recommendation", "dedup_key", "observation_ids"):
        assert key in finding
    # 标准映射现来自规则内容的 standards 块，必须是真实取值而不是空列表。
    # 编号于 2026-09-29 对 OWASP/maswe 仓库原文核实：MASWE-0067「Lack of
    # Anonymization or Pseudonymisation Measures」，其 frontmatter 自报
    # masvs-v2 为 MASVS-PRIVACY-2。原先这里写的是 MASWE-0001——那一条讲的是
    # 「敏感数据未加密落盘」(MASVS-STORAGE)，与通讯录外传没有关系。
    assert finding["maswe_ids"] == ["MASWE-0067"]
    assert finding["masvs_controls"] == ["MASVS-PRIVACY-2"]
    # mastg 为**空列表是预期**，不是漏填：MASTG 稳定版没有任何隐私测试，
    # beta 版的隐私测试编号形如 MASTG-TEST-0206，没有一条能挂到本规则上。
    # 原值 `MASTG-TEST-PRIVACY-1` 在 MASTG 仓库里不存在（编号段的形状也对不上）。
    assert finding["mastg_test_ids"] == []
