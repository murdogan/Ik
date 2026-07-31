from __future__ import annotations

import asyncio
import smtplib
import socket
import ssl
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from email.message import EmailMessage as StdlibEmailMessage
from hashlib import sha256
from unittest.mock import AsyncMock, MagicMock, Mock
from uuid import UUID

import pytest
from app.core.config import Settings
from app.modules.notifications.application.email import EmailDeliveryError, EmailMessage
from app.services import notification_email_provider as email_provider_module
from app.workers.notifications import NotificationWorker
from pydantic import ValidationError

TENANT_ID = UUID("aa000000-0000-4000-8000-000000000001")
DELIVERY_ID = UUID("aa000000-0000-4000-8000-000000000002")
OTHER_DELIVERY_ID = UUID("aa000000-0000-4000-8000-000000000003")
RECIPIENT_USER_ID = UUID("aa000000-0000-4000-8000-000000000004")
SMTP_PASSWORD = "unit-test-smtp-password"
RAW_ACTIVATION_TOKEN = "unit-test-raw-activation-token"


@pytest.fixture(autouse=True)
def forbid_real_smtp_network(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail_if_network_is_attempted(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("SMTP unit tests must never open a real network connection")

    monkeypatch.setattr(socket, "create_connection", fail_if_network_is_attempted)


def _production_settings(**overrides: object) -> Settings:
    values: dict[str, object] = {
        "_env_file": None,
        "environment": "prod",
        "release_commit_sha": "a" * 40,
        "release_build_timestamp": datetime(2026, 7, 29, tzinfo=UTC),
        "auth_signing_key": "production-test-signing-key",
        "frontend_base_url": "https://app.example.test",
    }
    values.update(overrides)
    return Settings(**values)


def _smtp_settings(**overrides: object) -> Settings:
    values: dict[str, object] = {
        "_env_file": None,
        "environment": "test",
        "auth_signing_key": "smtp-provider-test-signing-key-material",
        "notification_email_backend": "smtp",
        "notification_smtp_host": "smtp.example.test",
        "notification_smtp_port": 587,
        "notification_smtp_from_address": "notifications@example.test",
        "notification_smtp_username": "smtp-user",
        "notification_smtp_password": SMTP_PASSWORD,
        "notification_smtp_tls_mode": "starttls",
        "notification_smtp_timeout_seconds": 7.5,
    }
    values.update(overrides)
    return Settings(**values)


def _message(
    *,
    delivery_id: UUID = DELIVERY_ID,
    idempotency_key: str = "outbox-event:user:email",
    attempt_number: int = 1,
) -> EmailMessage:
    portal_url = f"https://app.example.test/activate#token={RAW_ACTIVATION_TOKEN}"
    return EmailMessage(
        tenant_id=TENANT_ID,
        delivery_id=delivery_id,
        recipient_user_id=RECIPIENT_USER_ID,
        recipient_email="initial.admin@example.test",
        subject="Your organization access is ready",
        body=f"Set up access to your organization. Open the HR portal: {portal_url}",
        portal_url=portal_url,
        idempotency_key=idempotency_key,
        attempt_number=attempt_number,
        message_id=(
            f"<{sha256(str(delivery_id).encode('ascii')).hexdigest()}@notifications.example.test>"
        ),
    )


def test_production_rejects_fake_email_delivery() -> None:
    with pytest.raises(ValidationError, match="Production notification email"):
        _production_settings(notification_email_backend="fake")


def test_production_accepts_disabled_or_valid_smtp_email_delivery() -> None:
    disabled = _production_settings(notification_email_backend="disabled")
    smtp = _production_settings(
        notification_email_backend="smtp",
        notification_smtp_host="smtp.example.test",
        notification_smtp_port=587,
        notification_smtp_from_address="notifications@example.test",
        notification_smtp_username="smtp-user",
        notification_smtp_password=SMTP_PASSWORD,
        notification_smtp_tls_mode="starttls",
        notification_smtp_timeout_seconds=7.5,
    )

    assert disabled.notification_email_backend == "disabled"
    assert smtp.notification_email_backend == "smtp"


@pytest.mark.parametrize(
    ("overrides", "expected_error_fragments"),
    [
        ({"notification_smtp_host": None}, ("smtp", "host")),
        ({"notification_smtp_host": ""}, ("smtp", "host")),
        ({"notification_smtp_host": "smtp.example.test\ninvalid"}, ("smtp", "host")),
        ({"notification_smtp_from_address": None}, ("smtp", "from")),
        ({"notification_smtp_from_address": "not-an-email-address"}, ("smtp", "from")),
        (
            {
                "notification_smtp_from_address": (
                    "notifications@example.test\nBcc: hidden@example.test"
                )
            },
            ("smtp", "from"),
        ),
        (
            {"notification_smtp_username": "smtp-user", "notification_smtp_password": None},
            ("username", "password"),
        ),
        (
            {"notification_smtp_username": None, "notification_smtp_password": SMTP_PASSWORD},
            ("username", "password"),
        ),
        (
            {"notification_smtp_username": None, "notification_smtp_password": ""},
            ("password", "empty"),
        ),
        ({"notification_smtp_port": 0}, ("notification_smtp_port",)),
        ({"notification_smtp_port": 65_536}, ("notification_smtp_port",)),
        ({"notification_smtp_timeout_seconds": 0}, ("notification_smtp_timeout_seconds",)),
        ({"notification_smtp_tls_mode": "opportunistic"}, ("notification_smtp_tls_mode",)),
    ],
)
def test_smtp_backend_rejects_missing_or_invalid_configuration(
    overrides: dict[str, object],
    expected_error_fragments: tuple[str, ...],
) -> None:
    with pytest.raises(ValidationError) as caught:
        _smtp_settings(**overrides)

    error_text = str(caught.value).lower()
    assert all(fragment.lower() in error_text for fragment in expected_error_fragments)


@pytest.mark.parametrize(
    ("environment", "backend", "fake_failures"),
    [
        ("local", "disabled", 0),
        ("local", "fake", 2),
        ("test", "disabled", 0),
        ("test", "fake", 2),
    ],
)
def test_local_and_test_preserve_disabled_and_fake_email_backends(
    environment: str,
    backend: str,
    fake_failures: int,
) -> None:
    settings = Settings(
        _env_file=None,
        environment=environment,
        notification_email_backend=backend,
        notification_fake_email_failures_before_success=fake_failures,
    )

    assert settings.notification_email_backend == backend
    assert settings.notification_fake_email_failures_before_success == fake_failures


def test_smtp_password_is_secret_backed_and_redacted() -> None:
    settings = _smtp_settings()

    assert settings.notification_smtp_password is not None
    assert settings.notification_smtp_password.get_secret_value() == SMTP_PASSWORD
    assert SMTP_PASSWORD not in repr(settings)


@dataclass(slots=True)
class _MockedSmtpRuntime:
    smtp_client: MagicMock
    smtp_factory: Mock
    smtp_ssl_factory: Mock
    tls_context: object
    tls_context_factory: Mock
    to_thread: AsyncMock


@pytest.fixture
def mocked_smtp_runtime(monkeypatch: pytest.MonkeyPatch) -> _MockedSmtpRuntime:
    smtp_client = MagicMock(name="smtp_client")
    smtp_client.__enter__.return_value = smtp_client
    smtp_client.__exit__.return_value = False
    smtp_client.send_message.return_value = {}
    smtp_factory = Mock(name="SMTP", return_value=smtp_client)
    smtp_ssl_factory = Mock(name="SMTP_SSL", return_value=smtp_client)
    tls_context = object()
    tls_context_factory = Mock(name="create_default_context", return_value=tls_context)

    async def run_inline(function, /, *args: object, **kwargs: object):
        return function(*args, **kwargs)

    to_thread = AsyncMock(name="to_thread", side_effect=run_inline)

    monkeypatch.setattr(smtplib, "SMTP", smtp_factory)
    monkeypatch.setattr(smtplib, "SMTP_SSL", smtp_ssl_factory)
    monkeypatch.setattr(ssl, "create_default_context", tls_context_factory)
    monkeypatch.setattr(asyncio, "to_thread", to_thread)
    # Also cover implementations which import the stdlib callables directly.
    monkeypatch.setattr(email_provider_module, "SMTP", smtp_factory, raising=False)
    monkeypatch.setattr(email_provider_module, "SMTP_SSL", smtp_ssl_factory, raising=False)
    monkeypatch.setattr(
        email_provider_module,
        "create_default_context",
        tls_context_factory,
        raising=False,
    )
    monkeypatch.setattr(email_provider_module, "to_thread", to_thread, raising=False)
    return _MockedSmtpRuntime(
        smtp_client=smtp_client,
        smtp_factory=smtp_factory,
        smtp_ssl_factory=smtp_ssl_factory,
        tls_context=tls_context,
        tls_context_factory=tls_context_factory,
        to_thread=to_thread,
    )


def _smtp_provider(
    *,
    tls_mode: str = "starttls",
    username: str | None = "smtp-user",
    password: str | None = SMTP_PASSWORD,
):
    provider_type = email_provider_module.SmtpEmailProvider
    return provider_type(
        host="smtp.example.test",
        port=587,
        from_address="notifications@example.test",
        username=username,
        password=password,
        tls_mode=tls_mode,
        timeout_seconds=7.5,
    )


def _assert_connection_settings(factory: Mock) -> None:
    factory.assert_called()
    positional = factory.call_args.args
    keywords = factory.call_args.kwargs
    host = keywords.get("host", positional[0] if len(positional) > 0 else None)
    port = keywords.get("port", positional[1] if len(positional) > 1 else None)
    timeout = keywords.get("timeout", positional[3] if len(positional) > 3 else None)
    assert host == "smtp.example.test"
    assert port == 587
    assert timeout == 7.5


async def test_starttls_smtp_delivery_runs_off_loop_and_authenticates(
    mocked_smtp_runtime: _MockedSmtpRuntime,
) -> None:
    provider = _smtp_provider()

    await provider.send(_message())

    _assert_connection_settings(mocked_smtp_runtime.smtp_factory)
    mocked_smtp_runtime.smtp_ssl_factory.assert_not_called()
    mocked_smtp_runtime.smtp_client.starttls.assert_called_once_with(
        context=mocked_smtp_runtime.tls_context
    )
    mocked_smtp_runtime.smtp_client.login.assert_called_once_with("smtp-user", SMTP_PASSWORD)
    mocked_smtp_runtime.to_thread.assert_awaited_once()
    sent_message = mocked_smtp_runtime.smtp_client.send_message.call_args.args[0]
    assert isinstance(sent_message, StdlibEmailMessage)
    assert sent_message["From"] == "notifications@example.test"
    assert sent_message["To"] == "initial.admin@example.test"
    assert sent_message["Subject"] == "Your organization access is ready"
    assert RAW_ACTIVATION_TOKEN in sent_message.get_content()


async def test_implicit_tls_uses_smtp_ssl_without_starttls(
    mocked_smtp_runtime: _MockedSmtpRuntime,
) -> None:
    provider = _smtp_provider(tls_mode="implicit")

    await provider.send(_message())

    mocked_smtp_runtime.smtp_factory.assert_not_called()
    _assert_connection_settings(mocked_smtp_runtime.smtp_ssl_factory)
    assert (
        mocked_smtp_runtime.smtp_ssl_factory.call_args.kwargs["context"]
        is mocked_smtp_runtime.tls_context
    )
    mocked_smtp_runtime.smtp_client.starttls.assert_not_called()
    mocked_smtp_runtime.smtp_client.login.assert_called_once_with("smtp-user", SMTP_PASSWORD)


async def test_smtp_delivery_without_credentials_skips_login(
    mocked_smtp_runtime: _MockedSmtpRuntime,
) -> None:
    provider = _smtp_provider(username=None, password=None)

    await provider.send(_message())

    mocked_smtp_runtime.smtp_client.starttls.assert_called_once_with(
        context=mocked_smtp_runtime.tls_context
    )
    mocked_smtp_runtime.smtp_client.login.assert_not_called()
    mocked_smtp_runtime.smtp_client.send_message.assert_called_once()


async def test_smtp_delivery_uses_deterministic_idempotency_headers_across_retries(
    mocked_smtp_runtime: _MockedSmtpRuntime,
) -> None:
    provider = _smtp_provider()
    first = _message()
    retry = replace(first, attempt_number=2)
    other_delivery = replace(
        first,
        delivery_id=OTHER_DELIVERY_ID,
        idempotency_key="other-outbox-event:user:email",
        message_id=(
            f"<{sha256(str(OTHER_DELIVERY_ID).encode('ascii')).hexdigest()}"
            "@notifications.example.test>"
        ),
    )

    await provider.send(first)
    await provider.send(retry)
    await provider.send(other_delivery)

    sent_messages = [
        call.args[0] for call in mocked_smtp_runtime.smtp_client.send_message.call_args_list
    ]
    first_message_id = sent_messages[0]["Message-ID"]
    assert first_message_id
    assert first_message_id == sent_messages[1]["Message-ID"]
    assert first_message_id != sent_messages[2]["Message-ID"]
    assert sent_messages[0]["X-Idempotency-Key"] == first.idempotency_key
    assert sent_messages[1]["X-Idempotency-Key"] == retry.idempotency_key
    header_text = "\n".join(f"{name}: {value}" for name, value in sent_messages[0].items())
    assert RAW_ACTIVATION_TOKEN not in header_text


@pytest.mark.parametrize(
    ("provider_error", "expected_code"),
    [
        (
            smtplib.SMTPRecipientsRefused(
                {"initial.admin@example.test": (550, b"private recipient detail")}
            ),
            "recipient_unavailable",
        ),
        (
            smtplib.SMTPSenderRefused(
                550,
                b"private sender detail",
                "notifications@example.test",
            ),
            "provider_rejected",
        ),
        (smtplib.SMTPDataError(554, b"private provider detail"), "provider_rejected"),
        (smtplib.SMTPServerDisconnected("private disconnect detail"), "provider_unavailable"),
        (TimeoutError("private timeout detail"), "provider_unavailable"),
        (OSError("private network detail"), "provider_unavailable"),
    ],
)
async def test_smtp_failures_map_to_safe_retry_errors(
    mocked_smtp_runtime: _MockedSmtpRuntime,
    provider_error: BaseException,
    expected_code: str,
) -> None:
    mocked_smtp_runtime.smtp_client.send_message.side_effect = provider_error
    provider = _smtp_provider()

    with pytest.raises(EmailDeliveryError) as caught:
        await provider.send(_message())

    assert caught.value.code == expected_code
    assert str(caught.value) == caught.value.safe_message
    assert "private" not in str(caught.value).lower()


async def test_smtp_authentication_failure_maps_to_safe_provider_rejection(
    mocked_smtp_runtime: _MockedSmtpRuntime,
) -> None:
    mocked_smtp_runtime.smtp_client.login.side_effect = smtplib.SMTPAuthenticationError(
        535,
        b"private authentication detail",
    )
    provider = _smtp_provider()

    with pytest.raises(EmailDeliveryError) as caught:
        await provider.send(_message())

    assert caught.value.code == "provider_rejected"
    assert "private" not in str(caught.value).lower()


def test_notification_worker_wires_validated_smtp_provider(
    mocked_smtp_runtime: _MockedSmtpRuntime,
) -> None:
    del mocked_smtp_runtime
    settings = _smtp_settings()
    worker = NotificationWorker(session_factory=Mock(), settings=settings)

    provider = worker._provider(Mock())

    provider_type = email_provider_module.SmtpEmailProvider
    assert isinstance(provider, provider_type)
