import {
  expect,
  test,
  type Request as PlaywrightRequest,
  type Route,
} from "@playwright/test";

const PLATFORM_PASSWORD = "A safe platform browser password";
const PLATFORM_ACCESS_TOKEN = "platform-tenant-operations-access";
const TENANT_CURSOR = "tenant-page-two";
const TENANT_ID = "10000000-0000-4000-8000-000000000001";

const tenantStatuses = [
  "active",
  "suspended",
  "provisioning",
  "trial",
  "offboarding",
  "closed",
] as const;
type TenantStatus = (typeof tenantStatuses)[number];

const featureKeys = [
  "organization",
  "employees",
  "documents",
  "leave",
  "self_service",
  "reporting",
  "notifications",
] as const;
type FeatureKey = (typeof featureKeys)[number];

const defaultFeatureState: Record<FeatureKey, boolean> = {
  organization: false,
  employees: true,
  documents: false,
  leave: true,
  self_service: true,
  reporting: true,
  notifications: true,
};

const healthByStatus: Record<TenantStatus, string> = {
  active: "healthy",
  suspended: "restricted",
  provisioning: "provisioning",
  trial: "healthy",
  offboarding: "offboarding",
  closed: "closed",
};

const primaryTenantNames = [
  "Anadolu Teknoloji",
  "Kuzey Lojistik",
  "Mavi Perakende",
  "Doru Sağlık",
  "Pera Tasarım",
  "Eski Tenant",
] as const;

function responseMeta(correlationId = "platform-operations-correlation") {
  return {
    request_id: `${correlationId}-request`,
    trace_id: `${correlationId}-trace`,
    correlation_id: correlationId,
  };
}

function envelope(
  data: unknown,
  meta: Record<string, unknown> = responseMeta(),
): string {
  return JSON.stringify({ data, meta });
}

function tenantListEnvelope(
  data: unknown[],
  nextCursor: string | null,
): string {
  return envelope(data, {
    ...responseMeta("tenant-list-correlation"),
    limit: 200,
    next_cursor: nextCursor,
  });
}

function tenantId(index: number): string {
  return `10000000-0000-4000-8000-${String(index + 1).padStart(12, "0")}`;
}

function tenantName(index: number): string {
  return primaryTenantNames[index] ?? `Demo Tenant ${String(index + 1).padStart(2, "0")}`;
}

function tenantSlug(index: number): string {
  const primarySlugs = [
    "anadolu-teknoloji",
    "kuzey-lojistik",
    "mavi-perakende",
    "doru-saglik",
    "pera-tasarim",
    "eski-tenant",
  ];
  return primarySlugs[index] ?? `demo-tenant-${String(index + 1).padStart(2, "0")}`;
}

function mockTenant(index: number) {
  const status = tenantStatuses[index % tenantStatuses.length];
  const updatedAt = new Date(
    Date.UTC(2026, 6, 28, 12) - index * 24 * 60 * 60 * 1_000,
  ).toISOString();

  return {
    id: tenantId(index),
    slug: tenantSlug(index),
    name: tenantName(index),
    status,
    plan_code: ["core", "professional", "enterprise"][index % 3],
    data_region: index % 2 === 0 ? "tr-1" : "eu-1",
    locale: index % 2 === 0 ? "tr-TR" : "en-US",
    timezone: index % 2 === 0 ? "Europe/Istanbul" : "Europe/Berlin",
    health: healthByStatus[status],
    limits: {
      active_employees: index === 0 ? 250 : null,
    },
    created_at: new Date(Date.UTC(2025, 0, index + 1, 8)).toISOString(),
    updated_at: updatedAt,
  };
}

function mockFeatures(organizationEnabled: boolean) {
  return featureKeys.map((key) => {
    const enabled =
      key === "organization"
        ? organizationEnabled
        : defaultFeatureState[key];
    return {
      key,
      enabled,
      source: enabled === defaultFeatureState[key] ? "default" : "override",
    };
  });
}

const tenants = Array.from({ length: 24 }, (_, index) => mockTenant(index));

