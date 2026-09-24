from app.services.finding_service import generate_findings
from app.models import EngineObservation, DetectionTask, SubTask, EngineExecution
from app.core.security import generate_uid
from sqlalchemy import text


def test_observations_produce_platform_finding(db):
    row = db.execute(text(
        "select v.id as version_id, a.project_id as project_id from app_versions v "
        "join app_assets a on a.id = v.app_id order by v.id limit 1")).first()
    task = DetectionTask(task_code=generate_uid("test"), app_version_id=row.version_id,
                         project_id=row.project_id, detection_type="static_only", status="running_static")
    db.add(task)
    db.flush()
    sub = SubTask(sub_task_code=generate_uid("st"), task_id=task.id, engine_type="static", status="running")
    db.add(sub)
    db.flush()
    execution = EngineExecution(task_id=task.id, sub_task_id=sub.id, engine_type="appshark",
                                engine_name="AppShark", status="completed", attempt_no=1)
    db.add(execution)
    db.flush()
    db.add(EngineObservation(task_id=task.id, execution_id=execution.id, engine_type="androguard",
                             observation_type="fact.permission", subject="android.permission.READ_CONTACTS",
                             payload={}, evidence_level="observed"))
    db.add(EngineObservation(task_id=task.id, execution_id=execution.id, engine_type="appshark",
                             observation_type="dataflow.privacy", subject="Contacts",
                             payload={"sink": {"category": "network"}}, evidence_level="potential"))
    db.commit()

    findings = generate_findings(db, task.id)
    assert len(findings) == 1
    assert findings[0].finding_code == "PRIVACY_CONTACTS_NETWORK"
    assert findings[0].observation_count == 2

    # 重复生成不应产生重复 Finding
    assert len(generate_findings(db, task.id)) == 1

    db.execute(text("delete from finding_observations where finding_id in (select id from platform_findings where task_id=:t)"), {"t": task.id})
    db.execute(text("delete from platform_findings where task_id=:t"), {"t": task.id})
    db.execute(text("delete from engine_observations where task_id=:t"), {"t": task.id})
    db.execute(text("delete from engine_executions where task_id=:t"), {"t": task.id})
    db.execute(text("delete from sub_tasks where task_id=:t"), {"t": task.id})
    db.execute(text("delete from detection_tasks where id=:t"), {"t": task.id})
    db.commit()
