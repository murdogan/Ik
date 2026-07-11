import asyncio
from collections.abc import Callable

import pytest
from app.platform.identity import PasswordManager


async def test_cancelled_password_operation_keeps_concurrency_slot_until_worker_finishes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    manager = PasswordManager(max_concurrent_operations=1)
    loop = asyncio.get_running_loop()
    submitted: list[asyncio.Future[str]] = []

    def submit_without_running(
        _executor: object,
        _operation: Callable[..., str],
        *_args: object,
    ) -> asyncio.Future[str]:
        future: asyncio.Future[str] = loop.create_future()
        submitted.append(future)
        return future

    monkeypatch.setattr(loop, "run_in_executor", submit_without_running)

    cancelled_waiter = asyncio.create_task(manager.hash_async("first password"))
    await asyncio.sleep(0)
    assert len(submitted) == 1

    cancelled_waiter.cancel()
    with pytest.raises(asyncio.CancelledError):
        await cancelled_waiter

    next_waiter = asyncio.create_task(manager.hash_async("second password"))
    await asyncio.sleep(0)
    assert len(submitted) == 1

    submitted[0].set_result("first hash")
    for _ in range(3):
        await asyncio.sleep(0)
        if len(submitted) == 2:
            break

    assert len(submitted) == 2
    submitted[1].set_result("second hash")
    assert await next_waiter == "second hash"
