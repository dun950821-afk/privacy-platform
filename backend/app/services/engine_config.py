"""引擎全局配置服务：默认值、敏感字段加密与脱敏。"""
import base64
import hashlib
import os
from copy import deepcopy
from pathlib import Path
from urllib.parse import urlparse

from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models import EngineConfig


def _project_rule_dir() -> str:
    return str(Path(__file__).resolve().parents[2] / "appshark" / "rules")


ENGINE_CONFIG_DEFINITIONS = {
    "androguard": {
        "fields": [
            {"key": "alias", "label": "显示别名", "type": "text", "required": False, "default": "", "help": "配置后用户界面只显示该名称；留空使用系统默认名称。"},
            {"key": "python_path", "label": "Python 环境", "type": "path", "required": False,
             "default": os.environ.get("PYTHON", "/tmp/venv/bin/python"), "readonly": True,
             "help": "Worker 本地 Python 环境，Androguard 不需要服务地址。"},
            {"key": "parse_timeout", "label": "解析超时（秒）", "type": "number", "required": True,
             "default": 300, "help": "单个 APK 的最大解析时间。"},
        ],
        "help": {"title": "Androguard 使用说明", "text": "Androguard 在静态检测 Worker 所在机器本地执行，无需启动 HTTP 服务。请确保 Worker 使用的 Python 环境已安装 androguard。", "docs_url": "https://github.com/androguard/androguard"},
    },
    "appshark": {
        "fields": [
            {"key": "alias", "label": "显示别名", "type": "text", "required": False, "default": "", "help": "配置后用户界面只显示该名称；留空使用系统默认名称。"},
            {"key": "java_path", "label": "Java 可执行文件", "type": "path", "required": True, "default": os.environ.get("APPSHARK_JAVA", "java"), "help": "需要 JRE 11 或更高版本。"},
            {"key": "jar_path", "label": "AppShark JAR 路径", "type": "path", "required": True, "default": os.environ.get("APPSHARK_JAR", "/opt/appshark/AppShark-0.1.2-all.jar"), "help": "AppShark 主程序 JAR 文件。"},
            {"key": "home_path", "label": "工作目录", "type": "path", "required": True, "default": os.environ.get("APPSHARK_HOME", "/opt/appshark"), "help": "目录下必须包含 config/EngineConfig.json5。"},
            {"key": "sdk_path", "label": "Android 平台目录", "type": "path", "required": True, "default": os.environ.get("APPSHARK_SDK_PATH", "/opt/appshark/config/tools/platforms"), "help": "目录下需要存在 android-*/android.jar。"},
            {"key": "rule_dir", "label": "规则目录", "type": "path", "required": True, "default": os.environ.get("APPSHARK_RULE_DIR", _project_rule_dir()), "help": "目录下需要存在 JSON 规则文件。"},
            {"key": "java_opts", "label": "JVM 参数", "type": "text", "required": True, "default": os.environ.get("APPSHARK_JAVA_OPTS", "-Xms1g -Xmx4g"), "help": "例如 -Xms1g -Xmx4g。"},
            {"key": "scan_timeout", "label": "扫描超时（秒）", "type": "number", "required": True, "default": 1800, "help": "单次 AppShark 扫描的最大时间。"},
        ],
        "help": {"title": "AppShark 使用说明", "text": "AppShark 需要 JRE 11+、EngineConfig.json5、Android 平台 android.jar 和项目规则文件。", "docs_url": "https://github.com/bytedance/appshark"},
    },
    "mobsf": {
        "fields": [
            {"key": "alias", "label": "显示别名", "type": "text", "required": False, "default": "", "help": "配置后用户界面只显示该名称；留空使用系统默认名称。"},
            {"key": "url", "label": "服务地址", "type": "url", "required": True, "default": os.environ.get("MOBSF_URL", "http://127.0.0.1:8001"), "help": "填写 MobSF Web 服务地址，不要填写 /docs。"},
            {"key": "connect_timeout", "label": "连接超时（秒）", "type": "number", "required": True, "default": 10, "help": "健康检查和上传连接建立的超时时间。"},
            {"key": "scan_timeout", "label": "扫描超时（秒）", "type": "number", "required": True, "default": 300, "help": "MobSF 扫描请求的最大等待时间。"},
        ],
        "secrets": [{"key": "api_key", "label": "API Key", "type": "password", "help": "MobSF 页面或 API 配置中的认证密钥。"}],
        "help": {"title": "MobSF 使用说明", "text": "MobSF 通过 REST API 执行扫描。请先启动 MobSF 容器，再填写服务地址和 API Key；新版 MobSF 没有 /docs 路由。", "docs_url": "https://mobsf.github.io/docs/"},
    },
}


def _fernet() -> Fernet:
    digest = hashlib.sha256(settings.SECRET_KEY.encode()).digest()
    return Fernet(base64.urlsafe_b64encode(digest))


def encrypt_secret(value: str) -> str:
    return _fernet().encrypt(value.encode()).decode()


def decrypt_secret(value: str) -> str:
    try:
        return _fernet().decrypt(value.encode()).decode()
    except (InvalidToken, ValueError):
        raise ValueError("引擎敏感配置无法解密，请检查 SECRET_KEY")


