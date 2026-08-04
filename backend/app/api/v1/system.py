"""系统管理路由"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.security import hash_password
from app.models import User, AgentNode, Device, AuditLog, SysDict
from app.schemas import UserCreate, UserUpdate, DictCreate
from app.api.deps import get_current_user, require_permission

router = APIRouter(prefix="/system", tags=["系统管理"])


# --- Users ---
@router.get("/users")
def list_users(user: User = Depends(require_permission("system:user:read")),
               db: Session = Depends(get_db)):
    users = db.query(User).order_by(User.id).all()
    return {"code": 0, "data": [
        {"id": u.id, "username": u.username, "full_name": u.full_name,
         "email": u.email, "role": u.role, "status": u.status,
         "last_login_at": str(u.last_login_at) if u.last_login_at else None,
         "created_at": str(u.created_at) if u.created_at else None} for u in users
    ]}


@router.post("/users")
def create_user(req: UserCreate, user: User = Depends(require_permission("system:user:write")),
                db: Session = Depends(get_db)):
    existing = db.query(User).filter(User.username == req.username).first()
    if existing:
        raise HTTPException(status_code=409, detail="用户名已存在")
    u = User(username=req.username, password_hash=hash_password(req.password),
             full_name=req.full_name, email=req.email, phone=req.phone, role=req.role)
    db.add(u)
    db.commit()
    return {"code": 0, "data": {"id": u.id}}


@router.put("/users/{uid}")
def update_user(uid: int, req: UserUpdate,
                user: User = Depends(require_permission("system:user:write")),
                db: Session = Depends(get_db)):
    u = db.query(User).get(uid)
    if not u:
        raise HTTPException(status_code=404, detail="用户不存在")
    if req.full_name is not None: u.full_name = req.full_name
    if req.email is not None: u.email = req.email
    if req.phone is not None: u.phone = req.phone
    if req.role: u.role = req.role
    if req.status: u.status = req.status
    db.commit()
    return {"code": 0, "data": {"id": u.id}}


@router.delete("/users/{uid}")
def delete_user(uid: int, user: User = Depends(require_permission("system:user:write")),
                db: Session = Depends(get_db)):
    u = db.query(User).get(uid)
    if not u:
        raise HTTPException(status_code=404, detail="用户不存在")
    u.status = "disabled"
    db.commit()
    return {"code": 0, "message": "已禁用"}


# --- Nodes ---
@router.get("/nodes")
def list_nodes(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    nodes = db.query(AgentNode).order_by(AgentNode.created_at.desc()).all()
    return {"code": 0, "data": [
        {"id": n.id, "node_uid": n.node_uid, "node_name": n.node_name,
         "node_type": n.node_type, "status": n.status,
         "capabilities": n.capabilities, "tools_info": n.tools_info,
         "last_heartbeat_at": str(n.last_heartbeat_at) if n.last_heartbeat_at else None} for n in nodes
    ]}


# --- Devices ---
@router.get("/devices")
def list_devices(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    devices = db.query(Device).order_by(Device.created_at.desc()).all()
    return {"code": 0, "data": [
        {"id": d.id, "serial": d.serial, "brand": d.brand, "model": d.model,
         "android_version": d.android_version, "is_rooted": d.is_rooted,
         "is_frida_ready": d.is_frida_ready, "status": d.status,
         "agent_id": d.agent_id,
         "last_seen_at": str(d.last_seen_at) if d.last_seen_at else None} for d in devices
    ]}


# --- Audit Logs ---
@router.get("/audit-logs")
def list_audit_logs(page: int = 1, page_size: int = 50,
                    user: User = Depends(require_permission("system:audit:read")),
                    db: Session = Depends(get_db)):
    q = db.query(AuditLog)
    total = q.count()
    items = q.order_by(AuditLog.created_at.desc()).offset((page-1)*page_size).limit(page_size).all()
    return {"code": 0, "data": {
        "items": [{"id": a.id, "actor_name": a.actor_name, "action": a.action,
                   "target_type": a.target_type, "target_id": a.target_id,
                   "source_ip": a.source_ip, "request_id": a.request_id,
                   "before_json": a.before_json, "after_json": a.after_json,
                   "created_at": str(a.created_at)} for a in items],
        "total": total, "page": page, "page_size": page_size
    }}


# --- Dashboard ---
@router.get("/dashboard")
def system_dashboard(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    from app.models import Project, AppAsset, DetectionTask, Finding
    from sqlalchemy import func
    from datetime import datetime, timezone, timedelta

    # 严重度/状态分布（大小写不敏感）
    severity_rows = db.query(func.lower(Finding.severity), func.count()) \
        .group_by(func.lower(Finding.severity)).all()
    finding_status_rows = db.query(Finding.status, func.count()) \
        .group_by(Finding.status).all()
    task_status_rows = db.query(DetectionTask.status, func.count()) \
        .group_by(DetectionTask.status).all()

    # 近30天任务趋势（缺失日期补0）
    since = datetime.now(timezone.utc).date() - timedelta(days=29)
    trend_rows = db.query(func.date(DetectionTask.created_at), func.count()) \
        .filter(DetectionTask.created_at >= datetime.combine(since, datetime.min.time(), timezone.utc)) \
        .group_by(func.date(DetectionTask.created_at)).all()
    trend_map = {str(d): c for d, c in trend_rows}
    task_trend = [{"date": str(since + timedelta(days=i)),
                   "count": trend_map.get(str(since + timedelta(days=i)), 0)}
                  for i in range(30)]

    # 最新高风险未关闭问题
    recent = db.query(Finding) \
        .filter(func.lower(Finding.severity).in_(["critical", "high"]),
                Finding.status != "closed") \
        .order_by(Finding.created_at.desc()).limit(5).all()

    return {"code": 0, "data": {
        "project_count": db.query(Project).filter(Project.status == "active").count(),
        "app_count": db.query(AppAsset).count(),
        "task_count": db.query(DetectionTask).count(),
        "finding_count": db.query(Finding).count(),
        "high_finding_count": db.query(Finding).filter(
            func.lower(Finding.severity).in_(["critical", "high"])).count(),
        "node_count": db.query(AgentNode).filter(AgentNode.status == "online").count(),
        "device_count": db.query(Device).count(),
        "severity_distribution": {k: v for k, v in severity_rows},
        "finding_status_distribution": {k: v for k, v in finding_status_rows},
        "task_status_distribution": {k: v for k, v in task_status_rows},
        "task_trend": task_trend,
        "recent_findings": [{
            "id": f.id, "title": f.title, "severity": f.severity,
            "status": f.status, "task_id": f.task_id,
            "created_at": str(f.created_at)} for f in recent]
    }}


# --- Dict ---
@router.get("/dict")
def list_dict(dict_type: str = None, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    q = db.query(SysDict).filter(SysDict.status == "active")
    if dict_type:
        q = q.filter(SysDict.dict_type == dict_type)
    items = q.order_by(SysDict.dict_type, SysDict.sort_order).all()
    return {"code": 0, "data": [
        {"id": d.id, "dict_type": d.dict_type, "dict_key": d.dict_key,
         "dict_value": d.dict_value, "remark": d.remark} for d in items
    ]}


@router.post("/dict")
def create_dict(req: DictCreate, user: User = Depends(require_permission("system:dict:write")),
                db: Session = Depends(get_db)):
    existing = db.query(SysDict).filter(
        SysDict.dict_type == req.dict_type, SysDict.dict_key == req.dict_key
    ).first()
    if existing:
        raise HTTPException(status_code=409, detail="字典项已存在")
    d = SysDict(dict_type=req.dict_type, dict_key=req.dict_key,
                dict_value=req.dict_value, sort_order=req.sort_order, remark=req.remark)
    db.add(d)
    db.commit()
    return {"code": 0, "data": {"id": d.id}}
