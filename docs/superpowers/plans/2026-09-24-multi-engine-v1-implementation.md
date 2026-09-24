# 移动应用多引擎检测平台 V1.0 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 按冻结的 V1.0 总体设计，将当前项目从“串行适配器 + 混合事件展示”升级为可恢复的多引擎执行平台，并先以 MobSF 完成第一条完整 Reference Implementation，再迁移 Androguard、AppShark 和 Platform Finding。

**Architecture:** 保留 FastAPI、PostgreSQL 和 Redis Streams；以 `ScanTask → EngineExecution → Artifact → Observation → PlatformFinding → Report` 为主链路。Redis 只做调度通知，数据库保存状态事实；Worker 通过 Lease/CAS 获取执行权，Adapter 负责引擎专属逻辑，TaskDetail 展示执行过程，TaskReport 展示风险结论。

**Tech Stack:** FastAPI、SQLAlchemy/PostgreSQL、Alembic、Redis Streams、Python async/process executors、httpx、Vue 3、Element Plus、pytest。

**Spec:** `docs/superpowers/specs/2026-09-24-multi-engine-detection-v1-design.md`

## Global Constraints

- V1.0 仅正式实现 Androguard、AppShark、MobSF 静态域；动态域仅保留 Schema/API。
- Androguard = Facts；AppShark = Privacy Data Flow；MobSF = Mobile Security Observation。
- 结果流水线固定为 `Raw Artifact → Observation → Platform Finding`。
- TaskDetail 是执行视角；TaskReport 是风险视角；一级报告导航不使用引擎名。
- AppShark 原生参数必须以当前代码 `ArgumentConfig`/官方已验证字段为准；平台 Executor 参数必须与原生参数明确分离。
- MobSF 记录运行实例实际版本和 Provider hash；Provider hash 不作为 APK 身份。
- 每次重试新建 EngineExecution；历史失败记录不可覆盖。
- Lease/CAS、动态 Cancellation Token、ArtifactStore、Fingerprint 作用域和 schema version 是强制要求。
- 本计划不实现 JADX、Quark、FlowDroid、动态 Agent、首阶段并行调度或复杂 AI 自动判漏。

---

## 当前代码与计划映射

- `frontend/src/views/Workspace.vue` 当前只提交引擎字符串数组，需要改为 V1 Task Config Schema。
- `backend/app/tasks/orchestrator.py` 当前串行创建静态任务，需要增加 Execution Planner 和按引擎配置解析。
- `backend/app/engine/worker.py` 当前直接写状态，需要迁移到 Repository/Lease/CAS。
- `backend/app/engine/adapters/` 当前是 Androguard/AppShark/MobSF 兼容适配器，需要逐个迁移到统一 Adapter Contract。
- `backend/app/models/__init__.py` 已有部分 EngineExecution/Artifact/Observation 字段，需要补齐核心实体和 ExecutionEvent。
- `frontend/src/views/TaskDetail.vue` 当前混合子任务和事件流，需要变为执行控制台。
- `frontend/src/views/TaskReport.vue` 当前混合聚合事件，需要重构为概览/风险/数据流/应用事实/SDK与第三方/证据。

---

## Phase 0：Foundation

### Task 1: Versioned Task Config Schema

**Files:** `backend/app/services/task_config.py`, `backend/app/schemas/__init__.py`, `backend/app/api/v1/tasks.py`, `backend/app/tasks/orchestrator.py`, `frontend/src/views/Workspace.vue`, `backend/tests/test_task_config_schema.py`

- [ ] 定义 `schema_version=1.0` 的 `static.engines.{engine_type}.enabled/config` 和 `dynamic.enabled/scenarios` 结构。
- [ ] 写测试：新版 schema 选择引擎、旧 `engines` 数组兼容、默认值合并、Secret 脱敏、canonical config hash。
- [ ] 实现 `normalize_task_config`、`enabled_engine_types`、`resolved_task_config`、`redact_task_config`、`task_config_hash`。
- [ ] 修改 Workspace 提交结构，保留旧任务读取兼容。
- [ ] 将 resolved snapshot/hash 注入 EngineExecution，禁止写入 API Key/Authorization/password。
- [ ] 运行：`PYTHONPATH=. /tmp/venv/bin/pytest tests/test_task_config_schema.py -q`。
- [ ] 提交：`feat: add versioned multi-engine task config`。

