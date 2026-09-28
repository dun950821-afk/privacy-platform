# Finding 生成与证据关联 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans. Steps use checkbox (`- [ ]`) syntax.

**Goal:** 按设计文档 `2026-09-28-finding-evidence-join-design.md` 重建 Finding 生成与证据关联：先逐层验证引擎能力边界，再把 Provider 语义保留为平台一等字段，最后让具备完整语义的证据直接成结论、跨引擎仅做证据增强。

**Architecture:** 三条生成路径——Direct Finding（引擎结果本身即结论）、Evidence Join（共享语义键增强已有 Finding，不新增）、Composite Rule（合并后产生新语义才新增 Finding）。Provider 语义经 Rule Semantic Registry 归一化为 `data_category` / `sink_type` / `entity_keys`，关联器 JOIN ON `entity_keys` 而非匹配字面值。

**Tech Stack:** AppShark JSON5 规则、Python、PostgreSQL、pytest、Vue 3。

**Spec:** `docs/superpowers/specs/2026-09-28-finding-evidence-join-design.md`

> **本计划取代** `2026-09-28-rule-library-expansion.md`（v1 与 v2），后者的 Task 3 仍是字段过滤、Task 2 与 Global Constraint 自相矛盾，已作废。

## Global Constraints

- 不得先大批量新增规则；必须先完成 Task 1 能力实验。
- 能力实验失败时**不得自行扩大规则 Source 范围**来「救」规则。
- **未验证规则不得进入生产规则目录**（`backend/appshark/rules/`）。状态记入 `docs/rule-coverage.md`。
- 不得把 URI Field 当作隐私数据 Source。
- 不得使用 rule-name substring 作为正式 Join Key。
- 不得为了让测试通过而修改真实任务结果。
- 不得删除开发库中的既有真实数据。
- **不得把分析失败解释成「未发现风险」**（`ANALYSIS_FAILED` ≠ `NOT_DETECTED`）。
- 若实验结果与设计文档预期不符，**以真实 AppShark 结果为准**，先更新设计结论再继续实现。
- 规则必须通过 `validate_rule_content`。
- 状态只能取 `VERIFIED / FAILED / NOT_EXPRESSIBLE / NOT_VERIFIED`，禁用「理论支持」「预计覆盖」。

---

### Task 1: Contacts 能力边界实验（前置）

**Files:**
- Create: `docs/appshark-rule-capability.md`（产出：能力矩阵结论）
- 试验规则置于临时目录，结论产出后按结果保留或删除

**六项实验，逐项独立判定：**

- [ ] **Step 1: 实验 A — API Fact**

`APIMode: true`，**sink 用方法签名** `ContentResolver.query`（不得用 URI 常量，AppShark 的 APIMode sink 列表只匹配方法签名）。
判定：能否识别「调用了查询 API」。
预期观测名：`fact.content_resolver_query`。

- [ ] **Step 2: 实验 B — URI Fact**

`Field` source 用 `ContactsContract$Contacts.CONTENT_URI` 等常量，配一个必然可达的 sink（如日志）以证明 Field source 本身可被识别。
判定：能否识别「使用了 Contacts URI 常量」。
若命中，观测名只能是 `fact.contacts_provider_access`，**不得命名为 contacts 数据读取**。

- [ ] **Step 3: 实验 C — URI → query**

验证 `Contacts.CONTENT_URI → ContentResolver.query(uri,...)` 能否建立传播关系。
判定：能否证明该 URI 是 query 的参数。

- [ ] **Step 4: 实验 D — Contacts Data → Network**

source 语义必须本身代表联系人数据。禁止用 `CONTENT_URI` 冒充。
判定：能否形成精确的 Contacts Source → Sink。
若无法在不误报 Calendar/CallLog/Media 的前提下表达 → `NOT_EXPRESSIBLE`。

- [ ] **Step 5: 实验 E — 跨类目隔离（必须项）**

至少验证 Contacts / Calendar / CallLog / Media 四类：
```text
Contacts → Network    命中 / 未命中（如实记录）
Calendar → Network    不得被归类为 Contacts
CallLog  → Network    不得被归类为 Contacts
Media    → Network    不得被归类为 Contacts
```
不通过即 `FAILED`，且不得进入生产。

- [ ] **Step 6: 汇总能力矩阵并 commit**

写入 `docs/appshark-rule-capability.md`，六项各标 `VERIFIED / FAILED / NOT_EXPRESSIBLE / NOT_VERIFIED`。

```bash
git commit -m "test(appshark): establish contacts detection capability boundary"
```

---

### Task 2: Provider 语义保留（Observation Normalization）

**Files:**
- Create: `backend/app/services/appshark_semantic_registry.py`
- Create: `backend/app/appshark/rules/registry.json`
- Modify: `backend/app/services/observation_service.py`
- Modify: `backend/app/models/__init__.py`（`EngineObservation` 增加字段）
- Create: `backend/alembic/versions/<ts>_observation_semantics.py`
- Test: `backend/tests/test_appshark_semantic_mapping.py`

**Interfaces:**
- Registry 必须覆盖规则目录中**每一个** `provider_rule_id`；缺失即测试失败。
- 归一化输出：`data_category` / `sink_type` / `result_semantics` / `observation_kind` / `provider_rule_id` / `provider_level`。
- 保留原始值：`compliance_category_raw`。

