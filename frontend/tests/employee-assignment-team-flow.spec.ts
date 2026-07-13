import { expect, test, type Route } from "@playwright/test";

const tenant = {
  slug: "wealthy-falcon-demo",
  name: "Wealthy Falcon HR Demo",
};

const hrUser = {
  id: "f2000000-0000-4000-8000-000000000031",
  tenant_id: "f1000000-0000-4000-8000-000000000001",
  email: "hr@wealthyfalcon.demo",
  full_name: "Deniz Kaya",
  tenant,
  workspace_scope: "tenant",
  roles: [
    {
      id: "f3000000-0000-4000-8000-000000000004",
      code: "hr_specialist",
      name: "İK Uzmanı",
      scope_type: "tenant",
    },
  ],
  permissions: [
    "dashboard:read:tenant",
    "organization:read:tenant",
    "organization:update:tenant",
    "employee:read:tenant",
    "employee:update:tenant",
  ],
  permission_version: 6,
};

const managerUser = {
  id: "f2000000-0000-4000-8000-000000000032",
  tenant_id: hrUser.tenant_id,
  email: "manager@wealthyfalcon.demo",
  full_name: "Mert Yönetici",
  tenant,
  workspace_scope: "tenant",
  roles: [
    {
      id: "f3000000-0000-4000-8000-000000000007",
      code: "manager",
      name: "Yönetici",
      scope_type: "tenant",
    },
  ],
  permissions: ["dashboard:read:own", "employee:read:own", "employee:read:team"],
  permission_version: 4,
};

const timestamps = {
  created_at: "2026-07-13T08:00:00Z",
  updated_at: "2026-07-13T08:00:00Z",
};

const legalEntity = {
  id: "fa000000-0000-4000-8000-000000000001",
  code: "WF_TR",
  name: "Wealthy Falcon Türkiye",
  registered_name: "Wealthy Falcon İnsan Kaynakları A.Ş.",
  country_code: "TR",
  tax_number: "1234567890",
  timezone: "Europe/Istanbul",
  status: "active",
  is_default: true,
  ...timestamps,
};

const activeBranch = {
  id: "fb000000-0000-4000-8000-000000000001",
  legal_entity_id: legalEntity.id,
  code: "IST_MERKEZ",
  name: "İstanbul Merkez",
  timezone: "Europe/Istanbul",
  country_code: "TR",
  city: "İstanbul",
  address: "Levent",
  status: "active",
  archived_at: null,
  accepts_new_assignments: true,
  ...timestamps,
};

const archivedBranch = {
  ...activeBranch,
  id: "fb000000-0000-4000-8000-000000000099",
  code: "ESKI_SUBE",
  name: "Arşiv Şube",
  status: "archived",
  archived_at: "2026-07-12T08:00:00Z",
  accepts_new_assignments: false,
};

const activeDepartment = {
  id: "fc000000-0000-4000-8000-000000000001",
  parent_id: null,
  code: "ENG",
  name: "Mühendislik",
  status: "active",
  archived_at: null,
  has_children: false,
  accepts_new_assignments: true,
  ...timestamps,
};

const archivedDepartment = {
  ...activeDepartment,
  id: "fc000000-0000-4000-8000-000000000099",
  code: "OLD_ENG",
  name: "Arşiv Departman",
  status: "archived",
  archived_at: "2026-07-12T08:00:00Z",
  accepts_new_assignments: false,
};

const softwarePosition = {
  id: "fd000000-0000-4000-8000-000000000001",
  code: "SOFTWARE_ENGINEER",
  title: "Yazılım Mühendisi",
  status: "active",
  archived_at: null,
  accepts_new_assignments: true,
  ...timestamps,
};

const leadPosition = {
  ...softwarePosition,
  id: "fd000000-0000-4000-8000-000000000002",
  code: "ENGINEERING_LEAD",
  title: "Mühendislik Lideri",
};

const archivedPosition = {
  ...softwarePosition,
  id: "fd000000-0000-4000-8000-000000000099",
  code: "OLD_POSITION",
  title: "Arşiv Pozisyon",
  status: "archived",
  archived_at: "2026-07-12T08:00:00Z",
  accepts_new_assignments: false,
};

const targetEmployee = {
  id: "ee000000-0000-4000-8000-000000000001",
  employee_number: "WF-0042",
  first_name: "Ece",
  last_name: "Çalışkan",
  email: "ece@wealthyfalcon.demo",
  status: "active",
};

const firstManager = {
  id: "ee000000-0000-4000-8000-000000000010",
  full_name: "Mert Yönetici",
  email: "manager@wealthyfalcon.demo",
};

