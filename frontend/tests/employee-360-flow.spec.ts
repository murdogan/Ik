import { expect, test, type Route } from "@playwright/test";

const EMPLOYEE_ID = "fa000000-0000-4000-8000-000000000001";

function envelope(data: unknown): string {
  return JSON.stringify({
    data,
    meta: {
      request_id: "browser-p4b",
      trace_id: "browser-p4b-trace",
      correlation_id: "browser-p4b",
    },
  });
}

function errorEnvelope(code: string, correlationId = "browser-p4b"): string {
  return JSON.stringify({
    error: {
      code,
      message: "Request failed",
      details: null,
      correlation_id: correlationId,
    },
  });
}

const hrUser = {
  id: "f2000000-0000-4000-8000-000000000041",
  tenant_id: "f1000000-0000-4000-8000-000000000001",
  email: "hr@wealthyfalcon.demo",
  full_name: "Derya İnsan",
  tenant: {
    slug: "wealthy-falcon-demo",
    name: "Wealthy Falcon HR Demo",
  },
  workspace_scope: "tenant",
  roles: [
    {
      id: "f3000000-0000-4000-8000-000000000004",
      code: "hr_specialist",
      name: "İK uzmanı",
      scope_type: "tenant",
    },
  ],
  permissions: [
    "dashboard:read:own",
    "employee:read:tenant",
    "employee:update:tenant",
  ],
  permission_version: 4,
};

const directoryEmployee = {
  id: EMPLOYEE_ID,
  employee_number: "WF-001",
  first_name: "Ada",
  last_name: "Yılmaz",
  email: "ada@wealthyfalcon.demo",
  department: "İnsan ve Kültür",
  position: "İK Uzmanı",
  status: "active",
  employment_start_date: "2025-02-03",
  employment_end_date: null,
  version: 5,
  current_assignment: {
    id: "f7400000-0000-4000-8000-000000000001",
    legal_entity: {
      id: "f7000000-0000-4000-8000-000000000001",
      code: "WF-TR",
      name: "Wealthy Falcon Türkiye",
    },
    branch: {
      id: "f7100000-0000-4000-8000-000000000001",
      code: "IST",
      name: "İstanbul",
    },
    department: {
      id: "f7200000-0000-4000-8000-000000000001",
      code: "PEOPLE",
      name: "İnsan ve Kültür",
    },
    position: {
      id: "f7300000-0000-4000-8000-000000000001",
      code: "HR-SPEC",
      title: "İK Uzmanı",
    },
    effective_from: "2025-02-03",
  },
};

const assignmentEmployee = {
  id: EMPLOYEE_ID,
  employee_number: "WF-001",
  first_name: "Ada",
  last_name: "Yılmaz",
  email: "ada@wealthyfalcon.demo",
  status: "active",
};

const currentAssignment = {
  id: "f7400000-0000-4000-8000-000000000001",
  employee: assignmentEmployee,
  legal_entity: {
    id: "f7000000-0000-4000-8000-000000000001",
    code: "WF-TR",
    name: "Wealthy Falcon Türkiye",
    status: "active",
  },
  branch: {
    id: "f7100000-0000-4000-8000-000000000001",
    code: "IST",
    name: "İstanbul",
    status: "active",
  },
  department: {
    id: "f7200000-0000-4000-8000-000000000001",
    code: "PEOPLE",
    name: "İnsan ve Kültür",
    status: "active",
  },
  position: {
    id: "f7300000-0000-4000-8000-000000000001",
    code: "HR-SPEC",
    title: "İK Uzmanı",
    status: "active",
  },
  manager: {
    id: "f2000000-0000-4000-8000-000000000051",
    full_name: "Mert Yönetici",
    email: "mert@wealthyfalcon.demo",
    status: "active",
  },
  effective_from: "2025-02-03",
  effective_to: null,
  supersedes_assignment_id: "f7400000-0000-4000-8000-000000000002",
  change_reason: "İnsan ve Kültür ekibine geçiş",
  is_current: true,
  created_at: "2025-02-03T08:00:00Z",
  updated_at: "2025-02-03T08:00:00Z",
};

