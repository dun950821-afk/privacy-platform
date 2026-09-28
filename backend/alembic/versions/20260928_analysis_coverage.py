"""引擎执行与检测任务增加分析有效性字段。

设计依据：docs/analysis-coverage-design.md

「引擎跑完了」不等于「这个 App 被分析过了」：加固样本上 AppShark 分析的是壳，
却报告 completed / 0 漏洞，平台据此显示「未发现风险」。本迁移为「结果算不算数」
提供独立的落库位置——**不与 status 混用**，二者都为真，压进一个字段会丢信息。

既有行不回填：NULL 表示未判定，语义上等价于 UNKNOWN，**不得**被当成 FULL。
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "20260928_analysis_coverage"
down_revision = "20260928_observation_semantics"
branch_labels = None
depends_on = None

ADDITIONS = {
    "engine_executions": {"analysis_coverage": sa.String(20),
                          "coverage_detail": postgresql.JSONB()},
    "detection_tasks": {"analysis_coverage": sa.String(20),
                        "coverage_detail": postgresql.JSONB()},
}


def upgrade():
    bind = op.get_bind()
    for table, columns in ADDITIONS.items():
        existing = {r[0] for r in bind.execute(sa.text(
            "select column_name from information_schema.columns "
            "where table_name=:t"), {"t": table})}
        for name, typ in columns.items():
            if name not in existing:
                op.add_column(table, sa.Column(name, typ))


def downgrade():
    for table, columns in ADDITIONS.items():
        for name in columns:
            op.drop_column(table, name)
