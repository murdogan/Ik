import { ApiClientError } from "@/lib/api-client";
import type { Employee, EmployeeStatus } from "@/lib/employees";

export const EMPLOYEE_STATUS_LABELS: Record<EmployeeStatus, string> = {
  active: "Aktif",
  on_leave: "İzinli",
  terminated: "İşten ayrıldı",
};

export interface EmployeeErrorPresentation {
  message: string;
  reference?: string | null;
}

export type EmployeeAction = "list" | "read" | "create";

const GENERIC_MESSAGES: Record<EmployeeAction, string> = {
  list: "Çalışan listesi şu anda yüklenemiyor. Lütfen yeniden deneyin.",
  read: "Çalışan özeti şu anda yüklenemiyor. Lütfen yeniden deneyin.",
  create: "Çalışan kaydı şu anda oluşturulamadı. Lütfen yeniden deneyin.",
};

export function employeeErrorPresentation(
  cause: unknown,
  action: EmployeeAction,
): EmployeeErrorPresentation {
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
      action === "create"
        ? "Çalışan oluşturmak için gerekli İK yetkiniz bulunmuyor."
        : "Tenant çalışan kayıtlarını görüntüleme yetkiniz bulunmuyor.";
  } else if (cause.status === 404) {
    message = "Çalışan bulunamadı veya artık bu çalışma alanında değil.";
  } else if (cause.status === 409 && cause.code === "employee_number_conflict") {
    message = "Bu çalışan numarası çalışma alanında başka bir kayıtta kullanılıyor.";
  } else if (
    cause.status === 409 &&
    (cause.code === "employee_email_conflict" ||
      cause.code === "employee_work_email_conflict")
  ) {
    message = "Bu iş e-postası çalışma alanında başka bir çalışanda kullanılıyor.";
  } else if (cause.status === 409) {
    message = "Çalışan kaydı mevcut verilerle çakışıyor. Listeyi yenileyip tekrar deneyin.";
  } else if (cause.status === 422) {
    message =
      action === "create"
        ? "Çalışan numarası, ad, e-posta, durum ve başlangıç tarihini kontrol edin."
        : action === "list"
          ? "Filtre değerlerini kontrol edip yeniden deneyin."
          : "Çalışan bağlantısı geçerli değil. Dizine dönüp kaydı yeniden açın.";
  } else if (cause.status === 429) {
    message = "Çok sayıda istek gönderildi. Kısa bir süre bekleyip yeniden deneyin.";
  }

  return { message, reference: cause.correlationId };
}

export function employeeFullName(employee: Employee): string {
  return `${employee.first_name} ${employee.last_name}`.trim();
}

export function formatEmployeeDate(value: string | null): string {
  if (!value) return "—";
  const date = new Date(`${value.slice(0, 10)}T00:00:00`);
  if (Number.isNaN(date.getTime())) return "—";
  return new Intl.DateTimeFormat("tr-TR", { dateStyle: "medium" }).format(date);
}
