import {
  expect,
  test,
  type Page,
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

function errorEnvelope(
  code: string,
  correlationId = "platform-operations-error",
): string {
  return JSON.stringify({
    error: {
      code,
      message: "Request failed",
      details: null,
      correlation_id: correlationId,
    },
  });
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

let platformSessionUpdateSequence = 0;

async function publishPlatformSessionUpdate(
  page: Page,
  {
    accessToken,
    user,
  }: {
    accessToken: string;
    user: typeof platformAdmin;
  },
): Promise<void> {
  platformSessionUpdateSequence += 1;
  const timestamp = Date.now() + platformSessionUpdateSequence * 1_000;
  await page.evaluate(
    ({ nextAccessToken, nextUser, nextTimestamp, sequence }) => {
      const channel = new BroadcastChannel(
        "wf:platform-session:updates:v1",
      );
      channel.postMessage({
        scope: "platform",
        version: 1,
        senderId: `platform-test-sender-${sequence}`,
        updateId: `platform-test-update-${sequence}`,
        type: "session_updated",
        reason: "established",
        startedAt: nextTimestamp,
        issuedAt: nextTimestamp + 1,
        data: {
          access_token: nextAccessToken,
          token_type: "bearer",
          expires_in: 900,
          user: nextUser,
        },
      });
      channel.close();
    },
    {
      nextAccessToken: accessToken,
      nextUser: user,
      nextTimestamp: timestamp,
      sequence: platformSessionUpdateSequence,
    },
  );
  await page.waitForTimeout(50);
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
    page.getByRole("main", { name: "Platform çalışma alanı" }),
  ).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "Platform operasyonları" }),
  ).toBeVisible();
  await expect(
    page
      .getByRole("navigation", { name: "Platform menüsü", exact: true })
      .getByRole("link", { name: "Platform genel bakış" }),
  ).toHaveAttribute("aria-current", "page");
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

  const recentTable = page.getByRole("table", {
    name: "Son güncellenen tenantlar",
  });
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

  await page.setViewportSize({ width: 390, height: 844 });
  const recentTableScroller = page.getByRole("region", {
    name: "Son güncellenen tenantlar tablosu",
  });
  await expect(recentTable.locator("thead")).toBeVisible();
  await expect(
    recentTable.getByRole("columnheader", { name: "Tenant" }),
  ).toBeVisible();
  expect(
    await recentTableScroller.evaluate(
      (scroller) => scroller.scrollWidth > scroller.clientWidth,
    ),
  ).toBe(true);
  expect(
    await page.evaluate(
      () => document.documentElement.scrollWidth <= window.innerWidth + 1,
    ),
  ).toBe(true);
  await page.setViewportSize({ width: 1280, height: 720 });

  await page.getByRole("link", { name: "Tenant yönetimine git" }).click();
  await expect(page).toHaveURL(/\/platform\/tenants$/);
  await expect(
    page.getByRole("heading", { name: "Tenant yönetimi" }),
  ).toBeVisible();
  await expect(
    page.getByRole("search", {
      name: "Tenant listesinde ara ve filtrele",
    }),
  ).toBeVisible();
  await expect(page.getByText(/24 gösteriliyor ·\s*toplam 24/)).toBeVisible();
  const tenantTable = page.getByRole("table", { name: "Tenant listesi" });
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
    page
      .getByRole("banner", { name: "Platform üst çubuğu" })
      .getByLabel("Wealthy Falcon HR Platform"),
  ).toBeVisible();
  await expect(
    mobileNavigation.getByRole("link", { name: "Tenant yönetimi" }),
  ).toHaveAttribute("aria-current", "page");
  await expect(tenantTable.locator("thead")).toBeVisible();
  await expect(
    tenantTable.getByRole("columnheader", { name: "Tenant" }),
  ).toBeVisible();
  await expect(tenantTable.locator("tbody td").first()).toHaveCSS(
    "display",
    "table-cell",
  );
  expect(
    await page
      .getByRole("region", { name: "Tenant listesi tablosu" })
      .evaluate((scroller) => scroller.scrollWidth > scroller.clientWidth),
  ).toBe(true);
  await expect(
    page
      .getByRole("region", { name: "Tenant listesi tablosu" })
      .getByRole("link", {
        name: "Anadolu Teknoloji tenantını yönet",
      }),
  ).toHaveCSS(
    "min-height",
    "44px",
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
  await expect(
    page.getByRole("region", { name: "Kimlik ve durum" }),
  ).toBeVisible();
  await expect(
    page.getByRole("region", {
      name: "Ticari ve bölgesel bilgiler",
    }),
  ).toBeVisible();
  await expect(
    page.getByRole("region", { name: "Yaşam döngüsü kontrolleri" }),
  ).toBeVisible();

  const featureCard = page
    .getByRole("heading", { name: "Feature flag’ler" })
    .locator("xpath=ancestor::section[1]");
  await expect(
    page.getByRole("region", { name: "Feature kontrolleri" }),
  ).toBeVisible();
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

  const organizationFeatureToggle =
    organizationFeature.getByRole("button");
  await organizationFeatureToggle.click();
  const confirmation = page.getByRole("dialog", {
    name: "Organizasyon özelliğini etkinleştir",
  });
  await expect(confirmation).toBeVisible();
  const cancelConfirmation = confirmation.getByRole("button", {
    name: "Vazgeç",
  });
  const applyConfirmation = confirmation.getByRole("button", {
    name: "Değişikliği uygula",
  });
  await expect(cancelConfirmation).toBeFocused();
  await page.keyboard.press("Shift+Tab");
  await expect(applyConfirmation).toBeFocused();
  await page.keyboard.press("Tab");
  await expect(cancelConfirmation).toBeFocused();
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
  await expect(confirmation).toHaveAttribute("tabindex", "-1");
  await expect(confirmation).toBeFocused();
  await page.keyboard.press("Tab");
  await expect(confirmation).toBeFocused();
  await page.keyboard.press("Shift+Tab");
  await expect(confirmation).toBeFocused();
  await page.keyboard.press("Escape");
  await expect(confirmation).toBeVisible();
  expect(featurePatches).toBe(1);
  releaseFeaturePatch();

  await expect(confirmation).toBeHidden();
  await expect(organizationFeatureToggle).toBeFocused();
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

test("validated lifecycle and feature PATCHes remain committed when their follow-up refresh fails", async ({
  context,
  page,
}) => {
  const longTenantName = `Anadolu ${"x".repeat(190)}`;
  let currentTenant = {
    ...tenants[0],
    name: longTenantName,
    timezone: "US/Eastern",
  };
  let organizationEnabled = false;
  let tenantDetailGets = 0;
  let featureGets = 0;
  let lifecyclePatches = 0;
  let featurePatches = 0;
  let observeLifecycleRefresh = () => {};
  const lifecycleRefreshObserved = new Promise<void>((resolve) => {
    observeLifecycleRefresh = resolve;
  });
  let releaseLifecycleRefresh = () => {};
  const lifecycleRefreshRelease = new Promise<void>((resolve) => {
    releaseLifecycleRefresh = resolve;
  });
  let observeFeatureRefresh = () => {};
  const featureRefreshObserved = new Promise<void>((resolve) => {
    observeFeatureRefresh = resolve;
  });
  let releaseFeatureRefresh = () => {};
  const featureRefreshRelease = new Promise<void>((resolve) => {
    releaseFeatureRefresh = resolve;
  });

  await context.addCookies([
    {
      name: "wf_platform_refresh",
      value: "platform-committed-mutation-refresh",
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

    if (path === `/api/v1/platform/tenants/${TENANT_ID}`) {
      if (request.method() === "PATCH") {
        lifecyclePatches += 1;
        expect(request.postDataJSON()).toEqual({ status: "suspended" });
        currentTenant = {
          ...currentTenant,
          status: "suspended",
          health: "restricted",
          updated_at: "2026-07-29T13:00:00.000Z",
        };
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: envelope(
            currentTenant,
            responseMeta("lifecycle-committed-correlation"),
          ),
        });
        return;
      }

      expect(request.method()).toBe("GET");
      tenantDetailGets += 1;
      if (tenantDetailGets === 1) {
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: envelope(currentTenant),
        });
        return;
      }
      observeLifecycleRefresh();
      await lifecycleRefreshRelease;
      await route.fulfill({
        status: 503,
        contentType: "application/json",
        body: errorEnvelope(
          "platform_temporarily_unavailable",
          "lifecycle-refresh-failed",
        ),
      });
      return;
    }

    if (path === `/api/v1/platform/tenants/${TENANT_ID}/features`) {
      if (request.method() === "PATCH") {
        featurePatches += 1;
        expect(request.postDataJSON()).toEqual({
          features: [{ key: "organization", enabled: true }],
        });
        organizationEnabled = true;
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: envelope(
            { features: mockFeatures(true) },
            responseMeta("feature-committed-correlation"),
          ),
        });
        return;
      }

      expect(request.method()).toBe("GET");
      featureGets += 1;
      if (featureGets === 1) {
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: envelope({ features: mockFeatures(organizationEnabled) }),
        });
        return;
      }
      observeFeatureRefresh();
      await featureRefreshRelease;
      await route.fulfill({
        status: 503,
        contentType: "application/json",
        body: errorEnvelope(
          "platform_temporarily_unavailable",
          "feature-refresh-failed",
        ),
      });
      return;
    }

    await route.fulfill({ status: 404 });
  });

  await page.goto(`/platform/tenants/${TENANT_ID}`);
  await expect(
    page.getByRole("heading", { name: longTenantName }),
  ).toBeVisible();
  const timezone = page.getByLabel("Saat dilimi");
  await expect(timezone).toHaveValue("US/Eastern");
  expect(
    await timezone
      .locator('option[value="US/Eastern"]')
      .count(),
  ).toBe(1);
  await expect(
    page.getByText(
      "Saat dilimi, yerel tarih ve saatlerin nasıl gösterileceğini ve yorumlanacağını belirler.",
      { exact: true },
    ),
  ).toBeVisible();

  await page.setViewportSize({ width: 390, height: 260 });
  await page
    .getByLabel("Yeni yaşam döngüsü durumu")
    .selectOption("suspended");
  await page.getByRole("button", { name: "Geçişi incele" }).click();
  const lifecycleConfirmation = page.getByRole("dialog", {
    name: "Askıya alınmış durumuna geçir",
  });
  await expect(lifecycleConfirmation).toBeVisible();
  const compactDialogMetrics = await lifecycleConfirmation.evaluate(
    (dialog) => {
      const body = dialog.children.item(1) as HTMLElement | null;
      const backdrop = dialog.parentElement;
      return {
        horizontalOverflow: dialog.scrollWidth > dialog.clientWidth,
        bodyHasHeight: body !== null && body.clientHeight > 0,
        backdropScrolls:
          backdrop !== null &&
          backdrop.scrollHeight > backdrop.clientHeight,
        viewportHorizontalOverflow:
          document.documentElement.scrollWidth > window.innerWidth + 1,
      };
    },
  );
  expect(compactDialogMetrics.horizontalOverflow).toBe(false);
  expect(compactDialogMetrics.bodyHasHeight).toBe(true);
  expect(compactDialogMetrics.backdropScrolls).toBe(true);
  expect(compactDialogMetrics.viewportHorizontalOverflow).toBe(false);
  for (const control of [
    lifecycleConfirmation.getByRole("heading", {
      name: "Askıya alınmış durumuna geçir",
    }),
    lifecycleConfirmation.getByRole("button", { name: "Vazgeç" }),
    lifecycleConfirmation.getByRole("button", {
      name: "Değişikliği uygula",
    }),
  ]) {
    await control.scrollIntoViewIfNeeded();
    await expect(control).toBeInViewport();
    const bounds = await control.boundingBox();
    expect(bounds).not.toBeNull();
    expect(bounds!.y).toBeGreaterThanOrEqual(-1);
    expect(bounds!.y + bounds!.height).toBeLessThanOrEqual(261);
  }
  await page.setViewportSize({ width: 1280, height: 720 });

  await lifecycleConfirmation
    .getByRole("button", { name: "Değişikliği uygula" })
    .click();
  try {
    await lifecycleRefreshObserved;
    await expect(lifecycleConfirmation).toBeHidden();
    await expect(
      page.getByText("Yaşam döngüsü güncellendi", { exact: true }),
    ).toBeVisible();
    await expect(
      page.getByText("Referans: lifecycle-committed-correlation"),
    ).toBeVisible();
    await expect(
      page.getByLabel("Yeni yaşam döngüsü durumu"),
    ).toHaveValue("");
    await expect(
      page.getByLabel("Yeni yaşam döngüsü durumu"),
    ).toBeFocused();
    await expect(
      page.locator('[data-status="suspended"]').first(),
    ).toContainText("Askıya alınmış");
    expect(lifecyclePatches).toBe(1);
  } finally {
    releaseLifecycleRefresh();
  }

  await expect(
    page.getByText("İşlem uygulandı, güncel görünüm alınamadı", {
      exact: true,
    }),
  ).toBeVisible();
  await expect(
    page.getByText("İşlem tamamlanamadı", { exact: true }),
  ).toHaveCount(0);
  await expect(lifecycleConfirmation).toBeHidden();
  await expect(
    page.locator('[data-status="suspended"]').first(),
  ).toContainText("Askıya alınmış");
  expect(lifecyclePatches).toBe(1);

  const organizationFeature = page
    .getByRole("heading", { name: "Feature flag’ler" })
    .locator("xpath=ancestor::section[1]")
    .locator("article")
    .filter({ hasText: "Organizasyon" });
  await organizationFeature.getByRole("button").click();
  const featureConfirmation = page.getByRole("dialog", {
    name: "Organizasyon özelliğini etkinleştir",
  });
  await featureConfirmation
    .getByRole("button", { name: "Değişikliği uygula" })
    .click();
  try {
    await featureRefreshObserved;
    await expect(featureConfirmation).toBeHidden();
    await expect(
      page.getByText("Modül özelliği güncellendi", { exact: true }),
    ).toBeVisible();
    await expect(
      page.getByText("Referans: feature-committed-correlation"),
    ).toBeVisible();
    await expect(
      organizationFeature.getByText("Etkin", { exact: true }),
    ).toBeVisible();
    await expect(organizationFeature).toContainText("Tenant override");
    expect(featurePatches).toBe(1);
  } finally {
    releaseFeatureRefresh();
  }

  await expect(
    page.getByText("İşlem uygulandı, güncel görünüm alınamadı", {
      exact: true,
    }),
  ).toBeVisible();
  await expect(
    page.getByText("İşlem tamamlanamadı", { exact: true }),
  ).toHaveCount(0);
  await expect(featureConfirmation).toBeHidden();
  await expect(
    organizationFeature.getByText("Etkin", { exact: true }),
  ).toBeVisible();
  expect(featurePatches).toBe(1);
});

