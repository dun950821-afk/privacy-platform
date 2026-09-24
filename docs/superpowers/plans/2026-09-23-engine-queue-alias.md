# 队列引擎可视化与引擎别名 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans (current-session execution) to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让队列和任务详情清晰展示每个任务正在执行、等待、已完成或失败的引擎，并支持管理员配置全局引擎别名；配置别名后所有用户界面、历史任务、报告、事件和证据展示都只显示别名，未配置时回退到真实名称。

**Architecture:** 在现有 `engine_configs.config_json` 增加普通字段 `alias`，内部始终使用稳定的 `engine_type`；展示层通过统一的 `display_name(engine_type)` 动态解析当前别名，因此改名立即影响历史数据。任务提交时为选定的每个引擎创建 `EngineExecution(status="pending")` 记录，Worker 按顺序将记录更新为 `running`、`completed` 或 `failed`，任务/执行 API 返回按引擎聚合的队列进度，前端队列页展示摘要，任务详情展示完整时间线。

**Tech Stack:** FastAPI、SQLAlchemy/PostgreSQL JSONB、Redis Streams、Vue 3、TypeScript、Element Plus、pytest、Vite。

**Spec:** `docs/superpowers/specs/2026-09-23-engine-config-design.md` 及本轮已确认的队列和别名决策：全局别名、当前别名动态生效、队列概览加详情时间线。

## Global Constraints

- `engine_type` 是内部稳定标识，永远用于任务配置、Worker、查询过滤和关联；别名只用于展示。
- 别名非空时只展示别名，不并列展示真实引擎名；未配置或空字符串时回退 `ENGINE_REGISTRY[name]`。
- 修改别名后，历史任务、报告、事件、证据和统计均通过当前 `engine_type` 动态解析新别名。
- API Key 等敏感配置保持现有加密和脱敏规则；别名属于普通配置，可读写。
- 队列状态至少区分 `pending`（等待）、`running`（执行中）、`completed`、`failed`、`canceled`。
- 不通过 Redis 内存状态猜测引擎进度；数据库 `EngineExecution` 是队列展示的事实来源。
- 任务重试必须删除并重新创建该次任务的 EngineExecution，避免旧状态污染新一轮执行。

---

## 文件地图

- Modify `backend/app/services/engine_config.py`: 增加 alias 字段定义、规范化和 `display_name`/批量解析函数。
- Modify `backend/app/engine/worker.py`: 使用动态展示名；创建/推进 pending EngineExecution；返回当前别名。
- Modify `backend/app/tasks/orchestrator.py`: 提交任务时初始化选定引擎的 pending 执行记录。
- Modify `backend/app/api/v1/tasks.py`: 任务列表/详情返回 queue engine summary 和当前别名。
- Modify `backend/app/api/v1/engines.py`: 配置 API 支持 alias，并让执行、统计 API 动态返回 alias。
- Modify `backend/app/api/v1/system.py` only if dashboard needs engine queue counts.
- Modify `backend/app/models/__init__.py` only if a timestamp/heartbeat field is required; prefer existing `EngineExecution` fields.
- Modify `frontend/src/views/Queue.vue`: 当前执行引擎、等待引擎、`N/M` 进度和状态标签。
- Modify `frontend/src/views/TaskDetail.vue`: 引擎执行时间线和当前别名展示。
- Modify `frontend/src/views/Engines.vue`: “显示别名”配置字段和说明。
- Modify `frontend/src/api/tasks.ts` and `frontend/src/api/engines.ts`: 类型/接口字段适配。
- Create/modify `backend/tests/test_engine_queue_alias.py`: alias fallback, dynamic rename, pending lifecycle and API projection tests.
- Modify `README.md`: document global alias behavior and queue semantics.

---

### Task 1: Add global engine alias semantics

**Files:**
- Modify: `backend/app/services/engine_config.py`
- Modify: `backend/app/engine/worker.py`
- Modify: `backend/app/api/v1/engines.py`
- Test: `backend/tests/test_engine_queue_alias.py`

**Interfaces:**
- `engine_config` definitions expose ordinary field `{key: "alias", label: "显示别名", type: "text", required: false}` for all registered engines.
- `display_name(db, engine_type) -> str` returns trimmed configured alias when non-empty, otherwise registry name.
- `display_names(db, engine_types: list[str]) -> dict[str, str]` resolves aliases in one database session.

