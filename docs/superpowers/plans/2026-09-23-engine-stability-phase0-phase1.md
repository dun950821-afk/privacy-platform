# 引擎稳定执行基础与 MobSF Reference Adapter Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans (current-session execution) to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 实现 V1.0 设计的 Phase 0.1–0.3 和 Phase 1.1：建立带 Lease/CAS、动态取消、结构化错误、ArtifactStore、Observation 和 fingerprint 的统一执行基础，并用 MobSF 跑通可观测的完整生命周期。

**Architecture:** 扩展现有 `EngineAdapter`/`TaskContext` 为统一生命周期与执行上下文；把 `EngineExecution` 作为数据库事实来源，使用租约和 CAS 防止 Worker 并发覆盖。先将 MobSF 改造成 reference implementation，分阶段执行 validate → upload → scan/poll → collect → normalize，保存 provider 标识、原始 Artifact 和结构化错误；Androguard/AppShark 继续通过兼容适配器接入，后续阶段再迁移其深度能力。

**Tech Stack:** FastAPI、SQLAlchemy/PostgreSQL、Alembic、Redis Streams、httpx、Pydantic/dataclasses、pytest、Vue 3/Vite（仅更新兼容状态接口所需字段）。

**Spec:** `docs/superpowers/specs/2026-09-23-engine-stability-and-results-design.md`

## Global Constraints

- `EngineExecution` 是状态事实来源；Redis 只负责通知/调度入口。
- 所有更新必须验证 `execution_id + state_version + lease_token + lease_expires_at`，CAS 失败后旧 Worker 必须停止写入。
- 状态终态为 `completed/failed/timed_out/canceled/skipped`；取消过程必须经过 `canceling`。
- 阶段超时使用 `STAGE_TIMEOUT`；引擎超时使用 `ENGINE_TIMEOUT`；任务超时使用 `TASK_TIMEOUT`；Provider 自身扫描超时使用 `PROVIDER_SCAN_TIMEOUT`。
- `max_attempts` 包含初始执行；重试由 `error_code + engine_type + stage` 决定。
- Secret、Authorization、API Key 不进入日志、fingerprint、Artifact 元数据或响应明文。
- `finished_at` 是终止时间唯一事实字段；`completed_at` 仅为兼容响应映射。
- 原始结果必须先保存为 Artifact，再进行 Parser/Observation/平台 Finding 处理；解析失败不能删除原始结果。
- 本计划仅实现 Phase 0 和 MobSF reference implementation；AppShark 进程隔离、Androguard 扩展、并行调度属于后续计划。

---

## 文件地图

- Modify `backend/app/engine/base.py`: 新增执行上下文、取消令牌、结构化错误、生命周期结果和兼容基类方法。
- Create `backend/app/engine/errors.py`: 错误码、`AdapterError`、重试决策函数。
- Create `backend/app/engine/artifacts.py`: `ArtifactStore` 接口和本地文件实现。
- Create `backend/app/engine/fingerprint.py`: canonical JSON、配置归一化和 scoped fingerprint。
- Modify `backend/app/models/__init__.py`: 扩展 `EngineExecution`；新增 `EngineArtifact`、`EngineObservation`、`FindingObservationRelation` 最小模型。
- Create `backend/alembic/versions/<timestamp>_engine_execution_foundation.py`: 字段、索引和新表迁移。
- Create `backend/app/engine/repository.py`: Lease/CAS claim、heartbeat、cancel signal、状态迁移和重试 attempt 持久化。
- Modify `backend/app/engine/worker.py`: 使用 repository claim 和生命周期编排；保持现有 Androguard/AppShark 兼容路径。
- Modify `backend/app/engine/adapters/mobsf.py`: 分阶段 MobSF reference adapter，结构化响应、provider hash、poll 兼容、Artifact 保存和 normalize。
- Modify `backend/app/api/v1/engines.py`: 返回阶段、错误码、provider 状态和动态进度；提供 engine retry/status 所需字段。
- Modify `backend/app/api/v1/tasks.py`: 暴露执行生命周期和错误结构；保留旧响应字段。
- Create `backend/tests/test_execution_foundation.py`: 状态、CAS、取消、错误和 fingerprint 测试。
- Create `backend/tests/test_mobsf_adapter.py`: MobSF 成功、认证、上传、超时、空结果、解析失败测试。
- Create `backend/tests/test_artifacts_and_observations.py`: Artifact、Observation 和 schema version 测试。
- Modify `README.md`: 更新执行状态、MobSF 诊断和故障排查命令。

---

### Task 1: Define lifecycle context, structured errors, and state transitions

