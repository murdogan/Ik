from app.core.config import Settings
from app.main import create_app
from fastapi.testclient import TestClient


def test_health_endpoint_returns_service_status() -> None:
    client = TestClient(create_app())

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "IK Platform API",
        "version": "0.1.0",
        "environment": "local",
    }


def test_health_endpoint_uses_application_settings() -> None:
    settings = Settings(
        _env_file=None,
        app_name="Configured API",
        app_version="9.8.7",
        environment="test",
        database_url="sqlite+aiosqlite:///:memory:",
    )
    client = TestClient(create_app(settings=settings))

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "Configured API",
        "version": "9.8.7",
        "environment": "test",
    }
