# 任务详情页改造 · 实施计划

写于 2026-09-29，供节后执行。**本文所有数字与结论都经过实测**，不是推断。

两个产品决策已于 2026-09-29 定下（见第 2 节），**无遗留待定项，可直接开工**。

---

## 0. 一句话

主视图从「引擎结果罗列」改成「**问题清单**」，`App 背景`侧滑面板承载参考信息，
整改操作内嵌进问题卡片。**开工前必须先做数据层改动**，否则主视图是空的。

---

## 1. 已确认的事实（不要再花时间验证）

### 1.1 当前页面的问题

合规画像 3275px 长、tab 无计数、表格全是重复噪音（「隐私政策」列 6/6 行「无数据」、
「无需权限」6/6 行、权限表 9/14 行同一句「无法判定」）、色彩语义倒挂（0 值用了警告色）。

### 1.2 数据分层（**这是阻塞项的根源**）

| 数据在哪 | 字段 | 取值 | 全库量 |
|---|---|---|---|
| `engine_observations` | `provider_level` | **L2 / L3 / L4** | 7636 / 1912 / 1388 |
| `platform_findings` | `severity` | **high / medium** | 84 / 28 |
| 旧 `findings` 表 | — | — | **0 行** |

**`platform_findings` 没有 `level` 列**；`/report-overview` 读的是旧 `findings` 表，实测返回
`{"total": 0, "by_severity": {}}`。**当前没有任何接口能给「L3 N 条 / L2 M 条」。**

### 1.3 关键：L2/L3/L4 不是严重度阶梯，是三个规则族

| level | observation_type | 含义 | 样例规则 |
|---|---|---|---|
| **L2** | `security.sensitive_api` | 敏感 API **调用点** | `DeviceId_APICall`、`Location_APICall`、`Network_APICall` |
| **L3** | `dataflow.privacy` | **数据流**（数据真的流出去了） | `DeviceId_Log`、`DeviceId_NetworkTransfer` |
| **L4** | `security.other` + 部分 `sensitive_api` | 安全缺陷 | `PendingIntentMutable`、`UnZipSlip`、`ContentProviderPathTraversal` |

同一个规则**不会跨 level**（实测 `having count(distinct provider_level)>1` 返回 0 行）。
代码库里**没有任何地方定义过 level 顺序**。

### 1.4 其余实测结论

| 结论 | 数字 |
|---|---|
| `finding_observations` 关联覆盖 | 11069 行，覆盖全部 112 个 finding ✅ |
| 被关联 observation 的 `location` 覆盖率 | **99.7%**（11040/11069）——调用点可逐条列出 |
| 单任务 finding 数分布 | 1条×6、2条×4、3条×1、4条×8、5条×6、8条×3、9条×1（**中位数 4，最大 9**） |
| `severity` 的推导规则 | `severity = "high" if 有 data_category else "medium"`（`finding_service.py:86`） |
| `triage_status` 取值 | **全库只有 `needs_review`**（112/112） |
| `PlatformFinding` 有无 `assigned_to`/`due_date` | **没有**（在旧 `Finding` 表上） |
| `RetestRecord.original_finding_id` 外键 | → **旧 `findings.id`**，且表 0 行 |
| MobSF `trackers` | **全空**——SDK 识别来自我们知识库（`component_hit` 1162 条） |
| Androguard `endpoints` 去重 | 41 URL → **6 个 host**，`test.bankofyk.com` ×32（**测试服务器残留，合规信号**） |
| AppShark `target` | 是 list，`len(target)` 即节点数 |
| AppShark `details` 真实键 | 只有 `url` / `target` / `position`（**无 `entryMethod`/`sinkMethod`**） |
| `position` 是什么 | **方法签名**，不是文件行号 |
| `details.url` | `/tmp/appshark_out_<id>/...`，**不可访问**，别做 iframe |
| 隐私政策模块 | **0 条政策、0 个关联任务** |