### Task 2: Adapter Contract、Error Model、Cancellation Token、ArtifactStore

**Files:** `backend/app/engine/base.py`, `backend/app/engine/errors.py`, `backend/app/engine/artifacts.py`, tests

- [ ] 将 `EngineExecutionContext` 扩展为 `task_id/execution_id/engine_type/apk_artifact_id/apk_sha256/workspace_id/work_dir/deadline/resolved_config/trace_id`。
- [ ] 保留旧 TaskContext/AdapterResult 兼容性，新增 `validate/prepare/execute/poll/collect/normalize/cancel/cleanup` 默认契约。
- [ ] `CancelToken.is_cancelled()` 通过动态 Repository callback 查询，不使用创建时快照。
- [ ] 错误码和 `AdapterError` 统一返回 user/debug/provider/retryable/stage；敏感字段不得序列化。
- [ ] ArtifactStore 提供 `put/get/open/exists/delete/get_download_url`；V1 实现 `LocalArtifactStore`，返回 URI、SHA256、size、content_type、schema_version。
- [ ] 写并运行契约测试；提交：`feat: formalize engine execution foundation`。

### Task 3: Execution 数据模型、ExecutionEvent、Lease/CAS

**Files:** `backend/app/models/__init__.py`, `backend/app/engine/repository.py`, `backend/alembic/versions/`, tests

- [ ] 完善 `EngineExecution`：attempt/root/parent/latest、stage/progress、queued/started/heartbeat/finished、worker/lease/state_version、cancel/error/provider/config/fingerprint 字段。
- [ ] 新增 `EngineExecutionEvent`，记录不可变的 from/to status、stage、message、state_version、时间。
- [ ] 保留 `EngineArtifact`、`Observation`、`FindingObservation`，补齐 schema version 和索引。
- [ ] 写 Alembic 迁移：可重复执行、检查已有列/表，不使用 `create_all()` 代替正式升级。
- [ ] 实现 repository：`claim_execution`、`cas_update_execution`、`heartbeat_execution`、`request_cancel`、`is_cancel_requested`、`transition_execution`。
- [ ] 状态迁移严格执行：`queued → preparing → validating → running → collecting → normalizing → completed`，异常进入 failed/timed_out/canceling→canceled；终态不可迁移。
- [ ] 测试 stale worker、租约过期接管、终态保护、重复 Claim、CAS 失败；提交：`feat: enforce leased execution state machine`。

### Task 4: Execution Planner 与 Worker Claim-first

**Files:** `backend/app/tasks/orchestrator.py`, `backend/app/engine/worker.py`, `backend/app/tasks/engine_queue.py`, API/tests

- [ ] 提交任务时创建每个启用静态引擎的 queued EngineExecution，保存 resolved config snapshot/hash、fingerprint、cache_scope。
- [ ] Worker 消费 Redis 后只 Claim 数据库 Execution；Claim 失败禁止调用 Adapter。
- [ ] 所有状态/阶段/进度/心跳/错误/结果更新改为 CAS；取消在阶段切换、长轮询、normalize 批处理前实时检查。
- [ ] 重复 Redis 消息不得重复执行；旧 Worker CAS 失败后停止写入。
- [ ] 队列 API 保留旧字段并增加 `stage_message/progress/error_code/retryable/heartbeat_at/finished_at/provider_hash`。
- [ ] 测试重复投递、kill worker 后租约接管、取消、失败 attempt；提交：`feat: migrate worker to claim-first lifecycle`。

### Task 5: Phase 0 Verification

**Files:** `backend/tests/test_phase0_acceptance.py`, `README.md`

- [ ] 验证迁移前后 `engine_executions/engine_execution_events/engine_artifacts/engine_observations` schema。
- [ ] 验证所有 API 不返回 Secret；验证 fingerprint 包含 resolved config hash 和 workspace/tenant scope。
- [ ] 运行：`cd backend && PYTHONPATH=. /tmp/venv/bin/pytest -q`。
- [ ] 运行：`cd frontend && npm run build`。
- [ ] 文档明确升级顺序：Alembic → API restart → Worker restart → frontend restart。
- [ ] 提交：`docs: document phase zero operations`。

