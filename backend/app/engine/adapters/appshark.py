"""AppShark适配器 - 深度数据流/污点分析

运行方式（与官方一致）:
    java -jar AppShark-0.1.2-all.jar <config.json5>
- 要求 JRE 11+
- 工作目录(APPSHARK_HOME)下需有 config/EngineConfig.json5
- 规则为 JSON 文件, 定义 source/sink, 详见 backend/appshark/rules/
- 结果输出到 <out>/results.json, 顶层为 SecurityInfo / ComplianceInfo
"""
import glob
import json
import logging
import os
import re
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.core.config import settings
from app.engine.base import EngineAdapter, TaskContext, AdapterResult
from app.engine.runners.appshark_executor import AppSharkExecutor
from app.engine.runners.appshark_rules import resolve_rule_groups
from app.services.raw_section_service import split_sections

logger = logging.getLogger(__name__)


def _read_text(path: str, limit: int = 20000) -> str:
    try:
        with open(path, errors="ignore") as f:
            return f.read(limit)
    except OSError:
        return ""

APPSHARK_JAR = os.environ.get("APPSHARK_JAR", "/opt/appshark/AppShark-0.1.2-all.jar")
APPSHARK_HOME = os.environ.get("APPSHARK_HOME", "/opt/appshark")
# 默认使用项目内置隐私合规规则集
APPSHARK_RULE_DIR = os.environ.get(
    "APPSHARK_RULE_DIR",
    str(Path(__file__).resolve().parents[3] / "appshark" / "rules"),
)
# soot 需要的 Android 平台目录(android-<level>/android.jar)
# 注意: AppShark 0.1.2 不支持 config 中的 sdkPath 键, 平台库固定从
# <工作目录>/config/tools/platforms 加载
APPSHARK_SDK_PATH = os.environ.get(
    "APPSHARK_SDK_PATH", os.path.join(APPSHARK_HOME, "config", "tools", "platforms"))
# JVM 堆参数(污点分析内存消耗大)
APPSHARK_JAVA_OPTS = os.environ.get("APPSHARK_JAVA_OPTS", "-Xms1g -Xmx4g").split()


def _find_java11() -> str:
    """定位 JRE 11+ 的 java 可执行文件（不依赖系统默认 java 版本）"""
    env_java = os.environ.get("APPSHARK_JAVA")
    if env_java:
        return env_java
    for pattern in ("/usr/lib/jvm/java-11*/bin/java", "/usr/lib/jvm/jre-11*/bin/java",
                    "/usr/lib/jvm/java-17*/bin/java", "/usr/lib/jvm/jre-17*/bin/java"):
        matches = sorted(glob.glob(pattern))
        if matches:
            return matches[0]
    return "java"


def _java_major_version(java_bin: str) -> int:
    """解析 java 主版本号，失败返回 0"""
    try:
        r = subprocess.run([java_bin, "-version"], capture_output=True, text=True, timeout=10)
        m = re.search(r'version "(\d+)(?:\.(\d+))?', r.stderr + r.stdout)
        if not m:
            return 0
        major = int(m.group(1))
        if major == 1 and m.group(2):  # 1.8 风格
            major = int(m.group(2))
        return major
    except Exception:
        return 0


