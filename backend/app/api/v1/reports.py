"""报告路由"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.models import DetectionTask, Finding, DetectionEvent, Evidence, User, AppVersion
from app.api.deps import get_current_user, require_permission, get_request_id
from app.services.report_service import ReportService
from fastapi import Request

router = APIRouter(prefix="/reports", tags=["报告管理"])


@router.post("/{tid}/generate")
def generate_report(tid: int, request: Request,
                     user: User = Depends(require_permission("report:generate")),
                     db: Session = Depends(get_db)):
    task = db.query(DetectionTask).get(tid)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    service = ReportService(db)
    result = service.generate(task)
    return {"code": 0, "request_id": get_request_id(request), "data": result}


@router.get("/{tid}")
def get_report(tid: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    task = db.query(DetectionTask).get(tid)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    findings = db.query(Finding).filter(Finding.task_id == tid).all()
    events = db.query(DetectionEvent).filter(DetectionEvent.task_id == tid).count()
    evidence = db.query(Evidence).filter(Evidence.task_id == tid).count()
    
    severity_count = {}
    for f in findings:
        severity_count[f.severity] = severity_count.get(f.severity, 0) + 1
    
    version = db.query(AppVersion).get(task.app_version_id)
    
    return {"code": 0, "data": {
        "task": {"id": task.id, "task_code": task.task_code, "status": task.status,
                 "detection_type": task.detection_type,
                 "created_at": str(task.created_at),
                 "completed_at": str(task.completed_at) if task.completed_at else None},
        "app": {"name": version.app.app_name, "package_name": version.app.package_name} if version else None,
        "version": {"version_name": version.version_name, "version_code": version.version_code} if version else None,
        "summary": {
            "event_count": events, "evidence_count": evidence,
            "finding_count": len(findings),
            "severity_distribution": severity_count
        },
        "findings": [{"id": f.id, "title": f.title, "severity": f.severity,
                       "status": f.status, "data_type": f.data_type} for f in findings]
    }}
