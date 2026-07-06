from __future__ import annotations

import json
import sys
import urllib.request

BASE_URL = sys.argv[1].rstrip("/") if len(sys.argv) > 1 else "http://127.0.0.1:8001"


def fetch(path: str) -> tuple[int, str, str]:
    request = urllib.request.Request(
        f"{BASE_URL}{path}",
        headers={"User-Agent": "ik-staging-smoke-test"},
    )
    with urllib.request.urlopen(request, timeout=10) as response:  # noqa: S310
        body = response.read().decode("utf-8")
        content_type = response.headers.get("content-type", "")
        return response.status, content_type, body


def main() -> None:
    landing_status, landing_type, landing_body = fetch("/")
    assert landing_status == 200, landing_status
    assert "text/html" in landing_type, landing_type
    assert "Wealthy Falcon HR" in landing_body
    assert "IK Platform" not in landing_body

    health_status, health_type, health_body = fetch("/health")
    assert health_status == 200, health_status
    assert "application/json" in health_type, health_type
    payload = json.loads(health_body)
    assert payload["status"] == "ok", payload
    assert payload["service"] == "IK Platform API", payload

    print(f"SMOKE_OK base_url={BASE_URL} service={payload['service']} env={payload['environment']}")


if __name__ == "__main__":
    main()
