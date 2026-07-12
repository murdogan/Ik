import { expect, test, type Route } from "@playwright/test";

const tenantAdminRole = {
  id: "f3000000-0000-4000-8000-000000000001",
  code: "tenant_admin",
  name: "Tenant yöneticisi",
  scope_type: "tenant",
};
const employeeRole = {
  id: "f3000000-0000-4000-8000-000000000002",
  code: "employee",
  name: "Çalışan",
  scope_type: "tenant",
};
const hrSpecialistRole = {
  id: "f3000000-0000-4000-8000-000000000003",
  code: "hr_specialist",
  name: "İK uzmanı",
  scope_type: "tenant",
};
const platformRole = {
  id: "f3000000-0000-4000-8000-000000000004",
  code: "super_admin",
  name: "Süper yönetici",
  scope_type: "platform",
};
const roleCatalog = [
  {
    ...employeeRole,
    description: "Kendi çalışan alanına erişir.",
    permissions: ["employee:read:own"],
  },
  {
    ...hrSpecialistRole,
    description: "Tenant İK operasyonlarını yürütür.",
    permissions: ["employee:read:tenant"],
  },
  {
    ...tenantAdminRole,
    description: "Kullanıcıları ve rolleri yönetir.",
    permissions: ["user:read:tenant", "role:assign:tenant"],
  },
  {
    ...platformRole,
    description: "Yalnız platform operasyonları.",
    permissions: ["tenant:read:platform"],
  },
];

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
    "user:read:tenant",
    "user:invite:tenant",
    "user:update:tenant",
    "role:assign:tenant",
  ],
  permission_version: 4,
};

const timestamps = {
  created_at: "2026-07-10T10:00:00Z",
  updated_at: "2026-07-10T10:00:00Z",
};

function envelope(data: unknown, page?: { limit: number; next_cursor: string | null }) {
  return JSON.stringify({
    data,
    meta: {
      request_id: "browser-f2c",
      trace_id: "browser-f2c-trace",
      correlation_id: "browser-f2c",
      ...(page ?? {}),
    },
  });
}