---

## Phase 1：MobSF Reference Implementation

### Task 6: MobSF Capability Probe、Health/Auth 和 Provider Metadata

**Files:** `backend/app/engine/adapters/mobsf.py`, `backend/app/engine/registry.py` 或 `worker.py`, config API/tests

- [ ] 健康检查记录服务可达、API Key、Provider version/build/mode；不能硬编码实例版本。
- [ ] Capability Probe 判断 Async/Sync 能力；配置 `MOBSF_ASYNC_ANALYSIS` 时优先 Async，失败再兼容 Sync。
- [ ] 错误映射：不可达、401/403、413、5xx、Provider timeout、空结果、JSON 解析失败。
- [ ] API Key 只从服务配置解密到内存，不进入 resolved snapshot、日志或 fingerprint。
- [ ] 添加 fixtures 目录保存真实 MobSF JSON（脱敏），测试 health/auth/provider metadata。
- [ ] 提交：`feat: add MobSF capability and provider probe`。

### Task 7: MobSF Upload/Async-Sync/Collect/Artifact

**Files:** `backend/app/engine/adapters/mobsf.py`, `backend/app/engine/artifacts.py`, `backend/app/models/__init__.py`, tests

- [ ] 实现阶段：`mobsf_validating → uploading → scan_starting → scanning → collecting → normalizing`。
- [ ] 上传成功保存 Provider scan hash；区分平台 `apk_sha256` 与 Provider hash。
- [ ] Async 模式轮询结果生成；Sync 模式兼容完整 JSON；不能以单个 HTTP 200 认定完成。
- [ ] 原始 JSON 先写 ArtifactStore，再进入 normalize；解析失败保留 Artifact。
- [ ] 保存 `provider_scan_hash/provider_execution_id/provider_version/provider_mode/raw_result_hash`。
- [ ] 测试正常、不可达、认证失败、413、5xx、空结果、扫描超时、解析失败；提交：`feat: implement MobSF reference lifecycle`。

### Task 8: MobSF Observation Parser

**Files:** `backend/app/engine/parsers/mobsf.py`, fixtures/tests, `backend/app/models/__init__.py`

- [ ] 根据真实 fixture 解析 Manifest、Certificate、Network Security、Code Security、Crypto、Secret、Tracker、Malware、Permission、Exported Component、URL/Domain。
- [ ] 统一 Observation：`source_engine/engine_version/observation_type/category/rule_id/severity/confidence/evidence_level/payload/schema_version`。
- [ ] 静态不确定结论使用 `observed/potential/unknown`，不把静态证据伪装成运行时 confirmed。
- [ ] Parser contract tests：fixture schema、空字段、未知字段、部分报告和 parser failure。
- [ ] 提交：`feat: normalize MobSF observations`。

### Task 9: TaskDetail Reference Lifecycle

**Files:** `backend/app/api/v1/tasks.py`, `backend/app/api/v1/engines.py`, `frontend/src/views/TaskDetail.vue`, `frontend/src/views/Queue.vue`, tests

- [ ] TaskDetail 作为运行控制台展示引擎别名、状态、阶段、stage_message、progress、耗时、错误码、重试、Artifact/log 入口。
- [ ] 提供单引擎 retry API；只创建新 attempt，不重跑成功引擎。
- [ ] 队列显示等待/执行/收集/标准化和当前阶段；旧历史任务仍可查询。
- [ ] 验证 MobSF 从新任务到 Raw JSON/Observation/TaskDetail 完整闭环。
- [ ] 提交：`feat: expose MobSF execution console`。

---

## Phase 2：Androguard

### Task 10: Androguard Runner 与 Facts Observation

**Files:** `backend/app/engine/adapters/androguard.py`, `backend/app/engine/runners/androguard_runner.py`, parser/tests

