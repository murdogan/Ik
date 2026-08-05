import asyncio
from datetime import UTC, datetime, timedelta
from pathlib import Path
from urllib.parse import parse_qs, urlsplit
from uuid import UUID

from app.core.config import Settings
from app.db.base import Base
from app.models.auth import UserActivationToken
from app.models.leave import OutboxEvent
from app.models.notification import (
    EmailCapture,
    Notification,
    NotificationDelivery,
    NotificationDeliveryStatus,
    OutboxEventConsumption,
)
from app.models.tenant import Tenant, TenantFeatureFlag, TenantStatus
from app.models.user import User, UserStatus
from app.modules.core.domain.feature_flags import FeatureFlagKey
from app.platform.identity import (
    ActivationDeliveryTokenCodec,
    hash_activation_token,
    manual_activation_delivery_event_id,
    parse_activation_token,
)
from app.services.notification_email_provider import (
    EmailDeliveryError,
    EmailMessage,
    EmailProvider,
    LocalCaptureEmailProvider,
)
from app.workers.notifications import NotificationWorker
from sqlalchemy import event, select
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import StaticPool

TENANT_ID = UUID("a7000000-0000-4000-8000-000000000001")
USER_ID = UUID("a7000000-0000-4000-8000-000000000002")
OUTBOX_ID = UUID("a7000000-0000-4000-8000-000000000003")
ACTIVATION_ID = UUID("a7000000-0000-4000-8000-000000000004")
ORDINARY_OUTBOX_ID = UUID("a7000000-0000-4000-8000-000000000005")


class _AcceptThenFailOnceEmailProvider:
    def __init__(
        self,
        session: AsyncSession,
        recorded_messages: list[EmailMessage],
    ) -> None:
        self._session = session
        self._capture = LocalCaptureEmailProvider(session)
        self._recorded_messages = recorded_messages

    async def send(self, message: EmailMessage, /) -> None:
        assert not self._session.in_transaction()
        self._recorded_messages.append(message)
        if len(self._recorded_messages) == 1:
            raise EmailDeliveryError("provider_rejected")
        await self._capture.send(message)


class _AmbiguousDeliveryNotificationWorker(NotificationWorker):
    def __init__(
        self,
        *,
        session_factory: async_sessionmaker[AsyncSession],
        settings: Settings,
        recorded_messages: list[EmailMessage],
    ) -> None:
        super().__init__(session_factory=session_factory, settings=settings)
        self._recorded_messages = recorded_messages

    def _provider(self, session: AsyncSession) -> EmailProvider:
        return _AcceptThenFailOnceEmailProvider(session, self._recorded_messages)


class _CrashAfterAcceptEmailProvider:
    def __init__(
        self,
        session: AsyncSession,
        recorded_messages: list[EmailMessage],
    ) -> None:
        self._session = session
        self._recorded_messages = recorded_messages

    async def send(self, message: EmailMessage, /) -> None:
        assert not self._session.in_transaction()
        self._recorded_messages.append(message)
        raise RuntimeError("simulated process crash after provider acceptance")


class _CrashAfterAcceptNotificationWorker(NotificationWorker):
    def __init__(
        self,
        *,
        session_factory: async_sessionmaker[AsyncSession],
        settings: Settings,
        recorded_messages: list[EmailMessage],
    ) -> None:
        super().__init__(session_factory=session_factory, settings=settings)
        self._recorded_messages = recorded_messages

    def _provider(self, session: AsyncSession) -> EmailProvider:
        return _CrashAfterAcceptEmailProvider(session, self._recorded_messages)


class _SuccessfulEmailProvider:
    def __init__(
        self,
        session: AsyncSession,
        recorded_messages: list[EmailMessage],
    ) -> None:
        self._session = session
        self._recorded_messages = recorded_messages

    async def send(self, message: EmailMessage, /) -> None:
        assert not self._session.in_transaction()
        self._recorded_messages.append(message)


class _SuccessfulNotificationWorker(NotificationWorker):
    def __init__(
        self,
        *,
        session_factory: async_sessionmaker[AsyncSession],
        settings: Settings,
        recorded_messages: list[EmailMessage],
    ) -> None:
        super().__init__(session_factory=session_factory, settings=settings)
        self._recorded_messages = recorded_messages

    def _provider(self, session: AsyncSession) -> EmailProvider:
        return _SuccessfulEmailProvider(session, self._recorded_messages)


