import { expect, test, type Request, type Route } from "@playwright/test";

const tenant = {
  slug: "wealthy-falcon-demo",
  name: "Wealthy Falcon HR Demo",
};

const tenantAdmin = {
  id: "f2000000-0000-4000-8000-000000000001",
  tenant_id: "f1000000-0000-4000-8000-000000000001",
  email: "admin@wealthyfalcon.demo",
  full_name: "Maya Stone",
  tenant,
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

const invitedEmployee = {
  id: "f2000000-0000-4000-8000-000000000014",
  tenant_id: tenantAdmin.tenant_id,
  email: "selin@wealthyfalcon.demo",
  full_name: "Selin Ak",
  tenant,
  workspace_scope: "tenant",
  roles: [
    {
      id: "f3000000-0000-4000-8000-000000000002",
      code: "employee",
      name: "Çalışan",
      scope_type: "tenant",
    },
  ],
  permissions: ["dashboard:read:own", "employee:read:own"],
  permission_version: 1,
};

function dataEnvelope(data: unknown): string {
  return JSON.stringify({ data });
}

function pagedEnvelope(data: unknown): string {
  return JSON.stringify({
    data,
    meta: {
      request_id: "browser-f2f",
      trace_id: "browser-f2f-trace",
      correlation_id: "browser-f2f",
      limit: 25,
      next_cursor: null,
    },
  });
}

function errorEnvelope(code: string): string {
  return JSON.stringify({
    error: {
      code,
      message: "Request failed",
      details: null,
      correlation_id: "browser-f2f",
    },
  });
}

function refreshCookie(value: string): string {
  return `wf_refresh=${value}; Path=/; HttpOnly; SameSite=Lax; Max-Age=3600`;
}

async function requestCookie(request: Request): Promise<string> {
  return (await request.headerValue("cookie")) ?? "";
}

test("invite, activate, login, refresh, protected navigation, and logout", async ({
  browser,
  context: adminContext,
  page: adminPage,
}) => {
  const invitationToken = "safe-browser-invitation-token";
  const password = "A safe browser smoke password";
  let invitationUrl = "";
  let adminAccessToken = "";
  let invitationCount = 0;

  await adminContext.addCookies([
    {
      name: "wf_refresh",
      value: "admin-refresh",
      url: "http://127.0.0.1:3100",
      httpOnly: true,
      sameSite: "Lax",
    },
  ]);

  await adminPage.route("**/api/v1/**", async (route: Route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname;

    if (path === "/api/v1/auth/refresh") {
      expect(request.method()).toBe("POST");
      expect(await requestCookie(request)).toContain("wf_refresh=admin-refresh");
      adminAccessToken = "access-admin";
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: dataEnvelope({
          access_token: adminAccessToken,
          token_type: "bearer",
          expires_in: 900,
          user: tenantAdmin,
        }),
      });
      return;
    }

    expect(request.headers().authorization).toBe(`Bearer ${adminAccessToken}`);
    if (path === "/api/v1/me") {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: dataEnvelope({ user: tenantAdmin }),
      });
      return;
    }

    if (path === "/api/v1/users") {
      expect(request.method()).toBe("GET");
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: pagedEnvelope([]),
      });
      return;
    }

    if (path === "/api/v1/users/invitations") {
      expect(request.method()).toBe("POST");
      expect(request.postDataJSON()).toEqual({
        email: invitedEmployee.email,
        full_name: invitedEmployee.full_name,
      });
      invitationCount += 1;
      invitationUrl = `http://127.0.0.1:3100/activate#token=${invitationToken}`;
      await route.fulfill({
        status: 201,
        contentType: "application/json",
        body: dataEnvelope({
          user: {
            id: invitedEmployee.id,
            email: invitedEmployee.email,
            full_name: invitedEmployee.full_name,
            status: "invited",
          },
          activation_url: invitationUrl,
          expires_at: "2026-07-13T10:00:00Z",
        }),
      });
      return;
    }

    await route.fulfill({ status: 404 });
  });

  await adminPage.goto("/users");
  await expect(
    adminPage.getByRole("heading", { name: "Kullanıcılar", exact: true }),
  ).toBeVisible();
  await adminPage.getByRole("button", { name: "Kullanıcı davet et" }).first().click();
  await adminPage.getByLabel("Ad soyad").fill(invitedEmployee.full_name);
  await adminPage.getByLabel("İş e-postası").fill(invitedEmployee.email);
  await adminPage.getByRole("button", { name: "Davet gönder" }).click();
  await expect(adminPage.getByRole("heading", { name: "Davet hazır" })).toBeVisible();
  await expect(adminPage.getByLabel("Etkinleştirme bağlantısı")).toHaveValue(
    invitationUrl,
  );
  expect(invitationCount).toBe(1);

  const inviteeContext = await browser.newContext({
    baseURL: "http://127.0.0.1:3100",
  });
  const inviteePage = await inviteeContext.newPage();
  let accessToken = "";
  let refreshCredential = "";
  let activationCount = 0;
  let refreshCount = 0;
  let meCount = 0;
  let logoutCount = 0;

  await inviteePage.route("**/api/v1/**", async (route: Route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname;

    if (path === "/api/v1/auth/activate") {
      expect(request.method()).toBe("POST");
      expect(request.postDataJSON()).toEqual({ token: invitationToken, password });
      activationCount += 1;
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: dataEnvelope({ user: invitedEmployee }),
      });
      return;
    }

    if (path === "/api/v1/auth/login") {
      expect(request.method()).toBe("POST");
      expect(request.postDataJSON()).toEqual({
        email: invitedEmployee.email,
        password,
      });
      accessToken = "access-login";
      refreshCredential = "refresh-1";
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        headers: { "set-cookie": refreshCookie(refreshCredential) },
        body: dataEnvelope({
          status: "authenticated",
          access_token: accessToken,
          token_type: "bearer",
          expires_in: 900,
          user: invitedEmployee,
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
          user: invitedEmployee,
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
        body: dataEnvelope({ user: invitedEmployee }),
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

  await inviteePage.goto(invitationUrl);
  await expect(inviteePage).toHaveURL(/\/activate$/);
  await inviteePage.getByLabel("Hesap parolası", { exact: true }).fill(password);
  await inviteePage.getByLabel("Hesap parolasını doğrulayın").fill(password);
  await inviteePage.getByRole("button", { name: "Davetimi tamamla" }).click();
  await expect(inviteePage.getByText("Üyeliğiniz hazır")).toBeVisible();
  expect(activationCount).toBe(1);
  expect(await inviteePage.evaluate(() => window.location.hash)).toBe("");
  expect(await inviteePage.evaluate(() => window.history.state?.token)).toBeUndefined();

  await inviteePage.getByRole("link", { name: "Giriş ekranına git" }).click();
  await expect(inviteePage).toHaveURL(/\/login$/);
  await expect(inviteePage.getByLabel("Kurum kodu")).toHaveCount(0);
  await inviteePage.getByLabel("E-posta adresi").fill(invitedEmployee.email);
  await inviteePage.getByLabel("Parola").fill(password);
  await inviteePage.getByRole("button", { name: "Giriş yap" }).click();

  await expect(inviteePage).toHaveURL(/\/dashboard$/);
  await expect(
    inviteePage.getByRole("heading", { name: "Merhaba, Selin Ak" }),
  ).toBeVisible();
  await expect(inviteePage.getByText(tenant.name).first()).toBeVisible();
  await expect(inviteePage.getByRole("link", { name: "Kullanıcılar" })).toHaveCount(0);
  await expect(inviteePage.getByRole("link", { name: "Denetim kayıtları" })).toHaveCount(
    0,
  );
  expect(refreshCount).toBe(1);
  expect(meCount).toBe(2);

  const refreshedCookie = (await inviteeContext.cookies()).find(
    (cookie) => cookie.name === "wf_refresh",
  );
  expect(refreshedCookie).toMatchObject({
    value: "refresh-2",
    httpOnly: true,
    sameSite: "Lax",
  });
  expect(await inviteePage.evaluate(() => document.cookie)).not.toContain("wf_refresh");
  const loginStorage = await inviteePage.evaluate(() =>
    JSON.stringify({
      local: { ...localStorage },
      session: { ...sessionStorage },
    }),
  );
  expect(loginStorage).not.toContain("access-");
  expect(loginStorage).not.toContain("refresh-");
  expect(loginStorage).not.toContain("token");

  await inviteePage.reload();

  await expect(
    inviteePage.getByRole("heading", { name: "Merhaba, Selin Ak" }),
  ).toBeVisible();
  expect(refreshCount).toBe(2);
  expect(meCount).toBe(3);
  const rotatedCookie = (await inviteeContext.cookies()).find(
    (cookie) => cookie.name === "wf_refresh",
  );
  expect(rotatedCookie?.value).toBe("refresh-3");
  const restoredStorage = await inviteePage.evaluate(() =>
    JSON.stringify({
      local: { ...localStorage },
      session: { ...sessionStorage },
    }),
  );
  expect(restoredStorage).not.toContain("access-");
  expect(restoredStorage).not.toContain("refresh-");
  expect(restoredStorage).not.toContain("token");

  await inviteePage.getByRole("button", { name: "Çıkış yap" }).click();

  await expect(inviteePage).toHaveURL(/\/login$/);
  expect(logoutCount).toBe(1);
  expect(
    (await inviteeContext.cookies()).some((cookie) => cookie.name === "wf_refresh"),
  ).toBe(false);

  await inviteePage.goto("/dashboard");
  await expect(inviteePage).toHaveURL(/\/login$/);
  expect(refreshCount).toBe(2);
  await inviteeContext.close();
});

test("existing identity accepts a membership then selects an organization", async ({
  context,
  page,
}) => {
  const email = "multi@wealthyfalcon.demo";
  const password = "A safe multi organization password";
  const activationToken = "existing-identity-invitation-token";
  const selectionTransaction =
    "os1.f1000000-0000-4000-8000-000000000020.safe-single-purpose-selection-material-000001";
  const organizations = [
    {
      selection_key: "f1000000-0000-4000-8000-000000000021",
      display_name: "Wealthy Falcon Türkiye",
    },
    {
      selection_key: "f1000000-0000-4000-8000-000000000022",
      display_name: "Wealthy Falcon Avrupa",
    },
  ];
  const selectedUser = {
    ...invitedEmployee,
    id: "f2000000-0000-4000-8000-000000000022",
    tenant_id: "f1000000-0000-4000-8000-000000000022",
    email,
    full_name: "Çok Kurumlu Kullanıcı",
    tenant: {
      slug: "wealthy-falcon-europe",
      name: organizations[1].display_name,
    },
  };
  let accessToken = "";
  let activationCount = 0;
  let loginCount = 0;
  let selectionCount = 0;
  let meCount = 0;

  await page.route("**/api/v1/**", async (route: Route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname;

    if (path === "/api/v1/auth/activate") {
      expect(request.method()).toBe("POST");
      expect(request.postDataJSON()).toEqual({
        token: activationToken,
        password,
      });
      activationCount += 1;
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: dataEnvelope({ user: selectedUser }),
      });
      return;
    }

    if (path === "/api/v1/auth/login") {
      expect(request.method()).toBe("POST");
      expect(request.postDataJSON()).toEqual({ email, password });
      loginCount += 1;
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: dataEnvelope({
          status: "organization_selection_required",
          selection_transaction: selectionTransaction,
          expires_in: 120,
          organizations,
        }),
      });
      return;
    }

    if (path === "/api/v1/auth/select-organization") {
      expect(request.method()).toBe("POST");
      expect(request.headers().authorization).toBeUndefined();
      expect(request.postDataJSON()).toEqual({
        selection_transaction: selectionTransaction,
        selection_key: organizations[1].selection_key,
      });
      selectionCount += 1;
      accessToken = "multi-selected-access";
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        headers: { "set-cookie": refreshCookie("multi-selected-refresh") },
        body: dataEnvelope({
          status: "authenticated",
          access_token: accessToken,
          token_type: "bearer",
          expires_in: 900,
          user: selectedUser,
        }),
      });
      return;
    }

    if (path === "/api/v1/me") {
      expect(request.method()).toBe("GET");
      expect(request.headers().authorization).toBe(`Bearer ${accessToken}`);
      meCount += 1;
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: dataEnvelope({ user: selectedUser }),
      });
      return;
    }

    await route.fulfill({ status: 404 });
  });

  await page.goto(`/activate#token=${activationToken}`);
  await expect(
    page.getByText("mevcut hesabınız varsa kullandığınız parolayı girin", {
      exact: false,
    }),
  ).toBeVisible();
  await page.getByLabel("Hesap parolası", { exact: true }).fill(password);
  await page.getByLabel("Hesap parolasını doğrulayın").fill(password);
  await page.getByRole("button", { name: "Davetimi tamamla" }).click();
  await expect(page.getByText("Üyeliğiniz hazır")).toBeVisible();
  expect(activationCount).toBe(1);
  expect(await page.evaluate(() => window.location.hash)).toBe("");
  await page.getByRole("link", { name: "Giriş ekranına git" }).click();

  await expect(page).toHaveURL(/\/login$/);
  await expect(page.getByLabel("Kurum kodu")).toHaveCount(0);
  await page.getByLabel("E-posta adresi").fill(email);
  await page.getByLabel("Parola").fill(password);
  await page.getByRole("button", { name: "Giriş yap" }).click();

  await expect(page).toHaveURL(/\/select-organization$/);
  await expect(
    page.getByRole("heading", { name: "Çalışacağınız kurumu seçin" }),
  ).toBeVisible();
  const organizationList = page.getByRole("list", { name: "Erişilebilir kurumlar" });
  await expect(organizationList.getByRole("listitem")).toHaveCount(2);
  await expect(page.getByText(selectionTransaction)).toHaveCount(0);
  for (const organization of organizations) {
    await expect(page.getByText(organization.display_name, { exact: true })).toBeVisible();
    await expect(page.getByText(organization.selection_key)).toHaveCount(0);
  }
  expect(loginCount).toBe(1);
  expect((await context.cookies()).some((cookie) => cookie.name === "wf_refresh")).toBe(
    false,
  );

  const browserStorage = await page.evaluate(() =>
    JSON.stringify({
      local: { ...localStorage },
      session: { ...sessionStorage },
    }),
  );
  expect(browserStorage).not.toContain(selectionTransaction);
  expect(browserStorage).not.toContain(email);

  await page
    .getByRole("button", { name: new RegExp(organizations[1].display_name) })
    .click();

  await expect(page).toHaveURL(/\/dashboard$/);
  await expect(
    page.getByRole("heading", { name: "Merhaba, Çok Kurumlu Kullanıcı" }),
  ).toBeVisible();
  await expect(page.getByText(organizations[1].display_name).first()).toBeVisible();
  expect(loginCount).toBe(1);
  expect(selectionCount).toBe(1);
  expect(meCount).toBe(1);
  expect(
    (await context.cookies()).find((cookie) => cookie.name === "wf_refresh")?.value,
  ).toBe("multi-selected-refresh");
  await expect(page.getByText(selectionTransaction)).toHaveCount(0);
  for (const organization of organizations) {
    await expect(page.getByText(organization.selection_key)).toHaveCount(0);
  }

  const selectedStorage = await page.evaluate(() =>
    JSON.stringify({
      local: { ...localStorage },
      session: { ...sessionStorage },
    }),
  );
  expect(selectedStorage).not.toContain(selectionTransaction);
  expect(selectedStorage).not.toContain("multi-selected-access");
  expect(selectedStorage).not.toContain("multi-selected-refresh");
});

