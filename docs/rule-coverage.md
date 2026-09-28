# 规则覆盖度

状态只取四个取值（设计文档 §1.6）：`已验证` / `待验证` / `静态不可表达` / `未覆盖`。
**不得**出现「理论支持」「预计覆盖」这类冒充已覆盖的写法。

MASWE 编号一律标 `待核实`（本环境无法访问官方站点），详见设计文档 §9。

> 完整的「数据/安全类别 · 流向 · 规则 · Observation · Finding · MASWE · MASTG」矩阵
> 见实施计划 Task 8，尚未产出。本文件先记录**已经在真实样本上暴露的能力缺口**，
> 因为这些缺口决定了当前哪些规则/关联是空转的。

## 已知缺口

### G1：非 AppShark 观察不带 `data_category`，跨引擎 join 无法成立

**状态：未覆盖**（需求已确认，实现待做）

`Rule Semantic Registry`（`backend/app/services/appshark_semantic_registry.py`）按
`payload.rule` 查表，而只有 AppShark 的事件带 `payload.rule`。Androguard / MobSF 的
观察归一化后 `data_category` 恒为 NULL。

后果：

- 设计文档 §8 置信度阶梯的最高一档「＋另一引擎独立印证 → high」**当前不可达**；
  实测能到的是 `medium_high`（AppShark 数据流 + AppShark 同类目 API 事实）
- 设计文档 §7.1 的示例规则以 `fact.sensitive_permission`（Androguard 敏感权限）为
  证据侧，该 join 在现有数据上永不命中
- 因此内置增强规则 `PRIVACY_FLOW_FACT_ENRICHMENT` **只声明今天真的会生效的 join**，
  不写进那条空转的 join（写进去等于让规则看起来覆盖了跨引擎印证）

补法：给 Androguard 的 `SENSITIVE_PERMISSIONS`（`app/engine/runners/androguard_runner.py`
的 LOCATION / PHONE_STATE / CONTACTS / CAMERA / MICROPHONE / STORAGE / SMS）建立到
`data_category` 的映射。映射本身是代码，**必须先按 Task 1 的方式在真实样本上验证**
每个类目都能正确区分，再进生产——理由与设计文档 §5.1 相同：这类映射改错会让 join
静默失效（键对不上不报错），不能靠推断写。