test("validated metadata PATCH is committed before its follow-up refresh and is never presented as failed", async ({
  context,
  page,
}) => {
  const tenantUpdater = {
    ...platformAdmin,
    permissions: ["tenant:read:platform", "tenant:update:platform"],
    permission_version: 32,
  };
  const committedTenant = {
    ...tenants[0],
    name: "Anadolu Teknoloji Güncel",
    updated_at: "2026-07-29T14:00:00.000Z",
  };
  let tenantDetailGets = 0;
  let metadataPatches = 0;
  let observeMetadataRefresh = () => {};
  const metadataRefreshObserved = new Promise<void>((resolve) => {
    observeMetadataRefresh = resolve;
  });
  let releaseMetadataRefresh = () => {};
  const metadataRefreshRelease = new Promise<void>((resolve) => {
    releaseMetadataRefresh = resolve;
  });

  await context.addCookies([
    {
      name: "wf_platform_refresh",
      value: "platform-metadata-committed-refresh",
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
          user: tenantUpdater,
        }),
      });
      return;
    }

    expectPlatformBearer(request, PLATFORM_ACCESS_TOKEN);
    if (path === "/api/v1/platform/me") {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: envelope({ user: tenantUpdater }),
      });
      return;
    }

    if (path === `/api/v1/platform/tenants/${TENANT_ID}`) {
      if (request.method() === "PATCH") {
        metadataPatches += 1;
        if (metadataPatches === 2) {
          expect(request.postDataJSON()).toEqual({
            name: "Kaydedilmemiş Tenant Adı",
          });
          await route.fulfill({
            status: 503,
            contentType: "application/json",
            body: errorEnvelope(
              "platform_temporarily_unavailable",
              "metadata-patch-failed",
            ),
          });
          return;
        }

        expect(metadataPatches).toBe(1);
        expect(request.postDataJSON()).toEqual({
          name: "Anadolu Teknoloji Güncel",
        });
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: envelope(
            committedTenant,
            responseMeta("metadata-committed-correlation"),
          ),
        });
        return;
      }

      expect(request.method()).toBe("GET");
      tenantDetailGets += 1;
      if (tenantDetailGets === 1) {
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: envelope(tenants[0]),
        });
        return;
      }

      observeMetadataRefresh();
      await metadataRefreshRelease;
      await route.fulfill({
        status: 503,
        contentType: "application/json",
        body: errorEnvelope(
          "platform_temporarily_unavailable",
          "metadata-refresh-failed",
        ),
      });
      return;
    }

    await route.fulfill({ status: 404 });
  });

  await page.goto(`/platform/tenants/${TENANT_ID}`);
  const settingsCard = page
    .getByRole("heading", { name: "Tenant ayarları" })
    .locator("xpath=ancestor::section[1]");
  await settingsCard
    .getByLabel("Tenant adı")
    .fill("Anadolu Teknoloji Güncel");
  await settingsCard
    .getByRole("button", { name: "Ayarları kaydet" })
    .click();

  try {
    await metadataRefreshObserved;
    await expect(
      page.getByText("Tenant ayarları güncellendi", { exact: true }),
    ).toBeVisible();
    await expect(
      page.getByText("Referans: metadata-committed-correlation"),
    ).toBeVisible();
    await expect(settingsCard.getByLabel("Tenant adı")).toHaveValue(
      "Anadolu Teknoloji Güncel",
    );
    await expect(
      settingsCard.getByRole("button", { name: "Ayarları kaydet" }),
    ).toBeEnabled();
    await expect(
      page.getByRole("button", { name: "Yenile", exact: true }),
    ).toBeDisabled();
    await expect(
      page.getByText("İşlem tamamlanamadı", { exact: true }),
    ).toHaveCount(0);
    expect(metadataPatches).toBe(1);
  } finally {
    releaseMetadataRefresh();
  }

  await expect(
    page.getByText("İşlem uygulandı, güncel görünüm alınamadı", {
      exact: true,
    }),
  ).toBeVisible();
  await expect(
    page.getByText(
      "Tenant ayarları şu anda güncellenemiyor. Veriyi yenileyip yeniden deneyin.",
      { exact: true },
    ),
  ).toHaveCount(0);
  await expect(
    page.getByText("İşlem tamamlanamadı", { exact: true }),
  ).toHaveCount(0);
  await expect(settingsCard.getByLabel("Tenant adı")).toHaveValue(
    "Anadolu Teknoloji Güncel",
  );
  await expect(
    page.getByRole("button", { name: "Yenile", exact: true }),
  ).toBeEnabled();
  expect(metadataPatches).toBe(1);
  expect(tenantDetailGets).toBe(2);

  await settingsCard
    .getByLabel("Tenant adı")
    .fill("Kaydedilmemiş Tenant Adı");
  await settingsCard.locator("form").evaluate((form) => {
    form.dispatchEvent(new Event("submit", { bubbles: true, cancelable: true }));
    form.dispatchEvent(new Event("submit", { bubbles: true, cancelable: true }));
  });
  const settingsAlert = page
    .getByRole("alert")
    .filter({ hasText: "İşlem tamamlanamadı" });
  await expect(settingsAlert).toBeVisible();
  await expect(settingsAlert).toHaveAttribute("tabindex", "-1");
  await expect(settingsAlert).toBeFocused();
  await expect(settingsAlert).toContainText(
    "Değişikliğin uygulanıp uygulanmadığı güvenilir biçimde doğrulanamadı.",
  );
  await expect(settingsAlert).toContainText(
    "tenant ayarları ve yaşam döngüsü işlemleri kilitlendi",
  );
  await expect(settingsAlert).toContainText("Referans: metadata-patch-failed");
  await expect(settingsCard.getByLabel("Tenant adı")).toHaveValue(
    "Kaydedilmemiş Tenant Adı",
  );
  await expect(
    settingsCard.getByRole("button", { name: "Yenileme bekleniyor" }),
  ).toBeDisabled();
  expect(metadataPatches).toBe(2);
  expect(tenantDetailGets).toBe(3);
});

test("confirmed lifecycle and feature failures remain actionable and focused inside their active dialogs", async ({
  context,
  page,
}) => {
  let lifecyclePatches = 0;
  let featurePatches = 0;
  let observeLifecyclePatch = () => {};
  const lifecyclePatchObserved = new Promise<void>((resolve) => {
    observeLifecyclePatch = resolve;
  });
  let releaseLifecyclePatch = () => {};
  const lifecyclePatchRelease = new Promise<void>((resolve) => {
    releaseLifecyclePatch = resolve;
  });
  let observeFeaturePatch = () => {};
  const featurePatchObserved = new Promise<void>((resolve) => {
    observeFeaturePatch = resolve;
  });
  let releaseFeaturePatch = () => {};
  const featurePatchRelease = new Promise<void>((resolve) => {
    releaseFeaturePatch = resolve;
  });

  await context.addCookies([
    {
      name: "wf_platform_refresh",
      value: "platform-dialog-local-errors-refresh",
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

    if (path === `/api/v1/platform/tenants/${TENANT_ID}`) {
      if (request.method() === "PATCH") {
        lifecyclePatches += 1;
        expect(request.postDataJSON()).toEqual({ status: "suspended" });
        observeLifecyclePatch();
        await lifecyclePatchRelease;
        await route.fulfill({
          status: 409,
          contentType: "application/json",
          body: errorEnvelope(
            "invalid_lifecycle_transition",
            "lifecycle-dialog-failure",
          ),
        });
        return;
      }

      expect(request.method()).toBe("GET");
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: envelope(tenants[0]),
      });
      return;
    }

    if (path === `/api/v1/platform/tenants/${TENANT_ID}/features`) {
      if (request.method() === "PATCH") {
        featurePatches += 1;
        expect(request.postDataJSON()).toEqual({
          features: [{ key: "organization", enabled: true }],
        });
        observeFeaturePatch();
        await featurePatchRelease;
        await route.fulfill({
          status: 503,
          contentType: "application/json",
          body: errorEnvelope(
            "platform_temporarily_unavailable",
            "feature-dialog-failure",
          ),
        });
        return;
      }

      expect(request.method()).toBe("GET");
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: envelope({ features: mockFeatures(false) }),
      });
      return;
    }

    await route.fulfill({ status: 404 });
  });

  await page.goto(`/platform/tenants/${TENANT_ID}`);
  const lifecycleSelect = page.getByLabel("Yeni yaşam döngüsü durumu");
  await lifecycleSelect.selectOption("suspended");
  const lifecycleOpener = page.getByRole("button", {
    name: "Geçişi incele",
  });
  await lifecycleOpener.click();
  let dialog = page.getByRole("dialog", {
    name: "Askıya alınmış durumuna geçir",
  });
  await dialog
    .getByRole("button", { name: "Değişikliği uygula" })
    .evaluate((button) => {
      button.dispatchEvent(new MouseEvent("click", { bubbles: true }));
      button.dispatchEvent(new MouseEvent("click", { bubbles: true }));
    });

  try {
    await lifecyclePatchObserved;
    await expect.poll(() => lifecyclePatches).toBe(1);
    await expect(
      dialog.getByRole("button", { name: "Değişiklik uygulanıyor…" }),
    ).toBeDisabled();
  } finally {
    releaseLifecyclePatch();
  }

  const lifecycleAlert = dialog.getByRole("alert");
  await expect(lifecycleAlert).toBeVisible();
  await expect(lifecycleAlert).toHaveAttribute("tabindex", "-1");
  await expect(lifecycleAlert).toBeFocused();
  await expect(lifecycleAlert).toContainText(
    "İşlem tenant’ın güncel yaşam döngüsü durumuyla çakıştı. Veriyi yenileyip geçerli bir işlem seçin.",
  );
  await expect(lifecycleAlert).toContainText(
    "Referans: lifecycle-dialog-failure",
  );
  await expect(dialog).toBeVisible();
  await expect(lifecycleSelect).toHaveValue("suspended");
  await expect(
    dialog.getByRole("button", { name: "Değişikliği uygula" }),
  ).toBeEnabled();
  await page.keyboard.press("Escape");
  await expect(dialog).toBeHidden();
  await expect(lifecycleOpener).toBeFocused();

  const organizationFeature = page
    .getByRole("heading", { name: "Feature flag’ler" })
    .locator("xpath=ancestor::section[1]")
    .locator("article")
    .filter({ hasText: "Organizasyon" });
  const featureOpener = organizationFeature.getByRole("button", {
    name: "Organizasyon özelliğini etkinleştir",
  });
  await featureOpener.click();
  dialog = page.getByRole("dialog", {
    name: "Organizasyon özelliğini etkinleştir",
  });
  await dialog
    .getByRole("button", { name: "Değişikliği uygula" })
    .evaluate((button) => {
      button.dispatchEvent(new MouseEvent("click", { bubbles: true }));
      button.dispatchEvent(new MouseEvent("click", { bubbles: true }));
    });

  try {
    await featurePatchObserved;
    await expect.poll(() => featurePatches).toBe(1);
    await expect(
      dialog.getByRole("button", { name: "Değişiklik uygulanıyor…" }),
    ).toBeDisabled();
  } finally {
    releaseFeaturePatch();
  }

  const featureAlert = dialog.getByRole("alert");
  await expect(featureAlert).toBeVisible();
  await expect(featureAlert).toHaveAttribute("tabindex", "-1");
  await expect(featureAlert).toBeFocused();
  await expect(featureAlert).toContainText(
    "İstenen değişiklik sunucuda görülmedi.",
  );
  await expect(featureAlert).toContainText(
    "Referans: feature-dialog-failure",
  );
  await expect(dialog).toBeVisible();
  await expect(
    organizationFeature.getByText("Devre dışı", { exact: true }),
  ).toBeVisible();
  await expect(
    dialog.getByRole("button", { name: "Değişikliği uygula" }),
  ).toBeEnabled();
  await page.keyboard.press("Escape");
  await expect(dialog).toBeHidden();
  await expect(featureOpener).toBeFocused();
  expect(lifecyclePatches).toBe(1);
  expect(featurePatches).toBe(1);
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

