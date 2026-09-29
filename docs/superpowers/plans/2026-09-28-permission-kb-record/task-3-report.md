# Task 3 报告：Android 解析器

**Status: DONE_WITH_CONCERNS**
Commit: `a83d400` feat(kb): Android 权限清单解析器 + `1f8da10` test(kb): 钉住同名权限「取更严主级别」的归并方向
BASE `58beace` → HEAD `1f8da10`

> 唯一顾虑与本次实现无关，是**下游 T6/T7 的数据安全洞**：首次导入会让 83 行人工填写的
> `capability` / `grant_mode` 被 NULL 覆盖。详见 §6.1，请控制方在派发 T6 前裁决。
> §5.1 记录的那个测试缺口已按审查裁决修复，见文末「修复循环第 1 轮」。

---

## 1. 实现了什么

新建 `backend/app/services/permission_sources.py`（69 行，纯函数、无 IO、无数据库）。

**导出接口**

| 名称 | 内容 |
|---|---|
| `parse_android_manifest(xml_text) -> list[dict]` | 解析 AOSP `core/res/AndroidManifest.xml`，按 `permission_name` 归并后按名排序返回 |
| `_android_level_width(raw)` | `protectionLevel` 主级别 → 宽窄分；`\|` 段之后忽略，取第一段 |
| `_LEVEL_WIDTH` / `_ANDROID_NS` / `_ANDROID_REF` | 模块常量，brief 取值逐字 |

统一行形状（即 T4/T5 的接口契约，逐字照 brief）：
`{"permission_name", "permission_type", "capability", "grant_mode", "official_reference", "raw_data"}`，
其中 `raw_data = {"platform_source": "aosp_core_manifest", "protection_levels_seen": [...], "permission_group": ...}`。

关键行为：
- **同名归并**：取更宽的主级别（`_LEVEL_WIDTH` 序 `normal < dangerous < internal/system/role/module < signature`），
  并为该级别重跑 `map_android_protection_level`；出现过的每个 `protectionLevel` 原样留在 `raw_data.protection_levels_seen`。
- **`capability` 恒为 `None`**（全局约束：AOSP core 清单不提供可解出的描述文本，不编造、不填占位）。
- `grant_mode` 恒为 `None`（设计文档 §4：Android 的授予方式来自 `protectionLevel`，已体现在 `permission_type`）。
- `official_reference` = `.../Manifest.permission#<名字最后一段>`。
- 非 `<permission>` 元素、无 `android:name` 的 `<permission>` 一律跳过；`_width` 是内部临时键，返回前 pop 掉。

## 2. 测了什么与结果

`backend/tests/test_permission_sources.py`，brief 逐字的 5 个测试（未增删）：

| 测试 | 断言 |
|---|---|
| `test_android_parse_dedupes_by_name` | 无重名行；`CAMERA` 只出 1 行 |
| `test_android_parse_maps_protection_level` | CAMERA→危险权限、ACCESS_NETWORK_STATE→普通权限、BIND_ACCESSIBILITY_SERVICE→签名权限、CONFIGURE_WIFI_DISPLAY→特殊权限 |
| `test_android_parse_keeps_all_protection_levels_in_raw_data` | CAMERA 的 `protection_levels_seen == ["dangerous", "dangerous\|privileged"]` |
| `test_android_parse_leaves_capability_empty` | 所有行 `capability is None` |
| `test_android_parse_sets_official_reference` | CAMERA 的引用以 `https://developer.android.com/reference/android/Manifest.permission#` 开头 |

**结果**
- 聚焦：`5 passed in 0.02s`，无 warning。
- 全量：`286 passed, 34 warnings in 12.41s` = 基线 281 + 新增 5，**与 brief 预期一致**。
  34 warnings 与 Task 2 记录的基线数量相同，全部是仓库既有 SQLAlchemy `LegacyAPIWarning`。
- 无一处 mock：纯函数直断言真实返回值。

### 2.1 额外验证（brief 之外，未新增测试文件内容）

**变异测试**（逐条篡改生产代码 → 跑 brief 的 5 个测试 → 从备份还原；还原后 `git diff` 为空）：

