"""为 Platform Finding 增加可复现字段。"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "20260924_finding_reproducibility"
down_revision = "20260924_platform_findings"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    existing = {r[0] for r in bind.execute(sa.text(
        "select column_name from information_schema.columns where table_name='platform_findings'"))}
    if "finding_uid" not in existing:
        op.add_column("platform_findings", sa.Column("finding_uid", sa.String(64)))
    if "rule_snapshot" not in existing:
        op.add_column("platform_findings", sa.Column("rule_snapshot", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb")))
    indexes = {r[0] for r in bind.execute(sa.text(
        "select indexname from pg_indexes where schemaname='public' and tablename='platform_findings'"))}
    if "idx_platform_finding_uid" not in indexes:
        op.create_index("idx_platform_finding_uid", "platform_findings", ["task_id", "finding_uid"])


def downgrade():
    op.drop_index("idx_platform_finding_uid", table_name="platform_findings")
    op.drop_column("platform_findings", "rule_snapshot")
    op.drop_column("platform_findings", "finding_uid")
