from app.services.correlation import correlate
from app.services.rule_seed import BUILTIN_CORRELATION_RULES

RULES = [{"rule": type("R", (), {"id": 1})(), "version": type("V", (), {"version": "1.0"})(),
          "content": BUILTIN_CORRELATION_RULES[0]["content"]}]


def test_finding_payload_is_complete_for_persistence():
    observations = [
        {"id": 1, "observation_type": "fact.permission", "subject": "android.permission.READ_CONTACTS", "payload": {}},
        {"id": 2, "observation_type": "dataflow.privacy", "subject": "Contacts", "payload": {"sink": {"category": "network"}}},
    ]
    findings = correlate(observations, RULES)
    assert len(findings) == 1
    finding = findings[0]
    for key in ("finding_code", "title", "category", "severity", "recommendation", "dedup_key", "observation_ids"):
        assert key in finding
    # 标准映射现来自规则内容的 standards 块，必须是真实取值而不是空列表
    assert finding["maswe_ids"] == ["MASWE-0001"]
    assert finding["masvs_controls"] == ["MASVS-PRIVACY-1"]
    assert finding["mastg_test_ids"] == ["MASTG-TEST-PRIVACY-1"]