const platformAdmin = {
  id: "f2000000-0000-4000-8000-000000000099",
  email: "platform@wealthyfalcon.demo",
  full_name: "Atlas Platform",
  workspace_scope: "platform",
  roles: [
    {
      id: "f3000000-0000-4000-8000-000000000099",
      code: "super_admin",
      name: "Süper yönetici",
      scope_type: "platform",
    },
  ],
  permissions: [
    "tenant:read:platform",
    "tenant:update:platform",
    "feature:read:platform",
    "feature:update:platform",
    "audit:read:platform",
  ],
  permission_version: 11,
  authentication_strength: "multi_factor",
};

function expectPlatformBearer(request: PlaywrightRequest, token: string): void {
  expect(request.headers().authorization).toBe(`Bearer ${token}`);
  expect(request.headers()["x-tenant-id"]).toBeUndefined();
  expect(request.headers()["x-tenant-slug"]).toBeUndefined();
}

test("platform login exposes cursor-complete tenant operations and refreshes a confirmed feature mutation", async ({
  page,
}) => {
  const listCursors: Array<string | null> = [];
  const nonPlatformApiPaths: string[] = [];
  const unknownPlatformApiPaths: string[] = [];
  let tenantDetailGets = 0;
  let featureGets = 0;
  let featurePatches = 0;
  let organizationEnabled = false;

  let observeFeaturePatch = () => {};
  const featurePatchObserved = new Promise<void>((resolve) => {
    observeFeaturePatch = resolve;
  });
  let releaseFeaturePatch = () => {};
  const featurePatchRelease = new Promise<void>((resolve) => {
    releaseFeaturePatch = resolve;
  });

  await page.route("**/api/v1/**", async (route: Route) => {
    const request = route.request();
    const url = new URL(request.url());
    const path = url.pathname;

    if (!path.startsWith("/api/v1/platform/")) {
      nonPlatformApiPaths.push(path);
      await route.fulfill({ status: 418 });
      return;
    }

    if (path === "/api/v1/platform/auth/login") {
      expect(request.method()).toBe("POST");
      expect(request.headers().authorization).toBeUndefined();
      expect(request.postDataJSON()).toEqual({
        email: platformAdmin.email,
        password: PLATFORM_PASSWORD,
      });
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        headers: {
          "set-cookie":
            "wf_platform_refresh=platform-operations-refresh; Path=/; HttpOnly; SameSite=Lax; Max-Age=3600",
        },
        body: envelope({
          status: "authenticated",
          access_token: PLATFORM_ACCESS_TOKEN,
          token_type: "bearer",
          expires_in: 900,
          user: platformAdmin,
        }),
      });
      return;
    }

    expectPlatformBearer(request, PLATFORM_ACCESS_TOKEN);

    if (path === "/api/v1/platform/me") {
      expect(request.method()).toBe("GET");
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: envelope({ user: platformAdmin }),
      });
      return;
    }

    if (path === "/api/v1/platform/tenants") {
      expect(request.method()).toBe("GET");
      expect(url.searchParams.get("limit")).toBe("200");
      const cursor = url.searchParams.get("cursor");
      listCursors.push(cursor);
      if (cursor === null) {
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: tenantListEnvelope(tenants.slice(0, 13), TENANT_CURSOR),
        });
        return;
      }
      expect(cursor).toBe(TENANT_CURSOR);
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: tenantListEnvelope(tenants.slice(13), null),
      });
      return;
    }

    if (path === `/api/v1/platform/tenants/${TENANT_ID}`) {
      expect(request.method()).toBe("GET");
      tenantDetailGets += 1;
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: envelope(tenants[0], responseMeta("tenant-detail-correlation")),
      });
      return;
    }

    if (path === `/api/v1/platform/tenants/${TENANT_ID}/features`) {
      if (request.method() === "GET") {
        featureGets += 1;
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: envelope(
            { features: mockFeatures(organizationEnabled) },
            responseMeta(`feature-get-${featureGets}`),
          ),
        });
        return;
      }

      expect(request.method()).toBe("PATCH");
      expect(request.postDataJSON()).toEqual({
        features: [{ key: "organization", enabled: true }],
      });
      featurePatches += 1;
      organizationEnabled = true;
      observeFeaturePatch();
      await featurePatchRelease;
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: envelope(
          { features: mockFeatures(true) },
          responseMeta("feature-toggle-correlation"),
        ),
      });
      return;
    }

    unknownPlatformApiPaths.push(`${request.method()} ${path}`);
    await route.fulfill({ status: 404 });
  });

  await page.goto("/platform/login");
  await page.getByLabel("E-posta adresi").fill(platformAdmin.email);
  await page.getByLabel("Parola").fill(PLATFORM_PASSWORD);
  await page.getByRole("button", { name: "Platform yönetimine gir" }).click();

  await expect(page).toHaveURL(/\/platform$/);
  await expect(
    page.getByRole("heading", { name: "Platform operasyonları" }),
  ).toBeVisible();
  await expect(page.getByTestId("platform-total-tenants")).toHaveText("24");
  const statusBreakdown = page
    .getByRole("heading", { name: "Durum dağılımı" })
    .locator("xpath=ancestor::section[1]");
  for (const statusLabel of [
    "Hazırlanıyor",
    "Deneme",
    "Aktif",
    "Askıya alınmış",
    "Kapatılıyor",
    "Kapalı",
  ]) {
    await expect(
      statusBreakdown
        .locator("dl > div")
        .filter({ hasText: statusLabel })
        .locator("dd"),
    ).toHaveText("4");
  }

  const recentTable = page.getByRole("table");
  await expect(recentTable.locator("tbody tr")).toHaveCount(6);
  await expect(recentTable.locator("tbody tr").first()).toContainText(
    "Anadolu Teknoloji",
  );
  await expect(recentTable.locator("tbody tr").last()).toContainText(
    "Eski Tenant",
  );
  await expect(
    page.getByRole("link", { name: "Tenant yönetimine git" }),
  ).toHaveAttribute("href", "/platform/tenants");
  await expect(
    page
      .getByRole("navigation", { name: "Platform menüsü", exact: true })
      .getByRole("link", { name: "Tenant yönetimi" }),
  ).toBeVisible();
  expect(listCursors).toEqual([null, TENANT_CURSOR]);

  await page.getByRole("link", { name: "Tenant yönetimine git" }).click();
  await expect(page).toHaveURL(/\/platform\/tenants$/);
  await expect(
    page.getByRole("heading", { name: "Tenant yönetimi" }),
  ).toBeVisible();
  await expect(page.getByText(/24 gösteriliyor ·\s*toplam 24/)).toBeVisible();
  const tenantTable = page.getByRole("table");
  await expect(tenantTable.locator("tbody tr")).toHaveCount(20);
  await expect(page.getByText("Sayfa 1 / 2")).toBeVisible();
  await page.getByRole("button", { name: "Sonraki" }).click();
  await expect(page.getByText("Sayfa 2 / 2")).toBeVisible();
  await expect(tenantTable.locator("tbody tr")).toHaveCount(4);
  await page.getByRole("button", { name: "Önceki" }).click();
  await expect(page.getByText("Sayfa 1 / 2")).toBeVisible();
  expect(listCursors).toEqual([
    null,
    TENANT_CURSOR,
    null,
    TENANT_CURSOR,
  ]);

  await page.setViewportSize({ width: 390, height: 844 });
  await expect(
    page.getByRole("navigation", { name: "Platform menüsü", exact: true }),
  ).toBeHidden();
  const mobileNavigation = page.getByRole("navigation", {
    name: "Mobil platform menüsü",
    exact: true,
  });
  await expect(mobileNavigation).toBeVisible();
  await expect(
    mobileNavigation.getByRole("link", { name: "Tenant yönetimi" }),
  ).toHaveAttribute("aria-current", "page");
  await expect(tenantTable.locator("thead")).toBeHidden();
  await expect(tenantTable.locator("tbody td").first()).toHaveCSS(
    "display",
    "flex",
  );
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth + 1,
    ),
  ).toBe(true);

  await page.getByLabel("Tenant ara").fill("eşleşmeyen-tenant");
  await expect(
    page.getByRole("heading", { name: "Eşleşen tenant bulunamadı" }),
  ).toBeVisible();
  const searchForm = page.getByRole("search");
  await searchForm
    .getByRole("button", { name: "Filtreleri temizle" })
    .click();
  await page
    .getByLabel("Yaşam döngüsü durumu")
    .selectOption({ label: "Askıya alınmış" });
  await expect(page.getByText(/4 gösteriliyor ·\s*toplam 24/)).toBeVisible();
  await expect(tenantTable.locator("tbody tr")).toHaveCount(4);
  await expect(tenantTable).toContainText("Kuzey Lojistik");
  await expect(tenantTable).not.toContainText("Anadolu Teknoloji");

  await searchForm
    .getByRole("button", { name: "Filtreleri temizle" })
    .click();
  await page.getByLabel("Tenant ara").fill("Anadolu");
  await expect(page.getByText(/1 gösteriliyor ·\s*toplam 24/)).toBeVisible();
  await expect(tenantTable.locator("tbody tr")).toHaveCount(1);
  await page
    .getByRole("link", { name: "Anadolu Teknoloji tenantını yönet" })
    .click();

  await expect(page).toHaveURL(new RegExp(`/platform/tenants/${TENANT_ID}$`));
  await expect(
    page.getByRole("heading", { name: "Anadolu Teknoloji" }),
  ).toBeVisible();
  const metadataCard = page
    .getByRole("heading", { name: "Tenant metadata’sı" })
    .locator("xpath=ancestor::section[1]");
  await expect(metadataCard).toContainText(TENANT_ID);
  await expect(metadataCard).toContainText("Sağlıklı");
  await expect(metadataCard).toContainText("Türkiye");
  await expect(metadataCard).toContainText("Europe/Istanbul");
  await expect(metadataCard).toContainText("250");

  const featureCard = page
    .getByRole("heading", { name: "Feature flag’ler" })
    .locator("xpath=ancestor::section[1]");
  await expect(featureCard.locator("article")).toHaveCount(7);
  const organizationFeature = featureCard
    .locator("article")
    .filter({ hasText: "Organizasyon" });
  await expect(
    organizationFeature.getByText("Devre dışı", { exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("complementary", { name: "Tenant veri sınırı" }),
  ).toContainText("Müşteri HR verisi bu ekrana yüklenmez");
  expect(tenantDetailGets).toBe(1);
  expect(featureGets).toBe(1);

  await page
    .getByRole("button", { name: "Organizasyon özelliğini etkinleştir" })
    .click();
  const confirmation = page.getByRole("dialog", {
    name: "Organizasyon özelliğini etkinleştir",
  });
  await expect(confirmation).toBeVisible();
  await confirmation
    .getByRole("button", { name: "Değişikliği uygula" })
    .evaluate((button) => {
      button.dispatchEvent(new MouseEvent("click", { bubbles: true }));
      button.dispatchEvent(new MouseEvent("click", { bubbles: true }));
    });
  await featurePatchObserved;
  await expect(
    confirmation.getByRole("button", {
      name: "Değişiklik uygulanıyor…",
    }),
  ).toBeDisabled();
  await expect(
    confirmation.getByRole("button", { name: "Vazgeç" }),
  ).toBeDisabled();
  expect(featurePatches).toBe(1);
  releaseFeaturePatch();

  await expect(
    page.getByText("Modül özelliği güncellendi", { exact: true }),
  ).toBeVisible();
  await expect(
    page.getByText("Referans: feature-toggle-correlation"),
  ).toBeVisible();
  await expect(
    organizationFeature.getByText("Etkin", { exact: true }),
  ).toBeVisible();
  await expect(organizationFeature).toContainText("Tenant override");
  expect(featurePatches).toBe(1);
  expect(featureGets).toBe(2);
  expect(nonPlatformApiPaths).toEqual([]);
  expect(unknownPlatformApiPaths).toEqual([]);
});

