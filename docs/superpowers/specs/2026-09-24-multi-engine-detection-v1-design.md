# 移动应用多引擎检测平台 V1.0 总体设计基线

## 1. 建设目标与范围

V1.0 解决三引擎检测中的执行稳定性、队列可观测性、失败诊断、原始结果留存、统一结果关联和报告展示问题。

V1.0 正式实现静态检测域：

- Androguard：APK Facts；
- AppShark：Privacy Data Flow；
- MobSF：Mobile Security Analysis。

动态检测域仅保留 Schema 和接口，不在 V1.0 实现 Dynamic Agent。

V1.0 必须做到：

```text
统一执行框架
可排队、可观察、可诊断、可超时、可取消、可重试、可恢复
原始结果完整保留，解析器可独立升级
Raw Artifact → Observation → Platform Finding
TaskDetail = 执行视角
TaskReport = 风险视角
```

## 2. 引擎职责边界

```text
Androguard → Facts：APK 客观事实
AppShark   → Data Flow：敏感数据 Source-Sink 流向
MobSF      → Security Observation：移动安全观察
平台规则层 → 关联、去重、风险判断、合规结论和整改建议
```

### Androguard

固定使用 Androguard 4.1.4。负责应用信息、Manifest、权限、组件、Intent Filter、Deep Link、证书、签名、DEX 类/方法、字符串、URL/Domain/IP、敏感 API 和 Native Library。Facts 默认生成 Observation，不直接生成平台漏洞结论。

### AppShark

负责 Source、Sink、Source-Sink Path、Call Chain、隐私数据类别、潜在第三方流向和网络流向。AppShark 原生参数以当前代码中的 `ArgumentConfig` 为准；V1.0 不在 UI 创造未经验证的原生参数。平台侧的 `rule_groups`、`scan_timeout`、`jvm_memory_mb` 属于 Executor 配置，不冒充 AppShark 原生参数。

### MobSF

负责 Manifest、证书、网络安全、代码安全、Crypto、硬编码密钥、Tracker、恶意指标、权限、导出组件、URL/Domain、Files、Firebase、WebView 和签名观察。平台记录运行实例实际版本、构建信息、commit 或容器镜像摘要（能采集则采集），不把版本写死为注册表常量。

## 3. 总体架构

```text
Workspace → ScanTask → Execution Planner
                         ├── Androguard Adapter
                         ├── AppShark Adapter
                         └── MobSF Adapter
                                  ↓
                           EngineExecution
                                  ↓
                             ArtifactStore
                                  ↓
                              Raw Result
                                  ↓
                                Parser
                                  ↓
                             Observation
                                  ↓
                 Correlation / Rules / Deduplication
                                  ↓
                         Platform Finding
                                  ↓
                    Security / Privacy Result / Report
```

## 4. 核心实体

V1.0 核心实体固定为：

```text
ScanTask
EngineExecution
EngineExecutionEvent
Artifact
Observation
PlatformFinding
FindingObservation
```

### ScanTask

代表用户的一次检测意图，字段包括：

```text
workspace_id, app_id, app_version_id
apk_artifact_id, apk_sha256
preset, config_schema_version, config_snapshot, config_hash
status, created_by, created_at, started_at, finished_at
task_timeout_seconds, cancel_requested_at, cancel_reason
```

任务状态：

```text
queued, running_static, completed, completed_with_warnings, failed, canceled, timed_out
```

### EngineExecution

代表一个引擎的一次实际尝试。每次重试创建新记录，不修改历史失败记录。

```text
id, task_id
engine_type, engine_version, adapter_version, rule_pack_version
attempt_no, root_execution_id, parent_execution_id, is_latest
status, stage, stage_message, progress
queued_at, started_at, stage_changed_at, heartbeat_at, finished_at
duration_ms
worker_id, lease_token, lease_expires_at, state_version
cancel_requested_at
error_code, error_message, debug_message, provider_status, retryable
provider_execution_id, provider_scan_hash
resolved_config_snapshot, resolved_config_hash, execution_fingerprint
raw_artifact_count, observation_count, finding_count
```

