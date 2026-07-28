import { expect, test, type Page, type Route } from "@playwright/test";

function envelope(data: unknown): string {
  return JSON.stringify({
    data,
    meta: {
      request_id: "admin-redirect-test",
      trace_id: "11111111111111111111111111111111",
      correlation_id: "admin-redirect-test",
    },
  });
}

const admin = {
  id: "a1000000-0000-4000-8000-000000000001",
  membership_id: "a2000000-0000-4000-8000-000000000001",
  tenant_id: "a3000000-0000-4000-8000-000000000001",
  email: "admin@wealthyfalcon.demo",
  full_name: "Tenant Admin",
  tenant: {
    slug: "wealthy-falcon-demo",
    name: "Wealthy Falcon HR Demo",
  },
  workspace_scope: "tenant",
  roles: [
    {
      id: "a4000000-0000-4000-8000-000000000001",
      code: "tenant_admin",
      name: "Tenant yöneticisi",
      scope_type: "tenant",
    },
  ],
  permissions: [
    "self_service:read:own",
    "dashboard:read:tenant",
    "user:read:tenant",
  ],
  permission_version: 1,
};

const manager = {
  ...admin,
  id: "a1000000-0000-4000-8000-000000000002",
  membership_id: "a2000000-0000-4000-8000-000000000002",
  email: "manager@wealthyfalcon.demo",
  full_name: "Team Manager",
  roles: [
    {
      id: "a4000000-0000-4000-8000-000000000002",
      code: "manager",
      name: "Ekip yöneticisi",
      scope_type: "tenant",
    },
  ],
  permissions: [
    "self_service:read:own",
    "dashboard:read:own",
    "dashboard:read:team",
  ],
  permission_version: 2,
};

const employee = {
  ...admin,
  id: "a1000000-0000-4000-8000-000000000003",
  membership_id: "a2000000-0000-4000-8000-000000000003",
  email: "employee@wealthyfalcon.demo",
  full_name: "Ordinary Employee",
  roles: [
    {
      id: "a4000000-0000-4000-8000-000000000003",
      code: "employee",
      name: "Çalışan",
      scope_type: "tenant",
    },
  ],
  permissions: ["self_service:read:own", "dashboard:read:own"],
  permission_version: 3,
};

async function installLoginApi(page: Page, user: typeof admin): Promise<void> {
  const accessToken = "admin-access-token";

  await page.route("**/api/v1/**", async (route: Route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname;

    if (path === "/api/v1/auth/login") {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        headers: {
          "set-cookie":
            "wf_refresh=admin-refresh; Path=/; HttpOnly; SameSite=Lax; Max-Age=3600",
        },
        body: envelope({
          status: "authenticated",
          access_token: accessToken,
          token_type: "bearer",
          expires_in: 900,
          user,
        }),
      });
      return;
    }

    if (path === "/api/v1/auth/refresh") {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        headers: {
          "set-cookie":
            "wf_refresh=admin-refresh-rotated; Path=/; HttpOnly; SameSite=Lax; Max-Age=3600",
        },
        body: envelope({
          access_token: accessToken,
          token_type: "bearer",
          expires_in: 900,
          user,
        }),
      });
      return;
    }

    if (path === "/api/v1/me") {
      expect(request.headers().authorization).toBe(`Bearer ${accessToken}`);
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: envelope({ user }),
      });
      return;
    }

    if (path === "/api/v1/tenant/features") {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: envelope({
          features: [
            { key: "self_service", enabled: true, source: "override" },
            { key: "reporting", enabled: true, source: "override" },
          ],
        }),
      });
      return;
    }

    await route.fulfill({ status: 404 });
  });
}

async function logIn(page: Page, user: typeof admin): Promise<void> {
  await installLoginApi(page, user);
  await page.goto("/login");
  await page.getByLabel("E-posta adresi").fill(user.email);
  await page.getByLabel("Parola").fill("A safe admin test password");
  await page.getByRole("button", { name: "Giriş yap" }).click();
}

test("tenant admin with self-service access lands on the admin dashboard", async ({ page }) => {
  await logIn(page, admin);
  await expect(page).toHaveURL(/\/dashboard$/);
  await expect(page.getByRole("link", { name: "Kullanıcılar" })).toBeVisible();
});

test("team manager with self-service access lands on the team dashboard", async ({
  page,
}) => {
  await logIn(page, manager);
  await expect(page).toHaveURL(/\/dashboard$/);
  await expect(page.getByRole("link", { name: "Genel bakış" })).toBeVisible();
});

test("ordinary employee with self-service access lands on the employee home", async ({
  page,
}) => {
  await logIn(page, employee);
  await expect(page).toHaveURL(/\/home$/);
  await expect(
    page.getByRole("link", { name: "Çalışan ana sayfası" }),
  ).toBeVisible();
  await expect(page.getByRole("link", { name: "Genel bakış" })).toHaveCount(0);
});
