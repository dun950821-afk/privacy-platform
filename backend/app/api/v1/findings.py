"""问题路由"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.models import (Finding, FindingEvidence, FindingEvent, Evidence, DetectionEvent,
                        Remediation, RetestRecord, User, Rule, SDKKnowledge, DetectionScenario)
from app.schemas import FindingAssign, FindingClose, RemediationCreate
from app.api.deps import get_current_user, require_permission
from datetime import datetime, timezone

router = APIRouter(prefix="/findings", tags=["问题管理"])


@router.get("")
def list_findings(project_id: int = None, task_id: int = None, severity: str = None,
                  status: str = None, assigned_to: int = None,
                  page: int = 1, page_size: int = 20,
                  user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    q = db.query(Finding)
    if task_id:
        q = q.filter(Finding.task_id == task_id)
    if severity:
        q = q.filter(Finding.severity == severity)
    if status:
        q = q.filter(Finding.status == status)
    if assigned_to:
        q = q.filter(Finding.assigned_to == assigned_to)
    total = q.count()
    items = q.order_by(Finding.created_at.desc()).offset((page-1)*page_size).limit(page_size).all()
    result = []
    for f in items:
        task = f.task
        result.append({
            "id": f.id, "finding_uid": f.finding_uid, "title": f.title,
            "severity": f.severity, "status": f.status, "confidence": f.confidence,
            "data_type": f.data_type, "task_id": f.task_id,
            "task_code": task.task_code if task else None,
            "app_name": task.app_version.app.app_name if task else None,
            "assigned_to": f.assigned_to, "created_at": str(f.created_at)
        })
    return {"code": 0, "data": {"items": result, "total": total, "page": page, "page_size": page_size}}


@router.get("/{fid}")
def get_finding(fid: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    f = db.query(Finding).get(fid)
    if not f:
        raise HTTPException(status_code=404, detail="问题不存在")
    
    scenario = db.query(DetectionScenario).get(f.scenario_id) if f.scenario_id else None
    rule = db.query(Rule).get(f.rule_id) if f.rule_id else None
    sdk = db.query(SDKKnowledge).get(f.sdk_id) if f.sdk_id else None
    
    return {"code": 0, "data": {
        "id": f.id, "finding_uid": f.finding_uid, "title": f.title,
        "severity": f.severity, "status": f.status, "confidence": f.confidence,
        "description": f.description, "data_type": f.data_type,
        "network_domain": f.network_domain, "api_path": f.api_path,
        "remediation_advice": f.remediation_advice,
        "task_id": f.task_id, "scenario_id": f.scenario_id,
        "scenario": {"type": scenario.scenario_type, "consent_status": scenario.consent_status} if scenario else None,
        "rule": {"rule_key": rule.rule_key, "name": rule.name} if rule else None,
        "sdk": {"name": sdk.name, "vendor": sdk.vendor} if sdk else None,
        "assigned_to": f.assigned_to, "due_date": str(f.due_date) if f.due_date else None,
        "closed_reason": f.closed_reason,
        "created_at": str(f.created_at), "updated_at": str(f.updated_at)
    }}


@router.put("/{fid}")
def update_finding(fid: int, req: dict,
                   user: User = Depends(require_permission("finding:write")),
                   db: Session = Depends(get_db)):
    f = db.query(Finding).get(fid)
    if not f:
        raise HTTPException(status_code=404, detail="问题不存在")
    for field in ["title", "description", "severity", "remediation_advice"]:
        if field in req:
            setattr(f, field, req[field])
    db.commit()
    return {"code": 0, "data": {"id": f.id}}


@router.post("/{fid}/assign")
def assign_finding(fid: int, req: FindingAssign,
                   user: User = Depends(require_permission("finding:assign")),
                   db: Session = Depends(get_db)):
    f = db.query(Finding).get(fid)
    if not f:
        raise HTTPException(status_code=404, detail="问题不存在")
    f.assigned_to = req.assigned_to
    f.assigned_at = datetime.now(timezone.utc)
    f.due_date = req.due_date
    f.status = "assigned"
    db.commit()
    return {"code": 0, "data": {"id": f.id, "status": f.status}}


@router.post("/{fid}/close")
def close_finding(fid: int, req: FindingClose,
                  user: User = Depends(require_permission("finding:write")),
                  db: Session = Depends(get_db)):
    f = db.query(Finding).get(fid)
    if not f:
        raise HTTPException(status_code=404, detail="问题不存在")
    f.status = f"closed_{req.closed_reason}"
    f.closed_reason = req.closed_reason
    f.closed_by = user.id
    f.closed_at = datetime.now(timezone.utc)
    db.commit()
    return {"code": 0, "data": {"id": f.id, "status": f.status}}


@router.get("/{fid}/evidence")
def finding_evidence(fid: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    links = db.query(FindingEvidence).filter(FindingEvidence.finding_id == fid).all()
    result = []
    for link in links:
        e = db.query(Evidence).get(link.evidence_id)
        if e:
            result.append({
                "id": e.id, "evidence_uid": e.evidence_uid, "evidence_type": e.evidence_type,
                "artifact_hash": e.artifact_hash[:16] if e.artifact_hash else None,
                "metadata_json": e.metadata_json, "relation_type": link.relation_type,
                "created_at": str(e.created_at)
            })
    return {"code": 0, "data": result}


@router.get("/{fid}/events")
def finding_events(fid: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    links = db.query(FindingEvent).filter(FindingEvent.finding_id == fid).all()
    result = []
    for link in links:
        e = db.query(DetectionEvent).get(link.event_id)
        if e:
            result.append({
                "id": e.id, "event_uid": e.event_uid, "event_type": e.event_type,
                "timestamp": str(e.timestamp), "consent_status": e.consent_status,
                "data_type": e.data_type, "api": e.api, "caller": e.caller,
                "event_data": e.event_data
            })
    return {"code": 0, "data": result}


@router.get("/{fid}/remediations")
def list_remediations(fid: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    items = db.query(Remediation).filter(Remediation.finding_id == fid).all()
    return {"code": 0, "data": [
        {"id": r.id, "remediation_type": r.remediation_type, "description": r.description,
         "status": r.status, "submitted_by": r.submitted_by,
         "submitted_at": str(r.submitted_at)} for r in items
    ]}


@router.post("/{fid}/remediations")
def create_remediation(fid: int, req: RemediationCreate,
                       user: User = Depends(require_permission("finding:remediate")),
                       db: Session = Depends(get_db)):
    f = db.query(Finding).get(fid)
    if not f:
        raise HTTPException(status_code=404, detail="问题不存在")
    r = Remediation(
        finding_id=fid, remediation_type=req.remediation_type,
        description=req.description, fix_version_id=req.fix_version_id,
        submitted_by=user.id, status="pending_retest"
    )
    db.add(r)
    f.status = "ready_for_retest"
    db.commit()
    return {"code": 0, "data": {"id": r.id}}