class _BlockingEmailProvider:
    def __init__(
        self,
        session: AsyncSession,
        *,
        started: asyncio.Event,
        release: asyncio.Event,
        recorded_messages: list[EmailMessage],
    ) -> None:
        self._session = session
        self._started = started
        self._release = release
        self._recorded_messages = recorded_messages

    async def send(self, message: EmailMessage, /) -> None:
        assert not self._session.in_transaction()
        self._recorded_messages.append(message)
        self._started.set()
        await self._release.wait()


class _BlockingNotificationWorker(NotificationWorker):
    def __init__(
        self,
        *,
        session_factory: async_sessionmaker[AsyncSession],
        settings: Settings,
        started: asyncio.Event,
        release: asyncio.Event,
        recorded_messages: list[EmailMessage],
    ) -> None:
        super().__init__(session_factory=session_factory, settings=settings)
        self._started = started
        self._release = release
        self._recorded_messages = recorded_messages

    def _provider(self, session: AsyncSession) -> EmailProvider:
        return _BlockingEmailProvider(
            session,
            started=self._started,
            release=self._release,
            recorded_messages=self._recorded_messages,
        )


async def _worker_runtime(
    database_path: Path | None = None,
) -> tuple[
    AsyncEngine,
    async_sessionmaker[AsyncSession],
    Settings,
]:
    if database_path is None:
        engine = create_async_engine(
            "sqlite+aiosqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
            use_insertmanyvalues=False,
        )
    else:
        engine = create_async_engine(
            f"sqlite+aiosqlite:///{database_path}",
            use_insertmanyvalues=False,
        )

    @event.listens_for(engine.sync_engine, "connect")
    def register_sqlite_now(dbapi_connection, _connection_record) -> None:
        dbapi_connection.create_function(
            "now",
            0,
            lambda: datetime.now(UTC).isoformat(),
        )

    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    async with sessions.begin() as session:
        session.add_all(
            [
                Tenant(
                    id=TENANT_ID,
                    slug="initial-admin-worker",
                    name="Initial Admin Worker",
                    status=TenantStatus.TRIAL.value,
                    plan_code="core",
                    data_region="tr-1",
                    locale="tr-TR",
                    timezone="Europe/Istanbul",
                ),
                TenantFeatureFlag(
                    tenant_id=TENANT_ID,
                    key=FeatureFlagKey.NOTIFICATIONS.value,
                    enabled=False,
                ),
                User(
                    id=USER_ID,
                    tenant_id=TENANT_ID,
                    email="initial.admin@example.test",
                    full_name="Initial Admin",
                    status=UserStatus.INVITED.value,
                    password_hash=None,
                ),
                UserActivationToken(
                    id=ACTIVATION_ID,
                    tenant_id=TENANT_ID,
                    user_id=USER_ID,
                    token_hash="0" * 64,
                    created_at=datetime.now(UTC) - timedelta(days=10),
                    expires_at=datetime.now(UTC) - timedelta(days=9),
                ),
                OutboxEvent(
                    id=OUTBOX_ID,
                    tenant_id=TENANT_ID,
                    aggregate_type="identity_membership",
                    aggregate_id=USER_ID,
                    event_type="identity.initial_admin_invited",
                    payload={
                        "recipient_user_id": str(USER_ID),
                        "activation_id": str(ACTIVATION_ID),
                    },
                    source_key=f"identity.initial_admin_invited:{USER_ID}",
                    occurred_at=datetime.now(UTC),
                ),
                OutboxEvent(
                    id=ORDINARY_OUTBOX_ID,
                    tenant_id=TENANT_ID,
                    aggregate_type="leave_balance",
                    aggregate_id=USER_ID,
                    event_type="leave.balance_adjusted",
                    payload={},
                    source_key=f"leave.balance_adjusted:{USER_ID}",
                    occurred_at=datetime.now(UTC),
                ),
            ]
        )

    settings = Settings(
        _env_file=None,
        environment="test",
        database_url="sqlite+aiosqlite:///:memory:",
        frontend_base_url="https://frontend.example.test",
        auth_signing_key="initial-admin-worker-test-signing-key",
        notification_email_backend="fake",
    )
    return engine, sessions, settings