`finished_at` 是终止时间唯一事实字段；旧 API 的 `completed_at` 映射为 `finished_at`。

## 5. 任务配置 Schema

不再使用 `engines: ["androguard", "appshark", "mobsf"]`，统一采用：

```json
{
  "schema_version": "1.0",
  "preset": "full_mobile_assessment",
  "static": {
    "engines": {
      "androguard": {
        "enabled": true,
        "config": {
          "parse_timeout": 300,
          "extract_strings": true,
          "extract_endpoints": true,
          "analyze_sensitive_apis": true,
          "analyze_certificates": true
        }
      },
      "appshark": {
        "enabled": true,
        "config": {
          "rule_groups": ["privacy_identity", "privacy_location", "privacy_contacts", "privacy_network"],
          "max_pointer_analyze_time": 300,
          "scan_timeout": 1800,
          "jvm_memory_mb": 4096
        }
      },
      "mobsf": {
        "enabled": true,
        "config": {"scan_timeout": 1800, "prefer_async": true}
      }
    }
  },
  "dynamic": {"enabled": false, "scenarios": []}
}
```

配置优先级：

```text
System Default → Workspace Default → Task Override → Resolved Config
```

EngineExecution 保存脱敏的 `resolved_config_snapshot` 和 `resolved_config_hash`。API Key、密码和 Authorization 不进入快照。

## 6. Adapter Contract

```python
class EngineAdapter:
    async def validate(self, ctx) -> ValidationResult: ...
    async def prepare(self, ctx) -> PrepareResult: ...
    async def execute(self, ctx) -> ExecuteResult: ...
    async def poll(self, ctx, handle) -> PollResult: ...
    async def collect(self, ctx, handle) -> RawResult: ...
    async def normalize(self, ctx, raw_result) -> NormalizeResult: ...
    async def cancel(self, ctx, handle) -> CancelResult: ...
    async def cleanup(self, ctx) -> None: ...
```

Worker 不允许按引擎类型编写专属分支；引擎专属逻辑放入 Adapter、Executor 和 Parser。

ExecutionContext 至少包含：

```text
task_id, execution_id, engine_type, apk_artifact_id, apk_sha256
workspace_id, work_dir, deadline, resolved_config, trace_id
```

取消使用动态 Token/Repository 查询，不使用创建时的布尔快照。

## 7. 状态机与 Lease/CAS

主状态：

```text
queued → preparing → validating → running → collecting → normalizing → completed
```

异常分支：

```text
任意非终止状态 → failed
任意非终止状态 → timed_out
任意非终止状态 → canceling → canceled
```

终止状态不可再次迁移；重试创建新的 EngineExecution。

Worker Claim 使用：

```text
worker_id
lease_token
lease_expires_at
state_version
heartbeat_at
```

状态更新必须使用：

```sql
UPDATE engine_execution
SET status = :status, stage = :stage, state_version = state_version + 1
WHERE id = :id
  AND lease_token = :lease_token
  AND state_version = :expected_version
  AND lease_expires_at > :now;
```

更新 0 行即代表失去执行权，旧 Worker 必须停止写状态、Observation、Artifact 和 Finding。Redis 只负责调度通知，数据库是状态事实来源。

## 8. ArtifactStore 与结果模型

原始结果不直接依赖本地路径字段，统一通过 ArtifactStore：

```python
put(), get(), open(), exists(), delete(), get_download_url()
```

Artifact 字段：

```text
id, task_id, execution_id, artifact_type
storage_backend, storage_uri, sha256, size, content_type
schema_version, created_at, retention_until
```

结果流水线：

```text
Raw Artifact → Engine Observation → Platform Finding
```

### Observation

