import { expect, test, type Request, type Route } from "@playwright/test";

const user = {
  id: "f2000000-0000-4000-8000-000000000001",
  tenant_id: "f1000000-0000-4000-8000-000000000001",
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
  permissions: [
    "user:read:tenant",
    "user:invite:tenant",
    "user:update:tenant",
    "role:assign:tenant",
  ],
  permission_version: 1,
};

function dataEnvelope(data: unknown): string {
  return JSON.stringify({ data });
}

function errorEnvelope(code: string): string {
  return JSON.stringify({
    error: {
      code,
      message: "Request failed",
      details: null,
      correlation_id: "browser-smoke",
    },
  });
}

function refreshCookie(value: string): string {
  return `wf_refresh=${value}; Path=/; HttpOnly; SameSite=Lax; Max-Age=3600`;
}

async function requestCookie(request: Request): Promise<string> {
  return (await request.headerValue("cookie")) ?? "";
}

test("login, reload refresh, protected shell, and logout", async ({ page, context }) => {
  let accessToken = "";
  let refreshCredential = "";
  let refreshCount = 0;
  let meCount = 0;
  let logoutCount = 0;

  await page.route("**/api/v1/**", async (route: Route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname;

    if (path === "/api/v1/auth/login") {
      expect(request.method()).toBe("POST");
      expect(request.postDataJSON()).toEqual({
        tenant_slug: "wealthy-falcon-demo",
        email: "admin@wealthyfalcon.demo",
        password: "A safe browser smoke password",
      });

      accessToken = "access-login";
      refreshCredential = "refresh-1";
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        headers: { "set-cookie": refreshCookie(refreshCredential) },
        body: dataEnvelope({
          access_token: accessToken,
          token_type: "bearer",
          expires_in: 900,
          user,
        }),
      });
      return;
    }

    if (path === "/api/v1/auth/refresh") {
      expect(request.method()).toBe("POST");
      expect(request.postData()).toBeNull();
      expect(await requestCookie(request)).toContain(`wf_refresh=${refreshCredential}`);

      refreshCount += 1;
      accessToken = `access-refresh-${refreshCount}`;
      refreshCredential = `refresh-${refreshCount + 1}`;
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        headers: { "set-cookie": refreshCookie(refreshCredential) },
        body: dataEnvelope({
          access_token: accessToken,
          token_type: "bearer",
          expires_in: 900,
          user,
        }),
      });
      return;
    }

    if (path === "/api/v1/me") {
      expect(request.method()).toBe("GET");
      expect(request.headers().authorization).toBe(`Bearer ${accessToken}`);
      meCount += 1;
      if (meCount === 1) {
        await route.fulfill({
          status: 401,
          contentType: "application/json",
          body: errorEnvelope("authentication_required"),
        });
        return;
      }
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: dataEnvelope({ user }),
      });
      return;
    }

    if (path === "/api/v1/auth/logout") {
      expect(request.method()).toBe("POST");
      expect(request.postData()).toBeNull();
      expect(request.headers().authorization).toBe(`Bearer ${accessToken}`);
      expect(await requestCookie(request)).toContain(`wf_refresh=${refreshCredential}`);
      logoutCount += 1;
      refreshCredential = "";
      await route.fulfill({
        status: 204,
        headers: {
          "set-cookie": "wf_refresh=; Path=/; HttpOnly; SameSite=Lax; Max-Age=0",
        },
      });
      return;
    }

    await route.fulfill({
      status: 404,
      contentType: "application/json",
      body: errorEnvelope("not_found"),
    });
  });

  await page.goto("/dashboard");
  await expect(page).toHaveURL(/\/login$/);

  await page.getByLabel("Kurum kodu").fill("wealthy-falcon-demo");
  await page.getByLabel("E-posta adresi").fill("admin@wealthyfalcon.demo");
  await page.getByLabel("Parola").fill("A safe browser smoke password");
  await page.getByRole("button", { name: "Giriş yap" }).click();

  await expect(page).toHaveURL(/\/dashboard$/);
  await expect(page.getByRole("heading", { name: "Merhaba, Maya Stone" })).toBeVisible();
  await expect(page.getByText("Wealthy Falcon HR Demo").first()).toBeVisible();
  expect(refreshCount).toBe(1);
  expect(meCount).toBe(2);

  const refreshedCookie = (await context.cookies()).find(
    (cookie) => cookie.name === "wf_refresh",
  );
  expect(refreshedCookie).toMatchObject({
    value: "refresh-2",
    httpOnly: true,
    sameSite: "Lax",
  });
  expect(await page.evaluate(() => document.cookie)).not.toContain("wf_refresh");
  const loginStorage = await page.evaluate(() =>
    JSON.stringify({
      local: { ...localStorage },
      session: { ...sessionStorage },
    }),
  );
  expect(loginStorage).not.toContain("access-");
  expect(loginStorage).not.toContain("refresh-");
  expect(loginStorage).not.toContain("token");

  await page.reload();

  await expect(page.getByRole("heading", { name: "Merhaba, Maya Stone" })).toBeVisible();
  expect(refreshCount).toBe(2);
  expect(meCount).toBe(3);
  const rotatedCookie = (await context.cookies()).find(
    (cookie) => cookie.name === "wf_refresh",
  );
  expect(rotatedCookie?.value).toBe("refresh-3");
  const restoredStorage = await page.evaluate(() =>
    JSON.stringify({
      local: { ...localStorage },
      session: { ...sessionStorage },
    }),
  );
  expect(restoredStorage).not.toContain("access-");
  expect(restoredStorage).not.toContain("refresh-");
  expect(restoredStorage).not.toContain("token");

  await page.getByRole("button", { name: "Çıkış yap" }).click();

  await expect(page).toHaveURL(/\/login$/);
  expect(logoutCount).toBe(1);
  expect((await context.cookies()).some((cookie) => cookie.name === "wf_refresh")).toBe(
    false,
  );

  await page.goto("/dashboard");
  await expect(page).toHaveURL(/\/login$/);
  expect(refreshCount).toBe(2);
});
