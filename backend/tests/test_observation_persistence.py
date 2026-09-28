"""观察语义字段必须真的落库。

单测只验 `event_to_observation` 的返回值，验不到「写库时字段还在不在」。
Task 3 第一次真实任务验证（app_version 12）暴露的正是这个缺口：
归一化已经算出了 data_category，但 worker 用一份手写白名单投影，
把 7 个语义字段全部丢在写库之前 —— 139 条观察的 data_category 全为 NULL，
Direct Finding 产出 0 条，而所有单测都是绿的。

因此这里测的不是「归一化算没算对」，而是「算出来的字段有没有活到库里」。
数据取自 task 553 回归基线（真实 AppShark 产物）。
"""
import json
from pathlib import Path

from app.models import EngineObservation
from app.services.observation_service import event_to_observation, observation_row

FIXTURE = Path(__file__).parent / "fixtures" / "appshark" / "task_553" / "observations.json"

EVENT_TYPE_FOR = {
    "dataflow.privacy": "static_data_flow",
    "security.sensitive_api": "static_sensitive_api",
    "fact.permission": "static_permission",
}

SEMANTIC_FIELDS = ("data_category", "sink_type", "result_semantics",
                   "observation_kind", "provider_rule_id", "provider_level", "entity_keys")

# 归一化结果里唯一一个不是 EngineObservation 列的键：
# 它只参与执行元数据，落库时丢弃是预期行为，其余一律不得丢。
NON_COLUMN_KEYS = {"engine_version"}


def _normalize(observation):
    return event_to_observation(
        {"event_type": EVENT_TYPE_FOR.get(observation["observation_type"], "unknown"),
         "api": observation["subject"], "event_data": observation["payload"]},
        task_id=553, execution_id=1, engine_type="appshark", engine_version="0.1.2")


def _baseline():
    return json.loads(FIXTURE.read_text())["observations"]


def test_projection_drops_nothing_but_non_columns():
    """凡是模型有列的键都必须进入写库投影，只有 engine_version 允许被丢。

    手写白名单的害处不是漏了某个字段，而是**新字段会静默消失**：没有报错、
    没有测试失败，只有库里一片 NULL。这条断言把「静默」变成「失败」。
    """
    columns = {c.key for c in EngineObservation.__table__.columns}
    for o in _baseline():
        normalized = _normalize(o)
        dropped = set(normalized) - columns
        assert dropped <= NON_COLUMN_KEYS, \
            "%s 归一化产出的字段被写库投影丢弃: %s" % (o["id"], sorted(dropped - NON_COLUMN_KEYS))

        row = observation_row(normalized)
        for field in SEMANTIC_FIELDS:
            assert getattr(row, field) == normalized[field], \
                "%s 的 %s 在写库投影后变了: %r -> %r" % (
                    o["id"], field, normalized[field], getattr(row, field))


def test_semantic_fields_persist_to_db(db, execution):
    """真实的直接结论规则，七个语义字段必须原样回读得到。"""
    flow = next(o for o in _baseline()
                if (o.get("payload") or {}).get("rule") == "DeviceId_FileWrite")
    normalized = _normalize(flow)
    normalized.update(task_id=execution.task_id, execution_id=execution.id)

    row = observation_row(normalized)
    db.add(row)
    db.commit()
    db.refresh(row)

    assert row.data_category == "device_information"
    assert row.sink_type == "file"
    assert row.result_semantics == "direct_finding"
    assert row.observation_kind == "dataflow"
    assert row.provider_rule_id == "DeviceId_FileWrite"
    assert row.provider_level == "L3"
    assert row.entity_keys == {"data_category": "device_information"}


def test_security_rule_without_category_still_persists_semantics(db, execution):
    """无数据类目的安全规则同样不得丢语义：它靠 result_semantics 成结论。"""
    flow = next(o for o in _baseline()
                if (o.get("payload") or {}).get("rule") == "unZipSlip")
    normalized = _normalize(flow)
    normalized.update(task_id=execution.task_id, execution_id=execution.id)

    row = observation_row(normalized)
    db.add(row)
    db.commit()
    db.refresh(row)

    assert row.data_category is None          # 合法取值，不是缺失
    assert row.sink_type == "file"
    assert row.result_semantics == "direct_finding"
    assert row.provider_rule_id == "unZipSlip"


def test_worker_uses_the_shared_projection():
    """Worker 必须用同一个投影函数，不得再手写一份字段列表。

    白名单一旦回到 worker 内部，上面两条断言就管不到真实写库路径了。
    """
    from app.engine import worker
    assert worker.observation_row is observation_row