test("tenant admin searches, pages, inspects, updates, and invites users", async ({
  page,
  context,
}) => {
  let accessToken = "";
  let targetUser = {
    id: "f2000000-0000-4000-8000-000000000010",
    email: "deniz@wealthyfalcon.demo",
    full_name: "Deniz Yılmaz",
    status: "active",
    roles: [employeeRole],
    permission_version: 1,
    ...timestamps,
  };
  const invitedUser = {
    id: "f2000000-0000-4000-8000-000000000011",
    email: "elif@wealthyfalcon.demo",
    full_name: "Elif Şahin",
    status: "invited",
    roles: [employeeRole],
    permission_version: 1,
    ...timestamps,
  };
  const secondPageUser = {
    id: "f2000000-0000-4000-8000-000000000012",
    email: "arda@wealthyfalcon.demo",
    full_name: "Arda Demir",
    status: "disabled",
    roles: [employeeRole],
    permission_version: 2,
    ...timestamps,
  };
  const listQueries: URLSearchParams[] = [];
  const patches: unknown[] = [];
  const invitations: unknown[] = [];
  const roleReplacements: unknown[] = [];

  await context.addCookies([
    {
      name: "wf_refresh",
      value: "browser-refresh",
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
      accessToken = "users-screen-access";
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

    if (path === "/api/v1/roles") {
      expect(request.method()).toBe("GET");
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: envelope(roleCatalog),
      });
      return;
    }

    if (path === "/api/v1/users/invitations") {
      expect(request.method()).toBe("POST");
      const payload = request.postDataJSON();
      invitations.push(payload);
      await route.fulfill({
        status: 201,
        contentType: "application/json",
        body: envelope({
          user: {
            id: "f2000000-0000-4000-8000-000000000013",
            email: payload.email,
            full_name: payload.full_name,
            status: "invited",
          },
          activation_url: "http://127.0.0.1:3100/activate#token=safe-browser-token",
          expires_at: "2026-07-13T10:00:00Z",
        }),
      });
      return;
    }

    if (path === `/api/v1/users/${targetUser.id}` && request.method() === "PATCH") {
      const payload = request.postDataJSON();
      patches.push(payload);
      targetUser = {
        ...targetUser,
        ...payload,
        updated_at: "2026-07-12T12:00:00Z",
      };
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: envelope(targetUser),
      });
      return;
    }

    if (
      path === `/api/v1/users/${targetUser.id}/roles` &&
      request.method() === "PUT"
    ) {
      const payload = request.postDataJSON();
      roleReplacements.push(payload);
      const selectedRoles = roleCatalog
        .filter((role) => role.scope_type === "tenant" && payload.role_ids.includes(role.id))
        .map(({ id, code, name, scope_type }) => ({ id, code, name, scope_type }));
      targetUser = {
        ...targetUser,
        roles: selectedRoles,
        permission_version: targetUser.permission_version + 1,
        updated_at: "2026-07-12T12:30:00Z",
      };
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: envelope(targetUser),
      });
      return;
    }

    if (path === `/api/v1/users/${targetUser.id}`) {
      expect(request.method()).toBe("GET");
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: envelope(targetUser),
      });
      return;
    }

    if (path === "/api/v1/users") {
      expect(request.method()).toBe("GET");
      listQueries.push(new URLSearchParams(url.searchParams));
      const cursor = url.searchParams.get("cursor");
      const search = (url.searchParams.get("search") ?? "").toLocaleLowerCase("tr-TR");
      const status = url.searchParams.get("status");
      let users = cursor ? [secondPageUser] : [targetUser, invitedUser];
      if (search) {
        users = users.filter((user) =>
          `${user.full_name} ${user.email}`.toLocaleLowerCase("tr-TR").includes(search),
        );
      }
      if (status) {
        users = users.filter((user) => user.status === status);
      }
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: envelope(users, {
          limit: 25,
          next_cursor: !cursor && !search && !status ? "users-page-2" : null,
        }),
      });
      return;
    }

    await route.fulfill({ status: 404 });
  });

  await page.goto("/users");

  await expect(page.getByRole("heading", { name: "Kullanıcılar", exact: true })).toBeVisible();
  await expect(page.getByText("Deniz Yılmaz").first()).toBeVisible();
  await page.getByRole("button", { name: "Sonraki" }).click();
  await expect(page.getByText("Arda Demir")).toBeVisible();
  expect(listQueries.at(-1)?.get("cursor")).toBe("users-page-2");

  await page.getByRole("button", { name: "Önceki" }).click();
  await page.getByLabel("Kullanıcı ara").fill("deniz");
  await page.getByLabel("Durum").selectOption("active");
  await page.getByRole("button", { name: "Filtrele" }).click();
  await expect(page.getByText("Deniz Yılmaz").first()).toBeVisible();
  expect(listQueries.at(-1)?.get("search")).toBe("deniz");
  expect(listQueries.at(-1)?.get("status")).toBe("active");
  expect(listQueries.at(-1)?.get("limit")).toBe("25");

  await page.getByRole("button", { name: "Deniz Yılmaz kullanıcısını incele" }).click();
  await expect(page.getByRole("dialog", { name: "Deniz Yılmaz" })).toBeVisible();
  await page.getByLabel("Ad soyad").fill("Deniz Kaya");
  await page.getByLabel("Hesap durumu").selectOption("locked");
  await page.getByRole("button", { name: "Değişiklikleri kaydet" }).click();
  await expect(page.getByText("Kullanıcı bilgileri güncellendi.")).toBeVisible();
  expect(patches).toEqual([{ full_name: "Deniz Kaya", status: "locked" }]);
  expect(JSON.stringify(patches)).not.toContain("tenant_id");
  expect(JSON.stringify(patches)).not.toContain("actor");

  await expect(page.getByRole("checkbox", { name: /İK uzmanı/ })).toBeVisible();
  await expect(page.getByRole("checkbox", { name: /Süper yönetici/ })).toHaveCount(0);
  await page.getByRole("checkbox", { name: /İK uzmanı/ }).check();
  await page.getByRole("button", { name: "Rolleri kaydet" }).click();
  await expect(page.getByText("Kullanıcı rolleri güncellendi.")).toBeVisible();
  expect(roleReplacements).toEqual([
    { role_ids: [employeeRole.id, hrSpecialistRole.id] },
  ]);
  expect(JSON.stringify(roleReplacements)).not.toContain("tenant_id");
  expect(JSON.stringify(roleReplacements)).not.toContain("actor");
  await expect(page.getByLabel("Roller: Çalışan, İK uzmanı")).toBeVisible();
  await page.getByRole("button", { name: "Kullanıcı ayrıntısını kapat" }).click();

  await page.getByRole("button", { name: "Kullanıcı davet et" }).first().click();
  await page.getByLabel("Ad soyad").fill("Selin Ak");
  await page.getByLabel("İş e-postası").fill("selin@wealthyfalcon.demo");
  await page.getByRole("button", { name: "Davet gönder" }).click();
  await expect(page.getByRole("heading", { name: "Davet hazır" })).toBeVisible();
  await expect(page.getByLabel("Etkinleştirme bağlantısı")).toHaveValue(
    /activate#token=safe-browser-token/,
  );
  expect(invitations).toEqual([
    { email: "selin@wealthyfalcon.demo", full_name: "Selin Ak" },
  ]);
  expect(JSON.stringify(invitations)).not.toContain("tenant_id");
  expect(JSON.stringify(invitations)).not.toContain("actor");

  await page.getByRole("button", { name: "Tamam" }).click();
  await page.setViewportSize({ width: 390, height: 844 });
  const mobileNavigation = page.getByRole("navigation", { name: "Mobil ana menü" });
  await expect(mobileNavigation).toBeVisible();
  await expect(mobileNavigation.getByRole("link", { name: "Kullanıcılar" })).toHaveAttribute(
    "aria-current",
    "page",
  );
  await expect(page.getByRole("heading", { name: "Kullanıcılar", exact: true })).toBeVisible();
  expect(
    await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth),
  ).toBe(true);
});
