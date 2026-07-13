interface ApiErrorBody {
  code?: unknown;
  correlation_id?: unknown;
}

interface ApiErrorEnvelope {
  error?: ApiErrorBody;
}

export interface ApiSuccessEnvelope<TResponse, TMeta = unknown> {
  data: TResponse;
  meta: TMeta;
}

export interface ApiPlainSuccess<TResponse> {
  data: TResponse;
  status: number;
  headers: Headers;
}

export interface ApiPlainCursorSuccess<TResponse> extends ApiPlainSuccess<TResponse> {
  nextCursor: string | null;
}

export interface ApiRequestOptions {
  method?: "GET" | "POST" | "PUT" | "PATCH" | "DELETE";
  body?: object;
  accessToken?: string;
}

export class ApiClientError extends Error {
  readonly status: number | null;
  readonly code: string;
  readonly correlationId: string | null;

  constructor({
    status,
    code,
    correlationId,
  }: {
    status: number | null;
    code: string;
    correlationId?: string | null;
  }) {
    super("API request failed");
    this.name = "ApiClientError";
    this.status = status;
    this.code = code;
    this.correlationId = correlationId ?? null;
  }
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function errorMetadata(
  payload: unknown,
  response: Response,
): { code: string; correlationId: string | null } {
  const envelope = isRecord(payload) ? (payload as ApiErrorEnvelope) : null;
  const body = envelope?.error;
  const code = typeof body?.code === "string" ? body.code : "request_failed";
  const bodyCorrelation =
    typeof body?.correlation_id === "string" ? body.correlation_id : null;

  return {
    code,
    correlationId: bodyCorrelation ?? response.headers.get("x-request-id"),
  };
}

async function responsePayload(response: Response): Promise<unknown> {
  const text = await response.text();
  if (!text) {
    return null;
  }

  try {
    return JSON.parse(text) as unknown;
  } catch {
    return null;
  }
}

async function sendApiRequest(
  path: `/api/${string}`,
  { method = "GET", body, accessToken }: ApiRequestOptions,
): Promise<{ payload: unknown; response: Response }> {
  const headers = new Headers({ Accept: "application/json" });
  if (body !== undefined) {
    headers.set("Content-Type", "application/json");
  }
  if (accessToken) {
    headers.set("Authorization", `Bearer ${accessToken}`);
  }

  let response: Response;
  try {
    response = await fetch(path, {
      method,
      headers,
      credentials: "same-origin",
      cache: "no-store",
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  } catch {
    throw new ApiClientError({
      status: null,
      code: "network_error",
    });
  }

  const payload = await responsePayload(response);
  if (!response.ok) {
    const metadata = errorMetadata(payload, response);
    throw new ApiClientError({
      status: response.status,
      code: metadata.code,
      correlationId: metadata.correlationId,
    });
  }

  return { payload, response };
}

export async function requestApi<TResponse>(
  path: `/api/${string}`,
  options: ApiRequestOptions = {},
): Promise<TResponse> {
  const { payload, response } = await sendApiRequest(path, options);

  if (!isRecord(payload) || !("data" in payload)) {
    throw new ApiClientError({
      status: response.status,
      code: "invalid_response",
      correlationId: response.headers.get("x-request-id"),
    });
  }

  return (payload as unknown as ApiSuccessEnvelope<TResponse>).data;
}

export async function requestApiEnvelope<TResponse, TMeta = unknown>(
  path: `/api/${string}`,
  options: ApiRequestOptions = {},
): Promise<ApiSuccessEnvelope<TResponse, TMeta>> {
  const { payload, response } = await sendApiRequest(path, options);

  if (
    !isRecord(payload) ||
    !("data" in payload) ||
    !("meta" in payload) ||
    !isRecord(payload.meta)
  ) {
    throw new ApiClientError({
      status: response.status,
      code: "invalid_response",
      correlationId: response.headers.get("x-request-id"),
    });
  }

  return payload as unknown as ApiSuccessEnvelope<TResponse, TMeta>;
}

export async function requestApiPlainSuccess<TResponse>(
  path: `/api/${string}`,
  options: ApiRequestOptions = {},
): Promise<ApiPlainSuccess<TResponse>> {
  const { payload, response } = await sendApiRequest(path, options);
  return {
    data: payload as TResponse,
    status: response.status,
    headers: response.headers,
  };
}

export async function requestApiPlainCursorSuccess<TResponse>(
  path: `/api/${string}`,
  options: ApiRequestOptions = {},
): Promise<ApiPlainCursorSuccess<TResponse>> {
  const response = await requestApiPlainSuccess<TResponse>(path, options);
  return {
    ...response,
    nextCursor: response.headers.get("x-next-cursor")?.trim() || null,
  };
}

export async function requestApiNoContent(
  path: `/api/${string}`,
  options: ApiRequestOptions,
): Promise<void> {
  const { payload, response } = await sendApiRequest(path, options);

  if (response.status !== 204 || payload !== null) {
    throw new ApiClientError({
      status: response.status,
      code: "invalid_response",
      correlationId: response.headers.get("x-request-id"),
    });
  }
}

export async function postApi<TRequest extends object, TResponse>(
  path: `/api/${string}`,
  body: TRequest,
): Promise<TResponse> {
  return requestApi<TResponse>(path, { method: "POST", body });
}
