# Task 6 报告：导入服务（`import_platform`）

## 交付物

| 文件 | 说明 |
| --- | --- |
| `backend/app/services/permission_import.py`（新增，120 行） | `SOURCE_LABEL`、`import_platform(db, platform, rows) -> {"inserted","updated","skipped"}`，自行 commit，写 `privacy_kb.import_batch` 审计（`source_file="permission-import:<平台>"`） |
| `backend/tests/test_permission_import.py`（新增，161 行） | brief 里的 7 个测试（测试体逐字保留） |

接口与 brief 一致：`import_platform(db, platform, rows)`；平台非三者抛 `ValueError`；
一条 CRUD 都不走 API 层，只依赖 Task 2 的 `PLATFORMS` / `validate_permission_type`。

三条已裁定的设计都原样落地，**没有简化**：

1. 幂等靠内容比较（`existing` 与 `incoming` 逐字段 + `raw_data` 全等 → `skipped`），不看时间戳。
2. `incoming` 只收非 `None` 字段（`_UPDATABLE` 白名单），`None` 不覆盖既有值。
3. `validate_permission_type` 抛错 → `skipped += 1` 并 `continue`，不中止整批、不入库。

## TDD 证据

### RED（第 1 次：模块还不存在）

```
$ cd backend && /tmp/venv/bin/python -m pytest tests/test_permission_import.py -v
ERROR collecting tests/test_permission_import.py
E   ModuleNotFoundError: No module named 'app.services.permission_import'
=========================== short test summary info ============================
ERROR tests/test_permission_import.py
!!!!!!!!!!!!!!!!!!!! Interrupted: 1 error during collection !!!!!!!!!!!!!!!!!!!!
============================= 1 error in 0.22s ==============================
```

预期失败：`permission_import` 尚未创建，collect 阶段就 ImportError。

### RED（第 2 次：brief 里的实现**没有通过它自己的测试**）

先按 brief 逐字实现（含 `batch.finished_at` 在 `db.commit()` 前赋值的原顺序），得到：

```
FAILED tests/test_permission_import.py::test_import_updates_row_that_import_itself_wrote
>       assert result == {"inserted": 0, "updated": 1, "skipped": 0}
E       AssertionError: assert {'inserted': ..., 'skipped': 1} == {'inserted': ..., 'skipped': 0}
E         {'skipped': 1} != {'skipped': 0}
E         {'updated': 0} != {'updated': 1}
1 failed, 6 passed, 1 warning in 0.92s
```

**这是一个真实缺陷，不是测试写错。** 根因是时间戳的先后顺序被写反了：

- 行的 `updated_at` 不是「上次导入的时间」，而是**它自己这一批写盘的时刻**。INSERT 走
  Python 默认值 `default=utcnow`，该默认值在 `db.commit()` 触发的 flush 时才求值；UPDATE 走数据库触发器
  `trg_permission_updated_at`，取 `CURRENT_TIMESTAMP`（= 本事务开始时刻）。
- brief 的顺序是「循环里 add/setattr → 赋 `batch.finished_at` → commit」，所以 `finished_at`
  恒早于本批行的 `updated_at`。实测差值（`row.updated_at - batch.finished_at`）= **+4644 µs**。
- 于是下一轮把本导入自己写的行判成「上次导入之后被人改过」→ 永远 `skipped`，
  「第一版写错了就永远修不回来」——正是该测试要挡的事。
  注意这条路径**只被 test 3 覆盖**：test 1/7 在内容比较处就 `continue` 了，test 2 期望
  `skipped` 恰好与错误行为同向，所以 brief 里「Expected: 6 passed」刚好差的就是这一个。

修复（唯一改动，1 行 + 注释）：**先把本批的行落盘，再盖 `finished_at`**：

```python
    db.flush()                              # ← 新增：先落盘本批的行
    batch.status = "SUCCESS"
    batch.statistics = {...}
    batch.finished_at = datetime.now(timezone.utc)
    db.commit()
```

`db.flush()` 之后，本批行的 `updated_at`（Python 默认值 / 触发器取的事务开始时刻）严格早于
`finished_at`，基线语义才成立。没有引入新机制、没动三条裁定。

### GREEN

```
$ cd backend && /tmp/venv/bin/python -m pytest tests/test_permission_import.py -v
tests/test_permission_import.py::test_import_inserts_then_is_idempotent PASSED
tests/test_permission_import.py::test_import_does_not_overwrite_human_edited_row PASSED
tests/test_permission_import.py::test_import_updates_row_that_import_itself_wrote PASSED
tests/test_permission_import.py::test_import_writes_audit_batch_named_per_platform PASSED
tests/test_permission_import.py::test_import_skips_row_with_type_outside_platform_vocabulary PASSED
tests/test_permission_import.py::test_import_accepts_rows_with_empty_capability PASSED
tests/test_permission_import.py::test_import_does_not_blank_existing_value_with_none PASSED
========================= 7 passed, 1 warning in 0.74s =========================
```

