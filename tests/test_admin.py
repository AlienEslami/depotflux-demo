from __future__ import annotations

import json

import pytest

from aggregator_demo.admin import create_backup, read_backup, restore_backup, seed_demo, write_backup
from aggregator_demo.database import create_database_engine, create_schema, create_session_factory
from aggregator_demo.run_repository import RunRepository


def test_seed_is_idempotent_and_backup_round_trips(tmp_path) -> None:
    engine = create_database_engine(f"sqlite:///{tmp_path / 'admin.db'}")
    create_schema(engine)
    first = seed_demo(engine, wait=False, timeout_seconds=0)
    second = seed_demo(engine, wait=False, timeout_seconds=0)
    assert first["created"] is True
    assert second["created"] is False
    assert second["run_id"] == first["run_id"]

    output = write_backup(engine, tmp_path / "backup.json")
    payload = read_backup(output)
    assert payload["schema_version"] == "depotflux-backup-v1"
    assert len(payload["tables"]["optimization_runs"]) == 1

    counts = restore_backup(engine, payload)
    assert counts["optimization_runs"] == 1
    with create_session_factory(engine)() as session:
        assert len(RunRepository(session).list(limit=10, offset=0)) == 1
    engine.dispose()


def test_backup_rejects_tampering(tmp_path) -> None:
    engine = create_database_engine(f"sqlite:///{tmp_path / 'tamper.db'}")
    create_schema(engine)
    payload = create_backup(engine)
    payload["application_version"] = "tampered"
    path = tmp_path / "tampered.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ValueError, match="digest"):
        read_backup(path)
    engine.dispose()
