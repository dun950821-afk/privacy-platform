"""SDK/组件知识库路由 (基于 privacy_kb)"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func
from app.core.database import get_db
from app.models import User
from app.models.kb import (
    KBComponent, KBVendor, KBComponentFingerprint, KBComponentAlias,
    KBComponentDataClaim, KBDataItem, KBComponentPermission, KBPermission,
)
from app.schemas import ComponentCreate, ComponentFingerprintCreate
from app.api.deps import get_current_user, require_permission
from app.core.security import generate_uid

router = APIRouter(prefix="/sdks", tags=["SDK知识库"])


def _normalize(text: str) -> str:
    return text.strip().lower()


def _upsert_vendor(db: Session, name: str) -> KBVendor:
    """按名称查找或创建厂商"""
    normalized = _normalize(name)
    vendor = db.query(KBVendor).filter(KBVendor.normalized_name == normalized).first()
    if vendor:
        return vendor
    vendor = KBVendor(
        vendor_key=generate_uid("ven"),
        name=name.strip(),
        normalized_name=normalized,
    )
    db.add(vendor)
    db.flush()
    return vendor


def _component_brief(c: KBComponent, fingerprint_count: int = None) -> dict:
    return {
        "id": c.id,
        "component_key": c.component_key,
        "name": c.name,
        "vendor": c.vendor.name if c.vendor else None,
        "component_kind": c.component_kind,
        "category_l1": c.category_l1,
        "category_l2": c.category_l2,
        "sensitivity_level": c.sensitivity_level,
        "confidence_level": c.confidence_level,
        "verification_status": c.verification_status,
        "is_active": c.is_active,
        "fingerprint_count": fingerprint_count,
    }


@router.get("")
def list_sdks(kind: str = None, category: str = None, keyword: str = None,
              page: int = 1, page_size: int = 50,
              user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """组件列表: 支持类型/分类/关键字筛选与分页"""
    page_size = min(max(page_size, 1), 200)
    page = max(page, 1)
    q = db.query(KBComponent).outerjoin(KBVendor, KBComponent.vendor_id == KBVendor.id)
    if kind:
        q = q.filter(KBComponent.component_kind == kind)
    if category:
        q = q.filter(KBComponent.category_l1 == category)
    if keyword:
        like = f"%{_normalize(keyword)}%"
        q = q.filter(KBComponent.normalized_name.like(like) |
                     KBVendor.normalized_name.like(like))
    total = q.count()
    items = q.order_by(KBComponent.component_kind, KBComponent.name) \
             .offset((page - 1) * page_size).limit(page_size).all()

    # 指纹数量统计
    fp_counts = dict(
        db.query(KBComponentFingerprint.component_id, func.count())
        .filter(KBComponentFingerprint.component_id.in_([c.id for c in items] or [0]))
        .group_by(KBComponentFingerprint.component_id).all()
    ) if items else {}

    return {"code": 0, "data": {
        "items": [_component_brief(c, fp_counts.get(c.id, 0)) for c in items],
        "total": total, "page": page, "page_size": page_size,
    }}


@router.post("")
def create_sdk(req: ComponentCreate, user: User = Depends(require_permission("sdk:write")),
               db: Session = Depends(get_db)):
    vendor = _upsert_vendor(db, req.vendor) if req.vendor else None
    component = KBComponent(
        component_key=generate_uid("comp"),
        name=req.name.strip(),
        normalized_name=_normalize(req.name),
        vendor_id=vendor.id if vendor else None,
        component_kind=req.component_kind,
        category_l1=req.category_l1,
        category_l2=req.category_l2,
        primary_purpose=req.primary_purpose,
        description=req.description,
        sensitivity_level=req.sensitivity_level,
        verification_status="PENDING",
    )
    db.add(component)
    db.commit()
    db.refresh(component)
    return {"code": 0, "data": {"id": component.id, "component_key": component.component_key}}


@router.get("/{sid}")
def get_sdk(sid: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    c = db.query(KBComponent).get(sid)
    if not c:
        raise HTTPException(status_code=404, detail="组件不存在")

    fingerprints = db.query(KBComponentFingerprint).filter(
        KBComponentFingerprint.component_id == sid
    ).order_by(KBComponentFingerprint.fingerprint_type, KBComponentFingerprint.id).all()

    aliases = db.query(KBComponentAlias).filter(KBComponentAlias.component_id == sid).all()

    claims = db.query(KBComponentDataClaim, KBDataItem) \
        .outerjoin(KBDataItem, KBComponentDataClaim.data_item_id == KBDataItem.id) \
        .filter(KBComponentDataClaim.component_id == sid).all()

    perms = db.query(KBComponentPermission, KBPermission) \
        .join(KBPermission, KBComponentPermission.permission_id == KBPermission.id) \
        .filter(KBComponentPermission.component_id == sid).all()

    data = _component_brief(c, len(fingerprints))
    data.update({
        "english_name": c.english_name,
        "vendor_website": c.vendor.official_website if c.vendor else None,
        "primary_purpose": c.primary_purpose,
        "description": c.description,
        "license_name": c.license_name,
        "compliance_note": c.compliance_note,
        "recommended_match_rule": c.recommended_match_rule,
        "aliases": [{"id": a.id, "alias_name": a.alias_name, "alias_type": a.alias_type}
                    for a in aliases],
        "fingerprints": [{
            "id": f.id, "fingerprint_type": f.fingerprint_type, "value": f.value,
            "match_mode": f.match_mode, "weight": f.weight,
            "evidence_role": f.evidence_role, "is_negative": f.is_negative,
            "version_from": f.version_from, "version_to": f.version_to,
        } for f in fingerprints],
        "data_claims": [{
            "id": cl.id, "data_description": cl.data_description,
            "personal_info_category": cl.personal_info_category,
            "sensitivity_level": cl.sensitivity_level,
            "collection_mode": cl.collection_mode, "purpose": cl.purpose,
            "data_item": item.item_name if item else None,
        } for cl, item in claims],
        "permissions": [{
            "id": p.id, "permission_name": p.permission_name,
            "risk_level": p.risk_level, "relation_type": cp.relation_type,
        } for cp, p in perms],
    })
    return {"code": 0, "data": data}


@router.put("/{sid}")
def update_sdk(sid: int, req: dict, user: User = Depends(require_permission("sdk:write")),
               db: Session = Depends(get_db)):
    c = db.query(KBComponent).get(sid)
    if not c:
        raise HTTPException(status_code=404, detail="组件不存在")
    for field in ["name", "english_name", "component_kind", "category_l1", "category_l2",
                  "primary_purpose", "description", "license_name", "sensitivity_level",
                  "confidence_level", "verification_status", "compliance_note", "is_active"]:
        if field in req:
            setattr(c, field, req[field])
    if "name" in req:
        c.normalized_name = _normalize(req["name"])
    if "vendor" in req:
        vendor = _upsert_vendor(db, req["vendor"]) if req["vendor"] else None
        c.vendor_id = vendor.id if vendor else None
    db.commit()
    return {"code": 0, "data": {"id": c.id}}


@router.get("/{sid}/fingerprints")
def list_fingerprints(sid: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    fps = db.query(KBComponentFingerprint).filter(
        KBComponentFingerprint.component_id == sid
    ).order_by(KBComponentFingerprint.fingerprint_type, KBComponentFingerprint.id).all()
    return {"code": 0, "data": [{
        "id": f.id, "fingerprint_type": f.fingerprint_type, "value": f.value,
        "match_mode": f.match_mode, "weight": f.weight,
        "evidence_role": f.evidence_role, "is_negative": f.is_negative,
        "version_from": f.version_from, "version_to": f.version_to,
    } for f in fps]}


@router.post("/{sid}/fingerprints")
def add_fingerprint(sid: int, req: ComponentFingerprintCreate,
                    user: User = Depends(require_permission("sdk:write")),
                    db: Session = Depends(get_db)):
    c = db.query(KBComponent).get(sid)
    if not c:
        raise HTTPException(status_code=404, detail="组件不存在")
    fp = KBComponentFingerprint(
        component_id=sid, fingerprint_type=req.fingerprint_type,
        value=req.value, normalized_value=_normalize(req.value),
        match_mode=req.match_mode, weight=req.weight,
        evidence_role=req.evidence_role,
        version_from=req.version_from, version_to=req.version_to,
    )
    db.add(fp)
    db.commit()
    return {"code": 0, "data": {"id": fp.id}}
