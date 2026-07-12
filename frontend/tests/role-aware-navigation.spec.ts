import { expect, test, type Route } from "@playwright/test";

function envelope(data: unknown): string {
  return JSON.stringify({
    data,
    meta: {
      request_id: "browser-f2d",
      trace_id: "browser-f2d-trace",
      correlation_id: "browser-f2d",
    },
  });
}

function errorEnvelope(code: string): string {
  return JSON.stringify({
    error: {
      code,
      message: "Request denied",
      details: null,
      correlation_id: "browser-f2d",
    },
  });
}

const employee = {
  id: "f2000000-0000-4000-8000-000000000021",
  tenant_id: "f1000000-0000-4000-8000-000000000001",
  email: "employee@wealthyfalcon.demo",
  full_name: "Ece Çalışkan",
  tenant: {
    slug: "wealthy-falcon-demo",
    name: "Wealthy Falcon HR Demo",
  },
  workspace_scope: "tenant",
  roles: [
    {
      id: "f3000000-0000-4000-8000-000000000002",
      code: "employee",
      name: "Çalışan",
      scope_type: "tenant",
    },
  ],
  permissions: ["employee:read:own"],
  permission_version: 2,
};

const elevatedEmployee = {
  ...employee,
  roles: [
    {
      id: "f3000000-0000-4000-8000-000000000001",
      code: "tenant_admin",
      name: "Tenant yöneticisi",
      scope_type: "tenant",
    },
  ],
  permissions: ["dashboard:read:own", "user:read:tenant"],
  permission_version: 3,
};

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
  permissions: ["tenant:read:platform", "tenant:update:platform"],
  permission_version: 7,
  authentication_strength: "single_factor",
};

test("landing exposes a secondary platform management entry", async ({ page }) => {
  await page.goto("/");

  const navigation = page.getByRole("navigation", { name: "Ana navigasyon" });
  const platformEntry = navigation.getByRole("link", {
    name: "Platform yönetimi",
  });
  await expect(platformEntry).toHaveAttribute("href", "/platform/login");
  await platformEntry.click();

  await expect(page).toHaveURL(/\/platform\/login$/);
  await expect(
    page.getByRole("heading", { name: "Platform yönetimine giriş" }),
  ).toBeVisible();
});

test("employee navigation hides admin and direct users route never mounts its API", async ({
  page,
  context,
}) => {
  let accessToken = "";
  let refreshCount = 0;
  let userAdministrationRequests = 0;
  let roleWasGranted = false;

  await context.addCookies([
    {
      name: "wf_refresh",
      value: "employee-refresh",
      url: "http://127.0.0.1:3100",
      httpOnly: true,
      sameSite: "Lax",
    },
  ]);

  await page.route("**/api/v1/**", async (route: Route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname;

    if (path === "/api/v1/auth/refresh") {
      refreshCount += 1;
      accessToken = `employee-access-${refreshCount}`;
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: envelope({
          access_token: accessToken,
          token_type: "bearer",
          expires_in: 900,
          user: roleWasGranted ? elevatedEmployee : employee,
        }),
      });
      return;
    }

    expect(request.headers().authorization).toBe(`Bearer ${accessToken}`);
    if (path === "/api/v1/me") {
      if (roleWasGranted && accessToken === "employee-access-1") {
        await route.fulfill({
          status: 401,
          contentType: "application/json",
          body: errorEnvelope("session_invalid"),
        });
        return;
      }
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: envelope({ user: roleWasGranted ? elevatedEmployee : employee }),
      });
      return;
    }
    if (path === "/api/v1/users" && roleWasGranted) {
      userAdministrationRequests += 1;
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          data: [],
          meta: {
            request_id: "browser-f2d",
            trace_id: "browser-f2d-trace",
            correlation_id: "browser-f2d",
            limit: 25,
            next_cursor: null,
          },
        }),
      });
      return;
    }
    if (path === "/api/v1/users" || path.startsWith("/api/v1/users/")) {
      userAdministrationRequests += 1;
      await route.fulfill({
        status: 403,
        contentType: "application/json",
        body: errorEnvelope("authorization_denied"),
      });
      return;
    }

    await route.fulfill({ status: 404 });
  });

  await page.goto("/dashboard");
  await expect(page.getByRole("heading", { name: "Merhaba, Ece Çalışkan" })).toBeVisible();
  await expect(page.getByRole("link", { name: "Kullanıcılar" })).toHaveCount(0);

  await page.goto("/users");
  await expect(page).toHaveURL(/\/dashboard$/);
  await expect(page.getByRole("heading", { name: "Merhaba, Ece Çalışkan" })).toBeVisible();
  expect(userAdministrationRequests).toBe(0);

  roleWasGranted = true;
  await page.evaluate(() => window.dispatchEvent(new Event("focus")));
  await expect(page.getByRole("link", { name: "Kullanıcılar" })).toBeVisible();
  await page.getByRole("link", { name: "Kullanıcılar" }).click();
  await expect(page).toHaveURL(/\/users$/);
  await expect(page.getByRole("heading", { name: "Kullanıcılar", exact: true })).toBeVisible();
  expect(userAdministrationRequests).toBe(1);
});