def get_definition(engine_type: str) -> dict:
    definition = ENGINE_CONFIG_DEFINITIONS.get(engine_type)
    if not definition:
        raise KeyError(f"引擎类型 {engine_type} 不存在")
    return definition


def _defaults(engine_type: str) -> dict:
    return {f["key"]: f.get("default") for f in get_definition(engine_type).get("fields", [])}


def get_or_create(db: Session, engine_type: str) -> EngineConfig:
    get_definition(engine_type)
    row = db.query(EngineConfig).filter(EngineConfig.engine_type == engine_type).first()
    if not row:
        row = EngineConfig(engine_type=engine_type, config_json=_defaults(engine_type), secret_json={})
        db.add(row)
        db.commit()
        db.refresh(row)
    return row


def _coerce_number(value):
    """数字输入框可能提交字符串，统一转成数字；非数字原样返回。"""
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value
    if isinstance(value, str):
        text = value.strip()
        try:
            return int(text)
        except ValueError:
            return value
    return value


def validate_config(engine_type: str, values: dict, require_required: bool = False) -> None:
    definition = get_definition(engine_type)
    allowed = {f["key"] for f in definition.get("fields", [])}
    unknown = set(values) - allowed
    if unknown:
        raise ValueError(f"未知配置项: {', '.join(sorted(unknown))}")
    for field in definition.get("fields", []):
        key = field["key"]
        if require_required and field.get("required") and (key not in values or values[key] in (None, "")):
            raise ValueError(f"配置项 {field['label']} 不能为空")
        if key not in values or values[key] in (None, ""):
            continue
        if field["type"] == "number":
            value = _coerce_number(values[key])
            if not isinstance(value, (int, float)) or isinstance(value, bool) or value <= 0:
                raise ValueError(f"配置项 {field['label']} 必须是正数")
        if field["type"] == "url":
            parsed = urlparse(str(values[key]))
            if parsed.scheme not in ("http", "https") or not parsed.netloc:
                raise ValueError("服务地址必须是完整的 http:// 或 https:// 地址")


def save(db: Session, engine_type: str, config: dict, secrets: dict, clear_secrets: list[str], user_id: int | None = None) -> EngineConfig:
    row = get_or_create(db, engine_type)
    validate_config(engine_type, config)
    definition = get_definition(engine_type)
    secret_keys = {s["key"] for s in definition.get("secrets", [])}
    if set(secrets) - secret_keys or set(clear_secrets) - secret_keys:
        raise ValueError("未知敏感配置项")
    merged = _defaults(engine_type)
    merged.update(row.config_json or {})
    merged.update(config)
    validate_config(engine_type, merged, require_required=True)
    # 数字输入框可能提交字符串，统一落库为数字
    for field in definition.get("fields", []):
        key = field["key"]
        if field["type"] == "number" and key in merged:
            merged[key] = _coerce_number(merged[key])
    encrypted = dict(row.secret_json or {})
    for key, value in secrets.items():
        if value:
            encrypted[key] = encrypt_secret(value)
    for key in clear_secrets:
        encrypted.pop(key, None)
    row.config_json = merged
    row.secret_json = encrypted
    row.updated_by = user_id
    db.commit()
    db.refresh(row)
    return row


def resolved(db: Session, engine_type: str) -> dict:
    row = get_or_create(db, engine_type)
    result = dict(row.config_json or {})
    for key, value in (row.secret_json or {}).items():
        result[key] = decrypt_secret(value)
    return result


def public(db: Session, engine_type: str) -> dict:
    row = get_or_create(db, engine_type)
    definition = get_definition(engine_type)
    secrets = {}
    for field in definition.get("secrets", []):
        configured = bool((row.secret_json or {}).get(field["key"]))
        secrets[field["key"]] = {"configured": configured, "masked": "********" if configured else ""}
    return {"config": row.config_json or {}, "secrets": secrets, "fields": definition.get("fields", []), "secret_fields": definition.get("secrets", []), "help": definition.get("help", {})}


def redacted(db: Session, engine_type: str) -> dict:
    value = resolved(db, engine_type)
    for field in get_definition(engine_type).get("secrets", []):
        if field["key"] in value:
            value[field["key"]] = "********"
    return value


def reset(db: Session, engine_type: str, user_id: int | None = None) -> EngineConfig:
    row = get_or_create(db, engine_type)
    row.config_json = _defaults(engine_type)
    row.secret_json = {}
    row.updated_by = user_id
    db.commit()
    db.refresh(row)
    return row


# ============ 展示名解析 ============

_REGISTRY_FALLBACK = {
    "androguard": "Androguard",
    "appshark": "AppShark",
    "mobsf": "MobSF",
}


def display_name(db: Session, engine_type: str) -> str:
    """返回引擎当前展示名：配置了别名则用别名，否则回退到注册表默认名。"""
    try:
        row = get_or_create(db, engine_type)
        alias = str(row.config_json.get("alias", "")).strip() if row.config_json else ""
        if alias:
            return alias
    except Exception:
        pass
    return _REGISTRY_FALLBACK.get(engine_type, engine_type)


def display_names(db: Session, engine_types: list[str]) -> dict[str, str]:
    return {et: display_name(db, et) for et in engine_types}
