import re

import pytest
from app.services.rule_evaluator import (
    MAX_CATEGORY_LEN, MAX_FINDING_CODE_LEN, MAX_TITLE_LEN,
    RuleValidationError, evaluate_rule, validate_rule_content,
)

# 条件字段与真实引擎产物一致：fact.sensitive_permission.payload.category / dataflow.privacy.payload.rule
VALID = {
    "schema_version": "1.0",
    "match": {"logic": "all", "conditions": [
        {"observation_type": "fact.sensitive_permission", "field": "payload.category",
         "operator": "equals", "value": "CONTACTS"},
        {"observation_type": "dataflow.privacy", "field": "payload.rule",
         "operator": "contains", "value": "_NetworkTransfer"},
    ]},
    "produce": {"finding_code": "PRIVACY_CONTACTS_NETWORK", "title": "通讯录外传",
                "category": "privacy", "severity": "high", "confidence": "possible",
                "recommendation": "确认授权与披露。"},
    "standards": {"masvs": ["MASVS-PRIVACY-1"], "maswe": ["MASWE-0001"],
                  "mastg": ["MASTG-TEST-PRIVACY-1"], "cwe": []},
}

CONTACTS_PERMISSION = {"id": 1, "observation_type": "fact.sensitive_permission",
                       "subject": "READ_CONTACTS",
                       "payload": {"api": "READ_CONTACTS", "category": "CONTACTS",
                                   "permission": "READ_CONTACTS"}}
NETWORK_FLOW = {"id": 2, "observation_type": "dataflow.privacy", "subject": "['<x: void b()>->$r8']",
                "payload": {"rule": "DeviceId_NetworkTransfer", "sink": ["<x: void b()>->$r8"]}}
LOG_FLOW = {"id": 3, "observation_type": "dataflow.privacy", "subject": "['<x: void a()>->$r3']",
            "payload": {"rule": "DeviceId_Log", "sink": ["<x: void a()>->$r3"]}}


def _with_produce(**overrides):
    produce = {**VALID["produce"], **overrides}
    return {**VALID, "produce": produce}


def test_valid_content_passes():
    validate_rule_content(VALID)


def test_rejects_unknown_operator():
    bad = {**VALID, "match": {"logic": "all", "conditions": [
        {"observation_type": "fact.permission", "field": "subject", "operator": "regex", "value": "x"}]}}
    with pytest.raises(RuleValidationError):
        validate_rule_content(bad)


def test_rejects_malformed_maswe_id():
    bad = {**VALID, "standards": {**VALID["standards"], "maswe": ["MASWE-1"]}}
    with pytest.raises(RuleValidationError):
        validate_rule_content(bad)


def test_rejects_non_string_logic():
    bad = {**VALID, "match": {"logic": ["all"], "conditions": [VALID["match"]["conditions"][0]]}}
    with pytest.raises(RuleValidationError):
        validate_rule_content(bad)


def test_rejects_non_dict_condition():
    bad = {**VALID, "match": {"logic": "all", "conditions": ["a"]}}
    with pytest.raises(RuleValidationError):
        validate_rule_content(bad)


def test_rejects_non_list_conditions():
    bad = {**VALID, "match": {"logic": "all", "conditions": "nope"}}
    with pytest.raises(RuleValidationError):
        validate_rule_content(bad)


def test_rejects_non_dict_match():
    bad = {**VALID, "match": "nope"}
    with pytest.raises(RuleValidationError):
        validate_rule_content(bad)


def test_rejects_non_string_standard_id():
    for value in (1, None):
        bad = {**VALID, "standards": {**VALID["standards"], "maswe": [value]}}
        with pytest.raises(RuleValidationError):
            validate_rule_content(bad)


def test_rejects_non_sequence_standard_ids():
    for value in (1, "MASWE-0001", {"MASWE-0001": 1}):
        bad = {**VALID, "standards": {**VALID["standards"], "maswe": value}}
        with pytest.raises(RuleValidationError):
            validate_rule_content(bad)


def test_accepts_tuple_standard_ids():
    validate_rule_content({**VALID, "standards": {**VALID["standards"], "maswe": ("MASWE-0001",)}})


def test_rejects_non_string_operator_and_field():
    for key, value in (("operator", {}), ("field", [])):
        condition = {**VALID["match"]["conditions"][0], key: value}
        bad = {**VALID, "match": {"logic": "all", "conditions": [condition]}}
        with pytest.raises(RuleValidationError):
            validate_rule_content(bad)


def test_all_logic_requires_every_condition():
    assert evaluate_rule(VALID, [CONTACTS_PERMISSION]) is None
    assert evaluate_rule(VALID, [NETWORK_FLOW]) is None


def test_all_logic_matches_when_every_condition_met():
    matched = evaluate_rule(VALID, [CONTACTS_PERMISSION, NETWORK_FLOW])
    assert sorted(o["id"] for o in matched) == [1, 2]


def test_network_condition_rejects_non_network_flow():
    """同形数据流只有 payload.rule 的取值不同（落盘/日志 ≠ 网络传输）。"""
    assert evaluate_rule(VALID, [CONTACTS_PERMISSION, LOG_FLOW]) is None


