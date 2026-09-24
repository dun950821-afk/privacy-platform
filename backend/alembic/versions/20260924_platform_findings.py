"""补充 Observation 字段并新增 Platform Finding 与关联表。"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "20260924_platform_findings"
down_revision = "20260923_execution_foundation"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    existing = {r[0] for r in bind.execute(sa.text(
        "select column_name from information_schema.columns where table_name='engine_observations'"))}
    additions = {
        "category": sa.String(80),
        "rule_version": sa.String(30),
        "evidence_level": sa.String(30),
        "subject": sa.String(500),
        "location": sa.String(500),
        "fingerprint": sa.String(64),
    }
    for name, typ in additions.items():
        if name not in existing:
            op.add_column("engine_observations", sa.Column(name, typ))
    op.execute(sa.text("update engine_observations set evidence_level='observed' where evidence_level is null"))

    tables = {r[0] for r in bind.execute(sa.text(
        "select table_name from information_schema.tables where table_schema='public'"))}
    if "platform_findings" not in tables:
        op.create_table(
            "platform_findings",
            sa.Column("id", sa.BigInteger(), primary_key=True),
            sa.Column("task_id", sa.BigInteger(), sa.ForeignKey("detection_tasks.id", ondelete="CASCADE"), nullable=False),
            sa.Column("finding_code", sa.String(120), nullable=False),
            sa.Column("title", sa.String(300), nullable=False),
            sa.Column("category", sa.String(80), nullable=False),
            sa.Column("subcategory", sa.String(80)),
            sa.Column("severity", sa.String(30), nullable=False, server_default="medium"),
            sa.Column("confidence", sa.String(30), nullable=False, server_default="medium"),
            sa.Column("triage_status", sa.String(30), nullable=False, server_default="needs_review"),
            sa.Column("baseline_state", sa.String(30), nullable=False, server_default="new"),
            sa.Column("description", sa.Text()),
            sa.Column("impact", sa.Text()),
            sa.Column("recommendation", sa.Text()),
            sa.Column("masvs_controls", postgresql.JSONB(), server_default=sa.text("'[]'::jsonb")),
            sa.Column("maswe_ids", postgresql.JSONB(), server_default=sa.text("'[]'::jsonb")),
            sa.Column("mastg_test_ids", postgresql.JSONB(), server_default=sa.text("'[]'::jsonb")),
            sa.Column("cwe_ids", postgresql.JSONB(), server_default=sa.text("'[]'::jsonb")),
            sa.Column("correlation_rule_id", sa.String(120)),
            sa.Column("correlation_rule_version", sa.String(30)),
            sa.Column("dedup_key", sa.String(200), nullable=False),
            sa.Column("observation_count", sa.Integer(), server_default="0"),
            sa.Column("schema_version", sa.String(30), nullable=False, server_default="1.0"),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        )
        op.create_index("idx_platform_finding_task", "platform_findings", ["task_id"])
        op.create_index("idx_platform_finding_dedup", "platform_findings", ["task_id", "dedup_key"])
    if "finding_observations" not in tables:
        op.create_table(
            "finding_observations",
            sa.Column("finding_id", sa.BigInteger(), sa.ForeignKey("platform_findings.id", ondelete="CASCADE"), primary_key=True),
            sa.Column("observation_id", sa.BigInteger(), sa.ForeignKey("engine_observations.id", ondelete="CASCADE"), primary_key=True),
            sa.Column("relation_type", sa.String(40), nullable=False, server_default="evidence"),
            sa.Column("weight", sa.Float(), server_default="1.0"),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        )


def downgrade():
    op.drop_table("finding_observations")
    op.drop_index("idx_platform_finding_dedup", table_name="platform_findings")
    op.drop_index("idx_platform_finding_task", table_name="platform_findings")
    op.drop_table("platform_findings")
    for name in ("category", "rule_version", "evidence_level", "subject", "location", "fingerprint"):
        op.drop_column("engine_observations", name)