---

## 2. 已定的两个决策（2026-09-29）

### 决策 A：用带语义的构成说明，不用 L2/L3 原始计数

页面展示 **`由 3 条敏感 API 调用 + 2 条数据流构成`**，而不是 `L2×3 · L3×2`。

**语义映射**（实测零反例，可直接用）：

| level | 展示文字 | 规则数 | 规则全貌 |
|---|---|---|---|
| **L2** | 敏感 API 调用 | 11 | `CameraMic_APICall`、`Camera_APICall`、`Clipboard_APICall`、`DeviceId_APICall`、`InstalledApps_APICall`、`Location_APICall`、`Media_APICall`、`Network_APICall`、`Photos_APICall`、`Sensor_APICall`、`Wifi_APICall` |
| **L3** | 数据流 | 6 | `DeviceId_Database`、`DeviceId_FileWrite`、`DeviceId_Log`、`DeviceId_NetworkTransfer`、`DeviceId_WebView`、`Location_NetworkTransfer` |
| **L4** | 安全缺陷 | 5 | `ContentProviderPathTraversal`、`IntentRedirectionBabyVersion`、`MAC`、`PendingIntentMutable`、`unZipSlip` |

**映射成立的依据**：按 `*_APICall` 后缀做反例检查，L2 的 14627 条**全部**命中、L3/L4 的 1864/1300 条
**全部**不命中——**零反例**。所以 `provider_level` 是这三类的可靠判别键，不需要按
`observation_type` 分（L4 里混了 `security.other` 与 `security.sensitive_api` 两类，反而不干净）。

**为什么不用 L4 计数**：L4 是安全缺陷，与隐私合规是两个维度，混在同一个构成说明里会误导。
建议**卡片只展示 L2+L3 的构成**，L4 放到 App 背景面板的「安全加固」块（那里已经在展示
MobSF 的安全数据）。

### 决策 B：不做 `max_provider_level`，排序用 `severity`

§1.3 已证明 L2/L3/L4 **不是严重度阶梯**（是三个规则族），所以"取最严重的 level"无依据。
**这一列不加。**

排序改用现成的 **`severity`**（high/medium，全库 84/28，`generate_direct_findings` 已在写）。

---

## 3. 阶段一：数据层（阻塞项，必须先做）

### 3.1 0a — `platform_findings` 加 level 聚合列

**迁移文件**：`backend/alembic/versions/20260929_finding_level_summary.py`

```python
revision = "20260929_finding_level_summary"
down_revision = "20260929_engine_raw_sections"   # 当前 head（实测确认）
```

加列（**逐列各自判存在**，不要共用一个 `if`——本仓踩过这个坑，见
`alembic/versions/20260928_permission_platform.py:30-38` 的注释）：

| 列 | 类型 | 说明 |
|---|---|---|
| `provider_level_summary` | `JSONB` | 如 `{"L2": 18, "L3": 2, "L4": 4}` |

**只加这一列**（决策 B：不加 `max_provider_level`）。保留 L2/L3/L4 原始计数，
语义映射放在展示层做（决策 A）——**不要把中文写进数据库**，否则以后改文案要动数据。

模型改 `backend/app/models/__init__.py` 的 `class PlatformFinding`（约 :577）。

**聚合挂载点**：`backend/app/services/finding_service.py`

`generate_direct_findings()`（:53）是**幂等**的——已存在的 finding 走
`existing.observation_count = len(obs_ids)`（:79）这一支。**照这个模式加**：

```python
# 在 :79 附近，与 observation_count 一起维护
existing.provider_level_summary = _level_summary(db, obs_ids)
```

新建分支同理（:83 的 `PlatformFinding(...)` 之后）。

> 建议把 `_level_summary()` 写成独立小函数放 `finding_service.py` 里，
> 两处（新建 / 已存在）与 `apply_enrichments()` 共用一个实现，避免三份口径。

