from app.main import create_app
from fastapi.testclient import TestClient


def test_dashboard_summary_endpoint_returns_demo_cards() -> None:
    client = TestClient(create_app())

    response = client.get("/api/v1/dashboard/summary")

    assert response.status_code == 200
    assert response.json() == {
        "employee_count": 42,
        "pending_leave_requests": 6,
        "new_starters_this_month": 3,
        "open_tasks": 8,
        "department_distribution": [
            {"department": "Sales", "count": 12},
            {"department": "Operations", "count": 9},
        ],
    }


def test_dashboard_summary_is_exposed_in_openapi() -> None:
    client = TestClient(create_app())

    response = client.get("/openapi.json")

    assert response.status_code == 200
    assert "/api/v1/dashboard/summary" in response.json()["paths"]