const nextManager = {
  id: "ee000000-0000-4000-8000-000000000011",
  full_name: "Selin Direktör",
  email: "selin@wealthyfalcon.demo",
};

function envelope(
  data: unknown,
  page?: { limit: number; next_cursor: string | null },
): string {
  return JSON.stringify({
    data,
    meta: {
      request_id: "browser-p3i",
      trace_id: "browser-p3i-trace",
      correlation_id: "browser-p3i",
      ...(page ?? {}),
    },
  });
}

function assignment(
  id: string,
  {
    position = softwarePosition,
    manager = firstManager,
    effectiveFrom,
    effectiveTo = null,
    supersedes = null,
    reason = null,
    current = true,
  }: {
    position?: typeof softwarePosition;
    manager?: typeof firstManager;
    effectiveFrom: string;
    effectiveTo?: string | null;
    supersedes?: string | null;
    reason?: string | null;
    current?: boolean;
  },
) {
  return {
    id,
    employee: targetEmployee,
    legal_entity: {
      id: legalEntity.id,
      code: legalEntity.code,
      name: legalEntity.name,
      status: "active",
    },
    branch: {
      id: activeBranch.id,
      code: activeBranch.code,
      name: activeBranch.name,
      status: "active",
    },
    department: {
      id: activeDepartment.id,
      code: activeDepartment.code,
      name: activeDepartment.name,
      status: "active",
    },
    position: {
      id: position.id,
      code: position.code,
      title: position.title,
      status: "active",
    },
    manager: { ...manager, status: "active" },
    effective_from: effectiveFrom,
    effective_to: effectiveTo,
    supersedes_assignment_id: supersedes,
    change_reason: reason,
    is_current: current,
    ...timestamps,
  };
}

