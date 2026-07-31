"""引擎适配器抽象基类"""
from abc import ABC, abstractmethod
from typing import Any
from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass
class TaskContext:
    """任务上下文"""
    task_id: int
    apk_path: str
    package_name: str
    rule_pack_version: str
    config: dict = field(default_factory=dict)


@dataclass
class AdapterResult:
    """适配器执行结果"""
    success: bool
    events: list[dict] = field(default_factory=list)
    artifacts: list[dict] = field(default_factory=list)
    raw_output_path: str = None
    error: str = None
    summary: dict = field(default_factory=dict)


class EngineAdapter(ABC):
    """引擎适配器抽象基类"""

    @abstractmethod
    def get_capabilities(self) -> list[str]:
        """声明适配器能力标签"""
        pass

    @abstractmethod
    def validate_environment(self) -> bool:
        """校验运行环境"""
        pass

    @abstractmethod
    async def prepare(self, ctx: TaskContext) -> None:
        """准备阶段"""
        pass

    @abstractmethod
    async def execute(self, ctx: TaskContext) -> AdapterResult:
        """执行检测"""
        pass

    @abstractmethod
    def normalize_events(self, raw_result: Any) -> list[dict]:
        """将原始结果标准化为统一事件"""
        pass

    @abstractmethod
    def collect_artifacts(self) -> list[dict]:
        """收集产出物引用"""
        pass

    async def cleanup(self):
        """清理临时文件"""
        pass

    async def cancel(self):
        """取消执行"""
        pass