test("tenant shell switches to another authorized organization with a rotated session", async ({
  context,
  page,
}) => {
  const currentTenant = {
    slug: "wealthy-falcon-turkiye",
    name: "Wealthy Falcon Türkiye",
  };
  const nextTenant = {
    slug: "wealthy-falcon-avrupa",
    name: "Wealthy Falcon Avrupa",
  };
  const currentUser = {
    ...tenantAdmin,
    tenant_id: "f1000000-0000-4000-8000-000000000031",
    email: "switcher@wealthyfalcon.demo",
    full_name: "Deniz Çoklu",
    tenant: currentTenant,
  };
  const nextUser = {
    ...currentUser,
    id: "f2000000-0000-4000-8000-000000000032",
    tenant_id: "f1000000-0000-4000-8000-000000000032",
    tenant: nextTenant,
  };
  const selectionTransaction =
    "os1.f1000000-0000-4000-8000-000000000030.safe-switch-selection-material-0000000001";
  const organizations = [
    {
      selection_key: "f4000000-0000-4000-8000-000000000032",
      display_name: nextTenant.name,
    },
  ];
  let accessToken = "current-tenant-access";
  let activeUser = currentUser;
  let switchCount = 0;
  let selectionCount = 0;
  let priorSessionRevoked = false;

  await context.addCookies([
    {
      name: "wf_refresh",
      value: "current-tenant-refresh",
      url: "http://127.0.0.1:3100",
      httpOnly: true,
      sameSite: "Lax",
    },
  ]);

  await page.route("**/api/v1/**", async (route: Route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname;

    if (path === "/api/v1/auth/refresh") {
      expect(priorSessionRevoked).toBe(false);
      expect(await requestCookie(request)).toContain(
        "wf_refresh=current-tenant-refresh",
      );
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: dataEnvelope({
          access_token: accessToken,
          token_type: "bearer",
          expires_in: 900,
          user: currentUser,
        }),
      });
      return;
    }

    if (path === "/api/v1/me") {
      expect(request.headers().authorization).toBe(`Bearer ${accessToken}`);
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: dataEnvelope({ user: activeUser }),
      });
      return;
    }

    if (path === "/api/v1/auth/organization-selection") {
      expect(request.method()).toBe("POST");
      expect(request.postData()).toBeNull();
      expect(request.headers().authorization).toBe("Bearer current-tenant-access");
      expect(await requestCookie(request)).toContain(
        "wf_refresh=current-tenant-refresh",
      );
      switchCount += 1;
      priorSessionRevoked = true;
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        headers: {
          "set-cookie": "wf_refresh=; Path=/; HttpOnly; SameSite=Lax; Max-Age=0",
        },
        body: dataEnvelope({
          status: "organization_selection_required",
          selection_transaction: selectionTransaction,
          expires_in: 120,
          organizations,
        }),
      });
      return;
    }

    if (path === "/api/v1/auth/select-organization") {
      expect(priorSessionRevoked).toBe(true);
      expect(request.headers().authorization).toBeUndefined();
      expect(await requestCookie(request)).not.toContain("wf_refresh=");
      expect(request.postDataJSON()).toEqual({
        selection_transaction: selectionTransaction,
        selection_key: organizations[0].selection_key,
      });
      selectionCount += 1;
      accessToken = "next-tenant-access";
      activeUser = nextUser;
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        headers: { "set-cookie": refreshCookie("next-tenant-refresh") },
        body: dataEnvelope({
          status: "authenticated",
          access_token: accessToken,
          token_type: "bearer",
          expires_in: 900,
          user: nextUser,
        }),
      });
      return;
    }

    await route.fulfill({ status: 404 });
  });

  await page.goto("/dashboard");
  await expect(page.getByRole("heading", { name: "Merhaba, Deniz Çoklu" })).toBeVisible();
  await expect(page.getByText(currentTenant.name).first()).toBeVisible();

  await page.getByRole("button", { name: "Kurum değiştir" }).click();
  await expect(page).toHaveURL(/\/select-organization$/);
  await expect(
    page.getByRole("heading", { name: "Çalışacağınız kurumu seçin" }),
  ).toBeVisible();
  expect(switchCount).toBe(1);
  expect(
    (await context.cookies()).some((cookie) => cookie.name === "wf_refresh"),
  ).toBe(false);
  await expect(page.getByText(selectionTransaction)).toHaveCount(0);
  for (const organization of organizations) {
    await expect(page.getByText(organization.selection_key)).toHaveCount(0);
  }

  await page
    .getByRole("button", { name: new RegExp(nextTenant.name) })
    .click();

  await expect(page).toHaveURL(/\/dashboard$/);
  await expect(page.getByText(nextTenant.name).first()).toBeVisible();
  expect(selectionCount).toBe(1);
  expect(
    (await context.cookies()).find((cookie) => cookie.name === "wf_refresh")?.value,
  ).toBe("next-tenant-refresh");

  const browserStorage = await page.evaluate(() =>
    JSON.stringify({
      local: { ...localStorage },
      session: { ...sessionStorage },
    }),
  );
  expect(browserStorage).not.toContain(selectionTransaction);
  expect(browserStorage).not.toContain("current-tenant-access");
  expect(browserStorage).not.toContain("next-tenant-access");
  expect(browserStorage).not.toContain("next-tenant-refresh");
});

