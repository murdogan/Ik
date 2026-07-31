import { expect, test } from "@playwright/test";

import {
  ApiClientError,
  requestApiEnvelope,
} from "../src/lib/api-client";
import {
  establishPlatformSession,
  logoutPlatformSession,
  requestPlatformAuthenticatedApiEnvelope,
} from "../src/lib/platform-session";
import { isAmbiguousPlatformMutationOutcome } from "../src/lib/platform-tenants";

const platformUser = {
  id: "f2000000-0000-4000-8000-000000000099",
  email: "platform@wealthyfalcon.demo",
  full_name: "Atlas Platform",
  workspace_scope: "platform" as const,
  roles: [
    {
      id: "f3000000-0000-4000-8000-000000000099",
      code: "super_admin",
      name: "Süper yönetici",
      scope_type: "platform" as const,
    },
  ],
  permissions: ["tenant:update:platform"],
  permission_version: 11,
  authentication_strength: "multi_factor" as const,
};

function platformGrant(accessToken: string) {
  return {
    access_token: accessToken,
    token_type: "bearer",
    expires_in: 900,
    user: platformUser,
  };
}

function installFetch(response: Response | Error): () => void {
  const originalFetch = globalThis.fetch;
  globalThis.fetch = async () => {
    if (response instanceof Error) {
      throw response;
    }
    return response;
  };
  return () => {
    globalThis.fetch = originalFetch;
  };
}

async function captureApiError(request: () => Promise<unknown>): Promise<ApiClientError> {
  try {
    await request();
  } catch (cause) {
    expect(cause).toBeInstanceOf(ApiClientError);
    return cause as ApiClientError;
  }
  throw new Error("Expected the API request to fail");
}

async function captureError(request: () => Promise<unknown>): Promise<unknown> {
  try {
    await request();
  } catch (cause) {
    return cause;
  }
  throw new Error("Expected the request to fail");
}

test.describe("API client response reliability", () => {
  test("normalizes a response body read failure with its HTTP status", async () => {
    const response = new Response(null, {
      status: 502,
      headers: { "x-request-id": "body-read-reference" },
    });
    response.text = async () => {
      throw new TypeError("terminated");
    };
    const restoreFetch = installFetch(response);

    try {
      const error = await captureApiError(() =>
        requestApiEnvelope("/api/v1/platform/tenants/example", {
          method: "PATCH",
          body: { name: "Updated tenant" },
        }),
      );

      expect(error.status).toBe(502);
      expect(error.code).toBe("invalid_response");
      expect(error.correlationId).toBe("body-read-reference");
    } finally {
      restoreFetch();
    }
  });

  test("normalizes malformed JSON on success and error responses", async () => {
    for (const status of [200, 409]) {
      const restoreFetch = installFetch(
        new Response("{not-json", {
          status,
          headers: { "x-request-id": `malformed-${status}` },
        }),
      );

      try {
        const error = await captureApiError(() =>
          requestApiEnvelope("/api/v1/platform/tenants/example", {
            method: "PATCH",
            body: { name: "Updated tenant" },
          }),
        );

        expect(error.status).toBe(status);
        expect(error.code).toBe("invalid_response");
        expect(error.correlationId).toBe(`malformed-${status}`);
      } finally {
        restoreFetch();
      }
    }
  });

  test("classifies only post-dispatch platform mutation failures as ambiguous", async () => {
    const cases = [
      {
        error: new ApiClientError({ status: null, code: "network_error" }),
        ambiguous: true,
      },
      {
        error: new ApiClientError({ status: 409, code: "invalid_response" }),
        ambiguous: true,
      },
      {
        error: new ApiClientError({
          status: 503,
          code: "service_unavailable",
        }),
        ambiguous: true,
      },
      {
        error: new ApiClientError({ status: 422, code: "validation_error" }),
        ambiguous: false,
      },
      {
        error: new ApiClientError({ status: 403, code: "access_denied" }),
        ambiguous: false,
      },
      {
        error: new ApiClientError({ status: 409, code: "slug_conflict" }),
        ambiguous: false,
      },
    ] as const;

    for (const { error, ambiguous } of cases) {
      expect(isAmbiguousPlatformMutationOutcome(error)).toBe(ambiguous);
    }
  });

  test("distinguishes a superseded successful response from supersession before mutation dispatch", async () => {
    establishPlatformSession(platformGrant("platform-response-token-a"));
    const originalFetch = globalThis.fetch;
    let mutationDispatches = 0;
    globalThis.fetch = async () => {
      mutationDispatches += 1;
      establishPlatformSession(platformGrant("platform-response-token-b"));
      return new Response(
        JSON.stringify({
          data: { status: "accepted" },
          meta: { request_id: "post-response" },
        }),
        { status: 200 },
      );
    };

    try {
      const postResponseCause = await captureError(() =>
        requestPlatformAuthenticatedApiEnvelope(
          "/api/v1/platform/tenants/example/initial-admin-invitation/resend",
          { method: "POST" },
        ),
      );
      expect(mutationDispatches).toBe(1);
      expect(isAmbiguousPlatformMutationOutcome(postResponseCause)).toBe(true);
    } finally {
      globalThis.fetch = originalFetch;
    }

    const restoreLogoutFetch = installFetch(new Response(null, { status: 204 }));
    try {
      await logoutPlatformSession();
    } finally {
      restoreLogoutFetch();
    }

    let refreshDispatches = 0;
    mutationDispatches = 0;
    globalThis.fetch = async (input) => {
      const path = String(input);
      if (path === "/api/v1/platform/auth/refresh") {
        refreshDispatches += 1;
        establishPlatformSession(platformGrant("platform-pre-dispatch-new"));
        return new Response(
          JSON.stringify({ data: platformGrant("platform-pre-dispatch-old") }),
          { status: 200 },
        );
      }
      mutationDispatches += 1;
      return new Response(
        JSON.stringify({ data: { status: "accepted" }, meta: {} }),
        { status: 200 },
      );
    };

    try {
      const preDispatchCause = await captureError(() =>
        requestPlatformAuthenticatedApiEnvelope(
          "/api/v1/platform/tenants/example/initial-admin-invitation/resend",
          { method: "POST" },
        ),
      );
      expect(refreshDispatches).toBe(1);
      expect(mutationDispatches).toBe(0);
      expect(isAmbiguousPlatformMutationOutcome(preDispatchCause)).toBe(false);
    } finally {
      globalThis.fetch = originalFetch;
    }
  });
});
