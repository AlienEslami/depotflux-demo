"""Add simulated operational notices and replanning links.

Revision ID: 0004_notices
Revises: 0003_approvals
Create Date: 2026-09-07
"""

import sqlalchemy as sa
from alembic import op


revision: str = "0004_notices"
down_revision: str | None = "0003_approvals"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "operational_notices",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("baseline_run_id", sa.String(length=36), nullable=False),
        sa.Column("candidate_run_id", sa.String(length=36), nullable=False),
        sa.Column("scenario", sa.String(length=32), nullable=False),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column("raw_notice", sa.String(length=2000), nullable=False),
        sa.Column("structured_facts", sa.JSON(), nullable=False),
        sa.Column("interpretation_backend", sa.String(length=32), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("replan_recommended", sa.Boolean(), nullable=False),
        sa.Column("rationale", sa.String(length=1000), nullable=False),
        sa.Column("created_by", sa.String(length=128), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "scenario IN ('late_return','charger_derating','combined_disruption')",
            name="ck_operational_notices_scenario",
        ),
        sa.CheckConstraint(
            "source = 'simulator'",
            name="ck_operational_notices_source",
        ),
        sa.CheckConstraint(
            "interpretation_backend = 'rule'",
            name="ck_operational_notices_backend",
        ),
        sa.CheckConstraint(
            "confidence >= 0 AND confidence <= 1",
            name="ck_operational_notices_confidence",
        ),
        sa.ForeignKeyConstraint(["baseline_run_id"], ["optimization_runs.id"]),
        sa.ForeignKeyConstraint(["candidate_run_id"], ["optimization_runs.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_operational_notices_baseline_run_id",
        "operational_notices",
        ["baseline_run_id"],
    )
    op.create_index(
        "ix_operational_notices_candidate_run_id",
        "operational_notices",
        ["candidate_run_id"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_operational_notices_candidate_run_id",
        table_name="operational_notices",
    )
    op.drop_index(
        "ix_operational_notices_baseline_run_id",
        table_name="operational_notices",
    )
    op.drop_table("operational_notices")
