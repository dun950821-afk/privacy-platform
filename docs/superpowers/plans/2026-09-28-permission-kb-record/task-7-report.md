# Task 7 报告：抓取脚本、原始文件入仓、实跑导入

日期：2026-09-28　分支：main

## 1. 抓取（`scripts/fetch_permission_sources.py`）

**10/10 全部成功，失败 0 条。** 联网只发生在这一步；`raw.githubusercontent.com` 上
`openharmony/docs` 一如既往拉不动，8 个鸿蒙文件全走 GitHub API 的
`Accept: application/vnd.github.raw`。

| 平台 | 文件 | 字节 | sha256 前 12 |
|---|---|---|---|
| android | AndroidManifest.xml | 503122 | `336cc3ed0c01` |
| harmonyos | permissions-for-all.md | 17848 | `f9e4318d99a1` |
| harmonyos | permissions-for-all-user.md | 7374 | `833a6bb08ef2` |
| harmonyos | permissions-for-system-apps.md | 128448 | `08061d8fc2f8` |
| harmonyos | permissions-for-system-apps-no-acl.md | 4734 | `adb5096af7ab` |
| harmonyos | permissions-for-system-apps-user.md | 6301 | `6b84556feb42` |
| harmonyos | permissions-for-enterprise-apps.md | 15981 | `080325d2867c` |
| harmonyos | permissions-for-mdm-apps.md | 17811 | `f288b4852a65` |
| harmonyos | restricted-permissions.md | 31139 | `6a7f8c055230` |
| ios | protected-resources.json | 123341 | `084ae066b432` |

`data/kb/SOURCES.json` 共 10 条，**带 `error` 字段的 0 条**（脚本对失败条目本来就会
写 `error` + `fetched_at: null`，这次没触发）。

## 2. 解析与导入结果

`/tmp/venv/bin/python scripts/import_permissions.py`

```
ANDROID    解析  1016 条  ->  {'inserted': 933, 'updated': 83, 'skipped': 0}
HARMONYOS  解析   742 条  ->  {'inserted': 742, 'updated': 0, 'skipped': 0}
IOS        解析    57 条  ->  {'inserted': 57, 'updated': 0, 'skipped': 0}
```

第二次跑（Step 6 幂等验证）：三平台 `inserted` 全为 0，
`{'inserted': 0, 'updated': 0, 'skipped': 1016 / 742 / 57}`。

落库（Step 5）：

```
 platform  | count | 有说明 |  pct
-----------+-------+--------+-------
 ANDROID   |  1036 |    103 |   9.9
 HARMONYOS |   742 |    742 | 100.0
 IOS       |    57 |     56 |  98.2
```

`ANDROID 1036 = 933 新 + 原有 103`。**Android 有说明占比 9.9% 是预期结果不是缺陷**——
AOSP 清单的 `permdesc_*` 定义在各模块自己的资源里，core 里解不出来，解析器按设计不编造描述。
iOS 那 1 条无说明是它的 `abstract` 为空。

与 brief 预期的偏差（都属上游漂移，非缺陷）：Android 1016 条 vs 预期「约 1018」
（AOSP master 一直在动）；重叠行 83 vs brief 的「81」。

## 3. 五条硬要求逐条验证

### 要求 1：断言解析条数非零 —— 落实并验证守卫真会响

`scripts/import_permissions.py` 在每平台解析后加了硬断言：`rows` 为空即
`raise SystemExit`，绝不把空结果当「干净导入」写库。实测：

```
OK SystemExit: ANDROID 解析出 0 条——文档形态可能变了，先查解析器再导入，别让空结果落库
```

额外加了一条**单文件守卫**（brief 之外，见§6 改动说明）：鸿蒙那支跨 8 个文件，
一个文件塌成 0 条不会拖垮「每平台 > 0」的总断言，会被其余 7 个文件的几百条掩盖，
所以单文件 0 条单独喊一声。实测：`警告 permissions-for-all.md 解析出 0 条`。

### 要求 2：81 行人工说明必须还在 —— 通过，附查询输出

```
             permission_name            |   capability   | grant_mode | permission_type
----------------------------------------+----------------+------------+-----------------
 android.permission.ACCESS_FINE_LOCATION | 获取精确位置   | 运行时授权 | 危险权限
 android.permission.CAMERA               | 使用相机       | 运行时授权 | 危险权限
 android.permission.RECORD_AUDIO         | 使用麦克风录音 | 运行时授权 | 危险权限
```

