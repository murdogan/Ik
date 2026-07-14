import { expect, test, type Route } from "@playwright/test";

const PAGE_LIMIT = 25;
const CREATED_EMPLOYEE_ID = "fa000000-0000-4000-8000-000000000099";

function envelope(data: unknown, page?: { limit: number; next_cursor: string | null }) {
  return JSON.stringify({
    data,
    meta: {
      request_id: "browser-p4a",
      trace_id: "browser-p4a-trace",
      correlation_id: "browser-p4a",
      ...(page ?? {}),
    },
  });
}

const hrUser = {
  id: "f2000000-0000-4000-8000-000000000041",
  tenant_id: "f1000000-0000-4000-8000-000000000001",
  email: "hr@wealthyfalcon.demo",
  full_name: "Derya İnsan",
  tenant: {
    slug: "wealthy-falcon-demo",
    name: "Wealthy Falcon HR Demo",
  },
  workspace_scope: "tenant",
  roles: [
    {
      id: "f3000000-0000-4000-8000-000000000004",
      code: "hr_specialist",
      name: "İK uzmanı",
      scope_type: "tenant",
    },
  ],
  permissions: [
    "dashboard:read:own",
    "employee:read:tenant",
    "employee:update:tenant",
    "organization:read:tenant",
  ],
  permission_version: 4,
};

const legalEntity = {
  id: "f7000000-0000-4000-8000-000000000001",
  code: "WF-TR",
  name: "Wealthy Falcon Türkiye",
  registered_name: "Wealthy Falcon Türkiye A.Ş.",
  country_code: "TR",
  tax_number: null,
  timezone: "Europe/Istanbul",
  status: "active",
  is_default: true,
  created_at: "2026-07-01T08:00:00Z",
  updated_at: "2026-07-01T08:00:00Z",
};

const branch = {
  id: "f7100000-0000-4000-8000-000000000001",
  legal_entity_id: legalEntity.id,
  code: "IST",
  name: "İstanbul",
  timezone: "Europe/Istanbul",
  country_code: "TR",
  city: "İstanbul",
  address: null,
  status: "active",
  archived_at: null,
  accepts_new_assignments: true,
  created_at: "2026-07-01T08:00:00Z",
  updated_at: "2026-07-01T08:00:00Z",
};

const department = {
  id: "f7200000-0000-4000-8000-000000000001",
  parent_id: null,
  code: "PEOPLE",
  name: "İnsan ve Kültür",
  status: "active",
  archived_at: null,
  has_children: false,
  accepts_new_assignments: true,
  created_at: "2026-07-01T08:00:00Z",
  updated_at: "2026-07-01T08:00:00Z",
};

const position = {
  id: "f7300000-0000-4000-8000-000000000001",
  code: "HR-SPEC",
  title: "İK Uzmanı",
  status: "active",
  archived_at: null,
  accepts_new_assignments: true,
  created_at: "2026-07-01T08:00:00Z",
  updated_at: "2026-07-01T08:00:00Z",
};

const firstEmployee = {
  id: "fa000000-0000-4000-8000-000000000001",
  employee_number: "WF-001",
  first_name: "Ada",
  last_name: "Yılmaz",
  email: "ada@wealthyfalcon.demo",
  department: department.name,
  position: position.title,
  status: "active",
  employment_start_date: "2025-02-03",
  employment_end_date: null,
  version: 1,
  current_assignment: {
    id: "f7400000-0000-4000-8000-000000000001",
    legal_entity: {
      id: legalEntity.id,
      code: legalEntity.code,
      name: legalEntity.name,
    },
    branch: { id: branch.id, code: branch.code, name: branch.name },
    department: {
      id: department.id,
      code: department.code,
      name: department.name,
    },
    position: { id: position.id, code: position.code, title: position.title },
    effective_from: "2025-02-03",
  },
};

const secondEmployee = {
  ...firstEmployee,
  id: "fa000000-0000-4000-8000-000000000002",
  employee_number: "WF-002",
  first_name: "Bora",
  last_name: "Demir",
  email: "bora@wealthyfalcon.demo",
};

