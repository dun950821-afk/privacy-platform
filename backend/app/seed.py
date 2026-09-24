"""初始数据: 默认用户、规则包、字典"""
from app.core.database import SessionLocal
from app.core.security import hash_password
from app.models import (
    User, Rule, RuleVersion, SysDict
)
from app.services.rule_seed import seed_correlation_rules
import json


SEED_RULES = [
    {
        "rule_key": "PRIV-CONSENT-001",
        "name": "用户同意前读取并发送设备标识",
        "category": "consent",
        "description": "在用户同意隐私政策前，App读取并发送设备标识信息",
        "version": "1.0",
        "rule_content": {
            "scope": "android",
            "when": {
                "consent_status": ["NOT_PRESENTED", "NOT_AGREED", "REJECTED"],
                "event_type": "sensitive_api_call",
                "data_type": ["ANDROID_ID", "OAID", "IMEI", "MAC", "ANDROID_ID"],
                "exists_network": True,
                "time_window_seconds": 5
            },
            "exclude": {"approved_exception": True},
            "evidence_required": ["api_call_stack", "network_request", "consent_state_snapshot"],
            "severity": "HIGH",
            "remediation_template": "延迟SDK初始化至用户同意后；同意前禁止调用设备标识API"
        }
    },
    {
        "rule_key": "PRIV-CONSENT-002",
        "name": "明确拒绝后仍收集个人信息",
        "category": "consent",
        "description": "用户明确拒绝隐私政策后，App继续收集个人信息",
        "version": "1.0",
        "rule_content": {
            "scope": "android",
            "when": {
                "consent_status": ["REJECTED"],
                "event_type": "sensitive_api_call",
                "data_type": ["ANDROID_ID", "OAID", "IMEI", "MAC", "LOCATION", "CONTACTS", "PHONE_LIST"]
            },
            "exclude": {},
            "evidence_required": ["api_call_stack", "rejection_screenshot"],
            "severity": "HIGH",
            "remediation_template": "用户拒绝后立即停止所有个人信息收集行为"
        }
    },
    {
        "rule_key": "PRIV-SDK-001",
        "name": "第三方SDK未披露",
        "category": "sdk",
        "description": "检测到第三方SDK产生隐私行为，但隐私政策未披露该SDK",
        "version": "1.0",
        "rule_content": {
            "scope": "android",
            "when": {
                "sdk_identified": True,
                "sdk_has_privacy_behavior": True,
                "policy_discloses_sdk": False
            },
            "exclude": {"sdk_category": "crash"},
            "evidence_required": ["sdk_fingerprint", "call_stack", "policy_excerpt"],
            "severity": "MEDIUM",
            "remediation_template": "在隐私政策第三方SDK清单中补充披露该SDK"
        }
    },
    {
        "rule_key": "PRIV-SDK-002",
        "name": "SDK在同意前自动初始化并收集",
        "category": "sdk",
        "description": "第三方SDK在用户同意前自动初始化并收集个人信息",
        "version": "1.0",
        "rule_content": {
            "scope": "android",
            "when": {
                "consent_status": ["NOT_PRESENTED", "NOT_AGREED"],
                "event_type": "sdk_init",
                "followed_by_sensitive_api": True,
                "time_window_seconds": 10
            },
            "exclude": {},
            "evidence_required": ["init_call_stack", "sensitive_api_event", "timeline"],
            "severity": "HIGH",
            "remediation_template": "配置SDK延迟初始化，在用户同意后再调用SDK初始化接口"
        }
    },
    {
        "rule_key": "PRIV-MIN-001",
        "name": "非业务场景提前申请敏感权限",
        "category": "permission",
        "description": "App在非业务必需场景下提前申请敏感权限",
        "version": "1.0",
        "rule_content": {
            "scope": "android",
            "when": {
                "event_type": "permission_request",
                "permission_in": ["ACCESS_FINE_LOCATION", "ACCESS_COARSE_LOCATION", "READ_CONTACTS", "READ_PHONE_STATE", "RECORD_AUDIO"],
                "page_context": "not_business_function"
            },
            "exclude": {"page_context": "business_function"},
            "evidence_required": ["page_screenshot", "permission_dialog"],
            "severity": "MEDIUM",
            "remediation_template": "在用户实际使用对应功能时再申请权限"
        }
    },
    {
        "rule_key": "PRIV-NET-001",
        "name": "敏感信息发送至未披露接收方",
        "category": "network",
        "description": "App将敏感信息发送至隐私政策未披露的接收方域名",
        "version": "1.0",
        "rule_content": {
            "scope": "android",
            "when": {
                "event_type": "network_request",
                "contains_sensitive_data": True,
                "domain_disclosed_in_policy": False
            },
            "exclude": {},
            "evidence_required": ["network_request", "domain_attribution", "policy_excerpt"],
            "severity": "HIGH",
            "remediation_template": "在隐私政策中补充披露该接收方"
        }
    },
    {
        "rule_key": "PRIV-POLICY-001",
        "name": "政策未声明实际收集的信息类型",
        "category": "policy",
        "description": "动态检测确认App收集了隐私政策中未声明的个人信息类型",
        "version": "1.0",
        "rule_content": {
            "scope": "android",
            "when": {
                "event_type": "sensitive_api_call",
                "data_type_collected": True,
                "policy_declares_data_type": False
            },
            "exclude": {},
            "evidence_required": ["api_call_stack", "policy_excerpt"],
            "severity": "HIGH",
            "remediation_template": "在隐私政策中补充声明该信息类型的收集目的和方式"
        }
    },
    {
        "rule_key": "PRIV-RIGHT-001",
        "name": "撤回同意后仍继续处理",
        "category": "right",
        "description": "用户撤回同意后，App仍然继续收集或处理个人信息",
        "version": "1.0",
        "rule_content": {
            "scope": "android",
            "when": {
                "consent_status": ["REVOKED"],
                "event_type": "sensitive_api_call",
                "same_data_type_as_before_revoke": True
            },
            "exclude": {},
            "evidence_required": ["revocation_screenshot", "api_call_stack", "timeline"],
            "severity": "HIGH",
            "remediation_template": "撤回同意后立即停止个人信息收集和处理"
        }
    },
    {
        "rule_key": "PRIV-SEC-001",
        "name": "敏感信息通过明文或URL参数传输",
        "category": "security",
        "description": "敏感个人信息通过HTTP明文传输或出现在URL参数中",
        "version": "1.0",
        "rule_content": {
            "scope": "android",
            "when": {
                "event_type": "network_request",
                "is_https": False,
                "contains_sensitive_data": True
            },
            "exclude": {},
            "evidence_required": ["network_request"],
            "severity": "CRITICAL",
            "remediation_template": "使用HTTPS加密传输，敏感信息放入请求体而非URL参数"
        }
    },
    {
        "rule_key": "PRIV-ACCOUNT-001",
        "name": "账号注销入口不可达或流程异常",
        "category": "account",
        "description": "App账号注销入口不可达或注销流程存在障碍",
        "version": "1.0",
        "rule_content": {
            "scope": "android",
            "when": {
                "account_cancel_entry_reachable": False,
                "or": {"cancel_process_abnormal": True}
            },
            "exclude": {},
            "evidence_required": ["operation_path", "screenshot", "result"],
            "severity": "MEDIUM",
            "remediation_template": "提供便捷可达的账号注销入口，确保注销流程正常可用"
        }
    }
]