更强的一步：把导入前 103 行按 `permission_name|capability|grant_mode|category|permission_type`
导出快照，导入后按精确名（`awk` 全字段匹配，不是 `grep -F` 的子串匹配——同名前缀会误配，
例如 `...BLUETOOTH` 会命中 `...BLUETOOTH_ADMIN`）逐字段 diff：

- **capability / grant_mode / category：103 行零变化**，逐字节相同。Ruling F 的
  「解析结果为 `None` 的字段不覆盖既有值」确实生效（首跑 baseline 为 NULL，全靠这层过滤挡着）。
- **permission_type：30 行被覆盖** —— 见§4，这是本次实跑挖出的真问题。

### 要求 3：鸿蒙跨文件去重由 `_load` 负责 —— 保留

`_load` 的 HARMONYOS 分支按 `permission_name` 跨文件去重，未省。原始 8 文件合计 742 条，
同一权限确实出现在多个文件里（`permissions-for-all.md` 与 `permissions-for-all-user.md` 等
存在交叉），去重后仍是 742，说明这批文件当前**没有**重叠命中，但去重逻辑保留以抵御后续改版。

### 要求 4：iOS `official_reference` 抽验 —— 三个全 200

代码产出的人类可读形式，实测 HTTP 码：

| URL | 码 |
|---|---|
| `.../information-property-list/nfcreaderusagedescription` | **200** |
| `.../information-property-list/nsaccessorytrackingusagedescription` | **200** |
| `.../information-property-list/nsappbundlesusagedescription` | **200** |

对照组（先前实测 200 的 JSON API 形式）同样 200：
`.../information-property-list/nscamerausagedescription.json`、`nfcreaderusagedescription.json`。
**两种形式都可访问**，人类可读形式这条不必改。

### 要求 5：鸿蒙文档里是否出现 `###` 子小节 —— 不存在

对 8 个文件逐个统计：`^### ` 计数**全部为 0**。当前 `openharmony/docs` 的 AccessToken
文档只用 `##`（每个权限一个 `## ohos.permission.X`），Ruling H 那类「级别被 `###` 子小节
借用」的形态在真实文档里**未出现**。

另外确认了一处相关形态：`permissions-for-all.md` 有 58 个 `##` 标题、其中 57 个是权限标题，
多出来的 `## 申请方式` 是非权限小节——正是 T4 把正文收口到「任何 `##`」要挡的情况，
实测它被正确跳过（没有把 `## 申请方式` 的正文吞进上一个权限、也没借用邻居的级别）。

## 4. 实跑挖出的两个真问题（**未擅自修改，请控制方裁决**）

### 4.1 【重要】鸿蒙解析器静默丢弃 41 条多段权限名

`_HARMONY_SECTION` 的正则是

```python
r"^##\s+(ohos\.permission\.[A-Za-z0-9_]+)\s*$"
```

`[A-Za-z0-9_]+` **不容许 `.`**，所以任何名字超过 `ohos.permission.<一段>` 的权限都被
静默跳过。真实文档里有 **41 条**这种权限，涉及 8 个命名段
（`kernel` / `cli` / `securityguard` / `hsdr` / `sec` / `radio` / `vehicle` / `atomicService`），
全部带「权限级别」字段、是货真价实的权限条目：