| 变异 | 结果 |
|---|---|
| `hit = merged.get(name)` → `hit = None`（取消归并） | **CAUGHT** 1 failed |
| `"capability": None` → `"capability": "待补充"` | **CAUGHT** 1 failed |
| 归并分支不再累积 `protection_levels_seen` | **CAUGHT** 1 failed |
| `_ANDROID_REF` 换成 `https://example.com/` | **CAUGHT** 1 failed |
| `permission_type` 硬编码 `"普通权限"`（不调映射） | **CAUGHT** 1 failed |
| `>` 改 `<`（取更窄的主级别） | **MISSED** 5 passed ← 见 §5.1 |
| `protection_levels_seen.sort()` 改 `sort(reverse=True)` | **MISSED** ← 见 §5.2 |
| `permission_group` 恒 `None` | **MISSED** ← 见 §5.3 |

**真实数据冒烟**（拉到 `/tmp`，**未入库、未提交**；`data/kb/` 是 T7 的产物）：
取 `raw.githubusercontent.com/aosp-mirror/platform_frameworks_base/master/core/res/AndroidManifest.xml`
（503,122 字节）跑解析器：

- `<permission>` 元素 **1018** 个，其中 2 个名字重复（`ACCESS_SHARED_LIBRARIES`、
  `SET_DEFAULT_ACCOUNT_FOR_CONTACTS`）→ **输出 1016 行，无重名**。与 brief 反复引用的
  「实测 1018 条」对得上，差额被归并逻辑精确解释。
- `permission_type` 分布：签名权限 751 / 普通权限 100 / 危险权限 43 / 特殊权限 122。
  「普通 App 可达」（危险+普通）= **143**，与设计文档 §4「1018 条里只有 143 条落在这里」**完全一致**。
- 1016 行全部 `capability is None`、`grant_mode is None`，引用全部带正确前缀，
  行内键集恰为契约 6 键（`_width` 无泄漏）。
- `root.iter("permission")` 与根直接子元素计数都是 1018（**无嵌套 `<permission>`**），
  即「只遍历根的直接子元素」在真实数据上不丢行。
- 边界行为另行核对通过：非 `<permission>` 元素与无 name 元素被跳过；缺 `protectionLevel`
  → `未标注` 且 `protection_levels_seen == []`；`permission_group` 能从后出现的重复条目补上；
  畸形 XML 抛 `ParseError`（不静默返回空表）。

## 3. TDD 证据

### RED
命令：`cd backend && /tmp/venv/bin/python -m pytest tests/test_permission_sources.py -v`

```
collecting ... collected 0 items / 1 error
==================================== ERRORS ====================================
______________ ERROR collecting tests/test_permission_sources.py _______________
ImportError while importing test module '/home/user/privacy-platform/backend/tests/test_permission_sources.py'.
Hint: make sure your test modules/packages have valid Python names.
Traceback:
tests/test_permission_sources.py:4: in <module>
    from app.services.permission_sources import parse_android_manifest
E   ModuleNotFoundError: No module named 'app.services.permission_sources'
=========================== short test summary info ============================
ERROR tests/test_permission_sources.py
!!!!!!!!!!!!!!!!!!!! Interrupted: 1 error during collection !!!!!!!!!!!!!!!!!!!!
=============================== 1 error in 0.10s ===============================
```

**为什么预期失败**：测试在导入期就 `from app.services.permission_sources import ...`，
而生产模块此时尚不存在 → 收集阶段即 `ModuleNotFoundError`，与 brief Step 3 预期逐字一致。
纯新增模块没有「已存在但逻辑错」的中间态，所以 RED 表现为收集失败。

### GREEN
命令：`cd backend && /tmp/venv/bin/python -m pytest tests/test_permission_sources.py -v`

```
collecting ... collected 5 items

tests/test_permission_sources.py::test_android_parse_dedupes_by_name PASSED [ 20%]
tests/test_permission_sources.py::test_android_parse_maps_protection_level PASSED [ 40%]
tests/test_permission_sources.py::test_android_parse_keeps_all_protection_levels_in_raw_data PASSED [ 60%]
tests/test_permission_sources.py::test_android_parse_leaves_capability_empty PASSED [ 80%]
tests/test_permission_sources.py::test_android_parse_sets_official_reference PASSED [100%]

============================== 5 passed in 0.02s ===============================
```

