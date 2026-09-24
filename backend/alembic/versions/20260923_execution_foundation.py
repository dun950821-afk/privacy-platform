"""扩展引擎执行基础字段和结果观察表。"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "20260923_execution_foundation"
down_revision = "20260923_engine_configs"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    existing = {r[0] for r in bind.execute(sa.text("select column_name from information_schema.columns where table_name='engine_executions'"))}
    additions = {
        "stage_message": sa.Text(), "progress": sa.Integer(), "error_code": sa.String(60),
        "debug_message": sa.Text(), "retryable": sa.Boolean(), "provider_status": sa.Integer(),
        "queued_at": sa.DateTime(timezone=True), "stage_changed_at": sa.DateTime(timezone=True),
        "heartbeat_at": sa.DateTime(timezone=True), "finished_at": sa.DateTime(timezone=True),
        "worker_id": sa.String(120), "lease_token": sa.String(120), "lease_expires_at": sa.DateTime(timezone=True),
        "state_version": sa.Integer(), "attempt_no": sa.Integer(), "parent_execution_id": sa.BigInteger(),
        "is_latest": sa.Boolean(), "execution_fingerprint": sa.String(64), "cache_scope": sa.String(200),
        "cancel_requested": sa.Boolean(), "provider_scan_id": sa.String(200), "provider_scan_hash": sa.String(200),
        "raw_result_hash": sa.String(64), "raw_result_size": sa.BigInteger(), "parser_version": sa.String(50),
        "parser_status": sa.String(30), "parser_error": sa.Text(), "normalized_at": sa.DateTime(timezone=True),
        "normalized_event_count": sa.Integer(), "normalized_finding_count": sa.Integer(),
    }
    for name, typ in additions.items():
        if name not in existing:
            op.add_column("engine_executions", sa.Column(name, typ))
    op.execute(sa.text("update engine_executions set state_version=0 where state_version is null"))
    op.execute(sa.text("update engine_executions set attempt_no=1 where attempt_no is null"))
    op.execute(sa.text("update engine_executions set is_latest=true where is_latest is null"))
    op.execute(sa.text("update engine_executions set cancel_requested=false where cancel_requested is null"))
    exec_indexes = {r[0] for r in bind.execute(sa.text(
        "select indexname from pg_indexes where schemaname='public' and tablename='engine_executions'"))}
    if "idx_engine_exec_lease" not in exec_indexes:
        op.create_index("idx_engine_exec_lease", "engine_executions", ["lease_expires_at"])
    if "idx_engine_exec_fingerprint" not in exec_indexes:
        op.create_index("idx_engine_exec_fingerprint", "engine_executions", ["execution_fingerprint", "cache_scope"])

    tables = {r[0] for r in bind.execute(sa.text(
        "select table_name from information_schema.tables where table_schema='public'"))}
    if "engine_artifacts" not in tables:
        op.create_table(
        "engine_artifacts",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("execution_id", sa.BigInteger(), sa.ForeignKey("engine_executions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("artifact_type", sa.String(60), nullable=False), sa.Column("artifact_uri", sa.String(1000), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False), sa.Column("size", sa.BigInteger(), nullable=False, server_default="0"),
        sa.Column("content_type", sa.String(200)), sa.Column("storage_backend", sa.String(40), nullable=False, server_default="local"),
        sa.Column("schema_version", sa.String(30)), sa.Column("metadata_json", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    if "idx_engine_artifact_execution" not in {r[0] for r in bind.execute(sa.text(
            "select indexname from pg_indexes where schemaname='public' and tablename='engine_artifacts'"))}:
        op.create_index("idx_engine_artifact_execution", "engine_artifacts", ["execution_id"])
    if "engine_observations" not in tables:
        op.create_table(
        "engine_observations",
        sa.Column("id", sa.BigInteger(), primary_key=True),
        sa.Column("task_id", sa.BigInteger(), sa.ForeignKey("detection_tasks.id", ondelete="CASCADE"), nullable=False),
        sa.Column("execution_id", sa.BigInteger(), sa.ForeignKey("engine_executions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("engine_type", sa.String(50), nullable=False), sa.Column("observation_type", sa.String(80), nullable=False),
        sa.Column("rule_code", sa.String(120)), sa.Column("severity", sa.String(30)), sa.Column("confidence", sa.String(30)),
        sa.Column("evidence_refs", postgresql.JSONB(), server_default=sa.text("'[]'::jsonb")),
        sa.Column("payload", postgresql.JSONB(), server_default=sa.text("'{}'::jsonb")),
        sa.Column("schema_version", sa.String(30), nullable=False, server_default="1.0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    obs_indexes = {r[0] for r in bind.execute(sa.text(
        "select indexname from pg_indexes where schemaname='public' and tablename='engine_observations'"))}
    if "idx_engine_observation_task" not in obs_indexes:
        op.create_index("idx_engine_observation_task", "engine_observations", ["task_id"])
    if "idx_engine_observation_execution" not in obs_indexes:
        op.create_index("idx_engine_observation_execution", "engine_observations", ["execution_id"])


def downgrade():
    op.drop_index("idx_engine_observation_execution", table_name="engine_observations")
    op.drop_index("idx_engine_observation_task", table_name="engine_observations")
    op.drop_table("engine_observations")
    op.drop_index("idx_engine_artifact_execution", table_name="engine_artifacts")
    op.drop_table("engine_artifacts")
    op.drop_index("idx_engine_exec_fingerprint", table_name="engine_executions")
    op.drop_index("idx_engine_exec_lease", table_name="engine_executions")
