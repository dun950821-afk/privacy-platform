"""统一引擎执行上下文、结果和取消令牌。"""
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable


class CancelToken:
    def __init__(self, checker: Callable[[], bool] | None = None):
        self._checker = checker or (lambda: False)
        self._local = False

    def cancel(self) -> None:
        self._local = True

    def is_cancelled(self) -> bool:
        return self._local or bool(self._checker())


@dataclass
class EngineExecutionContext:
    task_id: int
    execution_id: int
    engine_type: str
    engine_version: str
    apk_path: str
    apk_sha256: str = ""
    rule_version: str = ""
    config: dict = field(default_factory=dict)
    work_dir: str = ""
    deadline: datetime | None = None
    cancel_token: CancelToken = field(default_factory=CancelToken)
    metadata: dict = field(default_factory=dict)

    def is_cancelled(self) -> bool:
        return self.cancel_token.is_cancelled()


@dataclass
class TaskContext:
    """兼容旧适配器的任务上下文。"""
    task_id: int
    apk_path: str
    package_name: str
    rule_pack_version: str
    config: dict = field(default_factory=dict)
    execution_id: int | None = None
    cancel_token: CancelToken = field(default_factory=CancelToken)
    work_dir: str = ""

    def is_cancelled(self) -> bool:
        return self.cancel_token.is_cancelled()


@dataclass
class AdapterResult:
    success: bool
    events: list[dict] = field(default_factory=list)
    artifacts: list[dict] = field(default_factory=list)
    raw_output_path: str | None = None
    error: Any = None
    summary: dict = field(default_factory=dict)
    provider_scan_id: str | None = None
    provider_scan_hash: str | None = None
    stage_events: list[str] = field(default_factory=list)
    normalized_event_count: int = 0
    raw_result_hash: str | None = None
    # 原始结果的逐段存档（见 app/services/raw_section_service.py）。
    # 适配器自己填：它才拿得到 raw dict——提取完事件后那份原始数据本来就被丢掉了，
    # 于是没提取的段落等于不存在（实测 Androguard 的 endpoints 含隐私政策 URL，整段丢）。
    raw_sections: list[dict] = field(default_factory=list)


class EngineAdapter:
    """兼容旧适配器的统一生命周期基类。"""

    def get_capabilities(self) -> list[str]:
        raise NotImplementedError

    def validate_environment(self) -> bool:
        return True

    async def validate(self, ctx: TaskContext) -> None:
        if not self.validate_environment():
            raise RuntimeError("运行环境不满足")

    async def prepare(self, ctx: TaskContext) -> None:
        pass

    async def execute(self, ctx: TaskContext) -> AdapterResult:
        raise NotImplementedError

    async def poll(self, ctx: TaskContext, provider_id: str) -> dict | None:
        return None

    async def collect(self, ctx: TaskContext, provider_id: str) -> Any:
        return None

    def normalize_events(self, raw_result: Any) -> list[dict]:
        return []

    async def normalize(self, raw_result: Any, ctx: TaskContext) -> list[dict]:
        return self.normalize_events(raw_result)

    def collect_artifacts(self) -> list[dict]:
        return []

    async def cleanup(self, ctx: TaskContext | None = None) -> None:
        pass

    async def cancel(self, ctx: TaskContext | None = None, provider_id: str | None = None) -> bool:
        return True