async def test_worker_delivers_initial_admin_when_notifications_are_disabled() -> None:
    engine, sessions, settings = await _worker_runtime()
    recorded_messages: list[EmailMessage] = []
    worker = _AmbiguousDeliveryNotificationWorker(
        session_factory=sessions,
        settings=settings,
        recorded_messages=recorded_messages,
    )

    try:
        assert await worker.run_once() == 2
        assert len(recorded_messages) == 1

        async with sessions.begin() as session:
            notification = await session.scalar(
                select(Notification).where(Notification.source_event_id == OUTBOX_ID)
            )
            initial_consumption = await session.scalar(
                select(OutboxEventConsumption).where(
                    OutboxEventConsumption.source_event_id == OUTBOX_ID
                )
            )
            ordinary_consumption = await session.scalar(
                select(OutboxEventConsumption).where(
                    OutboxEventConsumption.source_event_id == ORDINARY_OUTBOX_ID
                )
            )
            capture = await session.scalar(
                select(EmailCapture).where(EmailCapture.tenant_id == TENANT_ID)
            )
            activation = await session.get(UserActivationToken, ACTIVATION_ID)
            delivery = await session.scalar(
                select(NotificationDelivery).where(
                    NotificationDelivery.source_event_id == OUTBOX_ID,
                    NotificationDelivery.status == NotificationDeliveryStatus.RETRY.value,
                )
            )
            assert initial_consumption is not None
            assert ordinary_consumption is None
            assert capture is None
            assert activation is not None
            first_attempt_hash = activation.token_hash
            assert delivery is not None
            delivery.next_attempt_at = datetime.now(UTC) - timedelta(seconds=1)

        worker = _AmbiguousDeliveryNotificationWorker(
            session_factory=sessions,
            settings=settings,
            recorded_messages=recorded_messages,
        )
        assert await worker.run_once() == 1

        async with sessions() as session:
            capture = await session.scalar(
                select(EmailCapture).where(EmailCapture.tenant_id == TENANT_ID)
            )
            activation = await session.get(UserActivationToken, ACTIVATION_ID)
            ordinary_consumption = await session.scalar(
                select(OutboxEventConsumption).where(
                    OutboxEventConsumption.source_event_id == ORDINARY_OUTBOX_ID
                )
            )

        assert notification is not None
        assert notification.notification_type == "initial_admin_invitation"
        assert notification.portal_path == "/activate"
        assert capture is not None
        assert capture.recipient_email == "initial.admin@example.test"
        assert capture.portal_url.startswith("https://frontend.example.test/activate#token=")
        raw_token = parse_qs(urlsplit(capture.portal_url).fragment)["token"][0]
        parsed = parse_activation_token(raw_token)
        assert parsed.tenant_id == TENANT_ID
        assert activation is not None
        assert ordinary_consumption is None
        assert activation.token_hash == first_attempt_hash
        assert activation.token_hash == hash_activation_token(raw_token)
        assert len(recorded_messages) == 2
        first_message, retry_message = recorded_messages
        assert first_message.portal_url == retry_message.portal_url == capture.portal_url
        assert first_message.body == retry_message.body == capture.body
        assert first_message.idempotency_key == retry_message.idempotency_key
        expires_at = activation.expires_at
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=UTC)
        assert expires_at > datetime.now(UTC) + timedelta(hours=47)
        assert (
            "token"
            not in str(
                {
                    "recipient_user_id": str(USER_ID),
                    "activation_id": str(ACTIVATION_ID),
                }
            ).lower()
        )
    finally:
        await engine.dispose()


