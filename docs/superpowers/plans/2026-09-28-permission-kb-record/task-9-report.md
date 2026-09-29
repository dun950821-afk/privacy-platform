# Task 9 报告：前端平台维度

日期：2026-09-28　commit：`0bd98e6` feat(ui): 权限知识库增加平台维度与可达性过滤

## 1. 实现了什么

严格按 brief 的模板片段实现（`dict.ts` 的 `PLATFORM`、两个控件的 HTML、表格平台列、
弹窗平台项、`loadData` 的 query 两行、`applicable: filters.applicable || undefined` 均逐字照抄）：

1. `frontend/src/utils/dict.ts`：追加 `PLATFORM`（配色用途，与既有 `PERMISSION_TYPE` 同类）。
2. `frontend/src/api/permissions.ts`：`meta: (params?: any) => api.get('/permissions/meta', { params })`。
3. `frontend/src/views/Permissions.vue`
   - 筛选栏关键字后加「全部平台」下拉（选项来自 `meta.platforms`，label 走 `dictLabel(PLATFORM, p)`）
     与「只看应用可申请」勾选框；
   - 列表在「权限名」后加「平台」列（`StatusTag :map="PLATFORM"`）；
   - `meta` 加 `platforms: []`，`filters` 加 `platform: ''` 与 `applicable: true`（默认只看可申请）；
   - `loadData` 的 query 加 `platform` 与 `applicable`；
   - `resetFilters` 重置这两项；弹窗加「平台」选择（`editingId` 时 `disabled`），
     `form.platform` 默认 `'ANDROID'`，`resetForm`/`openCreate` 恢复 `'ANDROID'`，
     创建 payload 带 `platform`，**编辑 payload 不带**。

### 与 brief 的 3 处刻意偏离（全部是功能性修正，均可一行删掉）

| # | brief 原文 | 我写的 | 为什么 |
|---|---|---|---|
| 1 | `async function loadMeta()`，内部读 `filters.platform` | `loadMeta(platform?: string)`，`p = platform ?? filters.platform` | brief 把弹窗的平台下拉挂在 `@change="loadMeta"` 上。el-select 的 change 会把新值当第一个实参传进来，若 loadMeta 不接参数，这个实参会被丢掉、词表仍按**筛选栏**的平台取——建鸿蒙权限时类型下拉给的是 Android 的 8 个取值，选了必被后端 400。加一个可选参数后，brief 的全部调用点（`loadMeta()`、`onPlatformChange`、`handleSubmit`、`@change="loadMeta"`）一字未改而语义正确。 |
| 2 | `resetFilters` 只重置 `platform`/`applicable` | 额外加一行 `loadMeta()` | `resetFilters` 把平台从「鸿蒙」改回「全部」，词表却留在鸿蒙，类型下拉会继续列 `normal/system_basic/system_core`——即 brief 在 `onPlatformChange` 里要避免的同一类问题。这行是维持「词表与当前平台一致」这条不变量的必要动作。 |
| 3 | 未提 `openEdit` 的 platform | `openEdit` 里加 `platform: res.data.platform \|\| 'ANDROID'` | 平台框在编辑态是 `disabled` 但**可见**。不填的话，编辑一条鸿蒙权限会显示成「Android」——是错的信息，不是留白。值取自后端 `_detail` 的 `platform`，非编造。 |

这三处都在既有模式内，没有新增抽象；第 1 处若不认可，改回无参版即可，代价是弹窗类型下拉与平台不匹配。

## 2. 跑过的验证与结果

- **类型检查**：`cd frontend && npx vue-tsc -b` → 退出码 0、无输出。
- **构建**：`cd frontend && npm run build` → `✓ built in 16.96s`，产出
  `dist/assets/Permissions-DFs7-X8X.js`（11.04 kB）。
- **dev server 编译**：运行中的 5173 是 vite dev（读源码、无 `--reload` 问题），我的改动它已生效。
  逐个拉取转换后的模块均为 HTTP 200：`src/views/Permissions.vue`（67 KB）、`src/utils/dict.ts`、
  `src/api/permissions.ts`；转换结果里 `只看应用可申请`/`全部平台`/`onPlatformChange`/`PLATFORM`/
  `platforms`/`loadMeta` 标记齐全（模板编译失败会返回 500，没出现）。
