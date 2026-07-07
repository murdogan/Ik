from app.main import create_app
from fastapi.testclient import TestClient


def test_landing_page_returns_staging_html() -> None:
    client = TestClient(create_app())

    response = client.get("/")

    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "Wealthy Falcon HR" in response.text
    assert "IK Platform" not in response.text
    assert "İnsan kaynaklarını karmaşadan çıkarıp tek ekranda yönetin." in response.text
    assert "Staging / Test Ortamı" in response.text
    assert "/health" in response.text
