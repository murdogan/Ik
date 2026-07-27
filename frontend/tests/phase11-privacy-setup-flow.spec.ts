import { expect, test } from "@playwright/test";

import {
  apiEnvelope,
  installTenantSession,
} from "./support/tenant-session";

const NOTICE_ID = "e1000000-0000-4000-8000-000000000001";
const PURPOSE_ID = "e2000000-0000-4000-8000-000000000001";
const POLICY_ID = "e3000000-0000-4000-8000-000000000001";
const CONTENT_HASH = "a".repeat(64);

const publishedNotice = {
  id: NOTICE_ID,
  notice_kind: "employee",
  locale: "tr-TR",
  notice_version: 1,
  revision: 1,
  title: "Çalışan gizlilik bildirimi",
  content_hash: CONTENT_HASH,
  status: "published" as "draft" | "published" | "superseded",
  published_at: "2026-07-27T08:00:00Z" as string | null,
  created_at: "2026-07-26T08:00:00Z",
  updated_at: "2026-07-27T08:00:00Z",
  body: "Veriler yalnız açık iş amaçları ve yasal yükümlülükler için işlenir.",
};

const employeeUser = {
  id: "e4000000-0000-4000-8000-000000000001",
  membership_id: "e4100000-0000-4000-8000-000000000001",
  tenant_id: "e4200000-0000-4000-8000-000000000001",
  email: "employee@phase11.example",
  full_name: "Ece Çalışkan",
  tenant: { slug: "phase11", name: "Phase 11" },
  workspace_scope: "tenant",
  roles: [
    {
      id: "e4300000-0000-4000-8000-000000000001",
      code: "employee",
      name: "Çalışan",
      scope_type: "tenant",
    },
  ],
  permissions: [
    "dashboard:read:own",
    "privacy_notice:read:own",
    "privacy_notice:acknowledge:own",
    "privacy_consent:manage:own",
  ],
  permission_version: 1,
};