**已验证的聚合 SQL**（我实测跑通过，可直接用）：

```sql
select o.provider_level, count(*)
from public.finding_observations fo
join public.engine_observations o on o.id = fo.observation_id
where fo.finding_id = :fid and o.provider_level is not null
group by 1
```

实测输出样例：`{"L3": 13}`、`{"L2": 18, "L3": 2, "L4": 7}`、`{"L2": 319, "L3": 30}`。
**合计与 `observation_count` 对得上**（如 18+2+7=27）。

⚠️ `apply_enrichments()`（:121，另一处 `PlatformFinding(` 在 :206）走的是更新路径，
**也要一起维护这两列**，否则 enrichment 产生的 finding 会是空 summary。

### 3.2 0b — 操作区字段

同一个迁移里加：

| 列 | 类型 | 说明 |
|---|---|---|
| `assigned_to` | `BIGINT REFERENCES users(id)` | 负责人 |
| `due_date` | `DATE` | 截止日期 |

`triage_status` 取值扩展为 `needs_review` / `fixing` / `fixed` / `ignored`
（当前全是 `needs_review`）。**只需扩展语义，不需要 DDL**（是 `VARCHAR(30)`），
但要在模型注释与 API 校验里写明允许值。

### 3.3 0c — `RetestRecord` 外键迁移

现状：`retest_records.original_finding_id` → `findings.id`（**0 行的旧表**）。

改指向 `platform_findings.id`。因为表里 0 行，可以直接 drop + recreate 外键，无需数据迁移。

### 3.4 0d — 三个缺失接口

都加在 `backend/app/api/v1/tasks.py`：

| 接口 | 说明 |
|---|---|
| `GET /{tid}/platform-findings/{fid}` | 单条详情（含关联 observation 列表） |
| `PUT /{tid}/platform-findings/{fid}/status` | 改 `triage_status` / `assigned_to` / `due_date` |
| `GET /{tid}/retest-records` | 复检记录 |

**注意**：现有 `GET /{tid}/platform-findings`（:356）**每次请求都会调 `generate_findings()`**
重新生成。新增的详情/状态接口不要重复调用生成逻辑，否则会把刚改的状态覆盖掉——
**状态接口必须先 `db.commit()` 再读**，且写状态的操作不能被后续 generate 覆盖
（`generate_direct_findings` 只更新 `observation_count`，不动 `triage_status`，所以是安全的，
但 `apply_enrichments` 需要确认）。

---

## 4. 阶段二：后端接口（含顺带完成的两块）

### 4.1 两个「需新增」的接口可以直接读 `engine_raw_sections`

上轮已建的 `engine_raw_sections` 表（`public` schema）就是为这个用途准备的，
**不用新写解析逻辑**：

| 接口 | 取数方式 |
|---|---|
| `GET /{tid}/endpoints` | `section_path = 'endpoints.urls'`（Androguard）|
| `GET /{tid}/security-findings` | `section_path in ('appsec','secrets','manifest_analysis.manifest_findings','certificate_analysis','sbom')`（MobSF）|

取数示例（已验证可用）：

```sql
select section_path, payload from public.engine_raw_sections
where task_id = :tid and engine_type = 'androguard' and section_path = 'endpoints.urls';
```

`endpoints` 接口要做的加工：**按 host 去重**（41 URL → 6 host），并标记：
- `test.*` / `*test*` → `⚠️ 测试服务器残留`
- 匹配 `component_hit` 的 SDK 域名前缀 → `第三方 SDK`
- 含 `privacy`/`policy` 关键词 → `隐私政策`
- 其余 → 不分类

### 4.2 结论条数据来源

⚠️ **不要用 `/report-overview`**（读旧 `findings` 表，返回 0）。
从 `GET /{tid}/platform-findings` 聚合 high/medium 计数。

---

## 5. 阶段三：前端

### 5.1 页面结构