## 4. 改了哪些文件

只新增 3 个文件，**未改动任何既有文件**（`git show --stat a83d400` = 3 files changed, 133 insertions）：

- `backend/app/services/permission_sources.py`（新增，69 行）
- `backend/tests/fixtures/permission_sources/android_manifest_sample.xml`（新增，19 行）
- `backend/tests/test_permission_sources.py`（新增，45 行）

三个文件与 brief 的代码块**逐字一致**，唯一的差别是去掉了代码块首行的路径注解行
（`# backend/...`、`<!-- backend/... -->`）——这是本仓库既有约定（Task 2 的
`test_permission_taxonomy.py` / `permission_taxonomy.py` 同样不带注解行，且已过审）。
XML 的注解行**必须**去掉：它落在 `<?xml ...?>` 声明之前，会让文档非法、`ET.fromstring` 直接报错。
已用脚本比对确认去掉注解行后三份文件与 brief 逐字相同。

**未提交**：工作树里那个与本任务无关的未跟踪文件
`backup/privacy_platform_20260928_pre_kb_fix.sql.gz`（会话早先的数据库备份）保持原位不动，
一如 Task 2 的处理。

## 5. 自审发现

### 5.1 「取更宽的主级别」这条规则没有被测试真正钉住（真缺口，但**不改**）
把 `_android_level_width(level) > hit["_width"]` 改成 `<`，5 个测试**全部通过**。
原因：fixture 里唯一的重复名是 `CAMERA`，两次都是 `dangerous` 族（宽度同为 2），
**没有任何一个名字出现过两个不同宽度的级别**，所以宽度比较分支在 fixture 上恒不生效。
真实数据同理——1016 个名字里只有 2 个重复，且那 2 个的主级别在两次声明中相同
（`signature|installer` vs `signature|installer|role`；`internal|role` vs `internal|role|knownSigner`）。
也就是说：**这条规则在当前真实数据上（含 fixture）从未真正决定过任何一行的取值**，它是防御性的。

我已离线单独验证过它的行为正确（`normal` + `signature` 同名 → 签名权限，且与声明顺序无关），
但**没有把它写成测试**：brief 明令逐字使用其 5 个测试，加第 6 个会破坏「286 passed」的验收口径。
若控制方认为该分支值得钉住，可在 T6 或后续补一条测试（用例：同名 `normal` + `signature`）。

### 5.2 `protection_levels_seen` 的排序未被断言
测试用 `sorted(raw[...])` 断言，对顺序不敏感，因此把 `.sort()` 改成 `sort(reverse=True)` 不被抓到。
这是 brief 测试自身的写法（`sorted()`），不是实现缺陷；实现确实排了序，且真实数据里只有 2 行含 2 个级别。
保留 brief 原样，不额外加断言。

### 5.3 `permission_group` 完全没有测试覆盖
brief 的 5 个测试都没断言它，所以「`permission_group` 恒 `None`」这种破坏也抓不到。
我已离线验证行为符合实现意图（保留首个非空值，能从前无后有的重复条目补上）。
属 brief 测试范围的既知空白，不擅自加测试。

### 5.4 逐项复核结论
- **完整性**：brief 的 Produces 契约（函数签名 + 6 键行形状）逐字落地；与 progress.md 的
  「T3 → T7 `_load`：返回 `list[dict]`」一致。
- **命名**：函数、常量、`raw_data` 键名（`platform_source` / `protection_levels_seen` / `permission_group`）
  与 brief 及设计文档一致；`platform_source` 取值 `aosp_core_manifest` 与 T4 的 `openharmony_docs`、
  T5 的 `apple_protected_resources` 构成同一命名族。
- **YAGNI**：零额外代码，未提前给 T4/T5 预留分支；未加任何「顺手」的辅助函数。
- **未使用 import `json` / `re`**：brief 逐字给定，本任务确实用不到（`json` 是 T5、`re` 是 T4 要用的）。
  已确认仓库无 ruff/flake8/pre-commit 等 lint 配置，不会挂门禁；删掉反而偏离逐字指令，故保留。
  提请 T4/T5 记得用上，否则这两个 import 会长期悬着。
