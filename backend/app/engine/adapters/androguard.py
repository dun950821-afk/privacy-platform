"""Androguard适配器 - APK基础分析 (Androguard 4.x)"""
import os
import json
import hashlib
import logging
from typing import Any
from app.engine.base import EngineAdapter, TaskContext, AdapterResult
from app.engine.runners.androguard_runner import run_in_process
from app.services.raw_section_service import split_sections
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


class AndroguardAdapter(EngineAdapter):
    """Androguard 4.x 适配器: APK基础解析"""

    def __init__(self, config: dict | None = None):
        self.config = config or {}
        self.parse_timeout = int(self.config.get("parse_timeout", 300))
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
            raw_path = f"/tmp/androguard_result_{ctx.task_id}.json"
            facts = run_in_process(ctx.apk_path, raw_path, timeout=self.parse_timeout, config=self.config)
            events = self.normalize_events(facts)
            return AdapterResult(success=True, events=events, artifacts=[{"path": raw_path, "type": "engine_output"}], raw_output_path=raw_path, summary=facts.get("stats", {}), normalized_event_count=len(events), raw_sections=split_sections(facts))
        except TimeoutError as exc:
            return AdapterResult(success=False, error=str(exc))
        except Exception as exc:
            logger.error("Androguard analysis failed: %s", exc, exc_info=True)
            return AdapterResult(success=False, error=str(exc))

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
        #
        # 键名曾长期写作 "dangerous"，而 runner 写的是 "declared"
        # （见 runners/androguard_runner.py 的 `"permissions": {"declared": …}`）——
        # 这个键**从来不存在**，于是声明权限被静默丢弃，不报错也不记日志。
        # 消费侧 compliance_profile._permission_rows 按权限名聚合并累计来源引擎，
        # 所以修好之后不会产生重复行，只是 declared_by 多出 androguard，归因更准确。
        for perm in raw_result.get("permissions", {}).get("declared", []):
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

        # native 库（APK 里 lib/**/*.so 的文件名），供 native 指纹匹配。
        # 数据一直在采集（runners/androguard_runner.py 的 `native_libraries`），
        # 只是从没变成过事件——2026-09-29 接上。空列表是常见情况（纯 Java 应用）。
        for lib in raw_result.get("native_libraries") or []:
            events.append({
                "event_type": "static_native_lib",
                "timestamp": ts,
                "data_type": "NATIVE_LIB",
                "api": lib,
                # caller 留空：native 库没有调用方。匹配器按 api 匹配。
                "event_data": {"library": lib, "source": "apk_lib_dir"}
            })

        return events

    def collect_artifacts(self) -> list[dict]:
        return self._artifacts
