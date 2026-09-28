"""规则管理路由"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.models import Rule, RuleVersion, User
from app.schemas import RuleCreate, RuleVersionCreate
from app.api.deps import get_current_user, require_permission
from datetime import datetime, timezone

router = APIRouter(prefix="/rules", tags=["规则管理"])


@router.get("")
def list_rules(category: str = None, status: str = None,
               user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    q = db.query(Rule)
    if category:
        q = q.filter(Rule.category == category)
    if status:
        q = q.filter(Rule.status == status)
    items = q.order_by(Rule.rule_key).all()
    return {"code": 0, "data": [
        {"id": r.id, "rule_key": r.rule_key, "name": r.name, "category": r.category,
         "description": r.description, "status": r.status,
         "current_version_id": r.current_version_id,
         "updated_at": str(r.updated_at) if r.updated_at else None} for r in items
    ]}


@router.post("")
def create_rule(req: RuleCreate, user: User = Depends(require_permission("rule:write")),
                db: Session = Depends(get_db)):
    existing = db.query(Rule).filter(Rule.rule_key == req.rule_key).first()
    if existing:
        raise HTTPException(status_code=409, detail="规则编号已存在")
    rule = Rule(rule_key=req.rule_key, name=req.name, category=req.category,
                description=req.description, status="draft")
    db.add(rule)
    db.commit()
    db.refresh(rule)
    return {"code": 0, "data": {"id": rule.id}}


@router.get("/{rid}")
def get_rule(rid: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    r = db.query(Rule).get(rid)
    if not r:
        raise HTTPException(status_code=404, detail="规则不存在")
    versions = db.query(RuleVersion).filter(RuleVersion.rule_id == rid).order_by(
        RuleVersion.created_at.desc()).all()
    user_ids = {v.published_by for v in versions if v.published_by}
    user_names = {u.id: (u.full_name or u.username)
                  for u in db.query(User).filter(User.id.in_(user_ids)).all()} if user_ids else {}
    current = next((v for v in versions if v.id == r.current_version_id), None)
    return {"code": 0, "data": {
        "id": r.id, "rule_key": r.rule_key, "name": r.name, "category": r.category,
        "description": r.description, "status": r.status,
        "current_version_id": r.current_version_id,
        "current_version": current.version if current else None,
        "current_content": current.rule_content if current else None,
        "created_at": str(r.created_at) if r.created_at else None,
        "updated_at": str(r.updated_at) if r.updated_at else None,
        "versions": [{"id": v.id, "version": v.version, "status": v.status,
                       "changelog": v.changelog,
                       "published_by": user_names.get(v.published_by),
                       "published_at": str(v.published_at) if v.published_at else None} for v in versions]
    }}


@router.post("/{rid}/versions")
def create_version(rid: int, req: RuleVersionCreate,
                   user: User = Depends(require_permission("rule:write")),
                   db: Session = Depends(get_db)):
    r = db.query(Rule).get(rid)
    if not r:
        raise HTTPException(status_code=404, detail="规则不存在")
    existing = db.query(RuleVersion).filter(
        RuleVersion.rule_id == rid, RuleVersion.version == req.version
    ).first()
    if existing:
        raise HTTPException(status_code=409, detail="版本号已存在")
    rv = RuleVersion(rule_id=rid, version=req.version, rule_content=req.rule_content,
                     changelog=req.changelog, status="draft")
    db.add(rv)
    db.commit()
    db.refresh(rv)
    return {"code": 0, "data": {"id": rv.id, "version": rv.version}}


@router.post("/{rid}/versions/{vid}/publish")
def publish_version(rid: int, vid: int,
                    user: User = Depends(require_permission("rule:publish")),
                    db: Session = Depends(get_db)):
    rv = db.query(RuleVersion).get(vid)
    if not rv or rv.rule_id != rid:
        raise HTTPException(status_code=404, detail="规则版本不存在")
    if db.query(Rule).get(rid).category == "correlation":
        raise HTTPException(status_code=400, detail="关联规则请通过 /correlation-rules 接口发布")
    rv.status = "published"
    rv.published_by = user.id
    rv.published_at = datetime.now(timezone.utc)
    
    rule = db.query(Rule).get(rid)
    if rule:
        rule.current_version_id = vid
        rule.status = "active"
    db.commit()
    return {"code": 0, "data": {"id": rv.id, "status": rv.status}}
