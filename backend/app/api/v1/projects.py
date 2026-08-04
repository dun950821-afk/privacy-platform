"""项目管理路由"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.models import Project, ProjectMember, User, AppAsset, DetectionTask, Finding
from app.schemas import ProjectCreate, ProjectUpdate, ProjectMemberAdd
from app.api.deps import get_current_user, get_request_id, require_permission
from fastapi import Request

router = APIRouter(prefix="/projects", tags=["项目管理"])


@router.post("")
def create_project(req: ProjectCreate, request: Request,
                   user: User = Depends(require_permission("project:write")),
                   db: Session = Depends(get_db)):
    proj = Project(name=req.name, description=req.description, owner_id=user.id)
    db.add(proj)
    db.commit()
    db.refresh(proj)
    # 添加创建者为owner
    db.add(ProjectMember(project_id=proj.id, user_id=user.id, role="owner"))
    db.commit()
    return {"code": 0, "request_id": get_request_id(request), "data": {"id": proj.id, "name": proj.name}}


@router.get("")
def list_projects(page: int = 1, page_size: int = 20, request: Request = None,
                  user: User = Depends(get_current_user),
                  db: Session = Depends(get_db)):
    q = db.query(Project).filter(Project.status == "active")
    total = q.count()
    items = q.order_by(Project.created_at.desc()).offset((page-1)*page_size).limit(page_size).all()
    return {"code": 0, "data": {
        "items": [{"id": p.id, "name": p.name, "description": p.description,
                    "status": p.status, "app_count": len(p.apps),
                    "created_at": str(p.created_at)} for p in items],
        "total": total, "page": page, "page_size": page_size
    }}


@router.get("/{pid}")
def get_project(pid: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    proj = db.query(Project).get(pid)
    if not proj:
        raise HTTPException(status_code=404, detail="项目不存在")
    members = db.query(ProjectMember).filter(ProjectMember.project_id == pid).all()
    app_count = db.query(AppAsset).filter(AppAsset.project_id == pid).count()
    task_count = db.query(DetectionTask).filter(DetectionTask.project_id == pid).count()
    return {"code": 0, "data": {
        "id": proj.id, "name": proj.name, "description": proj.description,
        "status": proj.status, "created_at": str(proj.created_at),
        "app_count": app_count, "task_count": task_count,
        "members": [{"user_id": m.user_id, "role": m.role} for m in members]
    }}


@router.put("/{pid}")
def update_project(pid: int, req: ProjectUpdate,
                   user: User = Depends(require_permission("project:write")),
                   db: Session = Depends(get_db)):
    proj = db.query(Project).get(pid)
    if not proj:
        raise HTTPException(status_code=404, detail="项目不存在")
    if req.name: proj.name = req.name
    if req.description is not None: proj.description = req.description
    if req.status: proj.status = req.status
    db.commit()
    return {"code": 0, "data": {"id": proj.id}}


@router.delete("/{pid}")
def delete_project(pid: int, user: User = Depends(require_permission("project:write")),
                  db: Session = Depends(get_db)):
    """删除项目：级联删除 App、版本、检测任务、事件、问题、证据等全部关联数据及磁盘文件"""
    from app.models import RetestRecord, AppVersion
    from app.core.config import settings
    from pathlib import Path
    import shutil

    proj = db.query(Project).get(pid)
    if not proj:
        raise HTTPException(status_code=404, detail="项目不存在")

    # 运行中的任务禁止删除
    RUNNING = ["queued", "running_static", "running_dynamic", "analyzing", "waiting_dynamic"]
    tasks = db.query(DetectionTask).filter(DetectionTask.project_id == pid).all()
    running = [t for t in tasks if t.status in RUNNING]
    if running:
        raise HTTPException(
            status_code=400,
            detail=f"存在 {len(running)} 个正在运行的检测任务，请先取消后再删除"
        )

    task_ids = [t.id for t in tasks]
    app_count = db.query(AppAsset).filter(AppAsset.project_id == pid).count()

    # 收集待清理的磁盘文件（任务证据目录 + APK安装包）
    versions = db.query(AppVersion).join(AppAsset).filter(AppAsset.project_id == pid).all()
    apk_paths = [v.artifact_path for v in versions if v.artifact_path]

    # 复测记录无级联约束，先手动清理
    if task_ids:
        finding_ids = [row[0] for row in db.query(Finding.id).filter(
            Finding.task_id.in_(task_ids)).all()]
        db.query(RetestRecord).filter(
            RetestRecord.retest_task_id.in_(task_ids) |
            RetestRecord.original_finding_id.in_(finding_ids or [0])
        ).delete(synchronize_session=False)
        # 删除任务：数据库级联清理 子任务/场景/事件/问题/证据/引擎执行/关联表/整改记录
        db.query(DetectionTask).filter(DetectionTask.id.in_(task_ids)) \
            .delete(synchronize_session=False)

    # 删除项目：级联 App资产/版本/隐私政策/项目成员
    db.delete(proj)
    db.commit()

    # 清理磁盘文件
    for tid in task_ids:
        shutil.rmtree(Path(settings.STORAGE_ROOT) / f"task_{tid}", ignore_errors=True)
    for p in apk_paths:
        try:
            Path(p).unlink(missing_ok=True)
        except OSError:
            pass

    return {"code": 0, "message": "已删除",
            "data": {"task_count": len(task_ids), "app_count": app_count}}


@router.get("/{pid}/members")
def list_members(pid: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    members = db.query(ProjectMember).filter(ProjectMember.project_id == pid).all()
    result = []
    for m in members:
        u = db.query(User).get(m.user_id)
        result.append({"user_id": m.user_id, "role": m.role,
                       "username": u.username if u else "", "full_name": u.full_name if u else ""})
    return {"code": 0, "data": result}


@router.post("/{pid}/members")
def add_member(pid: int, req: ProjectMemberAdd,
               user: User = Depends(require_permission("project:write")),
               db: Session = Depends(get_db)):
    existing = db.query(ProjectMember).filter(
        ProjectMember.project_id == pid, ProjectMember.user_id == req.user_id
    ).first()
    if existing:
        raise HTTPException(status_code=409, detail="成员已存在")
    member = ProjectMember(project_id=pid, user_id=req.user_id, role=req.role)
    db.add(member)
    db.commit()
    return {"code": 0, "data": {"id": member.id}}


@router.delete("/{pid}/members/{uid}")
def remove_member(pid: int, uid: int,
                  user: User = Depends(require_permission("project:write")),
                  db: Session = Depends(get_db)):
    member = db.query(ProjectMember).filter(
        ProjectMember.project_id == pid, ProjectMember.user_id == uid
    ).first()
    if member:
        db.delete(member)
        db.commit()
    return {"code": 0, "message": "已移除"}


@router.get("/{pid}/dashboard")
def project_dashboard(pid: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    apps = db.query(AppAsset).filter(AppAsset.project_id == pid).count()
    tasks = db.query(DetectionTask).filter(DetectionTask.project_id == pid).all()
    task_ids = [t.id for t in tasks]
    findings = db.query(Finding).filter(Finding.task_id.in_(task_ids)).all() if task_ids else []
    
    severity_count = {}
    status_count = {}
    for f in findings:
        severity_count[f.severity] = severity_count.get(f.severity, 0) + 1
        status_count[f.status] = status_count.get(f.status, 0) + 1
    
    return {"code": 0, "data": {
        "app_count": apps,
        "task_count": len(tasks),
        "finding_count": len(findings),
        "severity_distribution": severity_count,
        "status_distribution": status_count,
        "recent_tasks": [{"id": t.id, "task_code": t.task_code, "status": t.status,
                          "created_at": str(t.created_at)} for t in tasks[:5]]
    }}