test("tenant navigation and direct route fail closed without the read permission", async ({
  context,
  page,
}) => {
  const restrictedPlatformAdmin = {
    ...platformAdmin,
    permissions: ["audit:read:platform"],
    permission_version: 12,
  };
  const tenantApiPaths: string[] = [];
  const nonPlatformApiPaths: string[] = [];
  let refreshCount = 0;
  let accessToken = "";

  await context.addCookies([
    {
      name: "wf_platform_refresh",
      value: "restricted-platform-refresh",
      url: "http://127.0.0.1:3100",
      httpOnly: true,
      sameSite: "Lax",
    },
  ]);

  await page.route("**/api/v1/**", async (route: Route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname;

    if (!path.startsWith("/api/v1/platform/")) {
      nonPlatformApiPaths.push(path);
      await route.fulfill({ status: 418 });
      return;
    }

    if (path === "/api/v1/platform/auth/refresh") {
      expect(request.method()).toBe("POST");
      refreshCount += 1;
      accessToken = `restricted-platform-access-${refreshCount}`;
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: envelope({
          access_token: accessToken,
          token_type: "bearer",
          expires_in: 900,
          user: restrictedPlatformAdmin,
        }),
      });
      return;
    }

    expectPlatformBearer(request, accessToken);
    if (path === "/api/v1/platform/me") {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: envelope({ user: restrictedPlatformAdmin }),
      });
      return;
    }

    if (path.startsWith("/api/v1/platform/tenants")) {
      tenantApiPaths.push(`${request.method()} ${path}`);
      await route.fulfill({ status: 403 });
      return;
    }

    await route.fulfill({ status: 404 });
  });

  await page.goto("/platform");
  await expect(page).toHaveURL(/\/platform$/);
  await expect(
    page.getByText("Tenant görünümü yetkiniz kapsamında değil"),
  ).toBeVisible();
  await expect(
    page.getByRole("link", { name: "Tenant yönetimi" }),
  ).toHaveCount(0);
  expect(tenantApiPaths).toEqual([]);

  await page.goto("/platform/tenants");
  await expect(page).toHaveURL(/\/platform$/);
  await expect(
    page.getByText("Tenant görünümü yetkiniz kapsamında değil"),
  ).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "Tenant yönetimi" }),
  ).toHaveCount(0);
  await expect(
    page.getByRole("link", { name: "Tenant yönetimi" }),
  ).toHaveCount(0);
  expect(tenantApiPaths).toEqual([]);
  expect(nonPlatformApiPaths).toEqual([]);
});

