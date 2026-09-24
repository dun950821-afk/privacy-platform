import pytest
from datetime import datetime, timedelta, timezone

APK_PATH = "/home/user/privacy-platform/data/evidence/apks/base.apk"


@pytest.fixture(scope="module")
def sample_apk():
    return APK_PATH


@pytest.fixture
def db():
    from app.core.database import SessionLocal
    session = SessionLocal()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


@pytest.fixture
def execution(db):
    """创建一个临时 EngineExecution 用于租约测试，测试结束后回滚。"""
    from app.models import DetectionTask, EngineExecution, SubTask
    from app.core.security import generate_uid

    from sqlalchemy import text
    row = db.execute(text("select v.id as version_id, a.project_id as project_id from app_versions v join app_assets a on a.id = v.app_id order by v.id limit 1")).first()
    task = DetectionTask(task_code=generate_uid("test"), app_version_id=row.version_id,
                         project_id=row.project_id, detection_type="static_only", status="queued")
    db.add(task)
    db.flush()
    sub = SubTask(sub_task_code=generate_uid("st"), task_id=task.id, engine_type="static", status="pending")
    db.add(sub)
    db.flush()
    row = EngineExecution(
        task_id=task.id, sub_task_id=sub.id, engine_type="mobsf", engine_name="MobSF",
        engine_version="4.5.4", status="queued", stage="queued", attempt_no=1,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    try:
        yield row
    finally:
        # 测试数据不得留在业务库，否则 Worker 会把它们当成真实任务执行
        from sqlalchemy import text
        db.rollback()
        db.execute(text("delete from engine_observations where task_id = :tid"), {"tid": task.id})
        db.execute(text("delete from engine_artifacts where execution_id in (select id from engine_executions where task_id = :tid)"), {"tid": task.id})
        db.execute(text("delete from engine_executions where task_id = :tid"), {"tid": task.id})
        db.execute(text("delete from sub_tasks where task_id = :tid"), {"tid": task.id})
        db.execute(text("delete from detection_tasks where id = :tid"), {"tid": task.id})
        db.commit()


@pytest.fixture
def expire_lease():
    from datetime import datetime, timedelta, timezone

    def _expire(db, execution_id):
        from app.models import EngineExecution
        db.query(EngineExecution).filter(EngineExecution.id == execution_id).update(
            {"lease_expires_at": datetime.now(timezone.utc) - timedelta(seconds=5)}
        )
        db.commit()

    return _expire
