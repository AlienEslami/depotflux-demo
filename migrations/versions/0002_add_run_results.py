"""Add durable worker and result fields.

Revision ID: 0002_results
Revises: 0001_runs
Create Date: 2026-09-07
"""

import sqlalchemy as sa
from alembic import op


revision: str = "0002_results"
down_revision: str | None = "0001_runs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("optimization_runs") as batch_op:
        batch_op.add_column(sa.Column("worker_id", sa.String(length=128), nullable=True))
        batch_op.add_column(sa.Column("solver_name", sa.String(length=64), nullable=True))
        batch_op.add_column(sa.Column("result_sha256", sa.String(length=64), nullable=True))
        batch_op.add_column(sa.Column("result_payload", sa.JSON(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("optimization_runs") as batch_op:
        batch_op.drop_column("result_payload")
        batch_op.drop_column("result_sha256")
        batch_op.drop_column("solver_name")
        batch_op.drop_column("worker_id")