取消 tab 切换，主视图直接是问题清单；`App 背景`改成右上角按钮 + 右侧滑出面板（480px）；
整改概览折叠在底部。

组件树见设计文档第九节。**复用 `EngineReportViewer.vue`**（props: `{taskId, observationId}`）
——注意它要 **observationId 不是 findingId**，需先通过 `finding_observations` 取。

### 5.2 字段映射（全部对齐实测）

| 展示 | 来源 | 备注 |
|---|---|---|
| `[high]` / `[medium]` | `platform_findings.severity` | 主标签，也是排序键 |
| 规则名 | `platform_findings.title` / `finding_code` | 原样，不做业务语言映射 |
| `由 3 条敏感 API 调用 + 2 条数据流构成` | `provider_level_summary` | 见决策 A 的映射表 |
| `证据 5 处` | `observation_count` | **不是** `vulners[].length` |
| 状态 | `triage_status` | 四态映射见 3.2 |
| 调用点列表 | 关联 observation 的 `location` | 覆盖率 99.7% ✅ |
| 污点路径节点数 | `len(target)` | `target` 是 list |
| 权限冗余 | `guard_mapped && call_site_count == 0` | **不是** `申请 - 使用` |

**构成说明的渲染规则**（决策 A）：

```js
const LEVEL_CN = { L2: '敏感 API 调用', L3: '数据流', L4: '安全缺陷' }
// 只列出现过的档，L2 → L3 → L4 固定顺序，避免同一 finding 每次渲染顺序不同
const parts = ['L2','L3','L4']
  .filter(k => summary?.[k])
  .map(k => `${summary[k]} 条${LEVEL_CN[k]}`)
// 无 summary（0a 未回填的旧数据）时整行不渲染，不要显示 "0 条"
const text = parts.length ? `由 ${parts.join(' + ')}构成` : null
```

> **卡片上建议只列 L2+L3**（隐私维度），L4 是安全缺陷，归到 App 背景面板的「安全加固」块。

### 5.3 代码证据块

- 展示 `location` 的**方法签名原文**
- 「查看完整路径」→ `EngineReportViewer`（IR 代码块）
- **必须标注**：「以下为 IR 代码（smali 风格），非 Java 源码」——实测输出是
  `$r0 := @parameter0: android.content.Context` 这类 IR，不是 Java

### 5.4 网络证据块

按 host 平铺，**不做「业务服务器 / 第三方 SDK」分类**（无法判断），
但 `test.bankofyk.com` 这类要黄色高亮为**测试服务器残留**——这是现成的合规信号。
必须标注「端点与规则的精确关联暂未建立，以上为 App 全部端点」。

---

## 6. 验证清单

### 6.1 每步都要跑

```bash
cd backend && PYTHONPATH=. /tmp/venv/bin/pytest tests/ -q    # 当前基线：371 passed
```

### 6.2 ⚠️ 真实任务验证前必须重启服务

**`uvicorn` 与 `worker` 都没有 `--reload`。** 改完代码不重启就跑任务，会用旧代码执行，
得出「功能没生效」的错误结论（这个坑本轮踩过一次，浪费了一轮）。

```bash
cd backend
pkill -f "app.engine.worker"; pkill -f "uvicorn app.main"
nohup /tmp/venv/bin/python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 > /tmp/uvicorn.log 2>&1 &
sleep 1
nohup /tmp/venv/bin/python -m app.engine.worker > /tmp/worker.log 2>&1 &
sleep 8 && grep "Registered engines" /tmp/worker.log
```

### 6.3 端到端验证

提一个真实任务（`app_version_id=13` 是 25MB 样本，跑完约 30 秒）：

