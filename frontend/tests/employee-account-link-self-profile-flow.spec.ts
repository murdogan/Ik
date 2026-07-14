import { expect, test, type Page, type Route } from "@playwright/test";

const EMPLOYEE_ID = "fc000000-0000-4000-8000-000000000001";
const GUESSED_EMPLOYEE_ID = "fc000000-0000-4000-8000-000000000099";
const HR_MEMBERSHIP_ID = "fc100000-0000-4000-8000-000000000001";
const LINKED_MEMBERSHIP_ID = "fc100000-0000-4000-8000-000000000002";
const UNLINKED_MEMBERSHIP_ID = "fc100000-0000-4000-8000-000000000003";
const UNAUTHORIZED_MEMBERSHIP_ID = "fc100000-0000-4000-8000-000000000004";

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

function envelope(data: unknown): string {
  return JSON.stringify({
    data,
    meta: {
      request_id: "browser-p4c",
      trace_id: "browser-p4c-trace",
      correlation_id: "browser-p4c",
    },
  });
}

function errorEnvelope(code: string): string {
  return JSON.stringify({
    error: {
      code,
      message: "Request failed",
      details: null,
      correlation_id: "browser-p4c",
    },
  });
}

const tenant = {
  slug: "wealthy-falcon-demo",
  name: "Wealthy Falcon HR Demo",
};

const hrUser = {
  id: "fc200000-0000-4000-8000-000000000001",
  membership_id: HR_MEMBERSHIP_ID,
  tenant_id: "fc300000-0000-4000-8000-000000000001",
  email: "hr@wealthyfalcon.demo",
  full_name: "Derya İnsan",
  tenant,
  workspace_scope: "tenant",
  roles: [
    {
      id: "fc400000-0000-4000-8000-000000000001",
      code: "hr_specialist",
      name: "İK uzmanı",
      scope_type: "tenant",
    },
  ],
  permissions: [
    "dashboard:read:own",
    "employee:read:own",
    "employee:read:tenant",
    "employee:update:tenant",
  ],
  permission_version: 4,
};

const linkedEmployeeUser = {
  id: "fc200000-0000-4000-8000-000000000002",
  membership_id: LINKED_MEMBERSHIP_ID,
  tenant_id: hrUser.tenant_id,
  email: "ada.account@wealthyfalcon.demo",
  full_name: "Ada Hesap",
  tenant,
  workspace_scope: "tenant",
  roles: [
    {
      id: "fc400000-0000-4000-8000-000000000002",
      code: "employee",
      name: "Çalışan",
      scope_type: "tenant",
    },
  ],
  permissions: ["dashboard:read:own", "employee:read:own"],
  permission_version: 2,
};

const unlinkedEmployeeUser = {
  ...linkedEmployeeUser,
  id: "fc200000-0000-4000-8000-000000000003",
  membership_id: UNLINKED_MEMBERSHIP_ID,
  email: "ece.account@wealthyfalcon.demo",
  full_name: "Ece Çalışkan",
  permission_version: 3,
};

const unauthorizedUser = {
  ...linkedEmployeeUser,
  id: "fc200000-0000-4000-8000-000000000004",
  membership_id: UNAUTHORIZED_MEMBERSHIP_ID,
  email: "it@wealthyfalcon.demo",
  full_name: "İpek Teknik",
  roles: [
    {
      id: "fc400000-0000-4000-8000-000000000004",
      code: "it_admin",
      name: "BT yöneticisi",
      scope_type: "tenant",
    },
  ],
  permissions: ["dashboard:read:own", "user:read:tenant"],
  permission_version: 5,
};

const employeeReadOnlyUser = {
  ...hrUser,
  id: "fc200000-0000-4000-8000-000000000005",
  membership_id: "fc300000-0000-4000-8000-000000000005",
  email: "auditor@wealthyfalcon.demo",
  full_name: "Aylin Denetçi",
  roles: [
    {
      id: "fc400000-0000-4000-8000-000000000005",
      code: "auditor",
      name: "Denetçi",
      scope_type: "tenant",
    },
  ],
  permissions: ["dashboard:read:own", "employee:read:tenant"],
  permission_version: 6,
};

