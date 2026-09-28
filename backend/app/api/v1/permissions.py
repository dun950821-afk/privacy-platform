"""权限知识库路由 (基于 privacy_kb.permission)

权限表是**受控词表**，不是自由文本：`permission_type` 按平台各一套取值。
这张表此前攒到过 39 个自由文本取值（「危险/已弱化」「普通/受限 API权限」…），
根因就是没有写入侧的校验——所以枚举由后端给出（`/permissions/meta`），前端不硬编码。

**词表只有一处定义**：`app.services.permission_taxonomy`。这里不再抄一份，
免得两处各改各的、加了新取值只在一边生效。
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, or_, text
from sqlalchemy.orm import Session

from app.api.deps import require_permission
from app.core.database import get_db
from app.models import User
from app.models.kb import KBPermission
from app.schemas import PermissionCreate, PermissionUpdate
from app.services.permission_taxonomy import (
    PERMISSION_TYPES_BY_PLATFORM, PLATFORMS, is_applicable, validate_permission_type,
)

router = APIRouter(prefix="/permissions", tags=["权限知识库"])

RISK_LEVELS = ("LOW", "MEDIUM", "HIGH", "CRITICAL")


def _normalize(text_: str) -> str:
    return text_.strip().lower()


def _brief(p: KBPermission) -> dict:
    return {
        "id": p.id,
        "permission_name": p.permission_name,
        "platform": p.platform,
        "category": p.category,
        "permission_type": p.permission_type,
        "risk_level": p.risk_level,
        "is_active": p.is_active,
    }


def _detail(p: KBPermission) -> dict:
    data = _brief(p)
    data.update({
        "capability": p.capability,
        "grant_mode": p.grant_mode,
        "compliance_focus": p.compliance_focus,
        "official_reference": p.official_reference,
    })
    return data


def _check_type(platform: str, value: str | None):
    try:
        validate_permission_type(platform, value)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))


def _check_risk(value: str | None):
    if value is not None and value not in RISK_LEVELS:
        raise HTTPException(
            status_code=400, detail=f"risk_level 只能是：{'、'.join(RISK_LEVELS)}")


@router.get("/meta")
def permission_meta(platform: str = None,
                    user: User = Depends(require_permission("permission:read")),
                    db: Session = Depends(get_db)):
    """受控词表与现有分类取值。platform 给定则只返回该平台的词表。

    不传 platform 时 permission_type 返回三平台并集——前端在「还没选平台」的阶段
    只能这样兜底，别拿这个并集去校验任何单个平台的输入。
    """
    if platform and platform not in PERMISSION_TYPES_BY_PLATFORM:
        # 未知平台没有词表可给。放它下去会命中 `.get()` 的 None 直接 500，
        # 而退回并集又会让前端拿 Android 的词表去校验 iOS 的输入——两者都错，只能拒。
        raise HTTPException(status_code=400,
                            detail=f"platform 只能是：{'、'.join(PLATFORMS)}")
    q = db.query(KBPermission.category).filter(
        KBPermission.category.isnot(None), KBPermission.category != "")
    if platform:
        q = q.filter(KBPermission.platform == platform)
    categories = sorted({r[0] for r in q.all()})
    types = (PERMISSION_TYPES_BY_PLATFORM.get(platform) if platform
             else tuple(t for ts in PERMISSION_TYPES_BY_PLATFORM.values() for t in ts))
    return {"code": 0, "data": {
        "platforms": list(PLATFORMS),
        "permission_types": list(dict.fromkeys(types)),
        "risk_levels": list(RISK_LEVELS),
        "categories": categories,
    }}


@router.get("")
def list_permissions(category: str = None, permission_type: str = None,
                     risk_level: str = None, keyword: str = None,
                     platform: str = None, applicable: bool = None,
                     is_active: bool = None, page: int = 1, page_size: int = 50,
                     user: User = Depends(require_permission("permission:read")),
                     db: Session = Depends(get_db)):
    """权限列表：支持平台/分类/类型/风险/关键字/可达性/启停筛选与分页"""
    page_size = min(max(page_size, 1), 200)
    page = max(page, 1)

    q = db.query(KBPermission)
    if category:
        q = q.filter(KBPermission.category == category)
    if permission_type:
        q = q.filter(KBPermission.permission_type == permission_type)
    if risk_level:
        q = q.filter(KBPermission.risk_level == risk_level)
    if platform:
        q = q.filter(KBPermission.platform == platform)
    if is_active is not None:
        q = q.filter(KBPermission.is_active == is_active)
    if keyword:
        like = f"%{_normalize(keyword)}%"
        q = q.filter(or_(KBPermission.normalized_name.like(like),
                         func.lower(KBPermission.capability).like(like)))

    if applicable:
        # 可达性不能只在 SQL 里判：鸿蒙还要看 grant_mode，SQL 里拼不干净。
        # 取全量在 Python 侧过滤，分页放在过滤之后（数据量在千级，可以接受）。
        rows = [r for r in q.order_by(KBPermission.permission_name).all()
                if is_applicable(r.platform, r.permission_type, r.grant_mode)]
        total = len(rows)
        items = rows[(page - 1) * page_size: page * page_size]
    else:
        total = q.count()
        items = q.order_by(KBPermission.permission_name) \
                 .offset((page - 1) * page_size).limit(page_size).all()

    return {"code": 0, "data": {
        "items": [_brief(p) for p in items],
        "total": total, "page": page, "page_size": page_size,
    }}


@router.post("")
def create_permission(req: PermissionCreate,
                      user: User = Depends(require_permission("permission:write")),
                      db: Session = Depends(get_db)):
    name = (req.permission_name or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail="permission_name 不能为空")
    if db.query(KBPermission).filter(KBPermission.permission_name == name).first():
        raise HTTPException(status_code=400, detail="该权限名已存在")

    _check_type(req.platform, req.permission_type)
    _check_risk(req.risk_level)

    p = KBPermission(
        permission_name=name,
        platform=req.platform,
        normalized_name=_normalize(name),
        category=req.category,
        permission_type=req.permission_type,
        risk_level=req.risk_level,
        capability=req.capability,
        grant_mode=req.grant_mode,
        compliance_focus=req.compliance_focus,
        official_reference=req.official_reference,
    )
    db.add(p)
    db.commit()
    db.refresh(p)
    return {"code": 0, "data": _detail(p)}


@router.get("/{pid}")
def get_permission(pid: int, user: User = Depends(require_permission("permission:read")),
                   db: Session = Depends(get_db)):
    p = db.get(KBPermission, pid)
    if not p:
        raise HTTPException(status_code=404, detail="权限不存在")
    return {"code": 0, "data": _detail(p)}


@router.put("/{pid}")
def update_permission(pid: int, req: PermissionUpdate,
                      user: User = Depends(require_permission("permission:write")),
                      db: Session = Depends(get_db)):
    p = db.get(KBPermission, pid)
    if not p:
        raise HTTPException(status_code=404, detail="权限不存在")

    # 平台取自**这一行自身**：PermissionUpdate 不含 platform——平台是行的身份，
    # 和 permission_name 一样建后不可改，所以词表要按这一行的平台来校验。
    _check_type(p.platform, req.permission_type)
    _check_risk(req.risk_level)

    # permission_name 不在这里改：它是扫描记录按名字匹配的主键，
    # 改它等于让历史报告对不上（见 delete 的同款理由）。
    for field in ("category", "permission_type", "risk_level", "capability",
                  "grant_mode", "compliance_focus", "official_reference", "is_active"):
        value = getattr(req, field)
        if value is not None:
            setattr(p, field, value)
    db.commit()
    db.refresh(p)
    return {"code": 0, "data": _detail(p)}


@router.delete("/{pid}")
def delete_permission(pid: int, user: User = Depends(require_permission("permission:write")),
                      db: Session = Depends(get_db)):
    """删除权限。

    权限可能被历史扫描记录引用（privacy_scan.declared_permission）。这里**先断外键再删**：
    扫描记录本身留着、里面的 permission_name 也留着——历史报告按名字展示，把权限删了
    不该把历史记录弄成空白。组件侧的 component_permission 是 ON DELETE CASCADE，自动清。
    """
    p = db.get(KBPermission, pid)
    if not p:
        raise HTTPException(status_code=404, detail="权限不存在")

    db.execute(text(
        "UPDATE privacy_scan.declared_permission SET permission_id = NULL WHERE permission_id = :pid"
    ), {"pid": pid})
    db.delete(p)
    db.commit()
    return {"code": 0, "data": {"id": pid, "deleted": True}}