- [ ] **Step 1:** 建立 Registry，覆盖全部 21 条规则（含 7 条官方安全规则）
- [ ] **Step 2:** 扩展 `EngineObservation` 字段并写幂等迁移
- [ ] **Step 3:** 改造 Normalizer，回填语义字段
- [ ] **Step 4:** 测试：`DeviceId_NetworkTransfer → device_information/network`、`Location_NetworkTransfer → location/network`；且 `contacts != location != calllog`
- [ ] **Step 5:** Commit `feat(observation): preserve appshark compliance semantics`

---

### Task 3: Direct Finding Pipeline

**Files:**
- Modify: `backend/app/services/finding_service.py`
- Test: `backend/tests/test_direct_finding.py`

- [ ] **Step 1:** `result_semantics == direct_finding` 的 Observation 直接产出 Finding，**不经过关联器**
- [ ] **Step 2:** 测试：仅有 AppShark 数据流、无任何 Androguard 观察时，仍产出 Finding
- [ ] **Step 3:** 测试：`unZipSlip`（无 data_category）也能产出 Finding
- [ ] **Step 4:** Commit `feat(finding): allow direct appshark findings`

---

### Task 4: Evidence Join（共享语义键）

**Files:**
- Modify: `backend/app/services/rule_evaluator.py`（新增 join 语义）
- Modify: `backend/app/services/correlation.py`
- Test: `backend/tests/test_evidence_join.py`

- [ ] **Step 1:** 规则 DSL 支持 `anchor` / `join.on` / `scope` / `action`
- [ ] **Step 2:** 实现 `enrich`：找到同 `app_version_id + data_category` 的观察，补充证据，**不新增 Finding**
- [ ] **Step 3:** 测试：同类目可 join；**跨类目禁止 join**（contacts 不得连到 device_information）
- [ ] **Step 4:** Commit `feat(correlation): replace literal matching with semantic-key evidence join`

---

### Task 5: 旧关联规则停用与历史保留

- [ ] **Step 1:** 停用 `PRIVACY_CONTACTS_NETWORK`（其条件不可能成立），`status=disabled`
- [ ] **Step 2:** 历史 Finding #45 / #53 保留不动，不回填重算
- [ ] **Step 3:** Commit

---

### Task 6: 回归基线

**Files:** Create `backend/tests/fixtures/appshark/task_553/`

- [ ] **Step 1:** 固化 task 553 的 139 条 observation、`apk_sha256`、`engine_version`、`rule_version`、`raw_result_hash`
- [ ] **Step 2:** 断言：`data_category` 不得全为 null；12 条命中规则语义正确解析；Direct Finding 不依赖关联；同类目可 join；跨类目禁止 join；**修复前命中的 12 条规则修复后仍全部命中**
- [ ] **Step 3:** Commit `test(correlation): add same-category join regression coverage`

---

### Task 7: 官方安全规则并入与来源固化

- [ ] **Step 1:** 已并入 7 条（`e203e21`），来源已固化（`7abab7b`，commit `487fa2175c4a`）
- [ ] **Step 2:** 按 Task 1 结论在真实样本上逐条验证，`verified` 置 true 的才计入覆盖度
- [ ] **Step 3:** Commit `feat(appshark): vendor upstream security rules`

---

### Task 8: MASWE 覆盖矩阵

**Files:** Create `docs/rule-coverage.md`

- [ ] **Step 1:** 矩阵列：数据/安全类别 · 流向/风险 · AppShark Rule · Observation · Finding · MASWE · MASTG · 状态
- [ ] **Step 2:** 状态只取 `已验证 / 待验证 / 静态不可表达 / 未覆盖`
- [ ] **Step 3:** MASWE 编号一律标 `待核实`（本环境无法访问官方站点核实），版本固定 `1.0.0`
- [ ] **Step 4:** Commit `docs(rules): add MASWE 1.0.0 coverage matrix`

---

### Task 9: 端到端验收

- [ ] **Step 1:** 全量测试 + 前端构建
- [ ] **Step 2:** 样本 A 营口银行 v4.5.1（app_version_id=12）— 验证规则执行、语义归一化、Direct Finding、Evidence Join
- [ ] **Step 3:** 样本 B 营行企业银行 v1.4.2（13）— 验证可复现
- [ ] **Step 4:** 样本 C 门户测试 v3.4.24（11）— 负向对照，contacts finding 必须为 0
- [ ] **Step 5:** 样本 D 360 加固（8）— **只验证引擎失败诊断，不得作为安全检测的负向证据**
- [ ] **Step 6:** Commit `test(e2e): validate three-engine rule pipeline`

## 验收

```text
[ ] 所有生产规则真实验证，无未验证规则进入 production，无惰性规则
[ ] 官方规则来源可追溯（commit 已固化）
[ ] complianceCategory 不再丢失；data_category / sink_type 标准化
[ ] Direct Finding 不依赖关联器
[ ] Enrichment 不产生重复 Finding
[ ] Join 使用共享语义键，禁止 rule-name substring，禁止跨类目
[ ] MASWE v1.0.0，编号未核实者标 unmapped
[ ] task 553 回归通过；跨类目隔离通过
[ ] ANALYSIS_FAILED 与 NOT_DETECTED 严格区分
```

## Self-review coverage

- 能力边界：Task 1（前置）→ 决定 Task 7 的 verified 取值
- 语义保留：Task 2 → 是 Task 3/4 的前提
- 三条生成路径：Task 3（direct）、Task 4（enrich）、Composite 留待有真实用例
- 回归：Task 6 → 覆盖 Task 1..4 的全部改动
- 标准映射：Task 8
