import { expect, test } from "@playwright/test";

import {
  apiEnvelope,
  installTenantSession,
} from "./support/tenant-session";

const DOCUMENT_TYPE_ID = "a1000000-0000-4000-8000-000000000001";

const hrUser = {
  id: "a2000000-0000-4000-8000-000000000001",
  membership_id: "a2100000-0000-4000-8000-000000000001",
  tenant_id: "a2200000-0000-4000-8000-000000000001",
  email: "hr@phase11.example",
  full_name: "Deniz İnsan",
  tenant: { slug: "phase11", name: "Phase 11" },
  workspace_scope: "tenant",
  roles: [
    {
      id: "a2300000-0000-4000-8000-000000000001",
      code: "hr_specialist",
      name: "İK uzmanı",
      scope_type: "tenant",
    },
  ],
  permissions: ["dashboard:read:own", "document_type:manage:tenant"],
  permission_version: 1,
};

test("HR creates and archives a tenant document type without deleting history", async ({
  context,
  page,
}) => {
  let documentType:
    | {
        id: string;
        code: string;
        name: string;
        description: string;
        required: boolean;
        employee_visible: boolean;
        sensitivity: "sensitive";
        expiry_mode: "optional";
        allowed_mime_types: [
          "application/pdf",
          "image/jpeg",
          "image/png",
        ];
        allowed_extensions: ["pdf", "jpg", "jpeg", "png"];
        max_size_bytes: number;
        version: number;
        archived_at: string | null;
      }
    | null = null;
  const mutations: string[] = [];

  await installTenantSession({
    context,
    page,
    user: hrUser,
    handleApi: async (route, request, url) => {
      const { pathname } = url;
      if (
        pathname === "/api/v1/document-types" &&
        request.method() === "GET"
      ) {
        expect(url.searchParams.get("include_archived")).toBe("true");
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: apiEnvelope(documentType ? [documentType] : []),
        });
        return true;
      }
      if (
        pathname === "/api/v1/document-types" &&
        request.method() === "POST"
      ) {
        expect(request.postDataJSON()).toEqual({
          code: "employment_letter",
          name: "Çalışma belgesi",
          description: "İmzalı çalışma belgesi",
          required: true,
          employee_visible: false,
          sensitivity: "sensitive",
          expiry_mode: "optional",
          allowed_mime_types: [
            "application/pdf",
            "image/jpeg",
            "image/png",
          ],
          allowed_extensions: ["pdf", "jpg", "jpeg", "png"],
          max_size_bytes: 20 * 1024 * 1024,
        });
        documentType = {
          id: DOCUMENT_TYPE_ID,
          ...request.postDataJSON(),
          version: 1,
          archived_at: null,
        };
        mutations.push(pathname);
        await route.fulfill({
          status: 201,
          contentType: "application/json",
          body: apiEnvelope(documentType),
        });
        return true;
      }
      if (
        pathname ===
        `/api/v1/document-types/${DOCUMENT_TYPE_ID}/archive`
      ) {
        expect(request.postDataJSON()).toEqual({ expected_version: 1 });
        if (!documentType) throw new Error("document type missing");
        documentType = {
          ...documentType,
          version: 2,
          archived_at: "2026-07-27T12:00:00Z",
        };
        mutations.push(pathname);
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: apiEnvelope(documentType),
        });
        return true;
      }
      return false;
    },
  });

  await page.goto("/document-types");
  await expect(
    page.getByRole("heading", { name: "Belge türleri", exact: true }),
  ).toBeVisible();
  await page.getByLabel("Sabit kod").fill("EMPLOYMENT_LETTER");
  await page.getByLabel("Belge türü adı").fill("Çalışma belgesi");
  await page.getByLabel("Açıklama").fill("İmzalı çalışma belgesi");
  await page.getByRole("button", { name: "Belge türü oluştur" }).click();
  await expect(
    page
      .getByRole("status")
      .filter({ hasText: "Belge türü oluşturuldu" }),
  ).toBeVisible();
  await expect(
    page.getByText("Çalışma belgesi", { exact: true }),
  ).toBeVisible();

  await page.getByRole("button", { name: "Arşivle" }).click();
  await expect(
    page
      .getByRole("status")
      .filter({ hasText: "Belge türü arşivlendi" }),
  ).toBeVisible();
  await expect(page.getByText("Arşivli", { exact: true })).toBeVisible();
  expect(mutations).toEqual([
    "/api/v1/document-types",
    `/api/v1/document-types/${DOCUMENT_TYPE_ID}/archive`,
  ]);
});
