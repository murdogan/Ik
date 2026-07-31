import {
  expect,
  test,
  type BrowserContext,
  type Request as PlaywrightRequest,
  type Route,
} from "@playwright/test";

const PLATFORM_ORIGIN = "http://127.0.0.1:3100";

const platformAdmin = {
  id: "f2000000-0000-4000-8000-000000000099",
  email: "platform@wealthyfalcon.demo",
  full_name: "Atlas Platform",
  workspace_scope: "platform",
  roles: [
    {
      id: "f3000000-0000-4000-8000-000000000099",
      code: "super_admin",
      name: "Süper yönetici",
      scope_type: "platform",
    },
  ],
  permissions: ["tenant:read:platform"],
  permission_version: 11,
  authentication_strength: "multi_factor",
};

function envelope(data: unknown, list = false): string {
  return JSON.stringify({
    data,
    meta: {
      request_id: "platform-cross-tab-request",
      trace_id: "platform-cross-tab-trace",
      correlation_id: "platform-cross-tab-correlation",
      ...(list ? { limit: 200, next_cursor: null } : {}),
    },
  });
}

function errorEnvelope(code: string): string {
  return JSON.stringify({
    error: {
      code,
      message: "Request failed",
      details: null,
      correlation_id: "platform-cross-tab-error",
    },
  });
}

function bearerToken(request: PlaywrightRequest): string | null {
  const authorization = request.headers().authorization;
  return authorization?.startsWith("Bearer ")
    ? authorization.slice("Bearer ".length)
    : null;
}

