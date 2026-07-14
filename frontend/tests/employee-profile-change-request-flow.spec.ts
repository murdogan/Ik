import { expect, test, type Page, type Route } from "@playwright/test";

const EMPLOYEE_ID = "e5000000-0000-4000-8000-000000000001";
const STALE_EMPLOYEE_ID = "e5000000-0000-4000-8000-000000000002";
const CANCELLED_REQUEST_ID = "e5100000-0000-4000-8000-000000000001";
const APPROVAL_REQUEST_ID = "e5100000-0000-4000-8000-000000000002";
const STALE_REQUEST_ID = "e5100000-0000-4000-8000-000000000003";
const SENTINEL_REQUEST_ID = "e5100000-0000-4000-8000-000000000004";
const EMPLOYEE_MEMBERSHIP_ID = "e5200000-0000-4000-8000-000000000001";
const HR_MEMBERSHIP_ID = "e5200000-0000-4000-8000-000000000002";
const ROTATED_HR_MEMBERSHIP_ID = "e5200000-0000-4000-8000-000000000003";
const MANAGER_MEMBERSHIP_ID = "e5200000-0000-4000-8000-000000000004";
const RAW_PHONE_BASE = ["+90", "555", "111", "0000"].join("");
const RAW_PHONE_PROPOSED = ["+90", "555", "111", "2233"].join("");

type RequestStatus = "submitted" | "approved" | "rejected" | "cancelled";

function isHrMembership(membershipId: string): boolean {
  return (
    membershipId === HR_MEMBERSHIP_ID ||
    membershipId === ROTATED_HR_MEMBERSHIP_ID
  );
}

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
      request_id: "browser-p4e",
      trace_id: "browser-p4e-trace",
      correlation_id: "browser-p4e",
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
      correlation_id: "browser-p4e",
    },
  });
}

const tenant = {
  slug: "wealthy-falcon-demo",
  name: "Wealthy Falcon HR Demo",
};

const employeeUser = {
  id: "e5300000-0000-4000-8000-000000000001",
  membership_id: EMPLOYEE_MEMBERSHIP_ID,
  tenant_id: "e5400000-0000-4000-8000-000000000001",
  email: "ada.account@wealthyfalcon.demo",
  full_name: "Ada Çalışan",
  tenant,
  workspace_scope: "tenant",
  roles: [
    {
      id: "e5500000-0000-4000-8000-000000000001",
      code: "employee",
      name: "Çalışan",
      scope_type: "tenant",
    },
  ],
  permissions: ["dashboard:read:own", "employee:read:own"],
  permission_version: 3,
};