- [ ] 独立 process/spawn runner，超时 `terminate → grace → kill`。
- [ ] 固定 Androguard 4.1.4；提取 metadata、Manifest、permission、component、deeplink、certificate、DEX class/method、endpoint、string candidate、sensitive API、native library。
- [ ] Facts 只生成 Observation，不直接生成平台 Finding。
- [ ] 保存 structured-result.json 和 Artifact，测试 APK 错误、解析超时、正常事实输出。
- [ ] 提交：`feat: implement Androguard facts runner`。

---

## Phase 3：AppShark

### Task 11: AppShark Executor 与 Source-Sink Observation

**Files:** `backend/app/engine/adapters/appshark.py`, `backend/app/engine/runners/appshark_runner.py`, rule registry/parser/tests

- [ ] 独立进程、PID/process group、JDK、memory、timeout、stdout/stderr、exit code 和 cleanup。
- [ ] 仅使用已验证 AppShark 原生参数：`apkPath/out/rules/rulePath/maxPointerAnalyzeTime/debugRule`；平台 rule_groups 映射到规则注册表。
- [ ] 记录 jar_sha256、JDK version、rule_pack_hash、config_hash。
- [ ] 输出 `dataflow.privacy/security` Observation；third_party/encrypted/before_consent 使用三态。
- [ ] 测试正常、进程崩溃、确定性超时、取消和原始结果保留；提交：`feat: implement AppShark dataflow executor`。

---

## Phase 4：Platform Finding

### Task 12: Correlation、FindingObservation、MASVS/MASWE/MASTG

**Files:** `backend/app/models`, `backend/app/services/correlation.py`, `backend/app/api/v1/tasks.py`, fixtures/tests

- [ ] 新增 PlatformFinding 的 triage_status 和 baseline_state。
- [ ] 新增 FindingObservation 多对多关联。
- [ ] 首批规则：权限 + 数据流、导出组件、Tracker、硬编码密钥、网络安全配置。
- [ ] 映射 `MASVS → MASWE → MASTG`，规则版本化；AI 只生成摘要/解释/建议，不替代证据。
- [ ] 实现 dedup_key、new/unchanged/changed/resolved/reintroduced。
- [ ] 提交：`feat: add platform finding correlation`。

---

## Phase 5：产品 UI 与总验收

### Task 13: TaskReport 风险视图

**Files:** `frontend/src/views/TaskReport.vue`, report APIs/components/tests

- [ ] 一级导航固定：概览、风险、隐私数据流、应用事实、SDK与第三方、证据。
- [ ] 概览展示风险数量、检测覆盖、重点 Finding，不用混合事件总数作为主指标。
- [ ] 数据流页面展示 Source/Sink/path/evidence_level/三态评估。
- [ ] 应用事实页面展示 Androguard Facts，不默认显示漏洞标识。
- [ ] 安全观察页面展示 MobSF 分类、Provider 信息、原始 JSON 下载。
- [ ] 统一报告通过 Platform Finding 关联多个 Observation。
- [ ] 提交：`feat: add unified multi-engine report views`。

### Task 14: 安全、运行和稳定性验收

- [ ] 验证文件大小/MIME/APK 结构、随机工作目录、参数数组、路径穿越和 symlink 防护。
- [ ] 验证正常、不可达、API Key 错误、APK 错误、413、Provider 5xx、超时、取消、kill -9、Lease 接管、Redis 重复投递、fingerprint 复用、Parser 失败/重解析。
- [ ] 运行后端测试、前端 build、Alembic upgrade head、API smoke、真实 MobSF fixture/reference scan。
- [ ] 更新 README 运维和故障排查。
- [ ] 提交：`test: complete multi-engine v1 acceptance`。

## Self-review coverage

- 任务配置和引擎契约：Task 1–2。
- EngineExecution、Event、Lease/CAS、Cancellation：Task 3–4。
- MobSF 完整 Reference Implementation：Task 6–9。
- Androguard Facts：Task 10。
- AppShark Data Flow：Task 11。
- Observation→Platform Finding/MASWE：Task 12。
- TaskDetail/TaskReport/证据中心：Task 9、13–14。
- 安全边界、幂等、重复投递、崩溃恢复：Task 3–5、14。
