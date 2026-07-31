"""SDK知识库路由"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.models import SDKKnowledge, SDKFingerprint, User
from app.schemas import SDKCreate, SDKFingerprintCreate
from app.api.deps import get_current_user, require_permission
from app.core.security import generate_uid

router = APIRouter(prefix="/sdks", tags=["SDK知识库"])


@router.get("")
def list_sdks(category: str = None, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    q = db.query(SDKKnowledge)
    if category:
        q = q.filter(SDKKnowledge.category == category)
    items = q.order_by(SDKKnowledge.name).all()
    return {"code": 0, "data": [
        {"id": s.id, "sdk_uid": s.sdk_uid, "name": s.name, "vendor": s.vendor,
         "category": s.category, "status": s.status} for s in items
    ]}


@router.post("")
def create_sdk(req: SDKCreate, user: User = Depends(require_permission("sdk:write")),
               db: Session = Depends(get_db)):
    sdk = SDKKnowledge(
        sdk_uid=generate_uid("sdk"), name=req.name, vendor=req.vendor,
        category=req.category, official_url=req.official_url,
        privacy_policy_url=req.privacy_policy_url, description=req.description,
        privacy_behaviors=req.privacy_behaviors, config_capabilities=req.config_capabilities
    )
    db.add(sdk)
    db.commit()
    db.refresh(sdk)
    return {"code": 0, "data": {"id": sdk.id, "sdk_uid": sdk.sdk_uid}}


@router.get("/{sid}")
def get_sdk(sid: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    s = db.query(SDKKnowledge).get(sid)
    if not s:
        raise HTTPException(status_code=404, detail="SDK不存在")
    fingerprints = db.query(SDKFingerprint).filter(SDKFingerprint.sdk_id == sid).all()
    return {"code": 0, "data": {
        "id": s.id, "sdk_uid": s.sdk_uid, "name": s.name, "vendor": s.vendor,
        "category": s.category, "official_url": s.official_url,
        "privacy_policy_url": s.privacy_policy_url, "status": s.status,
        "privacy_behaviors": s.privacy_behaviors,
        "config_capabilities": s.config_capabilities,
        "description": s.description,
        "fingerprints": [{"id": f.id, "type": f.fingerprint_type, "value": f.fingerprint_value[:100],
                           "weight": f.weight, "version_range": f.version_range} for f in fingerprints]
    }}


@router.put("/{sid}")
def update_sdk(sid: int, req: dict, user: User = Depends(require_permission("sdk:write")),
               db: Session = Depends(get_db)):
    s = db.query(SDKKnowledge).get(sid)
    if not s:
        raise HTTPException(status_code=404, detail="SDK不存在")
    for field in ["name", "vendor", "category", "official_url", "privacy_policy_url",
                  "status", "description", "privacy_behaviors", "config_capabilities"]:
        if field in req:
            setattr(s, field, req[field])
    db.commit()
    return {"code": 0, "data": {"id": s.id}}


@router.get("/{sid}/fingerprints")
def list_fingerprints(sid: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    fps = db.query(SDKFingerprint).filter(SDKFingerprint.sdk_id == sid).all()
    return {"code": 0, "data": [
        {"id": f.id, "fingerprint_type": f.fingerprint_type, "fingerprint_value": f.fingerprint_value,
         "weight": f.weight, "version_range": f.version_range} for f in fps
    ]}


@router.post("/{sid}/fingerprints")
def add_fingerprint(sid: int, req: SDKFingerprintCreate,
                    user: User = Depends(require_permission("sdk:write")),
                    db: Session = Depends(get_db)):
    fp = SDKFingerprint(sdk_id=sid, fingerprint_type=req.fingerprint_type,
                        fingerprint_value=req.fingerprint_value, weight=req.weight,
                        version_range=req.version_range)
    db.add(fp)
    db.commit()
    return {"code": 0, "data": {"id": fp.id}}
