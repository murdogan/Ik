import {
  expect,
  type BrowserContext,
  type Page,
  type Request,
  type Route,
} from "@playwright/test";

import { tenantFeatureCatalog } from "./tenant-features";

export function apiEnvelope(
  data: unknown,
  extraMeta: Record<string, unknown> = {},
): string {
  return JSON.stringify({
    data,
    meta: {
      request_id: "phase11-browser",
      trace_id: "phase11-browser-trace",
      correlation_id: "phase11-browser",
      ...extraMeta,
    },
  });
}

export function apiError(code: string): string {
  return JSON.stringify({
    error: {
      code,
      message: "Request failed",
      details: null,
      correlation_id: "phase11-browser",
    },
  });
}

type ApiHandler = (
  route: Route,
  request: Request,
  url: URL,
) => Promise<boolean>;

export async function installTenantSession({
  context,
  page,
  user,
  handleApi,
  featureOverrides = {},
}: {
  context: BrowserContext;
  page: Page;
  user: Record<string, unknown>;
  handleApi: ApiHandler;
  featureOverrides?: Parameters<typeof tenantFeatureCatalog>[0];
}) {
  const accessToken = "phase11-access";

  await context.addCookies([
    {
      name: "wf_refresh",
      value: "phase11-refresh",
      url: "http://127.0.0.1:3100",
      httpOnly: true,
      sameSite: "Lax",
    },
  ]);

  await page.route("**/api/v1/**", async (route) => {
    const request = route.request();
    const url = new URL(request.url());
    const path = url.pathname;

    if (path === "/api/v1/auth/refresh") {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: apiEnvelope({
          access_token: accessToken,
          token_type: "bearer",
          expires_in: 900,
          user,
        }),
      });
      return;
    }

    expect(request.headers().authorization).toBe(`Bearer ${accessToken}`);
    if (path === "/api/v1/me") {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: apiEnvelope({ user }),
      });
      return;
    }
    if (path === "/api/v1/tenant/features") {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: apiEnvelope(tenantFeatureCatalog(featureOverrides)),
      });
      return;
    }
    if (await handleApi(route, request, url)) return;

    await route.fulfill({
      status: 404,
      contentType: "application/json",
      body: apiError("not_found"),
    });
  });
}
