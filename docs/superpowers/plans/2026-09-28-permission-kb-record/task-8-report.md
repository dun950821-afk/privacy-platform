# Task 8 报告：API 加平台与可达性维度

日期：2026-09-28　分支：main　commit：`0ce3e49` feat(kb): 权限接口增加平台与可达性筛选

## 1. 实现了什么

| 交付 | 说明 |
|---|---|
| `GET /permissions?platform=&applicable=` | `platform` 走 SQL 过滤；`applicable=true` 在 Python 侧按 `is_applicable` 过滤后再分页 |
| 列表项 `platform` | `_brief`/`_detail` 都带出 `platform`（`_detail` 复用 `_brief`，自动带上） |
| `GET /permissions/meta?platform=` | 给平台则只回该平台词表；不传回三平台并集；新增 `platforms` 键 |
| `PermissionCreate.platform` | 默认 `"ANDROID"`（`PermissionUpdate` 未动——平台是行的身份，建后不可改） |
| **词表校验收敛到一处** | 删掉本文件里那份重复的 8 值 `PERMISSION_TYPES` 与旧 `_check_type`；`_check_type(platform, value)` 转调 taxonomy 的 `validate_permission_type` |
| 编辑态按**行自身**的 platform 校验 | `_check_type(p.platform, req.permission_type)` |

`/meta` 落地的形状（实测）：

```
?platform=ANDROID  -> 8 个（危险权限…未标注）
?platform=IOS      -> ['用法描述键']
?platform=HARMONYOS-> ['normal','system_basic','system_core']
不传 platform      -> 12 个（并集，顺序去重）
```

## 2. 测了什么与结果

- 聚焦：`cd backend && /tmp/venv/bin/python -m pytest tests/test_permission_platform_api.py -v` → **8 passed**
- 回归：`cd backend && /tmp/venv/bin/python -m pytest tests/ -q` → **314 passed**（基线 306 + 新增 8），34 warnings（全是仓库既有）

## 3. TDD 证据

### RED（brief 的 6 条 + 我加的 2 条，在改动前的代码上）

命令与输出（为拿到逐条的确切信息，用 `git checkout HEAD~1 -- app/api/v1/permissions.py app/schemas/__init__.py`
临时退回改动前的源码后跑，跑完 `git checkout HEAD --` 复原，`git diff --stat HEAD -- app/` 为空）：

```
$ /tmp/venv/bin/python -m pytest tests/test_permission_platform_api.py -v
test_meta_returns_platform_specific_vocabulary FAILED
test_meta_rejects_unknown_platform FAILED
test_list_filters_by_platform FAILED
test_applicable_filter_excludes_signature_level FAILED
test_create_rejects_type_from_another_platform FAILED
test_update_validates_against_the_row_own_platform FAILED
test_create_defaults_to_android FAILED
test_ios_row_with_empty_capability_round_trips FAILED
```

为什么**预期**会失败（逐条对上失败点）：

| 用例 | 退化的断言 | 为什么改前必然挂 |
|---|---|---|
| `test_meta_returns_platform_specific_vocabulary` | `assert ios["permission_types"] == ["用法描述键"]` → 实得 `['危险权限','危险权限（受限）',…]` | `/meta` 根本没有 `platform` 参数，忽略后返回那份写死的 8 值 Android 词表 |
| `test_meta_rejects_unknown_platform`（新增） | `assert 200 == 400` | 同样没有 `platform` 参数，`?platform=FOO` 被忽略后照常 200 |
| `test_list_filters_by_platform` | `assert ['…camera','…danger','…sig'] == ['…camera']` | 列表没有 `platform` 过滤，3 行全回 |
| `test_applicable_filter_excludes_signature_level` | `assert P+'sig' not in names` → 在其中 | 没有 `applicable` 参数，签名权限照样进版面 |
| `test_create_rejects_type_from_another_platform` | `assert 400` → 实得 200 | 建行时 `platform` 被忽略，`危险权限` 落在旧那份全局 8 值词表里，放行 |
| `test_update_validates_against_the_row_own_platform`（新增） | 同上（400 实得 200） | 编辑态用的是无平台的全局词表，IOS 行能改成 Android 取值 |
| `test_create_defaults_to_android` | `data["platform"]` KeyError | `_brief` 没有 `platform` 字段 |
| `test_ios_row_with_empty_capability_round_trips` | `assert 400 == 200` | `用法描述键` 不在那份写死的 Android 词表里，IOS 行根本建不出来 |

