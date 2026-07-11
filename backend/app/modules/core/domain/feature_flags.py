"""Typed tenant feature rollout catalog.

The catalog is deliberately code-owned and finite. Tenant-specific state stores only an
allowlisted key and its effective boolean; customer-specific branches or arbitrary flag names are
not part of the contract.
"""

from collections.abc import Mapping
from enum import StrEnum
from types import MappingProxyType


class FeatureFlagKey(StrEnum):
    ORGANIZATION = "organization"
    EMPLOYEES = "employees"
    DOCUMENTS = "documents"
    LEAVE = "leave"
    SELF_SERVICE = "self_service"
    REPORTING = "reporting"
    NOTIFICATIONS = "notifications"


FEATURE_FLAG_KEYS: tuple[FeatureFlagKey, ...] = tuple(FeatureFlagKey)

# Only modules already deployed in the Phase-0 application surface start enabled. Future module
# flags remain visible but disabled until a platform rollout explicitly changes tenant state.
FEATURE_FLAG_DEFAULTS: Mapping[FeatureFlagKey, bool] = MappingProxyType(
    {
        FeatureFlagKey.ORGANIZATION: False,
        FeatureFlagKey.EMPLOYEES: True,
        FeatureFlagKey.DOCUMENTS: False,
        FeatureFlagKey.LEAVE: True,
        FeatureFlagKey.SELF_SERVICE: False,
        FeatureFlagKey.REPORTING: True,
        FeatureFlagKey.NOTIFICATIONS: False,
    }
)


def default_feature_flag_enabled(key: FeatureFlagKey | str) -> bool:
    """Return the rollout default for one canonical feature key."""

    return FEATURE_FLAG_DEFAULTS[FeatureFlagKey(key)]


def is_feature_flag_override(key: FeatureFlagKey | str, enabled: bool) -> bool:
    """Return whether tenant state differs from the deployed-module default."""

    if not isinstance(enabled, bool):
        raise TypeError("enabled must be a boolean")
    return enabled is not default_feature_flag_enabled(key)


__all__ = [
    "FEATURE_FLAG_DEFAULTS",
    "FEATURE_FLAG_KEYS",
    "FeatureFlagKey",
    "default_feature_flag_enabled",
    "is_feature_flag_override",
]
