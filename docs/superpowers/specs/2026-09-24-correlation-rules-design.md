# Correlation 规则体系与规则管理设计

## 1. 背景与目标

当前平台的关联规则是硬编码在 `backend/app/services/correlation.py` 中的 Python 列表，只有一条规则，标准映射（MASVS/MASWE/MASTG）硬编码在 `finding_baseline.py` 中。这导致：

- 无法新增规则而不改代码；
- 无法查看规则命中情况；
- 规则变更后历史结论无法解释；
- 标准映射与规则分离，容易漂移。

本设计建立可持久化、可版本化、可在界面查看与维护的关联规则体系，并保证历史结论可复现。

## 2. 业界调研结论

本节结论来自对多引擎检测平台、规则引擎与标准框架的调研，优先引用一手来源。

### 2.1 分层数据模型

OCSF 生态把检测链路拆分为五层，并明确 match/sighting 是管道产物而非事件类型：

```text
Source event   → 进入检测的活动或观察
Match/sighting → 满足匹配逻辑的证据
Detection Finding → 有独立身份、证据、triage 字段和生命周期的分析结论
Alert          → 标记 is_alert 的事件
Incident       → 进入处置流程的 finding
```

来源：Tenzir detections 文档、OCSF detection_finding schema。

标识符分层是关键：`finding_info.uid` 标识逻辑结论并在整个生命周期保持不变，`metadata.uid` 标识单次发出的事件，规则内容版本化时用 `analytic.version` 记录版本。该分层在 OCSF、AWS Security Hub BatchUpdateFindingsV2 与 Cisco Secure Network Analytics 的 OCSF 导出中均有体现。

### 2.2 规则存储形态

Elastic 官方文档列出三种规则治理模型：VCS 为真源、平台 UI 为真源、混合双向同步。Elastic 同时明确说明，UI 为真源时不具备 VCS 同级别的详细版本历史与回滚能力。

其他已验证实践：

| 项目 | 存储方式 |
|---|---|
| Sigma | YAML + Git，关联规则以 meta rule 表达 |
| sigma-pipeline | `rules/` 目录 + Git，lint/test/diff/deploy 全流程 |
| Datadog | 规则为 JSON，官方推荐用 Terraform 管理以走 PR 审查 |
| MobSF | 单个版本化 YAML，52 条规则，无数据库存储 |
| semgrep-rules | 规则库 + CI |
| MASWE | Markdown + YAML frontmatter，编译为版本化 YAML 发布物 |

没有发现「纯 UI 编辑作为唯一真源」的主流成功案例。

### 2.3 UI 维护规则的真实模式

**只读加重写（Panther）**：厂商规则的 Rule Function 与 Unit Test 编辑器只读灰化，用户仅可修改白名单元数据。Panther 故意禁止在启用状态下编辑 Detection-Pack 规则，以避免被厂商更新覆盖或产生合并冲突。

**编辑即新版本（Splunk ES）**：保存任何改动总是创建新版本；若被修改的版本原本启用，新版本默认不启用，必须显式开启。已知缺陷是带外编辑（Advanced Edit、API、手改 conf）的版本溯源可能延迟约 10 分钟。

**变更请求与审批（ContraForce CMC）**：仓库级开关打开后，所有编辑变为暂存工作项，流程为 edit → work in progress → change request → review → merge，并提供字段级 diff、审批计数与审计记录。

**干跑与命中预览（Elastic、Splunk）**：Elastic rule preview 对历史时间窗执行查询且不产生真实告警；Splunk 的 Testing 状态把结果写入隔离索引，仅出现在只读测试队列中。

### 2.4 标准框架映射

semgrep-rules 把 CWE 内联在规则 metadata 中，格式强制为 `CWE-000: Title`，并用同一套 DSL 编写 meta-rule 做机制化校验，违规级别为 ERROR。MobSF 把 cwe / owasp-mobile / masvs 内联在规则 metadata，52 条规则中 42 条带 MASTG 引用链接。MASWE 在每条 weakness 的 frontmatter 中内嵌 mappings 块。

未发现把标准映射放在独立映射表或外部映射服务的主流做法。

MAS 体系为四层结构：MASVS Control → MASWE Weakness → MASTG Test → MASTG Demo。

### 2.5 规则质量保障

sigma-pipeline 的正反例 fixture 是唯一被明确验证的规则回归测试实践：每条规则一个 fixture 目录，positive 必须命中，negative 必须不命中（要求 negative 是像威胁的良性噪声），测试失败即让构建失败；无 fixture 的规则报告为未测试但不阻塞构建。