test("HR creates and effective-dates a structural employee assignment", async ({
  context,
  page,
}) => {
  let accessToken = "";
  let assignments: ReturnType<typeof assignment>[] = [];
  const creates: unknown[] = [];
  const changes: unknown[] = [];
  const optionSearches: Array<string | null> = [];

  await context.addCookies([
    {
      name: "wf_refresh",
      value: "p3i-hr-refresh",
      url: "http://127.0.0.1:3100",
      httpOnly: true,
      sameSite: "Lax",
    },
  ]);

  await page.route("**/api/v1/**", async (route: Route) => {
    const request = route.request();
    const url = new URL(request.url());
    const path = url.pathname;

    if (path === "/api/v1/auth/refresh") {
      accessToken = "p3i-hr-access";
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: envelope({
          access_token: accessToken,
          token_type: "bearer",
          expires_in: 900,
          user: hrUser,
        }),
      });
      return;
    }

    expect(request.headers().authorization).toBe(`Bearer ${accessToken}`);

    if (path === "/api/v1/me") {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: envelope({ user: hrUser }),
      });
      return;
    }

    if (path === "/api/v1/legal-entities") {
      const limit = Number(url.searchParams.get("limit"));
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: envelope([legalEntity], { limit, next_cursor: null }),
      });
      return;
    }

    if (path === `/api/v1/legal-entities/${legalEntity.id}`) {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: envelope(legalEntity),
      });
      return;
    }

    if (path === "/api/v1/branches") {
      const activeOnly = url.searchParams.get("status") === "active";
      const data = activeOnly ? [activeBranch] : [activeBranch, archivedBranch];
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: envelope(data, {
          limit: Number(url.searchParams.get("limit")),
          next_cursor: null,
        }),
      });
      return;
    }

    if (path === "/api/v1/org-chart") {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: envelope([], { limit: 25, next_cursor: null }),
      });
      return;
    }

    if (path === "/api/v1/departments/tree") {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: envelope([activeDepartment], { limit: 25, next_cursor: null }),
      });
      return;
    }

    if (path === "/api/v1/departments") {
      const activeOnly = url.searchParams.get("status") === "active";
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: envelope(
          activeOnly ? [activeDepartment] : [activeDepartment, archivedDepartment],
          { limit: Number(url.searchParams.get("limit")), next_cursor: null },
        ),
      });
      return;
    }

    if (path === "/api/v1/positions") {
      const activeOnly = url.searchParams.get("status") === "active";
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: envelope(
          activeOnly
            ? [softwarePosition, leadPosition]
            : [softwarePosition, leadPosition, archivedPosition],
          { limit: Number(url.searchParams.get("limit")), next_cursor: null },
        ),
      });
      return;
    }

    if (path === "/api/v1/employee-assignments/options") {
      expect(url.searchParams.get("limit")).toBe("100");
      optionSearches.push(url.searchParams.get("search"));
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: envelope({
          employees: [
            {
              id: targetEmployee.id,
              employee_number: targetEmployee.employee_number,
              full_name: `${targetEmployee.first_name} ${targetEmployee.last_name}`,
              email: targetEmployee.email,
              status: targetEmployee.status,
              current_assignment_id: assignments.find((item) => item.is_current)?.id ?? null,
            },
          ],
          managers: [firstManager, nextManager],
        }),
      });
      return;
    }

    if (path === "/api/v1/employee-assignments" && request.method() === "GET") {
      expect(url.searchParams.get("employee_id")).toBe(targetEmployee.id);
      expect(url.searchParams.get("include_history")).toBe("true");
      const cursor = url.searchParams.get("cursor");
      if (cursor) {
        expect(cursor).toBe("history-next");
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: envelope(assignments.slice(1), { limit: 50, next_cursor: null }),
        });
        return;
      }
      const hasNextHistoryPage = assignments.length > 1;
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: envelope(hasNextHistoryPage ? assignments.slice(0, 1) : assignments, {
          limit: 50,
          next_cursor: hasNextHistoryPage ? "history-next" : null,
        }),
      });
      return;
    }

    if (path === "/api/v1/employee-assignments" && request.method() === "POST") {
      const payload = request.postDataJSON();
      creates.push(payload);
      const created = assignment(
        "ef000000-0000-4000-8000-000000000001",
        { effectiveFrom: payload.effective_from },
      );
      assignments = [created];
      await route.fulfill({
        status: 201,
        contentType: "application/json",
        body: envelope(created),
      });
      return;
    }

    if (
      path === "/api/v1/employee-assignments/ef000000-0000-4000-8000-000000000001" &&
      request.method() === "PATCH"
    ) {
      const payload = request.postDataJSON();
      changes.push(payload);
      const predecessor = {
        ...assignments[0],
        effective_to: "2026-08-01",
        is_current: false,
      };
      const successor = assignment(
        "ef000000-0000-4000-8000-000000000002",
        {
          position: leadPosition,
          manager: nextManager,
          effectiveFrom: payload.effective_from,
          supersedes: predecessor.id,
          reason: payload.change_reason,
          current: false,
        },
      );
      assignments = [successor, predecessor];
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: envelope(successor),
      });
      return;
    }

    await route.fulfill({ status: 404 });
  });

  await page.goto("/organization");

  const panel = page.getByRole("article", { name: "Çalışan atamaları" });
  await expect(panel).toBeVisible();
  await expect(panel.getByText("Henüz yapısal atama yok")).toBeVisible();
  await panel.getByLabel("Çalışan ara").fill("Ece Çalışkan");
  await panel.getByRole("button", { name: "Ara", exact: true }).click();
  await expect(panel.getByText("Henüz yapısal atama yok")).toBeVisible();
  expect(optionSearches).toEqual([null, "Ece Çalışkan"]);
  await panel.getByRole("button", { name: "İlk atamayı oluştur" }).click();

  const createDialog = page.getByRole("dialog", { name: "Ece Çalışkan" });
  await expect(createDialog.getByLabel("Tüzel kişilik")).toHaveValue(
    legalEntity.name,
  );
  await expect(createDialog.getByLabel("Şube").getByRole("option")).toHaveCount(1);
  await expect(
    createDialog.getByRole("option", { name: /Arşiv Şube/ }),
  ).toHaveCount(0);
  await expect(
    createDialog.getByRole("option", { name: /Arşiv Departman/ }),
  ).toHaveCount(0);
  await expect(
    createDialog.getByRole("option", { name: /Arşiv Pozisyon/ }),
  ).toHaveCount(0);
  await createDialog.getByLabel("Yönetici").selectOption(firstManager.id);
  await createDialog.getByLabel("Yürürlük tarihi").fill("2026-07-14");
  await createDialog.getByRole("button", { name: "Atamayı oluştur" }).click();

  await expect(panel.getByText("Yapısal çalışan ataması oluşturuldu.")).toBeVisible();
  await expect(panel.getByText("Yazılım Mühendisi", { exact: true })).toBeVisible();
  expect(creates).toEqual([
    {
      employee_id: targetEmployee.id,
      legal_entity_id: legalEntity.id,
      branch_id: activeBranch.id,
      department_id: activeDepartment.id,
      position_id: softwarePosition.id,
      manager_id: firstManager.id,
      effective_from: "2026-07-14",
      change_reason: null,
    },
  ]);
  expect(JSON.stringify(creates)).not.toContain("tenant_id");

  await panel.getByRole("button", { name: "Atamayı değiştir" }).click();
  const changeDialog = page.getByRole("dialog", { name: "Ece Çalışkan" });
  await changeDialog.getByLabel("Pozisyon").selectOption(leadPosition.id);
  await changeDialog.getByLabel("Yönetici").selectOption(nextManager.id);
  await changeDialog.getByLabel("Yürürlük tarihi").fill("2026-08-01");
  await changeDialog.getByLabel("Değişiklik nedeni").fill("Yeni ekip yapılanması");
  await changeDialog.getByRole("button", { name: "Değişikliği kaydet" }).click();

  await expect(
    panel.getByText("Atama ve raporlama hattı yürürlük tarihine göre değiştirildi."),
  ).toBeVisible();
  await expect(panel.getByText("Mühendislik Lideri", { exact: true })).toBeVisible();
  await expect(panel.getByText("Planlandı", { exact: true })).toBeVisible();
  await panel.getByRole("button", { name: "Daha eski atamaları göster" }).click();
  await expect(panel.getByText("Geçmiş", { exact: true })).toBeVisible();
  expect(changes).toEqual([
    {
      legal_entity_id: legalEntity.id,
      branch_id: activeBranch.id,
      department_id: activeDepartment.id,
      position_id: leadPosition.id,
      manager_id: nextManager.id,
      effective_from: "2026-08-01",
      change_reason: "Yeni ekip yapılanması",
    },
  ]);
  expect(JSON.stringify(changes)).not.toContain("tenant_id");
});

