import json
from datetime import UTC, datetime, timedelta

import httpx

from aelora_virtual_gateway.publisher import AeloraPublisher
from aelora_virtual_gateway.runtime import GatewayRuntime
from aelora_virtual_gateway.storage import StateStore


def test_enrollment_saves_gateway_identity_and_credential(tmp_path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/v1/gateway-enrollments"
        return httpx.Response(
            200,
            json={
                "data": {
                    "gatewayId": "gateway-1",
                    "credential": "aelora_credential_secret",
                    "expectedIntervalSec": 30,
                    "telemetryPath": "/api/v1/gateways/gateway-1/telemetry-batches",
                }
            },
        )

    store = StateStore(tmp_path / "gateway.db")
    publisher = AeloraPublisher(store, "http://aelora.test", transport=httpx.MockTransport(handler))
    publisher.enroll("aelora_enroll_token", "0.1.0")

    identity = store.load_identity()
    assert identity.gateway_id == "gateway-1"
    assert identity.credential == "aelora_credential_secret"


def test_failed_batch_is_buffered_and_replayed_with_bearer_auth(tmp_path) -> None:
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request)
        if len(calls) == 1:
            return httpx.Response(503, json={"error": "temporary"})
        assert request.headers["Authorization"] == "Bearer credential"
        return httpx.Response(202, json={"data": {"accepted": True}})

    store = StateStore(tmp_path / "gateway.db")
    store.save_identity("gateway-1", "credential", "/api/v1/gateways/gateway-1/telemetry-batches")
    publisher = AeloraPublisher(store, "http://aelora.test", transport=httpx.MockTransport(handler))
    batch = {"schemaVersion": "1.0", "batchId": "batch-1", "gatewayId": "gateway-1", "sequence": 1}

    assert publisher.publish(batch) is False
    assert store.pending_count() == 1
    assert publisher.flush_pending() == 1
    assert store.pending_count() == 0


def test_heartbeat_reports_gateway_health_when_telemetry_publishing_is_paused(tmp_path) -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(201, json={"data": {"accepted": True}})

    store = StateStore(tmp_path / "gateway.db")
    store.save_identity(
        "gateway-1",
        "credential",
        "/api/v1/gateways/gateway-1/telemetry-batches",
        "/api/v1/gateways/gateway-1/heartbeats",
    )
    publisher = AeloraPublisher(store, "http://aelora.test", transport=httpx.MockTransport(handler))

    assert publisher.heartbeat(
        publishing_enabled=False,
        queue_depth=2,
        device_count=7,
        heartbeat_id="52bcdd2b-cc48-4677-aac4-f987789724f5",
        sent_at=datetime(2026, 8, 11, 10, 30, tzinfo=UTC),
    ) is True

    assert requests[0].url.path == "/api/v1/gateways/gateway-1/heartbeats"
    assert requests[0].headers["Authorization"] == "Bearer credential"
    payload = json.loads(requests[0].content)
    assert payload["publishingEnabled"] is False
    assert payload["queueDepth"] == 2


def test_heartbeat_restores_an_expired_scenario_while_publishing_is_paused(tmp_path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/v1/gateways/gateway-1/heartbeats"
        return httpx.Response(201, json={"data": {"accepted": True}})

    store = StateStore(tmp_path / "gateway.db")
    store.save_identity(
        "gateway-1",
        "credential",
        "/api/v1/gateways/gateway-1/telemetry-batches",
        "/api/v1/gateways/gateway-1/heartbeats",
    )
    runtime = GatewayRuntime(
        store,
        "http://aelora.test",
        transport=httpx.MockTransport(handler),
    )
    runtime.plant.publishing_enabled = False
    runtime.start_scenario(
        "GRID_OUTAGE",
        duration_sec=10,
        now=datetime.now(UTC) - timedelta(seconds=20),
    )

    assert runtime.plant.grid.available is False
    assert runtime.heartbeat_once() is True
    assert runtime.plant.grid.available is True
    assert runtime.scenario_state() is None