class AppSharkAdapter(EngineAdapter):
    """AppShark适配器: 污点分析/隐私合规数据流"""

    def __init__(self, config: dict | None = None):
        config = config or {}
        self._artifacts = []
        self._java = config.get("java_path") or _find_java11()
        self.jar_path = config.get("jar_path") or APPSHARK_JAR
        self.home_path = config.get("home_path") or APPSHARK_HOME
        self.sdk_path = config.get("sdk_path") or APPSHARK_SDK_PATH
        self.rule_dir = config.get("rule_dir") or APPSHARK_RULE_DIR
        self.java_opts = str(config.get("java_opts", " ".join(APPSHARK_JAVA_OPTS))).split()

    def get_capabilities(self) -> list[str]:
        return ["DATA_FLOW", "TAINT_ANALYSIS"]

    def validate_environment(self) -> bool:
        # 必须同时满足: JRE 11+ / jar 存在 / EngineConfig.json5 存在 / 规则目录非空
        if _java_major_version(self._java) < 11:
            logger.warning(f"AppShark requires JRE 11+, got: {self._java}")
            return False
        if not os.path.isfile(self.jar_path):
            logger.warning(f"AppShark jar not found: {self.jar_path}")
            return False
        if not os.path.isfile(os.path.join(self.home_path, "config", "EngineConfig.json5")):
            logger.warning(f"EngineConfig.json5 not found under {self.home_path}/config")
            return False
        if not glob.glob(os.path.join(self.sdk_path, "android-*", "android.jar")):
            logger.warning(f"No android platform jars found in {self.sdk_path}")
            return False
        if not glob.glob(os.path.join(self.rule_dir, "*.json")):
            logger.warning(f"No rule files found in {self.rule_dir}")
            return False
        return True

    async def prepare(self, ctx: TaskContext) -> None:
        if not os.path.exists(ctx.apk_path):
            raise FileNotFoundError(f"APK not found: {ctx.apk_path}")

    async def execute(self, ctx: TaskContext) -> AdapterResult:
        out_dir = f"/tmp/appshark_out_{ctx.task_id}"
        stages = ["appshark_preparing"]
        # 平台规则组映射到已验证的规则文件；未指定时使用目录下全部规则
        rule_files = resolve_rule_groups(self.rule_dir, ctx.config.get("rule_groups"))
        if not rule_files:
            rule_files = sorted(os.path.basename(p)
                                for p in glob.glob(os.path.join(self.rule_dir, "*.json")))

        # config.json5: JSON 是 JSON5 的子集, 直接写 JSON 即可
        config = {
            "apkPath": ctx.apk_path,
            "out": out_dir,
            "rules": ",".join(rule_files),
            "rulePath": self.rule_dir,
            "logLevel": ctx.config.get("appshark_log_level", 1),
            "maxThread": min(os.cpu_count() or 2, 8),
            "maxPointerAnalyzeTime": ctx.config.get("appshark_pointer_timeout", 300),
            # 诊断与覆盖率相关配置(隐私合规检测建议开启)
            "CallBackEnhance": True,        # 回调增强: 匿名类回调纳入分析
            # Fragment 生命周期入口, 默认关闭——加固/壳 APK 缺 Fragment 框架类时会 NPE,
            # 确认 APK 未加固后可通过任务 config {"appshark_support_fragment": true} 开启
            "supportFragment": bool(ctx.config.get("appshark_support_fragment", False)),
            "maxPathLength": 64,            # source->sink 最长路径
            "ruleMaxAnalyzer": 20000,       # 单规则 analyzer 上限, 防止被默认5000丢弃
            # 对 Library 方法也做指针传播, 降低漏报(性能换准确)
            "skipPointerPropagationForLibraryMethod": False,
        }
        if ctx.config.get("appshark_java_source"):
            config["javaSource"] = True     # 结果中附带 jadx 反编译源码(需要 tools/jadx)
        config_path = f"/tmp/appshark_cfg_{ctx.task_id}.json5"
        with open(config_path, "w") as f:
            json.dump(config, f, indent=2)

        stages.append("appshark_analyzing")
        executor = AppSharkExecutor(
            java_path=self._java, jar_path=self.jar_path,
            home_path=self.home_path, java_opts=self.java_opts,
        )
        try:
            proc = executor.run(config_path, out_dir, timeout=ctx.config.get("appshark_timeout", 1800))
            stages.append("appshark_persisting")
            stdout_text = _read_text(proc.stdout_path)
            stderr_text = _read_text(proc.stderr_path)

            # 完整保留原始输出目录(results.json/profile.json/vuln HTML/运行日志),
            # /tmp 会被清理, 复制到证据存储下, 供审计和二次分析
            saved_dir = self._persist_output(out_dir, ctx.task_id)

            result_file = os.path.join(saved_dir, "results.json")
            if not os.path.exists(result_file):
                # AppShark 崩溃时退出码也是 0, 需检查 stdout 和日志里的异常
                crash = self._find_log_exception(saved_dir) \
                    or self._extract_exception(stdout_text) \
                    or self._extract_exception(stderr_text)
                if crash:
                    return AdapterResult(success=False, error=f"AppShark 执行异常: {crash}", stage_events=stages)
                return AdapterResult(
                    success=True,
                    summary={"vulnerability_count": 0},
                    stage_events=stages,
                )

            with open(result_file) as f:
                raw_result = json.load(f)

            self._artifacts.append({"path": result_file, "type": "engine_output"})
            profile_file = os.path.join(saved_dir, "profile.json")
            if os.path.exists(profile_file):
                self._artifacts.append({"path": profile_file, "type": "engine_output"})
            for log_name in ("stdout.log", "stderr.log"):
                log_file = os.path.join(saved_dir, log_name)
                if os.path.exists(log_file):
                    self._artifacts.append({"path": log_file, "type": "engine_log"})

            vuln_events = self.normalize_events(raw_result)
            scan_stats = self._load_scan_stats(raw_result)
            # 扫描概要事件：无论是否有发现，都说明"扫了什么"（规则/规模/统计/输出位置）
            overview = {
                "event_type": "static_basic_info",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "data_type": "appshark_scan",
                "event_data": {
                    "engine": "AppShark",
                    "engine_version": "0.1.2",
                    "app_info": raw_result.get("AppInfo"),
                    "rules": rule_files,
                    "rule_analyzer_count": scan_stats.get("ruleAnalyzerCount"),
                    "process_method_statistics": scan_stats.get("ProcessMethodStatistics"),
                    "use_permissions": raw_result.get("UsePermissions"),
                    "vulnerability_count": len(vuln_events),
                    "output_dir": saved_dir,
                    "note": "未发现匹配的污点路径" if not vuln_events else None,
                },
            }
            events = [overview] + vuln_events + self._auxiliary_events(raw_result)

            return AdapterResult(
                success=True,
                events=events,
                artifacts=self._artifacts,
                raw_output_path=result_file,
                summary={
                    "vulnerability_count": len(vuln_events),
                    "rules": rule_files,
                    "scan_stats": scan_stats.get("ProcessMethodStatistics"),
                },
                stage_events=stages,
                normalized_event_count=len(events),
                raw_sections=split_sections(raw_result),
            )

        except TimeoutError:
            return AdapterResult(success=False, error="AppShark analysis timeout", stage_events=stages)
        except FileNotFoundError:
            return AdapterResult(
                success=False,
                error=f"AppShark.jar not found at {self.jar_path}",
                stage_events=stages,
            )
        except Exception as e:
            logger.error(f"AppShark analysis failed: {e}")
            return AdapterResult(success=False, error=str(e), stage_events=stages)

    @staticmethod
    def _auxiliary_events(raw_result: dict) -> list[dict]:
        """AppShark 附带的客观事实（权限、HTTP API、深链、JS Bridge）。"""
        ts = datetime.now(timezone.utc).isoformat()
        events = []
        for perm in raw_result.get("UsePermissions") or []:
            events.append({"event_type": "static_permission", "timestamp": ts, "data_type": "PERMISSION",
                           "api": str(perm)[:480], "event_data": {"permission": perm, "source": "appshark"}})
        for entry in raw_result.get("HTTP_API") or []:
            value = entry if isinstance(entry, str) else json.dumps(entry, ensure_ascii=False)
            events.append({"event_type": "static_url", "timestamp": ts, "api": value[:480],
                           "event_data": {"endpoint": entry, "source": "appshark"}})
        for name in raw_result.get("DeepLinkInfo") or []:
            events.append({"event_type": "static_deeplink", "timestamp": ts, "api": str(name)[:480],
                           "event_data": {"deeplink": name}})
        for bridge in raw_result.get("JsBridgeInfo") or []:
            events.append({"event_type": "security_observation", "timestamp": ts, "data_type": "jsbridge",
                           "api": str(bridge)[:480], "event_data": {"jsbridge": bridge}})
        return events

    @staticmethod
    def _persist_output(out_dir: str, task_id: int) -> str:
        """把 AppShark 输出目录从 /tmp 复制到证据存储, 返回持久化后的目录"""
        try:
            dest = Path(settings.STORAGE_ROOT) / f"task_{task_id}" / "appshark"
            if dest.exists():
                shutil.rmtree(dest)
            shutil.copytree(out_dir, dest)
            return str(dest)
        except Exception as e:
            logger.warning(f"persist appshark output failed: {e}")
            return out_dir

    @staticmethod
    def _load_scan_stats(raw_result: dict) -> dict:
        """读取 results.json 里 Profile 指向的统计文件（分析规模、各规则匹配数）"""
        profile_path = raw_result.get("Profile")
        if profile_path and os.path.exists(profile_path):
            try:
                with open(profile_path) as f:
                    return json.load(f)
            except Exception:
                pass
        return {}

    @staticmethod
    def _extract_exception(text: str) -> str:
        """从输出文本中提取异常行"""
        for line in text.splitlines():
            if "Exception" in line or "Error" in line:
                return line.strip()[:300]
        return ""

    @staticmethod
    def _find_log_exception(out_dir: str) -> str:
        """从 AppShark 日志中检查是否有异常堆栈（其崩溃时退出码仍为 0）"""
        log_root = os.path.join(out_dir, "log")
        for path in glob.glob(os.path.join(log_root, "**", "*"), recursive=True):
            if not os.path.isfile(path):
                continue
            try:
                with open(path, errors="ignore") as f:
                    for line in f:
                        if "Exception" in line or line.lstrip().startswith("at "):
                            return line.strip()[:300]
            except OSError:
                continue
        return ""

    def normalize_events(self, raw_result: Any) -> list[dict]:
        """解析 results.json: SecurityInfo / ComplianceInfo 均为 分类->名称->漏洞组 三级结构"""
        events = []
        for section in ("ComplianceInfo", "SecurityInfo"):
            section_data = raw_result.get(section)
            if not isinstance(section_data, dict):
                continue
            for category, by_name in section_data.items():
                if not isinstance(by_name, dict):
                    continue
                for rule_name, group in by_name.items():
                    if not isinstance(group, dict):
                        continue
                    for vuln in group.get("vulners", []):
                        if not isinstance(vuln, dict):
                            continue
                        details = vuln.get("details", {})
                        if "Source" not in details and "Sink" not in details:
                            # APIMode 规则: 敏感API调用点
                            # position=调用方方法(str), target=[调用方方法, Jimple调用语句]
                            target = details.get("target") or []
                            statement = str(target[-1]) if target else ""
                            m = re.search(r"<[^>]+>", statement)
                            events.append({
                                "event_type": "static_sensitive_api",
                                "timestamp": datetime.now(timezone.utc).isoformat(),
                                "data_type": category,
                                "api": m.group(0) if m else statement,
                                "caller": str(details.get("position", "")),
                                "event_data": {
                                    "section": section,
                                    "mode": "APIMode",
                                    "rule": rule_name,
                                    "level": group.get("level"),
                                    "detail": group.get("detail"),
                                    "hash": vuln.get("hash"),
                                    "statement": statement,
                                    "url": details.get("url"),
                                },
                            })
                            continue
                        events.append({
                            "event_type": "static_data_flow",
                            "timestamp": datetime.now(timezone.utc).isoformat(),
                            "data_type": category,
                            "api": str(details.get("Sink", "")),
                            "caller": str(details.get("position", "")),
                            "event_data": {
                                "section": section,
                                "rule": rule_name,
                                "level": group.get("level"),
                                "detail": group.get("detail"),
                                "hash": vuln.get("hash"),
                                "source": details.get("Source"),
                                "sink": details.get("Sink"),
                                "entry_method": details.get("entryMethod"),
                                "taint_path": details.get("target"),
                                "url": details.get("url"),
                            },
                        })
        return events

    def collect_artifacts(self) -> list[dict]:
        return self._artifacts