- **测试输出干净**：聚焦运行无 warning；全量 34 warnings 与基线同数、同源。

## 6. 遗留顾虑

### 6.1 ⚠️ 首次导入会覆盖 83 行人工填写的 `capability` / `grant_mode`（**需控制方裁决，非本任务代码问题**）
`capability` 恒为 `None` 是 brief 的正确要求；但计划里 T6 的 UPSERT（plan 第 1026–1057 行）
对已存在的同名行是**整字段赋值**（`setattr(existing, field, value)`），且「不覆盖人工编辑」
的保护依赖 `import_batch.finished_at` 基线——**首次导入没有基线，保护不生效**。

我用真实 AOSP 解析结果 + 库中现有 103 行做了交集测算：

```
库中 103 行；与本次 AOSP 解析结果同名的 83 行
若 T6 直接覆盖：capability 会从有文本变 NULL 的 83 行
                grant_mode 会从有取值变 NULL 的 83 行
例：android.permission.ACCESS_FINE_LOCATION 现为 capability=<文本>、grant_mode='运行时授权'
    → 导入后会变成 capability=NULL、grant_mode=NULL
```

即 T7 一旦跑真实导入，**83 行人工知识会被静默清空**（`raw_data` 也会被换成解析值）。
今天库里 `grant_mode` 有 37 种人工取值（运行时授权 26、安装时授权 20……），全是人的心血。

可能的处置（我不越权改 T6 文件，交控制方选）：
1. **T6 改为字段级合并且尊重人工值**：解析值为 `None` 时不覆盖库中已有的非空值；
2. 或 T7 首跑前对 `privacy_kb.permission` 做快照/备份，导入后逐行比对恢复；
3. 或 T6 明确「解析结果对人工行的既有非空字段只读不写」，并加一条测试钉住。

无论选哪种，**建议 T6 的测试里补一条**：库中某行有非空 `capability`、解析行 `capability=None`
时，导入后该行 `capability` 仍非空。这条测试目前不存在，所以这个洞不会被 T6 自己的测试拦住。

### 6.2 「宽」的语义方向
`_LEVEL_WIDTH` 把 `signature`(4) 放在 `dangerous`(2) **之上**，即「更宽 = 更严格/更受限」，
所以「危险+签名」同名时归并结果是**签名权限**（普通 App 更不可达）。这符合设计文档
「取更宽的 protectionLevel」，但若控制方心中的「宽」指「更宽松（更可达）」，方向就反了。
brief 逐字规定了该常量，我照做；当前真实数据不触发该分支（见 §5.1），故无实际影响，仅备核。

### 6.3 `raw_data` 会带 `permission_group: null`
`<permission>` 无 `android:permissionGroup` 时该键为 `None`（真实数据里绝大多数如此）。
JSON 可序列化，与 T6 的 `raw_data=row.get("raw_data") or {}` 兼容；
但若 T8 的 API 把它原样透出，前端需容忍 `null`。提请 T8 注意。

无阻塞项，无需 HELP。

---

# 修复循环第 1 轮（审查 Important：plan-mandated）

**Status: DONE**
追加 Commit: `1f8da10` test(kb): 钉住同名权限「取更严主级别」的归并方向

审查发现与我的 §5.1 自审结论一致：`_LEVEL_WIDTH` 的 `>` 比较是实现「同名取更宽/更严主级别」
的唯一位置，而 fixture 里唯一的重名 CAMERA 两次声明的主级别都是 `dangerous`（宽度同为 2），
那个比较永不 fire —— 把 `>` 翻成 `<` 五个测试照样全绿。

## 1. 改了什么

**只改一处**：`backend/tests/test_permission_sources.py` 末尾新增
`test_android_parse_duplicate_name_keeps_the_more_restrictive_level`（+21 行）。
逐字取自更新后的 plan（`docs/superpowers/plans/2026-09-28-permission-kb-multi-platform.md`
Task 3 Step 2 末尾），已用脚本比对确认与 plan 代码块**逐字相同**。