test("tenant creation ignores same-task duplicate submissions", async ({
  context,
  page,
}) => {
  const tenantCreator = {
    ...platformAdmin,
    permissions: ["tenant:read:platform", "tenant:create:platform"],
  };
  const createdTenant = {
    ...tenants[0],
    id: "10000000-0000-4000-8000-000000000099",
    slug: "guvenli-yeni-tenant",
    name: "Güvenli Yeni Tenant",
    status: "provisioning",
    health: "provisioning",
    limits: { active_employees: 125 },
  };
  let createRequests = 0;
  let listRequests = 0;
  let observeCreateRequest = () => {};
  const createRequestObserved = new Promise<void>((resolve) => {
    observeCreateRequest = resolve;
  });
  let releaseCreateRequest = () => {};
  const createRequestRelease = new Promise<void>((resolve) => {
    releaseCreateRequest = resolve;
  });

  await context.addCookies([
    {
      name: "wf_platform_refresh",
      value: "platform-create-lock-refresh",
      url: "http://127.0.0.1:3100",
      httpOnly: true,
      sameSite: "Lax",
    },
  ]);

  await page.route("**/api/v1/**", async (route: Route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname;

    if (path === "/api/v1/platform/auth/refresh") {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: envelope({
          access_token: PLATFORM_ACCESS_TOKEN,
          token_type: "bearer",
          expires_in: 900,
          user: tenantCreator,
        }),
      });
      return;
    }

    expectPlatformBearer(request, PLATFORM_ACCESS_TOKEN);
    if (path === "/api/v1/platform/me") {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: envelope({ user: tenantCreator }),
      });
      return;
    }

    if (path === "/api/v1/platform/tenants" && request.method() === "GET") {
      listRequests += 1;
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: tenantListEnvelope(
          listRequests === 1
            ? tenants.slice(0, 2)
            : [createdTenant, ...tenants.slice(0, 2)],
          null,
        ),
      });
      return;
    }

    if (path === "/api/v1/platform/tenants" && request.method() === "POST") {
      createRequests += 1;
      expect(request.postDataJSON()).toEqual({
        name: "Güvenli Yeni Tenant",
        slug: "guvenli-yeni-tenant",
        plan_code: "core",
        data_region: "tr-1",
        locale: "tr-TR",
        timezone: "Europe/Istanbul",
        limits: { active_employees: 125 },
      });
      observeCreateRequest();
      await createRequestRelease;
      await route.fulfill({
        status: 201,
        contentType: "application/json",
        body: envelope(createdTenant, responseMeta("tenant-create-lock")),
      });
      return;
    }

    await route.fulfill({ status: 404 });
  });

  await page.goto("/platform/tenants");
  await expect(
    page.getByRole("heading", { name: "Tenant yönetimi" }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Yeni tenant oluştur" }).click();
  const dialog = page.getByRole("dialog", { name: "Yeni tenant oluştur" });
  await dialog.getByLabel("Tenant adı").fill("Güvenli Yeni Tenant");
  await dialog.getByLabel("Tenant kodu").fill("guvenli-yeni-tenant");
  await dialog.getByLabel("Tanımlı aktif çalışan limiti").fill("125");

  await dialog.locator("form").evaluate((form) => {
    form.dispatchEvent(new Event("submit", { bubbles: true, cancelable: true }));
    form.dispatchEvent(new Event("submit", { bubbles: true, cancelable: true }));
  });

  await createRequestObserved;
  await expect.poll(() => createRequests).toBe(1);
  await expect(
    dialog.getByRole("button", { name: "Tenant oluşturuluyor…" }),
  ).toBeDisabled();
  releaseCreateRequest();

  await expect(
    page.getByText("Güvenli Yeni Tenant oluşturuldu", { exact: true }),
  ).toBeVisible();
  await expect.poll(() => listRequests).toBe(2);
  expect(createRequests).toBe(1);
});