test("tenant creation sends the exact initial-admin contract and ignores same-task duplicate submissions", async ({
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
        initial_admin: {
          full_name: "Deniz Yönetici",
          email: "deniz.yonetici@example.com",
        },
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
        body: envelope(
          {
            ...createdTenant,
            initial_admin: { status: "invitation_prepared" },
          },
          responseMeta("tenant-create-lock"),
        ),
      });
      return;
    }

    await route.fulfill({ status: 404 });
  });

  await page.goto("/platform/tenants");
  await expect(
    page.getByRole("heading", { name: "Tenant yönetimi" }),
  ).toBeVisible();
  const createTenantOpener = page.getByRole("button", {
    name: "Yeni tenant oluştur",
  });

  await page.evaluate(() => {
    const testWindow = window as typeof window & {
      __platformSupportedValuesOf?: typeof Intl.supportedValuesOf;
    };
    testWindow.__platformSupportedValuesOf = Intl.supportedValuesOf;
    Object.defineProperty(Intl, "supportedValuesOf", {
      configurable: true,
      value: undefined,
    });
  });
  await createTenantOpener.click();
  let dialog = page.getByRole("dialog", { name: "Yeni tenant oluştur" });
  await expect(dialog.getByLabel("Tenant adı")).toBeFocused();
  const fallbackTimezone = dialog.getByLabel("Saat dilimi");
  await expect(fallbackTimezone).toHaveValue("Europe/Istanbul");
  expect(
    await fallbackTimezone.locator("option").evaluateAll((options) =>
      options.map((option) => (option as HTMLOptionElement).value),
    ),
  ).toEqual([
    "Europe/Istanbul",
    "Africa/Cairo",
    "Africa/Johannesburg",
    "America/Argentina/Buenos_Aires",
    "America/Chicago",
    "America/Los_Angeles",
    "America/New_York",
    "America/Sao_Paulo",
    "Asia/Dubai",
    "Asia/Hong_Kong",
    "Asia/Kolkata",
    "Asia/Singapore",
    "Asia/Tokyo",
    "Australia/Sydney",
    "Europe/Amsterdam",
    "Europe/Athens",
    "Europe/Berlin",
    "Europe/London",
    "Europe/Paris",
    "Europe/Warsaw",
    "Pacific/Auckland",
    "UTC",
  ]);
  await page.keyboard.press("Escape");
  await expect(dialog).toBeHidden();
  await expect(createTenantOpener).toBeFocused();
  await page.evaluate(() => {
    const testWindow = window as typeof window & {
      __platformSupportedValuesOf?: typeof Intl.supportedValuesOf;
    };
    Object.defineProperty(Intl, "supportedValuesOf", {
      configurable: true,
      value: testWindow.__platformSupportedValuesOf,
    });
    delete testWindow.__platformSupportedValuesOf;
  });

  await createTenantOpener.click();
  dialog = page.getByRole("dialog", { name: "Yeni tenant oluştur" });
  await expect(
    dialog.getByRole("group", { name: "Organizasyon bilgileri" }),
  ).toBeVisible();
  await expect(
    dialog.getByRole("group", { name: "İlk yönetici" }),
  ).toBeVisible();
  await expect(
    dialog.getByRole("group", {
      name: "Bölgesel ve ticari ayarlar",
    }),
  ).toBeVisible();
  const timezone = dialog.getByLabel("Saat dilimi");
  await expect(timezone).toHaveJSProperty("tagName", "SELECT");
  await expect(timezone).toHaveValue("Europe/Istanbul");
  const expectedTimezoneOptions = await page.evaluate(() => {
    const options = new Set(["UTC", ...Intl.supportedValuesOf("timeZone")]);
    options.delete("Europe/Istanbul");
    return ["Europe/Istanbul", ...[...options].sort()];
  });
  expect(
    await timezone.locator("option").evaluateAll((options) =>
      options.map((option) => (option as HTMLOptionElement).value),
    ),
  ).toEqual(expectedTimezoneOptions);
  expect(expectedTimezoneOptions.length).toBeGreaterThan(100);
  expect(expectedTimezoneOptions).toContain("Pacific/Honolulu");
  await expect(
    dialog.getByText(
      "Saat dilimi, yerel tarih ve saatlerin nasıl gösterileceğini ve yorumlanacağını belirler.",
      { exact: true },
    ),
  ).toBeVisible();
  await expect(dialog.getByLabel("İlk yönetici tam adı")).toHaveAttribute(
    "required",
    "",
  );
  await expect(
    dialog.getByLabel("İlk yönetici e-posta adresi"),
  ).toHaveAttribute("required", "");

  await dialog.getByLabel("Tenant adı").fill("Güvenli Yeni Tenant");
  await dialog.getByLabel("Tenant kodu").fill("guvenli-yeni-tenant");
  await dialog.getByLabel("İlk yönetici tam adı").fill("   ");
  await dialog
    .getByLabel("İlk yönetici e-posta adresi")
    .fill("deniz.yonetici@example.com");
  await dialog.getByRole("button", { name: "Tenant oluştur" }).click();
  await expect(
    dialog.getByRole("alert").filter({
      hasText: "İlk yönetici tam adını kontrol edin.",
    }),
  ).toBeVisible();
  await expect(dialog.getByLabel("İlk yönetici tam adı")).toBeFocused();
  expect(createRequests).toBe(0);

  await dialog.getByLabel("Tenant adı").fill("Güvenli Yeni Tenant");
  await dialog.getByLabel("Tenant kodu").fill("guvenli-yeni-tenant");
  await dialog
    .getByLabel("İlk yönetici tam adı")
    .fill("  Deniz Yönetici  ");
  await dialog
    .getByLabel("İlk yönetici e-posta adresi")
    .fill("  DENIZ.YONETICI@EXAMPLE.COM  ");
  await dialog.getByLabel("Tanımlı aktif çalışan limiti").fill("125");

  await dialog.locator("form").evaluate((form) => {
    form.dispatchEvent(new Event("submit", { bubbles: true, cancelable: true }));
    form.dispatchEvent(new Event("submit", { bubbles: true, cancelable: true }));
  });

  await createRequestObserved;
  const listRequestsBeforeCreatedReload = listRequests;
  await expect.poll(() => createRequests).toBe(1);
  await expect(
    dialog.getByRole("button", { name: "Tenant oluşturuluyor…" }),
  ).toBeDisabled();
  await expect(dialog).toHaveAttribute("tabindex", "-1");
  await expect(dialog).toBeFocused();
  await page.keyboard.press("Tab");
  await expect(dialog).toBeFocused();
  await page.keyboard.press("Shift+Tab");
  await expect(dialog).toBeFocused();
  await page.keyboard.press("Escape");
  await expect(dialog).toBeVisible();
  releaseCreateRequest();

  await expect(dialog).toBeHidden();
  await expect(createTenantOpener).toBeFocused();
  await expect(
    page.getByText("Güvenli Yeni Tenant oluşturuldu", { exact: true }),
  ).toBeVisible();
  await expect(
    page.getByText(
      "Tenant ve ilk yönetici daveti/erişimi hazırlandı. Ayrıntı ekranından güvenli metadata ve modül ayarlarını tamamlayabilirsiniz.",
      { exact: true },
    ),
  ).toBeVisible();
  await expect
    .poll(() => listRequests)
    .toBe(listRequestsBeforeCreatedReload + 1);
  expect(createRequests).toBe(1);
});

test("an exact slug found after a malformed create remains unresolved and locked for manual verification", async ({
  context,
  page,
}) => {
  const tenantCreator = {
    ...platformAdmin,
    permissions: ["tenant:read:platform", "tenant:create:platform"],
    permission_version: 29,
  };
  const reconciledTenant = {
    ...tenants[0],
    id: "10000000-0000-4000-8000-000000000098",
    slug: "uzlasilan-yeni-tenant",
    name: "Uzlaşılan Yeni Tenant",
    status: "provisioning",
    health: "provisioning",
    limits: { active_employees: 75 },
  };
  const reconcileCursor = "create-reconcile-page-two";
  const listCursors: Array<string | null> = [];
  let nullCursorRequests = 0;
  let createRequests = 0;

  await context.addCookies([
    {
      name: "wf_platform_refresh",
      value: "platform-create-reconcile-refresh",
      url: "http://127.0.0.1:3100",
      httpOnly: true,
      sameSite: "Lax",
    },
  ]);

  await page.route("**/api/v1/**", async (route: Route) => {
    const request = route.request();
    const url = new URL(request.url());
    const path = url.pathname;

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
      const cursor = url.searchParams.get("cursor");
      listCursors.push(cursor);
      if (cursor === reconcileCursor) {
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: tenantListEnvelope([reconciledTenant], null),
        });
        return;
      }

      expect(cursor).toBeNull();
      nullCursorRequests += 1;
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body:
          nullCursorRequests === 1
            ? tenantListEnvelope(tenants.slice(0, 2), null)
            : nullCursorRequests === 2
              ? tenantListEnvelope(tenants.slice(0, 2), reconcileCursor)
              : tenantListEnvelope(
                  [reconciledTenant, ...tenants.slice(0, 2)],
                  null,
                ),
      });
      return;
    }

    if (path === "/api/v1/platform/tenants" && request.method() === "POST") {
      createRequests += 1;
      expect(request.postDataJSON()).toEqual({
        name: "Uzlaşılan Yeni Tenant",
        slug: "uzlasilan-yeni-tenant",
        initial_admin: {
          full_name: "Gizli Yönetici",
          email: "gizli.yonetici@example.com",
        },
        plan_code: "core",
        data_region: "tr-1",
        locale: "tr-TR",
        timezone: "Europe/Istanbul",
        limits: { active_employees: 75 },
      });
      await route.fulfill({
        status: 201,
        contentType: "application/json",
        body: envelope(
          {
            ...reconciledTenant,
            initial_admin: {
              status: "invitation_prepared",
              email: "must-not-render@example.test",
              token: "must-not-render-token",
              activation_url:
                "https://identity.example.test/activate/must-not-render-token",
            },
          },
          responseMeta("unsafe-create-response"),
        ),
      });
      return;
    }

    await route.fulfill({ status: 404 });
  });

  await page.goto("/platform/tenants");
  const createTenantOpener = page.getByRole("button", {
    name: "Yeni tenant oluştur",
  });
  await createTenantOpener.click();
  const dialog = page.getByRole("dialog", { name: "Yeni tenant oluştur" });
  await dialog.getByLabel("Tenant adı").fill("Uzlaşılan Yeni Tenant");
  await dialog.getByLabel("Tenant kodu").fill("uzlasilan-yeni-tenant");
  await dialog.getByLabel("İlk yönetici tam adı").fill("Gizli Yönetici");
  await dialog
    .getByLabel("İlk yönetici e-posta adresi")
    .fill("gizli.yonetici@example.com");
  await dialog.getByLabel("Tanımlı aktif çalışan limiti").fill("75");
  await dialog.getByRole("button", { name: "Tenant oluştur" }).click();

  await expect(dialog).toBeVisible();
  const unresolvedAlert = dialog.getByRole("alert");
  await expect(unresolvedAlert).toContainText(
    "bu kayıt bu isteğin sonucu olduğunu kanıtlamaz",
  );
  await expect(unresolvedAlert).toContainText(
    "Mevcut veya oluşmuş olabilecek kayıt",
  );
  await expect(
    page.getByText("Uzlaşılan Yeni Tenant oluşturuldu", { exact: true }),
  ).toHaveCount(0);
  await expect(
    dialog.getByRole("link", {
      name: "Bulunan tenantı yeni sekmede incele",
    }),
  ).toHaveAttribute(
    "href",
    `/platform/tenants/${reconciledTenant.id}`,
  );
  await expect(
    dialog.getByRole("button", { name: "Tenant oluştur" }),
  ).toBeDisabled();
  await expect(dialog.getByLabel("Tenant adı")).toHaveValue(
    "Uzlaşılan Yeni Tenant",
  );
  await expect(dialog.getByLabel("Tenant adı")).toBeDisabled();
  await expect(dialog.getByLabel("Tenant kodu")).toHaveValue(
    "uzlasilan-yeni-tenant",
  );
  await expect(dialog.getByLabel("Tenant kodu")).toBeDisabled();
  await expect(dialog.getByLabel("İlk yönetici tam adı")).toHaveValue(
    "Gizli Yönetici",
  );
  await expect(
    dialog.getByLabel("İlk yönetici e-posta adresi"),
  ).toHaveValue("gizli.yonetici@example.com");
  const createRequestsBeforeStaleSubmit = createRequests;
  await dialog.locator("form").evaluate((form) => {
    form.dispatchEvent(new Event("submit", { bubbles: true, cancelable: true }));
  });
  await expect.poll(() => createRequests).toBe(createRequestsBeforeStaleSubmit);
  await expect.poll(() => listCursors).toEqual([
    null,
    null,
    reconcileCursor,
  ]);
  expect(createRequests).toBe(1);
  await expect(page.getByText("must-not-render@example.test")).toHaveCount(0);
  await expect(page.getByText("must-not-render-token")).toHaveCount(0);
  await expect(
    page.getByText(
      "https://identity.example.test/activate/must-not-render-token",
    ),
  ).toHaveCount(0);
});

test("an unverifiable tenant create stays locked through a cursor cycle until a complete absent scan permits retry", async ({
  context,
  page,
}) => {
  const tenantCreator = {
    ...platformAdmin,
    permissions: ["tenant:read:platform", "tenant:create:platform"],
    permission_version: 30,
  };
  const cycleCursor = "create-reconcile-cycle";
  const absentCursor = "create-reconcile-absent-page-two";
  let createRequests = 0;
  let listingRequests = 0;
  let createWasAttempted = false;
  let reconciliationMode: "cycle" | "absent" = "cycle";

  await context.addCookies([
    {
      name: "wf_platform_refresh",
      value: "platform-create-unknown-refresh",
      url: "http://127.0.0.1:3100",
      httpOnly: true,
      sameSite: "Lax",
    },
  ]);

  await page.route("**/api/v1/**", async (route: Route) => {
    const request = route.request();
    const url = new URL(request.url());
    const path = url.pathname;

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
      listingRequests += 1;
      const cursor = url.searchParams.get("cursor");
      if (!createWasAttempted) {
        expect(cursor).toBeNull();
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: tenantListEnvelope(tenants.slice(0, 2), null),
        });
        return;
      }

      if (reconciliationMode === "cycle") {
        expect([null, cycleCursor]).toContain(cursor);
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: tenantListEnvelope(
            cursor === null ? [tenants[0]] : [tenants[1]],
            cycleCursor,
          ),
        });
        return;
      }

      expect([null, absentCursor]).toContain(cursor);
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: tenantListEnvelope(
          cursor === null
            ? [{ ...tenants[0], slug: "sonucu-belirsiz-tenanta" }]
            : [tenants[1]],
          cursor === null ? absentCursor : null,
        ),
      });
      return;
    }

    if (path === "/api/v1/platform/tenants" && request.method() === "POST") {
      createRequests += 1;
      createWasAttempted = true;
      if (createRequests === 1) {
        await route.abort("failed");
        return;
      }
      await route.fulfill({
        status: 422,
        contentType: "application/json",
        body: errorEnvelope("platform_tenant_validation_failed"),
      });
      return;
    }

    await route.fulfill({ status: 404 });
  });

  await page.goto("/platform/tenants");
  await page.getByRole("button", { name: "Yeni tenant oluştur" }).click();
  const dialog = page.getByRole("dialog", { name: "Yeni tenant oluştur" });
  await dialog.getByLabel("Tenant adı").fill("Sonucu Belirsiz Tenant");
  await dialog.getByLabel("Tenant kodu").fill("sonucu-belirsiz-tenant");
  await dialog.getByLabel("İlk yönetici tam adı").fill("Belirsiz Yönetici");
  await dialog
    .getByLabel("İlk yönetici e-posta adresi")
    .fill("belirsiz.yonetici@example.com");
  await dialog.getByRole("button", { name: "Tenant oluştur" }).click();

  const unknownAlert = dialog.getByRole("alert");
  await expect(unknownAlert).toContainText(
    "Tenant oluşturma sonucu doğrulanamadı",
  );
  await expect(unknownAlert).toContainText(
    "Aynı oluşturma isteğini yeniden göndermeyin.",
  );
  await expect(unknownAlert).not.toContainText("Farklı bir kod");
  await expect(dialog.getByLabel("Tenant adı")).toHaveValue(
    "Sonucu Belirsiz Tenant",
  );
  await expect(dialog.getByLabel("Tenant kodu")).toHaveValue(
    "sonucu-belirsiz-tenant",
  );
  const createButton = dialog.getByRole("button", {
    name: "Tenant oluştur",
  });
  await expect(createButton).toBeDisabled();
  await expect(
    dialog.getByRole("button", { name: "Yeni tenant penceresini kapat" }),
  ).toBeEnabled();
  await expect(
    dialog.getByRole("button", { name: "Sonucu yeniden doğrula" }),
  ).toBeEnabled();
  const requestsBeforeForcedSubmit = createRequests;
  await dialog.locator("form").evaluate((form) => {
    form.dispatchEvent(new Event("submit", { bubbles: true, cancelable: true }));
    form.dispatchEvent(new Event("submit", { bubbles: true, cancelable: true }));
  });
  await expect.poll(() => createRequests).toBe(requestsBeforeForcedSubmit);

  reconciliationMode = "absent";
  const listingsBeforeRetry = listingRequests;
  await dialog
    .getByRole("button", { name: "Sonucu yeniden doğrula" })
    .click();
  await expect.poll(() => listingRequests).toBe(listingsBeforeRetry + 2);
  await expect(dialog.getByRole("alert")).toContainText(
    "Tam tenant listesi doğrulandı ve bu tenant koduyla bir kayıt bulunamadı.",
  );
  await expect(createButton).toBeEnabled();
  await expect(dialog.getByLabel("Tenant adı")).toHaveValue(
    "Sonucu Belirsiz Tenant",
  );
  await expect(dialog.getByLabel("Tenant kodu")).toHaveValue(
    "sonucu-belirsiz-tenant",
  );

  const listingsBeforeDefinitiveFailure = listingRequests;
  await createButton.click();
  await expect(dialog.getByRole("alert")).toContainText(
    "Gönderilen değerler doğrulanamadı.",
  );
  await expect(createButton).toBeEnabled();
  expect(createRequests).toBe(2);
  expect(listingRequests).toBe(listingsBeforeDefinitiveFailure);
});

