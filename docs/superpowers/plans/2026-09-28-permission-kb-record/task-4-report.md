# Task 4 报告：鸿蒙解析器

**Status:** DONE
**Commit:** `3e6f413` feat(kb): 鸿蒙权限文档解析器
**测试:** `tests/` 全量 290 passed（基线 287 → 目标 290，达成）

## 实现了什么

在 `backend/app/services/permission_sources.py` **追加**（未改动 Android 部分）
`parse_harmonyos_doc(md_text: str) -> list[dict]`：

- 用 `_HARMONY_SECTION`（`^##\s+(ohos\.permission\.[A-Za-z0-9_]+)\s*$`，`re.M`）切小节。
- 抽三个结构化字段：`**权限级别**`、`**授权方式**`、`**起始版本**`。
- **权限级别与授权方式分两个正交字段**：级别（`normal` / `system_basic` /
  `system_core`）进 `permission_type`，`user_grant` / `system_grant` 进 `grant_mode`。
- `capability` 取正文到第一个结构化字段为止（`body.split("**权限级别**")[0].strip()`），
  空则 `None`。
- `official_reference` 拼华为开发者文档 URL；`raw_data` 带
  `platform_source: "openharmony_docs"` 与 `since_api`。
- **缺「权限级别」字段的小节直接跳过**（`if not level_m: continue`），不编造级别。

行形状严格保持六键契约 `permission_name` / `permission_type` / `capability` /
`grant_mode` / `official_reference` / `raw_data`——已用脚本对解析结果逐个断言
键集合相等，无漂移、无多余键。

## 测了什么与结果

新增 fixture `backend/tests/fixtures/permission_sources/harmonyos_sample.md`
（3 个小节：两条完整权限 + 一条无结构化字段的干扰项），
追加 3 条用例到 `test_permission_sources.py` 末尾（**未改动 Task 3 的 6 条 Android 用例**）：

| 用例 | 断言 | 结果 |
|---|---|---|
| `test_harmonyos_parse_extracts_name_and_level` | 只出 2 条、名字精确匹配、级别为 `normal` | PASSED |
| `test_harmonyos_parse_captures_description_and_grant_mode` | `capability` 以描述开头、`grant_mode` 含 `user_grant`、`since_api == "10"` | PASSED |
| `test_harmonyos_parse_skips_section_without_fields` | 无字段小节不出现 | PASSED |

聚焦：`3 passed, 6 deselected`。全量：`290 passed, 34 warnings in 12.34s`（warnings 为既有的 SQLAlchemy LegacyAPIWarning，与本次改动无关）。

## TDD 证据

**RED** — `cd backend && /tmp/venv/bin/python -m pytest tests/test_permission_sources.py -v -k harmonyos`

```
ImportError while importing test module '.../tests/test_permission_sources.py'.
tests/test_permission_sources.py:69: in <module>
    from app.services.permission_sources import parse_harmonyos_doc
E   ImportError: cannot import name 'parse_harmonyos_doc' from 'app.services.permission_sources'
=========================== short test summary info ============================
ERROR tests/test_permission_sources.py
!!!!!!!!!!!!!!!!!!!! Interrupted: 1 error during collection !!!!!!!!!!!!!!!!!!!!
1 error in 0.10s
```

预期失败：实现函数尚不存在，brief Step 3 预期即为该 ImportError，实测逐字吻合。

**GREEN** — 同一命令：

```
tests/test_permission_sources.py::test_harmonyos_parse_extracts_name_and_level PASSED
tests/test_permission_sources.py::test_harmonyos_parse_captures_description_and_grant_mode PASSED
tests/test_permission_sources.py::test_harmonyos_parse_skips_section_without_fields PASSED
======================== 3 passed, 6 deselected in 0.02s ========================
```

**变异测试（额外做的）**：为确认「跳过」这条测试是**承重**的，把守卫
`if not level_m: continue` 换成编造默认值 `... if level_m else "normal"`，重跑：

```
FAILED tests/test_permission_sources.py::test_harmonyos_parse_extracts_name_and_level
FAILED tests/test_permission_sources.py::test_harmonyos_parse_skips_section_without_fields
2 failed, 1 passed, 6 deselected
```

→ 若实现退化成「给无字段小节编个级别」，测试 1、3 会立刻变红。变异已完整回滚
（回滚后 `git diff HEAD` 为空，提交内容含守卫，无 `else "normal"` 残留）。

## 改了哪些文件

- `backend/app/services/permission_sources.py`（+39，纯追加，Android 解析器零改动）
- `backend/tests/fixtures/permission_sources/harmonyos_sample.md`（新增，29 行）
- `backend/tests/test_permission_sources.py`（+23，纯追加）

