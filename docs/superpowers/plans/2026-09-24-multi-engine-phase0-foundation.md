# Phase 0 Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans (current-session execution) to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 V1.0 多引擎设计落到当前项目的 Phase 0 基础：统一任务配置、执行契约、错误模型、ArtifactStore、EngineExecution 迁移和可靠的 Lease/CAS 运行基础。

**Architecture:** 保留当前 FastAPI/SQLAlchemy/Redis Streams 架构，逐步把现有 Worker 和三个适配器迁移到统一的上下文与结构化结果。数据库 `EngineExecution` 是状态事实源，Redis 只负责调度；旧字段/接口保持兼容，新增字段通过 Alembic 正式迁移。

**Tech Stack:** FastAPI、SQLAlchemy/PostgreSQL、Alembic、Redis Streams、Python dataclasses、httpx、pytest。

**Spec:** `docs/superpowers/specs/2026-09-24-multi-engine-detection-v1-design.md`

## Global Constraints

- V1.0 正式实现静态检测域：Androguard、AppShark、MobSF；动态域只保留 Schema 和接口。
- Androguard = Facts；AppShark = Data Flow；MobSF = Security Observation。
- 结果流水线固定为 `Raw Artifact → Engine Observation → Platform Finding`。
- Redis 只承担调度通知，数据库是执行状态事实源。
- 所有执行状态更新必须验证 `lease_token + state_version + lease_expires_at`；CAS 失败的 Worker 必须停止写入。
- 终止状态为 `completed/failed/timed_out/canceled/skipped`；取消必须经过 `canceling`。
- 重试创建新的 EngineExecution，不把历史 `failed` 改回 `queued`。
- API Key、密码、Authorization 和敏感配置不得进入日志、fingerprint 或 resolved config snapshot。
- `finished_at` 是终止时间唯一事实字段，旧 `completed_at` 仅作兼容映射。
- 当前计划完成 Phase 0 Foundation；MobSF 完整 Reference Adapter 属于下一计划，不能在本轮混入大规模结果模型重构。

---

## 当前代码地图与必须修正点

- `backend/app/engine/base.py` 已有兼容 `TaskContext`/`AdapterResult`，需要从当前接口扩展但不能破坏 Androguard/AppShark。
- `backend/app/models/__init__.py` 已有扩展后的 `EngineExecution`、`EngineArtifact`、`EngineObservation`，需要补充缺少的 `EngineExecutionEvent` 和索引/关系一致性。
- `backend/app/engine/repository.py` 已有 Lease/CAS 初版，但状态迁移、事务边界、数据库方言兼容和动态取消需要测试后修正。
- `backend/app/tasks/orchestrator.py` 仍使用 `config.engines` 字符串数组，需要兼容并逐步支持 V1 `static.engines.{engine_type}.enabled/config`。
- `backend/app/engine/worker.py` 仍大量直接赋值 `execution.status`，必须用 Repository 统一更新。
- `backend/app/engine/adapters/mobsf.py` 已有结构化错误和阶段结果，但 ArtifactStore/Observation 持久化在本计划只提供接口，不完成完整 MobSF parser。

---

### Task 1: Normalize task configuration schema and resolved snapshots

**Files:**
- Create: `backend/app/services/task_config.py`
- Modify: `backend/app/schemas/__init__.py` around `TaskCreate`
- Modify: `backend/app/api/v1/tasks.py` task creation
- Modify: `backend/app/tasks/orchestrator.py` engine selection
- Test: `backend/tests/test_task_config_schema.py`

**Interfaces:**
- `normalize_task_config(config: dict) -> dict`
- `enabled_engine_types(config: dict, registry_types: Iterable[str]) -> list[str]`
- `resolved_task_config(config: dict, defaults: dict) -> dict`
- `redact_task_config(config: dict) -> dict`
- `task_config_hash(config: dict) -> str`

- [ ] **Step 1: Write failing schema tests**