const createdEmployee = {
  id: CREATED_EMPLOYEE_ID,
  employee_number: "WF-099",
  first_name: "Selin",
  last_name: "Arslan",
  email: "selin.arslan@wealthyfalcon.demo",
  department: null,
  position: null,
  status: "active",
  employment_start_date: "2026-08-01",
  employment_end_date: null,
  version: 1,
  current_assignment: null,
};

const createdProfile = {
  core: {
    id: createdEmployee.id,
    employee_number: createdEmployee.employee_number,
    first_name: createdEmployee.first_name,
    last_name: createdEmployee.last_name,
    email: createdEmployee.email,
    status: createdEmployee.status,
    employee_version: createdEmployee.version,
  },
  personal: {
    preferred_name: null,
    birth_date: null,
    phone: null,
    version: 1,
  },
  employment: {
    employment_start_date: createdEmployee.employment_start_date,
    contract_type: null,
    work_type: null,
    version: 1,
  },
  organization: {
    current_assignment: null,
    history: [],
    history_limit: 50,
    history_truncated: false,
  },
};

test("HR filters and pages the directory, creates an employee, and opens its summary", async ({
  context,
  page,
}) => {
  let accessToken = "";
  const employeeListQueries: URLSearchParams[] = [];
  let createBody: unknown = null;
  let detailRequests = 0;

  await context.addCookies([
    {
      name: "wf_refresh",
      value: "p4a-hr-refresh",
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
      accessToken = "p4a-hr-access";
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
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: envelope([legalEntity], { limit: 100, next_cursor: null }),
      });
      return;
    }
    if (path === "/api/v1/branches") {
      expect(url.searchParams.get("legal_entity_id")).toBe(legalEntity.id);
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: envelope([branch], { limit: 100, next_cursor: null }),
      });
      return;
    }
    if (path === "/api/v1/departments") {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: envelope([department], { limit: 100, next_cursor: null }),
      });
      return;
    }
    if (path === "/api/v1/positions") {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: envelope([position], { limit: 100, next_cursor: null }),
      });
      return;
    }

    if (path === "/api/v1/employees" && request.method() === "GET") {
      employeeListQueries.push(new URLSearchParams(url.searchParams));
      const onSecondPage = url.searchParams.get("cursor") === "employees-page-2";
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        headers: onSecondPage ? {} : { "x-next-cursor": "employees-page-2" },
        body: JSON.stringify(onSecondPage ? [secondEmployee] : [firstEmployee]),
      });
      return;
    }

    if (path === "/api/v1/employees" && request.method() === "POST") {
      createBody = request.postDataJSON();
      await route.fulfill({
        status: 201,
        contentType: "application/json",
        body: JSON.stringify(createdEmployee),
      });
      return;
    }

    if (path === `/api/v1/employees/${CREATED_EMPLOYEE_ID}/profile`) {
      detailRequests += 1;
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: envelope(createdProfile),
      });
      return;
    }

    await route.fulfill({ status: 404 });
  });

  await page.goto("/employees");
  await expect(page.getByRole("heading", { name: "Çalışanlar", exact: true })).toBeVisible();
  await expect(page.getByRole("link", { name: "Çalışanlar", exact: true })).toBeVisible();
  await expect(page.getByText("Ada Yılmaz", { exact: true })).toBeVisible();
  expect(employeeListQueries[0].get("limit")).toBe(String(PAGE_LIMIT));

  await page.getByRole("button", { name: "Sonraki" }).click();
  await expect(page.getByText("Bora Demir", { exact: true })).toBeVisible();
  expect(employeeListQueries.at(-1)?.get("cursor")).toBe("employees-page-2");
  await page.getByRole("button", { name: "Önceki" }).click();
  await expect(page.getByText("Ada Yılmaz", { exact: true })).toBeVisible();

  await page.getByLabel("Çalışan ara").fill("Ada");
  await page.getByLabel("Durum").selectOption("active");
  await page.getByLabel("Tüzel kişilik").selectOption(legalEntity.id);
  await page.getByLabel("Şube").selectOption(branch.id);
  await page.getByLabel("Departman").selectOption(department.id);
  await page.getByLabel("Pozisyon").selectOption(position.id);
  await page.getByRole("button", { name: "Filtrele" }).click();

  await expect.poll(() => employeeListQueries.length).toBeGreaterThan(3);
  const filteredQuery = employeeListQueries.at(-1);
  expect(filteredQuery?.get("q")).toBe("Ada");
  expect(filteredQuery?.get("status")).toBe("active");
  expect(filteredQuery?.get("legal_entity_id")).toBe(legalEntity.id);
  expect(filteredQuery?.get("branch_id")).toBe(branch.id);
  expect(filteredQuery?.get("department_id")).toBe(department.id);
  expect(filteredQuery?.get("position_id")).toBe(position.id);
  expect(filteredQuery?.has("cursor")).toBe(false);

  await page.getByRole("button", { name: "Yeni çalışan" }).click();
  const createDialog = page.getByRole("dialog", { name: "Yeni çalışan" });
  await createDialog.getByLabel("Çalışan numarası").fill("WF-099");
  await createDialog.getByLabel("Ad", { exact: true }).fill("Selin");
  await createDialog.getByLabel("Soyad", { exact: true }).fill("Arslan");
  await createDialog
    .getByLabel("İş e-postası (isteğe bağlı)")
    .fill("SELIN.ARSLAN@WEALTHYFALCON.DEMO");
  await createDialog.getByLabel("İşe başlangıç tarihi").fill("2026-08-01");
  await createDialog.getByLabel("Çalışma durumu").selectOption("active");
  await createDialog.getByRole("button", { name: "Çalışanı oluştur" }).click();

  await expect(page).toHaveURL(new RegExp(`/employees/${CREATED_EMPLOYEE_ID}$`));
  await expect(page.getByRole("dialog")).toHaveCount(0);
  await expect(
    page.getByRole("heading", { level: 1, name: "Selin Arslan", exact: true }),
  ).toBeVisible();
  await expect(page.getByText("WF-099", { exact: true }).first()).toBeVisible();
  await expect(page.getByText("Henüz yapısal atama yok")).toBeVisible();
  expect(createBody).toEqual({
    employee_number: "WF-099",
    first_name: "Selin",
    last_name: "Arslan",
    email: "selin.arslan@wealthyfalcon.demo",
    status: "active",
    employment_start_date: "2026-08-01",
  });
  expect(detailRequests).toBeGreaterThan(0);
});

