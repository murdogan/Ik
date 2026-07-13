import { expect, test, type Route } from "@playwright/test";

const PAGE_LIMIT = 25;

const tenantAdminRole = {
  id: "f3000000-0000-4000-8000-000000000001",
  code: "tenant_admin",
  name: "Tenant yöneticisi",
  scope_type: "tenant",
};

const sessionUser = {
  id: "f2000000-0000-4000-8000-000000000001",
  tenant_id: "f1000000-0000-4000-8000-000000000001",
  email: "admin@wealthyfalcon.demo",
  full_name: "Maya Stone",
  tenant: {
    slug: "wealthy-falcon-demo",
    name: "Wealthy Falcon HR Demo",
  },
  workspace_scope: "tenant",
  roles: [tenantAdminRole],
  permissions: [
    "dashboard:read:tenant",
    "organization:read:tenant",
    "organization:update:tenant",
  ],
  permission_version: 5,
};

const timestamps = {
  created_at: "2026-07-10T10:00:00Z",
  updated_at: "2026-07-10T10:00:00Z",
};

let legalEntity = {
  id: "fa000000-0000-4000-8000-000000000001",
  code: "WF_TR",
  name: "Wealthy Falcon Türkiye",
  registered_name: "Wealthy Falcon İnsan Kaynakları A.Ş.",
  country_code: "TR" as string | null,
  tax_number: "1234567890" as string | null,
  timezone: "Europe/Istanbul",
  status: "active" as "active" | "inactive",
  is_default: true,
  ...timestamps,
};

function branch(
  id: string,
  code: string,
  name: string,
  city: string,
  status: "active" | "archived" = "active",
) {
  return {
    id,
    legal_entity_id: legalEntity.id,
    code,
    name,
    timezone: "Europe/Istanbul",
    country_code: "TR" as string | null,
    city: city as string | null,
    address: `${city} iş merkezi` as string | null,
    status,
    archived_at: status === "archived" ? "2026-07-11T09:00:00Z" : null,
    accepts_new_assignments: status === "active",
    ...timestamps,
  };
}

function envelope(data: unknown, page?: { limit: number; next_cursor: string | null }) {
  return JSON.stringify({
    data,
    meta: {
      request_id: "browser-p3f",
      trace_id: "browser-p3f-trace",
      correlation_id: "browser-p3f",
      ...(page ?? {}),
    },
  });
}

function errorEnvelope(code: string): string {
  return JSON.stringify({
    error: {
      code,
      message: "Request denied",
      details: null,
      correlation_id: "browser-p3f",
    },
  });
}

test.beforeEach(() => {
  legalEntity = {
    ...legalEntity,
    name: "Wealthy Falcon Türkiye",
    registered_name: "Wealthy Falcon İnsan Kaynakları A.Ş.",
    country_code: "TR",
    tax_number: "1234567890",
    timezone: "Europe/Istanbul",
    status: "active",
    updated_at: timestamps.updated_at,
  };
});

