"""引擎管理路由"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.models import AgentNode, EngineExecution, DetectionTask, SubTask
from app.api.deps import get_current_user, require_permission
from app.engine.worker import list_engines, ENGINE_REGISTRY
from app.core.redis import redis_client
from datetime import datetime, timezone

router = APIRouter(prefix="/engines", tags=["引擎管理"])


@router.get("")
def list_all_engines(user=Depends(get_current_user)):
    """列出所有已注册引擎及其状态"""
    engines = list_engines()
    return {"code": 0, "data": engines}


@router.get("/types")
def engine_types(user=Depends(get_current_user)):
    """引擎类型字典"""
    return {"code": 0, "data": [
        {"type": k, "name": v["name"], "version": v["version"],
         "capabilities": v["capabilities"], "description": v["description"]}
        for k, v in ENGINE_REGISTRY.items()
    ]}


@router.get("/executions")
def list_executions(
    task_id: int = None,
    engine_type: str = None,
    status: str = None,
    page: int = 1,
    page_size: int = 20,
    user=Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """引擎执行记录列表"""
    q = db.query(EngineExecution)
    if task_id:
        q = q.filter(EngineExecution.task_id == task_id)
    if engine_type:
        q = q.filter(EngineExecution.engine_type == engine_type)
    if status:
        q = q.filter(EngineExecution.status == status)
    total = q.count()
    items = q.order_by(EngineExecution.created_at.desc()).offset((page-1)*page_size).limit(page_size).all()
    result = []
    for e in items:
        task = db.query(DetectionTask).get(e.task_id)
        sub_task = db.query(SubTask).get(e.sub_task_id) if e.sub_task_id else None
        result.append({
            "id": e.id,
            "task_id": e.task_id,
            "task_code": task.task_code if task else None,
            "sub_task_id": e.sub_task_id,
            "engine_type": e.engine_type,
            "engine_name": e.engine_name,
            "engine_version": e.engine_version,
            "status": e.status,
            "stage": e.stage,
            "event_count": e.event_count,
            "artifact_count": e.artifact_count,
            "duration_ms": e.duration_ms,
            "error_message": e.error_message,
            "started_at": str(e.started_at) if e.started_at else None,
            "completed_at": str(e.completed_at) if e.completed_at else None,
            "created_at": str(e.created_at),
        })
    return {"code": 0, "data": {
        "items": result, "total": total, "page": page, "page_size": page_size
    }}


@router.get("/executions/{eid}")
def get_execution(eid: int, user=Depends(get_current_user), db: Session = Depends(get_db)):
    """引擎执行详情"""
    e = db.query(EngineExecution).get(eid)
    if not e:
        raise HTTPException(status_code=404, detail="执行记录不存在")
    return {"code": 0, "data": {
        "id": e.id,
        "task_id": e.task_id,
        "sub_task_id": e.sub_task_id,
        "engine_type": e.engine_type,
        "engine_name": e.engine_name,
        "engine_version": e.engine_version,
        "status": e.status,
        "stage": e.stage,
        "config_json": e.config_json,
        "result_summary": e.result_summary,
        "event_count": e.event_count,
        "artifact_count": e.artifact_count,
        "error_message": e.error_message,
        "log_path": e.log_path,
        "raw_output_path": e.raw_output_path,
        "duration_ms": e.duration_ms,
        "started_at": str(e.started_at) if e.started_at else None,
        "completed_at": str(e.completed_at) if e.completed_at else None,
        "created_at": str(e.created_at),
    }}


@router.get("/stats")
def engine_stats(user=Depends(get_current_user), db: Session = Depends(get_db)):
    """引擎统计"""
    from sqlalchemy import func
    # 按引擎类型统计
    by_engine = db.query(
        EngineExecution.engine_type,
        EngineExecution.engine_name,
        func.count(EngineExecution.id).label("total"),
        func.sum((EngineExecution.status == "completed").cast(__import__('sqlalchemy').Integer)).label("success"),
        func.sum((EngineExecution.status == "failed").cast(__import__('sqlalchemy').Integer)).label("failed"),
        func.avg(EngineExecution.duration_ms).label("avg_duration"),
    ).group_by(EngineExecution.engine_type, EngineExecution.engine_name).all()

    # 按状态统计
    by_status = db.query(
        EngineExecution.status,
        func.count(EngineExecution.id).label("count")
    ).group_by(EngineExecution.status).all()

    # 最近执行
    recent = db.query(EngineExecution).order_by(
        EngineExecution.created_at.desc()
    ).limit(10).all()

    return {"code": 0, "data": {
        "by_engine": [{
            "engine_type": r.engine_type,
            "engine_name": r.engine_name,
            "total": r.total,
            "success": r.success or 0,
            "failed": r.failed or 0,
            "avg_duration_ms": int(r.avg_duration) if r.avg_duration else 0,
        } for r in by_engine],
        "by_status": {r.status: r.count for r in by_status},
        "total_executions": db.query(EngineExecution).count(),
        "recent": [{
            "id": e.id, "engine_name": e.engine_name,
            "status": e.status, "duration_ms": e.duration_ms,
            "created_at": str(e.created_at)
        } for e in recent],
    }}


@router.post("/{engine_type}/health-check")
def health_check(engine_type: str, user=Depends(require_permission("system:nodes:read"))):
    """对指定引擎做环境健康检查"""
    info = ENGINE_REGISTRY.get(engine_type)
    if not info:
        raise HTTPException(status_code=404, detail=f"引擎类型 {engine_type} 不存在")
    adapter = info["adapter"]()
    env_ok = adapter.validate_environment()
    return {"code": 0, "data": {
        "engine_type": engine_type,
        "name": info["name"],
        "version": info["version"],
        "env_ready": env_ok,
        "capabilities": info["capabilities"],
        "status": "ready" if env_ok else "not_configured",
        "checked_at": datetime.now(timezone.utc).isoformat(),
    }}
