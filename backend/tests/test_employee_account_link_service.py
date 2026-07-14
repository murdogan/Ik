from datetime import date

import pytest
from app.models.identity import Identity, IdentityStatus, MembershipStatus, TenantMembership
from app.models.user import User, UserStatus
from app.schemas.employee_account_link import EmployeeAccountLinkUpdate
from app.services.employee_account_link_service import (
    EmployeeAccountLinkService,
    EmployeeAccountLinkUnavailableError,
    EmployeeAccountLinkVersionConflictError,
)
from sqlalchemy import select
from tests._employee_account_link_support import (
    EMPLOYEE_ID,
    IDENTITY_ID,
    MEMBERSHIP_ID,
    OTHER_EMPLOYEE_ID,
    OTHER_TENANT_ID,
    OTHER_TENANT_MEMBERSHIP_ID,
    SECOND_EMPLOYEE_ID,
    SECOND_MEMBERSHIP_ID,
    SECOND_USER_ID,
    TENANT_ID,
    USER_ID,
    employee_account_link_database,
)


async def test_email_never_auto_links_and_lookup_is_tenant_bounded() -> None:
    async with employee_account_link_database() as database:
        async with database.sessions() as session:
            service = EmployeeAccountLinkService(session)
            state = await service.get_account_link(TENANT_ID, EMPLOYEE_ID)
            eligible = await service.list_eligible_memberships(
                TENANT_ID,
                EMPLOYEE_ID,
                query="ada@example.test",
                limit=20,
            )

    assert state.link is None
    assert [row.membership_id for row in eligible] == [MEMBERSHIP_ID]
    assert eligible[0].eligible is True
    assert OTHER_TENANT_MEMBERSHIP_ID not in {row.membership_id for row in eligible}


async def test_same_identity_resolves_a_distinct_link_for_each_selected_tenant_membership() -> None:
    async with employee_account_link_database() as database:
        async with database.sessions() as session:
            service = EmployeeAccountLinkService(session, today=date(2026, 7, 14))
            first = await service.update_account_link(
                TENANT_ID,
                EMPLOYEE_ID,
                EmployeeAccountLinkUpdate(
                    membership_id=MEMBERSHIP_ID,
                    expected_version=None,
                ),
            )
            second = await service.update_account_link(
                OTHER_TENANT_ID,
                OTHER_EMPLOYEE_ID,
                EmployeeAccountLinkUpdate(
                    membership_id=OTHER_TENANT_MEMBERSHIP_ID,
                    expected_version=None,
                ),
            )
            own_first = await service.get_own_profile(TENANT_ID, MEMBERSHIP_ID, USER_ID)
            other_user_id = await session.scalar(
                select(TenantMembership.legacy_user_id).where(
                    TenantMembership.id == OTHER_TENANT_MEMBERSHIP_ID
                )
            )
            assert other_user_id is not None
            own_second = await service.get_own_profile(
                OTHER_TENANT_ID,
                OTHER_TENANT_MEMBERSHIP_ID,
                other_user_id,
            )
            wrong_selected_tenant = await service.get_own_profile(
                TENANT_ID,
                OTHER_TENANT_MEMBERSHIP_ID,
                other_user_id,
            )
            mismatched_legacy_actor = await service.get_own_profile(
                TENANT_ID,
                MEMBERSHIP_ID,
                SECOND_USER_ID,
            )

    assert first.response.link is not None
    assert second.response.link is not None
    assert own_first.availability == "available"
    assert own_first.profile is not None
    assert own_first.profile.core.id == EMPLOYEE_ID
    assert own_first.profile.organization.current_assignment is not None
    assert own_first.profile.organization.current_assignment.department.name == "Engineering"
    assert own_second.availability == "available"
    assert own_second.profile is not None
    assert own_second.profile.core.id == OTHER_EMPLOYEE_ID
    assert wrong_selected_tenant.model_dump() == {
        "availability": "unavailable",
        "membership_id": None,
        "profile": None,
    }
    assert mismatched_legacy_actor.availability == "unavailable"
    assert mismatched_legacy_actor.membership_id is None


