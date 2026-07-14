import { expect, test, type Page, type Route } from "@playwright/test";

const DIRECT_EMPLOYEE_ID = "d4000000-0000-4000-8000-000000000001";
const UNRELATED_EMPLOYEE_ID = "d4000000-0000-4000-8000-000000000099";
const MISMATCH_ROUTE_EMPLOYEE_ID = "d4000000-0000-4000-8000-000000000098";
const WRONG_RESPONSE_EMPLOYEE_ID = "d4000000-0000-4000-8000-000000000097";

function deferred() {
  let release!: () => void;
  const wait = new Promise<void>((resolve) => {
    release = resolve;
  });
  return { wait, release };
}

async function flushClient(page: Page): Promise<void> {
  await page.evaluate(
    () =>
      new Promise<void>((resolve) => {
        requestAnimationFrame(() => requestAnimationFrame(() => resolve()));
      }),
  );
}

function envelope(
  data: unknown,
  page?: { limit: number; next_cursor: string | null },
): string {
  return JSON.stringify({
    data,
    meta: {
      request_id: "browser-p4d",
      trace_id: "browser-p4d-trace",
      correlation_id: "browser-p4d",
      ...(page ?? {}),
    },
  });
}

function errorEnvelope(code: string): string {
  return JSON.stringify({
    error: {
      code,
      message: "Request failed",
      details: null,
      correlation_id: "browser-p4d",
    },
  });
}

const tenant = {
  slug: "wealthy-falcon-demo",
  name: "Wealthy Falcon HR Demo",
};

const hrUser = {
  id: "d4100000-0000-4000-8000-000000000001",
  membership_id: "d4200000-0000-4000-8000-000000000001",
  tenant_id: "d4300000-0000-4000-8000-000000000001",
  email: "hr@wealthyfalcon.demo",
  full_name: "Derya İnsan",
  tenant,
  workspace_scope: "tenant",
  roles: [
    {
      id: "d4400000-0000-4000-8000-000000000001",
      code: "hr_specialist",
      name: "İK uzmanı",
      scope_type: "tenant",
    },
  ],
  permissions: ["dashboard:read:own", "employee:read:tenant"],
  permission_version: 4,
};

const managerUser = {
  ...hrUser,
  id: "d4100000-0000-4000-8000-000000000002",
  membership_id: "d4200000-0000-4000-8000-000000000002",
  email: "manager@wealthyfalcon.demo",
  full_name: "Mert Yönetici",
  roles: [
    {
      id: "d4400000-0000-4000-8000-000000000002",
      code: "manager",
      name: "Yönetici",
      scope_type: "tenant",
    },
  ],
  permissions: ["dashboard:read:own", "employee:read:team"],
  permission_version: 6,
};

const rotatedManagerUser = {
  ...managerUser,
  id: "d4100000-0000-4000-8000-000000000003",
  membership_id: "d4200000-0000-4000-8000-000000000003",
  email: "manager.two@wealthyfalcon.demo",
  full_name: "Selin Yönetici",
  permission_version: 7,
};

const employeeUser = {
  ...hrUser,
  id: "d4100000-0000-4000-8000-000000000004",
  membership_id: "d4200000-0000-4000-8000-000000000004",
  email: "ada.account@wealthyfalcon.demo",
  full_name: "Ada Çalışan",
  roles: [
    {
      id: "d4400000-0000-4000-8000-000000000004",
      code: "employee",
      name: "Çalışan",
      scope_type: "tenant",
    },
  ],
  permissions: ["dashboard:read:own", "employee:read:own"],
  permission_version: 3,
};

const hrProfile = {
  core: {
    id: DIRECT_EMPLOYEE_ID,
    employee_number: "WF-0042",
    first_name: "Ece",
    last_name: "Çalışkan",
    email: "ece@wealthyfalcon.demo",
    status: "active",
    employee_version: 5,
  },
  personal: {
    preferred_name: "Ece",
    birth_date: "1992-04-10",
    phone: "+905551110000",
    version: 2,
  },
  employment: {
    employment_start_date: "2025-02-03",
    contract_type: "indefinite",
    work_type: "full_time",
    version: 7,
  },
  organization: {
    current_assignment: null,
    history: [],
    history_limit: 50,
    history_truncated: false,
  },
};