- **后端契约（经 **5173 的 vite proxy**，即浏览器实际走的那条路；token 用 `create_access_token('admin','platform_admin')` 现签）**：
  - `meta`（不带参）→ `platforms: [ANDROID, IOS, HARMONYOS]`、`permission_types` = 12 个并集；
  - `meta?platform=HARMONYOS` → `["normal","system_basic","system_core"]`；
  - `meta?platform=ANDROID` → 8 个（危险权限…未标注）。与 brief Step 6 的预期逐字一致。
  - `list?applicable=true` → 308（= Android 136 + 鸿蒙 115 + iOS 57）；`applicable=false` → 1568；
    不传 → 1876。**三态在后端确实成立**，308+1568=1876。
  - `list?platform=HARMONYOS&applicable=true` → total 115，返回行 platform 全为 HARMONYOS；
  - `list?platform=ANDROID&permission_type=签名权限&applicable=true` → 0 行；同一条件去掉 `applicable`
    → 753 行。即 Step 6 的「取消勾选后能看到签名权限行」成立（签名权限被判定为不可达）。
  - 错误路径：`meta?platform=BAD` → HTTP 400 `{"detail":"platform 只能是：ANDROID、IOS、HARMONYOS"}`，
    是带 detail 的 4xx，axios 拦截器会 `ElMessage.error(detail)`，页面不会白屏或崩。
- **后端回归**：`cd backend && /tmp/venv/bin/python -m pytest tests/ -q` → **315 passed**（我只改前端）。

### 没能做到的验证

**本环境没有 headless 浏览器**（无 playwright / puppeteer / chromium，`node_modules` 里也没有 jsdom）。
所以 brief Step 6 的「打开 /permissions 上手点」我是**用等价手段替的**：把页面会发的每一次请求
（含默认勾选态、切平台、取消勾选、非法参数）按 axios 的序列化方式对着 5173 代理实打了一遍，
并确认 SFC 能被 dev server 编译。**没有真的在浏览器里点过**，视觉/交互（下拉宽度、勾选框对齐）
未经人眼确认。这一条如实标出，供控制方判断是否需要补一次人工点击。

## 3. 改了哪些文件

- `frontend/src/utils/dict.ts`（改，+7 行）
- `frontend/src/api/permissions.ts`（改，1 行）
- `frontend/src/views/Permissions.vue`（改，约 +55/-15 行）
- 后端**未动**。工作区只剩两个与本次无关的 untracked 文件
  （`backup/privacy_platform_20260928_pre_kb_fix.sql.gz`、`docs/kb-vendor-attribution-audit-2026-09-28.md`），
  未纳入本次提交。

## 4. 自审发现（按任务给定的四条检查项逐条读 diff）

- **`dict.ts` 的配色映射有没有被误用成词表**：没有。`PLATFORM` 只有 3 个英文平台码，
  是纯颜色映射（同 `PERMISSION_TYPE` 的定位），注释也按既有口径写清了「取值由后端给」。
  两处下拉的 `<el-option>` 一律 `v-for="p in meta.platforms"`，页面里**没有**硬编码
  `'ANDROID' | 'IOS' | 'HARMONYOS'` 作为选项。唯一的字面量是 `filters`/`form` 的**默认值**
  `'ANDROID'`——与后端 `PermissionCreate.platform` 的默认值一致，是「新建时的初值」而非候选清单。
  另：`PERMISSION_TYPE` 的 8 值映射保持原样没动，也没被当成筛选选项（筛选仍是 `meta.permission_types`）。
- **勾选框 `undefined` 语义有没有被改错**：没有。仍是 `applicable: filters.applicable || undefined`，
  勾选 → `true`、取消 → `undefined`（不筛），**没有**送 `false`。已在代码旁加注释钉住三态含义，
  免得后人「顺手」改成 `filters.applicable ?? undefined`（那会让取消勾选变成 false/只看不可达）。
- **平台切换有没有清掉不兼容的类型选择**：筛选栏清了（`onPlatformChange` 置 `filters.permission_type = ''`
  并重载词表）；`resetFilters` 同样清；弹窗的平台切换**不清** `form.permission_type`——见下方遗留项 1。
- **完整性/YAGNI**：`Platforms` 只在 `meta` 里存了一份，两处下拉共用；没有为平台单建字典或 composable；
  `PermissionItem` 只加了后端确实返回的 `platform` 字段；没顺手改任何布局/样式/文案。

## 5. 遗留顾虑

1. **弹窗内切平台不会清 `form.permission_type`**（brief 的模板里只有 `@change="loadMeta"`，我按 verbatim 保留）。
   用户先选了类型、再把弹窗平台从 Android 改成 iOS，那个 `危险权限` 会留在表单里，提交时被后端
   400 挡下（`IOS 的 permission_type 只能是：用法描述键`）——是**可见、可恢复**的报错，不是静默写错数据。
   若要修，把 `@change` 换成一个小 handler，同时清 `form.permission_type` 并 `loadMeta(form.platform)`。
   我判断这属于「brief 显然没写」的次要路径，没有擅自加，交控制方定。