test("create, correction, and confirmation dialogs remain fully reachable after a 390x320 mobile viewport is keyboard-shortened", async ({
  context,
  page,
}) => {
  const responsiveAdmin = {
    ...platformAdmin,
    permissions: [
      "tenant:read:platform",
      "tenant:create:platform",
      "tenant:update:platform",
    ],
    permission_version: 40,
  };

  await page.setViewportSize({ width: 390, height: 320 });
  await context.addCookies([
    {
      name: "wf_platform_refresh",
      value: "platform-short-dialog-refresh",
      url: "http://127.0.0.1:3100",
      httpOnly: true,
      sameSite: "Lax",
    },
  ]);

  await page.route("**/api/v1/**", async (route: Route) => {
    const request = route.request();
    const url = new URL(request.url());
    const path = url.pathname;

    if (path === "/api/v1/platform/auth/refresh") {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: envelope({
          access_token: PLATFORM_ACCESS_TOKEN,
          token_type: "bearer",
          expires_in: 900,
          user: responsiveAdmin,
        }),
      });
      return;
    }

    expectPlatformBearer(request, PLATFORM_ACCESS_TOKEN);
    if (path === "/api/v1/platform/me") {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: envelope({ user: responsiveAdmin }),
      });
      return;
    }

    if (path === "/api/v1/platform/tenants" && request.method() === "GET") {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: tenantListEnvelope([tenants[0]], null),
      });
      return;
    }

    if (path === `/api/v1/platform/tenants/${TENANT_ID}`) {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: envelope(tenants[0]),
      });
      return;
    }

    await route.fulfill({ status: 404 });
  });

  async function expectReachableControls(
    dialog: ReturnType<typeof page.getByRole>,
    controls: Array<ReturnType<typeof page.getByRole>>,
  ) {
    expect(
      await page.evaluate(
        () => document.documentElement.scrollWidth <= window.innerWidth + 1,
      ),
    ).toBe(true);
    expect(
      await dialog.evaluate(
        (element) => element.scrollWidth <= element.clientWidth + 1,
      ),
    ).toBe(true);
    const backdrop = dialog.locator("xpath=..");
    expect(
      await backdrop.evaluate(
        (element) => element.scrollWidth <= element.clientWidth + 1,
      ),
    ).toBe(true);

    for (const control of controls) {
      await control.scrollIntoViewIfNeeded();
      await expect(control).toBeInViewport();
      await expect(control).toBeVisible();
      const bounds = await control.boundingBox();
      expect(bounds).not.toBeNull();
      expect(bounds!.y).toBeGreaterThanOrEqual(-1);
      expect(bounds!.y + bounds!.height).toBeLessThanOrEqual(
        (await page.evaluate(() => window.innerHeight)) + 1,
      );
    }
    await controls[0].scrollIntoViewIfNeeded();
    await expect(controls[0]).toBeInViewport();
  }

  await page.goto("/platform/tenants");
  await page.getByRole("button", { name: "Yeni tenant oluştur" }).click();
  let dialog = page.getByRole("dialog", { name: "Yeni tenant oluştur" });
  await page.setViewportSize({ width: 390, height: 180 });
  const createBody = dialog.locator("form > div").first();
  expect(await createBody.evaluate((element) => element.clientHeight)).toBeGreaterThan(
    0,
  );
  await expectReachableControls(dialog, [
    dialog.getByLabel("Tenant adı"),
    dialog.getByLabel("Tanımlı aktif çalışan limiti"),
    dialog.getByRole("button", { name: "Vazgeç" }),
    dialog.getByRole("button", { name: "Tenant oluştur" }),
  ]);
  await dialog
    .getByRole("button", { name: "Yeni tenant penceresini kapat" })
    .click();

  await page.goto(`/platform/tenants/${TENANT_ID}`);
  await page
    .getByRole("button", { name: "İlk yönetici bilgilerini düzelt" })
    .click();
  dialog = page.getByRole("dialog", {
    name: "İlk yönetici bilgilerini düzelt",
  });
  const correctionBody = dialog.locator("form > div").first();
  expect(
    await correctionBody.evaluate((element) => element.clientHeight),
  ).toBeGreaterThan(0);
  await expectReachableControls(dialog, [
    dialog.getByLabel("İlk yönetici tam adı"),
    dialog.getByLabel("İlk yönetici e-posta adresi"),
    dialog.getByRole("button", { name: "Vazgeç" }),
    dialog.getByRole("button", { name: "Bilgileri düzelt" }),
  ]);
  await dialog.getByRole("button", { name: "Vazgeç" }).click();

  await page
    .getByRole("button", {
      name: "İlk yönetici davetini yeniden gönder",
    })
    .click();
  dialog = page.getByRole("dialog", {
    name: "İlk yönetici davetini yeniden gönder",
  });
  const confirmBody = dialog.locator("footer").locator("..");
  expect(
    await confirmBody.evaluate((element) => element.clientHeight),
  ).toBeGreaterThan(0);
  await expectReachableControls(dialog, [
    dialog.getByRole("heading", {
      name: "İlk yönetici davetini yeniden gönder",
    }),
    dialog.getByRole("button", { name: "Vazgeç" }),
    dialog.getByRole("button", { name: "Daveti yeniden gönder" }),
  ]);
});

test("initial-admin resend is confirmed, payload-free, duplicate-safe, permission-scoped, and identity-safe", async ({
  context,
  page,
}) => {
  const tenantUpdater = {
    ...platformAdmin,
    permissions: ["tenant:read:platform", "tenant:update:platform"],
    permission_version: 31,
  };
  let resendMode: "success" | "conflict" | "malformed" | "network" =
    "success";
  let resendRequests = 0;
  let observeResendRequest = () => {};
  const resendRequestObserved = new Promise<void>((resolve) => {
    observeResendRequest = resolve;
  });
  let releaseResendRequest = () => {};
  const resendRequestRelease = new Promise<void>((resolve) => {
    releaseResendRequest = resolve;
  });
  let holdNextTenantDetail = false;
  let observeHeldTenantDetail = () => {};
  const heldTenantDetailObserved = new Promise<void>((resolve) => {
    observeHeldTenantDetail = resolve;
  });
  let releaseHeldTenantDetail = () => {};
  const heldTenantDetailRelease = new Promise<void>((resolve) => {
    releaseHeldTenantDetail = resolve;
  });

  await context.addCookies([
    {
      name: "wf_platform_refresh",
      value: "platform-initial-admin-resend-refresh",
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
          user: tenantUpdater,
        }),
      });
      return;
    }

    expectPlatformBearer(request, PLATFORM_ACCESS_TOKEN);
    if (path === "/api/v1/platform/me") {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: envelope({ user: tenantUpdater }),
      });
      return;
    }

    if (
      path ===
      `/api/v1/platform/tenants/${TENANT_ID}/initial-admin-invitation/resend`
    ) {
      expect(request.method()).toBe("POST");
      expect(request.postData()).toBeNull();
      expect(request.headers()["content-type"]).toBeUndefined();
      resendRequests += 1;

      if (resendMode === "success") {
        observeResendRequest();
        await resendRequestRelease;
        await route.fulfill({
          status: 202,
          contentType: "application/json",
          body: envelope(
            { status: "invitation_prepared" },
            responseMeta("initial-admin-resend-correlation"),
          ),
        });
        return;
      }

      if (resendMode === "conflict") {
        await route.fulfill({
          status: 409,
          contentType: "application/json",
          body: errorEnvelope(
            "tenant_initial_admin_unavailable",
            "initial-admin-unavailable-correlation",
          ),
        });
        return;
      }

      if (resendMode === "network") {
        await route.abort("failed");
        return;
      }

      await route.fulfill({
        status: 202,
        contentType: "application/json",
        body: envelope(
          {
            status: "invitation_prepared",
            email: "initial-admin@example.test",
            token: "secret-activation-token",
            activation_url:
              "https://identity.example.test/activate/secret-activation-token",
          },
          responseMeta("unsafe-resend-response"),
        ),
      });
      return;
    }

    if (path === `/api/v1/platform/tenants/${TENANT_ID}`) {
      if (request.method() === "PATCH") {
        expect(request.postDataJSON()).toMatchObject({
          name: "Epoch Test Tenant",
        });
        holdNextTenantDetail = true;
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: envelope(
            { ...tenants[0], name: "Epoch Test Tenant" },
            responseMeta("metadata-commit-before-new-latch"),
          ),
        });
        return;
      }
      expect(request.method()).toBe("GET");
      if (holdNextTenantDetail) {
        holdNextTenantDetail = false;
        observeHeldTenantDetail();
        await heldTenantDetailRelease;
      }
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: envelope(tenants[0]),
      });
      return;
    }

    await route.fulfill({ status: 404 });
  });

  await page.goto(`/platform/tenants/${TENANT_ID}`);
  const resendButton = page.getByRole("button", {
    name: "İlk yönetici davetini yeniden gönder",
  });
  await expect(resendButton).toBeVisible();
  expect(resendRequests).toBe(0);

  await resendButton.click();
  let confirmation = page.getByRole("dialog", {
    name: "İlk yönetici davetini yeniden gönder",
  });
  await expect(confirmation).toContainText(
    "Bu ekranda e-posta adresi veya erişim bağlantısı gösterilmez.",
  );
  await expect(confirmation.getByRole("textbox")).toHaveCount(0);
  await confirmation
    .getByRole("button", { name: "Daveti yeniden gönder" })
    .evaluate((button) => {
      button.dispatchEvent(new MouseEvent("click", { bubbles: true }));
      button.dispatchEvent(new MouseEvent("click", { bubbles: true }));
    });

  await resendRequestObserved;
  await expect.poll(() => resendRequests).toBe(1);
  await expect(
    confirmation.getByRole("button", { name: "Davet hazırlanıyor…" }),
  ).toBeDisabled();
  await expect(
    confirmation.getByRole("button", { name: "Vazgeç" }),
  ).toBeDisabled();
  await expect(confirmation).toBeFocused();
  await page.keyboard.press("Escape");
  await expect(confirmation).toBeVisible();
  releaseResendRequest();

  await expect(confirmation).toBeHidden();
  await expect(resendButton).toBeFocused();
  await expect(
    page.getByText("İlk yönetici daveti yeniden hazırlandı", {
      exact: true,
    }),
  ).toBeVisible();
  await expect(
    page.getByText(
      "Davet gönderim için hazırlandı; teslim edildiği anlamına gelmez. Bu ekranda kimlik veya erişim bağlantısı gösterilmez.",
      { exact: true },
    ),
  ).toBeVisible();
  await expect(
    page.getByText("Referans: initial-admin-resend-correlation"),
  ).toBeVisible();
  await expect(page.getByText("initial-admin@example.test")).toHaveCount(0);
  await expect(page.getByText("secret-activation-token")).toHaveCount(0);

  await page.getByLabel("Tenant adı").fill("Epoch Test Tenant");
  await page.getByRole("button", { name: "Ayarları kaydet" }).click();
  await heldTenantDetailObserved;

  resendMode = "malformed";
  await resendButton.click();
  confirmation = page.getByRole("dialog", {
    name: "İlk yönetici davetini yeniden gönder",
  });
  await confirmation
    .getByRole("button", { name: "Daveti yeniden gönder" })
    .click();
  await expect(confirmation.getByRole("alert")).toContainText(
    "Sonuç doğrulanamadı",
  );
  await page.keyboard.press("Escape");
  await expect(confirmation).toBeHidden();
  await expect(resendButton).toBeDisabled();

  releaseHeldTenantDetail();
  await page.waitForTimeout(250);
  await expect(resendButton).toBeDisabled();

  await page
    .getByRole("heading", { name: "Tenant metadata’sı" })
    .locator("xpath=ancestor::section[1]")
    .getByRole("button", { name: "Yenile" })
    .click();
  await expect(resendButton).toBeEnabled();

  resendMode = "conflict";
  await resendButton.click();
  confirmation = page.getByRole("dialog", {
    name: "İlk yönetici davetini yeniden gönder",
  });
  await confirmation
    .getByRole("button", { name: "Daveti yeniden gönder" })
    .click();
  const conflictAlert = confirmation.getByRole("alert");
  await expect(conflictAlert).toBeVisible();
  await expect(conflictAlert).toHaveAttribute("tabindex", "-1");
  await expect(conflictAlert).toBeFocused();
  await expect(conflictAlert).toContainText(
    "İlk yönetici işlemi mevcut durumda kullanılamıyor. Tenant ayrıntısını yenileyip daha sonra yeniden deneyin.",
  );
  await expect(conflictAlert).toContainText(
    "Referans: initial-admin-unavailable-correlation",
  );
  await expect(conflictAlert).not.toContainText(
    "İlk yönetici daveti hazırlanamadı",
  );
  await expect(conflictAlert).not.toContainText("hesap durumunu");
  await expect(conflictAlert).not.toContainText(
    "farklı ilk yönetici bilgileri",
  );
  await expect(conflictAlert).not.toContainText(
    "Tenant aynı anda başka bir işlemle güncellendi",
  );
  await expect(
    confirmation.getByRole("button", { name: "Daveti yeniden gönder" }),
  ).toBeEnabled();
  await page.keyboard.press("Escape");
  await expect(confirmation).toBeHidden();
  await expect(resendButton).toBeFocused();

  resendMode = "malformed";
  await resendButton.click();
  confirmation = page.getByRole("dialog", {
    name: "İlk yönetici davetini yeniden gönder",
  });
  await confirmation
    .getByRole("button", { name: "Daveti yeniden gönder" })
    .click();
  const malformedAlert = confirmation.getByRole("alert");
  await expect(malformedAlert).toBeVisible();
  await expect(malformedAlert).toHaveAttribute("tabindex", "-1");
  await expect(malformedAlert).toBeFocused();
  await expect(malformedAlert).toContainText(
    "Sonuç doğrulanamadı",
  );
  await expect(malformedAlert).toContainText(
    "Yeni bir davet zaten hazırlanmış olabilir",
  );
  await expect(malformedAlert).toContainText(
    "platform denetim kaydını inceleyin ve sayfayı yenileyin",
  );
  await expect(confirmation).toBeVisible();
  const ambiguousResendButton = confirmation.getByRole("button", {
    name: "Daveti yeniden gönder",
  });
  await expect(ambiguousResendButton).toBeDisabled();
  await expect(
    confirmation.getByRole("button", { name: "Vazgeç" }),
  ).toBeEnabled();
  await ambiguousResendButton.evaluate((button) => {
    button.removeAttribute("disabled");
    button.dispatchEvent(new MouseEvent("click", { bubbles: true }));
    button.dispatchEvent(new MouseEvent("click", { bubbles: true }));
  });
  await expect.poll(() => resendRequests).toBe(4);
  await expect(page.getByText("initial-admin@example.test")).toHaveCount(0);
  await expect(page.getByText("secret-activation-token")).toHaveCount(0);
  await expect(
    page.getByText(
      "https://identity.example.test/activate/secret-activation-token",
    ),
  ).toHaveCount(0);
  expect(resendRequests).toBe(4);

  await page.keyboard.press("Escape");
  await expect(confirmation).toBeHidden();
  const invitationCard = page
    .getByRole("heading", { name: "İlk yönetici daveti" })
    .locator("xpath=ancestor::section[1]");
  await expect(invitationCard.getByRole("alert")).toContainText(
    "Davet işleminin sonucu doğrulanamadı",
  );
  await expect(resendButton).toBeDisabled();
  await page
    .getByRole("heading", { name: "Tenant metadata’sı" })
    .locator("xpath=ancestor::section[1]")
    .getByRole("button", { name: "Yenile" })
    .click();
  await expect(resendButton).toBeEnabled();
  await expect(invitationCard.getByRole("alert")).toHaveCount(0);
  resendMode = "network";
  await resendButton.click();
  confirmation = page.getByRole("dialog", {
    name: "İlk yönetici davetini yeniden gönder",
  });
  await confirmation
    .getByRole("button", { name: "Daveti yeniden gönder" })
    .click();
  const networkAlert = confirmation.getByRole("alert");
  await expect(networkAlert).toContainText("Sonuç doğrulanamadı");
  await expect(networkAlert).toContainText(
    "Yeni bir davet zaten hazırlanmış olabilir",
  );
  const networkResendButton = confirmation.getByRole("button", {
    name: "Daveti yeniden gönder",
  });
  await expect(networkResendButton).toBeDisabled();
  await expect(
    confirmation.getByRole("button", { name: "Vazgeç" }),
  ).toBeEnabled();
  await networkResendButton.evaluate((button) => {
    button.removeAttribute("disabled");
    button.dispatchEvent(new MouseEvent("click", { bubbles: true }));
  });
  await expect.poll(() => resendRequests).toBe(5);
});

