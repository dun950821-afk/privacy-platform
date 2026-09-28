"""EngineObservation 增加平台语义字段。

设计依据：docs/superpowers/specs/2026-09-28-finding-evidence-join-design.md §4

Provider 的 structured 语义（AppShark 的 complianceCategory）此前在归一化阶段被
降维成字符串，后端只能用字符串匹配猜语义。本迁移补回一等字段。
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "20260928_observation_semantics"
down_revision = "20260924_finding_reproducibility"
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    existing = {r[0] for r in bind.execute(sa.text(
        "select column_name from information_schema.columns "
        "where table_name='engine_observations'"))}
    additions = {
        "data_category": sa.String(60),
        "sink_type": sa.String(40),
        "result_semantics": sa.String(30),
        "observation_kind": sa.String(30),
        "provider_rule_id": sa.String(120),
        "provider_level": sa.String(10),
        "entity_keys": postgresql.JSONB(),
    }
    for name, typ in additions.items():
        if name not in existing:
            op.add_column("engine_observations", sa.Column(name, typ))
    op.execute(sa.text("update engine_observations set entity_keys='{}'::jsonb where entity_keys is null"))

    indexes = {r[0] for r in bind.execute(sa.text(
        "select indexname from pg_indexes where schemaname='public' "
        "and tablename='engine_observations'"))}
    if "idx_observation_join" not in indexes:
        op.create_index("idx_observation_join", "engine_observations",
                        ["task_id", "data_category"])


def downgrade():
    op.drop_index("idx_observation_join", table_name="engine_observations")
    for name in ("entity_keys", "provider_level", "provider_rule_id",
                 "observation_kind", "result_semantics", "sink_type", "data_category"):
        op.drop_column("engine_observations", name)
