import { ApiClientError } from "./api-client";

export interface AuthTenant {
  slug: string;
  name: string;
}

export interface AuthUser {
  id: string;
  tenant_id: string;
  email: string;
  full_name: string | null;
  tenant: AuthTenant;
}

export interface LoginResponseData {
  access_token: string;
  token_type: string;
  expires_in: number;
  user: AuthUser;
}

export interface ActivationResponseData {
  user: AuthUser;
}

export interface AuthErrorPresentation {
  message: string;
  reference?: string | null;
  offerLogin?: boolean;
}

const GENERIC_LOGIN_ERROR =
  "Kurum kodu, e-posta veya parola eşleşmedi. Bilgilerinizi kontrol edip yeniden deneyin.";
const GENERIC_ACTIVATION_ERROR =
  "Bu davet bağlantısı geçersiz, süresi dolmuş veya daha önce kullanılmış. Hesabınızı daha önce etkinleştirdiyseniz giriş yapmayı deneyin; aksi halde yöneticinizden yeni bir davet isteyin.";
const TENANT_SLUG_PATTERN = /^[a-z0-9](?:[a-z0-9-]{0,78}[a-z0-9])?$/;

export function validatedTenantSlug(value: unknown): string {
  if (typeof value !== "string") {
    return "";
  }

  const normalized = value.trim().toLowerCase();
  if (
    normalized.length < 2 ||
    normalized.length > 80 ||
    !TENANT_SLUG_PATTERN.test(normalized)
  ) {
    return "";
  }
  return normalized;
}

function presentation(
  message: string,
  error: ApiClientError,
): AuthErrorPresentation {
  return {
    message,
    reference: error.correlationId,
  };
}

export function loginErrorPresentation(cause: unknown): AuthErrorPresentation {
  if (!(cause instanceof ApiClientError)) {
    return { message: "Giriş şu anda tamamlanamıyor. Lütfen biraz sonra yeniden deneyin." };
  }

  const code = cause.code.toLowerCase();
  if (cause.status === null || code === "network_error") {
    return presentation(
      "Sunucuya ulaşılamadı. İnternet bağlantınızı kontrol edip yeniden deneyin.",
      cause,
    );
  }
  if (cause.status === 429 || code.includes("rate_limit")) {
    return presentation(
      "Çok sayıda giriş denemesi yapıldı. Kısa bir süre bekleyip yeniden deneyin.",
      cause,
    );
  }
  if (
    [401, 403, 404].includes(cause.status ?? 0) ||
    code.includes("credential") ||
    code.includes("tenant_not_found") ||
    code.includes("user_not_found")
  ) {
    return presentation(GENERIC_LOGIN_ERROR, cause);
  }
  if (cause.status === 422 || code.includes("validation")) {
    return presentation(
      "Kurum kodu ve e-posta biçimini kontrol edin; ardından parolanızı yeniden girin.",
      cause,
    );
  }
  if ((cause.status ?? 0) >= 500 || code === "invalid_response") {
    return presentation(
      "Giriş hizmeti geçici olarak kullanılamıyor. Lütfen biraz sonra yeniden deneyin.",
      cause,
    );
  }

  return presentation(GENERIC_LOGIN_ERROR, cause);
}

export function activationErrorPresentation(cause: unknown): AuthErrorPresentation {
  if (!(cause instanceof ApiClientError)) {
    return {
      message: "Hesabınız şu anda etkinleştirilemiyor. Lütfen biraz sonra yeniden deneyin.",
    };
  }

  const code = cause.code.toLowerCase();
  if (cause.status === null || code === "network_error") {
    return presentation(
      "Sunucuya ulaşılamadı. İnternet bağlantınızı kontrol edip yeniden deneyin.",
      cause,
    );
  }
  if (cause.status === 429 || code.includes("rate_limit")) {
    return presentation(
      "Çok sayıda deneme yapıldı. Kısa bir süre bekleyip yeniden deneyin.",
      cause,
    );
  }
  if (code.includes("password")) {
    return presentation(
      "Parolanız güvenlik gereksinimlerini karşılamıyor. En az 12 karakterlik, size özel bir parola seçin.",
      cause,
    );
  }
  if (
    [400, 404, 409, 410].includes(cause.status ?? 0) ||
    code.includes("token") ||
    code.includes("invitation") ||
    code.includes("activation")
  ) {
    return {
      ...presentation(GENERIC_ACTIVATION_ERROR, cause),
      offerLogin: true,
    };
  }
  if (cause.status === 422 || code.includes("validation")) {
    return presentation(
      "Parolanızı kontrol edin. En az 12 karakter kullanın ve iki alana aynı parolayı yazın.",
      cause,
    );
  }
  if ((cause.status ?? 0) >= 500 || code === "invalid_response") {
    return presentation(
      "Etkinleştirme hizmeti geçici olarak kullanılamıyor. Davet bağlantınızı kapatmadan biraz sonra yeniden deneyin.",
      cause,
    );
  }

  return {
    ...presentation(GENERIC_ACTIVATION_ERROR, cause),
    offerLogin: true,
  };
}