### 2.6 多证据关联的条件表达

Sigma 的关联规则共享基础规则元数据，用 `correlation` 属性替换 logsource 与 detection，包含 type、rules、group-by、timespan、condition 五个属性，与基础规则同文件存放。

这属于引用式关联，要求先有基础规则层。本平台当前不具备该前提，因此本期不采用。

## 3. 设计决策

### 3.1 条件表达能力限定为固定模板

本期采用受控条件模板，不支持嵌套逻辑、加权证据、否定条件与正则。理由：

- 当前 Observation 类型有限（fact.*、dataflow.privacy、security.*），完整 DSL 的复杂度无法转化为收益；
- 调研表明纯 UI 自由编辑规则无主流成功案例，受控表单是更安全的起点；
- 模板结构可平滑映射到后续的引用式关联。

### 3.2 复用现有规则表

复用 `rules` 与 `rule_versions`，不新建表。`rules.category = "correlation"` 用于区分关联规则。现有表已具备 `rule_content`(JSONB)、`version`、`status`、`published_by`、`published_at`，正好承载「已发布规则快照」语义。

`rules` 表的定位从「规则真源」调整为「规则版本快照与发布记录」。

### 3.3 保存即新版本，新版本默认不启用

对齐 Splunk ES 的显式启用模型。保存产生草稿版本，必须显式发布才生效。停用规则不删除历史结论。

### 3.4 结论可复现

新增两个字段保证历史结论可解释：

```text
platform_findings.finding_uid            逻辑结论 ID，重复计算保持不变
platform_findings.rule_snapshot          命中时的规则内容快照
```

`correlation_rule_id` 与 `correlation_rule_version` 已存在，继续沿用。

## 4. 数据模型

### 4.1 规则表使用方式

```text
rules
  rule_key            = PRIVACY_CONTACTS_NETWORK
  name                = 通讯录信息网络传输
  category            = "correlation"
  description
  status              = active / disabled
  current_version_id  → 当前生效版本

rule_versions
  rule_id
  version             = "1.0"
  rule_content        = 结构化规则 JSON
  changelog
  status              = draft / published
  published_by / published_at
```

### 4.2 规则内容 Schema

```json
{
  "schema_version": "1.0",
  "match": {
    "logic": "all",
    "conditions": [
      {
        "observation_type": "fact.sensitive_permission",
        "field": "payload.category",
        "operator": "equals",
        "value": "CONTACTS"
      },
      {
        "observation_type": "dataflow.privacy",
        "field": "payload.rule",
        "operator": "contains",
        "value": "_NetworkTransfer"
      }
    ]
  },
  "produce": {
    "finding_code": "PRIVACY_CONTACTS_NETWORK",
    "title": "通讯录信息存在潜在网络传输路径",
    "category": "privacy",
    "severity": "high",
    "confidence": "medium",
    "recommendation": "确认用户授权与隐私政策披露，并对传输数据做最小化与保护。"
  },
  "standards": {
    "masvs": ["MASVS-PRIVACY-1"],
    "maswe": ["MASWE-0001"],
    "mastg": ["MASTG-TEST-PRIVACY-1"],
    "cwe": []
  }
}
```

受控范围：

```text
logic       all / any
operator    equals / contains / exists
field       subject / location / payload.<路径>
```

`exists` 不使用 `value`；`payload.<路径>` 支持一层或多层点号路径，路径不存在视为不匹配。

### 4.3 内置规则的条件必须取自引擎真实产物

上面的条件不是示例值，而是与引擎实际输出对齐的取值：

```text
fact.sensitive_permission  subject 为短名（如 READ_CONTACTS），payload.category 为分类（如 CONTACTS）
dataflow.privacy           payload.rule 为 AppShark 规则名，payload.sink/source 为方法签名列表
```

两个容易踩的坑：`fact.permission` 的条件依赖 `permissions.dangerous`，而 Androguard runner 不产出该键；`payload.sink` 是列表而非对象，用 `payload.sink.category` 永远解析为不匹配。

因此新增或修改内置规则时，必须先取一次真实引擎产物确认字段路径与取值格式，再写条件；fixture 也应取自真实产物，否则测试会与规则互相验证同一个虚构。

## 5. 规则求值器

新增 `backend/app/services/rule_evaluator.py`。

接口：

```python
def validate_rule_content(content: dict) -> None
def evaluate_rule(content: dict, observations: list[dict]) -> list[dict] | None
def evaluate_rules(rules: list[tuple[dict, dict]], observations: list[dict]) -> list[dict]
```

`validate_rule_content` 校验：

