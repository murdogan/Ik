import type { AuthUser, WorkspaceScope } from "./auth-contracts";

export const AUTHORIZATION_PERMISSIONS = {
  readUsers: "user:read:tenant",
  inviteUsers: "user:invite:tenant",
  updateUsers: "user:update:tenant",
  assignRoles: "role:assign:tenant",
  readOrganization: "organization:read:tenant",
  updateOrganization: "organization:update:tenant",
  readOwnEmployee: "employee:read:own",
  readTeamEmployees: "employee:read:team",
  readTenantEmployees: "employee:read:tenant",
  updateEmployees: "employee:update:tenant",
  readOwnLeave: "leave:read:own",
  createOwnLeave: "leave:create:own",
  cancelOwnLeave: "leave:cancel:own",
  readTeamLeave: "leave:read:team",
  approveTeamLeave: "leave:approve:team",
  readTenantLeave: "leave:read:tenant",
  manageTenantLeave: "leave:manage:tenant",
  adjustTenantLeave: "leave:adjust:tenant",
  manageDocumentTypes: "document_type:manage:tenant",
  manageEmployeeDocuments: "employee_document:manage:tenant",
  readOwnEmployeeDocuments: "employee_document:read:own",
  uploadOwnEmployeeDocuments: "employee_document:upload:own",
  readOwnRequests: "request:read:own",
  readTeamRequests: "request:read:team",
  readTenantRequests: "request:read:tenant",
  createOwnDocumentRequest: "document_request:create:own",
  readOwnDocumentRequests: "document_request:read:own",
  manageTenantDocumentRequests: "document_request:manage:tenant",
  readOwnAnnouncements: "announcement:read:own",
  manageTenantAnnouncements: "announcement:manage:tenant",
  readOwnNotifications: "notification:read:own",
  readOwnSelfService: "self_service:read:own",
  readOwnPrivacyNotice: "privacy_notice:read:own",
  acknowledgeOwnPrivacyNotice: "privacy_notice:acknowledge:own",
  manageOwnPrivacyConsent: "privacy_consent:manage:own",
  readTenantPrivacyCompliance: "privacy_compliance:read:tenant",
  manageTenantPrivacyNotices: "privacy_notice:manage:tenant",
  manageTenantRetentionPolicies: "retention_policy:manage:tenant",
  readTenantAudit: "audit:read:tenant",
  readPlatformAudit: "audit:read:platform",
  readTenantDashboard: "dashboard:read:tenant",
  readTeamDashboard: "dashboard:read:team",
  readOwnDashboard: "dashboard:read:own",
  readTenantReports: "report:read:tenant",
  readTeamReports: "report:read:team",
  exportTenantReports: "report:export:tenant",
  exportTeamReports: "report:export:team",
  readReportWorkEmail: "report_field:read:work_email",
  manageEmployeeImports: "employee_import:manage:tenant",
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

export function homePathForUser(user: AuthUser): "/home" | "/dashboard" {
  return hasPermission(user, AUTHORIZATION_PERMISSIONS.readOwnSelfService)
    ? "/home"
    : "/dashboard";
}
