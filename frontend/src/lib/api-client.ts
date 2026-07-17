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
  body?: object | FormData;
  accessToken?: string;
  idempotencyKey?: string;
  accept?: string;
}

export interface ApiFileSuccess {
  blob: Blob;
  contentType: string;
  filename: string | null;
  status: number;
  headers: Headers;
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

function isFormData(value: object | FormData): value is FormData {
  return typeof FormData !== "undefined" && value instanceof FormData;
}

async function sendRawApiRequest(
  path: `/api/${string}`,
  {
    method = "GET",
    body,
    accessToken,
    idempotencyKey,
    accept = "application/json",
  }: ApiRequestOptions,
): Promise<Response> {
  const headers = new Headers({ Accept: accept });
  if (body !== undefined && !isFormData(body)) {
    headers.set("Content-Type", "application/json");
  }
  if (accessToken) {
    headers.set("Authorization", `Bearer ${accessToken}`);
  }
  if (idempotencyKey) {
    headers.set("X-Idempotency-Key", idempotencyKey);
  }

  let response: Response;
  try {
    response = await fetch(path, {
      method,
      headers,
      credentials: "same-origin",
      cache: "no-store",
      body:
        body === undefined
          ? undefined
          : isFormData(body)
            ? body
            : JSON.stringify(body),
    });
  } catch {
    throw new ApiClientError({
      status: null,
      code: "network_error",
    });
  }

  if (!response.ok) {
    const payload = await responsePayload(response);
    const metadata = errorMetadata(payload, response);
    throw new ApiClientError({
      status: response.status,
      code: metadata.code,
      correlationId: metadata.correlationId,
    });
  }

  return response;
}

async function sendApiRequest(
  path: `/api/${string}`,
  options: ApiRequestOptions,
): Promise<{ payload: unknown; response: Response }> {
  const response = await sendRawApiRequest(path, options);
  const payload = await responsePayload(response);

  return { payload, response };
}

function responseFilename(response: Response): string | null {
  const disposition = response.headers.get("content-disposition");
  const match = disposition?.match(/(?:^|;)\s*filename="([^"\\\r\n]{1,255})"(?:;|$)/i);
  return match?.[1] ?? null;
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

export async function requestApiFile(
  path: `/api/${string}`,
  options: ApiRequestOptions = {},
): Promise<ApiFileSuccess> {
  const response = await sendRawApiRequest(path, {
    ...options,
    accept:
      options.accept ??
      "text/csv, application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
  });
  const contentType = response.headers.get("content-type")?.split(";", 1)[0]?.trim() ?? "";
  if (!contentType || contentType === "application/json") {
    throw new ApiClientError({
      status: response.status,
      code: "invalid_response",
      correlationId: response.headers.get("x-request-id"),
    });
  }
  return {
    blob: await response.blob(),
    contentType,
    filename: responseFilename(response),
    status: response.status,
    headers: response.headers,
  };
}

export async function postApi<TRequest extends object, TResponse>(
  path: `/api/${string}`,
  body: TRequest,
): Promise<TResponse> {
  return requestApi<TResponse>(path, { method: "POST", body });
}
