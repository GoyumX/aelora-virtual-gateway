import httpx

from aelora_virtual_gateway.publisher import AeloraPublisher
from aelora_virtual_gateway.storage import StateStore


def test_enrollment_saves_gateway_identity_and_credential(tmp_path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/v1/gateway-enrollments"
        return httpx.Response(200, json={"data": {
            "gatewayId": "gateway-1",
            "credential": "aelora_credential_secret",
            "expectedIntervalSec": 30,
            "telemetryPath": "/api/v1/gateways/gateway-1/telemetry-batches",
        }})

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