未纳入提交：仓库根已存在的无关未跟踪文件 `backup/privacy_platform_20260928_pre_kb_fix.sql.gz`。
`app/permission_sources.py` 顶部的 `json` / `re` / `ET` 三行原样保留，`re` 本次投入使用，
未重复 import（遵守任务说明中的既有实现细节）。

## 自审发现

1. **测试文件末尾有一条模块级 import**（`from app.services.permission_sources import parse_harmonyos_doc`
   紧跟 Android 用例之后）。这是 brief 逐字给出的写法，且约束要求「只在文件末尾追加、
   不改动 6 条 Android 用例」，故保留原样。仓库无 ruff/flake8/pyproject 配置
   （已确认：根与 `backend/` 下均无 lint 配置），不会有 E402 类门禁报错。
   纯属观感问题，若审查方偏好可后续合并到文件头第 4 行 import。
2. **`desc` 的切分点硬编码字符串 `"**权限级别**"`，而级别字段匹配用的是正则**
   （容忍 `：`/`:` 与空白）。二者对文档格式的容忍度不一致：若真实文档写成
   `**权限级别:**`（冒号含在粗体内），正则仍能匹配到级别，但 `desc` 会把整行
   `**权限级别:** xxx` 也带进 `capability`。当前 fixture 与已知的 OpenHarmony
   文档格式均为 `**权限级别**：`，未触发；属 brief 逐字实现，未擅自改动。
3. 命名与既有 `parse_android_manifest` 对齐（`parse_<platform>_<source>`），
   模块级正则以 `_HARMONY_` 前缀区分，`_ANDROID_*` 未被污染。无 YAGNI 违规：
   未加抽象层、未加未用参数。

## 遗留顾虑（给后续任务）

- **小节边界的相邻性假设**：body 一直延伸到下一个 `## ohos.permission.X`。若真实文档
  在两个权限小节之间插入了一个**非权限的 `##` 小节**（例如「相关权限」「说明」），
  该小节会被吞进前一个权限的 body；此时若其中恰好出现 `**权限级别**` 字样，
  会被 `.search()` 误归给前一个权限。Task 7 抓真实文档实跑导入时应核对条数，
  确认没有这类串味。当前 fixture 未覆盖该形态。
- `permission_type` 只做原样透传，**未做受控词表校验**（brief 未要求）。
  若真实文档出现 `system_basic` 以外的写法或拼写变体，会带着原值入库。
  Task 2 的平台词表/归一化环节是否兜底，建议 Task 6 导入时确认。

---

# 修复循环第 1 轮（Ruling H / Ruling I）

**Status:** DONE
**Commit:** `818b6d4` fix(kb): 鸿蒙正文按下一个 ## 收口，official_reference 留空（Ruling H/I）
**测试:** 聚焦 `11 passed`（6 Android + 5 鸿蒙，与预期一致）；全量 **292 passed**（290 → 292，与预期一致）

## 改了什么

**Ruling H — 正文一律被下一个 `##` 收口。**

- 新增 `_HARMONY_ANY_HEADING = re.compile(r"^(?=##\s)", re.M)`（零宽前瞻，只切位置不切字符）。
- 循环从 `_HARMONY_SECTION.split(md_text)` 两两取对，改为遍历
  `_HARMONY_ANY_HEADING.split(md_text)` 得到的每个 block，再用
  `_HARMONY_SECTION.match(block)` 要求 block **必须以 `## ohos.permission.X` 开头**，
  否则跳过；`body = block[m.end():]`。这样非权限小节自成一块、不再被上一段吞掉，
  `level_m` 也就不可能冒领邻居的级别。
- `desc` 从字面量 `body.split("**权限级别**")[0]` 改为 `body[:level_m.start()]`，
  按级别正则**匹配到的位置**切，兼容 `**权限级别:**`（冒号在加粗内）——那正是我
  首轮自审第 2 条记下的容忍度不一致问题，本次一并消除。

**Ruling I — `official_reference` 一律 `None`。** 拼出来的
`https://developer.huawei.com/.../{name}` 是猜的，很可能 404；错误的官方链接比没有
更误导。溯源信息仍在 `raw_data.platform_source == "openharmony_docs"`。

**fixture** 末尾追加 `ohos.permission.NO_LEVEL_OF_ITS_OWN`（自己没有级别）+
非权限小节 `## 说明`（内含 `**权限级别**`：normal），构造出「借用邻居」的失效形态。
**测试** 追加 2 条。`_HARMONY_SECTION` 仍在使用（改为 `.match`），无死正则。