async def test_worker_preserves_manual_link_hash_and_expiry_when_material_is_already_deterministic(
) -> None:
    engine, sessions, settings = await _worker_runtime()
    signing_key = settings.auth_signing_key
    assert signing_key is not None
    codec = ActivationDeliveryTokenCodec(
        signing_key.get_secret_value().encode("utf-8")
    )
    manual_token = codec.issue(TENANT_ID, ACTIVATION_ID)
    manual_expiry = datetime.now(UTC) + timedelta(hours=23)
    recorded_messages: list[EmailMessage] = []

    try:
        async with sessions.begin() as session:
            activation = await session.get(UserActivationToken, ACTIVATION_ID)
            assert activation is not None
            activation.token_hash = manual_token.token_hash
            activation.expires_at = manual_expiry

        worker = _SuccessfulNotificationWorker(
            session_factory=sessions,
            settings=settings,
            recorded_messages=recorded_messages,
        )
        assert await worker.run_once() == 2
        assert len(recorded_messages) == 1
        delivered_token = parse_qs(
            urlsplit(recorded_messages[0].portal_url).fragment
        )["token"][0]
        assert delivered_token == manual_token.raw_token

        async with sessions() as session:
            activation = await session.get(UserActivationToken, ACTIVATION_ID)

        assert activation is not None
        persisted_expiry = activation.expires_at
        if persisted_expiry.tzinfo is None:
            persisted_expiry = persisted_expiry.replace(tzinfo=UTC)
        assert activation.token_hash == manual_token.token_hash
        assert activation.token_hash == hash_activation_token(delivered_token)
        assert abs((persisted_expiry - manual_expiry).total_seconds()) < 0.001
    finally:
        await engine.dispose()


async def test_worker_skips_manual_marker_across_signing_key_drift() -> None:
    engine, sessions, settings = await _worker_runtime()
    signing_key = settings.auth_signing_key
    assert signing_key is not None
    manual_token = ActivationDeliveryTokenCodec(
        signing_key.get_secret_value().encode("utf-8")
    ).issue(TENANT_ID, ACTIVATION_ID)
    manual_event_id = manual_activation_delivery_event_id(ACTIVATION_ID)
    recorded_messages: list[EmailMessage] = []

    try:
        async with sessions.begin() as session:
            activation = await session.get(UserActivationToken, ACTIVATION_ID)
            event = await session.get(OutboxEvent, OUTBOX_ID)
            assert activation is not None
            assert event is not None
            activation.token_hash = manual_token.token_hash
            activation.expires_at = datetime.now(UTC) + timedelta(hours=23)
            event.id = manual_event_id

        drifted_settings = Settings(
            _env_file=None,
            environment="test",
            database_url="sqlite+aiosqlite:///:memory:",
            frontend_base_url="https://frontend.example.test",
            auth_signing_key="different-worker-signing-key-material-0000000000000000",
            notification_email_backend="fake",
        )
        worker = _SuccessfulNotificationWorker(
            session_factory=sessions,
            settings=drifted_settings,
            recorded_messages=recorded_messages,
        )
        assert await worker.run_once() == 1
        assert recorded_messages == []

        async with sessions() as session:
            activation = await session.get(UserActivationToken, ACTIVATION_ID)
            notification = await session.scalar(
                select(Notification).where(Notification.source_event_id == manual_event_id)
            )
            consumption = await session.scalar(
                select(OutboxEventConsumption).where(
                    OutboxEventConsumption.source_event_id == manual_event_id
                )
            )

        assert activation is not None
        assert activation.token_hash == manual_token.token_hash
        assert notification is None
        assert consumption is not None
        assert consumption.outcome == "skipped"
    finally:
        await engine.dispose()


async def test_worker_does_not_deliver_or_rotate_an_expired_activation() -> None:
    engine, sessions, settings = await _worker_runtime()
    signing_key = settings.auth_signing_key
    assert signing_key is not None
    expired_token = ActivationDeliveryTokenCodec(
        signing_key.get_secret_value().encode("utf-8")
    ).issue(TENANT_ID, ACTIVATION_ID)
    expired_at = datetime.now(UTC) - timedelta(minutes=1)
    recorded_messages: list[EmailMessage] = []

    try:
        async with sessions.begin() as session:
            activation = await session.get(UserActivationToken, ACTIVATION_ID)
            assert activation is not None
            activation.token_hash = expired_token.token_hash
            original_hash = activation.token_hash
            activation.expires_at = expired_at

        worker = _SuccessfulNotificationWorker(
            session_factory=sessions,
            settings=settings,
            recorded_messages=recorded_messages,
        )
        assert await worker.run_once() == 2
        assert recorded_messages == []

        async with sessions() as session:
            activation = await session.get(UserActivationToken, ACTIVATION_ID)

        assert activation is not None
        persisted_expiry = activation.expires_at
        if persisted_expiry.tzinfo is None:
            persisted_expiry = persisted_expiry.replace(tzinfo=UTC)
        assert activation.token_hash == original_hash
        assert abs((persisted_expiry - expired_at).total_seconds()) < 0.001
    finally:
        await engine.dispose()


