# 检测引擎稳定性、统一执行框架与能力深化设计

## 1. 目标与范围

本设计解决当前检测引擎执行过程中的排队不可见、MobSF 失败不可诊断、AppShark 进程阻塞、结果难以复用和三个引擎能力未充分发挥等问题。

首期覆盖 Androguard、AppShark、MobSF；JADX、Quark-Engine、FlowDroid 等后续引擎只需遵循统一 Adapter 接口，不在本期实现。

最终引擎定位：

- Androguard：Facts，提取 APK 客观事实；
- AppShark：Data Flow，分析敏感数据 Source-Sink 流向；
- MobSF：Security Findings，提供移动安全风险、跟踪器和配置扫描；
- 平台规则层：负责去重、合并、风险判断、合规结论和整改建议。

实施分四阶段：

```text
Phase 0 统一执行框架、状态和错误模型
Phase 1 三个引擎稳定执行、可诊断、可超时、可取消、可重试
Phase 2 能力深化与统一结果模型
Phase 3 并行执行、资源调度、优先级和监控
```

## 2. 统一 Adapter 框架

所有引擎实现统一生命周期：

```python
class EngineAdapter:
    def prepare(self, ctx) -> PrepareResult: ...
    def validate(self, ctx) -> ValidationResult: ...
    def execute(self, ctx) -> ExecuteResult: ...
    def poll(self, ctx, execution_id) -> PollResult: ...
    def collect(self, ctx, execution_id) -> RawResult: ...
    def normalize(self, raw_result, ctx) -> NormalizedResult: ...
    def cleanup(self, ctx) -> None: ...
    def cancel(self, ctx, execution_id) -> CancelResult: ...
```

同步引擎不需要实现真正的轮询，但必须通过同一生命周期返回结果。Worker 只负责任务获取、状态推进、超时、取消、重试、资源调度、事务和结果关联；引擎专属的 HTTP、Java、规则和解析逻辑全部留在 Adapter/Executor。

统一 `EngineExecutionContext` 包含：

```json
{
  "task_id": 128,
  "execution_id": 501,
  "engine_type": "mobsf",
  "engine_version": "4.5.4",
  "apk_path": "/data/evidence/apks/base.apk",
  "apk_sha256": "...",
  "rule_version": "1.0",
  "config": {},
  "work_dir": "/data/evidence/task_128/mobsf",
  "deadline": "...",
  "cancel_requested": false
}
```

每个引擎使用独立工作目录；API Key 只在内存配置中使用，不写入上下文日志或数据库快照。

## 3. 状态、阶段、进度与时间

### 3.1 引擎主状态

```text
queued / preparing / validating / running / collecting / normalizing
completed / failed / timed_out / canceled / skipped
```

终止状态为 `completed`、`failed`、`timed_out`、`canceled`、`skipped`。非终止状态不允许被过期 Worker 覆盖。

### 3.2 阶段

`status` 表示大阶段，`stage` 表示具体动作，命名采用 `<engine>_<action>`：

```text
androguard_parsing
androguard_strings
appshark_preparing
appshark_analyzing
appshark_persisting
mobsf_validating
mobsf_uploading
mobsf_scan_starting
mobsf_scanning
mobsf_collecting
mobsf_normalizing
```

同时记录：

```text
stage_message
progress  # 0..100，无法计算时只显示阶段，不伪造精确百分比
```

### 3.3 时间和心跳

`EngineExecution` 增加：

```text
queued_at
stage_changed_at
heartbeat_at
finished_at
```

保留已有 `started_at`、`completed_at`、`duration_ms` 以兼容旧接口。排队时间、实际执行时间和卡死检测必须能够分别统计。

### 3.4 超时

分为任务级、引擎级和阶段级：

- 阶段超时：调用 `cancel()`，失败则强制终止；
- 引擎超时：终止当前引擎并按策略重试；
- 任务超时：终止所有运行引擎，剩余 pending 标记 `skipped`。

超时错误码统一为 `STAGE_TIMEOUT`、`ENGINE_TIMEOUT`、`TASK_TIMEOUT`；第三方服务自身报告的扫描超时使用 `PROVIDER_SCAN_TIMEOUT`。

取消流程为 `canceling → Adapter.cancel() → 资源清理 → canceled`。取消后禁止写入事件和证据，但保留原始结果和日志。

## 4. 错误模型与重试

统一错误对象：

