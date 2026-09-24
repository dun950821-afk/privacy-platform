"""引擎管理路由"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.models import AgentNode, EngineExecution, DetectionTask, SubTask
from app.api.deps import get_current_user, require_permission
from app.engine.worker import list_engines, ENGINE_REGISTRY
from app.services.engine_config import get_definition, get_or_create, public, save, reset, resolved, display_name
from app.services.execution_retry import can_retry_execution, create_retry_attempt
from app.core.redis import redis_client
from datetime import datetime, timezone

router = APIRouter(prefix="/engines", tags=["引擎管理"])


@router.get("")
def list_all_engines(user=Depends(get_current_user), db: Session = Depends(get_db)):
    """列出所有已注册引擎及其状态"""
    engines = list_engines(db)
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
            "engine_name": display_name(db, e.engine_type),
            "engine_version": e.engine_version,
            "status": e.status,
            "stage": e.stage,
            "stage_message": e.stage_message,
            "progress": e.progress,
            "error_code": e.error_code,
            "retryable": e.retryable,
            "heartbeat_at": str(e.heartbeat_at) if e.heartbeat_at else None,
            "finished_at": str(e.finished_at) if e.finished_at else (str(e.completed_at) if e.completed_at else None),
            "provider_scan_hash": e.provider_scan_hash,
            "provider_scan_id": e.provider_scan_id,
            "parser_version": e.parser_version,
            "parser_status": e.parser_status,
            "raw_result_hash": e.raw_result_hash,
            "normalized_event_count": e.normalized_event_count,
            "normalized_finding_count": e.normalized_finding_count,
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


@router.post("/executions/{eid}/retry")
def retry_execution(eid: int, user=Depends(require_permission("task:write")), db: Session = Depends(get_db)):
    execution = db.query(EngineExecution).get(eid)
    if not execution:
        raise HTTPException(status_code=404, detail="执行记录不存在")
    if not can_retry_execution(execution):
        raise HTTPException(status_code=400, detail="该引擎执行不可重试")
    attempt = create_retry_attempt(db, execution, display_name(db, execution.engine_type), execution.engine_version)
    return {"code": 0, "data": {"id": attempt.id, "parent_execution_id": execution.id, "status": attempt.status, "attempt_no": attempt.attempt_no}}


    """引擎执行详情"""
    e = db.query(EngineExecution).get(eid)
    if not e:
        raise HTTPException(status_code=404, detail="执行记录不存在")
    return {"code": 0, "data": {
        "id": e.id,
        "task_id": e.task_id,
        "sub_task_id": e.sub_task_id,
        "engine_type": e.engine_type,
        "engine_name": display_name(db, e.engine_type),
        "engine_version": e.engine_version,
        "status": e.status,
        "stage": e.stage,
        "stage_message": e.stage_message,
        "progress": e.progress,
        "error_code": e.error_code,
        "retryable": e.retryable,
        "heartbeat_at": str(e.heartbeat_at) if e.heartbeat_at else None,
        "finished_at": str(e.finished_at) if e.finished_at else (str(e.completed_at) if e.completed_at else None),
        "provider_scan_hash": e.provider_scan_hash,
        "provider_scan_id": e.provider_scan_id,
        "parser_version": e.parser_version,
        "parser_status": e.parser_status,
        "raw_result_hash": e.raw_result_hash,
        "normalized_event_count": e.normalized_event_count,
        "normalized_finding_count": e.normalized_finding_count,
        "config_json": e.config_json,
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
            "engine_name": display_name(db, r.engine_type),
            "total": r.total,
            "success": r.success or 0,
            "failed": r.failed or 0,
            "avg_duration_ms": int(r.avg_duration) if r.avg_duration else 0,
        } for r in by_engine],
        "by_status": {r.status: r.count for r in by_status},
        "total_executions": db.query(EngineExecution).count(),
        "recent": [{
            "id": e.id, "engine_name": display_name(db, e.engine_type),
            "status": e.status, "duration_ms": e.duration_ms,
            "created_at": str(e.created_at)
        } for e in recent],
    }}


@router.get("/{engine_type}/config")
def get_engine_config(engine_type: str, user=Depends(require_permission("engine:read")), db: Session = Depends(get_db)):
    if engine_type not in ENGINE_REGISTRY:
        raise HTTPException(status_code=404, detail=f"引擎类型 {engine_type} 不存在")
    return {"code": 0, "data": public(db, engine_type)}


@router.put("/{engine_type}/config")
def update_engine_config(engine_type: str, payload: dict, user=Depends(require_permission("engine:write")), db: Session = Depends(get_db)):
    if engine_type not in ENGINE_REGISTRY:
        raise HTTPException(status_code=404, detail=f"引擎类型 {engine_type} 不存在")
    try:
        row = save(db, engine_type, payload.get("config") or {}, payload.get("secrets") or {}, payload.get("clear_secrets") or [], user.id)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    return {"code": 0, "data": public(db, engine_type)}


@router.post("/{engine_type}/config/reset")
def reset_engine_config(engine_type: str, user=Depends(require_permission("engine:write")), db: Session = Depends(get_db)):
    if engine_type not in ENGINE_REGISTRY:
        raise HTTPException(status_code=404, detail=f"引擎类型 {engine_type} 不存在")
    reset(db, engine_type, user.id)
    return {"code": 0, "data": public(db, engine_type)}


@router.post("/{engine_type}/health-check")
def health_check(engine_type: str, user=Depends(require_permission("engine:health-check")), db: Session = Depends(get_db)):
    """对指定引擎做环境健康检查"""
    info = ENGINE_REGISTRY.get(engine_type)
    if not info:
        raise HTTPException(status_code=404, detail=f"引擎类型 {engine_type} 不存在")
    config = resolved(db, engine_type)
    adapter = info["adapter"](config)
    env_ok = adapter.validate_environment()
    row = get_or_create(db, engine_type)
    row.last_health_status = "ready" if env_ok else "not_configured"
    row.last_health_message = getattr(adapter, "last_error", "") or ("环境就绪" if env_ok else "运行环境不满足")
    row.last_checked_at = datetime.now(timezone.utc)
    db.commit()
    return {"code": 0, "data": {
        "engine_type": engine_type,
        "name": info["name"],
        "version": info["version"],
        "env_ready": env_ok,
        "status": row.last_health_status,
        "message": row.last_health_message,
        "capabilities": info["capabilities"],
        "checked_at": row.last_checked_at.isoformat(),
    }}
