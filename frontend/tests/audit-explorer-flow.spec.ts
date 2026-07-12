import { expect, test, type Route } from "@playwright/test";

const tenantId = "f1000000-0000-4000-8000-000000000001";
const actorId = "f2000000-0000-4000-8000-000000000001";

const tenantAdmin = {
  id: actorId,
  tenant_id: tenantId,
  email: "admin@wealthyfalcon.demo",
  full_name: "Maya Stone",
  tenant: {
    slug: "wealthy-falcon-demo",
    name: "Wealthy Falcon HR Demo",
  },
  workspace_scope: "tenant",
  roles: [
    {
      id: "f3000000-0000-4000-8000-000000000001",
      code: "tenant_admin",
      name: "Tenant yöneticisi",
      scope_type: "tenant",
    },
  ],
  permissions: ["dashboard:read:tenant", "audit:read:tenant"],
  permission_version: 5,
};

const employee = {
  ...tenantAdmin,
  id: "f2000000-0000-4000-8000-000000000022",
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
  permission_version: 2,
};

const platformAdmin = {
  id: "f2000000-0000-4000-8000-000000000099",
  tenant_id: "f1000000-0000-4000-8000-000000000099",
  email: "platform@wealthyfalcon.demo",
  full_name: "Atlas Platform",
  tenant: {
    slug: "internal-platform",
    name: "Internal Platform Identity Tenant",
  },
  workspace_scope: "platform",
  roles: [
    {
      id: "f3000000-0000-4000-8000-000000000099",
      code: "super_admin",
      name: "Süper yönetici",
      scope_type: "platform",
    },
  ],
  permissions: ["tenant:read:platform", "audit:read:platform"],
  permission_version: 8,
};

interface EventOverrides {
  id: string;
  event_type: string;
  category: string;
  action: string;
  result?: string;
  scope_type?: "tenant" | "platform";
  tenant_id?: string | null;
  resource_type?: string | null;
  resource_id?: string | null;
  changed_fields?: string[];
  metadata?: Record<string, string | number | boolean | null | (string | number | boolean | null)[]>;
}

function auditEvent(overrides: EventOverrides) {
  const scope = overrides.scope_type ?? "tenant";
  const visibilityClass =
    scope === "platform"
      ? "platform_ops"
      : overrides.category === "tenant_admin"
        ? "tenant_admin"
        : "tenant_security";
  return {
    id: overrides.id,
    occurred_at: "2026-07-12T14:30:00Z",
    scope_type: scope,
    tenant_id: overrides.tenant_id === undefined ? tenantId : overrides.tenant_id,
    actor_type: scope === "platform" ? "platform_admin" : "user",
    actor_user_id: scope === "platform" ? platformAdmin.id : actorId,
    event_type: overrides.event_type,
    category: overrides.category,
    severity: overrides.result === "failure" ? "warning" : "info",
    resource_type: overrides.resource_type ?? null,
    resource_id: overrides.resource_id ?? null,
    action: overrides.action,
    result: overrides.result ?? "success",
    request_id: `browser-${overrides.id.slice(-4)}`,
    trace_id: "1234567890abcdef1234567890abcdef",
    session_id: "f4000000-0000-4000-8000-000000000001",
    ip_address: "203.0.113.0",
    user_agent: "Chrome",
    changed_fields: overrides.changed_fields ?? [],
    metadata: overrides.metadata ?? {},
    data_classification:
      scope === "platform"
        ? "platform_metadata"
        : overrides.category === "tenant_admin"
          ? "tenant_administration"
          : "security_metadata",
    visibility_class: visibilityClass,
  };
}

const loginEvent = auditEvent({
  id: "a1000000-0000-4000-8000-000000000001",
  event_type: "auth.login.succeeded",
  category: "tenant_security",
  action: "login",
  resource_type: "session",
  resource_id: "f4000000-0000-4000-8000-000000000001",
  metadata: { authentication_method: "local" },
});

const invitationEvent = auditEvent({
  id: "a1000000-0000-4000-8000-000000000002",
  event_type: "user.invitation.created",
  category: "tenant_admin",
  action: "invite",
  resource_type: "user",
  resource_id: "f2000000-0000-4000-8000-000000000010",
  changed_fields: ["status", "roles"],
  metadata: { is_reinvite: false, initial_role: "employee" },
});

const roleEvent = auditEvent({
  id: "a1000000-0000-4000-8000-000000000003",
  event_type: "user.roles.replaced",
  category: "tenant_admin",
  action: "replace_roles",
  resource_type: "user",
  resource_id: "f2000000-0000-4000-8000-000000000010",
  changed_fields: ["roles", "permission_version"],
  metadata: {
    before_role_codes: ["employee"],
    after_role_codes: ["employee", "hr_specialist"],
    permission_version: 2,
  },
});

