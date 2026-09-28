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
from app.engine.errors import AdapterError
from app.engine.repository import (claim_execution, heartbeat_execution, request_cancel,
                                   is_cancel_requested, recover_expired_leases,
                                   find_tasks_with_queued_executions)
from app.services.task_config import enabled_engine_types, resolved_task_config
from app.services.observation_service import event_to_observation, observation_row
from app.engine.artifacts import LocalArtifactStore
from app.core.config import settings as app_settings

ARTIFACT_STORE = LocalArtifactStore(Path(app_settings.STORAGE_ROOT) / "artifacts")
from app.services.engine_config import get_or_create, resolved, public, redacted, get_definition, display_name

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
def build_engine_adapter(db, engine_type: str):
    """根据数据库中的全局配置创建引擎适配器。"""
    info = ENGINE_REGISTRY.get(engine_type)
    if not info:
        raise KeyError(f"引擎类型 {engine_type} 不存在")
    return info["adapter"](resolved(db, engine_type))


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
        self._recover_expired()
        await self._sweep_queued()

        last_recovery = time.time()
        while self.running:
            try:
                await self._consume_once()
                if time.time() - last_recovery > 30:
                    self._recover_expired()
                    await self._sweep_queued()
                    last_recovery = time.time()
            except asyncio.CancelledError:
                logger.info("Worker cancelled, stopping...")
                break
            except Exception as e:
                logger.error(f"Worker error: {e}", exc_info=True)
                await asyncio.sleep(5)

        logger.info(f"Engine Worker stopped: {self.worker_id}")

    async def _sweep_queued(self):
        """数据库轮询待执行任务，弥补 Redis 消息丢失或租约回收后的调度缺口。"""
        db = SessionLocal()
        try:
            task_ids = find_tasks_with_queued_executions(db)
        except Exception as e:
            logger.error(f"Queued task sweep failed: {e}")
            db.close()
            return
        db.close()
        for task_id in task_ids:
            try:
                await self._process_task(task_id)
            except Exception as e:
                logger.error(f"Sweep processing task {task_id} failed: {e}", exc_info=True)

    def _recover_expired(self):
        """回收租约过期的执行，让崩溃后中断的任务重新排队。"""
        db = SessionLocal()
        try:
            recovered = recover_expired_leases(db)
            if recovered:
                logger.warning(f"Recovered {len(recovered)} expired executions: {recovered}")
        except Exception as e:
            logger.error(f"Lease recovery failed: {e}")
        finally:
            db.close()

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

            # 状态守卫：只处理排队中的任务，防止同一任务被重复消费导致结果叠加。
            # 崩溃恢复后任务会回到 queued；已有执行完成的任务其执行记录为终态，会被 claim 跳过。
            if task.status != "queued":
                logger.warning(f"Task {task_id} status is {task.status}, skip duplicate dispatch")
                return

            logger.info(f"Processing task {task.task_code} (id={task_id})")

            # 提交时已创建 pending 执行记录；不要删除它们，否则队列无法展示等待引擎。
            # 仅保留任务重试时残留的旧记录兼容逻辑，由提交流程负责重建。

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
            engine_types_to_run = enabled_engine_types(task_config, self.engine_types)

            logger.info(f"Task {task_id} engines to run: {engine_types_to_run}")

            for engine_type in engine_types_to_run:
                engine_info = ENGINE_REGISTRY.get(engine_type)
                if not engine_info:
                    continue

                # 使用提交时创建的 pending 记录，避免重复创建并保留等待状态。
                execution = db.query(EngineExecution).filter(
                    EngineExecution.task_id == task_id,
                    EngineExecution.sub_task_id == sub_task.id,
                    EngineExecution.engine_type == engine_type,
                ).first()
                if execution is None:
                    execution = EngineExecution(
                        task_id=task_id, sub_task_id=sub_task.id, engine_type=engine_type,
                        engine_name=display_name(db, engine_type), engine_version=engine_info["version"],
                        status="pending", stage="prepare",
                    )
                    db.add(execution)
                execution.engine_name = display_name(db, engine_type)
                lease = claim_execution(db, execution.id, self.worker_id, lease_seconds=60)
                if not lease:
                    logger.warning(f"  -> {engine_type} claim failed, another worker owns execution")
                    continue
                execution = db.query(EngineExecution).get(execution.id)
                execution.status = "running"
                execution.stage = "prepare"
                execution.started_at = datetime.now(timezone.utc)
                db.commit()
                db.refresh(execution)

                logger.info(f"  -> Running {engine_info['name']}...")

                # 执行引擎
                start_time = time.time()
                try:
                    adapter = build_engine_adapter(db, engine_type)
                    execution.config_json = redacted(db, engine_type)
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
                        execution.error_code = "ENGINE_ENV_INVALID"
                        execution.error_message = "运行环境不满足"
                        execution.completed_at = datetime.now(timezone.utc)
                        execution.duration_ms = int((time.time() - start_time) * 1000)
                        db.commit()
                        engine_results.append({
                            "engine": display_name(db, engine_type),
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

                    # 写入事件和统一 Observation
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
                            engine_name=display_name(db, engine_type),
                            engine_version=engine_info["version"],
                        )
                        db.add(event)
                        observation_data = event_to_observation(evt_data, task_id=task_id, execution_id=execution.id, engine_type=engine_type, engine_version=engine_info["version"])
                        db.add(observation_row(observation_data))
                        all_events.append(evt_data)

                    # 保存产出物为证据
                    for artifact in result.artifacts:
                        if artifact.get("path") and os.path.exists(artifact["path"]):
                            file_hash = storage.compute_hash(artifact["path"])
                            file_size = os.path.getsize(artifact["path"])
                            artifact_ref = ARTIFACT_STORE.put(artifact["path"], task_id=task_id, execution_id=execution.id, artifact_type=artifact.get("type", "engine_output"), content_type="application/json")
                            from app.models import EngineArtifact
                            db.add(EngineArtifact(execution_id=execution.id, artifact_type=artifact.get("type", "engine_output"), artifact_uri=artifact_ref.uri, sha256=artifact_ref.sha256, size=artifact_ref.size, content_type=artifact_ref.content_type, storage_backend=artifact_ref.storage_backend, metadata_json=artifact_ref.metadata))
                            evidence = Evidence(
                                evidence_uid=generate_uid("evi"),
                                task_id=task_id,
                                evidence_type="engine_output",
                                artifact_path=artifact["path"],
                                artifact_hash=file_hash,
                                artifact_size=file_size,
                                metadata_json={
                                    "engine": display_name(db, engine_type),
                                    "engine_type": engine_type,
                                    "type": artifact.get("type", "engine_output"),
                                }
                            )
                            db.add(evidence)
                            all_artifacts.append(artifact)

                    # 更新执行记录
                    duration_ms = int((time.time() - start_time) * 1000)
                    execution.status = "completed" if result.success else "failed"
                    execution.error_code = result.error.error_code if isinstance(result.error, AdapterError) else None
                    execution.error_message = result.error.user_message if isinstance(result.error, AdapterError) else result.error
                    execution.debug_message = result.error.debug_message if isinstance(result.error, AdapterError) else None
                    execution.retryable = result.error.retryable if isinstance(result.error, AdapterError) else False
                    execution.provider_status = result.error.provider_status if isinstance(result.error, AdapterError) else None
                    execution.provider_scan_hash = result.provider_scan_hash
                    execution.stage_message = result.stage_events[-1] if result.stage_events else None
                    execution.normalized_event_count = result.normalized_event_count
                    execution.raw_result_hash = result.raw_result_hash
                    execution.finished_at = datetime.now(timezone.utc)
                    execution.completed_at = execution.finished_at
                    execution.duration_ms = duration_ms
                    execution.result_summary = result.summary
                    execution.raw_output_path = result.raw_output_path
                    db.commit()

                    engine_results.append({
                        "engine": display_name(db, engine_type),
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
                    execution.error_code = "ENGINE_PROCESS_CRASHED"
                    execution.error_message = str(e)
                    execution.completed_at = datetime.now(timezone.utc)
                    execution.duration_ms = duration_ms
                    db.commit()
                    logger.error(f"  -> {engine_info['name']} failed: {e}", exc_info=True)

                    engine_results.append({
                        "engine": display_name(db, engine_type),
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

            # 先判定「这次分析有没有覆盖到这个应用」，再产结论。
            # 顺序有意如此：结论一旦产生，用户就会看到；而覆盖度决定了这些结论
            # 算不算数（见 docs/analysis-coverage-design.md）。
            self._record_analysis_coverage(db, task, engine_types_to_run)

            # 静态引擎全部结束后，用 Observation 关联生成平台风险结论
            try:
                from app.services.finding_service import generate_findings
                produced = generate_findings(db, task_id)
                logger.info(f"Task {task_id} produced {len(produced)} platform findings")
            except Exception as exc:
                logger.error(f"Finding generation failed for task {task_id}: {exc}")

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

    def _record_analysis_coverage(self, db, task: DetectionTask, engine_types: list[str]):
        """判定每个引擎执行（以及整个任务）的分析有效性。

        APK 侧的判据来自 Androguard 的产物（它解析 manifest 与 DEX 类名表）；
        未启用该引擎时判 UNKNOWN——**缺数据不判 FULL**，那正是此前故障的成因。
        """
        from app.services import analysis_coverage as coverage

        executions = db.query(EngineExecution).filter(
            EngineExecution.task_id == task.id,
            EngineExecution.engine_type.in_(engine_types),
        ).all()
        if not executions:
            return

        artifact_summary = next((e.result_summary for e in executions
                                 if e.engine_type == "androguard" and e.result_summary), None)
        artifact, artifact_detail = coverage.artifact_verdict(artifact_summary)

        verdicts = []
        for execution in executions:
            verdict, detail = coverage.engine_verdict(
                execution.engine_type, execution.result_summary, artifact)
            execution.analysis_coverage = verdict
            execution.coverage_detail = detail
            verdicts.append(verdict)

        task.analysis_coverage = coverage.task_verdict(verdicts)
        task.coverage_detail = {"artifact": artifact, "artifact_detail": artifact_detail,
                                "engines": {e.engine_type: e.analysis_coverage for e in executions}}
        db.commit()
        if task.analysis_coverage == coverage.DEGRADED:
            logger.warning(
                f"Task {task.id} analysis DEGRADED: 本次分析未覆盖应用代码，"
                f"结论不可用于判断风险（依据: {artifact_detail}）")

    def _fail_task(self, db, task: DetectionTask, reason: str):
        """标记任务失败"""
        task.status = "failed"
        task.failed_reason = reason
        task.completed_at = datetime.now(timezone.utc)
        db.commit()
        logger.error(f"Task {task.id} failed: {reason}")


def list_engines(db=None) -> list[dict]:
    """列出所有已注册引擎及配置摘要。"""
    if db is None:
        db = SessionLocal()
        close_db = True
    else:
        close_db = False
    engines = []
    try:
        for engine_type, info in ENGINE_REGISTRY.items():
            adapter = build_engine_adapter(db, engine_type)
            env_ok = adapter.validate_environment()
            definition = get_definition(engine_type)
            row = get_or_create(db, engine_type)
            engines.append({
                "engine_type": engine_type, "name": display_name(db, engine_type), "version": info["version"],
                "capabilities": info["capabilities"], "description": info["description"],
                "env_ready": env_ok, "status": "ready" if env_ok else "not_configured",
                "message": getattr(adapter, "last_error", "") or ("环境就绪" if env_ok else "运行环境不满足"),
                "install_guide": info.get("install_guide", ""), "installed": env_ok,
                "config": public(db, engine_type), "last_health_status": row.last_health_status,
                "last_checked_at": row.last_checked_at.isoformat() if row.last_checked_at else None,
                "help": definition.get("help", {}),
            })
        return engines
    finally:
        if close_db:
            db.close()


async def run_worker(engine_types: list[str] = None):
    """运行Worker"""
    worker = EngineWorker(engine_types=engine_types)
    try:
        await worker.start()
    except KeyboardInterrupt:
        worker.stop()


if __name__ == "__main__":
    asyncio.run(run_worker())
