"""Agent通信路由"""
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.security import generate_uid
from app.core.storage import storage
from app.models import (AgentNode, Device, DetectionTask, SubTask,
                        DetectionEvent, DetectionScenario, Evidence)
from app.schemas import (AgentRegister, AgentHeartbeat, AgentProgress,
                         AgentEventBatch, AgentResult)
from datetime import datetime, timezone
import logging

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Agent通信"])


@router.post("/register")
def agent_register(req: AgentRegister, db: Session = Depends(get_db)):
    """Agent注册"""
    node = None
    if req.agent_id:
        node = db.query(AgentNode).filter(AgentNode.node_uid == req.agent_id).first()
    
    if not node:
        node_uid = req.agent_id or generate_uid("agt")
        node = AgentNode(
            node_uid=node_uid,
            node_name=req.node_name,
            node_type=req.node_type,
            status="online",
            capabilities=req.capabilities,
            tools_info=req.tools_info
        )
        db.add(node)
        db.commit()
        db.refresh(node)
    else:
        node.status = "online"
        node.node_name = req.node_name
        node.capabilities = req.capabilities
        node.tools_info = req.tools_info
        node.last_heartbeat_at = datetime.now(timezone.utc)
        db.commit()

    # 注册设备
    for dev_info in req.devices:
        serial = dev_info.get("serial")
        if serial:
            dev = db.query(Device).filter(Device.serial == serial).first()
            if not dev:
                dev = Device(
                    agent_id=node.id, serial=serial,
                    brand=dev_info.get("brand"), model=dev_info.get("model"),
                    android_version=dev_info.get("android_version"),
                    is_rooted=dev_info.get("is_rooted", False),
                    is_frida_ready=dev_info.get("is_frida_ready", False),
                    status="idle"
                )
                db.add(dev)
            else:
                dev.agent_id = node.id
                dev.status = "idle"
                dev.last_seen_at = datetime.now(timezone.utc)
            db.commit()

    return {"code": 0, "data": {
        "agent_id": node.node_uid,
        "registered": True,
        "heartbeat_interval": 15
    }}


@router.post("/heartbeat")
def agent_heartbeat(req: AgentHeartbeat, db: Session = Depends(get_db)):
    """Agent心跳"""
    node = db.query(AgentNode).filter(AgentNode.node_uid == req.agent_id).first()
    if not node:
        raise HTTPException(status_code=404, detail="Agent未注册")

    node.last_heartbeat_at = datetime.now(timezone.utc)
    node.status = "busy" if req.status == "busy" else "online"
    db.commit()

    # 更新设备状态
    for dev_info in req.devices:
        serial = dev_info.get("serial")
        if serial:
            dev = db.query(Device).filter(Device.serial == serial).first()
            if dev:
                dev.status = dev_info.get("status", "idle").lower()
                dev.last_seen_at = datetime.now(timezone.utc)

    db.commit()

    # 返回待处理任务和指令
    pending_tasks = db.query(SubTask).filter(
        SubTask.assigned_node_id == node.id,
        SubTask.status == "pending"
    ).limit(5).all()

    return {"code": 0, "data": {
        "pending_tasks": [{"sub_task_id": st.id, "task_id": st.task_id,
                           "engine_type": st.engine_type} for st in pending_tasks],
        "cancel_tasks": [],
        "commands": []
    }}


@router.post("/tasks/{tid}/progress")
def agent_progress(tid: int, req: AgentProgress, db: Session = Depends(get_db)):
    """Agent上报进度"""
    sub_task = db.query(SubTask).get(req.sub_task_id)
    if sub_task and sub_task.task_id == tid:
        sub_task.stage = req.stage
        db.commit()

    task = db.query(DetectionTask).get(tid)
    if task and req.stage:
        # 映射Agent stage到任务状态
        stage_map = {
            "RUNNING_DYNAMIC": "running_dynamic",
            "WAITING_DYNAMIC": "waiting_dynamic",
            "ANALYZING": "analyzing",
        }
        if req.stage in stage_map:
            task.status = stage_map[req.stage]
            db.commit()

    return {"code": 0}


@router.post("/tasks/{tid}/events")
def agent_events(tid: int, req: AgentEventBatch, db: Session = Depends(get_db)):
    """Agent上报事件 (批量)"""
    task = db.query(DetectionTask).get(tid)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")

    created = 0
    for evt in req.events:
        event = DetectionEvent(
            event_uid=evt.event_uid or generate_uid("evt"),
            task_id=tid,
            scenario_id=evt.scenario_id,
            event_type=evt.event_type,
            timestamp=evt.timestamp,
            consent_status=evt.consent_status,
            data_type=evt.data_type,
            api=evt.api,
            caller=evt.caller,
            trace_id=evt.trace_id,
            value_fingerprint=evt.value_fingerprint,
            event_data=evt.event_data,
            engine_name=evt.engine_name,
            engine_version=evt.engine_version
        )
        db.add(event)
        created += 1

    db.commit()
    return {"code": 0, "data": {"created": created}}


@router.post("/tasks/{tid}/evidence")
async def agent_upload_evidence(tid: int,
                                 file: UploadFile = File(...),
                                 evidence_type: str = Form(...),
                                 scenario_id: int = Form(None),
                                 metadata: str = Form("{}"),
                                 db: Session = Depends(get_db)):
    """Agent上传证据文件"""
    import json
    task = db.query(DetectionTask).get(tid)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")

    upload_result = await storage.save_upload(file, task_id=tid, subdir=evidence_type)

    meta = {}
    try:
        meta = json.loads(metadata)
    except Exception:
        pass
    if scenario_id:
        meta["scenario_id"] = scenario_id

    evidence = Evidence(
        evidence_uid=generate_uid("evi"),
        task_id=tid,
        evidence_type=evidence_type,
        artifact_path=upload_result["path"],
        artifact_hash=upload_result["hash"],
        artifact_size=upload_result["size"],
        metadata_json=meta
    )
    db.add(evidence)
    db.commit()
    db.refresh(evidence)

    return {"code": 0, "data": {
        "evidence_id": evidence.id,
        "evidence_uid": evidence.evidence_uid,
        "artifact_hash": evidence.artifact_hash
    }}


@router.post("/tasks/{tid}/result")
def agent_result(tid: int, req: AgentResult, db: Session = Depends(get_db)):
    """Agent上报最终结果"""
    task = db.query(DetectionTask).get(tid)
    if not task:
        raise HTTPException(status_code=404, detail="任务不存在")

    if req.status == "completed":
        task.status = "analyzing"
    elif req.status == "failed":
        task.status = "failed"
        task.failed_reason = req.error_message

    task.completed_at = datetime.now(timezone.utc)
    db.commit()

    return {"code": 0}
