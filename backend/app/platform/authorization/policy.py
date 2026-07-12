"""Small exact-match authorization policy with an explicit default denial."""

from __future__ import annotations

from collections.abc import Collection, Iterable
from dataclasses import dataclass
from enum import StrEnum

from app.platform.authorization.catalog import PERMISSIONS_BY_CODE, PermissionName


class AuthorizationEffect(StrEnum):
    ALLOW = "allow"
    DENY = "deny"


@dataclass(frozen=True, slots=True)
class PolicyDecision:
    permission: str
    effect: AuthorizationEffect

    @property
    def allowed(self) -> bool:
        return self.effect is AuthorizationEffect.ALLOW


class DenyByDefaultPolicy:
    """Allow only an exact, known permission held by the authenticated actor."""

    def __init__(self, known_permissions: Iterable[str] | None = None) -> None:
        catalog = PERMISSIONS_BY_CODE if known_permissions is None else known_permissions
        self._known_permissions = frozenset(catalog)

    def decide(
        self,
        required_permission: str | PermissionName,
        granted_permissions: Collection[str],
    ) -> PolicyDecision:
        code = (
            required_permission.code
            if isinstance(required_permission, PermissionName)
            else required_permission
        )
        if not isinstance(code, str):
            raise TypeError("Required permission must be a string or PermissionName")
        effect = (
            AuthorizationEffect.ALLOW
            if code in self._known_permissions and code in granted_permissions
            else AuthorizationEffect.DENY
        )
        return PolicyDecision(permission=code, effect=effect)

    def allows(
        self,
        required_permission: str | PermissionName,
        granted_permissions: Collection[str],
    ) -> bool:
        return self.decide(required_permission, granted_permissions).allowed


__all__ = ["AuthorizationEffect", "DenyByDefaultPolicy", "PolicyDecision"]