生产代码 `permission_sources.py` **一个字符都没动**（`git show --stat 1f8da10` = 1 file changed,
21 insertions；`git diff --stat` 中无该文件）。方向按裁决保持「更严的级别胜出」不变
（`signature` > `dangerous` > `normal`）。

测试用内联 XML（不落 fixture 文件）构造同名但主级别不同的两条声明：
`android.permission.DUP` 先 `normal` 后 `signature`，断言
`permission_type == "签名权限"` 且 `protection_levels_seen == ["normal", "signature"]`。

## 2. 跑了哪些覆盖性测试

### 2.1 聚焦（GREEN）
命令：`cd backend && /tmp/venv/bin/python -m pytest tests/test_permission_sources.py -v`

```
collecting ... collected 6 items

tests/test_permission_sources.py::test_android_parse_dedupes_by_name PASSED [ 16%]
tests/test_permission_sources.py::test_android_parse_maps_protection_level PASSED [ 33%]
tests/test_permission_sources.py::test_android_parse_keeps_all_protection_levels_in_raw_data PASSED [ 50%]
tests/test_permission_sources.py::test_android_parse_leaves_capability_empty PASSED [ 66%]
tests/test_permission_sources.py::test_android_parse_sets_official_reference PASSED [ 83%]
tests/test_permission_sources.py::test_android_parse_duplicate_name_keeps_the_more_restrictive_level PASSED [100%]

============================== 6 passed in 0.02s ===============================
```

5 → **6 passed**，与预期一致。

### 2.2 变异复验（本轮重点：证明新测试真的钉住了那条规则）
篡改 `permission_sources.py` → 跑测试 → 从备份还原（还原后校验字节相同，且 `git diff` 中无该文件）：

| 变异 | 结果 | 抓住它的测试 |
|---|---|---|
| `>` 改成 `<`（取更窄的主级别） | **CAUGHT** `1 failed, 5 passed` | `test_android_parse_duplicate_name_keeps_the_more_restrictive_level` |
| `_LEVEL_WIDTH` 把 `normal` 提到 9（签名反被压到普通之下） | **CAUGHT** `1 failed, 5 passed` | 同上 |
| 宽度取 `|` **最后**一段而非第一段 | MISSED `6 passed` | — 见下 |

前两条正是审查要求的核心验证：**`>` 翻成 `<` 现在会变红**，修复生效。
第三条不红是合理的：`normal` / `signature` 都不带 `|`，两个实现给出同样结果；
`|` 分段取法本身由 T2 的 `map_android_protection_level`（取第一段）与 fixture 的
`dangerous|privileged` 用例从另一侧约束，不属本轮范围。

### 2.3 全量回归
命令：`cd backend && /tmp/venv/bin/python -m pytest tests/ -q`

```
287 passed, 34 warnings in 12.17s
```

286 → **287 passed**，与预期一致；34 warnings 与基线同数同源（仓库既有 SQLAlchemy `LegacyAPIWarning`）。

## 3. 本轮自审

- 只加了这一条测试，没有「顺手」改别的：生产代码、fixture 文件、其余 5 个测试均未变。
- 新测试不依赖 fixture 文件、不 mock，直接对真实返回值断言；两个断言分别覆盖
  **主级别方向**（`签名权限`）与 **raw_data 保留全部出现**（`["normal", "signature"]`）。
- 未跟踪文件 `backup/privacy_platform_20260928_pre_kb_fix.sql.gz` 仍保持原位未提交。

## 4. 未提交项（交控制方）

`docs/superpowers/plans/2026-09-28-permission-kb-multi-platform.md` 现有**未提交的工作树改动**
（+56/-2，即本次新增该用例的那段 plan 更新），是控制方自己改的、不在我的 commit 列表内，
故**未提交**，保持原位。若需入库请由控制方以自己的 commit 提交。

## 5. 顾虑

§6.1 的 **T6/T7 覆盖风险不变**（首次导入无基线 → 83 行人工 `capability`/`grant_mode` 被 NULL 覆盖），
仍请控制方在派发 T6 前裁决。其余顾虑见 §6.2、§6.3，本轮无新增。