async function exerciseCrossTabRefresh(
  context: BrowserContext,
  { disableWebLocks }: { disableWebLocks: boolean },
): Promise<void> {
  await context.addInitScript(() => {
    const NativeBroadcastChannel = window.BroadcastChannel;
    const recordedMessages: string[] = [];
    Object.defineProperty(window, "__platformSessionBroadcastMessages", {
      configurable: true,
      value: recordedMessages,
    });
    if (typeof NativeBroadcastChannel === "function") {
      class RecordingBroadcastChannel extends NativeBroadcastChannel {
        override postMessage(message: unknown): void {
          recordedMessages.push(JSON.stringify(message));
          super.postMessage(message);
        }
      }
      Object.defineProperty(window, "BroadcastChannel", {
        configurable: true,
        value: RecordingBroadcastChannel,
      });
    }
  });

  if (disableWebLocks) {
    await context.addInitScript(() => {
      Object.defineProperty(navigator, "locks", {
        configurable: true,
        value: undefined,
      });
      if (!localStorage.getItem("wf:platform-session:refresh-lease:v1")) {
        localStorage.setItem(
          "wf:platform-session:refresh-lease:v1",
          JSON.stringify({
            version: 1,
            ownerId: "crashed-platform-tab",
            leaseId: "expired-platform-lease",
            expiresAt: Date.now() - 1,
          }),
        );
      }
    });
  }

  let currentRefreshCredential = "platform-cross-tab-refresh-1";
  let platformRefreshRequests = 0;
  let tenantRefreshRequests = 0;
  let accessExpired = false;
  const initialAccessTokens = new Set<string>();
  const freshAccessTokens = new Set<string>();
  let staleRecoveryRequests = 0;
  let successfulReplays = 0;
  let releaseStaleRecoveryRequests = () => {};
  const bothStaleRecoveryRequests = new Promise<void>((resolve) => {
    releaseStaleRecoveryRequests = resolve;
  });

  await context.addCookies([
    {
      name: "wf_platform_refresh",
      value: currentRefreshCredential,
      url: PLATFORM_ORIGIN,
      httpOnly: true,
      sameSite: "Lax",
    },
    {
      name: "wf_refresh",
      value: "tenant-refresh-must-remain-unused",
      url: PLATFORM_ORIGIN,
      httpOnly: true,
      sameSite: "Lax",
    },
  ]);

  await context.route("**/api/v1/**", async (route: Route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname;

    if (path === "/api/v1/auth/refresh") {
      tenantRefreshRequests += 1;
      await route.fulfill({ status: 418 });
      return;
    }

    if (path === "/api/v1/platform/auth/refresh") {
      platformRefreshRequests += 1;
      const cookie = request.headers().cookie ?? "";
      if (!cookie.includes(`wf_platform_refresh=${currentRefreshCredential}`)) {
        await route.fulfill({
          status: 401,
          contentType: "application/json",
          body: errorEnvelope("platform_refresh_reused"),
        });
        return;
      }

      const accessToken = `platform-cross-tab-${accessExpired ? "fresh" : "initial"}-${platformRefreshRequests}`;
      (accessExpired ? freshAccessTokens : initialAccessTokens).add(accessToken);
      currentRefreshCredential = `platform-cross-tab-refresh-${platformRefreshRequests + 1}`;

      // Keep the owner in flight long enough for the other document to become
      // a waiter. A second uncoordinated request would reuse the old cookie.
      await new Promise((resolve) => setTimeout(resolve, 150));
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        headers: {
          "set-cookie": `wf_platform_refresh=${currentRefreshCredential}; Path=/; HttpOnly; SameSite=Lax; Max-Age=3600`,
        },
        body: envelope({
          access_token: accessToken,
          token_type: "bearer",
          expires_in: 900,
          user: platformAdmin,
        }),
      });
      return;
    }

    if (path === "/api/v1/platform/me") {
      const token = bearerToken(request);
      expect(
        token !== null &&
          (initialAccessTokens.has(token) || freshAccessTokens.has(token)),
      ).toBe(true);
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: envelope({ user: platformAdmin }),
      });
      return;
    }

    if (path === "/api/v1/platform/tenants") {
      const token = bearerToken(request);
      if (accessExpired && token !== null && initialAccessTokens.has(token)) {
        staleRecoveryRequests += 1;
        if (staleRecoveryRequests === 2) {
          releaseStaleRecoveryRequests();
        }
        await Promise.race([
          bothStaleRecoveryRequests,
          new Promise((resolve) => setTimeout(resolve, 2_000)),
        ]);
        await route.fulfill({
          status: 403,
          contentType: "application/json",
          body: errorEnvelope("platform_access_denied"),
        });
        return;
      }

      if (accessExpired) {
        expect(token !== null && freshAccessTokens.has(token)).toBe(true);
        successfulReplays += 1;
      } else {
        expect(token !== null && initialAccessTokens.has(token)).toBe(true);
      }
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: envelope([], true),
      });
      return;
    }

    await route.fulfill({ status: 404 });
  });

  const firstPage = await context.newPage();
  const secondPage = await context.newPage();

  await Promise.all([
    firstPage.goto("/platform"),
    secondPage.goto("/platform"),
  ]);
  await Promise.all([
    expect(
      firstPage.getByRole("heading", { name: "Platform operasyonları" }),
    ).toBeVisible(),
    expect(
      secondPage.getByRole("heading", { name: "Platform operasyonları" }),
    ).toBeVisible(),
  ]);
  await Promise.all([
    expect(
      firstPage.getByRole("heading", { name: "Henüz tenant yok" }),
    ).toBeVisible(),
    expect(
      secondPage.getByRole("heading", { name: "Henüz tenant yok" }),
    ).toBeVisible(),
  ]);

  expect(platformRefreshRequests).toBe(2);

  accessExpired = true;
  await Promise.all([
    firstPage
      .getByRole("link", { name: "Tenant yönetimi", exact: true })
      .click(),
    secondPage
      .getByRole("link", { name: "Tenant yönetimi", exact: true })
      .click(),
  ]);
  await Promise.all([
    expect(
      firstPage.getByRole("heading", { name: "Tenant yönetimi" }),
    ).toBeVisible(),
    expect(
      secondPage.getByRole("heading", { name: "Tenant yönetimi" }),
    ).toBeVisible(),
  ]);
  await Promise.all([
    expect(
      firstPage.getByRole("heading", { name: "Henüz tenant yok" }),
    ).toBeVisible(),
    expect(
      secondPage.getByRole("heading", { name: "Henüz tenant yok" }),
    ).toBeVisible(),
  ]);

  expect(staleRecoveryRequests).toBe(2);
  expect(successfulReplays).toBe(2);
  expect(platformRefreshRequests).toBe(4);
  expect(tenantRefreshRequests).toBe(0);
  expect(
    (await context.cookies()).find((cookie) => cookie.name === "wf_refresh")
      ?.value,
  ).toBe("tenant-refresh-must-remain-unused");
  const durableCoordinationState = await firstPage.evaluate(() =>
    Object.fromEntries(
      Array.from({ length: localStorage.length }, (_, index) => {
        const key = localStorage.key(index) ?? "";
        return [key, localStorage.getItem(key)];
      }),
    ),
  );
  expect(
    durableCoordinationState["wf:platform-session:event:v1"],
  ).toBeUndefined();
  expect(JSON.stringify(durableCoordinationState)).not.toContain(
    "platform-cross-tab-fresh-access",
  );
  expect(JSON.stringify(durableCoordinationState)).not.toContain(
    currentRefreshCredential,
  );
  const broadcastMessages = await firstPage.evaluate(
    () =>
      (
        window as unknown as {
          __platformSessionBroadcastMessages?: string[];
        }
      ).__platformSessionBroadcastMessages ?? [],
  );
  const serializedBroadcastMessages = JSON.stringify(broadcastMessages);
  for (const accessToken of [...initialAccessTokens, ...freshAccessTokens]) {
    expect(serializedBroadcastMessages).not.toContain(accessToken);
  }
  expect(serializedBroadcastMessages).not.toContain(currentRefreshCredential);
  if (disableWebLocks) {
    expect(
      await firstPage.evaluate(() =>
        localStorage.getItem("wf:platform-session:refresh-lease:v1"),
      ),
    ).toBeNull();
  }
}

