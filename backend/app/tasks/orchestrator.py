"""任务编排服务"""
from sqlalchemy.orm import Session
from app.models import (DetectionTask, SubTask, DetectionScenario, AppVersion,
                        AgentNode, Device, EngineExecution)
from app.core.security import generate_uid
from app.core.redis import redis_client, TASK_STREAM
from app.services.task_config import normalize_task_config, enabled_engine_types
from datetime import datetime, timezone
import json


class TaskOrchestrator:
    """任务编排: 创建子任务、调度、推进状态"""

    def __init__(self, db: Session):
        self.db = db

    # 检测类型 → 是否需要动态检测
    DYNAMIC_TYPES = {"full", "consent_pre", "sdk_audit"}
    # 同意前专项 → 只跑 first_launch + rejected
    TYPE_SCENARIOS = {
        "full": ["first_launch", "rejected", "consented"],
        "consent_pre": ["first_launch", "rejected"],
        "sdk_audit": ["first_launch"],
    }

    def submit_task(self, task: DetectionTask):
        """提交任务: 根据检测类型创建子任务和场景, 推入队列"""
        config = normalize_task_config(task.config_json or {})
        task.config_json = config
        det_type = task.detection_type

        # 始终创建静态检测子任务
        static_subtask = SubTask(
            sub_task_code=generate_uid("st"),
            task_id=task.id,
            engine_type="static",
            stage="prepare",
            status="pending",
            config_json={
                "detection_type": det_type,
                "rule_pack_version": task.rule_pack_version
            }
        )
        self.db.add(static_subtask)

        # 只有需要动态检测的类型才创建动态场景和子任务
        scenarios = []
        dynamic_subtask = None

        if det_type in self.DYNAMIC_TYPES:
            # 场景来源：用户配置优先，否则用类型默认值
            user_scenarios = config.get("dynamic_scenarios")
            if user_scenarios:
                dynamic_scenarios = user_scenarios
            else:
                dynamic_scenarios = self.TYPE_SCENARIOS.get(det_type, [])

            scenario_map = {
                "first_launch": ("first_launch", "NOT_PRESENTED"),
                "rejected": ("rejected", "REJECTED"),
                "consented": ("consented", "CONSENTED"),
                "function_trigger": ("function_trigger", "CONSENTED"),
                "revoked": ("revoked", "REVOKED"),
                "account_cancel": ("account_cancel", "CONSENTED"),
            }

            for scn_type in dynamic_scenarios:
                if scn_type in scenario_map:
                    s_type, consent = scenario_map[scn_type]
                    scenario = DetectionScenario(
                        task_id=task.id,
                        scenario_type=s_type,
                        consent_status=consent,
                        status="pending"
                    )
                    self.db.add(scenario)
                    scenarios.append(scenario)

            self.db.flush()

            if scenarios:
                dynamic_subtask = SubTask(
                    sub_task_code=generate_uid("st"),
                    task_id=task.id,
                    engine_type="dynamic",
                    stage="prepare",
                    status="pending",
                    config_json={
                        "scenario_ids": [s.id for s in scenarios],
                        "device_requirements": config.get("device_requirements", {})
                    }
                )
                self.db.add(dynamic_subtask)
        else:
            self.db.flush()

        # 为本次提交选定的静态引擎创建 pending 执行记录，供队列展示"等待/执行中"
        from app.engine.worker import ENGINE_REGISTRY
        from app.services.engine_config import display_name
        engine_types = enabled_engine_types(config, ENGINE_REGISTRY.keys())
        self.db.flush()
        for et in engine_types:
            self.db.add(EngineExecution(
                task_id=task.id,
                sub_task_id=static_subtask.id,
                engine_type=et,
                engine_name=display_name(self.db, et),
                engine_version=ENGINE_REGISTRY[et]["version"],
                status="queued",
                stage="queued",
                queued_at=datetime.now(timezone.utc),
            ))

        # 更新任务状态
        task.status = "queued"
        task.started_at = datetime.now(timezone.utc)
        self.db.commit()

        # 推入Redis队列
        redis_client.xadd(TASK_STREAM, {
            "task_id": str(task.id),
            "task_code": task.task_code,
            "detection_type": task.detection_type,
            "priority": str(task.priority),
            "created_at": datetime.now(timezone.utc).isoformat()
        })

    def dispatch_task(self, task: DetectionTask):
        """重新分发任务"""
        redis_client.xadd(TASK_STREAM, {
            "task_id": str(task.id),
            "task_code": task.task_code,
            "detection_type": task.detection_type,
            "priority": str(task.priority),
            "created_at": datetime.now(timezone.utc).isoformat()
        })

    def update_task_status(self, task_id: int, status: str, reason: str = None):
        """更新任务状态"""
        task = self.db.query(DetectionTask).get(task_id)
        if not task:
            return
        
        task.status = status
        if status in ["completed", "failed", "canceled"]:
            task.completed_at = datetime.now(timezone.utc)
        if reason:
            task.failed_reason = reason
        elif status == "running_static":
            task.started_at = task.started_at or datetime.now(timezone.utc)
        self.db.commit()

    def assign_node(self, sub_task_id: int, node_id: int):
        """分配节点给子任务"""
        sub_task = self.db.query(SubTask).get(sub_task_id)
        if sub_task:
            sub_task.assigned_node_id = node_id
            sub_task.status = "running"
            sub_task.started_at = datetime.now(timezone.utc)
            self.db.commit()
