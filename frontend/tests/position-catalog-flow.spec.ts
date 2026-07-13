import { expect, test, type Route } from "@playwright/test";

const PAGE_LIMIT = 25;

const hrRole = {
  id: "f3000000-0000-4000-8000-000000000003",
  code: "hr_specialist",
  name: "İK Uzmanı",
  scope_type: "tenant",
};

const sessionUser = {
  id: "f2000000-0000-4000-8000-000000000003",
  tenant_id: "f1000000-0000-4000-8000-000000000001",
  email: "hr@wealthyfalcon.demo",
  full_name: "Deniz Kaya",
  tenant: {
    slug: "wealthy-falcon-demo",
    name: "Wealthy Falcon HR Demo",
  },
  workspace_scope: "tenant",
  roles: [hrRole],
  permissions: [
    "dashboard:read:tenant",
    "organization:read:tenant",
    "organization:update:tenant",
  ],
  permission_version: 5,
};

const timestamps = {
  created_at: "2026-07-13T08:00:00Z",
  updated_at: "2026-07-13T08:00:00Z",
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
  ...timestamps,
};

type MockPosition = ReturnType<typeof position>;

function position(
  id: string,
  code: string,
  title: string,
  status: "active" | "archived" = "active",
) {
  return {
    id,
    code,
    title,
    status,
    archived_at: status === "archived" ? "2026-07-12T09:00:00Z" : null,
    accepts_new_assignments: status === "active",
    ...timestamps,
  };
}

function envelope(data: unknown, page?: { limit: number; next_cursor: string | null }) {
  return JSON.stringify({
    data,
    meta: {
      request_id: "browser-p3h",
      trace_id: "browser-p3h-trace",
      correlation_id: "browser-p3h",
      ...(page ?? {}),
    },
  });
}