test("two platform tabs coordinate a rotating refresh and both replay successfully", async ({
  context,
}) => {
  await exerciseCrossTabRefresh(context, { disableWebLocks: false });
});

test("the localStorage lease fallback coordinates platform refresh without Web Locks", async ({
  context,
}) => {
  await exerciseCrossTabRefresh(context, { disableWebLocks: true });
});

test("platform login holds the shared transition lock and supersedes a queued refresh", async ({
  context,
}) => {
  const replacementAdmin = {
    ...platformAdmin,
    id: "f2000000-0000-4000-8000-000000000100",
    email: "replacement@wealthyfalcon.demo",
    full_name: "Replacement Platform",
    permission_version: 12,
  };
  let platformRefreshRequests = 0;
  let platformLoginRequests = 0;
  let tenantRefreshRequests = 0;
  let observeLoginRequest = () => {};
  const loginRequestObserved = new Promise<void>((resolve) => {
    observeLoginRequest = resolve;
  });
  let releaseLoginRequest = () => {};
  const loginRequestRelease = new Promise<void>((resolve) => {
    releaseLoginRequest = resolve;
  });

  await context.addCookies([
    {
      name: "wf_platform_refresh",
      value: "platform-login-transition-refresh",
      url: PLATFORM_ORIGIN,
      httpOnly: true,
      sameSite: "Lax",
    },
    {
      name: "wf_refresh",
      value: "tenant-login-transition-untouched",
      url: PLATFORM_ORIGIN,
      httpOnly: true,
      sameSite: "Lax",
    },
  ]);

  await context.route("**/api/v1/**", async (route: Route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname;

    if (path === "/api/v1/auth/refresh") {
      tenantRefreshRequests += 1;
      await route.fulfill({ status: 418 });
      return;
    }

    if (path === "/api/v1/platform/auth/refresh") {
      platformRefreshRequests += 1;
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        headers: {
          "set-cookie":
            platformRefreshRequests === 1
              ? "wf_platform_refresh=platform-login-transition-rotated; Path=/; HttpOnly; SameSite=Lax; Max-Age=3600"
              : "wf_platform_refresh=platform-post-login-tab-rotated; Path=/; HttpOnly; SameSite=Lax; Max-Age=3600",
        },
        body: envelope({
          access_token:
            platformRefreshRequests === 1
              ? "platform-before-explicit-login"
              : "platform-after-explicit-login",
          token_type: "bearer",
          expires_in: 900,
          user: platformRefreshRequests === 1 ? platformAdmin : replacementAdmin,
        }),
      });
      return;
    }

    if (path === "/api/v1/platform/auth/login") {
      platformLoginRequests += 1;
      observeLoginRequest();
      await loginRequestRelease;
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        headers: {
          "set-cookie":
            "wf_platform_refresh=platform-explicit-login-final; Path=/; HttpOnly; SameSite=Lax; Max-Age=3600",
        },
        body: envelope({
          status: "authenticated",
          access_token: "platform-explicit-login-access",
          token_type: "bearer",
          expires_in: 900,
          user: replacementAdmin,
        }),
      });
      return;
    }

    if (path === "/api/v1/platform/me") {
      const token = bearerToken(request);
      const user =
        token === "platform-explicit-login-access" ||
        token === "platform-after-explicit-login"
          ? replacementAdmin
          : platformAdmin;
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: envelope({ user }),
      });
      return;
    }

    if (path === "/api/v1/platform/tenants") {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: envelope([], true),
      });
      return;
    }

    await route.fulfill({ status: 404 });
  });

  const protectedPage = await context.newPage();
  const loginPage = await context.newPage();
  await protectedPage.goto("/platform");
  await expect(
    protectedPage.getByRole("heading", { name: "Platform operasyonları" }),
  ).toBeVisible();
  await loginPage.goto("/platform/login");
  await loginPage.getByLabel("E-posta adresi").fill(replacementAdmin.email);
  await loginPage.getByLabel("Parola").fill("replacement-platform-password");
  const loginSubmission = loginPage
    .getByRole("button", { name: "Platform yönetimine gir" })
    .click();
  await loginRequestObserved;

  await expect(protectedPage).toHaveURL(/\/platform\/login$/, {
    timeout: 2_000,
  });
  expect(platformRefreshRequests).toBe(1);

  releaseLoginRequest();
  await loginSubmission;
  await expect(loginPage).toHaveURL(/\/platform$/);
  await expect.poll(() => platformRefreshRequests).toBe(2);
  const establishedMarker = await loginPage.evaluate(() => {
    const raw = localStorage.getItem(
      "wf:platform-session:explicit-transition:v1",
    );
    return raw
      ? (JSON.parse(raw) as {
          transitionId: string;
          startedAt: number;
          issuedAt: number;
        })
      : null;
  });
  expect(establishedMarker).not.toBeNull();
  await protectedPage.evaluate((marker) => {
    localStorage.setItem(
      "wf:platform-session:event:v1",
      JSON.stringify({
        scope: "platform",
        version: 1,
        senderId: "delayed-transition-test-sender",
        updateId: crypto.randomUUID(),
        transitionId: marker?.transitionId,
        type: "invalidated",
        reason: "transition_started",
        startedAt: marker?.startedAt,
        issuedAt: marker?.issuedAt,
      }),
    );
  }, establishedMarker);
  await loginPage.waitForTimeout(250);
  await expect(loginPage).toHaveURL(/\/platform$/);
  expect(platformLoginRequests).toBe(1);
  expect(platformRefreshRequests).toBe(2);
  expect(tenantRefreshRequests).toBe(0);
  const cookies = await context.cookies();
  expect(
    cookies.find((cookie) => cookie.name === "wf_platform_refresh")?.value,
  ).toBe("platform-post-login-tab-rotated");
  expect(cookies.find((cookie) => cookie.name === "wf_refresh")?.value).toBe(
    "tenant-login-transition-untouched",
  );
});