- [ ] **Step 1: Write failing alias tests**

```python
def test_alias_falls_back_to_registry_name(db):
    assert display_name(db, "mobsf") == "MobSF"


def test_alias_replaces_real_name_and_updates_existing_history(db):
    save(db, "mobsf", {"alias": "移动安全扫描"}, {}, [], 1)
    assert display_name(db, "mobsf") == "移动安全扫描"
    save(db, "mobsf", {"alias": "合规扫描服务"}, {}, [], 1)
    assert display_name(db, "mobsf") == "合规扫描服务"


def test_blank_alias_uses_real_name(db):
    save(db, "mobsf", {"alias": "   "}, {}, [], 1)
    assert display_name(db, "mobsf") == "MobSF"
```

- [ ] **Step 2: Run the focused test and verify expected failure**

Run: `cd backend && /tmp/venv/bin/pytest tests/test_engine_queue_alias.py -q`
Expected: FAIL because `display_name` and alias field metadata do not exist.

- [ ] **Step 3: Implement alias metadata and display helpers**

Add the alias field to all three engine definitions. Implement `display_name` by reading `EngineConfig.config_json["alias"]`, trimming it, and falling back to `ENGINE_REGISTRY[engine_type]["name"]`; avoid importing the registry at module import time if it creates a circular import by passing a fallback name or moving registry metadata to a neutral helper.

- [ ] **Step 4: Make engine list/config API expose alias without exposing real name when configured**

Return `display_name`/`name` as the value to render and keep `engine_type` as the only stable identifier. Include the alias field in the configuration drawer with help text: “配置后用户界面只显示该名称；留空使用系统默认名称”。Do not return a second real-name field to frontend display payloads.

- [ ] **Step 5: Run tests and commit**

Run: `cd backend && /tmp/venv/bin/pytest tests/test_engine_queue_alias.py -q`
Expected: alias fallback and rename tests PASS.

```bash
git add backend/app/services/engine_config.py backend/app/engine/worker.py backend/app/api/v1/engines.py backend/tests/test_engine_queue_alias.py
git commit -m "feat: add global engine display aliases"
```

---

### Task 2: Create a durable pending/running EngineExecution lifecycle

**Files:**
- Modify: `backend/app/tasks/orchestrator.py`
- Modify: `backend/app/engine/worker.py`
- Modify: `backend/app/api/v1/tasks.py`
- Modify: `backend/app/api/v1/engines.py`
- Test: `backend/tests/test_engine_queue_alias.py`

**Interfaces:**
- `initialize_engine_executions(db, task, sub_task, engine_types) -> list[EngineExecution]` creates one pending row per selected engine.
- `get_task_engine_queue(db, task_id) -> dict` returns `items`, `current`, `waiting`, `completed`, `failed`, `total`, `finished`, `current_index`.
- Existing task retry behavior deletes old execution rows and creates fresh pending rows on the next submit.

- [ ] **Step 1: Write failing lifecycle tests**

```python
def test_submit_creates_pending_execution_for_each_selected_engine(db, task, sub_task):
    rows = initialize_engine_executions(db, task, sub_task, ["androguard", "appshark", "mobsf"])
    assert [r.status for r in rows] == ["pending", "pending", "pending"]


def test_queue_summary_distinguishes_running_and_waiting(db, task, sub_task):
    initialize_engine_executions(db, task, sub_task, ["androguard", "appshark", "mobsf"])
    db.query(EngineExecution).filter_by(task_id=task.id, engine_type="androguard").update({"status": "completed"})
    db.query(EngineExecution).filter_by(task_id=task.id, engine_type="appshark").update({"status": "running", "stage": "execute"})
    db.commit()
    summary = get_task_engine_queue(db, task.id)
    assert summary["current"]["engine_type"] == "appshark"
    assert [x["engine_type"] for x in summary["waiting"]] == ["mobsf"]
```

- [ ] **Step 2: Run tests and verify failure**

Run: `cd backend && /tmp/venv/bin/pytest tests/test_engine_queue_alias.py -q`
Expected: FAIL because pending records and queue summary do not exist.

- [ ] **Step 3: Initialize pending rows during task submission**

After the static subtask is created and the final selected engine list is known, insert one `EngineExecution` per selected engine with `status="pending"`, `stage="queued"`, `engine_type`, and current resolved display name only as a compatibility value. Keep `config_json` redacted. Ensure no rows are created for unknown or unselected types.