SEED_DICTS = [
    ("data_type", "ANDROID_ID", "Android ID"),
    ("data_type", "OAID", "匿名设备标识符"),
    ("data_type", "IMEI", "国际移动设备识别码"),
    ("data_type", "MAC", "MAC地址"),
    ("data_type", "LOCATION", "位置信息"),
    ("data_type", "CONTACTS", "通讯录"),
    ("data_type", "PHONE_LIST", "应用列表"),
    ("data_type", "IMSI", "国际移动用户识别码"),
    ("data_type", "PHONE_NUMBER", "手机号码"),
    ("data_type", "ICCID", "SIM卡序列号"),
    ("data_type", "SERIAL", "设备序列号"),
    ("data_type", "ADVERTISING_ID", "广告标识符"),
    ("event_type", "sensitive_api_call", "敏感API调用"),
    ("event_type", "network_request", "网络请求"),
    ("event_type", "permission_request", "权限申请"),
    ("event_type", "page_view", "页面浏览"),
    ("event_type", "static_data_flow", "静态数据流"),
    ("event_type", "consent_state_change", "同意状态变更"),
    ("event_type", "sdk_init", "SDK初始化"),
    ("consent_status", "NOT_PRESENTED", "未展示"),
    ("consent_status", "NOT_AGREED", "未同意"),
    ("consent_status", "REJECTED", "已拒绝"),
    ("consent_status", "CONSENTED", "已同意"),
    ("consent_status", "REVOKED", "已撤回"),
    ("scenario_type", "first_launch", "首次启动"),
    ("scenario_type", "rejected", "拒绝同意"),
    ("scenario_type", "consented", "同意隐私政策"),
    ("scenario_type", "function_trigger", "业务功能触发"),
    ("scenario_type", "revoked", "撤回同意"),
    ("scenario_type", "account_cancel", "账号注销"),
    ("severity", "critical", "严重"),
    ("severity", "high", "高"),
    ("severity", "medium", "中"),
    ("severity", "low", "低"),
    ("severity", "info", "提示"),
    ("finding_status", "open", "待处理"),
    ("finding_status", "assigned", "已分派"),
    ("finding_status", "fixing", "修复中"),
    ("finding_status", "ready_for_retest", "待复测"),
    ("finding_status", "retesting", "复测中"),
    ("finding_status", "closed_fixed", "已修复"),
    ("finding_status", "closed_accepted", "风险接受"),
    ("finding_status", "closed_false_positive", "误报"),
    ("finding_status", "reopened", "重新打开"),
    ("sdk_category", "analytics", "统计分析"),
    ("sdk_category", "ads", "广告"),
    ("sdk_category", "push", "推送"),
    ("sdk_category", "map", "地图"),
    ("sdk_category", "social", "社交"),
    ("sdk_category", "payment", "支付"),
    ("sdk_category", "crash", "崩溃收集"),
    ("sdk_category", "other", "其他"),
]