async def test_expired_claim_recovers_after_process_restart_without_rotating_message() -> None:
    engine, sessions, settings = await _worker_runtime()
    crashed_messages: list[EmailMessage] = []
    crash_worker = _CrashAfterAcceptNotificationWorker(
        session_factory=sessions,
        settings=settings,
        recorded_messages=crashed_messages,
    )

    try:
        assert await crash_worker.run_once() == 0
        assert len(crashed_messages) == 1

        async with sessions() as session:
            delivery = await session.scalar(
                select(NotificationDelivery).where(
                    NotificationDelivery.source_event_id == OUTBOX_ID,
                    NotificationDelivery.channel == "email",
                )
            )
            activation = await session.get(UserActivationToken, ACTIVATION_ID)
            assert delivery is not None
            assert delivery.lease_id is not None
            assert delivery.lease_expires_at is not None
            assert delivery.prepared_recipient_email == "initial.admin@example.test"
            assert delivery.prepared_subject == "Your organization access is ready"
            assert delivery.prepared_body_prefix.endswith("Open the HR portal: ")
            assert delivery.prepared_frontend_base_url == "https://frontend.example.test"
            assert delivery.prepared_portal_path == "/activate"
            assert delivery.prepared_message_id == crashed_messages[0].message_id
            assert delivery.prepared_activation_id == ACTIVATION_ID
            assert activation is not None
            prepared_hash = activation.token_hash
            prepared_expiry = activation.expires_at

        successful_messages: list[EmailMessage] = []
        restarted_settings = Settings(
            _env_file=None,
            environment="test",
            database_url="sqlite+aiosqlite:///:memory:",
            frontend_base_url="https://changed-frontend.example.test",
            auth_signing_key="initial-admin-worker-test-signing-key",
            notification_email_backend="smtp",
            notification_smtp_host="changed-smtp.example.test",
            notification_smtp_from_address="changed-sender@example.test",
        )
        restarted_worker = _SuccessfulNotificationWorker(
            session_factory=sessions,
            settings=restarted_settings,
            recorded_messages=successful_messages,
        )
        assert await restarted_worker.run_once() == 0
        assert successful_messages == []

        async with sessions.begin() as session:
            delivery = await session.scalar(
                select(NotificationDelivery).where(
                    NotificationDelivery.source_event_id == OUTBOX_ID,
                    NotificationDelivery.channel == "email",
                )
            )
            assert delivery is not None
            delivery.lease_expires_at = datetime.now(UTC) - timedelta(seconds=1)

        assert await restarted_worker.run_once() == 1
        assert len(successful_messages) == 1
        assert crashed_messages[0].portal_url == successful_messages[0].portal_url
        assert crashed_messages[0].body == successful_messages[0].body
        assert crashed_messages[0].idempotency_key == successful_messages[0].idempotency_key
        assert crashed_messages[0].delivery_id == successful_messages[0].delivery_id
        assert crashed_messages[0].message_id == successful_messages[0].message_id

        async with sessions() as session:
            delivery = await session.scalar(
                select(NotificationDelivery).where(
                    NotificationDelivery.source_event_id == OUTBOX_ID,
                    NotificationDelivery.channel == "email",
                )
            )
            activation = await session.get(UserActivationToken, ACTIVATION_ID)
            assert delivery is not None
            assert delivery.status == NotificationDeliveryStatus.DELIVERED.value
            assert delivery.attempt_count == 2
            assert delivery.lease_id is None
            assert delivery.lease_expires_at is None
            assert delivery.lease_attempt is None
            assert activation is not None
            assert activation.token_hash == prepared_hash
            assert activation.expires_at == prepared_expiry
    finally:
        await engine.dispose()