```text
id, task_id, execution_id
source_engine, engine_version
observation_type, category, rule_id, rule_version
severity, confidence, evidence_level
subject, location, payload, fingerprint, schema_version
```

`evidence_level`：

```text
observed, potential, confirmed, inferred, unknown
```

### Platform Finding

```text
finding_code, title, category, subcategory
severity, confidence, triage_status, baseline_state
description, impact, recommendation
masvs_controls, maswe_ids, mastg_test_ids, cwe_ids
correlation_rule_id, correlation_rule_version, dedup_key
first_seen_at, last_seen_at, resolved_at, observation_count, schema_version
```

Observation 与 Finding 通过 `FindingObservation` 多对多关联。三个引擎的证据可以共同支持一个平台风险，不将 Finding 强制归属单一引擎。

## 9. 引擎执行实现

### Androguard

使用独立 Runner/Process，避免同步解析阻塞主 Worker；超时后 `terminate → grace period → kill`。只生成 Facts Observation，不直接生成漏洞结论。

### AppShark

使用独立 Executor 管理 JDK、JAR、PID、进程组、stdout、stderr、CPU、内存、超时和退出码。公开原生配置以当前 `ArgumentConfig` 为准；平台规则组通过规则注册表映射为实际规则文件。保存 `results.json`、可用的 `profile.json`、日志和 resolved AppShark 配置。

AppShark Observation 使用 `dataflow.privacy` 或 `dataflow.security`，对 `third_party`、`encrypted`、`before_consent` 使用 `true/false/unknown`，并保存 confidence/evidence。

### MobSF

优先探测并使用异步模式，兼容同步模式：

```text
Capability Probe → Async preferred → Sync fallback
```

阶段：

```text
mobsf_validating → mobsf_uploading → mobsf_scan_starting
→ mobsf_scanning → mobsf_collecting → mobsf_normalizing
```

严格区分平台 `apk_sha256` 与 Provider `provider_scan_hash`，记录：

```text
provider, provider_scan_hash, provider_execution_id, provider_version, provider_mode
```

不得仅以 HTTP 200 判断扫描完成，必须确认报告已经生成；原始 JSON 先进入 ArtifactStore，再进行 Parser。

## 10. 错误、重试与幂等

错误模型：

```json
{
  "error_code": "ENGINE_AUTH_FAILED",
  "retryable": false,
  "user_message": "MobSF 认证失败",
  "debug_message": "HTTP 401",
  "provider_status": 401,
  "stage": "mobsf_validating"
}
```

RetryPolicy 按 `engine + error_code + stage` 判断。默认 `max_retries = 3`，即初始执行加最多三次重试，退避 10s/30s/60s。认证、配置、APK 解析和确定性 AppShark 超时不自动重试；网络不可达、Provider 5xx、进程崩溃可重试。

Fingerprint 使用 canonical JSON：

```text
apk_sha256 + engine_type + engine_version + adapter_version
+ rule_pack_version + resolved_config_hash + cache_scope
```

缓存至少按 workspace/tenant 隔离。Parser 另有 `parser_fingerprint`，允许不重新扫描而重新解析 Raw Artifact。

## 11. TaskDetail 与 TaskReport

### TaskDetail：执行控制台

展示：

```text
引擎别名、状态、当前阶段、stage_message、progress、耗时
错误码、用户提示、是否可重试、时间线、Artifact 和日志入口
```

失败时提供：

```text
重新执行本引擎
查看日志
前往引擎配置
```

### TaskReport：风险视图

一级导航固定为：

```text
概览
风险
隐私数据流
应用事实
SDK 与第三方
证据
```

不以 Androguard/AppShark/MobSF 作为一级 Tab；引擎作为来源过滤条件。

#### 概览

展示风险数量、覆盖状态、重点 Finding 和检测完整性，不把混合事件总数作为核心指标。

#### 应用事实

