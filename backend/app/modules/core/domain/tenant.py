"""Tenant value catalogs and lifecycle policy without framework dependencies."""

from enum import StrEnum


class TenantStatus(StrEnum):
    PROVISIONING = "provisioning"
    TRIAL = "trial"
    ACTIVE = "active"
    SUSPENDED = "suspended"
    OFFBOARDING = "offboarding"
    CLOSED = "closed"


class TenantPlan(StrEnum):
    CORE = "core"
    PROFESSIONAL = "professional"
    ENTERPRISE = "enterprise"


class TenantRegion(StrEnum):
    TR_1 = "tr-1"
    EU_1 = "eu-1"


class TenantLocale(StrEnum):
    TR_TR = "tr-TR"
    EN_US = "en-US"


class TenantWeekStartDay(StrEnum):
    MONDAY = "monday"
    SUNDAY = "sunday"


class TenantDateFormat(StrEnum):
    DAY_MONTH_YEAR = "DD.MM.YYYY"
    MONTH_DAY_YEAR = "MM/DD/YYYY"
    YEAR_MONTH_DAY = "YYYY-MM-DD"


class TenantTimeFormat(StrEnum):
    HOUR_24 = "24h"
    HOUR_12 = "12h"


class TenantAccessMode(StrEnum):
    PLATFORM_ONLY = "platform_only"
    READ_WRITE = "read_write"
    READ_ONLY = "read_only"
    DENIED = "denied"


class TenantHealth(StrEnum):
    PROVISIONING = "provisioning"
    HEALTHY = "healthy"
    RESTRICTED = "restricted"
    OFFBOARDING = "offboarding"
    CLOSED = "closed"


class TenantLifecycleTransitionError(ValueError):
    """Raised when a requested tenant lifecycle transition is not allowed."""

    def __init__(self, current: TenantStatus, target: TenantStatus) -> None:
        self.current = current
        self.target = target
        super().__init__(f"Tenant cannot transition from {current.value} to {target.value}.")


_TRANSITION_TARGETS: dict[TenantStatus, frozenset[TenantStatus]] = {
    TenantStatus.PROVISIONING: frozenset(
        {TenantStatus.TRIAL, TenantStatus.ACTIVE, TenantStatus.CLOSED}
    ),
    TenantStatus.TRIAL: frozenset(
        {TenantStatus.ACTIVE, TenantStatus.SUSPENDED, TenantStatus.OFFBOARDING}
    ),
    TenantStatus.ACTIVE: frozenset(
        {TenantStatus.SUSPENDED, TenantStatus.OFFBOARDING}
    ),
    TenantStatus.SUSPENDED: frozenset(
        {TenantStatus.TRIAL, TenantStatus.ACTIVE, TenantStatus.OFFBOARDING}
    ),
    TenantStatus.OFFBOARDING: frozenset({TenantStatus.CLOSED}),
    TenantStatus.CLOSED: frozenset(),
}

_ACCESS_MODES: dict[TenantStatus, TenantAccessMode] = {
    TenantStatus.PROVISIONING: TenantAccessMode.PLATFORM_ONLY,
    TenantStatus.TRIAL: TenantAccessMode.READ_WRITE,
    TenantStatus.ACTIVE: TenantAccessMode.READ_WRITE,
    TenantStatus.SUSPENDED: TenantAccessMode.READ_ONLY,
    TenantStatus.OFFBOARDING: TenantAccessMode.READ_ONLY,
    TenantStatus.CLOSED: TenantAccessMode.DENIED,
}

_HEALTH: dict[TenantStatus, TenantHealth] = {
    TenantStatus.PROVISIONING: TenantHealth.PROVISIONING,
    TenantStatus.TRIAL: TenantHealth.HEALTHY,
    TenantStatus.ACTIVE: TenantHealth.HEALTHY,
    TenantStatus.SUSPENDED: TenantHealth.RESTRICTED,
    TenantStatus.OFFBOARDING: TenantHealth.OFFBOARDING,
    TenantStatus.CLOSED: TenantHealth.CLOSED,
}


def allowed_transition_targets(
    status: TenantStatus | str,
) -> frozenset[TenantStatus]:
    """Return actual state-change targets; same-state idempotency is implicit."""

    return _TRANSITION_TARGETS[TenantStatus(status)]


def can_transition(current: TenantStatus | str, target: TenantStatus | str) -> bool:
    current_status = TenantStatus(current)
    target_status = TenantStatus(target)
    return current_status is target_status or target_status in _TRANSITION_TARGETS[current_status]


def transition_tenant_status(
    current: TenantStatus | str,
    target: TenantStatus | str,
) -> TenantStatus:
    """Validate a lifecycle change and return its canonical target status."""

    current_status = TenantStatus(current)
    target_status = TenantStatus(target)
    if not can_transition(current_status, target_status):
        raise TenantLifecycleTransitionError(current_status, target_status)
    return target_status


def access_mode_for_status(status: TenantStatus | str) -> TenantAccessMode:
    return _ACCESS_MODES[TenantStatus(status)]


def health_for_status(status: TenantStatus | str) -> TenantHealth:
    return _HEALTH[TenantStatus(status)]