async def test_unprepared_pre_send_failure_can_prepare_after_configuration_recovery() -> None:
    engine, sessions, _settings = await _worker_runtime()
    unavailable_settings = Settings(
        _env_file=None,
        environment="test",
        database_url="sqlite+aiosqlite:///:memory:",
        frontend_base_url="https://frontend.example.test",
        auth_signing_key=None,
        notification_email_backend="disabled",
    )
    unavailable_messages: list[EmailMessage] = []
    unavailable_worker = _SuccessfulNotificationWorker(
        session_factory=sessions,
        settings=unavailable_settings,
        recorded_messages=unavailable_messages,
    )

    try:
        assert await unavailable_worker.run_once() == 2
        assert unavailable_messages == []

        async with sessions.begin() as session:
            delivery = await session.scalar(
                select(NotificationDelivery).where(
                    NotificationDelivery.source_event_id == OUTBOX_ID,
                    NotificationDelivery.channel == "email",
                )
            )
            activation = await session.get(UserActivationToken, ACTIVATION_ID)
            assert delivery is not None
            assert delivery.status == NotificationDeliveryStatus.RETRY.value
            assert delivery.attempt_count == 1
            assert delivery.prepared_recipient_email is None
            assert activation is not None
            assert activation.token_hash == "0" * 64
            delivery.next_attempt_at = datetime.now(UTC) - timedelta(seconds=1)

        recovered_settings = Settings(
            _env_file=None,
            environment="test",
            database_url="sqlite+aiosqlite:///:memory:",
            frontend_base_url="https://frontend.example.test",
            auth_signing_key="initial-admin-worker-test-signing-key",
            notification_email_backend="fake",
        )
        recovered_messages: list[EmailMessage] = []
        recovered_worker = _SuccessfulNotificationWorker(
            session_factory=sessions,
            settings=recovered_settings,
            recorded_messages=recovered_messages,
        )
        assert await recovered_worker.run_once() == 1
        assert len(recovered_messages) == 1

        raw_token = parse_qs(urlsplit(recovered_messages[0].portal_url).fragment)["token"][0]
        async with sessions() as session:
            delivery = await session.scalar(
                select(NotificationDelivery).where(
                    NotificationDelivery.source_event_id == OUTBOX_ID,
                    NotificationDelivery.channel == "email",
                )
            )
            activation = await session.get(UserActivationToken, ACTIVATION_ID)
            assert delivery is not None
            assert delivery.status == NotificationDeliveryStatus.DELIVERED.value
            assert delivery.attempt_count == 2
            assert delivery.prepared_recipient_email == "initial.admin@example.test"
            assert activation is not None
            assert activation.token_hash == hash_activation_token(raw_token)
    finally:
        await engine.dispose()


async def test_expired_claim_at_max_attempts_is_terminal_without_another_send() -> None:
    engine, sessions, _settings = await _worker_runtime()
    settings = Settings(
        _env_file=None,
        environment="test",
        database_url="sqlite+aiosqlite:///:memory:",
        frontend_base_url="https://frontend.example.test",
        auth_signing_key="initial-admin-worker-test-signing-key",
        notification_email_backend="fake",
        notification_worker_max_attempts=1,
    )
    crashed_messages: list[EmailMessage] = []
    crash_worker = _CrashAfterAcceptNotificationWorker(
        session_factory=sessions,
        settings=settings,
        recorded_messages=crashed_messages,
    )

    try:
        assert await crash_worker.run_once() == 0
        assert len(crashed_messages) == 1

        async with sessions.begin() as session:
            delivery = await session.scalar(
                select(NotificationDelivery).where(
                    NotificationDelivery.source_event_id == OUTBOX_ID,
                    NotificationDelivery.channel == "email",
                )
            )
            assert delivery is not None
            assert delivery.attempt_count == 1
            assert delivery.lease_attempt == 1
            delivery.lease_expires_at = datetime.now(UTC) - timedelta(seconds=1)

        competing_messages: list[EmailMessage] = []
        restarted_worker = _SuccessfulNotificationWorker(
            session_factory=sessions,
            settings=settings,
            recorded_messages=competing_messages,
        )
        assert await restarted_worker.run_once() == 1
        assert competing_messages == []

        async with sessions() as session:
            delivery = await session.scalar(
                select(NotificationDelivery).where(
                    NotificationDelivery.source_event_id == OUTBOX_ID,
                    NotificationDelivery.channel == "email",
                )
            )
            assert delivery is not None
            assert delivery.status == NotificationDeliveryStatus.FAILED.value
            assert delivery.attempt_count == 1
            assert delivery.lease_id is None
            assert delivery.lease_attempt is None
            assert delivery.terminal_error_code == "provider_unavailable"
    finally:
        await engine.dispose()


