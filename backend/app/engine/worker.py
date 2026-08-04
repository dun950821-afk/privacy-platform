"""
引擎 Worker 服务
- 消费 Redis Streams 任务队列
- 调用对应引擎适配器执行检测
- 将结果标准化为统一事件写入数据库
- 记录引擎执行日志
"""
import sys
import os
import json
import time
import asyncio
import logging
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core.database import SessionLocal
from app.core.redis import redis_client, TASK_STREAM, STATIC_WORKER_GROUP
from app.core.storage import storage
from app.core.security import generate_uid
from app.models import (
    DetectionTask, SubTask, DetectionEvent, Evidence,
    AgentNode, EngineExecution, AppVersion, DetectionScenario
)
from app.engine.adapters import AndroguardAdapter, AppSharkAdapter, MobSFAdapter

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("engine-worker")

# 引擎注册表
ENGINE_REGISTRY = {
    "androguard": {
        "name": "Androguard",
        "version": "4.1.4",
        "adapter": AndroguardAdapter,
        "capabilities": ["BASIC_INFO", "PERMISSIONS", "COMPONENTS", "SIGNATURE", "STRINGS"],
        "description": "APK基础解析：包名、版本、权限、组件、签名、字符串",
        "install_guide": "pip install androguard",
        "installed": True,
    },
    "appshark": {
        "name": "AppShark",
        "version": "0.1.2",
        "adapter": AppSharkAdapter,
        "capabilities": ["DATA_FLOW", "TAINT_ANALYSIS"],
        "description": "深度污点分析：Source-Sink数据流追踪",
        "install_guide": "部署 /opt/appshark(AppShark-0.1.2-all.jar + config/EngineConfig.json5 + config/tools/platforms)，需 JRE 11+，详见 README 4.1.1",
        "installed": True,
    },
    "mobsf": {
        "name": "MobSF",
        "version": "4.0.0",
        "adapter": MobSFAdapter,
        "capabilities": ["STATIC_SCAN", "MALWARE_CHECK", "TRACKER_DETECTION"],
        "description": "静态扫描：恶意检测、跟踪器识别",
        "install_guide": "docker run -it -p 8000:8000 opensecurity/mobile-security-framework-mobsf",
        "installed": False,
    },
}


