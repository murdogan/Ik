interface ApiErrorBody {
  code?: unknown;
  correlation_id?: unknown;
}

interface ApiErrorEnvelope {
  error?: ApiErrorBody;
}

interface ApiSuccessEnvelope<TResponse> {
  data: TResponse;
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

export async function postApi<TRequest extends object, TResponse>(
  path: `/api/${string}`,
  body: TRequest,
): Promise<TResponse> {
  let response: Response;

  try {
    response = await fetch(path, {
      method: "POST",
      headers: {
        Accept: "application/json",
        "Content-Type": "application/json",
      },
      credentials: "same-origin",
      cache: "no-store",
      body: JSON.stringify(body),
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

  if (!isRecord(payload) || !("data" in payload)) {
    throw new ApiClientError({
      status: response.status,
      code: "invalid_response",
      correlationId: response.headers.get("x-request-id"),
    });
  }

  return (payload as unknown as ApiSuccessEnvelope<TResponse>).data;
}
