import { expect, test } from "@playwright/test";

import {
  apiEnvelope,
  installTenantSession,
} from "./support/tenant-session";

const EMPLOYEE_ID = "c1000000-0000-4000-8000-000000000001";
const REQUEST_ID = "c2000000-0000-4000-8000-000000000001";
const DOCUMENT_REQUEST_ID = "c3000000-0000-4000-8000-000000000001";
const ANNOUNCEMENT_ID = "c4000000-0000-4000-8000-000000000001";
const NOTIFICATION_ID = "c5000000-0000-4000-8000-000000000001";

const employeeUser = {
  id: "c6000000-0000-4000-8000-000000000001",
  membership_id: "c6100000-0000-4000-8000-000000000001",
  tenant_id: "c6200000-0000-4000-8000-000000000001",
  email: "employee@phase11.example",
  full_name: "Ece Çalışkan",
  tenant: { slug: "phase11", name: "Phase 11" },
  workspace_scope: "tenant",
  roles: [
    {
      id: "c6300000-0000-4000-8000-000000000001",
      code: "employee",
      name: "Çalışan",
      scope_type: "tenant",
    },
  ],
  permissions: [
    "dashboard:read:own",
    "self_service:read:own",
    "request:read:own",
    "document_request:create:own",
    "document_request:read:own",
    "announcement:read:own",
    "notification:read:own",
  ],
  permission_version: 2,
};

const unifiedRequest = {
  id: REQUEST_ID,
  kind: "document",
  status: "submitted",
  title: "Çalışma belgesi",
  requester_employee_id: EMPLOYEE_ID,
  requester_name: "Ece Çalışkan",
  submitted_at: "2026-07-27T09:00:00Z",
  updated_at: "2026-07-27T09:00:00Z",
  version: 1,
  start_date: null,
  end_date: null,
  counted_days: null,
  changed_fields: [],
  document_request_type: "employment_letter",
  timeline: [
    {
      event_type: "submitted",
      status: "submitted",
      occurred_at: "2026-07-27T09:00:00Z",
    },
  ],
};

const documentRequest = {
  id: DOCUMENT_REQUEST_ID,
  employee_id: EMPLOYEE_ID,
  employee_name: "Ece Çalışkan",
  request_type: "employment_letter",
  status: "submitted",
  version: 1,
  resolution_reason: null as string | null,
  decided_at: null as string | null,
  created_at: "2026-07-27T09:00:00Z",
  updated_at: "2026-07-27T09:00:00Z",
  timeline: [
    {
      event_type: "submitted",
      status: "submitted",
      occurred_at: "2026-07-27T09:00:00Z",
    },
  ],
};

const announcementSummary = {
  id: ANNOUNCEMENT_ID,
  title: "Acil durum tatbikatı",
  is_critical: true,
  status: "published",
  version: 1,
  published_at: "2026-07-27T08:00:00Z" as string | null,
  archived_at: null,
  read_at: null as string | null,
  acknowledged_at: null as string | null,
  created_at: "2026-07-26T08:00:00Z",
  updated_at: "2026-07-27T08:00:00Z",
};

const notification = {
  id: NOTIFICATION_ID,
  notification_type: "document_request.submitted",
  title: "Belge talebiniz alındı",
  body: "Çalışma belgesi talebiniz HR kuyruğuna iletildi.",
  portal_path: `/requests/${REQUEST_ID}`,
  read_at: null as string | null,
  version: 1,
  created_at: "2026-07-27T09:01:00Z",
};

