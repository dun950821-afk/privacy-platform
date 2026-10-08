"""worker 记录失败时，不能把原始错误变形成 PendingRollbackError。

## 实测链路（/tmp/privacy-worker.log 2026-09-28 + 那条 PendingRollbackError）

1. 另一个进程删掉了任务行 —— API 的 `POST /tasks/{id}/retry` 就是这么干的：
   `db.query(EngineExecution).filter(...).delete(synchronize_session=False)`
   **不告诉 session**；删任务本身还会级联到 engine_executions / detection_events。
2. worker 手里的 ORM 对象成了僵尸。下一次 flush 试图 UPDATE 它、影响 0 行
   → **`StaleDataError`**（"expected to update 1 row(s); 0 were matched"）。
   注：日志里那句「has been deleted, or its row is otherwise not present」是
   `ObjectDeletedError`，出现在**过期对象被 refresh** 时——同一场景的另一种表现。
3. **session 就此进入「需要 rollback」状态**
4. worker 的错误路径**没有 rollback 就直接 commit()**
   → 抛 `PendingRollbackError`，其 `Original exception` 才是真正的那个错误

后果有两层：错误记录（`status=failed` / `failed_reason`）**写不进去**；
且日志被一个二阶错误掩盖，看起来像 worker 自己崩了。

本文件不用 conftest 的 `execution` fixture：它会 `db.rollback()` 后接着用同一个
session，在「行已被删」的场景里 teardown 自己就会抛 ObjectDeletedError，
把测试结果弄脏。这里自带 fixture，清理一律走**新 session**。
"""
import pytest
from sqlalchemy import text
from sqlalchemy.exc import PendingRollbackError
from sqlalchemy.orm.exc import StaleDataError

from app.core.database import SessionLocal
from app.engine.worker import EngineWorker
from app.core.security import generate_uid
from app.models import DetectionTask


def _row_exists(task_id: int) -> bool:
    """用独立 session 查行是否还在（不受测试里那个被污染的 session 影响）。"""
    s = SessionLocal()
    try:
        return bool(s.execute(text("select 1 from detection_tasks where id = :i"),
                              {"i": task_id}).first())
    finally:
        s.close()


def _delete_task_row(task_id: int) -> None:
    """用**另一个 session**删掉任务行，模拟并发删除。"""
    s = SessionLocal()
    try:
        s.execute(text("delete from detection_tasks where id = :i"), {"i": task_id})
        s.commit()
    finally:
        s.close()


@pytest.fixture
def task(db):
    """建一个临时任务；清理走新 session，避免被测试里被污染的 session 拖累。"""
    from sqlalchemy import text as _text
    row = db.execute(_text(
        "select v.id as version_id, a.project_id as project_id from app_versions v "
        "join app_assets a on a.id = v.app_id order by v.id limit 1")).first()
    t = DetectionTask(task_code=generate_uid("test"), app_version_id=row.version_id,
                      project_id=row.project_id, detection_type="static_only",
                      status="queued")
    db.add(t)
    db.commit()
    task_id = t.id
    try:
        yield t
    finally:
        s = SessionLocal()
        try:
            s.execute(_text("delete from detection_tasks where id = :i"), {"i": task_id})
            s.commit()
        finally:
            s.close()


def test_fail_task_does_not_masquerade_as_pending_rollback(db, task):
    """行被并发删除后，_fail_task 不应抛 PendingRollbackError。"""
    worker = EngineWorker(worker_id="test-worker")
    task_id = task.id
    _delete_task_row(task_id)

    # 第一步：让 session 真的经历一次「行已不存在」的 flush 失败——这正是 worker
    # 在引擎执行中途会遇到的第一次失败。
    task.status = "failed"
    with pytest.raises(StaleDataError):
        db.flush()

    # 第二步：错误路径记录失败。今天的实现在这里抛 PendingRollbackError，
    # 于是失败记录写不进去、原始错误被掩盖。
    worker._fail_task(db, task, "并发删除后的失败记录")


def test_fail_task_is_safe_when_the_row_is_already_gone(db, task):
    """行已经不存在时也不应崩——没有记录可写，跳过即可。"""
    worker = EngineWorker(worker_id="test-worker")
    task_id = task.id
    _delete_task_row(task_id)

    worker._fail_task(db, task, "行已不存在")

    # 没有复活一行：跳过就是跳过
    assert not _row_exists(task_id)
