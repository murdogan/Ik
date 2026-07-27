import { expect, test } from "@playwright/test";

import {
  apiEnvelope,
  installTenantSession,
} from "./support/tenant-session";

const EXPORT_ID = "f1000000-0000-4000-8000-000000000001";
const IMPORT_ID = "f2000000-0000-4000-8000-000000000001";

const managerUser = {
  id: "f3000000-0000-4000-8000-000000000001",
  membership_id: "f3100000-0000-4000-8000-000000000001",
  tenant_id: "f3200000-0000-4000-8000-000000000001",
  email: "manager@phase11.example",
  full_name: "Mert Yönetici",
  tenant: { slug: "phase11", name: "Phase 11" },
  workspace_scope: "tenant",
  roles: [
    {
      id: "f3300000-0000-4000-8000-000000000001",
      code: "manager",
      name: "Yönetici",
      scope_type: "tenant",
    },
  ],
  permissions: [
    "dashboard:read:own",
    "report:read:team",
    "report:export:team",
  ],
  permission_version: 1,
};

function exportJob(downloadIntentsRemaining: number) {
  return {
    id: EXPORT_ID,
    report_type: "employees",
    format: "xlsx",
    status: "succeeded",
    request_scope: "team",
    fields: ["employee_number", "first_name", "last_name"],
    generated_scope: "team",
    generated_fields: ["employee_number", "first_name", "last_name"],
    field_classifications: ["work_safe"],
    row_count: 1,
    size_bytes: 2048,
    sha256: "b".repeat(64),
    failure_code: null,
    cancel_requested: false,
    download_intents_remaining: downloadIntentsRemaining,
    available_at: "2026-07-27T10:00:00Z",
    expires_at: "2026-07-27T11:00:00Z",
    created_at: "2026-07-27T09:59:00Z",
    updated_at: "2026-07-27T10:00:00Z",
  };
}

test("manager report and export stay team-scoped and omit ungranted work email", async ({
  context,
  page,
}) => {
  let exportBody: Record<string, unknown> | null = null;
  let intentCreated = false;
  let objectRequests = 0;
  let objectAuthorization: string | undefined;
  let objectCookie: string | undefined;

  await page.route("http://localhost:3999/**", async (route) => {
    objectRequests += 1;
    objectAuthorization = route.request().headers().authorization;
    objectCookie = route.request().headers().cookie;
    await route.fulfill({
      status: 200,
      headers: {
        "content-type":
          "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "content-disposition": 'attachment; filename="team-employees.xlsx"',
      },
      body: "private-export-proof",
    });
  });
  await installTenantSession({
    context,
    page,
    user: managerUser,
    handleApi: async (route, request, url) => {
      const { pathname } = url;
      if (pathname === "/api/v1/reports/employees") {
        expect(url.searchParams.get("limit")).toBe("50");
        expect(url.searchParams.has("scope")).toBe(false);
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify({
            data: [
              {
                values: {
                  employee_number: "WF-201",
                  first_name: "Ece",
                  last_name: "Çalışkan",
                },
              },
            ],
            meta: {
              request_id: "phase11-browser",
              trace_id: "phase11-browser-trace",
              correlation_id: "phase11-browser",
              limit: 50,
              next_cursor: null,
              scope: "team",
              fields: ["employee_number", "first_name", "last_name"],
            },
          }),
        });
        return true;
      }
      if (pathname === "/api/v1/export-jobs" && request.method() === "POST") {
        exportBody = request.postDataJSON();
        expect(exportBody).toEqual({
          report_type: "employees",
          format: "xlsx",
          fields: ["employee_number", "first_name", "last_name"],
          filters: {},
        });
        expect(exportBody).not.toHaveProperty("scope");
        expect(JSON.stringify(exportBody)).not.toContain("work_email");
        await route.fulfill({
          status: 201,
          contentType: "application/json",
          body: apiEnvelope(exportJob(1)),
        });
        return true;
      }
      if (
        pathname === `/api/v1/export-jobs/${EXPORT_ID}/download-intents`
      ) {
        intentCreated = true;
        await route.fulfill({
          status: 201,
          contentType: "application/json",
          body: apiEnvelope({
            export_job_id: EXPORT_ID,
            method: "GET",
            url: "http://localhost:3999/team-employees.xlsx?proof=phase11",
            expires_at: "2026-07-27T10:05:00Z",
          }),
        });
        return true;
      }
      if (pathname === `/api/v1/export-jobs/${EXPORT_ID}`) {
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: apiEnvelope(exportJob(intentCreated ? 0 : 1)),
        });
        return true;
      }
      return false;
    },
  });

  await page.goto("/reports");
  await expect(
    page.getByRole("heading", { name: "Raporlar ve aktarımlar" }),
  ).toBeVisible();
  await expect(page.getByText("Doğrudan ekibiniz")).toBeVisible();
  await expect(page.getByRole("columnheader", { name: "İş e-postası" })).toHaveCount(0);
  await expect(page.getByText("private@phase11.example")).toHaveCount(0);

  await page
    .getByRole("button", { name: "Dışa aktarmayı başlat" })
    .click();
  await expect(page.getByText("1 satır")).toBeVisible();
  await page
    .getByRole("button", { name: "Güvenli indirme oluştur" })
    .click();
  await expect.poll(() => objectRequests).toBe(1);
  expect(objectAuthorization).toBeUndefined();
  expect(objectCookie).toBeUndefined();
  expect(exportBody).not.toBeNull();
});