```python
def test_new_engine_map_schema_returns_enabled_types():
    config = {"static": {"engines": {
        "androguard": {"enabled": True, "config": {"parse_timeout": 300}},
        "appshark": {"enabled": False, "config": {}},
        "mobsf": {"enabled": True, "config": {"scan_timeout": 1800}},
    }}}
    assert enabled_engine_types(config, ["androguard", "appshark", "mobsf"]) == ["androguard", "mobsf"]


def test_legacy_engine_array_is_backward_compatible():
    assert enabled_engine_types({"engines": ["androguard", "mobsf"]}, ["androguard", "appshark", "mobsf"]) == ["androguard", "mobsf"]


def test_task_config_redacts_secrets():
    safe = redact_task_config({"static": {"engines": {"mobsf": {"config": {"api_key": "secret"}}}}})
    assert "secret" not in str(safe)
```

- [ ] **Step 2: Run focused tests and verify failure**

Run: `cd backend && PYTHONPATH=. /tmp/venv/bin/pytest tests/test_task_config_schema.py -q`
Expected: FAIL because the task configuration service does not exist.

- [ ] **Step 3: Implement normalization and compatibility**

Normalize legacy arrays into the new `static.engines` map, preserve `dynamic.enabled/scenarios`, reject unknown engine types only at execution planning, redact keys containing `key/token/password/authorization`, and hash canonical redacted resolved configuration.

- [ ] **Step 4: Integrate creation and orchestrator**

At task creation, store normalized config with `schema_version="1.0"`; at submission, call `enabled_engine_types()` rather than reading only `config.engines`. Keep legacy tasks readable and do not rewrite their persisted history unexpectedly.

- [ ] **Step 5: Run tests and commit**

Run: `cd backend && PYTHONPATH=. /tmp/venv/bin/pytest tests/test_task_config_schema.py -q`
Expected: PASS.

```bash
git add backend/app/services/task_config.py backend/app/schemas/__init__.py backend/app/api/v1/tasks.py backend/app/tasks/orchestrator.py backend/tests/test_task_config_schema.py
git commit -m "feat: add versioned multi-engine task config schema"
```

---

### Task 2: Complete Adapter Contract, Error Model, Cancellation Token, and ArtifactStore interfaces

**Files:**
- Modify: `backend/app/engine/base.py`
- Modify: `backend/app/engine/errors.py`
- Modify: `backend/app/engine/artifacts.py`
- Test: `backend/tests/test_execution_contract.py`

**Interfaces:**
- `EngineExecutionContext` includes `workspace_id`, `apk_artifact_id`, `trace_id`, `resolved_config`, `deadline`, `work_dir`, `cancel_token`.
- `CancelToken.is_cancelled() -> bool` must query a live callback/Repository, not a creation-time snapshot.
- `AdapterError.as_dict() -> dict` never includes secret values.
- `ArtifactStore.put/get/open/exists/delete/get_download_url` exists; `LocalArtifactStore` remains the V1 backend.
- `AdapterResult` retains old fields and adds `provider_execution_id`, `provider_scan_hash`, `stage_events`, `raw_result_hash`, `normalized_event_count`.

- [ ] **Step 1: Write failing contract tests**

```python
def test_context_contains_scope_and_trace():
    ctx = EngineExecutionContext(1, 2, "mobsf", "4.5.4", "/tmp/a.apk", workspace_id=9, trace_id="trace-1")
    assert ctx.workspace_id == 9
    assert ctx.trace_id == "trace-1"


def test_artifact_store_exposes_lifecycle_methods(tmp_path):
    store = LocalArtifactStore(tmp_path)
    for name in ("put", "get", "open", "exists", "delete", "get_download_url"):
        assert hasattr(store, name)
```

- [ ] **Step 2: Run tests and verify failure**

Run: `cd backend && PYTHONPATH=. /tmp/venv/bin/pytest tests/test_execution_contract.py -q`
Expected: FAIL because context scope fields and ArtifactStore lifecycle methods are incomplete.

- [ ] **Step 3: Implement the contract**

Add optional context fields without breaking positional legacy construction. Implement local ArtifactStore `get`, `open`, `delete`, and `get_download_url`; keep `file://` URLs and return metadata only. Ensure `AdapterError` serializes user/debug fields without config contents.

- [ ] **Step 4: Run tests and commit**

Run: `cd backend && PYTHONPATH=. /tmp/venv/bin/pytest tests/test_execution_contract.py -q`
Expected: PASS.

```bash
git add backend/app/engine/base.py backend/app/engine/errors.py backend/app/engine/artifacts.py backend/tests/test_execution_contract.py
git commit -m "feat: formalize engine adapter and artifact contracts"
```

---

