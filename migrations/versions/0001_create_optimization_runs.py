"""Create durable optimization runs.

Revision ID: 0001_runs
Revises:
Create Date: 2026-09-07
"""

from typing import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = "0001_runs"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "optimization_runs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("idempotency_key", sa.String(length=128), nullable=True),
        sa.Column("request_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("run_type", sa.String(length=32), nullable=False),
        sa.Column("optimization_mode", sa.String(length=32), nullable=False),
        sa.Column("input_reference", sa.String(length=255), nullable=False),
        sa.Column("input_sha256", sa.String(length=64), nullable=False),
        sa.Column("v2g_enabled", sa.Boolean(), nullable=False),
        sa.Column("agent_backend", sa.String(length=32), nullable=False),
        sa.Column("scenario_ids", sa.JSON(), nullable=False),
        sa.Column("requested_by", sa.String(length=128), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("failure_code", sa.String(length=64), nullable=True),
        sa.Column("failure_message", sa.String(length=1000), nullable=True),
        sa.CheckConstraint(
            "status IN ('queued','running','succeeded','failed','infeasible',"
            "'timed_out','cancel_requested','cancelled','degraded')",
            name="ck_optimization_runs_status",
        ),
        sa.CheckConstraint(
            "run_type IN ('day_ahead','real_time')",
            name="ck_optimization_runs_run_type",
        ),
        sa.CheckConstraint(
            "optimization_mode IN ('selfish','altruistic')",
            name="ck_optimization_runs_mode",
        ),
        sa.CheckConstraint(
            "agent_backend IN ('rule','openai')",
            name="ck_optimization_runs_agent_backend",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("idempotency_key"),
    )
    op.create_index(
        "ix_optimization_runs_status",
        "optimization_runs",
        ["status"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_optimization_runs_status", table_name="optimization_runs")
    op.drop_table("optimization_runs")
