# Finding 生成与证据关联重设计

## 1. 背景

V1.0 的关联模型是：

```text
Observation → Correlation → Platform Finding
```

即「所有观察都必须经过关联器才能成为结论」。实测证明这个抽象是错的。

### 1.1 直接证据

改造前 AppShark 规则加载存在缺陷（已于 `e203e21` 修复），修复前后在营口银行 v4.5.1 上的对比：

```text
                修复前   修复后
加载规则数        4        20
命中规则数        2        12
关联产出 Finding  0        0
```

**12 条规则真实命中，关联层产出 0 条结论。**

原因不是关联器有 bug，而是唯一的关联规则 `PRIVACY_CONTACTS_NETWORK` 瞄准通讯录，而通讯录在当前引擎能力下没有对应的数据流规则（见 §1.3）。

### 1.2 Provider 语义在 Normalize 阶段被降维

AppShark 的规则文件与结果都携带结构化语义：

```text
规则文件 desc.complianceCategory = PersonalDeviceInformation_NetworkTransfer
结果 payload.rule                = DeviceId_NetworkTransfer
结果 payload.section             = ComplianceInfo
结果 payload.level               = L3
```

但在观测映射阶段被丢弃：

```text
task 553 的 139 条 observation 中，category 列有值的：0 条
```

于是后端只能用字符串匹配把语义「猜」回来：

```python
if value == "network" or "_NetworkTransfer" in rule_name   # 旧关联规则的写法
```

### 1.3 能力边界（已实证）

contacts / sms / calllog 的「读取→外传」在当前配置下不可静态表达：

```text
路径 A  L2 用 URI 常量作 sink              → 零命中
        APIMode 的 sink 列表只匹配方法签名，不识别静态字段常量
路径 B  L3 用 ContentResolver.query 作 source → 零命中
        污点在 LibraryOnly + InstantDefault 模型下不传播到网络 sink
对照组  DEX 确实引用 ContactsContract，且 DeviceId_APICall 命中 18 次
        → 样本无问题，是引擎能力边界
```

结论：**不是规则库缺口，是能力边界。** 该结论直接决定了「不能靠为每个类目写规则来解决问题」。

### 1.4 命名约定不可靠

20 条规则的 `complianceCategory` 实际取值：

```text
符合 Personal<类目>_<流向> 约定     12 条
不符合                              8 条（官方 7 条安全规则 + NetworkRequest_APICall）
```

且符合约定的那 12 条内部仍不一致：

```text
PersonalDeviceInformation_Persist    流向词是 Persist 而非 File
PersonalNetworkEnv_APICall           类目词是 NetworkEnv 而非 NetworkInformation
PersonalMedia_APICall                媒体/相机/麦克风挤在同一类目
```

因此运行时字符串切割必然出错。

## 2. 核心原则

废除：

> Observation 经 Correlation 后形成 Platform Finding。

改为：

> **引擎结果首先标准化为具有稳定语义键的 Observation；具备完整风险语义的 Observation 可直接形成 Finding；跨引擎关联仅通过共享语义键完成证据增强，或推导单个证据不具备的新结论。**

## 3. 三条 Finding 生成路径

```text
                     Observation
                          │
         ┌────────────────┼────────────────┐
         ↓                ↓                ↓
   Direct Finding   Evidence Join    Composite Rule
   直接结论          证据增强          组合推导
         │                │                │
         ↓                ↓                ↓
   Platform Finding ← ENRICH        新 Platform Finding
   (CREATE)          (不新增)        (CREATE)
```

### 3.1 Direct Finding

引擎结果本身已具备完整风险语义时直接生成 Finding。

例如 AppShark 的 source→sink 命中：

```text
设备标识 Source → 完整污点传播路径 → Network Sink
```

这已经是「设备标识存在潜在网络传输路径」，不应再要求「权限 + 数据流 + 关联器」三步才让它出现。

### 3.2 Evidence Join

对已有 Finding 补充证据：

```text
增加证据来源
提升 confidence
补充解释与影响
记录 evidence_refs
```

**不新增 Finding。** 否则会产出同义重复：

```text
F100  设备标识存在网络传输路径        ← Direct Finding
F101  应用具有设备标识权限并存在数据流  ← 错误：同义重复
```

正确关系：

```text
Finding F100
  ├── AppShark Observation    Source → Network
  ├── Androguard Observation  敏感权限/API
  └── MobSF Observation       权限/安全结论
```

### 3.3 Composite Rule

只有两个观察**单独都不能表达完整风险**时才创建新 Finding。

判断标准：

> 合并后有没有产生单个证据本身不具备的新结论？

有 → CREATE；没有 → ENRICH。

例如：`usesCleartextTraffic = true` 单独只说明「允许明文流量」；与「个人信息 → HTTP 端点」结合，才产生「敏感信息存在明文网络传输路径」这一新结论。

