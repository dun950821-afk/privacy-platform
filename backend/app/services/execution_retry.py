"""引擎级重试策略和 attempt 创建。"""
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models import EngineExecution

RETRYABLE_TERMINAL = {"failed", "timed_out", "canceled"}


def can_retry_execution(execution) -> bool:
    return execution.status in RETRYABLE_TERMINAL and bool(execution.retryable)


def create_retry_attempt(db: Session, execution: EngineExecution, engine_name: str, engine_version: str | None = None) -> EngineExecution:
    """为一次失败执行创建新的 attempt，保留历史记录。"""
    root_id = execution.root_execution_id or execution.id
    db.query(EngineExecution).filter(
        EngineExecution.root_execution_id == root_id
    ).update({"is_latest": False}, synchronize_session=False)
    attempt = EngineExecution(
        task_id=execution.task_id,
        sub_task_id=execution.sub_task_id,
        engine_type=execution.engine_type,
        engine_name=engine_name,
        engine_version=engine_version or execution.engine_version,
        status="queued",
        stage="queued",
        queued_at=datetime.now(timezone.utc),
        attempt_no=(execution.attempt_no or 1) + 1,
        root_execution_id=root_id,
        parent_execution_id=execution.id,
        is_latest=True,
        execution_fingerprint=execution.execution_fingerprint,
        cache_scope=execution.cache_scope,
    )
    db.add(attempt)
    db.commit()
    db.refresh(attempt)
    return attempt
