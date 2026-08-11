from fastapi.testclient import TestClient

from aelora_virtual_gateway.main import create_app
from aelora_virtual_gateway.storage import StateStore


def test_operator_can_add_an_array_and_change_weather(tmp_path) -> None:
    app = create_app(StateStore(tmp_path / "gateway.db"), start_publisher=False)
    with TestClient(app) as client:
        added = client.post("/api/arrays", json={
            "externalId": "garage",
            "name": "Garage array",
            "panelCount": 6,
            "ratedPowerW": 450,
        })
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
