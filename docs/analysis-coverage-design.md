# 分析有效性（Analysis Coverage）设计提案

**状态：待评审，未实现**　**日期**：2026-09-28　**来源**：Task 9 端到端验收（样本 D 不通过）

---

## 1. 问题

平台目前把「引擎跑完了」直接等同于「这个 App 分析过了」。二者不是一回事。

实测（app_version 8，360 加固样本，task 1085）：

```text
appshark    status=completed   event_count=17   error_code=(空)
            scan_stats.availableClasses=337    availableMethods=30
任务        status=completed   failed_reason=(空)   结论 0 条
```

用户看到的是「扫描完成，未发现风险」。真相是这个 App 根本没被分析到——该 APK 的
`classes.dex` 头部只声明 **4 个类**，而它的 manifest 声明了 **225 个组件**。
AppShark 分析的是加固壳。

**这违反实施计划的 Global Constraint**：

> 不得把分析失败解释成「未发现风险」（`ANALYSIS_FAILED` ≠ `NOT_DETECTED`）

历史数据里还有更极端的形态：多条 app_version 8 的 appshark 执行是
`event_count=0`、`result_summary={"vulnerability_count": 0}`、**连 `scan_stats` 都没有**
（引擎根本没跑到调用图阶段），状态同样是 `completed`、无错误码。

## 2. 判据：用结构性矛盾，不用阈值

阈值（「可用方法数少于 N 就判退化」）在这个仓库是明确不受欢迎的：N 是几都说不清。
下面的主判据不需要 N。

### 2.1 主判据（输入侧）：DEX 声明的类数 < manifest 声明的组件数

正常应用里，manifest 里声明的每一个 Activity / Service / Provider / Receiver 都要有实现类。
**组件数多于 DEX 里声明的类数，是结构性不可能**——说明 DEX 里没有这个应用的代码。

实测四个样本（类数取自 DEX 头部 `class_defs_size`，组件数取自 manifest）：

```text
样本                DEX 声明类数   manifest 组件数   判定
8   (360加固)             4            225          矛盾 → DEGRADED
11  (门户测试)       37,419            153          正常
12  (营口银行)        8,009             23          正常
13  (营行企业银行)     5,840             25          正常
```

判据只用两个平台已经掌握的数字，不依赖引擎自报，也不依赖「正常应用长什么样」。

### 2.2 辅判据（引擎侧）：引擎自报可用量与其应有规模的关系

用于覆盖「DEX 看起来正常，但引擎实际没分析到」的情形：

- `availableMethods == 0` 或 `scan_stats` 缺失 → 引擎没跑到调用图阶段
- `availableMethods` 相对 APK 声明方法数的比例（样本 8：30 / 381 = 8%）——**这一条是阈值，
  必须先在真实样本上定标再启用**，不得先写一个数进来

辅判据的原始值（`availableClasses` / `availableMethods` 等）应原样入库，供复核。

## 3. 状态模型：不与执行状态混用

`engine_executions.status` 回答的是「引擎是否跑完」（它确实跑完了），
覆盖度回答的是「结果能否代表这个 App」。**两件事都为真，合并成一个字段就会丢掉信息**，
且现有 UI 与逻辑都按 status 取值分支。

因此新增独立字段：

```text
engine_executions.analysis_coverage   FULL | DEGRADED | UNKNOWN      -- 判定结果
engine_executions.coverage_detail     JSONB                          -- 原始数字与命中的判据
```

- `FULL`：通过主判据且引擎自报正常
- `DEGRADED`：命中主判据或辅判据 → **本次分析结果不可用于判断风险**
- `UNKNOWN`：缺少判定所需数据（如老数据没有 scan_stats）→ 不得当成 FULL

**默认值必须是 `UNKNOWN` 而不是 `FULL`**：缺数据时把结果当成有效，正是当前故障的成因。

## 4. 呈现规则

三处措辞必须改，否则状态字段只是库里的一个标记：

| 位置 | 现在 | 改为 |
|---|---|---|
| 任务/执行详情 | `completed` + 0 结论 | `completed` + 「**分析未覆盖应用代码**」+ 依据数字（DEX 声明 4 类 / manifest 225 组件） |
| 检测报告 | 「未发现风险」 | DEGRADED 时：「**本次分析未生效，不能据此判断是否存在风险**」 |
| 结论列表 | （不变） | 结论照常显示（若真有），但页面顶部给出上述提示 |

关键约束：**DEGRADED 不得用于任何负向结论**。「这个 App 没有某风险」这类判断，
在 DEGRADED 下与「没分析」无法区分——样本 D 尤其如此（Task 9 Step 5 已明确它
只能用于引擎失败诊断，不得作为安全检测的负向证据）。

## 5. 需要的数据支持

- Androguard runner 需输出 **APK 声明的类数与方法数**（DEX 头部 `class_defs_size` 0x60、
  `method_ids_size` 0x58，按 dex 文件求和）
- `class_count` 此前读错了字段（0x64 而非 0x60，读到的是字节偏移），已修复；
  方法数尚未采集，需一并加上
- manifest 组件数已由 Androguard 采集（activity/service/provider/receiver 四项）

## 6. 不做

- **不回填历史执行记录**。既有结论保留原样，与设计 §10 对历史数据的处理一致；
  需要判断某个历史任务是否 DEGRADED 时，按当时的 APK 重新计算输入侧判据即可
- **不因 DEGRADED 自动重跑或自动判为风险**。加固样本要能分析需要脱壳，
  那不是本平台的职责；平台的责任是**说清楚这次分析不算数**
- 不把 DEGRADED 引入 Finding 生成逻辑（结论该不该出仍由论断类型与证据决定）

## 7. 验证计划

1. 四个样本各跑一次完整任务，断言：app 8 → `DEGRADED`；app 11/12/13 → `FULL`
2. 用一批历史执行（含 `event_count=0` 且无 `scan_stats` 的）验证 `UNKNOWN` 分支
3. 报告页与任务详情页人工核对措辞（**需要起前端**，本环境无法自动化）
4. 辅判据的阈值在 1、2 步产出的真实分布上定标后再启用；定标前辅判据只记录不判定

## 8. 待定问题（需产品/设计决定）

1. DEGRADED 是否影响任务最终状态？当前提案是不改 `status`，只在任务与报告上显式提示；
   另一种做法是新增任务级状态（如 `completed_degraded`），代价是所有按 status 分支的
   地方都要改
2. 「分析未覆盖应用代码」的措辞与位置由谁定？报告是对外交付物，文案需要评审
3. 是否需要「按输入侧判据判定 → 自动提示重新上传未加固样本」的引导？
