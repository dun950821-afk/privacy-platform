"""retest_records 的外键从已废弃的 findings 表迁到 platform_findings。

## 为什么

`retest_records.original_finding_id` 指向 **旧 `findings` 表**，而那张表是
**0 行**——现行结论全在 `platform_findings`（117 行）。也就是说这条外键指向的是一张
已经没有数据的表，「把这个结论标为已复检」这件事在数据模型上根本落不下来。

## 为什么可以直接 drop + recreate

两张表**都是 0 行**（实测 `findings` 0、`retest_records` 0），没有数据要迁。
有数据的话就得先回填再换外键，这里不需要。

## 幂等

先读现有约束的定义：只有它**指向 findings** 时才 drop，drop 完再判名字不存在才 create。
不这么写的话，重跑时 `drop` 会报「约束不存在」或（更糟）把已经改对的外键又删一次。

不加 `ON DELETE`：与旧约束保持一致（旧的就是裸外键）。删一条结论时若还有复检记录
指着它，应当报错而不是静默连带删除复检历史。
"""
from alembic import op
import sqlalchemy as sa

# 注意 revision id **不能超过 32 个字符**：alembic_version.version_num 是 varchar(32)，
# 超了会在最后写版本戳时报 StringDataRightTruncation、整个事务回滚——
# 表现为「DDL 看着跑了但外键没变、版本没推进」。起名时先数长度。
revision = "20260929_retest_platform_fk"
down_revision = "20260929_finding_level_summary"
branch_labels = None
depends_on = None

TABLE = "retest_records"
COLUMN = "original_finding_id"
FK_NAME = "retest_records_original_finding_id_fkey"
SCHEMA = "public"
OLD_TARGET = "findings"
NEW_TARGET = "platform_findings"


def _fk_def(bind) -> str | None:
    # 用 to_regclass() 而不是 `:t::regclass`——后者里的 `::` 会被 SQLAlchemy 的
    # 绑定参数解析器吃掉（`:t::regclass` 被当成参数名 `t:`），实测报 syntax error。
    row = bind.execute(sa.text(
        "select pg_get_constraintdef(oid) from pg_constraint "
        "where conrelid = to_regclass(:t) and conname = :n"),
        {"t": f"{SCHEMA}.{TABLE}", "n": FK_NAME}).first()
    return row[0] if row else None


def upgrade():
    bind = op.get_bind()
    definition = _fk_def(bind)
    if definition and f"REFERENCES {OLD_TARGET}(" in definition:
        op.drop_constraint(FK_NAME, TABLE, type_="foreignkey", schema=SCHEMA)
        definition = None
    if definition is None:
        op.create_foreign_key(FK_NAME, TABLE, NEW_TARGET, [COLUMN], ["id"],
                              source_schema=SCHEMA, referent_schema=SCHEMA)


def downgrade():
    bind = op.get_bind()
    definition = _fk_def(bind)
    if definition and f"REFERENCES {NEW_TARGET}(" in definition:
        op.drop_constraint(FK_NAME, TABLE, type_="foreignkey", schema=SCHEMA)
        definition = None
    if definition is None:
        op.create_foreign_key(FK_NAME, TABLE, OLD_TARGET, [COLUMN], ["id"],
                              source_schema=SCHEMA, referent_schema=SCHEMA)