function importRecord(status: "ready" | "succeeded") {
  return {
    id: IMPORT_ID,
    status,
    template_version: "1",
    file_format: "csv",
    scan_result: "clean",
    row_count: 1,
    error_count: 0,
    warning_count: 0,
    committed_count: status === "succeeded" ? 1 : 0,
    failure_code: null,
    issues: [],
    issues_next_cursor: null,
    validated_at: "2026-07-27T10:00:00Z",
    committed_at:
      status === "succeeded" ? "2026-07-27T10:01:00Z" : null,
    expires_at: "2026-07-28T10:00:00Z",
    created_at: "2026-07-27T09:59:00Z",
    updated_at:
      status === "succeeded"
        ? "2026-07-27T10:01:00Z"
        : "2026-07-27T10:00:00Z",
  };
}

test("HR import requires a clean validation result and explicit atomic commit", async ({
  context,
  page,
}) => {
  const hrUser = {
    ...managerUser,
    id: "f4000000-0000-4000-8000-000000000001",
    membership_id: "f4100000-0000-4000-8000-000000000001",
    email: "hr@phase11.example",
    full_name: "Deniz İnsan",
    roles: [
      {
        id: "f4200000-0000-4000-8000-000000000001",
        code: "hr_specialist",
        name: "İK uzmanı",
        scope_type: "tenant",
      },
    ],
    permissions: ["dashboard:read:own", "employee_import:manage:tenant"],
    permission_version: 2,
  };
  let committed = false;
  let uploadCalls = 0;
  let commitCalls = 0;

  await installTenantSession({
    context,
    page,
    user: hrUser,
    handleApi: async (route, request, url) => {
      const { pathname } = url;
      if (
        pathname === "/api/v1/employees/imports" &&
        request.method() === "POST"
      ) {
        expect(request.headers()["content-type"]).toContain(
          "multipart/form-data",
        );
        expect(request.postDataBuffer()?.toString()).toContain(
          "employee_number",
        );
        uploadCalls += 1;
        await route.fulfill({
          status: 201,
          contentType: "application/json",
          body: apiEnvelope(importRecord("ready")),
        });
        return true;
      }
      if (
        pathname === `/api/v1/employees/imports/${IMPORT_ID}/commit`
      ) {
        expect(request.postData()).toBeNull();
        expect(request.headers()["x-idempotency-key"]).toMatch(
          /^[0-9a-f-]{36}$/i,
        );
        committed = true;
        commitCalls += 1;
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: apiEnvelope({
            id: IMPORT_ID,
            status: "succeeded",
            committed_count: 1,
            committed_at: "2026-07-27T10:01:00Z",
          }),
        });
        return true;
      }
      if (pathname === `/api/v1/employees/imports/${IMPORT_ID}`) {
        expect(url.searchParams.get("issue_limit")).toBe("200");
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: apiEnvelope(importRecord(committed ? "succeeded" : "ready")),
        });
        return true;
      }
      return false;
    },
  });

  await page.goto("/reports");
  await expect(
    page.getByRole("heading", { name: "Dosyayı doğrulamaya gönder" }),
  ).toBeVisible();
  await page.locator('input[type="file"]').setInputFiles({
    name: "employees.csv",
    mimeType: "text/csv",
    buffer: Buffer.from(
      "employee_number,first_name,last_name,status,employment_start_date\nWF-301,Ada,Yılmaz,active,2026-01-01\n",
    ),
  });
  await expect(
    page.getByRole("heading", { name: "Çalışan içe aktarma" }),
  ).toBeVisible();
  await expect(page.getByText("Temiz", { exact: true })).toBeVisible();
  await page
    .getByRole("checkbox", {
      name: "1 doğrulanmış çalışanın tek işlemde oluşturulacağını",
    })
    .check();
  await page
    .getByRole("button", { name: "İçe aktarmayı kesinleştir" })
    .click();
  await expect(page.getByText("Tamamlandı", { exact: true })).toBeVisible();
  await expect(page.getByText("1", { exact: true }).last()).toBeVisible();
  expect(uploadCalls).toBe(1);
  expect(commitCalls).toBe(1);
});