**Files:**
- Modify: `backend/app/engine/base.py`
- Create: `backend/app/engine/errors.py`
- Test: `backend/tests/test_execution_foundation.py`

**Interfaces:**
- `EngineExecutionContext(task_id, execution_id, engine_type, engine_version, apk_path, apk_sha256, rule_version, config, work_dir, deadline, cancel_token, metadata)`.
- `CancelToken.is_cancelled() -> bool`.
- `AdapterError(error_code, user_message, debug_message, retryable, provider_status, stage, details)`.
- `should_retry(error_code, engine_type, stage, attempt_no, max_attempts) -> bool`.
- `EngineAdapter` keeps existing methods compatible and adds default async `validate`, `collect`, `poll`, `normalize`, `cleanup`, `cancel` hooks.

- [ ] **Step 1: Write failing tests for transitions and error policy**

```python
def test_cancel_token_reads_live_callback():
    state = {"cancelled": False}
    token = CancelToken(lambda: state["cancelled"])
    assert token.is_cancelled() is False
    state["cancelled"] = True
    assert token.is_cancelled() is True


def test_auth_error_is_not_retryable():
    assert should_retry("ENGINE_AUTH_FAILED", "mobsf", "mobsf_uploading", 1, 4) is False


def test_provider_503_is_retryable_until_max_attempts():
    assert should_retry("SCAN_START_FAILED", "mobsf", "mobsf_scan_starting", 1, 4) is True
    assert should_retry("SCAN_START_FAILED", "mobsf", "mobsf_scan_starting", 4, 4) is False
```

- [ ] **Step 2: Run tests and verify expected failure**

Run: `cd backend && /tmp/venv/bin/pytest tests/test_execution_foundation.py -q`
Expected: FAIL because the new classes and retry policy do not exist.

- [ ] **Step 3: Implement minimal lifecycle and error types**

Add dataclasses and a finite transition table. Make `EngineAdapter.validate_environment()` remain supported for existing callers; add non-abstract defaults for new lifecycle hooks so Androguard/AppShark do not break during Phase 0.

- [ ] **Step 4: Run focused tests**

Run: `cd backend && /tmp/venv/bin/pytest tests/test_execution_foundation.py -q`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/app/engine/base.py backend/app/engine/errors.py backend/tests/test_execution_foundation.py
git commit -m "feat: add engine lifecycle and structured errors"
```

---

### Task 2: Add ArtifactStore, canonical fingerprint, and schema metadata

**Files:**
- Create: `backend/app/engine/artifacts.py`
- Create: `backend/app/engine/fingerprint.py`
- Test: `backend/tests/test_artifacts_and_observations.py`

**Interfaces:**
- `ArtifactStore.put(source_path, *, task_id, execution_id, artifact_type, content_type) -> ArtifactRef`.
- `ArtifactStore.exists(uri) -> bool`.
- `ArtifactRef(artifact_id, uri, sha256, size, content_type, storage_backend, metadata)`.
- `canonical_json(value) -> str`.
- `execution_fingerprint(payload: dict) -> str`.
- Fingerprint payload must include APK SHA256, engine/version, rule version, adapter version, normalized config hash, and `cache_scope`; never include secrets.

- [ ] **Step 1: Write failing tests**

```python
def test_fingerprint_is_order_independent_and_scoped():
    left = {"engine_type": "mobsf", "config": {"scan_timeout": 300}, "cache_scope": "project:1"}
    right = {"cache_scope": "project:1", "config": {"scan_timeout": 300}, "engine_type": "mobsf"}
    assert execution_fingerprint(left) == execution_fingerprint(right)
    right["cache_scope"] = "project:2"
    assert execution_fingerprint(left) != execution_fingerprint(right)


def test_artifact_store_writes_hash_and_metadata(tmp_path):
    source = tmp_path / "raw.json"
    source.write_text('{"ok":true}')
    artifact = LocalArtifactStore(tmp_path / "store").put(source, task_id=1, execution_id=2, artifact_type="raw_result", content_type="application/json")
    assert artifact.sha256
    assert artifact.size == source.stat().st_size
    assert artifact.storage_backend == "local"
```

- [ ] **Step 2: Run tests and verify failure**

Run: `cd backend && /tmp/venv/bin/pytest tests/test_artifacts_and_observations.py -q`
Expected: FAIL because ArtifactStore and fingerprint functions do not exist.

- [ ] **Step 3: Implement canonical JSON and local ArtifactStore**

Use sorted keys, compact separators and UTF-8 SHA256. Copy artifacts into a task/execution-specific directory and return `file://` URI plus metadata. Implement a store interface so later MinIO/S3 backends do not change adapters.