### Task 3: Finish EngineExecution migration, Observation/Event models, and Lease/CAS repository

**Files:**
- Modify: `backend/app/models/__init__.py`
- Modify: `backend/app/engine/repository.py`
- Modify: `backend/alembic/versions/20260923_execution_foundation.py`
- Create: `backend/alembic/versions/<timestamp>_engine_execution_event.py`
- Test: `backend/tests/test_execution_repository.py`

**Interfaces:**
- `claim_execution(db, execution_id, worker_id, lease_seconds) -> Lease | None`
- `cas_update_execution(db, execution_id, lease_token, expected_version, **fields) -> bool`
- `heartbeat_execution(...) -> int | None`
- `request_cancel(db, execution_id) -> bool`
- `is_cancel_requested(db, execution_id) -> bool`
- `transition_execution(...) -> bool`
- `EngineExecutionEvent` stores immutable stage/status transitions with `execution_id`, `from_status`, `to_status`, `stage`, `message`, `state_version`, `created_at`.

- [ ] **Step 1: Write failing repository/event tests**

```python
def test_stale_worker_cannot_update_after_reclaim(db, execution):
    first = claim_execution(db, execution.id, "worker-a", lease_seconds=1)
    expire_lease_for_test(db, execution.id)
    second = claim_execution(db, execution.id, "worker-b", lease_seconds=60)
    assert not cas_update_execution(db, execution.id, first.lease_token, first.state_version, status="running")
    assert cas_update_execution(db, execution.id, second.lease_token, second.state_version, status="running")


def test_terminal_execution_rejects_transition(db, execution):
    execution.status = "completed"
    db.commit()
    assert transition_execution(db, execution.id, "token", 0, "running") is False
```

- [ ] **Step 2: Run tests and verify failure**

Run: `cd backend && PYTHONPATH=. /tmp/venv/bin/pytest tests/test_execution_repository.py -q`
Expected: FAIL if fixtures are not present; add a local SQLite/PostgreSQL test fixture before testing production behavior, then ensure failure is due to stale repository/event behavior rather than fixture errors.

- [ ] **Step 3: Fix repository transaction and state behavior**

Use `setattr` rather than mutating SQLAlchemy `__dict__`; keep expected version returned after claim; verify lease expiry and worker identity in every write; enforce transition table including `canceling`; write one immutable `EngineExecutionEvent` per accepted transition. `request_cancel` sets `cancel_requested_at` when that column exists and remains compatible with the boolean field.

- [ ] **Step 4: Add Event model and migration**

Add `EngineExecutionEvent` and indexes on `execution_id`, `created_at`, and `status`. The migration must inspect existing columns/tables and be safe to run against the current database.

- [ ] **Step 5: Run tests and commit**

Run: `cd backend && PYTHONPATH=. /tmp/venv/bin/pytest tests/test_execution_repository.py -q`
Expected: PASS, including stale worker rejection and terminal transition rejection.

```bash
git add backend/app/models/__init__.py backend/app/engine/repository.py backend/alembic/versions backend/tests/test_execution_repository.py
git commit -m "feat: enforce leased execution state transitions"
```

---

### Task 4: Migrate Worker to claim-first lifecycle without breaking existing engines

**Files:**
- Modify: `backend/app/engine/worker.py`
- Modify: `backend/app/tasks/engine_queue.py`
- Modify: `backend/app/api/v1/engines.py`
- Modify: `backend/app/api/v1/tasks.py`
- Test: `backend/tests/test_worker_lifecycle.py`

**Interfaces:**
- Worker helper `claim_and_run_execution(db, execution, task, version, worker_id) -> EngineExecution`.
- All stage/status/error/progress writes go through repository CAS.
- Queue output includes `stage_message`, `progress`, `error_code`, `retryable`, `heartbeat_at`, `finished_at`, `provider_scan_hash`.

- [ ] **Step 1: Write failing Worker tests**

```python
def test_worker_does_not_call_adapter_when_claim_fails(db, monkeypatch):
    called = []
    monkeypatch.setattr("app.engine.worker.build_engine_adapter", lambda *_: called.append(True))
    claim_and_run_execution(db, execution_id=10, worker_id="stale")
    assert called == []


def test_cancel_is_checked_before_normalize(db, monkeypatch):
    result = run_fake_execution_with_live_cancel(db, monkeypatch)
    assert result.status == "canceled"
    assert result.normalized_event_count == 0
```

