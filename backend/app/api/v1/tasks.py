"""检测任务路由"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.security import generate_uid
from app.models import (DetectionTask, SubTask, DetectionScenario, DetectionEvent,
                        Finding, Evidence, AppVersion, User, AgentNode, EngineExecution,
                        EngineObservation)
from app.schemas import TaskCreate, ScenarioUpdate
from app.api.deps import get_current_user, require_permission, get_request_id
from app.tasks.orchestrator import TaskOrchestrator
from app.services.engine_config import display_name
from app.tasks.engine_queue import get_task_engine_queue
from app.services.task_config import normalize_task_config, task_config_hash
from fastapi import Request
from datetime import datetime, timezone

router = APIRouter(prefix="/tasks", tags=["检测任务"])


@router.post("")
def create_task(req: TaskCreate, request: Request,
                user: User = Depends(require_permission("task:write")),
                db: Session = Depends(get_db)):
    version = db.query(AppVersion).get(req.app_version_id)
    if not version:
        raise HTTPException(status_code=404, detail="App版本不存在")
    
    app = version.app
    task = DetectionTask(
        task_code=generate_uid("task"),
        app_version_id=req.app_version_id,
        privacy_policy_id=req.privacy_policy_id,
        project_id=app.project_id,
        detection_type=req.detection_type,
        rule_pack_version=req.rule_pack_version,
        status="draft",
        config_json=normalize_task_config(req.config),
        created_by=user.id
    )
    db.add(task)
    db.commit()
    db.refresh(task)
    return {"code": 0, "request_id": get_request_id(request), "data": {
        "id": task.id, "task_code": task.task_code, "status": task.status
    }}


@router.get("")
def list_tasks(project_id: int = None, status: str = None, app_version_id: int = None,
               page: int = 1, page_size: int = 20,
               user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    q = db.query(DetectionTask)
    if project_id:
        q = q.filter(DetectionTask.project_id == project_id)
    if status:
        # 支持逗号分隔多状态过滤，如 status=queued,running_static
        statuses = [s.strip() for s in status.split(",") if s.strip()]
        if len(statuses) == 1:
            q = q.filter(DetectionTask.status == statuses[0])
        elif statuses:
            q = q.filter(DetectionTask.status.in_(statuses))
    if app_version_id:
        q = q.filter(DetectionTask.app_version_id == app_version_id)
    total = q.count()
    items = q.order_by(DetectionTask.created_at.desc()).offset((page-1)*page_size).limit(page_size).all()
    result = []
    for t in items:
        v = db.query(AppVersion).get(t.app_version_id)
        result.append({
            "id": t.id, "task_code": t.task_code, "status": t.status,
            "detection_type": t.detection_type, "rule_pack_version": t.rule_pack_version,
            "app_version_id": t.app_version_id,
            "app_name": v.app.app_name if v else None,
            "version_name": v.version_name if v else None,
            "created_at": str(t.created_at),
            "started_at": str(t.started_at) if t.started_at else None,
            "completed_at": str(t.completed_at) if t.completed_at else None,
            # 分析有效性：DEGRADED 表示本次分析没覆盖到应用代码，列表页要能看出来
            "analysis_coverage": t.analysis_coverage,
            "coverage_detail": t.coverage_detail or {},
            "engine_queue": get_task_engine_queue(db, t.id),
        })
    return {"code": 0, "data": {"items": result, "total": total, "page": page, "page_size": page_size}}


@router.get("/{tid}")
def get_task(tid: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    t = db.query(DetectionTask).get(tid)
    if not t:
        raise HTTPException(status_code=404, detail="任务不存在")
    v = db.query(AppVersion).get(t.app_version_id)
    sub_tasks = db.query(SubTask).filter(SubTask.task_id == tid).all()
    scenarios = db.query(DetectionScenario).filter(DetectionScenario.task_id == tid).all()
    event_count = db.query(DetectionEvent).filter(DetectionEvent.task_id == tid).count()
    finding_count = db.query(Finding).filter(Finding.task_id == tid).count()
    
    return {"code": 0, "data": {
        "id": t.id, "task_code": t.task_code, "status": t.status,
        "detection_type": t.detection_type, "rule_pack_version": t.rule_pack_version,
        "config_json": t.config_json, "config_hash": task_config_hash(t.config_json), "priority": t.priority,
        "started_at": str(t.started_at) if t.started_at else None,
        "completed_at": str(t.completed_at) if t.completed_at else None,
        "failed_reason": t.failed_reason,
        "analysis_coverage": t.analysis_coverage,
        "coverage_detail": t.coverage_detail or {},
        "app": {"name": v.app.app_name, "package_name": v.app.package_name} if v else None,
        "version": {"version_name": v.version_name, "version_code": v.version_code,
                     "sha256": v.sha256[:16], "file_size": v.file_size,
                     "min_sdk": v.min_sdk, "target_sdk": v.target_sdk} if v else None,
        "sub_tasks": [{"id": s.id, "sub_task_code": s.sub_task_code,
                       "engine_type": s.engine_type, "stage": s.stage, "status": s.status,
                       "error_message": s.error_message,
                       "result_summary": s.result_summary,
                       "started_at": str(s.started_at) if s.started_at else None,
                       "completed_at": str(s.completed_at) if s.completed_at else None} for s in sub_tasks],
        "scenarios": [{"id": s.id, "scenario_type": s.scenario_type,
                       "consent_status": s.consent_status, "status": s.status} for s in scenarios],
        "event_count": event_count, "finding_count": finding_count,
        "engine_queue": get_task_engine_queue(db, tid),
        "created_by": t.created_by,
        "created_at": str(t.created_at)
    }}


@router.post("/{tid}/submit")
def submit_task(tid: int, request: Request,
                user: User = Depends(require_permission("task:submit")),
                db: Session = Depends(get_db)):
    t = db.query(DetectionTask).get(tid)
    if not t:
        raise HTTPException(status_code=404, detail="任务不存在")
    if t.status != "draft":
        raise HTTPException(status_code=400, detail="任务已提交")
    
    orchestrator = TaskOrchestrator(db)
    orchestrator.submit_task(t)
    
    return {"code": 0, "request_id": get_request_id(request),
            "data": {"id": t.id, "status": t.status}}


@router.post("/{tid}/cancel")
def cancel_task(tid: int, user: User = Depends(require_permission("task:write")),
                db: Session = Depends(get_db)):
    t = db.query(DetectionTask).get(tid)
    if not t:
        raise HTTPException(status_code=404, detail="任务不存在")
    if t.status in ["completed", "failed", "canceled"]:
        raise HTTPException(status_code=400, detail="任务已结束")
    t.status = "canceled"
    t.completed_at = datetime.now(timezone.utc)
    db.commit()
    return {"code": 0, "data": {"id": t.id, "status": t.status}}


@router.post("/{tid}/retry")
def retry_task(tid: int, user: User = Depends(require_permission("task:write")),
               db: Session = Depends(get_db)):
    t = db.query(DetectionTask).get(tid)
    if not t:
        raise HTTPException(status_code=404, detail="任务不存在")
    if t.status not in ["failed", "canceled"]:
        raise HTTPException(status_code=400, detail="任务状态不允许重试")
    # 清理上一轮的事件和引擎执行记录，避免重跑后结果叠加
    db.query(DetectionEvent).filter(DetectionEvent.task_id == tid).delete(synchronize_session=False)
    db.query(EngineExecution).filter(EngineExecution.task_id == tid).delete(synchronize_session=False)
    t.status = "queued"
    t.failed_reason = None
    t.started_at = None
    t.completed_at = None
    db.commit()
    # 重新为选定的静态引擎创建 pending 执行记录，恢复队列"等待/执行中"展示
    from app.engine.worker import ENGINE_REGISTRY
    config = t.config_json or {}
    selected = config.get("engines")
    engine_types = [e for e in (selected if selected is not None else ENGINE_REGISTRY.keys())
                    if e in ENGINE_REGISTRY]
    static_subtask = db.query(SubTask).filter(
        SubTask.task_id == tid, SubTask.engine_type == "static"
    ).first()
    if static_subtask:
        static_subtask.status = "pending"
        static_subtask.stage = "prepare"
        for et in engine_types:
            db.add(EngineExecution(
                task_id=tid, sub_task_id=static_subtask.id, engine_type=et,
                engine_name=display_name(db, et), engine_version=ENGINE_REGISTRY[et]["version"],
                status="pending", stage="queued",
            ))
        db.commit()
    orchestrator = TaskOrchestrator(db)
    orchestrator.dispatch_task(t)
    return {"code": 0, "data": {"id": t.id, "status": t.status}}


# ============ 事件 ↔ SDK知识库 关联匹配 ============

def _load_sdk_match_index(db):
    """加载包名/类名指纹索引（最长前缀优先），用于事件归属 SDK 匹配"""
    from app.models.kb import KBComponentFingerprint, KBComponent, KBVendor
    rows = db.query(KBComponentFingerprint, KBComponent, KBVendor) \
        .join(KBComponent, KBComponentFingerprint.component_id == KBComponent.id) \
        .outerjoin(KBVendor, KBComponent.vendor_id == KBVendor.id) \
        .filter(KBComponentFingerprint.fingerprint_type.in_(["PACKAGE_PREFIX", "CLASS"]),
                KBComponentFingerprint.is_negative == False,
                KBComponentFingerprint.match_mode.in_(["EXACT", "PREFIX"]),
                KBComponent.is_active == True) \
        .all()
    index = []
    for fp, comp, vendor in rows:
        val = (fp.normalized_value or "").strip().lower()
        if not val:
            continue
        index.append((val, {
            "id": comp.id, "name": comp.name,
            "vendor": vendor.name if vendor else None,
            "component_kind": comp.component_kind,
            "category_l1": comp.category_l1,
            "sensitivity_level": comp.sensitivity_level,
        }))
    index.sort(key=lambda x: len(x[0]), reverse=True)
    return index


def _match_sdk(index, *candidates):
    """按调用方/API 的包名前缀匹配 SDK（调用方优先，最长前缀命中）"""
    for cand in candidates:
        if not cand:
            continue
        c = cand.strip().lower()
        for val, comp in index:
            if c.startswith(val):
                return comp
    return None


def _load_permission_index(db):
    """加载权限知识库索引: 权限名(小写) -> 权限知识"""
    from app.models.kb import KBPermission
    index = {}
    for p in db.query(KBPermission).filter(KBPermission.is_active == True).all():
        key = (p.normalized_name or p.permission_name or "").strip().lower()
        if key:
            index[key] = {
                "id": p.id, "permission_name": p.permission_name,
                "category": p.category, "capability": p.capability,
                "permission_type": p.permission_type, "risk_level": p.risk_level,
                "grant_mode": p.grant_mode, "compliance_focus": p.compliance_focus,
            }
    return index


def _match_permission(index, api):
    """按完整权限名精确匹配权限知识"""
    if not api:
        return None
    return index.get(api.strip().lower())


@router.get("/{tid}/events")
def list_events(tid: int, event_type: str = None, scenario_id: int = None,
                data_type: str = None, sdk_id: int = None,
                page: int = 1, page_size: int = 50,
                user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    from sqlalchemy import func, or_
    from app.models.kb import KBComponentFingerprint

    def apply_base_filters(query):
        query = query.filter(DetectionEvent.task_id == tid)
        if event_type:
            query = query.filter(DetectionEvent.event_type == event_type)
        if scenario_id:
            query = query.filter(DetectionEvent.scenario_id == scenario_id)
        if data_type:
            query = query.filter(DetectionEvent.data_type == data_type)
        return query

    index = _load_sdk_match_index(db)
    perm_index = _load_permission_index(db)

    # 本任务命中的 SDK 汇总（不受 sdk_id 过滤影响，供筛选下拉与统计）
    matched_map = {}
    for caller, api in apply_base_filters(
            db.query(DetectionEvent.caller, DetectionEvent.api)).all():
        comp = _match_sdk(index, caller, api)
        if comp:
            entry = matched_map.setdefault(comp["id"], {**comp, "count": 0})
            entry["count"] += 1
    matched_sdks = sorted(matched_map.values(), key=lambda x: x["count"], reverse=True)

    q = apply_base_filters(db.query(DetectionEvent))

    # 按 SDK 过滤：命中该组件包名/类名前缀的事件
    if sdk_id:
        prefixes = [r[0] for r in db.query(KBComponentFingerprint.normalized_value).filter(
            KBComponentFingerprint.component_id == sdk_id,
            KBComponentFingerprint.fingerprint_type.in_(["PACKAGE_PREFIX", "CLASS"]),
            KBComponentFingerprint.is_negative == False).all() if r[0]]
        if prefixes:
            conds = []
            for p in prefixes:
                lp = p.strip().lower() + "%"
                conds.append(func.lower(DetectionEvent.caller).like(lp))
                conds.append(func.lower(DetectionEvent.api).like(lp))
            q = q.filter(or_(*conds))
        else:
            q = q.filter(DetectionEvent.id == 0)

    total = q.count()
    items = q.order_by(DetectionEvent.timestamp.asc()).offset((page-1)*page_size).limit(page_size).all()
    return {"code": 0, "data": {
        "items": [{
            "id": e.id, "event_uid": e.event_uid, "scenario_id": e.scenario_id,
            "event_type": e.event_type, "timestamp": str(e.timestamp),
            "consent_status": e.consent_status, "data_type": e.data_type,
            "api": e.api, "caller": e.caller, "trace_id": e.trace_id,
            "engine": e.engine_name, "engine_version": e.engine_version,
            "sdk": _match_sdk(index, e.caller, e.api),
            "permission": _match_permission(perm_index, e.api),
            "event_data": e.event_data
        } for e in items],
        "total": total, "page": page, "page_size": page_size,
        "matched_sdks": matched_sdks
    }}


@router.get("/{tid}/observations")
def task_observations(tid: int, engine_type: str = None, page: int = 1, page_size: int = 50,
                      observation_type: str = None, result_semantics: str = None,
                      user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """任务统一观察结果，可按引擎、观察类型、结果语义过滤。

    `result_semantics=supporting_evidence` 用来取「引擎检出但平台未核实」的线索。
    """
    from app.models import EngineObservation
    q = db.query(EngineObservation).filter(EngineObservation.task_id == tid)
    if engine_type:
        q = q.filter(EngineObservation.engine_type == engine_type)
    if observation_type:
        q = q.filter(EngineObservation.observation_type == observation_type)
    if result_semantics:
        q = q.filter(EngineObservation.result_semantics == result_semantics)
    total = q.count()
    items = q.order_by(EngineObservation.id).offset((page - 1) * page_size).limit(page_size).all()
    return {"code": 0, "data": {
        "items": [{
            "id": o.id, "execution_id": o.execution_id, "engine_type": o.engine_type,
            "observation_type": o.observation_type, "rule_code": o.rule_code,
            "rule_version": o.rule_version, "category": o.category,
            "severity": o.severity, "confidence": o.confidence,
            "evidence_level": o.evidence_level,
            "subject": o.subject, "location": o.location,
            "payload": o.payload, "schema_version": o.schema_version,
            # 平台语义字段：前端按引擎分区展示时要靠它们分组与标注
            "data_category": o.data_category, "sink_type": o.sink_type,
            "result_semantics": o.result_semantics, "observation_kind": o.observation_kind,
            "provider_rule_id": o.provider_rule_id, "provider_level": o.provider_level,
        } for o in items],
        "total": total, "page": page, "page_size": page_size,
    }}


@router.get("/{tid}/platform-findings")
def task_platform_findings(tid: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """平台风险结论（Platform Finding），区别于旧的 Finding 表。"""
    from app.models import PlatformFinding
    from app.services.finding_service import generate_findings
    generate_findings(db, tid)
    rows = db.query(PlatformFinding).filter(PlatformFinding.task_id == tid).all()
    return {"code": 0, "data": {
        "items": [{
            "id": f.id, "finding_uid": f.finding_uid, "finding_code": f.finding_code, "title": f.title,
            "category": f.category, "severity": f.severity, "confidence": f.confidence,
            "triage_status": f.triage_status, "baseline_state": f.baseline_state,
            "recommendation": f.recommendation, "observation_count": f.observation_count,
            "masvs_controls": f.masvs_controls, "maswe_ids": f.maswe_ids, "mastg_test_ids": f.mastg_test_ids,
            # 历史结论可复现：结论 ID 与生成时的规则快照必须对外可见
            "rule_snapshot": f.rule_snapshot,
            "correlation_rule_id": f.correlation_rule_id,
            "correlation_rule_version": f.correlation_rule_version,
            "schema_version": f.schema_version,
        } for f in rows],
        "total": len(rows),
    }}


@router.get("/{tid}/artifacts")
def task_artifacts(tid: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """任务原始制品列表。"""
    from app.models import EngineArtifact, EngineExecution
    rows = db.query(EngineArtifact).join(
        EngineExecution, EngineArtifact.execution_id == EngineExecution.id
    ).filter(EngineExecution.task_id == tid).all()
    return {"code": 0, "data": [{
        "id": a.id, "execution_id": a.execution_id, "artifact_type": a.artifact_type,
        "artifact_uri": a.artifact_uri, "sha256": a.sha256, "size": a.size,
        "content_type": a.content_type, "storage_backend": a.storage_backend,
    } for a in rows]}


@router.get("/{tid}/scenarios")
def list_scenarios(tid: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    scenarios = db.query(DetectionScenario).filter(DetectionScenario.task_id == tid).all()
    return {"code": 0, "data": [
        {"id": s.id, "scenario_type": s.scenario_type, "consent_status": s.consent_status,
         "status": s.status, "started_at": str(s.started_at) if s.started_at else None,
         "completed_at": str(s.completed_at) if s.completed_at else None,
         "notes": s.notes} for s in scenarios
    ]}


@router.put("/{tid}/scenarios/{sid}")
def update_scenario(tid: int, sid: int, req: ScenarioUpdate,
                    user: User = Depends(require_permission("task:write")),
                    db: Session = Depends(get_db)):
    s = db.query(DetectionScenario).get(sid)
    if not s or s.task_id != tid:
        raise HTTPException(status_code=404, detail="场景不存在")
    if req.status: s.status = req.status
    if req.consent_status: s.consent_status = req.consent_status
    if req.notes is not None: s.notes = req.notes
    if req.operator_id: s.operator_id = req.operator_id
    if req.status == "running" and not s.started_at:
        s.started_at = datetime.now(timezone.utc)
    if req.status == "completed":
        s.completed_at = datetime.now(timezone.utc)
    db.commit()
    return {"code": 0, "data": {"id": s.id, "status": s.status}}


@router.get("/{tid}/findings")
def task_findings(tid: int, user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    findings = db.query(Finding).filter(Finding.task_id == tid).all()
    return {"code": 0, "data": [
        {"id": f.id, "finding_uid": f.finding_uid, "title": f.title,
         "severity": f.severity, "status": f.status, "data_type": f.data_type,
         "created_at": str(f.created_at)} for f in findings
    ]}


@router.get("/{tid}/evidence")
def task_evidence(tid: int, evidence_type: str = None,
                  user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    q = db.query(Evidence).filter(Evidence.task_id == tid)
    if evidence_type:
        q = q.filter(Evidence.evidence_type == evidence_type)
    items = q.order_by(Evidence.created_at.desc()).all()
    return {"code": 0, "data": [
        {"id": e.id, "evidence_uid": e.evidence_uid, "evidence_type": e.evidence_type,
         "artifact_hash": e.artifact_hash[:16] if e.artifact_hash else None,
         "artifact_size": e.artifact_size,
         "metadata_json": e.metadata_json, "created_at": str(e.created_at)} for e in items
    ]}


# ============ 任务检测报告汇总 ============

@router.get("/{tid}/compliance-profile")
def task_compliance_profile(tid: int, user: User = Depends(get_current_user),
                            db: Session = Depends(get_db)):
    """这个 App 的隐私合规画像。

    各引擎的结果在这里被合并、去重、并**归因到收集主体**（应用自身 / 某个第三方组件 /
    未识别三方包）—— 单看任何一个引擎都答不出「谁在采集我的数据」。结构照
    T/GZHLW 团体标准第 4 章《App 检测详情》。
    """
    from app.services.compliance_profile import load_profile

    task = db.query(DetectionTask).get(tid)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    return {"code": 0, "data": load_profile(db, task)}


MAX_ENGINE_REPORT_BYTES = 2 * 1024 * 1024


@router.get("/{tid}/observations/{oid}/engine-report")
def observation_engine_report(tid: int, oid: int, user: User = Depends(get_current_user),
                              db: Session = Depends(get_db)):
    """引擎为该条命中生成的报告，解析成结构化数据。

    **只返回文本，不返回 HTML**：报告内容来自被检 APK（类名、方法名、字符串），
    是不可信输入，把引擎生成的 HTML 直接交给浏览器渲染等于把 XSS 面开给样本。
    前端用自家组件渲染这里返回的结构化代码。
    """
    from app.services.appshark_report import (find_report_file, parse_report,
                                              report_name_from_url)

    obs = db.query(EngineObservation).filter(
        EngineObservation.id == oid, EngineObservation.task_id == tid).first()
    if not obs:
        raise HTTPException(status_code=404, detail="观察不存在")

    report_name = report_name_from_url((obs.payload or {}).get("url"))
    if not report_name:
        raise HTTPException(status_code=404, detail="该观察没有对应的引擎报告")

    path = find_report_file(db, tid, report_name)
    if not path:
        raise HTTPException(status_code=404, detail="引擎报告文件不在证据库中")
    if path.stat().st_size > MAX_ENGINE_REPORT_BYTES:
        raise HTTPException(status_code=413, detail="引擎报告过大，不予内联展示")

    parsed = parse_report(path.read_text(encoding="utf-8", errors="replace"))
    return {"code": 0, "data": {
        "report_name": report_name,
        "provider_rule_id": obs.provider_rule_id or (obs.payload or {}).get("rule"),
        "fields": parsed["fields"],
        "rule": parsed["rule"],
        "code_blocks": parsed["code_blocks"],
    }}


@router.get("/{tid}/report-overview")
def task_report_overview(tid: int, user: User = Depends(get_current_user),
                         db: Session = Depends(get_db)):
    """任务检测报告汇总：聚合各引擎结果（基础信息/组件/权限/SDK识别/数据流/事件统计）"""
    from app.services import sdk_analysis

    t = db.query(DetectionTask).get(tid)
    if not t:
        raise HTTPException(status_code=404, detail="任务不存在")
    version = db.query(AppVersion).get(t.app_version_id)
    app = version.app if version else None

    events = db.query(DetectionEvent).filter(DetectionEvent.task_id == tid).all()

    events_by_type: dict = {}
    components: dict = {}
    permissions_declared: list = []
    permissions_sensitive: list = []
    data_flow_map: dict = {}
    api_call_map: dict = {}
    basic_info: dict = {}
    appshark_overview = None

    for e in events:
        events_by_type[e.event_type] = events_by_type.get(e.event_type, 0) + 1
        if e.event_type == "static_component":
            key = e.data_type or "UNKNOWN"
            components[key] = components.get(key, 0) + 1
        elif e.event_type == "static_permission":
            if e.api:
                permissions_declared.append(e.api)
        elif e.event_type == "static_sensitive_permission":
            if e.api:
                permissions_sensitive.append(e.api)
        elif e.event_type == "static_data_flow":
            ed = e.event_data or {}
            key = (e.data_type or "-", ed.get("rule") or "-")
            data_flow_map[key] = data_flow_map.get(key, 0) + 1
        elif e.event_type == "static_sensitive_api":
            key = (e.data_type or "-", e.api or "-")
            entry = api_call_map.setdefault(key, {"count": 0, "callers": set()})
            entry["count"] += 1
            if e.caller:
                entry["callers"].add(e.caller)
        elif e.event_type == "static_basic_info":
            if e.data_type == "appshark_scan":
                appshark_overview = e.event_data
            elif e.event_data:
                basic_info.update(e.event_data)

    # 引擎执行情况
    engines = [{
        "engine_name": display_name(db, x.engine_type), "engine_type": x.engine_type,
        "engine_version": x.engine_version, "status": x.status,
        "event_count": x.event_count, "artifact_count": x.artifact_count,
        "duration_ms": x.duration_ms, "error_message": x.error_message,
        "summary": x.result_summary,
    } for x in db.query(EngineExecution).filter(
        EngineExecution.task_id == tid).order_by(EngineExecution.id).all()]

    # 问题统计
    findings = db.query(Finding).filter(Finding.task_id == tid).all()
    finding_by_severity: dict = {}
    for f in findings:
        finding_by_severity[f.severity] = finding_by_severity.get(f.severity, 0) + 1

    # SDK 识别(已识别/未识别)
    sdk_hits = sdk_analysis.get_hits(db, t)
    clusters = sdk_analysis.get_clusters(db, t)

    # 权限关联知识库(能力说明/风险等级/类别)
    perm_index = _load_permission_index(db)

    def _perm_detail(name: str) -> dict:
        key = name.strip().lower()
        kb = perm_index.get(key)
        if kb is None and "." not in name:
            # 部分引擎上报的是短名(ACCESS_FINE_LOCATION), 补全前缀再匹配
            kb = perm_index.get(f"android.permission.{key}")
        kb = kb or {}
        full_name = kb.get("permission_name") or (
            name if "." in name else f"android.permission.{name}")
        return {"name": full_name, "capability": kb.get("capability"),
                "risk_level": kb.get("risk_level"), "category": kb.get("category")}

    return {"code": 0, "data": {
        "task": {
            "id": t.id, "task_code": t.task_code, "status": t.status,
            "detection_type": t.detection_type, "rule_pack_version": t.rule_pack_version,
            "started_at": str(t.started_at) if t.started_at else None,
            "completed_at": str(t.completed_at) if t.completed_at else None,
            # 报告必须能说清「这次分析算不算数」，否则 0 条结论会被读成「未发现风险」
            "analysis_coverage": t.analysis_coverage,
            "coverage_detail": t.coverage_detail or {},
        },
        "app": {
            "name": app.app_name if app else None,
            "package_name": app.package_name if app else None,
            "version_name": version.version_name if version else None,
            "version_code": version.version_code if version else None,
            "sha256": version.sha256 if version else None,
            "file_size": version.file_size if version else None,
            "min_sdk": version.min_sdk if version else None,
            "target_sdk": version.target_sdk if version else None,
        },
        "basic_info": basic_info,
        "engines": engines,
        "components": {
            "by_type": components,
            "total": sum(components.values()),
        },
        "permissions": {
            "declared": [_perm_detail(n) for n in sorted(set(permissions_declared))],
            "sensitive": [_perm_detail(n) for n in sorted(set(permissions_sensitive))],
        },
        "events_by_type": events_by_type,
        "event_total": len(events),
        "data_flows": [
            {"category": k[0], "rule": k[1], "count": v}
            for k, v in sorted(data_flow_map.items(), key=lambda x: -x[1])
        ],
        "sensitive_apis": [
            {"category": k[0], "api": k[1], "count": v["count"],
             "callers": sorted(v["callers"])[:5]}
            for k, v in sorted(api_call_map.items(), key=lambda x: -x[1]["count"])
        ],
        "appshark_overview": appshark_overview,
        "sdk": {
            "identified": sdk_hits,
            "unidentified": clusters,
            "identified_count": len(sdk_hits),
            "unidentified_count": len(clusters),
        },
        "findings": {"total": len(findings), "by_severity": finding_by_severity},
        "scenario_count": db.query(DetectionScenario).filter(
            DetectionScenario.task_id == tid).count(),
        "evidence_count": db.query(Evidence).filter(Evidence.task_id == tid).count(),
    }}


# ============ SDK识别分析 ============

@router.get("/{tid}/sdk-hits")
def task_sdk_hits(tid: int, refresh: bool = False,
                  user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """SDK识别结果：一个SDK一条聚合记录"""
    from app.services import sdk_analysis
    task = db.query(DetectionTask).get(tid)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    sdk_analysis.analyze_task(db, task, refresh=refresh)
    return {"code": 0, "data": sdk_analysis.get_hits(db, task)}


@router.get("/{tid}/sdk-hits/{hit_id}")
def task_sdk_hit_detail(tid: int, hit_id: int,
                        user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """SDK命中详情：证据汇总 + 证据明细（反关联事件流）"""
    from app.services import sdk_analysis
    task = db.query(DetectionTask).get(tid)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    detail = sdk_analysis.get_hit_detail(db, task, hit_id)
    if not detail:
        raise HTTPException(status_code=404, detail="命中记录不存在")
    return {"code": 0, "data": detail}


@router.post("/{tid}/sdk-hits/{hit_id}/review")
def review_sdk_hit(tid: int, hit_id: int, req: dict,
                   user: User = Depends(require_permission("task:write")),
                   db: Session = Depends(get_db)):
    """人工标记SDK命中: reject(误报) / whitelist(白名单) / confirm(确认)"""
    from app.models.kb import ScanComponentHit
    from app.services import sdk_analysis
    task = db.query(DetectionTask).get(tid)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    job = sdk_analysis.ensure_scan_job(db, task)
    hit = db.query(ScanComponentHit).get(hit_id)
    if not hit or hit.scan_job_id != job.id:
        raise HTTPException(status_code=404, detail="命中记录不存在")
    action = (req.get("action") or "").lower()
    status_map = {"reject": "REJECTED", "whitelist": "WHITELISTED", "confirm": "CONFIRMED"}
    if action not in status_map:
        raise HTTPException(status_code=400, detail="不支持的标记动作")
    hit.hit_status = status_map[action]
    db.commit()
    return {"code": 0, "data": {"hit_id": hit.id, "hit_status": hit.hit_status}}


@router.get("/{tid}/package-clusters")
def task_package_clusters(tid: int, refresh: bool = False,
                          user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """未识别包簇列表"""
    from app.services import sdk_analysis
    task = db.query(DetectionTask).get(tid)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    sdk_analysis.analyze_task(db, task, refresh=refresh)
    return {"code": 0, "data": sdk_analysis.get_clusters(db, task)}


@router.get("/{tid}/package-clusters/{cid}/classes")
def cluster_classes(tid: int, cid: int,
                    user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """包簇下全部类和组件（来自事件流）"""
    from app.models.kb import ScanPackageCluster
    from app.services import sdk_analysis
    task = db.query(DetectionTask).get(tid)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    job = sdk_analysis.ensure_scan_job(db, task)
    cluster = db.query(ScanPackageCluster).get(cid)
    if not cluster or cluster.scan_job_id != job.id:
        raise HTTPException(status_code=404, detail="包簇不存在")
    events = db.query(DetectionEvent).filter(
        DetectionEvent.task_id == tid,
        DetectionEvent.event_type == "static_component",
        DetectionEvent.api.like(cluster.package_prefix + ".%"),
    ).order_by(DetectionEvent.api).all()
    return {"code": 0, "data": {
        "package_prefix": cluster.package_prefix,
        "classes": [{"event_id": e.id, "class_name": e.api,
                     "component_type": e.data_type} for e in events],
    }}


@router.post("/{tid}/package-clusters/{cid}/review")
def review_cluster(tid: int, cid: int, req: dict,
                   user: User = Depends(require_permission("task:write")),
                   db: Session = Depends(get_db)):
    """包簇人工处理: self_code/link/create/whitelist/packer"""
    from app.models.kb import ScanPackageCluster, KBComponent, KBComponentFingerprint
    from app.services import sdk_analysis
    task = db.query(DetectionTask).get(tid)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")
    job = sdk_analysis.ensure_scan_job(db, task)
    cluster = db.query(ScanPackageCluster).get(cid)
    if not cluster or cluster.scan_job_id != job.id:
        raise HTTPException(status_code=404, detail="包簇不存在")

    action = (req.get("action") or "").lower()
    raw = dict(cluster.raw_data or {})

    if action in ("self_code", "whitelist", "packer"):
        raw["review_status"] = action
    elif action == "link":
        comp_id = req.get("component_id")
        comp = db.query(KBComponent).get(comp_id) if comp_id else None
        if not comp:
            raise HTTPException(status_code=400, detail="请选择要关联的SDK组件")
        cluster.matched_component_id = comp.id
        raw["review_status"] = "linked"
    elif action == "create":
        name = (req.get("name") or cluster.package_prefix).strip()
        comp = KBComponent(
            component_key=generate_uid("comp"), name=name,
            normalized_name=name.lower(),
            component_kind=req.get("kind") or "SDK",
            verification_status="PENDING",
        )
        db.add(comp)
        db.flush()
        db.add(KBComponentFingerprint(
            component_id=comp.id, fingerprint_type="PACKAGE_PREFIX",
            value=cluster.package_prefix,
            normalized_value=cluster.package_prefix.lower(),
            match_mode="PREFIX", weight=30, evidence_role="PRIMARY",
        ))
        cluster.matched_component_id = comp.id
        raw["review_status"] = "linked"
    else:
        raise HTTPException(status_code=400, detail="不支持的处理动作")

    raw["reviewed_by"] = user.username
    raw["reviewed_at"] = datetime.now(timezone.utc).isoformat()
    cluster.raw_data = raw
    db.commit()
    return {"code": 0, "data": {"id": cluster.id, "review_status": raw["review_status"],
                                "linked_component_id": cluster.matched_component_id}}