### GREEN

```
$ /tmp/venv/bin/python -m pytest tests/test_permission_platform_api.py -v
… 8 passed, 3 warnings in 4.74s

$ /tmp/venv/bin/python -m pytest tests/ -q
314 passed, 34 warnings in 16.26s
```

中间还有一步是既有测试的回归红：改完路由后跑全套得到
`1 failed, 311 passed`，唯一失败是 `test_permission_kb_api.py::test_meta_exposes_controlled_vocabulary`
（`assert len(permission_types) == 8` → 实得 12 = 8 Android + 3 鸿蒙 + 1 iOS），
与 Ruling C 的预判完全一致，改测试后转绿。

### 既有测试的两处同步修正（Ruling C 的必做项）

1. `test_meta_exposes_controlled_vocabulary`：**加**了 `params={"platform": "ANDROID"}` 再断言 8 个。
   这不是放松而是收紧——不指定平台时那个 8 量的其实是 12 个的并集，断言已经失去意义；
   同时保留了「危险权限」「三方声明权限」两个具体取值断言。
2. `test_update_rejects_invalid_permission_type`：**未改**，仍成立（改后重跑通过）。
   该行建时不传 platform → ANDROID，写「普通/受限 API权限」仍被 taxonomy 拒。
   另外把该文件模块 docstring 里「只允许归一后的 8 个取值」改为「按平台各一套」——原文已失真。

## 4. 改了哪些文件

- `backend/app/api/v1/permissions.py`（改）：删 `PERMISSION_TYPES` 常量、`_check_type` 带 platform、
  导入 taxonomy 三件套、`_brief` 加 platform、`/meta` 加 platform、列表加 platform/applicable、创建/编辑接平台
- `backend/app/schemas/__init__.py`（改）：`PermissionCreate` 加 `platform: str = "ANDROID"`
- `backend/tests/test_permission_platform_api.py`（新）：brief 的 6 条 + 我加的 2 条
- `backend/tests/test_permission_kb_api.py`（改）：meta 断言指定平台 + 模块 docstring

## 5. 自审发现

- **brief 的 `/meta` 有个 500**：`PERMISSION_TYPES_BY_PLATFORM.get(platform)` 对未知平台返回 `None`，
  `list(dict.fromkeys(None))` 抛 TypeError。实测 `?platform=FOO` → **HTTP 500**。
  我**偏离 brief 加了 2 行守卫**，改为 400（`detail` 复用 taxonomy 的 `PLATFORMS` 文案）：
  未知平台既不能 500，也不能退回并集——退回并集会让前端拿 Android 的词表去校验 iOS 的输入，
  比报错更坏。同新增 `test_meta_rejects_unknown_platform` 钉住。这是本任务唯一一处偏离 brief 的实现代码，可一行删掉。
- **新增了 `test_update_validates_against_the_row_own_platform`**（brief 之外）：
  brief 的用例集**没有任何一条**能在「编辑态用了全局/错平台词表」时变红——
  `test_update_rejects_invalid_permission_type` 用的是 ANDROID 行 + 「普通/受限 API权限」，
  换成任意词表都会被拒，测不出平台维度。我用变异验证过这条新测试确实有鉴别力：
  把 `_check_type(p.platform, …)` 改成 `_check_type("ANDROID", …)` → 该条 FAILED，其余 7 条仍 PASSED（已复原，`diff` 确认与复原前一致）。
- 两处词表已收敛：`grep -rn PERMISSION_TYPES` 确认 API 文件里那份常量及其全部引用已消失，
  全仓只剩 taxonomy 的一处定义 + 测试的导入。
- `git status` 干净：改动前有一次 `sed` 变异测试，已复原并用 `diff` 逐字节确认；
  DB 里 `permission_name like 'test.%'` 残留 0 行，三平台计数仍是 1036/783/57 未被污染。
- 手测（重启后，服务无 `--reload`）：日志里 `POST /auth/login 200`、`meta?platform=FOO 400`、
  `list?platform=IOS&applicable=true 200`、`list?platform=ANDROID&applicable=true 200`，**无一条 500**；
  日志里唯一的 Traceback 是仓库既有的 passlib/`bcrypt.__about__` 告警（trapped）。
