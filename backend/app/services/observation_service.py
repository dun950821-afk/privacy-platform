"""引擎事件到 Observation 的统一映射。"""
import logging

from app.models import EngineObservation
from app.services.appshark_semantic_registry import MissingSemanticsError, semantics_for

logger = logging.getLogger(__name__)

# 平台观察层次。不使用 L2/L3 —— 那是 AppShark 自己的 level 语义，
# 保留在 provider_level 字段，二者不得混用（设计文档 §4.1）。
KIND_MAP = {
    "fact.application": "fact",
    "fact.permission": "fact",
    "fact.sensitive_permission": "fact",
    "fact.component": "fact",
    "security.endpoint": "fact",
    "security.tracker": "security_finding",
    "security.sensitive_api": "fact",
    "dataflow.privacy": "dataflow",
    "security.other": "security_finding",
}

TYPE_MAP = {
    "static_tracker": "security.tracker",
    "static_url": "security.endpoint",
    "static_basic_info": "fact.application",
    "static_permission": "fact.permission",
    "static_sensitive_permission": "fact.sensitive_permission",
    "static_component": "fact.component",
    "static_data_flow": "dataflow.privacy",
    "static_sensitive_api": "security.sensitive_api",
}

# 静态数据流只能证明"可能存在"路径，不能当成运行时确认
EVIDENCE_LEVELS = {
    "dataflow.privacy": "potential",
    "static_data_flow": "potential",
}


def event_to_observation(event: dict, *, task_id: int, execution_id: int, engine_type: str, engine_version: str, rule_version: str | None = None) -> dict:
    event_type = event.get("event_type", "unknown")
    data_type = event.get("data_type")
    if event_type == "security_observation":
        observation_type = f"security.{data_type or 'other'}"
    else:
        observation_type = TYPE_MAP.get(event_type, "security.other")
    payload = dict(event.get("event_data") or {})
    if event.get("api"):
        payload.setdefault("api", event["api"])
    if event.get("caller"):
        payload.setdefault("caller", event["caller"])
    subject = event.get("api") or payload.get("name") or payload.get("component")
    result = {
        "task_id": task_id,
        "execution_id": execution_id,
        "engine_type": engine_type,
        "engine_version": engine_version,
        "observation_type": observation_type,
        "rule_code": payload.get("rule"),
        "severity": payload.get("severity"),
        "confidence": payload.get("confidence", "medium"),
        "evidence_level": EVIDENCE_LEVELS.get(observation_type, EVIDENCE_LEVELS.get(event_type, "observed")),
        "subject": subject,
        "location": event.get("caller"),
        "payload": payload,
        "evidence_refs": [],
        "schema_version": "1.0",
    }
    semantic = _semantic_fields(payload, observation_type)
    resolved_type = semantic.pop("_resolved_observation_type", None)
    if resolved_type:
        result["observation_type"] = resolved_type
        result["evidence_level"] = EVIDENCE_LEVELS.get(
            resolved_type, EVIDENCE_LEVELS.get(event_type, "observed"))
    result.update(semantic)
    return result


def observation_view(row) -> dict:
    """把 Observation 行投影成关联器能用的视图。

    必须带上平台语义字段：join 就是按 data_category 这类键连接的，
    漏掉它们的表现是**静默不关联**（规则看着生效，实际一条都不匹配）。
    关联与预览两处都走这个函数，避免两处各漏一个字段。
    """
    return {
        "id": row.id,
        "observation_type": row.observation_type,
        "subject": row.subject,
        "location": row.location,
        "payload": row.payload or {},
        "engine_type": row.engine_type,
        "data_category": row.data_category,
        "sink_type": row.sink_type,
        "result_semantics": row.result_semantics,
        "observation_kind": row.observation_kind,
        "provider_rule_id": row.provider_rule_id,
        "provider_level": row.provider_level,
        "entity_keys": row.entity_keys or {},
    }


# 归一化结果里唯一一个不是模型列的键，落库时丢弃是预期行为
NON_COLUMN_KEYS = frozenset({"engine_version"})


def observation_row(data: dict) -> EngineObservation:
    """把归一化结果投影成 EngineObservation。

    **按模型列投影，不手写字段白名单。** 手写白名单的失败方式是静默的：
    新增字段没有报错、没有测试失败，只是永远不落库。Task 3 首次真实任务
    验证就栽在这里——7 个语义字段全被白名单丢掉，139 条观察的 data_category
    为 NULL，直接结论产出 0，而全部单测仍然是绿的（它们只验返回值，不验写库）。

    以模型列为准之后，「模型加了列但忘了写进去」这类错误不可能再发生。
    """
    columns = {c.key for c in EngineObservation.__table__.columns}
    return EngineObservation(**{k: v for k, v in data.items() if k in columns})


def _semantic_fields(payload: dict, observation_type: str) -> dict:
    """从 Provider 规则名解析平台语义字段。

    规则未在注册表中登记时返回空语义并保留原文——不抛错、也不猜。
    缺失由 `test_registry_covers_every_rule_file` 在测试期拦下，
    运行期静默降级只影响该条观察，不应让整个任务失败。
    """
    rule = payload.get("rule")
    # 字段一律存在；无值时为 None，不留缺失键，避免下游出现 [] 与 .get() 的不一致。
    base = {
        "provider_rule_id": rule,
        "provider_level": payload.get("level"),
        "observation_kind": KIND_MAP.get(observation_type, "fact"),
        "data_category": None,
        "sink_type": None,
        "result_semantics": None,
        "entity_keys": {},
    }
    if not rule:
        return base
    try:
        sem = semantics_for(rule)
    except MissingSemanticsError:
        logger.warning("规则 %s 未登记语义，该观察不参与关联", rule)
        return base
    # 已登记规则由注册表裁决 observation_type —— 否则注册表声明了却不生效，
    # 等于没写（例：unZipSlip 是安全规则，不应被 TYPE_MAP 归入 dataflow.privacy）。
    resolved_type = sem.get("observation_type") or observation_type
    return {
        "provider_rule_id": rule,
        "provider_level": payload.get("level"),
        "observation_kind": KIND_MAP.get(resolved_type, "fact"),
        "data_category": sem["data_category"],
        "sink_type": sem["sink_type"],
        "result_semantics": sem["result_type"],
        "entity_keys": ({"data_category": sem["data_category"]} if sem["data_category"] else {}),
        "_resolved_observation_type": resolved_type,
    }
