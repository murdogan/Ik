import { ApiClientError, type ApiSuccessEnvelope } from "./api-client";
import type { RoleSummary } from "./auth-contracts";
import {
  requestAuthenticatedApi,
  requestAuthenticatedApiEnvelope,
} from "./session";

export const USER_STATUSES = ["invited", "active", "locked", "disabled"] as const;

export type UserStatus = (typeof USER_STATUSES)[number];

export interface TenantUser {
  id: string;
  email: string;
  full_name: string;
  status: UserStatus;
  created_at: string;
  updated_at: string;
  roles: RoleSummary[];
  permission_version: number;
}

export interface UserListMeta {
  request_id: string;
  trace_id: string;
  correlation_id: string;
  limit: number;
  next_cursor: string | null;
}

export interface UserListOptions {
  search?: string;
  status?: UserStatus | "";
  limit: number;
  cursor?: string | null;
}

export interface UserUpdateRequest {
  full_name?: string;
  status?: UserStatus;
}

export interface UserInvitationRequest {
  email: string;
  full_name: string;
}

export interface UserInvitation {
  user: {
    id: string;
    email: string;
    full_name: string;
    status: "invited";
  };
  activation_url: string;
  expires_at: string;
}

export async function listTenantUsers(
  options: UserListOptions,
): Promise<ApiSuccessEnvelope<TenantUser[], UserListMeta>> {
  const query = new URLSearchParams({ limit: String(options.limit) });
  const search = options.search?.trim();
  if (search) {
    query.set("search", search);
  }
  if (options.status) {
    query.set("status", options.status);
  }
  if (options.cursor) {
    query.set("cursor", options.cursor);
  }

  const envelope = await requestAuthenticatedApiEnvelope<TenantUser[], UserListMeta>(
    `/api/v1/users?${query.toString()}`,
  );
  if (
    !Number.isInteger(envelope.meta.limit) ||
    envelope.meta.limit < 1 ||
    envelope.meta.limit > 100 ||
    !(
      envelope.meta.next_cursor === null ||
      typeof envelope.meta.next_cursor === "string"
    )
  ) {
    throw new ApiClientError({ status: 200, code: "invalid_response" });
  }
  return envelope;
}

export function readTenantUser(userId: string): Promise<TenantUser> {
  return requestAuthenticatedApi<TenantUser>(
    `/api/v1/users/${encodeURIComponent(userId)}`,
  );
}

export function updateTenantUser(
  userId: string,
  update: UserUpdateRequest,
): Promise<TenantUser> {
  return requestAuthenticatedApi<TenantUser>(
    `/api/v1/users/${encodeURIComponent(userId)}`,
    { method: "PATCH", body: update },
  );
}

export function inviteTenantUser(
  invitation: UserInvitationRequest,
): Promise<UserInvitation> {
  return requestAuthenticatedApi<UserInvitation>("/api/v1/users/invitations", {
    method: "POST",
    body: invitation,
  });
}