test("a newer same-millisecond login supersedes the older in-flight principal", async ({
  context,
}) => {
  const fixedNow = 1_800_000_000_000;
  await context.addInitScript((timestamp) => {
    Date.now = () => timestamp;
    Object.defineProperty(window, "BroadcastChannel", {
      configurable: true,
      value: undefined,
    });
    const nativeAddEventListener = EventTarget.prototype.addEventListener;
    EventTarget.prototype.addEventListener = function (type, ...rest) {
      if (this === window && type === "storage") {
        return;
      }
      Reflect.apply(nativeAddEventListener, this, [type, ...rest]);
    };
  }, fixedNow);

  const olderAdmin = {
    ...platformAdmin,
    id: "f2000000-0000-4000-8000-000000000201",
    email: "older-same-ms@wealthyfalcon.demo",
    full_name: "Older Same Millisecond",
  };
  const newerAdmin = {
    ...platformAdmin,
    id: "f2000000-0000-4000-8000-000000000202",
    email: "newer-same-ms@wealthyfalcon.demo",
    full_name: "Newer Same Millisecond",
  };
  const loginEmails: string[] = [];
  let observeOlderRequest = () => {};
  const olderRequestObserved = new Promise<void>((resolve) => {
    observeOlderRequest = resolve;
  });
  let releaseOlderRequest = () => {};
  const olderRequestRelease = new Promise<void>((resolve) => {
    releaseOlderRequest = resolve;
  });

  await context.route("**/api/v1/**", async (route: Route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    if (path === "/api/v1/platform/auth/login") {
      const body = request.postDataJSON() as { email: string };
      loginEmails.push(body.email);
      const isOlder = body.email === olderAdmin.email;
      if (isOlder) {
        observeOlderRequest();
        await olderRequestRelease;
      }
      const user = isOlder ? olderAdmin : newerAdmin;
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        headers: {
          "set-cookie": `wf_platform_refresh=${isOlder ? "older" : "newer"}-same-ms; Path=/; HttpOnly; SameSite=Lax; Max-Age=3600`,
        },
        body: envelope({
          status: "authenticated",
          access_token: `${isOlder ? "older" : "newer"}-same-ms-access`,
          token_type: "bearer",
          expires_in: 900,
          user,
        }),
      });
      return;
    }
    if (path === "/api/v1/platform/auth/refresh") {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: envelope({
          access_token: "newer-same-ms-tab-access",
          token_type: "bearer",
          expires_in: 900,
          user: newerAdmin,
        }),
      });
      return;
    }
    if (path === "/api/v1/platform/me") {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: envelope({ user: newerAdmin }),
      });
      return;
    }
    if (path === "/api/v1/platform/tenants") {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: envelope([], true),
      });
      return;
    }
    await route.fulfill({ status: 404 });
  });

  const olderPage = await context.newPage();
  const newerPage = await context.newPage();
  await Promise.all([
    olderPage.goto("/platform/login"),
    newerPage.goto("/platform/login"),
  ]);
  await olderPage.getByLabel("E-posta adresi").fill(olderAdmin.email);
  await olderPage.getByLabel("Parola").fill("older-password");
  const olderSubmission = olderPage
    .getByRole("button", { name: "Platform yönetimine gir" })
    .click();
  await olderRequestObserved;
  const olderTransitionId = await olderPage.evaluate(() => {
    const raw = localStorage.getItem(
      "wf:platform-session:explicit-transition:v1",
    );
    return raw ? (JSON.parse(raw) as { updateId: string }).updateId : null;
  });
  expect(olderTransitionId).not.toBeNull();

  await newerPage.getByLabel("E-posta adresi").fill(newerAdmin.email);
  await newerPage.getByLabel("Parola").fill("newer-password");
  const newerSubmission = newerPage
    .getByRole("button", { name: "Platform yönetimine gir" })
    .click();
  await expect
    .poll(() =>
      newerPage.evaluate(() => {
        const raw = localStorage.getItem(
          "wf:platform-session:explicit-transition:v1",
        );
        return raw ? (JSON.parse(raw) as { updateId: string }).updateId : null;
      }),
    )
    .not.toBe(olderTransitionId);
  releaseOlderRequest();

  await Promise.all([olderSubmission, newerSubmission]);
  await expect(newerPage).toHaveURL(/\/platform$/);
  await expect(
    newerPage.getByText("Newer Same Millisecond", { exact: true }).last(),
  ).toBeVisible();
  expect(loginEmails).toEqual([olderAdmin.email, newerAdmin.email]);
  await expect(
    olderPage.getByRole("alert").getByText("Platform girişi tamamlanamadı"),
  ).toBeVisible();
});