```json
{
  "error_code": "ENGINE_AUTH_FAILED",
  "retryable": false,
  "user_message": "MobSF API Key 验证失败",
  "debug_message": "POST /api/v1/upload returned HTTP 401",
  "provider_status": 401,
  "stage": "mobsf_uploading"
}
```

数据库保存 `error_code`、脱敏的 `error_message`、`debug_message`、`retryable` 和 `provider_status`。敏感凭据、Authorization 和密码必须脱敏。

错误码分类：

```text
ENGINE_ENV_INVALID ENGINE_NOT_INSTALLED ENGINE_CONFIG_INVALID
ENGINE_UNREACHABLE ENGINE_AUTH_FAILED ENGINE_PERMISSION_DENIED
FILE_NOT_FOUND FILE_INVALID FILE_TOO_LARGE FILE_UNREADABLE APK_PARSE_FAILED
UPLOAD_FAILED SCAN_START_FAILED ENGINE_PROCESS_CRASHED SCAN_FAILED
EMPTY_RESULT RESULT_PARSE_FAILED NORMALIZE_FAILED
STAGE_TIMEOUT ENGINE_TIMEOUT TASK_TIMEOUT PROVIDER_SCAN_TIMEOUT TASK_CANCELED CANCEL_FAILED
```

重试以单个 `EngineExecution` 为单位，不重跑整个任务。自动重试最多三次，退避为 10 秒、30 秒、60 秒。网络不可达、上传失败、外部服务 5xx、扫描超时和进程崩溃通常可重试；认证、配置、文件格式和解析错误默认不可自动重试。

人工操作区分：

- 重新执行本引擎；
- 重新执行全部失败引擎；
- 重新执行整个任务。

每次重试保留原始尝试，使用 `attempt_no`、`parent_execution_id`、`is_latest` 标记最新尝试。

## 5. 幂等与结果复用

统一计算 APK SHA256。执行 fingerprint 为：

```text
SHA256(apk_sha256 + engine_type + engine_version + rule_pack_version + adapter_version)
```

相同 fingerprint 已有成功结果时默认复用；强制重新扫描时明确绕过缓存。相同 fingerprint 已处于运行状态时直接返回现有执行，不创建重复执行。

## 6. 原始结果、解析结果和统一结果

结果流水线：

```text
Raw Result → Parser Result → Unified Event / Finding
```

每次执行记录：

```text
raw_result_path
raw_result_hash
raw_result_size
parser_version
parser_status
parser_error
normalized_at
normalized_event_count
normalized_finding_count
```

原始结果必须保留，即使解析失败。重新解析只使用 Raw Result，不重新调用外部引擎。

统一 Event：

```text
id task_id execution_id event_type source_engine engine_version timestamp
app_component data_type api caller source sink evidence_ref payload
```

统一 Finding：

```text
id task_id execution_id finding_code title category severity confidence status
source_engine evidence_refs rule_code rule_version description recommendation dedup_key
```

证据通过 `EvidenceRef` 关联原始结果、日志、截图和输出目录，避免在事件/Finding 中复制大型 JSON。

## 7. 三个引擎能力设计

### 7.1 Androguard Facts

提取基础信息、Manifest、权限、组件、Intent、导出风险、深链、签名证书、DEX 类/方法、URL/域名/IP、敏感字符串、网络/加密/WebView/设备标识/位置/相机/麦克风等 API，并输出类数、方法数、端点数和敏感 API 数统计。

Androguard 只证明 APK 中存在事实，不证明行为必然执行；字符串候选需进入平台规则层，不直接全部判为高风险。

### 7.2 AppShark Data Flow

Source 分类包括设备标识、广告标识、位置、通讯录、电话、短信、相机、麦克风、剪贴板、账号、文件和传感器；Sink 分类包括网络、WebView、日志、文件、数据库和第三方 SDK。

每条数据流记录 Source、Sink、路径、规则、严重性、置信度、是否加密/脱敏、是否流向第三方和是否发生在用户同意前。

规则按 `privacy_identity`、`privacy_location`、`privacy_contacts`、`privacy_camera_microphone`、`privacy_network`、`security_crypto`、`security_webview`、`sdk_tracking` 分组；默认执行完整隐私规则集，专项任务可以选择规则组。

AppShark 使用独立执行器管理 PID、进程组、工作目录、stdout/stderr、超时、内存和 CPU；支持启动、心跳、终止、结果收集和临时目录清理。

### 7.3 MobSF Security Findings

