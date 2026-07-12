import type { RoleSummary } from "./auth-contracts";
import { requestAuthenticatedApi } from "./session";
import type { TenantUser } from "./user-administration";

export interface RoleDetail extends RoleSummary {
  description: string;
  permissions: string[];
}

export interface PermissionDetail {
  id: string;
  code: string;
  resource: string;
  action: string;
  scope: "own" | "team" | "department" | "branch" | "tenant" | "platform";
  description: string;
}

export function listRoles(): Promise<RoleDetail[]> {
  return requestAuthenticatedApi<RoleDetail[]>("/api/v1/roles");
}

export function listPermissions(): Promise<PermissionDetail[]> {
  return requestAuthenticatedApi<PermissionDetail[]>("/api/v1/permissions");
}

export function replaceUserRoles(userId: string, roleIds: string[]): Promise<TenantUser> {
  return requestAuthenticatedApi<TenantUser>(
    `/api/v1/users/${encodeURIComponent(userId)}/roles`,
    {
      method: "PUT",
      body: { role_ids: roleIds },
    },
  );
}
