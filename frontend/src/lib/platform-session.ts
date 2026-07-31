import type {
  PlatformAuthUser,
  PlatformLoginResponseData,
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
const PLATFORM_LOGIN_PATH = "/api/v1/platform/auth/login" as const;
const PLATFORM_LOGOUT_PATH = "/api/v1/platform/auth/logout" as const;
const PLATFORM_ME_PATH = "/api/v1/platform/me" as const;
// Keep the v1 wire names compatible with already-open tabs while using the
// primitive for every platform cookie transition, not only refresh.
export const PLATFORM_SESSION_TRANSITION_LOCK_NAME =
  "wf:platform-session:refresh:v1";
const PLATFORM_SESSION_CHANNEL_NAME = "wf:platform-session:updates:v1";
const PLATFORM_SESSION_MARKER_KEY = "wf:platform-session:marker:v1";
const PLATFORM_SESSION_EVENT_KEY = "wf:platform-session:event:v1";
const PLATFORM_EXPLICIT_TRANSITION_KEY =
  "wf:platform-session:explicit-transition:v1";
const PLATFORM_SESSION_TRANSITION_LEASE_KEY =
  "wf:platform-session:refresh-lease:v1";
const PLATFORM_COORDINATION_WAIT_MS = 12_000;
const PLATFORM_TRANSITION_LEASE_MS = 4_000;
const PLATFORM_TRANSITION_LEASE_HEARTBEAT_MS = 1_000;
const PLATFORM_TRANSITION_LEASE_POLL_MS = 75;
const PLATFORM_TRANSITION_LEASE_SETTLE_MS = 50;

let platformAccessToken: string | null = null;
let platformSessionGeneration = 0;
let platformRefreshInFlight: Promise<PlatformRefreshResponseData> | null = null;
let platformRestoreInFlight: Promise<PlatformAuthUser> | null = null;
let platformCoordinatorInitialized = false;
let platformCoordinatorTabId: string | null = null;
let platformSessionChannel: BroadcastChannel | null = null;
let platformLastHandledUpdateId: string | null = null;
let platformExplicitTransitionId: string | null = null;
let platformSessionTransitionAt = 0;
let platformTransitionQueueTail: Promise<void> = Promise.resolve();
const platformCoordinatorWaiters = new Set<() => void>();
const platformSessionChangeListeners = new Set<
  (change: PlatformSessionChange) => void
>();

interface PlatformSessionMarker {
  version: 1;
  updateId: string;
  type: "session_updated" | "invalidated";
  issuedAt: number;
}

interface PlatformSessionUpdateMessage {
  scope: "platform";
  version: 1;
  senderId: string;
  updateId: string;
  transitionId?: string;
  type: "session_updated";
  reason: "established" | "refresh";
  startedAt: number;
  issuedAt: number;
}

interface PlatformSessionInvalidationMessage {
  scope: "platform";
  version: 1;
  senderId: string;
  updateId: string;
  transitionId?: string;
  type: "invalidated";
  reason:
    | "authorization_failed"
    | "logout"
    | "refresh_failed"
    | "transition_started";
  startedAt: number;
  issuedAt: number;
}

type PlatformSessionCoordinatorMessage =
  | PlatformSessionUpdateMessage
  | PlatformSessionInvalidationMessage;

interface PlatformSessionTransitionLease {
  version: 1;
  ownerId: string;
  leaseId: string;
  expiresAt: number;
}

export type PlatformSessionChange =
  | { type: "user_updated"; user: PlatformAuthUser }
  | { type: "invalidated" };

type PlatformSessionSupersededPhase = "pre_dispatch" | "post_response";

class PlatformSessionSupersededError extends Error {
  readonly phase: PlatformSessionSupersededPhase;

  constructor(phase: PlatformSessionSupersededPhase = "pre_dispatch") {
    super("Platform session changed while the request was in flight");
    this.name = "PlatformSessionSupersededError";
    this.phase = phase;
  }
}

export function isPostResponsePlatformSessionSupersededError(
  cause: unknown,
): boolean {
  return (
    cause instanceof PlatformSessionSupersededError &&
    cause.phase === "post_response"
  );
}

class PlatformSessionTransitionCoordinationTimeoutError extends Error {
  constructor() {
    super("Timed out while coordinating a platform session transition");
    this.name = "PlatformSessionTransitionCoordinationTimeoutError";
  }
}

class PlatformWebLocksUnavailableError extends Error {
  constructor() {
    super("The platform refresh Web Lock could not be acquired");
    this.name = "PlatformWebLocksUnavailableError";
  }
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function isFiniteTimestamp(value: unknown): value is number {
  return typeof value === "number" && Number.isFinite(value) && value >= 0;
}

function isPlatformSessionGrant(
  value: unknown,
): value is PlatformRefreshResponseData {
  if (
    !isRecord(value) ||
    typeof value.access_token !== "string" ||
    value.access_token.length === 0 ||
    value.access_token.length > 16_384 ||
    typeof value.token_type !== "string" ||
    value.token_type.length === 0 ||
    typeof value.expires_in !== "number" ||
    !Number.isFinite(value.expires_in) ||
    value.expires_in <= 0 ||
    !isRecord(value.user)
  ) {
    return false;
  }

  const user = value.user;
  return (
    user.workspace_scope === "platform" &&
    typeof user.id === "string" &&
    typeof user.email === "string" &&
    (typeof user.full_name === "string" || user.full_name === null) &&
    Array.isArray(user.roles) &&
    Array.isArray(user.permissions) &&
    user.permissions.every((permission) => typeof permission === "string") &&
    typeof user.permission_version === "number" &&
    Number.isSafeInteger(user.permission_version) &&
    (user.authentication_strength === "single_factor" ||
      user.authentication_strength === "multi_factor" ||
      user.authentication_strength === "step_up")
  );
}

function isPlatformSessionCoordinatorMessage(
  value: unknown,
): value is PlatformSessionCoordinatorMessage {
  if (
    !isRecord(value) ||
    value.scope !== "platform" ||
    value.version !== 1 ||
    typeof value.senderId !== "string" ||
    typeof value.updateId !== "string" ||
    (value.transitionId !== undefined &&
      (typeof value.transitionId !== "string" ||
        value.transitionId.length === 0 ||
        value.transitionId.length > 256)) ||
    !isFiniteTimestamp(value.startedAt) ||
    !isFiniteTimestamp(value.issuedAt)
  ) {
    return false;
  }

  if (value.type === "session_updated") {
    return value.reason === "established" || value.reason === "refresh";
  }

  return (
    value.type === "invalidated" &&
    (value.reason === "authorization_failed" ||
      value.reason === "logout" ||
      value.reason === "refresh_failed" ||
      value.reason === "transition_started")
  );
}

function newPlatformCoordinatorId(): string {
  if (
    typeof crypto !== "undefined" &&
    typeof crypto.randomUUID === "function"
  ) {
    return crypto.randomUUID();
  }
  return `${Date.now().toString(36)}-${Math.random().toString(36).slice(2)}`;
}

function platformLocalStorage(): Storage | null {
  if (typeof window === "undefined") {
    return null;
  }
  try {
    return window.localStorage;
  } catch {
    return null;
  }
}

function wakePlatformCoordinatorWaiters(): void {
  for (const wake of [...platformCoordinatorWaiters]) {
    wake();
  }
}

function readPlatformExplicitTransition(): PlatformSessionCoordinatorMessage | null {
  const storage = platformLocalStorage();
  if (!storage) {
    return null;
  }
  try {
    const parsed: unknown = JSON.parse(
      storage.getItem(PLATFORM_EXPLICIT_TRANSITION_KEY) ?? "null",
    );
    if (
      isPlatformSessionCoordinatorMessage(parsed) &&
      ((parsed.type === "session_updated" && parsed.reason === "established") ||
        (parsed.type === "invalidated" &&
          (parsed.reason === "logout" ||
            parsed.reason === "transition_started")))
    ) {
      return parsed;
    }
  } catch {
    // Treat corrupt or unavailable explicit transition state as absent.
  }
  return null;
}

function publishPlatformSessionMarker(
  message: PlatformSessionCoordinatorMessage,
): void {
  const storage = platformLocalStorage();
  if (!storage) {
    return;
  }
  const marker: PlatformSessionMarker = {
    version: 1,
    updateId: message.updateId,
    type: message.type,
    issuedAt: message.issuedAt,
  };
  try {
    storage.setItem(PLATFORM_SESSION_MARKER_KEY, JSON.stringify(marker));
  } catch {
    // BroadcastChannel can still coordinate when storage is unavailable.
  }
}

function handlePlatformSessionCoordinatorMessage(value: unknown): void {
  if (
    !isPlatformSessionCoordinatorMessage(value) ||
    value.senderId === platformCoordinatorTabId ||
    value.updateId === platformLastHandledUpdateId
  ) {
    return;
  }

  platformLastHandledUpdateId = value.updateId;
  if (value.type === "session_updated") {
    if (value.startedAt < platformSessionTransitionAt) {
      wakePlatformCoordinatorWaiters();
      return;
    }
    if (value.reason === "established") {
      const isAmbiguousEqualTimestamp =
        value.startedAt === platformSessionTransitionAt &&
        (value.transitionId === undefined ||
          platformExplicitTransitionId === null ||
          value.transitionId !== platformExplicitTransitionId);
      if (
        isAmbiguousEqualTimestamp ||
        value.issuedAt < platformSessionTransitionAt
      ) {
        wakePlatformCoordinatorWaiters();
        return;
      }
      platformSessionTransitionAt = value.issuedAt;
      platformExplicitTransitionId = value.transitionId ?? null;
      platformSessionGeneration += 1;
      platformAccessToken = null;
      platformRefreshInFlight = null;
      platformRestoreInFlight = null;
      void refreshPlatformSession().catch(() => {
        // performPlatformRefresh publishes terminal invalidation on failure.
      });
    }
    wakePlatformCoordinatorWaiters();
    return;
  }

  const isStaleRefreshFailure =
    value.reason === "refresh_failed" &&
    value.startedAt <= platformSessionTransitionAt;
  const isStaleCompletedTransitionStart =
    value.reason === "transition_started" &&
    value.transitionId !== undefined &&
    value.transitionId === platformExplicitTransitionId &&
    value.startedAt <= platformSessionTransitionAt;
  if (
    isStaleRefreshFailure ||
    isStaleCompletedTransitionStart ||
    value.issuedAt < platformSessionTransitionAt
  ) {
    wakePlatformCoordinatorWaiters();
    return;
  }
  invalidatePlatformSession({
    broadcast: false,
    reason: value.reason,
    transitionId: value.transitionId,
    transitionAt:
      value.reason === "transition_started" ? value.startedAt : value.issuedAt,
  });
  wakePlatformCoordinatorWaiters();
}

function ensurePlatformSessionCoordinator(): void {
  if (platformCoordinatorInitialized || typeof window === "undefined") {
    return;
  }
  platformCoordinatorInitialized = true;
  platformCoordinatorTabId = newPlatformCoordinatorId();

  if (typeof BroadcastChannel === "function") {
    try {
      platformSessionChannel = new BroadcastChannel(
        PLATFORM_SESSION_CHANNEL_NAME,
      );
      platformSessionChannel.addEventListener("message", (event) => {
        handlePlatformSessionCoordinatorMessage(event.data);
      });
    } catch {
      platformSessionChannel = null;
    }
  }

  window.addEventListener("storage", (event) => {
    if (
      (event.key === PLATFORM_SESSION_EVENT_KEY ||
        event.key === PLATFORM_EXPLICIT_TRANSITION_KEY) &&
      event.newValue
    ) {
      try {
        handlePlatformSessionCoordinatorMessage(JSON.parse(event.newValue));
      } catch {
        // Ignore malformed same-origin coordination events.
      }
      return;
    }
    if (
      event.key === PLATFORM_SESSION_MARKER_KEY ||
      event.key === PLATFORM_SESSION_TRANSITION_LEASE_KEY
    ) {
      wakePlatformCoordinatorWaiters();
    }
  });
}

function publishPlatformSessionCoordinatorMessage(
  message: PlatformSessionCoordinatorMessage,
): void {
  ensurePlatformSessionCoordinator();
  publishPlatformSessionMarker(message);
  if (
    (message.type === "session_updated" && message.reason === "established") ||
    (message.type === "invalidated" &&
      (message.reason === "logout" ||
        message.reason === "transition_started"))
  ) {
    const storage = platformLocalStorage();
    try {
      storage?.setItem(
        PLATFORM_EXPLICIT_TRANSITION_KEY,
        JSON.stringify(message),
      );
    } catch {
      // BroadcastChannel still provides best-effort delivery when storage fails.
    }
  }
  platformLastHandledUpdateId = message.updateId;

  let channelDelivered = false;
  if (platformSessionChannel) {
    try {
      platformSessionChannel.postMessage(message);
      channelDelivered = true;
    } catch {
      platformSessionChannel = null;
    }
  }

  if (!channelDelivered) {
    const storage = platformLocalStorage();
    if (storage) {
      try {
        // This value is removed synchronously. It exists only to deliver an
        // in-memory-equivalent storage event when BroadcastChannel is absent.
        storage.setItem(PLATFORM_SESSION_EVENT_KEY, JSON.stringify(message));
        storage.removeItem(PLATFORM_SESSION_EVENT_KEY);
      } catch {
        // No cross-document primitive remains; document-local single-flight
        // still prevents duplicate requests inside this tab.
      }
    }
  }
  wakePlatformCoordinatorWaiters();
}

async function waitForPlatformCoordinatorSignal(timeoutMs: number): Promise<void> {
  await new Promise<void>((resolve) => {
    const finish = () => {
      clearTimeout(timer);
      platformCoordinatorWaiters.delete(finish);
      resolve();
    };
    platformCoordinatorWaiters.add(finish);
    const timer = setTimeout(finish, timeoutMs);
  });
}

function publishPlatformSessionChange(change: PlatformSessionChange): void {
  for (const listener of platformSessionChangeListeners) {
    listener(change);
  }
}

function applyPlatformSession(data: PlatformSessionGrantData): void {
  platformAccessToken = data.access_token;
  publishPlatformSessionChange({ type: "user_updated", user: data.user });
  wakePlatformCoordinatorWaiters();
}

function invalidatePlatformSession({
  notify = true,
  broadcast = true,
  reason = "authorization_failed",
  operationStartedAt,
  transitionId,
  transitionAt,
}: {
  notify?: boolean;
  broadcast?: boolean;
  reason?: PlatformSessionInvalidationMessage["reason"];
  operationStartedAt?: number;
  transitionId?: string;
  transitionAt?: number;
} = {}): string | null {
  const issuedAt = transitionAt ?? Date.now();
  platformSessionTransitionAt = Math.max(
    platformSessionTransitionAt,
    issuedAt,
  );
  platformExplicitTransitionId = transitionId ?? null;
  platformSessionGeneration += 1;
  platformAccessToken = null;
  platformRefreshInFlight = null;
  platformRestoreInFlight = null;
  if (notify) {
    publishPlatformSessionChange({ type: "invalidated" });
  }
  let publishedUpdateId: string | null = null;
  if (broadcast) {
    ensurePlatformSessionCoordinator();
    publishedUpdateId = newPlatformCoordinatorId();
    publishPlatformSessionCoordinatorMessage({
      scope: "platform",
      version: 1,
      senderId: platformCoordinatorTabId ?? newPlatformCoordinatorId(),
      updateId: publishedUpdateId,
      transitionId,
      type: "invalidated",
      reason,
      startedAt: operationStartedAt ?? issuedAt,
      issuedAt,
    });
  }
  wakePlatformCoordinatorWaiters();
  return publishedUpdateId;
}

export function subscribeToPlatformSessionChanges(
  listener: (change: PlatformSessionChange) => void,
): () => void {
  platformSessionChangeListeners.add(listener);
  return () => platformSessionChangeListeners.delete(listener);
}

function beginExplicitPlatformSessionTransition(
  startedAt: number,
  transitionId: string,
): number {
  ensurePlatformSessionCoordinator();
  platformSessionTransitionAt = Math.max(
    platformSessionTransitionAt,
    startedAt,
  );
  platformExplicitTransitionId = transitionId;
  platformSessionGeneration += 1;
  platformAccessToken = null;
  platformRefreshInFlight = null;
  platformRestoreInFlight = null;
  wakePlatformCoordinatorWaiters();
  return platformSessionGeneration;
}

function completePlatformSessionEstablishment(
  data: PlatformSessionGrantData,
  startedAt: number,
  transitionId: string,
): void {
  const updateId = newPlatformCoordinatorId();
  platformExplicitTransitionId = transitionId;
  applyPlatformSession(data);
  platformRestoreInFlight = null;
  publishPlatformSessionCoordinatorMessage({
    scope: "platform",
    version: 1,
    senderId: platformCoordinatorTabId ?? newPlatformCoordinatorId(),
    updateId,
    transitionId,
    type: "session_updated",
    reason: "established",
    startedAt,
    issuedAt: Date.now(),
  });
}

export function establishPlatformSession(data: PlatformSessionGrantData): void {
  if (!isPlatformSessionGrant(data)) {
    throw new ApiClientError({ status: 200, code: "invalid_response" });
  }
  const startedAt = Date.now();
  const transitionId = newPlatformCoordinatorId();
  beginExplicitPlatformSessionTransition(startedAt, transitionId);
  completePlatformSessionEstablishment(data, startedAt, transitionId);
}

export async function loginPlatformSession({
  email,
  password,
}: {
  email: string;
  password: string;
}): Promise<PlatformLoginResponseData> {
  const startedAt = Date.now();
  const transitionId = newPlatformCoordinatorId();
  const observedMarkerId = invalidatePlatformSession({
    reason: "transition_started",
    operationStartedAt: startedAt,
    transitionId,
  });
  const transitionGeneration = platformSessionGeneration;

  return withPlatformSessionTransitionLock(async (signal) => {
    reconcilePlatformExplicitTransition(observedMarkerId);
    if (transitionGeneration !== platformSessionGeneration) {
      throw new PlatformSessionSupersededError();
    }
    const data = await requestApi<PlatformLoginResponseData>(
      PLATFORM_LOGIN_PATH,
      {
        method: "POST",
        body: { email, password },
        signal,
      },
    );
    reconcilePlatformExplicitTransition(observedMarkerId);
    if (transitionGeneration !== platformSessionGeneration) {
      throw new PlatformSessionSupersededError("post_response");
    }
    if (
      data.status !== "authenticated" ||
      !isPlatformSessionGrant(data)
    ) {
      throw new ApiClientError({ status: 200, code: "invalid_response" });
    }
    completePlatformSessionEstablishment(data, startedAt, transitionId);
    return data;
  });
}

async function performPlatformRefresh(
  generation: number,
  signal: AbortSignal,
): Promise<PlatformRefreshResponseData> {
  const startedAt = Date.now();
  const updateId = newPlatformCoordinatorId();
  try {
    const data = await requestApi<PlatformRefreshResponseData>(
      PLATFORM_REFRESH_PATH,
      { method: "POST", signal },
    );
    if (generation !== platformSessionGeneration) {
      throw new PlatformSessionSupersededError();
    }
    if (!isPlatformSessionGrant(data)) {
      throw new ApiClientError({ status: 200, code: "invalid_response" });
    }
    applyPlatformSession(data);
    publishPlatformSessionCoordinatorMessage({
      scope: "platform",
      version: 1,
      senderId: platformCoordinatorTabId ?? newPlatformCoordinatorId(),
      updateId,
      type: "session_updated",
      reason: "refresh",
      startedAt,
      issuedAt: Date.now(),
    });
    return data;
  } catch (cause) {
    if (generation === platformSessionGeneration) {
      invalidatePlatformSession({
        reason: "refresh_failed",
        operationStartedAt: startedAt,
      });
    }
    throw cause;
  }
}

function platformLockManager(): LockManager | null {
  if (typeof navigator === "undefined") {
    return null;
  }
  try {
    const locks = (navigator as unknown as { locks?: LockManager }).locks;
    return locks && typeof locks.request === "function" ? locks : null;
  } catch {
    return null;
  }
}

async function withPlatformTransitionWebLock<T>(
  lockManager: LockManager,
  operation: (signal: AbortSignal) => Promise<T>,
): Promise<T> {
  const controller = new AbortController();
  let lockEntered = false;
  let waitExpired = false;
  const timer = setTimeout(() => {
    waitExpired = true;
    controller.abort();
  }, PLATFORM_COORDINATION_WAIT_MS);

  try {
    return await lockManager.request(
      PLATFORM_SESSION_TRANSITION_LOCK_NAME,
      { mode: "exclusive", signal: controller.signal },
      async () => {
        lockEntered = true;
        clearTimeout(timer);
        const operationTimer = setTimeout(
          () => controller.abort(),
          PLATFORM_COORDINATION_WAIT_MS,
        );
        try {
          return await operation(controller.signal);
        } finally {
          clearTimeout(operationTimer);
        }
      },
    );
  } catch (cause) {
    if (waitExpired && !lockEntered) {
      throw new PlatformSessionTransitionCoordinationTimeoutError();
    }
    if (!lockEntered) {
      throw new PlatformWebLocksUnavailableError();
    }
    throw cause;
  } finally {
    clearTimeout(timer);
  }
}

function parsePlatformTransitionLease(
  value: string | null,
): PlatformSessionTransitionLease | null {
  if (!value) {
    return null;
  }
  try {
    const parsed: unknown = JSON.parse(value);
    if (
      isRecord(parsed) &&
      parsed.version === 1 &&
      typeof parsed.ownerId === "string" &&
      typeof parsed.leaseId === "string" &&
      isFiniteTimestamp(parsed.expiresAt)
    ) {
      return parsed as unknown as PlatformSessionTransitionLease;
    }
  } catch {
    // A malformed lease is equivalent to an expired lease.
  }
  return null;
}

function readPlatformTransitionLease(
  storage: Storage,
): PlatformSessionTransitionLease | null {
  try {
    return parsePlatformTransitionLease(
      storage.getItem(PLATFORM_SESSION_TRANSITION_LEASE_KEY),
    );
  } catch {
    return null;
  }
}

function platformTransitionLeaseMatches(
  left: PlatformSessionTransitionLease | null,
  right: PlatformSessionTransitionLease,
): boolean {
  return (
    left?.ownerId === right.ownerId &&
    left.leaseId === right.leaseId
  );
}

function writePlatformTransitionLease(
  storage: Storage,
  lease: PlatformSessionTransitionLease,
): boolean {
  try {
    storage.setItem(
      PLATFORM_SESSION_TRANSITION_LEASE_KEY,
      JSON.stringify(lease),
    );
    return true;
  } catch {
    return false;
  }
}

function releasePlatformTransitionLease(
  storage: Storage,
  lease: PlatformSessionTransitionLease,
): void {
  try {
    if (
      platformTransitionLeaseMatches(
        readPlatformTransitionLease(storage),
        lease,
      )
    ) {
      storage.removeItem(PLATFORM_SESSION_TRANSITION_LEASE_KEY);
    }
  } catch {
    // The lease expires even when storage becomes unavailable during release.
  }
}

async function withPlatformTransitionStorageLease<T>(
  storage: Storage,
  operation: (signal: AbortSignal) => Promise<T>,
): Promise<T> {
  const ownerId = platformCoordinatorTabId ?? newPlatformCoordinatorId();
  const deadline = Date.now() + PLATFORM_COORDINATION_WAIT_MS;

  while (Date.now() < deadline) {
    const now = Date.now();
    const currentLease = readPlatformTransitionLease(storage);
    if (!currentLease || currentLease.expiresAt <= now) {
      const candidate: PlatformSessionTransitionLease = {
        version: 1,
        ownerId,
        leaseId: newPlatformCoordinatorId(),
        expiresAt: now + PLATFORM_TRANSITION_LEASE_MS,
      };
      if (!writePlatformTransitionLease(storage, candidate)) {
        throw new PlatformSessionTransitionCoordinationTimeoutError();
      }

      await waitForPlatformCoordinatorSignal(
        PLATFORM_TRANSITION_LEASE_SETTLE_MS,
      );
      if (
        platformTransitionLeaseMatches(
          readPlatformTransitionLease(storage),
          candidate,
        )
      ) {
        const controller = new AbortController();
        let leaseLost = false;
        let operationExpired = false;
        const heartbeat = setInterval(() => {
          const activeLease = readPlatformTransitionLease(storage);
          if (!platformTransitionLeaseMatches(activeLease, candidate)) {
            leaseLost = true;
            controller.abort();
            return;
          }
          candidate.expiresAt = Date.now() + PLATFORM_TRANSITION_LEASE_MS;
          if (!writePlatformTransitionLease(storage, candidate)) {
            leaseLost = true;
            controller.abort();
          }
        }, PLATFORM_TRANSITION_LEASE_HEARTBEAT_MS);
        const operationTimer = setTimeout(() => {
          operationExpired = true;
          controller.abort();
        }, PLATFORM_COORDINATION_WAIT_MS);
        try {
          const result = await operation(controller.signal);
          if (
            leaseLost ||
            operationExpired ||
            !platformTransitionLeaseMatches(
              readPlatformTransitionLease(storage),
              candidate,
            )
          ) {
            throw new PlatformSessionTransitionCoordinationTimeoutError();
          }
          return result;
        } catch (cause) {
          if (leaseLost || operationExpired) {
            throw new PlatformSessionTransitionCoordinationTimeoutError();
          }
          throw cause;
        } finally {
          clearTimeout(operationTimer);
          clearInterval(heartbeat);
          releasePlatformTransitionLease(storage, candidate);
        }
      }
    }

    const remaining = Math.max(1, deadline - Date.now());
    await waitForPlatformCoordinatorSignal(
      Math.min(PLATFORM_TRANSITION_LEASE_POLL_MS, remaining),
    );
  }

  throw new PlatformSessionTransitionCoordinationTimeoutError();
}

async function runPlatformSessionTransition<T>(
  operation: (signal: AbortSignal) => Promise<T>,
): Promise<T> {
  if (typeof window === "undefined") {
    return operation(new AbortController().signal);
  }

  ensurePlatformSessionCoordinator();
  const lockManager = platformLockManager();
  if (lockManager) {
    try {
      return await withPlatformTransitionWebLock(lockManager, operation);
    } catch (cause) {
      if (!(cause instanceof PlatformWebLocksUnavailableError)) {
        throw cause;
      }
      // A browser can expose a non-functional Web Locks implementation. The
      // bounded same-origin lease remains the cross-document fallback.
    }
  }

  const storage = platformLocalStorage();
  if (storage) {
    return withPlatformTransitionStorageLease(storage, operation);
  }
  throw new PlatformSessionTransitionCoordinationTimeoutError();
}

export async function withPlatformSessionTransitionLock<T>(
  operation: (signal: AbortSignal) => Promise<T>,
): Promise<T> {
  const ready = platformTransitionQueueTail.catch(() => {});
  let releaseTurn = () => {};
  const turn = new Promise<void>((resolve) => {
    releaseTurn = resolve;
  });
  platformTransitionQueueTail = ready.then(() => turn);
  await ready;
  try {
    return await runPlatformSessionTransition(operation);
  } finally {
    releaseTurn();
  }
}

function reconcilePlatformExplicitTransition(
  observedMarkerId: string | null,
): string | null {
  const currentTransition = readPlatformExplicitTransition();
  if (
    currentTransition !== null &&
    currentTransition.updateId !== observedMarkerId
  ) {
    // BroadcastChannel delivery is asynchronous and may lag behind lock
    // hand-off. Reconcile the durable, secret-free explicit transition before
    // dispatching under a principal generation that may be stale.
    handlePlatformSessionCoordinatorMessage(currentTransition);
  }
  return currentTransition?.updateId ?? null;
}

async function performCoordinatedPlatformRefresh(
  generation: number,
  observedMarkerId: string | null,
): Promise<PlatformRefreshResponseData> {
  // Every document obtains its own in-memory access grant. The shared
  // HttpOnly refresh cookie is rotated serially, while the coordinator only
  // announces secret-free transition markers.
  return withPlatformSessionTransitionLock(async (signal) => {
    reconcilePlatformExplicitTransition(observedMarkerId);
    if (generation !== platformSessionGeneration) {
      throw new PlatformSessionSupersededError();
    }
    return performPlatformRefresh(generation, signal);
  });
}

export function refreshPlatformSession(): Promise<PlatformRefreshResponseData> {
  if (platformRefreshInFlight) {
    return platformRefreshInFlight;
  }

  ensurePlatformSessionCoordinator();
  const generation = platformSessionGeneration;
  const observedMarkerId =
    readPlatformExplicitTransition()?.updateId ?? null;
  const pending = performCoordinatedPlatformRefresh(
    generation,
    observedMarkerId,
  );
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

function shouldRecoverPlatformAuthentication(cause: unknown): boolean {
  return (
    cause instanceof ApiClientError &&
    (cause.status === 401 ||
      (cause.status === 403 && cause.code === "platform_access_denied"))
  );
}

async function requestPlatformAuthenticated<TResponse>(
  path: `/api/${string}`,
  options: PlatformAuthenticatedRequestOptions,
  requester: PlatformAuthenticatedRequester<TResponse>,
): Promise<TResponse> {
  const requestMarkerId = reconcilePlatformExplicitTransition(
    platformLastHandledUpdateId,
  );
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
    reconcilePlatformExplicitTransition(requestMarkerId);
    if (requestGeneration !== platformSessionGeneration) {
      throw new PlatformSessionSupersededError("post_response");
    }
    return data;
  } catch (cause) {
    reconcilePlatformExplicitTransition(requestMarkerId);
    if (requestGeneration !== platformSessionGeneration) {
      throw new PlatformSessionSupersededError("post_response");
    }
    if (!shouldRecoverPlatformAuthentication(cause)) {
      throw cause;
    }
  }

  reconcilePlatformExplicitTransition(requestMarkerId);
  if (requestGeneration !== platformSessionGeneration) {
    throw new PlatformSessionSupersededError();
  }

  if (!platformAccessToken || platformAccessToken === attemptedToken) {
    await refreshPlatformSession();
  }

  const retryMarkerId = reconcilePlatformExplicitTransition(requestMarkerId);
  if (requestGeneration !== platformSessionGeneration) {
    throw new PlatformSessionSupersededError();
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
    reconcilePlatformExplicitTransition(retryMarkerId);
    if (requestGeneration !== platformSessionGeneration) {
      throw new PlatformSessionSupersededError("post_response");
    }
    return data;
  } catch (cause) {
    reconcilePlatformExplicitTransition(retryMarkerId);
    if (requestGeneration !== platformSessionGeneration) {
      throw new PlatformSessionSupersededError("post_response");
    }
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
  publishPlatformSessionChange({ type: "user_updated", user: data.user });
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
  const logoutAccessToken = platformAccessToken;
  const logoutStartedAt = Date.now();
  const transitionId = newPlatformCoordinatorId();
  const observedMarkerId = invalidatePlatformSession({
    notify: false,
    reason: "logout",
    operationStartedAt: logoutStartedAt,
    transitionId,
  });
  const logoutGeneration = platformSessionGeneration;

  await withPlatformSessionTransitionLock(async (signal) => {
    reconcilePlatformExplicitTransition(observedMarkerId);
    if (logoutGeneration !== platformSessionGeneration) {
      throw new PlatformSessionSupersededError();
    }
    try {
      await requestApiNoContent(PLATFORM_LOGOUT_PATH, {
        method: "POST",
        accessToken: logoutAccessToken ?? undefined,
        signal,
      });
    } finally {
      if (logoutGeneration === platformSessionGeneration) {
        platformAccessToken = null;
      }
    }
  });
}
