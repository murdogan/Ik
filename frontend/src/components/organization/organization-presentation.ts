import { ApiClientError } from "@/lib/api-client";
import type {
  BranchStatus,
  DepartmentStatus,
  LegalEntityStatus,
} from "@/lib/organization";

export interface OrganizationErrorPresentation {
  message: string;
  reference?: string | null;
}

export type OrganizationAction =
  | "legal_list"
  | "legal_read"
  | "legal_update"
  | "branch_list"
  | "branch_create"
  | "branch_update"
  | "branch_archive"
  | "department_tree"
  | "department_history"
  | "department_create"
  | "department_update"
  | "department_move"
  | "department_archive";

const GENERIC_MESSAGES: Record<OrganizationAction, string> = {
  legal_list: "Tüzel kişilikler şu anda yüklenemiyor. Lütfen yeniden deneyin.",
  legal_read: "Tüzel kişilik bilgileri şu anda yüklenemiyor. Lütfen yeniden deneyin.",
  legal_update: "Tüzel kişilik değişiklikleri kaydedilemedi. Lütfen yeniden deneyin.",
  branch_list: "Şube listesi şu anda yüklenemiyor. Lütfen yeniden deneyin.",
  branch_create: "Şube oluşturulamadı. Lütfen yeniden deneyin.",
  branch_update: "Şube değişiklikleri kaydedilemedi. Lütfen yeniden deneyin.",
  branch_archive: "Şube arşivlenemedi. Lütfen yeniden deneyin.",
  department_tree: "Departman hiyerarşisi şu anda yüklenemiyor. Lütfen yeniden deneyin.",
  department_history: "Departman arşiv geçmişi şu anda yüklenemiyor. Lütfen yeniden deneyin.",
  department_create: "Departman oluşturulamadı. Lütfen yeniden deneyin.",
  department_update: "Departman adı güncellenemedi. Lütfen yeniden deneyin.",
  department_move: "Departman taşınamadı. Lütfen yeniden deneyin.",
  department_archive: "Departman arşivlenemedi. Lütfen yeniden deneyin.",
};

export const LEGAL_ENTITY_STATUS_LABELS: Record<LegalEntityStatus, string> = {
  active: "Aktif",
  inactive: "Pasif",
};

export const BRANCH_STATUS_LABELS: Record<BranchStatus, string> = {
  active: "Aktif",
  archived: "Arşivlendi",
};

export const DEPARTMENT_STATUS_LABELS: Record<DepartmentStatus, string> = {
  active: "Aktif",
  archived: "Arşivlendi",
};

