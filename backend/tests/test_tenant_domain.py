import pytest
from app.modules.core.domain import (
    TenantAccessMode,
    TenantDateFormat,
    TenantHealth,
    TenantLifecycleTransitionError,
    TenantLocale,
    TenantPlan,
    TenantRegion,
    TenantStatus,
    TenantTimeFormat,
    TenantWeekStartDay,
    access_mode_for_status,
    allowed_transition_targets,
    can_transition,
    health_for_status,
    transition_tenant_status,
)

ALLOWED_TRANSITIONS = {
    TenantStatus.PROVISIONING: {
        TenantStatus.TRIAL,
        TenantStatus.ACTIVE,
        TenantStatus.CLOSED,
    },
    TenantStatus.TRIAL: {
        TenantStatus.ACTIVE,
        TenantStatus.SUSPENDED,
        TenantStatus.OFFBOARDING,
    },
    TenantStatus.ACTIVE: {
        TenantStatus.SUSPENDED,
        TenantStatus.OFFBOARDING,
    },
    TenantStatus.SUSPENDED: {
        TenantStatus.TRIAL,
        TenantStatus.ACTIVE,
        TenantStatus.OFFBOARDING,
    },
    TenantStatus.OFFBOARDING: {TenantStatus.CLOSED},
    TenantStatus.CLOSED: set(),
}


def test_tenant_value_catalogs_are_closed_and_typed() -> None:
    assert [value.value for value in TenantPlan] == [
        "core",
        "professional",
        "enterprise",
    ]
    assert [value.value for value in TenantRegion] == ["tr-1", "eu-1"]
    assert [value.value for value in TenantLocale] == ["tr-TR", "en-US"]
    assert [value.value for value in TenantWeekStartDay] == ["monday", "sunday"]
    assert [value.value for value in TenantDateFormat] == [
        "DD.MM.YYYY",
        "MM/DD/YYYY",
        "YYYY-MM-DD",
    ]
    assert [value.value for value in TenantTimeFormat] == ["24h", "12h"]


@pytest.mark.parametrize("current", TenantStatus)
@pytest.mark.parametrize("target", TenantStatus)
def test_tenant_transition_policy_is_exhaustive(
    current: TenantStatus,
    target: TenantStatus,
) -> None:
    expected_allowed = current is target or target in ALLOWED_TRANSITIONS[current]

    assert can_transition(current, target) is expected_allowed
    assert allowed_transition_targets(current) == frozenset(ALLOWED_TRANSITIONS[current])

    if expected_allowed:
        assert transition_tenant_status(current.value, target.value) is target
        return

    with pytest.raises(TenantLifecycleTransitionError) as error:
        transition_tenant_status(current, target)

    assert error.value.current is current
    assert error.value.target is target


@pytest.mark.parametrize(
    ("status", "access_mode", "health"),
    [
        (
            TenantStatus.PROVISIONING,
            TenantAccessMode.PLATFORM_ONLY,
            TenantHealth.PROVISIONING,
        ),
        (TenantStatus.TRIAL, TenantAccessMode.READ_WRITE, TenantHealth.HEALTHY),
        (TenantStatus.ACTIVE, TenantAccessMode.READ_WRITE, TenantHealth.HEALTHY),
        (
            TenantStatus.SUSPENDED,
            TenantAccessMode.READ_ONLY,
            TenantHealth.RESTRICTED,
        ),
        (
            TenantStatus.OFFBOARDING,
            TenantAccessMode.READ_ONLY,
            TenantHealth.OFFBOARDING,
        ),
        (TenantStatus.CLOSED, TenantAccessMode.DENIED, TenantHealth.CLOSED),
    ],
)
def test_every_status_has_explicit_access_and_health_policy(
    status: TenantStatus,
    access_mode: TenantAccessMode,
    health: TenantHealth,
) -> None:
    assert access_mode_for_status(status) is access_mode
    assert health_for_status(status.value) is health