连跑 5 次均 7 passed（时间戳逻辑，专门验抖动）。

全量回归（提交后重跑）：

```
$ cd backend && /tmp/venv/bin/python -m pytest tests/ -q
302 passed, 34 warnings in 12.50s
```

295 + 7 = 302，与预期条数一致。

### 测试之外的手工验尸（时间戳边界，测试没盖到的部分）

真实库里跑完整生命周期（脚本跑完即清理）：

```
1st  v1 -> {'inserted': 1, 'updated': 0, 'skipped': 0}
2nd  v2 -> {'inserted': 0, 'updated': 1, 'skipped': 0}   # 自己的行能更新
3rd  v2 -> {'inserted': 0, 'updated': 0, 'skipped': 1}   # 重跑无操作
4th  v3 -> {'inserted': 0, 'updated': 1, 'skipped': 0}   # 更新过的行**仍能**继续更新
5th  v3（人工改后）-> {'inserted': 0, 'updated': 0, 'skipped': 1}
value now = 人工改的
```

第 4 步是关键：修 `flush` 顺序后，被 UPDATE 过的行（`updated_at` 由触发器写成事务开始时刻）
在下一轮仍然可更新，不会出现「更新一次就锁死」。

## 自审发现

1. **brief 的测试清理是空转的**（已修）。原 `_cleanup` 里
   `delete ... where source_file like 'permission-import:test%'` 永远匹配不到任何行——
   导入写的标签就是 `permission-import:ANDROID` / `:IOS`，**没有** `:test` 段。7 个测试
   每个都自行 commit，于是每跑一次测试就往业务库的 `import_batch` 里漏 1 行，且这些行是
   真实平台标签，会污染后续导入的基线。改成 autouse fixture 用 **id 水位线**：
   记录测试开始前 `max(id)`，结束时只删 `id > floor` 的批次。前缀删是不可行的（漏自己 / 误伤真实
   审计记录两个方向都是错的），水位线两个方向都安全；顺便在 teardown 兜底再删一次 `test.import.perm.%`。
   7 个测试函数体逐字未动。实测：连跑 5 次聚焦 + 1 次全量后
   `source_file like 'permission-import:%'` 计数 = 0。
2. 顺手去掉 brief 实现里未使用的 `from sqlalchemy import text`，并把函数内
   `from datetime import datetime, timezone` 提到模块顶部（`grep datetime` 无同名遮蔽）。
   两处都是零行为改动。
3. 复核三条裁定确实各有测试承重：裁定 1 → test 1/7；裁定 2 → test 7；裁定 3 → test 5。
   没有测试是 mock 出来的：全部打真库、走真 ORM、由 SQL 断言最终状态（`select capability/...`），
   断言的是行为而非调用。
4. 复核业务库未被污染：`privacy_kb.permission` 仍是 **103 行 ANDROID**（无 `test.import.perm.%` /
   `dbg.%` 残留），`permission-import:%` 批次 0 行，`git status` 已跟踪文件干净。
5. `import_platform` 对首跑场景（库里已有 103 行 ANDROID 说明、无任何 `permission-import:ANDROID`
   批次 → `baseline is None`）的行为复核过：`baseline is None` 时内容比较仍生效，若 AOSP 行与人工行
   字段全等则 `skipped`，**只要有一处不同**才会走到覆盖分支——而 AOSP 的 `capability` 恒为 `None`，
   被裁定 2 的过滤器挡掉，不会进 `incoming`。这是我理解该保护能挡住 Task 7 首跑的原因。

## 遗留顾虑

1. **同一批内出现同名行会整批炸**（Task 7 的边界，已知并分派）。实测：
   一个 batch 里塞两条同名行 → `IntegrityError: duplicate key value violates unique constraint
   "permission_permission_name_key"`，且因为 `SessionLocal` 是 `autoflush=False`，
   循环里的 `db.query(...)` 看不到同一批尚未 flush 的 pending 行，第二条会再 INSERT 一次。
   后果比「这一行失败」重：整批回滚，连审计批次都不留。progress.md 第 18 行已经把
   「同名跨文件去重由 T7 负责」写明了，所以本任务**没有**擅自加去重/加 flush——但 Task 7
   的 `_load` 必须真的去重（鸿蒙 6 个文档文件拼接时尤其要看）。
