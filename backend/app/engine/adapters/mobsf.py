"""MobSF适配器 - 静态扫描"""
import os
import json
import logging
import httpx
from typing import Any
from app.engine.base import EngineAdapter, TaskContext, AdapterResult
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


class MobSFAdapter(EngineAdapter):
    """MobSF适配器: 通过MobSF REST API进行静态扫描"""

    def __init__(self, mobsf_url: str = None, api_key: str = ""):
        if mobsf_url is None:
            mobsf_url = os.environ.get("MOBSF_URL", "http://localhost:8001")
        self.mobsf_url = mobsf_url.rstrip("/")
        self.api_key = api_key
        self._artifacts = []

    def get_capabilities(self) -> list[str]:
        return ["STATIC_SCAN", "MALWARE_CHECK", "TRACKER_DETECTION"]

    def validate_environment(self) -> bool:
        try:
            r = httpx.get(f"{self.mobsf_url}/docs", timeout=5)
            return r.status_code == 200
        except Exception:
            return False

    async def prepare(self, ctx: TaskContext) -> None:
        if not os.path.exists(ctx.apk_path):
            raise FileNotFoundError(f"APK not found: {ctx.apk_path}")

    async def execute(self, ctx: TaskContext) -> AdapterResult:
        headers = {"Authorization": self.api_key} if self.api_key else {}
        
        try:
            async with httpx.AsyncClient(timeout=300) as client:
                # 上传APK
                with open(ctx.apk_path, "rb") as f:
                    upload_resp = await client.post(
                        f"{self.mobsf_url}/api/v1/upload",
                        files={"file": (os.path.basename(ctx.apk_path), f)},
                        headers=headers
                    )
                
                if upload_resp.status_code != 200:
                    return AdapterResult(success=False, error="MobSF upload failed")
                
                scan_hash = upload_resp.json().get("hash")
                
                # 触发静态扫描
                scan_resp = await client.post(
                    f"{self.mobsf_url}/api/v1/scan",
                    data={"hash": scan_hash},
                    headers=headers
                )
                
                if scan_resp.status_code != 200:
                    return AdapterResult(success=False, error="MobSF scan failed")
                
                raw_result = scan_resp.json()
                
                # 保存结果
                raw_path = f"/tmp/mobsf_result_{ctx.task_id}.json"
                with open(raw_path, "w") as f:
                    json.dump(raw_result, f, ensure_ascii=False, indent=2, default=str)
                
                self._artifacts.append({"path": raw_path, "type": "engine_output"})
                
                return AdapterResult(
                    success=True,
                    events=self.normalize_events(raw_result),
                    artifacts=self._artifacts,
                    raw_output_path=raw_path,
                    summary={"tracker_count": len(raw_result.get("trackers", {}).get("trackers", []))}
                )
                
        except Exception as e:
            logger.error(f"MobSF scan failed: {e}")
            return AdapterResult(success=False, error=str(e))

    def normalize_events(self, raw_result: Any) -> list[dict]:
        events = []
        
        # 跟踪器/SDK
        trackers = raw_result.get("trackers", {}).get("trackers", [])
        for t in trackers:
            events.append({
                "event_type": "static_tracker",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "event_data": {"name": t.get("name"), "url": t.get("url")}
            })
        
        # URL
        urls = raw_result.get("urls", [])
        for url in urls[:100]:
            events.append({
                "event_type": "static_url",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "api": url.get("url", str(url)) if isinstance(url, dict) else str(url),
                "event_data": {"url": url}
            })
        
        return events

    def collect_artifacts(self) -> list[dict]:
        return self._artifacts