test("initial-admin correction sends the exact safe contract and keeps validation, busy state, and failures inside its dialog", async ({
  context,
  page,
}) => {
  const tenantUpdater = {
    ...platformAdmin,
    permissions: ["tenant:read:platform", "tenant:update:platform"],
    permission_version: 33,
  };
  let correctionMode: "success" | "conflict" | "malformed" = "success";
  let correctionRequests = 0;
  let tenantDetailGets = 0;
  let observeCorrectionRequest = () => {};
  const correctionRequestObserved = new Promise<void>((resolve) => {
    observeCorrectionRequest = resolve;
  });
  let releaseCorrectionRequest = () => {};
  const correctionRequestRelease = new Promise<void>((resolve) => {
    releaseCorrectionRequest = resolve;
  });

  await context.addCookies([
    {
      name: "wf_platform_refresh",
      value: "platform-initial-admin-correction-refresh",
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
          user: tenantUpdater,
        }),
      });
      return;
    }

    expectPlatformBearer(request, PLATFORM_ACCESS_TOKEN);
    if (path === "/api/v1/platform/me") {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: envelope({ user: tenantUpdater }),
      });
      return;
    }

    if (
      path ===
      `/api/v1/platform/tenants/${TENANT_ID}/initial-admin-invitation`
    ) {
      expect(request.method()).toBe("PATCH");
      expect(request.headers()["content-type"]).toContain("application/json");
      expect(request.postDataJSON()).toEqual({
        full_name: "Deniz Yönetici",
        email: "deniz.yonetici@example.com",
      });
      correctionRequests += 1;

      if (correctionMode === "success") {
        observeCorrectionRequest();
        await correctionRequestRelease;
        await route.fulfill({
          status: 202,
          contentType: "application/json",
          body: envelope(
            { status: "invitation_prepared" },
            responseMeta("initial-admin-correction-correlation"),
          ),
        });
        return;
      }

      if (correctionMode === "conflict") {
        await route.fulfill({
          status: 409,
          contentType: "application/json",
          body: errorEnvelope(
            "tenant_initial_admin_unavailable",
            "initial-admin-correction-unavailable",
          ),
        });
        return;
      }

      await route.fulfill({
        status: 202,
        contentType: "application/json",
        body: envelope(
          {
            status: "invitation_prepared",
            email: "leaked-initial-admin@example.test",
            token: "leaked-activation-token",
            activation_url:
              "https://identity.example.test/activate/leaked-activation-token",
          },
          responseMeta("unsafe-correction-response"),
        ),
      });
      return;
    }

    if (path === `/api/v1/platform/tenants/${TENANT_ID}`) {
      expect(request.method()).toBe("GET");
      tenantDetailGets += 1;
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: envelope(tenants[0]),
      });
      return;
    }

    await route.fulfill({ status: 404 });
  });

  await page.goto(`/platform/tenants/${TENANT_ID}`);
  const correctionButton = page.getByRole("button", {
    name: "İlk yönetici bilgilerini düzelt",
  });
  await expect(correctionButton).toBeVisible();
  await correctionButton.click();

  let dialog = page.getByRole("dialog", {
    name: "İlk yönetici bilgilerini düzelt",
  });
  const fullName = dialog.getByLabel("İlk yönetici tam adı");
  const email = dialog.getByLabel("İlk yönetici e-posta adresi");
  await expect(fullName).toBeFocused();
  await expect(fullName).toHaveValue("");
  await expect(email).toHaveValue("");
  await expect(fullName).toHaveAttribute("required", "");
  await expect(fullName).toHaveAttribute("minlength", "1");
  await expect(fullName).toHaveAttribute("maxlength", "200");
  await expect(email).toHaveAttribute("type", "email");
  await expect(email).toHaveAttribute("required", "");
  await expect(email).toHaveAttribute("minlength", "3");
  await expect(email).toHaveAttribute("maxlength", "320");
  await expect(dialog.locator("form")).toHaveAttribute(
    "autocomplete",
    "off",
  );
  await expect(fullName).toHaveAttribute("autocomplete", "off");
  await expect(email).toHaveAttribute("autocomplete", "off");
  await expect(dialog).toContainText(
    "Önceki etkinleştirme bağlantısı geçersiz olur",
  );
  await expect(dialog).toContainText("yeni bir davet hazırlanır");

  await fullName.evaluate((input) => {
    const field = input as HTMLInputElement;
    field.value = "x".repeat(201);
    field.dispatchEvent(new Event("input", { bubbles: true }));
  });
  await email.fill("deniz.yonetici@example.com");
  await dialog.locator("form").evaluate((form) => {
    form.dispatchEvent(new Event("submit", { bubbles: true, cancelable: true }));
  });
  const validationAlert = dialog.getByRole("alert");
  await expect(validationAlert).toBeVisible();
  await expect(validationAlert).toContainText("İlk yönetici");
  await expect(validationAlert).toHaveAttribute("tabindex", "-1");
  await expect(validationAlert).toBeFocused();
  expect(correctionRequests).toBe(0);

  await fullName.evaluate((input) => {
    const field = input as HTMLInputElement;
    field.value = "y".repeat(201);
    field.dispatchEvent(new Event("input", { bubbles: true }));
  });
  await dialog.locator("form").evaluate((form) => {
    form.dispatchEvent(new Event("submit", { bubbles: true, cancelable: true }));
  });
  await expect(validationAlert).toBeFocused();
  expect(correctionRequests).toBe(0);

  await fullName.fill("  Deniz Yönetici  ");
  await email.fill("  DENIZ.YONETICI@EXAMPLE.COM  ");
  await dialog.locator("form").evaluate((form) => {
    form.dispatchEvent(new Event("submit", { bubbles: true, cancelable: true }));
    form.dispatchEvent(new Event("submit", { bubbles: true, cancelable: true }));
  });

  await correctionRequestObserved;
  await expect.poll(() => correctionRequests).toBe(1);
  await expect(
    dialog.getByRole("button", { name: /hazırlanıyor…/i }),
  ).toBeDisabled();
  await expect(dialog.getByRole("button", { name: "Vazgeç" })).toBeDisabled();
  await expect(fullName).toBeDisabled();
  await expect(email).toBeDisabled();
  await expect(dialog).toHaveAttribute("aria-busy", "true");
  await expect(dialog).toHaveAttribute("tabindex", "-1");
  await expect(dialog).toBeFocused();
  await page.keyboard.press("Tab");
  await expect(dialog).toBeFocused();
  await page.keyboard.press("Shift+Tab");
  await expect(dialog).toBeFocused();
  await page.keyboard.press("Escape");
  await expect(dialog).toBeVisible();
  releaseCorrectionRequest();

  await expect(dialog).toBeHidden();
  await expect(correctionButton).toBeFocused();
  await expect(
    page.getByText("İlk yönetici bilgileri düzeltildi", { exact: true }),
  ).toBeVisible();
  await expect(
    page.getByText("Referans: initial-admin-correction-correlation"),
  ).toBeVisible();
  await expect(
    page.getByText("deniz.yonetici@example.com", { exact: true }),
  ).toHaveCount(0);
  await expect(page.getByText("leaked-activation-token")).toHaveCount(0);
  expect(tenantDetailGets).toBe(1);

  correctionMode = "conflict";
  await correctionButton.click();
  dialog = page.getByRole("dialog", {
    name: "İlk yönetici bilgilerini düzelt",
  });
  await expect(dialog.getByLabel("İlk yönetici tam adı")).toHaveValue("");
  await expect(
    dialog.getByLabel("İlk yönetici e-posta adresi"),
  ).toHaveValue("");
  await dialog.getByLabel("İlk yönetici tam adı").fill("Deniz Yönetici");
  await dialog
    .getByLabel("İlk yönetici e-posta adresi")
    .fill("deniz.yonetici@example.com");
  await dialog.getByRole("button", { name: "Bilgileri düzelt" }).click();

  const conflictAlert = dialog.getByRole("alert");
  await expect(conflictAlert).toBeVisible();
  await expect(conflictAlert).toHaveAttribute("tabindex", "-1");
  await expect(conflictAlert).toBeFocused();
  await expect(conflictAlert).toContainText(
    "İlk yönetici işlemi mevcut durumda kullanılamıyor. Tenant ayrıntısını yenileyip daha sonra yeniden deneyin.",
  );
  await expect(conflictAlert).toContainText(
    "Referans: initial-admin-correction-unavailable",
  );
  await expect(conflictAlert).not.toContainText(
    "İlk yönetici daveti hazırlanamadı",
  );
  await expect(conflictAlert).not.toContainText("hesap durumunu");
  await expect(conflictAlert).not.toContainText(
    "farklı ilk yönetici bilgileri",
  );
  await expect(dialog.getByLabel("İlk yönetici tam adı")).toHaveValue(
    "Deniz Yönetici",
  );
  await expect(
    dialog.getByLabel("İlk yönetici e-posta adresi"),
  ).toHaveValue("deniz.yonetici@example.com");
  await expect(
    dialog.getByRole("button", { name: "Bilgileri düzelt" }),
  ).toBeEnabled();
  await page.keyboard.press("Escape");
  await expect(dialog).toBeHidden();
  await expect(correctionButton).toBeFocused();

  correctionMode = "malformed";
  await correctionButton.click();
  dialog = page.getByRole("dialog", {
    name: "İlk yönetici bilgilerini düzelt",
  });
  await dialog.getByLabel("İlk yönetici tam adı").fill("Deniz Yönetici");
  await dialog
    .getByLabel("İlk yönetici e-posta adresi")
    .fill("deniz.yonetici@example.com");
  await dialog.getByRole("button", { name: "Bilgileri düzelt" }).click();

  const malformedAlert = dialog.getByRole("alert");
  await expect(malformedAlert).toBeVisible();
  await expect(malformedAlert).toHaveAttribute("tabindex", "-1");
  await expect(malformedAlert).toBeFocused();
  await expect(malformedAlert).toContainText(
    "Sonuç doğrulanamadı",
  );
  await expect(malformedAlert).toContainText(
    "Yeni bir davet zaten hazırlanmış olabilir",
  );
  await expect(malformedAlert).toContainText(
    "platform denetim kaydını inceleyin ve sayfayı yenileyin",
  );
  await expect(dialog.getByLabel("İlk yönetici tam adı")).toHaveValue(
    "Deniz Yönetici",
  );
  await expect(
    dialog.getByLabel("İlk yönetici e-posta adresi"),
  ).toHaveValue("deniz.yonetici@example.com");
  const ambiguousCorrectionButton = dialog.getByRole("button", {
    name: "Bilgileri düzelt",
  });
  await expect(ambiguousCorrectionButton).toBeDisabled();
  await expect(
    dialog.getByRole("button", { name: "Vazgeç" }),
  ).toBeEnabled();
  await expect(
    dialog.getByRole("button", {
      name: "İlk yönetici bilgileri penceresini kapat",
    }),
  ).toBeEnabled();
  await dialog.locator("form").evaluate((form) => {
    form.dispatchEvent(new Event("submit", { bubbles: true, cancelable: true }));
    form.dispatchEvent(new Event("submit", { bubbles: true, cancelable: true }));
  });
  await expect.poll(() => correctionRequests).toBe(3);
  await expect(
    page.getByText("leaked-initial-admin@example.test", { exact: true }),
  ).toHaveCount(0);
  await expect(page.getByText("leaked-activation-token")).toHaveCount(0);
  await expect(
    page.getByText(
      "https://identity.example.test/activate/leaked-activation-token",
      { exact: true },
    ),
  ).toHaveCount(0);
  expect(correctionRequests).toBe(3);
  expect(tenantDetailGets).toBe(1);
});