const teamMember = {
  employee: {
    id: DIRECT_EMPLOYEE_ID,
    employee_number: "WF-0042",
    first_name: "Ece",
    last_name: "Çalışkan",
    preferred_name: "Ece",
    email: "ece@wealthyfalcon.demo",
    status: "active",
  },
  assignment: {
    legal_entity: { code: "WF-TR", name: "Wealthy Falcon Türkiye" },
    branch: { code: "IST", name: "İstanbul" },
    department: { code: "ENG", name: "Mühendislik" },
    position: { code: "SWE", title: "Yazılım Mühendisi" },
    effective_from: "2026-01-05",
  },
};

function managerProfile({
  employeeId = DIRECT_EMPLOYEE_ID,
  firstName = "Ece",
  lastName = "Çalışkan",
  managerName = "Mert Yönetici",
}: {
  employeeId?: string;
  firstName?: string;
  lastName?: string;
  managerName?: string;
} = {}) {
  return {
    core: {
      id: employeeId,
      employee_number: "WF-0042",
      first_name: firstName,
      last_name: lastName,
      preferred_name: firstName,
      email: "ece@wealthyfalcon.demo",
      status: "active",
    },
    employment: {
      employment_start_date: "2025-02-03",
      contract_type: "indefinite",
      work_type: "full_time",
    },
    organization: {
      current_assignment: {
        legal_entity: { code: "WF-TR", name: "Wealthy Falcon Türkiye" },
        branch: { code: "IST", name: "İstanbul" },
        department: { code: "ENG", name: "Mühendislik" },
        position: { code: "SWE", title: "Yazılım Mühendisi" },
        manager: { full_name: managerName },
        effective_from: "2026-01-05",
      },
    },
  };
}

const ownProfile = {
  core: {
    id: DIRECT_EMPLOYEE_ID,
    employee_number: "WF-0042",
    first_name: "Ece",
    last_name: "Çalışkan",
    email: "ece@wealthyfalcon.demo",
    status: "active",
  },
  personal: {
    preferred_name: "Ece",
    birth_date: {
      visibility: "masked",
      display_value: "••••-04-10",
    },
    phone: {
      visibility: "unavailable",
      display_value: null,
    },
  },
  employment: {
    employment_start_date: "2025-02-03",
    contract_type: "indefinite",
    work_type: "full_time",
  },
  organization: {
    current_assignment: {
      legal_entity: { code: "WF-TR", name: "Wealthy Falcon Türkiye" },
      branch: { code: "IST", name: "İstanbul" },
      department: { code: "ENG", name: "Mühendislik" },
      position: { code: "SWE", title: "Yazılım Mühendisi" },
      manager: { full_name: "Mert Yönetici" },
    },
  },
};

