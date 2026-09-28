from app.services.finding_service import compute_finding_uid, generate_findings
from app.services.rule_seed import seed_correlation_rules
from app.models import EngineObservation, DetectionTask, SubTask, EngineExecution, PlatformFinding
from app.core.security import generate_uid
from sqlalchemy import text


def _purge_task(db, task_id):
    """清理测试任务的全部痕迹；断言失败也必须走到这里，否则会污染业务库。"""
    db.rollback()
    db.execute(text("delete from finding_observations where finding_id in (select id from platform_findings where task_id=:t)"), {"t": task_id})
    db.execute(text("delete from platform_findings where task_id=:t"), {"t": task_id})
    db.execute(text("delete from engine_observations where task_id=:t"), {"t": task_id})
    db.execute(text("delete from engine_executions where task_id=:t"), {"t": task_id})
    db.execute(text("delete from sub_tasks where task_id=:t"), {"t": task_id})
    db.execute(text("delete from detection_tasks where id=:t"), {"t": task_id})
    db.commit()


def test_observations_produce_platform_finding(db, client, admin_headers):
    row = db.execute(text(
        "select v.id as version_id, a.project_id as project_id from app_versions v "
        "join app_assets a on a.id = v.app_id order by v.id limit 1")).first()
    task = DetectionTask(task_code=generate_uid("test"), app_version_id=row.version_id,
                         project_id=row.project_id, detection_type="static_only", status="running_static")
    db.add(task)
    db.flush()
    task_id = task.id
    try:
        sub = SubTask(sub_task_code=generate_uid("st"), task_id=task.id, engine_type="static", status="running")
        db.add(sub)
        db.flush()
        execution = EngineExecution(task_id=task.id, sub_task_id=sub.id, engine_type="appshark",
                                    engine_name="AppShark", status="completed", attempt_no=1)
        db.add(execution)
        db.flush()
        # 观察对象形状取自真实引擎产物（端到端任务 465）
        db.add(EngineObservation(task_id=task.id, execution_id=execution.id, engine_type="androguard",
                                 observation_type="fact.sensitive_permission", subject="READ_CONTACTS",
                                 payload={"api": "READ_CONTACTS", "category": "CONTACTS",
                                          "permission": "READ_CONTACTS"}, evidence_level="observed"))
        db.add(EngineObservation(task_id=task.id, execution_id=execution.id, engine_type="appshark",
                                 observation_type="dataflow.privacy",
                                 subject="['<com.baidu.mobstat.ba: java.net.HttpURLConnection a(android.content.Context,java.lang.String,int,int)>->$r0']",
                                 payload={"section": "ComplianceInfo", "rule": "DeviceId_NetworkTransfer",
                                          "level": "L3",
                                          "sink": ["<com.baidu.mobstat.ba: java.net.HttpURLConnection a(android.content.Context,java.lang.String,int,int)>->$r0"]},
                                 evidence_level="potential"))
        db.commit()
        seed_correlation_rules(db)

        # 内置规则的内容来自库中启用版本（可能已被维护者升级），断言与之保持一致而非硬编码版本号
        active_version = db.execute(text(
            "select v.version from rules r join rule_versions v on v.id = r.current_version_id "
            "where r.rule_key = 'PRIVACY_CONTACTS_NETWORK'")).scalar()

        findings = generate_findings(db, task.id)
        assert len(findings) == 1
        assert findings[0].finding_code == "PRIVACY_CONTACTS_NETWORK"
        assert findings[0].observation_count == 2

        # 规则溯源字段必须真正落库：重新查询而不读内存对象
        db.expire_all()
        persisted = db.query(PlatformFinding).filter(PlatformFinding.task_id == task.id).one()
        assert isinstance(persisted.finding_uid, str) and len(persisted.finding_uid) == 64
        assert all(c in "0123456789abcdef" for c in persisted.finding_uid)
        assert persisted.finding_uid == compute_finding_uid(persisted.finding_code, persisted.dedup_key)
        assert isinstance(persisted.rule_snapshot, dict) and persisted.rule_snapshot
        assert persisted.rule_snapshot["produce"]["finding_code"] == persisted.finding_code
        assert persisted.correlation_rule_id
        assert persisted.correlation_rule_version == active_version

        # 重复生成不应产生重复 Finding
        assert len(generate_findings(db, task.id)) == 1

        # 接口必须暴露可复现字段，否则「历史结论可复现」在 API 上不可观测
        resp = client.get(f"/api/v1/tasks/{task.id}/platform-findings", headers=admin_headers)
        assert resp.status_code == 200
        items = resp.json()["data"]["items"]
        assert len(items) == 1
        assert items[0]["finding_uid"] == persisted.finding_uid
        assert items[0]["rule_snapshot"] == persisted.rule_snapshot
        assert items[0]["rule_snapshot"]["produce"]["finding_code"] == "PRIVACY_CONTACTS_NETWORK"
    finally:
        _purge_task(db, task_id)