const sessionEvent = auditEvent({
  id: "a1000000-0000-4000-8000-000000000004",
  event_type: "session.revoked",
  category: "tenant_security",
  action: "revoke",
  resource_type: "session",
  resource_id: "f4000000-0000-4000-8000-000000000001",
  metadata: { revocation_reason: "logout", source: "access_session" },
});

function envelope(
  data: unknown,
  pagination?: { limit: number; next_cursor: string | null },
): string {
  return JSON.stringify({
    data,
    meta: {
      request_id: "browser-f2e",
      trace_id: "1234567890abcdef1234567890abcdef",
      correlation_id: "browser-f2e",
      ...(pagination ?? {}),
    },
  });
}

test("permitted tenant admin filters, pages, and inspects redacted audit events", async ({
  page,
  context,
}) => {
  let accessToken = "";
  const listQueries: URLSearchParams[] = [];
  let detailRequests = 0;

  await context.addCookies([
    {
      name: "wf_refresh",
      value: "tenant-audit-refresh",
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
      accessToken = "tenant-audit-access";
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: envelope({
          access_token: accessToken,
          token_type: "bearer",
          expires_in: 900,
          user: tenantAdmin,
        }),
      });
      return;
    }

    expect(request.headers().authorization).toBe(`Bearer ${accessToken}`);
    if (path === "/api/v1/me") {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: envelope({ user: tenantAdmin }),
      });
      return;
    }

    if (path === "/api/v1/audit-events") {
      expect(request.method()).toBe("GET");
      listQueries.push(new URLSearchParams(url.searchParams));
      const isSecondPage = url.searchParams.get("cursor") === "tenant-audit-page-2";
      const hasFilters = Boolean(
        url.searchParams.get("category") ||
          url.searchParams.get("event_type") ||
          url.searchParams.get("result"),
      );
      const events = isSecondPage
        ? [sessionEvent]
        : hasFilters
          ? [loginEvent]
          : [loginEvent, invitationEvent, roleEvent, sessionEvent];
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: envelope(events, {
          limit: 25,
          next_cursor: !isSecondPage && !hasFilters ? "tenant-audit-page-2" : null,
        }),
      });
      return;
    }

    if (path === `/api/v1/audit-events/${loginEvent.id}`) {
      detailRequests += 1;
      expect(request.method()).toBe("GET");
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: envelope(loginEvent),
      });
      return;
    }

    await route.fulfill({ status: 404 });
  });

  await page.goto("/audit");

  await expect(page.getByRole("heading", { name: "Denetim kayıtları" })).toBeVisible();
  await expect(page.getByText("Salt okunur ve hassas veriden arındırılmış")).toBeVisible();
  await expect(page.getByText("Giriş başarılı").first()).toBeVisible();
  await expect(page.getByText("Kullanıcı davet edildi").first()).toBeVisible();
  await expect(page.getByText("Kullanıcı rolleri değiştirildi").first()).toBeVisible();
  await expect(page.getByText("Oturum sonlandırıldı").first()).toBeVisible();

  await page.getByRole("button", { name: "Sonraki" }).click();
  await expect(page.getByText("Sayfa 2")).toBeVisible();
  expect(listQueries.at(-1)?.get("cursor")).toBe("tenant-audit-page-2");
  await page.getByRole("button", { name: "Önceki" }).click();

  await page.getByLabel("Kategori").fill("tenant_security");
  await page.getByLabel("Olay türü").fill("auth.login.succeeded");
  await page.getByLabel("Sonuç").selectOption("success");
  await page.getByRole("button", { name: "Filtrele" }).click();
  await expect(page.getByText("1 olay bu sayfada gösteriliyor")).toBeVisible();
  expect(listQueries.at(-1)?.get("category")).toBe("tenant_security");
  expect(listQueries.at(-1)?.get("event_type")).toBe("auth.login.succeeded");
  expect(listQueries.at(-1)?.get("result")).toBe("success");
  expect(listQueries.at(-1)?.get("limit")).toBe("25");

  await page.getByRole("button", { name: "Giriş başarılı olayını incele" }).click();
  const detail = page.getByRole("dialog", { name: "Giriş başarılı" });
  await expect(detail).toBeVisible();
  await expect(detail.getByText("Authentication method")).toBeVisible();
  await expect(detail.getByText("local", { exact: true })).toBeVisible();
  await expect(detail.getByRole("button", { name: /sil|kaydet/i })).toHaveCount(0);
  expect(detailRequests).toBe(1);
  await expect(page.getByText("super-secret-browser-value")).toHaveCount(0);
  await page.getByRole("button", { name: "Denetim kaydı ayrıntısını kapat" }).click();

  await page.setViewportSize({ width: 390, height: 844 });
  const mobileNavigation = page.getByRole("navigation", { name: "Mobil ana menü" });
  await expect(mobileNavigation.getByRole("link", { name: "Denetim kayıtları" })).toHaveAttribute(
    "aria-current",
    "page",
  );
  expect(
    await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth),
  ).toBe(true);
});

