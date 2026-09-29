# Task 1 报告：`platform` 列与迁移

**Status:** DONE

## 实现了什么

给 `privacy_kb.permission` 增加平台维度，为后续 8 个任务导入 Android / 鸿蒙 / iOS
三套命名体系的权限铺路。本任务只加列 + 迁移 + 模型字段，**不碰任何数据内容**。

1. **迁移** `20260928_permission_platform`：`down_revision = 20260928_analysis_coverage`
   （确认过这是当时的 head）。`op.add_column` 加 `varchar(20) NOT NULL
   server_default='ANDROID'`，并建索引 `idx_permission_platform`。
   `upgrade` 里保留了 brief 的幂等守卫（列已存在则跳过）。写出了 `downgrade`。
2. **模型**：`KBPermission` 在 `permission_name` 之后加一行
   `platform = Column(String(20), nullable=False, default="ANDROID", server_default="ANDROID")`。
3. **测试**：`backend/tests/test_permission_platform_migration.py`，2 条。

`DEFAULT 'ANDROID'` 让既有 103 行自动落位——它们确实全是 Android 权限。

## 测了什么与结果

| 测试 | 验证的行为 |
|---|---|
| `test_platform_column_is_backfilled_to_android` | 无 `platform` 为空的行；旧行 `android.permission.CAMERA` == `ANDROID` |
| `test_platform_column_is_not_nullable` | `information_schema` 里 `is_nullable == 'NO'` |

两条都是直连真实 PostgreSQL 的 `select`，不是 mock（`db` fixture 是 conftest 里的
`SessionLocal()`，测试后 rollback，只读不写）。

**按需求方交代，刻意没有断言「全表只有 ANDROID」**，只断言「无空行」+「已知旧行为
ANDROID」。后续任务导入鸿蒙/iOS 后这条测试仍然成立。

结果：聚焦 2 passed；全量 **271 passed**（基线 269 + 新增 2），符合验收口径。

数据库实测：

```
 platform | count
----------+-------
 ANDROID  |   103
```

列属性实测：`platform | character varying(20) | not null | 'ANDROID'::character varying`，
索引 `idx_permission_platform btree (platform)` 已建。

## TDD 证据

**RED** — `cd backend && /tmp/venv/bin/python -m pytest tests/test_permission_platform_migration.py -v`

```
E       psycopg2.errors.UndefinedColumn: column "platform" does not exist
E       sqlalchemy.exc.ProgrammingError: (psycopg2.errors.UndefinedColumn) column "platform" does not exist
FAILED tests/test_permission_platform_migration.py::test_platform_column_is_backfilled_to_android
FAILED tests/test_permission_platform_migration.py::test_platform_column_is_not_nullable
2 failed, 1 warning in 0.70s
```

预期失败的理由：列还没建，第一条撞 `UndefinedColumn`；第二条 `is_nullable` 查不到行返回
`None`（`assert None == 'NO'`）。两条失败的原因都与「列不存在」直接对应，不是无关错误。

**GREEN** — 写完迁移 + 模型、跑过 `alembic upgrade head` 后再跑同一条命令：

```
tests/test_permission_platform_migration.py::test_platform_column_is_backfilled_to_android PASSED
tests/test_permission_platform_migration.py::test_platform_column_is_not_nullable PASSED
2 passed, 1 warning in 0.40s
```

迁移执行输出确认走的是预期 revision：

```
Running upgrade 20260928_analysis_coverage -> 20260928_permission_platform, 权限知识库增加平台维度。
```

**回归** — `cd backend && /tmp/venv/bin/python -m pytest tests/ -q` → `271 passed, 34 warnings in 13.54s`

## 额外验证（超出 brief，自审时做的）

迁移里带了 `downgrade`，所以实测了来回一趟，确认它真的可逆：

- `alembic downgrade -1` → 列数 0 命中，`privacy_kb.permission` 仍 103 行（数据未被误删）
- `alembic upgrade head` → 再次回填，103 行全部 ANDROID

## 改了哪些文件

- Create `backend/alembic/versions/20260928_permission_platform.py`（35 行）
- Modify `backend/app/models/kb.py`（+1 行，`KBPermission`）
- Create `backend/tests/test_permission_platform_migration.py`（29 行）

Commit：`5b7dcec feat(kb): 权限表增加 platform 列，旧行回填 ANDROID`（3 files changed, 65 insertions）

## 自审发现

- 逐行比对 brief：迁移代码与模型那一行都按 brief 原样落地，`revision` / `down_revision`
  与 brief 一致，未改名。
- YAGNI：没有多写字段、没有顺手改 `permission_type` / `category`、没有提前导入任何数据。
- 测试输出干净：唯一 warning 是 `app/core/config.py` 的 `PydanticDeprecatedSince20`，
  任何 import config 的测试都带它，属既有、非本次引入。
- 确认 commit 只含我的 3 个文件。

## 遗留顾虑

1. **工作树里有本次任务之外的改动**，均未被我触碰、也未被我提交：
   `backend/app/api/v1/permissions.py`、`backend/tests/test_permission_kb_api.py`、
   `frontend/src/views/Permissions.vue`、`frontend/src/api/permissions.ts` 等
   （看着像「权限知识库 API/页面」的活儿）。**注意：会话开始时的 git 快照显示工作树是
   clean 的**，这些改动是此后出现的，来源不在我这条线。已按 brief 的 `git add` 精确提交，
   未把它们卷进本 commit。控制方如发现有并行改动，需自行处置。
2. **迁移的幂等守卫有个窄边界**：`if COLUMN not in existing` 同时罩住了 `add_column`
   和 `create_index`。若某库上列已存在但索引缺失，重跑不会补索引。这是 brief 给定的代码，
   按「verbatim」要求未改动；且 alembic 的 DDL 在事务里，半应用状态基本不会出现，
   实际风险很低。若后续要收紧，把 `create_index` 移出守卫即可。
