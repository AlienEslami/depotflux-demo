from __future__ import annotations

import argparse
import hashlib
import json
import time
from datetime import datetime, timezone
from hmac import compare_digest
from pathlib import Path
from typing import Any, Sequence

from sqlalchemy import DateTime, delete, insert, select
from sqlalchemy.engine import Engine

from . import __version__
from .contracts import AgentBackend, OptimizationMode, RunCreateRequest, RunType
from .database import (
    ApprovalRow,
    ControlSimulationRow,
    OTDispatchAttemptRow,
    OperationalNoticeRow,
    RunRow,
    SecurityEventRow,
    create_database_engine,
    create_session_factory,
    ping_database,
)
from .input_registry import DemoInputRegistry
from .run_repository import RunRepository
from .settings import RuntimeSettings


BACKUP_SCHEMA_VERSION = "depotflux-backup-v1"
_MODELS = (
    RunRow,
    OperationalNoticeRow,
    ApprovalRow,
    ControlSimulationRow,
    OTDispatchAttemptRow,
    SecurityEventRow,
)
_DELETE_MODELS = tuple(reversed(_MODELS))


def _json_value(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    return value


def _canonical_payload(payload: dict[str, Any]) -> bytes:
    unsigned = {key: value for key, value in payload.items() if key != "sha256"}
    return json.dumps(
        unsigned, sort_keys=True, separators=(",", ":"), ensure_ascii=True
    ).encode("utf-8")


def _digest(payload: dict[str, Any]) -> str:
    return hashlib.sha256(_canonical_payload(payload)).hexdigest()


def create_backup(engine: Engine) -> dict[str, Any]:
    session_factory = create_session_factory(engine)
    tables: dict[str, list[dict[str, Any]]] = {}
    with session_factory() as session:
        for model in _MODELS:
            rows = session.execute(select(model)).scalars().all()
            tables[model.__tablename__] = [
                {
                    column.name: _json_value(getattr(row, column.name))
                    for column in model.__table__.columns
                }
                for row in rows
            ]
    payload: dict[str, Any] = {
        "schema_version": BACKUP_SCHEMA_VERSION,
        "application_version": __version__,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "tables": tables,
    }
    payload["sha256"] = _digest(payload)
    return payload


def write_backup(engine: Engine, output: Path) -> Path:
    output = output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_name(f".{output.name}.tmp")
    temporary.write_text(
        json.dumps(create_backup(engine), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    temporary.replace(output)
    return output


def _validate_backup(payload: dict[str, Any]) -> None:
    if payload.get("schema_version") != BACKUP_SCHEMA_VERSION:
        raise ValueError("unsupported DepotFlux backup schema")
    digest = payload.get("sha256")
    if not isinstance(digest, str) or not compare_digest_hex(digest, _digest(payload)):
        raise ValueError("backup digest does not match its contents")
    tables = payload.get("tables")
    expected = {model.__tablename__ for model in _MODELS}
    if not isinstance(tables, dict) or set(tables) != expected:
        raise ValueError("backup table set is incomplete or unexpected")


def compare_digest_hex(left: str, right: str) -> bool:
    return len(left) == 64 and len(right) == 64 and compare_digest(left, right)


def _database_row(model, row: dict[str, Any]) -> dict[str, Any]:
    expected_columns = {column.name: column for column in model.__table__.columns}
    if set(row) != set(expected_columns):
        raise ValueError(f"backup row for {model.__tablename__} has unexpected columns")
    restored: dict[str, Any] = {}
    for name, column in expected_columns.items():
        value = row[name]
        if value is not None and isinstance(column.type, DateTime):
            value = datetime.fromisoformat(value)
        restored[name] = value
    return restored


def restore_backup(engine: Engine, payload: dict[str, Any]) -> dict[str, int]:
    _validate_backup(payload)
    counts: dict[str, int] = {}
    with engine.begin() as connection:
        for model in _DELETE_MODELS:
            connection.execute(delete(model.__table__))
        for model in _MODELS:
            rows = [
                _database_row(model, row)
                for row in payload["tables"][model.__tablename__]
            ]
            if rows:
                connection.execute(insert(model.__table__), rows)
            counts[model.__tablename__] = len(rows)
    return counts


def read_backup(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"backup could not be read: {path}") from exc
    if not isinstance(payload, dict):
        raise ValueError("backup root must be a JSON object")
    _validate_backup(payload)
    return payload


def seed_demo(engine: Engine, *, wait: bool, timeout_seconds: float) -> dict[str, Any]:
    session_factory = create_session_factory(engine)
    descriptor = DemoInputRegistry().list()[0]
    with session_factory() as session:
        run, created = RunRepository(session).create(
            RunCreateRequest(
                run_type=RunType.DAY_AHEAD,
                optimization_mode=OptimizationMode.SELFISH,
                input_reference=descriptor.reference,
                input_sha256=descriptor.sha256,
                v2g_enabled=True,
                agent_backend=AgentBackend.RULE,
                scenario_ids=["nominal"],
            ),
            requested_by="depotflux-bootstrap",
            idempotency_key="depotflux-bootstrap-v1",
        )
    if wait:
        deadline = time.monotonic() + timeout_seconds
        while time.monotonic() < deadline:
            with session_factory() as session:
                run = RunRepository(session).get(run.id)
            if run.status.is_terminal:
                break
            time.sleep(0.5)
        else:
            raise TimeoutError("timed out waiting for the seeded optimization run")
    return {
        "run_id": str(run.id),
        "status": run.status.value,
        "created": created,
        "input_reference": descriptor.reference,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="depotflux", description="Administer the local DepotFlux demonstrator."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("version", help="Print the application version.")
    subparsers.add_parser("check-config", help="Validate and safely summarize configuration.")
    seed = subparsers.add_parser("seed", help="Queue the deterministic starter run.")
    seed.add_argument("--wait", action="store_true")
    seed.add_argument("--timeout", type=float, default=120.0)
    backup = subparsers.add_parser("backup", help="Create a verified application-data backup.")
    backup.add_argument("--output", type=Path, required=True)
    restore = subparsers.add_parser("restore", help="Replace application data from a backup.")
    restore.add_argument("--input", type=Path, required=True)
    restore.add_argument(
        "--confirm-restore",
        action="store_true",
        help="Required acknowledgement that current application data will be replaced.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "version":
        print(__version__)
        return 0
    settings = RuntimeSettings.from_environment()
    if args.command == "check-config":
        print(json.dumps(settings.safe_summary(), indent=2, sort_keys=True))
        return 0

    engine = create_database_engine(settings.database_url)
    try:
        ping_database(engine)
        if args.command == "seed":
            result = seed_demo(engine, wait=args.wait, timeout_seconds=args.timeout)
        elif args.command == "backup":
            result = {"backup": str(write_backup(engine, args.output))}
        elif args.command == "restore":
            if not args.confirm_restore:
                raise SystemExit("restore requires --confirm-restore")
            result = {"restored": restore_backup(engine, read_backup(args.input))}
        else:  # pragma: no cover - argparse guarantees the command
            raise AssertionError(args.command)
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0
    finally:
        engine.dispose()


if __name__ == "__main__":
    raise SystemExit(main())
