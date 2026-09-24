"""任务引擎队列汇总：把 EngineExecution 记录聚合成队列视图。"""
from sqlalchemy.orm import Session

from app.models import EngineExecution
from app.services.engine_config import display_name

# 队列中视为"已结束"的状态
FINISHED_STATUSES = {"completed", "failed", "canceled"}


def get_task_engine_queue(db: Session, task_id: int) -> dict:
    """返回某任务的引擎执行队列：当前执行、等待、已完成和失败。"""
    rows = db.query(EngineExecution).filter(
        EngineExecution.task_id == task_id
    ).order_by(EngineExecution.id).all()

    items, current, waiting, completed, failed = [], None, [], [], []
    for idx, row in enumerate(rows, start=1):
        item = {
            "id": row.id,
            "engine_type": row.engine_type,
            "engine_name": display_name(db, row.engine_type),
            "status": row.status,
            "stage": row.stage,
            "stage_message": row.stage_message,
            "progress": row.progress,
            "error_code": row.error_code,
            "retryable": row.retryable,
            "position": idx,
            "started_at": str(row.started_at) if row.started_at else None,
            "completed_at": str(row.completed_at) if row.completed_at else None,
            "duration_ms": row.duration_ms,
            "error_message": row.error_message,
        }
        items.append(item)
        if row.status == "running":
            current = item
        elif row.status == "pending":
            waiting.append(item)
        elif row.status == "completed":
            completed.append(item)
        elif row.status in ("failed", "canceled"):
            failed.append(item)

    running_index = current["position"] if current else len(completed) + 1
    return {
        "items": items,
        "current": current,
        "waiting": waiting,
        "completed": completed,
        "failed": failed,
        "total": len(items),
        "finished": len(completed) + len(failed),
        "current_index": running_index,
    }
