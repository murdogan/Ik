import type {
  AuthUser,
  MeResponseData,
  OrganizationSelectionRequiredData,
  RefreshResponseData,
  SessionGrantData,
} from "./auth-contracts";
import {
  ApiClientError,
  type ApiFileSuccess,
  type ApiPlainCursorSuccess,
  type ApiPlainSuccess,
  type ApiRequestOptions,
  type ApiSuccessEnvelope,
  requestApi,
  requestApiEnvelope,
  requestApiFile,
  requestApiNoContent,
  requestApiPlainCursorSuccess,
  requestApiPlainSuccess,
} from "./api-client";

const REFRESH_PATH = "/api/v1/auth/refresh" as const;
const LOGOUT_PATH = "/api/v1/auth/logout" as const;
const ME_PATH = "/api/v1/me" as const;
const ORGANIZATION_SELECTION_PATH = "/api/v1/auth/organization-selection" as const;

let accessToken: string | null = null;
let sessionGeneration = 0;
let refreshInFlight: Promise<RefreshResponseData> | null = null;
let restoreInFlight: Promise<AuthUser> | null = null;
let organizationSelectionInFlight: Promise<OrganizationSelectionRequiredData> | null =
  null;
let sessionTransitionInProgress = false;
let sessionSuspendedForOrganizationSelection = false;
const sessionChangeListeners = new Set<(change: SessionChange) => void>();

export type SessionChange =
  | { type: "user_updated"; user: AuthUser }
  | { type: "invalidated" };

export function getSessionGeneration(): number {
  return sessionGeneration;
}

export function isSessionGenerationCurrent(generation: number): boolean {
  return generation === sessionGeneration;
}

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
  sessionSuspendedForOrganizationSelection = false;
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
  if (sessionTransitionInProgress || sessionSuspendedForOrganizationSelection) {
    return Promise.reject(new SessionSupersededError());
  }
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
  if (sessionTransitionInProgress || sessionSuspendedForOrganizationSelection) {
    throw new SessionSupersededError();
  }
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

export async function requestAuthenticatedApiPlainSuccess<TResponse>(
  path: `/api/${string}`,
  options: AuthenticatedRequestOptions = {},
): Promise<ApiPlainSuccess<TResponse>> {
  return requestAuthenticated(path, options, (requestPath, requestOptions) =>
    requestApiPlainSuccess<TResponse>(requestPath, requestOptions),
  );
}

export async function requestAuthenticatedApiPlainCursorSuccess<TResponse>(
  path: `/api/${string}`,
  options: AuthenticatedRequestOptions = {},
): Promise<ApiPlainCursorSuccess<TResponse>> {
  return requestAuthenticated(path, options, (requestPath, requestOptions) =>
    requestApiPlainCursorSuccess<TResponse>(requestPath, requestOptions),
  );
}

export async function requestAuthenticatedApiFile(
  path: `/api/${string}`,
  options: AuthenticatedRequestOptions = {},
): Promise<ApiFileSuccess> {
  return requestAuthenticated(path, options, (requestPath, requestOptions) =>
    requestApiFile(requestPath, requestOptions),
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

async function performOrganizationSelectionRequest(): Promise<OrganizationSelectionRequiredData> {
  if (!accessToken) {
    await refreshSession();
  }

  const pendingRefresh = refreshInFlight;
  if (pendingRefresh) {
    await pendingRefresh;
  }

  const requestGeneration = sessionGeneration;
  const selectionAccessToken = accessToken;
  if (!selectionAccessToken) {
    throw new SessionSupersededError();
  }

  sessionTransitionInProgress = true;
  try {
    const data = await requestApi<OrganizationSelectionRequiredData>(
      ORGANIZATION_SELECTION_PATH,
      {
        method: "POST",
        accessToken: selectionAccessToken,
      },
    );
    if (requestGeneration !== sessionGeneration) {
      throw new SessionSupersededError();
    }

    // The server has revoked the previous tenant family and cleared its cookie. Incrementing the
    // client generation prevents any old-tenant response from being applied while the selection
    // credential remains only in the root in-memory provider.
    invalidateSession({ notify: false });
    sessionSuspendedForOrganizationSelection = true;
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
  } finally {
    sessionTransitionInProgress = false;
  }
}

export function requestOrganizationSelection(): Promise<OrganizationSelectionRequiredData> {
  if (organizationSelectionInFlight) {
    return organizationSelectionInFlight;
  }

  const pending = performOrganizationSelectionRequest();
  organizationSelectionInFlight = pending;
  pending.then(
    () => {
      if (organizationSelectionInFlight === pending) {
        organizationSelectionInFlight = null;
      }
    },
    () => {
      if (organizationSelectionInFlight === pending) {
        organizationSelectionInFlight = null;
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
