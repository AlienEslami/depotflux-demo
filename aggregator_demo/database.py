from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Float,
    String,
    create_engine,
    text,
)
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker
from sqlalchemy.pool import StaticPool

from .contracts import AgentBackend, OptimizationMode, RunStatus, RunType


DEFAULT_DATABASE_URL = "sqlite:///./.demo/agentic_aggregator.db"


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class RunRow(Base):
    __tablename__ = "optimization_runs"
    __table_args__ = (
        CheckConstraint(
            "status IN ('queued','running','succeeded','failed','infeasible',"
            "'timed_out','cancel_requested','cancelled','degraded')",
            name="ck_optimization_runs_status",
        ),
        CheckConstraint(
            "run_type IN ('day_ahead','real_time')",
            name="ck_optimization_runs_run_type",
        ),
        CheckConstraint(
            "optimization_mode IN ('selfish','altruistic')",
            name="ck_optimization_runs_mode",
        ),
        CheckConstraint(
            "agent_backend IN ('rule','openai')",
            name="ck_optimization_runs_agent_backend",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    idempotency_key: Mapped[str | None] = mapped_column(
        String(128), unique=True, nullable=True
    )
    request_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default=RunStatus.QUEUED.value, index=True
    )
    run_type: Mapped[str] = mapped_column(String(32), nullable=False)
    optimization_mode: Mapped[str] = mapped_column(String(32), nullable=False)
    input_reference: Mapped[str] = mapped_column(String(255), nullable=False)
    input_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    v2g_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    agent_backend: Mapped[str] = mapped_column(String(32), nullable=False)
    scenario_ids: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    requested_by: Mapped[str] = mapped_column(String(128), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )
    started_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    failure_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    failure_message: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    worker_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    heartbeat_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    recovery_count: Mapped[int] = mapped_column(nullable=False, default=0)
    last_recovered_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    solver_name: Mapped[str | None] = mapped_column(String(64), nullable=True)
    result_sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    result_payload: Mapped[dict | None] = mapped_column(JSON, nullable=True)


class ApprovalRow(Base):
    __tablename__ = "operator_approvals"
    __table_args__ = (
        CheckConstraint(
            "decision IN ('approved','rejected')",
            name="ck_operator_approvals_decision",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    run_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("optimization_runs.id"),
        unique=True,
        nullable=False,
        index=True,
    )
    decision: Mapped[str] = mapped_column(String(16), nullable=False)
    decided_by: Mapped[str] = mapped_column(String(128), nullable=False)
    result_sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    note: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )


class OperationalNoticeRow(Base):
    __tablename__ = "operational_notices"
    __table_args__ = (
        CheckConstraint(
            "scenario IN ('late_return','charger_derating','combined_disruption',"
            "'site_power_isolation')",
            name="ck_operational_notices_scenario",
        ),
        CheckConstraint(
            "source = 'simulator'",
            name="ck_operational_notices_source",
        ),
        CheckConstraint(
            "interpretation_backend = 'rule'",
            name="ck_operational_notices_backend",
        ),
        CheckConstraint(
            "confidence >= 0 AND confidence <= 1",
            name="ck_operational_notices_confidence",
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    baseline_run_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("optimization_runs.id"), nullable=False, index=True
    )
    candidate_run_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("optimization_runs.id"),
        unique=True,
        nullable=False,
        index=True,
    )
    scenario: Mapped[str] = mapped_column(String(32), nullable=False)
    source: Mapped[str] = mapped_column(String(32), nullable=False, default="simulator")
    raw_notice: Mapped[str] = mapped_column(String(2000), nullable=False)
    structured_facts: Mapped[dict] = mapped_column(JSON, nullable=False)
    interpretation_backend: Mapped[str] = mapped_column(
        String(32), nullable=False, default="rule"
    )
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    replan_recommended: Mapped[bool] = mapped_column(Boolean, nullable=False)
    rationale: Mapped[str] = mapped_column(String(1000), nullable=False)
    created_by: Mapped[str] = mapped_column(String(128), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utc_now
    )


def database_url_from_environment() -> str:
    return os.environ.get("DEMO_DATABASE_URL", DEFAULT_DATABASE_URL)


def _prepare_sqlite_directory(database_url: str) -> None:
    if not database_url.startswith("sqlite:///") or database_url.endswith(":memory:"):
        return
    path_text = database_url.removeprefix("sqlite:///")
    if path_text.startswith("./"):
        path_text = path_text[2:]
    if path_text:
        Path(path_text).expanduser().resolve().parent.mkdir(parents=True, exist_ok=True)


def create_database_engine(database_url: str | None = None) -> Engine:
    resolved_url = database_url or database_url_from_environment()
    _prepare_sqlite_directory(resolved_url)
    options: dict[str, Any] = {"pool_pre_ping": True}
    if resolved_url.startswith("sqlite"):
        options["connect_args"] = {"check_same_thread": False}
        if resolved_url.endswith(":memory:"):
            options["poolclass"] = StaticPool
    return create_engine(resolved_url, **options)


def create_session_factory(engine: Engine) -> sessionmaker:
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def create_schema(engine: Engine) -> None:
    Base.metadata.create_all(engine)


def ping_database(engine: Engine) -> None:
    with engine.connect() as connection:
        connection.execute(text("SELECT 1"))
        connection.execute(text("SELECT 1 FROM optimization_runs LIMIT 1"))
