import type { AuthUser, WorkspaceScope } from "./auth-contracts";

export const AUTHORIZATION_PERMISSIONS = {
  readUsers: "user:read:tenant",
  inviteUsers: "user:invite:tenant",
  updateUsers: "user:update:tenant",
  assignRoles: "role:assign:tenant",
  readOrganization: "organization:read:tenant",
  updateOrganization: "organization:update:tenant",
  readTenantAudit: "audit:read:tenant",
  readPlatformAudit: "audit:read:platform",
} as const;

export function hasPermission(
  user: { permissions: readonly string[] },
  permission: string,
): boolean {
  return user.permissions.includes(permission);
}

export function isWorkspace(user: AuthUser, scope: WorkspaceScope): boolean {
  return user.workspace_scope === scope;
}

export function homePathForUser(user: AuthUser): "/dashboard" {
  void user;
  return "/dashboard";
}