2. **筛选栏与弹窗共用一份 `meta`**：编辑态属于 brief 的设计。副作用是——筛选栏为「全部平台」时打开创建弹窗、
   在里面切平台，会把筛选栏的类型下拉也一起换成该平台的词表（关掉弹窗不还原）。不崩、不出错数据，
   但「全部平台」+ 某个平台专属类型的组合会查不到东西。同上，未擅自修。
3. **iOS / 鸿蒙的 `category` 全为 NULL**（实测：ANDROID 1036 行里 103 行有 category；
   HARMONYOS 783、IOS 57 行**全为 NULL**）。因此选中鸿蒙或 iOS 时，「分类」下拉是空的。
   这是导入侧的数据缺口（非本次前端引入、也非编造得出来），但会让用户以为下拉坏了。
   若要补，应在导入/解析器侧给非 Android 行填 `category`，属后端任务。
4. **页面副标题仍是「Android 平台权限与三方声明权限的合规档案」**，现在库里已有三平台，这句话失真。
   文案属用户自己的版式范围（memory: UI 由用户负责），我按「不擅自发挥」没有改，仅在此标注。
5. **默认只看可申请后首屏只有 308 / 1876 行**（brief 明确要求，spec §6）。勾选框可见且带文案，
   但若用户不知道有这个开关，容易误以为数据丢了。属交互设计，非缺陷。
6. `loadMeta` 的 3 处偏离见 §1 表格；其中 #1 是本任务里最需要控制方裁决的一处，因为它改动了
   brief 给出的函数签名（虽然所有调用点逐字未变）。

---

# 修复循环第 1 轮：Ruling —— 弹窗独立一份词表

日期：2026-09-28　commit：`455189b` fix(ui): 弹窗独立一份词表，与筛选栏分开，避免平台错配

## F1. 改了什么

按裁决实现「两处下拉各读各的」：

- 新增 `dialogMeta = reactive({ permission_types: [], categories: [] })`；
- 新增 `loadDialogMeta(platform)` → `GET /permissions/meta?platform=…` 写进 `dialogMeta`；
- 弹窗的**类型**下拉（原 `meta.permission_types`）与**分类**下拉（原 `meta.categories`）改读 `dialogMeta`；
  筛选栏的四个下拉继续读 `meta`；
- `openCreate()` 改为 async：`resetForm()` 后 `await loadDialogMeta(form.platform)`（即 `'ANDROID'`）；
- `openEdit(row)`：`Object.assign(form, …)` 之后 `await loadDialogMeta(form.platform)`
  —— 顺带修好了「编辑 iOS 行时类型下拉列的是筛选栏平台的词表」；
- 弹窗平台 `@change` 由 `loadMeta` 换成新增的 `onFormPlatformChange()`：
  `form.permission_type = ''` + `loadDialogMeta(form.platform)`（Minor 1）；
- `onPlatformChange()` 增清 `filters.category = ''`（Minor 2）；
- **`loadMeta(platform?)` 回退为无参 `loadMeta()`** —— 见 F4，这是本轮唯一需要确认的自选动作。

未改：弹窗「平台」下拉的候选项仍读 `meta.platforms`（平台清单本身与平台无关，后端对任何
`platform` 都返回同一个 `list(PLATFORMS)`），弹窗「风险等级」仍读 `meta.risk_levels`
（`RISK_LEVELS` 是常量，与平台无关）。两处都不存在错配。

## F2. 验证

- 类型检查：`npx vue-tsc -b` → 退出码 0、无输出。
- 构建：`npm run build` → `✓ built in 16.67s`，`dist/assets/Permissions-B7JW1OJP.js`（11.32 kB）。
- dev server 转换：`/src/views/Permissions.vue` HTTP 200（70 683 B），
  `dialogMeta`/`loadDialogMeta`/`onFormPlatformChange` 标记齐全；
  `grep 'loadMeta(platform\|@change="loadMeta"'` → 0 命中，旧绑定无残留。
- **静态核对哪一侧读哪一份词表**（`grep -n "meta\.\|dialogMeta\." src/views/Permissions.vue`）：
  - 筛选栏（模板 12/16/19/22 行）：`meta.platforms`/`meta.categories`/`meta.permission_types`/`meta.risk_levels`；
  - 弹窗（模板 100/105 行）：`dialogMeta.categories`/`dialogMeta.permission_types`；
  - 写入侧（脚本 201-204 / 210-211 行）：`loadMeta` 只写 `meta`，`loadDialogMeta` 只写 `dialogMeta`，
    两者无交叉赋值。