```
ohos.permission.kernel.NET_RAW / DEBUGGER / ALLOW_DEBUG / IGNORE_LIBRARY_VALIDATION /
  EXEMPT_ANONYMOUS_EXECUTABLE_MEMORY / AUTH_AUDIT_EVENT / ALLOW_APP_CODE_DECRYPT /
  DISABLE_CODE_MEMORY_PROTECTION / ALLOW_WRITABLE_CODE_MEMORY / ALLOW_EXECUTABLE_FORT_MEMORY /
  ALLOW_USE_JITFORT_INTERFACE / DISABLE_GOTPLT_RO_PROTECTION / SUPPORT_PLUGIN /
  LOAD_INDEPENDENT_LIBRARY / AS_LDK_DRIVER
ohos.permission.cli.WRITE_ACCESSIBILITY_CONFIG_VISION / _HEARING / _ACTION /
  READ_ACCESSIBILITY_CONFIG_VISION / _HEARING / _ACTION / BUNDLE_ACTIVE_INFO / INSTALL_BUNDLE /
  UNINSTALL_BUNDLE / GET_BUNDLE_INFO_PRIVILEGED / REMOVE_BUNDLE_DATA_AND_CACHE_FILES /
  MANAGE_DISPOSED_APP_STATUS / GET_STORAGE_MANAGER / START_ABILITY / KILL_APP_PROCESSES
ohos.permission.securityguard.SET_MODEL_STATE / REQUEST_SECURITY_EVENT_INFO /
  REPORT_SECURITY_INFO / REQUEST_SECURITY_MODEL_RESULT
ohos.permission.hsdr.HSDR_ACCESS / REQUEST_HSDR
ohos.permission.sec.ACCESS_UDID
ohos.permission.radio.ACCESS_FM_AM
ohos.permission.vehicle.CAR_MODE_MANAGEMENT
ohos.permission.atomicService.MANAGE_STORAGE / MANAGE_AGING
```

修复是一处字符类放宽（`[A-Za-z0-9_.]+` 或 `[A-Za-z0-9_]+(?:\.[A-Za-z0-9_]+)*`），
落点是 **Task 4 的 `permission_sources.py`，不在 Task 7 的 Files 清单里**，
故未改。它**不会**被要求 1 的断言挡住（742 > 0），是典型的部分静默丢失。
影响面：鸿蒙侧少 41 条（742 → 应为 783），且这 41 条**全部**集中在系统/受控权限，
不影响普通 App 可达集。

### 4.2 【重要】首跑覆盖了 30 行人工 `permission_type`（其中 14 行可达性翻转）

`capability`/`grant_mode` 因是 `None` 被 Ruling F 保住了，但 `permission_type` 由
AOSP 解析器**恒非空**产出，于是首跑（baseline 为 NULL，无人工编辑基线可挡）无条件覆盖。
30 行受影响，逐条：

| 权限 | 覆盖前 → 覆盖后 |
|---|---|
| BLUETOOTH / BROADCAST_STICKY / DISABLE_KEYGUARD / FLASHLIGHT / RESTART_PACKAGES / USE_CREDENTIALS | 已弃用权限 → 普通权限 |
| BODY_SENSORS_BACKGROUND / PROCESS_OUTGOING_CALLS / READ_CALL_LOG / READ_SMS / RECEIVE_MMS / RECEIVE_SMS / SEND_SMS / WRITE_CALL_LOG | 危险权限（受限） → 危险权限 |
| AUTHENTICATE_ACCOUNTS / MANAGE_ACCOUNTS | 签名权限 → 普通权限 |
| QUERY_ALL_PACKAGES / REQUEST_IGNORE_BATTERY_OPTIMIZATIONS | 特殊权限 → 普通权限 |
| com.android.launcher.permission.INSTALL_SHORTCUT / UNINSTALL_SHORTCUT | 三方声明权限 → 普通权限 |
| ACCESS_LOCATION_EXTRA_COMMANDS | 未标注 → 普通权限 |
| GET_ACCOUNTS | 未标注 → 危险权限 |
| MANAGE_EXTERNAL_STORAGE / PACKAGE_USAGE_STATS / READ_CLIPBOARD_IN_BACKGROUND / READ_PRIVILEGED_PHONE_STATE / REQUEST_INSTALL_PACKAGES / SCHEDULE_EXACT_ALARM / SYSTEM_ALERT_WINDOW / WRITE_SETTINGS | 特殊权限 → 签名权限 |

关键在于：`已弃用权限` / `危险权限（受限）` / `三方声明权限` / `未标注` 这 4 个取值
**AOSP 解析器根本产不出来**（`map_android_protection_level` 只会给 危险/普通/签名/特殊/未标注），
它们只可能来自人工。这 10 行（6 + 2 + 2）的信息**在库里已丢失**，只存在于本报告的
上表与导入前快照（`/tmp/t7/pre_android.tsv`，103 行导入前原值）。

下游影响：`permission_taxonomy.is_applicable` 按 `permission_type` 判可达性，
**14 行从「不可达」翻成「可达」**（上表 已弃用权限 6 行 + 签名权限→普通 2 行 +
特殊权限→普通 2 行 + 三方声明 2 行 + 未标注→普通 1 行 + 未标注→危险 1 行）。
这会让合规画像里这些权限被算作「普通 App 可达」。

