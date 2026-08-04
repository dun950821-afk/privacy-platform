"""报告路由"""
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.config import settings
from app.models import DetectionTask, Finding, DetectionEvent, Evidence, User, AppVersion
from app.api.deps import get_current_user, require_permission, get_request_id
from app.services.report_service import ReportService
from fastapi import Request
from pathlib import Path
from datetime import datetime, timezone
import json

router = APIRouter(prefix="/reports", tags=["报告管理"])


def _latest_report_file(task_id: int) -> Path | None:
    """查找任务最新的报告文件"""
    report_dir = Path(settings.STORAGE_ROOT) / f"task_{task_id}" / "reports"
    if not report_dir.is_dir():
        return None
    files = sorted(report_dir.glob("report_*.json"), key=lambda p: p.stat().st_mtime)
    return files[-1] if files else None


@router.get("")
def list_reports(page: int = 1, page_size: int = 20,
                 user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """报告列表: 已生成报告的任务"""
    page_size = min(max(page_size, 1), 100)
    tasks = db.query(DetectionTask).order_by(DetectionTask.created_at.desc()).all()
    items = []
    for t in tasks:
        report_file = _latest_report_file(t.id)
        if not report_file:
            continue
        v = db.query(AppVersion).get(t.app_version_id)
        summary = {}
        try:
            summary = json.loads(report_file.read_text(encoding="utf-8")).get("summary", {})
        except Exception:
            pass
        items.append({
            "task_id": t.id, "task_code": t.task_code, "status": t.status,
            "detection_type": t.detection_type,
            "app_name": v.app.app_name if v else None,
            "package_name": v.app.package_name if v else None,
            "version_name": v.version_name if v else None,
            "finding_count": summary.get("total_findings"),
            "severity_distribution": summary.get("severity_distribution", {}),
            "generated_at": str(datetime.fromtimestamp(
                report_file.stat().st_mtime, tz=timezone.utc)),
        })
    total = len(items)
    start = (page - 1) * page_size
    return {"code": 0, "data": {
        "items": items[start:start + page_size],
        "total": total, "page": page, "page_size": page_size,
    }}


@router.get("/{tid}/download")
def download_report(tid: int, user: User = Depends(get_current_user),
                    db: Session = Depends(get_db)):
    """下载任务最新的报告文件"""
    task = db.query(DetectionTask).get(tid)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    report_file = _latest_report_file(tid)
    if not report_file:
        raise HTTPException(status_code=404, detail="报告尚未生成")
    return FileResponse(
        path=str(report_file), filename=report_file.name,
        media_type="application/json"
    )


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
