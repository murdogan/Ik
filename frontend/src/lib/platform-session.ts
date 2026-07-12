import type {
  PlatformAuthUser,
  PlatformMeResponseData,
  PlatformRefreshResponseData,
  PlatformSessionGrantData,
} from "./auth-contracts";
import {
  ApiClientError,
  type ApiRequestOptions,
  type ApiSuccessEnvelope,
  requestApi,
  requestApiEnvelope,
  requestApiNoContent,
} from "./api-client";

const PLATFORM_REFRESH_PATH = "/api/v1/platform/auth/refresh" as const;
const PLATFORM_LOGOUT_PATH = "/api/v1/platform/auth/logout" as const;
const PLATFORM_ME_PATH = "/api/v1/platform/me" as const;

let platformAccessToken: string | null = null;
let platformSessionGeneration = 0;
let platformRefreshInFlight: Promise<PlatformRefreshResponseData> | null = null;
let platformRestoreInFlight: Promise<PlatformAuthUser> | null = null;
const platformSessionChangeListeners = new Set<
  (change: PlatformSessionChange) => void
>();

export type PlatformSessionChange =
  | { type: "user_updated"; user: PlatformAuthUser }
  | { type: "invalidated" };

class PlatformSessionSupersededError extends Error {
  constructor() {
    super("Platform session changed while the request was in flight");
    this.name = "PlatformSessionSupersededError";
  }
}

function publishPlatformSessionChange(change: PlatformSessionChange): void {
  for (const listener of platformSessionChangeListeners) {
    listener(change);
  }
}

function applyPlatformSession(data: PlatformSessionGrantData): void {
  platformAccessToken = data.access_token;
  publishPlatformSessionChange({ type: "user_updated", user: data.user });
}

function invalidatePlatformSession({ notify = true }: { notify?: boolean } = {}): void {
  platformSessionGeneration += 1;
  platformAccessToken = null;
  platformRestoreInFlight = null;
  if (notify) {
    publishPlatformSessionChange({ type: "invalidated" });
  }
}

export function subscribeToPlatformSessionChanges(
  listener: (change: PlatformSessionChange) => void,
): () => void {
  platformSessionChangeListeners.add(listener);
  return () => platformSessionChangeListeners.delete(listener);
}

export function establishPlatformSession(data: PlatformSessionGrantData): void {
  platformSessionGeneration += 1;
  applyPlatformSession(data);
  platformRestoreInFlight = null;
}

async function performPlatformRefresh(
  generation: number,
): Promise<PlatformRefreshResponseData> {
  try {
    const data = await requestApi<PlatformRefreshResponseData>(
      PLATFORM_REFRESH_PATH,
      { method: "POST" },
    );
    if (generation !== platformSessionGeneration) {
      throw new PlatformSessionSupersededError();
    }
    applyPlatformSession(data);
    return data;
  } catch (cause) {
    if (generation === platformSessionGeneration) {
      invalidatePlatformSession();
    }
    throw cause;
  }
}

export function refreshPlatformSession(): Promise<PlatformRefreshResponseData> {
  if (platformRefreshInFlight) {
    return platformRefreshInFlight;
  }

  const generation = platformSessionGeneration;
  const pending = performPlatformRefresh(generation);
  platformRefreshInFlight = pending;
  pending.then(
    () => {
      if (platformRefreshInFlight === pending) {
        platformRefreshInFlight = null;
      }
    },
    () => {
      if (platformRefreshInFlight === pending) {
        platformRefreshInFlight = null;
      }
    },
  );
  return pending;
}

type PlatformAuthenticatedRequestOptions = Omit<
  ApiRequestOptions,
  "accessToken"
>;
type PlatformAuthenticatedRequester<TResponse> = (
  path: `/api/${string}`,
  options: ApiRequestOptions,
) => Promise<TResponse>;