const historicalAssignment = {
  ...currentAssignment,
  id: "f7400000-0000-4000-8000-000000000002",
  department: {
    id: "f7200000-0000-4000-8000-000000000002",
    code: "OPS",
    name: "Operasyon",
    status: "archived",
  },
  position: {
    id: "f7300000-0000-4000-8000-000000000002",
    code: "OPS-SPEC",
    title: "Operasyon Uzmanı",
    status: "archived",
  },
  manager: null,
  effective_from: "2023-06-01",
  effective_to: "2025-02-03",
  supersedes_assignment_id: null,
  change_reason: "İlk yapısal atama",
  is_current: false,
  created_at: "2023-06-01T08:00:00Z",
  updated_at: "2025-02-03T08:00:00Z",
};

const assignmentHistory = [
  currentAssignment,
  historicalAssignment,
  ...Array.from({ length: 48 }, (_, offset) => {
    const sequence = offset + 3;
    return {
      ...historicalAssignment,
      id: `f7400000-0000-4000-8000-${String(sequence).padStart(12, "0")}`,
      department: {
        ...historicalAssignment.department,
        id: `f7200000-0000-4000-8000-${String(sequence).padStart(12, "0")}`,
        code: `OLD-${sequence}`,
        name: `Geçmiş Departman ${sequence}`,
      },
      effective_from: "2020-01-01",
      effective_to: "2020-12-31",
      change_reason: `Geçmiş atama ${sequence}`,
      created_at: "2020-01-01T08:00:00Z",
      updated_at: "2020-12-31T08:00:00Z",
    };
  }),
];

function initialProfile() {
  return {
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
      current_assignment: currentAssignment,
      history: assignmentHistory,
      history_limit: 50,
      history_truncated: true,
    },
  };
}