test("unauthorized tenant role has no audit navigation and direct route mounts no audit API", async ({
  page,
  context,
}) => {
  let accessToken = "";
  let auditRequests = 0;

  await context.addCookies([
    {
      name: "wf_refresh",
      value: "employee-audit-refresh",
      url: "http://127.0.0.1:3100",
      httpOnly: true,
      sameSite: "Lax",
    },
  ]);

  await page.route("**/api/v1/**", async (route: Route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    if (path === "/api/v1/auth/refresh") {
      accessToken = "employee-audit-access";
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

    expect(request.headers().authorization).toBe(`Bearer ${accessToken}`);
    if (path === "/api/v1/me") {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: envelope({ user: employee }),
      });
      return;
    }
    if (path.startsWith("/api/v1/audit-events")) {
      auditRequests += 1;
      await route.fulfill({ status: 403 });
      return;
    }
    await route.fulfill({ status: 404 });
  });

  await page.goto("/audit");

  await expect(page).toHaveURL(/\/dashboard$/);
  await expect(page.getByRole("heading", { name: "Merhaba, Ece Çalışkan" })).toBeVisible();
  await expect(page.getByRole("link", { name: "Denetim kayıtları" })).toHaveCount(0);
  expect(auditRequests).toBe(0);
});

test("platform audit view stays in the platform shell and never calls tenant audit APIs", async ({
  page,
  context,
}) => {
  let accessToken = "";
  let platformListRequests = 0;
  let tenantAuditRequests = 0;
  const platformEvent = auditEvent({
    id: "a1000000-0000-4000-8000-000000000099",
    event_type: "platform.tenant.created",
    category: "platform_operations",
    action: "create_tenant",
    scope_type: "platform",
    tenant_id: null,
    resource_type: "tenant",
    resource_id: tenantId,
    changed_fields: ["status", "plan_code"],
    metadata: { status: "provisioning", plan_code: "core" },
  });

  await context.addCookies([
    {
      name: "wf_refresh",
      value: "platform-audit-refresh",
      url: "http://127.0.0.1:3100",
      httpOnly: true,
      sameSite: "Lax",
    },
  ]);

  await page.route("**/api/v1/**", async (route: Route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    if (path === "/api/v1/auth/refresh") {
      accessToken = "platform-audit-access";
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

    expect(request.headers().authorization).toBe(`Bearer ${accessToken}`);
    if (path === "/api/v1/me") {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: envelope({ user: platformAdmin }),
      });
      return;
    }
    if (path === "/api/v1/platform/audit-events") {
      platformListRequests += 1;
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: envelope([platformEvent], { limit: 25, next_cursor: null }),
      });
      return;
    }
    if (path.startsWith("/api/v1/audit-events")) {
      tenantAuditRequests += 1;
      await route.fulfill({ status: 403 });
      return;
    }
    await route.fulfill({ status: 404 });
  });

  await page.goto("/platform/audit");

  await expect(page.locator('[data-workspace-shell="platform"]')).toBeVisible();
  await expect(page.locator('[data-workspace-shell="tenant"]')).toHaveCount(0);
  await expect(
    page.getByRole("heading", { name: "Platform denetim kayıtları" }),
  ).toBeVisible();
  await expect(page.getByText(/müşteri HR verileri bu görünümde yer almaz/i)).toBeVisible();
  const platformNavigation = page.getByRole("navigation", { name: "Platform menüsü" });
  await expect(
    platformNavigation.getByRole("link", { name: "Denetim kayıtları" }),
  ).toHaveAttribute("aria-current", "page");
  await expect(
    platformNavigation.getByRole("link", { name: "Platform genel bakış" }),
  ).not.toHaveAttribute("aria-current", "page");

  await expect(page.getByText("Tenant oluşturuldu").first()).toBeVisible();
  await page.getByRole("button", { name: "Tenant oluşturuldu olayını incele" }).click();
  await expect(page.getByRole("dialog", { name: "Tenant oluşturuldu" })).toBeVisible();
  expect(platformListRequests).toBe(1);
  expect(tenantAuditRequests).toBe(0);
  await expect(page.getByText("Internal Platform Identity Tenant")).toHaveCount(0);
});