同样**未擅自处置**：修 `_UPDATABLE` 的过滤策略属 Task 6 的契约，回填 30 行属数据决策，
两者都该由控制方定（例如：AOSP 的 protectionLevel 权威，还是要保护人工的
「已弃用/受限/三方声明」这些 AOSP 推不出来的取值？）。

## 5. 与 brief 的偏差（有意为之，逐条）

1. **`import_permissions.py` 增加了零条断言**——brief 的代码只 `print(len(rows))`，
   而任务上下文把「断言 > 0」列为硬要求 1。故加了 `SystemExit`。
2. **`import_permissions.py` 增加了鸿蒙单文件 0 条告警**——见§3 要求 1 的说明。
3. **改了 `backend/tests/test_permission_import.py` 的一个测试**——见下。

### 测试修复说明（为了「收尾必须仍全绿」）

`test_import_writes_audit_batch_named_per_platform` 原先断言
`count(*) where source_file='permission-import:IOS'` **等于 1**，即隐含假设
「库里从没跑过真导入」。它的 autouse 清理按 id 水位线只删**测试期间新增**的批次，
所以 Task 7 实跑留下的 2 条真实批次（id 201/204）永远留在库里 → 断言变成 3，翻红。

这是 Task 6 测试的隔离性缺陷，被 Task 7「真的跑一次导入」打出来了。
改成断言**增量**（`after == before + 1`，仍按标签过滤，命名语义照旧被检查），
不再依赖全表基数。Task 1 的迁移测试（`test_permission_platform_migration.py`）
当初就写明了「后续任务会导入鸿蒙/iOS 的行」，未受影响。

修完：**303 passed**，与任务基线一致。

## 6. 改动的文件

- 新增 `scripts/fetch_permission_sources.py`（brief 原文）
- 新增 `scripts/import_permissions.py`（brief 原文 + 零条断言 + 单文件告警）
- 新增 `data/kb/`：`SOURCES.json` + 3 平台共 10 个原始文件
- 改 `backend/tests/test_permission_import.py`：1 个测试改为断言增量（§5）

未触碰 `permission_sources.py` / `permission_import.py` / `permission_taxonomy.py`。

## 7. 自审

- **抓取失败条目**：无，10/10 成功，`SOURCES.json` 里 `error` 计数 0。
- **三平台条数与说明占比**：Android 1036（9.9% 有说明）、鸿蒙 742（100%）、iOS 57（98.2%）。
  Android 低占比是预期结果，见§2。
- **那 81 行人工说明**：capability/grant_mode/category 103/103 逐字节未变（§3 要求 2）。
  但同批 30 行的 `permission_type` 被覆盖，已在§4.2 全量列出。
- **测试/临时文件漏进仓库**：`/tmp/t7/` 下的快照都在 `/tmp`，未入仓；
  `data/kb/` 下无 `.tmp`/测试残留；`git add data/` 干跑确认只加 11 个 kb 文件
  （`data/evidence/`、`data/pgdata/` 由 `.gitignore` 挡住）。
- 工作区里另有**不属于本任务**的未跟踪文件，未动：
  `backup/privacy_platform_20260928_pre_kb_fix.sql.gz`、
  `docs/kb-vendor-attribution-audit-2026-09-28.md`。

## 8. 遗留顾虑

1. **鸿蒙少 41 条多段权限名**（§4.1）——一行正则修复，建议尽快补，
   否则 Task 8 的 API 会建在残缺集合上。当前未改（不在 Task 7 Files 清单内）。
2. **30 行 `permission_type` 被首跑覆盖、14 行可达性翻转**（§4.2）——需要一条策略裁决：
   AOSP 权威，还是保护人工推不出来的取值（已弃用/受限/三方声明）？导入前原值我留了快照。
3. 「首次导入无基线可挡」这个洞仍在：任何**恒非空**的人工维护字段（`permission_type`
   是已知的第二个）都会在首跑被冲掉，`None` 过滤只护得住可空字段。若后续还有人工字段，
   建议在 `_UPDATABLE` 层面按字段定策略，而不是继续依赖 `None`。
4. 单文件 0 条告警只覆盖鸿蒙；Android/iOS 各只有一个源文件，其 0 条已被平台级断言挡住，
   暂无缺口。

---

# 修复循环第 1 轮（裁决 L / M / N）

