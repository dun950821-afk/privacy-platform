"""Androguard 敏感权限必须带上 data_category，否则跨引擎 join 恒不成立。

改造前：语义注册表只按 `payload.rule` 查表，而只有 AppShark 的事件有这个字段。
Androguard 的观察 data_category 恒为 NULL → 同类目 join 连不上 → 设计 §8 置信度
最高一档「＋另一引擎独立印证 → high」不可达，设计 §7.1 的示例增强规则永不命中。

取值取自真实产物（app_version 11 / 门户测试 3.4.24，19 条敏感权限观察）。
"""
import pytest

from app.engine.runners.androguard_runner import SENSITIVE_PERMISSIONS
from app.services.appshark_semantic_registry import (
    ANDROGUARD_PERMISSION_CATEGORIES, androguard_permission_semantics)
from app.services.observation_service import event_to_observation


def _permission_event(category, permission="ACCESS_FINE_LOCATION"):
    """androguard 适配器发出的 static_sensitive_permission 事件形状。"""
    return {
        "event_type": "static_sensitive_permission",
        "data_type": category,
        "api": permission,
        "event_data": {"api": permission, "category": category,
                       "permission": permission, "source": "manifest"},
    }


def _normalize(event, engine_type="androguard"):
    return event_to_observation(event, task_id=11, execution_id=1,
                                engine_type=engine_type, engine_version="4.1.4")


def test_registry_covers_every_runner_category():
    """runner 的每个敏感权限分组都必须有平台类目，否则该分组的观察静默失去类目。

    runner 新增一个分组而注册表没跟上时，症状不是报错，是那条观察的 data_category
    为 NULL —— join 不命中、也不提示。所以这条断言必须存在。
    """
    assert set(ANDROGUARD_PERMISSION_CATEGORIES) == set(SENSITIVE_PERMISSIONS)


@pytest.mark.parametrize("category,expected", [
    ("LOCATION", "location"),
    ("PHONE_STATE", "phone"),
    ("CONTACTS", "contacts"),
    ("CAMERA", "camera"),
    ("MICROPHONE", "microphone"),
    ("STORAGE", "files"),
    ("SMS", "sms"),
])
def test_permission_category_maps_to_data_category(category, expected):
    result = _normalize(_permission_event(category))
    assert result["data_category"] == expected
    assert result["result_semantics"] == "supporting_evidence"   # 事实，不是结论
    assert result["observation_kind"] == "fact"
    assert result["entity_keys"] == {"data_category": expected}
    assert result["observation_type"] == "fact.sensitive_permission"


def test_categories_do_not_bleed_across_permissions():
    """类目之间不得互相串：这是跨类目误配的正面防线。"""
    resolved = {c: _normalize(_permission_event(c))["data_category"] for c in SENSITIVE_PERMISSIONS}
    assert len(set(resolved.values())) == len(resolved), f"类目有重复: {resolved}"
    assert resolved["CONTACTS"] != resolved["LOCATION"] != resolved["PHONE_STATE"]


def test_appshark_observations_are_unaffected():
    """加了 Androguard 分支后，AppShark 的解析路径不得改变。"""
    result = _normalize({
        "event_type": "static_data_flow", "data_type": "ComplianceInfo",
        "api": "...", "event_data": {"rule": "Location_NetworkTransfer", "level": "L3",
                                     "section": "ComplianceInfo"},
    }, engine_type="appshark")
    assert result["data_category"] == "location"
    assert result["sink_type"] == "network"
    assert result["result_semantics"] == "direct_finding"
    assert result["provider_rule_id"] == "Location_NetworkTransfer"


def test_unregistered_category_degrades_without_inventing_a_category():
    """未登记分组不得猜一个类目出来：错类目比没有类目更糟（会误连）。"""
    assert androguard_permission_semantics("SOME_NEW_GROUP") is None
    result = _normalize(_permission_event("SOME_NEW_GROUP"))
    assert result["data_category"] is None
    assert result["result_semantics"] is None


def test_appshark_engine_with_permission_event_gets_no_category():
    """同一个 observation_type 来自不同引擎时，不能因为类型相同就借用别人的映射。"""
    result = _normalize(_permission_event("CONTACTS"), engine_type="appshark")
    assert result["data_category"] is None
