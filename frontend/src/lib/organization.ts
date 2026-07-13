import { ApiClientError, type ApiSuccessEnvelope } from "./api-client";
import {
  requestAuthenticatedApi,
  requestAuthenticatedApiEnvelope,
} from "./session";

export type LegalEntityStatus = "active" | "inactive";
export type BranchStatus = "active" | "archived";
export type DepartmentStatus = "active" | "archived";
export type PositionStatus = "active" | "archived";

export interface LegalEntity {
  id: string;
  code: string;
  name: string;
  registered_name: string;
  country_code: string | null;
  tax_number: string | null;
  timezone: string;
  status: LegalEntityStatus;
  is_default: boolean;
  created_at: string;
  updated_at: string;
}

export interface LegalEntityUpdateRequest {
  name?: string;
  registered_name?: string;
  country_code?: string | null;
  tax_number?: string | null;
  timezone?: string;
  status?: LegalEntityStatus;
}

export interface Branch {
  id: string;
  legal_entity_id: string;
  code: string;
  name: string;
  timezone: string;
  country_code: string | null;
  city: string | null;
  address: string | null;
  status: BranchStatus;
  archived_at: string | null;
  accepts_new_assignments: boolean;
  created_at: string;
  updated_at: string;
}

export interface BranchCreateRequest {
  legal_entity_id: string;
  code: string;
  name: string;
  timezone: string;
  country_code: string | null;
  city: string | null;
  address: string | null;
}

export interface BranchUpdateRequest {
  name?: string;
  timezone?: string;
  country_code?: string | null;
  city?: string | null;
  address?: string | null;
}

export interface Department {
  id: string;
  parent_id: string | null;
  code: string;
  name: string;
  status: DepartmentStatus;
  archived_at: string | null;
  has_children: boolean;
  accepts_new_assignments: boolean;
  created_at: string;
  updated_at: string;
}

export interface DepartmentCreateRequest {
  code: string;
  name: string;
  parent_id: string | null;
}

export interface DepartmentUpdateRequest {
  name?: string;
  parent_id?: string | null;
}

export interface Position {
  id: string;
  code: string;
  title: string;
  status: PositionStatus;
  archived_at: string | null;
  accepts_new_assignments: boolean;
  created_at: string;
  updated_at: string;
}

export interface PositionCreateRequest {
  code: string;
  title: string;
}

export interface PositionUpdateRequest {
  title: string;
}

export interface OrganizationListMeta {
  request_id?: string;
  trace_id?: string;
  correlation_id?: string;
  limit: number;
  next_cursor: string | null;
}

export interface CursorListOptions {
  limit: number;
  cursor?: string | null;
}

export interface BranchListOptions extends CursorListOptions {
  legalEntityId: string;
  status?: BranchStatus | "";
}

export interface DepartmentTreeOptions extends CursorListOptions {
  parentId?: string | null;
  includeArchived?: boolean;
}

export interface DepartmentListOptions extends CursorListOptions {
  status?: DepartmentStatus;
}

export interface PositionListOptions extends CursorListOptions {
  status?: PositionStatus | "";
  search?: string;
}

function assertPageMeta(
  envelope: ApiSuccessEnvelope<unknown, OrganizationListMeta>,
): void {
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
}

export async function listLegalEntities(
  options: CursorListOptions,
): Promise<ApiSuccessEnvelope<LegalEntity[], OrganizationListMeta>> {
  const query = new URLSearchParams({ limit: String(options.limit) });
  if (options.cursor) {
    query.set("cursor", options.cursor);
  }

  const envelope = await requestAuthenticatedApiEnvelope<
    LegalEntity[],
    OrganizationListMeta
  >(`/api/v1/legal-entities?${query.toString()}`);
  if (!Array.isArray(envelope.data)) {
    throw new ApiClientError({ status: 200, code: "invalid_response" });
  }
  assertPageMeta(envelope);
  return envelope;
}

export function readLegalEntity(legalEntityId: string): Promise<LegalEntity> {
  return requestAuthenticatedApi<LegalEntity>(
    `/api/v1/legal-entities/${encodeURIComponent(legalEntityId)}`,
  );
}

export function updateLegalEntity(
  legalEntityId: string,
  update: LegalEntityUpdateRequest,
): Promise<LegalEntity> {
  return requestAuthenticatedApi<LegalEntity>(
    `/api/v1/legal-entities/${encodeURIComponent(legalEntityId)}`,
    { method: "PATCH", body: update },
  );
}

export async function listBranches(
  options: BranchListOptions,
): Promise<ApiSuccessEnvelope<Branch[], OrganizationListMeta>> {
  const query = new URLSearchParams({
    limit: String(options.limit),
    legal_entity_id: options.legalEntityId,
  });
  if (options.cursor) {
    query.set("cursor", options.cursor);
  }
  if (options.status) {
    query.set("status", options.status);
  }

  const envelope = await requestAuthenticatedApiEnvelope<
    Branch[],
    OrganizationListMeta
  >(`/api/v1/branches?${query.toString()}`);
  if (!Array.isArray(envelope.data)) {
    throw new ApiClientError({ status: 200, code: "invalid_response" });
  }
  assertPageMeta(envelope);
  return envelope;
}