2. 「人工改过」的判定依赖 `updated_at > 上次 finished_at`。触发器写的是 `CURRENT_TIMESTAMP`
   = **事务开始时刻**，所以一个长事务（如某个 API 会话先开了事务、之后才 UPDATE）里的编辑，
   其 `updated_at` 可能早于最近一次导入的基线而被判成「非人工」并覆盖。这是 brief 设计里既有
   的窗口（裁定 1 只把幂等改成内容比较，没动这条），我没有扩大改动面；若 Task 8 的编辑接口
   是「读-改-写」同一事务，需要留意。**未验尸**，仅从 DDL/触发器语义推断。
3. 词表外的 `permission_type` 与「名字为空」两类行的计数口径不同：前者 `skipped += 1`，
   后者（`name` 为空）直接 `continue` 不计数。brief 原样，且解析器不会产出无名行，未改动。
4. `raw_data` 不参与 `None` 过滤：调用方若整行不带 `raw_data` 键，既有行的 `raw_data` 会被清成 `{}`
   （只在内容比较发现差异、且非人工行时才发生）。三个解析器都必带 `raw_data`，实际打不到；未改动。
5. test 2 的「人工编辑」用例把 `updated_at` 显式写成 `now()`，与真实人工编辑路径（触发器）
   时序上等价但来源不同；真实路径由顾虑 2 描述。未加测试。

## Commit

`4f40220 feat(kb): 权限导入服务，幂等且不覆盖人工编辑`（2 files, +281）

---

# 修复循环第 1 轮（Ruling J / K）

审查结论 Spec ✅ / Approved，1 条 Important（同批同名静默回滚）+ 1 条 Minor（两个时钟混用），
两条我都认。改动落在 `561b71f`。

## ① Ruling J：同批同名守卫

`app/services/permission_import.py` 循环里加 `seen_names` 守卫（在 `name` 归一之后），
空名一并改为 `skipped += 1`（审计数字与 `len(rows)` 对得上）。新增测试
`test_import_survives_duplicate_name_in_one_batch`（放在
`test_import_does_not_blank_existing_value_with_none` 之前，逐字用裁决给的版本）。

**承重验证（临时移除守卫 → 变红 → 改回）**：

```
$ cd backend && /tmp/venv/bin/python -m pytest \
    tests/test_permission_import.py::test_import_survives_duplicate_name_in_one_batch -v
FAILED tests/test_permission_import.py::test_import_survives_duplicate_name_in_one_batch
E       psycopg2.errors.UniqueViolation: duplicate key value violates unique constraint
        "permission_permission_name_key"
app/services/permission_import.py:125: in import_platform        ← 炸弹在 commit/flush 里响
E       sqlalchemy.exc.IntegrityError: (psycopg2.errors.UniqueViolation) duplicate key value
        violates unique constraint "permission_permission_name_key"
E       sqlalchemy.exc.PendingRollbackError: This Session's transaction has been rolled back
        due to a previous exception during flush. Original exception was: (psycopg2...UniqueViolation)
1 failed, 1 warning in 0.96s
```

比审查描述的还难看一层：整批炸在 `import_platform` 内部的 commit 上，测试的清理语句随即撞
`PendingRollbackError`——**库里连审计批次都不留**（已查证：该测试跑红之后
`permission-import:%` 计数仍为 0），事后无从知道发生过。守卫改回后该测试转绿。
（顺带说明：这也证明 autouse fixture 里的 `db.rollback()` 是必要的——红那次正是它兜住了 session。）

## ② Ruling K：时钟——**按字面改会让 test 3 变红，因此做了两处而非一处**

字面照做（`batch.finished_at = db.execute(text("select now()")).scalar()`，保留 flush 在后）之后：

```
FAILED tests/test_permission_import.py::test_import_updates_row_that_import_itself_wrote
E   AssertionError: assert {'inserted': ..., 'skipped': 1} == {'inserted': ..., 'skipped': 0}
1 failed, 7 passed, 1 warning in 0.80s
```

根因（实测，非推断）：

```
row.updated_at  = 2026-09-28 19:32:33.460949+08:00   (ORM Python 默认值 / 应用时钟，flush 时求值)
batch.finish_at = 2026-09-28 19:32:33.446889+08:00   (DB now() = **事务开始**时刻)
row > batch ? True    delta_us = 14060
2nd v2 -> {'inserted': 0, 'updated': 0, 'skipped': 1}   期望 updated=1
```

`now()` 是**事务开始**时刻，比 `db.flush()` 还早；而 INSERT 路径的 `updated_at` 来自 ORM 的
Python 默认值（应用时钟，flush 时才求值）。只换 `finished_at` 不换行，等于把刚修好的顺序 bug
原样搬回来：本批自己的行比基线晚 14 ms → 下一轮判成「人工改过」。

**做法：让 INSERT 路径与 `finished_at` 用同一个 DB 时钟值**，一处取、两处用：

