import {
  expect,
  test,
  type BrowserContext,
  type Page,
  type Route,
} from "@playwright/test";

const PAGE_LIMIT = 25;
const ENTITY_ID = "fa000000-0000-4000-8000-000000000001";
const MANAGER_ID = "fb000000-0000-4000-8000-000000000001";
const ADA_USER_ID = "fb000000-0000-4000-8000-000000000002";

const sessionUser = {
  id: "f2000000-0000-4000-8000-000000000003",
  tenant_id: "f1000000-0000-4000-8000-000000000001",
  email: "hr@wealthyfalcon.demo",
  full_name: "Deniz İnsan",
  tenant: {
    slug: "wealthy-falcon-demo",
    name: "Wealthy Falcon HR Demo",
  },
  workspace_scope: "tenant",
  roles: [
    {
      id: "f3000000-0000-4000-8000-000000000003",
      code: "hr_director",
      name: "İK Direktörü",
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

const timestamps = {
  created_at: "2026-07-13T08:00:00Z",
  updated_at: "2026-07-13T08:00:00Z",
};

const legalEntity = {
  id: ENTITY_ID,
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

function pageEnvelope(data: unknown, nextCursor: string | null = null): string {
  return JSON.stringify({
    data,
    meta: {
      request_id: "browser-p3j",
      trace_id: "browser-p3j-trace",
      correlation_id: "browser-p3j",
      limit: PAGE_LIMIT,
      next_cursor: nextCursor,
    },
  });
}

function dataEnvelope(data: unknown): string {
  return JSON.stringify({
    data,
    meta: {
      request_id: "browser-p3j",
      trace_id: "browser-p3j-trace",
      correlation_id: "browser-p3j",
    },
  });
}

function errorEnvelope(code = "request_failed"): string {
  return JSON.stringify({
    error: {
      code,
      message: "Request failed",
      details: null,
      correlation_id: "browser-p3j",
    },
  });
}

function managerRoot() {
  return {
    id: MANAGER_ID,
    node_type: "manager",
    employee_id: null,
    user_id: MANAGER_ID,
    parent_user_id: null,
    assignment_id: null,
    full_name: "Mert Yönetici",
    email: "mert@wealthyfalcon.demo",
    employee_number: null,
    employee_status: null,
    user_status: "active",
    legal_entity: null,
    branch: null,
    department: null,
    position: null,
    has_children: true,
    has_archived_reference: false,
  };
}

function employeeNode({
  id,
  userId,
  fullName,
  employeeNumber,
  archived = false,
}: {
  id: string;
  userId: string | null;
  fullName: string;
  employeeNumber: string;
  archived?: boolean;
}) {
  return {
    id,
    node_type: "employee",
    employee_id: id,
    user_id: userId,
    parent_user_id: MANAGER_ID,
    assignment_id: `fc${id.slice(2)}`,
    full_name: fullName,
    email: `${employeeNumber.toLowerCase()}@wealthyfalcon.demo`,
    employee_number: employeeNumber,
    employee_status: "active",
    user_status: userId ? "active" : null,
    legal_entity: {
      id: ENTITY_ID,
      code: "WF_TR",
      name: "Wealthy Falcon Türkiye",
      status: "active",
    },
    branch: {
      id: "fd000000-0000-4000-8000-000000000001",
      code: "IST",
      name: "İstanbul Merkez",
      status: "active",
    },
    department: {
      id: "fe000000-0000-4000-8000-000000000001",
      code: "PLATFORM",
      name: archived ? "Eski Platform" : "Platform",
      status: archived ? "archived" : "active",
    },
    position: {
      id: "ff000000-0000-4000-8000-000000000001",
      code: "ENGINEER",
      title: "Yazılım Mühendisi",
      status: "active",
    },
    has_children: userId !== null,
    has_archived_reference: archived,
  };
}

async function installWorkspaceRoutes(
  page: Page,
  context: BrowserContext,
  chartHandler: (route: Route, url: URL) => Promise<void>,
): Promise<void> {
  let accessToken = "";
  await context.addCookies([
    {
      name: "wf_refresh",
      value: "p3j-workspace-refresh",
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
      accessToken = "p3j-workspace-access";
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: dataEnvelope({
          access_token: accessToken,
          token_type: "bearer",
          expires_in: 900,
          user: sessionUser,
        }),
      });
      return;
    }

    expect(request.headers().authorization).toBe(`Bearer ${accessToken}`);
    if (path === "/api/v1/me") {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: dataEnvelope({ user: sessionUser }),
      });
      return;
    }
    if (path === "/api/v1/org-chart") {
      await chartHandler(route, url);
      return;
    }
    if (path === "/api/v1/legal-entities") {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: pageEnvelope([legalEntity]),
      });
      return;
    }
    if (path === `/api/v1/legal-entities/${ENTITY_ID}`) {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: dataEnvelope(legalEntity),
      });
      return;
    }
    if (path === "/api/v1/branches") {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: pageEnvelope([
          {
            id: "fd000000-0000-4000-8000-000000000001",
            legal_entity_id: ENTITY_ID,
            code: "IST",
            name: "İstanbul Merkez",
            timezone: "Europe/Istanbul",
            country_code: "TR",
            city: "İstanbul",
            address: "Levent",
            status: "active",
            archived_at: null,
            accepts_new_assignments: true,
            ...timestamps,
          },
        ]),
      });
      return;
    }
    if (path === "/api/v1/departments/tree" || path === "/api/v1/positions") {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: pageEnvelope([]),
      });
      return;
    }
    if (path === "/api/v1/employee-assignments/options") {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: dataEnvelope({ employees: [], managers: [] }),
      });
      return;
    }

    await route.fulfill({ status: 404 });
  });
}

