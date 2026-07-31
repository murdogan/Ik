from datetime import UTC, datetime
from unittest.mock import Mock

import pytest
from app.core.config import Settings, get_settings
from app.main import create_app
from app.workers.notifications import run_worker
from pydantic import ValidationError

_RELEASE_SETTINGS = {
    "release_commit_sha": "a" * 40,
    "release_build_timestamp": datetime(2026, 7, 29, tzinfo=UTC),
}


@pytest.mark.parametrize("environment", ("staging", "prod"))
def test_protected_settings_reject_http_frontend_base_url(environment: str) -> None:
    with pytest.raises(
        ValidationError,
        match="Staging and production require an HTTPS frontend_base_url",
    ):
        Settings(
            _env_file=None,
            environment=environment,
            frontend_base_url="http://frontend.example.test",
            **_RELEASE_SETTINGS,
        )


@pytest.mark.parametrize("environment", ("local", "dev", "test"))
def test_local_and_test_settings_allow_http_frontend_base_url(environment: str) -> None:
    settings = Settings(
        _env_file=None,
        environment=environment,
        frontend_base_url="http://frontend.example.test/",
    )

    assert settings.frontend_base_url == "http://frontend.example.test"


@pytest.mark.parametrize("environment", ("dev", "staging", "prod"))
def test_nonlocal_settings_reject_fake_notification_email_capture(
    environment: str,
) -> None:
    protected_settings = (
        {
            "frontend_base_url": "https://frontend.example.test",
            **_RELEASE_SETTINGS,
        }
        if environment in {"staging", "prod"}
        else {}
    )

    with pytest.raises(
        ValidationError,
        match="Fake notification email capture is restricted to local and test environments",
    ):
        Settings(
            _env_file=None,
            environment=environment,
            notification_email_backend="fake",
            **protected_settings,
        )


@pytest.mark.parametrize("environment", ("local", "test"))
def test_local_and_test_settings_allow_fake_notification_email_capture(
    environment: str,
) -> None:
    settings = Settings(
        _env_file=None,
        environment=environment,
        notification_email_backend="fake",
    )

    assert settings.notification_email_backend == "fake"


@pytest.mark.parametrize("environment", ("staging", "prod"))
def test_protected_settings_allow_https_frontend_base_url(environment: str) -> None:
    settings = Settings(
        _env_file=None,
        environment=environment,
        frontend_base_url="https://frontend.example.test/",
        **_RELEASE_SETTINGS,
    )

    assert settings.frontend_base_url == "https://frontend.example.test"


def test_api_startup_rejects_protected_http_frontend_base_url(monkeypatch) -> None:
    _set_protected_http_environment(monkeypatch)

    try:
        with pytest.raises(
            ValidationError,
            match="Staging and production require an HTTPS frontend_base_url",
        ):
            create_app()
    finally:
        get_settings.cache_clear()


async def test_notification_worker_startup_rejects_protected_http_frontend_base_url(
    monkeypatch,
) -> None:
    runtime_factory = Mock()
    monkeypatch.setattr(
        "app.workers.notifications.create_database_runtime",
        runtime_factory,
    )
    _set_protected_http_environment(monkeypatch)

    try:
        with pytest.raises(
            ValidationError,
            match="Staging and production require an HTTPS frontend_base_url",
        ):
            await run_worker()
    finally:
        get_settings.cache_clear()

    runtime_factory.assert_not_called()


def _set_protected_http_environment(monkeypatch) -> None:
    monkeypatch.setenv("IK_ENVIRONMENT", "staging")
    monkeypatch.setenv("IK_RELEASE_COMMIT_SHA", "a" * 40)
    monkeypatch.setenv("IK_RELEASE_BUILD_TIMESTAMP", "2026-07-29T00:00:00Z")
    monkeypatch.setenv("IK_FRONTEND_BASE_URL", "http://frontend.example.test")
    get_settings.cache_clear()
