"""关联规则管理路由"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, require_permission
from app.core.database import get_db
from app.models import (EngineObservation, FindingObservation, PlatformFinding, Rule,
                        RuleVersion, User)
from app.schemas import CorrelationRuleCreate, CorrelationRulePreview, CorrelationRuleVersionCreate
from app.services.observation_service import observation_view
from app.services.rule_evaluator import (
    RuleValidationError, evaluate_join_rule, evaluate_rule, validate_rule_content)

router = APIRouter(prefix="/correlation-rules", tags=["关联规则"])


def _serialize(rule: Rule, version: RuleVersion | None, hit_count: int = 0) -> dict:
    return {
        "id": rule.id, "rule_key": rule.rule_key, "name": rule.name,
        "description": rule.description, "status": rule.status,
        "current_version_id": rule.current_version_id,
        "current_version": version.version if version else None,
        "current_content": version.rule_content if version else None,
        "hit_count": hit_count,
        "updated_at": str(rule.updated_at) if rule.updated_at else None,
    }


@router.get("")
def list_correlation_rules(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    rules = db.query(Rule).filter(Rule.category == "correlation").order_by(Rule.rule_key).all()
    result = []
    for rule in rules:
        version = db.query(RuleVersion).get(rule.current_version_id) if rule.current_version_id else None
        hits = db.query(PlatformFinding).filter(PlatformFinding.correlation_rule_id == str(rule.id)).count()
        result.append(_serialize(rule, version, hits))
    return {"code": 0, "data": result}


@router.get("/{rid}")
def get_correlation_rule(rid: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    rule = db.query(Rule).get(rid)
    if not rule or rule.category != "correlation":
        raise HTTPException(status_code=404, detail="规则不存在")
    versions = db.query(RuleVersion).filter(RuleVersion.rule_id == rid).order_by(RuleVersion.created_at.desc()).all()
    current = db.query(RuleVersion).get(rule.current_version_id) if rule.current_version_id else None
    data = _serialize(rule, current)
    data["versions"] = [{"id": v.id, "version": v.version, "status": v.status, "changelog": v.changelog,
                         "created_at": str(v.created_at) if v.created_at else None} for v in versions]
    return {"code": 0, "data": data}


@router.post("")
def create_correlation_rule(req: CorrelationRuleCreate,
                            user: User = Depends(require_permission("rule:write")),
                            db: Session = Depends(get_db)):
    if db.query(Rule).filter(Rule.rule_key == req.rule_key).first():
        raise HTTPException(status_code=409, detail="规则编号已存在")
    try:
        validate_rule_content(req.content)
    except RuleValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    rule = Rule(rule_key=req.rule_key, name=req.name, category="correlation",
                description=req.description, status="disabled")
    db.add(rule)
    db.flush()
    version = RuleVersion(rule_id=rule.id, version="1.0", rule_content=req.content,
                          changelog="初始版本", status="draft")
    db.add(version)
    db.commit()
    db.refresh(rule)
    return {"code": 0, "data": {"id": rule.id, "version_id": version.id}}


@router.put("/{rid}/versions")
def save_correlation_version(rid: int, req: CorrelationRuleVersionCreate,
                             user: User = Depends(require_permission("rule:write")),
                             db: Session = Depends(get_db)):
    rule = db.query(Rule).get(rid)
    if not rule or rule.category != "correlation":
        raise HTTPException(status_code=404, detail="规则不存在")
    if db.query(RuleVersion).filter(RuleVersion.rule_id == rid, RuleVersion.version == req.version).first():
        raise HTTPException(status_code=409, detail="版本号已存在")
    try:
        validate_rule_content(req.content)
    except RuleValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    version = RuleVersion(rule_id=rid, version=req.version, rule_content=req.content,
                          changelog=req.changelog, status="draft")
    db.add(version)
    # 保存即新版本，新版本默认不启用
    rule.status = "disabled"
    db.commit()
    db.refresh(version)
    return {"code": 0, "data": {"id": version.id, "version": version.version}}


@router.post("/{rid}/versions/{vid}/publish")
def publish_correlation_version(rid: int, vid: int,
                                user=Depends(require_permission("rule:publish")),
                                db: Session = Depends(get_db)):
    rule = db.query(Rule).get(rid)
    if not rule or rule.category != "correlation":
        raise HTTPException(status_code=404, detail="规则不存在")
    version = db.query(RuleVersion).get(vid)
    if not version or version.rule_id != rid:
        raise HTTPException(status_code=404, detail="规则版本不存在")
    version.status = "published"
    version.published_by = user.id
    rule.current_version_id = vid
    rule.status = "active"
    db.commit()
    return {"code": 0, "data": {"id": vid, "status": "active"}}


@router.post("/{rid}/disable")
def disable_correlation_rule(rid: int, user=Depends(require_permission("rule:write")),
                             db: Session = Depends(get_db)):
    rule = db.query(Rule).get(rid)
    if not rule or rule.category != "correlation":
        raise HTTPException(status_code=404, detail="规则不存在")
    rule.status = "disabled"
    db.commit()
    return {"code": 0, "data": {"id": rule.id, "status": rule.status}}


def _findings_for_observations(db: Session, task_id: int, observation_ids: list) -> list:
    """锚点观察所属的结论 —— 预览时告诉用户「这条增强会挂到哪些结论上」。"""
    if not observation_ids:
        return []
    return db.query(PlatformFinding).join(
        FindingObservation, FindingObservation.finding_id == PlatformFinding.id
    ).filter(PlatformFinding.task_id == task_id,
             FindingObservation.observation_id.in_(observation_ids)).all()


@router.post("/{rid}/preview")
def preview_correlation_rule(rid: int, req: CorrelationRulePreview,
                             user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    rule = db.query(Rule).get(rid)
    if not rule or rule.category != "correlation":
        raise HTTPException(status_code=404, detail="规则不存在")
    version = db.query(RuleVersion).get(rule.current_version_id) if rule.current_version_id else None
    if not version:
        raise HTTPException(status_code=400, detail="规则没有可预览的版本")
    rows = db.query(EngineObservation).filter(EngineObservation.task_id == req.task_id).all()
    observations = [observation_view(o) for o in rows]
    content = version.rule_content or {}
    is_v2 = content.get("schema_version") == "2.0"
    try:
        if is_v2:
            groups = evaluate_join_rule(content, observations) or []
        else:
            matched = evaluate_rule(content, observations) or []
    except RuleValidationError as exc:
        # 库中存量内容可能非法，这属于客户端可见的校验失败，不能变成 500
        raise HTTPException(status_code=422, detail=f"规则内容非法: {exc}")
    if is_v2:
        # 增强规则的「命中」是指有证据可挂；它不会产生新结论，预览里如实区分
        anchor_ids = sorted({g["anchor"]["id"] for g in groups if g["anchor"].get("id")})
        evidence_ids = sorted({o["id"] for g in groups for o in g["evidence"] if o.get("id")})
        return {"code": 0, "data": {
            "rule_key": rule.rule_key,
            "action": "enrich",
            "would_match": bool(groups),
            "matched_observation_ids": anchor_ids,
            "evidence_observation_ids": evidence_ids,
            "finding_code": None,          # 增强不产出结论码
            "existing_findings": [f.finding_code for f in _findings_for_observations(db, req.task_id, anchor_ids)],
            "writes": False,
        }}
    current = db.query(PlatformFinding).filter(
        PlatformFinding.task_id == req.task_id,
        PlatformFinding.correlation_rule_id == str(rule.id)).all()
    return {"code": 0, "data": {
        "rule_key": rule.rule_key,
        "action": "create",
        "would_match": bool(matched),
        "matched_observation_ids": [o["id"] for o in matched],
        "finding_code": (content.get("produce") or {}).get("finding_code"),
        "existing_findings": [f.finding_code for f in current],
        "writes": False,
    }}
