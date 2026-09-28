"""SDK 识别聚合的幂等性。

线上故障（2026-09-28）：某 App 的三方包**一个都没命中知识库指纹**，于是分析结果是
「0 条命中 + 4 个未识别包簇」。而「已分析过」的判据当时只看命中数，于是：

  第二次读取 → 判据为假 → 不认为分析过 → 也不清理旧结果 → 再次插入同样的 4 个包簇
             → 唯一约束 (scan_job_id, package_prefix) 冲突 → 接口 500

且**每次都这样**：一旦进入「0 命中」状态，该任务的 SDK 识别页永久 500。本文件锁住这个场景。
"""
from datetime import datetime, timezone

import pytest

from app.core.security import generate_uid
from app.models import DetectionEvent, DetectionTask, EngineExecution, SubTask
from app.services.sdk_analysis import analyze_task


@pytest.fixture
def task_with_unmatched_components(db):
    """建一个只含「不命中任何指纹」的组件事件的任务，跑完清理干净。"""
    from sqlalchemy import text

    row = db.execute(text(
        "select v.id as version_id, a.project_id as project_id from app_versions v "
        "join app_assets a on a.id = v.app_id order by v.id limit 1")).first()
    task = DetectionTask(task_code=generate_uid("test"), app_version_id=row.version_id,
                         project_id=row.project_id, detection_type="static_only",
                         status="completed")
    db.add(task)
    db.flush()
    sub = SubTask(sub_task_code=generate_uid("st"), task_id=task.id,
                  engine_type="static", status="completed")
    db.add(sub)
    db.flush()
    execution = EngineExecution(task_id=task.id, sub_task_id=sub.id, engine_type="androguard",
                                engine_name="Androguard", status="completed", attempt_no=1)
    db.add(execution)
    db.flush()
    # nolint: 这些类名不会命中任何指纹（知识库按 fingerprint 匹配），但都能形成包簇前缀
    for class_name in ("com.example.unmatched.a.A", "com.example.unmatched.a.B",
                       "com.example.unmatched.b.C"):
        db.add(DetectionEvent(event_uid=generate_uid("evt"), task_id=task.id,
                              event_type="static_component", timestamp=datetime.now(timezone.utc),
                              data_type="ACTIVITY", api=class_name,
                              event_data={"component": class_name},
                              engine_name="Androguard", engine_version="4.1.4"))
    db.commit()
    try:
        yield task
    finally:
        db.rollback()
        tid = task.id
        # app_build 以 build_key="task:{id}" 标识，没有 task_id 列
        build_key = "task:%d" % tid
        db.execute(text("delete from privacy_scan.component_hit where scan_job_id in "
                        "(select j.id from privacy_scan.scan_job j join privacy_scan.app_build b on b.id=j.app_build_id "
                        " where b.build_key=:k)"), {"k": build_key})
        db.execute(text("delete from privacy_scan.package_cluster where scan_job_id in "
                        "(select j.id from privacy_scan.scan_job j join privacy_scan.app_build b on b.id=j.app_build_id "
                        " where b.build_key=:k)"), {"k": build_key})
        db.execute(text("delete from privacy_scan.scan_job where app_build_id in "
                        "(select id from privacy_scan.app_build where build_key=:k)"), {"k": build_key})
        db.execute(text("delete from privacy_scan.app_build where build_key=:k"), {"k": build_key})
        db.execute(text("delete from detection_events where task_id=:t"), {"t": tid})
        db.execute(text("delete from engine_executions where task_id=:t"), {"t": tid})
        db.execute(text("delete from sub_tasks where task_id=:t"), {"t": tid})
        db.execute(text("delete from detection_tasks where id=:t"), {"t": tid})
        db.commit()


def _cluster_count(db, job_id):
    from sqlalchemy import text
    return db.execute(text("select count(*) from privacy_scan.package_cluster where scan_job_id=:j"),
                      {"j": job_id}).scalar()


def _hit_count(db, job_id):
    from sqlalchemy import text
    return db.execute(text("select count(*) from privacy_scan.component_hit where scan_job_id=:j"),
                      {"j": job_id}).scalar()


def test_repeated_analysis_with_zero_hits_is_idempotent(db, task_with_unmatched_components):
    """0 命中也算「分析过了」——重复读取不得再插一遍包簇。

    这正是线上 500 的成因：判据只看命中数，0 命中时判定为「没分析过」，
    却又跳过了清理，于是每次都在已有包簇上再插一次。
    """
    job = analyze_task(db, task_with_unmatched_components)
    assert _hit_count(db, job.id) == 0, "本用例前提：没有任何指纹命中"
    first = _cluster_count(db, job.id)
    assert first > 0, "本用例前提：未命中的组件应形成包簇"

    # 第二次分析不得抛唯一约束冲突，且结果数量不变
    analyze_task(db, task_with_unmatched_components)
    assert _cluster_count(db, job.id) == first


def test_refresh_with_zero_hits_recomputes_cleanly(db, task_with_unmatched_components):
    """显式 refresh 时走清空重算路径，同样不得残留或冲突。"""
    job = analyze_task(db, task_with_unmatched_components)
    first = _cluster_count(db, job.id)

    analyze_task(db, task_with_unmatched_components, refresh=True)
    assert _cluster_count(db, job.id) == first
