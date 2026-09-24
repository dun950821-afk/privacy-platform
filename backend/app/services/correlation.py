"""跨引擎 Observation 关联和去重规则。"""
from hashlib import sha256
import json

RULES = [
    {
        "id": "PRIVACY_CONTACTS_NETWORK",
        "version": "1.0",
        "required": {"fact.permission": "android.permission.READ_CONTACTS", "dataflow.privacy": "network"},
        "finding_code": "PRIVACY_CONTACTS_NETWORK",
        "category": "privacy",
        "severity": "high",
        "title": "通讯录信息存在潜在网络传输路径",
        "recommendation": "确认用户授权和隐私政策披露，并对传输数据进行最小化和保护。",
    },
]


def observation_dedup_key(observation: dict) -> str:
    payload = {"type": observation.get("observation_type"), "subject": observation.get("subject"), "payload": observation.get("payload")}
    return sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()


def correlate(observations: list[dict]) -> list[dict]:
    findings = []
    for rule in RULES:
        matched = []
        for required_type, value in rule["required"].items():
            candidates = [o for o in observations if o.get("observation_type") == required_type]
            if value == "network":
                candidates = [o for o in candidates if "network" in str(o.get("payload", {})).lower() or "network" in str(o.get("subject", "")).lower()]
            else:
                candidates = [o for o in candidates if value in str(o.get("subject", "")) or value in str(o.get("payload", {}))]
            if not candidates:
                break
            matched.extend(candidates)
        else:
            key = sha256((rule["finding_code"] + "|" + "|".join(str(o.get("id", observation_dedup_key(o))) for o in matched)).encode()).hexdigest()
            findings.append({"finding_code": rule["finding_code"], "title": rule["title"], "category": rule["category"], "severity": rule["severity"], "recommendation": rule["recommendation"], "dedup_key": key, "observation_ids": [o.get("id") for o in matched if o.get("id")]})
    return findings