test("invalid credentials stay generic and never reveal organizations", async ({
  page,
}) => {
  const email = "unknown@wealthyfalcon.demo";
  const password = "An incorrect but safe length password";
  let requestCount = 0;

  await page.route("**/api/v1/**", async (route: Route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname;

    if (path === "/api/v1/auth/login") {
      expect(request.method()).toBe("POST");
      expect(request.postDataJSON()).toEqual({ email, password });
      requestCount += 1;
      await route.fulfill({
        status: 401,
        contentType: "application/json",
        body: errorEnvelope("invalid_credentials"),
      });
      return;
    }

    requestCount += 1;
    await route.fulfill({ status: 404 });
  });

  await page.goto("/login");
  await expect(page.getByLabel("Kurum kodu")).toHaveCount(0);
  await page.getByLabel("E-posta adresi").fill(email);
  await page.getByLabel("Parola").fill(password);
  await page.getByRole("button", { name: "Giriş yap" }).click();

  await expect(page.getByText("Giriş tamamlanamadı")).toBeVisible();
  await expect(
    page.getByText(
      "E-posta veya parola eşleşmedi. Bilgilerinizi kontrol edip yeniden deneyin.",
    ),
  ).toBeVisible();
  await expect(page.getByText("Kurum seçimi gerekiyor")).toHaveCount(0);
  await expect(page.getByRole("list", { name: "Erişilebilir kurumlar" })).toHaveCount(0);
  expect(requestCount).toBe(1);
});