- [ ] **Step 4: Run tests and commit**

Run: `cd backend && /tmp/venv/bin/pytest tests/test_artifacts_and_observations.py -q`
Expected: PASS.

```bash
git add backend/app/engine/artifacts.py backend/app/engine/fingerprint.py backend/tests/test_artifacts_and_observations.py
git commit -m "feat: add artifact storage and execution fingerprints"
```

---

### Task 3: Extend database execution model with Lease/CAS and Observation foundation

**Files:**
- Modify: `backend/app/models/__init__.py`
- Create: `backend/alembic/versions/<timestamp>_engine_execution_foundation.py`
- Create: `backend/app/engine/repository.py`
- Test: `backend/tests/test_execution_foundation.py`, `backend/tests/test_artifacts_and_observations.py`

**Interfaces:**
- `claim_execution(db, execution_id, worker_id, lease_seconds) -> Lease | None`.
- `cas_update_execution(db, execution_id, lease_token, expected_version, **fields) -> bool`.
- `heartbeat_execution(db, execution_id, lease_token, expected_version, lease_seconds) -> int | None`.
- `request_cancel(db, execution_id) -> bool` and `is_cancel_requested(db, execution_id) -> bool`.
- `transition_execution(...) -> bool` validates the state table and performs CAS.

- [ ] **Step 1: Add failing repository tests**

```python
def test_expired_lease_cannot_update_execution(db, execution):
    lease = claim_execution(db, execution.id, "worker-a", lease_seconds=1)
    assert lease
    db.refresh(execution)
    execution.lease_expires_at = datetime.now(timezone.utc) - timedelta(seconds=1)
    db.commit()
    assert cas_update_execution(db, execution.id, lease.lease_token, lease.state_version, status="running") is False


def test_old_worker_cannot_overwrite_new_lease(db, execution):
    first = claim_execution(db, execution.id, "worker-a", lease_seconds=1)
    expire_lease_for_test(db, execution.id)
    second = claim_execution(db, execution.id, "worker-b", lease_seconds=30)
    assert cas_update_execution(db, execution.id, first.lease_token, first.state_version, status="running") is False
    assert cas_update_execution(db, execution.id, second.lease_token, second.state_version, status="running") is True
```

- [ ] **Step 2: Run tests and verify failure**

Run: `cd backend && /tmp/venv/bin/pytest tests/test_execution_foundation.py -q`
Expected: FAIL because lease fields, repository and CAS methods are absent.

- [ ] **Step 3: Add model fields and observation/artifact tables**

Extend `EngineExecution` with `status`, `stage_message`, `progress`, `error_code`, `debug_message`, `retryable`, `provider_status`, `queued_at`, `stage_changed_at`, `heartbeat_at`, `finished_at`, `worker_id`, `lease_token`, `lease_expires_at`, `state_version`, `attempt_no`, `parent_execution_id`, `is_latest`, `execution_fingerprint`, `cache_scope`, `provider_scan_id`, `provider_scan_hash`, `raw_result_hash`, `raw_result_size`, `parser_version`, `parser_status`, `parser_error`, `normalized_at`, `normalized_event_count`, `normalized_finding_count`, and `cancel_requested`.

Add `EngineArtifact` and `EngineObservation` models with schema versions and indexes. Add `FindingObservationRelation` only as the relation foundation; platform Finding behavior remains a later phase.

- [ ] **Step 4: Add migration and repository CAS implementation**

Create indexes for task/status, lease expiry, fingerprint/scope, provider hash, and observation execution. Use a unique constraint for active latest execution per scoped fingerprint at the application/repository layer, because PostgreSQL partial uniqueness must account for retry semantics.

- [ ] **Step 5: Run tests**

Run: `cd backend && /tmp/venv/bin/pytest tests/test_execution_foundation.py tests/test_artifacts_and_observations.py -q`
Expected: PASS, including expired lease and stale-worker rejection.

- [ ] **Step 6: Commit**

```bash
git add backend/app/models/__init__.py backend/app/engine/repository.py backend/alembic/versions backend/tests
git commit -m "feat: add leased engine execution and observations"
```

---

### Task 4: Refactor Worker to claim executions and preserve compatibility

**Files:**
- Modify: `backend/app/engine/worker.py`
- Modify: `backend/app/tasks/orchestrator.py`
- Modify: `backend/app/api/v1/tasks.py`
- Modify: `backend/app/api/v1/engines.py`
- Test: `backend/tests/test_execution_foundation.py`