test("tenant admin edits the legal entity and creates, updates, pages, and archives branches", async ({
  context,
  page,
}) => {
  let accessToken = "";
  const secondPageBranch = branch(
    "fb000000-0000-4000-8000-000000000003",
    "ANKARA",
    "Ankara Şubesi",
    "Ankara",
  );
  let branches = [
    branch(
      "fb000000-0000-4000-8000-000000000001",
      "ISTANBUL_MERKEZ",
      "İstanbul Merkez",
      "İstanbul",
    ),
    branch(
      "fb000000-0000-4000-8000-000000000002",
      "IZMIR",
      "İzmir Şubesi",
      "İzmir",
      "archived",
    ),
    ...Array.from({ length: PAGE_LIMIT - 2 }, (_, index) =>
      branch(
        `fb000000-0000-4000-8000-${String(index + 10).padStart(12, "0")}`,
        `SAYFALAMA_${String(index + 1).padStart(2, "0")}`,
        `Sayfalama Şubesi ${String(index + 1).padStart(2, "0")}`,
        "İstanbul",
      ),
    ),
    secondPageBranch,
  ];
  const legalListQueries: URLSearchParams[] = [];
  const branchListQueries: URLSearchParams[] = [];
  const legalPatches: unknown[] = [];
  const branchCreates: unknown[] = [];
  const branchPatches: unknown[] = [];
  const archiveMethods: string[] = [];

  await context.addCookies([
    {
      name: "wf_refresh",
      value: "organization-refresh",
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
      accessToken = "organization-access";
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: envelope({
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
        body: envelope({ user: sessionUser }),
      });
      return;
    }

    if (path === "/api/v1/legal-entities") {
      expect(request.method()).toBe("GET");
      legalListQueries.push(new URLSearchParams(url.searchParams));
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: envelope([legalEntity], { limit: PAGE_LIMIT, next_cursor: null }),
      });
      return;
    }

    if (path === `/api/v1/legal-entities/${legalEntity.id}`) {
      if (request.method() === "PATCH") {
        const payload = request.postDataJSON();
        legalPatches.push(payload);
        legalEntity = {
          ...legalEntity,
          ...payload,
          updated_at: "2026-07-12T12:00:00Z",
        };
      } else {
        expect(request.method()).toBe("GET");
      }
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: envelope(legalEntity),
      });
      return;
    }

    if (path === "/api/v1/branches") {
      if (request.method() === "POST") {
        const payload = request.postDataJSON();
        branchCreates.push(payload);
        const createdBranch = {
          id: "fb000000-0000-4000-8000-000000000004",
          ...payload,
          status: "active" as const,
          archived_at: null,
          accepts_new_assignments: true,
          ...timestamps,
        };
        branches = [...branches, createdBranch];
        await route.fulfill({
          status: 201,
          contentType: "application/json",
          body: envelope(createdBranch),
        });
        return;
      }

      expect(request.method()).toBe("GET");
      branchListQueries.push(new URLSearchParams(url.searchParams));
      expect(url.searchParams.get("legal_entity_id")).toBe(legalEntity.id);
      const status = url.searchParams.get("status");
      const cursor = url.searchParams.get("cursor");
      const filteredBranches = status
        ? branches.filter((item) => item.status === status)
        : branches;
      const pageStart = cursor === "branches-page-2" ? PAGE_LIMIT : 0;
      const listedBranches = filteredBranches.slice(pageStart, pageStart + PAGE_LIMIT);
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: envelope(listedBranches, {
          limit: PAGE_LIMIT,
          next_cursor:
            pageStart + PAGE_LIMIT < filteredBranches.length
              ? "branches-page-2"
              : null,
        }),
      });
      return;
    }

    const targetBranch = branches.find((item) => path === `/api/v1/branches/${item.id}`);
    if (targetBranch) {
      if (request.method() === "PATCH") {
        const payload = request.postDataJSON();
        branchPatches.push(payload);
        const updatedBranch = {
          ...targetBranch,
          ...payload,
          updated_at: "2026-07-12T13:00:00Z",
        };
        branches = branches.map((item) =>
          item.id === updatedBranch.id ? updatedBranch : item,
        );
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: envelope(updatedBranch),
        });
        return;
      }

      if (request.method() === "DELETE") {
        archiveMethods.push(request.method());
        expect(request.postData()).toBeNull();
        const archivedBranch = {
          ...targetBranch,
          status: "archived" as const,
          archived_at: "2026-07-12T14:00:00Z",
          accepts_new_assignments: false,
          updated_at: "2026-07-12T14:00:00Z",
        };
        branches = branches.map((item) =>
          item.id === archivedBranch.id ? archivedBranch : item,
        );
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: envelope(archivedBranch),
        });
        return;
      }
    }

    await route.fulfill({ status: 404 });
  });

  await page.goto("/organization");

  await expect(page.getByRole("heading", { name: "Organizasyon", exact: true })).toBeVisible();
  await expect(page.getByText("İstanbul Merkez")).toBeVisible();
  expect(legalListQueries.at(-1)?.get("limit")).toBe(String(PAGE_LIMIT));
  expect(branchListQueries.at(-1)?.get("limit")).toBe(String(PAGE_LIMIT));

  await page.getByRole("button", { name: "Sonraki" }).last().click();
  await expect(page.getByText("Ankara Şubesi")).toBeVisible();
  expect(branchListQueries.at(-1)?.get("cursor")).toBe("branches-page-2");
  await page.getByRole("button", { name: "Önceki" }).last().click();
  await expect(page.getByText("İstanbul Merkez")).toBeVisible();

  await page.getByRole("button", { name: "Bilgileri düzenle" }).click();
  await expect(page.getByLabel("Sabit kod").first()).toHaveAttribute("readonly", "");
  await page.getByLabel("Görünen ad").fill("Wealthy Falcon Türkiye Operasyonları");
  await page.getByLabel("Vergi numarası").fill("9876543210");
  await page.getByRole("button", { name: "Değişiklikleri kaydet" }).click();
  await expect(page.getByText("Tüzel kişilik bilgileri güncellendi.")).toBeVisible();
  expect(legalPatches).toEqual([
    { name: "Wealthy Falcon Türkiye Operasyonları", tax_number: "9876543210" },
  ]);
  expect(JSON.stringify(legalPatches)).not.toContain("code");
  expect(JSON.stringify(legalPatches)).not.toContain("tenant_id");

  await page.getByRole("button", { name: "Yeni şube" }).first().click();
  const createDialog = page.getByRole("dialog", { name: "Yeni şube" });
  await createDialog.getByLabel("Sabit kod").fill("BURSA");
  await createDialog.getByLabel("Şube adı").fill("Bursa Şubesi");
  await createDialog.getByLabel("Şehir").fill("Bursa");
  await createDialog.getByLabel("Adres").fill("Nilüfer iş merkezi");
  await createDialog.getByRole("button", { name: "Şube oluştur" }).click();
  await expect(page.getByText("Şube oluşturuldu.")).toBeVisible();
  expect(branchCreates).toEqual([
    {
      legal_entity_id: legalEntity.id,
      code: "BURSA",
      name: "Bursa Şubesi",
      timezone: "Europe/Istanbul",
      country_code: "TR",
      city: "Bursa",
      address: "Nilüfer iş merkezi",
    },
  ]);
  expect(JSON.stringify(branchCreates)).not.toContain("actor");

  await page.getByRole("button", { name: "İstanbul Merkez şubesini düzenle" }).click();
  const editDialog = page.getByRole("dialog", { name: "İstanbul Merkez" });
  await expect(editDialog.getByLabel("Sabit kod")).toHaveAttribute("readonly", "");
  await editDialog.getByLabel("Şube adı").fill("İstanbul Avrupa Merkez");
  await editDialog.getByLabel("Adres").fill("Levent iş merkezi");
  await editDialog.getByRole("button", { name: "Değişiklikleri kaydet" }).click();
  await expect(page.getByText("Şube bilgileri güncellendi.")).toBeVisible();
  expect(branchPatches).toEqual([
    { name: "İstanbul Avrupa Merkez", address: "Levent iş merkezi" },
  ]);
  expect(JSON.stringify(branchPatches)).not.toContain("code");
  expect(JSON.stringify(branchPatches)).not.toContain("legal_entity_id");

  await page
    .getByRole("button", { name: "İstanbul Avrupa Merkez şubesini arşivle" })
    .click();
  const archiveDialog = page.getByRole("dialog", {
    name: "İstanbul Avrupa Merkez arşivlensin mi?",
  });
  await expect(archiveDialog.getByText(/Yeni atamalar durdurulacak/)).toBeVisible();
  await archiveDialog.getByRole("button", { name: "Şubeyi arşivle" }).click();
  const archiveSuccessNotice = page
    .getByRole("status")
    .filter({ hasText: "Şube arşivlendi. Geçmiş kaydı korunur" });
  await expect(archiveSuccessNotice).toBeVisible();
  await expect(archiveSuccessNotice).toBeFocused();
  expect(archiveMethods).toEqual(["DELETE"]);

  const archivedRow = page.locator('tr[data-branch-status="archived"]', {
    hasText: "İstanbul Avrupa Merkez",
  });
  await expect(archivedRow).toContainText("Yeni atamaya kapalı");
  await expect(archivedRow.getByText("Geçmiş kayıt")).toBeVisible();

  await page.getByLabel("Şube durumu").selectOption("archived");
  await expect(page.getByText("İstanbul Avrupa Merkez")).toBeVisible();
  expect(branchListQueries.at(-1)?.get("status")).toBe("archived");
  await expect(
    page.getByRole("button", { name: "İstanbul Avrupa Merkez şubesini düzenle" }),
  ).toHaveCount(0);

  await page.setViewportSize({ width: 390, height: 844 });
  const mobileNavigation = page.getByRole("navigation", { name: "Mobil ana menü" });
  await expect(mobileNavigation.getByRole("link", { name: "Organizasyon" })).toHaveAttribute(
    "aria-current",
    "page",
  );
  expect(
    await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth),
  ).toBe(true);
});

