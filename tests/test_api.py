import httpx
from fastapi.testclient import TestClient

from aelora_virtual_gateway.main import create_app
from aelora_virtual_gateway.storage import StateStore


def test_operator_can_add_an_array_and_change_weather(tmp_path) -> None:
    app = create_app(StateStore(tmp_path / "gateway.db"), start_publisher=False)
    with TestClient(app) as client:
        added = client.post(
            "/api/arrays",
            json={
                "externalId": "garage",
                "name": "Garage array",
                "panelCount": 6,
                "ratedPowerW": 450,
            },
        )
        weather = client.patch("/api/environment", json={"weather": "RAINY", "hourOfDay": 12})
        state = client.get("/api/state")

    assert added.status_code == 201
    assert weather.status_code == 200
    assert state.status_code == 200
    assert any(array["externalId"] == "garage" for array in state.json()["plant"]["arrays"])
    assert state.json()["plant"]["environment"]["weather"] == "RAINY"


def test_operator_can_turn_device_communications_off_without_stopping_plant(tmp_path) -> None:
    app = create_app(StateStore(tmp_path / "gateway.db"), start_publisher=False)
    with TestClient(app) as client:
        response = client.patch("/api/devices/array-east/control", json={"communicationsEnabled": False})
        tick = client.post("/api/tick")

    assert response.status_code == 200
    array = next(device for device in tick.json()["devices"] if device["externalId"] == "array-east")
    assert array["connectivityStatus"] == "OFFLINE"
    assert tick.json()["siteSnapshot"]["pvPowerW"] > 0


def test_operator_can_pause_cloud_publishing(tmp_path) -> None:
    app = create_app(StateStore(tmp_path / "gateway.db"), start_publisher=False)
    with TestClient(app) as client:
        response = client.patch("/api/publishing", json={"enabled": False, "intervalSec": 60})
        state = client.get("/api/state")

    assert response.status_code == 200
    assert state.json()["plant"]["publishingEnabled"] is False
    assert state.json()["plant"]["publishIntervalSec"] == 60


def test_operator_can_apply_a_staged_credential_without_echoing_it(tmp_path) -> None:
    store = StateStore(tmp_path / "gateway.db")
    store.save_identity(
        "gateway-1",
        "old-credential-value-that-is-long-enough",
        "/api/v1/gateways/gateway-1/telemetry-batches",
        "/api/v1/gateways/gateway-1/heartbeats",
    )
    app = create_app(store, start_publisher=False)

    with TestClient(app) as client:
        response = client.patch(
            "/api/identity/credential",
            json={"credential": "new-credential-value-that-is-long-enough"},
        )
        state = client.get("/api/state")

    assert response.status_code == 200
    assert response.json() == {"updated": True}
    assert store.load_identity().credential == "new-credential-value-that-is-long-enough"
    assert "credential" not in str(state.json()).lower()


def test_operator_sees_redacted_exact_outbound_request(tmp_path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/heartbeats"):
            return httpx.Response(201, json={"data": {"accepted": True}})
        return httpx.Response(202, json={"data": {"accepted": True}})

    store = StateStore(tmp_path / "gateway.db")
    store.save_identity(
        "gateway-1",
        "super-secret-gateway-credential-value",
        "/api/v1/gateways/gateway-1/telemetry-batches",
        "/api/v1/gateways/gateway-1/heartbeats",
    )
    app = create_app(store, start_publisher=False, transport=httpx.MockTransport(handler))

    with TestClient(app) as client:
        published = client.post("/api/publish-now")
        state = client.get("/api/state").json()

    assert published.status_code == 200
    outbound = state["outbound"]
    assert outbound["request"]["headers"]["Authorization"] == "Bearer <redacted>"
    assert outbound["request"]["body"]["gatewayId"] == "gateway-1"
    assert "super-secret" not in str(outbound)


def test_operator_can_start_and_stop_a_timed_scenario(tmp_path) -> None:
    app = create_app(StateStore(tmp_path / "gateway.db"), start_publisher=False)

    with TestClient(app) as client:
        started = client.post("/api/scenarios", json={"code": "GRID_OUTAGE", "durationSec": 60})
        active = client.get("/api/state").json()
        stopped = client.delete("/api/scenarios/current")
        restored = client.get("/api/state").json()

    assert started.status_code == 201
    assert active["scenario"]["code"] == "GRID_OUTAGE"
    assert active["plant"]["grid"]["available"] is False
    assert stopped.status_code == 200
    assert restored["scenario"] is None
    assert restored["plant"]["grid"]["available"] is True
