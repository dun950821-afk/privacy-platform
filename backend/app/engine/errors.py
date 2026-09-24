"""引擎执行结构化错误和重试策略。"""
from dataclasses import dataclass, field


ERROR_CODES = {
    "ENGINE_ENV_INVALID", "ENGINE_NOT_INSTALLED", "ENGINE_CONFIG_INVALID",
    "ENGINE_UNREACHABLE", "ENGINE_AUTH_FAILED", "ENGINE_PERMISSION_DENIED",
    "FILE_NOT_FOUND", "FILE_INVALID", "FILE_TOO_LARGE", "FILE_UNREADABLE",
    "APK_PARSE_FAILED", "UPLOAD_FAILED", "SCAN_START_FAILED",
    "ENGINE_PROCESS_CRASHED", "SCAN_FAILED", "EMPTY_RESULT", "RESULT_PARSE_FAILED",
    "NORMALIZE_FAILED", "STAGE_TIMEOUT", "ENGINE_TIMEOUT", "TASK_TIMEOUT",
    "PROVIDER_SCAN_TIMEOUT", "TASK_CANCELED", "CANCEL_FAILED",
}


@dataclass
class AdapterError(Exception):
    error_code: str
    user_message: str
    debug_message: str = ""
    retryable: bool = False
    provider_status: int | None = None
    stage: str | None = None
    details: dict = field(default_factory=dict)

    def __post_init__(self):
        super().__init__(self.user_message)
        if self.error_code not in ERROR_CODES:
            raise ValueError(f"未知引擎错误码: {self.error_code}")

    def as_dict(self) -> dict:
        return {
            "error_code": self.error_code,
            "user_message": self.user_message,
            "debug_message": self.debug_message,
            "retryable": self.retryable,
            "provider_status": self.provider_status,
            "stage": self.stage,
            "details": self.details,
        }


def should_retry(error_code: str, engine_type: str, stage: str | None, attempt_no: int, max_attempts: int) -> bool:
    if attempt_no >= max_attempts:
        return False
    if error_code in {"ENGINE_AUTH_FAILED", "ENGINE_CONFIG_INVALID", "FILE_INVALID", "FILE_TOO_LARGE", "RESULT_PARSE_FAILED", "NORMALIZE_FAILED", "TASK_CANCELED"}:
        return False
    if engine_type == "appshark" and error_code in {"ENGINE_TIMEOUT", "STAGE_TIMEOUT"}:
        return False
    return error_code in {"ENGINE_UNREACHABLE", "UPLOAD_FAILED", "SCAN_START_FAILED", "ENGINE_PROCESS_CRASHED", "PROVIDER_SCAN_TIMEOUT", "SCAN_FAILED", "STAGE_TIMEOUT", "ENGINE_TIMEOUT"}
