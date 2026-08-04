"""App资产管理路由"""
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, Query
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.storage import storage
from app.models import AppAsset, AppVersion, PrivacyPolicy, User
from app.models.kb import KBComponent, KBVendor
from app.models.kb import ScanApp, ScanAppBuild, ScanJob, ScanComponentHit
from app.schemas import AppCreate, AppUpdate, PrivacyPolicyCreate
from app.api.deps import get_current_user, require_permission, get_request_id
from fastapi import Request
import hashlib, os

router = APIRouter(prefix="/apps", tags=["App资产管理"])


@router.post("")
def create_app(req: AppCreate, request: Request,
               user: User = Depends(require_permission("app:write")),
               db: Session = Depends(get_db)):
    existing = db.query(AppAsset).filter(
        AppAsset.project_id == req.project_id,
        AppAsset.package_name == req.package_name
    ).first()
    if existing:
        raise HTTPException(status_code=409, detail="该包名在项目中已存在")
    app = AppAsset(
        project_id=req.project_id, package_name=req.package_name,
        app_name=req.app_name, app_type=req.app_type, category=req.category,
        department=req.department, vendor=req.vendor, description=req.description,
        owner_id=user.id
    )
    db.add(app)
    db.commit()
    db.refresh(app)
    return {"code": 0, "request_id": get_request_id(request), "data": {"id": app.id}}


