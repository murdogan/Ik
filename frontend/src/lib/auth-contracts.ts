import { ApiClientError } from "./api-client";

export interface AuthTenant {
  slug: string;
  name: string;
}

export type WorkspaceScope = "tenant" | "platform";

export interface RoleSummary {
  id: string;
  code: string;
  name: string;
  scope_type: WorkspaceScope;
}

export interface AuthUser {
  id: string;
  tenant_id: string;
  email: string;
  full_name: string | null;
  tenant: AuthTenant;
  workspace_scope: "tenant";
  roles: RoleSummary[];
  permissions: string[];
  permission_version: number;
}

export type PlatformAuthenticationStrength =
  | "single_factor"
  | "multi_factor"
  | "step_up";

export interface PlatformAuthUser {
  id: string;
  email: string;
  full_name: string | null;
  workspace_scope: "platform";
  roles: RoleSummary[];
  permissions: string[];
  permission_version: number;
  authentication_strength: PlatformAuthenticationStrength;
}

export interface SessionGrantData {
  access_token: string;
  token_type: string;
  expires_in: number;
  user: AuthUser;
}

export interface AuthenticatedLoginResponseData extends SessionGrantData {
  status: "authenticated";
}

export interface PlatformSessionGrantData {
  access_token: string;
  token_type: string;
  expires_in: number;
  user: PlatformAuthUser;
}

export interface PlatformAuthenticatedLoginResponseData
  extends PlatformSessionGrantData {
  status: "authenticated";
}

export type PlatformLoginResponseData = PlatformAuthenticatedLoginResponseData;

export type PlatformRefreshResponseData = PlatformSessionGrantData;

export interface PlatformMeResponseData {
  user: PlatformAuthUser;
}

export interface OrganizationSelectionOption {
  selection_key: string;
  display_name: string;
}

export interface OrganizationSelectionRequiredData {
  status: "organization_selection_required";
  selection_transaction: string;
  expires_in: number;
  organizations: OrganizationSelectionOption[];
}

export interface OrganizationSelectionRequestData {
  selection_transaction: string;
  selection_key: string;
}

export type LoginResponseData =
  | AuthenticatedLoginResponseData
  | OrganizationSelectionRequiredData;

// Refresh rotates an existing tenant-bound session. Unlike login, it can never return an
// organization-selection transaction and the backend response has no `status` discriminator.
export type RefreshResponseData = SessionGrantData;

export interface MeResponseData {
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

export interface OrganizationSelectionErrorPresentation
  extends AuthErrorPresentation {
  terminal: boolean;
}

const GENERIC_LOGIN_ERROR =
  "E-posta veya parola eşleşmedi. Bilgilerinizi kontrol edip yeniden deneyin.";
const GENERIC_ACTIVATION_ERROR =
  "Bu davet bağlantısı geçersiz, süresi dolmuş veya daha önce kullanılmış. Hesabınızı daha önce etkinleştirdiyseniz giriş yapmayı deneyin; aksi halde yöneticinizden yeni bir davet isteyin.";

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
      "E-posta biçimini kontrol edin; ardından parolanızı yeniden girin.",
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

export function platformLoginErrorPresentation(
  cause: unknown,
): AuthErrorPresentation {
  if (!(cause instanceof ApiClientError)) {
    return {
      message:
        "Platform girişi şu anda tamamlanamıyor. Lütfen biraz sonra yeniden deneyin.",
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
      "Çok sayıda platform giriş denemesi yapıldı. Kısa bir süre bekleyip yeniden deneyin.",
      cause,
    );
  }
  if (cause.status === 403 && code === "platform_role_required") {
    return presentation(
      "Bu hesap platform yönetimi için yetkilendirilmemiş. Kurum çalışma alanı için standart giriş ekranını kullanın.",
      cause,
    );
  }
  if (
    [401, 403, 404].includes(cause.status ?? 0) ||
    code.includes("credential") ||
    code.includes("user_not_found")
  ) {
    return presentation(GENERIC_LOGIN_ERROR, cause);
  }
  if (cause.status === 422 || code.includes("validation")) {
    return presentation(
      "E-posta biçimini kontrol edin; ardından parolanızı yeniden girin.",
      cause,
    );
  }
  if ((cause.status ?? 0) >= 500 || code === "invalid_response") {
    return presentation(
      "Platform giriş hizmeti geçici olarak kullanılamıyor. Lütfen biraz sonra yeniden deneyin.",
      cause,
    );
  }

  return presentation(GENERIC_LOGIN_ERROR, cause);
}

export function organizationSelectionErrorPresentation(
  cause: unknown,
): OrganizationSelectionErrorPresentation {
  if (!(cause instanceof ApiClientError)) {
    return {
      message: "Kurum seçimi şu anda tamamlanamıyor. Lütfen yeniden deneyin.",
      terminal: false,
    };
  }

  const code = cause.code.toLowerCase();
  if (cause.status === null || code === "network_error") {
    return {
      ...presentation(
        "Sunucuya ulaşılamadı. Bağlantınızı kontrol edip yeniden deneyin.",
        cause,
      ),
      terminal: false,
    };
  }
  if (
    [400, 401, 403, 404, 409, 410, 422].includes(cause.status ?? 0) ||
    code.includes("selection") ||
    code.includes("credential") ||
    code.includes("session")
  ) {
    return {
      ...presentation(
        "Güvenli kurum seçiminin süresi doldu veya seçim daha önce kullanıldı. E-posta ve parolanızla yeniden giriş yapın.",
        cause,
      ),
      terminal: true,
    };
  }

  return {
    ...presentation(
      "Kurum seçimi şu anda tamamlanamıyor. Lütfen yeniden deneyin.",
      cause,
    ),
    terminal: false,
  };
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