class EngineWorker:
    """引擎Worker：消费任务队列并执行检测"""

    def __init__(self, worker_id: str = None, engine_types: list[str] = None):
        self.worker_id = worker_id or f"worker_{os.getpid()}"
        self.engine_types = engine_types or list(ENGINE_REGISTRY.keys())
        self.running = False
        self.current_task = None
        self._ensure_consumer_group()

    def _ensure_consumer_group(self):
        """确保Redis Stream消费者组存在"""
        try:
            redis_client.xgroup_create(TASK_STREAM, STATIC_WORKER_GROUP, id="0", mkstream=True)
            logger.info(f"Created consumer group: {STATIC_WORKER_GROUP}")
        except Exception as e:
            if "BUSYGROUP" in str(e):
                logger.info(f"Consumer group already exists: {STATIC_WORKER_GROUP}")
            else:
                logger.error(f"Failed to create consumer group: {e}")

    async def start(self):
        """启动Worker循环"""
        self.running = True
        logger.info(f"Engine Worker started: {self.worker_id}")
        logger.info(f"Registered engines: {', '.join(self.engine_types)}")

        while self.running:
            try:
                await self._consume_once()
            except asyncio.CancelledError:
                logger.info("Worker cancelled, stopping...")
                break
            except Exception as e:
                logger.error(f"Worker error: {e}", exc_info=True)
                await asyncio.sleep(5)

        logger.info(f"Engine Worker stopped: {self.worker_id}")

    def stop(self):
        """停止Worker"""
        self.running = False

    async def _consume_once(self):
        """消费一条任务"""
        # 非阻塞读取：先检查是否有新消息
        try:
            messages = redis_client.xreadgroup(
                STATIC_WORKER_GROUP,
                self.worker_id,
                {TASK_STREAM: ">"},
                count=1,
                block=5000,
            )
        except Exception as e:
            if "Timeout" in str(e):
                return
            logger.error(f"Redis read error: {e}")
            await asyncio.sleep(5)
            return

        if not messages:
            return

        for stream, msgs in messages:
            for msg_id, fields in msgs:
                try:
                    task_id = int(fields.get(b"task_id", fields.get("task_id", 0)))
                    await self._process_task(task_id)
                    redis_client.xack(TASK_STREAM, STATIC_WORKER_GROUP, msg_id)
                except Exception as e:
                    logger.error(f"Failed to process task: {e}", exc_info=True)
                    redis_client.xack(TASK_STREAM, STATIC_WORKER_GROUP, msg_id)

    async def _process_task(self, task_id: int):
        """处理一个检测任务"""
        db = SessionLocal()
        try:
            task = db.query(DetectionTask).get(task_id)
            if not task:
                logger.warning(f"Task {task_id} not found")
                return

            # 状态守卫：只处理排队中的任务，防止同一任务被重复消费导致结果叠加
            if task.status != "queued":
                logger.warning(f"Task {task_id} status is {task.status}, skip duplicate dispatch")
                return

            logger.info(f"Processing task {task.task_code} (id={task_id})")

            # 幂等清理：重跑前删除该任务上一轮的事件和引擎执行记录
            db.query(DetectionEvent).filter(DetectionEvent.task_id == task_id).delete(synchronize_session=False)
            db.query(EngineExecution).filter(EngineExecution.task_id == task_id).delete(synchronize_session=False)
            db.commit()

            # 获取APK路径
            version = db.query(AppVersion).get(task.app_version_id)
            if not version or not version.artifact_path:
                logger.error(f"APK file not found for task {task_id}")
                self._fail_task(db, task, "APK文件不存在")
                return

            # 更新任务状态
            task.status = "running_static"
            task.started_at = datetime.now(timezone.utc)
            db.commit()

            # 获取或创建静态子任务
            sub_tasks = db.query(SubTask).filter(
                SubTask.task_id == task_id,
                SubTask.engine_type == "static"
            ).all()

            if not sub_tasks:
                # 创建默认静态子任务
                sub_task = SubTask(
                    sub_task_code=generate_uid("st"),
                    task_id=task_id,
                    engine_type="static",
                    stage="prepare",
                    status="pending",
                    config_json={"rule_pack_version": task.rule_pack_version}
                )
                db.add(sub_task)
                db.commit()
                db.refresh(sub_task)
                sub_tasks = [sub_task]

            sub_task = sub_tasks[0]
            sub_task.status = "running"
            sub_task.started_at = datetime.now(timezone.utc)
            db.commit()

            # 依次执行各引擎
            all_events = []
            all_artifacts = []
            engine_results = []

            # 从任务配置中读取用户选择的引擎
            task_config = task.config_json or {}
            selected_engines = task_config.get("engines")
            if selected_engines is not None:
                # 用户显式选择了引擎（包括空列表=不执行任何引擎）
                engine_types_to_run = [e for e in selected_engines if e in ENGINE_REGISTRY]
            else:
                # 未指定引擎 → 执行全部
                engine_types_to_run = self.engine_types

            logger.info(f"Task {task_id} engines to run: {engine_types_to_run}")

            for engine_type in engine_types_to_run:
                engine_info = ENGINE_REGISTRY.get(engine_type)
                if not engine_info:
                    continue

                # 创建执行记录
                execution = EngineExecution(
                    task_id=task_id,
                    sub_task_id=sub_task.id,
                    engine_type=engine_type,
                    engine_name=engine_info["name"],
                    engine_version=engine_info["version"],
                    status="running",
                    stage="prepare",
                    started_at=datetime.now(timezone.utc),
                )
                db.add(execution)
                db.commit()
                db.refresh(execution)

                logger.info(f"  -> Running {engine_info['name']}...")

                # 执行引擎
                start_time = time.time()
                try:
                    adapter = engine_info["adapter"]()
                    from app.engine.base import TaskContext

                    ctx = TaskContext(
                        task_id=task_id,
                        apk_path=version.artifact_path,
                        package_name=version.app.package_name if version.app else "",
                        rule_pack_version=task.rule_pack_version,
                        config=task.config_json or {},
                    )

                    # 检查环境
                    if not adapter.validate_environment():
                        logger.warning(f"  -> {engine_info['name']} environment not ready, skipping")
                        execution.status = "failed"
                        execution.error_message = "运行环境不满足"
                        execution.completed_at = datetime.now(timezone.utc)
                        execution.duration_ms = int((time.time() - start_time) * 1000)
                        db.commit()
                        engine_results.append({
                            "engine": engine_info["name"],
                            "status": "skipped",
                            "reason": "environment_not_ready"
                        })
                        continue

                    # 执行
                    execution.stage = "execute"
                    db.commit()

                    result = await adapter.execute(ctx)

                    # 标准化事件 - result.events 已由适配器生成
                    events = result.events
                    execution.event_count = len(events)
                    execution.artifact_count = len(result.artifacts)
                    execution.stage = "normalize"
                    db.commit()

                    # 写入事件到数据库
                    for evt_data in events:
                        event = DetectionEvent(
                            event_uid=generate_uid("evt"),
                            task_id=task_id,
                            event_type=evt_data.get("event_type", "unknown"),
                            timestamp=datetime.now(timezone.utc),
                            data_type=evt_data.get("data_type"),
                            api=evt_data.get("api"),
                            caller=evt_data.get("caller"),
                            event_data=evt_data.get("event_data", {}),
                            engine_name=engine_info["name"],
                            engine_version=engine_info["version"],
                        )
                        db.add(event)
                        all_events.append(evt_data)

                    # 保存产出物为证据
                    for artifact in result.artifacts:
                        if artifact.get("path") and os.path.exists(artifact["path"]):
                            file_hash = storage.compute_hash(artifact["path"])
                            file_size = os.path.getsize(artifact["path"])
                            evidence = Evidence(
                                evidence_uid=generate_uid("evi"),
                                task_id=task_id,
                                evidence_type="engine_output",
                                artifact_path=artifact["path"],
                                artifact_hash=file_hash,
                                artifact_size=file_size,
                                metadata_json={
                                    "engine": engine_info["name"],
                                    "engine_type": engine_type,
                                    "type": artifact.get("type", "engine_output"),
                                }
                            )
                            db.add(evidence)
                            all_artifacts.append(artifact)

                    # 更新执行记录
                    duration_ms = int((time.time() - start_time) * 1000)
                    execution.status = "completed" if result.success else "failed"
                    execution.error_message = result.error
                    execution.completed_at = datetime.now(timezone.utc)
                    execution.duration_ms = duration_ms
                    execution.result_summary = result.summary
                    execution.raw_output_path = result.raw_output_path
                    db.commit()

                    engine_results.append({
                        "engine": engine_info["name"],
                        "type": engine_type,
                        "status": "completed" if result.success else "failed",
                        "events": len(events),
                        "duration_ms": duration_ms,
                        "summary": result.summary,
                    })

                    logger.info(f"  -> {engine_info['name']} done: {len(events)} events, {duration_ms}ms")

                except Exception as e:
                    duration_ms = int((time.time() - start_time) * 1000)
                    execution.status = "failed"
                    execution.error_message = str(e)
                    execution.completed_at = datetime.now(timezone.utc)
                    execution.duration_ms = duration_ms
                    db.commit()
                    logger.error(f"  -> {engine_info['name']} failed: {e}", exc_info=True)

                    engine_results.append({
                        "engine": engine_info["name"],
                        "type": engine_type,
                        "status": "failed",
                        "error": str(e),
                        "duration_ms": duration_ms,
                    })

            # 更新子任务
            sub_task.status = "completed"
            sub_task.completed_at = datetime.now(timezone.utc)
            sub_task.result_summary = {
                "engines": engine_results,
                "total_events": len(all_events),
                "total_artifacts": len(all_artifacts),
            }
            db.commit()

            # 更新任务状态
            # 检查是否有动态子任务/场景需要执行
            scenarios = db.query(DetectionScenario).filter(
                DetectionScenario.task_id == task_id
            ).all()

            if scenarios:
                task.status = "waiting_dynamic"
                task.completed_at = None
                logger.info(f"Task {task_id} waiting for dynamic detection")
            else:
                # 纯静态任务 → 直接完成
                task.status = "completed"
                task.completed_at = datetime.now(timezone.utc)
                logger.info(f"Task {task_id} completed (static only)")
            db.commit()

            logger.info(f"Task {task_id} static phase done: {len(all_events)} events, {len(all_artifacts)} artifacts")

        finally:
            db.close()

    def _fail_task(self, db, task: DetectionTask, reason: str):
        """标记任务失败"""
        task.status = "failed"
        task.failed_reason = reason
        task.completed_at = datetime.now(timezone.utc)
        db.commit()
        logger.error(f"Task {task.id} failed: {reason}")


def list_engines() -> list[dict]:
    """列出所有已注册引擎"""
    engines = []
    for engine_type, info in ENGINE_REGISTRY.items():
        adapter = info["adapter"]()
        env_ok = adapter.validate_environment()
        engines.append({
            "engine_type": engine_type,
            "name": info["name"],
            "version": info["version"],
            "capabilities": info["capabilities"],
            "description": info["description"],
            "env_ready": env_ok,
            "status": "ready" if env_ok else "not_configured",
            "install_guide": info.get("install_guide", ""),
            "installed": info.get("installed", False),
        })
    return engines


async def run_worker(engine_types: list[str] = None):
    """运行Worker"""
    worker = EngineWorker(engine_types=engine_types)
    try:
        await worker.start()
    except KeyboardInterrupt:
        worker.stop()


if __name__ == "__main__":
    asyncio.run(run_worker())
