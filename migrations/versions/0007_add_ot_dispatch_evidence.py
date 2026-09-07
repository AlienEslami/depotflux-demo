"""add OT dispatch attempts and structured security events

Revision ID: 0007_add_ot_dispatch_evidence
Revises: 0006_add_control_simulations
Create Date: 2026-09-07
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0007_add_ot_dispatch_evidence"
down_revision: Union[str, None] = "0006_add_control_simulations"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "ot_dispatch_attempts",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("run_id", sa.String(length=36), nullable=True),
        sa.Column("interval_index", sa.Integer(), nullable=True),
        sa.Column("command_id", sa.String(length=36), nullable=False),
        sa.Column("correlation_id", sa.String(length=36), nullable=False),
        sa.Column("action", sa.String(length=32), nullable=False),
        sa.Column("decision", sa.String(length=16), nullable=False),
        sa.Column("reason_code", sa.String(length=64), nullable=False),
        sa.Column("reason_message", sa.String(length=1000), nullable=False),
        sa.Column("setpoint_kw", sa.Float(), nullable=True),
        sa.Column("result_sha256", sa.String(length=64), nullable=True),
        sa.Column("modbus_frame_hex", sa.String(length=1024), nullable=True),
        sa.Column("response_frame_hex", sa.String(length=1024), nullable=True),
        sa.Column("policy_checks", sa.JSON(), nullable=False),
        sa.Column("controller_response", sa.JSON(), nullable=True),
        sa.Column("requested_by", sa.String(length=128), nullable=False),
        sa.Column("issued_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "action IN ('dispatch','safe_state')", name="ck_ot_dispatch_attempts_action"
        ),
        sa.CheckConstraint(
            "decision IN ('accepted','rejected','failed')",
            name="ck_ot_dispatch_attempts_decision",
        ),
        sa.ForeignKeyConstraint(["run_id"], ["optimization_runs.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    for column in ("run_id", "command_id", "correlation_id", "decision"):
        op.create_index(f"ix_ot_dispatch_attempts_{column}", "ot_dispatch_attempts", [column])

    op.create_table(
        "security_events",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("event_type", sa.String(length=96), nullable=False),
        sa.Column("severity", sa.String(length=16), nullable=False),
        sa.Column("correlation_id", sa.String(length=36), nullable=False),
        sa.Column("run_id", sa.String(length=36), nullable=True),
        sa.Column("actor", sa.String(length=128), nullable=False),
        sa.Column("source_zone", sa.String(length=64), nullable=False),
        sa.Column("destination", sa.String(length=128), nullable=False),
        sa.Column("outcome", sa.String(length=32), nullable=False),
        sa.Column("reason_code", sa.String(length=64), nullable=False),
        sa.Column("details", sa.JSON(), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    for column in ("event_type", "severity", "correlation_id", "run_id"):
        op.create_index(f"ix_security_events_{column}", "security_events", [column])


def downgrade() -> None:
    for column in ("event_type", "severity", "correlation_id", "run_id"):
        op.drop_index(f"ix_security_events_{column}", table_name="security_events")
    op.drop_table("security_events")
    for column in ("run_id", "command_id", "correlation_id", "decision"):
        op.drop_index(f"ix_ot_dispatch_attempts_{column}", table_name="ot_dispatch_attempts")
    op.drop_table("ot_dispatch_attempts")
