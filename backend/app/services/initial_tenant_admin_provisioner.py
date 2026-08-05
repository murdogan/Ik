"""Initial tenant-administrator invitation provisioning inside tenant creation."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from sqlalchemy import select, text
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.auth import UserActivationToken
from app.models.authorization import UserRole
from app.models.identity import (
    Identity,
    IdentityStatus,
    MembershipRole,
    MembershipStatus,
    TenantMembership,
)
from app.models.leave import OutboxEvent
from app.models.tenant import Tenant, TenantStatus
from app.models.user import User, UserStatus
from app.platform.authorization import ROLES_BY_CODE
from app.platform.db import sqlstate_from_error
from app.platform.errors.application import ApplicationError
from app.platform.identity import ActivationDeliveryTokenCodec, issue_activation_token
from app.schemas.tenant import TenantInitialAdminCorrection, TenantInitialAdminProvision
from app.services.authorization_service import assign_system_role
from app.services.identity_projection_service import sync_identity_membership_projection

_POSTGRES_PROVISION_FUNCTION = "provision_platform_initial_tenant_admin"
_POSTGRES_REISSUE_FUNCTION = "reissue_platform_initial_tenant_admin_invitation"
_POSTGRES_CORRECTION_FUNCTION = "correct_platform_initial_tenant_admin_invitation"
_INITIAL_ADMIN_UNAVAILABLE_SQLSTATE = "WF003"
_INVITATION_EVENT_TYPE = "identity.initial_admin_invited"
_REISSUE_ELIGIBLE_TENANT_STATUSES = frozenset(
    {
        TenantStatus.PROVISIONING.value,
        TenantStatus.TRIAL.value,
        TenantStatus.ACTIVE.value,
    }
)


class InitialTenantAdminUnavailableError(ApplicationError):
    """The requested initial administrator cannot enter the activation flow."""


@dataclass(frozen=True, slots=True)
class InitialTenantAdminManualLinkMaterial:
    """Ephemeral credential material returned only to the authorized API edge."""

    raw_token: str = field(repr=False)
    expires_at: datetime


class InitialTenantAdminProvisioner:
    def __init__(
        self,
        session: AsyncSession,
        *,
        activation_ttl: timedelta,
        activation_delivery_tokens: ActivationDeliveryTokenCodec | None = None,
    ) -> None:
        if activation_ttl <= timedelta(0):
            raise ValueError("Activation TTL must be positive")
        self.session = session
        self.activation_ttl = activation_ttl
        self._activation_delivery_tokens = activation_delivery_tokens

    async def provision(
        self,
        *,
        tenant: Tenant,
        initial_admin: TenantInitialAdminProvision,
    ) -> None:
        token = issue_activation_token(tenant.id)
        now = datetime.now(UTC)
        expires_at = now + self.activation_ttl
        user_id = uuid4()
        activation_id = uuid4()
        outbox_id = uuid4()

        if self.session.get_bind().dialect.name == "postgresql":
            try:
                await self.session.execute(
                    text(
                        f"select public.{_POSTGRES_PROVISION_FUNCTION}("
                        ":tenant_id, :user_id, :full_name, :email, "
                        ":activation_id, :token_hash, :expires_at, "
                        ":outbox_id)"
                    ),
                    {
                        "tenant_id": tenant.id,
                        "user_id": user_id,
                        "full_name": initial_admin.full_name,
                        "email": initial_admin.email,
                        "activation_id": activation_id,
                        "token_hash": token.token_hash,
                        "expires_at": expires_at,
                        "outbox_id": outbox_id,
                    },
                )
            except DBAPIError as exc:
                if sqlstate_from_error(exc) == _INITIAL_ADMIN_UNAVAILABLE_SQLSTATE:
                    raise InitialTenantAdminUnavailableError() from exc
                raise
            return

        await self._provision_compatibility(
            tenant=tenant,
            initial_admin=initial_admin,
            user_id=user_id,
            activation_id=activation_id,
            token_hash=token.token_hash,
            expires_at=expires_at,
            outbox_id=outbox_id,
            occurred_at=now,
        )

    async def reissue(self, *, tenant_id: UUID) -> None:
        token = issue_activation_token(tenant_id)
        now = datetime.now(UTC)
        expires_at = now + self.activation_ttl
        activation_id = uuid4()
        outbox_id = uuid4()

        await self._persist_reissue(
            tenant_id=tenant_id,
            activation_id=activation_id,
            token_hash=token.token_hash,
            expires_at=expires_at,
            outbox_id=outbox_id,
            occurred_at=now,
        )

    async def reissue_manual_link(
        self,
        *,
        tenant_id: UUID,
    ) -> InitialTenantAdminManualLinkMaterial:
        token_codec = self._activation_delivery_tokens
        if token_codec is None:
            raise RuntimeError("Manual activation-link signing is unavailable")
        if tenant_id.int == 0:
            raise InitialTenantAdminUnavailableError()

        activation_id = uuid4()
        token = token_codec.issue(tenant_id, activation_id)
        now = datetime.now(UTC)
        expires_at = now + self.activation_ttl
        outbox_id = uuid4()

        await self._persist_reissue(
            tenant_id=tenant_id,
            activation_id=activation_id,
            token_hash=token.token_hash,
            expires_at=expires_at,
            outbox_id=outbox_id,
            occurred_at=now,
        )
        return InitialTenantAdminManualLinkMaterial(
            raw_token=token.raw_token,
            expires_at=expires_at,
        )

    async def _persist_reissue(
        self,
        *,
        tenant_id: UUID,
        activation_id: UUID,
        token_hash: str,
        expires_at: datetime,
        outbox_id: UUID,
        occurred_at: datetime,
    ) -> None:
        if self.session.get_bind().dialect.name == "postgresql":
            try:
                await self.session.execute(
                    text(
                        f"select public.{_POSTGRES_REISSUE_FUNCTION}("
                        ":tenant_id, :activation_id, :token_hash, :expires_at, :outbox_id)"
                    ),
                    {
                        "tenant_id": tenant_id,
                        "activation_id": activation_id,
                        "token_hash": token_hash,
                        "expires_at": expires_at,
                        "outbox_id": outbox_id,
                    },
                )
            except DBAPIError as exc:
                if sqlstate_from_error(exc) == _INITIAL_ADMIN_UNAVAILABLE_SQLSTATE:
                    raise InitialTenantAdminUnavailableError() from exc
                raise
            return

        await self._reissue_compatibility(
            tenant_id=tenant_id,
            activation_id=activation_id,
            token_hash=token_hash,
            expires_at=expires_at,
            outbox_id=outbox_id,
            occurred_at=occurred_at,
        )

    async def correct(
        self,
        *,
        tenant_id: UUID,
        correction: TenantInitialAdminCorrection,
    ) -> None:
        token = issue_activation_token(tenant_id)
        now = datetime.now(UTC)
        expires_at = now + self.activation_ttl
        identity_id = uuid4()
        activation_id = uuid4()
        outbox_id = uuid4()

        if self.session.get_bind().dialect.name == "postgresql":
            try:
                await self.session.execute(
                    text(
                        f"select public.{_POSTGRES_CORRECTION_FUNCTION}("
                        ":tenant_id, :full_name, :email, :identity_id, "
                        ":activation_id, :token_hash, :expires_at, :outbox_id)"
                    ),
                    {
                        "tenant_id": tenant_id,
                        "full_name": correction.full_name,
                        "email": correction.email,
                        "identity_id": identity_id,
                        "activation_id": activation_id,
                        "token_hash": token.token_hash,
                        "expires_at": expires_at,
                        "outbox_id": outbox_id,
                    },
                )
            except DBAPIError as exc:
                if sqlstate_from_error(exc) == _INITIAL_ADMIN_UNAVAILABLE_SQLSTATE:
                    raise InitialTenantAdminUnavailableError() from exc
                raise
            return

        try:
            await self._correct_compatibility(
                tenant_id=tenant_id,
                correction=correction,
                identity_id=identity_id,
                activation_id=activation_id,
                token_hash=token.token_hash,
                expires_at=expires_at,
                outbox_id=outbox_id,
                occurred_at=now,
            )
        except IntegrityError as exc:
            # A target identity/user race is deliberately indistinguishable from every other
            # ineligible correction. The surrounding UoW rolls the failed transaction back.
            raise InitialTenantAdminUnavailableError() from exc

    async def _provision_compatibility(
        self,
        *,
        tenant: Tenant,
        initial_admin: TenantInitialAdminProvision,
        user_id: UUID,
        activation_id: UUID,
        token_hash: str,
        expires_at: datetime,
        outbox_id: UUID,
        occurred_at: datetime,
    ) -> None:
        if await self.session.scalar(select(User.id).where(User.tenant_id == tenant.id)):
            raise InitialTenantAdminUnavailableError()
        identity = await self.session.scalar(
            select(Identity)
            .where(Identity.email_normalized == initial_admin.email)
            .with_for_update()
        )
        if identity is not None and identity.status not in {
            IdentityStatus.PENDING.value,
            IdentityStatus.ACTIVE.value,
        }:
            raise InitialTenantAdminUnavailableError()

        user = User(
            id=user_id,
            tenant_id=tenant.id,
            email=initial_admin.email,
            full_name=initial_admin.full_name,
            status=UserStatus.INVITED.value,
            password_hash=None,
        )
        self.session.add(user)
        await self.session.flush()
        await assign_system_role(
            self.session,
            tenant_id=tenant.id,
            user_id=user.id,
            role_code="tenant_admin",
        )
        await sync_identity_membership_projection(self.session, user)
        self.session.add(
            UserActivationToken(
                id=activation_id,
                tenant_id=tenant.id,
                user_id=user.id,
                token_hash=token_hash,
                expires_at=expires_at,
            )
        )
        self.session.add(
            OutboxEvent(
                id=outbox_id,
                tenant_id=tenant.id,
                aggregate_type="identity_membership",
                aggregate_id=user.id,
                event_type=_INVITATION_EVENT_TYPE,
                payload={
                    "recipient_user_id": str(user.id),
                    "activation_id": str(activation_id),
                },
                source_key=f"{_INVITATION_EVENT_TYPE}:{user.id}",
                occurred_at=occurred_at,
            )
        )
        await self.session.flush()

    async def _reissue_compatibility(
        self,
        *,
        tenant_id: UUID,
        activation_id: UUID,
        token_hash: str,
        expires_at: datetime,
        outbox_id: UUID,
        occurred_at: datetime,
    ) -> None:
        tenant = await self.session.scalar(
            select(Tenant).where(Tenant.id == tenant_id).with_for_update()
        )
        if tenant is None or tenant.status not in _REISSUE_ELIGIBLE_TENANT_STATUSES:
            raise InitialTenantAdminUnavailableError()

        invitation_events = tuple(
            await self.session.scalars(
                select(OutboxEvent)
                .where(
                    OutboxEvent.tenant_id == tenant_id,
                    OutboxEvent.event_type == _INVITATION_EVENT_TYPE,
                )
                .order_by(OutboxEvent.created_at, OutboxEvent.id)
                .with_for_update()
            )
        )
        original_events = tuple(
            event for event in invitation_events if _is_original_initial_admin_invitation(event)
        )
        if len(original_events) != 1:
            raise InitialTenantAdminUnavailableError()
        original_event = original_events[0]
        user_id = original_event.aggregate_id

        user = await self.session.scalar(
            select(User)
            .where(
                User.tenant_id == tenant_id,
                User.id == user_id,
            )
            .with_for_update()
        )
        membership = await self.session.scalar(
            select(TenantMembership)
            .where(
                TenantMembership.tenant_id == tenant_id,
                TenantMembership.id == user_id,
                TenantMembership.legacy_user_id == user_id,
            )
            .with_for_update()
        )
        if (
            user is None
            or user.status != UserStatus.INVITED.value
            or user.password_hash is not None
            or membership is None
            or membership.status != MembershipStatus.INVITED.value
        ):
            raise InitialTenantAdminUnavailableError()

        identity = await self.session.scalar(
            select(Identity).where(Identity.id == membership.identity_id).with_for_update()
        )
        if identity is None or identity.status not in {
            IdentityStatus.PENDING.value,
            IdentityStatus.ACTIVE.value,
        }:
            raise InitialTenantAdminUnavailableError()

        tenant_admin_role_id = ROLES_BY_CODE["tenant_admin"].id
        active_user_roles = set(
            await self.session.scalars(
                select(UserRole.role_id).where(
                    UserRole.tenant_id == tenant_id,
                    UserRole.user_id == user_id,
                    UserRole.active.is_(True),
                )
            )
        )
        active_membership_roles = set(
            await self.session.scalars(
                select(MembershipRole.role_id).where(
                    MembershipRole.tenant_id == tenant_id,
                    MembershipRole.membership_id == membership.id,
                    MembershipRole.active.is_(True),
                )
            )
        )
        if active_user_roles != {tenant_admin_role_id} or active_membership_roles != {
            tenant_admin_role_id
        }:
            raise InitialTenantAdminUnavailableError()

        activations = tuple(
            await self.session.scalars(
                select(UserActivationToken)
                .where(
                    UserActivationToken.tenant_id == tenant_id,
                    UserActivationToken.user_id == user_id,
                )
                .with_for_update()
            )
        )
        if any(activation.consumed_at is not None for activation in activations):
            raise InitialTenantAdminUnavailableError()
        for activation in activations:
            if activation.revoked_at is None:
                activation.revoked_at = occurred_at

        self.session.add(
            UserActivationToken(
                id=activation_id,
                tenant_id=tenant_id,
                user_id=user_id,
                token_hash=token_hash,
                expires_at=expires_at,
            )
        )
        self.session.add(
            OutboxEvent(
                id=outbox_id,
                tenant_id=tenant_id,
                aggregate_type="identity_membership",
                aggregate_id=user_id,
                event_type=_INVITATION_EVENT_TYPE,
                payload={
                    "recipient_user_id": str(user_id),
                    "activation_id": str(activation_id),
                },
                source_key=(f"{_INVITATION_EVENT_TYPE}:{user_id}:reissue:{activation_id}"),
                occurred_at=occurred_at,
            )
        )
        await self.session.flush()

    async def _correct_compatibility(
        self,
        *,
        tenant_id: UUID,
        correction: TenantInitialAdminCorrection,
        identity_id: UUID,
        activation_id: UUID,
        token_hash: str,
        expires_at: datetime,
        outbox_id: UUID,
        occurred_at: datetime,
    ) -> None:
        tenant = await self.session.scalar(
            select(Tenant).where(Tenant.id == tenant_id).with_for_update()
        )
        if tenant is None or tenant.status not in _REISSUE_ELIGIBLE_TENANT_STATUSES:
            raise InitialTenantAdminUnavailableError()

        invitation_events = tuple(
            await self.session.scalars(
                select(OutboxEvent)
                .where(
                    OutboxEvent.tenant_id == tenant_id,
                    OutboxEvent.event_type == _INVITATION_EVENT_TYPE,
                )
                .order_by(OutboxEvent.created_at, OutboxEvent.id)
                .with_for_update()
            )
        )
        original_events = tuple(
            event for event in invitation_events if _is_original_initial_admin_invitation(event)
        )
        if len(original_events) != 1:
            raise InitialTenantAdminUnavailableError()
        original_event = original_events[0]
        user_id = original_event.aggregate_id
        original_activation_id = UUID(original_event.payload["activation_id"])

        user = await self.session.scalar(
            select(User)
            .where(
                User.tenant_id == tenant_id,
                User.id == user_id,
            )
            .with_for_update()
        )
        membership = await self.session.scalar(
            select(TenantMembership)
            .where(
                TenantMembership.tenant_id == tenant_id,
                TenantMembership.id == user_id,
                TenantMembership.legacy_user_id == user_id,
            )
            .with_for_update()
        )
        if (
            user is None
            or user.status != UserStatus.INVITED.value
            or user.password_hash is not None
            or membership is None
            or membership.status != MembershipStatus.INVITED.value
        ):
            raise InitialTenantAdminUnavailableError()

        old_identity = await self.session.scalar(
            select(Identity).where(Identity.id == membership.identity_id).with_for_update()
        )
        if (
            old_identity is None
            or old_identity.status
            not in {
                IdentityStatus.PENDING.value,
                IdentityStatus.ACTIVE.value,
            }
            or old_identity.email_normalized != user.email_normalized
        ):
            raise InitialTenantAdminUnavailableError()

        tenant_admin_role_id = ROLES_BY_CODE["tenant_admin"].id
        active_user_roles = set(
            await self.session.scalars(
                select(UserRole.role_id).where(
                    UserRole.tenant_id == tenant_id,
                    UserRole.user_id == user_id,
                    UserRole.active.is_(True),
                )
            )
        )
        active_membership_roles = set(
            await self.session.scalars(
                select(MembershipRole.role_id).where(
                    MembershipRole.tenant_id == tenant_id,
                    MembershipRole.membership_id == membership.id,
                    MembershipRole.active.is_(True),
                )
            )
        )
        if active_user_roles != {tenant_admin_role_id} or active_membership_roles != {
            tenant_admin_role_id
        }:
            raise InitialTenantAdminUnavailableError()

        activations = tuple(
            await self.session.scalars(
                select(UserActivationToken)
                .where(
                    UserActivationToken.tenant_id == tenant_id,
                    UserActivationToken.user_id == user_id,
                )
                .with_for_update()
            )
        )
        if (
            any(activation.consumed_at is not None for activation in activations)
            or sum(activation.id == original_activation_id for activation in activations) != 1
        ):
            raise InitialTenantAdminUnavailableError()

        target_identity = await self.session.scalar(
            select(Identity).where(Identity.email_normalized == correction.email).with_for_update()
        )
        if target_identity is not None and target_identity.status not in {
            IdentityStatus.PENDING.value,
            IdentityStatus.ACTIVE.value,
        }:
            raise InitialTenantAdminUnavailableError()
        if target_identity is not None:
            conflicting_membership = await self.session.scalar(
                select(TenantMembership.id)
                .where(
                    TenantMembership.tenant_id == tenant_id,
                    TenantMembership.identity_id == target_identity.id,
                    TenantMembership.id != membership.id,
                )
                .with_for_update()
            )
            if conflicting_membership is not None:
                raise InitialTenantAdminUnavailableError()
        elif await self.session.scalar(select(Identity.id).where(Identity.id == identity_id)):
            raise InitialTenantAdminUnavailableError()

        duplicate_user = await self.session.scalar(
            select(User.id)
            .where(
                User.tenant_id == tenant_id,
                User.email_normalized == correction.email,
                User.id != user_id,
            )
            .with_for_update()
        )
        if duplicate_user is not None:
            raise InitialTenantAdminUnavailableError()

        if target_identity is None:
            target_identity = Identity(
                id=identity_id,
                email=correction.email,
                status=IdentityStatus.PENDING.value,
                password_hash=None,
            )
            self.session.add(target_identity)
            await self.session.flush()

        user.email = correction.email
        user.full_name = correction.full_name
        membership.identity_id = target_identity.id
        membership.full_name = correction.full_name
        for activation in activations:
            if activation.revoked_at is None:
                activation.revoked_at = occurred_at

        self.session.add(
            UserActivationToken(
                id=activation_id,
                tenant_id=tenant_id,
                user_id=user_id,
                token_hash=token_hash,
                expires_at=expires_at,
            )
        )
        self.session.add(
            OutboxEvent(
                id=outbox_id,
                tenant_id=tenant_id,
                aggregate_type="identity_membership",
                aggregate_id=user_id,
                event_type=_INVITATION_EVENT_TYPE,
                payload={
                    "recipient_user_id": str(user_id),
                    "activation_id": str(activation_id),
                },
                source_key=(f"{_INVITATION_EVENT_TYPE}:{user_id}:correction:{activation_id}"),
                occurred_at=occurred_at,
            )
        )
        await self.session.flush()


def _is_original_initial_admin_invitation(event: OutboxEvent) -> bool:
    if (
        event.aggregate_type != "identity_membership"
        or event.source_key != f"{_INVITATION_EVENT_TYPE}:{event.aggregate_id}"
        or set(event.payload) != {"recipient_user_id", "activation_id"}
        or event.payload.get("recipient_user_id") != str(event.aggregate_id)
    ):
        return False
    activation_id = event.payload.get("activation_id")
    if not isinstance(activation_id, str):
        return False
    try:
        return UUID(activation_id).int != 0
    except ValueError:
        return False


__all__ = [
    "InitialTenantAdminManualLinkMaterial",
    "InitialTenantAdminProvisioner",
    "InitialTenantAdminUnavailableError",
]