test("live platform permission grants and revocations update mounted tenant controls", async ({
  context,
  page,
}) => {
  let currentUser = {
    ...platformAdmin,
    permissions: ["tenant:read:platform", "feature:read:platform"],
    permission_version: 20,
  };
  let meRequests = 0;
  let mutationRequests = 0;

  await context.addCookies([
    {
      name: "wf_platform_refresh",
      value: "platform-live-permission-refresh",
      url: "http://127.0.0.1:3100",
      httpOnly: true,
      sameSite: "Lax",
    },
  ]);

  await page.route("**/api/v1/**", async (route: Route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname;

    if (path === "/api/v1/platform/auth/refresh") {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: envelope({
          access_token: PLATFORM_ACCESS_TOKEN,
          token_type: "bearer",
          expires_in: 900,
          user: currentUser,
        }),
      });
      return;
    }

    expectPlatformBearer(request, PLATFORM_ACCESS_TOKEN);
    if (path === "/api/v1/platform/me") {
      meRequests += 1;
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: envelope({ user: currentUser }),
      });
      return;
    }

    if (path === "/api/v1/platform/tenants") {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: tenantListEnvelope([tenants[0]], null),
      });
      return;
    }

    if (path === `/api/v1/platform/tenants/${TENANT_ID}`) {
      if (request.method() === "PATCH") mutationRequests += 1;
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: envelope(tenants[0]),
      });
      return;
    }

    if (path === `/api/v1/platform/tenants/${TENANT_ID}/features`) {
      if (request.method() === "PATCH") mutationRequests += 1;
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: envelope({ features: mockFeatures(false) }),
      });
      return;
    }

    await route.fulfill({ status: 404 });
  });

  async function revalidateWithPermissions(permissions: string[]) {
    const previousMeRequests = meRequests;
    currentUser = {
      ...currentUser,
      permissions,
      permission_version: currentUser.permission_version + 1,
    };
    await page.evaluate(() => window.dispatchEvent(new Event("focus")));
    await expect.poll(() => meRequests).toBe(previousMeRequests + 1);
  }

  await page.goto("/platform/tenants");
  await expect(
    page.getByRole("heading", { name: "Tenant yönetimi" }),
  ).toBeVisible();
  await page
    .getByRole("link", { name: "Platform genel bakış" })
    .click();
  await expect(page).toHaveURL(/\/platform$/);

  await revalidateWithPermissions(["feature:read:platform"]);
  await expect(
    page.getByText("Tenant görünümü yetkiniz kapsamında değil"),
  ).toBeVisible();

  const meRequestsBeforeBoundaryGrant = meRequests;
  currentUser = {
    ...currentUser,
    permissions: ["tenant:read:platform", "feature:read:platform"],
    permission_version: currentUser.permission_version + 1,
  };
  await page.goBack();
  await expect.poll(() => meRequests).toBe(meRequestsBeforeBoundaryGrant + 1);
  await expect(
    page.getByRole("heading", { name: "Tenant yönetimi" }),
  ).toBeVisible();

  await page
    .getByRole("link", { name: "Anadolu Teknoloji tenantını yönet" })
    .click();
  await expect(
    page.getByRole("heading", { name: "Anadolu Teknoloji" }),
  ).toBeVisible();
  await expect(
    page.getByText("Yaşam döngüsü güncelleme yetkiniz yok"),
  ).toBeVisible();

  await revalidateWithPermissions([
    "tenant:read:platform",
    "tenant:update:platform",
    "feature:read:platform",
    "feature:update:platform",
  ]);
  await page
    .getByLabel("Yeni yaşam döngüsü durumu")
    .selectOption("suspended");
  await page.getByRole("button", { name: "Geçişi incele" }).click();
  const lifecycleConfirmation = page.getByRole("dialog", {
    name: "Askıya alınmış durumuna geçir",
  });
  await expect(lifecycleConfirmation).toBeVisible();

  await revalidateWithPermissions([
    "tenant:read:platform",
    "feature:read:platform",
    "feature:update:platform",
  ]);
  await expect(lifecycleConfirmation).toBeHidden();
  await expect(
    page.getByText("Yaşam döngüsü güncelleme yetkiniz yok"),
  ).toBeVisible();

  const featureButton = page.getByRole("button", {
    name: "Organizasyon özelliğini etkinleştir",
  });
  await featureButton.click();
  const featureConfirmation = page.getByRole("dialog", {
    name: "Organizasyon özelliğini etkinleştir",
  });
  await expect(featureConfirmation).toBeVisible();

  await revalidateWithPermissions([
    "tenant:read:platform",
    "feature:read:platform",
  ]);
  await expect(featureConfirmation).toBeHidden();
  await expect(featureButton).toHaveCount(0);
  expect(mutationRequests).toBe(0);
});

