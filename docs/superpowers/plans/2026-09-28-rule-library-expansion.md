# 规则库扩充与关联规则修正 Implementation Plan（修订版 v2）

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans. Steps use checkbox (`- [ ]`) syntax.

**Goal:** 先验证能力边界，再据此补规则；把关联规则从「跨类目拼证据」改为「同类目证据关联」；并入 AppShark 官方安全规则；用 MASWE 编号完成覆盖度盘点。

**Architecture:** 规则库分三层——L2 事实规则（APIMode，证明某 API 被调用）、L3 数据流规则（source→sink，证明数据流向）、关联规则（把同类目证据合成为平台结论）。本计划与 v1 的关键差别：**先做可行性验证，再决定写什么规则**，不再假设「缺规则 → 补规则」这条路径成立。

**Tech Stack:** AppShark JSON5 规则、Python 规则种子、PostgreSQL、pytest、Vue 3。

**Spec:** `docs/superpowers/specs/2026-09-24-correlation-rules-design.md`

## Global Constraints

- **规则必须取自真实引擎产物并经真实任务验证。** 未经真实 APK 验证的规则不得提交。
- **禁止交付惰性规则**：一条永远不可能命中的规则比没有规则更糟，因为它会让覆盖度看起来是够的。
- 关联规则的条件必须来自**同一数据类目**；禁止跨类目拼接证据。
- source 语义必须匹配 AppShark 定义：`Return` = 返回隐私数据的 API；`Field` = **本身就是数据的静态字段**（如 `Build.SERIAL`）。URI 常量不是数据，不得用作 `Field` source。
- 规则必须通过 `validate_rule_content` 的取值域与长度边界。
- 数据库为含真实数据的开发库：种子与迁移幂等，不得删除非本任务创建的行。
- 每批规则加入后必须用真实任务验证，命中与否都要如实记录。

---

## v1 计划被推翻的前提（保留作为依据）

v1 假设「contacts/sms/calllog 缺规则 → 补上 source 类目即可」。验证后被推翻：

```text
1. contacts/sms/calllog 读取都走 ContentResolver.query(具体URI) 这一个通用方法
2. AppShark 的 source 只能指定方法签名，没有「按参数取值过滤」能力（TaintParamType 仅用于 sink）
3. 若把 ContentResolver.query 的 Return 作为 source，会把日历/媒体/通话记录全部算作联系人
   —— 这正是要修的跨类目错误
4. Field source 的官方语义是「该字段本身就是数据」；URI 常量是查询条件，不满足该语义
```

因此本版把「补规则」改为「先验证可行性，再按结论补规则或标记为不可静态表达」。

## 验证样本

```text
营口银行         v4.5.1  67MB  app_version_id=12  未加固，引用 ContactsContract + CommonDataKinds$Phone
营行企业银行      v1.4.2  24MB  app_version_id=13  未加固，同上
门户测试         3.4.24  118MB app_version_id=11  可分析，不读通讯录（对照组）
测试              v3.3.8  42MB  app_version_id=8   360加固，AppShark 分析不动（负面对照）
```

---

### Task 1: 验证 contacts 的 L2 与 L3 可行性（前置，决定后续形态）

**Files:**
- Create: `backend/appshark/rules/api_contacts.json`（L2 试验）
- Create: `backend/appshark/rules/contacts_to_network.json`（L3 试验）
- 验证后按结论保留或删除

**Interfaces:**
- L2 试验：`APIMode: true`，sink 用 `ContactsContract$Contacts.CONTENT_URI` 等常量
- L3 试验：`Field` source 用同一批 URI 常量，sink 用网络栈

- [ ] **Step 1: 写入两个试验规则**

- [ ] **Step 2: 对营口银行（v12）跑 AppShark**，只启用 appshark 引擎

Run: 提交任务 → `engine_executions` 确认 status=completed 且 duration 明显大于纯 API 扫描

- [ ] **Step 3: 判定**

