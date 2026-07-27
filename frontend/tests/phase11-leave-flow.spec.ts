import { expect, test } from "@playwright/test";

import { installTenantSession } from "./support/tenant-session";

const EMPLOYEE_ID = "d1000000-0000-4000-8000-000000000001";
const LEAVE_TYPE_ID = "d2000000-0000-4000-8000-000000000001";
const POLICY_ID = "d3000000-0000-4000-8000-000000000001";
const REQUEST_ID = "d4000000-0000-4000-8000-000000000001";
const ACTOR_ID = "d5000000-0000-4000-8000-000000000001";

const policy = {
  id: POLICY_ID,
  leave_type_id: LEAVE_TYPE_ID,
  leave_type_code: "annual",
  leave_type_name: "Yıllık izin",
  version: 1,
  effective_from: "2026-01-01",
  effective_to: null,
  created_at: "2026-01-01T08:00:00Z",
  paid: true,
  document_required: false,
  negative_balance_allowed: false,
  accrual_enabled: false,
  accrual_days_per_month: 0,
  carryover_enabled: false,
  carryover_limit_days: null,
};

const leaveType = {
  id: LEAVE_TYPE_ID,
  code: "annual",
  name: "Yıllık izin",
  description: "Yıllık ücretli izin",
  is_active: true,
  version: 1,
  current_policy: policy as typeof policy | null,
};

function leaveRequest(status: "pending" | "approved" | "cancelled", version: number) {
  return {
    id: REQUEST_ID,
    employee_id: EMPLOYEE_ID,
    employee_name: "Ece Çalışkan",
    leave_type_id: LEAVE_TYPE_ID,
    leave_type_code: "annual",
    leave_type_name: "Yıllık izin",
    policy_id: POLICY_ID,
    start_date: "2026-08-03",
    end_date: "2026-08-04",
    counted_days: 2,
    status,
    requested_by_user_id: ACTOR_ID,
    decided_by_user_id: status === "approved" ? ACTOR_ID : null,
    employee_note: "Aile ziyareti",
    decision_note: null,
    has_document: false,
    version,
    created_at: "2026-07-27T10:00:00Z",
    decided_at:
      status === "approved" ? "2026-07-27T10:30:00Z" : null,
    timeline: [
      {
        id: "d6000000-0000-4000-8000-000000000001",
        event_type: "submitted",
        status: "pending",
        actor_user_id: ACTOR_ID,
        occurred_at: "2026-07-27T10:00:00Z",
      },
      ...(status === "pending"
        ? []
        : [
            {
              id:
                status === "approved"
                  ? "d6000000-0000-4000-8000-000000000002"
                  : "d6000000-0000-4000-8000-000000000003",
              event_type: status,
              status,
              actor_user_id: ACTOR_ID,
              occurred_at: "2026-07-27T10:30:00Z",
            },
          ]),
    ],
  };
}

const baseUser = {
  id: ACTOR_ID,
  membership_id: "d7000000-0000-4000-8000-000000000001",
  tenant_id: "d8000000-0000-4000-8000-000000000001",
  email: "employee@phase11.example",
  full_name: "Ece Çalışkan",
  tenant: { slug: "phase11", name: "Phase 11" },
  workspace_scope: "tenant",
  roles: [
    {
      id: "d9000000-0000-4000-8000-000000000001",
      code: "employee",
      name: "Çalışan",
      scope_type: "tenant",
    },
  ],
  permissions: [
    "dashboard:read:own",
    "leave:read:own",
    "leave:create:own",
    "leave:cancel:own",
  ],
  permission_version: 1,
};