test("employee acknowledgment binds the immutable hash and consent history stays append-only", async ({
  context,
  page,
}) => {
  let acknowledgedAt: string | null = null;
  let purpose = {
    id: PURPOSE_ID,
    code: "wellbeing_updates",
    version: 1,
    title: "İsteğe bağlı iyi yaşam duyuruları",
    description: "Zorunlu olmayan kurum içi iyi yaşam içerikleri.",
    is_active: true,
    granted: false,
    state_version: 0,
    updated_at: null as string | null,
    history: [] as Array<{
      id: string;
      action: "grant" | "withdraw";
      purpose_version: number;
      occurred_at: string;
    }>,
  };
  const mutations: string[] = [];

  await installTenantSession({
    context,
    page,
    user: employeeUser,
    handleApi: async (route, request, url) => {
      const { pathname } = url;
      if (pathname === "/api/v1/privacy/notice") {
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: apiEnvelope({
            notice: publishedNotice,
            acknowledged_at: acknowledgedAt,
          }),
        });
        return true;
      }
      if (pathname === "/api/v1/privacy/consents") {
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: apiEnvelope({ purposes: [purpose] }),
        });
        return true;
      }
      if (pathname === "/api/v1/privacy/notice/acknowledge") {
        expect(request.postDataJSON()).toEqual({
          notice_id: NOTICE_ID,
          notice_content_hash: CONTENT_HASH,
        });
        acknowledgedAt = "2026-07-27T10:00:00Z";
        mutations.push(pathname);
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: apiEnvelope({
            notice: publishedNotice,
            acknowledged_at: acknowledgedAt,
          }),
        });
        return true;
      }
      if (
        pathname === `/api/v1/privacy/consents/${PURPOSE_ID}/grant` ||
        pathname === `/api/v1/privacy/consents/${PURPOSE_ID}/withdraw`
      ) {
        expect(request.postDataJSON()).toEqual({});
        const grant = pathname.endsWith("/grant");
        const occurredAt = grant
          ? "2026-07-27T10:01:00Z"
          : "2026-07-27T10:02:00Z";
        purpose = {
          ...purpose,
          granted: grant,
          state_version: purpose.state_version + 1,
          updated_at: occurredAt,
          history: [
            ...purpose.history,
            {
              id: grant
                ? "e5000000-0000-4000-8000-000000000001"
                : "e5000000-0000-4000-8000-000000000002",
              action: grant ? "grant" : "withdraw",
              purpose_version: 1,
              occurred_at: occurredAt,
            },
          ],
        };
        mutations.push(pathname);
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: apiEnvelope(purpose),
        });
        return true;
      }
      return false;
    },
  });

  await page.goto("/privacy");
  await expect(
    page.getByRole("heading", {
      name: "Gizlilik ve isteğe bağlı onaylar",
    }),
  ).toBeVisible();
  await expect(page.getByText(CONTENT_HASH, { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Okuduğumu kaydet" }).click();
  await expect(page.getByRole("status")).toContainText(
    "bu bildirim sürümü ve içerik özetiyle",
  );

  await page
    .getByRole("button", { name: "Bu amaç için onay ver" })
    .click();
  await page
    .getByRole("dialog", { name: "İsteğe bağlı onay ver" })
    .getByRole("button", { name: "Bu amaç için onay ver" })
    .click();
  await expect(page.getByRole("status")).toContainText(
    "isteğe bağlı onayınız kaydedildi",
  );

  await page.getByRole("button", { name: "Onayı geri çek" }).click();
  await page
    .getByRole("dialog", { name: "İsteğe bağlı onayı geri çek" })
    .getByRole("button", { name: "Onayı geri çek" })
    .click();
  await expect(page.getByRole("status")).toContainText(
    "isteğe bağlı onayınız geri çekildi",
  );
  expect(purpose.history.map((item) => item.action)).toEqual([
    "grant",
    "withdraw",
  ]);
  expect(mutations).toEqual([
    "/api/v1/privacy/notice/acknowledge",
    `/api/v1/privacy/consents/${PURPOSE_ID}/grant`,
    `/api/v1/privacy/consents/${PURPOSE_ID}/withdraw`,
  ]);
});

test("tenant admin publishes a notice, inventories retention metadata, and reads setup readiness", async ({
  context,
  page,
}) => {
  const adminUser = {
    ...employeeUser,
    id: "e6000000-0000-4000-8000-000000000001",
    membership_id: "e6100000-0000-4000-8000-000000000001",
    email: "admin@phase11.example",
    full_name: "Maya Stone",
    roles: [
      {
        id: "e6200000-0000-4000-8000-000000000001",
        code: "tenant_admin",
        name: "Tenant yöneticisi",
        scope_type: "tenant",
      },
    ],
    permissions: [
      "dashboard:read:own",
      "organization:read:tenant",
      "organization:update:tenant",
      "user:read:tenant",
      "privacy_compliance:read:tenant",
      "privacy_notice:manage:tenant",
      "retention_policy:manage:tenant",
    ],
    permission_version: 4,
  };
  let notice:
    | (typeof publishedNotice & {
        acknowledged_count: number;
        eligible_count: number;
      })
    | null = null;
  let retentionPolicy: {
    id: string;
    data_category: "employee_records";
    legal_basis_note: string;
    retention_days: number;
    anchor: "employment_end_date";
    action: "review";
    status: "draft";
    version: number;
    created_at: string;
    updated_at: string;
  } | null = null;
  const mutations: string[] = [];

  await installTenantSession({
    context,
    page,
    user: adminUser,
    handleApi: async (route, request, url) => {
      const { pathname } = url;
      if (
        pathname === "/api/v1/privacy/manage/notices" &&
        request.method() === "GET"
      ) {
        expect(url.searchParams.get("limit")).toBe("50");
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: apiEnvelope(
            notice ? [{ ...notice, body: undefined }] : [],
          ),
        });
        return true;
      }
      if (
        pathname === "/api/v1/privacy/manage/notices" &&
        request.method() === "POST"
      ) {
        expect(request.postDataJSON()).toEqual({
          title: "Çalışan gizlilik bildirimi",
          body: "Veriler yalnız açık iş amaçları için işlenir.",
          locale: "tr-TR",
        });
        notice = {
          ...publishedNotice,
          status: "draft",
          published_at: null,
          body: "Veriler yalnız açık iş amaçları için işlenir.",
          acknowledged_count: 0,
          eligible_count: 12,
        };
        mutations.push(pathname);
        await route.fulfill({
          status: 201,
          contentType: "application/json",
          body: apiEnvelope(notice),
        });
        return true;
      }
      if (
        pathname === `/api/v1/privacy/manage/notices/${NOTICE_ID}/publish`
      ) {
        expect(request.postDataJSON()).toEqual({ expected_revision: 1 });
        if (!notice) throw new Error("notice draft missing");
        notice = {
          ...notice,
          status: "published",
          published_at: "2026-07-27T12:00:00Z",
          updated_at: "2026-07-27T12:00:00Z",
        };
        mutations.push(pathname);
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: apiEnvelope(notice),
        });
        return true;
      }
      if (
        pathname === "/api/v1/privacy/manage/retention-policies" &&
        request.method() === "GET"
      ) {
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: apiEnvelope(retentionPolicy ? [retentionPolicy] : []),
        });
        return true;
      }
      if (
        pathname === "/api/v1/privacy/manage/retention-policies" &&
        request.method() === "POST"
      ) {
        expect(request.postDataJSON()).toEqual({
          data_category: "employee_records",
          legal_basis_note: "İş ilişkisi sonrası yasal saklama incelemesi",
          retention_days: 365,
          anchor: "employment_end_date",
          action: "review",
          status: "draft",
        });
        retentionPolicy = {
          id: POLICY_ID,
          ...request.postDataJSON(),
          version: 1,
          created_at: "2026-07-27T12:10:00Z",
          updated_at: "2026-07-27T12:10:00Z",
        };
        mutations.push(pathname);
        await route.fulfill({
          status: 201,
          contentType: "application/json",
          body: apiEnvelope(retentionPolicy),
        });
        return true;
      }
      if (
        pathname ===
        "/api/v1/privacy/manage/retention-policies/dry-run"
      ) {
        expect(request.postDataJSON()).toEqual({ policy_ids: [POLICY_ID] });
        mutations.push(pathname);
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: apiEnvelope({
            as_of: "2026-07-27T12:15:00Z",
            items: [
              {
                policy_id: POLICY_ID,
                data_category: "employee_records",
                retention_days: 365,
                anchor: "employment_end_date",
                action: "review",
                status: "draft",
                policy_version: 1,
                cutoff_at: "2025-07-27T12:15:00Z",
                count: 7,
              },
            ],
          }),
        });
        return true;
      }
      if (pathname === "/api/v1/tenant/readiness") {
        const evaluatedAt = "2026-07-27T12:20:00Z";
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: apiEnvelope({
            overall_state: "ready",
            evaluated_at: evaluatedAt,
            items: [
              ["default_legal_entity", "ready", 1, "/organization"],
              ["organization_structure", "ready", null, "/organization"],
              ["active_tenant_administrator", "ready", 1, "/users"],
              ["employee_master_data", "ready", 1, "/employees"],
              ["leave_configuration", "ready", null, "/leave/admin"],
              ["document_configuration", "ready", 1, null],
              ["privacy_notice", "ready", 1, "/privacy/manage"],
              ["feature_dependencies", "ready", null, null],
              ["notification_delivery", "not_applicable", null, null],
            ].map(([key, state, count, remediation_route]) => ({
              key,
              state,
              count,
              remediation_route,
              evaluated_at: evaluatedAt,
            })),
          }),
        });
        return true;
      }
      return false;
    },
  });

  await page.goto("/privacy/manage");
  await expect(
    page.getByRole("heading", { name: "Gizlilik uyumu" }),
  ).toBeVisible();
  await page.getByLabel("Başlık").fill("Çalışan gizlilik bildirimi");
  await page
    .getByLabel("Bildirim metni")
    .fill("Veriler yalnız açık iş amaçları için işlenir.");
  await page.getByRole("button", { name: "Taslak oluştur" }).click();
  await expect(
    page.getByText("Çalışan gizlilik bildirimi", { exact: true }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Yayınla" }).click();
  await page
    .getByRole("dialog", { name: "Gizlilik bildirimini yayınla" })
    .getByRole("button", { name: "Değişmez sürümü yayınla" })
    .click();
  await expect(
    page.getByText(
      "Bildirim için değişmez sürüm yayınlama işlemi tamamlandı. Güncel yaşam döngüsü listede gösteriliyor.",
      { exact: true },
    ),
  ).toBeVisible();

  await page.getByRole("tab", { name: "Saklama politikaları" }).click();
  await page
    .getByLabel("Hukuki / politika dayanağı notu")
    .fill("İş ilişkisi sonrası yasal saklama incelemesi");
  await page.getByRole("button", { name: "Politika oluştur" }).click();
  await expect(
    page.getByText("Saklama politikası metadatası oluşturuldu.", {
      exact: true,
    }),
  ).toBeVisible();
  await page.getByRole("checkbox", { name: "Envantere seç" }).check();
  await page
    .getByRole("button", { name: "Sayım envanterini çalıştır" })
    .click();
  await expect(
    page.getByRole("heading", { name: "Saklama envanteri" }),
  ).toBeVisible();
  await expect(page.getByText(/7 kayıt/)).toBeVisible();

  await page.goto("/setup");
  await expect(
    page.getByRole("heading", { name: "Kurulum hazırlığı" }),
  ).toBeVisible();
  await expect(page.getByText("Kurulum kontrolleri hazır")).toBeVisible();
  await expect(page.getByText("0", { exact: true }).first()).toBeVisible();

  expect(mutations).toEqual([
    "/api/v1/privacy/manage/notices",
    `/api/v1/privacy/manage/notices/${NOTICE_ID}/publish`,
    "/api/v1/privacy/manage/retention-policies",
    "/api/v1/privacy/manage/retention-policies/dry-run",
  ]);
});