- 实测总量对得上：ANDROID 1036（可达 136）、HARMONYOS 783（可达 115）、IOS 57（可达 57），
  1036+783+57 = 1876 = 不带 platform 的 `total`；HARMONYOS 分页 50+50+15 = 115 与 `total` 一致。
- 编辑态平台身份实测：IOS 行 PUT `危险权限` → `400 {"detail":"IOS 的 permission_type 只能是：用法描述键"}`，
  PUT `用法描述键` → 200；建行写错平台取值同样 400；未知平台建行 → 400。

## 6. 遗留顾虑

1. **`applicable=false` 等同于不筛选**（brief 的 `if applicable:` 写法）。语义上「只看不可达」
   做不到，传 `applicable=false` 会静默退化成全量。brief 如此、我也没加测试；
   若前端 Task 9 要展示「不可达」那一档，这里需要改成三态（None/true/false）。
2. **列表的 `platform` 参数不校验**：`?platform=FOO` 返回空列表而非 400，
   与其它筛选参数（`category`/`risk_level` 拼错也只是空结果）一致。
   但叠加 `applicable=true` 时，同样是 taxonomy 的 `is_applicable` 对未知平台返回 `False` 静默失败
   （T2 的 deferred 项）。我按「筛选参数宽松、词表接口严格」处理，没有扩大 400 的范围。
3. `applicable=true` 时把符合前置筛选的行**全量拉进内存**再分页（brief 明说千级可接受）。
   Android 全库 1036 行时无所谓；若某天单平台上万行，这里会变成全表加载。
4. `/meta` 的分类列表由 `distinct + order_by`（SQL）改成 Python `sorted(set(...))`——brief 的写法。
   结果等价；中文排序依赖 Python 的码点序，与 PostgreSQL 的 collation 排序在极端情况下可能不同，
   我没找到会因此出问题的调用方（前端只当候选值渲染）。

---

# 修复循环第 1 轮：Ruling O —— `applicable` 改三态

日期：2026-09-28　commit：`b252b3b` fix(kb): applicable 改三态，false = 只看不可达

## 1. 改了什么

审查认定 Important（且是 brief 原文即计划原文的错误）：`if applicable:` 让
`applicable=false` 与「不传」走同一分支，调用方明确要「不可达」那一档却拿到**全量**——
不报错、也没提示，是个不报错的错答案。

按 Ruling O 改为三态，并把签名从 `applicable: bool = None` 改为 `applicable: bool | None = None`：

```python
    if applicable is None:
        total = q.count()
        items = q.order_by(KBPermission.permission_name) \
                 .offset((page - 1) * page_size).limit(page_size).all()
    else:
        # **三态**：true = 只看可达，false = 只看**不可达**，不传 = 不筛。
        # 不能写成 `if applicable:`——那样 false 会静默退化成「不筛选」…
        rows = [r for r in q.order_by(KBPermission.permission_name).all()
                if is_applicable(r.platform, r.permission_type, r.grant_mode) is applicable]
        total = len(rows)
        items = rows[(page - 1) * page_size: page * page_size]
```

新增测试 `test_applicable_filter_is_tri_state`（照裁决给的原文）。**只改这一处**，
未知 `platform` 返回空列表那条按 Minor 记 ledger，本轮未动。

## 2. 变异验证（裁决要求）

变异体取 **HEAD 里 pre-Ruling-O 的原文**（即 `git checkout HEAD -- app/api/v1/permissions.py`；
该文件当时唯一未提交的改动就是本轮的 Ruling O 修改，所以这条命令恰好只回退这一处）：