- [ ] **Step 2: Run tests and verify failure**

Run: `cd backend && PYTHONPATH=. /tmp/venv/bin/pytest tests/test_worker_lifecycle.py -q`
Expected: FAIL because current Worker directly assigns statuses and does not claim pending rows through Repository.

- [ ] **Step 3: Implement claim-first execution**

Before adapter invocation, claim the existing pending row. Build a live `CancelToken` from `is_cancel_requested()`. Transition through `preparing → validating → running → collecting → normalizing`; heartbeat during long operations; stop immediately on CAS failure or cancellation. Store finished time and compatibility `completed_at` together only on accepted terminal transition.

- [ ] **Step 4: Preserve queue/report compatibility**

Use current alias resolver for `engine_name`; expose new fields while retaining existing `status`, `stage`, `duration_ms`, `error_message`, and `completed_at`. Do not expose secrets or debug message to non-admin users.

- [ ] **Step 5: Run tests and commit**

Run: `cd backend && PYTHONPATH=. /tmp/venv/bin/pytest tests/test_worker_lifecycle.py -q`
Expected: PASS.

```bash
git add backend/app/engine/worker.py backend/app/tasks/engine_queue.py backend/app/api/v1/engines.py backend/app/api/v1/tasks.py backend/tests/test_worker_lifecycle.py
git commit -m "feat: migrate worker to claim-first execution lifecycle"
```

---

### Task 5: Validate Phase 0 against live services and document operations

**Files:**
- Modify: `README.md`
- Create: `backend/tests/test_phase0_acceptance.py`
- Modify: `backend/app/core/config.py` only if an explicit artifact root/schema setting is needed.

- [ ] **Step 1: Add acceptance checks**

```python
def test_fingerprint_excludes_mobsf_key():
    assert execution_fingerprint({"engine": "mobsf", "api_key": "a"}) == execution_fingerprint({"engine": "mobsf", "api_key": "b"})


def test_error_response_contains_no_secret():
    error = AdapterError("ENGINE_AUTH_FAILED", "认证失败", "HTTP 401")
    assert "api_key" not in str(error.as_dict()).lower()
```

- [ ] **Step 2: Run all Phase 0 tests**

Run:

```bash
cd backend
PYTHONPATH=. /tmp/venv/bin/pytest tests/test_task_config_schema.py tests/test_execution_contract.py tests/test_execution_repository.py tests/test_worker_lifecycle.py tests/test_phase0_acceptance.py -q
```

Expected: all Phase 0 tests pass. Existing environment warnings may remain, but no collection or runtime errors are allowed.

- [ ] **Step 3: Apply Alembic migrations safely**

Run the configured Alembic upgrade command against the current database. Before and after, inspect `information_schema.columns` and verify `engine_executions`, `engine_execution_events`, `engine_artifacts`, and `engine_observations`. Do not use `init_db.py` to retrofit the existing database.

- [ ] **Step 4: Verify live API and services**

Use the admin token and verify:

```bash
GET /api/v1/engines
GET /api/v1/engines/mobsf/config
POST /api/v1/engines/mobsf/health-check
GET /api/v1/tasks/{id}
GET /api/v1/engines/executions
```

Expected: HTTP 200; lifecycle fields appear; no API Key appears in any response.

- [ ] **Step 5: Build frontend and document operation**

Run:

```bash
cd frontend && npm run build
git diff --check
```

Document the required order: database migration → API restart → Worker restart → frontend build/restart; document `alembic upgrade head` as the only supported schema upgrade path.

- [ ] **Step 6: Commit**

```bash
git add README.md backend/tests backend/app/core/config.py
git commit -m "docs: document phase zero execution foundation operations"
```

## Self-review coverage

- Task Config Schema and legacy compatibility: Task 1.
- Adapter Contract, Cancellation Token, Error Model, ArtifactStore: Task 2.
- EngineExecution migration, Lease/CAS and immutable execution events: Task 3.
- Worker integration and queue/API diagnostics: Task 4.
- Live service/schema/build verification: Task 5.

MobSF result parser, Androguard Runner, AppShark Executor, Correlation/Finding layer and final product UI remain later phases of the frozen V1.0 design and are intentionally not mixed into this Phase 0 plan.
