# 端到端验收记录

**日期**：2026-09-28 　**计划**：`docs/superpowers/plans/2026-09-28-finding-evidence-join.md` Task 9

样本口径（与 `rule-coverage.md` 一致）：`11` 门户测试 3.4.24、`12` 营口银行 4.5.1、
`13` 营行企业银行 1.4.2、`8` 测试 v3.3.8（360 加固）。A/B/C 三个样本均以
**AppShark + Androguard 双引擎**运行，便于横向比较与验证跨引擎增强。

---

## Step 1：全量测试 + 前端构建 —— 通过

```text
后端 202 passed
前端 vite build 成功
```

## Step 2：样本 A 营口银行 v4.5.1（12）—— 通过

```text
task 1082   命中规则 12 条   观察 169 条   带 data_category 124 条
结论 4 条，correlation_rule_id 均为空（全部来自 Direct Finding，不经关联器）
  PRIVACY_DEVICE_INFORMATION_FILE  medium_high   锚点 2  + 增强证据 25
  PRIVACY_DEVICE_INFORMATION_LOG   medium_high   锚点 13 + 增强证据 25
  SECURITY_PENDINGINTENTMUTABLE    medium
  SECURITY_UNZIPSLIP               medium
```

四条验收目标逐项成立：规则执行（12 条命中）、语义归一化（124 条带类目）、
Direct Finding（4 条，不依赖关联器）、Evidence Join（同引擎同类目证据把置信度
推到 `medium_high`，且**结论数没有增加**）。

## Step 3：样本 B 营行企业银行 v1.4.2（13）—— 通过（可复现）

同一配置连跑两次（task 1083 / 1086），逐项对比：

```text
             规则数  观察数  带类目  结论数   结论集合
第一遍 1083     5      63      21      2    PRIVACY_DEVICE_INFORMATION_LOG:medium_high,
                                            SECURITY_PENDINGINTENTMUTABLE:medium
第二遍 1086     5      63      21      2    同上，逐字符一致
```

可复现不是断言出来的，是两次独立运行的结论集合比对出来的。

## Step 4：样本 C 门户测试 v3.4.24（11）—— 通过（负向对照）

该样本**有** Androguard 的通讯录权限观察（CONTACTS ×3），正是旧规则
`PRIVACY_CONTACTS_NETWORK` 此前误报的那类输入（G3，task 810 曾在此样本上产出
「通讯录信息存在潜在网络传输路径」）。该规则已停用后：

```text
task 1084   命中规则 18 条   观察 1411 条   结论 8 条
contacts 相关结论数：0        ← 负向对照通过
跨引擎增强：PRIVACY_LOCATION_NETWORK  high（Androguard location 权限 + AppShark location 数据流）
```

## Step 5：样本 D 360 加固（8）—— **不通过**

计划要求：本样本**只用于验证引擎失败诊断，不得作为安全检测的负向证据**。
按此检查后发现，平台对「分析退化」没有任何诊断，直接把它当成了「扫完没发现问题」。

task 1085（AppShark + Androguard）实测：

```text
appshark    status=completed   event_count=17   error_code=(空)   retryable=false
            scan_stats.availableClasses=337   availableMethods=30
androguard  status=completed   event_count=230
任务        status=completed   failed_reason=(空)   结论 0 条   观察 247 条
```

与健康样本对比（同一轮验收）：

```text
app_version 12   AppShark availableClasses=5911
app_version 11   AppShark availableClasses=23366   availableMethods=132301
app_version 8    AppShark availableClasses=337     availableMethods=30
```

**337 个类 / 30 个方法是加固壳的规模，不是这个 App 的规模**——该样本
`classes.dex` 头部记录的类定义数只有 **4**。也就是说 AppShark 分析的是壳，不是应用。

平台对此的呈现是：任务 `completed`、无错误码、无失败原因、0 条结论。用户看到的是
「扫描完成，未发现风险」，而真相是「这个 App 根本没被分析到」。

**这违反实施计划的 Global Constraint**：

> 不得把分析失败解释成「未发现风险」（`ANALYSIS_FAILED` ≠ `NOT_DETECTED`）

同一现象在历史数据里更极端：多条 app_version 8 的 appshark 执行是
`event_count=0`、`result_summary={"vulnerability_count": 0}`、**连 scan_stats 都没有**
（即引擎根本没跑到调用图阶段），状态同样是 `completed`、无错误码。

### 附带发现并已修复：`class_count` 读错了 DEX 头部字段

排查过程中发现 `androguard_runner._dex_class_count` 读的是 DEX 头部的
**`class_defs_off`（0x64，类定义区的字节偏移）**，而不是
**`class_defs_size`（0x60，类定义数量）**。二者相邻、同为 4 字节小端，读错不报错，
只是给出一个「看起来像数字的」字节偏移：

```text
app_version 8 的 classes.dex：真实类数 4，被读成 9784（9784 正是类定义区偏移）
```

该值以「类数量」为列名直接显示在任务详情与报告中（`TaskDetail.vue`、`TaskReport.vue`），
因此界面上的类数量一直是错的。

已修复（`DEX_CLASS_DEFS_SIZE_OFF = 0x60`）。**测试此前抓不到它，因为假 DEX 也把类数写在
偏移 100**——测试照着实现写，与实现互相印证，全绿而线上数值是错的。新测试给
`class_defs_size` 与 `class_defs_off` 填入不同值，并补了一条用规范字段互相印证的用例。

历史执行记录中的旧值**不回填**：那些是当时的真实产物，与既有结论的 reproducibility
原则一致（同设计 §10 对历史 Finding 的处理）。

### 未做（需要先定策略）

「分析退化」的判定与呈现涉及语义层改动，不在本次验收内擅自动手。可选的判定信号：

- `scan_stats.availableClasses` 远低于该 APK 的实际类数（同任务内 Androguard 的
  `class_count` 可作为对照——但注意它的历史值是错的，修复后的新任务才可用）
- `event_count == 0` 且 `result_summary` 中缺失 `scan_stats`
- 引擎自身的 `vulnerability_count` 为 0 而可用类数处于壳规模

处置方式（新增 `ANALYSIS_INCOMPLETE` 之类的执行状态、或在任务层标记「检测未生效」）
需先定，因为直接关系到报告页怎么向用户表达「这次扫描不算数」。