test("durable explicit markers fence authenticated dispatch and response acceptance", async ({
  context,
}) => {
  await context.addInitScript(() => {
    Object.defineProperty(window, "BroadcastChannel", {
      configurable: true,
      value: undefined,
    });
    const nativeAddEventListener = EventTarget.prototype.addEventListener;
    EventTarget.prototype.addEventListener = function (type, ...rest) {
      if (this === window && type === "storage") {
        return;
      }
      Reflect.apply(nativeAddEventListener, this, [type, ...rest]);
    };
  });

  const newerAdmin = {
    ...platformAdmin,
    id: "f2000000-0000-4000-8000-000000000204",
    email: "durable-fence-newer@wealthyfalcon.demo",
    full_name: "Durable Fence Newer",
  };
  const tenantTokens: Array<string | null> = [];
  let fenceActive = false;
  let observeFirstTenantRequest = () => {};
  const firstTenantRequestObserved = new Promise<void>((resolve) => {
    observeFirstTenantRequest = resolve;
  });
  let releaseFirstTenantRequest = () => {};
  const firstTenantRequestRelease = new Promise<void>((resolve) => {
    releaseFirstTenantRequest = resolve;
  });
  let observeLoginRequest = () => {};
  const loginRequestObserved = new Promise<void>((resolve) => {
    observeLoginRequest = resolve;
  });
  let releaseLoginRequest = () => {};
  const loginRequestRelease = new Promise<void>((resolve) => {
    releaseLoginRequest = resolve;
  });

  await context.addCookies([
    {
      name: "wf_platform_refresh",
      value: "durable-fence-old-cookie",
      url: PLATFORM_ORIGIN,
      httpOnly: true,
      sameSite: "Lax",
    },
  ]);
  await context.route("**/api/v1/**", async (route: Route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    if (path === "/api/v1/platform/auth/refresh") {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: envelope({
          access_token: "durable-fence-old-access",
          token_type: "bearer",
          expires_in: 900,
          user: platformAdmin,
        }),
      });
      return;
    }
    if (path === "/api/v1/platform/me") {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: envelope({ user: platformAdmin }),
      });
      return;
    }
    if (path === "/api/v1/platform/tenants") {
      if (fenceActive) {
        tenantTokens.push(bearerToken(request));
        if (tenantTokens.length === 1) {
          observeFirstTenantRequest();
          await firstTenantRequestRelease;
        }
      }
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: envelope([], true),
      });
      return;
    }
    if (path === "/api/v1/platform/auth/login") {
      observeLoginRequest();
      await loginRequestRelease;
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: envelope({
          status: "authenticated",
          access_token: "durable-fence-newer-access",
          token_type: "bearer",
          expires_in: 900,
          user: newerAdmin,
        }),
      });
      return;
    }
    await route.fulfill({ status: 404 });
  });

  const staleResponsePage = await context.newPage();
  const staleDispatchPage = await context.newPage();
  const loginPage = await context.newPage();
  await staleResponsePage.goto("/platform");
  await staleDispatchPage.goto("/platform");
  await loginPage.goto("/platform/login");
  fenceActive = true;

  const staleResponseNavigation = staleResponsePage
    .getByRole("link", { name: "Tenant yönetimi", exact: true })
    .click();
  await firstTenantRequestObserved;
  await loginPage.getByLabel("E-posta adresi").fill(newerAdmin.email);
  await loginPage.getByLabel("Parola").fill("newer-password");
  const loginSubmission = loginPage
    .getByRole("button", { name: "Platform yönetimine gir" })
    .click();
  await loginRequestObserved;

  const staleDispatchNavigation = staleDispatchPage
    .getByRole("link", { name: "Tenant yönetimi", exact: true })
    .click();
  try {
    await staleDispatchPage.waitForTimeout(250);
    releaseFirstTenantRequest();
    await expect(staleResponsePage).toHaveURL(/\/platform\/login$/, {
      timeout: 2_000,
    });
    await expect(staleDispatchPage).toHaveURL(/\/platform\/login$/, {
      timeout: 2_000,
    });
    expect(tenantTokens).toEqual(["durable-fence-old-access"]);
  } finally {
    releaseFirstTenantRequest();
    releaseLoginRequest();
  }
  await Promise.allSettled([
    staleResponseNavigation,
    staleDispatchNavigation,
    loginSubmission,
  ]);
});

