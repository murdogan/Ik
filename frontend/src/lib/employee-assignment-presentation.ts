import { ApiClientError } from "./api-client";
import type { EmployeeLifecycleStatus } from "./employee-assignments";

export type EmployeeAssignmentAction =
  | "options"
  | "history"
  | "create"
  | "change"
  | "team";

export interface EmployeeAssignmentErrorPresentation {
  message: string;
  reference?: string | null;
}

const GENERIC_MESSAGES: Record<EmployeeAssignmentAction, string> = {
  options: "Çalışan atama seçenekleri şu anda yüklenemiyor. Lütfen yeniden deneyin.",
  history: "Çalışanın atama geçmişi şu anda yüklenemiyor. Lütfen yeniden deneyin.",
  create: "Çalışan ataması oluşturulamadı. Lütfen yeniden deneyin.",
  change: "Atama değişikliği kaydedilemedi. Lütfen yeniden deneyin.",
  team: "Ekip listeniz şu anda yüklenemiyor. Lütfen yeniden deneyin.",
};

export const EMPLOYEE_STATUS_LABELS: Record<EmployeeLifecycleStatus, string> = {
  active: "Aktif",
  on_leave: "İzinli",
  terminated: "İşten ayrıldı",
};

export function employeeAssignmentErrorPresentation(
  cause: unknown,
  action: EmployeeAssignmentAction,
): EmployeeAssignmentErrorPresentation {
  if (!(cause instanceof ApiClientError)) {
    return { message: GENERIC_MESSAGES[action] };
  }

  let message = GENERIC_MESSAGES[action];
  if (cause.status === null || cause.code === "network_error") {
    message = "Sunucuya ulaşılamadı. Bağlantınızı kontrol edip yeniden deneyin.";
  } else if (cause.status === 401) {
    message = "Oturumunuz doğrulanamadı. Lütfen yeniden giriş yapın.";
  } else if (cause.status === 403) {
    message =
      action === "team"
        ? "Ekip görünümüne erişim yetkiniz bulunmuyor."
        : "Çalışan atamalarını yönetme yetkiniz bulunmuyor.";
  } else if (cause.status === 404) {
    message =
      action === "team"
        ? "Yönetici çalışan kaydınız bulunamadı veya artık erişim kapsamınızda değil."
        : "Çalışan ya da atama artık bu çalışma alanında bulunmuyor.";
  } else if (cause.status === 409) {
    message =
      cause.code.includes("archived") || cause.code.includes("inactive")
        ? "Seçilen organizasyon kaydı artık yeni atamaya açık değil. Seçenekleri yenileyin."
        : "Atama siz düzenlerken değişti. Geçmişi yenileyip yeniden deneyin.";
  } else if (cause.status === 422) {
    message =
      action === "change"
        ? "Yapı, yürürlük tarihi ve değişiklik nedenini kontrol edin."
        : "Çalışan, organizasyon yapısı ve yürürlük tarihini kontrol edin.";
  } else if (cause.status === 429) {
    message = "Çok sayıda istek gönderildi. Kısa bir süre bekleyip yeniden deneyin.";
  }

  return { message, reference: cause.correlationId };
}

export function formatAssignmentDate(value: string | null): string {
  if (!value) return "Devam ediyor";
  const date = new Date(`${value.slice(0, 10)}T00:00:00`);
  if (Number.isNaN(date.getTime())) return "—";
  return new Intl.DateTimeFormat("tr-TR", { dateStyle: "medium" }).format(date);
}
