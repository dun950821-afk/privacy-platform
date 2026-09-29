"""新增引擎原始结果的逐段存档表。

原始产物本来就落盘归档了（`engine_artifacts`），但提取是**一次性**的：适配器取完事件
就把 raw dict 丢掉，于是没被提取的段落等于不存在。

实测 task 2216：

    Androguard  endpoints（41 URL + 12 域名 + 3 IP，含隐私政策 URL）  整段丢弃
    MobSF       53 个段落只用了 4 个
                appsec / manifest_findings / secrets / sbom / certificate_analysis 全丢

同一批数据里，入库的 24 条 MobSF URL 去重后只有 3 个值（OpenSSL 文档链接在 8 个
ABI 目录的 .so 里各一份）——噪声进了库，信号被丢掉。

本表只存不判，不参与任何业务逻辑。拆分规则见 app/services/raw_section_service.py。
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "20260929_engine_raw_sections"
down_revision = "20260928_permission_platform"
branch_labels = None
depends_on = None

TABLE = "engine_raw_sections"
INDEXES = (
    ("idx_raw_section_task", ["task_id"]),
    ("idx_raw_section_execution", ["execution_id"]),
    ("idx_raw_section_path", ["section_path"]),
)


def _table_exists(bind) -> bool:
    return bind.execute(sa.text(
        "select 1 from information_schema.tables "
        "where table_schema='public' and table_name=:t"), {"t": TABLE}).first() is not None


def _index_exists(bind, name: str) -> bool:
    return bind.execute(sa.text(
        "select 1 from pg_indexes "
        "where schemaname='public' and indexname=:n"), {"n": name}).first() is not None


def upgrade():
    bind = op.get_bind()
    if not _table_exists(bind):
        op.create_table(
            TABLE,
            sa.Column("id", sa.BigInteger(), primary_key=True),
            sa.Column("task_id", sa.BigInteger(),
                      sa.ForeignKey("detection_tasks.id", ondelete="CASCADE"), nullable=False),
            sa.Column("execution_id", sa.BigInteger(),
                      sa.ForeignKey("engine_executions.id", ondelete="CASCADE"), nullable=False),
            sa.Column("engine_type", sa.String(50), nullable=False),
            sa.Column("section_path", sa.String(500), nullable=False),
            sa.Column("section_kind", sa.String(20), nullable=False),
            sa.Column("item_count", sa.Integer()),
            sa.Column("payload", postgresql.JSONB(), nullable=False),
            sa.Column("payload_hash", sa.String(64), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True),
                      nullable=False, server_default=sa.func.now()),
            sa.UniqueConstraint("execution_id", "section_path",
                                name="uq_raw_section_execution_path"),
        )

    # 索引**逐个判存在**，不跟着建表的 if 走：建表与建索引是两件事。
    # 罩在同一个 if 里时，只要上一次迁移在 create_table 之后、create_index 之前失败
    # （或有人在已有表的库上补跑），表在 → 整个 if 跳过 → 索引**永远补不上**，
    # 而且是静默的：迁移报成功，查询只是慢。（同 20260928_permission_platform 的教训）
    for name, cols in INDEXES:
        if not _index_exists(bind, name):
            op.create_index(name, TABLE, cols)

    # payload 的 GIN 索引：跨任务查「谁的原始结果里出现 X」靠它。
    # jsonb_path_ops 比默认的 jsonb_ops 小且快，代价是只支持 @> 包含查询——
    # 而包含查询正是我们的用法（不需要键存在性 / 数组元素存在性那类操作符）。
    if not _index_exists(bind, "idx_raw_section_payload_gin"):
        op.create_index("idx_raw_section_payload_gin", TABLE, ["payload"],
                        postgresql_using="gin", postgresql_ops={"payload": "jsonb_path_ops"})


def downgrade():
    op.drop_index("idx_raw_section_payload_gin", TABLE)
    for name, _ in INDEXES:
        op.drop_index(name, TABLE)
    op.drop_table(TABLE)