test("HR searches, pages, creates, updates, and archives reusable positions", async ({
  context,
  page,
}) => {
  let accessToken = "";
  const softwareId = "fc000000-0000-4000-8000-000000000001";
  const paginationFillers = Array.from({ length: PAGE_LIMIT - 2 }, (_, index) =>
    position(
      `fd000000-0000-4000-8000-${String(index + 1).padStart(12, "0")}`,
      `FILLER_${String(index + 1).padStart(2, "0")}`,
      `Dolgu Pozisyon ${index + 1}`,
    ),
  );
  let positions: MockPosition[] = [
    position(softwareId, "SOFTWARE_ENGINEER", "Yazılım Mühendisi"),
    ...paginationFillers,
    position(
      "fc000000-0000-4000-8000-000000000002",
      "LEGACY_ACCOUNTANT",
      "Eski Muhasebe Uzmanı",
      "archived",
    ),
    position(
      "fc000000-0000-4000-8000-000000000003",
      "SALES_SPECIALIST",
      "Satış Uzmanı",
    ),
  ];
  const listQueries: URLSearchParams[] = [];
  const creates: unknown[] = [];
  const patches: unknown[] = [];
  const archiveMethods: string[] = [];

  await context.addCookies([
    {
      name: "wf_refresh",
      value: "position-catalog-refresh",
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
      accessToken = "position-catalog-access";
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

    if (path === "/api/v1/branches" || path === "/api/v1/departments/tree") {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: envelope([], { limit: PAGE_LIMIT, next_cursor: null }),
      });
      return;
    }

    if (path === "/api/v1/positions") {
      if (request.method() === "POST") {
        const payload = request.postDataJSON();
        creates.push(payload);
        const createdPosition: MockPosition = {
          id: "fc000000-0000-4000-8000-000000000004",
          code: payload.code,
          title: payload.title,
          status: "active",
          archived_at: null,
          accepts_new_assignments: true,
          ...timestamps,
        };
        positions = [createdPosition, ...positions];
        await route.fulfill({
          status: 201,
          contentType: "application/json",
          body: envelope(createdPosition),
        });
        return;
      }

      expect(request.method()).toBe("GET");
      listQueries.push(new URLSearchParams(url.searchParams));
      const status = url.searchParams.get("status");
      const search = url.searchParams.get("search")?.toLocaleLowerCase("tr-TR") ?? "";
      const cursor = url.searchParams.get("cursor");
      const filtered = positions.filter(
        (item) =>
          (!status || item.status === status) &&
          (!search ||
            item.code.toLocaleLowerCase("tr-TR").includes(search) ||
            item.title.toLocaleLowerCase("tr-TR").includes(search)),
      );
      const paged = !status && !search
        ? cursor === "positions-page-2"
          ? filtered.slice(PAGE_LIMIT)
          : filtered.slice(0, PAGE_LIMIT)
        : filtered;
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: envelope(paged, {
          limit: PAGE_LIMIT,
          next_cursor:
            !status &&
            !search &&
            cursor !== "positions-page-2" &&
            filtered.length > PAGE_LIMIT
              ? "positions-page-2"
              : null,
        }),
      });
      return;
    }

    const target = positions.find(
      (item) => path === `/api/v1/positions/${item.id}`,
    );
    if (target && request.method() === "GET") {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: envelope(target),
      });
      return;
    }

    if (target && request.method() === "PATCH") {
      const payload = request.postDataJSON();
      patches.push(payload);
      const updatedPosition: MockPosition = {
        ...target,
        ...payload,
        updated_at: "2026-07-13T12:00:00Z",
      };
      positions = positions.map((item) =>
        item.id === target.id ? updatedPosition : item,
      );
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: envelope(updatedPosition),
      });
      return;
    }

    if (target && request.method() === "DELETE") {
      archiveMethods.push(request.method());
      expect(request.postData()).toBeNull();
      const archivedPosition: MockPosition = {
        ...target,
        status: "archived",
        archived_at: "2026-07-13T13:00:00Z",
        accepts_new_assignments: false,
        updated_at: "2026-07-13T13:00:00Z",
      };
      positions = positions.map((item) =>
        item.id === target.id ? archivedPosition : item,
      );
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: envelope(archivedPosition),
      });
      return;
    }

    await route.fulfill({ status: 404 });
  });

  await page.goto("/organization");

  const catalog = page.getByRole("article", { name: "Pozisyon kataloğu" });
  await expect(catalog).toBeVisible();
  await expect(catalog.getByText("Yazılım Mühendisi", { exact: true })).toBeVisible();
  await expect(catalog.getByLabel("Pozisyon ara")).toHaveAttribute("minlength", "1");
  await expect(catalog.getByLabel("Pozisyon ara")).toHaveAttribute("maxlength", "100");
  expect(listQueries.at(-1)?.get("limit")).toBe(String(PAGE_LIMIT));
  expect(listQueries.at(-1)?.has("search")).toBe(false);

  await catalog.getByRole("button", { name: "Sonraki" }).click();
  await expect(catalog.getByText("Satış Uzmanı", { exact: true })).toBeVisible();
  expect(listQueries.at(-1)?.get("cursor")).toBe("positions-page-2");
  await catalog.getByRole("button", { name: "Önceki" }).click();
  await expect(catalog.getByText("Yazılım Mühendisi", { exact: true })).toBeVisible();

  const positionSearch = catalog.getByLabel("Pozisyon ara");
  const queryCountBeforeInvalidSearch = listQueries.length;
  await positionSearch.fill("---");
  await catalog.getByRole("button", { name: "Ara", exact: true }).click();
  await expect(positionSearch).toHaveJSProperty(
    "validationMessage",
    "1–2 karakterli aramalar tam kod olmalı; diğer aramalar en az 3 ardışık harf veya rakam içermelidir.",
  );
  expect(listQueries).toHaveLength(queryCountBeforeInvalidSearch);

  await positionSearch.fill("Yazılım");
  await catalog.getByRole("button", { name: "Ara", exact: true }).click();
  await expect(catalog.getByText("Yazılım Mühendisi", { exact: true })).toBeVisible();
  expect(listQueries.at(-1)?.get("search")).toBe("Yazılım");
  expect(listQueries.at(-1)?.has("cursor")).toBe(false);
  await catalog.getByRole("button", { name: "Temizle" }).click();
  await expect(catalog.getByText("Eski Muhasebe Uzmanı", { exact: true })).toBeVisible();

  await catalog.getByRole("button", { name: "Yeni pozisyon" }).click();
  const createDialog = page.getByRole("dialog", { name: "Yeni pozisyon" });
  await createDialog.getByLabel("Sabit kod").fill("DATA_ANALYST");
  await createDialog.getByLabel("Pozisyon unvanı").fill("Veri Analisti");
  await createDialog.getByRole("button", { name: "Pozisyon oluştur" }).click();
  await expect(catalog.getByText("Veri Analisti", { exact: true })).toBeVisible();
  expect(creates).toEqual([{ code: "DATA_ANALYST", title: "Veri Analisti" }]);
  expect(JSON.stringify(creates)).not.toContain("tenant_id");

  await catalog
    .getByRole("button", { name: "Yazılım Mühendisi pozisyonunu düzenle" })
    .click();
  const editDialog = page.getByRole("dialog", { name: "Yazılım Mühendisi" });
  await expect(editDialog.getByLabel("Sabit kod")).toHaveAttribute("readonly", "");
  await editDialog.getByLabel("Pozisyon unvanı").fill("Kıdemli Yazılım Mühendisi");
  await editDialog.getByRole("button", { name: "Değişiklikleri kaydet" }).click();
  await expect(
    catalog.getByText("Kıdemli Yazılım Mühendisi", { exact: true }),
  ).toBeVisible();
  expect(patches).toEqual([{ title: "Kıdemli Yazılım Mühendisi" }]);
  expect(JSON.stringify(patches)).not.toContain("code");

  await catalog
    .getByRole("button", {
      name: "Kıdemli Yazılım Mühendisi pozisyonunu arşivle",
    })
    .click();
  const archiveDialog = page.getByRole("dialog", {
    name: "Kıdemli Yazılım Mühendisi arşivlensin mi?",
  });
  await expect(archiveDialog.getByText(/Yeni atamalar durdurulacak/)).toBeVisible();
  await archiveDialog.getByRole("button", { name: "Pozisyonu arşivle" }).click();
  const archiveNotice = catalog
    .getByRole("status")
    .filter({ hasText: "Geçmiş atamalar korunur" });
  await expect(archiveNotice).toBeVisible();
  await expect(archiveNotice).toBeFocused();
  expect(archiveMethods).toEqual(["DELETE"]);

  const archivedRow = catalog.locator('tr[data-position-status="archived"]', {
    hasText: "Kıdemli Yazılım Mühendisi",
  });
  await expect(archivedRow).toContainText("Yeni atamaya kapalı");
  await expect(archivedRow.getByText("Geçmiş kayıt")).toBeVisible();
  await expect(
    catalog.getByRole("button", {
      name: "Kıdemli Yazılım Mühendisi pozisyonunu düzenle",
    }),
  ).toHaveCount(0);

  await catalog.getByLabel("Pozisyon durumu").selectOption("archived");
  await expect(catalog.getByText("Eski Muhasebe Uzmanı", { exact: true })).toBeVisible();
  expect(listQueries.at(-1)?.get("status")).toBe("archived");
  expect(listQueries.at(-1)?.has("cursor")).toBe(false);

  await page.setViewportSize({ width: 390, height: 844 });
  expect(
    await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth),
  ).toBe(true);
});
