"""platform_findings 增加 level 聚合列与整改闭环字段。

## provider_level_summary（决策 A）

新主视图是「问题清单」，卡片上要写 **`由 3 条敏感 API 调用 + 2 条数据流构成`**。
而 `platform_findings` 上没有任何 level 分布——`provider_level` 在
`engine_observations` 上，要现算。每次都现算等于每次读页面都做一次 join 聚合，
且聚合口径会散落在各处。存一列，口径收在 `finding_service._level_summary()` 里。

**只加这一列**。决策 B 明确**不加** `max_provider_level`——实测证明 L2/L3/L4 不是
严重度阶梯而是三个规则族（同一个规则不会跨 level，`having count(distinct
provider_level)>1` 返回 0 行），所以「取最严重的 level」没有依据；排序改用现成的
`severity`（high/medium）。

**存原始计数，不存中文**：`{"L2": 18, "L3": 2, "L4": 4}` 这样的键值对，
中文映射（敏感 API 调用 / 数据流 / 安全缺陷）放在展示层。写中文进库的话，
以后改文案要动数据。

## assigned_to / due_date（0b）

整改闭环要有负责人与截止日期。这两列在旧的 `findings` 表上有，
`platform_findings` 上没有。`triage_status` 的取值扩展
（`needs_review`/`fixing`/`fixed`/`ignored`）**不需要 DDL**——它已经是 `VARCHAR(30)`，
只需扩展语义，写进模型注释与 API 校验。

## 幂等

逐列各自判存在，**不共用一个 if**：加列与建外键是两件事，罩在同一个判断里时，
只要上一次迁移在 add_column 之后、create_foreign_key 之前失败，列在 → 整个 if 跳过 →
外键**永远补不上**，而且是静默的。见 `20260928_permission_platform.py:30-38` 的完整说明。
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "20260929_finding_level_summary"
down_revision = "20260929_engine_raw_sections"
branch_labels = None
depends_on = None

TABLE = "platform_findings"
SCHEMA = "public"
FK_NAME = "platform_findings_assigned_to_fkey"

# (列名, 类型)——逐列判存在
COLUMNS = (
    ("provider_level_summary", postgresql.JSONB()),
    ("assigned_to", sa.BigInteger()),
    ("due_date", sa.Date()),
)


def _columns(bind) -> set[str]:
    return {r[0] for r in bind.execute(sa.text(
        "select column_name from information_schema.columns "
        "where table_schema = :s and table_name = :t"),
        {"s": SCHEMA, "t": TABLE})}


def upgrade():
    bind = op.get_bind()
    existing = _columns(bind)
    for name, type_ in COLUMNS:
        if name not in existing:
            op.add_column(TABLE, sa.Column(name, type_, nullable=True), schema=SCHEMA)

    # 外键单独判存在（理由见模块 docstring）
    fk = bind.execute(sa.text(
        "select 1 from pg_constraint where conname = :n"), {"n": FK_NAME}).first()
    if not fk:
        op.create_foreign_key(FK_NAME, TABLE, "users", ["assigned_to"], ["id"],
                              source_schema=SCHEMA, referent_schema=SCHEMA)


def downgrade():
    bind = op.get_bind()
    fk = bind.execute(sa.text(
        "select 1 from pg_constraint where conname = :n"), {"n": FK_NAME}).first()
    if fk:
        op.drop_constraint(FK_NAME, TABLE, type_="foreignkey", schema=SCHEMA)
    existing = _columns(bind)
    for name, _ in COLUMNS:
        if name in existing:
            op.drop_column(TABLE, name, schema=SCHEMA)
