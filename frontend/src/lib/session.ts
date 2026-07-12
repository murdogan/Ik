import type {
  AuthUser,
  MeResponseData,
  RefreshResponseData,
  SessionGrantData,
} from "./auth-contracts";
import {
  ApiClientError,
  type ApiRequestOptions,
  type ApiSuccessEnvelope,
  requestApi,
  requestApiEnvelope,
  requestApiNoContent,
} from "./api-client";

const REFRESH_PATH = "/api/v1/auth/refresh" as const;
const LOGOUT_PATH = "/api/v1/auth/logout" as const;
const ME_PATH = "/api/v1/me" as const;

let accessToken: string | null = null;
let sessionGeneration = 0;
let refreshInFlight: Promise<RefreshResponseData> | null = null;
let restoreInFlight: Promise<AuthUser> | null = null;
const sessionChangeListeners = new Set<(change: SessionChange) => void>();

export type SessionChange =
  | { type: "user_updated"; user: AuthUser }
  | { type: "invalidated" };

class SessionSupersededError extends Error {
  constructor() {
    super("Session changed while the request was in flight");
    this.name = "SessionSupersededError";
  }
}

function applySession(data: SessionGrantData): void {
  accessToken = data.access_token;
  publishSessionChange({ type: "user_updated", user: data.user });
}

function invalidateSession({ notify = true }: { notify?: boolean } = {}): void {
  sessionGeneration += 1;
  accessToken = null;
  restoreInFlight = null;
  if (notify) {
    publishSessionChange({ type: "invalidated" });
  }
}

function publishSessionChange(change: SessionChange): void {
  for (const listener of sessionChangeListeners) {
    listener(change);
  }
}

export function subscribeToSessionChanges(
  listener: (change: SessionChange) => void,
): () => void {
  sessionChangeListeners.add(listener);
  return () => sessionChangeListeners.delete(listener);
}

export function establishSession(data: SessionGrantData): void {
  sessionGeneration += 1;
  applySession(data);
  restoreInFlight = null;
}

async function performRefresh(generation: number): Promise<RefreshResponseData> {
  try {
    const data = await requestApi<RefreshResponseData>(REFRESH_PATH, {
      method: "POST",
    });
    if (generation !== sessionGeneration) {
      throw new SessionSupersededError();
    }
    applySession(data);
    return data;
  } catch (cause) {
    if (generation === sessionGeneration) {
      invalidateSession();
    }
    throw cause;
  }
}

export function refreshSession(): Promise<RefreshResponseData> {
  if (refreshInFlight) {
    return refreshInFlight;
  }

  const generation = sessionGeneration;
  const pending = performRefresh(generation);
  refreshInFlight = pending;
  pending.then(
    () => {
      if (refreshInFlight === pending) {
        refreshInFlight = null;
      }
    },
    () => {
      if (refreshInFlight === pending) {
        refreshInFlight = null;
      }
    },
  );
  return pending;
}

type AuthenticatedRequestOptions = Omit<ApiRequestOptions, "accessToken">;
type AuthenticatedRequester<TResponse> = (
  path: `/api/${string}`,
  options: ApiRequestOptions,
) => Promise<TResponse>;

async function requestAuthenticated<TResponse>(
  path: `/api/${string}`,
  options: AuthenticatedRequestOptions,
  requester: AuthenticatedRequester<TResponse>,
): Promise<TResponse> {
  const requestGeneration = sessionGeneration;
  if (!accessToken) {
    await refreshSession();
  }

  if (requestGeneration !== sessionGeneration) {
    throw new SessionSupersededError();
  }

  const attemptedToken = accessToken;
  if (!attemptedToken) {
    throw new SessionSupersededError();
  }

  try {
    const data = await requester(path, {
      ...options,
      accessToken: attemptedToken,
    });
    if (requestGeneration !== sessionGeneration) {
      throw new SessionSupersededError();
    }
    return data;
  } catch (cause) {
    if (!(cause instanceof ApiClientError) || cause.status !== 401) {
      throw cause;
    }
  }

  if (requestGeneration !== sessionGeneration) {
    throw new SessionSupersededError();
  }

  if (!accessToken || accessToken === attemptedToken) {
    await refreshSession();
  }

  const retryToken = accessToken;
  if (!retryToken) {
    throw new SessionSupersededError();
  }

  try {
    const data = await requester(path, {
      ...options,
      accessToken: retryToken,
    });
    if (requestGeneration !== sessionGeneration) {
      throw new SessionSupersededError();
    }
    return data;
  } catch (cause) {
    if (
      cause instanceof ApiClientError &&
      cause.status === 401 &&
      requestGeneration === sessionGeneration
    ) {
      invalidateSession();
    }
    throw cause;
  }
}

export async function requestAuthenticatedApi<TResponse>(
  path: `/api/${string}`,
  options: AuthenticatedRequestOptions = {},
): Promise<TResponse> {
  return requestAuthenticated(path, options, (requestPath, requestOptions) =>
    requestApi<TResponse>(requestPath, requestOptions),
  );
}

export async function requestAuthenticatedApiEnvelope<TResponse, TMeta = unknown>(
  path: `/api/${string}`,
  options: AuthenticatedRequestOptions = {},
): Promise<ApiSuccessEnvelope<TResponse, TMeta>> {
  return requestAuthenticated(
    path,
    options,
    (requestPath, requestOptions) =>
      requestApiEnvelope<TResponse, TMeta>(requestPath, requestOptions),
  );
}

async function performRestore(): Promise<AuthUser> {
  if (!accessToken) {
    await refreshSession();
  }
  const data = await requestAuthenticatedApi<MeResponseData>(ME_PATH);
  return data.user;
}

export function restoreSession(): Promise<AuthUser> {
  if (restoreInFlight) {
    return restoreInFlight;
  }

  const pending = performRestore();
  restoreInFlight = pending;
  pending.then(
    () => {
      if (restoreInFlight === pending) {
        restoreInFlight = null;
      }
    },
    () => {
      if (restoreInFlight === pending) {
        restoreInFlight = null;
      }
    },
  );
  return pending;
}

export async function logoutSession(): Promise<void> {
  const pendingRefresh = refreshInFlight;
  const logoutAccessToken = accessToken;
  invalidateSession({ notify: false });

  if (pendingRefresh) {
    try {
      await pendingRefresh;
    } catch {
      // A superseded or failed refresh must not prevent the cookie-backed logout attempt.
    }
  }

  try {
    await requestApiNoContent(LOGOUT_PATH, {
      method: "POST",
      accessToken: logoutAccessToken ?? undefined,
    });
  } finally {
    accessToken = null;
  }
}
