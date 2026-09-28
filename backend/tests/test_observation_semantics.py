"""Normalizer 从真实引擎产物解析平台语义字段。

数据取自 task 553 回归基线（真实 AppShark 产物），不构造合成数据——
合成数据正是此前「fixture、单测、端到端互相验证同一个虚构」的成因。
"""
import json
from pathlib import Path

import pytest

from app.services.observation_service import event_to_observation

FIXTURE = Path(__file__).parent / "fixtures" / "appshark" / "task_553" / "observations.json"

EVENT_TYPE_FOR = {
    "dataflow.privacy": "static_data_flow",
    "security.sensitive_api": "static_sensitive_api",
    "fact.permission": "static_permission",
}


@pytest.fixture(scope="module")
def baseline():
    return json.loads(FIXTURE.read_text())


def _normalize(observation):
    return event_to_observation(
        {"event_type": EVENT_TYPE_FOR.get(observation["observation_type"], "unknown"),
         "api": observation["subject"], "event_data": observation["payload"]},
        task_id=553, execution_id=1, engine_type="appshark", engine_version="0.1.2")


def test_was_null_now_populated(baseline):
    """改造前 category 列全为 NULL；隐私数据流规则归一化后必须有类目。

    fixture 记录的是改造前状态（category 为 NULL），且其中的 observation_type
    是旧分类——安全规则当时被 TYPE_MAP 误归入 dataflow.privacy。因此这里按
    **归一化后**的类型筛选，只统计真正属于隐私数据流的规则。
    """
    assert all(o["category"] is None for o in baseline["observations"]), \
        "基线记录的是改造前状态：category 应全为 NULL"

    populated = [r for r in (_normalize(o) for o in baseline["observations"])
                 if r["observation_type"] == "dataflow.privacy"]
    assert populated, "应存在隐私数据流观察"
    for r in populated:
        assert r["data_category"], "%s 归一化后仍无 data_category" % r["provider_rule_id"]

    # 安全规则不应被计入，它们本来就没有数据类目
    security = [r for r in (_normalize(o) for o in baseline["observations"])
                if r["observation_type"] == "security.other"]
    assert all(r["data_category"] is None for r in security), \
        "安全类规则不应被强加数据类目"

    # 未归一化前，这批观察的 category 一个都没有值
    assert populated, "至少应有一条数据流观察由 NULL 变为有值"


def test_all_dataflow_rules_get_category_and_sink(baseline):
    """归一化后属于 dataflow 的规则，都必须解析出类目与流向。

    注意按「归一化后的类型」筛选：fixture 存的是改造前的旧分类，unZipSlip
    这类安全规则当时被 TYPE_MAP 误归入 dataflow.privacy。
    """
    seen = set()
    for o in baseline["observations"]:
        r = _normalize(o)
        if r["observation_type"] != "dataflow.privacy":
            continue
        seen.add(r["provider_rule_id"])
        assert r["data_category"], "%s 缺 data_category" % r["provider_rule_id"]
        assert r["sink_type"], "%s 缺 sink_type" % r["provider_rule_id"]
        assert r["result_semantics"] == "direct_finding"
    assert seen, "应至少解析出一条数据流规则"


def test_provider_level_is_preserved_not_reused_as_kind(baseline):
    """AppShark 的 L2/L3 必须留在 provider_level，不得当成平台层次。"""
    flows = [o for o in baseline["observations"] if o["observation_type"] == "dataflow.privacy"]
    r = _normalize(flows[0])
    assert r["provider_level"] == "L3"
    assert r["observation_kind"] == "dataflow"     # 平台层次，不是 "L3"


def test_api_call_is_supporting_evidence_not_a_finding(baseline):
    """APICall 只证明调用了 API，是事实层证据，不得直接成结论。"""
    apis = [o for o in baseline["observations"] if o["observation_type"] == "security.sensitive_api"]
    assert apis
    for o in apis:
        r = _normalize(o)
        assert r["result_semantics"] == "supporting_evidence"
        assert r["observation_kind"] == "fact"


def test_categories_are_distinct_across_rules(baseline):
    """不同类目必须产出不同 data_category，否则关联会跨类目误连。"""
    cats = set()
    for o in baseline["observations"]:
        if o["observation_type"] == "dataflow.privacy":
            cats.add(_normalize(o)["data_category"])
    assert len(cats) >= 2, "基线应覆盖多个数据类目，实际: %s" % cats


def test_unknown_rule_degrades_without_raising(baseline):
    """未登记规则不得让整个任务失败，只降级为无语义。"""
    r = event_to_observation(
        {"event_type": "static_data_flow", "event_data": {"rule": "SomeUnknownRule_v9"}},
        task_id=553, execution_id=1, engine_type="appshark", engine_version="0.1.2")
    assert r["data_category"] is None
    assert r["provider_rule_id"] == "SomeUnknownRule_v9"