const employee360Profile = {
  core: {
    id: EMPLOYEE_ID,
    employee_number: "WF-001",
    first_name: "Ada",
    last_name: "Yılmaz",
    email: "ada@wealthyfalcon.demo",
    status: "active",
    employee_version: 5,
  },
  personal: {
    preferred_name: "Ada",
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

const eligibleMembership = {
  membership_id: LINKED_MEMBERSHIP_ID,
  full_name: "Ada Hesap",
  email: "ada.account@wealthyfalcon.demo",
  membership_status: "active",
  user_status: "active",
  eligible: true,
};

const ownProfile = {
  core: {
    id: EMPLOYEE_ID,
    employee_number: "WF-001",
    first_name: "Ada",
    last_name: "Yılmaz",
    email: "ada@wealthyfalcon.demo",
    status: "active",
  },
  personal: {
    preferred_name: "Ada",
    birth_date: "1992-04-10",
    phone: "+905551110000",
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
      department: { code: "PEOPLE", name: "İnsan ve Kültür" },
      position: { code: "HR-SPEC", title: "İK Uzmanı" },
      manager: { full_name: "Mert Yönetici" },
    },
  },
};

test("HR links a canonical membership and only that linked session can populate Profilim", async ({
  context,
  page,
}) => {
  const staleOwnProfileGate = deferred();
  let activeUser = hrUser;
  let nextUser: typeof hrUser | null = null;
  let accessToken = "";
  let refreshCount = 0;
  let accountLinkState: {
    employee_id: string;
    link: null | {
      id: string;
      membership: typeof eligibleMembership;
      version: number;
      created_at: string;
      updated_at: string;
    };
  } = { employee_id: EMPLOYEE_ID, link: null };
  let accountPatchBody: unknown = null;
  let accountLinkReads = 0;
  let eligibleSearches = 0;
  let ownProfileRequests = 0;
  let employeePathRequestsFromOwnSessions = 0;
  let deferNextLinkedRead = false;
  let staleLinkedReads = 0;
  const ownRequestUrls: string[] = [];

  await context.addCookies([
    {
      name: "wf_refresh",
      value: "p4c-browser-refresh",
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
      accessToken = `p4c-access-${refreshCount}`;
      if (nextUser) {
        activeUser = nextUser;
        nextUser = null;
      }
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

    expect(request.headers().authorization).toMatch(/^Bearer p4c-access-\d+$/);

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
      path === `/api/v1/employees/${EMPLOYEE_ID}/profile` &&
      request.method() === "GET"
    ) {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: envelope(employee360Profile),
      });
      return;
    }

    if (
      path === `/api/v1/employees/${EMPLOYEE_ID}/account-link/eligible-memberships` &&
      request.method() === "GET"
    ) {
      eligibleSearches += 1;
      expect(url.searchParams.get("q")).toBe("ada");
      expect(url.searchParams.get("limit")).toBe("20");
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: envelope([eligibleMembership]),
      });
      return;
    }

    if (path === `/api/v1/employees/${EMPLOYEE_ID}/account-link`) {
      if (request.method() === "GET") {
        accountLinkReads += 1;
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: envelope(accountLinkState),
        });
        return;
      }
      if (request.method() === "PATCH") {
        accountPatchBody = request.postDataJSON();
        accountLinkState = {
          employee_id: EMPLOYEE_ID,
          link: {
            id: "fc500000-0000-4000-8000-000000000001",
            membership: eligibleMembership,
            version: 1,
            created_at: "2026-07-14T10:00:00Z",
            updated_at: "2026-07-14T10:00:00Z",
          },
        };
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: envelope(accountLinkState),
        });
        return;
      }
    }

    if (path === "/api/v1/me/employee-profile") {
      ownProfileRequests += 1;
      ownRequestUrls.push(request.url());
      expect(request.method()).toBe("GET");
      expect(request.postData()).toBeNull();
      const requestMembershipId = activeUser.membership_id;
      if (requestMembershipId === LINKED_MEMBERSHIP_ID) {
        if (deferNextLinkedRead) {
          deferNextLinkedRead = false;
          staleLinkedReads += 1;
          await staleOwnProfileGate.wait;
        }
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: envelope({
            availability: "available",
            membership_id: LINKED_MEMBERSHIP_ID,
            profile: ownProfile,
          }),
        });
        return;
      }
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: envelope({
          availability: "unavailable",
          membership_id: null,
          profile: null,
        }),
      });
      return;
    }

    if (
      activeUser.membership_id !== HR_MEMBERSHIP_ID &&
      path.startsWith("/api/v1/employees")
    ) {
      employeePathRequestsFromOwnSessions += 1;
    }

    await route.fulfill({
      status: 404,
      contentType: "application/json",
      body: errorEnvelope("not_found"),
    });
  });

  await page.goto(`/employees/${EMPLOYEE_ID}`);
  await expect(
    page.getByRole("heading", { level: 1, name: "Ada Yılmaz", exact: true }),
  ).toBeVisible();
  await expect(page.getByRole("heading", { name: "Hesap bağlantısı" })).toBeVisible();
  await page.getByRole("button", { name: "Hesap bağlantısını yönet" }).click();
  await expect(page.getByText("Bu çalışana bağlı hesap yok")).toBeVisible();

  await page.getByLabel("Ad soyad veya e-posta").fill("ada");
  await page.getByRole("button", { name: "Uygun hesapları ara" }).click();
  await expect.poll(() => eligibleSearches).toBe(1);
  await page.getByRole("radio", { name: /Ada Hesap/ }).check();
  await page.getByRole("button", { name: "Hesabı bağla", exact: true }).click();
  const confirmation = page.getByRole("dialog", {
    name: "Hesap çalışana bağlansın mı?",
  });
  await expect(confirmation).toContainText("Ada Hesap");
  await confirmation.getByRole("button", { name: "Hesabı bağla" }).click();

  await expect(page.getByRole("status")).toContainText("Hesap çalışana bağlandı");
  await expect(page.getByText("Profilim erişimine uygun")).toBeVisible();
  expect(accountPatchBody).toEqual({
    membership_id: LINKED_MEMBERSHIP_ID,
    expected_version: null,
  });
  await expect(page.getByText(HR_MEMBERSHIP_ID)).toHaveCount(0);
  await expect(page.getByText(LINKED_MEMBERSHIP_ID)).toHaveCount(0);

  nextUser = linkedEmployeeUser;
  await page.evaluate(() => window.dispatchEvent(new Event("focus")));
  await expect(page).toHaveURL(/\/dashboard$/);
  const profileNavigation = page.getByRole("link", { name: "Profilim", exact: true });
  await expect(profileNavigation).toBeVisible();
  await profileNavigation.click();
  await expect(page).toHaveURL(/\/profile$/);
  await expect(page.getByRole("heading", { level: 1, name: "Profilim" })).toBeVisible();
  await expect(page.getByText("Ada Yılmaz", { exact: true })).toBeVisible();
  await expect(page.getByText("İnsan ve Kültür", { exact: true })).toBeVisible();
  await expect(page.getByText("Mert Yönetici", { exact: true })).toBeVisible();

  deferNextLinkedRead = true;
  await page.getByRole("link", { name: "Genel bakış", exact: true }).click();
  await expect(page).toHaveURL(/\/dashboard$/);
  await page.getByRole("link", { name: "Profilim", exact: true }).click();
  await expect.poll(() => staleLinkedReads).toBe(1);

  nextUser = unlinkedEmployeeUser;
  await page.evaluate(() => window.dispatchEvent(new Event("focus")));
  await expect(
    page.getByRole("heading", { name: "Profiliniz henüz kullanıma hazır değil" }),
  ).toBeVisible();
  await expect(page.getByText("Ada Yılmaz", { exact: true })).toHaveCount(0);
  await expect(page.getByText(EMPLOYEE_ID)).toHaveCount(0);
  await expect(page.getByText(UNLINKED_MEMBERSHIP_ID)).toHaveCount(0);

  const staleResponse = page.waitForResponse(
    (response) =>
      new URL(response.url()).pathname === "/api/v1/me/employee-profile" &&
      response.request().headers().authorization !== `Bearer ${accessToken}`,
  );
  staleOwnProfileGate.release();
  await staleResponse;
  await flushClient(page);
  await expect(
    page.getByRole("heading", { name: "Profiliniz henüz kullanıma hazır değil" }),
  ).toBeVisible();
  await expect(page.getByText("Ada Yılmaz", { exact: true })).toHaveCount(0);
  await expect(page.getByText("Mert Yönetici", { exact: true })).toHaveCount(0);

  await page.goto(`/profile?employee_id=${GUESSED_EMPLOYEE_ID}`);
  await expect(
    page.getByRole("heading", { name: "Profiliniz henüz kullanıma hazır değil" }),
  ).toBeVisible();
  expect(
    ownRequestUrls.every((requestUrl) => {
      const requestUrlValue = new URL(requestUrl);
      return (
        requestUrlValue.pathname === "/api/v1/me/employee-profile" &&
        requestUrlValue.search === ""
      );
    }),
  ).toBe(true);
  expect(employeePathRequestsFromOwnSessions).toBe(0);

  const ownRequestsBeforeDenial = ownProfileRequests;
  nextUser = unauthorizedUser;
  await page.evaluate(() => window.dispatchEvent(new Event("focus")));
  await expect(page).toHaveURL(/\/dashboard$/);
  await expect(page.getByRole("link", { name: "Profilim", exact: true })).toHaveCount(0);

  await page.goto("/profile");
  await expect(page).toHaveURL(/\/dashboard$/);
  await expect(page.getByRole("heading", { name: "Merhaba, İpek Teknik" })).toBeVisible();
  expect(ownProfileRequests).toBe(ownRequestsBeforeDenial);
  expect(employeePathRequestsFromOwnSessions).toBe(0);

  const accountLinkReadsBeforeReadOnly = accountLinkReads;
  nextUser = employeeReadOnlyUser;
  await page.evaluate(() => window.dispatchEvent(new Event("focus")));
  await page.goto(`/employees/${EMPLOYEE_ID}`);
  await expect(
    page.getByRole("heading", { level: 1, name: "Ada Yılmaz", exact: true }),
  ).toBeVisible();
  await expect(page.getByRole("heading", { name: "Hesap bağlantısı" })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Hesap bağlantısını yönet" })).toHaveCount(0);
  expect(accountLinkReads).toBe(accountLinkReadsBeforeReadOnly);
});
