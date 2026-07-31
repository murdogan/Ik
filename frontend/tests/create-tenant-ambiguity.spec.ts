import {
  expect,
  test,
  type Request as PlaywrightRequest,
  type Route,
} from "@playwright/test";

const PLATFORM_ACCESS_TOKEN = "platform-create-ambiguity-access";
const MATCHED_TENANT_ID = "10000000-0000-4000-8000-000000000098";

function responseMeta(correlationId: string) {
  return {
    request_id: `${correlationId}-request`,
    trace_id: `${correlationId}-trace`,
    correlation_id: correlationId,
  };
}

function envelope(
  data: unknown,
  meta: Record<string, unknown> = responseMeta("create-ambiguity"),
) {
  return JSON.stringify({ data, meta });
}

function tenantListEnvelope(data: unknown[]) {
  return envelope(data, {
    ...responseMeta("create-ambiguity-list"),
    limit: 200,
    next_cursor: null,
  });
}

function expectPlatformBearer(request: PlaywrightRequest) {
  expect(request.headers().authorization).toBe(
    `Bearer ${PLATFORM_ACCESS_TOKEN}`,
  );
  expect(request.headers()["x-tenant-id"]).toBeUndefined();
  expect(request.headers()["x-tenant-slug"]).toBeUndefined();
}

test("an exact slug match after an ambiguous create remains locked for manual verification", async ({
  context,
  page,
}) => {
  const platformCreator = {
    id: "f2000000-0000-4000-8000-000000000098",
    email: "platform@example.test",
    full_name: "Platform Creator",
    workspace_scope: "platform",
    roles: [
      {
        id: "f3000000-0000-4000-8000-000000000098",
        code: "tenant_creator",
        name: "Tenant creator",
        scope_type: "platform",
      },
    ],
    permissions: ["tenant:read:platform", "tenant:create:platform"],
    permission_version: 1,
    authentication_strength: "multi_factor",
  };
  const possibleTenant = {
    id: MATCHED_TENANT_ID,
    slug: "belirsiz-yeni-tenant",
    name: "Listede Bulunan Tenant",
    status: "provisioning",
    plan_code: "core",
    data_region: "tr-1",
    locale: "tr-TR",
    timezone: "Europe/Istanbul",
    health: "provisioning",
    limits: { active_employees: null },
    created_at: "2026-07-29T08:00:00Z",
    updated_at: "2026-07-29T08:00:00Z",
  };
  let createRequests = 0;
  let listRequests = 0;

  await context.addCookies([
    {
      name: "wf_platform_refresh",
      value: "platform-create-ambiguity-refresh",
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
          user: platformCreator,
        }),
      });
      return;
    }

    expectPlatformBearer(request);
    if (path === "/api/v1/platform/me") {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: envelope({ user: platformCreator }),
      });
      return;
    }

    if (path === "/api/v1/platform/tenants" && request.method() === "GET") {
      listRequests += 1;
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: tenantListEnvelope(listRequests === 1 ? [] : [possibleTenant]),
      });
      return;
    }

    if (path === "/api/v1/platform/tenants" && request.method() === "POST") {
      createRequests += 1;
      await route.fulfill({
        status: 201,
        contentType: "application/json",
        body: envelope({ malformed: true }, responseMeta("ambiguous-create")),
      });
      return;
    }

    await route.fulfill({ status: 404 });
  });

  await page.goto("/platform/tenants");
  await page.getByRole("button", { name: "Yeni tenant oluştur" }).click();
  const dialog = page.getByRole("dialog", { name: "Yeni tenant oluştur" });
  await dialog.getByLabel("Tenant adı").fill("Belirsiz Yeni Tenant");
  await dialog.getByLabel("Tenant kodu").fill("belirsiz-yeni-tenant");
  await dialog.getByLabel("İlk yönetici tam adı").fill("Gizli Yönetici");
  await dialog
    .getByLabel("İlk yönetici e-posta adresi")
    .fill("gizli.yonetici@example.test");
  await dialog.getByRole("button", { name: "Tenant oluştur" }).click();

  await expect(dialog).toBeVisible();
  const alert = dialog.getByRole("alert");
  await expect(alert).toContainText("bu isteğin sonucu olduğunu kanıtlamaz");
  await expect(alert).toContainText("Listede Bulunan Tenant");
  await expect(alert).toContainText("belirsiz-yeni-tenant");
  await expect(dialog.getByLabel("Tenant adı")).toHaveValue(
    "Belirsiz Yeni Tenant",
  );
  await expect(dialog.getByLabel("Tenant adı")).toBeDisabled();
  await expect(dialog.getByLabel("Tenant kodu")).toHaveValue(
    "belirsiz-yeni-tenant",
  );
  await expect(dialog.getByLabel("Tenant kodu")).toBeDisabled();
  await expect(dialog.getByLabel("İlk yönetici tam adı")).toHaveValue(
    "Gizli Yönetici",
  );
  await expect(
    dialog.getByLabel("İlk yönetici e-posta adresi"),
  ).toHaveValue("gizli.yonetici@example.test");
  await expect(
    dialog.getByRole("button", { name: "Tenant oluştur" }),
  ).toBeDisabled();
  const verificationLink = dialog.getByRole("link", {
    name: "Bulunan tenantı yeni sekmede incele",
  });
  await expect(verificationLink).toHaveAttribute(
    "href",
    `/platform/tenants/${MATCHED_TENANT_ID}`,
  );
  await expect(verificationLink).toHaveAttribute("target", "_blank");
  await expect(verificationLink).toHaveAttribute(
    "rel",
    "noopener noreferrer",
  );
  await expect(
    page.getByText("Listede Bulunan Tenant oluşturuldu", { exact: true }),
  ).toHaveCount(0);

  const requestsBeforeStaleSubmit = createRequests;
  await dialog.locator("form").evaluate((form) => {
    form.dispatchEvent(new Event("submit", { bubbles: true, cancelable: true }));
  });
  await expect.poll(() => createRequests).toBe(requestsBeforeStaleSubmit);
  expect(createRequests).toBe(1);
  expect(listRequests).toBe(2);
});