test("a user without organization permission is redirected before organization APIs mount", async ({
  context,
  page,
}) => {
  const employee = {
    ...sessionUser,
    id: "f2000000-0000-4000-8000-000000000002",
    email: "employee@wealthyfalcon.demo",
    full_name: "Ece Çalışkan",
    roles: [
      {
        id: "f3000000-0000-4000-8000-000000000002",
        code: "employee",
        name: "Çalışan",
        scope_type: "tenant",
      },
    ],
    permissions: ["dashboard:read:own"],
    permission_version: 1,
  };
  let accessToken = "";
  let organizationRequests = 0;

  await context.addCookies([
    {
      name: "wf_refresh",
      value: "employee-organization-refresh",
      url: "http://127.0.0.1:3100",
      httpOnly: true,
      sameSite: "Lax",
    },
  ]);

  await page.route("**/api/v1/**", async (route: Route) => {
    const path = new URL(route.request().url()).pathname;
    if (path === "/api/v1/auth/refresh") {
      accessToken = "employee-organization-access";
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: envelope({
          access_token: accessToken,
          token_type: "bearer",
          expires_in: 900,
          user: employee,
        }),
      });
      return;
    }
    expect(route.request().headers().authorization).toBe(`Bearer ${accessToken}`);
    if (path === "/api/v1/me") {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: envelope({ user: employee }),
      });
      return;
    }
    if (path.startsWith("/api/v1/legal-entities") || path.startsWith("/api/v1/branches")) {
      organizationRequests += 1;
      await route.fulfill({
        status: 403,
        contentType: "application/json",
        body: errorEnvelope("authorization_denied"),
      });
      return;
    }
    await route.fulfill({ status: 404 });
  });

  await page.goto("/organization");

  await expect(page).toHaveURL(/\/dashboard$/);
  await expect(page.getByRole("heading", { name: "Merhaba, Ece Çalışkan" })).toBeVisible();
  await expect(page.getByRole("link", { name: "Organizasyon" })).toHaveCount(0);
  expect(organizationRequests).toBe(0);
});