@pytest.mark.parametrize(
    ("record_type", "attribute", "value"),
    [
        (Identity, "status", IdentityStatus.PENDING.value),
        (Identity, "status", IdentityStatus.LOCKED.value),
        (Identity, "status", IdentityStatus.DISABLED.value),
        (TenantMembership, "status", MembershipStatus.INVITED.value),
        (TenantMembership, "status", MembershipStatus.LOCKED.value),
        (TenantMembership, "status", MembershipStatus.DISABLED.value),
        (User, "status", UserStatus.INVITED.value),
        (User, "status", UserStatus.LOCKED.value),
        (User, "status", UserStatus.DISABLED.value),
        (TenantMembership, "permission_version", 2),
    ],
)
async def test_disabled_locked_invited_and_stale_compatibility_states_are_unavailable(
    record_type: type[object],
    attribute: str,
    value: object,
) -> None:
    async with employee_account_link_database() as database:
        async with database.sessions() as session:
            service = EmployeeAccountLinkService(session)
            await service.update_account_link(
                TENANT_ID,
                EMPLOYEE_ID,
                EmployeeAccountLinkUpdate(
                    membership_id=MEMBERSHIP_ID,
                    expected_version=None,
                ),
            )
            lookup_id = (
                IDENTITY_ID
                if record_type is Identity
                else (MEMBERSHIP_ID if record_type is TenantMembership else USER_ID)
            )
            record = await session.get(record_type, lookup_id)
            assert record is not None
            setattr(record, attribute, value)
            if record_type is Identity and value == IdentityStatus.PENDING.value:
                record.password_hash = None
            await session.flush()

            own = await service.get_own_profile(TENANT_ID, MEMBERSHIP_ID, USER_ID)
            current = await service.get_account_link(TENANT_ID, EMPLOYEE_ID)
            assert current.link is not None
            await service.update_account_link(
                TENANT_ID,
                EMPLOYEE_ID,
                EmployeeAccountLinkUpdate(
                    membership_id=None,
                    expected_version=current.link.version,
                ),
            )
            with pytest.raises(EmployeeAccountLinkUnavailableError):
                await service.update_account_link(
                    TENANT_ID,
                    EMPLOYEE_ID,
                    EmployeeAccountLinkUpdate(
                        membership_id=MEMBERSHIP_ID,
                        expected_version=None,
                    ),
                )

    assert own.availability == "unavailable"
    assert own.membership_id is None
    assert own.profile is None
    assert current.link.membership.eligible is False


async def test_stale_link_relink_unlink_writers_lose_and_retries_are_idempotent() -> None:
    async with employee_account_link_database() as database:
        async with database.sessions() as session:
            service = EmployeeAccountLinkService(session)
            with pytest.raises(EmployeeAccountLinkVersionConflictError):
                await service.update_account_link(
                    TENANT_ID,
                    EMPLOYEE_ID,
                    EmployeeAccountLinkUpdate(
                        membership_id=MEMBERSHIP_ID,
                        expected_version=1,
                    ),
                )

            linked = await service.update_account_link(
                TENANT_ID,
                EMPLOYEE_ID,
                EmployeeAccountLinkUpdate(
                    membership_id=MEMBERSHIP_ID,
                    expected_version=None,
                ),
            )
            assert linked.response.link is not None
            version = linked.response.link.version
            same_target = await service.update_account_link(
                TENANT_ID,
                EMPLOYEE_ID,
                EmployeeAccountLinkUpdate(
                    membership_id=MEMBERSHIP_ID,
                    expected_version=version + 99,
                ),
            )
            assert same_target.changed is False
            assert same_target.response.link is not None
            assert same_target.response.link.version == version

            with pytest.raises(EmployeeAccountLinkVersionConflictError):
                await service.update_account_link(
                    TENANT_ID,
                    EMPLOYEE_ID,
                    EmployeeAccountLinkUpdate(
                        membership_id=SECOND_MEMBERSHIP_ID,
                        expected_version=version + 1,
                    ),
                )
            relinked = await service.update_account_link(
                TENANT_ID,
                EMPLOYEE_ID,
                EmployeeAccountLinkUpdate(
                    membership_id=SECOND_MEMBERSHIP_ID,
                    expected_version=version,
                ),
            )
            assert relinked.response.link is not None
            assert relinked.response.link.version == version + 1
            assert relinked.link_status == "relinked"

            with pytest.raises(EmployeeAccountLinkVersionConflictError):
                await service.update_account_link(
                    TENANT_ID,
                    EMPLOYEE_ID,
                    EmployeeAccountLinkUpdate(
                        membership_id=None,
                        expected_version=version,
                    ),
                )
            unlinked = await service.update_account_link(
                TENANT_ID,
                EMPLOYEE_ID,
                EmployeeAccountLinkUpdate(
                    membership_id=None,
                    expected_version=version + 1,
                ),
            )
            retry = await service.update_account_link(
                TENANT_ID,
                EMPLOYEE_ID,
                EmployeeAccountLinkUpdate(
                    membership_id=None,
                    expected_version=version + 1,
                ),
            )

    assert unlinked.changed is True
    assert unlinked.response.link is None
    assert retry.changed is False
    assert retry.response.link is None


async def test_foreign_or_already_linked_membership_uses_one_generic_conflict() -> None:
    async with employee_account_link_database() as database:
        async with database.sessions() as session:
            service = EmployeeAccountLinkService(session)
            await service.update_account_link(
                TENANT_ID,
                EMPLOYEE_ID,
                EmployeeAccountLinkUpdate(
                    membership_id=MEMBERSHIP_ID,
                    expected_version=None,
                ),
            )
            with pytest.raises(EmployeeAccountLinkUnavailableError):
                await service.update_account_link(
                    TENANT_ID,
                    SECOND_EMPLOYEE_ID,
                    EmployeeAccountLinkUpdate(
                        membership_id=MEMBERSHIP_ID,
                        expected_version=None,
                    ),
                )
            with pytest.raises(EmployeeAccountLinkUnavailableError):
                await service.update_account_link(
                    TENANT_ID,
                    SECOND_EMPLOYEE_ID,
                    EmployeeAccountLinkUpdate(
                        membership_id=OTHER_TENANT_MEMBERSHIP_ID,
                        expected_version=None,
                    ),
                )
