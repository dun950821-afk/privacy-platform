"""EngineExecution 租约、CAS 和动态取消仓储。"""
from datetime import datetime, timedelta, timezone
from dataclasses import dataclass
import secrets

from sqlalchemy.orm import Session

from app.models import EngineExecution

TERMINAL = {"completed", "failed", "timed_out", "canceled", "skipped"}
TRANSITIONS = {
    "queued": {"preparing", "canceling", "failed", "skipped"},
    "preparing": {"validating", "running", "canceling", "failed", "timed_out"},
    "validating": {"running", "canceling", "failed", "timed_out"},
    "running": {"collecting", "normalizing", "canceling", "failed", "timed_out"},
    "collecting": {"normalizing", "canceling", "failed", "timed_out"},
    "normalizing": {"completed", "failed", "canceling", "timed_out"},
    "canceling": {"canceled", "failed"},
}


@dataclass
class Lease:
    lease_token: str
    state_version: int
    worker_id: str


def claim_execution(db: Session, execution_id: int, worker_id: str, lease_seconds: int = 60) -> Lease | None:
    now = datetime.now(timezone.utc)
    row = db.query(EngineExecution).filter(EngineExecution.id == execution_id).with_for_update().first()
    if not row or row.status in TERMINAL:
        return None
    if row.lease_expires_at and row.lease_expires_at > now and row.worker_id != worker_id:
        return None
    token = secrets.token_urlsafe(32)
    row.worker_id = worker_id
    row.lease_token = token
    row.lease_expires_at = now + timedelta(seconds=lease_seconds)
    row.heartbeat_at = now
    row.state_version = (row.state_version or 0) + 1
    db.commit()
    return Lease(token, row.state_version, worker_id)


def cas_update_execution(db: Session, execution_id: int, lease_token: str, expected_version: int, **fields) -> bool:
    row = db.query(EngineExecution).filter(
        EngineExecution.id == execution_id,
        EngineExecution.lease_token == lease_token,
        EngineExecution.state_version == expected_version,
        EngineExecution.lease_expires_at > datetime.now(timezone.utc),
    ).first()
    if not row:
        db.rollback()
        return False
    for key, value in fields.items():
        if not key.startswith("_"):
            setattr(row, key, value)
    row.state_version += 1
    db.commit()
    return True


def heartbeat_execution(db: Session, execution_id: int, lease_token: str, expected_version: int, lease_seconds: int = 60) -> int | None:
    now = datetime.now(timezone.utc)
    row = db.query(EngineExecution).filter(
        EngineExecution.id == execution_id,
        EngineExecution.lease_token == lease_token,
        EngineExecution.state_version == expected_version,
        EngineExecution.lease_expires_at > now,
    ).first()
    if not row:
        db.rollback()
        return None
    row.heartbeat_at = now
    row.lease_expires_at = now + timedelta(seconds=lease_seconds)
    row.state_version += 1
    db.commit()
    return row.state_version


def request_cancel(db: Session, execution_id: int) -> bool:
    changed = db.query(EngineExecution).filter(EngineExecution.id == execution_id, ~EngineExecution.status.in_(TERMINAL)).update({"cancel_requested": True}, synchronize_session=False)
    db.commit()
    return bool(changed)


def is_cancel_requested(db: Session, execution_id: int) -> bool:
    row = db.query(EngineExecution.cancel_requested).filter(EngineExecution.id == execution_id).first()
    return bool(row and row[0])


def recover_expired_leases(db: Session, max_attempts: int = 4) -> list[int]:
    """回收租约过期的执行：可重试的回到 queued，否则标记崩溃失败。"""
    now = datetime.now(timezone.utc)
    rows = db.query(EngineExecution).filter(
        ~EngineExecution.status.in_(TERMINAL),
        EngineExecution.lease_expires_at.isnot(None),
        EngineExecution.lease_expires_at < now,
    ).all()
    from app.models import DetectionTask

    recovered = []
    task_ids = set()
    for row in rows:
        row.lease_token = None
        row.worker_id = None
        row.lease_expires_at = None
        if (row.attempt_no or 1) < max_attempts:
            row.status = "queued"
            row.stage = "queued"
            row.stage_message = "租约过期，等待重新执行"
            row.started_at = None
            recovered.append(row.id)
            task_ids.add(row.task_id)
        else:
            row.status = "failed"
            row.error_code = "ENGINE_PROCESS_CRASHED"
            row.error_message = "执行进程中断，重试次数已用尽"
            row.finished_at = now
            row.completed_at = now
            row.retryable = True
            task_ids.add(row.task_id)
    # 有执行被回收的任务需要重新排队，否则任务会永远停在 running_static
    for task_id in task_ids:
        task = db.query(DetectionTask).get(task_id)
        if task and task.status not in ("completed", "failed", "canceled", "timed_out"):
            task.status = "queued"
    db.commit()
    return recovered


def claim_queued_executions(db: Session, limit: int = 10) -> list[int]:
    """领取未被任何 Worker 持有的 queued 执行。"""
    rows = db.query(EngineExecution).filter(
        EngineExecution.status == "queued",
        EngineExecution.lease_token.is_(None),
    ).order_by(EngineExecution.id).limit(limit).all()
    return [row.id for row in rows]


def find_tasks_with_queued_executions(db: Session, limit: int = 5) -> list[int]:
    """数据库轮询：找出有待执行引擎且任务未结束的任务。

    Redis 只做调度通知；任务被回收后即使没有新的 Redis 消息也能继续执行。
    """
    from app.models import DetectionTask

    rows = db.query(EngineExecution.task_id).join(
        DetectionTask, DetectionTask.id == EngineExecution.task_id
    ).filter(
        EngineExecution.status == "queued",
        EngineExecution.lease_token.is_(None),
        DetectionTask.status == "queued",
    ).distinct().limit(limit).all()
    return [row[0] for row in rows]


def transition_execution(db: Session, execution_id: int, lease_token: str, expected_version: int, status: str, **fields) -> bool:
    row = db.query(EngineExecution).filter(EngineExecution.id == execution_id).first()
    if not row or status not in TRANSITIONS.get(row.status, set()):
        return False
    return cas_update_execution(db, execution_id, lease_token, expected_version, status=status, **fields)