```text
L2 命中 + L3 命中   → URI 常量建模可行，Task 2 按此模式补齐三个类目
L2 命中 + L3 不命中 → 确认能力边界：读取可检出、流向不可检出。
                      保留 L2，放弃 L3，并在覆盖度矩阵中标记「静态不可表达」
L2 不命中           → APIMode 不识别静态字段常量，两个试验都失败；
                      改为只用方法签名（如 ContentResolver.query）并接受其跨类目宽度
```

- [ ] **Step 4: 对营行企业银行（v13）复现同一结论**，避免单样本偶然

- [ ] **Step 5: 按判定处理规则文件并 commit**

```bash
git commit -m "test(rules): determine contacts detection feasibility"
```

---

### Task 2: 按 Task 1 结论补规则

**Files:** 依 Task 1 判定结果决定

- [ ] **Step 1:** 若 L2 可行 → 补 sms/calllog 的 L2 规则（样本无引用，规则保留但不声称已验证，需在 commit message 中写明「规则已就位，样本未覆盖，未验证」）
- [ ] **Step 2:** 若 L3 可行 → 补 sms/calllog 的 L3；可行则优先做，因为流向比调用有价值
- [ ] **Step 3:** 样本验证
- [ ] **Step 4:** Commit

---

### Task 3: 关联规则改为同类目关联（独立于 Task 1）

**Files:**
- Modify: `backend/app/services/rule_seed.py`
- Modify: `backend/tests/test_correlation.py`, `test_finding_service.py`, `test_finding_auto_trigger.py`
- Modify: `backend/tests/fixtures/correlation/`

**Interfaces:**
- 条件必须同类目。旧规则 `_NetworkTransfer` 会匹配任意类目的外传流，必须收紧。

- [ ] **Step 1: 升版本到 1.2**，条件改为 `category == CONTACTS` + `rule contains <类目专属规则名>`
- [ ] **Step 2:** 若 Task 1 判定 contacts L3 不可表达，则本关联规则同样不可成立 → 改为**停用**并在描述中说明原因，而不是留一条永远不命中的规则
- [ ] **Step 3: 更新 fixture 与测试**
- [ ] **Step 4:** 全量测试 + 真实任务验证
- [ ] **Step 5: Commit**

---

### Task 4: 并入 AppShark 官方安全规则（独立，已下载）

**Files:**
- Create: `backend/appshark/rules/` 下 7 个文件（源：`/tmp/appshark_official/`）

```text
ContentProviderPathTraversal   IntentRedirectionBabyVersion   PendingIntentMutable
broadcastIMEI                  logSerial                      mac
unZipSlip
```

- [ ] **Step 1:** 复制并统一 `complianceCategory` 前缀约定
- [ ] **Step 2:** JSON 合法性校验
- [ ] **Step 3:** 对营口银行与营行企业银行跑真实任务，记录哪些官方规则命中
- [ ] **Step 4:** Commit（commit message 注明来源与上游版本）

---

### Task 5: MASWE 编号对齐与覆盖度矩阵

**Files:**
- Modify: `backend/app/services/rule_seed.py`
- Create: `docs/rule-coverage.md`

- [ ] **Step 1:** 为每条关联规则填真实 MASWE 编号
- [ ] **Step 2:** 生成「数据类目 × 流向」矩阵，每格标注：已覆盖 / 静态不可表达 / 待验证
- [ ] **Step 3:** Commit

---

### Task 6: 端到端验收

- [ ] **Step 1:** 全量测试 + 前端构建
- [ ] **Step 2:** 对营口银行跑三引擎完整任务，记录引擎耗时、观察数、命中规则、平台结论
- [ ] **Step 3:** 确认关联规则结论的证据来自同类目
- [ ] **Step 4:** Commit

## Self-review coverage

- 能力边界验证：Task 1（前置）
- 规则补充：Task 2
- 关联规则同类目修正：Task 3
- 官方安全规则并入：Task 4
- 标准映射与覆盖度：Task 5
- 端到端：Task 6
