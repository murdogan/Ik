#!/usr/bin/env python3
"""Isolated executable smoke for the P4C HR-link and own-profile endpoints."""

# ruff: noqa: E402

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND_DIR = ROOT / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from tests._employee_account_link_support import (
    EMPLOYEE_ID,
    MEMBERSHIP_ID,
    employee_account_link_api,
    tenant_headers,
)


async def main() -> None:
    async with employee_account_link_api() as (client, _database):
        current = await client.get(
            f"/api/v1/employees/{EMPLOYEE_ID}/account-link",
            headers=tenant_headers(),
        )
        assert current.status_code == 200, current.text
        assert current.json()["data"]["link"] is None

        eligible = await client.get(
            f"/api/v1/employees/{EMPLOYEE_ID}/account-link/eligible-memberships",
            headers=tenant_headers(),
            params={"q": "ada@example.test", "limit": 20},
        )
        assert eligible.status_code == 200, eligible.text
        assert [row["membership_id"] for row in eligible.json()["data"]] == [str(MEMBERSHIP_ID)]

        linked = await client.patch(
            f"/api/v1/employees/{EMPLOYEE_ID}/account-link",
            headers=tenant_headers(),
            json={"membership_id": str(MEMBERSHIP_ID), "expected_version": None},
        )
        assert linked.status_code == 200, linked.text
        link = linked.json()["data"]["link"]
        assert link["membership"]["membership_id"] == str(MEMBERSHIP_ID)

        own = await client.get(
            "/api/v1/me/employee-profile",
            headers=tenant_headers(),
        )
        assert own.status_code == 200, own.text
        assert own.json()["data"]["availability"] == "available"
        assert own.json()["data"]["profile"]["core"]["id"] == str(EMPLOYEE_ID)

        unlinked = await client.patch(
            f"/api/v1/employees/{EMPLOYEE_ID}/account-link",
            headers=tenant_headers(),
            json={"membership_id": None, "expected_version": link["version"]},
        )
        assert unlinked.status_code == 200, unlinked.text
        assert unlinked.json()["data"]["link"] is None

        unavailable = await client.get(
            "/api/v1/me/employee-profile",
            headers=tenant_headers(),
        )
        assert unavailable.status_code == 200, unavailable.text
        assert unavailable.json()["data"] == {
            "availability": "unavailable",
            "membership_id": None,
            "profile": None,
        }

    print("P4C_API_SMOKE_OK")


if __name__ == "__main__":
    asyncio.run(main())
