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
    {
        "rule_key": "PRIVACY_FLOW_FACT_ENRICHMENT",
        "name": "隐私数据流事实证据增强",
        "description": (
            "同一数据类目的敏感 API 事实（如设备标识 API 调用）为该类目已有的数据流结论补充证据、"
            "提升置信度；**不新增结论**。规则内不出现任何具体类目名，新增类目由同一条规则覆盖（设计 §7.1）。"
        ),
        "content": {
            "schema_version": "2.0",
            "anchor": {"type": "dataflow.privacy"},
            "join": [
                # 只看 AppShark 自己的事实证据：非 AppShark 引擎的观察目前不带
                # data_category（注册表只覆盖 AppShark 规则），join 上会因键为 NULL
                # 而拒绝连接 —— 这是刻意的，见 docs/rule-coverage.md 的已知缺口。
                {"type": "security.sensitive_api", "on": ["data_category"]},
            ],
            "scope": ["app_version_id"],
            "action": "enrich",
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