test("employee creates and cancels an own-scope leave request", async ({
  context,
  page,
}) => {
  let requestState: ReturnType<typeof leaveRequest> | null = null;
  const mutations: string[] = [];

  await installTenantSession({
    context,
    page,
    user: baseUser,
    handleApi: async (route, request, url) => {
      const { pathname } = url;
      if (pathname === "/api/v1/me/leave-balances") {
        expect(url.searchParams.get("period_year")).toBe("2026");
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify([
            {
              id: "da000000-0000-4000-8000-000000000001",
              employee_id: EMPLOYEE_ID,
              period_year: 2026,
              leave_type_id: LEAVE_TYPE_ID,
              leave_type_code: "annual",
              leave_type_name: "Yıllık izin",
              earned_days: 14,
              adjusted_days: 0,
              used_days: 0,
              planned_days: 0,
              available_days: 14,
              negative_balance_allowed: false,
            },
          ]),
        });
        return true;
      }
      if (pathname === "/api/v1/me/leave-balances/history") {
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify([]),
        });
        return true;
      }
      if (pathname === "/api/v1/leave-types") {
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify([leaveType]),
        });
        return true;
      }
      if (
        pathname === "/api/v1/leave-requests" &&
        request.method() === "GET"
      ) {
        expect(url.searchParams.get("scope")).toBe("own");
        expect(url.searchParams.has("employee_id")).toBe(false);
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify(requestState ? [requestState] : []),
        });
        return true;
      }
      if (
        pathname === "/api/v1/leave-requests" &&
        request.method() === "POST"
      ) {
        expect(request.postDataJSON()).toEqual({
          leave_type_id: LEAVE_TYPE_ID,
          start_date: "2026-08-03",
          end_date: "2026-08-04",
          employee_note: "Aile ziyareti",
        });
        expect(request.headers()["x-idempotency-key"]).toMatch(
          /^[0-9a-f-]{36}$/i,
        );
        requestState = leaveRequest("pending", 1);
        mutations.push(pathname);
        await route.fulfill({
          status: 201,
          contentType: "application/json",
          body: JSON.stringify(requestState),
        });
        return true;
      }
      if (
        pathname === `/api/v1/leave-requests/${REQUEST_ID}/cancel`
      ) {
        expect(request.postDataJSON()).toEqual({ expected_version: 1 });
        requestState = leaveRequest("cancelled", 2);
        mutations.push(pathname);
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify(requestState),
        });
        return true;
      }
      return false;
    },
  });

  await page.goto("/leave");
  await expect(
    page.getByRole("heading", { name: "İzinlerim", exact: true }),
  ).toBeVisible();
  await expect(page.getByText("14", { exact: true }).first()).toBeVisible();
  await page.getByLabel("İzin türü").selectOption(LEAVE_TYPE_ID);
  await page.getByLabel("Başlangıç").fill("2026-08-03");
  await page.getByLabel("Bitiş").fill("2026-08-04");
  await page.getByLabel("Çalışan notu").fill("  Aile ziyareti  ");
  await page
    .getByRole("button", { name: "İzin talebini gönder" })
    .click();
  await expect(page.getByRole("status")).toContainText(
    "Sunucu 2 çalışma günü hesapladı",
  );

  await page.getByRole("button", { name: "İptal et" }).click();
  const dialog = page.getByRole("dialog", {
    name: "İzin talebi iptal edilsin mi?",
  });
  await dialog.getByRole("button", { name: "Talebi iptal et" }).click();
  await expect(page.getByRole("status")).toContainText(
    "İzin talebi iptal edildi",
  );
  expect(mutations).toEqual([
    "/api/v1/leave-requests",
    `/api/v1/leave-requests/${REQUEST_ID}/cancel`,
  ]);
});

test("manager portal and direct approvals use server-derived team scope", async ({
  context,
  page,
}) => {
  const managerUser = {
    ...baseUser,
    id: "db000000-0000-4000-8000-000000000001",
    membership_id: "db100000-0000-4000-8000-000000000001",
    email: "manager@phase11.example",
    full_name: "Mert Yönetici",
    roles: [
      {
        id: "db200000-0000-4000-8000-000000000001",
        code: "manager",
        name: "Yönetici",
        scope_type: "tenant",
      },
    ],
    permissions: [
      "dashboard:read:own",
      "employee:read:team",
      "leave:read:team",
      "leave:approve:team",
      "self_service:read:own",
    ],
    permission_version: 2,
  };
  let pending = true;
  let approvalCalls = 0;

  await installTenantSession({
    context,
    page,
    user: managerUser,
    handleApi: async (route, request, url) => {
      const { pathname } = url;
      if (pathname === "/api/v1/approval-tasks") {
        expect(url.searchParams.get("limit")).toBe("25");
        expect(url.searchParams.has("employee_id")).toBe(false);
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify(
            pending
              ? [
                  {
                    id: "db300000-0000-4000-8000-000000000001",
                    request: leaveRequest("pending", 1),
                    available_days: 14,
                    manager_context: "Doğrudan ekip",
                  },
                ]
              : [],
          ),
        });
        return true;
      }
      if (pathname === "/api/v1/teams/me/members") {
        expect(url.searchParams.get("limit")).toBe("50");
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify([]),
        });
        return true;
      }
      if (
        pathname === `/api/v1/leave-requests/${REQUEST_ID}` &&
        request.method() === "GET"
      ) {
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify(leaveRequest("pending", 1)),
        });
        return true;
      }
      if (
        pathname === `/api/v1/leave-requests/${REQUEST_ID}/approve`
      ) {
        expect(request.postDataJSON()).toEqual({ expected_version: 1 });
        pending = false;
        approvalCalls += 1;
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify(leaveRequest("approved", 2)),
        });
        return true;
      }
      return false;
    },
  });

  await page.goto("/manager");
  await expect(
    page.getByRole("heading", { name: "İzin onayları", exact: true }),
  ).toBeVisible();
  await expect(page.getByText("Doğrudan ekip")).toBeVisible();

  await page.goto("/leave/approvals");
  await page.getByRole("button", { name: "Talebi aç" }).click();
  await page
    .getByRole("button", { name: "Onaylamayı gözden geçir" })
    .click();
  await page
    .getByRole("dialog", { name: "İzin talebi onaylansın mı?" })
    .getByRole("button", { name: "Talebi onayla" })
    .click();
  await expect(page.getByRole("status")).toContainText(
    "atomik olarak güncellendi",
  );
  expect(approvalCalls).toBe(1);
});