async function requestPlatformAuthenticated<TResponse>(
  path: `/api/${string}`,
  options: PlatformAuthenticatedRequestOptions,
  requester: PlatformAuthenticatedRequester<TResponse>,
): Promise<TResponse> {
  const requestGeneration = platformSessionGeneration;
  if (!platformAccessToken) {
    await refreshPlatformSession();
  }

  if (requestGeneration !== platformSessionGeneration) {
    throw new PlatformSessionSupersededError();
  }

  const attemptedToken = platformAccessToken;
  if (!attemptedToken) {
    throw new PlatformSessionSupersededError();
  }

  try {
    const data = await requester(path, {
      ...options,
      accessToken: attemptedToken,
    });
    if (requestGeneration !== platformSessionGeneration) {
      throw new PlatformSessionSupersededError();
    }
    return data;
  } catch (cause) {
    if (!(cause instanceof ApiClientError) || cause.status !== 401) {
      throw cause;
    }
  }

  if (requestGeneration !== platformSessionGeneration) {
    throw new PlatformSessionSupersededError();
  }

  if (!platformAccessToken || platformAccessToken === attemptedToken) {
    await refreshPlatformSession();
  }

  const retryToken = platformAccessToken;
  if (!retryToken) {
    throw new PlatformSessionSupersededError();
  }

  try {
    const data = await requester(path, {
      ...options,
      accessToken: retryToken,
    });
    if (requestGeneration !== platformSessionGeneration) {
      throw new PlatformSessionSupersededError();
    }
    return data;
  } catch (cause) {
    if (
      cause instanceof ApiClientError &&
      cause.status === 401 &&
      requestGeneration === platformSessionGeneration
    ) {
      invalidatePlatformSession();
    }
    throw cause;
  }
}

export async function requestPlatformAuthenticatedApi<TResponse>(
  path: `/api/${string}`,
  options: PlatformAuthenticatedRequestOptions = {},
): Promise<TResponse> {
  return requestPlatformAuthenticated(
    path,
    options,
    (requestPath, requestOptions) =>
      requestApi<TResponse>(requestPath, requestOptions),
  );
}

export async function requestPlatformAuthenticatedApiEnvelope<
  TResponse,
  TMeta = unknown,
>(
  path: `/api/${string}`,
  options: PlatformAuthenticatedRequestOptions = {},
): Promise<ApiSuccessEnvelope<TResponse, TMeta>> {
  return requestPlatformAuthenticated(
    path,
    options,
    (requestPath, requestOptions) =>
      requestApiEnvelope<TResponse, TMeta>(requestPath, requestOptions),
  );
}

async function performPlatformRestore(): Promise<PlatformAuthUser> {
  if (!platformAccessToken) {
    await refreshPlatformSession();
  }
  const data = await requestPlatformAuthenticatedApi<PlatformMeResponseData>(
    PLATFORM_ME_PATH,
  );
  return data.user;
}

export function restorePlatformSession(): Promise<PlatformAuthUser> {
  if (platformRestoreInFlight) {
    return platformRestoreInFlight;
  }

  const pending = performPlatformRestore();
  platformRestoreInFlight = pending;
  pending.then(
    () => {
      if (platformRestoreInFlight === pending) {
        platformRestoreInFlight = null;
      }
    },
    () => {
      if (platformRestoreInFlight === pending) {
        platformRestoreInFlight = null;
      }
    },
  );
  return pending;
}

export async function logoutPlatformSession(): Promise<void> {
  const pendingRefresh = platformRefreshInFlight;
  const logoutAccessToken = platformAccessToken;
  invalidatePlatformSession({ notify: false });

  if (pendingRefresh) {
    try {
      await pendingRefresh;
    } catch {
      // A superseded or failed refresh must not prevent the cookie-backed logout attempt.
    }
  }

  try {
    await requestApiNoContent(PLATFORM_LOGOUT_PATH, {
      method: "POST",
      accessToken: logoutAccessToken ?? undefined,
    });
  } finally {
    platformAccessToken = null;
  }
}