test("platform login uses its own contract and lands in the separate shell", async ({
  context,
  page,
}) => {
  let accessToken = "";
  let tenantAuthRequests = 0;
  let platformLogoutRequests = 0;

  await page.route("**/api/v1/**", async (route: Route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname;

    if (path === "/api/v1/platform/auth/login") {
      expect(request.method()).toBe("POST");
      expect(request.postDataJSON()).toEqual({
        email: "platform@wealthyfalcon.demo",
        password: "A safe platform browser password",
      });
      accessToken = "platform-access";
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        headers: {
          "set-cookie": "wf_platform_refresh=platform-refresh; Path=/; HttpOnly; SameSite=Lax; Max-Age=3600",
        },
        body: envelope({
          status: "authenticated",
          access_token: accessToken,
          token_type: "bearer",
          expires_in: 900,
          user: platformAdmin,
        }),
      });
      return;
    }

    if (path === "/api/v1/platform/me") {
      expect(request.headers().authorization).toBe(`Bearer ${accessToken}`);
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: envelope({ user: platformAdmin }),
      });
      return;
    }

    if (path === "/api/v1/platform/auth/logout") {
      expect(request.method()).toBe("POST");
      expect(request.headers().authorization).toBe(`Bearer ${accessToken}`);
      platformLogoutRequests += 1;
      await route.fulfill({
        status: 204,
        headers: {
          "set-cookie":
            "wf_platform_refresh=; Path=/; HttpOnly; SameSite=Lax; Max-Age=0",
        },
      });
      return;
    }

    if (path.startsWith("/api/v1/auth/") || path === "/api/v1/me") {
      tenantAuthRequests += 1;
    }

    await route.fulfill({ status: 404 });
  });

  await page.goto("/platform/login");
  await expect(page.locator('[data-auth-surface="platform"]')).toBeVisible();
  await expect(page.getByLabel("Kurum kodu")).toHaveCount(0);
  await expect(page.getByText("Kurum seçimi")).toHaveCount(0);
  await page.getByLabel("E-posta adresi").fill("platform@wealthyfalcon.demo");
  await page.getByLabel("Parola").fill("A safe platform browser password");
  await page.getByRole("button", { name: "Platform yönetimine gir" }).click();

  await expect(page).toHaveURL(/\/platform$/);
  await expect(page.locator('[data-workspace-shell="platform"]')).toBeVisible();
  await expect(page.locator('[data-workspace-shell="tenant"]')).toHaveCount(0);
  await expect(page.getByRole("heading", { name: "Platform operasyonları" })).toBeVisible();
  await expect(page.getByRole("navigation", { name: "Platform menüsü" })).toBeVisible();
  await expect(page.getByRole("link", { name: "Kullanıcılar" })).toHaveCount(0);
  await expect(page.getByText("Internal Platform Identity Tenant")).toHaveCount(0);
  await expect(page.getByText(/Tek faktörlü doğrulama/).first()).toBeVisible();
  expect(tenantAuthRequests).toBe(0);

  await page.getByRole("button", { name: "Çıkış yap" }).click();
  await expect(page).toHaveURL(/\/platform\/login$/);
  expect(platformLogoutRequests).toBe(1);
  expect(
    (await context.cookies()).some(
      (cookie) => cookie.name === "wf_platform_refresh",
    ),
  ).toBe(false);
});

test("verified tenant credentials without a platform role are denied safely", async ({
  page,
}) => {
  let platformLoginRequests = 0;
  let tenantAuthRequests = 0;

  await page.route("**/api/v1/**", async (route: Route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    if (path === "/api/v1/platform/auth/login") {
      platformLoginRequests += 1;
      expect(request.postDataJSON()).toEqual({
        email: "tenant-admin@wealthyfalcon.demo",
        password: "A valid tenant-only browser password",
      });
      await route.fulfill({
        status: 403,
        contentType: "application/json",
        body: errorEnvelope("platform_role_required"),
      });
      return;
    }
    if (path.startsWith("/api/v1/auth/") || path === "/api/v1/me") {
      tenantAuthRequests += 1;
    }
    await route.fulfill({ status: 404 });
  });

  await page.goto("/platform/login");
  await page.getByLabel("E-posta adresi").fill("tenant-admin@wealthyfalcon.demo");
  await page.getByLabel("Parola").fill("A valid tenant-only browser password");
  await page.getByRole("button", { name: "Platform yönetimine gir" }).click();

  await expect(page).toHaveURL(/\/platform\/login$/);
  await expect(page.getByText("Platform girişi tamamlanamadı")).toBeVisible();
  await expect(
    page.getByText(/Bu hesap platform yönetimi için yetkilendirilmemiş/),
  ).toBeVisible();
  await expect(page.getByRole("list", { name: "Erişilebilir kurumlar" })).toHaveCount(0);
  expect(platformLoginRequests).toBe(1);
  expect(tenantAuthRequests).toBe(0);
});

test("refresh cookies cannot open the other authentication realm", async ({
  context,
  page,
}) => {
  await context.addCookies([
    {
      name: "wf_refresh",
      value: "tenant-only-refresh",
      url: "http://127.0.0.1:3100",
      httpOnly: true,
      sameSite: "Lax",
    },
  ]);

  await page.goto("/platform");

  await expect(page).toHaveURL(/\/platform\/login$/);
  await expect(
    page.getByRole("heading", { name: "Platform yönetimine giriş" }),
  ).toBeVisible();

  await context.clearCookies();
  await context.addCookies([
    {
      name: "wf_platform_refresh",
      value: "platform-only-refresh",
      url: "http://127.0.0.1:3100",
      httpOnly: true,
      sameSite: "Lax",
    },
  ]);

  await page.goto("/dashboard");

  await expect(page).toHaveURL(/\/login$/);
  await expect(page.getByRole("heading", { name: "Tekrar hoş geldiniz" })).toBeVisible();
});
