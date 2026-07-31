"""AppShark适配器 - 深度数据流分析"""
import os
import json
import subprocess
import logging
from typing import Any
from app.engine.base import EngineAdapter, TaskContext, AdapterResult
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

APPSHARK_JAR = os.environ.get("APPSHARK_JAR", "/opt/appshark/AppShark.jar")


class AppSharkAdapter(EngineAdapter):
    """AppShark适配器: 污点分析/数据流"""

    def __init__(self):
        self._artifacts = []

    def get_capabilities(self) -> list[str]:
        return ["DATA_FLOW", "TAINT_ANALYSIS"]

    def validate_environment(self) -> bool:
        # 必须同时满足: Java 可用 + AppShark.jar 存在
        try:
            r = subprocess.run(["java", "-version"], capture_output=True, timeout=10)
            if r.returncode != 0:
                return False
        except Exception:
            return False
        return os.path.isfile(APPSHARK_JAR)

    async def prepare(self, ctx: TaskContext) -> None:
        if not os.path.exists(ctx.apk_path):
            raise FileNotFoundError(f"APK not found: {ctx.apk_path}")

    async def execute(self, ctx: TaskContext) -> AdapterResult:
        config = {
            "apk_path": ctx.apk_path,
            "output_dir": f"/tmp/appshark_output_{ctx.task_id}",
            "rules": ctx.config.get("rules", []),
        }

        config_path = f"/tmp/appshark_config_{ctx.task_id}.json"
        with open(config_path, "w") as f:
            json.dump(config, f)

        try:
            cmd = [
                "java", "-jar", APPSHARK_JAR,
                "-c", config_path,
                "-o", config["output_dir"]
            ]

            proc = subprocess.run(
                cmd, capture_output=True, text=True,
                timeout=ctx.config.get("timeout", 1800)
            )

            if proc.returncode != 0:
                return AdapterResult(
                    success=False,
                    error=f"AppShark exited {proc.returncode}: {proc.stderr[:500]}"
                )

            result_file = os.path.join(config["output_dir"], "results.json")
            if not os.path.exists(result_file):
                return AdapterResult(
                    success=True,
                    summary={"vulnerability_count": 0},
                    artifacts=self._artifacts,
                )

            with open(result_file) as f:
                raw_result = json.load(f)

            self._artifacts.append({"path": result_file, "type": "engine_output"})

            return AdapterResult(
                success=True,
                events=self.normalize_events(raw_result),
                artifacts=self._artifacts,
                raw_output_path=result_file,
                summary={"vulnerability_count": len(raw_result.get("results", {}))}
            )

        except subprocess.TimeoutExpired:
            return AdapterResult(success=False, error="AppShark analysis timeout")
        except FileNotFoundError:
            return AdapterResult(
                success=False,
                error=f"AppShark.jar not found at {APPSHARK_JAR}"
            )
        except Exception as e:
            logger.error(f"AppShark analysis failed: {e}")
            return AdapterResult(success=False, error=str(e))

    def normalize_events(self, raw_result: Any) -> list[dict]:
        events = []
        results = raw_result.get("results", raw_result)

        if isinstance(results, dict):
            for vuln_type, vulns in results.items():
                if isinstance(vulns, list):
                    for v in vulns:
                        events.append({
                            "event_type": "static_data_flow",
                            "timestamp": datetime.now(timezone.utc).isoformat(),
                            "data_type": vuln_type,
                            "api": v.get("target", {}).get("method", "") if isinstance(v, dict) else "",
                            "caller": v.get("source", {}).get("method", "") if isinstance(v, dict) else "",
                            "event_data": {
                                "source": v.get("source", {}) if isinstance(v, dict) else {},
                                "target": v.get("target", {}) if isinstance(v, dict) else {},
                                "path": v.get("path", []) if isinstance(v, dict) else [],
                                "vulnerability_type": vuln_type
                            }
                        })
        return events

    def collect_artifacts(self) -> list[dict]:
        return self._artifacts