test("platform tenant responses fail closed for malformed bounded and localized fields", async ({
  context,
  page,
}) => {
  const malformedTenants = [
    { title: "short slug", tenant: { ...tenants[0], slug: "a" } },
    {
      title: "overlong slug",
      tenant: { ...tenants[0], slug: "a".repeat(81) },
    },
    { title: "empty name", tenant: { ...tenants[0], name: "" } },
    {
      title: "overlong name",
      tenant: { ...tenants[0], name: "n".repeat(201) },
    },
    {
      title: "unknown timezone",
      tenant: { ...tenants[0], timezone: "Mars/Olympus" },
    },
    {
      title: "timezone abbreviation accepted by Intl but not the IANA contract",
      tenant: { ...tenants[0], timezone: "CST" },
    },
    {
      title: "impossible calendar date",
      tenant: {
        ...tenants[0],
        created_at: "2026-02-30T12:00:00.000Z",
      },
    },
    {
      title: "non-Z UTC offset",
      tenant: {
        ...tenants[0],
        updated_at: "2026-07-28T12:00:00+00:00",
      },
    },
    {
      title: "year zero",
      tenant: {
        ...tenants[0],
        created_at: "0000-01-01T00:00:00Z",
      },
    },
    {
      title: "timestamp junk",
      tenant: {
        ...tenants[0],
        updated_at: "2026-07-28T12:00:00Z trailing",
      },
    },
  ];
  let responseTenant = malformedTenants[0].tenant;

  await context.addCookies([
    {
      name: "wf_platform_refresh",
      value: "malformed-platform-response-refresh",
      url: "http://127.0.0.1:3100",
      httpOnly: true,
      sameSite: "Lax",
    },
  ]);

  await page.route("**/api/v1/**", async (route: Route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname;

    if (path === "/api/v1/platform/auth/refresh") {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: envelope({
          access_token: PLATFORM_ACCESS_TOKEN,
          token_type: "bearer",
          expires_in: 900,
          user: platformAdmin,
        }),
      });
      return;
    }

    expectPlatformBearer(request, PLATFORM_ACCESS_TOKEN);
    if (path === "/api/v1/platform/me") {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: envelope({ user: platformAdmin }),
      });
      return;
    }

    if (path === "/api/v1/platform/tenants") {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: tenantListEnvelope([responseTenant], null),
      });
      return;
    }

    await route.fulfill({ status: 404 });
  });

  for (const candidate of malformedTenants) {
    await test.step(candidate.title, async () => {
      responseTenant = candidate.tenant;
      await page.goto("/platform");
      const alert = page
        .getByRole("alert")
        .filter({ hasText: "Operasyon özeti yüklenemedi" });
      await expect(alert).toContainText(
        "Sunucudan beklenmeyen bir yanıt alındı. Güvenliğiniz için veri gösterilmedi.",
      );
      await expect(page.getByTestId("platform-total-tenants")).toHaveCount(0);
    });
  }
});