test("a timed-out platform login invalidates the old principal across tabs", async ({
  context,
}) => {
  test.setTimeout(30_000);
  let observeLoginRequest = () => {};
  const loginRequestObserved = new Promise<void>((resolve) => {
    observeLoginRequest = resolve;
  });
  let releaseLoginRequest = () => {};
  const loginRequestRelease = new Promise<void>((resolve) => {
    releaseLoginRequest = resolve;
  });
  const tenantRequestTokens: Array<string | null> = [];
  let loginTransitionStarted = false;

  await context.addCookies([
    {
      name: "wf_platform_refresh",
      value: "platform-before-ambiguous-login",
      url: PLATFORM_ORIGIN,
      httpOnly: true,
      sameSite: "Lax",
    },
  ]);

  await context.route("**/api/v1/**", async (route: Route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    if (path === "/api/v1/platform/auth/refresh") {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: envelope({
          access_token: "platform-old-principal-access",
          token_type: "bearer",
          expires_in: 900,
          user: platformAdmin,
        }),
      });
      return;
    }
    if (path === "/api/v1/platform/me") {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: envelope({ user: platformAdmin }),
      });
      return;
    }
    if (path === "/api/v1/platform/auth/login") {
      // Model the ambiguous boundary: the server committed a different
      // principal's cookie, but the response never reaches the caller.
      await context.addCookies([
        {
          name: "wf_platform_refresh",
          value: "platform-ambiguous-new-principal",
          url: PLATFORM_ORIGIN,
          httpOnly: true,
          sameSite: "Lax",
        },
      ]);
      loginTransitionStarted = true;
      observeLoginRequest();
      await loginRequestRelease;
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: envelope({
          status: "authenticated",
          access_token: "platform-ambiguous-new-access",
          token_type: "bearer",
          expires_in: 900,
          user: { ...platformAdmin, email: "new-principal@example.test" },
        }),
      });
      return;
    }
    if (path === "/api/v1/platform/tenants") {
      if (loginTransitionStarted) {
        tenantRequestTokens.push(bearerToken(request));
      }
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: envelope([], true),
      });
      return;
    }
    await route.fulfill({ status: 404 });
  });

  const protectedPage = await context.newPage();
  const loginPage = await context.newPage();
  try {
    await protectedPage.goto("/platform");
    await expect(
      protectedPage.getByRole("heading", { name: "Platform operasyonları" }),
    ).toBeVisible();
    await loginPage.goto("/platform/login");
    await loginPage.getByLabel("E-posta adresi").fill("new-principal@example.test");
    await loginPage.getByLabel("Parola").fill("replacement-platform-password");
    await loginPage
      .getByRole("button", { name: "Platform yönetimine gir" })
      .click();
    await loginRequestObserved;

    await expect(protectedPage).toHaveURL(/\/platform\/login$/, {
      timeout: 2_000,
    });
    await expect(
      loginPage.getByRole("alert").getByText("Platform girişi tamamlanamadı"),
    ).toBeVisible({ timeout: 20_000 });
    expect(tenantRequestTokens).toEqual([]);
    const explicitTransition = await loginPage.evaluate(() =>
      localStorage.getItem(
        "wf:platform-session:explicit-transition:v1",
      ),
    );
    expect(explicitTransition).toContain('"type":"invalidated"');
    expect(explicitTransition).not.toContain("platform-old-principal-access");
    expect(explicitTransition).not.toContain("platform-ambiguous-new-access");
  } finally {
    releaseLoginRequest();
  }
});