test("initial-admin resend and correction are lifecycle-gated in the DOM and stale controls cannot start an action", async ({
  context,
  page,
}) => {
  const tenantUpdater = {
    ...platformAdmin,
    permissions: ["tenant:read:platform", "tenant:update:platform"],
    permission_version: 34,
  };
  const eligibleStatuses = [
    "provisioning",
    "trial",
    "active",
  ] as const;
  const ineligibleStatuses = [
    "suspended",
    "offboarding",
    "closed",
  ] as const;
  let currentStatus: TenantStatus = "active";
  let initialAdminMutationRequests = 0;

  await context.addCookies([
    {
      name: "wf_platform_refresh",
      value: "platform-initial-admin-lifecycle-refresh",
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
          user: tenantUpdater,
        }),
      });
      return;
    }

    expectPlatformBearer(request, PLATFORM_ACCESS_TOKEN);
    if (path === "/api/v1/platform/me") {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: envelope({ user: tenantUpdater }),
      });
      return;
    }

    if (path === `/api/v1/platform/tenants/${TENANT_ID}`) {
      expect(request.method()).toBe("GET");
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: envelope({
          ...tenants[0],
          status: currentStatus,
          health: healthByStatus[currentStatus],
        }),
      });
      return;
    }

    if (
      path.startsWith(
        `/api/v1/platform/tenants/${TENANT_ID}/initial-admin-invitation`,
      )
    ) {
      initialAdminMutationRequests += 1;
      await route.fulfill({ status: 418 });
      return;
    }

    await route.fulfill({ status: 404 });
  });

  for (const status of eligibleStatuses) {
    currentStatus = status;
    await page.goto(`/platform/tenants/${TENANT_ID}`);
    const invitationCard = page
      .getByRole("heading", { name: "İlk yönetici daveti" })
      .locator("xpath=ancestor::section[1]");
    await expect(
      invitationCard.getByRole("button", {
        name: "İlk yönetici davetini yeniden gönder",
      }),
    ).toBeEnabled();
    await expect(
      invitationCard.getByRole("button", {
        name: "İlk yönetici bilgilerini düzelt",
      }),
    ).toBeEnabled();
    await expect(
      invitationCard.getByText(
        /İlk yönetici işlemleri.*Hazırlanıyor.*Deneme.*Aktif/,
      ),
    ).toHaveCount(0);
  }

  for (const status of ineligibleStatuses) {
    currentStatus = status;
    await page.goto(`/platform/tenants/${TENANT_ID}`);
    const invitationCard = page
      .getByRole("heading", { name: "İlk yönetici daveti" })
      .locator("xpath=ancestor::section[1]");
    const resendButton = invitationCard.getByRole("button", {
      name: "İlk yönetici davetini yeniden gönder",
    });
    const correctionButton = invitationCard.getByRole("button", {
      name: "İlk yönetici bilgilerini düzelt",
    });
    await expect(resendButton).toBeDisabled();
    await expect(correctionButton).toBeDisabled();
    await expect(
      invitationCard.getByText(
        /İlk yönetici işlemleri.*Hazırlanıyor.*Deneme.*Aktif/,
      ),
    ).toBeVisible();

    await resendButton.evaluate((button) => {
      button.removeAttribute("disabled");
      button.dispatchEvent(new MouseEvent("click", { bubbles: true }));
    });
    await correctionButton.evaluate((button) => {
      button.removeAttribute("disabled");
      button.dispatchEvent(new MouseEvent("click", { bubbles: true }));
    });
    await expect(
      page.getByRole("dialog", {
        name: "İlk yönetici davetini yeniden gönder",
      }),
    ).toHaveCount(0);
    await expect(
      page.getByRole("dialog", {
        name: "İlk yönetici bilgilerini düzelt",
      }),
    ).toHaveCount(0);
    expect(initialAdminMutationRequests).toBe(0);
  }

  expect(initialAdminMutationRequests).toBe(0);
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
  await expect(
    page.getByRole("button", {
      name: "İlk yönetici davetini yeniden gönder",
    }),
  ).toHaveCount(0);
  await expect(
    page.getByRole("button", {
      name: "İlk yönetici bilgilerini düzelt",
    }),
  ).toHaveCount(0);

  await revalidateWithPermissions([
    "tenant:read:platform",
    "tenant:update:platform",
    "feature:read:platform",
    "feature:update:platform",
  ]);
  await expect(
    page.getByRole("button", {
      name: "İlk yönetici davetini yeniden gönder",
    }),
  ).toBeVisible();
  const correctionButton = page.getByRole("button", {
    name: "İlk yönetici bilgilerini düzelt",
  });
  await expect(correctionButton).toBeVisible();
  await correctionButton.click();
  const correctionDialog = page.getByRole("dialog", {
    name: "İlk yönetici bilgilerini düzelt",
  });
  await expect(correctionDialog).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(correctionDialog).toBeHidden();
  await expect(correctionButton).toBeFocused();
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
  await expect(
    page.getByRole("button", {
      name: "İlk yönetici davetini yeniden gönder",
    }),
  ).toHaveCount(0);
  await expect(
    page.getByRole("button", {
      name: "İlk yönetici bilgilerini düzelt",
    }),
  ).toHaveCount(0);

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

test("expired platform access is refreshed once across concurrent requests without crossing auth realms", async ({
  context,
  page,
}) => {
  const staleToken = "expired-platform-access";
  const freshToken = "refreshed-platform-access";
  let platformRefreshRequests = 0;
  let tenantRefreshRequests = 0;
  let staleProtectedRequests = 0;
  let releaseStaleRequests = () => {};
  const bothStaleRequestsObserved = new Promise<void>((resolve) => {
    releaseStaleRequests = resolve;
  });
  const detailTokens: string[] = [];
  const featureTokens: string[] = [];

  await context.addCookies([
    {
      name: "wf_platform_refresh",
      value: "platform-expiry-refresh",
      url: "http://127.0.0.1:3100",
      httpOnly: true,
      sameSite: "Lax",
    },
    {
      name: "wf_refresh",
      value: "tenant-refresh-must-not-be-used",
      url: "http://127.0.0.1:3100",
      httpOnly: true,
      sameSite: "Lax",
    },
  ]);

  await page.route("**/api/v1/**", async (route: Route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname;

    if (path === "/api/v1/auth/refresh") {
      tenantRefreshRequests += 1;
      await route.fulfill({ status: 418 });
      return;
    }

    if (path === "/api/v1/platform/auth/refresh") {
      platformRefreshRequests += 1;
      const accessToken =
        platformRefreshRequests === 1 ? staleToken : freshToken;
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: envelope({
          access_token: accessToken,
          token_type: "bearer",
          expires_in: 900,
          user: platformAdmin,
        }),
      });
      return;
    }

    if (path === "/api/v1/platform/me") {
      expectPlatformBearer(request, staleToken);
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: envelope({ user: platformAdmin }),
      });
      return;
    }

    if (
      path === `/api/v1/platform/tenants/${TENANT_ID}` ||
      path === `/api/v1/platform/tenants/${TENANT_ID}/features`
    ) {
      const authorization = request.headers().authorization ?? "";
      const token = authorization.replace(/^Bearer /, "");
      const observedTokens =
        path.endsWith("/features") ? featureTokens : detailTokens;
      observedTokens.push(token);

      if (token === staleToken) {
        staleProtectedRequests += 1;
        if (staleProtectedRequests === 2) {
          releaseStaleRequests();
        }
        await bothStaleRequestsObserved;
        await route.fulfill({
          status: 403,
          contentType: "application/json",
          body: errorEnvelope("platform_access_denied"),
        });
        return;
      }

      expect(token).toBe(freshToken);
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: path.endsWith("/features")
          ? envelope({ features: mockFeatures(false) })
          : envelope(tenants[0]),
      });
      return;
    }

    await route.fulfill({ status: 404 });
  });

  await page.goto(`/platform/tenants/${TENANT_ID}`);
  await expect(
    page.getByRole("heading", { name: tenants[0].name }),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Organizasyon özelliğini etkinleştir" }),
  ).toBeVisible();

  expect(platformRefreshRequests).toBe(2);
  expect(tenantRefreshRequests).toBe(0);
  expect(detailTokens).toEqual([staleToken, freshToken]);
  expect(featureTokens).toEqual([staleToken, freshToken]);
  expect(
    (await context.cookies()).find((cookie) => cookie.name === "wf_refresh")
      ?.value,
  ).toBe("tenant-refresh-must-not-be-used");
});

test("other platform 403s are not refreshed and an exact replayed denial is surfaced without a loop", async ({
  context,
  page,
}) => {
  const restrictedAdmin = {
    ...platformAdmin,
    permissions: ["tenant:read:platform"],
    permission_version: 41,
  };
  let platformRefreshRequests = 0;
  let detailRequests = 0;
  let denialCode = "authorization_denied";
  let accessToken = "";

  await context.addCookies([
    {
      name: "wf_platform_refresh",
      value: "platform-denial-refresh",
      url: "http://127.0.0.1:3100",
      httpOnly: true,
      sameSite: "Lax",
    },
  ]);

  await page.route("**/api/v1/**", async (route: Route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname;

    if (path === "/api/v1/platform/auth/refresh") {
      platformRefreshRequests += 1;
      accessToken = `platform-denial-access-${platformRefreshRequests}`;
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: envelope({
          access_token: accessToken,
          token_type: "bearer",
          expires_in: 900,
          user: restrictedAdmin,
        }),
      });
      return;
    }

    expectPlatformBearer(request, accessToken);
    if (path === "/api/v1/platform/me") {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: envelope({ user: restrictedAdmin }),
      });
      return;
    }

    if (path === `/api/v1/platform/tenants/${TENANT_ID}`) {
      detailRequests += 1;
      await route.fulfill({
        status: 403,
        contentType: "application/json",
        body: errorEnvelope(denialCode),
      });
      return;
    }

    await route.fulfill({ status: 404 });
  });

  await page.goto(`/platform/tenants/${TENANT_ID}`);
  const detailAlert = page
    .getByRole("main", { name: "Platform çalışma alanı" })
    .getByRole("alert");
  await expect(detailAlert).toContainText(
    "Bu işlem mevcut platform yetkilerinizle kullanılamıyor.",
  );
  expect(platformRefreshRequests).toBe(1);
  expect(detailRequests).toBe(1);

  denialCode = "platform_access_denied";
  await page.getByRole("button", { name: "Yeniden dene" }).click();
  await expect(detailAlert).toContainText(
    "Bu işlem mevcut platform yetkilerinizle kullanılamıyor.",
  );
  expect(platformRefreshRequests).toBe(2);
  expect(detailRequests).toBe(3);
  await expect(page).toHaveURL(
    new RegExp(`/platform/tenants/${TENANT_ID}$`),
  );
});

test("a failed guarded platform refresh does not replay or fall back to tenant refresh", async ({
  context,
  page,
}) => {
  let platformRefreshRequests = 0;
  let tenantRefreshRequests = 0;
  let detailRequests = 0;

  await context.addCookies([
    {
      name: "wf_platform_refresh",
      value: "platform-refresh-will-fail",
      url: "http://127.0.0.1:3100",
      httpOnly: true,
      sameSite: "Lax",
    },
    {
      name: "wf_refresh",
      value: "tenant-refresh-remains-isolated",
      url: "http://127.0.0.1:3100",
      httpOnly: true,
      sameSite: "Lax",
    },
  ]);

  await page.route("**/api/v1/**", async (route: Route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname;

    if (path === "/api/v1/auth/refresh") {
      tenantRefreshRequests += 1;
      await route.fulfill({ status: 418 });
      return;
    }

    if (path === "/api/v1/platform/auth/refresh") {
      platformRefreshRequests += 1;
      if (platformRefreshRequests === 1) {
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: envelope({
            access_token: "platform-access-that-expires",
            token_type: "bearer",
            expires_in: 900,
            user: {
              ...platformAdmin,
              permissions: ["tenant:read:platform"],
            },
          }),
        });
        return;
      }
      await route.fulfill({
        status: 401,
        contentType: "application/json",
        body: errorEnvelope("platform_refresh_invalid"),
      });
      return;
    }

    expectPlatformBearer(request, "platform-access-that-expires");
    if (path === "/api/v1/platform/me") {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: envelope({
          user: {
            ...platformAdmin,
            permissions: ["tenant:read:platform"],
          },
        }),
      });
      return;
    }

    if (path === `/api/v1/platform/tenants/${TENANT_ID}`) {
      detailRequests += 1;
      await route.fulfill({
        status: 403,
        contentType: "application/json",
        body: errorEnvelope("platform_access_denied"),
      });
      return;
    }

    await route.fulfill({ status: 404 });
  });

  await page.goto(`/platform/tenants/${TENANT_ID}`);
  await expect(page).toHaveURL(/\/platform\/login$/);
  await expect(
    page.getByRole("heading", { name: "Platform yönetimine giriş" }),
  ).toBeVisible();
  expect(platformRefreshRequests).toBe(2);
  expect(detailRequests).toBe(1);
  expect(tenantRefreshRequests).toBe(0);
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