commit `29275bd` `fix(kb): 鸿蒙多段权限名不再静默丢弃；permission_type 与人工成果同等保护`
（父提交 `4dc9ff6 docs(plan): Ruling L/M`，我的首提交 `aa8f0cb` 在祖先链上）。

## 9. 改了什么

| # | 文件 | 改动 |
|---|---|---|
| 1 | `backend/app/services/permission_sources.py` | `_HARMONY_SECTION` 名字段 `[A-Za-z0-9_]+` → `[A-Za-z0-9_.]+`（裁决 L） |
| 2 | `backend/app/services/permission_import.py` | `incoming` 构造后，`existing.permission_type` 非空则 `incoming.pop("permission_type")`（裁决 M） |
| 3 | `backend/tests/test_permission_sources.py` | +`test_harmonyos_parse_accepts_multi_segment_permission_names` |
| 4 | `backend/tests/test_permission_import.py` | +`test_import_does_not_overwrite_human_permission_type` |
| 5 | `data/kb/SOURCES.json` | 重抓产生的 `fetched_at` 刷新（源文件字节未变） |
| 6 | 库（非文件） | 回填 30 行 `permission_type` + 1 行 `manual-corr:` 审计批次（裁决 N） |

两个新用例先单独跑过：`2 passed`。`permission_taxonomy.py` 未触碰。

## 10. 裁决 N：回填与四个字段的被改行数

回填方式：由导入前快照 `/tmp/t7/pre_android.tsv` 生成一条
`UPDATE ... FROM (VALUES ...) WHERE permission_type IS DISTINCT FROM v.pt`，
**只 SET `permission_type` 一个字段**，单事务提交（`UPDATE 30`）。
审计批次沿用库内既有惯例（`manual-corr:` + `statistics.reason` + `created_by`）：

```
source_file | manual-corr:2026-09-28 恢复被首跑覆盖的人工 permission_type
statistics  | {"reason": "...按裁决 M/N 只回填该字段", "rows": 30}
```

**回填后与导入前快照逐字段比对（103 行）：**

| 字段 | 被改行数（期望 0） |
|---|---|
| `capability` | **0** |
| `grant_mode` | **0** |
| `category` | **0** |
| `permission_type` | **0** |

四个数字全为 0。随后重跑导入 `inserted/updated` 全 0 → **机器不会再把它们改回去**，
裁决 M 端到端验证通过。抽查 `android.permission.BLUETOOTH` 仍是 `已弃用权限`、
`SEND_SMS` 仍是 `危险权限（受限）`；`CAMERA` / `ACCESS_FINE_LOCATION` 的
`capability`（使用相机 / 获取精确位置）与 `grant_mode`（运行时授权）原样还在。

### 与裁决里给的两个数字不符（照实报，未凑）

裁决 M 写「被改掉 **28** 行」、表格里「`grant_mode`/`category`/`permission_type`
原有非空 **92**」。**我实测是 30 行、四个字段原有非空均为 103**：

- 快照 103 行、5 字段、无任何空字段（`awk -F'|' '{print NF}'` 全是 5，无 `||`），
  所以「原有非空」= 103 而非 92。
- 差异集合用 Python 全字段精确比对（**不是**我首轮报告里那次 `join`：那次按整行
  `sort` 而非按第 1 字段排序，`'|'`(0x7C) 与 `'.'`(0x2E) 的相对大小会让
  `android.permission.BLUETOOTH` 与 `...BLUETOOTH_ADMIN` 的相对次序翻转，join 有误配风险。
  这轮的 30 是精确比对的结果）。
- 28 → 30 差的 2 行推测是裁决所依据的快照与我的导入前快照不同源（裁决说
  `permission_type` 原有非空 92，即那份快照有 11 个空值，我这份一个都没有）。
- 我按 **30** 全部回填的依据：回填后差异集合恰好为 0；若只回填 28，
  剩下 2 行仍会与快照不符，「四个字段全 0」这条要求就达不成。

**回填的副作用（如实记录）**：`privacy_kb.permission` 上有
`BEFORE UPDATE ... FOR EACH ROW` 的 `trg_permission_updated_at` 触发器，无条件写
`NEW.updated_at = CURRENT_TIMESTAMP`，所以这 30 行的 `updated_at` 被推进到当前时刻
（这是 `UPDATE` 的必然结果，不是我又改了别的字段）。后果是这 30 行在导入的时间戳
基线判定里也算「上次导入之后被人改过」，会被一并冻结——与裁决 M 的意图一致，且
`permission_import` 的内容比较本来就已经先一步把它们 skip 掉。

