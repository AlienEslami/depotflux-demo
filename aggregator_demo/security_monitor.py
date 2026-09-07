from __future__ import annotations

import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.error import URLError
from urllib.request import urlopen


API_URL = os.environ.get("DEMO_API_URL", "http://api:8000").rstrip("/")


class MonitorHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802 - stdlib handler API
        if self.path == "/health/live":
            self._json(200, {"service": "depotflux-security-monitor", "status": "ok"})
            return
        if self.path != "/metrics/security-summary":
            self._json(404, {"code": "not_found"})
            return
        try:
            with urlopen(f"{API_URL}/api/v1/security/events?limit=200", timeout=2) as response:
                events = json.load(response)["items"]
        except (OSError, URLError, ValueError, KeyError):
            self._json(503, {"status": "unavailable", "source": "security-events"})
            return
        summary: dict[str, int | str | bool] = {
            "status": "ok",
            "simulated_only": True,
            "event_count": len(events),
        }
        for event in events:
            key = f"reason_{event['reason_code']}"
            summary[key] = int(summary.get(key, 0)) + 1
        self._json(200, summary)

    def log_message(self, format: str, *args) -> None:
        return

    def _json(self, status_code: int, payload: dict) -> None:
        body = json.dumps(payload, sort_keys=True).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def main() -> int:
    host = os.environ.get("DEMO_MONITOR_HOST", "0.0.0.0")
    port = int(os.environ.get("DEMO_MONITOR_PORT", "9100"))
    ThreadingHTTPServer((host, port), MonitorHandler).serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