**Interfaces:**
- Worker uses `claim_execution` and `transition_execution`; no direct status assignment for lifecycle fields.
- Existing Androguard/AppShark execution remains functional through compatibility adapter path.
- New API responses include `status`, `stage`, `stage_message`, `progress`, `error_code`, `retryable`, `heartbeat_at`, and `finished_at`; old `completed_at` remains mapped.

- [ ] **Step 1: Write failing worker lifecycle tests**

```python
def test_worker_claim_failure_does_not_execute_adapter(db, monkeypatch):
    calls = []
    monkeypatch.setattr("app.engine.worker.build_engine_adapter", lambda *_: calls.append("executed"))
    process_one_execution(db, execution_id=10, worker_id="stale-worker")
    assert calls == []


def test_cancel_signal_stops_before_normalize(db, monkeypatch):
    # Adapter returns a raw result, but repository cancel signal becomes true before normalize.
    result = process_one_execution(db, execution_id=10, worker_id="worker-a")
    assert result.status == "canceled"
    assert result.normalized_event_count == 0
```

- [ ] **Step 2: Run tests and verify failure**

Run: `cd backend && /tmp/venv/bin/pytest tests/test_execution_foundation.py -q`
Expected: FAIL because Worker still directly creates/updates rows and does not claim leases.

- [ ] **Step 3: Implement claim-first execution flow**

Before invoking any adapter, claim the existing pending row using a unique lease token. Pass a live `CancelToken` backed by the repository. Every stage transition updates through CAS, updates `heartbeat_at`, `stage_changed_at`, `stage_message` and `progress`, and aborts if CAS returns false.

- [ ] **Step 4: Preserve old task and queue API fields**

Map `finished_at` to existing `completed_at` response fields. Include structured error and current stage in `engine_queue` while retaining `engine_name`, `status`, `stage`, `duration_ms` and existing alias behavior.

- [ ] **Step 5: Run tests and live smoke check**

Run: `cd backend && /tmp/venv/bin/pytest tests/test_execution_foundation.py -q`
Then call `GET /api/v1/tasks/{id}` and confirm lifecycle fields are present and no secret appears.

- [ ] **Step 6: Commit**

```bash
git add backend/app/engine/worker.py backend/app/tasks/orchestrator.py backend/app/api/v1/tasks.py backend/app/api/v1/engines.py backend/tests/test_execution_foundation.py
git commit -m "feat: run engine executions through leases and CAS"
```

---

### Task 5: Implement MobSF reference lifecycle and diagnostic errors

**Files:**
- Modify: `backend/app/engine/adapters/mobsf.py`
- Modify: `backend/app/engine/base.py`
- Modify: `backend/app/engine/artifacts.py` only for adapter integration
- Test: `backend/tests/test_mobsf_adapter.py`

**Interfaces:**
- `MobSFAdapter.validate(ctx) -> ValidationResult`.
- `MobSFAdapter.execute(ctx) -> AdapterResult` remains compatible but populates structured error, provider scan metadata, stage updates, raw artifact, and parser counts.
- Upload/scan behavior supports synchronous full JSON and “processing/poll/collect” responses.

- [ ] **Step 1: Write failing MobSF lifecycle tests**

```python
def test_mobsf_success_records_provider_hash_and_raw_artifact(tmp_path, mobsf_client):
    result = asyncio.run(adapter.execute(context_for(tmp_path / "app.apk")))
    assert result.success is True
    assert result.provider_scan_hash
    assert result.raw_output_path.startswith("file:")
    assert result.stage_events == ["mobsf_uploading", "mobsf_scan_starting", "mobsf_scanning", "mobsf_collecting", "mobsf_normalizing"]


def test_mobsf_401_is_non_retryable_auth_error(mobsf_client):
    result = asyncio.run(adapter.execute(context))
    assert result.error.error_code == "ENGINE_AUTH_FAILED"
    assert result.error.retryable is False


def test_mobsf_upload_413_is_file_error(mobsf_client):
    result = asyncio.run(adapter.execute(context))
    assert result.error.error_code == "FILE_TOO_LARGE"


def test_mobsf_invalid_json_keeps_raw_artifact(mobsf_client):
    result = asyncio.run(adapter.execute(context))
    assert result.success is False
    assert result.error.error_code == "RESULT_PARSE_FAILED"
    assert result.raw_output_path
```

- [ ] **Step 2: Run focused tests and verify failure**

Run: `cd backend && /tmp/venv/bin/pytest tests/test_mobsf_adapter.py -q`
Expected: FAIL because current Adapter returns plain strings, writes `/tmp` paths, does not expose provider metadata/stages, and cannot poll.

- [ ] **Step 3: Implement MobSF validate/upload/scan/poll/collect**