test("HR opens the unified workspace and expands only requested chart levels", async ({
  context,
  page,
}) => {
  let releaseRoots: () => void = () => undefined;
  const rootGate = new Promise<void>((resolve) => {
    releaseRoots = resolve;
  });
  const rootQueries: URLSearchParams[] = [];
  const parentQueries: URLSearchParams[] = [];
  let unpagedParentAttempts = 0;

  await installWorkspaceRoutes(page, context, async (route, url) => {
    if (url.searchParams.get("root") === "true") {
      rootQueries.push(new URLSearchParams(url.searchParams));
      await rootGate;
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: pageEnvelope([managerRoot()]),
      });
      return;
    }

    expect(url.searchParams.get("parent_id")).toBe(MANAGER_ID);
    parentQueries.push(new URLSearchParams(url.searchParams));
    const cursor = url.searchParams.get("cursor");
    if (!cursor) {
      unpagedParentAttempts += 1;
      if (unpagedParentAttempts === 1) {
        await route.fulfill({
          status: 503,
          contentType: "application/json",
          body: errorEnvelope(),
        });
        return;
      }
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: pageEnvelope(
          [
            employeeNode({
              id: "aa000000-0000-4000-8000-000000000001",
              userId: ADA_USER_ID,
              fullName: "Ada Geliştirici",
              employeeNumber: "WF-001",
              archived: true,
            }),
          ],
          "manager-children-page-2",
        ),
      });
      return;
    }

    expect(cursor).toBe("manager-children-page-2");
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: pageEnvelope([
        employeeNode({
          id: "aa000000-0000-4000-8000-000000000002",
          userId: null,
          fullName: "Bora Tasarımcı",
          employeeNumber: "WF-002",
        }),
      ]),
    });
  });

  await page.goto("/dashboard");
  const organizationEntry = page.getByRole("link", {
    name: /Organizasyon çalışma alanını aç/,
  });
  await expect(organizationEntry).toBeVisible();
  await organizationEntry.click();

  await expect(page).toHaveURL(/\/organization$/);
  await expect(page.getByText("Organizasyon kökleri yükleniyor")).toBeVisible();
  expect(parentQueries).toHaveLength(0);
  releaseRoots();

  await expect(page.getByText("Mert Yönetici", { exact: true })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Şubeler ve lokasyonlar" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Departman hiyerarşisi" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Pozisyon kataloğu" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Çalışan atamaları" })).toBeVisible();
  expect(rootQueries).toHaveLength(1);
  expect(rootQueries[0].get("limit")).toBe(String(PAGE_LIMIT));
  expect(rootQueries[0].has("parent_id")).toBe(false);

  await page
    .getByRole("button", { name: "Mert Yönetici doğrudan ekibini göster" })
    .click();
  const childError = page
    .getByRole("alert")
    .filter({ hasText: "Doğrudan ekip yüklenemedi" });
  await expect(childError).toBeVisible();
  await childError.getByRole("button", { name: "Yeniden dene" }).click();

  await expect(page.getByText("Ada Geliştirici", { exact: true })).toBeVisible();
  await expect(page.getByText("Eski Platform · Arşiv")).toBeVisible();
  await expect(page.getByText("Arşiv referansı", { exact: true })).toBeVisible();
  await page
    .getByRole("button", {
      name: "Bu yöneticinin daha fazla ekip üyesini göster",
    })
    .click();
  await expect(page.getByText("Bora Tasarımcı", { exact: true })).toBeVisible();

  expect(parentQueries).toHaveLength(3);
  for (const query of parentQueries) {
    expect(query.get("parent_id")).toBe(MANAGER_ID);
    expect(query.get("limit")).toBe(String(PAGE_LIMIT));
    expect(query.has("root")).toBe(false);
  }
  expect(parentQueries[2].get("cursor")).toBe("manager-children-page-2");
  expect(parentQueries.some((query) => query.get("parent_id") === ADA_USER_ID)).toBe(false);

  await page.setViewportSize({ width: 390, height: 844 });
  expect(
    await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth),
  ).toBe(true);
});

test("organization chart root failure can be retried into a useful empty state", async ({
  context,
  page,
}) => {
  let rootAttempts = 0;
  await installWorkspaceRoutes(page, context, async (route, url) => {
    expect(url.searchParams.get("root")).toBe("true");
    expect(url.searchParams.get("limit")).toBe(String(PAGE_LIMIT));
    rootAttempts += 1;
    if (rootAttempts === 1) {
      await route.fulfill({
        status: 503,
        contentType: "application/json",
        body: errorEnvelope(),
      });
      return;
    }
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: pageEnvelope([]),
    });
  });

  await page.goto("/organization");
  const rootError = page
    .getByRole("alert")
    .filter({ hasText: "Organizasyon şeması yüklenemedi" });
  await expect(rootError).toBeVisible();
  await rootError.getByRole("button", { name: "Yeniden dene" }).click();
  await expect(
    page.getByRole("heading", { name: "Organizasyon şeması henüz oluşmadı" }),
  ).toBeVisible();
  expect(rootAttempts).toBe(2);
});