### 3.4 result_semantics 由平台定义

**不得**用引擎的 level 字段判断：

```python
if level == "L3": create_finding()      # 错误：L3 是 Provider 语义
```

平台模型：

```text
result_semantics ∈ { fact, supporting_evidence, direct_finding }
```

反例佐证：`unZipSlip` 没有 data_category，但确实是 `direct_finding`。这证明「是否成 Finding」不能由类目或 level 决定。

## 4. 观测语义字段

### 4.1 新增一等字段

`EngineObservation` 增加：

```text
data_category     数据类目（join 的主键）
source_type       数据来源类型
sink_type         流向类型
result_semantics  fact / supporting_evidence / direct_finding
provider_rule_id  Provider 原始规则名（保留，用于回溯）
entity_keys       通用连接键容器
```

不继续只用一个 `category`，因为未来会同时存在风险类别、MASVS 类别、数据类别、MobSF category、规则类别。

### 4.2 data_category 枚举

```text
device_information  advertising_identifier  location      contacts
phone               sms                     camera        microphone
clipboard           account                 calendar      files
photos              sensor                  network_information
installed_apps      biometric               personal_information  unknown
```

枚举允许存在但未被任何引擎填充的值；覆盖度矩阵必须区分「枚举存在」与「引擎可产出」。

### 4.3 sink_type 枚举

```text
network  file  database  log  webview  ipc  clipboard
third_party_sdk  unknown
```

### 4.4 entity_keys

```json
{
  "observation_type": "dataflow.privacy",
  "data_category": "device_information",
  "sink_type": "network",
  "entity_keys": {
    "app_version": "12",
    "data_category": "device_information"
  }
}
```

关联器 JOIN ON `entity_keys`，而不是匹配字面值。

**V1 只填两个键**：`app_version` 与 `data_category`。组件、endpoint、SDK、证书四类连接键等有真实用例再加。

## 5. Rule Semantic Registry

### 5.1 定位

Registry 是**代码 + 测试**，不是可在 UI 编辑的规则。

理由：`PersonalDeviceInformation → device_information` 这类映射改错会使所有关联**静默失效**（join key 对不上，不报错）。它必须像代码一样评审。

```text
Normalization  → 代码 / 配置 + 测试      不可 UI 编辑
Finding        → 数据库规则 + 版本 + UI  可维护
Enrichment     → 数据库规则 + 版本 + UI  可维护
```

### 5.2 结构

```yaml
provider: appshark
provider_rule_id: DeviceId_NetworkTransfer
semantics:
  result_type: direct_finding
  observation_type: dataflow.privacy
  data_category: device_information
  sink_type: network
```

```yaml
provider: appshark
provider_rule_id: unZipSlip
semantics:
  result_type: direct_finding
  observation_type: security.other
  data_category: null          # 合法取值，不是缺失
  sink_type: file
```

```yaml
provider: appshark
provider_rule_id: DeviceId_APICall
semantics:
  result_type: supporting_evidence
  observation_type: security.sensitive_api
  data_category: device_information
  sink_type: null
```

### 5.3 约束

- Registry 必须覆盖规则目录中**每一个** `provider_rule_id`；缺失即测试失败（防止静默降级）。
- Provider 改规则名时只改 Registry，平台 Observation Schema 不变。
- Registry 自身有测试：每条规则的语义标注与规则文件中的 `desc.complianceCategory` 做一致性校验。

## 6. 规则类型

### 6.1 Normalization（Registry，代码）

```text
Provider Raw Result → Canonical Observation
```

### 6.2 Finding Rule（DB，UI 可维护）

```text
Observation → Finding
```

包含 `direct` 与 `composite` 两类。

### 6.3 Enrichment Rule（DB，UI 可维护）

```text
Finding + related Observation → richer Finding（不新增 Finding）
```

## 7. 关联 DSL

### 7.1 表达连接关系，不重复字面值

废除：

```json
{"conditions": [
  {"field": "category", "equals": "contacts"},
  {"field": "category", "equals": "contacts"}
]}
```

问题：`contacts` 写了两遍，每个数据类目仍需一条规则，维护量为 `O(类目数 × 流向 × 引擎)`。

改为：

```yaml
id: privacy_flow_permission_enrichment
version: 1

anchor:
  type: dataflow.privacy
where:
  sink_type: network

join:
  - type: fact.sensitive_permission
    on:
      - data_category

scope:
  - app_version_id

action:
  type: enrich
```

规则中**不出现任何具体类目名**。新增 contacts / location / camera / microphone / sms / account 等，全部由同一条规则覆盖，维护量为 `O(1)`。

### 7.2 Composite 示例

```yaml
id: sensitive_data_cleartext_network
version: 1

anchor:
  type: dataflow.privacy
where:
  sink_type: network

join:
  - type: security.network
    where:
      cleartext_allowed: true
    on:
      - app_version_id

action:
  type: create
finding:
  code: PRIVACY_CLEARTEXT_TRANSFER
```

