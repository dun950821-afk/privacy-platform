"""MobSF适配器 - 静态扫描"""
import os
import json
import logging
import httpx
from typing import Any
import hashlib
import time
from app.engine.errors import AdapterError
from app.engine.base import EngineAdapter, TaskContext, AdapterResult
from app.services.raw_section_service import split_sections
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


class MobSFAdapter(EngineAdapter):
    """MobSF适配器: 通过MobSF REST API进行静态扫描"""

    def __init__(self, config: dict | None = None, mobsf_url: str = None, api_key: str = ""):
        config = config or {}
        if mobsf_url is None:
            mobsf_url = config.get("url") or os.environ.get("MOBSF_URL", "http://localhost:8001")
        self.mobsf_url = mobsf_url.rstrip("/")
        self.api_key = config.get("api_key") or api_key or os.environ.get("MOBSF_API_KEY", "")
        self.connect_timeout = int(config.get("connect_timeout", 10))
        self.scan_timeout = int(config.get("scan_timeout", 300))
        self.prefer_async = bool(config.get("prefer_async", False))
        self.last_error = ""
        self._artifacts = []

    def provider_metadata(self, raw_result: dict) -> dict:
        return {
            "provider": "mobsf",
            "provider_version": raw_result.get("version") or raw_result.get("mobsf_version"),
            "provider_mode": "sync",
        }

    def get_capabilities(self) -> list[str]:
        return ["STATIC_SCAN", "MALWARE_CHECK", "TRACKER_DETECTION"]

    def probe_capabilities(self) -> dict:
        """探测 Provider 端点；未知端点不影响同步回退。"""
        headers = {"Authorization": self.api_key} if self.api_key else {}
        result = {"async_supported": False, "sync_supported": True, "provider_mode": "sync"}
        try:
            response = httpx.get(f"{self.mobsf_url}/api/v1/scans", headers=headers, timeout=self.connect_timeout)
            if response.status_code in (200, 401, 403):
                result["async_supported"] = response.status_code == 200
            if self.prefer_async and result["async_supported"]:
                result["provider_mode"] = "async"
        except httpx.RequestError as exc:
            result["probe_error"] = str(exc)
        return result

    def validate_environment(self) -> bool:
        try:
            # MobSF 新版没有 FastAPI /docs；根路径重定向到登录页即可证明服务在线。
            r = httpx.get(f"{self.mobsf_url}/", timeout=self.connect_timeout, follow_redirects=True)
            if r.status_code >= 500:
                self.last_error = f"MobSF 服务异常（HTTP {r.status_code}）"
                return False
            if not self.api_key:
                self.last_error = "MobSF 服务在线，但未配置 API Key"
                return False
            api = httpx.get(f"{self.mobsf_url}/api/v1/", headers={"Authorization": self.api_key}, timeout=self.connect_timeout)
            if api.status_code in (401, 403):
                self.last_error = "MobSF 服务在线，但 API Key 无效"
                return False
            self.last_error = ""
            return api.status_code < 500
        except Exception as exc:
            self.last_error = f"无法连接 MobSF 服务: {exc}"
            return False

    async def prepare(self, ctx: TaskContext) -> None:
        if not os.path.exists(ctx.apk_path):
            raise FileNotFoundError(f"APK not found: {ctx.apk_path}")

    async def execute(self, ctx: TaskContext) -> AdapterResult:
        headers = {"Authorization": self.api_key} if self.api_key else {}
        stages = []
        try:
            stages.append("mobsf_uploading")
            timeout = httpx.Timeout(self.scan_timeout, connect=self.connect_timeout)
            async with httpx.AsyncClient(timeout=timeout) as client:
                with open(ctx.apk_path, "rb") as f:
                    upload_resp = await client.post(
                        f"{self.mobsf_url}/api/v1/upload",
                        files={"file": (os.path.basename(ctx.apk_path), f)}, headers=headers,
                    )
                if upload_resp.status_code in (401, 403):
                    raise AdapterError("ENGINE_AUTH_FAILED", "MobSF API Key 验证失败", f"upload HTTP {upload_resp.status_code}", False, upload_resp.status_code, "mobsf_uploading")
                if upload_resp.status_code == 413:
                    raise AdapterError("FILE_TOO_LARGE", "APK 文件超过 MobSF 限制", "upload HTTP 413", False, 413, "mobsf_uploading")
                if upload_resp.status_code >= 500:
                    raise AdapterError("UPLOAD_FAILED", "MobSF 上传服务暂时不可用", f"upload HTTP {upload_resp.status_code}", True, upload_resp.status_code, "mobsf_uploading")
                if upload_resp.status_code != 200:
                    raise AdapterError("UPLOAD_FAILED", "MobSF APK 上传失败", f"upload HTTP {upload_resp.status_code}: {upload_resp.text[:300]}", False, upload_resp.status_code, "mobsf_uploading")
                upload_data = upload_resp.json()
                scan_hash = upload_data.get("hash")
                if not scan_hash:
                    raise AdapterError("UPLOAD_FAILED", "MobSF 未返回扫描标识", "upload response missing hash", False, upload_resp.status_code, "mobsf_uploading")

                stages.append("mobsf_scan_starting")
                scan_resp = await client.post(f"{self.mobsf_url}/api/v1/scan", data={"hash": scan_hash, "scan_type": "apk"}, headers=headers)
                if scan_resp.status_code in (401, 403):
                    raise AdapterError("ENGINE_AUTH_FAILED", "MobSF API Key 验证失败", f"scan HTTP {scan_resp.status_code}", False, scan_resp.status_code, "mobsf_scan_starting")
                if scan_resp.status_code >= 500:
                    raise AdapterError("SCAN_START_FAILED", "MobSF 扫描服务暂时不可用", f"scan HTTP {scan_resp.status_code}", True, scan_resp.status_code, "mobsf_scan_starting")
                if scan_resp.status_code != 200:
                    raise AdapterError("SCAN_START_FAILED", "MobSF 扫描启动失败", f"scan HTTP {scan_resp.status_code}: {scan_resp.text[:300]}", False, scan_resp.status_code, "mobsf_scan_starting")
                stages.append("mobsf_scanning")
                raw_result = scan_resp.json()
                if not self.looks_like_report(raw_result):
                    # 扫描请求成功不代表报告已生成；异步模式下需轮询 report_json
                    deadline = time.monotonic() + self.scan_timeout
                    polled = await self._poll_report(client, headers, scan_hash, deadline)
                    if polled is None:
                        raise AdapterError("PROVIDER_SCAN_TIMEOUT", "MobSF 扫描超时，报告未生成",
                                           f"report_json not ready after {self.scan_timeout}s", True,
                                           scan_resp.status_code, "mobsf_collecting")
                    raw_result = polled
                stages.append("mobsf_collecting")
                if not raw_result:
                    raise AdapterError("EMPTY_RESULT", "MobSF 返回空扫描结果", "empty JSON response", False, scan_resp.status_code, "mobsf_collecting")

            raw_path = f"/tmp/mobsf_result_{ctx.task_id}.json"
            with open(raw_path, "w") as f:
                json.dump(raw_result, f, ensure_ascii=False, indent=2, default=str)
            raw_hash = hashlib.sha256(open(raw_path, "rb").read()).hexdigest()
            stages.append("mobsf_normalizing")
            events = self.normalize_events(raw_result)
            return AdapterResult(success=True, events=events, artifacts=[{"path": raw_path, "type": "engine_output"}], raw_output_path=raw_path, summary={"tracker_count": len(raw_result.get("trackers", {}).get("trackers", []))}, provider_scan_hash=scan_hash, stage_events=stages, normalized_event_count=len(events), raw_result_hash=raw_hash, raw_sections=split_sections(raw_result))
        except AdapterError as exc:
            logger.warning("MobSF execution failed: %s", exc.error_code)
            return AdapterResult(success=False, error=exc, stage_events=stages)
        except httpx.TimeoutException as exc:
            error = AdapterError("PROVIDER_SCAN_TIMEOUT", "MobSF 扫描超时", str(exc), True, None, stages[-1] if stages else "mobsf_scanning")
            return AdapterResult(success=False, error=error, stage_events=stages)
        except httpx.RequestError as exc:
            error = AdapterError("ENGINE_UNREACHABLE", "无法连接 MobSF 服务", str(exc), True, None, stages[-1] if stages else "mobsf_validating")
            return AdapterResult(success=False, error=error, stage_events=stages)
        except (json.JSONDecodeError, ValueError) as exc:
            error = AdapterError("RESULT_PARSE_FAILED", "MobSF 返回结果无法解析", str(exc), False, None, "mobsf_normalizing")
            return AdapterResult(success=False, error=error, stage_events=stages)
        except Exception as exc:
            logger.error("MobSF scan failed: %s", exc)
            error = AdapterError("SCAN_FAILED", "MobSF 扫描失败", str(exc), False, None, stages[-1] if stages else "mobsf_scanning")
            return AdapterResult(success=False, error=error, stage_events=stages)

    REPORT_MARKERS = ("app_name", "package_name", "title", "version", "md5")

    @classmethod
    def looks_like_report(cls, payload: Any) -> bool:
        """判断响应是否是完整报告；仅凭 HTTP 200 不代表扫描完成。"""
        if not isinstance(payload, dict) or not payload:
            return False
        return sum(1 for key in cls.REPORT_MARKERS if key in payload) >= 3

    async def _poll_report(self, client, headers, scan_hash: str, deadline: float) -> dict | None:
        """扫描未同步返回完整报告时，轮询 report_json 直到结果生成或超时。"""
        import asyncio
        while time.monotonic() < deadline:
            await asyncio.sleep(5)
            resp = await client.post(f"{self.mobsf_url}/api/v1/report_json",
                                     data={"hash": scan_hash}, headers=headers)
            if resp.status_code == 200:
                payload = resp.json()
                if self.looks_like_report(payload):
                    return payload
            elif resp.status_code in (401, 403):
                raise AdapterError("ENGINE_AUTH_FAILED", "MobSF API Key 验证失败",
                                   f"report_json HTTP {resp.status_code}", False,
                                   resp.status_code, "mobsf_collecting")
        return None

    @staticmethod
    def _url_value(entry: Any) -> str:
        if isinstance(entry, str):
            return entry.strip()
        if isinstance(entry, dict):
            value = entry.get("url")
            if isinstance(value, str):
                return value.strip()
            urls = entry.get("urls")
            if isinstance(urls, list) and urls:
                return str(urls[0]).strip()
        return ""

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
        
        # URL：MobSF 不同版本返回结构不同，可能是字符串或 {"urls": [...], "path": ...}
        urls = raw_result.get("urls", [])
        for url in urls[:100]:
            value = self._url_value(url)
            if not value:
                continue
            events.append({
                "event_type": "static_url",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "api": value[:480],
                "event_data": {"url": url}
            })
        
        # 权限、导出组件等安全观察
        permissions = raw_result.get("permissions") or {}
        for permission, detail in permissions.items():
            if isinstance(detail, dict) and detail.get("status") in ("dangerous", "warning"):
                events.append({"event_type": "security_observation", "data_type": "permission", "api": permission, "event_data": {"permission": permission, "detail": detail}})
        for component in raw_result.get("exported_activities", []) or []:
            # 部分 MobSF 版本该字段含空白或占位噪声，过滤掉避免污染事件流
            name = str(component).strip() if component else ""
            if len(name) < 3:
                continue
            events.append({"event_type": "security_observation", "data_type": "exported_component", "api": name[:480], "event_data": {"component": name}})

        return events

    def collect_artifacts(self) -> list[dict]:
        return self._artifacts