test("employee home, requests, critical announcements, and notifications preserve own scope", async ({
  context,
  page,
}) => {
  const mutationBodies: Array<{ path: string; body: unknown }> = [];
  let announcement = {
    ...announcementSummary,
    body: "Saat 15.00'te güvenli toplanma alanına ilerleyin.",
    targets: null,
  };

  await installTenantSession({
    context,
    page,
    user: employeeUser,
    handleApi: async (route, request, url) => {
      const { pathname } = url;
      if (pathname === "/api/v1/self-service/home") {
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: apiEnvelope({
            work: {
              employee_id: EMPLOYEE_ID,
              display_name: "Ece Çalışkan",
              employee_number: "WF-101",
              status: "active",
              department_name: "Mühendislik",
              branch_name: "İstanbul",
              position_title: "Yazılım Mühendisi",
              employment_start_date: "2025-01-06",
            },
            leave_balances: [
              {
                leave_type_id: "c7000000-0000-4000-8000-000000000001",
                leave_type_name: "Yıllık izin",
                period_year: 2026,
                available_days: "12.5",
              },
            ],
            leave_request_path: "/leave",
            requests_path: "/requests",
            recent_requests: [unifiedRequest],
            document_summary: {
              missing: 0,
              available: 2,
              expiring: 0,
              expired: 0,
            },
            announcements: [announcementSummary],
            unread_notification_count: 1,
            notifications: [notification],
          }),
        });
        return true;
      }
      if (pathname === "/api/v1/requests") {
        expect(url.searchParams.get("limit")).toBe("30");
        expect(url.searchParams.has("scope")).toBe(false);
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: apiEnvelope([unifiedRequest], {
            limit: 30,
            next_cursor: null,
          }),
        });
        return true;
      }
      if (pathname === `/api/v1/requests/${REQUEST_ID}`) {
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: apiEnvelope(unifiedRequest),
        });
        return true;
      }
      if (
        pathname === "/api/v1/document-requests" &&
        request.method() === "POST"
      ) {
        expect(request.headers()["x-idempotency-key"]).toMatch(
          /^[0-9a-f-]{36}$/i,
        );
        expect(request.postDataJSON()).toEqual({
          request_type: "employment_letter",
        });
        mutationBodies.push({
          path: pathname,
          body: request.postDataJSON(),
        });
        await route.fulfill({
          status: 201,
          contentType: "application/json",
          body: apiEnvelope(documentRequest),
        });
        return true;
      }
      if (pathname === "/api/v1/announcements") {
        expect(url.searchParams.get("scope")).toBe("own");
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: apiEnvelope([announcementSummary], {
            limit: 30,
            next_cursor: null,
          }),
        });
        return true;
      }
      if (
        pathname === `/api/v1/announcements/${ANNOUNCEMENT_ID}` &&
        request.method() === "GET"
      ) {
        expect(url.searchParams.get("scope")).toBe("own");
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: apiEnvelope(announcement),
        });
        return true;
      }
      if (
        pathname ===
          `/api/v1/announcements/${ANNOUNCEMENT_ID}/read` ||
        pathname === `/api/v1/announcements/${ANNOUNCEMENT_ID}/ack`
      ) {
        const isAck = pathname.endsWith("/ack");
        expect(request.postDataJSON()).toEqual({
          expected_version: announcement.version,
        });
        announcement = {
          ...announcement,
          version: announcement.version + 1,
          read_at: announcement.read_at ?? "2026-07-27T10:00:00Z",
          acknowledged_at: isAck
            ? "2026-07-27T10:01:00Z"
            : announcement.acknowledged_at,
          updated_at: isAck
            ? "2026-07-27T10:01:00Z"
            : "2026-07-27T10:00:00Z",
        };
        mutationBodies.push({
          path: pathname,
          body: request.postDataJSON(),
        });
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: apiEnvelope(announcement),
        });
        return true;
      }
      if (pathname === "/api/v1/notifications") {
        const limit = Number(url.searchParams.get("limit"));
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: apiEnvelope({
            items: [notification],
            next_cursor: null,
            unread_count: notification.read_at ? 0 : 1,
          }),
        });
        expect(limit === 1 || limit === 30).toBe(true);
        return true;
      }
      if (
        pathname === `/api/v1/notifications/${NOTIFICATION_ID}/read`
      ) {
        expect(request.postDataJSON()).toEqual({ expected_version: 1 });
        notification.read_at = "2026-07-27T10:02:00Z";
        notification.version = 2;
        mutationBodies.push({
          path: pathname,
          body: request.postDataJSON(),
        });
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: apiEnvelope(notification),
        });
        return true;
      }
      return false;
    },
  });

  await page.goto("/home");
  await expect(
    page.getByRole("heading", { name: "Merhaba, Ece Çalışkan" }),
  ).toBeVisible();
  await expect(page.getByText("12,5", { exact: true })).toBeVisible();

  await page.goto("/requests");
  await expect(
    page.getByRole("heading", { name: "Talepler", exact: true }),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "Belge talebi gönder" })
    .click();
  await expect(
    page.getByText("Belge talebiniz HR ekibine gönderildi.", {
      exact: true,
    }),
  ).toBeVisible();

  await page.goto(`/requests/${REQUEST_ID}`);
  await expect(
    page.getByRole("heading", { name: "Çalışma belgesi" }),
  ).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "Zaman çizelgesi", exact: true }),
  ).toBeVisible();

  await page.goto("/announcements");
  await expect(
    page.getByRole("heading", { name: "Duyurular", exact: true }),
  ).toBeVisible();
  await expect(
    page.getByText("Acil durum tatbikatı", { exact: true }),
  ).toBeVisible();

  await page.goto(`/announcements/${ANNOUNCEMENT_ID}`);
  await expect(
    page.getByRole("heading", { name: "Acil durum tatbikatı" }),
  ).toBeVisible();
  await expect.poll(() => announcement.version).toBe(2);
  await page
    .getByRole("button", { name: "Okudum ve onaylıyorum" })
    .click();
  await expect(
    page.getByText(
      "Kritik duyuruyu okuduğunuz kaydedildi. Bu onay geri alınamaz.",
      { exact: true },
    ),
  ).toBeVisible();

  await page.goto("/notifications");
  await expect(
    page.getByRole("heading", { name: "Bildirimler", exact: true }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Aç" }).click();
  await expect(page).toHaveURL(new RegExp(`/requests/${REQUEST_ID}$`));

  expect(mutationBodies.map((entry) => entry.path)).toEqual([
    "/api/v1/document-requests",
    `/api/v1/announcements/${ANNOUNCEMENT_ID}/read`,
    `/api/v1/announcements/${ANNOUNCEMENT_ID}/ack`,
    `/api/v1/notifications/${NOTIFICATION_ID}/read`,
  ]);
});