承载 Androguard：应用信息、Manifest、权限、组件、导出组件、Deep Link、DEX、Endpoint、Sensitive API、证书和 Native Library。Facts 不默认显示红色漏洞标识。

#### 隐私数据流

承载 AppShark：数据类别、Sink、路径、Source/Sink API、规则、严重性、置信度、三态评估和原始 `results.json`/`profile.json`。

#### 安全观察

承载 MobSF：Manifest、Certificate、Network Security、Code Security、Crypto、Secrets、Tracker、Malware、Permission 和 Exported Component，显示 Provider 版本、扫描时间、Provider hash 和原始 JSON 下载。

## 12. API 契约

```text
POST /api/tasks
GET /api/tasks/{task_id}
POST /api/tasks/{task_id}/cancel
GET /api/tasks/{task_id}/executions
POST /api/executions/{execution_id}/retry
GET /api/tasks/{task_id}/timeline
GET /api/tasks/{task_id}/observations
GET /api/tasks/{task_id}/findings
GET /api/tasks/{task_id}/report
GET /api/tasks/{task_id}/artifacts
GET /api/artifacts/{artifact_id}/download
GET /api/engines
GET /api/engines/{engine}/health
POST /api/engines/{engine}/recheck
```

前端不直接请求 MobSF/AppShark；所有调用通过平台后端。

## 13. 安全边界

APK 视为不可信输入。必须有文件大小、扩展名/MIME/APK 结构校验；随机工作目录；参数数组而非 Shell 拼接；工作目录隔离；路径穿越和符号链接防护；Artifact 下载 attachment；凭据脱敏；非 root 执行；临时文件清理。

## 14. 实施顺序

```text
Phase 0 Foundation
1. Task Config Schema
2. EngineExecution 字段迁移
3. EngineExecutionEvent
4. Lease/CAS
5. Adapter Contract
6. Cancellation Token
7. Error Model
8. ArtifactStore

Phase 1 MobSF Reference
9. MobSF Adapter
10. Health/Auth
11. Upload
12. Async/Sync compatibility
13. Raw JSON
14. Artifact
15. MobSF Observation Parser
16. TaskDetail 生命周期

Phase 2 Androguard
17. 独立 Runner
18. Facts Schema
19. APK/Manifest/Component
20. Certificate/DEX
21. Endpoint/API
22. Observation

Phase 3 AppShark
23. Executor Process
24. PID/Process Group
25. JDK/Memory/Timeout
26. Rule Group Mapping
27. Raw Result
28. Source-Sink Observation

Phase 4 Finding
29. Correlation Rules
30. FindingObservation
31. MASVS/MASWE/MASTG
32. Finding Dedup
33. Triage/Baseline

Phase 5 Product UI
34. 新建检测
35. TaskDetail
36. TaskReport
37. Risk Detail
38. Data Flow
39. Application Facts
40. Evidence Center
```

## 15. V1.0 不做

- 新动态检测 Agent；
- JADX、Quark、FlowDroid；
- 复杂 AI 自动判漏；
- 引擎自行生成最终报告；
- 第一阶段并行调度；
- 未经当前 AppShark 代码确认的原生参数；
- MobSF URL/API Key 下沉到任务页面；
- 删除旧 Task 历史失败记录；
- 为处理单引擎失败而重跑成功引擎。

## 16. 第一轮验收

必须覆盖：

```text
正常完成、服务不可达、API Key 错误、APK 错误、HTTP 上传失败
扫描启动失败、Provider 5xx、扫描超时、主动取消
Worker kill -9、Lease 失效接管、Redis 重复投递
相同 fingerprint 重复提交、Raw Result 成功/Parser 失败
Parser 升级重新解析、旧 Worker 无法覆盖新状态
```

V1.0 首先只以 MobSF 完成从创建任务到 Raw JSON、Observation 和 TaskDetail 的完整 Reference Implementation，再迁移 Androguard 和 AppShark。