Use separate HTTP timeouts for connect, upload and scan. Record response status and provider hash. For `/scan`: if full JSON is returned, collect immediately; if response indicates processing, poll the supported MobSF status/report endpoint until completed or deadline. Map 401/403 to `ENGINE_AUTH_FAILED`, 413 to `FILE_TOO_LARGE`, connect errors to `ENGINE_UNREACHABLE`, 5xx to retryable `SCAN_START_FAILED`/`SCAN_FAILED`, read deadline to `PROVIDER_SCAN_TIMEOUT`.

- [ ] **Step 4: Persist raw result before normalization**

Copy response into `ArtifactStore`, compute SHA256/size, set provider metadata and schema version, then normalize trackers/URLs/manifest/security fields into `EngineObservation`-compatible payloads. A parser failure keeps the raw Artifact and returns `RESULT_PARSE_FAILED`.

- [ ] **Step 5: Implement cancel and cleanup**

`cancel()` closes the active HTTP client/task and marks the context canceled; cleanup removes only temporary local files, never the persisted raw Artifact. Do not claim that MobSF remote work was canceled if the provider has no cancel endpoint.

- [ ] **Step 6: Run tests and real reference scan**

Run: `cd backend && /tmp/venv/bin/pytest tests/test_mobsf_adapter.py -q`
Then use the known local MobSF container and a sample APK to verify upload, scan, raw artifact, provider hash, normalization count and the `mobsf_scanning` stage. Do not log the API Key.

- [ ] **Step 7: Commit**

```bash
git add backend/app/engine/base.py backend/app/engine/adapters/mobsf.py backend/app/engine/artifacts.py backend/tests/test_mobsf_adapter.py
git commit -m "feat: add observable MobSF reference lifecycle"
```

---

### Task 6: Add Phase 0/1 API projections, documentation, and acceptance matrix

**Files:**
- Modify: `backend/app/api/v1/engines.py`
- Modify: `backend/app/api/v1/tasks.py`
- Modify: `frontend/src/views/Queue.vue`
- Modify: `frontend/src/views/TaskDetail.vue`
- Modify: `README.md`
- Test: `backend/tests/test_execution_foundation.py`, `backend/tests/test_mobsf_adapter.py`

- [ ] **Step 1: Expose structured lifecycle in queue and detail APIs**

Return per execution:

```json
{
  "status": "running",
  "stage": "mobsf_scanning",
  "stage_message": "MobSF 静态分析中",
  "progress": 45,
  "error_code": null,
  "retryable": false,
  "heartbeat_at": "...",
  "finished_at": null,
  "provider_scan_hash": "..."
}
```

Keep alias resolution and old fields intact.

- [ ] **Step 2: Update queue/timeline UI**

Show current stage message, elapsed time, progress when known, error code/user message, and provider hash only to authorized administrators. Keep the configured engine alias as the only displayed engine name.

- [ ] **Step 3: Run the full acceptance matrix**

Run focused tests and manually verify:

```text
正常完成
服务不可达
API Key 错误
APK 损坏
HTTP 413
MobSF 500
MobSF 空结果
JSON 解析失败
Normalize 失败
阶段/引擎/任务超时
扫描中取消
Worker kill -9 后租约接管
Redis 重复投递
相同 fingerprint 重复提交
Raw Result 成功但 Parser 失败
重新解析 Raw Result
跨项目缓存隔离
```

- [ ] **Step 4: Build frontend and run backend checks**

```bash
cd backend && /tmp/venv/bin/pytest -q
cd ../frontend && npm run build
git diff --check
```

- [ ] **Step 5: Document operations**

Update README with lifecycle states, MobSF endpoint/API Key checks, worker lease recovery, artifact storage, and the exact command for a new reference scan. Keep old task failure records immutable.

- [ ] **Step 6: Commit**

```bash
git add backend/app/api/v1 frontend/src/views README.md backend/tests
git commit -m "feat: expose engine execution diagnostics and acceptance checks"
```

## Self-review coverage

- Phase 0.1 Adapter/Context/error/state foundation: Task 1.
- Phase 0.2 Lease/CAS, cancellation, ArtifactStore and database schema: Tasks 2–4.
- Phase 0.3 Observation, schema versions and fingerprint scope: Tasks 2–3.
- Phase 1.1 MobSF reference implementation: Task 5.
- Queue/UI projections, documentation and acceptance: Task 6.
- Lease stale-worker protection, dynamic cancel, `canceling`, timeout names, max_attempts, config-aware scoped fingerprint, three-layer result model, tri-state analysis, ArtifactStore and provider hash are explicit in Tasks 1–6.
