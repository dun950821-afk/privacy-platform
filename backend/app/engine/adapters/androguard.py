"""Androguard适配器 - APK基础分析 (Androguard 4.x)"""
import os
import json
import hashlib
import logging
from typing import Any
from app.engine.base import EngineAdapter, TaskContext, AdapterResult
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


class AndroguardAdapter(EngineAdapter):
    """Androguard 4.x 适配器: APK基础解析"""

    def __init__(self):
        self._artifacts = []

    def get_capabilities(self) -> list[str]:
        return ["BASIC_INFO", "PERMISSIONS", "COMPONENTS", "SIGNATURE", "STRINGS"]

    def validate_environment(self) -> bool:
        try:
            import androguard
            return True
        except ImportError:
            return False

    async def prepare(self, ctx: TaskContext) -> None:
        if not os.path.exists(ctx.apk_path):
            raise FileNotFoundError(f"APK not found: {ctx.apk_path}")

    async def execute(self, ctx: TaskContext) -> AdapterResult:
        try:
            from androguard.core.apk import APK
        except ImportError:
            return AdapterResult(success=False, error="androguard not installed")

        try:
            apk = APK(ctx.apk_path)

            # 基本信息
            sha256 = hashlib.sha256(open(ctx.apk_path, "rb").read()).hexdigest()
            basic_info = {
                "package_name": apk.get_package(),
                "app_name": apk.get_app_name(),
                "version_name": apk.get_androidversion_name(),
                "version_code": apk.get_androidversion_code(),
                "min_sdk": apk.get_min_sdk_version(),
                "target_sdk": apk.get_target_sdk_version(),
                "max_sdk": apk.get_max_sdk_version(),
                "file_size": os.path.getsize(ctx.apk_path),
                "sha256": sha256,
            }

            # 权限
            permissions = apk.get_permissions()
            dangerous_perms = [p for p in permissions if "android.permission" in p]

            # 组件
            activities = apk.get_activities()
            services = apk.get_services()
            receivers = apk.get_receivers()
            providers = apk.get_providers()

            # 签名
            cert_info = {}
            if apk.is_signed():
                certs = apk.get_certificates()
                for cert in certs:
                    cert_info = {
                        "subject": str(cert.subject),
                        "issuer": str(cert.issuer),
                        "serial": cert.serial_number,
                    }
                    break

            # 敏感权限分类
            sensitive_perms = {
                "LOCATION": ["ACCESS_FINE_LOCATION", "ACCESS_COARSE_LOCATION"],
                "PHONE_STATE": ["READ_PHONE_STATE", "CALL_PHONE", "READ_PHONE_NUMBERS"],
                "CONTACTS": ["READ_CONTACTS", "WRITE_CONTACTS"],
                "CAMERA": ["CAMERA"],
                "MICROPHONE": ["RECORD_AUDIO"],
                "STORAGE": ["READ_EXTERNAL_STORAGE", "WRITE_EXTERNAL_STORAGE"],
                "SMS": ["READ_SMS", "SEND_SMS"],
            }
            matched_sensitive = []
            for category, perms in sensitive_perms.items():
                for p in perms:
                    if any(p in dp for dp in dangerous_perms):
                        matched_sensitive.append({"category": category, "permission": p})

            result_data = {
                "basic_info": basic_info,
                "permissions": {
                    "declared": permissions,
                    "dangerous": dangerous_perms,
                    "sensitive_matched": matched_sensitive,
                },
                "components": {
                    "activities": activities,
                    "services": services,
                    "receivers": receivers,
                    "providers": providers,
                },
                "signature": cert_info,
                "stats": {
                    "permission_count": len(permissions),
                    "activity_count": len(activities),
                    "service_count": len(services),
                    "receiver_count": len(receivers),
                    "provider_count": len(providers),
                },
            }

            # 保存原始结果
            raw_path = f"/tmp/androguard_result_{ctx.task_id}.json"
            with open(raw_path, "w") as f:
                json.dump(result_data, f, ensure_ascii=False, indent=2, default=str)

            self._artifacts.append({"path": raw_path, "type": "engine_output"})

            return AdapterResult(
                success=True,
                events=self.normalize_events(result_data),
                artifacts=self._artifacts,
                raw_output_path=raw_path,
                summary=result_data["stats"]
            )

        except Exception as e:
            logger.error(f"Androguard analysis failed: {e}", exc_info=True)
            return AdapterResult(success=False, error=str(e))

    def normalize_events(self, raw_result: Any) -> list[dict]:
        events = []
        ts = datetime.now(timezone.utc).isoformat()
        info = raw_result.get("basic_info", {})

        # 基础信息事件
        events.append({
            "event_type": "static_basic_info",
            "timestamp": ts,
            "event_data": info
        })

        # 权限事件
        for perm in raw_result.get("permissions", {}).get("dangerous", []):
            events.append({
                "event_type": "static_permission",
                "timestamp": ts,
                "data_type": "PERMISSION",
                "api": perm,
                "event_data": {"permission": perm, "source": "manifest"}
            })

        # 敏感权限匹配
        for sp in raw_result.get("permissions", {}).get("sensitive_matched", []):
            events.append({
                "event_type": "static_sensitive_permission",
                "timestamp": ts,
                "data_type": sp["category"],
                "api": sp["permission"],
                "event_data": sp
            })

        # 全部声明组件（Activity/Service/Receiver/Provider），供 SDK 指纹匹配
        comp = raw_result.get("components", {})
        for ctype, key in [("ACTIVITY", "activities"), ("SERVICE", "services"),
                           ("RECEIVER", "receivers"), ("PROVIDER", "providers")]:
            for name in comp.get(key, []):
                events.append({
                    "event_type": "static_component",
                    "timestamp": ts,
                    "data_type": ctype,
                    "api": name,
                    "event_data": {"component": name, "type": key}
                })

        return events

    def collect_artifacts(self) -> list[dict]:
        return self._artifacts
