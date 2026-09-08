from __future__ import annotations

import argparse
import json
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

import httpx


def _read_environment(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if line and not line.lstrip().startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            values[key.strip()] = value.strip()
    return values


def _role_headers(environment: dict[str, str], role: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {environment[f'DEMO_{role.upper()}_API_KEY']}"
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run a local software-only OT smoke demo.")
    parser.add_argument("--env-file", default=".demo/ot-lab.env")
    parser.add_argument("--output", default=".demo/evidence/compose-smoke.json")
    args = parser.parse_args()
    environment = _read_environment(Path(args.env_file))
    base_url = "http://127.0.0.1:8000"
    control_headers = {
        **_role_headers(environment, "operator"),
        "X-Control-Key": environment["DEMO_CONTROL_API_KEY"],
    }
    evidence: dict = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "simulated_only": True,
        "direct_asset_control": False,
        "checks": [],
    }
    with httpx.Client(base_url=base_url, timeout=10) as client:
        health = client.get("/health/ready")
        health.raise_for_status()
        inputs = client.get(
            "/api/v1/inputs", headers=_role_headers(environment, "operator")
        ).json()["items"]
        selected = inputs[0]
        created = client.post(
            "/api/v1/runs",
            headers={
                **_role_headers(environment, "operator"),
                "Idempotency-Key": str(uuid4()),
            },
            json={
                "run_type": "day_ahead",
                "optimization_mode": "selfish",
                "input_reference": selected["reference"],
                "input_sha256": selected["sha256"],
                "v2g_enabled": True,
                "agent_backend": "rule",
                "scenario_ids": ["nominal"],
            },
        )
        created.raise_for_status()
        run_id = created.json()["id"]
        deadline = time.monotonic() + 90
        while time.monotonic() < deadline:
            run = client.get(
                f"/api/v1/runs/{run_id}",
                headers=_role_headers(environment, "operator"),
            ).json()
            if run["status"] in {"succeeded", "failed", "infeasible", "timed_out"}:
                break
            time.sleep(0.5)
        if run["status"] != "succeeded":
            raise RuntimeError(f"compose smoke optimization ended as {run['status']}")
        approval = client.post(
            f"/api/v1/runs/{run_id}/approval",
            headers=_role_headers(environment, "approver"),
            json={"decision": "approved", "note": "software-only smoke evidence"},
        )
        approval.raise_for_status()
        endpoint = f"/api/v1/runs/{run_id}/dispatch-simulations"
        command_id = str(uuid4())
        accepted = client.post(
            endpoint,
            headers=control_headers,
            json={"interval_index": 1, "command_id": command_id},
        )
        accepted.raise_for_status()
        evidence["checks"].append(
            {"scenario": "valid_approved_dispatch", "passed": True, "response": accepted.json()}
        )
        replay = client.post(
            endpoint,
            headers=control_headers,
            json={"interval_index": 1, "command_id": command_id},
        )
        evidence["checks"].append(
            {
                "scenario": "replayed_command",
                "passed": replay.status_code == 409 and replay.json()["reason_code"] == "replayed_command",
                "response": replay.json(),
            }
        )
        issued = datetime.now(timezone.utc) - timedelta(minutes=2)
        stale = client.post(
            endpoint,
            headers=control_headers,
            json={
                "interval_index": 1,
                "issued_at": issued.isoformat(),
                "expires_at": (issued + timedelta(seconds=20)).isoformat(),
            },
        )
        evidence["checks"].append(
            {
                "scenario": "stale_command",
                "passed": stale.status_code == 409 and stale.json()["reason_code"] == "stale_command",
                "response": stale.json(),
            }
        )
        invalid = client.post(
            endpoint,
            headers={
                **_role_headers(environment, "operator"),
                "X-Control-Key": "deliberately-wrong",
            },
            json={"interval_index": 1},
        )
        evidence["checks"].append(
            {
                "scenario": "invalid_credential",
                "passed": invalid.status_code == 401 and invalid.json()["reason_code"] == "invalid_credential",
                "response": invalid.json(),
            }
        )
        outside = client.post(
            endpoint,
            headers=control_headers,
            json={"interval_index": selected["horizon_intervals"] + 1},
        )
        evidence["checks"].append(
            {
                "scenario": "interval_outside_horizon",
                "passed": outside.status_code == 409 and outside.json()["reason_code"] == "interval_in_horizon",
                "response": outside.json(),
            }
        )
        safe = client.post(
            "/api/v1/emergency-safe-state",
            headers={
                **_role_headers(environment, "admin"),
                "X-Emergency-Key": environment["DEMO_EMERGENCY_API_KEY"],
            },
            json={"reason": "deterministic local recovery drill"},
        )
        safe.raise_for_status()
        evidence["checks"].append(
            {"scenario": "emergency_safe_state", "passed": True, "response": safe.json()}
        )
        evidence["security_events"] = client.get(
            "/api/v1/security/events?limit=50",
            headers=_role_headers(environment, "auditor"),
        ).json()["items"]
        evidence["run_id"] = run_id
    evidence["passed"] = all(check["passed"] for check in evidence["checks"])
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"passed": evidence["passed"], "output": str(output)}, indent=2))
    return 0 if evidence["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