当前 MobSF 4.5.4 实测上传 HTTP 200、扫描 HTTP 200、耗时约 145 秒并返回完整 JSON。适配器分为 validating、uploading、scan_starting、scanning、collecting、normalizing 阶段，保存 MobSF hash、HTTP 状态、原始完整 JSON和服务版本。

解析 manifest、代码、证书、网络安全、恶意指标、跟踪器、权限、文件、URL、域名、Firebase 和导出组件，统一为包含类型、标题、描述、严重性、置信度、组件、位置、建议、证据和引擎版本的 Finding。

## 8. Worker、队列和资源调度

Redis Stream 继续负责任务入口，数据库 `EngineExecution` 是引擎状态事实来源。初期保持串行以保证可诊断：Androguard → AppShark → MobSF；后续支持执行图和并行。

任务状态聚合：

- 任一运行：`running_static`；
- 全部完成：`completed`；
- 完成和失败混合：新增 `completed_with_warnings`；
- 全部失败：`failed`；
- 用户取消：`canceled`。

资源声明：

```json
{
  "engine_type": "appshark",
  "concurrency": 1,
  "cpu_weight": 8,
  "memory_mb": 4096,
  "exclusive": true,
  "queue_name": "heavy-static"
}
```

默认 Androguard 并发 2～4、AppShark 并发 1 且独占、MobSF 并发 1；不超过引擎并发、节点内存预算或未清理的重试资源。

## 9. 监控与验收

增加任务、引擎和队列指标：执行数、成功/失败/部分成功数、耗时、超时、重试、错误码、队列深度、等待时间和运行数。日志必须关联 `task_id`、`execution_id`、`engine_type`、`attempt_no`、`stage`、`error_code`，禁止记录密钥。

首个最小闭环只验证 MobSF：

```text
新任务 → queued → validating → uploading → scanning → collecting → normalizing → completed
```

必须保存任务 ID、执行 ID、APK SHA256、MobSF hash、各阶段时间、HTTP 状态、原始结果路径/哈希和标准化事件数量。随后将相同框架迁移到 AppShark 和 Androguard。

旧任务（如 task 64）的历史失败记录保留，不改写；新尝试单独创建并显示完整生命周期。

## 10. V1.0 基础约束补充

### 10.1 Lease、CAS 与 Worker 接管

`EngineExecution` 增加执行租约字段：

```text
worker_id
lease_token
lease_expires_at
state_version
heartbeat_at
```

Worker 不能仅依赖 Redis 消费组或内存状态获得执行权。领取执行记录时创建租约；所有状态、阶段、进度和结果更新都必须带 `id + state_version + lease_token` 条件：

```sql
UPDATE engine_executions
SET status = :status,
    stage = :stage,
    state_version = state_version + 1
WHERE id = :id
  AND state_version = :expected_version
  AND lease_token = :lease_token
  AND lease_expires_at > :now;
```

更新影响行数为 0 时，Worker 视为已失去执行权，立即停止写状态、标准化结果和证据。Worker 崩溃后由恢复流程在租约过期后重新 Claim，旧 Worker 恢复时不能覆盖新 Worker 的终态。

### 10.2 动态取消令牌

`cancel_requested` 不能只作为创建 Context 时的布尔快照。Context 提供动态取消令牌或执行仓储查询：

```python
ctx.cancel_token.is_cancelled()
# 或
ctx.execution_repo.is_cancel_requested(ctx.execution_id)
```

Worker/Executor 必须在阶段切换、长时间轮询、AppShark 心跳和批量 normalize 前检查取消信号。数据库中的取消状态是事实来源。

### 10.3 完整状态迁移表

正式状态增加 `canceling`，并限制迁移：

```text
queued → preparing → validating → running → collecting → normalizing → completed

任意非终止状态 → failed
任意非终止状态 → timed_out
任意非终止状态 → canceling → canceled
```

终止状态不可再次迁移。重试不执行 `failed → queued` 原地修改，而是创建新的 `EngineExecution` attempt。

### 10.4 超时和重试定义

阶段超时统一使用：

```text
STAGE_TIMEOUT
ENGINE_TIMEOUT
TASK_TIMEOUT
PROVIDER_SCAN_TIMEOUT
```

第三方扫描服务自身报告的超时使用 `PROVIDER_SCAN_TIMEOUT`；某个 Adapter 阶段超时使用 `STAGE_TIMEOUT` 并记录具体 `stage`。