const hrUser = {
  ...employeeUser,
  id: "e5300000-0000-4000-8000-000000000002",
  membership_id: HR_MEMBERSHIP_ID,
  email: "hr@wealthyfalcon.demo",
  full_name: "Derya İnsan",
  roles: [
    {
      id: "e5500000-0000-4000-8000-000000000002",
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
  permission_version: 9,
};

const rotatedHrUser = {
  ...hrUser,
  id: "e5300000-0000-4000-8000-000000000003",
  membership_id: ROTATED_HR_MEMBERSHIP_ID,
  email: "hr.two@wealthyfalcon.demo",
  full_name: "Selin İnsan",
  permission_version: 10,
};

const managerUser = {
  ...employeeUser,
  id: "e5300000-0000-4000-8000-000000000004",
  membership_id: MANAGER_MEMBERSHIP_ID,
  email: "manager@wealthyfalcon.demo",
  full_name: "Mert Yönetici",
  roles: [
    {
      id: "e5500000-0000-4000-8000-000000000004",
      code: "manager",
      name: "Yönetici",
      scope_type: "tenant",
    },
  ],
  permissions: ["dashboard:read:own", "employee:read:own", "employee:read:team"],
  permission_version: 11,
};

const primaryEmployee = {
  id: EMPLOYEE_ID,
  employee_number: "WF-001",
  first_name: "Ada",
  last_name: "Yılmaz",
  email: "ada@wealthyfalcon.demo",
  status: "active",
};

const staleEmployee = {
  id: STALE_EMPLOYEE_ID,
  employee_number: "WF-002",
  first_name: "Ece",
  last_name: "Çalışkan",
  email: "ece@wealthyfalcon.demo",
  status: "active",
};

function commonRequest(
  id: string,
  status: RequestStatus,
  version: number,
  submittedAt: string,
  changedFields: string[],
  rejectionReason: string | null = null,
) {
  return {
    id,
    status,
    version,
    submitted_at: submittedAt,
    decided_at:
      status === "approved" || status === "rejected"
        ? "2026-07-14T12:00:00Z"
        : null,
    cancelled_at: status === "cancelled" ? "2026-07-14T09:30:00Z" : null,
    rejection_reason: status === "rejected" ? rejectionReason : null,
    changed_fields: changedFields,
  };
}

function ownProtected(displayValue: string | null) {
  return displayValue === null
    ? { visibility: "unavailable", display_value: null }
    : { visibility: "masked", display_value: displayValue };
}

test("employee request and HR decision remain tenant-safe across session rotation", async ({
  context,
  page,
}) => {
  const staleOwnPageGate = deferred();
  const staleApprovalGate = deferred();
  let activeUser = employeeUser;
  let nextUser: typeof employeeUser | null = null;
  let accessToken = "";
  let refreshCount = 0;
  let oldRequestStatus: "submitted" | "cancelled" = "submitted";
  let approvalRequestStatus: "absent" | "submitted" | "approved" = "absent";
  let staleRequestStatus: "submitted" | "rejected" = "submitted";
  let staleProfileDetected = false;
  let deferNextOwnPage = false;
  let staleOwnPageReads = 0;
  let hrQueueRequests = 0;
  let p4eClientRequests = 0;
  let unauthorizedHrRequests = 0;
  let employee360Reads = 0;
  let deferNextApproval = false;
  let delayedApprovalAttempts = 0;
  let malformedOwnDetailPending = true;
  let mismatchedOwnDetailPending = true;
  let incoherentHrDetailPending = true;
  let mismatchedHrReloadPending = false;
  let createBody: unknown = null;
  let rejectBody: unknown = null;
  let approvedPreferredName = "Ada";
  let approvedPhone = RAW_PHONE_BASE;
  let approvedBirthDate = "1992-04-10";

  function ownCancelledRequest() {
    return {
      ...commonRequest(
        CANCELLED_REQUEST_ID,
        oldRequestStatus,
        oldRequestStatus === "submitted" ? 1 : 2,
        "2026-07-14T09:00:00Z",
        ["phone"],
      ),
      employee_id: EMPLOYEE_ID,
      changes: {
        preferred_name: null,
        phone: {
          previous_value: ownProtected("••••••••00"),
          proposed_value: ownProtected(null),
        },
        birth_date: null,
      },
    };
  }

  function ownApprovalRequest() {
    const status = approvalRequestStatus === "approved" ? "approved" : "submitted";
    return {
      ...commonRequest(
        APPROVAL_REQUEST_ID,
        status,
        status === "approved" ? 2 : 1,
        "2026-07-14T10:00:00Z",
        ["preferred_name", "phone", "birth_date"],
      ),
      employee_id: EMPLOYEE_ID,
      changes: {
        preferred_name: { previous_value: "Ada", proposed_value: "Ada Deniz" },
        phone: {
          previous_value: ownProtected("••••••••00"),
          proposed_value: ownProtected("••••••••33"),
        },
        birth_date: {
          previous_value: ownProtected("••••-04-10"),
          proposed_value: ownProtected("••••-05-11"),
        },
      },
    };
  }

  function ownSentinelRequest() {
    return {
      ...commonRequest(
        SENTINEL_REQUEST_ID,
        "rejected",
        2,
        "2026-06-01T08:00:00Z",
        ["preferred_name"],
        "Eksik belge",
      ),
      employee_id: EMPLOYEE_ID,
      changes: {
        preferred_name: {
          previous_value: "Ada",
          proposed_value: "ESKİ OTURUM İÇERİĞİ",
        },
        phone: null,
        birth_date: null,
      },
    };
  }

  function hrApprovalDetail() {
    const approved = approvalRequestStatus === "approved";
    return {
      ...commonRequest(
        APPROVAL_REQUEST_ID,
        approved ? "approved" : "submitted",
        approved ? 2 : 1,
        "2026-07-14T10:00:00Z",
        ["preferred_name", "phone", "birth_date"],
      ),
      employee: primaryEmployee,
      base_profile_version: 2,
      current_profile_version: approved ? 3 : 2,
      profile_is_stale: false,
      changes: {
        preferred_name: {
          base_value: "Ada",
          current_value: approved ? "Ada Deniz" : "Ada",
          proposed_value: "Ada Deniz",
          current_matches_base: !approved,
        },
        phone: {
          base_value: RAW_PHONE_BASE,
          current_value: approved ? RAW_PHONE_PROPOSED : RAW_PHONE_BASE,
          proposed_value: RAW_PHONE_PROPOSED,
          current_matches_base: !approved,
        },
        birth_date: {
          base_value: "1992-04-10",
          current_value: approved ? "1993-05-11" : "1992-04-10",
          proposed_value: "1993-05-11",
          current_matches_base: !approved,
        },
      },
    };
  }

  function hrStaleDetail() {
    const rejected = staleRequestStatus === "rejected";
    return {
      ...commonRequest(
        STALE_REQUEST_ID,
        rejected ? "rejected" : "submitted",
        rejected ? 2 : 1,
        "2026-07-14T08:00:00Z",
        ["preferred_name"],
        rejected ? "Kaynak belge gerekli" : null,
      ),
      employee: staleEmployee,
      base_profile_version: 4,
      current_profile_version: staleProfileDetected ? 5 : 4,
      profile_is_stale: !rejected && staleProfileDetected,
      changes: {
        preferred_name: {
          base_value: "Ece",
          current_value: staleProfileDetected ? "Ece Güncel" : "Ece",
          proposed_value: null,
          current_matches_base: !staleProfileDetected,
        },
        phone: null,
        birth_date: null,
      },
    };
  }

  function hrSummary(
    detail:
      | ReturnType<typeof hrApprovalDetail>
      | ReturnType<typeof hrStaleDetail>,
  ) {
    const { changes: _changes, ...summary } = detail;
    void _changes;
    return summary;
  }

  function ownProfileResponse() {
    return {
      availability: "available",
      membership_id: EMPLOYEE_MEMBERSHIP_ID,
      employee_id: EMPLOYEE_ID,
      profile: {
        core: primaryEmployee,
        personal: {
          preferred_name: approvedPreferredName,
          phone: ownProtected(
            approvedPhone.endsWith("2233")
              ? "••••••••33"
              : "••••••••00",
          ),
          birth_date: ownProtected(
            approvedBirthDate === "1993-05-11" ? "••••-05-11" : "••••-04-10",
          ),
        },
        employment: {
          employment_start_date: "2025-02-03",
          contract_type: "indefinite",
          work_type: "full_time",
        },
        organization: { current_assignment: null },
      },
    };
  }

  function employee360Profile() {
    return {
      core: { ...primaryEmployee, employee_version: 5 },
      personal: {
        preferred_name: approvedPreferredName,
        phone: approvedPhone,
        birth_date: approvedBirthDate,
        version: 3,
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
  }

  await context.addCookies([
    {
      name: "wf_refresh",
      value: "p4e-browser-refresh",
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
      accessToken = `p4e-access-${refreshCount}`;
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

    if (path.includes("profile-change-requests")) {
      p4eClientRequests += 1;
    }

    expect(request.headers().authorization).toMatch(/^Bearer p4e-access-\d+$/);
    const requestMembershipId = activeUser.membership_id;

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

    if (path === "/api/v1/me/employee-profile" && request.method() === "GET") {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: envelope(
          requestMembershipId === EMPLOYEE_MEMBERSHIP_ID
            ? ownProfileResponse()
            : {
                availability: "unavailable",
                membership_id: null,
                employee_id: null,
                profile: null,
              },
        ),
      });
      return;
    }

    if (path === "/api/v1/me/profile-change-requests") {
      if (request.method() === "POST") {
        expect(requestMembershipId).toBe(EMPLOYEE_MEMBERSHIP_ID);
        createBody = request.postDataJSON();
        expect(oldRequestStatus).toBe("cancelled");
        approvalRequestStatus = "submitted";
        await route.fulfill({
          status: 201,
          contentType: "application/json",
          body: envelope(ownApprovalRequest()),
        });
        return;
      }

      expect(request.method()).toBe("GET");
      expect(url.searchParams.get("limit")).toBe("10");
      if (requestMembershipId !== EMPLOYEE_MEMBERSHIP_ID) {
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: envelope([], { limit: 10, next_cursor: null }),
        });
        return;
      }
      if (url.searchParams.get("cursor") === "older-own-page") {
        if (deferNextOwnPage) {
          deferNextOwnPage = false;
          staleOwnPageReads += 1;
          await staleOwnPageGate.wait;
        }
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: envelope([ownSentinelRequest()], {
            limit: 10,
            next_cursor: null,
          }),
        });
        return;
      }
      const requests = [
        ...(approvalRequestStatus === "absent" ? [] : [ownApprovalRequest()]),
        ownCancelledRequest(),
      ];
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: envelope(requests, { limit: 10, next_cursor: "older-own-page" }),
      });
      return;
    }

    const ownRequestMatch = path.match(
      /^\/api\/v1\/me\/profile-change-requests\/([^/]+)(?:\/(cancel))?$/,
    );
    if (ownRequestMatch) {
      expect(requestMembershipId).toBe(EMPLOYEE_MEMBERSHIP_ID);
      const [, requestId, action] = ownRequestMatch;
      if (action === "cancel") {
        expect(request.method()).toBe("POST");
        expect(requestId).toBe(CANCELLED_REQUEST_ID);
        expect(request.postDataJSON()).toEqual({ expected_version: 1 });
        oldRequestStatus = "cancelled";
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: envelope(ownCancelledRequest()),
        });
        return;
      }
      expect(request.method()).toBe("GET");
      const ownRequest =
        requestId === APPROVAL_REQUEST_ID
          ? ownApprovalRequest()
          : ownCancelledRequest();
      const responseRequest =
          requestId === APPROVAL_REQUEST_ID && malformedOwnDetailPending
          ? (() => {
              return {
                ...ownRequest,
                changes: {
                  ...ownRequest.changes,
                  preferred_name: {
                    previous_value: "Ada",
                    proposed_value: "••••",
                  },
                },
              };
            })()
          : requestId === APPROVAL_REQUEST_ID && mismatchedOwnDetailPending
            ? (() => {
                return { ...ownRequest, employee_id: STALE_EMPLOYEE_ID };
              })()
          : ownRequest;
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: envelope(responseRequest),
      });
      return;
    }

    if (path === "/api/v1/employee-profile-change-requests") {
      hrQueueRequests += 1;
      if (!isHrMembership(requestMembershipId)) unauthorizedHrRequests += 1;
      expect(isHrMembership(requestMembershipId)).toBe(true);
      expect(request.method()).toBe("GET");
      expect(url.searchParams.get("limit")).toBe("25");
      const status = url.searchParams.get("status");
      const requests =
        status === "submitted"
          ? [
              ...(staleRequestStatus === "submitted"
                ? [hrSummary(hrStaleDetail())]
                : []),
              ...(approvalRequestStatus === "submitted"
                ? [hrSummary(hrApprovalDetail())]
                : []),
            ]
          : status === "rejected" && staleRequestStatus === "rejected"
            ? [hrSummary(hrStaleDetail())]
            : status === "approved" && approvalRequestStatus === "approved"
              ? [hrSummary(hrApprovalDetail())]
              : [];
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: envelope(requests, { limit: 25, next_cursor: null }),
      });
      return;
    }

    const hrRequestMatch = path.match(
      /^\/api\/v1\/employee-profile-change-requests\/([^/]+)(?:\/(approve|reject))?$/,
    );
    if (hrRequestMatch) {
      if (!isHrMembership(requestMembershipId)) unauthorizedHrRequests += 1;
      expect(isHrMembership(requestMembershipId)).toBe(true);
      const [, requestId, action] = hrRequestMatch;
      if (!action) {
        expect(request.method()).toBe("GET");
        const detail =
          requestId === STALE_REQUEST_ID
            ? hrStaleDetail()
            : hrApprovalDetail();
        const responseDetail =
          requestId === STALE_REQUEST_ID && incoherentHrDetailPending
            ? (() => {
                return {
                  ...detail,
                  current_profile_version: detail.base_profile_version + 1,
                  profile_is_stale: false,
                };
              })()
            : requestId === STALE_REQUEST_ID && mismatchedHrReloadPending
            ? (() => {
                return { ...detail, employee: primaryEmployee };
              })()
            : detail;
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: envelope(responseDetail),
        });
        return;
      }
      expect(request.method()).toBe("POST");
      if (requestId === STALE_REQUEST_ID && action === "approve") {
        expect(request.postDataJSON()).toEqual({ expected_version: 1 });
        staleProfileDetected = true;
        mismatchedHrReloadPending = true;
        await route.fulfill({
          status: 409,
          contentType: "application/json",
          body: errorEnvelope("employee_profile_change_request_stale_profile"),
        });
        return;
      }
      if (requestId === STALE_REQUEST_ID && action === "reject") {
        rejectBody = request.postDataJSON();
        staleRequestStatus = "rejected";
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: envelope(hrStaleDetail()),
        });
        return;
      }
      expect(requestId).toBe(APPROVAL_REQUEST_ID);
      expect(action).toBe("approve");
      expect(request.postDataJSON()).toEqual({ expected_version: 1 });
      if (deferNextApproval) {
        deferNextApproval = false;
        delayedApprovalAttempts += 1;
        await staleApprovalGate.wait;
        await route.fulfill({
          status: 409,
          contentType: "application/json",
          body: errorEnvelope("employee_profile_change_request_conflict"),
        });
        return;
      }
      approvalRequestStatus = "approved";
      approvedPreferredName = "Ada Deniz";
      approvedPhone = RAW_PHONE_PROPOSED;
      approvedBirthDate = "1993-05-11";
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: envelope(hrApprovalDetail()),
      });
      return;
    }

    if (
      path === `/api/v1/employees/${EMPLOYEE_ID}/profile` &&
      request.method() === "GET"
    ) {
      expect(isHrMembership(requestMembershipId)).toBe(true);
      employee360Reads += 1;
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: envelope(employee360Profile()),
      });
      return;
    }

    await route.fulfill({
      status: 404,
      contentType: "application/json",
      body: errorEnvelope("not_found"),
    });
  });

  await page.goto("/profile-change-requests");
  await expect(page).toHaveURL(/\/dashboard$/);
  await expect(
    page.getByRole("heading", { name: "Merhaba, Ada Çalışan" }),
  ).toBeVisible();
  expect(hrQueueRequests).toBe(0);

  const p4eRequestsBeforeManager = p4eClientRequests;
  nextUser = managerUser;
  await page.evaluate(() => window.dispatchEvent(new Event("focus")));
  await expect(page.getByRole("heading", { name: "Merhaba, Mert Yönetici" })).toBeVisible();
  await expect(
    page.getByRole("link", { name: "Değişiklik talepleri", exact: true }),
  ).toHaveCount(0);
  await page.goto("/profile-change-requests");
  await expect(page).toHaveURL(/\/dashboard$/);
  await expect(page.getByRole("heading", { name: "Merhaba, Mert Yönetici" })).toBeVisible();
  expect(p4eClientRequests).toBe(p4eRequestsBeforeManager);

  nextUser = employeeUser;
  await page.evaluate(() => window.dispatchEvent(new Event("focus")));
  await expect(page.getByRole("heading", { name: "Merhaba, Ada Çalışan" })).toBeVisible();

  await page.getByRole("link", { name: "Profilim", exact: true }).click();
  await expect(page.getByRole("heading", { level: 1, name: "Profilim" })).toBeVisible();
  await expect(page.getByRole("heading", { name: "Profil değişiklik taleplerim" })).toBeVisible();
  await expect(page.getByText("••••••••00", { exact: true })).toBeVisible();
  await expect(page.getByText(RAW_PHONE_BASE, { exact: true })).toHaveCount(0);
  await expect(page.getByText("1992-04-10", { exact: true })).toHaveCount(0);

  await page.getByRole("button", { name: "Talebi iptal et", exact: true }).click();
  const cancelDialog = page.getByRole("dialog", {
    name: "Değişiklik talebi iptal edilsin mi?",
  });
  await cancelDialog.getByRole("button", { name: "Talebi iptal et" }).click();
  await expect(
    page.getByText("Değişiklik talebiniz iptal edildi.", { exact: true }),
  ).toBeVisible();

  await page.getByRole("button", { name: "Değişiklik talebi oluştur" }).click();
  const requestForm = page.locator("form").filter({
    has: page.getByRole("button", { name: "Talebi gözden geçir" }),
  });
  const preferredField = requestForm.getByRole("group", { name: "Tercih edilen ad" });
  const phoneField = requestForm.getByRole("group", { name: "Telefon" });
  const birthDateField = requestForm.getByRole("group", { name: "Doğum tarihi" });
  await preferredField.getByLabel("İşlem").selectOption("set");
  await preferredField.getByLabel("Yeni tercih edilen ad").fill("  Ada   Deniz  ");
  await phoneField.getByLabel("İşlem").selectOption("set");
  await expect(phoneField.getByLabel("Yeni telefon")).toHaveValue("");
  await phoneField.getByLabel("Yeni telefon").fill("+90 (555) 111-2233");
  await birthDateField.getByLabel("İşlem").selectOption("set");
  await expect(birthDateField.getByLabel("Yeni doğum tarihi")).toHaveValue("");
  await birthDateField.getByLabel("Yeni doğum tarihi").fill("1993-05-11");
  await requestForm.getByRole("button", { name: "Talebi gözden geçir" }).click();
  const submitDialog = page.getByRole("dialog", {
    name: "Değişiklik talebi gönderilsin mi?",
  });
  await submitDialog.getByRole("button", { name: "Talebi gönder" }).click();
  await expect(
    page.getByText("Değişiklik talebiniz İK onayına gönderildi.", {
      exact: true,
    }),
  ).toBeVisible();
  expect(createBody).toEqual({
    preferred_name: "Ada Deniz",
    phone: "+90 (555) 111-2233",
    birth_date: "1993-05-11",
  });
  await expect(page.getByText("Ada", { exact: true }).first()).toBeVisible();
  await expect(page.getByText("+905551112233", { exact: true })).toHaveCount(0);

  deferNextOwnPage = true;
  await page.getByRole("button", { name: "Daha fazla göster" }).click();
  await expect.poll(() => staleOwnPageReads).toBe(1);

  nextUser = hrUser;
  await page.evaluate(() => window.dispatchEvent(new Event("focus")));
  const queueNavigation = page.getByRole("link", {
    name: "Değişiklik talepleri",
    exact: true,
  });
  await expect(queueNavigation).toBeVisible();
  await queueNavigation.click();
  await expect(page.getByRole("heading", { level: 1, name: "Değişiklik talepleri" })).toBeVisible();
  await expect(page.getByText("+905551112233", { exact: true })).toHaveCount(0);
  await expect(page.getByText("Ada Yılmaz", { exact: true })).toBeVisible();
  await expect(page.getByText("Ece Çalışkan", { exact: true })).toBeVisible();
  await expect(page.getByText(RAW_PHONE_PROPOSED, { exact: true })).toHaveCount(0);
  await expect(page.getByText("+905551112233", { exact: true })).toHaveCount(0);

  const staleResponse = page.waitForResponse(
    (response) =>
      new URL(response.url()).searchParams.get("cursor") === "older-own-page",
  );
  staleOwnPageGate.release();
  await staleResponse;
  await flushClient(page);
  await expect(page.getByText("ESKİ OTURUM İÇERİĞİ", { exact: true })).toHaveCount(0);

  await page
    .getByRole("link", { name: "Ece Çalışkan değişiklik talebini aç" })
    .click();
  await expect(
    page.getByText("Talep ayrıntısı yüklenemedi", { exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Onaylamayı gözden geçir" }),
  ).toHaveCount(0);
  incoherentHrDetailPending = false;
  await page.getByRole("button", { name: "Yeniden dene" }).click();
  await expect(page.getByRole("heading", { level: 1, name: "Ece Çalışkan" })).toBeVisible();
  await expect(page.getByText("Temizlenecek", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Onaylamayı gözden geçir" }).click();
  await page
    .getByRole("dialog", { name: "Talep onaylansın mı?" })
    .getByRole("button", { name: "Talebi onayla" })
    .click();
  await expect(
    page.getByText(/Hiçbir değer uygulanmadı; güncel karşılaştırmayı yükleyip/),
  ).toBeVisible();
  await page.getByRole("button", { name: "Güncel talebi yükle" }).click();
  await expect(
    page.getByText("Talep ayrıntısı yüklenemedi", { exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("heading", { level: 1, name: "Ada Yılmaz" }),
  ).toHaveCount(0);
  mismatchedHrReloadPending = false;
  await page.getByRole("button", { name: "Yeniden dene" }).click();
  await expect(page.getByText("Ece Güncel", { exact: true })).toBeVisible();
  await expect(page.getByText("Temizlenecek", { exact: true })).toBeVisible();
  await page.getByLabel("Ret açıklaması").fill("  Kaynak   belge gerekli  ");
  await page.getByRole("button", { name: "Reddetmeyi gözden geçir" }).click();
  await page
    .getByRole("dialog", { name: "Talep reddedilsin mi?" })
    .getByRole("button", { name: "Talebi reddet" })
    .click();
  await expect(
    page.getByText("Talep reddedildi. Çalışan profili değiştirilmedi.", {
      exact: true,
    }),
  ).toBeVisible();
  expect(rejectBody).toEqual({
    expected_version: 1,
    reason: "Kaynak belge gerekli",
  });

  await page.getByRole("link", { name: "Taleplere dön" }).click();
  await page
    .getByRole("link", { name: "Ada Yılmaz değişiklik talebini aç" })
    .click();
  await expect(page.getByText("+905551112233", { exact: true })).toBeVisible();
  deferNextApproval = true;
  await page.getByRole("button", { name: "Onaylamayı gözden geçir" }).click();
  await page
    .getByRole("dialog", { name: "Talep onaylansın mı?" })
    .getByRole("button", { name: "Talebi onayla" })
    .click();
  await expect.poll(() => delayedApprovalAttempts).toBe(1);

  nextUser = rotatedHrUser;
  await page.evaluate(() => window.dispatchEvent(new Event("focus")));
  await expect(page.getByText("Selin İnsan", { exact: true })).toBeVisible();
  await expect(
    page.getByRole("heading", { level: 1, name: "Ada Yılmaz" }),
  ).toBeVisible();
  await expect(
    page.getByRole("dialog", { name: "Talep onaylansın mı?" }),
  ).toHaveCount(0);
  await expect(
    page.getByRole("button", { name: "Onaylamayı gözden geçir" }),
  ).toBeEnabled();

  const staleDecisionResponse = page.waitForResponse(
    (response) =>
      new URL(response.url()).pathname.endsWith(
        `/${APPROVAL_REQUEST_ID}/approve`,
      ) && response.status() === 409,
  );
  staleApprovalGate.release();
  await staleDecisionResponse;
  await flushClient(page);
  await expect(page.getByText("Karar tamamlanamadı", { exact: true })).toHaveCount(0);
  await expect(
    page.getByRole("button", { name: "Onaylamayı gözden geçir" }),
  ).toBeEnabled();

  await page.getByRole("button", { name: "Onaylamayı gözden geçir" }).click();
  await page
    .getByRole("dialog", { name: "Talep onaylansın mı?" })
    .getByRole("button", { name: "Talebi onayla" })
    .click();
  await expect(
    page.getByText(
      "Talep onaylandı. Kişisel profil sunucudan atomik olarak güncellendi.",
      { exact: true },
    ),
  ).toBeVisible();
  await page.getByRole("link", { name: "Çalışan 360’ı aç" }).click();
  await expect.poll(() => employee360Reads).toBeGreaterThan(0);
  await page.getByRole("tab", { name: "Kişisel" }).click();
  await expect(page.getByLabel("Telefon")).toHaveValue("+905551112233");
  await expect(page.getByLabel("Doğum tarihi")).toHaveValue("1993-05-11");

  nextUser = employeeUser;
  await page.evaluate(() => window.dispatchEvent(new Event("focus")));
  await expect(page).toHaveURL(/\/dashboard$/);
  await page.getByRole("link", { name: "Profilim", exact: true }).click();
  await expect(page.getByText("Ada Deniz", { exact: true }).first()).toBeVisible();
  await expect(page.getByText("••••••••33", { exact: true })).toBeVisible();
  await expect(page.getByText("••••-05-11", { exact: true })).toBeVisible();
  await expect(page.getByText("+905551112233", { exact: true })).toHaveCount(0);
  await expect(page.getByText("Onaylandı", { exact: true })).toBeVisible();
  await expect(page.getByText("İptal edildi", { exact: true })).toBeVisible();

  await page
    .getByRole("button", { name: "Ayrıntıları göster" })
    .first()
    .click();
  await expect(
    page.getByText("Talep ayrıntısı yüklenemedi", { exact: true }),
  ).toBeVisible();
  await expect(page.getByText("+905551110000", { exact: true })).toHaveCount(0);
  malformedOwnDetailPending = false;
  await page.getByRole("button", { name: "Yeniden dene" }).click();
  await expect(
    page.getByText("Talep ayrıntısı yüklenemedi", { exact: true }),
  ).toBeVisible();
  mismatchedOwnDetailPending = false;
  await page.getByRole("button", { name: "Yeniden dene" }).click();
  await expect(page.getByText("••••••••00", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Talep ayrıntısını kapat" }).click();

  await page
    .getByRole("button", { name: "Ayrıntıları göster" })
    .last()
    .click();
  await expect(page.getByText("Temizlenecek", { exact: true })).toBeVisible();
  expect(unauthorizedHrRequests).toBe(0);
});