test("HR resolves a document request and publishes a targeted critical announcement", async ({
  context,
  page,
}) => {
  const ROLE_ID = "c8000000-0000-4000-8000-000000000001";
  const hrUser = {
    ...employeeUser,
    id: "c9000000-0000-4000-8000-000000000001",
    membership_id: "c9100000-0000-4000-8000-000000000001",
    email: "hr@phase11.example",
    full_name: "Deniz İnsan",
    roles: [
      {
        id: "c9200000-0000-4000-8000-000000000001",
        code: "hr_specialist",
        name: "İK uzmanı",
        scope_type: "tenant",
      },
    ],
    permissions: [
      "dashboard:read:own",
      "employee:read:tenant",
      "employee:update:tenant",
      "request:read:tenant",
      "document_request:manage:tenant",
      "announcement:manage:tenant",
    ],
    permission_version: 3,
  };
  let pendingDocumentRequest = { ...documentRequest };
  let managedAnnouncement:
    | (typeof announcementSummary & {
        body: string;
        targets: {
          role_ids: string[];
          department_ids: string[];
          branch_ids: string[];
        };
      })
    | null = null;
  const mutations: string[] = [];

  await installTenantSession({
    context,
    page,
    user: hrUser,
    handleApi: async (route, request, url) => {
      const { pathname } = url;
      if (
        pathname === "/api/v1/document-requests" &&
        request.method() === "GET"
      ) {
        expect(url.searchParams.get("scope")).toBe("hr");
        const rows =
          pendingDocumentRequest.status === url.searchParams.get("status")
            ? [pendingDocumentRequest]
            : [];
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: apiEnvelope(rows, { limit: 30, next_cursor: null }),
        });
        return true;
      }
      if (
        pathname ===
          `/api/v1/document-requests/${DOCUMENT_REQUEST_ID}/resolve`
      ) {
        expect(request.postDataJSON()).toEqual({
          expected_version: 1,
          reason: "İmzalı belge hazır",
        });
        pendingDocumentRequest = {
          ...pendingDocumentRequest,
          status: "resolved",
          version: 2,
          resolution_reason: "İmzalı belge hazır",
          decided_at: "2026-07-27T11:00:00Z",
          updated_at: "2026-07-27T11:00:00Z",
          timeline: [
            ...pendingDocumentRequest.timeline,
            {
              event_type: "resolved",
              status: "resolved",
              occurred_at: "2026-07-27T11:00:00Z",
            },
          ],
        };
        mutations.push(pathname);
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: apiEnvelope(pendingDocumentRequest),
        });
        return true;
      }
      if (pathname === "/api/v1/employee-profile-change-requests") {
        expect(url.searchParams.get("status")).toBe("submitted");
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: apiEnvelope([], { limit: 25, next_cursor: null }),
        });
        return true;
      }
      if (pathname === "/api/v1/announcements/target-options") {
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: apiEnvelope({
            roles: [{ id: ROLE_ID, label: "Çalışan" }],
            departments: [],
            branches: [],
          }),
        });
        return true;
      }
      if (
        pathname === "/api/v1/announcements" &&
        request.method() === "GET"
      ) {
        expect(url.searchParams.get("scope")).toBe("manage");
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: apiEnvelope(
            managedAnnouncement
              ? [
                  {
                    ...managedAnnouncement,
                    body: undefined,
                    targets: undefined,
                  },
                ]
              : [],
            {
              limit: 30,
              next_cursor: null,
            },
          ),
        });
        return true;
      }
      if (
        pathname === "/api/v1/announcements" &&
        request.method() === "POST"
      ) {
        expect(request.postDataJSON()).toEqual({
          title: "Zorunlu güvenlik eğitimi",
          body: "Eğitimi cuma gününe kadar tamamlayın.",
          is_critical: true,
          targets: {
            role_ids: [ROLE_ID],
            department_ids: [],
            branch_ids: [],
          },
        });
        managedAnnouncement = {
          ...announcementSummary,
          title: "Zorunlu güvenlik eğitimi",
          status: "draft",
          published_at: null,
          body: "Eğitimi cuma gününe kadar tamamlayın.",
          targets: {
            role_ids: [ROLE_ID],
            department_ids: [],
            branch_ids: [],
          },
        };
        mutations.push(pathname);
        await route.fulfill({
          status: 201,
          contentType: "application/json",
          body: apiEnvelope(managedAnnouncement),
        });
        return true;
      }
      if (
        pathname === `/api/v1/announcements/${ANNOUNCEMENT_ID}/publish`
      ) {
        expect(request.postDataJSON()).toEqual({ expected_version: 1 });
        if (!managedAnnouncement) throw new Error("draft missing");
        managedAnnouncement = {
          ...managedAnnouncement,
          status: "published",
          version: 2,
          published_at: "2026-07-27T11:30:00Z",
          updated_at: "2026-07-27T11:30:00Z",
        };
        mutations.push(pathname);
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: apiEnvelope(managedAnnouncement),
        });
        return true;
      }
      return false;
    },
  });

  await page.goto("/hr/requests");
  await expect(
    page.getByRole("heading", { name: "Profil ve belge talepleri" }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Karar ver" }).click();
  await page.getByLabel("Gerekçe").fill("  İmzalı belge hazır  ");
  await page
    .getByRole("button", { name: "Çözüldü olarak işaretle" })
    .click();
  await expect(
    page.getByText("Belge talebi çözüldü olarak kaydedildi.", {
      exact: true,
    }),
  ).toBeVisible();

  await page.goto("/announcements/manage");
  await expect(
    page.getByRole("heading", { name: "Duyurular", exact: true }),
  ).toBeVisible();
  await page.getByLabel("Başlık").fill("Zorunlu güvenlik eğitimi");
  await page
    .getByLabel("Duyuru metni")
    .fill("Eğitimi cuma gününe kadar tamamlayın.");
  await page
    .getByRole("checkbox", {
      name: "Çalışanın tek yönlü okudum onayı",
    })
    .check();
  await page
    .getByRole("checkbox", { name: "Çalışan", exact: true })
    .check();
  await page.getByRole("button", { name: "Taslak oluştur" }).click();
  await expect(
    page.getByText("Zorunlu güvenlik eğitimi", { exact: true }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Yayınla" }).click();
  await expect(
    page.getByText("Duyuru hedef kitlesi sabitlenerek yayınlandı.", {
      exact: true,
    }),
  ).toBeVisible();

  expect(mutations).toEqual([
    `/api/v1/document-requests/${DOCUMENT_REQUEST_ID}/resolve`,
    "/api/v1/announcements",
    `/api/v1/announcements/${ANNOUNCEMENT_ID}/publish`,
  ]);
});
