"""检测任务路由"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.security import generate_uid
from app.models import (DetectionTask, SubTask, DetectionScenario, DetectionEvent,
                        Finding, Evidence, AppVersion, User, AgentNode)
from app.schemas import TaskCreate, ScenarioUpdate
from app.api.deps import get_current_user, require_permission, get_request_id
from app.tasks.orchestrator import TaskOrchestrator
from fastapi import Request
from datetime import datetime, timezone

router = APIRouter(prefix="/tasks", tags=["检测任务"])


@router.post("")
def create_task(req: TaskCreate, request: Request,
                user: User = Depends(require_permission("task:write")),
                db: Session = Depends(get_db)):
    version = db.query(AppVersion).get(req.app_version_id)
    if not version:
        raise HTTPException(status_code=404, detail="App版本不存在")
    
    app = version.app
    task = DetectionTask(
        task_code=generate_uid("task"),
        app_version_id=req.app_version_id,
        privacy_policy_id=req.privacy_policy_id,
        project_id=app.project_id,
        detection_type=req.detection_type,
        rule_pack_version=req.rule_pack_version,
        status="draft",
        config_json=req.config,
        created_by=user.id
    )
    db.add(task)
    db.commit()
    db.refresh(task)
    return {"code": 0, "request_id": get_request_id(request), "data": {
        "id": task.id, "task_code": task.task_code, "status": task.status
    }}


@router.get("")
def list_tasks(project_id: int = None, status: str = None,
               page: int = 1, page_size: int = 20,
               user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    q = db.query(DetectionTask)
    if project_id:
        q = q.filter(DetectionTask.project_id == project_id)
    if status:
        q = q.filter(DetectionTask.status == status)
    total = q.count()
    items = q.order_by(DetectionTask.created_at.desc()).offset((page-1)*page_size).limit(page_size).all()
    result = []
    for t in items:
        v = db.query(AppVersion).get(t.app_version_id)
        result.append({
            "id": t.id, "task_code": t.task_code, "status": t.status,
            "detection_type": t.detection_type, "rule_pack_version": t.rule_pack_version,
            "app_name": v.app.app_name if v else None,
            "version_name": v.version_name if v else None,
            "created_at": str(t.created_at),
            "started_at": str(t.started_at) if t.started_at else None,
            "completed_at": str(t.completed_at) if t.completed_at else None
        })
    return {"code": 0, "data": {"items": result, "total": total, "page": page, "page_size": page_size}}


@router.get("/{tid}")
def get_task(tid: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    t = db.query(DetectionTask).get(tid)
    if not t:
        raise HTTPException(status_code=404, detail="任务不存在")
    v = db.query(AppVersion).get(t.app_version_id)
    sub_tasks = db.query(SubTask).filter(SubTask.task_id == tid).all()
    scenarios = db.query(DetectionScenario).filter(DetectionScenario.task_id == tid).all()
    event_count = db.query(DetectionEvent).filter(DetectionEvent.task_id == tid).count()
    finding_count = db.query(Finding).filter(Finding.task_id == tid).count()
    
    return {"code": 0, "data": {
        "id": t.id, "task_code": t.task_code, "status": t.status,
        "detection_type": t.detection_type, "rule_pack_version": t.rule_pack_version,
        "config_json": t.config_json, "priority": t.priority,
        "started_at": str(t.started_at) if t.started_at else None,
        "completed_at": str(t.completed_at) if t.completed_at else None,
        "failed_reason": t.failed_reason,
        "app": {"name": v.app.app_name, "package_name": v.app.package_name} if v else None,
        "version": {"version_name": v.version_name, "version_code": v.version_code,
                     "sha256": v.sha256[:16], "file_size": v.file_size,
                     "min_sdk": v.min_sdk, "target_sdk": v.target_sdk} if v else None,
        "sub_tasks": [{"id": s.id, "sub_task_code": s.sub_task_code,
                       "engine_type": s.engine_type, "stage": s.stage, "status": s.status,
                       "error_message": s.error_message} for s in sub_tasks],
        "scenarios": [{"id": s.id, "scenario_type": s.scenario_type,
                       "consent_status": s.consent_status, "status": s.status} for s in scenarios],
        "event_count": event_count, "finding_count": finding_count,
        "created_at": str(t.created_at)
    }}


@router.post("/{tid}/submit")
def submit_task(tid: int, request: Request,
                user: User = Depends(require_permission("task:submit")),
                db: Session = Depends(get_db)):
    t = db.query(DetectionTask).get(tid)
    if not t:
        raise HTTPException(status_code=404, detail="任务不存在")
    if t.status != "draft":
        raise HTTPException(status_code=400, detail="任务已提交")
    
    orchestrator = TaskOrchestrator(db)
    orchestrator.submit_task(t)
    
    return {"code": 0, "request_id": get_request_id(request),
            "data": {"id": t.id, "status": t.status}}


@router.post("/{tid}/cancel")
def cancel_task(tid: int, user: User = Depends(require_permission("task:write")),
                db: Session = Depends(get_db)):
    t = db.query(DetectionTask).get(tid)
    if not t:
        raise HTTPException(status_code=404, detail="任务不存在")
    if t.status in ["completed", "failed", "canceled"]:
        raise HTTPException(status_code=400, detail="任务已结束")
    t.status = "canceled"
    t.completed_at = datetime.now(timezone.utc)
    db.commit()
    return {"code": 0, "data": {"id": t.id, "status": t.status}}


@router.post("/{tid}/retry")
def retry_task(tid: int, user: User = Depends(require_permission("task:write")),
               db: Session = Depends(get_db)):
    t = db.query(DetectionTask).get(tid)
    if not t:
        raise HTTPException(status_code=404, detail="任务不存在")
    if t.status not in ["failed", "canceled"]:
        raise HTTPException(status_code=400, detail="任务状态不允许重试")
    t.status = "queued"
    t.failed_reason = None
    t.started_at = None
    t.completed_at = None
    db.commit()
    orchestrator = TaskOrchestrator(db)
    orchestrator.dispatch_task(t)
    return {"code": 0, "data": {"id": t.id, "status": t.status}}


@router.get("/{tid}/events")
def list_events(tid: int, event_type: str = None, scenario_id: int = None,
                data_type: str = None, page: int = 1, page_size: int = 50,
                user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    q = db.query(DetectionEvent).filter(DetectionEvent.task_id == tid)
    if event_type:
        q = q.filter(DetectionEvent.event_type == event_type)
    if scenario_id:
        q = q.filter(DetectionEvent.scenario_id == scenario_id)
    if data_type:
        q = q.filter(DetectionEvent.data_type == data_type)
    total = q.count()
    items = q.order_by(DetectionEvent.timestamp.asc()).offset((page-1)*page_size).limit(page_size).all()
    return {"code": 0, "data": {
        "items": [{
            "id": e.id, "event_uid": e.event_uid, "scenario_id": e.scenario_id,
            "event_type": e.event_type, "timestamp": str(e.timestamp),
            "consent_status": e.consent_status, "data_type": e.data_type,
            "api": e.api, "caller": e.caller, "trace_id": e.trace_id,
            "event_data": e.event_data
        } for e in items],
        "total": total, "page": page, "page_size": page_size
    }}


@router.get("/{tid}/scenarios")
def list_scenarios(tid: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    scenarios = db.query(DetectionScenario).filter(DetectionScenario.task_id == tid).all()
    return {"code": 0, "data": [
        {"id": s.id, "scenario_type": s.scenario_type, "consent_status": s.consent_status,
         "status": s.status, "started_at": str(s.started_at) if s.started_at else None,
         "completed_at": str(s.completed_at) if s.completed_at else None,
         "notes": s.notes} for s in scenarios
    ]}


@router.put("/{tid}/scenarios/{sid}")
def update_scenario(tid: int, sid: int, req: ScenarioUpdate,
                    user: User = Depends(require_permission("task:write")),
                    db: Session = Depends(get_db)):
    s = db.query(DetectionScenario).get(sid)
    if not s or s.task_id != tid:
        raise HTTPException(status_code=404, detail="场景不存在")
    if req.status: s.status = req.status
    if req.consent_status: s.consent_status = req.consent_status
    if req.notes is not None: s.notes = req.notes
    if req.operator_id: s.operator_id = req.operator_id
    if req.status == "running" and not s.started_at:
        s.started_at = datetime.now(timezone.utc)
    if req.status == "completed":
        s.completed_at = datetime.now(timezone.utc)
    db.commit()
    return {"code": 0, "data": {"id": s.id, "status": s.status}}


@router.get("/{tid}/findings")
def task_findings(tid: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    findings = db.query(Finding).filter(Finding.task_id == tid).all()
    return {"code": 0, "data": [
        {"id": f.id, "finding_uid": f.finding_uid, "title": f.title,
         "severity": f.severity, "status": f.status, "data_type": f.data_type,
         "created_at": str(f.created_at)} for f in findings
    ]}


@router.get("/{tid}/evidence")
def task_evidence(tid: int, evidence_type: str = None,
                  user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    q = db.query(Evidence).filter(Evidence.task_id == tid)
    if evidence_type:
        q = q.filter(Evidence.evidence_type == evidence_type)
    items = q.order_by(Evidence.created_at.desc()).all()
    return {"code": 0, "data": [
        {"id": e.id, "evidence_uid": e.evidence_uid, "evidence_type": e.evidence_type,
         "artifact_hash": e.artifact_hash[:16] if e.artifact_hash else None,
         "artifact_size": e.artifact_size,
         "metadata_json": e.metadata_json, "created_at": str(e.created_at)} for e in items
    ]}