test("platform logout waits for a cross-tab refresh and clears the last rotated cookie", async ({
  context,
}) => {
  let platformRefreshRequests = 0;
  let platformLogoutRequests = 0;
  let tenantRefreshRequests = 0;
  let accessExpired = false;
  let refreshIsHeld = false;
  let logoutStartedWhileRefreshHeld = false;
  let observeRefreshRequest = () => {};
  const refreshRequestObserved = new Promise<void>((resolve) => {
    observeRefreshRequest = resolve;
  });
  let releaseRefreshRequest = () => {};
  const refreshRequestRelease = new Promise<void>((resolve) => {
    releaseRefreshRequest = resolve;
  });
  let observeLogoutRequest = () => {};
  const logoutRequestObserved = new Promise<void>((resolve) => {
    observeLogoutRequest = resolve;
  });

  await context.addCookies([
    {
      name: "wf_platform_refresh",
      value: "platform-logout-transition-refresh",
      url: PLATFORM_ORIGIN,
      httpOnly: true,
      sameSite: "Lax",
    },
    {
      name: "wf_refresh",
      value: "tenant-logout-transition-untouched",
      url: PLATFORM_ORIGIN,
      httpOnly: true,
      sameSite: "Lax",
    },
  ]);

  await context.route("**/api/v1/**", async (route: Route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname;

    if (path === "/api/v1/auth/refresh") {
      tenantRefreshRequests += 1;
      await route.fulfill({ status: 418 });
      return;
    }

    if (path === "/api/v1/platform/auth/refresh") {
      platformRefreshRequests += 1;
      if (platformRefreshRequests === 1) {
        // Keep the initial owner in flight so both documents participate in
        // the same restore transition instead of legitimately refreshing one
        // after the other has already finished.
        await new Promise((resolve) => setTimeout(resolve, 150));
      }
      if (platformRefreshRequests === 3) {
        refreshIsHeld = true;
        observeRefreshRequest();
        await refreshRequestRelease;
        refreshIsHeld = false;
      }
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        headers: {
          "set-cookie": `wf_platform_refresh=platform-logout-transition-rotated-${platformRefreshRequests}; Path=/; HttpOnly; SameSite=Lax; Max-Age=3600`,
        },
        body: envelope({
          access_token:
            platformRefreshRequests <= 2
              ? `platform-before-explicit-logout-${platformRefreshRequests}`
              : "platform-refresh-superseded-by-logout",
          token_type: "bearer",
          expires_in: 900,
          user: platformAdmin,
        }),
      });
      return;
    }

    if (path === "/api/v1/platform/auth/logout") {
      platformLogoutRequests += 1;
      logoutStartedWhileRefreshHeld = refreshIsHeld;
      observeLogoutRequest();
      await route.fulfill({
        status: 204,
        headers: {
          "set-cookie":
            "wf_platform_refresh=; Path=/; HttpOnly; SameSite=Lax; Max-Age=0",
        },
      });
      return;
    }

    if (path === "/api/v1/platform/me") {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: envelope({ user: platformAdmin }),
      });
      return;
    }

    if (path === "/api/v1/platform/tenants") {
      if (
        accessExpired &&
        bearerToken(request)?.startsWith("platform-before-explicit-logout-")
      ) {
        await route.fulfill({
          status: 403,
          contentType: "application/json",
          body: errorEnvelope("platform_access_denied"),
        });
        return;
      }
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: envelope([], true),
      });
      return;
    }

    await route.fulfill({ status: 404 });
  });

  const refreshPage = await context.newPage();
  const logoutPage = await context.newPage();
  await Promise.all([
    refreshPage.goto("/platform"),
    logoutPage.goto("/platform"),
  ]);
  await Promise.all([
    expect(
      refreshPage.getByRole("heading", { name: "Platform operasyonları" }),
    ).toBeVisible(),
    expect(
      logoutPage.getByRole("heading", { name: "Platform operasyonları" }),
    ).toBeVisible(),
  ]);
  expect(platformRefreshRequests).toBe(2);

  accessExpired = true;
  const tenantNavigation = refreshPage
    .getByRole("link", { name: "Tenant yönetimi", exact: true })
    .click();
  await refreshRequestObserved;
  const logoutSubmission = logoutPage
    .getByRole("button", { name: "Çıkış yap" })
    .click();
  await logoutPage.waitForTimeout(250);
  expect(platformLogoutRequests).toBe(0);

  releaseRefreshRequest();
  await logoutRequestObserved;
  await logoutSubmission;
  await tenantNavigation.catch(() => {});
  expect(logoutStartedWhileRefreshHeld).toBe(false);
  expect(platformLogoutRequests).toBe(1);
  expect(platformRefreshRequests).toBe(3);
  expect(tenantRefreshRequests).toBe(0);
  await expect(logoutPage).toHaveURL(/\/platform\/login$/);
  const cookies = await context.cookies();
  expect(
    cookies.find((cookie) => cookie.name === "wf_platform_refresh"),
  ).toBeUndefined();
  expect(cookies.find((cookie) => cookie.name === "wf_refresh")?.value).toBe(
    "tenant-logout-transition-untouched",
  );
});