## 关键证据：新测试确实能抓到旧行为

按要求先把 `parse_harmonyos_doc` 换回 HEAD 版本（旧「只按 `## ohos.permission.X` 收口」
写法），再跑新测试。

命令：

```
cd backend && git show HEAD:backend/app/services/permission_sources.py > app/services/permission_sources.py
/tmp/venv/bin/python -m pytest tests/test_permission_sources.py -v -k "borrow or official_reference"
```

输出：

```
>       assert all(r["permission_name"] != "ohos.permission.NO_LEVEL_OF_ITS_OWN" for r in rows)
E       assert False
tests/test_permission_sources.py:100: AssertionError
>       assert all(r["official_reference"] is None for r in rows)
E       assert False
tests/test_permission_sources.py:107: AssertionError
=========================== short test summary info ============================
FAILED tests/test_permission_sources.py::test_harmonyos_parse_does_not_borrow_neighbour_level
FAILED tests/test_permission_sources.py::test_harmonyos_parse_leaves_official_reference_empty
2 failed, 1 passed, 8 deselected in 0.04s
```

两条新用例对旧实现都变红（供给变异覆盖 Ruling H 与 Ruling I 各自）。进一步把旧实现
**实际产出的那一行**打出来，确认审查描述的失效形态确实成立：

```
permission_type = 'normal'                       ← 借来的邻居级别
capability      = '这条自己没有权限级别字段。\n\n## 说明'   ← 连非权限小节标题一起吞
```

随后从备份恢复新实现（`grep` 确认 `_HARMONY_ANY_HEADING` / `level_m.start` /
`"official_reference": None` 三处均在位），再跑——

```
tests/test_permission_sources.py ... 11 passed in 0.02s
```

并以 `git diff HEAD` 为空确认换回来的文件与新实现逐字节一致，无旧代码或临时改写残留。

## 回归与边界

- `cd backend && /tmp/venv/bin/python -m pytest tests/test_permission_sources.py -v`
  → **11 passed**（6 Android + 5 鸿蒙，与预期一致）。
- `cd backend && /tmp/venv/bin/python -m pytest tests/ -q` → **292 passed, 34 warnings**
  （warnings 仍为既有 SQLAlchemy LegacyAPIWarning）。
- 六键契约复验：解析结果逐行断言键集合等于
  `{permission_name, permission_type, capability, grant_mode, official_reference, raw_data}`，无漂移。
- 边界：空串 → `[]`；纯说明文本（无权限小节）→ `[]`；文档以 `##` 开头时分块正常，
  空首块被 `.match` 挡掉。fixture 现产出恰好 2 行（两条真权限），
  `NO_LEVEL_OF_ITS_OWN` 与 `## 说明` 均未成行。

## 本轮自审发现

1. `git status` 里除我改的 3 个文件外，还有 `docs/superpowers/plans/...md` 的改动
   ——内容是本次 Ruling H/I 的计划同步（逐行核对过，**只涉及 Task 4**，未夹带其他
   任务的改动）。为免留下未提交的脏改动，一并纳入本提交。
2. 顺带确认 `_HARMONY_SECTION` 改成 `.match` 后，其 `\s*$` 在 `re.M` 下仍正确：
   `m.end()` 落在正文起始处，`capability` 取值未被标题行污染（测试 2 的
   `startswith("允许应用接入蓝牙")` 通过）。
3. 首轮自审把「非权限小节的相邻性」记为「给 Task 7 的提醒」，审查方正确地将它升级为
   **Important**：它不是保真度小瑕疵，而是会**产出编造数据**、直接违反 spec 硬约束，
   且 `if not level_m: continue` 那道闸确实挡不住（旧实现在此形态下正常产出该行）。
   我的定级偏轻，记下这个教训。
4. 首轮自审第 2 条（`desc` 字面量 vs 正则容忍度不一致）本轮已按 Ruling H 消除。
   首轮自审第 1 条（模块级 import）与第 3 条（命名）无变化、维持原状。

## 遗留顾虑（更新）

- 原第一条顾虑已由 Ruling H 修掉，fixture 现已覆盖该形态。
- 仍存（未改，非本任务范围）：`permission_type` 原样透传、未做受控词表校验。
  建议 Task 6 导入时确认 Task 2 的词表是否兜底。
- `official_reference` 现在恒为 `None`，若下游（Task 5/6/7 或 UI）假定该字段非空、
  把它直接渲染成链接或做非空断言，会踩空。**导入侧应对 None 做判空**，
  鸿蒙条目的溯源改读 `raw_data.platform_source`。建议相关任务留意。