- `schema_version` 受支持；
- `logic` 属于 all/any；
- `operator` 属于允许集合；
- `field` 属于允许集合；
- `maswe` 匹配 `MASWE-\d{4}`、`masvs` 匹配 `MASVS-[A-Z]+-\d+`、`mastg` 匹配 `MASTG-[A-Z]+-[A-Z0-9-]+`；
- `finding_code` 非空且为大写标识符。

校验失败抛出明确异常，API 返回 422。

`evaluate_rule` 返回命中的 Observation 列表，未命中返回 None。

`correlate` 的现有行为改为：从数据库读取启用规则，逐条求值，产出与原先相同的 finding 结构。

## 6. Finding 生成与可复现

`finding_service.generate_findings` 调整：

- 使用数据库规则而非硬编码；
- 写入 `finding_uid`：由 `finding_code` 与 `dedup_key` 派生，同一逻辑结论重复计算保持稳定；
- 写入 `rule_snapshot`：命中版本的规则内容；
- 写入 `correlation_rule_id` 与 `correlation_rule_version`。

`finding_baseline.py` 中的 `MAS_MAPPINGS` 硬编码字典删除，标准映射从规则内容读取。

## 7. 后端接口

```text
GET    /api/v1/correlation-rules
GET    /api/v1/correlation-rules/{id}
POST   /api/v1/correlation-rules
PUT    /api/v1/correlation-rules/{id}/versions
POST   /api/v1/correlation-rules/{id}/versions/{vid}/publish
POST   /api/v1/correlation-rules/{id}/disable
POST   /api/v1/correlation-rules/{id}/preview
```

权限沿用 `rule:read` 与 `rule:write`。

`preview` 接受 `task_id`，对该任务的 Observation 重跑关联，返回：

```json
{
  "matched": [{"finding_code": "...", "observation_ids": [1, 2]}],
  "current": ["PRIVACY_CONTACTS_NETWORK"],
  "added": [],
  "removed": []
}
```

预览不写入数据库。

## 8. 前端界面

新增 `frontend/src/views/CorrelationRules.vue`，并在路由与菜单中注册。

```text
规则列表
  规则编号 / 名称 / 类别 / 严重性 / 当前版本 / 状态 / 命中数 / 最近变更

规则详情
  基本信息       表单编辑：名称、描述、启用状态
  匹配条件       结构化表单：观察类型 + 字段 + 操作符 + 值，可增删条件行，logic 为 all/any
  产出定义       标题、类别、严重性、置信度、整改建议
  标准映射       MASVS / MASWE / MASTG / CWE 标签输入
  版本历史       版本列表、字段级差异、发布与回滚
  命中预览       选择任务 → 展示会命中的结论
```

不提供自由代码编辑器。条件部分仅使用下拉框与文本输入。

## 9. 规则质量保障

按 sigma-pipeline 的正反例 fixture 模式建立回归测试：

```text
backend/tests/fixtures/correlation/{rule_key}/
  positive.json   必须命中
  negative.json   必须不命中
```

`pytest` 遍历 fixture 执行求值器，positive 未命中或 negative 命中即失败。

## 10. 迁移

新增 Alembic 迁移：

```text
platform_findings.finding_uid       VARCHAR(64)
platform_findings.rule_snapshot     JSONB
```

迁移需检查列是否已存在，保持可重复执行。

同时提供内置规则种子，把现有硬编码规则写入 `rules` 与 `rule_versions` 的已发布版本。

## 11. 非目标

本期明确不做：

- 嵌套 AND/OR/NOT 条件、加权证据、否定条件、正则；
- Sigma 风格的引用式关联（基础规则 + 关联规则）；
- 规则灰度发布与变更请求审批流；
- 规则命中隔离测试队列；
- AI 参与规则判定。

## 12. 实施顺序

```text
1. 规则求值器与校验器（含单元测试）
2. Alembic 迁移：finding_uid 与 rule_snapshot
3. 规则种子：内置规则写入 rules / rule_versions
4. 改造 correlation 与 finding_service 读取数据库规则
5. 规则管理 API
6. 规则管理前端界面
7. 正反例 fixture 与回归测试
8. 端到端验收
```

## 13. 验收

```text
新建规则 → 保存草稿 → 发布启用 → 提交检测任务 → 产生 Platform Finding
修改规则 → 保存新版本（默认不启用）→ 历史 Finding 的 rule_snapshot 不变
停用规则 → 不再产生新 Finding → 历史 Finding 保留
命中预览 → 不写入数据库
规则校验失败 → 返回 422 且不落库
positive fixture 命中、negative fixture 不命中
```