async def test_protected_worker_never_sends_persisted_http_activation_message() -> None:
    engine, sessions, _settings = await _worker_runtime()
    local_settings = Settings(
        _env_file=None,
        environment="local",
        database_url="sqlite+aiosqlite:///:memory:",
        frontend_base_url="http://localhost:3000",
        auth_signing_key="initial-admin-worker-test-signing-key",
        notification_email_backend="fake",
        notification_worker_max_attempts=2,
    )
    crashed_messages: list[EmailMessage] = []
    local_worker = _CrashAfterAcceptNotificationWorker(
        session_factory=sessions,
        settings=local_settings,
        recorded_messages=crashed_messages,
    )

    try:
        assert await local_worker.run_once() == 0
        assert len(crashed_messages) == 1
        assert crashed_messages[0].portal_url.startswith("http://")

        async with sessions.begin() as session:
            delivery = await session.scalar(
                select(NotificationDelivery).where(
                    NotificationDelivery.source_event_id == OUTBOX_ID,
                    NotificationDelivery.channel == "email",
                )
            )
            assert delivery is not None
            assert delivery.prepared_frontend_base_url == "http://localhost:3000"
            delivery.lease_expires_at = datetime.now(UTC) - timedelta(seconds=1)

        prod_settings = Settings(
            _env_file=None,
            environment="prod",
            release_commit_sha="a" * 40,
            release_build_timestamp=datetime(2026, 7, 29, tzinfo=UTC),
            database_url="sqlite+aiosqlite:///:memory:",
            frontend_base_url="https://app.example.test",
            auth_signing_key="initial-admin-worker-test-signing-key",
            notification_email_backend="disabled",
            notification_worker_max_attempts=2,
        )
        protected_messages: list[EmailMessage] = []
        protected_worker = _SuccessfulNotificationWorker(
            session_factory=sessions,
            settings=prod_settings,
            recorded_messages=protected_messages,
        )
        assert await protected_worker.run_once() == 1
        assert protected_messages == []

        async with sessions() as session:
            delivery = await session.scalar(
                select(NotificationDelivery).where(
                    NotificationDelivery.source_event_id == OUTBOX_ID,
                    NotificationDelivery.channel == "email",
                )
            )
            assert delivery is not None
            assert delivery.status == NotificationDeliveryStatus.FAILED.value
            assert delivery.terminal_error_code == "provider_unavailable"
    finally:
        await engine.dispose()


async def test_concurrent_workers_cannot_send_the_same_active_claim(tmp_path: Path) -> None:
    engine, sessions, settings = await _worker_runtime(tmp_path / "notification-worker.sqlite3")
    started = asyncio.Event()
    release = asyncio.Event()
    first_messages: list[EmailMessage] = []
    competing_messages: list[EmailMessage] = []
    first_worker = _BlockingNotificationWorker(
        session_factory=sessions,
        settings=settings,
        started=started,
        release=release,
        recorded_messages=first_messages,
    )
    competing_worker = _SuccessfulNotificationWorker(
        session_factory=sessions,
        settings=settings,
        recorded_messages=competing_messages,
    )

    try:
        first_run = asyncio.create_task(first_worker.run_once())
        await asyncio.wait_for(started.wait(), timeout=2)

        assert await competing_worker.run_once() == 0
        assert competing_messages == []
        assert len(first_messages) == 1

        async with sessions() as session:
            delivery = await session.scalar(
                select(NotificationDelivery).where(
                    NotificationDelivery.source_event_id == OUTBOX_ID,
                    NotificationDelivery.channel == "email",
                )
            )
            assert delivery is not None
            assert delivery.lease_id is not None
            assert delivery.lease_expires_at is not None
            assert delivery.lease_attempt == 1
            assert delivery.attempt_count == 1

        release.set()
        assert await asyncio.wait_for(first_run, timeout=2) == 2

        async with sessions() as session:
            delivery = await session.scalar(
                select(NotificationDelivery).where(
                    NotificationDelivery.source_event_id == OUTBOX_ID,
                    NotificationDelivery.channel == "email",
                )
            )
            assert delivery is not None
            assert delivery.status == NotificationDeliveryStatus.DELIVERED.value
            assert delivery.lease_id is None
            assert delivery.lease_attempt is None
            assert delivery.attempt_count == 1
    finally:
        release.set()
        await engine.dispose()