test("a disabled organization feature redirects after an authoritative availability probe", async ({
  context,
  page,
}) => {
  let accessToken = "";
  let featureRequests = 0;
  let organizationRequests = 0;

  await context.addCookies([
    {
      name: "wf_refresh",
      value: "disabled-organization-refresh",
      url: "http://127.0.0.1:3100",
      httpOnly: true,
      sameSite: "Lax",
    },
  ]);

  await page.route("**/api/v1/**", async (route: Route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    if (path === "/api/v1/auth/refresh") {
      accessToken = "disabled-organization-access";
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: envelope({
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
        body: envelope({ user: sessionUser }),
      });
      return;
    }
    if (path === "/api/v1/legal-entities" && request.method() === "GET") {
      featureRequests += 1;
      await route.fulfill({
        status: 404,
        contentType: "application/json",
        body: errorEnvelope("organization_feature_unavailable"),
      });
      return;
    }
    if (path.startsWith("/api/v1/legal-entities") || path.startsWith("/api/v1/branches")) {
      organizationRequests += 1;
      await route.fulfill({
        status: 403,
        contentType: "application/json",
        body: errorEnvelope("feature_disabled"),
      });
      return;
    }
    await route.fulfill({ status: 404 });
  });

  await page.goto("/organization");

  await expect(page).toHaveURL(/\/dashboard$/);
  await expect(page.getByRole("heading", { name: "Merhaba, Maya Stone" })).toBeVisible();
  await expect(page.getByRole("link", { name: "Organizasyon" })).toHaveCount(0);
  expect(featureRequests).toBe(1);
  expect(organizationRequests).toBe(0);
});
