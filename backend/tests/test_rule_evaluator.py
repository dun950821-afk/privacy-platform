import pytest
from app.services.rule_evaluator import RuleValidationError, evaluate_rule, validate_rule_content

VALID = {
    "schema_version": "1.0",
    "match": {"logic": "all", "conditions": [
        {"observation_type": "fact.permission", "field": "subject", "operator": "contains",
         "value": "android.permission.READ_CONTACTS"},
        {"observation_type": "dataflow.privacy", "field": "payload.sink.category",
         "operator": "equals", "value": "network"},
    ]},
    "produce": {"finding_code": "PRIVACY_CONTACTS_NETWORK", "title": "通讯录外传",
                "category": "privacy", "severity": "high", "confidence": "medium",
                "recommendation": "确认授权与披露。"},
    "standards": {"masvs": ["MASVS-PRIVACY-1"], "maswe": ["MASWE-0001"],
                  "mastg": ["MASTG-TEST-PRIVACY-1"], "cwe": []},
}


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


def test_all_logic_requires_every_condition():
    observations = [
        {"id": 1, "observation_type": "fact.permission", "subject": "android.permission.READ_CONTACTS", "payload": {}},
    ]
    assert evaluate_rule(VALID, observations) is None


def test_all_logic_matches_when_every_condition_met():
    observations = [
        {"id": 1, "observation_type": "fact.permission", "subject": "android.permission.READ_CONTACTS", "payload": {}},
        {"id": 2, "observation_type": "dataflow.privacy", "subject": "Contacts",
         "payload": {"sink": {"category": "network"}}},
    ]
    matched = evaluate_rule(VALID, observations)
    assert sorted(o["id"] for o in matched) == [1, 2]


def test_any_logic_matches_with_single_condition():
    content = {**VALID, "match": {"logic": "any", "conditions": [VALID["match"]["conditions"][0]]}}
    observations = [{"id": 1, "observation_type": "fact.permission",
                     "subject": "android.permission.READ_CONTACTS", "payload": {}}]
    assert [o["id"] for o in evaluate_rule(content, observations)] == [1]


def test_missing_payload_path_does_not_match():
    observations = [{"id": 1, "observation_type": "dataflow.privacy", "subject": "x", "payload": {}}]
    content = {**VALID, "match": {"logic": "all", "conditions": [VALID["match"]["conditions"][1]]}}
    assert evaluate_rule(content, observations) is None


def test_exists_operator_needs_no_value():
    content = {**VALID, "match": {"logic": "all", "conditions": [
        {"observation_type": "fact.permission", "field": "subject", "operator": "exists"}]}}
    observations = [{"id": 1, "observation_type": "fact.permission", "subject": "android.permission.CAMERA", "payload": {}}]
    assert [o["id"] for o in evaluate_rule(content, observations)] == [1]


def test_any_logic_returns_every_matching_observation():
    content = {**VALID, "match": {"logic": "any", "conditions": [
        {"observation_type": "fact.permission", "field": "subject", "operator": "contains",
         "value": "android.permission.READ_CONTACTS"},
        {"observation_type": "dataflow.privacy", "field": "payload.sink.category",
         "operator": "equals", "value": "network"},
    ]}}
    observations = [
        {"id": 1, "observation_type": "fact.permission",
         "subject": "android.permission.READ_CONTACTS", "payload": {}},
        {"id": 2, "observation_type": "dataflow.privacy", "subject": "Contacts",
         "payload": {"sink": {"category": "network"}}},
        {"id": 3, "observation_type": "fact.permission", "subject": "android.permission.CAMERA", "payload": {}},
        {"id": 4, "observation_type": "dataflow.privacy", "subject": "Contacts",
         "payload": {"sink": {"category": "network"}}},
    ]
    assert [o["id"] for o in evaluate_rule(content, observations)] == [1, 2, 4]


def test_any_logic_returns_none_without_matches():
    content = {**VALID, "match": {"logic": "any", "conditions": [VALID["match"]["conditions"][1]]}}
    observations = [{"id": 1, "observation_type": "fact.permission",
                     "subject": "android.permission.CAMERA", "payload": {}}]
    assert evaluate_rule(content, observations) is None
