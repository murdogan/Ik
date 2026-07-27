import { expect, test } from "@playwright/test";

import { installTenantSession } from "./support/tenant-session";

const employeeUser = {
  id: "b1000000-0000-4000-8000-000000000001",
  membership_id: "b1100000-0000-4000-8000-000000000001",
  tenant_id: "b1200000-0000-4000-8000-000000000001",
  email: "employee@phase11.example",
  full_name: "Ece Çalışkan",
  tenant: { slug: "phase11", name: "Phase 11" },
  workspace_scope: "tenant",
  roles: [
    {
      id: "b1300000-0000-4000-8000-000000000001",
      code: "employee",
      name: "Çalışan",
      scope_type: "tenant",
    },
  ],
  permissions: [
    "dashboard:read:own",
    "employee:read:own",
    "leave:read:own",
    "leave:create:own",
    "leave:cancel:own",
    "employee_document:read:own",
    "employee_document:upload:own",
    "request:read:own",
    "document_request:create:own",
    "document_request:read:own",
    "announcement:read:own",
    "notification:read:own",
    "self_service:read:own",
    "privacy_notice:read:own",
    "privacy_notice:acknowledge:own",
    "privacy_consent:manage:own",
  ],
  permission_version: 1,
};

const privilegedPrefixes = [
  "/api/v1/document-types",
  "/api/v1/document-requests",
  "/api/v1/employee-profile-change-requests",
  "/api/v1/tenant/readiness",
  "/api/v1/privacy/manage",
  "/api/v1/approval-tasks",
  "/api/v1/teams/me/members",
  "/api/v1/reports",
  "/api/v1/export-jobs",
  "/api/v1/employees/imports",
  "/api/v1/leave-types",
  "/api/v1/leave-policies",
  "/api/v1/holiday-calendars",
] as const;

test("employee direct routes never mount tenant-admin, HR, manager, or reporting clients", async ({
  context,
  page,
}) => {
  const privilegedCalls: string[] = [];
  await installTenantSession({
    context,
    page,
    user: employeeUser,
    handleApi: async (route, _request, url) => {
      if (url.pathname === "/api/v1/notifications") {
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify({
            data: [],
            meta: {
              request_id: "phase11-browser",
              trace_id: "phase11-browser-trace",
              correlation_id: "phase11-browser",
              limit: Number(url.searchParams.get("limit")),
              next_cursor: null,
            },
          }),
        });
        return true;
      }
      if (
        privilegedPrefixes.some((prefix) =>
          url.pathname.startsWith(prefix),
        )
      ) {
        privilegedCalls.push(url.pathname);
      }
      return false;
    },
  });

  for (const route of [
    "/document-types",
    "/hr/requests",
    "/announcements/manage",
    "/setup",
    "/privacy/manage",
    "/manager",
    "/reports",
    "/leave/approvals",
    "/leave/admin",
  ]) {
    await page.goto(route);
    await expect(
      page.getByText("Ece Çalışkan", { exact: true }),
    ).toBeVisible();
  }

  await expect(
    page.getByRole("heading", { name: "İzin yönetimi" }),
  ).toHaveCount(0);
  expect(privilegedCalls).toEqual([]);
});

const featureBoundaryCases = [
  {
    route: "/requests",
    feature: "self_service" as const,
    endpoint: "/api/v1/requests",
    redirect: /\/dashboard$/,
  },
  {
    route: "/leave",
    feature: "leave" as const,
    endpoint: "/api/v1/leave-requests",
    redirect: /\/home$/,
  },
  {
    route: "/reports",
    feature: "reporting" as const,
    endpoint: "/api/v1/reports",
    redirect: /\/home$/,
  },
  {
    route: "/notifications",
    feature: "notifications" as const,
    endpoint: "/api/v1/notifications",
    redirect: /\/home$/,
  },
];

for (const boundaryCase of featureBoundaryCases) {
  test(`${boundaryCase.route} redirects before its API mounts when ${boundaryCase.feature} is disabled`, async ({
    context,
    page,
  }) => {
    let domainCalls = 0;
    await installTenantSession({
      context,
      page,
      user: {
        ...employeeUser,
        permissions: [
          ...employeeUser.permissions,
          "report:read:team",
          "report:export:team",
        ],
      },
      featureOverrides: { [boundaryCase.feature]: false },
      handleApi: async (_route, _request, url) => {
        if (url.pathname.startsWith(boundaryCase.endpoint)) {
          domainCalls += 1;
        }
        return false;
      },
    });

    await page.goto(boundaryCase.route);
    await expect(page).toHaveURL(boundaryCase.redirect);
    expect(domainCalls).toBe(0);
  });
}
