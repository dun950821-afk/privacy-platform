"""内置关联规则种子。"""
from sqlalchemy.orm import Session

from app.models import Rule, RuleVersion
from app.services.rule_evaluator import validate_rule_content

BUILTIN_CORRELATION_RULES = [
    {
        "rule_key": "PRIVACY_CONTACTS_NETWORK",
        "name": "通讯录信息网络传输",
        "description": "同时存在通讯录权限与通讯录数据流才成立。",
        "content": {
            "schema_version": "1.0",
            "match": {"logic": "all", "conditions": [
                {"observation_type": "fact.permission", "field": "subject",
                 "operator": "contains", "value": "android.permission.READ_CONTACTS"},
                {"observation_type": "dataflow.privacy", "field": "payload.sink.category",
                 "operator": "equals", "value": "network"},
            ]},
            "produce": {
                "finding_code": "PRIVACY_CONTACTS_NETWORK",
                "title": "通讯录信息存在潜在网络传输路径",
                "category": "privacy", "severity": "high", "confidence": "medium",
                "recommendation": "确认用户授权与隐私政策披露，并对传输数据做最小化与保护。",
            },
            "standards": {"masvs": ["MASVS-PRIVACY-1"], "maswe": ["MASWE-0001"],
                          "mastg": ["MASTG-TEST-PRIVACY-1"], "cwe": []},
        },
    },
]


def seed_correlation_rules(db: Session) -> int:
    created = 0
    for item in BUILTIN_CORRELATION_RULES:
        if db.query(Rule).filter(Rule.rule_key == item["rule_key"]).first():
            continue
        validate_rule_content(item["content"])
        rule = Rule(rule_key=item["rule_key"], name=item["name"],
                    category="correlation", description=item["description"], status="active")
        db.add(rule)
        db.flush()
        version = RuleVersion(rule_id=rule.id, version="1.0", rule_content=item["content"],
                              changelog="内置规则初始化", status="published")
        db.add(version)
        db.flush()
        rule.current_version_id = version.id
        created += 1
    db.commit()
    return created