def seed_database():
    """初始化数据库种子数据"""
    db = SessionLocal()
    try:
        # 默认管理员
        if not db.query(User).filter(User.username == "admin").first():
            admin = User(
                username="admin",
                password_hash=hash_password("admin123"),
                role="platform_admin",
                full_name="系统管理员",
                status="active"
            )
            db.add(admin)
            db.commit()
            print("Created admin user: admin / admin123")

        # 默认规则
        for rule_data in SEED_RULES:
            existing = db.query(Rule).filter(Rule.rule_key == rule_data["rule_key"]).first()
            if not existing:
                rule = Rule(
                    rule_key=rule_data["rule_key"],
                    name=rule_data["name"],
                    category=rule_data["category"],
                    description=rule_data["description"],
                    status="active"
                )
                db.add(rule)
                db.flush()

                rv = RuleVersion(
                    rule_id=rule.id,
                    version=rule_data["version"],
                    rule_content=rule_data["rule_content"],
                    changelog="初始版本",
                    status="published"
                )
                db.add(rv)
                db.flush()

                rule.current_version_id = rv.id
                db.commit()
                print(f"Created rule: {rule_data['rule_key']}")

        # 默认字典
        for dtype, dkey, dvalue in SEED_DICTS:
            existing = db.query(SysDict).filter(
                SysDict.dict_type == dtype,
                SysDict.dict_key == dkey
            ).first()
            if not existing:
                db.add(SysDict(dict_type=dtype, dict_key=dkey, dict_value=dvalue))
        db.commit()
        print(f"Seeded {len(SEED_DICTS)} dictionary entries")

        # 内置关联规则（幂等：已存在 rule_key 则跳过）
        created_correlation = seed_correlation_rules(db)
        if created_correlation:
            print(f"Seeded {created_correlation} correlation rule(s)")

        print("Database seed completed.")
    finally:
        db.close()


if __name__ == "__main__":
    seed_database()