export function createBranch(branch: BranchCreateRequest): Promise<Branch> {
  return requestAuthenticatedApi<Branch>("/api/v1/branches", {
    method: "POST",
    body: branch,
  });
}

export function updateBranch(
  branchId: string,
  update: BranchUpdateRequest,
): Promise<Branch> {
  return requestAuthenticatedApi<Branch>(
    `/api/v1/branches/${encodeURIComponent(branchId)}`,
    { method: "PATCH", body: update },
  );
}

export function archiveBranch(branchId: string): Promise<Branch> {
  return requestAuthenticatedApi<Branch>(
    `/api/v1/branches/${encodeURIComponent(branchId)}`,
    { method: "DELETE" },
  );
}

export async function listDepartmentTree(
  options: DepartmentTreeOptions,
): Promise<ApiSuccessEnvelope<Department[], OrganizationListMeta>> {
  const query = new URLSearchParams({
    limit: String(options.limit),
    include_archived: String(options.includeArchived ?? false),
  });
  if (options.parentId) {
    query.set("parent_id", options.parentId);
  }
  if (options.cursor) {
    query.set("cursor", options.cursor);
  }

  const envelope = await requestAuthenticatedApiEnvelope<
    Department[],
    OrganizationListMeta
  >(`/api/v1/departments/tree?${query.toString()}`);
  if (!Array.isArray(envelope.data)) {
    throw new ApiClientError({ status: 200, code: "invalid_response" });
  }
  assertPageMeta(envelope);
  return envelope;
}

export async function listDepartments(
  options: DepartmentListOptions,
): Promise<ApiSuccessEnvelope<Department[], OrganizationListMeta>> {
  const query = new URLSearchParams({ limit: String(options.limit) });
  if (options.status) {
    query.set("status", options.status);
  }
  if (options.cursor) {
    query.set("cursor", options.cursor);
  }

  const envelope = await requestAuthenticatedApiEnvelope<
    Department[],
    OrganizationListMeta
  >(`/api/v1/departments?${query.toString()}`);
  if (!Array.isArray(envelope.data)) {
    throw new ApiClientError({ status: 200, code: "invalid_response" });
  }
  assertPageMeta(envelope);
  return envelope;
}

export function createDepartment(
  department: DepartmentCreateRequest,
): Promise<Department> {
  return requestAuthenticatedApi<Department>("/api/v1/departments", {
    method: "POST",
    body: department,
  });
}

export function updateDepartment(
  departmentId: string,
  update: DepartmentUpdateRequest,
): Promise<Department> {
  return requestAuthenticatedApi<Department>(
    `/api/v1/departments/${encodeURIComponent(departmentId)}`,
    { method: "PATCH", body: update },
  );
}

export function archiveDepartment(departmentId: string): Promise<Department> {
  return requestAuthenticatedApi<Department>(
    `/api/v1/departments/${encodeURIComponent(departmentId)}`,
    { method: "DELETE" },
  );
}

export async function listPositions(
  options: PositionListOptions,
): Promise<ApiSuccessEnvelope<Position[], OrganizationListMeta>> {
  const query = new URLSearchParams({ limit: String(options.limit) });
  if (options.cursor) {
    query.set("cursor", options.cursor);
  }
  if (options.status) {
    query.set("status", options.status);
  }
  if (options.search) {
    query.set("search", options.search);
  }

  const envelope = await requestAuthenticatedApiEnvelope<
    Position[],
    OrganizationListMeta
  >(`/api/v1/positions?${query.toString()}`);
  if (!Array.isArray(envelope.data)) {
    throw new ApiClientError({ status: 200, code: "invalid_response" });
  }
  assertPageMeta(envelope);
  return envelope;
}

export function readPosition(positionId: string): Promise<Position> {
  return requestAuthenticatedApi<Position>(
    `/api/v1/positions/${encodeURIComponent(positionId)}`,
  );
}

export function createPosition(
  position: PositionCreateRequest,
): Promise<Position> {
  return requestAuthenticatedApi<Position>("/api/v1/positions", {
    method: "POST",
    body: position,
  });
}

export function updatePosition(
  positionId: string,
  update: PositionUpdateRequest,
): Promise<Position> {
  return requestAuthenticatedApi<Position>(
    `/api/v1/positions/${encodeURIComponent(positionId)}`,
    { method: "PATCH", body: update },
  );
}

export function archivePosition(positionId: string): Promise<Position> {
  return requestAuthenticatedApi<Position>(
    `/api/v1/positions/${encodeURIComponent(positionId)}`,
    { method: "DELETE" },
  );
}
