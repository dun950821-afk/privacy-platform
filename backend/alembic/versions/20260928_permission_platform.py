"""权限知识库增加平台维度。

平台与「权限级别」「功能分类」是三个正交维度，所以单独一列，不塞进
permission_type 或 category——上一轮刚把被覆盖的功能分类从 category 里恢复出来
（AD_ID 的分类一度被写成「三方声明权限」），再塞平台会把刚理干净的字段又搅浑。

DEFAULT 'ANDROID' 让现有 103 行自动回填：它们确实全是 Android 权限。
"""
from alembic import op
import sqlalchemy as sa

revision = "20260928_permission_platform"
down_revision = "20260928_analysis_coverage"
branch_labels = None
depends_on = None

TABLE = "permission"
COLUMN = "platform"


def upgrade():
    bind = op.get_bind()
    existing = {r[0] for r in bind.execute(sa.text(
        "select column_name from information_schema.columns "
        "where table_schema='privacy_kb' and table_name=:t"), {"t": TABLE})}
    if COLUMN not in existing:
        op.add_column(TABLE, sa.Column(COLUMN, sa.String(20), nullable=False,
                                       server_default="ANDROID"),
                      schema="privacy_kb")
    # 索引**单独判存在**，不跟着上面那个 if 走：加列与建索引是两件事。
    # 罩在同一个 if 里时，只要上一次迁移在 add_column 之后、create_index 之前失败
    # （或者有人在已有列的库上补跑），列在 → 整个 if 跳过 → 索引**永远补不上**，
    # 而且是静默的：迁移报成功，查询只是慢。
    indexed = bind.execute(sa.text(
        "select 1 from pg_indexes "
        "where schemaname='privacy_kb' and indexname='idx_permission_platform'")).first()
    if not indexed:
        op.create_index("idx_permission_platform", TABLE, [COLUMN], schema="privacy_kb")


def downgrade():
    op.drop_index("idx_permission_platform", TABLE, schema="privacy_kb")
    op.drop_column(TABLE, COLUMN, schema="privacy_kb")