test("employee-read permission controls navigation and blocks direct directory API mounting", async ({
  context,
  page,
}) => {
  const employeeUser = {
    ...hrUser,
    id: "f2000000-0000-4000-8000-000000000042",
    email: "employee@wealthyfalcon.demo",
    full_name: "Ece Çalışkan",
    roles: [
      {
        id: "f3000000-0000-4000-8000-000000000008",
        code: "employee",
        name: "Çalışan",
        scope_type: "tenant",
      },
    ],
    permissions: ["dashboard:read:own", "employee:read:own"],
  };
  let accessToken = "";
  let employeeRequests = 0;

  await context.addCookies([
    {
      name: "wf_refresh",
      value: "p4a-employee-refresh",
      url: "http://127.0.0.1:3100",
      httpOnly: true,
      sameSite: "Lax",
    },
  ]);

  await page.route("**/api/v1/**", async (route: Route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    if (path === "/api/v1/auth/refresh") {
      accessToken = "p4a-employee-access";
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: envelope({
          access_token: accessToken,
          token_type: "bearer",
          expires_in: 900,
          user: employeeUser,
        }),
      });
      return;
    }

    expect(request.headers().authorization).toBe(`Bearer ${accessToken}`);
    if (path === "/api/v1/me") {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: envelope({ user: employeeUser }),
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
  await expect(page.getByRole("heading", { name: "Merhaba, Ece Çalışkan" })).toBeVisible();
  await expect(page.getByRole("link", { name: "Çalışanlar", exact: true })).toHaveCount(0);

  await page.goto("/employees");
  await expect(page).toHaveURL(/\/dashboard$/);
  await expect(page.getByRole("heading", { name: "Merhaba, Ece Çalışkan" })).toBeVisible();
  expect(employeeRequests).toBe(0);
});
