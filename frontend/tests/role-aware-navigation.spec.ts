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
  permissions: ["tenant:read:platform", "tenant:update:platform"],
  permission_version: 7,
};

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

test("platform login lands in a separate shell without tenant navigation", async ({ page }) => {
  let accessToken = "";

  await page.route("**/api/v1/**", async (route: Route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname;

    if (path === "/api/v1/auth/login") {
      expect(request.method()).toBe("POST");
      expect(request.postDataJSON()).toEqual({
        tenant_slug: "internal-platform",
        email: "platform@wealthyfalcon.demo",
        password: "A safe platform browser password",
      });
      accessToken = "platform-access";
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        headers: {
          "set-cookie": "wf_refresh=platform-refresh; Path=/; HttpOnly; SameSite=Lax; Max-Age=3600",
        },
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

    await route.fulfill({ status: 404 });
  });

  await page.goto("/login");
  await page.getByLabel("Kurum kodu").fill("internal-platform");
  await page.getByLabel("E-posta adresi").fill("platform@wealthyfalcon.demo");
  await page.getByLabel("Parola").fill("A safe platform browser password");
  await page.getByRole("button", { name: "Giriş yap" }).click();

  await expect(page).toHaveURL(/\/platform$/);
  await expect(page.locator('[data-workspace-shell="platform"]')).toBeVisible();
  await expect(page.locator('[data-workspace-shell="tenant"]')).toHaveCount(0);
  await expect(page.getByRole("heading", { name: "Platform operasyonları" })).toBeVisible();
  await expect(page.getByRole("navigation", { name: "Platform menüsü" })).toBeVisible();
  await expect(page.getByRole("link", { name: "Kullanıcılar" })).toHaveCount(0);
  await expect(page.getByText("Internal Platform Identity Tenant")).toHaveCount(0);
});