@router.get("")
def list_apps(project_id: int = None, page: int = 1, page_size: int = 20,
              user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    q = db.query(AppAsset)
    if project_id:
        q = q.filter(AppAsset.project_id == project_id)
    total = q.count()
    items = q.order_by(AppAsset.created_at.desc()).offset((page-1)*page_size).limit(page_size).all()
    return {"code": 0, "data": {
        "items": [{"id": a.id, "package_name": a.package_name, "app_name": a.app_name,
                    "app_alias": a.app_alias,
                    "app_type": a.app_type, "category": a.category, "vendor": a.vendor,
                    "project_id": a.project_id, "version_count": len(a.versions),
                    "created_at": str(a.created_at)} for a in items],
        "total": total, "page": page, "page_size": page_size
    }}


@router.get("/{aid}")
def get_app(aid: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    app = db.query(AppAsset).get(aid)
    if not app:
        raise HTTPException(status_code=404, detail="App不存在")
    versions = db.query(AppVersion).filter(AppVersion.app_id == aid).all()
    policies = db.query(PrivacyPolicy).filter(PrivacyPolicy.app_id == aid).all()
    return {"code": 0, "data": {
        "id": app.id, "package_name": app.package_name, "app_name": app.app_name,
        "category": app.category, "department": app.department, "vendor": app.vendor,
        "description": app.description,
        "versions": [{"id": v.id, "version_name": v.version_name, "version_code": v.version_code,
                      "sha256": v.sha256[:16], "file_size": v.file_size,
                      "created_at": str(v.created_at)} for v in versions],
        "privacy_policies": [{"id": p.id, "version": p.version, "parse_status": p.parse_status} for p in policies]
    }}


@router.put("/{aid}")
def update_app(aid: int, req: AppUpdate,
               user: User = Depends(require_permission("app:write")),
               db: Session = Depends(get_db)):
    app = db.query(AppAsset).get(aid)
    if not app:
        raise HTTPException(status_code=404, detail="App不存在")
    if req.app_name: app.app_name = req.app_name
    if req.app_alias is not None: app.app_alias = req.app_alias
    if req.category is not None: app.category = req.category
    if req.department is not None: app.department = req.department
    if req.vendor is not None: app.vendor = req.vendor
    if req.description is not None: app.description = req.description
    db.commit()
    return {"code": 0, "data": {"id": app.id}}


@router.delete("/{aid}")
def delete_app(aid: int, user: User = Depends(require_permission("app:write")),
               db: Session = Depends(get_db)):
    app = db.query(AppAsset).get(aid)
    if not app:
        raise HTTPException(status_code=404, detail="App不存在")
    db.delete(app)
    db.commit()
    return {"code": 0, "message": "已删除"}


@router.post("/{aid}/versions/upload")
async def upload_version(aid: int,
                          file: UploadFile = File(...),
                          version_name: str = Form(...),
                          version_code: int = Form(...),
                          channel: str = Form("official"),
                          upload_notes: str = Form(""),
                          user: User = Depends(require_permission("app:upload")),
                          db: Session = Depends(get_db)):
    app = db.query(AppAsset).get(aid)
    if not app:
        raise HTTPException(status_code=404, detail="App不存在")
    if not file.filename or not file.filename.endswith(".apk"):
        raise HTTPException(status_code=400, detail="请上传APK文件")
    
    # 保存文件
    upload_result = await storage.save_upload(file, subdir="apks")
    
    # 计算基本信息 (MVP简化, 实际由Worker解析后更新)
    version = AppVersion(
        app_id=aid, version_name=version_name, version_code=version_code,
        sha256=upload_result["hash"], file_size=upload_result["size"],
        artifact_path=upload_result["path"], channel=channel,
        upload_notes=upload_notes, uploaded_by=user.id
    )
    db.add(version)
    db.commit()
    db.refresh(version)
    return {"code": 0, "data": {
        "id": version.id, "version_name": version.version_name,
        "version_code": version.version_code, "sha256": version.sha256,
        "file_size": version.file_size, "package_name": app.package_name
    }}


@router.get("/{aid}/versions")
def list_versions(aid: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    versions = db.query(AppVersion).filter(AppVersion.app_id == aid).order_by(AppVersion.created_at.desc()).all()
    app = db.query(AppAsset).get(aid)
    return {"code": 0, "data": [
        {"id": v.id, "version_name": v.version_name, "version_code": v.version_code,
         "sha256": v.sha256[:16], "file_size": v.file_size, "channel": v.channel,
         "min_sdk": v.min_sdk, "target_sdk": v.target_sdk,
         "package_name": app.package_name if app else None,
         "app_name": app.app_name if app else None,
         "created_at": str(v.created_at)} for v in versions
    ]}


@router.get("/{aid}/versions/{vid}")
def get_version(aid: int, vid: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    v = db.query(AppVersion).get(vid)
    if not v or v.app_id != aid:
        raise HTTPException(status_code=404, detail="版本不存在")
    return {"code": 0, "data": {
        "id": v.id, "version_name": v.version_name, "version_code": v.version_code,
        "sha256": v.sha256, "file_size": v.file_size, "min_sdk": v.min_sdk,
        "target_sdk": v.target_sdk, "signature_info": v.signature_info,
        "channel": v.channel, "build_time": str(v.build_time) if v.build_time else None,
        "upload_notes": v.upload_notes, "created_at": str(v.created_at)
    }}


@router.post("/{aid}/privacy-policies")
def create_policy(aid: int, req: PrivacyPolicyCreate,
                  user: User = Depends(require_permission("app:write")),
                  db: Session = Depends(get_db)):
    policy = PrivacyPolicy(
        app_id=aid, version=req.version, effective_date=req.effective_date,
        raw_text=req.raw_text, parse_status="pending"
    )
    db.add(policy)
    db.commit()
    db.refresh(policy)
    return {"code": 0, "data": {"id": policy.id, "parse_status": policy.parse_status}}


@router.get("/{aid}/privacy-policies")
def list_policies(aid: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    policies = db.query(PrivacyPolicy).filter(PrivacyPolicy.app_id == aid).all()
    return {"code": 0, "data": [
        {"id": p.id, "version": p.version, "parse_status": p.parse_status,
         "effective_date": str(p.effective_date) if p.effective_date else None,
         "created_at": str(p.created_at)} for p in policies
    ]}


@router.get("/{aid}/privacy-policies/{pid}")
def get_policy(aid: int, pid: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    p = db.query(PrivacyPolicy).get(pid)
    if not p or p.app_id != aid:
        raise HTTPException(status_code=404, detail="隐私政策不存在")
    return {"code": 0, "data": {
        "id": p.id, "version": p.version, "effective_date": str(p.effective_date) if p.effective_date else None,
        "raw_text": p.raw_text[:500] if p.raw_text else None,
        "parsed_json": p.parsed_json, "parse_status": p.parse_status,
        "parse_confidence": p.parse_confidence
    }}


@router.get("/{aid}/sdks")
def list_app_sdks(aid: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """App识别到的SDK/组件列表 (来自 privacy_scan 扫描命中结果)"""
    app = db.query(AppAsset).get(aid)
    if not app:
        raise HTTPException(status_code=404, detail="App不存在")
    rows = db.query(ScanComponentHit, KBComponent, KBVendor) \
        .join(ScanJob, ScanComponentHit.scan_job_id == ScanJob.id) \
        .join(ScanAppBuild, ScanJob.app_build_id == ScanAppBuild.id) \
        .join(ScanApp, ScanAppBuild.app_id == ScanApp.id) \
        .join(KBComponent, ScanComponentHit.component_id == KBComponent.id) \
        .outerjoin(KBVendor, KBComponent.vendor_id == KBVendor.id) \
        .filter(ScanApp.package_name == app.package_name) \
        .order_by(ScanComponentHit.total_score.desc()).all()
    result = []
    seen = set()
    for hit, comp, vendor in rows:
        if comp.id in seen:
            continue
        seen.add(comp.id)
        result.append({
            "id": comp.id, "name": comp.name,
            "vendor": vendor.name if vendor else None,
            "component_kind": comp.component_kind,
            "category_l1": comp.category_l1,
            "sensitivity_level": comp.sensitivity_level,
            "total_score": hit.total_score,
            "confidence_level": hit.confidence_level,
            "hit_status": hit.hit_status,
            "evidence_count": hit.evidence_count,
        })
    return {"code": 0, "data": result}


@router.post("/quick-upload")
async def quick_upload(
    project_id: int = Form(...),
    app_alias: str = Form(None),
    app_name: str = Form(None),  # 兼容旧前端，等价于别称
    file: UploadFile = File(...),
    user: User = Depends(require_permission("app:upload")),
    db: Session = Depends(get_db),
):
    """
    一体化上传：创建App + 上传APK + Androguard自动解析
    包名、App名称、版本、SHA256、SDK版本等全部从APK自动解析
    App别称（app_alias）为用户自定义显示名，可选
    """
    import logging
    logger = logging.getLogger(__name__)
    alias = (app_alias or app_name or "").strip() or None

    if not file.filename or not file.filename.endswith(".apk"):
        raise HTTPException(status_code=400, detail="请上传APK文件")

    # 1. 保存APK文件
    upload_result = await storage.save_upload(file, subdir="apks")
    apk_path = upload_result["path"]

    # 2. 用Androguard解析APK
    parsed = {}
    try:
        from androguard.core.apk import APK
        import hashlib as hl

        with open(apk_path, "rb") as f:
            apk_data = f.read()
        sha256 = hl.sha256(apk_data).hexdigest()

        apk = APK(apk_path)
        parsed = {
            "package_name": apk.get_package(),
            "app_name_from_apk": apk.get_app_name(),
            "version_name": apk.get_androidversion_name() or "",
            "version_code": int(apk.get_androidversion_code() or 1),
            "min_sdk": int(apk.get_min_sdk_version() or 0) if apk.get_min_sdk_version() else None,
            "target_sdk": int(apk.get_target_sdk_version() or 0) if apk.get_target_sdk_version() else None,
            "max_sdk": int(apk.get_max_sdk_version() or 0) if apk.get_max_sdk_version() else None,
            "sha256": sha256,
            "file_size": upload_result["size"],
            "permissions": apk.get_permissions(),
            "activities": apk.get_activities(),
            "services": apk.get_services(),
            "receivers": apk.get_receivers(),
            "providers": apk.get_providers(),
            "is_signed": apk.is_signed(),
        }
        logger.info(f"APK parsed: {parsed['package_name']} v{parsed['version_name']}")
    except ImportError:
        logger.warning("androguard not installed, skipping APK parsing")
        parsed = {
            "sha256": upload_result["hash"],
            "file_size": upload_result["size"],
            "version_name": "1.0.0",
            "version_code": 1,
        }
    except Exception as e:
        logger.error(f"APK parsing failed: {e}")
        parsed = {
            "sha256": upload_result["hash"],
            "file_size": upload_result["size"],
            "version_name": "1.0.0",
            "version_code": 1,
        }

    # 3. 创建或查找App资产（名称以APK解析为准，别称用户自定义）
    package_name = parsed.get("package_name", "")
    parsed_name = parsed.get("app_name_from_apk") or ""
    app = None
    if package_name:
        app = db.query(AppAsset).filter(
            AppAsset.project_id == project_id,
            AppAsset.package_name == package_name
        ).first()

    if not app:
        app = AppAsset(
            project_id=project_id,
            package_name=package_name or f"unknown.{upload_result['hash'][:8]}",
            app_name=parsed_name or alias or package_name or "未知应用",
            app_alias=alias,
            app_type="android",
        )
        db.add(app)
        db.commit()
        db.refresh(app)
    elif alias and app.app_alias != alias:
        app.app_alias = alias
        db.commit()

    # 4. 创建版本
    version = AppVersion(
        app_id=app.id,
        version_name=parsed.get("version_name", "1.0.0"),
        version_code=parsed.get("version_code", 1),
        sha256=parsed.get("sha256", upload_result["hash"]),
        file_size=parsed.get("file_size", upload_result["size"]),
        min_sdk=parsed.get("min_sdk"),
        target_sdk=parsed.get("target_sdk"),
        artifact_path=apk_path,
        channel="official",
        upload_notes="",
        uploaded_by=user.id,
    )
    db.add(version)
    db.commit()
    db.refresh(version)

    return {"code": 0, "data": {
        "app_id": app.id,
        "app_name": app.app_name,
        "app_alias": app.app_alias,
        "package_name": app.package_name,
        "version_id": version.id,
        "version_name": version.version_name,
        "version_code": version.version_code,
        "sha256": version.sha256,
        "file_size": version.file_size,
        "min_sdk": version.min_sdk,
        "target_sdk": version.target_sdk,
        "parsed": parsed,
    }}
