from __future__ import annotations

import json
import logging
import threading
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from time import perf_counter
from uuid import UUID, uuid4


def correlation_id(value: str | None) -> str:
    if value:
        try:
            return str(UUID(value))
        except ValueError:
            pass
    return str(uuid4())


class JsonLogFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname.lower(),
            "logger": record.name,
            "message": record.getMessage(),
        }
        for field in (
            "correlation_id",
            "method",
            "route",
            "status_code",
            "duration_ms",
            "actor",
            "role",
            "run_id",
            "worker_id",
            "run_status",
            "failure_code",
        ):
            value = getattr(record, field, None)
            if value is not None:
                payload[field] = value
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, separators=(",", ":"), ensure_ascii=True)


def configure_logging(level: str) -> None:
    logger = logging.getLogger("depotflux")
    logger.setLevel(level)
    logger.propagate = False
    if not any(getattr(handler, "_depotflux_json", False) for handler in logger.handlers):
        handler = logging.StreamHandler()
        handler.setFormatter(JsonLogFormatter())
        handler._depotflux_json = True  # type: ignore[attr-defined]
        logger.addHandler(handler)


@dataclass(frozen=True)
class RequestMetric:
    method: str
    route: str
    status_code: int
    count: int
    duration_seconds_sum: float


class RequestMetrics:
    """Small in-process metrics registry with bounded route labels."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._started = perf_counter()
        self._count: dict[tuple[str, str, int], int] = defaultdict(int)
        self._duration: dict[tuple[str, str, int], float] = defaultdict(float)

    def record(
        self, *, method: str, route: str, status_code: int, duration_seconds: float
    ) -> None:
        key = (method.upper(), route, status_code)
        with self._lock:
            self._count[key] += 1
            self._duration[key] += max(0.0, duration_seconds)

    def snapshot(self) -> list[RequestMetric]:
        with self._lock:
            return [
                RequestMetric(
                    method=method,
                    route=route,
                    status_code=status_code,
                    count=self._count[(method, route, status_code)],
                    duration_seconds_sum=self._duration[(method, route, status_code)],
                )
                for method, route, status_code in sorted(self._count)
            ]

    def render_prometheus(self) -> str:
        lines = [
            "# HELP depotflux_up Whether the API process is running.",
            "# TYPE depotflux_up gauge",
            "depotflux_up 1",
            "# HELP depotflux_process_uptime_seconds API process uptime.",
            "# TYPE depotflux_process_uptime_seconds gauge",
            f"depotflux_process_uptime_seconds {max(0.0, perf_counter() - self._started):.6f}",
            "# HELP depotflux_http_requests_total HTTP requests by route and status.",
            "# TYPE depotflux_http_requests_total counter",
            "# HELP depotflux_http_request_duration_seconds_total Cumulative request duration.",
            "# TYPE depotflux_http_request_duration_seconds_total counter",
        ]
        for metric in self.snapshot():
            labels = (
                f'method="{metric.method}",route="{metric.route}",'
                f'status="{metric.status_code}"'
            )
            lines.append(f"depotflux_http_requests_total{{{labels}}} {metric.count}")
            lines.append(
                "depotflux_http_request_duration_seconds_total"
                f"{{{labels}}} {metric.duration_seconds_sum:.6f}"
            )
        return "\n".join(lines) + "\n"
