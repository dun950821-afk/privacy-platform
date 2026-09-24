"""跨引擎 Observation 关联和去重规则。"""
from hashlib import sha256
import json

from sqlalchemy.orm import Session

from app.models import Rule, RuleVersion
from app.services.rule_evaluator import evaluate_rule


def observation_dedup_key(observation: dict) -> str:
    payload = {"type": observation.get("observation_type"), "subject": observation.get("subject"),
               "payload": observation.get("payload")}
    return sha256(json.dumps(payload, sort_keys=True, default=str).encode()).hexdigest()


def load_active_rules(db: Session) -> list[dict]:
    """读取已发布的关联规则。"""
    rows = db.query(Rule, RuleVersion).join(
        RuleVersion, Rule.current_version_id == RuleVersion.id
    ).filter(Rule.category == "correlation", Rule.status == "active").all()
    return [{"rule": rule, "version": version, "content": version.rule_content or {}}
            for rule, version in rows]


def correlate(observations: list[dict], rules: list[dict]) -> list[dict]:
    findings = []
    for entry in rules:
        content = entry["content"]
        matched = evaluate_rule(content, observations)
        if not matched:
            continue
        produce = content.get("produce") or {}
        standards = content.get("standards") or {}
        key = sha256((produce.get("finding_code", "") + "|" + "|".join(
            str(o.get("id", observation_dedup_key(o))) for o in matched)).encode()).hexdigest()
        findings.append({
            "finding_code": produce.get("finding_code"),
            "title": produce.get("title"),
            "category": produce.get("category"),
            "severity": produce.get("severity", "medium"),
            "confidence": produce.get("confidence", "medium"),
            "recommendation": produce.get("recommendation"),
            "masvs_controls": standards.get("masvs", []),
            "maswe_ids": standards.get("maswe", []),
            "mastg_test_ids": standards.get("mastg", []),
            "cwe_ids": standards.get("cwe", []),
            "correlation_rule_id": str(entry["rule"].id),
            "correlation_rule_version": entry["version"].version,
            "rule_snapshot": content,
            "dedup_key": key,
            "observation_ids": [o.get("id") for o in matched if o.get("id")],
        })
    return findings