## 11. 重跑抓取与导入

**抓取**：第一次重跑时 AOSP 清单读超时（`The read operation timed out`），脚本按设计
把它记进 `SOURCES.json`（`error` + `fetched_at: null`）并且**没有覆盖**磁盘上第 1 轮的
好文件；重试一次即 10/10、`error` 计数 0，10 个文件的 sha256 全部与磁盘一致。

> 附带发现（脚本的固有小缺口，brief 原文如此，未改）：失败条目会把 `sha256` 写回
> `null`，而磁盘上那份**仍然有效**——于是 `SOURCES.json` 不再描述仓库里实际存的文件。
> 本次靠重试绕开，但长期看「失败时保留上一轮 sha256」更稳妥。

**解析与导入**（源文件逐字节未变，`git diff` 只有 `SOURCES.json` 的 `fetched_at`）：

```
ANDROID    解析  1016 条  ->  {'inserted': 0,  'updated': 0, 'skipped': 1016}
HARMONYOS  解析   783 条  ->  {'inserted': 41, 'updated': 0, 'skipped': 742}
IOS        解析    57 条  ->  {'inserted': 0,  'updated': 0, 'skipped': 57}
```

**鸿蒙 783 条**（742 + 41），与裁决 L 的预期一致；41 条全部落库，无一因词表外被跳
（否则 `inserted` 会少于 41）。第三次跑三平台 `inserted` 全 0，幂等仍成立。

41 条按命名段与级别分布（级别全部落在 `normal` / `system_basic` / `system_core` 词表内）：

| 段 | 条数 | 级别 |
|---|---|---|
| kernel | 15 | normal, system_basic, system_core |
| cli | 15 | system_basic, system_core |
| securityguard | 4 | system_basic, system_core |
| atomicService | 2 | system_basic |
| hsdr | 2 | normal, system_basic |
| sec | 1 | system_basic |
| radio | 1 | system_core |
| vehicle | 1 | system_basic |

**落库最终态**：

```
 platform  | count | 有说明
-----------+-------+--------
 ANDROID   |  1036 |    103
 HARMONYOS |   783 |    783
 IOS       |    57 |     56
```

## 12. 全套回归

`cd backend && /tmp/venv/bin/python -m pytest tests/ -q` → **305 passed**（303 + 2 个新用例，
与裁决预期一致）。测试无残留（`test.import.perm.%` 计数 0），库中数据未被测试改动。

## 13. 修复后的遗留顾虑

1. **裁决 L 的同类风险未复查**：`_HARMONY_ANY_HEADING` 是 `^(?=##\s)`，`###` 前是
   `#` 不是空白，所以 `###` **不是**切分点——这正是 Ruling H 的形态。本次真实文档里
   `###` 计数为 0（§3 要求 5），所以没暴露；但鸿蒙文档哪天加了 `###` 子小节，
   级别仍会被借用。未改（不在裁决 L/M/N 范围内）。
2. 「首次导入无基线可挡」的洞现在被两层（`None` 过滤 + `permission_type` 保护）挡住了
   已知的两个字段，但**没有通用机制**：第三个恒非空的人工字段还会重蹈覆辙。
   建议后续在 `_UPDATABLE` 层面按字段声明策略，而不是继续加特例。
3. 抓取失败会清空 `SOURCES.json` 里对应文件的 `sha256`（见§11），与磁盘实际内容脱节。

---

# 修复循环第 2 轮（4 条 Important + 可复现性补强）

commit `02a0633` `fix(kb): 只冻结机器推不出的 permission_type；抓取清单与实际文件不再脱节`
（父 `baf4aa7 docs(plan): Ruling M'`）。

## 14. 修复 1（Ruling M'）：`permission_type` 保护过度 → 只冻结机器推不出的取值

上一轮的 `if existing.permission_type: incoming.pop(...)` 是**保护过度**：解析器从不返回空，
首跑之后 1036 行全非空 → AOSP 的重新分类永远进不来，全库冻结在该字段上，而
`is_applicable` 正是从它推的。