test("manager dashboard renders only the team derived by teams me", async ({
  context,
  page,
}) => {
  let accessToken = "";
  const teamRequestCursors: Array<string | null> = [];
  let employeeRequests = 0;
  const teamAssignment = assignment(
    "ef000000-0000-4000-8000-000000000010",
    { effectiveFrom: "2026-07-01" },
  );
  const secondEmployee = {
    ...targetEmployee,
    id: "ee000000-0000-4000-8000-000000000002",
    employee_number: "WF-0043",
    first_name: "Bora",
    last_name: "Takım",
    email: "bora@wealthyfalcon.demo",
  };
  const secondTeamAssignment = {
    ...teamAssignment,
    id: "ef000000-0000-4000-8000-000000000011",
    employee: secondEmployee,
  };

  await context.addCookies([
    {
      name: "wf_refresh",
      value: "p3i-manager-refresh",
      url: "http://127.0.0.1:3100",
      httpOnly: true,
      sameSite: "Lax",
    },
  ]);

  await page.route("**/api/v1/**", async (route: Route) => {
    const request = route.request();
    const url = new URL(request.url());
    const path = url.pathname;
    if (path === "/api/v1/auth/refresh") {
      accessToken = "p3i-manager-access";
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: envelope({
          access_token: accessToken,
          token_type: "bearer",
          expires_in: 900,
          user: managerUser,
        }),
      });
      return;
    }

    expect(request.headers().authorization).toBe(`Bearer ${accessToken}`);
    if (path === "/api/v1/me") {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: envelope({ user: managerUser }),
      });
      return;
    }
    if (path === "/api/v1/teams/me") {
      const cursor = url.searchParams.get("cursor");
      teamRequestCursors.push(cursor);
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: envelope(
          cursor
            ? [{ employee: secondEmployee, assignment: secondTeamAssignment }]
            : [{ employee: targetEmployee, assignment: teamAssignment }],
          { limit: 50, next_cursor: cursor ? null : "team-next" },
        ),
      });
      return;
    }
    if (path === "/api/v1/employees" || path.startsWith("/api/v1/employees/")) {
      employeeRequests += 1;
      await route.fulfill({ status: 403 });
      return;
    }
    await route.fulfill({ status: 404 });
  });

  await page.goto("/dashboard");

  const team = page.getByRole("article", { name: "Ekibim" });
  await expect(team).toBeVisible();
  await expect(team.getByText("Ece Çalışkan", { exact: true })).toBeVisible();
  await expect(team.getByText("Yazılım Mühendisi", { exact: true })).toBeVisible();
  await team.getByRole("button", { name: "Daha fazla ekip üyesi göster" }).click();
  await expect(team.getByText("Bora Takım", { exact: true })).toBeVisible();
  await expect(page.getByText("Tenant Dışı Çalışan", { exact: true })).toHaveCount(0);
  expect(teamRequestCursors).toEqual([null, "team-next"]);
  expect(employeeRequests).toBe(0);
});
