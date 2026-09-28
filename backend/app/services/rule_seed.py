"""内置关联规则种子。"""
from sqlalchemy.orm import Session

from app.models import Rule, RuleVersion
from app.services.rule_evaluator import validate_rule_content

# 条件字段取值必须来自引擎真实产物：
# - 通讯录权限侧：Androguard runner 的 SENSITIVE_PERMISSIONS["CONTACTS"]
#   (app/engine/runners/androguard_runner.py) 命中后由适配器发出
#   static_sensitive_permission 事件, 归一化后 observation_type 为
#   fact.sensitive_permission, subject 为短名(READ_CONTACTS),
#   payload = {"api", "category", "permission"}, 其中 category 为 "CONTACTS"。
# - 网络传输侧：AppShark 的数据流事件(event_type=static_data_flow)归一化后
#   observation_type 为 dataflow.privacy, payload.rule 为规则名(如
#   Location_NetworkTransfer / DeviceId_NetworkTransfer), payload.sink 为
#   污点汇聚点的**方法签名列表**(不是 dict, 也不是网络 API), 因此只有
#   payload.rule 能真实区分「网络传输」与「落盘/日志」等同形数据流。
BUILTIN_CORRELATION_RULES = [
    {
        "rule_key": "PRIVACY_CONTACTS_NETWORK",
        "name": "通讯录信息网络传输",
        "description": "应用申请了通讯录敏感权限，且 AppShark 发现至少一条到达网络的数据流路径。",
        "content": {
            "schema_version": "1.0",
            "match": {"logic": "all", "conditions": [
                {"observation_type": "fact.sensitive_permission", "field": "payload.category",
                 "operator": "equals", "value": "CONTACTS"},
                {"observation_type": "dataflow.privacy", "field": "payload.rule",
                 "operator": "contains", "value": "_NetworkTransfer"},
            ]},
            "produce": {
                "finding_code": "PRIVACY_CONTACTS_NETWORK",
                "title": "通讯录信息存在潜在网络传输路径",
                # confidence 取 CONFIDENCE 受控词表口径(前端「疑似」); 静态数据流
                # 只证明"可能存在"路径, 与 evidence_level=potential 保持一致
                "category": "privacy", "severity": "high", "confidence": "possible",
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