配置统一使用 `max_attempts`，包含初始执行：

```text
max_attempts = 4  # 初始执行 + 最多 3 次重试
```

是否可重试由 `error_code + engine_type + stage` 联合决策。网络不可达、HTTP 502/503/504、网络超时和进程崩溃可以重试；AppShark 在相同资源和相同配置下的确定性超时默认不自动重试，人工重试时应允许提高资源或超时。

### 10.5 带配置和作用域的 Fingerprint

Fingerprint 的输入不是字符串拼接，而是 canonical JSON：

```json
{
  "apk_sha256": "...",
  "engine_type": "appshark",
  "engine_version": "0.1.2",
  "rule_pack_version": "2026.09",
  "adapter_version": "2",
  "normalized_config_hash": "...",
  "cache_scope": "project:10"
}
```

对 canonical serialization 后的 JSON 计算 SHA256。`normalized_config_hash` 包含影响结果的规则组、超时和引擎参数；API Key 等秘密不进入 fingerprint。缓存至少按租户或项目隔离，不能让不同租户读取同一 APK 的成功结果。

### 10.6 三层结果模型

结果模型正式调整为：

```text
Raw Artifact → Engine Observation → Platform Finding
```

`Engine Observation` 表示某个引擎观察到的证据，包含：

```text
observation_id
execution_id
engine_type
observation_type
rule_code
severity
confidence
evidence_refs
payload
```

`Platform Finding` 表示平台规则层合并后的风险结论。通过 `FindingObservationRelation` 关联多个 Observation，因此一个通讯录外传风险可以同时关联 Androguard 权限、AppShark 数据流和 MobSF Manifest 发现，不再强制一个 Finding 归属单一引擎。

### 10.7 三态分析结论

静态分析不能把运行时事实伪装成确定布尔值。以下属性使用 `true / false / unknown`，并附带来源、置信度和证据：

```text
third_party
encrypted
before_consent
```

例如 SDK 指纹可使 `third_party=true`，但仅看到 Crypto API 不足以证明数据在 Sink 前已加密；用户同意前行为通常只能标记为 `unknown`，除非有明确的控制流/运行时证据。

### 10.8 ArtifactStore 与 Schema Version

`raw_result_path` 仅作为兼容字段，不作为长期存储抽象。新增 `ArtifactStore` 接口，数据库保存：

```text
artifact_id
artifact_uri
sha256
size
content_type
storage_backend
retention_until
```

开发环境可使用 `file://`，后续可替换为 MinIO、S3 或 NAS。原始结果、Observation 和 Finding 增加 schema version：

```text
raw_schema_version
observation_schema_version
finding_schema_version
parser_version
```

`finished_at` 是终止时间唯一事实字段；旧接口的 `completed_at` 由 Serializer 映射为 `finished_at`。`duration_ms` 优先由 `finished_at - started_at` 计算，避免两个时间字段漂移。

### 10.9 MobSF provider 标识

MobSF 返回的 `hash` 是 Provider 扫描标识，不是平台 APK 身份。平台必须分开保存：

```text
apk_sha256
provider
provider_scan_id
provider_scan_hash
```

Adapter 同时兼容 `/scan` 同步返回完整 JSON 和返回处理中后通过 `poll()` 再 `collect()` 的模式。

## 11. 实施顺序

```text
Phase 0.1 统一 Adapter 接口、Context、错误对象和状态迁移表
Phase 0.2 EngineExecution 字段迁移、Lease/CAS、Cancellation Token、ArtifactStore 接口
Phase 0.3 Engine Observation 三层模型、schema version、fingerprint 和作用域
Phase 1.1 MobSF reference implementation：validate → upload → scan/poll → collect → normalize
Phase 1.2 AppShark 独立进程、资源限制和生命周期
Phase 1.3 Androguard 事实提取生命周期
Phase 1.4 引擎级重试、取消、崩溃恢复和最小闭环验收
Phase 2.1 三个引擎能力深化和规则分组
Phase 2.2 Raw Artifact、Observation、Finding 去重合并和重新解析
Phase 3.1 队列前端、时间线、错误诊断和人工引擎级重试
Phase 3.2 并行执行、资源调度、优先级和监控
```

## 12. V1.0 验收矩阵

至少覆盖：

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
更换 Parser 后重新解析 Raw Result
租约失效后旧 Worker CAS 更新失败
不同项目/租户不能复用彼此缓存
```
