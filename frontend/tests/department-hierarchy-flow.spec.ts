import { expect, test, type Route } from "@playwright/test";

const PAGE_LIMIT = 25;

const sessionUser = {
  id: "f2000000-0000-4000-8000-000000000031",
  tenant_id: "f1000000-0000-4000-8000-000000000001",
  email: "hr@wealthyfalcon.demo",
  full_name: "Deniz Kaya",
  tenant: {
    slug: "wealthy-falcon-demo",
    name: "Wealthy Falcon HR Demo",
  },
  workspace_scope: "tenant",
  roles: [
    {
      id: "f3000000-0000-4000-8000-000000000031",
      code: "hr_specialist",
      name: "İK uzmanı",
      scope_type: "tenant",
    },
  ],
  permissions: [
    "dashboard:read:tenant",
    "organization:read:tenant",
    "organization:update:tenant",
  ],
  permission_version: 6,
};

const legalEntity = {
  id: "fa000000-0000-4000-8000-000000000001",
  code: "WF_TR",
  name: "Wealthy Falcon Türkiye",
  registered_name: "Wealthy Falcon İnsan Kaynakları A.Ş.",
  country_code: "TR",
  tax_number: "1234567890",
  timezone: "Europe/Istanbul",
  status: "active",
  is_default: true,
  created_at: "2026-07-10T10:00:00Z",
  updated_at: "2026-07-10T10:00:00Z",
};

type DepartmentStatus = "active" | "archived";

interface MockDepartment {
  id: string;
  parent_id: string | null;
  code: string;
  name: string;
  status: DepartmentStatus;
  archived_at: string | null;
  has_children: boolean;
  accepts_new_assignments: boolean;
  created_at: string;
  updated_at: string;
}

const engineeringId = "fc000000-0000-4000-8000-000000000001";
const peopleId = "fc000000-0000-4000-8000-000000000002";
const platformId = "fc000000-0000-4000-8000-000000000003";
const createdId = "fc000000-0000-4000-8000-000000000004";

function department(
  id: string,
  code: string,
  name: string,
  parentId: string | null,
  hasChildren = false,
): MockDepartment {
  return {
    id,
    parent_id: parentId,
    code,
    name,
    status: "active",
    archived_at: null,
    has_children: hasChildren,
    accepts_new_assignments: true,
    created_at: "2026-07-10T10:00:00Z",
    updated_at: "2026-07-10T10:00:00Z",
  };
}

function envelope(
  data: unknown,
  page?: { limit: number; next_cursor: string | null },
): string {
  return JSON.stringify({
    data,
    meta: {
      request_id: "browser-p3g",
      trace_id: "browser-p3g-trace",
      correlation_id: "browser-p3g",
      ...(page ?? {}),
    },
  });
}

