"""add engine configs

Revision ID: 20260923_engine_configs
Revises:
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "20260923_engine_configs"
down_revision = None
branch_labels = None
depends_on = None


def _tables(bind) -> set:
    return {r[0] for r in bind.execute(sa.text(
        "select table_name from information_schema.tables where table_schema='public'"))}


def _indexes(bind, table: str) -> set:
    return {r[0] for r in bind.execute(sa.text(
        "select indexname from pg_indexes where schemaname='public' and tablename=:t"), {"t": table})}


def upgrade():
    bind = op.get_bind()
    if "engine_configs" not in _tables(bind):
        op.create_table(
            "engine_configs",
            sa.Column("id", sa.BigInteger(), primary_key=True),
            sa.Column("engine_type", sa.String(50), nullable=False),
            sa.Column("config_json", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
            sa.Column("secret_json", postgresql.JSONB(), nullable=False, server_default=sa.text("'{}'::jsonb")),
            sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
            sa.Column("last_health_status", sa.String(30)),
            sa.Column("last_health_message", sa.Text()),
            sa.Column("last_checked_at", sa.DateTime(timezone=True)),
            sa.Column("updated_by", sa.BigInteger(), sa.ForeignKey("users.id")),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
            sa.UniqueConstraint("engine_type", name="uq_engine_configs_engine_type"),
        )
    if "idx_engine_config_health" not in _indexes(bind, "engine_configs"):
        op.create_index("idx_engine_config_health", "engine_configs", ["last_health_status"])


def downgrade():
    op.drop_index("idx_engine_config_health", table_name="engine_configs")
    op.drop_table("engine_configs")
