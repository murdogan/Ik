import { ApiClientError } from "@/lib/api-client";
import type { LeaveRequestStatus } from "@/lib/leave";

export const LEAVE_STATUS_LABELS: Record<LeaveRequestStatus, string> = {
  pending: "Değerlendirmede",
  approved: "Onaylandı",
  rejected: "Reddedildi",
  cancelled: "İptal edildi",
};

export interface LeaveErrorPresentation {
  message: string;
  reference: string | null;
  conflict: boolean;
}

export function leaveErrorPresentation(
  cause: unknown,
  fallback = "İzin işlemi şu anda tamamlanamıyor. Lütfen yeniden deneyin.",
): LeaveErrorPresentation {
  let message = fallback;
  let reference: string | null = null;
  let conflict = false;
  if (!(cause instanceof ApiClientError)) return { message, reference, conflict };
  reference = cause.correlationId;
  const code = cause.code.toLocaleLowerCase("en-US");
  if (cause.status === null || code === "network_error") {
    message = "Sunucuya ulaşılamadı. Bağlantınızı kontrol edip yeniden deneyin.";
  } else if (cause.status === 401) {
    message = "Oturumunuz doğrulanamadı. Lütfen yeniden giriş yapın.";
  } else if (cause.status === 403) {
    message = "Bu izin işlemi için gerekli yetkiniz veya güncel kapsamınız bulunmuyor.";
  } else if (cause.status === 404) {
    message = "Kayıt bulunamadı veya artık erişim kapsamınızda değil.";
  } else if (cause.status === 409) {
    conflict = true;
    message = code.includes("overlap")
      ? "Seçilen tarihler mevcut bir izin talebiyle çakışıyor. Güncel taleplerinizi kontrol edin."
      : code.includes("balance")
        ? "Kullanılabilir bakiye bu talep için yeterli değil. Güncel bakiyeyi yükleyin."
        : code.includes("version") || code.includes("transition") || code.includes("concurrent")
          ? "Kayıt siz işlem yaparken değişti. Güncel durumu yükleyip yeniden değerlendirin."
          : "İşlem güncel izin kurallarıyla tamamlanamadı. Tarihleri, bakiyeyi ve güncel kapsamı kontrol edin.";
  } else if (cause.status === 422) {
    if (code.includes("document")) {
      message = "Bu izin türü için geçerli bir belge yüklenmesi gerekiyor.";
    } else if (code.includes("employment")) {
      message = "İzin tarihleri etkin çalışma dönemi içinde olmalıdır.";
    } else if (code.includes("policy")) {
      message = "Bu tarihler için etkin bir izin politikası bulunmuyor.";
    } else if (code.includes("balance")) {
      message = "Kullanılabilir bakiye bu talep için yeterli değil.";
    } else {
      message = "Tarihleri, izin türünü ve zorunlu alanları kontrol edin.";
    }
  } else if (cause.status === 429) {
    message = "Çok sayıda istek gönderildi. Kısa bir süre bekleyip yeniden deneyin.";
  } else if (cause.status === 503) {
    message = "Belge veya izin hizmeti geçici olarak kullanılamıyor. Lütfen biraz sonra yeniden deneyin.";
  } else if (code === "invalid_response") {
    message = "Sunucudan beklenmeyen bir yanıt alındı. Ekrandaki veriler değiştirilmedi.";
  }
  return { message, reference, conflict };
}

export function formatLeaveDate(value: string): string {
  const date = new Date(`${value}T00:00:00`);
  if (!Number.isFinite(date.valueOf())) return "—";
  return new Intl.DateTimeFormat("tr-TR", { dateStyle: "medium" }).format(date);
}

export function formatLeaveTimestamp(value: string | null): string {
  if (!value) return "—";
  const date = new Date(value);
  if (!Number.isFinite(date.valueOf())) return "—";
  return new Intl.DateTimeFormat("tr-TR", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(date);
}

export function formatLeaveDays(value: number): string {
  return new Intl.NumberFormat("tr-TR", {
    maximumFractionDigits: 2,
    minimumFractionDigits: Number.isInteger(value) ? 0 : 1,
  }).format(value);
}

const TIMELINE_LABELS: Record<string, string> = {
  submitted: "Talep gönderildi",
  approved: "Talep onaylandı",
  rejected: "Talep reddedildi",
  cancelled: "Talep iptal edildi",
};

export function formatLeaveTimelineEvent(eventType: string): string {
  return TIMELINE_LABELS[eventType] ?? "Talep güncellendi";
}

const LEDGER_LABELS: Record<string, string> = {
  earned: "Kazanım",
  adjustment: "Düzeltme",
  planned: "Planlandı",
  planned_release: "Planlama serbest bırakıldı",
  used: "Kullanıldı",
  used_release: "Kullanım serbest bırakıldı",
};

export function formatLeaveLedgerEntry(entryType: string): string {
  return LEDGER_LABELS[entryType] ?? "Bakiye hareketi";
}

export function localDateValue(date = new Date()): string {
  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, "0");
  const day = String(date.getDate()).padStart(2, "0");
  return `${year}-${month}-${day}`;
}

export function commandKey(): string {
  return crypto.randomUUID();
}