```bash
TOKEN=$(curl -s -X POST http://127.0.0.1:8000/api/v1/auth/login \
  -H 'Content-Type: application/json' -d '{"username":"admin","password":"admin123"}' \
  | python3 -c "import sys,json;print(json.load(sys.stdin)['data']['access_token'])")
TID=$(curl -s -X POST http://127.0.0.1:8000/api/v1/tasks -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' -d '{"app_version_id":13,"detection_type":"static_only","rule_pack_version":"1.0"}' \
  | python3 -c "import sys,json;print(json.load(sys.stdin)['data']['id'])")
curl -s -X POST "http://127.0.0.1:8000/api/v1/tasks/$TID/submit" -H "Authorization: Bearer $TOKEN"
```

然后确认 0a 生效：

```sql
select severity, provider_level_summary, observation_count
from public.platform_findings where task_id = <TID>;
```

**三条断言**：

1. `provider_level_summary` **非空**（空说明聚合没挂上）
2. `sum(summary 的各档计数) == observation_count`（实测基线里两者一致；
   偶有差 1 是因为个别 observation 的 `provider_level` 为空，属正常）
3. `provider_level_summary` 的键**只在 `L2`/`L3`/`L4` 里**，不出现别的值

### 6.4 前端验证

用 playwright 截图（脚本在 `/tmp/shot3.py`，`/tmp/venv/bin/python`），确认无 console error。

---

## 7. 已知陷阱（本轮踩过的）

1. **服务无 `--reload`** —— 见 6.2，最容易浪费时间的坑
2. **测试跑在真实库上** —— `tests/conftest.py:16` 的 `db` fixture 直连业务库，
   跑测试前需 `alembic upgrade head`
3. **alembic 幂等守卫** —— 建表/加列与建索引**必须各自判存在**，共用一个 `if` 会导致
   索引静默补不上（`20260928_permission_platform.py:30-38` 有完整说明）
4. **`/platform-findings` 每次读取都重新生成** —— 见 3.4
5. **归档路径 vs `/tmp`** —— 引擎产物已归档在 `data/evidence/artifacts/`，
   但 `Evidence.artifact_path` 对历史任务仍指向失效的 `/tmp`（按你的选择未回填）
6. **备份习惯** —— 动库前先 `pg_dump` 到 `backup/`，命名 `privacy_platform_YYYYMMDD_HHMM_pre_<原因>.sql.gz`

---

## 8. 工作量估算

| 阶段 | 内容 | 估时 |
|---|---|---|
| 0a | 加列 + 迁移 + 聚合挂载 | 0.5 天 |
| 0b | 加列 + 取值扩展 | 0.5 天 |
| 0c | 外键迁移 | 0.5 天 |
| 0d | 3 个接口 | 1 天 |
| 4.1 | endpoints + security-findings（读 raw_sections） | 0.5 天 |
| 5.1-5.2 | 主视图骨架 + 结论条 + 列表折叠态 | 1.5 天 |
| 5.3 | 展开态 + 代码证据 | 1 天 |
| 5.4 | 网络证据块 | 0.5 天 |
| — | App 背景面板（6 块） | 2 天 |
| — | 操作区 + 整改概览 | 1 天 |
| — | 联调 + 修 | 1.5 天 |
| | **合计** | **约 10 人天** |

**前端可以从 5.1 开始并行**（用 mock 数据），但联调依赖 0a。

---

## 9. 建议的提交切分

按本仓的提交习惯（一个修复一个提交，commit message 写清「现象 → 根因 → 实测数据」）：

1. `feat(finding): platform_findings 聚合 provider_level——主视图需要 L2/L3 分布`
2. `feat(finding): 整改闭环字段（assigned_to / due_date / triage_status 取值）`
3. `fix(retest): RetestRecord 外键从已废弃的 findings 表迁到 platform_findings`
4. `feat(api): platform-finding 详情 / 状态 / 复检记录三个接口`
5. `feat(api): endpoints 与 security-findings 直接读 engine_raw_sections`
6. `feat(ui): 任务详情页改为问题清单主视图`
7. `feat(ui): App 背景侧滑面板`