### 7.3 保留的过滤能力

`where` 中的 `field / operator / literal` 仍然保留，但**只用于筛选**，不再冒充关联原语。

### 7.4 V1 关联原语

```text
1. observation type selector
2. shared-key join
3. all / any
4. create / enrich
```

不实现 timespan、event_count、value_count、temporal_ordered、跨主机、跨用户。Sigma 需要这些是因为它处理跨时间跨事件的检测场景；本平台一次扫描内所有观察属于同一 App、同一时刻，不需要。

## 8. 置信度模型

不使用固定增量：

```yaml
confidence_delta: 0.1      # 错误：为什么是 0.1？三条证据加 0.2？
```

改为基于**证据来源数量与独立性**的函数：

```text
仅单一数据流                        → medium
+ 同类目权限事实（同引擎）           → medium_high
+ 另一引擎独立印证                   → high
记录 source_engines 数量与 evidence_refs
```

依据：Quark-Engine 的权重模型是 `(2^(达到阶段数-1) × 规则分值) / 2^4`，即证据越完整置信度指数上升，而非累加固定值。

## 9. 既有 Finding 的迁移

库中已有真实 Finding：

```text
platform_findings #45   task 465   correlation_rule_version=1.1
platform_findings #53   task 536   同上
```

处理策略：

```text
保留历史 Finding 不动，新模型只对新任务生效
```

理由：历史行已有 `rule_snapshot`，记录了当时的规则内容。这正是「历史结论可复现」的正确语义。不做回填重算——重算会用新规则重新判定历史数据，反而破坏可复现性。

旧关联规则 `PRIVACY_CONTACTS_NETWORK` 按以下规则处理：

```text
若其条件在当前能力下不可能成立 → 停用（status=disabled），而非升级后继续留用
停用不删除历史 Finding
```

## 10. 数据链

```text
               Engine Raw Result
                       │
                       ↓
              Semantic Normalizer        ← Registry（代码 + 测试）
                       │
                       ↓
                  Observation              ← 带 data_category / sink_type / entity_keys
                       │
              ┌────────┴────────┐
              │                 │
       Direct Finding      Evidence Join    ← DB 规则（UI 可维护）
              │              (ENRICH)
              ↓                 │
        Platform Finding ◄──────┘
              │
              ├──────── Composite Rules ────→ Derived Finding
              │
              ↓
          Risk Report
```

## 11. 回归基线

改造前先把 task 553 的 139 条 observation 固化为 fixture：

```text
backend/tests/fixtures/normalization/task_553_observations.json
```

**必须在改造代码之前固化**，否则改造过程中无法回答「原来 12 条命中，现在还是 12 条吗」。

断言：

```text
139 observations 全部有 data_category（AppShark 隐私类）
AppShark ComplianceInfo 正确解析出 data_category
NetworkTransfer 正确解析出 sink_type=network
12 条命中规则即使没有 Androguard 对应观察，仍生成 Direct Finding
存在同 data_category 的 Androguard 观察时，只 enrich，不重复产生 Finding
不存在同 data_category 时，绝不跨类目误关联
修复前命中的 12 条规则在修复后仍全部命中（覆盖度不回归）
```

## 12. 实施顺序

```text
0. 固化 task 553 为回归 fixture（改造前）
1. Rule Semantic Registry（代码 + 测试，覆盖全部 20 条规则）
2. Observation Schema 扩展 + Normalizer 改造（回填 data_category / sink_type / entity_keys）
3. 用 fixture 验证第 2 步：category 不再为 0，语义解析正确
4. Direct Finding Pipeline（result_semantics=direct_finding → Finding）
5. 用 fixture 验证第 4 步：12 条命中即使无对应观察仍成 Finding
6. Evidence Join（只做 data_category 一个键，action=enrich）
7. 旧关联规则停用 + 历史 Finding 保留策略落地
8. 端到端真实任务验收（营口银行 + 营行企业银行）
```

## 13. 非目标

本期不做：

- SIEM 式时间窗、聚合阈值、跨主机/跨用户关联
- 五类 join key 全量实现（只做 `app_version` + `data_category`）
- Normalization 的 UI 编辑
- contacts/sms/calllog 的静态流规则（§1.3 已证明不可表达）
- 既有 Finding 的回填重算
- AI 参与风险判定

## 14. 验收

```text
task 553 fixture 全部断言通过
12 条命中规则在改造后仍全部命中
即使无跨引擎对应观察，Direct Finding 仍产出
有同类目权限观察时只 enrich，Finding 数量不增
跨类目不会误关联（contacts 与 device_information 不互相连接）
既有 Finding #45 / #53 的 rule_snapshot 保持不变
营口银行与营行企业银行真实任务端到端通过
```