test("HR, manager and employee stay inside their backend field projections", async ({
  context,
  page,
}) => {
  const staleTeamProfileGate = deferred();
  let activeUser = hrUser;
  let nextUser: typeof hrUser | null = null;
  let accessToken = "";
  let refreshCount = 0;
  let hrProfileRequests = 0;
  let teamListRequests = 0;
  let legacyTeamListRequests = 0;
  let teamListRequestsWithoutPermission = 0;
  let managerProfileRequests = 0;
  let employeeManagerProfileRequests = 0;
  let nonHrEmployeeProfileRequests = 0;
  let ownProfileRequests = 0;
  let managerOwnProfileRequests = 0;
  let deferNextTeamProfile = false;
  let staleTeamProfileRequests = 0;
  let staleTeamProfileToken = "";
  let ownProfileResponseMode:
    | "membership_mismatch"
    | "employee_mismatch"
    | "valid" = "membership_mismatch";
  const ownProfileResponses = {
    membership_mismatch: 0,
    employee_mismatch: 0,
    valid: 0,
  };
  const ownRequestUrls: string[] = [];

  await context.addCookies([
    {
      name: "wf_refresh",
      value: "p4d-browser-refresh",
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
      refreshCount += 1;
      if (nextUser) {
        activeUser = nextUser;
        nextUser = null;
      }
      accessToken = `p4d-access-${refreshCount}`;
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: envelope({
          access_token: accessToken,
          token_type: "bearer",
          expires_in: 900,
          user: activeUser,
        }),
      });
      return;
    }

    expect(request.headers().authorization).toBe(`Bearer ${accessToken}`);

    if (path === "/api/v1/me") {
      if (nextUser) {
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
        body: envelope({ user: activeUser }),
      });
      return;
    }

    if (
      path === `/api/v1/employees/${DIRECT_EMPLOYEE_ID}/profile` &&
      request.method() === "GET"
    ) {
      if (activeUser.membership_id !== hrUser.membership_id) {
        nonHrEmployeeProfileRequests += 1;
        await route.fulfill({
          status: 403,
          contentType: "application/json",
          body: errorEnvelope("authorization_denied"),
        });
        return;
      }
      hrProfileRequests += 1;
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: envelope(hrProfile),
      });
      return;
    }

    if (path === "/api/v1/teams/me") {
      legacyTeamListRequests += 1;
      await route.fulfill({
        status: 403,
        contentType: "application/json",
        body: errorEnvelope("authorization_denied"),
      });
      return;
    }

    if (path === "/api/v1/teams/me/members") {
      if (!activeUser.permissions.includes("employee:read:team")) {
        teamListRequestsWithoutPermission += 1;
        await route.fulfill({
          status: 403,
          contentType: "application/json",
          body: errorEnvelope("authorization_denied"),
        });
        return;
      }
      teamListRequests += 1;
      expect(url.searchParams.get("limit")).toBe("50");
      expect(url.searchParams.get("cursor")).toBeNull();
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: envelope([teamMember], { limit: 50, next_cursor: null }),
      });
      return;
    }

    const teamProfilePrefix = "/api/v1/teams/me/members/";
    if (path.startsWith(teamProfilePrefix) && path.endsWith("/profile")) {
      managerProfileRequests += 1;
      const requestMembershipId = activeUser.membership_id;
      if (requestMembershipId === employeeUser.membership_id) {
        employeeManagerProfileRequests += 1;
      }

      if (
        path ===
        `/api/v1/teams/me/members/${DIRECT_EMPLOYEE_ID}/profile`
      ) {
        if (
          deferNextTeamProfile &&
          requestMembershipId === managerUser.membership_id
        ) {
          deferNextTeamProfile = false;
          staleTeamProfileRequests += 1;
          staleTeamProfileToken = request.headers().authorization ?? "";
          await staleTeamProfileGate.wait;
          await route.fulfill({
            status: 200,
            contentType: "application/json",
            body: envelope(
              managerProfile({
                firstName: "Eski",
                lastName: "Oturum",
              }),
            ),
          });
          return;
        }
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: envelope(
            requestMembershipId === rotatedManagerUser.membership_id
              ? managerProfile({
                  firstName: "Bora",
                  lastName: "Güncel",
                  managerName: "Selin Yönetici",
                })
              : managerProfile(),
          ),
        });
        return;
      }

      if (
        path ===
        `/api/v1/teams/me/members/${MISMATCH_ROUTE_EMPLOYEE_ID}/profile`
      ) {
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: envelope(
            managerProfile({
              employeeId: WRONG_RESPONSE_EMPLOYEE_ID,
              firstName: "Yanlış",
              lastName: "Çalışan",
            }),
          ),
        });
        return;
      }

      await route.fulfill({
        status: 404,
        contentType: "application/json",
        body: errorEnvelope("team_member_not_found"),
      });
      return;
    }

    if (path === "/api/v1/me/employee-profile") {
      ownProfileRequests += 1;
      ownRequestUrls.push(request.url());
      if (activeUser.membership_id !== employeeUser.membership_id) {
        managerOwnProfileRequests += 1;
        await route.fulfill({
          status: 403,
          contentType: "application/json",
          body: errorEnvelope("authorization_denied"),
        });
        return;
      }
      const responseMode = ownProfileResponseMode;
      ownProfileResponses[responseMode] += 1;
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: envelope({
          availability: "available",
          membership_id:
            responseMode === "membership_mismatch"
              ? managerUser.membership_id
              : employeeUser.membership_id,
          employee_id:
            responseMode === "employee_mismatch"
              ? WRONG_RESPONSE_EMPLOYEE_ID
              : DIRECT_EMPLOYEE_ID,
          profile: ownProfile,
        }),
      });
      return;
    }

    if (path.startsWith("/api/v1/employees")) {
      if (activeUser.membership_id !== hrUser.membership_id) {
        nonHrEmployeeProfileRequests += 1;
      }
      await route.fulfill({
        status: 403,
        contentType: "application/json",
        body: errorEnvelope("authorization_denied"),
      });
      return;
    }

    await route.fulfill({
      status: 404,
      contentType: "application/json",
      body: errorEnvelope("not_found"),
    });
  });

  await page.goto(`/employees/${DIRECT_EMPLOYEE_ID}`);
  await expect(
    page.getByRole("heading", { level: 1, name: "Ece Çalışkan", exact: true }),
  ).toBeVisible();
  await page.getByRole("tab", { name: "Kişisel", exact: true }).click();
  const hrPersonalPanel = page.getByRole("tabpanel", { name: "Kişisel" });
  await expect(hrPersonalPanel.getByText("+905551110000", { exact: true })).toBeVisible();
  await expect(hrPersonalPanel.getByText("10 Nis 1992", { exact: true })).toBeVisible();
  expect(hrProfileRequests).toBeGreaterThan(0);
  expect(managerProfileRequests).toBe(0);
  expect(ownProfileRequests).toBe(0);

  nextUser = managerUser;
  await page.evaluate(() => window.dispatchEvent(new Event("focus")));
  await expect(page).toHaveURL(/\/dashboard$/);
  const firstTeam = page.getByRole("article", { name: "Ekibim" });
  await expect(firstTeam.getByText("Ece Çalışkan", { exact: true })).toBeVisible();
  await expect(firstTeam.getByText("Yazılım Mühendisi", { exact: true })).toBeVisible();
  await firstTeam
    .getByRole("link", { name: "Ece Çalışkan güvenli ekip profilini aç" })
    .click();

  await expect(page).toHaveURL(new RegExp(`/team/${DIRECT_EMPLOYEE_ID}$`));
  await expect(
    page.getByRole("heading", { level: 1, name: "Ece Çalışkan", exact: true }),
  ).toBeVisible();
  await expect(page.getByText("Mühendislik", { exact: true })).toBeVisible();
  await expect(page.getByText("Yazılım Mühendisi", { exact: true })).toBeVisible();
  await expect(page.getByText("Telefon", { exact: true })).toHaveCount(0);
  await expect(page.getByText("Doğum tarihi", { exact: true })).toHaveCount(0);
  await expect(page.getByText("+905551110000", { exact: true })).toHaveCount(0);
  await expect(page.getByText("10 Nis 1992", { exact: true })).toHaveCount(0);
  expect(teamListRequests).toBeGreaterThan(0);
  expect(managerProfileRequests).toBeGreaterThan(0);
  expect(nonHrEmployeeProfileRequests).toBe(0);
  expect(managerOwnProfileRequests).toBe(0);

  await page.getByRole("link", { name: "Ekibime dön" }).click();
  await expect(page).toHaveURL(/\/dashboard#manager-team-title$/);
  const refreshedTeam = page.getByRole("article", { name: "Ekibim" });
  await expect(
    refreshedTeam.getByRole("link", {
      name: "Ece Çalışkan güvenli ekip profilini aç",
    }),
  ).toBeVisible();
  deferNextTeamProfile = true;
  await refreshedTeam
    .getByRole("link", { name: "Ece Çalışkan güvenli ekip profilini aç" })
    .click();
  await expect.poll(() => staleTeamProfileRequests).toBe(1);

  nextUser = rotatedManagerUser;
  await page.evaluate(() => window.dispatchEvent(new Event("focus")));
  await expect(
    page.getByRole("heading", { level: 1, name: "Bora Güncel", exact: true }),
  ).toBeVisible();
  await expect(page.getByText("Selin Yönetici", { exact: true }).last()).toBeVisible();

  const staleResponse = page.waitForResponse(
    (response) =>
      new URL(response.url()).pathname ===
        `/api/v1/teams/me/members/${DIRECT_EMPLOYEE_ID}/profile` &&
      response.request().headers().authorization === staleTeamProfileToken,
  );
  staleTeamProfileGate.release();
  await staleResponse;
  await flushClient(page);
  await expect(
    page.getByRole("heading", { level: 1, name: "Bora Güncel", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("heading", { level: 1, name: "Eski Oturum", exact: true }),
  ).toHaveCount(0);

  const beforeUnrelated = managerProfileRequests;
  await page.goto(`/team/${UNRELATED_EMPLOYEE_ID}`);
  await expect(
    page.getByRole("alert").filter({ hasText: "Ekip profili yüklenemedi" }),
  ).toContainText("Bu ekip üyesi profili kullanılamıyor");
  await expect(page.getByText("Bora Güncel", { exact: true })).toHaveCount(0);
  await expect(page.getByText("Mühendislik", { exact: true })).toHaveCount(0);
  await expect(page.getByText(UNRELATED_EMPLOYEE_ID)).toHaveCount(0);
  expect(managerProfileRequests).toBeGreaterThan(beforeUnrelated);

  const beforeMismatch = managerProfileRequests;
  await page.goto(`/team/${MISMATCH_ROUTE_EMPLOYEE_ID}`);
  await expect(
    page.getByRole("alert").filter({ hasText: "Ekip profili yüklenemedi" }),
  ).toContainText("Ekip üyesi profili şu anda yüklenemiyor");
  await expect(
    page.getByRole("heading", { level: 1, name: "Yanlış Çalışan", exact: true }),
  ).toHaveCount(0);
  await expect(page.getByText(WRONG_RESPONSE_EMPLOYEE_ID)).toHaveCount(0);
  expect(managerProfileRequests).toBeGreaterThan(beforeMismatch);

  nextUser = employeeUser;
  await page.evaluate(() => window.dispatchEvent(new Event("focus")));
  await expect(page).toHaveURL(/\/dashboard$/);
  await expect(
    page.getByRole("heading", { name: "Merhaba, Ada Çalışan" }),
  ).toBeVisible();
  const managerRequestsBeforeEmployeeDirect = managerProfileRequests;
  await page.goto(`/team/${DIRECT_EMPLOYEE_ID}`);
  await expect(page).toHaveURL(/\/dashboard$/);
  await expect(page.getByRole("article", { name: "Ekibim" })).toHaveCount(0);
  expect(managerProfileRequests).toBe(managerRequestsBeforeEmployeeDirect);
  expect(employeeManagerProfileRequests).toBe(0);
  expect(teamListRequestsWithoutPermission).toBe(0);

  const ownRequestsBeforeProfile = ownProfileRequests;
  await page.goto(`/profile?employee_id=${UNRELATED_EMPLOYEE_ID}`);
  await expect(page).toHaveURL(
    new RegExp(`/profile\\?employee_id=${UNRELATED_EMPLOYEE_ID}$`),
  );
  await expect
    .poll(() => ownProfileResponses.membership_mismatch)
    .toBeGreaterThan(0);
  await expect(
    page.getByRole("heading", { name: "Profiliniz yüklenemedi" }),
  ).toBeVisible();
  await expect(page.getByText("Ece Çalışkan", { exact: true })).toHaveCount(0);

  const ownRequestsBeforeEmployeeMismatch = ownProfileRequests;
  ownProfileResponseMode = "employee_mismatch";
  await page.getByRole("button", { name: "Yeniden dene" }).click();
  await expect
    .poll(() => ownProfileRequests)
    .toBeGreaterThan(ownRequestsBeforeEmployeeMismatch);
  await expect.poll(() => ownProfileResponses.employee_mismatch).toBeGreaterThan(0);
  await flushClient(page);
  await expect(
    page.getByRole("heading", { name: "Profiliniz yüklenemedi" }),
  ).toBeVisible();
  await expect(page.getByText("Ece Çalışkan", { exact: true })).toHaveCount(0);

  const ownRequestsBeforeValid = ownProfileRequests;
  ownProfileResponseMode = "valid";
  await page.getByRole("button", { name: "Yeniden dene" }).click();
  await expect.poll(() => ownProfileRequests).toBeGreaterThan(ownRequestsBeforeValid);
  await expect.poll(() => ownProfileResponses.valid).toBeGreaterThan(0);
  await expect(page.getByRole("heading", { level: 1, name: "Profilim" })).toBeVisible();
  await expect(page.getByText("••••-04-10", { exact: true })).toBeVisible();
  await expect(page.getByText("Maskeli", { exact: true })).toBeVisible();
  await expect(page.getByText("Görüntülenemiyor", { exact: true })).toBeVisible();
  await expect(page.getByText("Kullanılamıyor", { exact: true })).toBeVisible();
  await expect(page.getByRole("note")).toContainText(
    "ayrıntıları açma özelliği bulunmaz",
  );
  await expect(page.getByText("+905551110000", { exact: true })).toHaveCount(0);
  await expect(page.getByText("1992-04-10", { exact: true })).toHaveCount(0);
  await expect(page.getByText(UNRELATED_EMPLOYEE_ID)).toHaveCount(0);
  await expect(
    page.getByRole("button", {
      name: /ayrıntıları (göster|aç)|maskeyi kaldır|reveal|unmask/i,
    }),
  ).toHaveCount(0);

  expect(ownProfileRequests).toBeGreaterThan(0);
  expect(nonHrEmployeeProfileRequests).toBe(0);
  expect(managerOwnProfileRequests).toBe(0);
  expect(managerProfileRequests).toBe(managerRequestsBeforeEmployeeDirect);
  expect(legacyTeamListRequests).toBe(0);
  expect(ownProfileRequests).toBeGreaterThan(ownRequestsBeforeProfile);
  expect(
    ownRequestUrls.every((requestUrl) => {
      const ownUrl = new URL(requestUrl);
      return ownUrl.pathname === "/api/v1/me/employee-profile" && ownUrl.search === "";
    }),
  ).toBe(true);
});
