"""Add immutable operator approvals.

Revision ID: 0003_approvals
Revises: 0002_results
Create Date: 2026-09-07
"""

import sqlalchemy as sa
from alembic import op


revision: str = "0003_approvals"
down_revision: str | None = "0002_results"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "operator_approvals",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("run_id", sa.String(length=36), nullable=False),
        sa.Column("decision", sa.String(length=16), nullable=False),
        sa.Column("decided_by", sa.String(length=128), nullable=False),
        sa.Column("result_sha256", sa.String(length=64), nullable=False),
        sa.Column("note", sa.String(length=1000), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "decision IN ('approved','rejected')",
            name="ck_operator_approvals_decision",
        ),
        sa.ForeignKeyConstraint(["run_id"], ["optimization_runs.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_operator_approvals_run_id",
        "operator_approvals",
        ["run_id"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("ix_operator_approvals_run_id", table_name="operator_approvals")
    op.drop_table("operator_approvals")
