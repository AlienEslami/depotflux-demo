"""add secure OT control simulation records

Revision ID: 0006_add_control_simulations
Revises: 0005_controlled_failure_recovery
Create Date: 2026-09-07
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0006_add_control_simulations"
down_revision: Union[str, None] = "0005_controlled_failure_recovery"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "control_simulations",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("run_id", sa.String(length=36), nullable=False),
        sa.Column("interval_index", sa.Integer(), nullable=False),
        sa.Column("setpoint_kw", sa.Float(), nullable=False),
        sa.Column("unit_id", sa.Integer(), nullable=False),
        sa.Column("register_address", sa.Integer(), nullable=False),
        sa.Column("register_scale_kw", sa.Float(), nullable=False),
        sa.Column("modbus_frame_hex", sa.String(length=24), nullable=False),
        sa.Column("result_sha256", sa.String(length=64), nullable=False),
        sa.Column("policy_version", sa.String(length=32), nullable=False),
        sa.Column("policy_checks", sa.JSON(), nullable=False),
        sa.Column("requested_by", sa.String(length=128), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "unit_id >= 1 AND unit_id <= 247",
            name="ck_control_simulations_unit_id",
        ),
        sa.CheckConstraint(
            "register_address >= 0 AND register_address <= 65535",
            name="ck_control_simulations_register_address",
        ),
        sa.ForeignKeyConstraint(["run_id"], ["optimization_runs.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "run_id",
            "interval_index",
            name="uq_control_simulations_run_interval",
        ),
    )
    op.create_index(
        "ix_control_simulations_run_id",
        "control_simulations",
        ["run_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_control_simulations_run_id", table_name="control_simulations")
    op.drop_table("control_simulations")