```
$ git checkout HEAD -- app/api/v1/permissions.py
$ sed -n '124,128p' app/api/v1/permissions.py
    if applicable:
        # 可达性不能只在 SQL 里判：鸿蒙还要看 grant_mode，SQL 里拼不干净。
        # 取全量在 Python 侧过滤，分页放在过滤之后（数据量在千级，可以接受）。
        rows = [r for r in q.order_by(KBPermission.permission_name).all()
                if is_applicable(r.platform, r.permission_type, r.grant_mode)]

$ /tmp/venv/bin/python -m pytest tests/test_permission_platform_api.py -v
test_meta_returns_platform_specific_vocabulary PASSED        [ 11%]
test_meta_rejects_unknown_platform PASSED                    [ 22%]
test_list_filters_by_platform PASSED                         [ 33%]
test_applicable_filter_excludes_signature_level PASSED       [ 44%]
test_applicable_filter_is_tri_state FAILED                   [ 55%]
test_create_rejects_type_from_another_platform PASSED        [ 66%]
test_update_validates_against_the_row_own_platform PASSED    [ 77%]
test_create_defaults_to_android PASSED                       [ 88%]
test_ios_row_with_empty_capability_round_trips PASSED        [100%]

        assert [i["permission_name"] for i in only_reachable] == [P + "danger"]
>       assert [i["permission_name"] for i in only_unreachable] == [P + "sig"]
E       AssertionError: assert ['test.platfo...form.api.sig'] == ['test.platform.api.sig']
E         At index 0 diff: 'test.platform.api.danger' != 'test.platform.api.sig'
E         Left contains one more item: 'test.platform.api.sig'
E       Full diff:
E         [
E       +     'test.platform.api.danger',
E             'test.platform.api.sig',
E         ]
tests/test_permission_platform_api.py:84: AssertionError
```

失败症状与预期**逐字对上**：`applicable=false` 该只回 `…sig`，实得 `[danger, sig]` 两行——
正是「false 退化成不筛选」的那个错答案。

**关键旁证**：同一轮里 `test_applicable_filter_excludes_signature_level`（brief 原有）**仍是绿的**，
证明原有用例集测不到这处——新测试是必要的，不是重复覆盖。

复原：`/bin/cp -f /tmp/t8_final.py app/api/v1/permissions.py`，随后
`diff /tmp/t8_final.py app/api/v1/permissions.py` → 空（IDENTICAL），再跑 9 passed。

## 3. 测试结果

```
$ /tmp/venv/bin/python -m pytest tests/test_permission_platform_api.py -v
9 passed, 3 warnings in 5.12s          # 8 → 9

$ /tmp/venv/bin/python -m pytest tests/ -q
315 passed, 34 warnings in 16.27s      # 314 → 315
```

## 4. 重启后手测（服务无 `--reload`，已重启）

```
platform    不传     可达    不可达
ANDROID     1036     136     900
HARMONYOS    783     115     668
IOS           57      57       0
```

三平台都满足 `可达 + 不可达 == 不传`（1036/783/57 各自对得上），IOS 不可达为 0
（用法描述键本就全可达）——三态确实切出了两个**互补**的桶，而不是让 false 落回全量。

不可达那档的内容也认得出来（Android 不可达 900 条的前 200 条类型分布）：
`签名权限 189 / 特殊权限 6 / 已弃用权限 4 / 三方声明权限 1`——正是 brief 里
「签名/系统级默认不进版面」所指的那批。日志 `grep -c " 500 "` = 0，无新错误。

（注：手测时 `page_size=1000` 被既有上限截到 200，故 `total 900 / n 200`，非缺陷。）

## 5. 自审

- 本轮改动只落在 `applicable` 这一处 + 一条测试，`git diff --stat`：
  2 files changed, 31 insertions(+), 7 deletions(-)。
- `is_applicable(...) is applicable` 里的 `is` 比的是 `True`/`False` 单例，
  `is_applicable` 三个分支都返回真布尔字面量（`return (…) in _ANDROID_APPLICABLE` 等），
  不存在返回非布尔真值而让 `is` 判错的情况；`applicable is None` 已在外层把 None 挡住。
- 变异体是 HEAD 的原文而非我手搓的近似版本：第一版脚本用字符串替换拼出的变异体形态不干净
  （把两个分支弄成了错位的样子，虽也能变红但说服力弱），已弃用，改用 git 检出，变异体即
  上一提交的真实代码。
- 本轮新测试与 brief 原有的 `test_applicable_filter_excludes_signature_level` 在
  `applicable=true` 上是重叠的（都断言 danger 在、sig 不在）；保留原有那条不动——
  任务是修 Important，不是精简 brief 的用例。重叠不算镀金，删了反而偏离 brief。
- 报告第 6 节遗留顾虑 1 就此关闭；顾虑 2（列表未知 platform 返回空列表）按 Minor 保留，本轮未动。