export function organizationErrorPresentation(
  cause: unknown,
  action: OrganizationAction,
): OrganizationErrorPresentation {
  if (!(cause instanceof ApiClientError)) {
    return { message: GENERIC_MESSAGES[action] };
  }

  let message = GENERIC_MESSAGES[action];
  if (cause.status === null || cause.code === "network_error") {
    message = "Sunucuya ulaşılamadı. Bağlantınızı kontrol edip yeniden deneyin.";
  } else if (cause.status === 401) {
    message = "Oturumunuz doğrulanamadı. Lütfen yeniden giriş yapın.";
  } else if (cause.status === 403) {
    message = action.endsWith("list") || action.endsWith("read")
      ? "Organizasyon bilgilerini görüntüleme yetkiniz bulunmuyor."
      : "Bu organizasyon değişikliğini yapma yetkiniz bulunmuyor.";
  } else if (
    cause.status === 404 &&
    cause.code === "organization_feature_unavailable"
  ) {
    message =
      "Organizasyon özelliği bu çalışma alanında artık etkin değil. " +
      "Yetkili ana sayfanıza dönüp yöneticinizle iletişime geçin.";
  } else if (cause.status === 404) {
    message = action.startsWith("legal_")
      ? "Tüzel kişilik bulunamadı veya artık erişim kapsamınızda değil."
      : action.startsWith("department_")
        ? "Departman bulunamadı veya artık erişim kapsamınızda değil."
        : "Şube bulunamadı veya artık erişim kapsamınızda değil.";
  } else if (cause.status === 409 && cause.code === "branch_code_conflict") {
    message =
      "Bu sabit kod tenant genelinde başka bir şube tarafından kullanılıyor. " +
      "Arşivlenmiş şube kodları da rezerve kalır ve yeniden kullanılamaz.";
  } else if (
    cause.status === 409 &&
    cause.code === "department_code_conflict"
  ) {
    message =
      "Bu sabit kod tenant genelinde başka bir departman tarafından kullanılıyor. " +
      "Arşivlenmiş departman kodları da rezerve kalır ve yeniden kullanılamaz.";
  } else if (
    cause.status === 409 &&
    cause.code === "organization_conflict" &&
    action === "legal_update"
  ) {
    message =
      "Tüzel kişilik pasifleştirilemedi. Varsayılan tüzel kişilik etkin kalmalıdır; " +
      "diğer tüzel kişiliklerin aktif şubelerini önce arşivleyin.";
  } else if (
    cause.status === 409 &&
    cause.code === "organization_conflict" &&
    action === "branch_create"
  ) {
    message =
      "Şube yalnızca etkin bir tüzel kişilik altında oluşturulabilir. " +
      "Tüzel kişiliği etkinleştirip yeniden deneyin.";
  } else if (
    cause.status === 409 &&
    cause.code === "organization_conflict" &&
    action === "branch_update"
  ) {
    message =
      "Arşivlenmiş şubeler değiştirilemez. Pencereyi kapatıp güncel kaydı " +
      "arşiv geçmişinden görüntüleyin.";
  } else if (
    cause.status === 409 &&
    cause.code === "organization_conflict" &&
    action === "branch_archive"
  ) {
    message =
      "Şubenin arşiv durumu değişmiş olabilir. Pencereyi kapatıp şube listesini yenileyin.";
  } else if (
    cause.status === 409 &&
    (cause.code === "department_cycle" ||
      cause.code === "department_cycle_conflict")
  ) {
    message =
      "Bu taşıma bir departmanı kendi altına bağlayacağı için yapılamaz. " +
      "Hiyerarşiyi yenileyip başka bir üst departman seçin.";
  } else if (
    cause.status === 409 &&
    cause.code === "organization_conflict" &&
    action === "department_create"
  ) {
    message =
      "Yeni departman yalnızca etkin bir üst departman altında oluşturulabilir. " +
      "Hiyerarşiyi yenileyip yeniden deneyin.";
  } else if (
    cause.status === 409 &&
    cause.code === "organization_conflict" &&
    action === "department_update"
  ) {
    message =
      "Arşivlenmiş departmanlar yeniden adlandırılamaz. Pencereyi kapatıp " +
      "güncel kaydı arşiv geçmişinden görüntüleyin.";
  } else if (
    cause.status === 409 &&
    cause.code === "organization_conflict" &&
    action === "department_move"
  ) {
    message =
      "Bu taşıma hiyerarşide döngü oluşturuyor olabilir veya seçilen üst departman " +
      "artık etkin değildir. Hiyerarşiyi yenileyip yeniden deneyin.";
  } else if (
    cause.status === 409 &&
    cause.code === "organization_conflict" &&
    action === "department_archive"
  ) {
    message =
      "Yalnızca etkin alt departmanı bulunmayan departmanlar arşivlenebilir. " +
      "Önce alt departmanları taşıyın veya arşivleyin.";
  } else if (cause.status === 409) {
    message = "Kayıt siz düzenlerken değişti. Sayfayı yenileyip yeniden deneyin.";
  } else if (cause.status === 422) {
    message = action.startsWith("department_")
      ? "Departman adı, sabit kodu ve üst departman seçimini kontrol edip yeniden deneyin."
      : "Alanları ve saat dilimi seçimini kontrol edip yeniden deneyin.";
  } else if (cause.status === 429) {
    message = "Çok sayıda istek gönderildi. Kısa bir süre bekleyip yeniden deneyin.";
  }

  return { message, reference: cause.correlationId };
}

export function formatOrganizationDate(value: string | null): string {
  if (!value) {
    return "—";
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return "—";
  }
  return new Intl.DateTimeFormat("tr-TR", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(date);
}

const FALLBACK_TIMEZONES = [
  "UTC",
  "Europe/Istanbul",
  "Europe/London",
  "Europe/Berlin",
  "Asia/Dubai",
] as const;

export function timezoneOptions(currentTimezone?: string): string[] {
  let values: string[];
  try {
    values = Intl.supportedValuesOf("timeZone");
  } catch {
    values = [...FALLBACK_TIMEZONES];
  }

  const timezones = new Set(["UTC", ...values]);
  if (currentTimezone) {
    timezones.add(currentTimezone);
  }
  return [...timezones].sort((left, right) => left.localeCompare(right, "tr-TR"));
}