test("HR uses the full Employee 360 tabs, resolves a personal conflict, and reads bounded organization history", async ({
  context,
  page,
}) => {
  let accessToken = "";
  let profileState = initialProfile();
  let profileReadCount = 0;
  let assignmentRequests = 0;
  const personalPatchBodies: unknown[] = [];
  const employmentPatchBodies: unknown[] = [];

  await context.addCookies([
    {
      name: "wf_refresh",
      value: "p4b-hr-refresh",
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
      accessToken = "p4b-hr-access";
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: envelope({
          access_token: accessToken,
          token_type: "bearer",
          expires_in: 900,
          user: hrUser,
        }),
      });
      return;
    }

    expect(request.headers().authorization).toBe(`Bearer ${accessToken}`);
    if (path === "/api/v1/me") {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: envelope({ user: hrUser }),
      });
      return;
    }

    if (path === "/api/v1/employees" && request.method() === "GET") {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify([directoryEmployee]),
      });
      return;
    }

    if (
      path === `/api/v1/employees/${EMPLOYEE_ID}/profile` &&
      request.method() === "GET"
    ) {
      profileReadCount += 1;
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: envelope(profileState),
      });
      return;
    }

    if (
      path === `/api/v1/employees/${EMPLOYEE_ID}/profile/personal` &&
      request.method() === "PATCH"
    ) {
      personalPatchBodies.push(request.postDataJSON());
      if (personalPatchBodies.length === 1) {
        profileState = {
          ...profileState,
          core: {
            ...profileState.core,
            email: "ada.server@wealthyfalcon.demo",
            employee_version: 6,
          },
          personal: {
            preferred_name: "Ada Naz",
            birth_date: "1992-04-11",
            phone: "+905551110001",
            version: 3,
          },
        };
        await route.fulfill({
          status: 409,
          contentType: "application/json",
          headers: { "x-request-id": "p4b-conflict-001" },
          body: errorEnvelope("concurrent_write_conflict", "p4b-conflict-001"),
        });
        return;
      }

      profileState = {
        ...profileState,
        personal: {
          preferred_name: "Ado",
          birth_date: "1992-04-12",
          phone: "+905551112233",
          version: 4,
        },
      };
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: envelope({
          core: profileState.core,
          personal: profileState.personal,
        }),
      });
      return;
    }

    if (
      path === `/api/v1/employees/${EMPLOYEE_ID}/profile/employment` &&
      request.method() === "PATCH"
    ) {
      employmentPatchBodies.push(request.postDataJSON());
      profileState = {
        ...profileState,
        employment: {
          employment_start_date: "2025-02-03",
          contract_type: "fixed_term",
          work_type: "part_time",
          version: 8,
        },
      };
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: envelope({
          core: profileState.core,
          employment: profileState.employment,
        }),
      });
      return;
    }

    if (path === "/api/v1/employee-assignments") {
      assignmentRequests += 1;
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: envelope(assignmentHistory),
      });
      return;
    }

    // P4A uses this compatibility detail while the Employee 360 route is still RED.
    if (path === `/api/v1/employees/${EMPLOYEE_ID}`) {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(directoryEmployee),
      });
      return;
    }

    await route.fulfill({
      status: 404,
      contentType: "application/json",
      body: errorEnvelope("not_found"),
    });
  });

  await page.goto("/employees");
  await expect(page.getByRole("heading", { name: "Çalışanlar", exact: true })).toBeVisible();
  await page
    .getByRole("link", { name: "Ada Yılmaz çalışanını incele", exact: true })
    .click();

  await expect(page).toHaveURL(new RegExp(`/employees/${EMPLOYEE_ID}$`));
  await expect(page.getByRole("dialog")).toHaveCount(0);
  await expect(
    page.getByRole("heading", { level: 1, name: "Ada Yılmaz", exact: true }),
  ).toBeVisible();
  await expect.poll(() => profileReadCount).toBe(1);

  const tablist = page.getByRole("tablist", { name: "Çalışan profil bölümleri" });
  const summaryTab = tablist.getByRole("tab", { name: "Özet", exact: true });
  const personalTab = tablist.getByRole("tab", { name: "Kişisel", exact: true });
  const employmentTab = tablist.getByRole("tab", { name: "İstihdam", exact: true });
  const organizationTab = tablist.getByRole("tab", {
    name: "Organizasyon",
    exact: true,
  });

  await expect(summaryTab).toHaveAttribute("aria-selected", "true");
  await summaryTab.focus();
  await summaryTab.press("ArrowRight");
  await expect(personalTab).toBeFocused();
  await expect(personalTab).toHaveAttribute("aria-selected", "true");
  await personalTab.press("End");
  await expect(organizationTab).toBeFocused();
  await expect(organizationTab).toHaveAttribute("aria-selected", "true");
  await organizationTab.press("Home");
  await expect(summaryTab).toBeFocused();
  await expect(summaryTab).toHaveAttribute("aria-selected", "true");

  await personalTab.click();
  const personalPanel = page.getByRole("tabpanel", { name: "Kişisel" });
  await personalPanel.getByLabel("Ad", { exact: true }).fill("Ada");
  await personalPanel.getByLabel("Soyad", { exact: true }).fill("Yılmaz");
  await personalPanel.getByLabel("Tercih edilen ad").fill("Ado");
  await personalPanel.getByLabel("Doğum tarihi").fill("1992-04-12");
  await personalPanel.getByLabel("Telefon").fill("+905551112233");
  await personalPanel
    .getByRole("button", { name: "Kişisel bilgileri kaydet" })
    .click();

  await expect(personalPanel.getByRole("alert")).toContainText(
    "Bu bölüm siz düzenlerken değişti",
  );
  await expect(personalPanel.getByRole("alert")).toContainText("p4b-conflict-001");
  expect(personalPatchBodies[0]).toEqual({
    expected_version: 2,
    preferred_name: "Ado",
    birth_date: "1992-04-12",
    phone: "+905551112233",
  });

  await personalPanel.getByRole("button", { name: "Güncel veriyi yükle" }).click();
  await expect.poll(() => profileReadCount).toBe(2);
  await expect(personalPanel.getByLabel("İş e-postası", { exact: true })).toHaveValue(
    "ada.server@wealthyfalcon.demo",
  );
  await expect(personalPanel.getByLabel("Tercih edilen ad")).toHaveValue("Ada Naz");

  await personalPanel.getByLabel("Tercih edilen ad").fill("Ado");
  await personalPanel.getByLabel("Doğum tarihi").fill("1992-04-12");
  await personalPanel.getByLabel("Telefon").fill("+905551112233");
  await personalPanel
    .getByRole("button", { name: "Kişisel bilgileri kaydet" })
    .click();
  await expect(personalPanel.getByRole("status")).toContainText(
    "Kişisel bilgiler güncellendi",
  );
  expect(personalPatchBodies[1]).toEqual({
    expected_version: 3,
    preferred_name: "Ado",
    birth_date: "1992-04-12",
    phone: "+905551112233",
  });

  await employmentTab.click();
  const employmentPanel = page.getByRole("tabpanel", { name: "İstihdam" });
  await employmentPanel.getByLabel("Sözleşme türü").selectOption("fixed_term");
  await employmentPanel.getByLabel("Çalışma türü").selectOption("part_time");
  await employmentPanel
    .getByRole("button", { name: "İstihdam bilgilerini kaydet" })
    .click();
  await expect(employmentPanel.getByRole("status")).toContainText(
    "İstihdam bilgileri güncellendi",
  );
  expect(employmentPatchBodies).toEqual([
    {
      expected_version: 7,
      contract_type: "fixed_term",
      work_type: "part_time",
    },
  ]);

  // A successful employment merge must not discard the independently updated personal section.
  await personalTab.click();
  await expect(personalPanel.getByLabel("Tercih edilen ad")).toHaveValue("Ado");

  await organizationTab.click();
  const organizationPanel = page.getByRole("tabpanel", { name: "Organizasyon" });
  await expect(organizationPanel.getByText("İnsan ve Kültür", { exact: true }).first()).toBeVisible();
  await expect(
    organizationPanel.getByText("Mert Yönetici", { exact: true }).first(),
  ).toBeVisible();
  await expect(organizationPanel.getByText("Operasyon", { exact: true })).toBeVisible();
  await expect(
    organizationPanel.getByText("Operasyon Uzmanı", { exact: true }).first(),
  ).toBeVisible();
  await expect(organizationPanel).toContainText("İlk 50 atama kaydı gösteriliyor");
  expect(assignmentRequests).toBe(0);

  await expect(page.getByLabel(/TCKN|kimlik numarası|IBAN|maaş|adres/i)).toHaveCount(0);
  await expect(
    page.getByRole("button", {
      name: /atama oluştur|atamayı değiştir|işten çıkar|arşivle/i,
    }),
  ).toHaveCount(0);
});