```python
    db_now = db.execute(text("select now()")).scalar()   # 本事务的 DB 时钟，事务内恒定
    ...
            KBPermission(..., updated_at=db_now)         # 不让 ORM 的 Python 默认值写它
    ...
    batch.finished_at = db_now
```

于是基线判定 `existing.updated_at > baseline` 全程只有数据库时钟、且对**本批自己写的行恒为相等**
（`>` 不成立 → 可更新），不再是「比大小」而是同一事务同一个 `now()` 值：

```
row.updated_at  = 2026-09-28 19:33:51.014703+08:00
batch.finished = 2026-09-28 19:33:51.014703+08:00
相等（单一 DB 时钟不变量）? True
```

这同时消掉了 Ruling K 担心的偏差窗口（不再有「应用时钟 vs 数据库时钟」的比较），并且把
「顺序承重」也去掉了。`db.flush()` 保留在盖章之前，理由改写成它在今天真正的职责：保证所有行
已落盘才标 SUCCESS，且写库错误在盖章前抛出——批次不会挂着一个骗人的 SUCCESS（这正是 ① 里
那个静默回滚的另一面）。Ruling K 要求把 flush 顺序连同理由写进注释，已写（注释里保留了
原始的 +4.6 ms 实测数字作为「为什么不能用 Python 默认值」的存档）。

**如果我判断错了，请驳回**：字面 `now()` + 不动 INSERT 路径，与 test 3 是不可兼得的；
我选了保测试所钉的行为（「第一版写错了要能修回来」），并让时钟口径比字面要求更统一。
`clock_timestamp()`（语句执行时刻）也能过 test 3，但它仍让 INSERT 行留在应用时钟上，
=Ruling K 想消灭的那种混用，所以没走那条。

**逐轮回放（真库，跑完即清）**：

```
1st  v1           -> {'inserted': 1, 'updated': 0, 'skipped': 0}
2nd  v2           -> {'inserted': 0, 'updated': 1, 'skipped': 0}  期望 updated=1
3rd  v2           -> {'inserted': 0, 'updated': 0, 'skipped': 1}  期望 skipped=1
4th  v3           -> {'inserted': 0, 'updated': 1, 'skipped': 0}  期望 updated=1
5th  v3 人工改过后 -> {'inserted': 0, 'updated': 0, 'skipped': 1}  期望 skipped=1
   值 = 人工改的
   finished_at 序列严格递增（5 个不同值）
```

## ③ 测试与清理（要求 3/4/5）

```
$ cd backend && /tmp/venv/bin/python -m pytest tests/test_permission_import.py -v
8 passed, 1 warning in 0.83s          # 7 → 8

$ cd backend && /tmp/venv/bin/python -m pytest tests/ -q
303 passed, 34 warnings in 12.42s     # 302 → 303
```

业务库残留（全量跑完之后查）：

| 查询 | 结果 |
| --- | --- |
| `import_batch where source_file like 'permission-import:%'` | **0** |
| `permission where permission_name like 'test.import.perm.%'` | **0** |
| `permission where permission_name like 'dbg.%'`（我验尸脚本的前缀） | 0 |
| `permission` 总行数 | **103**（仍是原样，未被测试动过） |

即：测试造的行与**批次**都被清干净，import_batch 里没有测试残留，任务 7 首跑不会被污染。

## 本轮自审

- 只动了裁决要求的两处 + 为让 Ruling K 落地所必需的 INSERT 时钟（②里的第二处），以及随之
  而来的 `datetime/timezone` 未使用导入清理（`text` 转回被使用）。没有别的改动。
- 复核守卫与既有分支互不干扰：`validate_permission_type` 的跳过发生在守卫**之前**，所以
  「非法类型 + 同名」只计一次 `skipped`，不会被守卫二次计数。
- 复核 8 个测试里没有一条是 mock：全部打真库、真 ORM、断言 SQL 取回的最终状态。
- 遗留顾虑 1（同批同名）已由本轮的守卫消解，可以从「遗留」划掉；顾虑 2（长事务中的编辑
  可能被覆盖）与 Ruling K 无关，仍然存在，未动。
- 顾虑 5 现在更值得看一眼：test 2 的人工编辑仍是「测试自己写 `now()`」，而真实路径是触发器写
  `CURRENT_TIMESTAMP`。两者语义一致（都是编辑事务的 `now()`），本轮已用真库逐轮回放覆盖
  「人类编辑」这一步（上面 5th 步，走的是 UPDATE + 显式 `now()`），结论一致。

## Commit（本轮）

`561b71f fix(kb): 同名守卫 + finished_at 与行 updated_at 同源数据库时钟（Ruling J/K）`（2 files, +52/-8）
