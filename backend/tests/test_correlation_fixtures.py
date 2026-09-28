import json
from pathlib import Path
import pytest

from app.services.rule_evaluator import evaluate_join_rule, evaluate_rule
from app.services.rule_seed import BUILTIN_CORRELATION_RULES

FIXTURES = Path(__file__).parent / "fixtures" / "correlation"


def _evaluate(content, observations):
    """按 schema_version 分派：1.0 是字面匹配，2.0 是共享键 join。"""
    if content.get("schema_version") == "2.0":
        return evaluate_join_rule(content, observations)
    return evaluate_rule(content, observations)


@pytest.mark.parametrize("rule", BUILTIN_CORRELATION_RULES, ids=lambda r: r["rule_key"])
def test_positive_fixture_matches(rule):
    observations = json.loads((FIXTURES / rule["rule_key"] / "positive.json").read_text())
    assert _evaluate(rule["content"], observations) is not None


@pytest.mark.parametrize("rule", BUILTIN_CORRELATION_RULES, ids=lambda r: r["rule_key"])
def test_negative_fixture_does_not_match(rule):
    observations = json.loads((FIXTURES / rule["rule_key"] / "negative.json").read_text())
    assert _evaluate(rule["content"], observations) is None


def test_enrichment_fixtures_are_a_genuine_near_miss():
    """增强规则的正反例必须只差在数据类目，否则负例证明不了 join key 在起作用。

    两个正例观察取自真实产物（appshark 的 DeviceId_NetworkTransfer 与
    DeviceId_APICall，同一 APK）；负例把事实证据换成「位置信息」，其余字段不动。
    """
    rule_key = "PRIVACY_FLOW_FACT_ENRICHMENT"
    positive = json.loads((FIXTURES / rule_key / "positive.json").read_text())
    negative = json.loads((FIXTURES / rule_key / "negative.json").read_text())

    assert positive[0]["data_category"] == negative[0]["data_category"] == "device_information"
    assert positive[1]["observation_type"] == negative[1]["observation_type"] == "security.sensitive_api"
    assert positive[1]["data_category"] == "device_information"
    assert negative[1]["data_category"] == "location"


def test_builtin_fixtures_are_a_genuine_near_miss():
    """正反例必须只差在决定性命中值(payload.rule)，否则负例证明不了条件本身在起作用。

    两个观察对象都取自真实引擎产物：权限侧来自 androguard 的
    fact.sensitive_permission，数据流侧来自 appshark 的 DeviceId_NetworkTransfer /
    DeviceId_Log（同一 APK、同一污点源与入口方法，只有流向不同）。
    """
    rule_key = BUILTIN_CORRELATION_RULES[0]["rule_key"]
    positive = json.loads((FIXTURES / rule_key / "positive.json").read_text())
    negative = json.loads((FIXTURES / rule_key / "negative.json").read_text())

    assert positive[0] == negative[0], "权限侧观察对象必须完全相同"

    pos_flow, neg_flow = positive[1], negative[1]
    assert pos_flow["observation_type"] == neg_flow["observation_type"] == "dataflow.privacy"
    assert "_NetworkTransfer" in pos_flow["payload"]["rule"]
    assert "_NetworkTransfer" not in neg_flow["payload"]["rule"]

    # 除流向相关的字段外，两个数据流观察对象必须一致（同源、同入口、同层级）
    for key in ("section", "level", "source", "entry_method", "caller"):
        assert pos_flow["payload"].get(key) == neg_flow["payload"].get(key), f"payload.{key} 不应不同"
    assert pos_flow["location"] == neg_flow["location"]