test("a hanging platform transition aborts and releases the storage lease", async ({
  context,
  page,
}) => {
  test.setTimeout(30_000);
  await context.addInitScript(() => {
    Object.defineProperty(navigator, "locks", {
      configurable: true,
      value: undefined,
    });
  });
  await context.addCookies([
    {
      name: "wf_platform_refresh",
      value: "platform-hanging-refresh",
      url: PLATFORM_ORIGIN,
      httpOnly: true,
      sameSite: "Lax",
    },
  ]);

  let releaseRefresh = () => {};
  const refreshGate = new Promise<void>((resolve) => {
    releaseRefresh = resolve;
  });
  let observeRefresh = () => {};
  const refreshObserved = new Promise<void>((resolve) => {
    observeRefresh = resolve;
  });
  await context.route("**/api/v1/**", async (route: Route) => {
    const path = new URL(route.request().url()).pathname;
    if (path === "/api/v1/platform/auth/refresh") {
      observeRefresh();
      await refreshGate;
      await route.fulfill({ status: 503 });
      return;
    }
    await route.fulfill({ status: 404 });
  });

  try {
    await page.goto("/platform");
    await refreshObserved;
    await expect(page).toHaveURL(/\/platform\/login$/, { timeout: 20_000 });
    expect(
      await page.evaluate(() =>
        localStorage.getItem("wf:platform-session:refresh-lease:v1"),
      ),
    ).toBeNull();
  } finally {
    releaseRefresh();
  }
});

test("platform cookie transitions fail closed when browser coordination is unavailable", async ({
  context,
  page,
}) => {
  let platformRefreshRequests = 0;

  await context.addInitScript(() => {
    Object.defineProperty(navigator, "locks", {
      configurable: true,
      value: undefined,
    });
    const originalSetItem = Storage.prototype.setItem;
    Object.defineProperty(Storage.prototype, "setItem", {
      configurable: true,
      value(key: string, value: string) {
        if (key === "wf:platform-session:refresh-lease:v1") {
          throw new DOMException("Storage writes are blocked", "SecurityError");
        }
        return originalSetItem.call(this, key, value);
      },
    });
  });

  await context.addCookies([
    {
      name: "wf_platform_refresh",
      value: "platform-uncoordinated-refresh",
      url: PLATFORM_ORIGIN,
      httpOnly: true,
      sameSite: "Lax",
    },
  ]);

  await context.route("**/api/v1/**", async (route: Route) => {
    const path = new URL(route.request().url()).pathname;
    if (path === "/api/v1/platform/auth/refresh") {
      platformRefreshRequests += 1;
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: envelope({
          access_token: "platform-uncoordinated-access",
          token_type: "bearer",
          expires_in: 900,
          user: platformAdmin,
        }),
      });
      return;
    }
    if (path === "/api/v1/platform/me") {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: envelope({ user: platformAdmin }),
      });
      return;
    }
    if (path === "/api/v1/platform/tenants") {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: envelope([], true),
      });
      return;
    }
    await route.fulfill({ status: 404 });
  });

  await page.goto("/platform");
  await expect(page).toHaveURL(/\/platform\/login$/);
  expect(platformRefreshRequests).toBe(0);
});