- `backend/app/services/permission_taxonomy.py` 新增 `PARSER_PRODUCIBLE_TYPES`：
  `ANDROID = set(ANDROID_PROTECTION_LEVEL_MAP.values()) | {"未标注"}` =
  `{危险权限, 普通权限, 签名权限, 特殊权限, 未标注}`；鸿蒙/iOS 取各自词表。
- `permission_import.py` 判据改为「值不在 `PARSER_PRODUCIBLE_TYPES[platform]` 里才拦」。
- 补成对测试 `test_import_lets_parser_recoverable_type_update`（306 passed 里的 +1）。

### 解冻了多少行：**14 行**，逐条如下（重跑导入 `updated: 14`，与快照比对的 permission_type 差异也是这 14 行）

| 权限 | 更新前 → 更新后 |
|---|---|
| MANAGE_EXTERNAL_STORAGE / PACKAGE_USAGE_STATS / READ_CLIPBOARD_IN_BACKGROUND / READ_PRIVILEGED_PHONE_STATE / REQUEST_INSTALL_PACKAGES / SCHEDULE_EXACT_ALARM / SYSTEM_ALERT_WINDOW / WRITE_SETTINGS | 特殊权限 → 签名权限（8） |
| AUTHENTICATE_ACCOUNTS / MANAGE_ACCOUNTS | 签名权限 → 普通权限（2） |
| QUERY_ALL_PACKAGES / REQUEST_IGNORE_BATTERY_OPTIMIZATIONS | 特殊权限 → 普通权限（2） |
| GET_ACCOUNTS | 未标注 → 危险权限（1） |
| ACCESS_LOCATION_EXTRA_COMMANDS | 未标注 → 普通权限（1） |

全部 14 行的原值**恰好都是机器自己算得出来的取值**，所以按 M' 归机器。其中 6 行
（签名权限→普通 2、特殊权限→普通 2、未标注→危险/普通 2）的 `is_applicable` 由不可达
变可达——这是 AOSP 的判定，不是被抹掉的人工知识。

**机器推不出来的取值一行未动**：`已弃用权限` 12 行、`危险权限（受限）` 8 行、
`三方声明权限` 12 行（合计 32 行），重跑后全部保持原值。

> 与快照比对时注意：那 14 行的差异是**设计如此**，不是回归——回填脚本刻意不回填
> 机器算得出来的值（否则就把 AOSP 的重新分类挡在门外，正是 M' 要修的）。
> 快照对这些行的定位是「人工来源记录」，不是「终态」。

## 15. 修复 2：抓取失败不再让清单与实际文件脱节

`scripts/fetch_permission_sources.py`：写清单前先读回上一轮清单；**失败条目沿用**
上一次的 `sha256`/`bytes`/`fetched_at` 并带上新的 `error`；成功且字节未变时也沿用
`fetched_at`（它记的是内容何时到手，不是脚本何时跑过）。

验证两路：
- **成功路（真实）**：重抓 10/10，逐条打印「（内容未变）」，`git diff -- data/kb/SOURCES.json`
  **零变化**——上一轮那种每次重抓都刷 `fetched_at` 的噪声没有了。
- **失败路（构造）**：临时 ROOT + 打不通的地址（`http://127.0.0.1:1`）实测：
  `error` 写入、`sha256`/`bytes`/`fetched_at` 三项与上一轮完全一致、磁盘文件未被删。

## 16. 修复 3：鸿蒙文件清单不再有两份

`scripts/import_permissions.py` 删掉 `glob("permissions-for-*.md") + glob("restricted-permissions.md")`，
改为新增 `_harmony_files()` 从入仓的 `SOURCES.json` 派生。抓什么就导什么。

验证：临时 KB 里放一个**老 glob 匹配不到**的 `extra-permissions.md`（清单里登记了它），
`_load("HARMONYOS")` 读到了它（`['ohos.permission.X']`）——这正是原先会静默漏读的形态。
清单登记了而磁盘缺失时 `SystemExit` 出声：
`SOURCES.json 列了 extra-permissions.md，但磁盘上没有——先跑抓取脚本`。

## 17. 修复 4：断言与导入分两趟

`main()` 拆为 `_load_all()`（三平台全部解析 + 断言非零）与导入两趟，任何写入之前即中止。