test("an unknown initial-admin outcome stays tenant-scoped across modal close and unlocks only after a fresh authoritative detail", async ({
  context,
  page,
}) => {
  const tenantUpdater = {
    ...platformAdmin,
    permissions: ["tenant:read:platform", "tenant:update:platform"],
    permission_version: 51,
  };
  let detailGets = 0;
  let resendRequests = 0;
  let correctionRequests = 0;

  await context.addCookies([
    {
      name: "wf_platform_refresh",
      value: "platform-initial-admin-latch-refresh",
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
          user: tenantUpdater,
        }),
      });
      return;
    }

    expectPlatformBearer(request, PLATFORM_ACCESS_TOKEN);
    if (path === "/api/v1/platform/me") {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: envelope({ user: tenantUpdater }),
      });
      return;
    }

    if (path === `/api/v1/platform/tenants/${TENANT_ID}`) {
      expect(request.method()).toBe("GET");
      detailGets += 1;
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: envelope(
          tenants[0],
          responseMeta(`initial-admin-latch-detail-${detailGets}`),
        ),
      });
      return;
    }

    if (
      path ===
      `/api/v1/platform/tenants/${TENANT_ID}/initial-admin-invitation/resend`
    ) {
      resendRequests += 1;
      await route.fulfill({
        status: 202,
        contentType: "application/json",
        body: envelope(
          {
            status: "invitation_prepared",
            token: "must-never-render",
          },
          responseMeta("initial-admin-latch-ambiguous"),
        ),
      });
      return;
    }

    if (
      path ===
      `/api/v1/platform/tenants/${TENANT_ID}/initial-admin-invitation`
    ) {
      correctionRequests += 1;
      await route.fulfill({ status: 418 });
      return;
    }

    await route.fulfill({ status: 404 });
  });

  await page.goto(`/platform/tenants/${TENANT_ID}`);
  const invitationCard = page
    .getByRole("heading", { name: "İlk yönetici daveti" })
    .locator("xpath=ancestor::section[1]");
  const resendButton = invitationCard.getByRole("button", {
    name: "İlk yönetici davetini yeniden gönder",
  });
  const correctionButton = invitationCard.getByRole("button", {
    name: "İlk yönetici bilgilerini düzelt",
  });

  await resendButton.click();
  const confirmation = page.getByRole("dialog", {
    name: "İlk yönetici davetini yeniden gönder",
  });
  await confirmation
    .getByRole("button", { name: "Daveti yeniden gönder" })
    .click();
  await expect(confirmation.getByRole("alert")).toContainText(
    "Sonuç doğrulanamadı",
  );
  await page.keyboard.press("Escape");
  await expect(confirmation).toBeHidden();

  const latchExplanation = invitationCard.getByRole("alert");
  await expect(latchExplanation).toContainText(
    "Davet işleminin sonucu doğrulanamadı",
  );
  await expect(latchExplanation).toContainText("kilitlendi");
  await expect(resendButton).toBeDisabled();
  await expect(correctionButton).toBeDisabled();
  await expect(page.getByText("must-never-render")).toHaveCount(0);

  await resendButton.evaluate((button) => {
    button.removeAttribute("disabled");
    button.dispatchEvent(new MouseEvent("click", { bubbles: true }));
  });
  await correctionButton.evaluate((button) => {
    button.removeAttribute("disabled");
    button.dispatchEvent(new MouseEvent("click", { bubbles: true }));
  });
  await expect(
    page.getByRole("dialog", {
      name: "İlk yönetici davetini yeniden gönder",
    }),
  ).toHaveCount(0);
  await expect(
    page.getByRole("dialog", {
      name: "İlk yönetici bilgilerini düzelt",
    }),
  ).toHaveCount(0);
  expect(resendRequests).toBe(1);
  expect(correctionRequests).toBe(0);

  await page
    .getByRole("heading", { name: "Tenant metadata’sı" })
    .locator("xpath=ancestor::section[1]")
    .getByRole("button", { name: "Yenile" })
    .click();
  await expect.poll(() => detailGets).toBe(2);
  await expect(latchExplanation).toHaveCount(0);
  await expect(resendButton).toBeEnabled();
  await expect(correctionButton).toBeEnabled();

  await correctionButton.click();
  const correctionDialog = page.getByRole("dialog", {
    name: "İlk yönetici bilgilerini düzelt",
  });
  await expect(correctionDialog).toBeVisible();
  await correctionDialog.getByRole("button", { name: "Vazgeç" }).click();
  expect(resendRequests).toBe(1);
  expect(correctionRequests).toBe(0);
});

test("ambiguous tenant mutations reconcile committed state and an unreconciled feature stays locked until authoritative reload", async ({
  context,
  page,
}) => {
  let currentTenant = { ...tenants[0] };
  const secondTenant = { ...tenants[1] };
  let tenantGets = 0;
  let tenantPatches = 0;
  let featureGets = 0;
  let featurePatches = 0;
  let secondFeatureGets = 0;
  let secondFeaturePatches = 0;
  const organizationEnabled = false;
  let featureReadMode: "valid" | "malformed" = "valid";

  await context.addCookies([
    {
      name: "wf_platform_refresh",
      value: "platform-ambiguous-reconciliation-refresh",
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

    if (
      path === "/api/v1/platform/tenants" &&
      request.method() === "GET"
    ) {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: tenantListEnvelope([currentTenant, secondTenant], null),
      });
      return;
    }

    if (path === `/api/v1/platform/tenants/${TENANT_ID}`) {
      if (request.method() === "GET") {
        tenantGets += 1;
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: envelope(
            currentTenant,
            responseMeta(`ambiguous-tenant-get-${tenantGets}`),
          ),
        });
        return;
      }

      tenantPatches += 1;
      const payload = request.postDataJSON() as Record<string, unknown>;
      if (payload.name === "Ağ Sonrası Doğrulanan Tenant") {
        currentTenant = {
          ...currentTenant,
          name: "Ağ Sonrası Doğrulanan Tenant",
          updated_at: "2026-07-29T15:00:00.000Z",
        };
        await route.abort("failed");
        return;
      }

      expect(payload).toEqual({ status: "suspended" });
      currentTenant = {
        ...currentTenant,
        status: "suspended",
        health: "restricted",
        updated_at: "2026-07-29T15:01:00.000Z",
      };
      await route.fulfill({
        status: 503,
        contentType: "application/json",
        body: errorEnvelope(
          "platform_temporarily_unavailable",
          "lifecycle-ambiguous-503",
        ),
      });
      return;
    }

    if (path === `/api/v1/platform/tenants/${secondTenant.id}`) {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: envelope(
          secondTenant,
          responseMeta("ambiguous-second-tenant-get"),
        ),
      });
      return;
    }

    if (path === `/api/v1/platform/tenants/${TENANT_ID}/features`) {
      if (request.method() === "GET") {
        featureGets += 1;
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body:
            featureReadMode === "valid"
              ? envelope(
                  { features: mockFeatures(organizationEnabled) },
                  responseMeta(`ambiguous-feature-get-${featureGets}`),
                )
              : envelope(
                  { features: [{ key: "organization", enabled: true }] },
                  responseMeta("ambiguous-feature-malformed"),
                ),
        });
        return;
      }

      featurePatches += 1;
      expect(request.postDataJSON()).toEqual({
        features: [{ key: "organization", enabled: true }],
      });
      await route.fulfill({
        status: 503,
        contentType: "application/json",
        body: errorEnvelope(
          "platform_temporarily_unavailable",
          `feature-ambiguous-${featurePatches}`,
        ),
      });
      return;
    }

    if (
      path === `/api/v1/platform/tenants/${secondTenant.id}/features`
    ) {
      if (request.method() === "GET") {
        secondFeatureGets += 1;
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: envelope(
            { features: mockFeatures(false) },
            responseMeta(`ambiguous-second-feature-get-${secondFeatureGets}`),
          ),
        });
        return;
      }

      secondFeaturePatches += 1;
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: envelope({ features: mockFeatures(true) }),
      });
      return;
    }

    await route.fulfill({ status: 404 });
  });

  await page.goto(`/platform/tenants/${TENANT_ID}`);
  const settingsCard = page
    .getByRole("heading", { name: "Tenant ayarları" })
    .locator("xpath=ancestor::section[1]");
  await settingsCard
    .getByLabel("Tenant adı")
    .fill("Ağ Sonrası Doğrulanan Tenant");
  await settingsCard
    .getByRole("button", { name: "Ayarları kaydet" })
    .click();

  await expect(
    page.getByText("Tenant ayarları güncellendi", { exact: true }),
  ).toBeVisible();
  await expect(settingsCard.getByLabel("Tenant adı")).toHaveValue(
    "Ağ Sonrası Doğrulanan Tenant",
  );
  await expect(
    page.getByText("İşlem tamamlanamadı", { exact: true }),
  ).toHaveCount(0);
  expect(tenantPatches).toBe(1);
  expect(tenantGets).toBe(2);

  await page
    .getByLabel("Yeni yaşam döngüsü durumu")
    .selectOption("suspended");
  await page.getByRole("button", { name: "Geçişi incele" }).click();
  const lifecycleDialog = page.getByRole("dialog", {
    name: "Askıya alınmış durumuna geçir",
  });
  await lifecycleDialog
    .getByRole("button", { name: "Değişikliği uygula" })
    .click();
  await expect(lifecycleDialog).toBeHidden();
  await expect(
    page.getByText("Yaşam döngüsü güncellendi", { exact: true }),
  ).toBeVisible();
  await expect(
    page.getByText("Askıya alınmış", { exact: true }).first(),
  ).toBeVisible();
  await expect(
    page.getByText("İşlem tamamlanamadı", { exact: true }),
  ).toHaveCount(0);
  expect(tenantPatches).toBe(2);
  expect(tenantGets).toBe(3);

  const featureCard = page
    .getByRole("heading", { name: "Feature flag’ler" })
    .locator("xpath=ancestor::section[1]");
  const organizationFeature = featureCard
    .locator("article")
    .filter({ hasText: "Organizasyon" });
  const organizationToggle = organizationFeature.getByRole("button", {
    name: "Organizasyon özelliğini etkinleştir",
  });
  const employeeToggle = featureCard.getByRole("button", {
    name: "Çalışan yönetimi özelliğini devre dışı bırak",
  });
  featureReadMode = "malformed";
  await organizationToggle.click();
  const featureDialog = page.getByRole("dialog", {
    name: "Organizasyon özelliğini etkinleştir",
  });
  await featureDialog
    .getByRole("button", { name: "Değişikliği uygula" })
    .click();
  await expect(featureDialog).toBeHidden();
  const unknownFeatureAlert = featureCard.locator(
    "#feature-mutation-unknown-outcome",
  );
  await expect(unknownFeatureAlert).toContainText("sonucu doğrulanamadı");
  await expect(unknownFeatureAlert).toContainText("kilitlendi");
  await expect(organizationToggle).toBeDisabled();
  await expect(employeeToggle).toBeDisabled();
  await employeeToggle.evaluate((button) => {
    button.removeAttribute("disabled");
    button.dispatchEvent(new MouseEvent("click", { bubbles: true }));
  });
  await expect(
    page.getByRole("dialog", {
      name: "Çalışan yönetimi özelliğini devre dışı bırak",
    }),
  ).toHaveCount(0);
  expect(featurePatches).toBe(1);

  await featureCard.getByRole("button", { name: "Yenile" }).click();
  await expect.poll(() => featureGets).toBe(3);
  await expect(unknownFeatureAlert).toBeVisible();

  await page
    .getByRole("link", { name: "Tenant yönetimine dön" })
    .click();
  await page
    .getByRole("link", { name: "Kuzey Lojistik tenantını yönet" })
    .click();
  await expect.poll(() => secondFeatureGets).toBe(1);
  const secondFeatureCard = page
    .getByRole("heading", { name: "Feature flag’ler" })
    .locator("xpath=ancestor::section[1]");
  const secondOrganizationToggle = secondFeatureCard.getByRole("button", {
    name: "Organizasyon özelliğini etkinleştir",
  });
  await expect(
    secondFeatureCard.locator("#feature-mutation-unknown-outcome"),
  ).toBeVisible();
  await expect(secondOrganizationToggle).toBeDisabled();
  await secondOrganizationToggle.evaluate((button) => {
    button.removeAttribute("disabled");
    button.dispatchEvent(new MouseEvent("click", { bubbles: true }));
  });
  await expect(
    page.getByRole("dialog", {
      name: "Organizasyon özelliğini etkinleştir",
    }),
  ).toHaveCount(0);
  expect(secondFeaturePatches).toBe(0);

  await page
    .getByRole("link", { name: "Tenant yönetimine dön" })
    .click();
  await page
    .getByRole("link", {
      name: "Ağ Sonrası Doğrulanan Tenant tenantını yönet",
    })
    .click();
  await expect.poll(() => featureGets).toBe(4);
  await expect(unknownFeatureAlert).toBeVisible();

  featureReadMode = "valid";
  await featureCard.getByRole("button", { name: "Yenile" }).click();
  await expect.poll(() => featureGets).toBe(5);
  await expect(unknownFeatureAlert).toHaveCount(0);
  await expect(organizationToggle).toBeEnabled();
  await expect(employeeToggle).toBeEnabled();

  await organizationToggle.click();
  const mismatchDialog = page.getByRole("dialog", {
    name: "Organizasyon özelliğini etkinleştir",
  });
  await mismatchDialog
    .getByRole("button", { name: "Değişikliği uygula" })
    .click();
  const mismatchAlert = mismatchDialog.getByRole("alert");
  await expect(mismatchAlert).toContainText(
    "İstenen değişiklik sunucuda görülmedi",
  );
  await expect(
    mismatchDialog.getByRole("button", { name: "Değişikliği uygula" }),
  ).toBeEnabled();
  await expect(
    organizationFeature.getByText("Devre dışı", { exact: true }),
  ).toBeVisible();
  expect(featurePatches).toBe(2);
});