- **真实 HTTP 复现（经 5173 的 vite proxy，即浏览器走的那条路；token 现签）**，
  按 UI 动作逐个回放页面会发的请求：

  | 动作 | 请求 | 响应 |
  |---|---|---|
  | A 筛选栏选「鸿蒙」 | `meta?platform=HARMONYOS` | types `[normal, system_basic, system_core]`，categories 0 |
  | A 同上 | `list?platform=HARMONYOS&applicable=true` | total 115 |
  | **B 此时点「新建」** | **`meta?platform=ANDROID`**（`openCreate` → `loadDialogMeta('ANDROID')`） | **types = Android 的 8 个**（危险权限/危险权限（受限）/普通权限/签名权限/特殊权限/已弃用权限/三方声明权限/未标注），categories 41 |
  | C 弹窗内平台切 iOS | `meta?platform=IOS` | types `['用法描述键']`，categories 0 |
  | D 编辑真实 iOS 行 #2194 | `GET /permissions/2194` → `platform='IOS'`，再 `meta?platform=IOS` | types `['用法描述键']` |

  B 行是本轮的核心证据：**筛选栏持有鸿蒙词表的同时，弹窗请求到的是 Android 的 8 个取值**，
  两边是两次独立请求、两份独立 state，错配在构造上已不存在。
  （修复前的实际后果即审查所述：弹窗列鸿蒙的 3 个取值，提交被
  `validate_permission_type('ANDROID', …)` 挡成 400。）
- **各平台 category 取值实测**（照实报）：`ANDROID` 41 个（`下载`、`传感器与健康`、`位置信息`…）；
  `IOS` **0 个**；`HARMONYOS` **0 个**。库内计数：ANDROID 1036 行中 103 行有 category，
  HARMONYOS 783 / IOS 57 **全为 NULL**。即 iOS/鸿蒙 的分类下拉为空是**数据事实**，不是本次前端引入的缺陷。
  这也正是 Minor 2 要清 `filters.category` 的原因：Android 选「位置信息」→ 切鸿蒙，若不清就是
  「下拉已空 + 隐藏筛选值仍在」→ 0 行且原因不可见。
- 后端回归：`pytest tests/ -q` → **315 passed**（本轮仍未动后端）。

## F3. 自审（读本轮 diff）

- **两侧词表有没有真正分开**：分开了。两份 reactive 对象、两个 loader，各自只写自己那份
  （脚本 201-204 vs 210-211），模板里各读各的（见 F2 静态核对）。没有任何一处把 `dialogMeta`
  写进 `meta` 或反向。
- **`form.permission_type` 的清理**：弹窗内换平台会清（`onFormPlatformChange`）；
  筛选栏换平台会清（`onPlatformChange`）。**`form.category` 弹窗内换平台时不清**——
  与裁决给的范围一致，且弹窗分类是 `allow-create` 的自由输入、后端不校验，
  残留值不会造成 400，只会把上个平台的分类名带过去。如需一并清，一行即可。
- **勾选框语义未被碰到**：`applicable: filters.applicable || undefined` 与三态注释原样保留，
  本轮 diff 未触及 `loadData`。
- **YAGNI**：没有再引入第三份 state、没有抽象出「按平台取词表」的工厂；
  `dialogMeta` 只装弹窗真正会渲染的两个下拉（platforms/risk_levels 与平台无关，继续共用）。

## F4. 本轮唯一需要确认的自选动作：`loadMeta(platform?)` 回退为无参

上一轮为了救 brief 的 `@change="loadMeta"` 才给 `loadMeta` 加了可选参数。本轮弹窗改挂
`onFormPlatformChange` + `loadDialogMeta` 之后，**没有任何调用点再传平台给 `loadMeta`**
（`onPlatformChange`/`resetFilters`/`handleSubmit` 三处都是无参调用），参数变成死参数，
所以我把签名改回 brief 原文的无参形态、内部直接读 `filters.platform`。

这不是推翻上轮的修补，而是它的**职责已被 `loadDialogMeta` 接管**之后的收尾。
若控制方希望保留该参数（例如为将来可能的复用），一行即可加回，行为无差别。

## F5. 本轮遗留

1. **快速连点弹窗平台下拉存在响应竞争**：`loadDialogMeta` 未做请求序号/取消，
   极端情况下先发后到的响应会覆盖后发的，词表短暂与选中平台不符。
   这与页面既有的 `loadMeta`/`loadData` 是同一模式（非本轮引入的新类问题），
   如需修应统一加序号守卫，属独立改动，本轮未做。
2. 上一轮遗留 §5 的 2（共用 meta 的副作用）、3（非 Android 分类为 NULL）、4（副标题）、5（默认只看可申请）
   状态更新：**§5-2 已被本轮修复消除**（不再共用）；3/4/5 按裁决继续保留，不在本轮范围。
3. 上一轮 §5-1（弹窗内切平台不清类型）**已修**（Minor 1）；筛选栏分类未清 **已修**（Minor 2）。
