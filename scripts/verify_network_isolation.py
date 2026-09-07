from __future__ import annotations

import argparse
import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path


def _exec(compose: list[str], service: str, command: list[str]) -> dict:
    completed = subprocess.run(
        [*compose, "exec", "-T", service, *command],
        capture_output=True,
        text=True,
        check=False,
    )
    return {
        "service": service,
        "exit_code": completed.returncode,
        "stdout": completed.stdout.strip(),
        "stderr": completed.stderr.strip(),
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Verify that only the supervisory gateway can resolve the synthetic PLC."
    )
    parser.add_argument("--env-file", default=".demo/ot-lab.env")
    parser.add_argument("--output", default=".demo/network-isolation-evidence.json")
    args = parser.parse_args()
    compose = ["docker", "compose", "--env-file", args.env_file]
    blocked_script = (
        "import socket,sys;\n"
        "try: socket.getaddrinfo('plc-simulator',1502)\n"
        "except socket.gaierror: sys.exit(0)\n"
        "sys.exit(9)"
    )
    gateway_script = (
        "import socket; s=socket.create_connection(('plc-simulator',1502),2); s.close()"
    )
    checks = [
        _exec(compose, "api", ["python", "-c", blocked_script]),
        _exec(compose, "worker", ["python", "-c", blocked_script]),
        _exec(compose, "security-monitor", ["python", "-c", blocked_script]),
        _exec(compose, "ot-gateway", ["python", "-c", gateway_script]),
    ]
    for check in checks:
        check["passed"] = check["exit_code"] == 0
    evidence = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "claim": "API, worker, and monitor cannot resolve the PLC; the OT gateway can connect.",
        "simulated_only": True,
        "checks": checks,
        "passed": all(check["passed"] for check in checks),
    }
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(evidence, indent=2))
    return 0 if evidence["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
