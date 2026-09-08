from __future__ import annotations

from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from aggregator_demo.app import create_app
from aggregator_demo.observability import RequestMetrics


def test_api_propagates_valid_correlation_id_and_replaces_invalid_value(tmp_path) -> None:
    app = create_app(database_url=f"sqlite:///{tmp_path / 'observability.db'}")
    with TestClient(app) as client:
        requested = str(uuid4())
        response = client.get("/health/live", headers={"X-Correlation-ID": requested})
        assert response.headers["X-Correlation-ID"] == requested

        replaced = client.get("/health/live", headers={"X-Correlation-ID": "log\ninjection"})
        assert replaced.headers["X-Correlation-ID"] != "log\ninjection"
        UUID(replaced.headers["X-Correlation-ID"])

        metrics = client.get("/metrics")
        assert metrics.status_code == 200
        assert 'route="/health/live"' in metrics.text
        assert "depotflux_http_requests_total" in metrics.text


def test_request_metrics_use_bounded_route_labels() -> None:
    metrics = RequestMetrics()
    metrics.record(
        method="GET", route="/api/v1/runs/{run_id}", status_code=200, duration_seconds=0.1
    )
    metrics.record(
        method="GET", route="/api/v1/runs/{run_id}", status_code=200, duration_seconds=0.2
    )
    snapshot = metrics.snapshot()
    assert snapshot[0].count == 2
    assert snapshot[0].duration_seconds_sum == pytest.approx(0.3)
