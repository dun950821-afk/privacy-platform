"""引擎事件到 Observation 的统一映射。"""
import logging

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
