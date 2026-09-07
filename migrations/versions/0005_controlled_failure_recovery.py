"""add controlled failure and worker recovery state

Revision ID: 0005_controlled_failure_recovery
Revises: 0004_notices
Create Date: 2026-09-07
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "0005_controlled_failure_recovery"
down_revision: Union[str, None] = "0004_notices"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("optimization_runs") as batch_op:
        batch_op.add_column(sa.Column("heartbeat_at", sa.DateTime(timezone=True)))
        batch_op.add_column(
            sa.Column(
                "recovery_count",
                sa.Integer(),
                nullable=False,
                server_default="0",
            )
        )
        batch_op.add_column(sa.Column("last_recovered_at", sa.DateTime(timezone=True)))

    with op.batch_alter_table("operational_notices") as batch_op:
        batch_op.drop_constraint("ck_operational_notices_scenario", type_="check")
        batch_op.create_check_constraint(
            "ck_operational_notices_scenario",
            "scenario IN ('late_return','charger_derating','combined_disruption',"
            "'site_power_isolation')",
        )


def downgrade() -> None:
    with op.batch_alter_table("operational_notices") as batch_op:
        batch_op.drop_constraint("ck_operational_notices_scenario", type_="check")
        batch_op.create_check_constraint(
            "ck_operational_notices_scenario",
            "scenario IN ('late_return','charger_derating','combined_disruption')",
        )

    with op.batch_alter_table("optimization_runs") as batch_op:
        batch_op.drop_column("last_recovered_at")
        batch_op.drop_column("recovery_count")
        batch_op.drop_column("heartbeat_at")