- [ ] **Step 4: Update Worker to claim pending rows**

Before adapter execution, query the task/subtask execution row by `task_id`, `sub_task_id`, and `engine_type`; set `status="running"`, `stage="prepare"`, and `started_at`. Do not create a duplicate row. On environment failure or adapter exception set `failed`; on success set `completed`; preserve `completed_at`, duration, counts and result summary.

- [ ] **Step 5: Add queue aggregation to task APIs**

Return `engine_queue` in `GET /tasks` items and `GET /tasks/{id}`. Each item includes `engine_type`, dynamic `engine_name`, `status`, `stage`, `started_at`, `completed_at`, `error_message`, and `position`. Summary includes `current`, `waiting`, `completed`, `failed`, `finished`, `total`, and `current_index`. Use current alias resolution for every response.

- [ ] **Step 6: Verify lifecycle and commit**

Run: `cd backend && /tmp/venv/bin/pytest tests/test_engine_queue_alias.py -q`
Expected: pending → running → completed/failed tests PASS, including retry cleanup.

```bash
git add backend/app/tasks/orchestrator.py backend/app/engine/worker.py backend/app/api/v1/tasks.py backend/app/api/v1/engines.py backend/tests/test_engine_queue_alias.py
git commit -m "feat: track per-engine queue lifecycle"
```

---

### Task 3: Make all backend display projections use the current alias

**Files:**
- Modify: `backend/app/api/v1/tasks.py`
- Modify: `backend/app/api/v1/engines.py`
- Modify: `backend/app/engine/worker.py`
- Modify: `backend/app/api/agent/v1.py` only for server-generated event names
- Modify: `backend/app/services/report_service.py` if it emits engine names
- Test: `backend/tests/test_engine_queue_alias.py`

**Interfaces:**
- Every display response maps `engine_type` through `display_name`; no client-facing response should rely on the stored `EngineExecution.engine_name` snapshot.
- Internal filtering and joins remain on `engine_type`.

- [ ] **Step 1: Write failing projection tests**

```python
def test_execution_and_report_projection_changes_after_alias_update(db, execution):
    save(db, "mobsf", {"alias": "首次名称"}, {}, [], 1)
    assert execution_projection(db, execution)["engine_name"] == "首次名称"
    save(db, "mobsf", {"alias": "新名称"}, {}, [], 1)
    assert execution_projection(db, execution)["engine_name"] == "新名称"
```

- [ ] **Step 2: Run test and verify failure**

Run: `cd backend && /tmp/venv/bin/pytest tests/test_engine_queue_alias.py::test_execution_and_report_projection_changes_after_alias_update -q`
Expected: FAIL because APIs currently return `EngineExecution.engine_name` snapshots.

- [ ] **Step 3: Centralize response projection**

Add a small helper that maps execution rows to API dictionaries and receives one alias map per response. Replace `e.engine_name` in execution lists/details/stats, task events, report overview, evidence metadata response, and server-generated Worker event fields with `display_name(db, e.engine_type)`. Keep stored fields untouched for backward compatibility.

- [ ] **Step 4: Verify all display paths**

Run focused projection tests and manually call:

```bash
GET /api/v1/engines/executions
GET /api/v1/engines/executions/{id}
GET /api/v1/tasks/{id}
GET /api/v1/tasks/{id}/events
GET /api/v1/tasks/{id}/report-overview
```

After changing one alias, every response must contain the new alias and no configured real name in display fields.

- [ ] **Step 5: Commit**

```bash
git add backend/app/api/v1/tasks.py backend/app/api/v1/engines.py backend/app/engine/worker.py backend/app/api/agent/v1.py backend/app/services/report_service.py backend/tests/test_engine_queue_alias.py
git commit -m "feat: resolve engine aliases across backend displays"
```

---

### Task 4: Add queue overview and engine timeline to the frontend

**Files:**
- Modify: `frontend/src/api/tasks.ts`
- Modify: `frontend/src/api/engines.ts` only if response types are defined there
- Modify: `frontend/src/views/Queue.vue`
- Modify: `frontend/src/views/TaskDetail.vue`
- Modify: `frontend/src/views/Engines.vue`
- Test: existing frontend build and any existing component test setup

