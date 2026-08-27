from pathlib import Path

from fastapi.testclient import TestClient

from aelora_virtual_gateway.main import create_app
from aelora_virtual_gateway.storage import StateStore

ROOT = Path(__file__).resolve().parents[1]


def test_local_container_contract_preserves_state_and_limits_console_exposure() -> None:
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    compose = (ROOT / "compose.yaml").read_text(encoding="utf-8")

    assert "USER aelora" in dockerfile
    assert "AELORA_GATEWAY_DB=/app/data/gateway.db" in dockerfile
    assert "127.0.0.1:4100:4100" in compose
    assert "/app/data" in compose


def test_health_endpoint_is_independent_of_cloud_enrollment(tmp_path) -> None:
    app = create_app(StateStore(tmp_path / "gateway.db"), start_publisher=False)

    with TestClient(app) as client:
        response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.headers["cache-control"] == "no-store"
