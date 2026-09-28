from app.services.finding_service import compute_finding_uid, generate_findings
from app.services.rule_seed import BUILTIN_CORRELATION_RULES
from app.models import EngineObservation, DetectionTask, SubTask, EngineExecution, PlatformFinding
from app.core.security import generate_uid
from sqlalchemy import text

# 这条用例验的是「关联规则产出的结论能否完整落库并可复现」，与具体哪条规则无关。
# 注入规则而不依赖库里的启用状态：内置的通讯录规则已停用（设计 §10），
# 若把它当作测试载体，规则一停用这条用例就会跟着失效。
LEGACY_CONTENT = next(r for r in BUILTIN_CORRELATION_RULES
                      if r["rule_key"] == "PRIVACY_CONTACTS_NETWORK")["content"]


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


def test_observations_produce_platform_finding(db, client, admin_headers, monkeypatch):
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

        from app.services import correlation
        monkeypatch.setattr(correlation, "load_active_rules", lambda session: [{
            "rule": type("R", (), {"id": 147, "rule_key": "PRIVACY_CONTACTS_NETWORK"})(),
            "version": type("V", (), {"version": "1.1"})(),
            "content": LEGACY_CONTENT,
        }])

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
        assert persisted.correlation_rule_id == "147"
        assert persisted.correlation_rule_version == "1.1"

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