**Interfaces:**
- Queue item consumes `engine_queue` with `current`, `waiting`, `completed`, `failed`, `finished`, `total`, `current_index`.
- Engine cards/config drawer consume `alias` as an ordinary field and display `name` already resolved by backend.

- [ ] **Step 1: Add UI-level data fixtures/tests**

```ts
const queue = {
  current: { engine_name: '深度合规分析', status: 'running', stage: 'execute' },
  waiting: [{ engine_name: '移动安全扫描', status: 'pending' }],
  finished: 1,
  total: 3,
  current_index: 2,
}
expect(queueProgressText(queue)).toBe('正在执行 深度合规分析（第 2/3 个）')
```

- [ ] **Step 2: Run frontend baseline/build and verify missing helper/UI**

Run: `cd frontend && npm run build`
Expected: baseline build passes; the new fixture/helper is absent until implemented.

- [ ] **Step 3: Add queue summary rendering**

In `Queue.vue`, add a column/stack beneath the task status:

- running: `正在执行 {current.engine_name}（第 {current_index}/{total} 个）` plus stage label;
- queued with no current: `等待执行：{waiting names}`;
- completed: `已完成 {finished}/{total}`;
- failed: `失败：{failed names}`.

Keep the existing 5-second polling and avoid displaying `engine_type` or real names to users.

- [ ] **Step 4: Add task detail timeline**

In `TaskDetail.vue`, add an engine timeline ordered by `position`, with status tags `等待执行/执行中/已完成/失败/已取消`, current stage, start/end time, duration, and error message. Render alias names only. Poll the existing task detail endpoint while the task is active.

- [ ] **Step 5: Add alias editing field and help**

In `Engines.vue` configuration drawer, render the new alias field before engine-specific fields. Add help text explaining that a configured alias completely replaces the real engine name across current and historical displays; clearing it restores the default name. Save through existing config API and refresh cards immediately.

- [ ] **Step 6: Build and commit**

Run: `cd frontend && npm run build`
Expected: TypeScript/Vite build passes with the queue summary, timeline, and alias form.

```bash
git add frontend/src/api/tasks.ts frontend/src/api/engines.ts frontend/src/views/Queue.vue frontend/src/views/TaskDetail.vue frontend/src/views/Engines.vue
git commit -m "feat: show engine queue progress and aliases"
```

---

### Task 5: End-to-end verification and documentation

**Files:**
- Modify: `README.md`
- Modify: backend/frontend tests only for verified regressions.

- [ ] **Step 1: Run backend tests and migration checks**

Run:

```bash
cd backend
/tmp/venv/bin/pytest -q
```

Expected: all focused queue/alias tests pass; record any pre-existing “no tests collected” result separately rather than treating it as a successful full suite.

- [ ] **Step 2: Verify live alias flow**

Use admin login, set MobSF alias to `移动安全扫描`, call engine/task/execution/report endpoints, and confirm display values use only `移动安全扫描`. Clear alias and confirm fallback to `MobSF`.

- [ ] **Step 3: Verify live queue flow**

Submit a task with at least two selected engines and observe:

```text
等待执行：...
正在执行 移动安全扫描（第 1/2 个）
已完成 1/2
```

Open task details and verify the timeline includes both the running and pending engine rows; after completion verify completed/failed rows remain visible.

- [ ] **Step 4: Verify rename propagation**

Rename an engine after a task has completed, refresh Queue, TaskDetail, Engine executions and report overview, and confirm all use the new alias without changing `engine_type`.

- [ ] **Step 5: Build and inspect changes**

Run:

```bash
cd frontend && npm run build
git diff --check
git status --short
```

Expected: build succeeds, no whitespace errors, and no API key/secret appears in any response or log.

- [ ] **Step 6: Commit documentation**

```bash
git add README.md backend/tests frontend
git commit -m "docs: document engine queue and alias behavior"
```

## Self-review coverage

- Global alias with fallback and no real-name display: Task 1.
- Pending/running/waiting/completed/failed engine queue lifecycle: Task 2.
- Current alias applied to historical API/report/event/evidence projections: Task 3.
- Queue overview, detail timeline, polling and alias editor: Task 4.
- Runtime verification, rename propagation and documentation: Task 5.

The plan keeps `engine_type` internal and stable, uses database execution rows as the source of queue truth, and does not require a new alias table or Redis progress protocol.
