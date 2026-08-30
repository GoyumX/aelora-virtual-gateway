from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from aelora_virtual_gateway.__main__ import resolve_port
from aelora_virtual_gateway.main import create_app
from aelora_virtual_gateway.storage import StateStore

ROOT = Path(__file__).resolve().parents[1]


def test_local_container_contract_preserves_state_and_limits_console_exposure() -> None:
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    compose = (ROOT / "compose.yaml").read_text(encoding="utf-8")
    entrypoint = (ROOT / "docker-entrypoint.sh").read_text(encoding="utf-8")

    assert 'ENTRYPOINT ["/usr/local/bin/gateway-entrypoint"]' in dockerfile
    assert 'exec gosu aelora "$@"' in entrypoint
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


def test_railway_port_takes_precedence_over_local_gateway_port(monkeypatch) -> None:
    monkeypatch.setenv("PORT", "53721")
    monkeypatch.setenv("AELORA_GATEWAY_PORT", "4100")

    assert resolve_port() == 53721


def test_local_console_remains_available_without_authentication(tmp_path, monkeypatch) -> None:
    monkeypatch.delenv("AELORA_GATEWAY_PUBLIC_DEMO", raising=False)
    monkeypatch.delenv("AELORA_GATEWAY_CONSOLE_USERNAME", raising=False)
    monkeypatch.delenv("AELORA_GATEWAY_CONSOLE_PASSWORD", raising=False)
    app = create_app(StateStore(tmp_path / "gateway.db"), start_publisher=False)

    with TestClient(app) as client:
        response = client.get("/api/state")

    assert response.status_code == 200


def test_public_demo_requires_authentication_for_console_and_controls(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("AELORA_GATEWAY_PUBLIC_DEMO", "true")
    monkeypatch.setenv("AELORA_GATEWAY_CONSOLE_USERNAME", "demo-operator")
    monkeypatch.setenv("AELORA_GATEWAY_CONSOLE_PASSWORD", "correct-horse-battery-staple")
    app = create_app(StateStore(tmp_path / "gateway.db"), start_publisher=False)

    with TestClient(app) as client:
        console = client.get("/")
        state = client.get("/api/state")
        mutation = client.post("/api/tick")
        health = client.get("/api/health")

    for response in (console, state, mutation):
        assert response.status_code == 401
        assert response.headers["www-authenticate"] == 'Basic realm="Aelora Virtual Gateway"'
        assert response.headers["cache-control"] == "no-store"
    assert health.status_code == 200


def test_public_demo_accepts_valid_console_credentials(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("AELORA_GATEWAY_PUBLIC_DEMO", "true")
    monkeypatch.setenv("AELORA_GATEWAY_CONSOLE_USERNAME", "demo-operator")
    monkeypatch.setenv("AELORA_GATEWAY_CONSOLE_PASSWORD", "correct-horse-battery-staple")
    app = create_app(StateStore(tmp_path / "gateway.db"), start_publisher=False)

    with TestClient(app) as client:
        response = client.get(
            "/api/state",
            auth=("demo-operator", "correct-horse-battery-staple"),
        )

    assert response.status_code == 200


@pytest.mark.parametrize(
    ("username", "password"),
    [
        ("", "correct-horse-battery-staple"),
        ("demo-operator", ""),
        ("demo-operator", "too-short"),
    ],
)
def test_public_demo_refuses_missing_or_weak_credentials(
    tmp_path, monkeypatch, username: str, password: str
) -> None:
    monkeypatch.setenv("AELORA_GATEWAY_PUBLIC_DEMO", "true")
    monkeypatch.setenv("AELORA_GATEWAY_CONSOLE_USERNAME", username)
    monkeypatch.setenv("AELORA_GATEWAY_CONSOLE_PASSWORD", password)

    with pytest.raises(ValueError, match="Public demo mode requires"):
        create_app(StateStore(tmp_path / "gateway.db"), start_publisher=False)
