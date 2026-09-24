"""引擎事件到 Observation 的统一映射。"""

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
    return {
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
