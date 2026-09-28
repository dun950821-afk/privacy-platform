# data/kb —— 权限知识库的来源文件与「从仓库重建」步骤

这个目录里的东西分两类，**缺一类就复现不出活库**：

| 类别 | 文件 | 来源 | 谁生成 |
|---|---|---|---|
| 抓取源文件 | `android/AndroidManifest.xml`、`harmonyos/*.md`、`ios/protected-resources.json` | 上游官网 / 仓库 | `scripts/fetch_permission_sources.py`（唯一联网的地方） |
| 人工整理 | `curated_permission_snapshot.tsv` | 人工在权限维护页整理的 103 行 | 人（入仓即为准） |
| 清单 | `SOURCES.json` | —— | 抓取脚本整份重写；其中 `source_kind: repo` 的条目由脚本按磁盘内容重建 |

`capability` / `grant_mode` / `category` / `risk_level` / `compliance_focus` 这五个字段
**任何解析器都产不出来**（AOSP 清单不给描述文本，更不给风险定级），`已弃用权限` /
`危险权限（受限）` / `三方声明权限` 这三个 `permission_type` 取值也推不出来。
它们只存在于 `curated_permission_snapshot.tsv` 里——没有这张快照，重建出来的库会在
`is_applicable`（由 permission_type 推）、`compliance_profile`（按 risk_level 归一）、
`sdk_analysis`（按 risk_level 判敏感权限）三处**静默给出不同的答案**。

## 重建顺序（五步，顺序不能换）

```bash
# 1. 建 schema 与表（privacy_kb / privacy_scan）
PGPASSWORD=privacy123 psql -h localhost -U privacy -d privacy_platform \
  -f backend/sql/app_privacy_kb_schema_postgresql.sql

# 2. 补后续迁移（platform 列、索引等）
cd backend && PYTHONPATH=. /tmp/venv/bin/alembic upgrade head && cd ..

# 3. 抓源文件到本目录（唯一需要联网的一步；已有文件时会保留上一次的 fetched_at）
/tmp/venv/bin/python scripts/fetch_permission_sources.py

# 4. 解析并导入三个平台（读本地文件，不联网；幂等）
/tmp/venv/bin/python scripts/import_permissions.py

# 5. 回填人工整理的字段（读 curated_permission_snapshot.tsv，幂等）
/tmp/venv/bin/python scripts/restore_curated_permissions.py
```

**为什么导入必须在回填之前**（第 4 步在第 5 步前）：`permission_type` 的保护范围是
「解析器产不出来的取值」，机器算得出来的值留给导入器更新（Ruling M'）。反过来先回填、
后导入的话，回填的机器可产出值会把导入器的更新挡在门外，字段就冻结了。
第 5 步是幂等的，跑第二遍不会覆盖库里已有的人工值。

第 4 步的落库数（2026-09-28 实跑）：ANDROID 1016 / HARMONYOS 783 / IOS 57 解析行；
其中 ANDROID 有 1036 行（含快照里 20 行不在 AOSP 清单中的 `com.*` 与废弃权限）。

## 校验重建是否完整

```bash
# 快照里的 103 行，六个字段应全部非空（重建后重跑这条应为 103）
PGPASSWORD=privacy123 psql -h localhost -U privacy -d privacy_platform -At -c \
  "select count(*) from privacy_kb.permission
   where platform='ANDROID' and risk_level is not null and compliance_focus is not null"
```

`SOURCES.json` 里 `source_kind: repo` 的条目对应的是仓库内文件，**不要**手动往 JSON 里加——
抓取脚本会整份重写它，只重建 `REPO_SOURCES` 里声明过的那几条。