test("direct Employee 360 denial redirects without mounting profile or assignment clients", async ({
  context,
  page,
}) => {
  const deniedUser = {
    ...hrUser,
    id: "f2000000-0000-4000-8000-000000000042",
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
  };
  let accessToken = "";
  let profileRequests = 0;
  let assignmentRequests = 0;
  let anyEmployeeDataRequests = 0;

  await context.addCookies([
    {
      name: "wf_refresh",
      value: "p4b-denied-refresh",
      url: "http://127.0.0.1:3100",
      httpOnly: true,
      sameSite: "Lax",
    },
  ]);

  await page.route("**/api/v1/**", async (route: Route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    if (path === "/api/v1/auth/refresh") {
      accessToken = "p4b-denied-access";
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: envelope({
          access_token: accessToken,
          token_type: "bearer",
          expires_in: 900,
          user: deniedUser,
        }),
      });
      return;
    }

    expect(request.headers().authorization).toBe(`Bearer ${accessToken}`);
    if (path === "/api/v1/me") {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: envelope({ user: deniedUser }),
      });
      return;
    }
    if (path.startsWith("/api/v1/employees")) {
      anyEmployeeDataRequests += 1;
      if (path.endsWith("/profile")) profileRequests += 1;
      await route.fulfill({
        status: 403,
        contentType: "application/json",
        body: errorEnvelope("authorization_denied"),
      });
      return;
    }
    if (path === "/api/v1/employee-assignments") {
      assignmentRequests += 1;
      await route.fulfill({
        status: 403,
        contentType: "application/json",
        body: errorEnvelope("authorization_denied"),
      });
      return;
    }
    await route.fulfill({ status: 404 });
  });

  await page.goto(`/employees/${EMPLOYEE_ID}`);
  await expect(page).toHaveURL(/\/dashboard$/);
  await expect(page.getByRole("heading", { name: "Merhaba, Ece Çalışkan" })).toBeVisible();
  await expect(page.getByRole("link", { name: "Çalışanlar", exact: true })).toHaveCount(0);
  expect(profileRequests).toBe(0);
  expect(assignmentRequests).toBe(0);
  expect(anyEmployeeDataRequests).toBe(0);
});