test("HR lazily expands, creates, renames, moves, archives, and reads department history", async ({
  context,
  page,
}) => {
  let accessToken = "";
  let departments: MockDepartment[] = [
    department(engineeringId, "ENG", "Mühendislik", null, true),
    department(peopleId, "PEOPLE", "İnsan ve Kültür", null),
    department(platformId, "PLATFORM", "Platform", engineeringId),
  ];
  const treeQueries: URLSearchParams[] = [];
  const historyQueries: URLSearchParams[] = [];
  const creates: unknown[] = [];
  const patches: unknown[] = [];
  const archiveMethods: string[] = [];

  function withCurrentChildState(item: MockDepartment): MockDepartment {
    return {
      ...item,
      has_children: departments.some(
        (candidate) =>
          candidate.status === "active" && candidate.parent_id === item.id,
      ),
    };
  }

  await context.addCookies([
    {
      name: "wf_refresh",
      value: "department-hierarchy-refresh",
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
      accessToken = "department-hierarchy-access";
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

    if (path === "/api/v1/legal-entities") {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: envelope([legalEntity], { limit: PAGE_LIMIT, next_cursor: null }),
      });
      return;
    }

    if (path === `/api/v1/legal-entities/${legalEntity.id}`) {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: envelope(legalEntity),
      });
      return;
    }

    if (path === "/api/v1/branches") {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: envelope([], { limit: PAGE_LIMIT, next_cursor: null }),
      });
      return;
    }

    if (path === "/api/v1/departments/tree") {
      expect(request.method()).toBe("GET");
      treeQueries.push(new URLSearchParams(url.searchParams));
      expect(url.searchParams.get("limit")).toBe(String(PAGE_LIMIT));
      expect(url.searchParams.get("include_archived")).toBe("false");
      const parentId = url.searchParams.get("parent_id");
      const items = departments
        .filter(
          (item) =>
            item.status === "active" && item.parent_id === (parentId ?? null),
        )
        .map(withCurrentChildState);
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: envelope(items, { limit: PAGE_LIMIT, next_cursor: null }),
      });
      return;
    }

    if (path === "/api/v1/departments") {
      if (request.method() === "POST") {
        const payload = request.postDataJSON();
        creates.push(payload);
        const createdDepartment = department(
          createdId,
          payload.code,
          payload.name,
          payload.parent_id,
        );
        departments = [...departments, createdDepartment];
        await route.fulfill({
          status: 201,
          contentType: "application/json",
          body: envelope(createdDepartment),
        });
        return;
      }

      expect(request.method()).toBe("GET");
      historyQueries.push(new URLSearchParams(url.searchParams));
      const status = url.searchParams.get("status");
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: envelope(
          departments.filter((item) => item.status === status),
          { limit: PAGE_LIMIT, next_cursor: null },
        ),
      });
      return;
    }

    const target = departments.find(
      (item) => path === `/api/v1/departments/${item.id}`,
    );
    if (target && request.method() === "PATCH") {
      const payload = request.postDataJSON();
      patches.push(payload);
      const updatedDepartment: MockDepartment = {
        ...target,
        ...payload,
        updated_at: "2026-07-13T12:00:00Z",
      };
      departments = departments.map((item) =>
        item.id === target.id ? updatedDepartment : item,
      );
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: envelope(withCurrentChildState(updatedDepartment)),
      });
      return;
    }

    if (target && request.method() === "DELETE") {
      archiveMethods.push(request.method());
      expect(request.postData()).toBeNull();
      const archivedDepartment: MockDepartment = {
        ...target,
        status: "archived",
        archived_at: "2026-07-13T13:00:00Z",
        has_children: false,
        accepts_new_assignments: false,
        updated_at: "2026-07-13T13:00:00Z",
      };
      departments = departments.map((item) =>
        item.id === target.id ? archivedDepartment : item,
      );
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: envelope(archivedDepartment),
      });
      return;
    }

    await route.fulfill({ status: 404 });
  });

  await page.goto("/organization");

  await expect(
    page.getByRole("heading", { name: "Departman hiyerarşisi" }),
  ).toBeVisible();
  await expect(page.getByText("Mühendislik", { exact: true })).toBeVisible();
  expect(treeQueries).toHaveLength(1);
  expect(treeQueries[0].has("parent_id")).toBe(false);
  await expect(page.getByText("Platform", { exact: true })).toHaveCount(0);

  await page
    .getByRole("button", { name: "Mühendislik alt departmanlarını göster" })
    .click();
  await expect(page.getByText("Platform", { exact: true })).toBeVisible();
  expect(treeQueries.at(-1)?.get("parent_id")).toBe(engineeringId);

  await expect(
    page.getByRole("button", {
      name: "İnsan ve Kültür alt departmanlarını göster",
    }),
  ).toHaveCount(0);
  await page
    .getByRole("button", { name: "İnsan ve Kültür altında departman oluştur" })
    .click();
  const createDialog = page.getByRole("dialog", {
    name: "İnsan ve Kültür altında yeni departman",
  });
  await createDialog.getByLabel("Sabit kod").fill("TALENT");
  await createDialog.getByLabel("Departman adı").fill("Yetenek Kazanımı");
  await createDialog.getByRole("button", { name: "Departman oluştur" }).click();
  await expect(page.getByText("Yetenek Kazanımı", { exact: true })).toBeVisible();
  await expect(
    page.getByRole("button", {
      name: "İnsan ve Kültür alt departmanlarını gizle",
    }),
  ).toBeVisible();
  expect(creates).toEqual([
    { code: "TALENT", name: "Yetenek Kazanımı", parent_id: peopleId },
  ]);
  expect(JSON.stringify(creates)).not.toContain("tenant_id");

  await page
    .getByRole("button", { name: "Platform departmanını yeniden adlandır" })
    .click();
  const renameDialog = page.getByRole("dialog", { name: "Platform" });
  await expect(renameDialog.getByLabel("Sabit kod")).toHaveAttribute("readonly", "");
  await renameDialog.getByLabel("Departman adı").fill("Platform Mühendisliği");
  await renameDialog.getByRole("button", { name: "Yeni adı kaydet" }).click();
  await expect(page.getByText("Platform Mühendisliği", { exact: true })).toBeVisible();
  expect(patches[0]).toEqual({ name: "Platform Mühendisliği" });
  expect(JSON.stringify(patches[0])).not.toContain("code");

  await page
    .getByRole("button", { name: "Platform Mühendisliği departmanını taşı" })
    .click();
  await expect(
    page.getByText("Platform Mühendisliği için yeni üst departmanı seçin"),
  ).toBeVisible();
  await page
    .getByRole("button", {
      name: "Platform Mühendisliği departmanını İnsan ve Kültür altına taşı",
    })
    .click();
  await expect(
    page.getByRole("status").filter({ hasText: "İnsan ve Kültür altına taşındı" }),
  ).toBeVisible();
  expect(patches[1]).toEqual({ parent_id: peopleId });

  await page
    .getByRole("button", { name: "İnsan ve Kültür alt departmanlarını göster" })
    .click();
  await expect(page.getByText("Yetenek Kazanımı", { exact: true })).toBeVisible();
  await page
    .getByRole("button", { name: "Yetenek Kazanımı departmanını arşivle" })
    .click();
  const archiveDialog = page.getByRole("dialog", {
    name: "Yetenek Kazanımı arşivlensin mi?",
  });
  await expect(archiveDialog.getByText(/üst bağlantısıyla okunmaya devam eder/)).toBeVisible();
  await archiveDialog.getByRole("button", { name: "Departmanı arşivle" }).click();
  const archiveNotice = page
    .getByRole("status")
    .filter({ hasText: "üst bağlantısı ve sabit kodu geçmiş için korundu" });
  await expect(archiveNotice).toBeVisible();
  await expect(archiveNotice).toBeFocused();
  expect(archiveMethods).toEqual(["DELETE"]);

  await page.getByRole("button", { name: "Arşiv geçmişi" }).click();
  await expect(page.getByText("Yetenek Kazanımı", { exact: true })).toBeVisible();
  await expect(page.getByText("Geçmiş üst bağlantısı korunuyor")).toBeVisible();
  await expect(page.getByText("Yeni atamaya kapalı")).toBeVisible();
  expect(historyQueries.at(-1)?.get("limit")).toBe(String(PAGE_LIMIT));
  expect(historyQueries.at(-1)?.get("status")).toBe("archived");

  await page.setViewportSize({ width: 390, height: 844 });
  expect(
    await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth),
  ).toBe(true);
});