验证：把 IOS 的 `_load` 换成返回 `[]` 后跑 `main()`——
先打印 `ANDROID 解析 1016 条` / `HARMONYOS 解析 783 条`，随即
`SystemExit: IOS 解析出 0 条…`；库内 `import_batch` 计数 **48 → 48**、
`permission` 总行数 **1876 未变**，确认一条都没写。

## 18. 修复 5：Ruling N 的产物入仓（可复现性）

- 新增 `data/kb/curated_permission_snapshot.tsv`：导入前的 103 行人工值，
  `|` 分隔（**不是** tab，脚本对列数不对会报错），`#` 起首为注释（含列定义与用途）。
  其中 **20 行不在 AOSP 清单里**（`com.*` 三方声明权限、若干已废弃的 `android.permission.*`）。
- 新增 `scripts/restore_curated_permissions.py`（幂等、不联网）：只填机器推不出来的
  ——`capability`/`grant_mode`/`category` 仅在库中为空时填；`permission_type` 只填
  非 `PARSER_PRODUCIBLE_TYPES` 的取值，机器能算的留给导入器；快照有而库里没有的行
  **创建**（不建则重建少 20 行）。每次运行留一条 `manual-corr:` 审计批次。

验证（三条路径都实测）：
1. **no-op**：在正确态上连跑两次 → `新建 0 行，回填 0 行`。
2. **回填**：把 `android.permission.BLUETOOTH` 的 `capability`/`grant_mode`/`category`
   清空、`permission_type` 改成机器可产的 `普通权限` → 跑一次全部复原为
   `旧版蓝牙连接能力|安装时授权|蓝牙与附近设备|已弃用权限`。
3. **新建 + 不覆盖机器可算值**：用临时快照加一行库里没有的（`三方声明权限`）→ 被创建且
   5 个字段齐全；同时造一行库里为 `普通权限`、快照为 `危险权限`（两者都可产）→
   **未被改动**（仍是 `普通权限`），证明回填不会顶掉机器的判定。测试数据已清理。

## 19. 重跑与最终数字

**抓取**：10/10 成功，`error` 计数 0，`SOURCES.json` 零 diff（内容未变，见§15）。

**导入**（三平台解析数不变，因为源文件字节未变）：

```
ANDROID    解析  1016 条  ->  {'inserted': 0, 'updated': 14, 'skipped': 1002}
HARMONYOS  解析   783 条  ->  {'inserted': 0, 'updated':  0, 'skipped':  783}
IOS        解析    57 条  ->  {'inserted': 0, 'updated':  0, 'skipped':   57}
```

**第三次跑**：三平台 `inserted`/`updated` 全 0（幂等仍成立）。

**落库**：

```
 platform  | count | 有说明
-----------+-------+--------
 ANDROID   |  1036 |    103
 HARMONYOS |   783 |    783
 IOS       |    57 |     56
```

**与入仓快照的逐字段比对（103 行）**：`capability` **0**、`grant_mode` **0**、
`category` **0**、`permission_type` **14**（即§14 那批 AOSP 重新分类，设计如此）。

**回归**：`cd backend && /tmp/venv/bin/python -m pytest tests/ -q` → **306 passed**
（305 + 新增的成对测试），与裁决预期一致。库内无测试残留（`test.%` 计数 0）。

## 20. 本轮的遗留顾虑

1. **§14 那 14 行的语义变化要有意识**：6 行的 `is_applicable` 由不可达变可达，是按 M'
   把判定权交给了 AOSP。若业务上认为「特殊权限」这个人工判断优于 AOSP 的
   `protectionLevel`，那 M' 的边界（哪些值算「机器能算」）需要再谈——现在快照保留了
   原值，可回溯。
2. 快照与库的 `permission_type` 差异会**长期存在 14 行**，这是设计而非漂移。
   别把「与快照零差异」当成健康检查的判据。
3. 「恒非空的人工字段」现在靠 `PARSER_PRODUCIBLE_TYPES` 这个按平台的集合兜着，
   比上一轮的「非空即冻结」精确得多，但**机制仍是特例**：新增平台词表时要记得同步
   维护这个集合（它已从 `PERMISSION_TYPES_BY_PLATFORM` / `ANDROID_PROTECTION_LEVEL_MAP`
   派生，新增取值只要走这两个来源就会自动跟上）。
4. `_HARMONY_ANY_HEADING` 的 `###` 借用风险（上轮§13.1）本轮未动，仍在。