test("HR creates a leave type and a new immutable policy version", async ({
  context,
  page,
}) => {
  const hrUser = {
    ...baseUser,
    id: "dc000000-0000-4000-8000-000000000001",
    membership_id: "dc100000-0000-4000-8000-000000000001",
    email: "hr@phase11.example",
    full_name: "Deniz İnsan",
    roles: [
      {
        id: "dc200000-0000-4000-8000-000000000001",
        code: "hr_specialist",
        name: "İK uzmanı",
        scope_type: "tenant",
      },
    ],
    permissions: [
      "dashboard:read:own",
      "leave:read:tenant",
      "leave:manage:tenant",
    ],
    permission_version: 3,
  };
  let catalog: typeof leaveType[] = [];
  let policies: typeof policy[] = [];

  await installTenantSession({
    context,
    page,
    user: hrUser,
    handleApi: async (route, request, url) => {
      const { pathname } = url;
      if (pathname === "/api/v1/leave-types") {
        if (request.method() === "POST") {
          expect(request.postDataJSON()).toEqual({
            code: "parental",
            name: "Ebeveyn izni",
            description: "Yeni doğum sonrası izin",
          });
          catalog = [
            {
              ...leaveType,
              code: "parental",
              name: "Ebeveyn izni",
              description: "Yeni doğum sonrası izin",
              current_policy: null,
            },
          ];
          await route.fulfill({
            status: 201,
            contentType: "application/json",
            body: JSON.stringify(catalog[0]),
          });
        } else {
          expect(url.searchParams.get("include_inactive")).toBe("true");
          await route.fulfill({
            status: 200,
            contentType: "application/json",
            body: JSON.stringify(catalog),
          });
        }
        return true;
      }
      if (pathname === "/api/v1/leave-policies") {
        if (request.method() === "POST") {
          expect(request.postDataJSON()).toEqual({
            leave_type_id: LEAVE_TYPE_ID,
            effective_from: "2026-08-01",
            paid: true,
            document_required: false,
            negative_balance_allowed: false,
            accrual_enabled: false,
            accrual_days_per_month: 0,
            carryover_enabled: false,
            carryover_limit_days: null,
          });
          policies = [{ ...policy, effective_from: "2026-08-01" }];
          await route.fulfill({
            status: 201,
            contentType: "application/json",
            body: JSON.stringify(policies[0]),
          });
        } else {
          await route.fulfill({
            status: 200,
            contentType: "application/json",
            body: JSON.stringify(policies),
          });
        }
        return true;
      }
      if (pathname === "/api/v1/holiday-calendars") {
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify([]),
        });
        return true;
      }
      if (pathname === "/api/v1/leave-requests") {
        expect(url.searchParams.get("scope")).toBe("tenant");
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify([]),
        });
        return true;
      }
      return false;
    },
  });

  await page.goto("/leave/admin");
  await expect(
    page.getByRole("heading", { name: "İzin yönetimi", exact: true }),
  ).toBeVisible();
  await page.getByRole("tab", { name: "İzin türleri" }).click();
  await page.getByLabel("Sabit kod").fill("PARENTAL");
  await page.getByLabel("Görünen ad").fill("Ebeveyn izni");
  await page.getByLabel("Açıklama").fill("Yeni doğum sonrası izin");
  await page.getByRole("button", { name: "İzin türü oluştur" }).click();
  await expect(page.getByRole("status")).toContainText(
    "sabit kod korunur",
  );

  await page.getByRole("tab", { name: "Politikalar" }).click();
  await page.getByLabel("Yürürlük tarihi").fill("2026-08-01");
  await page
    .getByRole("button", { name: "Yeni sürümü oluştur" })
    .click();
  await expect(page.getByRole("status")).toContainText(
    "Önceki sürümler değişmeden korundu",
  );
  expect(catalog).toHaveLength(1);
  expect(policies).toHaveLength(1);
});
