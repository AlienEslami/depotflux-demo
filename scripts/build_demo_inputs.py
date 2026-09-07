from __future__ import annotations

import copy
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from generate_benchmark_files import build_input_data


SOURCE = ROOT / "data" / "inputs"
OUTPUT = ROOT / "aggregator_demo" / "demo_data"
BASE_FLEET_SIZE = 8


def replicate_rows(rows: list[dict], factor: int, id_fields: tuple[str, ...]) -> list[dict]:
    replicated: list[dict] = []
    for block in range(factor):
        for row in rows:
            clone = copy.deepcopy(row)
            for field in id_fields:
                value = clone.get(field)
                if value is not None:
                    clone[field] = int(value) + block * BASE_FLEET_SIZE
            replicated.append(clone)
    return replicated


def build_scaled_input(base: dict, fleet_size: int) -> dict:
    factor = fleet_size // BASE_FLEET_SIZE
    scaled = copy.deepcopy(base)
    scaled["buses"] = replicate_rows(base["buses"], factor, ("bus_id",))
    scaled["chargers"] = replicate_rows(base["chargers"], factor, ("charger_id",))
    scaled["trip_time"] = replicate_rows(
        base["trip_time"], factor, ("trip_id", "bus_id")
    )
    scaled["realtime_state"] = replicate_rows(
        base["realtime_state"], factor, ("bus_id",)
    )
    return scaled


def write_json(path: Path, payload: dict) -> str:
    encoded = (json.dumps(payload, indent=2, sort_keys=True, allow_nan=False) + "\n").encode(
        "utf-8"
    )
    path.write_bytes(encoded)
    return hashlib.sha256(encoded).hexdigest()


def main() -> int:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    base, _ = build_input_data(
        SOURCE / "case_study_inputs.xlsx",
        SOURCE / "spot_prices.xlsx",
        SOURCE / "aggregator_tariffs.xlsx",
    )
    inputs = []
    for fleet_size in (8, 16, 32):
        filename = f"depot_a_{fleet_size}_v1.json"
        payload = build_scaled_input(base, fleet_size)
        digest = write_json(OUTPUT / filename, payload)
        inputs.append(
            {
                "reference": f"demo/depot-a-{fleet_size}-v1",
                "sha256": digest,
                "filename": filename,
                "depot": "depot-a",
                "fleet_size": fleet_size,
                "charger_count": len(payload["chargers"]),
                "trip_count": len(payload["trip_time"]),
                "horizon_intervals": 48,
                "interval_minutes": 30,
                "provenance": (
                    "Deterministic demonstrator fixture derived from the canonical "
                    "eight-bus research case; larger fleets use declared block replication."
                ),
            }
        )
    write_json(
        OUTPUT / "manifest.json",
        {
            "manifest_version": "v1",
            "inputs": inputs,
        },
    )
    print(OUTPUT / "manifest.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
