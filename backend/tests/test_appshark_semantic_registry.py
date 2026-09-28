"""语义注册表的完整性与正确性。"""
import json
import glob
import os
import pytest

from app.services.appshark_semantic_registry import (
    REGISTRY, RESULT_DIRECT, MissingSemanticsError, enrich_observation, semantics_for,
)

RULE_DIR = "appshark/rules"


def _all_provider_rule_ids():
    ids = set()
    for p in glob.glob(os.path.join(RULE_DIR, "*.json")):
        for rid in json.load(open(p)):
            ids.add(rid)
    return ids


def test_registry_covers_every_rule_file():
    """规则目录里每一条规则都必须有语义标注。

    缺一条就静默降级成「无语义」，关联层会看不见它——宁可在测试里失败。
    """
    missing = _all_provider_rule_ids() - set(REGISTRY)
    assert not missing, "以下规则未登记语义: %s" % sorted(missing)


def test_registry_has_no_stale_entries():
    """注册表不得包含规则目录中已不存在的规则，避免清理后残留死映射。"""
    stale = set(REGISTRY) - _all_provider_rule_ids()
    assert not stale, "以下注册项已无对应规则: %s" % sorted(stale)


def test_unknown_rule_raises_instead_of_degrading():
    with pytest.raises(MissingSemanticsError):
        semantics_for("NoSuchRule_v99")


def test_dataflow_rules_are_direct_findings_with_category_and_sink():
    """数据流规则必须同时有类目与流向，否则无法参与共享键关联。"""
    for rid, sem in REGISTRY.items():
        if sem["observation_type"] == "dataflow.privacy" and rid != "IMEI_SendBroadcast":
            assert sem["result_type"] == RESULT_DIRECT, "%s 应直接成结论" % rid
            assert sem["data_category"], "%s 缺 data_category" % rid
            assert sem["sink_type"], "%s 缺 sink_type" % rid


def test_api_call_rules_are_supporting_evidence():
    """APICall 只证明「调用了 API」，是支撑证据，不得单独成结论。"""
    for rid, sem in REGISTRY.items():
        if rid.endswith("_APICall"):
            assert sem["result_type"] != RESULT_DIRECT, "%s 是事实不是结论" % rid
            assert sem["sink_type"] is None, "%s 无流向" % rid


def test_security_rules_may_have_null_category():
    """安全类规则没有数据类目，None 是合法取值而非缺失。

    这是「是否成结论不能由类目决定」的证据：unZipSlip 无类目但属 direct_finding。
    """
    unzip = semantics_for("unZipSlip")
    assert unzip["data_category"] is None
    assert unzip["result_type"] == RESULT_DIRECT


def test_enrich_sets_shared_join_key():
    """同类目的不同引擎观察必须产出相同的 entity_keys.data_category，才能连接。"""
    flow = enrich_observation({"app_version_id": 12}, "DeviceId_NetworkTransfer")
    api = enrich_observation({"app_version_id": 12}, "DeviceId_APICall")
    assert flow["entity_keys"]["data_category"] == api["entity_keys"]["data_category"]
    assert flow["entity_keys"]["app_version"] == 12


def test_enrich_does_not_cross_categories():
    """不同类目必须产出不同的 join key，否则会跨类目误关联。"""
    device = enrich_observation({"app_version_id": 12}, "DeviceId_NetworkTransfer")
    location = enrich_observation({"app_version_id": 12}, "Location_NetworkTransfer")
    assert device["entity_keys"]["data_category"] != location["entity_keys"]["data_category"]


def test_enrich_omits_null_category_from_keys():
    """无类目的规则不得产出 data_category 键，否则会与别的 None 类目互相连接。"""
    out = enrich_observation({"app_version_id": 12}, "unZipSlip")
    assert "data_category" not in out["entity_keys"]


def test_enrich_is_pure():
    src = {"app_version_id": 12}
    enrich_observation(src, "DeviceId_APICall")
    assert src == {"app_version_id": 12}, "enrich 不得修改传入对象"