def test_any_logic_matches_with_single_condition():
    content = {**VALID, "match": {"logic": "any", "conditions": [VALID["match"]["conditions"][0]]}}
    assert [o["id"] for o in evaluate_rule(content, [CONTACTS_PERMISSION])] == [1]


def test_missing_payload_path_does_not_match():
    observations = [{"id": 1, "observation_type": "dataflow.privacy", "subject": "x", "payload": {}}]
    content = {**VALID, "match": {"logic": "all", "conditions": [VALID["match"]["conditions"][1]]}}
    assert evaluate_rule(content, observations) is None


def test_exists_operator_needs_no_value():
    content = {**VALID, "match": {"logic": "all", "conditions": [
        {"observation_type": "fact.sensitive_permission", "field": "subject", "operator": "exists"}]}}
    observations = [{"id": 1, "observation_type": "fact.sensitive_permission", "subject": "CAMERA",
                     "payload": {"category": "CAMERA"}}]
    assert [o["id"] for o in evaluate_rule(content, observations)] == [1]


def test_any_logic_returns_every_matching_observation():
    content = {**VALID, "match": {"logic": "any", "conditions": [
        {"observation_type": "fact.sensitive_permission", "field": "payload.category",
         "operator": "equals", "value": "CONTACTS"},
        {"observation_type": "dataflow.privacy", "field": "payload.rule",
         "operator": "contains", "value": "_NetworkTransfer"},
    ]}}
    observations = [
        CONTACTS_PERMISSION,
        NETWORK_FLOW,
        {"id": 4, "observation_type": "fact.sensitive_permission", "subject": "CAMERA",
         "payload": {"category": "CAMERA"}},
        {**NETWORK_FLOW, "id": 5},
    ]
    assert [o["id"] for o in evaluate_rule(content, observations)] == [1, 2, 5]


def test_any_logic_returns_none_without_matches():
    content = {**VALID, "match": {"logic": "any", "conditions": [VALID["match"]["conditions"][1]]}}
    assert evaluate_rule(content, [CONTACTS_PERMISSION]) is None


# ============ produce 字段长度/枚举边界 ============
# platform_findings 列宽: finding_code 120 / title 300 / category 80 / severity 30 / confidence 30。
# 校验器必须在写入前收口，否则超长值在 generate_findings 的最终 commit 抛
# StringDataRightTruncation 并回滚整个事务。

def test_finding_code_at_max_length_passes():
    validate_rule_content(_with_produce(finding_code="A" * MAX_FINDING_CODE_LEN))


def test_finding_code_over_max_length_rejected():
    with pytest.raises(RuleValidationError):
        validate_rule_content(_with_produce(finding_code="A" * (MAX_FINDING_CODE_LEN + 1)))


def test_finding_code_too_long_for_column_but_valid_regex_rejected():
    """150 个字符仍满足 ^[A-Z][A-Z0-9_]{2,}$, 但超过列宽 → 必须在校验期拒绝。"""
    code = "A" * 150
    assert re.match(r"^[A-Z][A-Z0-9_]{2,}$", code)
    with pytest.raises(RuleValidationError):
        validate_rule_content(_with_produce(finding_code=code))


def test_title_at_max_length_passes():
    validate_rule_content(_with_produce(title="标" * MAX_TITLE_LEN))


def test_title_over_max_length_rejected():
    with pytest.raises(RuleValidationError):
        validate_rule_content(_with_produce(title="标" * (MAX_TITLE_LEN + 1)))


def test_title_must_be_non_empty_string():
    with pytest.raises(RuleValidationError):
        validate_rule_content(_with_produce(title="   "))
    with pytest.raises(RuleValidationError):
        validate_rule_content(_with_produce(title={"a": 1}))


def test_category_at_max_length_passes():
    validate_rule_content(_with_produce(category="c" * MAX_CATEGORY_LEN))


def test_category_over_max_length_rejected():
    with pytest.raises(RuleValidationError):
        validate_rule_content(_with_produce(category="c" * (MAX_CATEGORY_LEN + 1)))


def test_severity_must_be_from_controlled_vocabulary():
    for value in ("critical", "high", "medium", "low"):
        validate_rule_content(_with_produce(severity=value))
    for value in ("severe", "HIGH", "", None, 5, ["high"]):
        with pytest.raises(RuleValidationError):
            validate_rule_content(_with_produce(severity=value))


def test_confidence_must_be_from_controlled_vocabulary():
    for value in ("confirmed", "probable", "possible"):
        validate_rule_content(_with_produce(confidence=value))
    # "medium" 是严重性词表的值, 不是置信度取值 —— 初版内置规则曾误用它
    for value in ("medium", "high", "", None, 1):
        with pytest.raises(RuleValidationError):
            validate_rule_content(_with_produce(confidence=value))


def test_severity_and_confidence_may_be_omitted():
    produce = {k: v for k, v in VALID["produce"].items() if k not in ("severity", "confidence")}
    validate_rule_content({**VALID, "produce": produce})


def test_recommendation_length_is_bounded():
    validate_rule_content(_with_produce(recommendation=None))
    with pytest.raises(RuleValidationError):
        validate_rule_content(_with_produce(recommendation="x" * 2001))