test("post-response session supersession reconciles create and latches resend and correction", async ({
  context,
  page,
}) => {
  const platformOperator = {
    ...platformAdmin,
    permissions: [
      ...platformAdmin.permissions,
      "tenant:create:platform",
    ],
  };
  let currentAccessToken = "platform-post-response-access-1";
  let listGets = 0;
  let detailGets = 0;
  let createRequests = 0;
  let resendRequests = 0;
  let correctionRequests = 0;
  let observeCreateRequest = () => {};
  const createRequestObserved = new Promise<void>((resolve) => {
    observeCreateRequest = resolve;
  });
  let releaseCreateRequest = () => {};
  const createRequestRelease = new Promise<void>((resolve) => {
    releaseCreateRequest = resolve;
  });
  let observeResendRequest = () => {};
  const resendRequestObserved = new Promise<void>((resolve) => {
    observeResendRequest = resolve;
  });
  let releaseResendRequest = () => {};
  const resendRequestRelease = new Promise<void>((resolve) => {
    releaseResendRequest = resolve;
  });
  let observeCorrectionRequest = () => {};
  const correctionRequestObserved = new Promise<void>((resolve) => {
    observeCorrectionRequest = resolve;
  });
  let releaseCorrectionRequest = () => {};
  const correctionRequestRelease = new Promise<void>((resolve) => {
    releaseCorrectionRequest = resolve;
  });

  await context.addCookies([
    {
      name: "wf_platform_refresh",
      value: "platform-post-response-refresh",
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
          access_token: currentAccessToken,
          token_type: "bearer",
          expires_in: 900,
          user: platformOperator,
        }),
      });
      return;
    }

    expectPlatformBearer(request, currentAccessToken);
    if (path === "/api/v1/platform/me") {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: envelope({ user: platformOperator }),
      });
      return;
    }

    if (path === "/api/v1/platform/tenants") {
      if (request.method() === "POST") {
        createRequests += 1;
        observeCreateRequest();
        await createRequestRelease;
        await route.fulfill({
          status: 201,
          contentType: "application/json",
          body: envelope(
            {
              ...tenants[2],
              slug: "post-response-create",
              name: "Post Response Tenant",
              initial_admin: { status: "invitation_prepared" },
            },
            responseMeta("post-response-create"),
          ),
        });
        return;
      }
      listGets += 1;
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: tenantListEnvelope([], null),
      });
      return;
    }

    if (path === `/api/v1/platform/tenants/${TENANT_ID}`) {
      detailGets += 1;
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: envelope(
          tenants[0],
          responseMeta(`post-response-detail-${detailGets}`),
        ),
      });
      return;
    }

    if (path === `/api/v1/platform/tenants/${TENANT_ID}/features`) {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: envelope({ features: mockFeatures(false) }),
      });
      return;
    }

    if (
      path ===
      `/api/v1/platform/tenants/${TENANT_ID}/initial-admin-invitation/resend`
    ) {
      resendRequests += 1;
      observeResendRequest();
      await resendRequestRelease;
      await route.fulfill({
        status: 202,
        contentType: "application/json",
        body: envelope(
          { status: "invitation_prepared" },
          responseMeta("post-response-resend"),
        ),
      });
      return;
    }

    if (
      path ===
      `/api/v1/platform/tenants/${TENANT_ID}/initial-admin-invitation`
    ) {
      correctionRequests += 1;
      observeCorrectionRequest();
      await correctionRequestRelease;
      await route.fulfill({
        status: 202,
        contentType: "application/json",
        body: envelope(
          { status: "invitation_prepared" },
          responseMeta("post-response-correction"),
        ),
      });
      return;
    }

    await route.fulfill({ status: 404 });
  });

  await page.goto("/platform/tenants");
  await page.getByRole("button", { name: "Yeni tenant oluştur" }).click();
  const createDialog = page.getByRole("dialog", {
    name: "Yeni tenant oluştur",
  });
  await createDialog.getByLabel("Tenant adı").fill("Post Response Tenant");
  await createDialog.getByLabel("Tenant kodu").fill("post-response-create");
  await createDialog
    .getByLabel("İlk yönetici tam adı")
    .fill("Post Response Admin");
  await createDialog
    .getByLabel("İlk yönetici e-posta adresi")
    .fill("post-response@example.com");
  await createDialog.getByRole("button", { name: "Tenant oluştur" }).click();
  await createRequestObserved;
  currentAccessToken = "platform-post-response-access-2";
  await publishPlatformSessionUpdate(page, {
    accessToken: currentAccessToken,
    user: { ...platformOperator, permission_version: 12 },
  });
  releaseCreateRequest();

  await expect.poll(() => listGets).toBe(2);
  await expect(createDialog.getByRole("alert")).toContainText(
    "Tam tenant listesi doğrulandı",
  );
  await expect(
    createDialog.getByRole("button", { name: "Tenant oluştur" }),
  ).toBeEnabled();
  expect(createRequests).toBe(1);

  await createDialog
    .getByRole("button", { name: "Vazgeç", exact: true })
    .click();
  await page.goto(`/platform/tenants/${TENANT_ID}`);
  const invitationCard = page
    .getByRole("heading", { name: "İlk yönetici daveti" })
    .locator("xpath=ancestor::section[1]");
  const resendButton = invitationCard.getByRole("button", {
    name: "İlk yönetici davetini yeniden gönder",
  });
  const correctionButton = invitationCard.getByRole("button", {
    name: "İlk yönetici bilgilerini düzelt",
  });

  await resendButton.click();
  const resendDialog = page.getByRole("dialog", {
    name: "İlk yönetici davetini yeniden gönder",
  });
  await resendDialog
    .getByRole("button", { name: "Daveti yeniden gönder" })
    .click();
  await resendRequestObserved;
  currentAccessToken = "platform-post-response-access-3";
  await publishPlatformSessionUpdate(page, {
    accessToken: currentAccessToken,
    user: { ...platformOperator, permission_version: 13 },
  });
  releaseResendRequest();

  await expect(resendDialog.getByRole("alert")).toContainText(
    "Sonuç doğrulanamadı",
  );
  await page.keyboard.press("Escape");
  await expect(resendDialog).toBeHidden();
  await expect(resendButton).toBeDisabled();
  await expect(correctionButton).toBeDisabled();
  await resendButton.evaluate((button) => {
    button.removeAttribute("disabled");
    button.dispatchEvent(new MouseEvent("click", { bubbles: true }));
  });
  expect(resendRequests).toBe(1);

  await page
    .getByRole("heading", { name: "Tenant metadata’sı" })
    .locator("xpath=ancestor::section[1]")
    .getByRole("button", { name: "Yenile" })
    .click();
  await expect.poll(() => detailGets).toBe(2);
  await expect(correctionButton).toBeEnabled();

  await correctionButton.click();
  const correctionDialog = page.getByRole("dialog", {
    name: "İlk yönetici bilgilerini düzelt",
  });
  await correctionDialog
    .getByLabel("İlk yönetici tam adı")
    .fill("Corrected Post Response Admin");
  await correctionDialog
    .getByLabel("İlk yönetici e-posta adresi")
    .fill("corrected-post-response@example.com");
  await correctionDialog
    .getByRole("button", { name: "Bilgileri düzelt" })
    .click();
  await correctionRequestObserved;
  currentAccessToken = "platform-post-response-access-4";
  await publishPlatformSessionUpdate(page, {
    accessToken: currentAccessToken,
    user: { ...platformOperator, permission_version: 14 },
  });
  releaseCorrectionRequest();

  await expect(correctionDialog.getByRole("alert")).toContainText(
    "Sonuç doğrulanamadı",
  );
  await expect(
    correctionDialog.getByRole("button", {
      name: "Bilgileri düzelt",
    }),
  ).toBeDisabled();
  expect(correctionRequests).toBe(1);
});

test("a principal change remounts protected forms without clearing the session ambiguity latch", async ({
  context,
  page,
}) => {
  const originalAdmin = {
    ...platformAdmin,
    permissions: [
      ...platformAdmin.permissions,
      "tenant:create:platform",
    ],
  };
  const replacementAdmin = {
    ...originalAdmin,
    id: "f2000000-0000-4000-8000-000000000101",
    email: "next-platform-admin@wealthyfalcon.demo",
    full_name: "Next Platform Admin",
    permission_version: 21,
  };
  let currentAccessToken = "platform-principal-a-access";
  let listMode: "valid" | "failed" = "valid";
  let listGets = 0;
  let createRequests = 0;
  let observeCreateRequest = () => {};
  const createRequestObserved = new Promise<void>((resolve) => {
    observeCreateRequest = resolve;
  });
  let releaseCreateRequest = () => {};
  const createRequestRelease = new Promise<void>((resolve) => {
    releaseCreateRequest = resolve;
  });
  let holdNextFailedList = false;
  let reconciliationFinished = false;
  let observeReconciliationRequest = () => {};
  const reconciliationRequestObserved = new Promise<void>((resolve) => {
    observeReconciliationRequest = resolve;
  });
  let releaseReconciliationRequest = () => {};
  const reconciliationRequestRelease = new Promise<void>((resolve) => {
    releaseReconciliationRequest = resolve;
  });

  await context.addCookies([
    {
      name: "wf_platform_refresh",
      value: "platform-principal-remount-refresh",
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
          access_token: currentAccessToken,
          token_type: "bearer",
          expires_in: 900,
          user:
            currentAccessToken === "platform-principal-a-access"
              ? originalAdmin
              : replacementAdmin,
        }),
      });
      return;
    }

    expectPlatformBearer(request, currentAccessToken);
    if (path === "/api/v1/platform/me") {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: envelope({
          user:
            currentAccessToken === "platform-principal-a-access"
              ? originalAdmin
              : replacementAdmin,
        }),
      });
      return;
    }

    if (path === "/api/v1/platform/tenants") {
      if (request.method() === "POST") {
        createRequests += 1;
        observeCreateRequest();
        await createRequestRelease;
        await route.fulfill({
          status: 201,
          contentType: "application/json",
          body: envelope(
            {
              ...tenants[2],
              slug: "principal-boundary-tenant",
              name: "Principal Boundary Tenant",
              initial_admin: { status: "invitation_prepared" },
            },
            responseMeta("principal-create-ambiguous"),
          ),
        });
        return;
      }
      listGets += 1;
      if (listMode === "failed") {
        const isHeldReconciliation = holdNextFailedList;
        if (isHeldReconciliation) {
          holdNextFailedList = false;
          observeReconciliationRequest();
          await reconciliationRequestRelease;
        }
        await route.fulfill({
          status: 503,
          contentType: "application/json",
          body: errorEnvelope(
            "platform_temporarily_unavailable",
            `principal-list-failed-${listGets}`,
          ),
        });
        if (isHeldReconciliation) {
          reconciliationFinished = true;
        }
        return;
      }
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: tenantListEnvelope([], null),
      });
      return;
    }

    await route.fulfill({ status: 404 });
  });

  await page.goto("/platform/tenants");
  await page.getByRole("button", { name: "Yeni tenant oluştur" }).click();
  let createDialog = page.getByRole("dialog", {
    name: "Yeni tenant oluştur",
  });
  await createDialog.getByLabel("Tenant adı").fill("Principal Boundary Tenant");
  await createDialog
    .getByLabel("Tenant kodu")
    .fill("principal-boundary-tenant");
  await createDialog
    .getByLabel("İlk yönetici tam adı")
    .fill("Previous Principal PII");
  await createDialog
    .getByLabel("İlk yönetici e-posta adresi")
    .fill("previous-principal@example.com");
  await createDialog.getByRole("button", { name: "Tenant oluştur" }).click();
  await createRequestObserved;
  expect(createRequests).toBe(1);

  listMode = "failed";
  currentAccessToken = "platform-principal-b-access";
  await publishPlatformSessionUpdate(page, {
    accessToken: currentAccessToken,
    user: replacementAdmin,
  });
  await expect(
    page.getByText("Next Platform Admin", { exact: true }).last(),
  ).toBeVisible();
  await expect(createDialog).toBeHidden();
  await expect.poll(() => listGets).toBe(2);

  holdNextFailedList = true;
  releaseCreateRequest();
  await reconciliationRequestObserved;

  await page.getByRole("button", { name: "Yeni tenant oluştur" }).click();
  createDialog = page.getByRole("dialog", {
    name: "Yeni tenant oluştur",
  });
  await expect(createDialog.getByRole("alert")).toContainText(
    "Tenant oluşturma sonucu doğrulanamadı",
  );
  await expect(createDialog.getByLabel("İlk yönetici tam adı")).toHaveValue("");
  await expect(
    createDialog.getByLabel("İlk yönetici e-posta adresi"),
  ).toHaveValue("");
  await expect(
    createDialog.getByRole("button", { name: "Tenant oluştur" }),
  ).toBeDisabled();
  expect(createRequests).toBe(1);

  releaseReconciliationRequest();
  await expect.poll(() => reconciliationFinished).toBe(true);
  listMode = "valid";
  await createDialog
    .getByRole("button", { name: "Sonucu yeniden doğrula" })
    .click();
  await expect(createDialog.getByRole("alert")).toContainText(
    "Tam tenant listesi doğrulandı",
  );
  await expect(
    createDialog.getByRole("button", { name: "Tenant oluştur" }),
  ).toBeEnabled();
});

test("manual initial-admin link is confirmed, copied once, and never persisted in browser storage", async ({
  context,
  page,
}) => {
  const tenantUpdater = {
    ...platformAdmin,
    permissions: ["tenant:read:platform", "tenant:update:platform"],
    permission_version: 41,
  };
  const activationUrl = `http://127.0.0.1:3100/activate#token=v1.${TENANT_ID}.${"a".repeat(64)}`;
  let manualLinkRequests = 0;

  await context.grantPermissions(["clipboard-read", "clipboard-write"], {
    origin: "http://127.0.0.1:3100",
  });
  await context.addCookies([
    {
      name: "wf_platform_refresh",
      value: "platform-manual-link-refresh",
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
          user: tenantUpdater,
        }),
      });
      return;
    }

    expectPlatformBearer(request, PLATFORM_ACCESS_TOKEN);
    if (path === "/api/v1/platform/me") {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: envelope({ user: tenantUpdater }),
      });
      return;
    }

    if (
      path ===
      `/api/v1/platform/tenants/${TENANT_ID}/initial-admin-invitation/manual-link`
    ) {
      expect(request.method()).toBe("POST");
      expect(request.postData()).toBeNull();
      expect(request.headers()["content-type"]).toBeUndefined();
      manualLinkRequests += 1;
      await route.fulfill({
        status: 201,
        contentType: "application/json",
        headers: {
          "Cache-Control": "no-store",
          Pragma: "no-cache",
        },
        body: envelope(
          {
            status: "manual_link_ready",
            activation_url: activationUrl,
            expires_at: "2099-08-05T15:00:00Z",
          },
          responseMeta("manual-link-correlation"),
        ),
      });
      return;
    }

    if (path === `/api/v1/platform/tenants/${TENANT_ID}`) {
      expect(request.method()).toBe("GET");
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: envelope(tenants[0]),
      });
      return;
    }

    await route.fulfill({ status: 404 });
  });

  await page.goto(`/platform/tenants/${TENANT_ID}`);
  const trigger = page.getByRole("button", { name: "Yeni davet linki üret" });
  await expect(trigger).toBeVisible();
  await trigger.click();

  const confirmation = page.getByRole("dialog", {
    name: "Yeni davet linki üret",
  });
  await expect(confirmation).toContainText(
    "önceki etkinleştirme linki hemen geçersiz olur",
  );
  await expect(confirmation).toContainText("süreli ve tek kullanımlıdır");
  await confirmation
    .getByRole("button", { name: "Yeni linki üret" })
    .evaluate((button) => {
      button.dispatchEvent(new MouseEvent("click", { bubbles: true }));
      button.dispatchEvent(new MouseEvent("click", { bubbles: true }));
    });

  const result = page.getByRole("region", { name: "Yeni davet linki hazır" });
  await expect(result).toBeVisible();
  await expect(result.getByLabel("Etkinleştirme linki")).toHaveValue(
    activationUrl,
  );
  expect(manualLinkRequests).toBe(1);

  await result.getByRole("button", { name: "Linki kopyala" }).click();
  await expect(result.getByRole("status")).toHaveText(
    "Davet linki panoya kopyalandı.",
  );
  expect(await page.evaluate(() => navigator.clipboard.readText())).toBe(
    activationUrl,
  );
  const browserStorage = await page.evaluate(
    () => `${JSON.stringify(localStorage)}${JSON.stringify(sessionStorage)}`,
  );
  expect(browserStorage).not.toContain(activationUrl);
  expect(browserStorage).not.toContain("a".repeat(64));

  await page.reload();
  await expect(
    page.getByRole("region", { name: "Yeni davet linki hazır" }),
  ).toHaveCount(0);
  await expect(page.getByLabel("Etkinleştirme linki")).toHaveCount(0);
});
